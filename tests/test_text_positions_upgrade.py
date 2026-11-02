"""
Open a v17 project with emoji through the real MainWindow and check the v18 position upgrade.
Run: python tests/test_text_positions_upgrade.py src
"""
import builtins
import os
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

from PyQt6 import QtWidgets  # noqa: E402

QAPP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
from qualcoder import error_dlg  # noqa: E402

error_dlg.ErrorDlg = lambda msg, tb: types.SimpleNamespace(exec=lambda: print("UNCAUGHT", msg, tb))
import qualcoder.__main__ as qm  # noqa: E402
from qualcoder import merge_projects  # noqa: E402

qm.Message = lambda *a, **k: types.SimpleNamespace(exec=lambda: None)
qm.MainWindow._offer_first_ai_setup = lambda self, *a, **k: None
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))


TEXT = "Hola 😀 familia 👨‍👩‍👧, cruzamos el río ❤️ y seguimos.\n"
app = qm.App()
win = qm.MainWindow(app, force_quit=True)

# build a v17 project by creating a fresh one and stripping the v18 column
proj = str(Path(HOME) / "legacy")
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (proj, "x"))
win.new_project()
path = win.app.project_path
cur = win.app.conn.cursor()
cur.execute("insert into source (id, name, fulltext, owner, date) values (1, 'e.txt', ?, 'x', '')", [TEXT])
cur.execute("insert into code_name (cid, name, owner, date, color) values (1, 'c', 'x', '', '#ffffff')")
probe = QtWidgets.QPlainTextEdit(TEXT)
qc = probe.document().find("cruzamos el río")
cur.execute("insert into code_text (cid, fid, seltext, pos0, pos1, owner, date) values (1, 1, ?, ?, ?, 'x', '')",
            [qc.selectedText(), qc.selectionStart(), qc.selectionEnd()])
qa = probe.document().find("seguimos")
cur.execute("insert into annotation (fid, pos0, pos1, memo, owner, date) values (1, ?, ?, 'n', 'x', '')",
            [qa.selectionStart(), qa.selectionEnd()])
win.app.conn.commit()
win.close_project()
con = sqlite3.connect(Path(path) / "data.qda")
con.execute("create table p2 as select databaseversion, date, memo, about, bookmarkfile, bookmarkpos, codername, "
            "recently_used_codes, avbookmarkfile, avbookmarkmsec, avbookmarktextpos from project")
con.execute("drop table project")
con.execute("alter table p2 rename to project")
con.execute("update project set databaseversion='v17'")
con.commit()
con.close()

# merge guard sees an unmigrated source with emoji
dest = str(Path(HOME) / "dest")
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (dest, "x"))
win.new_project()
merger = merge_projects.MergeProjects.__new__(merge_projects.MergeProjects)
merger.conn_s = sqlite3.connect(Path(path) / "data.qda")
merger.summary_msg = ""
merger.journals_s = []
ok = merge_projects.MergeProjects.get_source_data(merger)
check("merge refuses an unmigrated source with emoji", ok is False, merger.summary_msg)
merger.conn_s.close()
win.close_project()

# open the legacy project: v18 upgrade with backup
win.open_project(path)
cur = win.app.conn.cursor()
check("upgraded to v18", cur.execute("select databaseversion, position_units from project").fetchone() == ("v18", "codepoint"))
p0, p1 = cur.execute("select pos0, pos1 from code_text").fetchone()
check("coding converted to code points", TEXT[p0:p1] == "cruzamos el río", (p0, p1))
a0, a1 = cur.execute("select pos0, pos1 from annotation").fetchone()
check("annotation converted", TEXT[a0:a1] == "seguimos", (a0, a1))
backups = [p.name for p in Path(HOME).iterdir() if "_before_v18" in p.name]
check("backup taken before converting", len(backups) == 1, list(Path(HOME).iterdir()))
log = win.ui.textEdit.toPlainText()
check("action log reports the adjustment", "Text positions adjusted" in log)
win.close_project()
win.open_project(path)
p0b, p1b = win.app.conn.execute("select pos0, pos1 from code_text").fetchone()
check("reopening does not convert again", (p0b, p1b) == (p0, p1))
print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(RESULTS) else 1)
