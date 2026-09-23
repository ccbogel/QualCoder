"""
GUI regression for the coding undo/redo: a real main window with a real project
database, the text coding dialog, the shared code tree controller and the Edit menu.
Runs offscreen. Every check prints PASS or FAIL; exit code 1 if anything failed.
Run: python tests/test_coding_undo_gui.py [path/to/src]
"""
import ast
import builtins
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

builtins._ = lambda s: s
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _find_source_root():
    candidates = []
    if len(sys.argv) > 1:
        candidates.append(Path(sys.argv[1]))
    if os.environ.get("QUALCODER_SRC"):
        candidates.append(Path(os.environ["QUALCODER_SRC"]))
    here = Path(__file__).resolve().parent
    candidates += [here, here / "src", here.parent, here.parent / "src"]
    for candidate in candidates:
        if (candidate / "qualcoder" / "coding_undo.py").is_file():
            return candidate
    sys.exit("Could not find qualcoder/coding_undo.py. Pass the src path as an argument.")


SRC = _find_source_root()
sys.path.insert(0, str(SRC))

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402
from qualcoder.app import App  # noqa: E402
from qualcoder.__main__ import MainWindow  # noqa: E402
from qualcoder.code_text import DialogCodeText  # noqa: E402

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name)


def create_project_database():
    """Build a project from the CREATE statements of MainWindow.new_project plus the views."""

    main_src = (SRC / "qualcoder" / "__main__.py").read_text()
    statements = []
    for node in ast.walk(ast.parse(main_src)):
        if isinstance(node, ast.FunctionDef) and node.name == "new_project":
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "execute" and call.args \
                        and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                    statements.append(call.args[0].value)
    project = Path(tempfile.mkdtemp()) / "undo_gui.qda"
    project.mkdir()
    conn = sqlite3.connect(str(project / "data.qda"))
    cur = conn.cursor()
    for sql in statements:
        if sql.lstrip().upper().startswith("CREATE"):
            cur.execute(sql)
    cur.execute("insert into project (databaseversion, date, memo, about, bookmarkfile, bookmarkpos, codername, "
                "recently_used_codes) values ('v11', '2026', '', 'QualCoder undo test', 0, 0, 'me', '')")
    cur.execute("insert into source (name, fulltext, mediapath, memo, owner, date) values ('undo.txt', ?, null, '', 'me', '2026')",
                ["The quick brown fox jumps over the lazy dog. " * 3])
    cur.execute("insert into code_name (name, memo, catid, owner, date, color) values ('fox', '', null, 'me', '2026', '#ff0000')")
    cur.execute("CREATE TABLE IF NOT EXISTS coder_names (name TEXT UNIQUE NOT NULL, "
                "visibility INTEGER NOT NULL DEFAULT 1 CHECK (visibility IN (0, 1)))")
    cur.execute("insert into coder_names (name, visibility) values ('me', 1)")
    app_src = (SRC / "qualcoder" / "app.py").read_text()
    for view in ("code_image_visible", "code_text_visible", "code_av_visible", "annotation_visible"):
        start = app_src.index(f"CREATE VIEW IF NOT EXISTS {view}")
        cur.execute(app_src[start:app_src.index('"""', start)])
    conn.commit()
    return project, conn


def pump(qapp, times=5):
    for _ in range(times):
        qapp.processEvents()


def select_code_item(tree):
    iterator = QtWidgets.QTreeWidgetItemIterator(tree)
    while iterator.value():
        item = iterator.value()
        if item.text(1).startswith("cid:"):
            tree.setCurrentItem(item)
            return item
        iterator += 1
    return None


def count(conn, table):
    return conn.execute(f"select count(*) from {table}").fetchone()[0]


qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
project, conn = create_project_database()
app = App()
app.settings['codername'] = 'me'
app.settings['ai_first_startup'] = 'False'  # no first-run dialog in a headless run
app.conn = conn
app.project_path = str(project)
app.project_name = project.name

window = MainWindow(app)
window.show_menu_options()
check("Edit menu offers only undo and redo",
      [a.text() for a in window.ui.menuEdit.actions()] == ["Undo coding", "Redo coding"])
check("undo disabled with empty history", not window.ui.actionUndo_coding.isEnabled())

dialog = DialogCodeText(app, window.ui.textEdit, window.ui.tab_reports)
window.tab_layout_helper(window.ui.tab_coding, dialog)
dialog.show()
pump(qapp)
dialog.load_file(dialog.files[0])
pump(qapp)
select_code_item(dialog.ui.treeWidget)
cursor = dialog.ui.plainTextEdit.textCursor()
cursor.setPosition(4)
cursor.setPosition(9, QtGui.QTextCursor.MoveMode.KeepAnchor)
dialog.ui.plainTextEdit.setTextCursor(cursor)
dialog.mark()
pump(qapp)
check("mark writes one coding", count(conn, "code_text") == 1 and len(dialog.code_text) == 1)
check("menu names the step", window.ui.actionUndo_coding.text() == "Undo Code 'fox' (undo.txt)"
      and window.ui.actionUndo_coding.isEnabled())

window.ui.actionUndo_coding.trigger()
pump(qapp)
check("undo removes the coding and refreshes the dialog", count(conn, "code_text") == 0 and len(dialog.code_text) == 0)
check("redo becomes available", window.ui.actionRedo_coding.isEnabled())
window.ui.actionRedo_coding.trigger()
pump(qapp)
check("redo restores the coding in database and dialog", count(conn, "code_text") == 1 and len(dialog.code_text) == 1)

# Ctrl+Z inside the editable text widget, which would otherwise swallow the key
dialog.ui.plainTextEdit.setFocus()
QtWidgets.QApplication.sendEvent(
    dialog.ui.plainTextEdit,
    QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier, "z"))
pump(qapp)
check("Ctrl+Z in the text widget undoes the coding", count(conn, "code_text") == 0 and len(dialog.code_text) == 0)
app.coding_undo.stack.redo()
pump(qapp)

# Delete the code through the shared tree controller, then undo it
with patch("qualcoder.code_tree.DialogConfirmDelete") as confirm:
    confirm.return_value.exec.return_value = True
    dialog.code_tree.delete_code(dialog.ui.treeWidget.currentItem())
pump(qapp)
check("delete code removes code and coding", count(conn, "code_name") == 0 and count(conn, "code_text") == 0)
check("menu names the delete step", window.ui.actionUndo_coding.text() == "Undo Delete code 'fox'")
window.ui.actionUndo_coding.trigger()
pump(qapp)
tree_names = [dialog.ui.treeWidget.topLevelItem(i).text(0) for i in range(dialog.ui.treeWidget.topLevelItemCount())]
check("undo delete restores code, coding and tree",
      count(conn, "code_name") == 1 and count(conn, "code_text") == 1 and tree_names == ["fox"] and len(dialog.code_text) == 1)

# Closing the project empties the history
app.coding_undo.clear()
pump(qapp)
check("clear disables undo and redo",
      not window.ui.actionUndo_coding.isEnabled() and not window.ui.actionRedo_coding.isEnabled())

failed = [name for name, passed in RESULTS if not passed]
print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
