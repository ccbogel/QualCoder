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

Have backups of both projects. Essential.
The texts, and codings and codes from Project B will be copied into Project A.
If there are matching codes (same codenames), thats OK.
If there are unique codes in Project B, these will be copied into Project A.

TODO
Categories (the code tree structure) is not copied from Project B to Project A.
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
     The merge will not insert the Source Categories structure into the Destination.
     Codes will be merged into the Destination.
     """

    app = None
    path_d = ""  # Path to destination project folder
    conn_d = None
    path_s = ""  # Path to source project folder
    conn_s = None
    source_s = []  # source text from Source project
    code_text_s = []  # coded text segments from Source project
    annotations_s = []  # annotations from Source project
    summary_msg = ""

    # TODO
    code_image_s = []  # coded image areas from Source project
    code_av_s = []  # coded A/V segments from Source project

    code_name_s = []  # code names from Source project
    # TODO to import code cats
    code_cat_s = []  # code cats from Source project
    # TODO import journals, stored_sql, cases, case_text, attributes

    def __init__(self, app, path_s):
        self.app = app
        self.path_s = path_s
        self.conn_s = sqlite3.connect(os.path.join(self.path_s, 'data.qda'))
        self.conn_d = self.app.conn
        self.path_d = self.app.project_path
        self.summary_msg = _("Merging: ") + self.path_s + "\n" + _("Into: ") + self.app.project_path + "\n"
        self.copy_source_files_into_destination()
        self.get_source_data()
        self.fill_sources_update_id()
        self.update_code_name_cid()
        self.insert_data_into_destination()
        print("Finished merging ", self.path_s, " into ", self.path_d)

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
                print(_("Adding new code name: " + cn['name'] + ", " + str(cn['newcid'])))
        # Update code_text cids
        print("Updating Source.code_text cid to Destination.cid")
        for cn in self.code_name_s:
            for ct in self.code_text_s:
                if ct['cid'] == cn['cid']:
                    ct['newcid'] = cn['newcid']

    def insert_data_into_destination(self):
        """ Code text fid and cid updated, annotation fid updated.
        Now insert into Destination project. """

        print("Inserting coded text and annotations into Destination project.")
        cur_d = self.conn_d.cursor()
        for c in self.code_text_s:
            cur_d.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date, important) values(?,?,?,?,?,?,?,?,?)", (c['newcid'], c['newfid'],
                c['seltext'], c['pos0'], c['pos1'], c['owner'],
                c['memo'], c['date'], c['important']))
        self.conn_d.commit()
        for a in self.annotations_s:
            cur_d.execute("insert into annotation (fid,pos0,pos1,memo,owner,date) values(?,?,?,?,?,?)",
                          [a["newfid"], a["pos0"], a["pos1"], a["memo"], a["owner"], a["date"]])
        self.conn_d.commit()

    def fill_sources_update_id(self):
        """ Insert Source.source into Destination.source, unless source name is already present.
        update newfid in source_s and code_text_s. """

        print("Inserting Source.source into Destination.source")
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
        # Update code_text and annotations fids
        print("Updating code_text.fid and annotation.fid")
        for src in self.source_s:
            for ct in self.code_text_s:
                if ct['fid'] == src['id']:
                    ct['newfid'] = src['newid']
            for an in self.annotations_s:
                if an['fid'] == src['id']:
                    an['newfid'] = src['newid']
        # Display potential problems
        for ct in self.code_text_s:
            if ct['newfid'] == -1:
                print("Code Text. No Match for existing fid ", ct)
        for an in self.annotations_s:
            if an['newfid'] == -1:
                print("Annotation. No Match for existing fid ", an)

    def copy_source_files_into_destination(self):
        """ Copy source files into destination project.
        TODO Do not copy matching file names.
        """

        print("Copy source files into dest")
        folders = ["audio", "documents", "images", "video"]
        for folder_name in folders:
            dir_ = self.path_s + "/" + folder_name
            files = os.listdir(dir_)
            for f in files:
                try:
                    shutil.copyfile(dir_ + "/" + f, self.app.project_path + "/" + folder_name + "/" + f)
                    self.summary_msg += _("File copied: ") + f + "\n"
                except shutil.SameFileError:
                    pass
                except PermissionError:
                    self.summary_msg += f + " " + _("NOT copied. Permission error")

    def get_source_data(self):
        """ Load the source data into memory.

        code_name (cid integer primary key, name text, memo text, catid integer, owner text,date text, color text, unique(name))
        ##code_cat (catid integer primary key, name text, owner text, date text, memo text, supercatid integer, unique(name))
        source (id integer primary key, name text, fulltext text, mediapath text, memo text, owner text, date text, unique(name))
        code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, pos1 integer,
        owner text, date text, memo text, avid integer, important integer
        annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, owner text, date text,
        unique(fid,pos0,pos1,owner
        """

        print("Getting Source table data for source, code_text, code_name, annotation")
        cur_s = self.conn_s.cursor()
        sql_source = "select id, name, fulltext,mediapath,memo,owner,date from source"
        cur_s.execute(sql_source)
        res_source = cur_s.fetchall()
        for i in res_source:
            src = {"id": i[0], "newid": -1, "name": i[1], "fulltext": i[2], "mediapath": i[3], "memo": i[4],
                   "owner": i[5], "date": i[6]}
            #print(src)
            self.source_s.append(src)
        sql_codenames = "select cid, name, memo, owner, date, color from code_name"
        cur_s.execute(sql_codenames)
        res_codenames = cur_s.fetchall()
        for i in res_codenames:
            cn = {"cid": i[0], "newcid": -1, "name": i[1], "memo": i[2], "owner": i[3], "date": i[4], "color": i[5],
                  "catid": None}
            #print(cn)
            self.code_name_s.append(cn)
        sql_codetext = "select cid, fid, seltext, pos0, pos1, owner, date, memo, important from code_text"
        cur_s.execute(sql_codetext)
        res_codetext = cur_s.fetchall()
        for i in res_codetext:
            ct = {"cid": i[0], "newcid": -1, "fid": i[1], "newfid": -1, "seltext": i[2], "pos0": i[3], "pos1": i[4],
                  "owner": i[5], "date": i[6], "memo": i[7], "important": i[8]}
            #print(ct)
            self.code_text_s.append(ct)
        sql_annotations = "select fid, pos0, pos1, memo, owner, date from annotation"
        cur_s.execute(sql_annotations)
        res_annot = cur_s.fetchall()
        for i in res_annot:
            an = {"fid": i[0], "newfid": -1, "pos0": i[1], "pos1": i[2], "memo": i[3], "owner": i[4], "date": i[5]}
            # print(an)
            self.annotations_s.append(an)

