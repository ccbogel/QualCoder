from unittest import TestCase
from qualcoder.__main__ import App
import datetime
import os
import shutil
import sqlite3
import tempfile

""" Useful insights from:
https: // stackoverflow.com / questions / 32527861 / python - unit - test - that - uses - an - external - data - file / 32528173
https: // www.blog.pythonlibrary.org / 2016 / 07 / 07 / python - 3 - testing - an - intro - to - unittest /
https: // simpleit.rocks / python / test - files - creating - a - temporal - directory - in -python - unittests /
"""


class TestApp(TestCase):
    """ Testing Various App class methods.
    """

    def setUp(self):
        # Need to mock these later when I learn how to do it
        self.confighome = tempfile.mkdtemp()
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')

        shutil.copy(
            os.path.join(os.path.dirname(__file__), "fixtures", "config-ai-ec4c0559.ini"),
            self.configpath,
        )
        self.settings, _ = App._load_config_ini(self)

        # Create temporary database
        try:
            os.remove(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        except (FileNotFoundError, PermissionError) as e_:
            print(e_)
        self.conn = sqlite3.connect(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        cur = self.conn.cursor()
        dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "CREATE TABLE project (databaseversion text, date text, memo text,about text, bookmarkfile integer, "
            "bookmarkpos integer, codername text, recently_used_codes text)")
        cur.execute(
            "CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, "
            "owner text, date text, av_text_id integer, risid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, "
            "height integer, cid integer, memo text, date text, owner text, important integer, pdf_page integer)")
        cur.execute(
            "CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, "
            "memo text, date text, owner text, important integer)")
        cur.execute(
            "CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, "
            "owner text, date text, unique(fid,pos0,pos1,owner))")
        cur.execute(
            "CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, "
            "valuetype text)")
        cur.execute(
            "CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, "
            "date text, owner text, unique(name,attr_type,id))")
        cur.execute(
            "CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, "
            "owner text, date text, memo text)")
        cur.execute(
            "CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, "
            "constraint ucm unique(name))")
        cur.execute(
            "CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, "
            "supercatid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, "
            "pos1 integer, owner text, date text, memo text, avid integer, important integer, "
            "unique(cid,fid,pos0,pos1, owner))")
        cur.execute(
            "CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,"
            "date text, color text, unique(name))")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text, "
                    "unique(name))")
        cur.execute("CREATE TABLE stored_sql (title text, description text, grouper text, ssql text, unique(title))")
        cur.execute("CREATE TABLE ris (risid integer, tag text, longtag text, value text);")
        # Tables to store graph. sqlite 0 is False 1 is True
        cur.execute("CREATE TABLE graph (grid integer primary key, name text, description text, "
                    "date text, scene_width integer, scene_height integer, unique(name));")
        cur.execute("CREATE TABLE gr_cdct_text_item (gtextid integer primary key, grid integer, x integer, y integer, "
                    "supercatid integer, catid integer, cid integer, font_size integer, bold integer, "
                    "isvisible integer, displaytext text);")
        cur.execute("CREATE TABLE gr_case_text_item (gcaseid integer primary key, grid integer, x integer, "
                    "y integer, caseid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_file_text_item (gfileid integer primary key, grid integer, x integer, "
                    "y integer, fid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_free_text_item (gfreeid integer primary key, grid integer, freetextid integer,"
                    "x integer, y integer, free_text text, font_size integer, bold integer, color text,"
                    "tooltip text, ctid integer,memo_ctid integer, memo_imid integer, memo_avid integer);")
        cur.execute("CREATE TABLE gr_cdct_line_item (glineid integer primary key, grid integer, "
                    "fromcatid integer, fromcid integer, tocatid integer, tocid integer, color text, "
                    "linewidth real, linetype text, isvisible integer);")
        cur.execute("CREATE TABLE gr_free_line_item (gflineid integer primary key, grid integer, "
                    "fromfreetextid integer, fromcatid integer, fromcid integer, fromcaseid integer,"
                    "fromfileid integer, fromimid integer, fromavid integer, tofreetextid integer, tocatid integer, "
                    "tocid integer, tocaseid integer, tofileid integer, toimid integer, toavid integer, color text,"
                    "linewidth real, linetype text);")
        cur.execute("CREATE TABLE gr_pix_item (grpixid integer primary key, grid integer, imid integer,"
                    "x integer, y integer, px integer, py integer, w integer, h integer, filepath text,"
                    "tooltip text, pdf_page integer);")
        cur.execute("CREATE TABLE gr_av_item (gr_avid integer primary key, grid integer, avid integer,"
                    "x integer, y integer, pos0 integer, pos1 integer, filepath text, tooltip text, color text);")
        self.conn.commit()
        cur.execute("INSERT INTO project VALUES(?,?,?,?,?,?,?,?)",
                    (
                        'v11', datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), '', 'QualCoder 3.7',
                        0,
                        0, self.settings['codername'], ""))
        cur.execute("insert into cases (name,memo,owner,date) VALUES(?,?,?,?)",
                    ('case one', 'memo 1', 'default', dt))
        cur.execute("insert into cases (name,memo,owner,date) VALUES(?,?,?,?)",
                    ('case two', 'memo 2', 'default', dt))
        cur.execute("insert into code_name (name,memo,catid, owner,date, color) VALUES(?,?,?,?,?,?)",
                    ('code one', 'memo 1', None, 'default', dt, "#F5A9A9"))
        cur.execute("insert into code_cat (catid, name,memo,supercatid, owner,date) VALUES(?,?,?,?,?,?)",
                    (1, 'cat one', 'memo 1', None, 'default', dt))
        cur.execute("insert into code_name (name,memo, catid,owner,date, color) VALUES(?,?,?,?,?,?)",
                    ('code two', 'memo 2', 1, 'default', dt, "#D0A9F5"))
        cur.execute("insert into source (id, name, fulltext, mediapath, memo, owner, date) VALUES (?,?,?,?,?,?,?)",
                    (1, "textfile one", "a short boring story.", None, 'memo', 'default', dt))
        cur.execute("insert into source (id, name, fulltext, mediapath, memo, owner, date) VALUES (?,?,?,?,?,?,?)",
                    (2, "pic one", None, "/images/firstimage.png", 'memo', 'coder2', dt))
        cur.execute("insert into source (id, name, fulltext, mediapath, memo, owner, date) VALUES (?,?,?,?,?,?,?)",
                    (3, "vid one", None, "/video/firstvideo.mp4", 'memo', 'coder2', dt))
        self.conn.commit()

    def tearDown(self):
        self.conn = None
        os.remove(os.path.join(self.confighome, "test_qualcoder_test.qda"))

    def test_read_previous_project_paths(self):
        """ Check the project paths is a list object """

        result = App.read_previous_project_paths(self)
        self.assertTrue(type(result) == list)

    def test_load_config_ini(self):
        """ Tests that all config.ini fields are present """

        result, ai_models = App._load_config_ini(self)
        keys = result.keys()
        self.assertEqual(keys, CONFIG_INI_AI_EX4C0559.keys())

        for ai_model in ai_models:
            self.assertEqual(tuple(ai_model.keys()), CONFIG_INI_AI_MODEL_KEYS)


    def test_get_casenames(self):
        result = App.get_casenames(self)
        self.assertEqual(2, len(result))

    def test_get_codenames(self):
        result = App.get_code_names(self)
        self.assertEqual(2, len(result))

    def test_get_filenames(self):
        result = App.get_filenames(self)
        self.assertEqual(3, len(result))

    def test_get_av_filenames(self):
        result = App.get_av_filenames(self)
        self.assertEqual(1, len(result))

    def test_get_image_filenames(self):
        result = App.get_image_filenames(self)
        self.assertEqual(1, len(result))

    def test_get_text_filenames(self):
        result = App.get_text_filenames(self)
        self.assertEqual(1, len(result))

    def test_get_file_texts(self):
        result = App.get_file_texts(self)
        self.assertEqual(1, len(result))

    def test_get_coder_names_in_project(self):
        result = App.get_coder_names_in_project(self)
        self.assertEqual(2, len(result))

    '''def test_get_most_recent_projectpath(self):
        result = App.get_most_recent_projectpath(self)
        print(result)
        self.fail()'''

    '''def test_write_config_ini(self):
        """ This contains a write method. so unsure how to continue """"
        self.fail()'''

    '''def test_check_and_add_additional_settings(self):
        self.fail()'''

    '''def test_merge_settings_with_default_stylesheet(self):
            """ This contains a write method. so unsure how to continue """"
        self.fail()'''

    '''self test_load_settings(self):
        """
        Stumbling block:
         AttributeError: 'TestApp' object has no attribute '_load_config_ini'"""

        result = App.load_settings(self)
        print(result)
        self.fail()'''


class TestMainWindow(TestCase):
    """ Testing Various MainWindow class methods.
    """

    def setUp(self):
        # Need to mock these later when I learn how to do it
        self.confighome = tempfile.mkdtemp()
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')

        shutil.copy(
            os.path.join(os.path.dirname(__file__), "fixtures", "config-ai-ec4c0559.ini"),
            self.configpath,
        )
        self.settings, _ = App._load_config_ini(self)

        # Create temporary database
        try:
            os.remove(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        except (FileNotFoundError, PermissionError) as e_:
            print(e_)
        self.conn = sqlite3.connect(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        cur = self.conn.cursor()
        dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "CREATE TABLE project (databaseversion text, date text, memo text,about text, bookmarkfile integer, "
            "bookmarkpos integer, codername text, recently_used_codes text)")
        cur.execute(
            "CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, "
            "owner text, date text, av_text_id integer, risid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, "
            "height integer, cid integer, memo text, date text, owner text, important integer, pdf_page integer)")
        cur.execute(
            "CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, "
            "memo text, date text, owner text, important integer)")
        cur.execute(
            "CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, "
            "owner text, date text, unique(fid,pos0,pos1,owner))")
        cur.execute(
            "CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, "
            "valuetype text)")
        cur.execute(
            "CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, "
            "date text, owner text, unique(name,attr_type,id))")
        cur.execute(
            "CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, "
            "owner text, date text, memo text)")
        cur.execute(
            "CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, "
            "constraint ucm unique(name))")
        cur.execute(
            "CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, "
            "supercatid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, "
            "pos1 integer, owner text, date text, memo text, avid integer, important integer, "
            "unique(cid,fid,pos0,pos1, owner))")
        cur.execute(
            "CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,"
            "date text, color text, unique(name))")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text, "
                    "unique(name))")
        cur.execute("CREATE TABLE stored_sql (title text, description text, grouper text, ssql text, unique(title))")
        cur.execute("CREATE TABLE ris (risid integer, tag text, longtag text, value text);")
        # Tables to store graph. sqlite 0 is False 1 is True
        cur.execute("CREATE TABLE graph (grid integer primary key, name text, description text, "
                    "date text, scene_width integer, scene_height integer, unique(name));")
        cur.execute("CREATE TABLE gr_cdct_text_item (gtextid integer primary key, grid integer, x integer, y integer, "
                    "supercatid integer, catid integer, cid integer, font_size integer, bold integer, "
                    "isvisible integer, displaytext text);")
        cur.execute("CREATE TABLE gr_case_text_item (gcaseid integer primary key, grid integer, x integer, "
                    "y integer, caseid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_file_text_item (gfileid integer primary key, grid integer, x integer, "
                    "y integer, fid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_free_text_item (gfreeid integer primary key, grid integer, freetextid integer,"
                    "x integer, y integer, free_text text, font_size integer, bold integer, color text,"
                    "tooltip text, ctid integer,memo_ctid integer, memo_imid integer, memo_avid integer);")
        cur.execute("CREATE TABLE gr_cdct_line_item (glineid integer primary key, grid integer, "
                    "fromcatid integer, fromcid integer, tocatid integer, tocid integer, color text, "
                    "linewidth real, linetype text, isvisible integer);")
        cur.execute("CREATE TABLE gr_free_line_item (gflineid integer primary key, grid integer, "
                    "fromfreetextid integer, fromcatid integer, fromcid integer, fromcaseid integer,"
                    "fromfileid integer, fromimid integer, fromavid integer, tofreetextid integer, tocatid integer, "
                    "tocid integer, tocaseid integer, tofileid integer, toimid integer, toavid integer, color text,"
                    "linewidth real, linetype text);")
        cur.execute("CREATE TABLE gr_pix_item (grpixid integer primary key, grid integer, imid integer,"
                    "x integer, y integer, px integer, py integer, w integer, h integer, filepath text,"
                    "tooltip text, pdf_page integer);")
        cur.execute("CREATE TABLE gr_av_item (gr_avid integer primary key, grid integer, avid integer,"
                    "x integer, y integer, pos0 integer, pos1 integer, filepath text, tooltip text, color text);")
        self.conn.commit()
        cur.execute("INSERT INTO project VALUES(?,?,?,?,?,?,?,?)",
                    (
                        'v11', datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), '', 'QualCoder 3.7',
                        0,
                        0, self.settings['codername'], ""))
        cur.execute("insert into cases (name,memo,owner,date) VALUES(?,?,?,?)",
                    ('case one', 'memo 1', 'default', dt))
        cur.execute("insert into cases (name,memo,owner,date) VALUES(?,?,?,?)",
                    ('case two', 'memo 2', 'default', dt))
        cur.execute("insert into code_name (name,memo,catid, owner,date, color) VALUES(?,?,?,?,?,?)",
                    ('code one', 'memo 1', None, 'default', dt, "#F5A9A9"))
        cur.execute("insert into code_cat (catid, name,memo,supercatid, owner,date) VALUES(?,?,?,?,?,?)",
                    (1, 'cat one', 'memo 1', None, 'default', dt))
        cur.execute("insert into code_name (name,memo, catid,owner,date, color) VALUES(?,?,?,?,?,?)",
                    ('code two', 'memo 2', 1, 'default', dt, "#D0A9F5"))
        cur.execute("insert into source (id, name, fulltext, mediapath, memo, owner, date) VALUES (?,?,?,?,?,?,?)",
                    (1, "textfile one", "a short boring story.", None, 'memo', 'default', dt))
        cur.execute("insert into source (id, name, fulltext, mediapath, memo, owner, date) VALUES (?,?,?,?,?,?,?)",
                    (2, "pic one", None, "/images/firstimage.png", 'memo', 'coder2', dt))
        self.conn.commit()

    def tearDown(self):
        self.conn = None
        os.remove(os.path.join(self.confighome, "test_qualcoder_test.qda"))

    def test_settings_report(self):
        pass


# TEST_PERSIST_PATH = '/fake/path/'
CONFIG_INI_AI_EX4C0559 = {
    "backup_num": "5",
    "codername": "default",
    "font": "DejaVu Sans",
    "fontsize": "12",
    "docfontsize": "12",
    "treefontsize": "12",
    "directory": "/cephyr/users/vikren/Alvis",
    "showids": "False",
    "language": "en",
    "backup_on_open": "True",
    "backup_av_files": "True",
    "timestampformat": "[hh.mm.ss]",
    "speakernameformat": "[]",
    "mainwindow_geometry": "",
    "dialogcodetext_splitter0": "1",
    "dialogcodetext_splitter1": "1",
    "dialogcodetext_splitter_v0": "1",
    "dialogcodetext_splitter_v1": "1",
    "dialogcodeimage_splitter0": "1",
    "dialogcodeimage_splitter1": "1",
    "dialogcodeimage_splitter_h0": "1",
    "dialogcodeimage_splitter_h1": "1",
    "dialogreportcodes_splitter0": "1",
    "dialogreportcodes_splitter1": "1",
    "dialogreportcodes_splitter_v0": "30",
    "dialogreportcodes_splitter_v1": "30",
    "dialogreportcodes_splitter_v2": "30",
    "dialogjournals_splitter0": "1",
    "dialogjournals_splitter1": "1",
    "dialogsql_splitter_h0": "1",
    "dialogsql_splitter_h1": "1",
    "dialogsql_splitter_v0": "1",
    "dialogsql_splitter_v1": "1",
    "dialogcasefilemanager_w": "0",
    "dialogcasefilemanager_h": "0",
    "dialogcasefilemanager_splitter0": "1",
    "dialogcasefilemanager_splitter1": "1",
    "video_w": "0",
    "video_h": "0",
    "viewav_video_pos_x": "0",
    "viewav_video_pos_y": "0",
    "codeav_video_pos_x": "0",
    "codeav_video_pos_y": "0",
    "codeav_abs_pos_x": "0",
    "codeav_abs_pos_y": "0",
    "dialogcodeav_splitter_0": "0",
    "dialogcodeav_splitter_1": "0",
    "dialogcodeav_splitter_h0": "0",
    "dialogcodeav_splitter_h1": "0",
    "viewav_abs_pos_x": "0",
    "viewav_abs_pos_y": "0",
    "dialogcodecrossovers_w": "0",
    "dialogcodecrossovers_h": "0",
    "dialogcodecrossovers_splitter0": "0",
    "dialogcodecrossovers_splitter1": "0",
    "dialogmanagelinks_w": "0",
    "dialogmanagelinks_h": "0",
    "bookmark_file_id": "0",
    "bookmark_pos": "0",
    "dialogreport_file_summary_splitter0": "100",
    "dialogreport_file_summary_splitter1": "100",
    "dialogreport_code_summary_splitter0": "100",
    "dialogreport_code_summary_splitter1": "100",
    "stylesheet": "native",
    "report_text_context_chars": "150",
    "report_text_context-style": "Bold",
    "codetext_chunksize": "50000",
    "ai_enable": "False",
    "ai_first_startup": "False",
    "ai_model_index": "2",
    "report_text_context_characters": "100",
    "report_text_context_style": "Bold",
    "ai_send_project_memo": "True",
    "ai_language_ui": "True",
    "ai_language": "",
    "ai_temperature": "1.0",
    "ai_top_p": "1.0",
    "ai_timeout": "30.0",
}


CONFIG_INI_AI_MODEL_KEYS = (
    'name', 'desc',
    'access_info_url',
    'large_model', 'large_model_context_window',
    'fast_model', 'fast_model_context_window',
    'api_base', 'api_key',
)
