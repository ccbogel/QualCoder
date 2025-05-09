from unittest import TestCase
from qualcoder.__main__ import App
import datetime
import os
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
        # Need to mock these later when I learn howto do it
        self.confighome = os.path.expanduser('~/.qualcoder')
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')

        # Create temporary database
        try:
            os.remove(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        except:
            pass
        self.conn = sqlite3.connect(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        cur = self.conn.cursor()
        dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("CREATE TABLE project (databaseversion text, date text, memo text,about text);")
        cur.execute("CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, owner text, date text, unique(name));")
        cur.execute("CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, height integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, owner text, date text);")
        cur.execute("CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, valuetype text);")
        cur.execute("CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, date text, owner text);")
        cur.execute("CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, owner text, date text, memo text);")
        cur.execute("CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, constraint ucm unique(name));")
        cur.execute("CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, supercatid integer, unique(name));")
        cur.execute("CREATE TABLE code_text (cid integer, fid integer,seltext text, pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, unique(cid,fid,pos0,pos1, owner));")
        cur.execute("CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,date text, color text, unique(name));")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text);")

        cur.execute("INSERT INTO project VALUES(?,?,?,?)",
            ('v2', dt, '', 'QualCoder'))
        self.conn.commit()
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

        result = App._load_config_ini(self)
        keys = result.keys()
        self.assertEqual(keys, CONFIG_INI_TEST.keys())

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
        # Need to mock these later when I learn howto do it
        self.test_dir = tempfile.TemporaryFile()

        self.confighome = os.path.expanduser('~/.qualcoder')
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')

        # Create temporary database
        try:
            os.remove(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        except:
            pass
        self.conn = sqlite3.connect(os.path.join(self.confighome, "test_qualcoder_test.qda"))
        cur = self.conn.cursor()
        dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("CREATE TABLE project (databaseversion text, date text, memo text,about text);")
        cur.execute("CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, owner text, date text, unique(name));")
        cur.execute("CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, height integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, owner text, date text);")
        cur.execute("CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, valuetype text);")
        cur.execute("CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, date text, owner text);")
        cur.execute("CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, owner text, date text, memo text);")
        cur.execute("CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, constraint ucm unique(name));")
        cur.execute("CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, supercatid integer, unique(name));")
        cur.execute("CREATE TABLE code_text (cid integer, fid integer,seltext text, pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, unique(cid,fid,pos0,pos1, owner));")
        cur.execute("CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,date text, color text, unique(name));")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text);")

        cur.execute("INSERT INTO project VALUES(?,?,?,?)",
            ('v2', dt, '', 'QualCoder'))
        self.conn.commit()
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
        self.test_dir.close()

    def test_settings_report(self):
        pass

#TEST_PERSIST_PATH = '/fake/path/'
CONFIG_INI_TEST = {'codername': 'default', 'font': 'Noto Sans', 'fontsize': 12, 'treefontsize': 10, 'directory': '/home/fake/Desktop',
 'showids': 'False', 'language': 'en', 'backup_on_open': 'True', 'backup_av_files': 'True', 'timestampformat': '[hh.mm.ss]',
 'speakernameformat': '{}', 'mainwindow_w': '602', 'mainwindow_h': '515', 'dialogcodetext_w': '1110',
 'dialogcodetext_h': '611', 'dialogcodetext_splitter0': '361', 'dialogcodetext_splitter1': '723',
 'dialogcodeimage_w': '0', 'dialogcodeimage_h': '0', 'dialogcodeimage_splitter0': '1', 'dialogcodeimage_splitter1': '1',
 'dialogviewimage_w': '0', 'dialogviewimage_h': '0', 'dialogreportcodes_w': '0', 'dialogreportcodes_h': '0',
 'dialogreportcodefrequencies_w': '0', 'dialogreportcodefrequencies_h': '0', 'dialogreportcodes_splitter0': '1',
 'dialogreportcodes_splitter1': '1', 'dialogmanagefiles_w': '794', 'dialogmanagefiles_h': '560', 'dialogjournals_w': '0',
 'dialogjournals_h': '0', 'dialogjournals_splitter0': '1', 'dialogjournals_splitter1': '1', 'dialogsql_w': '0',
 'dialogsql_h': '0', 'dialogsql_splitter_h0': '1', 'dialogsql_splitter_h1': '1', 'dialogsql_splitter_v0': '1',
 'dialogsql_splitter_v1': '1', 'dialogcases_w': '0', 'dialogcases_h': '0', 'dialogcases_splitter0': '1',
 'dialogcases_splitter1': '1', 'dialogcasefilemanager_w': '0', 'dialogcasefilemanager_h': '0',
 'dialogcasefilemanager_splitter0': '1', 'dialogcasefilemanager_splitter1': '1', 'dialogmanageattributes_w': '0',
 'dialogmanageattributes_h': '0', 'video_w': '374', 'video_h': '261', 'viewav_video_pos_x': '72',
 'viewav_video_pos_y': '-10', 'codeav_video_pos_x': '72', 'codeav_video_pos_y': '27', 'dialogcodeav_w': '1032',
 'dialogcodeav_h': '689', 'codeav_abs_pos_x': '652', 'codeav_abs_pos_y': '87', 'dialogviewav_w': '1021',
 'dialogviewav_h': '413', 'viewav_abs_pos_x': '362', 'viewav_abs_pos_y': '250', 'bookmark_file_id': '7',
 'bookmark_pos': '147', 'dialogmanagesttributes_w': '0', 'dialogcodecrossovers_w': 0, 'dialogcodecrossovers_h': 0,
 'dialogcodecrossovers_splitter0': 1, 'dialogcodecrossovers_splitter1': 1}

