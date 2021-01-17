# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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
import sys
import traceback

from PyQt5 import QtGui, QtWidgets, QtCore

from confirm_delete import DialogConfirmDelete
from GUI.ui_dialog_special_functions import Ui_Dialog_special_functions


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

    def __init__(self, app, parent_textEdit, parent=None):

        super(DialogSpecialFunctions, self).__init__(parent)
        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_special_functions()
        self.ui.setupUi(self)
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
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

    def accept(self):
        """ Overrride accept button. """

        super(DialogSpecialFunctions, self).accept()


'''if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogSpecialFunctions()
    ui.show()
    sys.exit(app.exec_())'''
