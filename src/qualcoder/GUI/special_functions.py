# -*- coding: utf-8 -*-

"""
Copyright (c) 2021 Colin Curtain

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
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io/
"""

import logging
import os
import sys
import traceback

from PyQt5 import QtGui, QtWidgets, QtCore

from .code_text import DialogCodeText  # for isinstance()
from .confirm_delete import DialogConfirmDelete
from .GUI.base64_helper import *
from .GUI.ui_special_functions import Ui_Dialog_special_functions


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


class DialogSpecialFunctions(QtWidgets.QDialog):
    """ Dialog for special QualCoder functions.
    """

    app = None
    parent_textEdit = None
    tab_coding = None  # Tab widget coding tab for updates

    def __init__(self, app, parent_textEdit, tab_coding, parent=None):

        super(DialogSpecialFunctions, self).__init__(parent)
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_special_functions()
        self.ui.setupUi(self)
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.tab_coding = tab_coding
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(eye_doc_icon), "png")
        self.ui.pushButton_select_text_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_select_replacement_text_file.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_text_starts.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_text_ends.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_change_prefix.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_text_update.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_text_starts.clicked.connect(self.change_text_code_start_positions)
        self.ui.pushButton_text_ends.clicked.connect(self.change_text_code_end_positions)

    def change_text_code_start_positions(self):
        """ Extend or shrink text coding start positions in all codings and all files for owner. """

        delta = self.ui.spinBox_text_starts.value()
        if delta == 0:
            return
        cur = self.app.conn.cursor()
        sql = "select cid,fid,pos0,pos1,code_text.owner, length(source.fulltext) from code_text join source on source.id=code_text.fid where code_text.owner=?"
        text_sql = "select substr(source.fulltext, ?, ?) from source where source.id=?"
        update_sql = "update code_text set pos0=?, seltext=? where pos0=? and pos1=? and cid=? and fid=? and owner=?"
        cur.execute(sql, [self.app.settings['codername']])
        res = cur.fetchall()
        if res == []:
            return
        msg = _("Change ALL text code start positions in ALL text files by ")
        msg += str(delta) + _(" characters.\n")
        msg += _("Made by coder: ") + self.app.settings['codername'] + "\n"
        msg += str(len(res)) + _(" to change.") + "\n"
        msg += _("Backup project before performing this function.\n")
        msg += _("Press OK to continue.")
        ui = DialogConfirmDelete(self.app, msg, _("Change code start positions"))
        ok = ui.exec_()
        if not ok:
            return

        for r in res:
            new_pos0 = r[2] - delta
            # cannot have start pos less than start of text
            if new_pos0 < 0:
                new_pos0 = 0
            # cannot have start pos larger than end pos
            if new_pos0 > r[3]:
                new_pos0 = r[3] - 1
            cur.execute(text_sql, [new_pos0 + 1, r[3] - new_pos0, r[1]])
            seltext = cur.fetchone()[0]
            try:
                cur.execute(update_sql, [new_pos0, seltext, r[2], r[3], r[0], r[1], r[4]])
            except:
                pass
        self.app.conn.commit()
        self.parent_textEdit.append(_("All text codings by ") + self.app.settings['codername'] + _(" resized by ") + str(delta) + _(" characters."))
        self.update_tab_coding_dialog()

    def change_text_code_end_positions(self):
        """ Extend or shrink text coding start positions in all codings and all files for owner. """

        delta = self.ui.spinBox_text_ends.value()
        if delta == 0:
            return
        cur = self.app.conn.cursor()
        sql = "select cid,fid,pos0,pos1,code_text.owner, length(source.fulltext) from code_text join source on source.id=code_text.fid where code_text.owner=?"
        text_sql = "select substr(source.fulltext, ?, ?) from source where source.id=?"
        update_sql = "update code_text set pos1=?, seltext=? where pos0=? and pos1=? and cid=? and fid=? and owner=?"
        cur.execute(sql, [self.app.settings['codername']])
        res = cur.fetchall()
        if res == []:
            return
        msg = _("Change ALL text code end positions in ALL text files by ")
        msg += str(delta) + _(" characters.\n")
        msg += _("Made by coder: ") + self.app.settings['codername'] + "\n"
        msg += str(len(res)) + _(" to change.") + "\n"
        msg += _("Backup project before performing this function.\n")
        msg += _("Press OK to continue.")
        ui = DialogConfirmDelete(self.app, msg, _("Change code end positions"))
        ok = ui.exec_()
        if not ok:
            return

        for r in res:
            new_pos1 = r[3] + delta
            # cannot have end pos less or equal to startpos
            if new_pos1 <= r[2]:
                new_pos1 = r[2] + 1
            # cannot have end pos larger than text
            if new_pos1 >= r[5]:
                new_pos1 = r[5] - 1
            cur.execute(text_sql, [r[2] + 1, new_pos1 - r[2], r[1]])
            seltext = cur.fetchone()[0]
            try:
                cur.execute(update_sql, [new_pos1, seltext, r[2], r[3], r[0], r[1], r[4]])
            except:
                pass
        self.app.conn.commit()
        self.parent_textEdit.append(_("All text codings by ") + self.app.settings['codername'] + _(" resized by ") + str(delta) + _(" characters."))
        self.update_tab_coding_dialog()

    def update_tab_coding_dialog(self):
        """ DialogCodeText """

        contents = self.tab_coding.layout()
        if contents:
            # Remove code text widgets from layout
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogCodeText):
                    c.get_coded_text_update_eventfilter_tooltips()
                    break

    def accept(self):
        """ Overrride accept button. """

        super(DialogSpecialFunctions, self).accept()

    '''def menelic(self):
        """ Convert MAXQDA REFI-QDA export from many files into one text file.
         Need to load the qdpx file first. Then run this function to collate and add codings. """
        text = ""
        cur = self.app.conn.cursor()
        owner = "default"
        date = ""
        o_sql = "select owner, date from source limit 1"
        cur.execute(o_sql)
        o_res = cur.fetchone()
        owner = o_res[0]
        date_ = o_res[1]

        # Insert empty text file, named '0_collated', to get the id_
        cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
            ('0_collated',  '', None, '', owner, date_))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        print("id_ ", id_)
        source_sql = "select id, name, fulltext from source order by id"
        cur.execute(source_sql)
        source_res = cur.fetchall()
        coding_sql = "select cid, pos0, pos1, seltext, owner, date from code_text where fid=?"
        code_text = []
        pos = 0
        for source in source_res:
            id_text = source[1] + " "
            insert_text = source[2] + "\n"
            text += id_text + insert_text  
            # Get codings for this file
            cur.execute(coding_sql, [source[0]])
            coding_res = cur.fetchall()
            for c in coding_res:
                pos0 = pos + len(id_text) + c[1]
                pos1 = pos + len(id_text) + c[2]
                seltext = insert_text[c[1]:c[2]]
                code_text.append({'cid': c[0], 'fid': id_, 'seltext': seltext, 'pos0': pos0, 'pos1': pos1, 'owner': c[4], 'date': c[5]})
                #print(code_text)
            pos = len(text)
        #print(text)

        # Update file, named '0_collated' with text
        cur.execute("update source set fulltext=? where id=?", [text, id_])
        self.app.conn.commit()
        self.ui.label_2.setText("0_collated Text file created")

        # Insert codings
        # Making up memo at nothing and date as current date
        for c in code_text:
            try:
                cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                    memo,date) values(?,?,?,?,?,?,?,?)",
                    [c['cid'], c['fid'], c['seltext'], c['pos0'], c['pos1'], c['owner'], '', c['date']])
                self.app.conn.commit()
            except Exception as e:
                logger.debug(str(e))
        self.ui.label_2.setText("Codes added to file 0_collated")
        self.ui.pushButton_text_starts.hide()

        # Delete other codes and files
        """cur.execute("delete from source where id != ?", [id_])
        self.app.conn.commit()
        cur.execute("delete from code_text where fid != ?", [id_])
        self.app.conn.commit()"""'''


