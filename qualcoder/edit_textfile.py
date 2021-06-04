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
    text = ""
    fid = -1
    codetext = []
    annotations = []
    casetext = []
    prev_text = ""
    all_is_case_text = False  # may not use
    no_codes_annotes_cases = True
    change = False

    def __init__(self, app, fid, clear_button="show"):
        """ """

        super(DialogEditTextFile, self).__init__(parent=None)  # overrride accept method

        sys.excepthook = exception_handler
        self.app = app
        self.fid = fid
        cur = self.app.conn.cursor()
        cur.execute("select fulltext, name from source where id=?", [self.fid])
        res = cur.fetchone()
        self.text = ""
        if res[0] is not None:
            self.text = res[0]
        title = res[1]
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
        self.change = False
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

        self.change = True

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
        
        Replacing 's' with 'T'  (highlight s and replace with T
        -s  previous 4 None  post 4 None
        """
        # No additions or deletions
        if pre_start == post_start and pre_chars == post_chars:
            return

        """
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
        for item in self.casetext:
            cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
            format_.setFontUnderline(True)
            format_.setUnderlineColor(QtCore.Qt.green)
            cursor.setCharFormat(format_)
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
        #self.update_codings()

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

    def update_codings(self):
        """ Update coding positions and seltext. """

        sql = "update code_text set pos0=?, pos1=? where pos0=? and pos1=? and fid=?"
        sqltext = ""
        for c in self.codetext:
            pass

    '''def textEdit_unrestricted_menu(self, position):
            """ Context menu for select all and copy of text.
            """

            if self.ui.textEdit.toPlainText() == "":
                return
            menu = QtWidgets.QMenu()
            menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            action_select_all = menu.addAction(_("Select all"))
            action_copy = menu.addAction(_("Copy"))
            action = menu.exec_(self.ui.textEdit.mapToGlobal(position))
            if action == action_copy:
                selected_text = self.ui.textEdit.textCursor().selectedText()
                cb = QtWidgets.QApplication.clipboard()
                cb.clear(mode=cb.Clipboard)
                cb.setText(selected_text, mode=cb.Clipboard)
            if action == action_select_all:
                self.ui.textEdit.selectAll()'''

    '''def restricted_edit_text:
        """ UPDATE CODES//CASES/ANNOTATIONS located after the selected text
        Update database for codings, annotations and case linkages.
        Find affected codings annotations and case linkages.
        All codes, annotations and case linkages that occur after this text selection can be easily updated
        by adding the length diff to the pos0 and pos1 fields. """
        cur = self.app.conn.cursor()
        # find cases after this text section
        sql = "select id, pos0,pos1 from case_text where fid=? and pos1>? "
        sql += "and not(?>=pos0 and ?<=pos1)"
        cur.execute(sql, [self.source[x]['id'], selend, selstart, selend])
        post_case_linked = cur.fetchall()
        # find annotations after this text selection
        sql = "select anid,pos0,pos1 from annotation where fid=? and pos1>? "
        sql += "and not(?>=pos0 and ?<=pos1)"
        cur.execute(sql, [self.source[x]['id'], selend, selstart, selend])
        post_annote_linked = cur.fetchall()
        # find codes after this text selection section
        sql = "select pos0,pos1 from code_text where fid=? and pos1>? "
        sql += "and not(?>=pos0 and ?<=pos1)"
        cur.execute(sql, [self.source[x]['id'], selend, selstart, selend])
        post_code_linked = cur.fetchall()
        txt = text_cursor.selectedText()
        #print("cursor selstart", text_cursor.selectionStart())
        #print("cursor selend", text_cursor.selectionEnd())
        #print("length_diff", length_diff, "\n")

        for i in post_case_linked:
            #print(i)
            #print(i[0], i[1] + length_diff, i[2] + length_diff)
            #print("lengths ", len(original_text), i[2] - i[1])
            sql = "update case_text set pos0=?, pos1=? where id=?"
            cur.execute(sql, [i[1] + length_diff, i[2] + length_diff, i[0]])
        for i in post_annote_linked:
            sql = "update annotation set pos0=?, pos1=? where anid=?"
            cur.execute(sql, [i[1] + length_diff, i[2] + length_diff, i[0]])
        for i in post_code_linked:
            sql = "update code_text set pos0=?,pos1=? where fid=? and pos0=? and pos1=?"
            cur.execute(sql, [i[0] + length_diff, i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        self.app.conn.commit()

        # UPDATE THE CODED AND/OR ANNOTATED SECTION
        # The crossover dictionary contains annotations and codes for this section
        # need to extend or reduce the code or annotation length
        # the coded text stored in code_text also need to be updated
        crossovers = self.crossover_check(x, text_cursor)
        # Codes in this selection
        for i in crossovers['coded_section']:
            #print("selected text coded: ", i)
            sql = "update code_text set seltext=?,pos1=? where fid=? and pos0=? and pos1=?"
            newtext = fulltext[i[0]:i[1] + length_diff]
            cur.execute(sql, [newtext, i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        # Annotations in this selection
        for i in crossovers['annoted_section']:
            #print("selected text annoted: ", i)
            sql = "update annotation set pos1=? where fid=? and pos0=? and pos1=?"
            cur.execute(sql, [i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        for i in crossovers['cased_section']:
            #print("selected text as case: ", i)
            sql = "update case_text set pos1=? where fid=? and pos0=? and pos1=?"
            cur.execute(sql, [i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        self.app.conn.commit()

        self.app.delete_backup = False'''

    '''def crossover_check(self, x, text_cursor):
        """ Check text selection for codes and annotations that cross over with non-coded
        and non-annotated sections. User can only select coded or non-coded text, this makes
        updating changes much simpler.

        param: x the current table row
        param: text_cursor  - the document cursor
        return: dictionary of crossover indication and of whether selection is entirely coded annotated or neither """

        response = {"crossover": True, "coded_section":[], "annoted_section":[], "cased_section":[]}
        msg = _("Please select text that does not have a combination of coded and uncoded text.")
        msg += _(" Nor a combination of annotated and un-annotated text.\n")
        selstart = text_cursor.selectionStart()
        selend = text_cursor.selectionEnd()
        msg += _("Selection start: ") + str(selstart) + _(" Selection end: ") + str(selend) + "\n"
        cur = self.app.conn.cursor()
        sql = "select pos0,pos1 from code_text where fid=? and "
        sql += "((pos0>? and pos0<?)  or (pos1>? and pos1<?)) "
        cur.execute(sql, [self.source[x]['id'], selstart, selend, selstart, selend])
        code_crossover = cur.fetchall()
        if code_crossover != []:
            msg += _("Code crossover: ") + str(code_crossover)
            Message(self.app, _('Codes cross over text'), msg, "warning").exec_()
            return response
        # find if the selected text is coded
        sql = "select pos0,pos1 from code_text where fid=? and ?>=pos0 and ?<=pos1"
        cur.execute(sql, [self.source[x]['id'], selstart, selend])
        response['coded_section'] = cur.fetchall()
        sql = "select pos0,pos1 from annotation where fid=? and "
        sql += "((pos0>? and pos0<?) or (pos1>? and pos1<?))"
        cur.execute(sql, [self.source[x]['id'], selstart, selend, selstart, selend])
        annote_crossover = cur.fetchall()
        if annote_crossover != []:
            msg += _("Annotation crossover: ") + str(annote_crossover)
            Message(self.app, _('Annotations cross over text'), msg, "warning").exec_()
            return response
        # find if the selected text is annotated
        sql = "select pos0,pos1 from annotation where fid=? and ?>=pos0 and ?<=pos1"
        cur.execute(sql, [self.source[x]['id'], selstart, selend])
        response['annoted_section'] = cur.fetchall()
        response['crossover'] = False
        # find if the selected text is assigned to case
        sql = "select pos0,pos1, id from case_text where fid=? and ?>=pos0 and ?<=pos1"
        cur.execute(sql, [self.source[x]['id'], selstart, selend])
        response['cased_section'] = cur.fetchall()
        response['crossover'] = False
        return response'''


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogEditTextFile("settings", "title", "text")
    ui.show()
    sys.exit(app.exec_())

