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
        self.fill_table()
        self.ui.tableWidget.itemChanged.connect(self.on_item_changed)
        self.ui.buttonBox.accepted.connect(self.ok)
        # self.ui.buttonBox.rejected.connect(self.cancel) 
        self.ui.buttonBox.helpRequested.connect(self.help)
        
    def table_add_row(self, name, codings_count, current_coder, hidden_coders=[], position="bottom"):
        """Will add a new row to the tableWidget, but only if name is not empty and name 
        is not already in the table.
        

        Args:
            name (str): Coder name
            codings_count (Any): codings
            current_coder (str): the current coder will be selected 
            hidden_coders (list, optional): List of hidden coders. Defaults to [].
            position (str, optional): Position in the table. Can be "top" or "bottom". Defaults to "bottom".
        """
        if name == "":
            return
        # Check if the name is already in the table:
        for row in range(self.ui.tableWidget.rowCount()):
            if self.ui.tableWidget.item(row, 0).text() == name:
                return
        if position == "top":
            row = 0
        else:
            row = self.ui.tableWidget.rowCount()
        self.ui.tableWidget.insertRow(row)
        
        # name
        name_item = QtWidgets.QTableWidgetItem(name)
        name_item.setFlags(
            QtCore.Qt.ItemFlag.ItemIsUserCheckable |
            QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable) # non editable
        if name == current_coder:
            name_item.setCheckState(QtCore.Qt.CheckState.Checked)
            current_coder_found = True
        else:
            name_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
        self.ui.tableWidget.setItem(row, 0, name_item)
        
        # codings count
        count_item = QtWidgets.QTableWidgetItem(str(codings_count))
        count_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
        count_item.setFlags(count_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.ui.tableWidget.setItem(row, 1, count_item)
        
        # visibility
        combo = QtWidgets.QComboBox()
        combo.addItems([_('visible'), _('hidden')])
        combo.setEditable(False)
        if name in hidden_coders:
            combo.setCurrentIndex(1)
        else:
            combo.setCurrentIndex(0)
        combo.currentIndexChanged.connect(lambda index: self.on_coder_visibility_changed(row, index))
        self.ui.tableWidget.setCellWidget(row, 2, combo)   
                
    def fill_table(self):
        self.ui.tableWidget.blockSignals(True)
        try:
            # clear
            rows = self.ui.tableWidget.rowCount()
            for r in range(0, rows):
                self.ui.tableWidget.removeRow(0)

            # Add coder names from all tables including count for codings
            current_coder = self.app.settings['codername']
            hidden_coders = []
            if self.app.conn is not None:
                sql = """
                SELECT owner, SUM(cnt) AS count
                FROM (
                    SELECT owner, COUNT(*) AS cnt FROM code_image GROUP BY owner
                    UNION ALL SELECT owner, COUNT(*) AS cnt FROM code_text GROUP BY owner
                    UNION ALL SELECT owner, COUNT(*) AS cnt FROM code_av   GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM code_name GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM code_cat GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM cases GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM case_text GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM attribute GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM attribute_type GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM source GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM annotation GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM journal GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM manage_files_display GROUP BY owner
                    UNION ALL SELECT owner, 0 AS cnt FROM files_filter GROUP BY owner
                ) t
                GROUP BY owner
                ORDER BY owner;
                """
                cur = self.app.conn.cursor()
                cur.execute(sql)
                results = cur.fetchall()
                for name in results:
                    self.table_add_row(name[0], name[1], current_coder, hidden_coders, 'bottom')

                # Ensure that current_coder and the default coders ("[AI]", "[Speaker_markings]") are added
                self.table_add_row(current_coder, 0, current_coder, hidden_coders, 'top')
                # for future updates: self.table_add_row('[AI]', 0, current_coder, hidden_coders, 'bottom')
                self.table_add_row('[Speaker_markings]', 0, current_coder, hidden_coders, 'bottom')
                
                self.ui.tableWidget.resizeColumnsToContents()
        finally:
            self.ui.tableWidget.blockSignals(False)

    def on_item_changed(self, item):
        """Called if the selection status of a row changes. 
        Ensures that one item is selected at any time. We always need a unique coder name.
        """
        sel_state = self.ui.tableWidget.item(item.row(), 0).checkState() == QtCore.Qt.CheckState.Checked
        if sel_state:
            self.ui.tableWidget.blockSignals(True)
            try: 
                for row in range(self.ui.tableWidget.rowCount()):
                    if row != item.row():
                        self.ui.tableWidget.item(row, 0).setCheckState(QtCore.Qt.CheckState.Unchecked)
            finally:
                self.ui.tableWidget.blockSignals(False)
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

    def ok(self):
        return

    @staticmethod
    def help():
        """ Open help in browser. """
        url = "https://github.com/ccbogel/QualCoder/wiki/"
        webbrowser.open(url)
