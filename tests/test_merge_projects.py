"""
Regression and safety suite for qualcoder/merge_projects.py.
Every check prints PASS or FAIL. The exit code is 1 if anything failed.
"""
import builtins
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import types
from contextlib import contextmanager
from pathlib import Path

builtins._ = lambda s: s  # merge_projects expects gettext to be installed
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
        if (candidate / "qualcoder" / "merge_projects.py").is_file():
            return candidate
    sys.exit("Could not find qualcoder/merge_projects.py. Pass the src path as an argument.")


sys.path.insert(0, str(_find_source_root()))

from PyQt6 import QtWidgets  # noqa: E402
from qualcoder import merge_projects  # noqa: E402

# Silence the modal message boxes
merge_projects.Message = lambda *a, **k: types.SimpleNamespace(exec=lambda: None)
APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
TMP = Path(tempfile.mkdtemp(prefix="qc_merge_tests_"))
RESULTS = []


@contextmanager
def expected_error():
    """Silence the traceback merge_projects logs on purpose during the failure tests."""

    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(logging.NOTSET)


SCHEMA = [
    "CREATE TABLE project (databaseversion text, date text, memo text,about text, bookmarkfile integer, "
    "bookmarkpos integer, codername text, recently_used_codes text, avbookmarkfile integer, "
    "avbookmarkmsec integer, avbookmarktextpos integer)",
    "CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, "
    "owner text, date text, av_text_id integer, risid integer, unique(name))",
    "CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, "
    "height integer, cid integer, memo text, date text, owner text, important integer, pdf_page integer)",
    "CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, "
    "memo text, date text, owner text, important integer)",
    "CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, "
    "owner text, date text, unique(fid,pos0,pos1,owner))",
    "CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, "
    "valuetype text)",
    "CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, "
    "date text, owner text, unique(name,attr_type,id))",
    "CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, "
    "owner text, date text, memo text)",
    "CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, "
    "constraint ucm unique(name))",
    "CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, "
    "supercatid integer, unique(name))",
    "CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, "
    "pos1 integer, owner text, date text, memo text, avid integer, important integer, "
    "unique(cid,fid,pos0,pos1, owner))",
    "CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,"
    "date text, color text, supercid integer, unique(name))",
    "CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text, unique(name))",
    "CREATE TABLE stored_sql (title text, description text, grouper text, ssql text, unique(title))",
]


class StubApp:
    def __init__(self, path):
        self.project_path = str(path)
        self.conn = sqlite3.connect(Path(path) / "data.qda")
        self.settings = {"codername": "tester", "ai_enable": "False",
                         "fontsize": 10, "font": "Noto Sans"}
        self.project_events = None
        self.delete_backup = True

    def save_backup(self, suffix):
        return f"backup{suffix}", "backup"


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print(("PASS  " if condition else "FAIL  ") + name + (f"   {detail}" if detail else ""))


def make(folder, rows, media=(), schema=None, project_row=True):
    folder = Path(folder)
    for sub in ("audio", "documents", "images", "video"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    for sub, fname, content in media:
        (folder / sub / fname).write_bytes(content)
    conn = sqlite3.connect(folder / "data.qda")
    cur = conn.cursor()
    for stmt in (schema or SCHEMA):
        cur.execute(stmt)
    if project_row:
        cur.execute("insert into project values(?,?,?,?,?,?,?,?,null,null,null)",
                    ("v17", "2026-08-24", "", "t", 0, 0, "tester", ""))
    for sql in rows:
        cur.execute(sql)
    conn.commit()
    conn.close()


def fresh(name):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    return path


def counts(conn):
    cur = conn.cursor()
    out = {}
    for table in ("source", "code_name", "code_cat", "code_text", "code_image", "code_av",
                  "annotation", "cases", "case_text", "journal", "stored_sql", "attribute_type"):
        cur.execute(f"select count(*) from {table}")
        out[table] = cur.fetchone()[0]
    return out


def sections_map(mp):
    return {s['title']: s['detail'] for s in mp.preview_sections}


# A rich source project used by several tests
RICH_SOURCE = [
    "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
    "values(1,'E01_Rosa.txt','texto de rosa aqui','/docs/E01_Rosa.txt','','t','d',null)",
    "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
    "values(4,'E02_Marta.pdf','texto del pdf','/docs/E02_Marta.pdf','','t','d',null)",
    "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
    "values(6,'foto.jpg',null,'/images/foto.jpg','','t','d',null)",
    "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
    "values(7,'sesion.mp3',null,'/audio/sesion.mp3','','t','d',1)",
    "insert into code_cat (catid,name,owner,date,memo,supercatid) values(2,'Cuidado','t','d','',null)",
    "insert into code_cat (catid,name,owner,date,memo,supercatid) values(3,'Apoyos','t','d','',2)",
    "insert into code_name (cid,name,memo,catid,owner,date,color,supercid) "
    "values(1,'Sobrecarga','',2,'t','d','#F44336',null)",
    "insert into code_name (cid,name,memo,catid,owner,date,color,supercid) "
    "values(2,'Red familiar','',3,'t','d','#2196F3',null)",
    "insert into code_name (cid,name,memo,catid,owner,date,color,supercid) "
    "values(3,'Hermana','',null,'t','d','#4CAF50',2)",
    "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
    "values(1,1,1,'texto',0,5,'t','d','',null,0)",
    "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
    "values(2,3,1,'de rosa',6,13,'t','d','',null,0)",
    "insert into code_av (avid,id,pos0,pos1,cid,memo,date,owner,important) values(9,7,1000,5000,1,'','d','t',0)",
    "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
    "values(3,1,1,'aqui',14,18,'t','d','',9,0)",
    "insert into code_image (imid,id,x1,y1,width,height,cid,memo,date,owner,important,pdf_page) "
    "values(1,4,10,10,50,50,1,'','d','t',0,0)",
    "insert into code_image (imid,id,x1,y1,width,height,cid,memo,date,owner,important,pdf_page) "
    "values(2,4,20,20,50,50,2,'','d','t',0,3)",
    "insert into code_image (imid,id,x1,y1,width,height,cid,memo,date,owner,important,pdf_page) "
    "values(3,6,5,5,30,30,2,'','d','t',0,null)",
    "insert into annotation (anid,fid,pos0,pos1,memo,owner,date) values(1,1,0,4,'nota','t','d')",
    "insert into cases (caseid,name,memo,owner,date) values(1,'Rosa','memo caso','t','d')",
    "insert into case_text (caseid,fid,pos0,pos1,owner,date,memo) values(1,1,0,18,'t','d','link memo')",
    "insert into journal (jid,name,jentry,date,owner) values(1,'Diario de campo','texto','d','t')",
    "insert into stored_sql (title,description,grouper,ssql) values('Consulta A','d','g','select 1')",
    "insert into attribute_type (name,date,owner,memo,caseOrFile,valuetype) "
    "values('Edad','d','t','','case','numeric')",
    "insert into attribute (attrid,name,attr_type,value,id,date,owner) values(1,'Edad','case','58',1,'d','t')",
]
RICH_MEDIA = [("documents", "E02_Marta.pdf", b"%PDF fake"),
              ("images", "foto.jpg", b"jpg"),
              ("audio", "sesion.mp3", b"mp3")]


# A1. The preview counts must equal what the merge actually inserts
def a1_preview_matches_reality():
    base = fresh("a1")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [
        # Destination shares one file and one code name, and holds one identical coding already
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(1,'E01_Rosa.txt','texto de rosa aqui','/docs/E01_Rosa.txt','','t','d',null)",
        "insert into code_name (cid,name,memo,catid,owner,date,color,supercid) "
        "values(1,'Sobrecarga','',null,'t','d','#F44336',null)",
        "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
        "values(1,1,1,'texto',0,5,'t','d','',null,0)",
    ])
    app = StubApp(base / "dst.qda")
    before = counts(app.conn)
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    after = counts(app.conn)
    sec = sections_map(mp)
    expected = {
        "source": "Files to add",
        "code_name": "Codes to add",
        "code_cat": "Code categories to add",
        "code_text": "Coded text segments to add",
        "code_av": "Coded audio/video segments to add",
        "annotation": "Text annotations to add",
        "cases": "Cases to add",
        "case_text": "Case file links to add",
        "journal": "Journals to add",
        "stored_sql": "Stored queries to add",
        "attribute_type": "Attribute types to add",
    }
    for table, title in expected.items():
        delta = after[table] - before[table]
        check(f"A1 preview matches inserted rows: {table}", delta == int(sec[title]),
              f"real {delta}, preview {sec[title]} ({title})")
    image_delta = after["code_image"] - before["code_image"]
    preview_images = int(sec["Coded PDF areas to add"]) + int(sec["Coded image areas to add"])
    check("A1 preview matches inserted rows: code_image", image_delta == preview_images,
          f"real {image_delta}, preview {preview_images}")
    check("A1 preview reports the coding already present",
          sec.get("Codings already in this project, not duplicated") == "1",
          f"got {sec.get('Codings already in this project, not duplicated')}")


# A2. Merging the same project twice must add nothing the second time
def a2_idempotent():
    base = fresh("a2")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    before = counts(app.conn)
    mp2 = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    after = counts(app.conn)
    changed = {t: (before[t], after[t]) for t in before if before[t] != after[t]}
    check("A2 second merge inserts nothing", not changed, f"{changed}")
    sec = sections_map(mp2)
    zeros = [t for t in ("Coded text segments to add", "Coded PDF areas to add", "Coded image areas to add",
                         "Coded audio/video segments to add", "Text annotations to add", "Files to add",
                         "Codes to add", "Cases to add") if sec[t] != "0"]
    check("A2 second preview shows nothing to add", not zeros, f"non zero: {zeros}")


# A3. Codings whose code or file is missing must not land as cid or fid -1
def a3_orphans():
    base = fresh("a3")
    make(base / "src.qda", [
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(1,'ok.txt','texto valido','/docs/ok.txt','','t','d',null)",
        "insert into code_name (cid,name,memo,catid,owner,date,color,supercid) "
        "values(1,'Bueno','',null,'t','d','#111',null)",
        # Coding on a code that does not exist
        "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
        "values(1,99,1,'texto',0,5,'t','d','',null,0)",
        # Coding on a file that does not exist
        "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
        "values(2,1,99,'texto',0,5,'t','d','',null,0)",
        "insert into code_image (imid,id,x1,y1,width,height,cid,memo,date,owner,important,pdf_page) "
        "values(1,99,0,0,10,10,1,'','d','t',0,2)",
        "insert into code_av (avid,id,pos0,pos1,cid,memo,date,owner,important) values(1,99,0,10,1,'','d','t',0)",
        "insert into annotation (anid,fid,pos0,pos1,memo,owner,date) values(1,99,0,4,'n','t','d')",
        # One good coding
        "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
        "values(3,1,1,'valido',6,12,'t','d','',null,0)",
    ])
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    cur = app.conn.cursor()
    bad = 0
    for table, cid_col, fid_col in (("code_text", "cid", "fid"), ("code_image", "cid", "id"),
                                    ("code_av", "cid", "id")):
        cur.execute(f"select count(*) from {table} where {cid_col}=-1 or {fid_col}=-1")
        bad += cur.fetchone()[0]
    cur.execute("select count(*) from annotation where fid=-1")
    bad += cur.fetchone()[0]
    check("A3 no coding rows with cid or fid -1", bad == 0, f"{bad} bad rows")
    cur.execute("select count(*) from code_text")
    check("A3 the valid coding is still merged", cur.fetchone()[0] == 1)
    check("A3 orphans reported in the summary", "Codings skipped" in mp.summary_msg)
    check("A3 orphans flagged in the preview",
          sections_map(mp).get("Codings skipped, missing code or file in the source project") == "5",
          str(sections_map(mp).get("Codings skipped, missing code or file in the source project")))


# A4. A folder without data.qda must not crash and must not create a database there
def a4_not_a_project():
    base = fresh("a4")
    (base / "src.qda").mkdir(parents=True)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    check("A4 no crash on a folder without a project", mp.projects_merged is False)
    check("A4 no database created in the source folder", not (base / "src.qda" / "data.qda").exists())


# A5. An unreadable or empty project database must be refused
def a5_empty_project_table():
    base = fresh("a5")
    make(base / "src.qda", [], project_row=False)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    before = counts(app.conn)
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    check("A5 empty project table refused", mp.projects_merged is False)
    check("A5 nothing written", counts(app.conn) == before)
    check("A5 reason in the summary", "Could not read" in mp.summary_msg)


# A6. Old database versions must still be refused with the upgrade message
def a6_old_version():
    base = fresh("a6")
    make(base / "src.qda", [], project_row=False)
    conn = sqlite3.connect(base / "src.qda" / "data.qda")
    conn.execute("insert into project values(?,?,?,?,?,?,?,?,null,null,null)",
                 ("v4", "2026-08-24", "", "t", 0, 0, "tester", ""))
    conn.commit()
    conn.close()
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    check("A6 pre v5 project refused", mp.projects_merged is False)
    check("A6 upgrade message shown", "update the source project" in mp.summary_msg)


# A7. Case data carried across, and case attribute placeholders typed as case
def a7_case_data():
    base = fresh("a7")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [
        # Destination already has a case attribute type, which triggers the placeholder path
        "insert into attribute_type (name,date,owner,memo,caseOrFile,valuetype) "
        "values('Zona','d','t','','case','character')",
    ])
    app = StubApp(base / "dst.qda")
    merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    cur = app.conn.cursor()
    cur.execute("select owner, date, memo from case_text")
    row = cur.fetchone()
    check("A7 case link keeps owner, date and memo", row == ('t', 'd', 'link memo'), str(row))
    cur.execute("select attr_type from attribute where name='Zona'")
    types_ = [r[0] for r in cur.fetchall()]
    check("A7 case attribute placeholder typed as case", types_ == ['case'], str(types_))
    cur.execute("select value from attribute where name='Edad' and attr_type='case'")
    val = cur.fetchone()
    check("A7 case attribute value carried across", val is not None and val[0] == '58', str(val))


# A8. Sub-codes, categories and the transcript link survive the merge
def a8_structure():
    base = fresh("a8")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    cur = app.conn.cursor()
    cur.execute("select cid from code_name where name='Red familiar'")
    parent = cur.fetchone()[0]
    cur.execute("select supercid from code_name where name='Hermana'")
    check("A8 sub-code keeps its parent", cur.fetchone()[0] == parent)
    cur.execute("select catid from code_cat where name='Cuidado'")
    parent_cat = cur.fetchone()[0]
    cur.execute("select supercatid from code_cat where name='Apoyos'")
    check("A8 sub-category keeps its parent", cur.fetchone()[0] == parent_cat)
    cur.execute("select id from source where name='E01_Rosa.txt'")
    transcript = cur.fetchone()[0]
    cur.execute("select av_text_id from source where name='sesion.mp3'")
    check("A8 A/V transcript link rebuilt", cur.fetchone()[0] == transcript)
    cur.execute("select avid from code_av")
    av = cur.fetchone()[0]
    cur.execute("select avid from code_text where pos0=14")
    check("A8 transcript coding still points at its A/V segment", cur.fetchone()[0] == av)
    cur.execute("select pdf_page from code_image where pdf_page is not null order by pdf_page")
    check("A8 PDF pages preserved", [r[0] for r in cur.fetchall()] == [0, 3])


# A9. Existing media files are never overwritten, and the source db is closed
def a9_files_and_handles():
    base = fresh("a9")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [], media=[("documents", "E02_Marta.pdf", b"ORIGINAL DEL DESTINO")])
    app = StubApp(base / "dst.qda")
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    kept = (base / "dst.qda" / "documents" / "E02_Marta.pdf").read_bytes()
    check("A9 existing file not overwritten", kept == b"ORIGINAL DEL DESTINO", str(kept))
    check("A9 other files copied", (base / "dst.qda" / "images" / "foto.jpg").exists())
    check("A9 source database closed after merge", mp.conn_s is None)
    check("A9 source project files untouched",
          (base / "src.qda" / "documents" / "E02_Marta.pdf").read_bytes() == b"%PDF fake")


# A10. Names with quotes and accents must survive
def a10_unicode_and_quotes():
    base = fresh("a10")
    make(base / "src.qda", [
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(1,'Entrevista ''Doña Rosa''.txt','texto','/docs/x.txt','','t','d',null)",
        "insert into code_name (cid,name,memo,catid,owner,date,color,supercid) "
        "values(1,'Acompañamiento ''cercano''','',null,'t','d','#111',null)",
        "insert into code_text (ctid,cid,fid,seltext,pos0,pos1,owner,date,memo,avid,important) "
        "values(1,1,1,'texto',0,5,'t','d','',null,0)",
    ])
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    cur = app.conn.cursor()
    cur.execute("select name from code_name")
    check("A10 code name with accents and quotes merged",
          cur.fetchone()[0] == "Acompañamiento 'cercano'")
    cur.execute("select count(*) from code_text")
    check("A10 its coding merged", cur.fetchone()[0] == 1)
    check("A10 preview lists the name",
          "Acompañamiento 'cercano'" in [i for s in mp.preview_sections for i in s['items']])


# A11. Attribute values do not overwrite existing non blank values
def a11_attribute_values():
    base = fresh("a11")
    make(base / "src.qda", [
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(1,'comun.txt','texto','/docs/comun.txt','','t','d',null)",
        "insert into attribute_type (name,date,owner,memo,caseOrFile,valuetype) "
        "values('Sitio','d','t','','file','character')",
        "insert into attribute (attrid,name,attr_type,value,id,date,owner) values(1,'Sitio','file','Mazatlan',1,'d','t')",
    ])
    make(base / "dst.qda", [
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(1,'comun.txt','texto','/docs/comun.txt','','t','d',null)",
        "insert into attribute_type (name,date,owner,memo,caseOrFile,valuetype) "
        "values('Sitio','d','t','','file','character')",
        "insert into attribute (attrid,name,attr_type,value,id,date,owner) values(1,'Sitio','file','Culiacan',1,'d','t')",
    ])
    app = StubApp(base / "dst.qda")
    merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    cur = app.conn.cursor()
    cur.execute("select value from attribute where name='Sitio'")
    check("A11 existing attribute value not overwritten", cur.fetchone()[0] == 'Culiacan')


# A12. Cancelling from the dialog closes the source database and writes nothing
def a12_cancel_releases():
    base = fresh("a12")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")

    class CancelDialog:
        def __init__(self, app_, sections, path_s_, parent=None):
            pass

        def exec(self):
            return 0

        def save_to_journal(self):
            return False

    original = merge_projects.DialogMergePreview
    merge_projects.DialogMergePreview = CancelDialog
    before = counts(app.conn)
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"))
    merge_projects.DialogMergePreview = original
    check("A12 cancel writes nothing", counts(app.conn) == before)
    check("A12 cancel closes the source database", mp.conn_s is None)
    check("A12 cancel copies no files", not (base / "dst.qda" / "images" / "foto.jpg").exists())



# A13. Very large lists are capped in the tree and the journal entry, counts stay complete
def a13_large_lists():
    base = fresh("a13")
    rows = []
    for i in range(1, 461):
        rows.append(f"insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
                    f"values({i},'f{i:04}.txt','texto','/docs/f{i:04}.txt','','t','d',null)")
    make(base / "src.qda", rows)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    app.settings.update({"fontsize": 10, "font": "Noto Sans"})
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    files_section = next(s for s in mp.preview_sections if s['title'] == "Files to add")
    check("A13 count is complete", files_section['detail'] == "460", files_section['detail'])
    check("A13 listed names are capped", len(files_section['items']) == 201,
          f"{len(files_section['items'])} rows listed")
    check("A13 cap line states the remainder", "260" in files_section['items'][-1],
          files_section['items'][-1])
    dlg = merge_projects.DialogMergePreview(app, mp.preview_sections, str(base / "src.qda"))
    check("A13 dialog builds with the capped list", dlg.tree.topLevelItemCount() == len(mp.preview_sections))
    dlg.close()




def _progress_stub(fail_at, phase_label=None):
    """Progress that raises MergeCancelled at the nth tick, or on a named phase."""

    state = {'ticks': 0}

    class Stub:
        def __init__(self, app_, parent=None):
            pass

        def phase(self, label, value, repaint=True):
            if phase_label is not None and label == phase_label:
                raise merge_projects.MergeCancelled()

        def tick(self, index, total, base, span, every=100):
            state['ticks'] += 1
            if fail_at is not None and state['ticks'] >= fail_at:
                raise merge_projects.MergeCancelled()

        def check(self):
            pass

        def hide(self):
            pass

        def restart(self):
            pass

        def close(self):
            pass

    return Stub, state


# B1. Cancelling while files are copied leaves nothing behind
def b1_cancel_during_copy():
    base = fresh("b1")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    before = counts(app.conn)
    stub, _state = _progress_stub(fail_at=2)
    original = merge_projects.MergeProgress
    merge_projects.MergeProgress = stub
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProgress = original
    check("B1 cancel during copy writes nothing", counts(app.conn) == before)
    left = [p.name for p in (base / "dst.qda").rglob("*") if p.is_file() and p.name != "data.qda"]
    check("B1 copied files removed again", not left, f"left behind: {left}")
    check("B1 flagged as cancelled", mp.merge_cancelled is True)
    check("B1 source database closed", mp.conn_s is None)


# B2. Cancelling mid insert rolls the whole merge back
def b2_cancel_during_insert():
    base = fresh("b2")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    before = counts(app.conn)
    stub, _state = _progress_stub(fail_at=None, phase_label="Merging coded text")
    original = merge_projects.MergeProgress
    merge_projects.MergeProgress = stub
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProgress = original
    after = counts(app.conn)
    changed = {t: (before[t], after[t]) for t in before if before[t] != after[t]}
    check("B2 cancel mid merge rolls everything back", not changed, f"{changed}")
    left = [p.name for p in (base / "dst.qda").rglob("*") if p.is_file() and p.name != "data.qda"]
    check("B2 copied files removed again", not left, f"left behind: {left}")
    check("B2 flagged as cancelled", mp.merge_cancelled is True)
    check("B2 not reported as merged", mp.projects_merged is False)


# B3. A database error rolls back instead of leaving a half merged project
def b3_error_rolls_back():
    base = fresh("b3")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    before = counts(app.conn)
    original = merge_projects.MergeProjects.insert_cases

    def boom(self):
        raise sqlite3.OperationalError("simulated failure")

    merge_projects.MergeProjects.insert_cases = boom
    with expected_error():
        mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProjects.insert_cases = original
    check("B3 error rolls everything back", counts(app.conn) == before,
          str({t: (before[t], counts(app.conn)[t]) for t in before if before[t] != counts(app.conn)[t]}))
    check("B3 not reported as merged", mp.projects_merged is False)
    check("B3 failure reported", "Merge failed" in mp.summary_msg)


# B4. The whole merge is one transaction, invisible to other readers until it commits
def b4_single_transaction():
    base = fresh("b4")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    observed = {}
    reader = sqlite3.connect(base / "dst.qda" / "data.qda", timeout=0.2)

    class Watcher:
        def __init__(self, app_, parent=None):
            pass

        def phase(self, label, value, repaint=True):
            if label == "Merging coded image and PDF areas":
                try:
                    cur = reader.cursor()
                    cur.execute("select count(*) from code_text")
                    observed['code_text'] = cur.fetchone()[0]
                except sqlite3.Error as err:
                    observed['error'] = str(err)

        def tick(self, *a, **k):
            pass

        def check(self):
            pass

        def hide(self):
            pass

        def restart(self):
            pass

        def close(self):
            pass

    original = merge_projects.MergeProgress
    merge_projects.MergeProgress = Watcher
    merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProgress = original
    check("B4 uncommitted work is not visible to another reader",
          observed.get('code_text') == 0 or 'error' in observed, str(observed))
    reader.close()
    cur = app.conn.cursor()
    cur.execute("select count(*) from code_text")
    check("B4 committed after the merge", cur.fetchone()[0] == 3)


# B5. The progress helper is inert when there is no application
def b5_progress_headless():
    prog = merge_projects.MergeProgress.__new__(merge_projects.MergeProgress)
    prog.dialog = None
    prog.phase("x", 1)
    prog.tick(0, 10, 0, 10)
    prog.check()
    prog.hide()
    prog.restart()
    prog.close()
    check("B5 progress helper is inert without a dialog", True)




# C1. The progress dialog must come back after being hidden for the preview
def c1_progress_returns_after_hide():
    import time
    stub_app = types.SimpleNamespace(settings={"fontsize": 10, "font": "Noto Sans"})
    prog = merge_projects.MergeProgress(stub_app)
    prog.phase("reading", 2)
    time.sleep(0.6)
    prog.phase("preview", 10)
    check("C1 dialog shows during a slow read", prog.dialog.isVisible())
    prog.hide()
    prog.restart()
    time.sleep(0.6)
    prog.phase("copying", 15)
    time.sleep(0.6)
    prog.phase("merging", 40)
    APP.processEvents()
    check("C1 dialog returns for the merge phase", prog.dialog.isVisible())
    check("C1 cancel flag cleared by restart", not prog.dialog.wasCanceled())
    prog.close()


# C2. The merge must not run on the shared app connection
def c2_own_connection():
    base = fresh("c2")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    seen = {}

    class Watcher:
        def __init__(self, app_, parent=None):
            pass

        def phase(self, label, value, repaint=True):
            if label == "Merging coded text":
                seen['conn_is_shared'] = MERGE_HOLDER[0].conn_d is app.conn

        def tick(self, *a, **k):
            pass

        def check(self):
            pass

        def hide(self):
            pass

        def restart(self):
            pass

        def close(self):
            pass

    original = merge_projects.MergeProgress
    merge_projects.MergeProgress = Watcher
    MERGE_HOLDER[0] = merge_projects.MergeProjects.__new__(merge_projects.MergeProjects)
    mp = MERGE_HOLDER[0]
    mp.__init__(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProgress = original
    check("C2 merge uses its own connection", seen.get('conn_is_shared') is False, str(seen))
    check("C2 connections released", mp.conn_d is None and mp.conn_s is None)
    cur = app.conn.cursor()
    cur.execute("select count(*) from code_text")
    check("C2 shared connection sees the committed merge", cur.fetchone()[0] == 3)


# C3. A pending write on the shared connection survives a cancelled merge
def c3_other_writes_survive_rollback():
    base = fresh("c3")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    # Another dialog writes and commits on the shared connection before the merge starts
    cur = app.conn.cursor()
    cur.execute("insert into journal (name,jentry,date,owner) values('otro diario','texto','d','t')")
    app.conn.commit()
    stub, _state = _progress_stub(fail_at=None, phase_label="Merging coded text")
    original = merge_projects.MergeProgress
    merge_projects.MergeProgress = stub
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProgress = original
    cur.execute("select name from journal")
    names = [r[0] for r in cur.fetchall()]
    check("C3 the other dialog's row survives the rollback", names == ['otro diario'], str(names))
    check("C3 merge rolled back", mp.merge_cancelled is True)


# C4. Any unexpected error rolls back and releases everything
def c4_unexpected_error():
    base = fresh("c4")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    before = counts(app.conn)
    original = merge_projects.MergeProjects.insert_categories

    def boom(self):
        raise ValueError("not a database error")

    merge_projects.MergeProjects.insert_categories = boom
    with expected_error():
        mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProjects.insert_categories = original
    check("C4 non database error rolls back", counts(app.conn) == before)
    check("C4 connections released", mp.conn_d is None and mp.conn_s is None)
    check("C4 progress dialog closed", mp.progress.dialog is None)
    check("C4 failure reported", "Merge failed" in mp.summary_msg)
    left = [q.name for q in (base / "dst.qda").rglob("*") if q.is_file() and q.name != "data.qda"]
    check("C4 copied files removed", not left, str(left))


# C5. A failing vectorstore update must not lose a committed merge
def c5_vectorstore_failure():
    base = fresh("c5")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    app.settings["ai_enable"] = "True"

    class BadAi:
        @property
        def sources_vectorstore(self):
            raise RuntimeError("vectorstore unavailable")

    app.ai = BadAi()
    with expected_error():
        mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    check("C5 merge still reported as merged", mp.projects_merged is True)
    cur = app.conn.cursor()
    cur.execute("select count(*) from code_text")
    check("C5 merge data committed", cur.fetchone()[0] == 3)
    check("C5 vectorstore problem reported", "vectorstore" in mp.summary_msg)
    check("C5 progress dialog closed", mp.progress.dialog is None)


# C6. A folder that is not a project must release the dialog too
def c6_not_a_project_releases():
    base = fresh("c6")
    (base / "src.qda").mkdir(parents=True)
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    check("C6 progress dialog closed", mp.progress.dialog is None)
    check("C6 attributes present for the caller",
          mp.projects_merged is False and mp.merge_cancelled is False and mp.copied_files == [])




# D1. Document text is fetched at insert time, not held for every file
def d1_text_not_held_in_memory():
    base = fresh("d1")
    texto = "Rosa dijo que el cuidado la desborda. " * 50
    make(base / "src.qda", [
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        f"values(1,'larga.txt','{texto}','/docs/larga.txt','','t','d',null)",
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(2,'video.mp4',null,'/video/video.mp4','','t','d',null)",
    ])
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    check("D1 source rows carry the length, not the text",
          all('fulltext' not in src and 'fulltext_len' in src for src in mp.source_s))
    check("D1 length recorded for the text file",
          mp.source_s[0]['fulltext_len'] == len(texto), str(mp.source_s[0]['fulltext_len']))
    check("D1 media file has no length", mp.source_s[1]['fulltext_len'] is None)
    cur = app.conn.cursor()
    cur.execute("select fulltext from source where name='larga.txt'")
    check("D1 the full text is still merged intact", cur.fetchone()[0] == texto)
    cur.execute("select fulltext from source where name='video.mp4'")
    check("D1 media file keeps a null text", cur.fetchone()[0] is None)


# D2. Cancelling inside a large file leaves no partial copy
def d2_cancel_inside_large_file():
    base = fresh("d2")
    big = b"0" * (30 * 1024 * 1024)  # 30 MB, several chunks
    make(base / "src.qda", [
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(1,'grande.mp4',null,'/video/grande.mp4','','t','d',null)",
    ], media=[("video", "grande.mp4", big)])
    make(base / "dst.qda", [])
    app = StubApp(base / "dst.qda")
    state = {'checks': 0}

    class ChunkCanceller:
        def __init__(self, app_, parent=None):
            pass

        def phase(self, label, value, repaint=True):
            pass

        def tick(self, *a, **k):
            pass

        def check(self):
            state['checks'] += 1
            if state['checks'] >= 2:  # Part way through the file
                raise merge_projects.MergeCancelled()

        def hide(self):
            pass

        def restart(self):
            pass

        def close(self):
            pass

    original = merge_projects.MergeProgress
    merge_projects.MergeProgress = ChunkCanceller
    before = counts(app.conn)
    mp = merge_projects.MergeProjects(app, str(base / "src.qda"), show_preview=False)
    merge_projects.MergeProgress = original
    check("D2 cancel fires inside the file, not only between files", state['checks'] >= 2)
    check("D2 no partial file left behind",
          not (base / "dst.qda" / "video" / "grande.mp4").exists())
    check("D2 nothing written to the database", counts(app.conn) == before)
    check("D2 flagged as cancelled", mp.merge_cancelled is True)
    check("D2 source file untouched",
          (base / "src.qda" / "video" / "grande.mp4").stat().st_size == len(big))




# E1. The preview report can be stored as a journal entry, merged or cancelled
def e1_journal_report():
    for merged_run in (True, False):
        base = fresh("e1_merged" if merged_run else "e1_cancelled")
        make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
        make(base / "dst.qda", [])
        app = StubApp(base / "dst.qda")

        class Dialog:
            def __init__(self, app_, sections, path_s_, parent=None):
                pass

            def exec(self):
                return 1 if merged_run else 0

            def save_to_journal(self):
                return True

        original = merge_projects.DialogMergePreview
        merge_projects.DialogMergePreview = Dialog
        mp = merge_projects.MergeProjects(app, str(base / "src.qda"))
        merge_projects.DialogMergePreview = original
        label = "merged" if merged_run else "cancelled"
        cur = app.conn.cursor()
        cur.execute("select name, jentry from journal where name like 'Merge preview%'")
        rows = cur.fetchall()
        check(f"E1 report saved to a journal ({label})", len(rows) == 1, str([r[0] for r in rows]))
        if rows:
            check(f"E1 entry states the outcome ({label})",
                  ("Result: merged" if merged_run else "cancelled") in rows[0][1])
            check(f"E1 entry carries the counts ({label})", "Coded PDF areas to add" in rows[0][1])
        check(f"E1 merge flag correct ({label})", mp.projects_merged is merged_run)


# E2. The preview dialog itself builds and lists what it was given
def e2_preview_dialog_builds():
    base = fresh("e2")
    make(base / "src.qda", RICH_SOURCE, media=RICH_MEDIA)
    make(base / "dst.qda", [
        "insert into source (id,name,fulltext,mediapath,memo,owner,date,av_text_id) "
        "values(1,'E01_Rosa.txt','corto','/docs/E01_Rosa.txt','','t','d',null)",
    ])
    app = StubApp(base / "dst.qda")
    captured = {}
    original = merge_projects.DialogMergePreview

    class Capture:
        def __init__(self, app_, sections, path_s_, parent=None):
            captured['sections'] = sections

        def exec(self):
            return 0

        def save_to_journal(self):
            return False

    merge_projects.DialogMergePreview = Capture
    merge_projects.MergeProjects(app, str(base / "src.qda"))
    merge_projects.DialogMergePreview = original
    dialog = original(app, captured['sections'], str(base / "src.qda"))
    check("E2 dialog renders one row per section",
          dialog.tree.topLevelItemCount() == len(captured['sections']))
    warnings = [s for s in captured['sections'] if s['warning']]
    check("E2 different text lengths raised as a warning", len(warnings) == 1,
          str([s['title'] for s in warnings]))
    check("E2 journal checkbox defaults to off", dialog.save_to_journal() is False)
    dialog.close()




# C7. hide() must also stop Qt's pending auto-show timer, or the modal progress dialog
# pops back on top of the preview and the application looks frozen
def c7_hidden_progress_stays_hidden():
    from PyQt6 import QtCore
    stub_app = types.SimpleNamespace(settings={"fontsize": 10, "font": "Noto Sans"})
    prog = merge_projects.MergeProgress(stub_app)
    prog.phase("reading", 2)  # Faster than minimumDuration, so the show timer is left armed
    prog.phase("preview", 10)
    prog.hide()
    loop = QtCore.QEventLoop()  # Stands in for the preview dialog's event loop
    QtCore.QTimer.singleShot(900, loop.quit)
    loop.exec()
    check("C7 hidden progress does not pop back over the preview", not prog.dialog.isVisible())
    prog.restart()
    prog.phase("copying", 15)
    APP.processEvents()
    check("C7 restart still re-arms the dialog", prog.dialog is not None)
    prog.close()



MERGE_HOLDER = [None]


if __name__ == "__main__":
    a1_preview_matches_reality()
    a2_idempotent()
    a3_orphans()
    a4_not_a_project()
    a5_empty_project_table()
    a6_old_version()
    a7_case_data()
    a8_structure()
    a9_files_and_handles()
    a10_unicode_and_quotes()
    a11_attribute_values()
    a12_cancel_releases()
    a13_large_lists()
    b1_cancel_during_copy()
    b2_cancel_during_insert()
    b3_error_rolls_back()
    b4_single_transaction()
    b5_progress_headless()
    c1_progress_returns_after_hide()
    c2_own_connection()
    c3_other_writes_survive_rollback()
    c4_unexpected_error()
    c5_vectorstore_failure()
    c6_not_a_project_releases()
    c7_hidden_progress_stays_hidden()
    d1_text_not_held_in_memory()
    d2_cancel_inside_large_file()
    e1_journal_report()
    e2_preview_dialog_builds()
    failed = [r for r in RESULTS if not r[1]]
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for name, _ok, detail in failed:
        print(f"FAILED: {name}   {detail}")
    sys.exit(1 if failed else 0)
