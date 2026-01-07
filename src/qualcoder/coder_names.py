# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import logging
import re
import datetime
from typing import Any, Dict, List, Tuple, Optional
from PyQt6 import QtCore, QtWidgets
import webbrowser
from random import randint
import sqlite3

from .GUI.ui_dialog_coder_names import Ui_Dialog_coders
from .color_selector import colors
from .helpers import Message

logger = logging.getLogger(__name__)
max_name_len: int = 63

class DialogCoderNames(QtWidgets.QDialog):
    """Extracts speaker names from a transcript of an interview or a focus group, lets the user select
    which to keep, and creates codes for each speaker in the "Speakers" category.
    """

    def __init__(self, app):
        self.app = app
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_coders()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        headers = [_("Name"), _("Codings"), _("Visibility")]
        self.ui.tableWidget.setColumnCount(len(headers))
        self.ui.tableWidget.setHorizontalHeaderLabels(headers)
        self.coder_names = []
        self.current_coder = self.app.settings['codername']
        self.fill_table()
        self.ui.tableWidget.itemChanged.connect(self.on_item_changed)
        self.ui.pushButton_add.clicked.connect(self.add_coder_name)
        self.ui.pushButton_rename.clicked.connect(self.rename_coder)
        self.ui.pushButton_merge.clicked.connect(self.merge_coder)
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel) 
        self.ui.buttonBox.helpRequested.connect(self.help)

        
    def read_coder_names(self):
        """
        Reads the content of the table 'coder_names' into self.coder_names.
        If no project is open, only self.app.settings['codername'] will be added.
        """
        self.coder_names = []
        if self.app.conn is None: # no project open
            self.coder_names.append((self.current_coder, 1, 0))
            self.cursor = None
        else: 
            self.cursor = self.app.conn.cursor()
            # collect coder names and codings count
            sql = """
                SELECT
                    cn.name,
                    cn.visibility,
                    (
                        SELECT COUNT(*) FROM code_image ci WHERE ci.owner = cn.name
                    ) +
                    (
                        SELECT COUNT(*) FROM code_text ct WHERE ct.owner = cn.name
                    ) +
                    (
                        SELECT COUNT(*) FROM code_av ca WHERE ca.owner = cn.name
                    ) AS codings_count
                FROM coder_names cn;
            """
            self.cursor.execute(sql)
            self.coder_names = self.cursor.fetchall()
        
                        
    def fill_table(self):
        self.ui.tableWidget.blockSignals(True)
        try:
            # clear
            rows = self.ui.tableWidget.rowCount()
            for r in range(0, rows):
                self.ui.tableWidget.removeRow(0)

            # Add coder names from all tables including count for codings
            self.app.update_coder_names()
            self.read_coder_names()            

            for item in self.coder_names:
                row = self.ui.tableWidget.rowCount()
                self.ui.tableWidget.insertRow(row)
                
                # name
                name = item[0]
                name_item = QtWidgets.QTableWidgetItem(name)
                name_item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsUserCheckable |
                    QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable) # non editable
                if name == self.current_coder:
                    name_item.setCheckState(QtCore.Qt.CheckState.Checked)
                else:
                    name_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
                self.ui.tableWidget.setItem(row, 0, name_item)
                
                # codings count
                codings_count = str(item[2])
                count_item = QtWidgets.QTableWidgetItem(codings_count)
                count_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
                count_item.setFlags(count_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, 1, count_item)
                
                # visibility
                visible = item[1] == 1
                combo = QtWidgets.QComboBox()
                combo.addItems([_('visible'), _('hidden')])
                combo.setEditable(False)
                if visible:
                    combo.setCurrentIndex(0)
                else:
                    combo.setCurrentIndex(1)
                combo.currentIndexChanged.connect(
                   lambda index, r=row: self.on_coder_visibility_changed(r, index)
                )
                self.ui.tableWidget.setCellWidget(row, 2, combo)   
        finally:
            self.ui.tableWidget.blockSignals(False)
            # self.ui.tableWidget.verticalHeader().setStretchLastSection(True)
            self.ui.tableWidget.resizeColumnsToContents()
            self.ui.tableWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)


    def on_item_changed(self, item):
        """Called if the selection status of a row changes. 
        Ensures that one item is selected at any time. We always need a unique coder name.
        """
        is_selected = self.ui.tableWidget.item(item.row(), 0).checkState() == QtCore.Qt.CheckState.Checked
        if is_selected:            
            self.ui.tableWidget.blockSignals(True)
            try: 
                for row in range(self.ui.tableWidget.rowCount()):
                    if row != item.row():
                        self.ui.tableWidget.item(row, 0).setCheckState(QtCore.Qt.CheckState.Unchecked)
            finally:
                self.ui.tableWidget.blockSignals(False)
            self.current_coder = self.ui.tableWidget.item(item.row(), 0).text()
            # ensure current coder is set to "visible"
            combo = self.ui.tableWidget.cellWidget(item.row(), 2)
            combo.setCurrentIndex(0)            
        else:
            self.ui.tableWidget.blockSignals(True)
            try:
                self.ui.tableWidget.item(item.row(), 0).setCheckState(QtCore.Qt.CheckState.Checked)
            finally:
                self.ui.tableWidget.blockSignals(False)
            Message(self.app, _('Coder'), _('We always need one coder selected. Choose another one if you want to change.'), 'critical').exec()
        return

        
    def on_coder_visibility_changed(self, row, index):
        """Called if the "Visibility" combo box is changed. 
        Ensures that the current coder will always stay visible."""
        if index == 1 and self.ui.tableWidget.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked:
            combo = self.ui.tableWidget.cellWidget(row, 2)
            combo.blockSignals(True)
            try: 
                combo.setCurrentIndex(0)
                Message(self.app, _('Coder'), _('You cannot hide the current coder.'), 'critical').exec()
            finally:
                combo.blockSignals(False)
        else:
            if self.cursor is not None:
                name = self.ui.tableWidget.item(row, 0).text()
                visibility = 1 if index == 0 else 0
                self.cursor.execute("UPDATE coder_names SET visibility = ? WHERE name = ?", (visibility, name))           


    def add_coder_name(self):
        if self.app.conn is not None:
            dialog = QtWidgets.QInputDialog(self)
            dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            dialog.setWindowTitle(_("Coder"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
            dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
            dialog.setLabelText(_("New coder name:"))
            ok = dialog.exec()
            if not ok:
                return
            new_name = str(dialog.textValue())
            try:
                self.cursor.execute('INSERT INTO coder_names VALUES (?, 1)', (new_name, ))
            except sqlite3.IntegrityError:
                Message(self.app, _('Coder'), _('Name already exists.'), 'critical').exec()
                return
            self.fill_table()
        else:
            Message(self.app, _('Coder'), _('Open a project first.'), 'critical').exec()

    def _rename_coder(self, old_name, new_name) -> bool:
        """Renames the coder (owner) in all tables. 
        This function can also be used to merge two coder names if new_name is already existing.
        If any error occures, the operation roles back completely so that no partial renaming
        happens.

        Args:
            old_name (str)
            new_name (str)

        Returns:
            bool: True on success, False on error
        """
        err_msg = _('An error occured while renaming.')
        if self.app.conn is not None:
            self.cursor.execute("savepoint rename_coder") # allows to return to this point in case of an error
            try: 
                # update coder name in all tables
                sqls = ["update code_image set owner=? where owner=?",
                        "update code_av set owner=? where owner=?",
                        "update code_name set owner=? where owner=?",
                        "update code_cat set owner=? where owner=?",
                        "update cases set owner=? where owner=?",
                        "update case_text set owner=? where owner=?",
                        "update attribute set owner=? where owner=?",
                        "update attribute_type set owner=? where owner=?",
                        "update source set owner=? where owner=?",
                        "update journal set owner=? where owner=?",
                        "update manage_files_display set owner=? where owner=?",
                        "update files_filter set owner=? where owner=?"]
                for sql in sqls:
                    try:
                        self.cursor.execute(sql, [new_name, old_name])
                    except Exception as e:
                        table_name = "<unknown>"
                        match = re.search(r'^\s*update\s+([^\s]+)', sql, re.IGNORECASE)
                        if match:
                            table_name = match.group(1)
                        err_msg = _('An error ocurred while changing the name in "{}".').format(table_name)
                        raise

                # Code text has an extensive unique constraint across: cid, fid, pos0, pos1, owner
                # If the renaming produces duplicates, ignore and delete them.
                self.cursor.execute("select ctid from code_text where owner=?", [old_name])
                ctid_res = self.cursor.fetchall()
                for row in ctid_res:
                    try:
                        self.cursor.execute("update code_text set owner=? where ctid=?", [new_name, row[0]])
                    except sqlite3.IntegrityError:
                        self.cursor.execute("delete from code_text where ctid=?", [row[0]])

                # Annotation has an extensive unique constraint across: fid, pos0, pos1, owner
                self.cursor.execute("select anid from annotation where owner=?", [old_name])
                anid_res = self.cursor.fetchall()
                for row in anid_res:
                    try:
                        self.cursor.execute("update annotation set owner=? where anid=?", [new_name, row[0]])
                    except sqlite3.IntegrityError:
                        self.cursor.execute("delete from annotation where anid=?", [row[0]])
                        
                # update coder_names table
                try:
                    self.cursor.execute("update coder_names set name=? where name=?", [new_name, old_name])
                except sqlite3.IntegrityError: # new_name already exists (=merging), delete old_name 
                    self.cursor.execute("delete from coder_names where name=?", [old_name])


            except Exception as e:
                # In case of an error that could not be resolved (like deleting duplicates), 
                # we restore the state before renaming started, and show an error message so
                # users can address the issue manually.
                self.cursor.execute("rollback to rename_coder")
                self.cursor.execute("release rename_coder")
                err_msg += f'\n{e}'
                Message(self.app, _('Coder'), err_msg, "critical").exec()
                return False
            
            self.cursor.execute("release rename_coder") # success, delete savepoint

        if self.current_coder == old_name:
            self.current_coder = new_name
        self.fill_table()
        return True


    def rename_coder(self, merge=False):
        row = self.ui.tableWidget.currentRow()
        if row == -1:
            Message(self.app, _('Coder'), _('No name selected.'), 'critical').exec()
            return
        
        old_name = self.ui.tableWidget.item(row, 0).text()
        dialog = QtWidgets.QInputDialog(self)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Coder"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        if merge:
            dialog.setLabelText(_('Merge "{}" into:').format(old_name))
        else:
            dialog.setLabelText(_('Rename "{}" into:').format(old_name))
            dialog.setTextValue(old_name)
        ok = dialog.exec()
        if not ok:
            return
        new_name = str(dialog.textValue())
        if new_name == old_name:
            Message(self.app, _('Coder'), _('Old and new name are identical.'), 'critical').exec()
            return
        # check if new_name already exists (required for merging, not allowed for renaming)
        new_name_exists = False
        for item in self.coder_names:
            if new_name == item[0]:
                new_name_exists = True
                break
        if merge and not new_name_exists:
            Message(self.app, _('Coder'), _('The coder name you want to merge into does not exist.'), 'critical').exec()
            return
        if not merge and new_name_exists:
            Message(self.app, _('Coder'), _('The new coder name already exists.'), 'critical').exec()
            return
        
        if self._rename_coder(old_name, new_name):
            if merge:
                Message(self.app, _('Coder'), _('Merging was successful. If you click OK, "{}" will be changed to "{}" in all tables.').format(old_name, new_name) , 'Information').exec()
            else:
                Message(self.app, _('Coder'), _('Renaming was successful. If you click OK, "{}" will be changed to "{}" in all tables.').format(old_name, new_name) , 'Information').exec()


    def merge_coder(self):
        self.rename_coder(merge=True)


    def ok(self):
        if self.app.conn is not None:
            self.cursor.execute('update project set codername=?', [self.current_coder])
            self.app.conn.commit() # this writes all the changes finally to the database
        self.app.settings['codername'] = self.current_coder
        
        
    def cancel(self):
        if self.app.conn is not None:
            self.app.conn.rollback()        


    def help(self):
        """ Open help in browser. """
        self.app.help_wiki("")