# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
"""

import logging
import os
import shutil
import sqlite3

from PyQt5 import QtWidgets

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class MergeProjects:
    """ Merge one external Qualcoder project (source) database into existing project (destination).
    The merge will combine files, and codings.
    Copies files from source to destination folders.
    Adds new source code names to destination database.
    Adds journals and stored_sql to destination database, as long as they have unique names,
    Adds text codings, annotations, image codings, av codings to destination database.

    TODO
        Does not insert the Source Categories tree into the Destination.
        Does not add new category names.
        Does not add cases.
        Does not add attributes.
        Does not link A/V to text transcript file
     """

    app = None
    path_d = ""  # Path to destination project folder
    conn_d = None
    path_s = ""  # Path to source project folder
    conn_s = None
    source_s = []  # source text from Source project
    code_text_s = []  # coded text segments from Source project
    annotations_s = []  # annotations from Source project
    journals_s = []
    stored_sql_s = []
    summary_msg = ""
    code_image_s = []  # coded image areas from Source project
    code_av_s = []  # coded A/V segments from Source project
    code_name_s = []  # code names from Source project
    code_cat_s = []  # code cats from Source project

    # TODO import cases, case_text, attribute_types, attributes

    def __init__(self, app, path_s):
        self.app = app
        self.path_s = path_s
        self.conn_s = sqlite3.connect(os.path.join(self.path_s, 'data.qda'))
        self.conn_d = self.app.conn
        self.path_d = self.app.project_path
        self.summary_msg = _("Merging: ") + self.path_s + "\n" + _("Into: ") + self.app.project_path + "\n"
        self.copy_source_files_into_destination()
        self.get_source_data()
        self.fill_sources_get_new_file_ids()
        self.update_coding_file_ids()
        self.update_code_name_cid()
        self.insert_data_into_destination()
        self.summary_msg += _("Finished merging " + self.path_s + " into " + self.path_d) + "\n"
        self.summary_msg += _("NOT MERGED: code categories, cases, attributes") + "\n"
        self.summary_msg += _("NOT LINKED: text transcript to audio/video")

    def update_code_name_cid(self):
        """ Update the cid to the one already in Destination.code_name.
        Check for no matches and insert these into the Destination.code_name table.
        """

        print("Updating Source.code_name cid")
        cur_d = self.conn_d.cursor()
        sql = "select cid, name from code_name"
        cur_d.execute(sql)
        res = cur_d.fetchall()
        for r in res:
            for cn in self.code_name_s:
                if cn['name'] == r[1]:
                    cn['newcid'] = r[0]
        for cn in self.code_name_s:
            # Unmatched code name
            if cn['newcid'] == -1:
                cur_d.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                              (cn['name'], cn['memo'], cn['owner'], cn['date'], None, cn['color']))
                self.conn_d.commit()
                cur_d.execute("select last_insert_rowid()")
                cid = cur_d.fetchone()[0]
                cn['newcid'] = cid
                self.summary_msg += _("Adding code name: ") + cn['name'] + "\n"
        # Update code_text, code_image, code_av cids
        print("Updating Source.code_text cid to Destination.cid")
        for cn in self.code_name_s:
            for ct in self.code_text_s:
                if ct['cid'] == cn['cid']:
                    ct['newcid'] = cn['newcid']
            for ci in self.code_image_s:
                if ci['cid'] == cn['cid']:
                    ci['newcid'] = cn['newcid']
            for cav in self.code_av_s:
                if cav['cid'] == cn['cid']:
                    cav['newcid'] = cn['newcid']

    def insert_data_into_destination(self):
        """ Code text fid and cid updated, annotation fid updated.
        Now insert into Destination project. """

        cur_d = self.conn_d.cursor()
        # Earlier db versions did not have Unique journal name
        # Need to identify duplicate journal names and not import them
        cur_d.execute("select name from journal")
        j_names_res = cur_d.fetchall()
        j_names = []
        for j in j_names_res:
            j_names.append(j[0])
        for j in self.journals_s:
            # Possible to have two identical journal names in earlier db versions
            if j['name'] not in j_names:
                cur_d.execute("insert into journal (name, jentry, date, owner) values(?,?,?,?)",
                              (j['name'], j['jentry'], j['date'], j['owner']))
                self.summary_msg += _("Copying journal: ") + j['name'] + "\n"
                self.conn_d.commit()
        for s in self.stored_sql_s:
            # Cannot have two identical stored_sql titles, using 'or ignore'
            cur_d.execute("insert or ignore into stored_sql (title, description, grouper, ssql) values(?,?,?,?)",
                            (s['title'], s['description'], s['grouper'], s['ssql']))
            self.conn_d.commit()
        for c in self.code_text_s:
            cur_d.execute("insert or ignore into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date, important) values(?,?,?,?,?,?,?,?,?)", (c['newcid'], c['newfid'],
                                                                   c['seltext'], c['pos0'], c['pos1'], c['owner'],
                                                                   c['memo'], c['date'], c['important']))
            self.conn_d.commit()
        if len(self.code_text_s) > 0:
            self.summary_msg += _("Merging coded text") + "\n"
        for a in self.annotations_s:
            cur_d.execute("insert or ignore into annotation (fid,pos0,pos1,memo,owner,date) values(?,?,?,?,?,?)",
                          [a["newfid"], a["pos0"], a["pos1"], a["memo"], a["owner"], a["date"]])
            self.conn_d.commit()
        if len(self.annotations_s) > 0:
            self.summary_msg += _("Merging annotations") + "\n"
        for c in self.code_image_s:
            cur_d.execute("insert or ignore into code_image (cid, id,x1,y1,width,height,memo,owner,date,important) values(?,?,?,?,?,?,?,?,?,?)",
                          [c["newcid"], c["newfid"], c["x1"], c["y1"], c["width"], c["height"], c["memo"], c["owner"], c["date"], c["important"]])
            self.conn_d.commit()
        if len(self.code_image_s) > 0:
            self.summary_msg += _("Merging coded image areas") + "\n"
        for c in self.code_av_s:
            cur_d.execute("insert or ignore into code_av (cid, id,pos0,pos1,memo,owner,date,important) values(?,?,?,?,?,?,?,?)",
                [c["newcid"], c["newfid"], c["pos0"], c["pos1"], c["memo"], c["owner"], c["date"], c["important"]])
            self.conn_d.commit()
        if len(self.code_av_s) > 0:
            self.summary_msg += _("Merging coded audio/video segments") + "\n"

    def fill_sources_get_new_file_ids(self):
        """ Insert Source.source into Destination.source, unless source name is already present.
        update newfid in source_s and code_text_s.
        TODO link transcript to A/V file """

        cur_d = self.conn_d.cursor()
        for src in self.source_s:
            cur_d.execute("select id from source where name=?", [src['name']])
            res = cur_d.fetchone()
            if res is not None:
                src['newid'] = res[0]
            else:
                cur_d.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                              (src['name'], src['fulltext'], src['mediapath'], src['memo'], src['owner'], src['date']))
                self.conn_d.commit()
                cur_d.execute("select last_insert_rowid()")
                id_ = cur_d.fetchone()[0]
                src['newid'] = id_

    def update_coding_file_ids(self):

        # Update code_text and annotations fids
        print("Updating code_text.fid and annotation.fid")
        for src in self.source_s:
            for c_text in self.code_text_s:
                if c_text['fid'] == src['id']:
                    c_text['newfid'] = src['newid']
            for an in self.annotations_s:
                if an['fid'] == src['id']:
                    an['newfid'] = src['newid']
            for c_img in self.code_image_s:
                if c_img['fid'] == src['id']:
                    c_img['newfid'] = src['newid']
            for c_av in self.code_av_s:
                if c_av['fid'] == src['id']:
                    c_av['newfid'] = src['newid']
        # Display potential problems
        '''for ct in self.code_text_s:
            if ct['newfid'] == -1:
                print("Code Text. No Match for existing fid ", ct)
        for an in self.annotations_s:
            if an['newfid'] == -1:
                print("Annotation. No Match for existing fid ", an)'''

    def copy_source_files_into_destination(self):
        """ Copy source files into destination project.
        Do not copy over existing files.
        """

        print("Copy source files into dest")
        folders = ["audio", "documents", "images", "video"]
        for folder_name in folders:
            dir_ = self.path_s + "/" + folder_name
            files = os.listdir(dir_)
            for f in files:
                if not os.path.exists(self.app.project_path + "/" + folder_name + "/" + f):
                    try:
                        shutil.copyfile(dir_ + "/" + f, self.app.project_path + "/" + folder_name + "/" + f)
                        self.summary_msg += _("File copied: ") + f + "\n"
                    except shutil.SameFileError:
                        pass
                    except PermissionError:
                        self.summary_msg += f + " " + _("NOT copied. Permission error")

    def get_source_data(self):
        """ Load the source data into memory.
        TODO
        ##code_cat (catid integer primary key, name text, owner text, date text, memo text, supercatid integer, unique(name)
        TODO
        cases (caseid integer primary key, name text, memo text, owner text,date text
        TODO
        case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, "
            "owner text, date text, memo
        TODO
        attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, "
            "valuetype
        TODO
        attribute (attrid integer primary key, name text, attr_type text, value text, id integer, "
            "date text, owner
        """

        self.journals_s = []
        self.stored_sql_s = []
        self.code_name_s = []
        self.code_cat_s = []
        self.code_text_s = []
        self.annotations_s = []
        self.code_image_s = []
        self.code_av_s = []
        print("Getting Source table data for source, code_text, code_name, annotation")
        cur_s = self.conn_s.cursor()
        # Journal data
        sql_journal = "select name, jentry, date, owner from journal"
        cur_s.execute(sql_journal)
        res_journals = cur_s.fetchall()
        for i in res_journals:
            src = {"name": i[0], "jentry": i[1], "date": i[2], "owner": i[3]}
            self.journals_s.append(src)
        # Stored sql data
        sql_stored_sql = "select title, description, grouper, ssql from stored_sql"
        cur_s.execute(sql_stored_sql)
        res_stored_sqls = cur_s.fetchall()
        for i in res_stored_sqls:
            src = {"title": i[0], "description": i[1], "grouper": i[2], "ssql": i[3]}
            self.stored_sql_s.append(src)
        # Source data
        sql_source = "select id, name, fulltext,mediapath,memo,owner,date from source"
        cur_s.execute(sql_source)
        res_source = cur_s.fetchall()
        for i in res_source:
            src = {"id": i[0], "newid": -1, "name": i[1], "fulltext": i[2], "mediapath": i[3], "memo": i[4],
                   "owner": i[5], "date": i[6]}
            self.source_s.append(src)
        # Code data
        sql_codenames = "select cid, name, memo, owner, date, color from code_name"
        cur_s.execute(sql_codenames)
        res_codenames = cur_s.fetchall()
        for i in res_codenames:
            cn = {"cid": i[0], "newcid": -1, "name": i[1], "memo": i[2], "owner": i[3], "date": i[4], "color": i[5],
                  "catid": None}
            self.code_name_s.append(cn)
        # Code category data
        sql_codecats = "select catid, supercatid, name, memo, owner, date from code_cat"
        cur_s.execute(sql_codecats)
        res_codecats = cur_s.fetchall()
        for i in res_codecats:
            ccat = {"catid": i[0], "newcatid": -1, "supercatid": i[1], "newsupercatid": -1,
                    "name": i[2], "memo": i[3], "owner": i[4], "date": i[5]}
            self.code_cat_s.append(ccat)
        # Code text and text annotation data
        sql_codetext = "select cid, fid, seltext, pos0, pos1, owner, date, memo, important from code_text"
        cur_s.execute(sql_codetext)
        res_codetext = cur_s.fetchall()
        for i in res_codetext:
            ct = {"cid": i[0], "newcid": -1, "fid": i[1], "newfid": -1, "seltext": i[2], "pos0": i[3], "pos1": i[4],
                  "owner": i[5], "date": i[6], "memo": i[7], "important": i[8]}
            self.code_text_s.append(ct)
        sql_annotations = "select fid, pos0, pos1, memo, owner, date from annotation"
        cur_s.execute(sql_annotations)
        res_annot = cur_s.fetchall()
        for i in res_annot:
            an = {"fid": i[0], "newfid": -1, "pos0": i[1], "pos1": i[2], "memo": i[3], "owner": i[4], "date": i[5]}
            self.annotations_s.append(an)
        # Code image data
        sql_code_img = "select cid, id, x1, y1, width, height, memo, date, owner, important from code_image"
        cur_s.execute(sql_code_img)
        res_code_img = cur_s.fetchall()
        for i in res_code_img:
            cimg = {"cid": i[0], "newcid": -1, "fid": i[1], "newfid": -1, "x1": i[2], "y1": i[3],
                  "width": i[4], "height": i[5], "memo": i[6], "date": i[7], "owner": i[8], "important": i[9]}
            self.code_image_s.append(cimg)
        # Code AV data
        sql_code_av = "select cid, id, pos0, pos1, owner, date, memo, important from code_av"
        cur_s.execute(sql_code_av)
        res_code_av = cur_s.fetchall()
        for i in res_code_av:
            c_av = {"cid": i[0], "newcid": -1, "fid": i[1], "newfid": -1, "pos0": i[2], "pos1": i[3],
                  "owner": i[4], "date": i[5], "memo": i[6], "important": i[7]}
            self.code_av_s.append(c_av)
