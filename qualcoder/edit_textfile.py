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
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from copy import copy
import difflib
import os
import sys
import logging
import traceback

from GUI.ui_dialog_memo import Ui_Dialog_memo
from memo import DialogMemo

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


class DialogEditTextFile(QtWidgets.QDialog):

    """ Dialog to view and edit text file data.
    Needs to adjust codings annotations and cases for changed character positions.
    """

    app = None
    title = ""
    text = ""
    fid = -1
    codetext = []
    annotations = []
    casetext = []
    prev_text = ""
    all_is_case_text = False
    no_codes_annotes_cases = True

    def __init__(self, app, title="", text="", fid=-1, clear_button="show"):
        """ This is based on memo DialogMemo """

        super(DialogEditTextFile, self).__init__(parent=None)  # overrride accept method

        sys.excepthook = exception_handler
        self.app = app
        self.text = text
        self.fid = fid
        self.ui = Ui_Dialog_memo()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowTitle(title)
        if clear_button == "hide":
            self.ui.pushButton_clear.hide()
        self.ui.pushButton_clear.pressed.connect(self.clear_contents)
        self.get_cases_codings_annotations()
        self.ui.textEdit.setPlainText(self.text)
        self.ui.textEdit.setFocus()
        print("FILE:", title)
        if self.casetext:
            print("CASE\n", self.casetext)
        if self.annotations:
            print("ANNOTE\n", self.annotations)
        if self.codetext:
            print("CODETEXT\n", self.codetext)
        self.prev_text = copy(self.text)
        self.highlight()
        self.ui.textEdit.textChanged.connect(self.update_positions)
        self.ui.textEdit.installEventFilter(self)

    def get_cases_codings_annotations(self):
        """ Get all linked cases, coded text and annotations for this file """

        cur = self.app.conn.cursor()
        sql = "select cid, pos0, pos1, seltext, owner from code_text where fid=?"
        cur.execute(sql, [self.fid])
        res = cur.fetchall()
        self.codetext = []
        for r in res:
            self.codetext.append({'cid': r[0], 'pos0': r[1], 'pos1': r[2], 'seltext': r[3],
                'owner': r[4], 'npos0': r[1], 'npos1': r[2]})
        sql = "select anid, pos0, pos1 from annotation where fid=?"
        cur.execute(sql, [self.fid])
        res = cur.fetchall()
        self.annotations = []
        for r in res:
            self.annotations.append({'anid': r[0], 'pos0': r[1], 'pos1': r[2],
                'npos0': r[1], 'npos1': r[2]})
        sql = "select id, pos0, pos1 from case_text where fid=?"
        cur.execute(sql, [self.fid])
        res = cur.fetchall()
        self.casetext = []
        for r in res:
            self.casetext.append({'id': r[0], 'pos0': r[1], 'pos1': r[2],
                'npos0': r[1], 'npos1': r[2]})
        if len(self.casetext) == 1 and self.casetext[0]['pos0'] == 0 and self.casetext[0]['pos1'] == len(self.text) - 1:
            self.all_is_case_text = True
        else:
            self.all_is_case_text = False
        self.no_codes_annotes_cases = True
        if len(self.codetext) > 0 or len(self.annotations) > 0 or len(self.casetext) > 0:
            self.no_codes_annotes_cases = False

    def clear_contents(self):
        """ Clear all text """
        self.ui.textEdit.setPlainText("")

    def update_positions(self):
        """ Update positions for code text, annotations and case text as each character changes
        via adding or deleting.

        Output: adding an e at pos 4:
        ---

        +++

        @@ -4,0 +5 @@

        +e
        """

        # No need to update positions (unless entire file is a case)
        if self.no_codes_annotes_cases:
            return

        cursor = self.ui.textEdit.textCursor()
        self.text = self.ui.textEdit.toPlainText()
        #print("cursor", cursor.position())
        #for d in difflib.unified_diff(self.prev_text, self.text):
        # n is how many context lines to show
        d = list(difflib.unified_diff(self.prev_text, self.text, n=0))
        #print(d)  # 4 items
        if len(d) < 4:
            #print("D", d)
            return
        characters = d[3]
        position = d[2][4:]  # Removes prefix @@ -
        position = position[:-4]  # Removes suffix space@@\n
        print("position", position)

        previous = position.split(" ")[0]
        pre_start = previous.split(",")[0]
        pre_chars = None
        try:
            pre_chars = previous.split(",")[1]
        except:
            pass
        post = position.split(" ")[1]
        post_start = int(post.split(",")[0])
        post_chars = None
        try:
            post_chars = post.split(",")[1]
        except:
            pass

        print(characters, " previous", pre_start, pre_chars, " post", post_start, post_chars)
        """
        Replacing 'way' with 'the' start position 13
        -w  previous 13 3  post 13 3
        
        Adding 'X' at inserted position 5, note: None as no number is provided from difflib
        +X  previous 4 0  post 5 None
        
        Removing 'X' from position 5, note None
        -X  previous 5 None  post 4 0
        
        Removing 'the' from position 13
        -t  previous 13 3  post 12 0
        """

        self.highlight()
        self.prev_text = copy(self.text)

    def highlight(self):
        """ Add coding and annotation highlights. """

        self.remove_formatting()
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])

        self.ui.textEdit.blockSignals(True)
        cursor = self.ui.textEdit.textCursor()
        for item in self.annotations:
            cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
            format_.setFontUnderline(True)
            format_.setUnderlineColor(QtCore.Qt.yellow)
            cursor.setCharFormat(format_)
        for item in self.codetext:
            cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
            format_.setFontUnderline(True)
            format_.setUnderlineColor(QtCore.Qt.red)
            cursor.setCharFormat(format_)
        #TODO casetext

        self.ui.textEdit.blockSignals(False)

    def remove_formatting(self):
        """ Remove formatting from text edit on changed text.
         Useful when pasting mime data (rich text or html) from clipboard. """

        self.ui.textEdit.blockSignals(True)
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(len(self.ui.textEdit.toPlainText()), QtGui.QTextCursor.KeepAnchor)
        cursor.setCharFormat(format_)
        self.ui.textEdit.blockSignals(False)

    def accept(self):
        """ Accepted button overridden method. """

        self.text = self.ui.textEdit.toPlainText()
        cur = self.app.conn.cursor()
        cur.execute("update source set fulltext=? where id=?", (self.text, self.fid))

        # Update codings
        sql = "update case_text set"
        for c in self.codetext:
            pass

        # Update annotations
        sql = "update annotation set pos0=?, pos1=? where anid=? and (pos0 !=? or pos1 !=?)"
        for a in self.annotations:
            #if a['pos0'] != a['npos0'] or a['pos1'] != a['npos1']:
            cur.execute(sql, [a['npos0'], a['npos1'], a['anid'], a['npos0'], a['npos1']])
        self.app.conn.commit()

        #  Update linked cases
        sql = "update case_text set"
        for c in self.casetext:
            pass

        self.app.conn.commit()
        super(DialogEditTextFile, self).accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogEditTextFile("settings", "title", "text")
    ui.show()
    sys.exit(app.exec_())

