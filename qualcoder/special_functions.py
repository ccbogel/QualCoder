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
import sys
import traceback

from PyQt6 import QtGui, QtWidgets, QtCore

from .code_text import DialogCodeText  # for isinstance()
from .confirm_delete import DialogConfirmDelete
from .GUI.base64_helper import *
from .GUI.ui_special_functions import Ui_Dialog_special_functions
from .helpers import Message
from .merge_projects import MergeProjects
from .select_items import DialogSelectItems
from .text_file_replacement import ReplaceTextFile

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogSpecialFunctions(QtWidgets.QDialog):
    """ Dialog for special QualCoder functions.
    """

    app = None
    parent_text_edit = None
    tab_coding = None  # Tab widget coding tab for updates

    # For Replacing a text file with another and keeping codings
    file_to_replace = None
    file_replacement = None

    # For merging projects
    merge_project_path = ""
    projects_merged = False

    def __init__(self, app, parent_text_edit, tab_coding, parent=None):

        super(DialogSpecialFunctions, self).__init__(parent)
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_special_functions()
        self.ui.setupUi(self)
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.tab_coding = tab_coding
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.merge_project_path = ""
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.pushButton_select_text_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_select_text_file.setFocus()
        self.ui.pushButton_select_replacement_text_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_select_project.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
        self.ui.pushButton_text_starts.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_text_starts.clicked.connect(self.change_text_code_start_positions)
        self.ui.pushButton_text_ends.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_text_ends.clicked.connect(self.change_text_code_end_positions)
        self.ui.pushButton_text_update.setIcon(QtGui.QIcon(pm))
        self.ui.groupBox_text_positions.hide()
        self.ui.pushButton_select_text_file.pressed.connect(self.select_original_text_file)
        self.ui.pushButton_select_replacement_text_file.pressed.connect(self.select_replacement_text_file)
        self.ui.pushButton_text_update.setEnabled(False)
        self.ui.pushButton_text_update.pressed.connect(self.replace_file_update_codings)
        self.ui.pushButton_merge.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_select_project.pressed.connect(self.select_project_folder)
        self.ui.pushButton_merge.setEnabled(False)
        self.ui.pushButton_merge.pressed.connect(self.merge_projects)

    # Functions to merge external project into this project
    def select_project_folder(self):
        """ Select another .qda project """

        self.merge_project_path = ""
        default_directory = self.app.settings['directory']
        if default_directory == "":
            default_directory = os.path.expanduser('~')
        self.merge_project_path = QtWidgets.QFileDialog.getExistingDirectory(self,
                                                                             _('Open project directory'),
                                                                             default_directory)
        if self.merge_project_path is False or len(self.merge_project_path) < 5:
            Message(self.app, _("Error"), _("No project selected")).exec()
            return
        if self.merge_project_path[-4:] != ".qda":
            Message(self.app, _("Error"), _("Not a QualCoder project")).exec()
            return
        if self.merge_project_path == self.app.project_path:
            Message(self.app, _("Error"), _("The same project")).exec()
            return
        msg = _("Merge") + "\n" + self.merge_project_path + "\n" + _("into") + "\n" + self.app.project_path + "\n"
        msg += _("Press Run Button to merge projects")
        Message(self.app, _("Merge projects"), msg).exec()
        self.ui.pushButton_merge.setEnabled(True)
        self.ui.pushButton_merge.setFocus()

    def merge_projects(self):
        """ Merge selected project into this project. """

        mp = MergeProjects(self.app, self.merge_project_path)
        self.parent_text_edit.append(mp.summary_msg)
        self.projects_merged = mp.projects_merged

    # Functions to update a text file but attempt to keep original codings
    def select_original_text_file(self):
        """ Select text file to replace. """

        self.file_to_replace = []
        file_texts = self.app.get_file_texts()
        ui = DialogSelectItems(self.app, file_texts, _("Delete files"), "single")
        ok = ui.exec()
        if not ok:
            return
        self.file_to_replace = ui.get_selected()
        if not self.file_to_replace:
            self.ui.pushButton_select_text_file.setToolTip(_("Select text file to replace"))
            return
        self.ui.pushButton_select_text_file.setToolTip(_("Replacing: ") + self.file_to_replace['name'])
        if self.file_to_replace and self.file_replacement:
            self.ui.pushButton_text_update.setEnabled(True)

    def select_replacement_text_file(self):
        """ Select replacement updated text file. """

        file_types = "Text Files (*.docx *.epub *.html *.htm *.md *.odt *.pdf *.txt)"
        filepath, ok = QtWidgets.QFileDialog.getOpenFileNames(None, _('Replacement file'),
                                                              self.app.settings['directory'], file_types)
        # options=QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        if not ok or filepath == []:
            self.ui.pushButton_select_replacement_text_file.setToolTip(_("Select replacement text file"))
            return
        self.file_replacement = filepath[0]
        self.ui.pushButton_select_replacement_text_file.setToolTip(_("Replacement file: ") + self.file_replacement)
        if self.file_to_replace and self.file_replacement:
            self.ui.pushButton_text_update.setEnabled(True)
            self.ui.pushButton_text_update.setToolTip(_("Press to replace the text file"))

    def replace_file_update_codings(self):
        """ Requires two files - original and replacement to be selected before button is enabled.
        Called by:
         pushButton_text_update """

        if self.file_to_replace is None or self.file_replacement is None:
            Message(self.app, _("No files selected"), _("No existing or replacement file selected")).exec()
            return
        ReplaceTextFile(self.app, self.file_to_replace, self.file_replacement)
        self.file_to_replace = None
        self.ui.pushButton_select_text_file.setToolTip(_("Select text file to replace"))
        self.file_replacement = None
        self.ui.pushButton_select_replacement_text_file.setToolTip(_("Select replacement text file"))

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
        if not res:
            return
        msg = _("Change ALL text code start positions in ALL text files by ")
        msg += str(delta) + _(" characters.\n")
        msg += _("Made by coder: ") + self.app.settings['codername'] + "\n"
        msg += str(len(res)) + _(" to change.") + "\n"
        msg += _("Backup project before performing this function.\n")
        msg += _("Press OK to continue.")
        ui = DialogConfirmDelete(self.app, msg, _("Change code start positions"))
        ok = ui.exec()
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
            seltext = ""
            try:
                seltext = cur.fetchone()[0]
            except TypeError:
                pass
            cur.execute(update_sql, [new_pos0, seltext, r[2], r[3], r[0], r[1], r[4]])
            self.app.conn.commit()
        self.parent_text_edit.append(
            _("All text codings by ") + self.app.settings['codername'] + _(" resized by ") + str(delta) + _(
                " characters."))
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
        if not res:
            return
        msg = _("Change ALL text code end positions in ALL text files by ")
        msg += str(delta) + _(" characters.\n")
        msg += _("Made by coder: ") + self.app.settings['codername'] + "\n"
        msg += str(len(res)) + _(" to change.") + "\n"
        msg += _("Backup project before performing this function.\n")
        msg += _("Press OK to continue.")
        ui = DialogConfirmDelete(self.app, msg, _("Change code end positions"))
        ok = ui.exec()
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
            seltext = ""
            try:
                seltext = cur.fetchone()[0]
            except TypeError:
                pass
            cur.execute(update_sql, [new_pos1, seltext, r[2], r[3], r[0], r[1], r[4]])
            self.app.conn.commit()
        self.parent_text_edit.append(
            _("All text codings by ") + self.app.settings['codername'] + _(" resized by ") + str(delta) + _(
                " characters."))
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
