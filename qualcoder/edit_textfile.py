# -*- coding: utf-8 -*-

"""
Copyright (c) 2024 Colin Curtain

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

from PyQt6 import QtWidgets, QtCore, QtGui
from copy import copy
import difflib
import diff_match_patch
import logging
import os

from .GUI.ui_dialog_memo import Ui_Dialog_memo

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogEditTextFile(QtWidgets.QDialog):
    """ Dialog to view and edit text file data.
    Needs to adjust codings annotations and cases for changed character positions.
    The Ui_dialog_memo QTextEdit is slow with large text files, QPlainTextEdit is better,
    so replacing with the plaintext edit here
    """

    app = None
    text = ""
    fid = -1
    name = ""
    codetext = []
    annotations = []
    casetext = []
    prev_text = ""
    no_codes_annotes_cases = True
    code_deletions = []
    has_changed = False

    def __init__(self, app, fid, clear_button="show"):

        super(DialogEditTextFile, self).__init__(parent=None)  # Overrride accept method
        self.app = app
        self.fid = fid
        cur = self.app.conn.cursor()
        cur.execute("select fulltext, name from source where id=?", [self.fid])
        res = cur.fetchone()
        self.text = ""
        if res[0] is not None:
            self.text = res[0]
        self.name = res[1]
        self.code_deletions = []
        self.ui = Ui_Dialog_memo()
        self.ui.setupUi(self)
        self.plain_text_edit = QtWidgets.QPlainTextEdit()
        self.ui.gridLayout.replaceWidget(self.ui.textEdit, self.plain_text_edit)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt '
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowTitle(self.name)
        msg = _(
            "Avoid selecting text combinations of unmarked text sections and coded/annotated/case-assigned sections.")
        msg += " " + _("Positions may not correctly adjust.") + " "
        msg += " " + _("Do not code this text until you reload Coding - Code Text from the menu bar.")
        label = QtWidgets.QLabel(msg)
        label.setWordWrap(True)

        tt = _(
            "Avoid selecting sections of text with a combination of not underlined (not coded / annotated / case-assigned) and underlined (coded, annotated, case-assigned).")
        tt += _(
            "Positions of the underlying codes / annotations / case-assigned may not correctly adjust if text is typed over or deleted.")
        label.setToolTip(tt)
        self.ui.gridLayout.addWidget(label, 2, 0, 1, 1)
        if clear_button == "hide":
            self.ui.pushButton_clear.hide()
        self.ui.pushButton_clear.pressed.connect(self.clear_contents)
        self.get_cases_codings_annotations()
        '''self.ui.textEdit.setPlainText(self.text)
        self.ui.textEdit.setFocus()'''
        self.plain_text_edit.setPlainText(self.text)
        self.plain_text_edit.setFocus()
        self.prev_text = copy(self.text)
        self.highlight()
        '''self.ui.textEdit.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.textedit_menu)
        self.ui.textEdit.textChanged.connect(self.update_positions)
        self.ui.textEdit.installEventFilter(self)'''
        self.plain_text_edit.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.plain_text_edit.customContextMenuRequested.connect(self.textedit_menu)
        self.plain_text_edit.textChanged.connect(self.update_positions)
        self.plain_text_edit.installEventFilter(self)

    def get_cases_codings_annotations(self):
        """ Get all linked cases, coded text and annotations for this file """

        cur = self.app.conn.cursor()
        sql = "select ctid, cid, pos0, pos1, seltext, owner from code_text where fid=?"
        cur.execute(sql, [self.fid])
        res = cur.fetchall()
        self.codetext = []
        for r in res:
            self.codetext.append({'ctid': r[0], 'cid': r[1], 'pos0': r[2], 'pos1': r[3], 'seltext': r[4],
                                  'owner': r[5], 'newpos0': r[2], 'newpos1': r[3]})
        sql = "select anid, pos0, pos1 from annotation where fid=?"
        cur.execute(sql, [self.fid])
        res = cur.fetchall()
        self.annotations = []
        for r in res:
            self.annotations.append({'anid': r[0], 'pos0': r[1], 'pos1': r[2],
                                     'newpos0': r[1], 'newpos1': r[2]})
        sql = "select id, pos0, pos1 from case_text where fid=?"
        cur.execute(sql, [self.fid])
        res = cur.fetchall()
        self.casetext = []
        for r in res:
            self.casetext.append({'id': r[0], 'pos0': r[1], 'pos1': r[2],
                                  'newpos0': r[1], 'newpos1': r[2]})
        self.no_codes_annotes_cases = True
        if len(self.codetext) > 0 or len(self.annotations) > 0 or len(self.casetext) > 0:
            self.no_codes_annotes_cases = False

    def clear_contents(self):
        #self.ui.textEdit.setPlainText("")
        self.plain_text_edit.setPlainText("")

    def update_positions(self):
        """ Update positions for code text, annotations and case text as each character changes
        via adding or deleting.
        uses diff-match-patch module much faster than difflib with large text files that are
        annotated, coded, cased.
        consider diff_match_patch 20x faster

        diff_match_patch.diff_main() Output:
        Adding X at pos 0
            [(1, 'X'), (0, "I rea...")]
        Adding X at pos 4
            [(0, 'I re'), (1, 'X'), (0, "ally...")]
        Adding X at end of file
            [(0, "...appy to pay €200."), (1, 'X')]
        Removing 'really'
            [(0, 'I '), (-1, 'really'), (0, " like ...")]

        """
        self.has_changed = True # mark contents as beeing changed
        
        # No need to update positions
        if self.no_codes_annotes_cases:
            return
        # self.text = self.ui.textEdit.toPlainText()
        self.text = self.plain_text_edit.toPlainText()
        diff = diff_match_patch.diff_match_patch()
        diff_list = diff.diff_main(self.prev_text, self.text)
        # print(diff_list)
        extending = True
        preceding_pos = 0
        chars_len = 0
        pre_chars_len = 0
        post_chars_len = 0
        if len(diff_list) == 2 and diff_list[0][0] == 1:
            # print("Add at start")
            chars_len = len(diff_list[0][1])
            pre_chars_len = 0
            preceding_pos = 0
            # dont need post_chars_len = len(diff_list[1][1])
        if len(diff_list) == 2 and diff_list[0][0] == -1:
            # print("Remove from start")
            extending = False
            chars_len = len(diff_list[0][1])
            pre_chars_len = 0
            preceding_pos = 0
            post_chars_len = len(diff_list[1][1])
        if len(diff_list) == 2 and diff_list[1][0] == 1:
            # print("Add at end")
            chars_len = len(diff_list[1][1])
            # dont need post_chars_len = 0
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 2 and diff_list[1][0] == -1:
            # print("Remove from end")
            extending = False
            chars_len = len(diff_list[1][1])
            post_chars_len = 0
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 3 and diff_list[1][0] == 1:
            # print("Add in middle")
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
            # dont need post_chars_len = len(diff_list[2][1])
        if len(diff_list) == 3 and diff_list[1][0] == -1:
            # print("Delete from middle")
            extending = False
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
            post_chars_len = len(diff_list[2][1])
        '''print("Pre chars:\n", pre_chars)
        print("Preceding pos:\n", preceding_pos)
        print("Post chars:\n", post_chars)
        print("Adding chars\n:", adding_chars)
        print("Deleting chars:\n", deleting_chars)'''
        # Adding characters
        if extending:
            for c in self.codetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c['newpos0'] >= preceding_pos  - pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    changed = True
                if not changed and c['newpos0'] is not None and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len
                #print("Code:\n", c)
            for c in self.annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c['newpos0'] >= preceding_pos + -pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len
            for c in self.casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c['newpos0'] >= preceding_pos + - pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len
                #print("Casetext:\n", c)
            self.highlight()
            self.prev_text = copy(self.text)
            return
        # Removing characters
        if not extending:
            for c in self.codetext:
                changed = False
                # print("CODE npos0", c['npos0'], "pre start", pre_start, pre_chars, post_chars)
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= preceding_pos and c['newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                    self.code_deletions.append(f"delete from code_text where ctid={c['ctid']}")
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from code_text where ctid={c['ctid']}")
                        c['newpos0'] = None
            for c in self.annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                    # Remove, as entire text is being removed (e.g. copy replace)
                    # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                    # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                    if not changed and c['newpos0'] >= preceding_pos and c['newpos1'] < preceding_pos + - pre_chars_len + post_chars_len:
                        c['newpos0'] -= chars_len
                        c['newpos1'] -= chars_len
                        changed = True
                        self.code_deletions.append(f"delete from annotations where anid={c['anid']}")
                        c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from annotation where anid={c['anid']}")
                        c['newpos0'] = None
            for c in self.casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['newpos0'],  pre_start, c['newpos1'], pre_chars, post_chars)
                # print(c['newpos0'], ">",  pre_start, "and", c['newpos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= preceding_pos and c['newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                    self.code_deletions.append(f"delete from case_text where id={c['id']}")
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from case_text where id={c['id']}")
                        c['newpos0'] = None
        self.highlight()
        self.prev_text = copy(self.text)

    def update_positions_difflib(self):
        """ Update positions for code text, annotations and case text as each character changes
        via adding or deleting.
        difflib is VERY SLOW with large text files that are annotated, coded, cased.
        Difflib Output: adding an e at pos 4:
        =====================================
        ---

        +++

        @@ -4,0 +5 @@

        +e
        """

        # No need to update positions
        if self.no_codes_annotes_cases:
            return
        #self.text = self.ui.textEdit.toPlainText()
        self.text = self.plain_text_edit.toPlainText()
        # n is how many context lines to show
        # difflib is very slow with large text files, use difflib with smaller text files?
        d = list(difflib.unified_diff(self.prev_text, self.text, n=0))
        if len(d) < 4:
            # print("D", d)
            return
        char = d[3]
        position = d[2][4:]  # Removes prefix '@@ -'
        position = position[:-4]  # Removes suffix space@@\n
        previous = position.split(" ")[0]
        pre_start = int(previous.split(",")[0])
        #print("DIFFLIB position", position, "char", inserted_chars)
        pre_chars = None
        try:
            pre_chars = previous.split(",")[1]
        except IndexError:
            pass
        post = position.split(" ")[1]
        post_start = int(post.split(",")[0])
        post_chars = None
        try:
            post_chars = post.split(",")[1]
        except IndexError:
            pass

        # print(inserted_chars, " previous", pre_start, pre_chars, " post", post_start, post_chars)
        """
        Replacing 'way' with 'the' start position 13
        -w  previous 13 3  post 13 3
        
        Replacing 's' with 'T'  (highlight s and replace with T
        -s  previous 4 None  post 4 None
        """
        # No additions or deletions
        if pre_start == post_start and pre_chars == post_chars:
            self.highlight()
            self.prev_text = copy(self.text)
            return

        """
        Adding 'X' at inserted position 5, note: None as no number is provided from difflib
        +X  previous 4 0  post 5 None
        
        Adding 'qda' at inserted position 5 (After 'This')
        +q  previous 4 0  post 5 3
        
        Removing 'X' from position 5, note None
        -X  previous 5 None  post 4 0
        
        Removing 'the' from position 13
        -t  previous 13 3  post 12 0
        """
        if pre_chars is None:
            pre_chars = 1
        pre_chars = -1 * int(pre_chars)  # String if not None
        if post_chars is None:
            post_chars = 1
        post_chars = int(post_chars)  # String if not None

        # print("XXX", char, " previous", pre_start, pre_chars, " post", post_start, post_chars)
        # Adding characters
        if char[0] == "+":
            for c in self.codetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                if not changed and c['newpos0'] is not None and c['newpos0'] < pre_start < c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
            for c in self.annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start < c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
            for c in self.casetext:
                changed = False
                print(pre_chars)
                # print("newpos0", c['newpos0'], "pre start", pre_start)
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start < c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
            self.highlight()
            self.prev_text = copy(self.text)
            return

        # Removing characters
        if char[0] == "-":
            for c in self.codetext:
                changed = False
                # print("CODE newpos0", c['newpos0'], "pre start", pre_start, pre_chars, post_chars)
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['newpos0'],  pre_start, c['newpos1'], pre_chars, post_chars)
                # print(c['newpos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['npos0'] is not None and not changed and c['newpos0'] >= pre_start and c['newpos1'] < pre_start + -1 \
                        * pre_chars + post_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start <= c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                        c['newpos0'] = None
            for c in self.annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                    # Remove, as entire text is being removed (e.g. copy replace)
                    # print(changed, c['newpos0'],  pre_start, c['newpos1'], pre_chars, post_chars)
                    # print(c['newpos0'], ">",  pre_start, "and", c['newpos1'], "<", pre_start + -1*pre_chars + post_chars)
                    if not changed and c['newpos0'] >= pre_start and c['newpos1'] < pre_start + -1 * pre_chars + post_chars:
                        c['newpos0'] += pre_chars + post_chars
                        c['newos1'] += pre_chars + post_chars
                        changed = True
                        self.code_deletions.append("delete from annotations where anid=" + str(c['anid']))
                        c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start <= c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append("delete from annotation where anid=" + str(c['anid']))
                        c['newpos0'] = None
            for c in self.casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['newpos0'],  pre_start, c['newpos1'], pre_chars, post_chars)
                # print(c['newpos0'], ">",  pre_start, "and", c['newpos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= pre_start and c['newpos1'] < pre_start + -1 \
                        * pre_chars + post_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start <= c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                        c['newpos0'] = None
        self.highlight()
        self.prev_text = copy(self.text)

    def highlight(self):
        """ Add coding and annotation highlights. """

        self.remove_formatting()
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])

        #self.ui.textEdit.blockSignals(True)
        self.plain_text_edit.blockSignals(True)
        #cursor = self.ui.textEdit.textCursor()
        cursor = self.plain_text_edit.textCursor()
        for item in self.casetext:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.green)
                cursor.setCharFormat(format_)
        for item in self.annotations:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.yellow)
                cursor.setCharFormat(format_)
        for item in self.codetext:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.red)
                cursor.setCharFormat(format_)
        #self.ui.textEdit.blockSignals(False)
        self.plain_text_edit.blockSignals(False)

    def remove_formatting(self):
        """ Remove formatting from text edit on changed text.
         Useful when pasting mime data (rich text or html) from clipboard. """

        #self.ui.textEdit.blockSignals(True)
        self.plain_text_edit.blockSignals(True)
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])
        #cursor = self.ui.textEdit.textCursor()
        cursor = self.plain_text_edit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        #cursor.setPosition(len(self.ui.textEdit.toPlainText()), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setPosition(len(self.plain_text_edit.toPlainText()), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(format_)
        #self.ui.textEdit.blockSignals(False)
        self.plain_text_edit.blockSignals(False)

    def accept(self):
        """ Accepted button overridden method. """

        #self.text = self.ui.textEdit.toPlainText()
        self.text = self.plain_text_edit.toPlainText()
        try:
            cur = self.app.conn.cursor()
            cur.execute("update source set fulltext=? where id=?", (self.text, self.fid))
            for item in self.code_deletions:
                cur.execute(item)
            self.code_deletions = []
            self.update_codings()
            self.update_annotations()
            self.update_casetext()
            self.app.conn.commit()  # Commit all changes in one go to prevent inconsistencies of the database
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # Revert all changes
            raise
        # update doc in vectorstore
        if self.has_changed:
            if self.app.settings['ai_enable'] == 'True':
                self.app.ai.sources_vectorstore.import_document(self.fid, self.name, self.text, update=True)
            else:
                # AI is disabled. Delete the file from the vectorstore. It will be reimported later when the AI is enabled again. 
                self.app.ai.sources_vectorstore.delete_document(self.fid)
        super(DialogEditTextFile, self).accept()

    def update_casetext(self):
        """ Update linked case text positions. """

        sql = "update case_text set pos0=?, pos1=? where id=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for c in self.casetext:
            if c['newpos0'] is not None:
                cur.execute(sql, [c['newpos0'], c['newpos1'], c['id'], c['newpos0'], c['newpos1']])
            if c['newpos1'] >= len(self.text):
                cur.execute("delete from case_text where id=?", [c['id']])

    def update_annotations(self):
        """ Update annotation positions. """

        sql = "update annotation set pos0=?, pos1=? where anid=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for a in self.annotations:
            if a['newpos0'] is not None:
                cur.execute(sql, [a['newpos0'], a['newpos1'], a['anid'], a['newpos0'], a['newpos1']])
            if a['newpos1'] >= len(self.text):
                cur.execute("delete from annotation where anid=?", [a['anid']])

    def update_codings(self):
        """ Update coding positions and seltext. """

        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
        for c in self.codetext:
            if c['newpos0'] is not None:
                seltext = self.text[c['newpos0']:c['newpos1']]
                cur.execute(sql, [c['newpos0'], c['newpos1'], seltext, c['ctid']])
            if c['newpos1'] >= len(self.text):
                cur.execute("delete from code_text where ctid=?", [c['ctid']])

    def textedit_menu(self, position):
        """ Context menu for select all and copy of text. """

        #if self.ui.textEdit.toPlainText() == "":
        if self.plain_text_edit.toPlainText() == "":
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_select_all = menu.addAction(_("Select all"))
        action_copy = menu.addAction(_("Copy"))
        #action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        action = menu.exec(self.plain_text_edit.mapToGlobal(position))
        if action == action_copy:
            #selected_text = self.ui.textEdit.textCursor().selectedText()
            selected_text = self.plain_text_edit.textCursor().selectedText()
            cb = QtWidgets.QApplication.clipboard()
            cb.setText(selected_text)
        if action == action_select_all:
            #self.ui.textEdit.selectAll()
            self.plain_text_edit.selectAll()
