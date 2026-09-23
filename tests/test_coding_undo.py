"""
Regression and safety suite for qualcoder/coding_undo.py.
Every check prints PASS or FAIL. The exit code is 1 if anything failed.
Run: python tests/test_coding_undo.py [path/to/src]
"""
import builtins
import os
import random
import sqlite3
import sys
import types
from pathlib import Path

builtins._ = lambda s: s  # coding_undo expects gettext to be installed
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _find_source_root():
    """Locate the qualcoder package: argv, then env, then the usual repo layout."""

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


sys.path.insert(0, str(_find_source_root()))

from PyQt6 import QtCore, QtWidgets  # noqa: E402
from qualcoder.coding_undo import CODE_TREE_TABLES, CodingUndoManager, undo_label  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
RESULTS = []

SCHEMA = [
    "CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, "
    "owner text, date text, av_text_id integer, risid integer, unique(name))",
    "CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, "
    "supercatid integer, unique(name))",
    "CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,"
    "date text, color text, supercid integer, unique(name))",
    "CREATE TABLE gr_cdct_text_item (gtextid integer primary key, grid integer, x integer, y integer, "
    "cid integer, catid integer, font_size integer, bold integer, isvisible integer, displaytext text)",
    "CREATE TABLE gr_cdct_line_item (glineid integer primary key, grid integer, fromcatid integer, "
    "fromcid integer, tocatid integer, tocid integer, color text, linewidth real, linetype text, isvisible integer)",
    "CREATE TABLE gr_free_line_item (gflineid integer primary key, grid integer, fromfreetextid integer, "
    "fromcatid integer, fromcid integer, fromimid integer, fromavid integer, fromcaseid integer, fromfileid integer, "
    "tofreetextid integer, tocatid integer, tocid integer, toimid integer, toavid integer, tocaseid integer, "
    "tofileid integer, color text, linewidth real, linetype text, isvisible integer)",
    "CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, "
    "pos1 integer, owner text, date text, memo text, avid integer, important integer, "
    "unique(cid,fid,pos0,pos1, owner))",
    "CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, "
    "height integer, cid integer, memo text, date text, owner text, important integer, pdf_page integer)",
    "CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, "
    "memo text, date text, owner text, important integer)",
]


class FakeBus:
    def __init__(self):
        self.events = []

    def emit_table_changes(self, tables, source=None):
        self.events.append((list(tables), source))


def make_app():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    for sql in SCHEMA:
        cur.execute(sql)
    cur.execute("insert into source (id, name, fulltext) values (1, 'one.txt', ?)", ["x" * 500])
    cur.execute("insert into source (id, name, fulltext) values (2, 'two.txt', ?)", ["y" * 500])
    cur.execute("insert into code_name (cid, name) values (10, 'fear')")
    cur.execute("insert into code_name (cid, name) values (11, 'hope')")
    conn.commit()
    app = types.SimpleNamespace(conn=conn, delete_backup=True, project_events=FakeBus())
    app.coding_undo = CodingUndoManager(app)
    return app


def check(name, condition):
    RESULTS.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name)


def table_rows(conn, table):
    cur = conn.cursor()
    cur.execute(f"select * from {table} order by 1")
    return cur.fetchall()


def pump():
    APP.processEvents()
    APP.processEvents()


# 1. Insert step: undo removes the row, redo brings it back with the same id
app = make_app()
undo = app.coding_undo
tok = undo.begin(undo_label("Code", "fear", "one.txt"), "code_text", 1)
app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                 "values (10,1,'xx',0,2,'me','d','',null)")
app.conn.commit()
check("insert step is pushed", undo.end(tok) is True)
check("insert step label", undo.stack.undoText() == "Code 'fear' (one.txt)")
undo.stack.undo()
check("undo insert removes row", table_rows(app.conn, "code_text") == [])
undo.stack.redo()
rows = table_rows(app.conn, "code_text")
check("redo insert restores row with same id", len(rows) == 1 and rows[0][0] == 1)
check("undo emits table change", app.project_events.events and app.project_events.events[-1][0] == ["code_text"])
check("undo marks backup as needed", app.delete_backup is False)

# 2. No change, no step
tok = undo.begin("nothing", "code_text", 1)
check("no diff means no step", undo.end(tok) is False and undo.stack.count() == 1)

# 3. Update step (memo) and delete step, then walk the whole history back and forth
tok = undo.begin("memo", "code_text", 1)
app.conn.execute("update code_text set memo='note' where ctid=1")
app.conn.commit()
undo.end(tok)
tok = undo.begin("unmark", "code_text", 1)
app.conn.execute("delete from code_text where ctid=1")
app.conn.commit()
undo.end(tok)
check("three steps recorded", undo.stack.count() == 3)
undo.stack.setIndex(0)
check("jump to start leaves table empty", table_rows(app.conn, "code_text") == [])
undo.stack.setIndex(2)
rows = table_rows(app.conn, "code_text")
check("jump forward restores memo", len(rows) == 1 and rows[0][8] == "note")
undo.stack.setIndex(3)
check("jump to end deletes again", table_rows(app.conn, "code_text") == [])

# 4. Scope: a change in another file is not swept into a file-scoped step
undo.clear()
tok = undo.begin("scoped", "code_text", 1)
app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                 "values (10,2,'yy',0,2,'me','d','',null)")
app.conn.commit()
check("other file ignored by scoped step", undo.end(tok) is False)
app.conn.execute("delete from code_text")
app.conn.commit()

# 5. Validation: a row changed elsewhere invalidates the history instead of being overwritten
undo.clear()
messages = []
undo.invalidated.connect(messages.append)
tok = undo.begin("code", "code_text", 1)
app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                 "values (10,1,'xx',0,2,'me','d','',null)")
app.conn.commit()
undo.end(tok)
app.conn.execute("update code_text set memo='changed elsewhere'")  # untracked change
app.conn.commit()
undo.stack.undo()
pump()
rows = table_rows(app.conn, "code_text")
check("stale undo writes nothing", len(rows) == 1 and rows[0][8] == "changed elsewhere")
check("stale undo clears history", undo.stack.count() == 0)
check("stale undo reports a message", len(messages) == 1)

# 6. Validation: reinserting a coding whose code was deleted is refused
app.conn.execute("delete from code_text")
app.conn.commit()
undo.clear()
messages.clear()
app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                 "values (11,1,'xx',5,7,'me','d','',null)")
app.conn.commit()
tok = undo.begin("unmark", "code_text", 1)
app.conn.execute("delete from code_text")
app.conn.commit()
undo.end(tok)
app.conn.execute("delete from code_name where cid=11")
app.conn.commit()
undo.stack.undo()
pump()
check("deleted code blocks reinsert", table_rows(app.conn, "code_text") == [])
check("deleted code clears history", undo.stack.count() == 0 and len(messages) == 1)
app.conn.execute("insert into code_name (cid, name) values (11, 'hope')")
app.conn.commit()

# 7. Merge: consecutive resizes of the same coding collapse into one step
undo.clear()
app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                 "values (10,1,'xxx',0,3,'me','d','',null)")
app.conn.commit()
for pos1 in (4, 5, 6):
    tok = undo.begin("resize", "code_text", 1, merge_key=("resize", 1))
    app.conn.execute("update code_text set pos1=? where ctid=1", [pos1])
    app.conn.commit()
    undo.end(tok)
check("resizes merged into one step", undo.stack.count() == 1)
undo.stack.undo()
check("merged undo restores first position", table_rows(app.conn, "code_text")[0][5] == 3)
undo.stack.redo()
check("merged redo restores last position", table_rows(app.conn, "code_text")[0][5] == 6)

# 8. Multi-table step with parent ordering (code_av before code_text)
undo.clear()
app.conn.execute("delete from code_text")
app.conn.commit()
tok = undo.begin("segment", ["code_av", "code_text"], 1)
app.conn.execute("insert into code_av (id,pos0,pos1,cid,memo,date,owner,important) values (1,0,100,10,'','d','me',null)")
app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important,avid) "
                 "values (10,1,'x',0,1,'me','d','',null,1)")
app.conn.commit()
undo.end(tok)
undo.stack.undo()
check("multi-table undo empties both", table_rows(app.conn, "code_av") == [] and table_rows(app.conn, "code_text") == [])
undo.stack.redo()
check("multi-table redo restores both", len(table_rows(app.conn, "code_av")) == 1 and len(table_rows(app.conn, "code_text")) == 1)

# 9. Random walk: any sequence of tracked operations must be exactly reversible
app = make_app()
undo = app.coding_undo
rng = random.Random(7)
history = [table_rows(app.conn, "code_text")]
for step in range(60):
    fid = rng.choice([1, 2])
    tok = undo.begin(f"step {step}", "code_text", rng.choice([fid, None]))
    cur = app.conn.cursor()
    cur.execute("select ctid from code_text where fid=?", [fid])
    ids = [r[0] for r in cur.fetchall()]
    op = rng.choice(["insert", "insert", "update", "delete"])
    if op == "insert" or not ids:
        p0 = rng.randrange(0, 400)
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                        "values (?,?,?,?,?,'me','d','',null)", (rng.choice([10, 11]), fid, "s", p0, p0 + 5))
        except sqlite3.IntegrityError:
            pass
    elif op == "update":
        cur.execute("update code_text set memo=? where ctid=?", (f"m{step}", rng.choice(ids)))
    else:
        cur.execute("delete from code_text where ctid=?", [rng.choice(ids)])
    app.conn.commit()
    if undo.end(tok):
        history.append(table_rows(app.conn, "code_text"))
    else:
        history[-1] = table_rows(app.conn, "code_text")
ok = True
for index in range(len(history) - 1, -1, -1):
    undo.stack.setIndex(index)
    if table_rows(app.conn, "code_text") != history[index]:
        ok = False
        break
check("random walk: every state reachable backwards", ok)
ok = True
for index in range(len(history)):
    undo.stack.setIndex(index)
    if table_rows(app.conn, "code_text") != history[index]:
        ok = False
        break
check("random walk: every state reachable forwards", ok)

# 10. Delete a code with codings, sub-code and graph node, then undo and redo
app = make_app()
undo = app.coding_undo
cur = app.conn.cursor()
cur.execute("insert into code_cat (catid, name) values (5, 'feelings')")
cur.execute("update code_name set catid=5 where cid=10")
cur.execute("insert into code_name (cid, name, supercid) values (12, 'dread', 10)")
cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) values (10,1,'a',0,1,'me','d','',null)")
cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) values (12,2,'b',0,1,'me','d','',null)")
cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,date,owner,important,pdf_page) values (1,0,0,5,5,10,'','d','me',null,0)")
cur.execute("insert into gr_cdct_text_item (grid, x, y, cid) values (1, 10, 10, 10)")
cur.execute("insert into gr_cdct_line_item (grid, fromcid, tocid) values (1, 10, 11)")
app.conn.commit()
full_before = {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES}
tok = undo.begin(undo_label("Delete code", "fear"), CODE_TREE_TABLES, code_ids=[10, 12])
for cid in (10, 12):
    cur.execute("delete from code_name where cid=?", [cid])
    cur.execute("delete from code_text where cid=?", [cid])
    cur.execute("delete from code_image where cid=?", [cid])
    cur.execute("delete from gr_cdct_text_item where cid=?", [cid])
    cur.execute("delete from gr_cdct_line_item where fromcid=? or tocid=?", [cid, cid])
app.conn.commit()
check("delete code is one step", undo.end(tok) is True and undo.stack.count() == 1)
full_after = {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES}
undo.stack.undo()
check("undo delete code restores every table", {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES} == full_before)
undo.stack.redo()
check("redo delete code removes every table row again", {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES} == full_after)
undo.stack.undo()

# 11. Merge code 10 into 11 with a duplicate coding and a sub-code, then undo and redo
cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) values (11,1,'a',0,1,'me','d','',null)")
app.conn.commit()
full_before = {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES}
tok = undo.begin(undo_label("Merge code", "fear") + " into 'hope'", CODE_TREE_TABLES, code_ids=[10, 11])
cur.execute("update code_name set memo='merged from fear' where cid=11")
cur.execute("select ctid from code_text where cid=10")
for (ctid,) in cur.fetchall():
    try:
        cur.execute("update code_text set cid=11 where ctid=?", [ctid])
    except sqlite3.IntegrityError:
        cur.execute("delete from code_text where ctid=?", [ctid])
cur.execute("update code_image set cid=11 where cid=10")
cur.execute("update code_name set supercid=11, catid=null where supercid=10")
cur.execute("delete from code_name where cid=10")
cur.execute("delete from gr_cdct_text_item where cid=10")
cur.execute("delete from gr_cdct_line_item where fromcid=10 or tocid=10")
app.conn.commit()
check("merge is one step", undo.end(tok) is True)
full_after = {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES}
check("merge removed the source code", not any(r[0] == 10 for r in full_after["code_name"]))
undo.stack.undo()
check("undo merge restores source code, codings, sub-code and memo",
      {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES} == full_before)
undo.stack.redo()
check("redo merge reapplies everything", {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES} == full_after)
undo.stack.undo()

# 12. Delete a category branch (category, its code, codings), then undo
full_before = {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES}
tok = undo.begin(undo_label("Delete category branch", "feelings"), CODE_TREE_TABLES, code_ids=[10, 12])
for cid in (10, 12):
    cur.execute("delete from code_text where cid=?", [cid])
    cur.execute("delete from code_image where cid=?", [cid])
    cur.execute("delete from code_name where cid=?", [cid])
    cur.execute("delete from gr_cdct_text_item where cid=?", [cid])
    cur.execute("delete from gr_cdct_line_item where fromcid=? or tocid=?", [cid, cid])
cur.execute("delete from code_cat where catid=5")
app.conn.commit()
undo.end(tok)
undo.stack.undo()
check("undo category branch restores category first, then codes and codings",
      {t: table_rows(app.conn, t) for t in CODE_TREE_TABLES} == full_before)

# 13. Undoing a code deletion is refused when its category was deleted elsewhere
messages = []
undo.invalidated.connect(messages.append)
cur.execute("update code_name set catid=5 where cid=12")
app.conn.commit()
tok = undo.begin("delete", CODE_TREE_TABLES, code_ids=[12])
cur.execute("delete from code_text where cid=12")
cur.execute("delete from code_name where cid=12")
app.conn.commit()
undo.end(tok)
cur.execute("update code_name set catid=null where cid=10")
cur.execute("delete from code_cat where catid=5")  # untracked change
app.conn.commit()
undo.stack.undo()
pump()
check("code without its category cannot come back unchecked",
      undo.stack.count() == 0 and messages and "category" in messages[0])

# 14. Nested begin/end inside one call chain folds into a single step
app = make_app()
undo = app.coding_undo

def helper_writes():
    tok = undo.begin("inner", "code_text", 1)
    app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                     "values (11,1,'in',10,12,'me','d','',null)")
    app.conn.commit()
    return undo.end(tok)

def outer_operation():
    tok = undo.begin("outer", "code_text", 1)
    app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important) "
                     "values (10,1,'out',0,2,'me','d','',null)")
    app.conn.commit()
    inner_pushed = helper_writes()
    return undo.end(tok), inner_pushed

outer_pushed, inner_pushed = outer_operation()
check("nested helper does not push its own step", inner_pushed is False)
check("outer step is pushed once with both rows", outer_pushed is True and undo.stack.count() == 1
      and undo.stack.undoText() == "outer")
undo.stack.undo()
check("undo of folded step removes both rows", table_rows(app.conn, "code_text") == [])
undo.stack.redo()

def abandoned_begin():
    undo.begin("abandoned", "code_text", 1)  # returns without end()

abandoned_begin()
tok = undo.begin("after stale", "code_text", 1)
check("stale outer token does not swallow later steps", tok is not None and not tok.nested)
app.conn.execute("delete from code_text")
app.conn.commit()
check("step after stale token is recorded", undo.end(tok) is True)

# 15. Per-table file scope: A/V file 1 with transcript file 2
tok = undo.begin("segment", ["code_av", "code_text"], file_id={"code_av": 1, "code_text": 2})
app.conn.execute("insert into code_av (id,pos0,pos1,cid,memo,date,owner,important) values (1,0,10,10,'','d','me',null)")
app.conn.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,date,memo,important,avid) "
                 "values (10,2,'t',0,1,'me','d','',null,1)")
app.conn.commit()
check("dict scope captures both tables", undo.end(tok) is True)
undo.stack.undo()
check("dict scope undo clears both", table_rows(app.conn, "code_av") == [] and table_rows(app.conn, "code_text") == [])

# 16. Snapshot of a table the project does not have yet is skipped, not fatal
app.conn.execute("drop table gr_free_line_item")
app.conn.commit()
tok = undo.begin("x", CODE_TREE_TABLES, code_ids=[10])
check("missing table skipped inside a multi-table step", tok is not None and len(tok.snapshots) == len(CODE_TREE_TABLES) - 1)
undo.end(tok)
app.conn.execute("drop table code_av")
app.conn.commit()
check("missing single table gives no token", undo.begin("x", "code_av", 1) is None)

failed = [name for name, passed in RESULTS if not passed]
print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
