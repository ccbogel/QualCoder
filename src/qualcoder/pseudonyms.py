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
import json
import os
import random
import string
from PyQt6 import QtCore, QtWidgets
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/

from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_pseudonyms import Ui_Dialog_pseudonyms
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class Pseudonyms(QtWidgets.QDialog):
    """ Create pseudonyms for original data. e.g. person names.
    Saves a pseudonyms.json file inside the qda data folder.
    Load json file for display and review.
    Can add or delete original-pseudonym pairs.
    Case sensitive, so TOM != Tom != tom
    Must have unique original text, and unique pseudonym text.
    Minimum original length = 2 characters.
    """

    def __init__(self, app):
        self.app = app
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_pseudonyms()
        self.ui.setupUi(self)
        # Note: table - selection behaviour - select rows
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.ui.tableWidget.setHorizontalHeaderLabels([_("Original"), _("Pseudonym")])
        self.ui.label_2.setPixmap(qta.icon('mdi6.arrow-right').pixmap(24, 24))
        self.ui.pushButton_add.setIcon(qta.icon('mdi6.plus', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_add.clicked.connect(self.add_pseudonym)
        self.ui.tableWidget.cellClicked.connect(self.delete_pseudonym)
        self.data = []
        print(os.path.join(self.app.project_path, "pseudonyms.json"))
        self.pseudonyms_filepath = os.path.join(self.app.project_path, "pseudonyms.json")
        self.fill_table()

    def add_pseudonym(self):
        """ Add pseudonym to json.
        Ensure the pseudonym has not been previously used. """

        original = self.ui.lineEdit_original.text()
        if len(original) < 2:
            Message(self.app, _("Original"), _("Too short") + "        ").exec()
            return
        pseudonym = self.ui.lineEdit_pseudonym.text()
        if 0 < len(pseudonym) < 3:
            Message(self.app, _("Original"), _("Too short, need 3 or more characters.\nLeave blank for random generated.")).exec()
            return
        if pseudonym == "":
            # Create random pseudonym
            characters = string.ascii_uppercase + string.digits
            pseudonym = ''.join(random.choices(characters, k=6))
        # Check if original used already, or pseudonym used already
        if any(d['original'] == original for d in self.data):
            Message(self.app, _("Original"), _("Original entry already exists.")).exec()
            return
        if any(d['pseudonym'] == pseudonym for d in self.data):
            Message(self.app, _("Pseudonym"), _("Pseudonym entry already exists.")).exec()
            return
        self.data.append({'original': original, 'pseudonym': pseudonym})
        # Save json
        with open(self.pseudonyms_filepath, 'w') as output_file:
            json.dump(self.data, output_file, indent=2)
        self.fill_table()

    def delete_pseudonym(self):
        """ Delete pseudonym from json data.
        It will be a single row with 2 items original, pseudonym, as single row selection is on.
        """

        row_items = self.ui.tableWidget.selectedItems()
        if not row_items:
            return
        item_to_remove = {"original": row_items[0].text(), "pseudonym": row_items[1].text()}
        ui = DialogConfirmDelete(self.app, f"{row_items[0].text()} --> {row_items[1].text()}")
        ok = ui.exec()
        if not ok:
            return
        self.data.remove(item_to_remove)
        # Save json
        with open(self.pseudonyms_filepath, 'w') as output_file:
            json.dump(self.data, output_file, indent=2)
        self.fill_table()

    def load_json(self):
        """ Pseudonyms stored in pseudonyms.json in qda data folder.
        Loads into list of dictionaries of 'original', ;pseudonym' keys.
        """

        self.data = []
        pseudonyms_filepath = os.path.join(self.app.project_path, "pseudonyms.json")
        try:
            with open(pseudonyms_filepath, "r") as f:
                self.data = json.load(f)
        except FileNotFoundError as err:
            print(err)

    def fill_table(self):

        self.load_json()
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        for row, data in enumerate(self.data):
            self.ui.tableWidget.insertRow(row)
            original_item = QtWidgets.QTableWidgetItem(data['original'])
            original_item.setFlags(original_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, 0, original_item)
            pseudonym_item = QtWidgets.QTableWidgetItem(data['pseudonym'])
            pseudonym_item.setFlags(pseudonym_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, 1, pseudonym_item)
