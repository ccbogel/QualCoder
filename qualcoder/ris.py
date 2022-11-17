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

import collections
import logging
import os
import rispy
import sys
import traceback
from PyQt6 import QtWidgets

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


class ImportRis:
    """ Import an RIS format bibliography and store in database.
    References in RIS can be poorly created often due to how the researcher created them. """

    app = None
    parent_text_edit = None

    def __init__(self, app, parent_text_edit):
        sys.excepthook = exception_handler
        self.app = app
        self.parent_text_edit = parent_text_edit
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select RIS references file'),
                                                          self.app.settings['directory'],
                                                          "(*.txt *.ris *.RIS)",
                                                          options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                          )
        # print("Response ", response)
        imports = response[0]
        if imports:
            self.import_ris_file(imports[0])

    def import_ris_file(self, filepath):
        """ Open file and extract RIS information.
        List tags: 'A1', 'A2', 'A3', 'A4', 'AU', 'KW', 'N1'  # authors, KW keywords, N1 Notes
        longtag is the extended wording of a tag
        tag_keys is the dictionary of 2 char short tag keys (e.g. AU) and the longtag wording
        """

        #list_tags = rispy.LIST_TYPE_TAGS
        #print("List tags ", list_tags)
        tag_keys = rispy.TAG_KEY_MAPPING
        for tk in tag_keys:
            print(tk, tag_keys[tk])
        longtag_to_tag = dict((v, k) for k, v in tag_keys.items())

        cur = self.app.conn.cursor()
        cur.execute("select max(risid) from ris")
        res = cur.fetchone()
        max_risid = 0
        if res is not None:
            max_risid = res[0]
            if max_risid is None:
                max_risid = 0
        #print("filepath", filepath)
        with open(filepath, 'r', encoding="utf-8", errors="surrogateescape") as ris_file:
            entries = rispy.load(ris_file)
        for entry in entries:
            #if not self.check_entry_exists(entry):
            max_risid += 1
            try:
                del entry['id']
            except KeyError:
                pass
            #print(entry.keys())
            for longtag in entry:
                if isinstance(entry[longtag], list):
                    data = "; ".join(entry[longtag])
                else:
                    data = entry[longtag]
                #print("risid", max_risid, longtag_to_tag[longtag], longtag, data)
                sql = "insert into ris (risid,tag,longtag,value) values (?,?,?,?)"
                cur.execute(sql, [max_risid, longtag_to_tag[longtag], longtag, data])
            self.app.conn.commit()
            print("================")

    def check_entry_exists(self, entry):
        """ Check if this entry exists.
        param: entry - dictionary of longtag and value
        return: exists - boolean
        TODO Does Not WOrk """

        exists = False
        #print(entry)
        res_list = []
        cur = self.app.conn.cursor()
        sql = "select risid from ris where longtag=? and value=?"
        length_adjuster = 0
        for longtag in entry:
            if isinstance(entry[longtag], list):
                data = "; ".join(entry[longtag])
                if len(entry[longtag]) > 1:
                    length_adjuster = len(entry[longtag]) - 1
            else:
                data = entry[longtag]
            #print("Parameters ", longtag, data)
            cur.execute(sql, [longtag, data])
            res = cur.fetchall()
            for r in res:
                res_list.append(r[0])
        #print("len entry ", len(entry) - length_adjuster)
        frequencies = collections.Counter(res_list)
        freq_dict = dict(frequencies)
        for k in freq_dict:
            if freq_dict[k] == len(entry) - length_adjuster:
                print(k, "matching")
                exists = True
        return exists


