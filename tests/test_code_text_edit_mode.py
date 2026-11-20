"""
Edit mode in Code text must track text changes only while editing.
Run: python tests/test_code_text_edit_mode.py src
Every check prints PASS or FAIL. The exit code is 1 if anything failed.
"""
import builtins
import datetime
import os
import sys
import tempfile
import types
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="qc_home_")
os.environ["HOME"] = HOME
os.environ["QT_QPA_PLATFORM"] = "offscreen"
builtins._ = lambda s: s
sys.path.insert(0, sys.argv[1])

from PyQt6 import QtWidgets  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

QAPP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
from qualcoder import error_dlg  # noqa: E402

error_dlg.ErrorDlg = lambda msg, tb: types.SimpleNamespace(exec=lambda: print("UNCAUGHT", msg, tb))
import qualcoder.__main__ as qm  # noqa: E402
from qualcoder import code_text, helpers  # noqa: E402

for mod in (qm, helpers, code_text):
    if hasattr(mod, "Message"):
        mod.Message = lambda *a, **k: types.SimpleNamespace(exec=lambda: None)
qm.MainWindow._offer_first_ai_setup = lambda self, *a, **k: None
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))


TEXT = "".join(f"Línea {i}: la familia cruzó el río y siguió en tren hasta la frontera.\n" for i in range(400))
app = qm.App()
win = qm.MainWindow(app, force_quit=True)
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(Path(HOME) / "edit_mode"), "x"))
win.new_project()
app = win.app
app.vectorstore_import_document = lambda *a, **k: None
cur = app.conn.cursor()
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
cur.execute("insert into source (name, fulltext, mediapath, memo, owner, date) values (?,?,?,?,?,?)",
            ["texto.txt", TEXT, None, "", app.settings['codername'], now])
fid = cur.lastrowid
cur.execute("insert into code_name (name, memo, catid, owner, date, color) values (?,?,?,?,?,?)",
            ["frontera", "", None, app.settings['codername'], now, "#F5A9A9"])
cid = cur.lastrowid
starts = [i for i in range(len(TEXT)) if TEXT.startswith("la frontera", i)]
for start in starts:
    cur.execute("insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo) values (?,?,?,?,?,?,?,?)",
                [cid, fid, "la frontera", start, start + len("la frontera"), app.settings['codername'], now, ""])
app.conn.commit()

dlg = code_text.DialogCodeText(app, win.ui.textEdit, win.ui.tab_reports)
f = next(x for x in dlg.files if x['id'] == fid)
dlg.load_file(f)
editor = dlg.ui.plainTextEdit
signal = editor.textChanged
# The test text has no emoji, so editor and stored positions agree without the emoji position fix
to_editor = getattr(dlg, "to_editor_pos", lambda pos: pos)
baseline = editor.receivers(signal)
calls = {'n': 0}
original_update = code_text.DialogCodeText.update_positions


def counting_update(self):
    calls['n'] += 1
    return original_update(self)


code_text.DialogCodeText.update_positions = counting_update
for session in range(3):
    dlg.edit_mode_toggle()
    check(f"session {session + 1}: one text change listener while editing", editor.receivers(signal) == baseline + 1,
          editor.receivers(signal) - baseline)
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    calls['n'] = 0
    editor.textCursor().insertText("x")
    QAPP.processEvents()
    check(f"session {session + 1}: one position update per keystroke", calls['n'] == 1, calls['n'])
    dlg.edit_mode_toggle()
    check(f"session {session + 1}: no listener left after editing", editor.receivers(signal) == baseline,
          editor.receivers(signal) - baseline)
calls['n'] = 0
dlg.load_file(dlg.file_)
dlg.highlight()
QAPP.processEvents()
check("highlighting outside edit mode does not run position updates", calls['n'] == 0, calls['n'])

# several fast edits, exit before the deferred repaint runs
dlg.edit_mode_toggle()
for pos in (0, 5000, 15000):
    cursor = editor.textCursor()
    cursor.setPosition(to_editor(pos))
    editor.setTextCursor(cursor)
    editor.textCursor().insertText("nuevo ")
QAPP.processEvents()
dlg.edit_mode_toggle()
QTest.qWait(500)
new_text = cur.execute("select fulltext from source where id=?", [fid]).fetchone()[0]
rows = cur.execute("select pos0, pos1 from code_text where fid=?", [fid]).fetchall()
check("fast edits then exit keep every coding on its text",
      len(rows) == len(starts) and all(new_text[a:b] == "la frontera" for a, b in rows),
      [new_text[a:b] for a, b in rows if new_text[a:b] != "la frontera"][:3])

# deferred repaint runs after a pause while still editing
dlg.edit_mode_toggle()
cursor = editor.textCursor()
cursor.setPosition(0)
editor.setTextCursor(cursor)
editor.textCursor().insertText("x")
QTest.qWait(600)
text_now = editor.toPlainText()
first = text_now.index("la frontera")
probe = editor.textCursor()
probe.setPosition(to_editor(first) + 2)
check("underlines repainted after a pause in typing", probe.charFormat().fontUnderline())
dlg.edit_mode_toggle()
code_text.DialogCodeText.update_positions = original_update

# changes from other dialogs while editing wait until edit mode ends
for round_no, tables in enumerate((["code_text"], ["code_name"], ["source"])):
    marker = f"EDITADO{round_no} "
    dlg.edit_mode_toggle()
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    editor.textCursor().insertText(marker)
    QAPP.processEvents()
    if tables == ["code_name"]:
        cur.execute("insert into code_name (name, memo, catid, owner, date, color) values (?,?,?,?,?,?)",
                    ["creado en otra ventana", "", None, app.settings['codername'], now, "#A9F5A9"])
        app.conn.commit()
    app.project_events.project_data_changed.emit(tables, None)
    QAPP.processEvents()
    check(f"event {tables} while editing keeps the typed text", editor.toPlainText().startswith(marker))
    dlg.edit_mode_toggle()
    saved = cur.execute("select fulltext from source where id=?", [fid]).fetchone()[0]
    check(f"event {tables} while editing: the edit is saved", saved.startswith(marker))
    if tables == ["code_name"]:
        names = [c['name'] for c in dlg.codes]
        check("change from another dialog is applied after leaving edit mode", "creado en otra ventana" in names)
check("no changes left pending after leaving edit mode", not getattr(dlg, "pending_project_changes", set()))

# closing the window while editing saves the edit
dlg.edit_mode_toggle()
cursor = editor.textCursor()
cursor.setPosition(0)
editor.setTextCursor(cursor)
editor.textCursor().insertText("CERRADO ")
QAPP.processEvents()
dlg.close()
QAPP.processEvents()
saved = cur.execute("select fulltext from source where id=?", [fid]).fetchone()[0]
rows = cur.execute("select pos0, pos1 from code_text where fid=?", [fid]).fetchall()
check("closing while editing saves the edit", saved.startswith("CERRADO "))
check("closing while editing keeps codings on their text", all(saved[a:b] == "la frontera" for a, b in rows))

print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(RESULTS) else 1)
