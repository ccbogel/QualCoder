"""
End to end checks for text positions with emoji and other characters above U+FFFF.
Positions are stored as code points and converted only at the Qt editor.
Run: python tests/test_text_positions.py src
Every check prints PASS or FAIL. The exit code is 1 if anything failed.
"""
import builtins
import datetime
import os
import re
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="qc_home_")
os.environ["HOME"] = HOME
os.environ["QT_QPA_PLATFORM"] = "offscreen"
builtins._ = lambda s: s
sys.path.insert(0, sys.argv[1])

from PyQt6 import QtGui, QtWidgets  # noqa: E402

QAPP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])

from qualcoder import error_dlg  # noqa: E402
error_dlg.ErrorDlg = lambda msg, tb: types.SimpleNamespace(exec=lambda: print("UNCAUGHT", msg, tb))
import qualcoder.__main__ as qm  # noqa: E402
from qualcoder import helpers, code_text, code_av, case_file_manager, report_codes  # noqa: E402
from qualcoder.text_positions import to_qt, to_py, migrate_positions_to_code_points  # noqa: E402

silent = lambda *a, **k: types.SimpleNamespace(exec=lambda: None)  # noqa: E731
for mod in (qm, helpers, code_text, code_av, case_file_manager, report_codes):
    if hasattr(mod, "Message"):
        mod.Message = silent
QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.No)
QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: None)
QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))


TEXT = ("E: ¿Cómo llegaste? ✅ ok\n"
        "P: Con mi familia 👨‍👩‍👧, cruzamos el río ❤️ y luego 😀 seguimos.\n"
        "E: ¿Y después? 𝑥 matemática\n"
        "P: Trabajo en el campo 🇲🇽 desde enero.\n")

# --- unit conversion ---
for py in range(len(TEXT) + 1):
    assert to_py(TEXT, to_qt(TEXT, py)) == py
te_probe = QtWidgets.QPlainTextEdit(TEXT)
ok = True
for target in ("cruzamos el río", "Trabajo en el campo", "desde enero", "matemática"):
    c = te_probe.document().find(target)
    py = TEXT.index(target)
    ok &= to_py(TEXT, c.selectionStart()) == py and to_qt(TEXT, py) == c.selectionStart()
check("conversion matches Qt document find for every target", ok)
check("text without astral is identity", to_qt("hola ✅ mundo", 7) == 7 and to_py("hola ✅ mundo", 7) == 7)

# --- real project via MainWindow ---
qm.MainWindow._offer_first_ai_setup = lambda self, *a, **k: None
app = qm.App()
win = qm.MainWindow(app, force_quit=True)
proj = str(Path(HOME) / "emoji_test")
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (proj, "x"))
win.new_project()
app = win.app
cur = app.conn.cursor()
check("new project is v18 with code point units",
      cur.execute("select databaseversion, position_units from project").fetchone() == ("v18", "codepoint"))
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
cur.execute("insert into source (name, fulltext, mediapath, memo, owner, date) values (?,?,?,?,?,?)",
            ("entrevista.txt", TEXT, None, "", app.settings['codername'], now))
fid = cur.lastrowid
cur.execute("insert into code_name (name, memo, catid, owner, date, color) values (?,?,?,?,?,?)",
            ("trayecto", "", None, app.settings['codername'], now, "#F5A9A9"))
cid = cur.lastrowid
app.conn.commit()

# --- DialogCodeText: manual coding ---
dlg = code_text.DialogCodeText(app, win.ui.textEdit, win.ui.tab_reports)
f = next(x for x in dlg.files if x['id'] == fid)
dlg.load_file(f)


def select(widget, target):
    c = widget.document().find(target)
    widget.setTextCursor(c)


def select_code(dialog, code_id):
    it = QtWidgets.QTreeWidgetItemIterator(dialog.ui.treeWidget)
    while it.value():
        if it.value().text(1) == f"cid:{code_id}":
            dialog.ui.treeWidget.setCurrentItem(it.value())
            return True
        it += 1
    return False


check("code selected in tree", select_code(dlg, cid))
select(dlg.ui.plainTextEdit, "cruzamos el río")
dlg.mark()
row = cur.execute("select pos0, pos1, seltext from code_text where fid=? order by ctid desc limit 1", [fid]).fetchone()
check("manual mark stores code point positions", TEXT[row[0]:row[1]] == "cruzamos el río", row)
check("manual mark seltext matches slice", row[2] == "cruzamos el río", row)
sub = cur.execute("select substr(fulltext, ?, ?) from source where id=?", [row[0] + 1, row[1] - row[0], fid]).fetchone()[0]
check("SQLite substr agrees with stored positions", sub == "cruzamos el río", sub)

# highlight reads back the exact span
coded = next(c for c in dlg.code_text if c['pos0'] == row[0])
cursor = dlg.ui.plainTextEdit.textCursor()
cursor.setPosition(dlg.to_editor_pos(coded['pos0']))
cursor.setPosition(dlg.to_editor_pos(coded['pos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
check("editor span of stored coding is exact", cursor.selectedText() == "cruzamos el río", cursor.selectedText())
fmt_cursor = dlg.ui.plainTextEdit.textCursor()
fmt_cursor.setPosition(dlg.to_editor_pos(coded['pos0']) + 1)
fmt_before = dlg.ui.plainTextEdit.textCursor()
fmt_before.setPosition(dlg.to_editor_pos(coded['pos0']) - 1)
check("highlight starts at the coding, not before",
      fmt_cursor.charFormat().background().color().name() != fmt_before.charFormat().background().color().name())

# context menu helpers: unmark by cursor position after the emoji
inside = dlg.from_editor_pos(dlg.ui.plainTextEdit.document().find("el río").selectionStart())
hits = [c for c in dlg.code_text if c['pos0'] <= inside <= c['pos1']]
check("cursor position inside coding finds it", len(hits) == 1)

# --- Mark speakers style insertion (python positions) shows correctly ---
p0 = TEXT.index("Trabajo en el campo")
cur.execute("insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo) values (?,?,?,?,?,?,?,?)",
            (cid, fid, "Trabajo en el campo", p0, p0 + 19, app.settings['codername'], now, ""))
app.conn.commit()
dlg.load_file(f)
dlg.get_coded_text_update_eventfilter_tooltips()
c2 = next(c for c in dlg.code_text if c['pos0'] == p0)
cursor = dlg.ui.plainTextEdit.textCursor()
cursor.setPosition(dlg.to_editor_pos(c2['pos0']))
cursor.setPosition(dlg.to_editor_pos(c2['pos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
check("python positioned coding (speakers, pdf, autocode) shows exact", cursor.selectedText() == "Trabajo en el campo",
      cursor.selectedText())

# --- annotation via selection ---
select(dlg.ui.plainTextEdit, "seguimos")
code_text.DialogMemo = lambda *a, **k: types.SimpleNamespace(exec=lambda: True, memo="nota")
dlg.annotate()
an = cur.execute("select pos0, pos1 from annotation where fid=?", [fid]).fetchone()
check("annotation stored in code points", an and TEXT[an[0]:an[1]] == "seguimos", an)

# --- edit mode: paste emoji before a coding keeps it in place ---
dlg.edit_mode_on()
ed_cursor = dlg.ui.plainTextEdit.textCursor()
ed_cursor.setPosition(dlg.to_editor_pos(TEXT.index("E: ¿Y")))
ed_cursor.insertText("🙂 ")
QAPP.processEvents()
dlg.edit_mode_off()
new_text = cur.execute("select fulltext from source where id=?", [fid]).fetchone()[0]
r = cur.execute("select pos0, pos1 from code_text where fid=? and seltext=?", [fid, "Trabajo en el campo"]).fetchone()
check("edit mode: emoji inserted before coding keeps the segment", new_text[r[0]:r[1]] == "Trabajo en el campo",
      new_text[r[0]:r[1]])
TEXT2 = new_text

# --- search result navigation ---
dlg.search_term = "enero"
dlg.search_indices = [(f, m.start(), len(m.group(0))) for m in re.finditer("enero", TEXT2)]
dlg.search_index = 0
dlg.file_['start'] = 0
dlg.load_file(dlg.file_)
view_pos = dlg.search_indices[0][1]
sc = dlg.ui.plainTextEdit.textCursor()
sc.setPosition(dlg.to_editor_pos(view_pos))
sc.setPosition(dlg.to_editor_pos(view_pos + 5), QtGui.QTextCursor.MoveMode.KeepAnchor)
check("search result selection exact", sc.selectedText() == "enero", sc.selectedText())

# --- tooltip filter maps mouse position to code points ---
dlg.get_coded_text_update_eventfilter_tooltips()
check("tooltip filter has codings", len(dlg.eventFilterTT.code_text) > 0)

# --- coding margin spans in editor units ---
if getattr(dlg, "coding_margin", None) is not None:
    span = dlg.coding_margin._editor_span(c2 if c2 in dlg.code_text else dlg.code_text[0])
    sm = dlg.ui.plainTextEdit.textCursor()
    sm.setPosition(span[0])
    sm.setPosition(span[1], QtGui.QTextCursor.MoveMode.KeepAnchor)
    check("coding margin span is exact", sm.selectedText() in ("Trabajo en el campo", "cruzamos el río"), sm.selectedText())

# --- View in context dialog ---
r = cur.execute("select ctid, pos0, pos1 from code_text where fid=? and seltext=?", [fid, "Trabajo en el campo"]).fetchone()
data = {'codename': 'trayecto', 'color': '#F5A9A9', 'file_or_casename': 'entrevista.txt', 'pos0': r[1], 'pos1': r[2],
        'text': 'Trabajo en el campo', 'coder': 'x', 'fid': fid, 'file_or_case': 'File', 'ctid': r[0]}
ctx = helpers.DialogCodeInText(app, data)
c = ctx.te.textCursor()
c.setPosition(to_qt(TEXT2, r[1]) + 2)
check("View in context highlights the coding", c.charFormat().background().color().name().lower() == "#f5a9a9")
ctx.extend_right()
st = cur.execute("select seltext from code_text where ctid=?", [r[0]]).fetchone()[0]
check("extend right keeps seltext aligned", st == "Trabajo en el campo ", st)
ctx.shrink_to_left()

# --- report context (pretext / posttext) ---
rep = types.SimpleNamespace(app=app, results=[{'fid': fid, 'pos0': r[1], 'pos1': r[2]}])
report_codes.DialogReportCodes.get_pretext_and_posttext(rep)
check("report posttext starts right after coding", rep.results[0]['posttext'].startswith(" 🇲🇽 desde"),
      rep.results[0]['posttext'][:10])

# --- case file manager ---
cfm = case_file_manager.DialogCaseFileManager.__new__(case_file_manager.DialogCaseFileManager)
cfm.selected_text_file = [None] * 10
FT = case_file_manager.FULLTEXT
cfm.selected_text_file[FT] = TEXT2
check("case manager converts", cfm.from_editor_pos(cfm.to_editor_pos(TEXT2.index("desde"))) == TEXT2.index("desde"))

# --- code_av conversion helpers ---
av = types.SimpleNamespace(transcription=(fid, TEXT2, "t.txt"))
q = code_av.DialogCodeAV.to_editor_pos(av, TEXT2.index("desde"))
check("code_av helper converts", code_av.DialogCodeAV.from_editor_pos(av, q) == TEXT2.index("desde"))

# --- migration of a legacy project ---
legacy = sqlite3.connect(":memory:")
lc = legacy.cursor()
lc.execute("create table project (databaseversion text, date text, memo text,about text, bookmarkfile integer, "
           "bookmarkpos integer, codername text, recently_used_codes text, avbookmarkfile integer, "
           "avbookmarkmsec integer, avbookmarktextpos integer)")
lc.execute("create table source (id integer primary key, name text, fulltext text, mediapath text, av_text_id integer)")
lc.execute("create table code_text (ctid integer primary key, cid integer, fid integer, seltext text, pos0 integer, pos1 integer)")
lc.execute("create table annotation (anid integer primary key, fid integer, pos0 integer, pos1 integer)")
lc.execute("create table case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer)")
lc.execute("insert into source values (1, 'a', ?, null, null)", [TEXT])
lc.execute("insert into source values (2, 'plain', 'sin emojis aqui', null, null)")
probe = QtWidgets.QPlainTextEdit(TEXT)
expected = {}
for i, t in enumerate(("cruzamos el río", "Trabajo en el campo", "desde enero")):
    qc = probe.document().find(t)
    lc.execute("insert into code_text values (?,1,1,?,?,?)", [10 + i, qc.selectedText(), qc.selectionStart(), qc.selectionEnd()])
    m = re.search(re.escape(t), TEXT)
    lc.execute("insert into code_text values (?,1,1,?,?,?)", [20 + i, t, m.start(), m.end()])
    shift = sum(e2 - s2 for s2, e2 in [(e['match_start'], e['match_end']) for e in __import__('emoji').emoji_list(TEXT)
                                       if e['match_end'] < m.start()])
    lc.execute("insert into code_text values (?,1,1,?,?,?)", [30 + i, t, m.start() + shift, m.end() + shift])
    expected[t] = (m.start(), m.end())
lc.execute("insert into code_text values (99,1,2,'emojis',4,10)")
qa = probe.document().find("seguimos")
lc.execute("insert into annotation values (1, 1, ?, ?)", [qa.selectionStart(), qa.selectionEnd()])
lc.execute("insert into case_text values (1, 1, 1, 0, ?)", [len(TEXT)])
lc.execute("insert into case_text values (2, 1, 1, ?, ?)", [qa.selectionStart(), qa.selectionEnd()])
lc.execute("insert into project values ('v17','', '', '', 1, ?, 'x', '', null, null, null)", [qa.selectionStart()])
counts, unresolved = migrate_positions_to_code_points(legacy)
ok = True
for ctid, s0, s1, sel in lc.execute("select ctid, pos0, pos1, seltext from code_text where fid=1").fetchall():
    ok &= TEXT[s0:s1] == sel.replace(" ", "\n")
check("migration: manual, python and emoji-lib codings all land on their text", ok, counts)
check("migration: no unresolved codings", not unresolved, unresolved)
check("migration: file without emoji untouched",
      lc.execute("select pos0, pos1 from code_text where ctid=99").fetchone() == (4, 10))
a = lc.execute("select pos0, pos1 from annotation").fetchone()
check("migration: annotation converted", TEXT[a[0]:a[1]] == "seguimos", a)
check("migration: whole file case link kept", lc.execute("select pos1 from case_text where id=1").fetchone()[0] == len(TEXT))
b = lc.execute("select pos0, pos1 from case_text where id=2").fetchone()
check("migration: case link converted", TEXT[b[0]:b[1]] == "seguimos", b)
check("migration: bookmark converted", lc.execute("select bookmarkpos from project").fetchone()[0] == TEXT.index("seguimos"))
again = migrate_positions_to_code_points(legacy)[0]
check("migration of codings is idempotent", again["converted"] == 0 and again["relocated"] == 0,
      again)

print(f"\n{sum(r[1] for r in RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(r[1] for r in RESULTS) else 1)
