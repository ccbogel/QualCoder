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
"""

import datetime
import os
import logging
import qtawesome as qta

from PyQt6 import QtCore, QtWidgets

from .add_attribute import DialogAddAttribute
from .confirm_delete import DialogConfirmDelete
from .memo import DialogMemo
from .GUI.ui_dialog_manage_attributes import Ui_Dialog_manage_attributes
from .GUI.ui_dialog_assign_attribute import Ui_Dialog_assignAttribute

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogManageAttributes(QtWidgets.QDialog):
    """ Attribute management. Create and delete attributes in the attributes table.
    """

    NAME_COLUMN = 0
    CASE_FILE_COLUMN = 1
    VALUETYPE_COLUMN = 2
    MEMO_COLUMN = 3
    app = None
    parent_tetEdit = None
    attributes = []

    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_textEdit = parent_text_edit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_attributes()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.get_attributes()
        self.fill_table_widget()
        # Initial resize of table columns
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.pushButton_add.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_add.clicked.connect(self.add_attribute)
        self.ui.pushButton_delete.setIcon(qta.icon('mdi6.delete-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_delete.clicked.connect(self.delete_attribute)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.tableWidget.cellChanged.connect(self.cell_modified)
        self.ui.tableWidget.itemSelectionChanged.connect(self.count_selected_items)
        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)

    def get_attributes(self):
        """ Get attributes from sqlite.
        caseOrFile  also now contains journal. """

        self.attributes = []
        cur = self.app.conn.cursor()
        cur.execute("select name, date, owner, memo, caseOrFile, valuetype from attribute_type order by name")
        result = cur.fetchall()
        self.attributes = []
        keys = 'name', 'date', 'owner', 'memo', 'caseOrFile', 'valuetype'
        for row in result:
            self.attributes.append(dict(zip(keys, row)))

    def count_selected_items(self):
        """ Update label with the count of selected items. """

        indexes = self.ui.tableWidget.selectedIndexes()
        ix = [i.row() for i in indexes]
        i = set(ix)
        self.ui.label.setText(_("Attributes: ") + f"{len(i)}/{len(self.attributes)}")

    def add_attribute(self):
        """ When add button pressed, open addItem dialog to get new attribute text.
        AddItem dialog checks for duplicate attribute name.
        New attribute is added to the model and database. """

        ui = DialogAddAttribute(self.app)
        ui.exec()  # ok = ui.exec() does not pick up pressing the cancel button
        name = ui.new_name
        value_type = ui.value_type
        if name == "":
            return
        dialog_assign = QtWidgets.QDialog()
        ui = Ui_Dialog_assignAttribute()
        ui.setupUi(dialog_assign)
        dialog_assign.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt '
        font += f'"{self.app.settings["font"]}";'
        dialog_assign.setStyleSheet(font)
        dialog_assign.exec()
        case_or_file = "case"
        if ui.radioButton_files.isChecked():
            case_or_file = "file"
        if ui.radioButton_cases .isChecked():
            case_or_file = "case"
        if ui.radioButton_journals.isChecked():
            case_or_file = "journal"
        # Update attributes list and database
        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        item = {'name': name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': now_date, 'valuetype': value_type,
                'caseOrFile': case_or_file}
        self.attributes.append(item)
        cur = self.app.conn.cursor()
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                    (item['name'], item['date'], item['owner'], item['memo'], item['caseOrFile'], item['valuetype']))
        self.app.conn.commit()
        sql = "select id from source"
        cur.execute(sql)
        ids = cur.fetchall()
        if case_or_file == "case":
            sql = "select caseid from cases"
            cur.execute(sql)
            ids = cur.fetchall()
        if case_or_file == "journal":
            sql = "select jid from journal"
            cur.execute(sql)
            ids = cur.fetchall()
        for id_ in ids:
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            cur.execute(sql, (item['name'], "", id_[0], case_or_file, now_date, self.app.settings['codername']))
        self.app.conn.commit()
        self.fill_table_widget()
        self.parent_textEdit.append(f"{_('Attribute added: ')}{item['name']} -> {_(case_or_file)}")

    def delete_attribute(self):
        """ When delete button pressed, attribute is deleted from database. """

        rows_to_delete = []  # for table widget ids
        names_to_delete = []
        for itemWidget in self.ui.tableWidget.selectedItems():
            rows_to_delete.append(int(itemWidget.row()))
            names_to_delete.append(self.ui.tableWidget.item(itemWidget.row(), 0).text())
        rows_to_delete.sort(reverse=True)
        if len(names_to_delete) == 0:
            return
        ui = DialogConfirmDelete(self.app, "\n".join(names_to_delete))
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        for name in names_to_delete:
            for attr in self.attributes:
                if attr['name'] == name:
                    self.parent_textEdit.append(_("Attribute deleted: ") + attr['name'])
                    cur.execute("delete from attribute where name = ?", (name,))
                    cur.execute("delete from attribute_type where name = ?", (name,))
        self.app.conn.commit()
        self.attributes = []
        cur.execute("select name, date, owner, memo, caseOrFile, valuetype from attribute_type")
        result = cur.fetchall()
        keys = 'name', 'date', 'owner', 'memo', 'caseOrFile', 'valuetype'
        for row in result:
            self.attributes.append(dict(zip(keys, row)))
        self.fill_table_widget()
        self.parent_textEdit.append(_("Attributes deleted: ") + ",".join(names_to_delete))

    def cell_selected(self):
        """ When the table widget memo cell is selected display the memo.
        Update memo text, or delete memo by clearing text.
        If a new memo also show in table widget by displaying Memo in the memo column. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.MEMO_COLUMN:
            ui = DialogMemo(self.app, _("Memo for Attribute ") + self.attributes[x]['name'],
                            self.attributes[x]['memo'])
            ui.exec()
            memo = ui.memo
            if memo != self.attributes[x]['memo']:
                self.attributes[x]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update attribute_type set memo=? where name=?", (memo, self.attributes[x]['name']))
                self.app.conn.commit()
            if memo == "":
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem(_("Memo")))
            self.attributes[x]['memo'] = str(memo)

    def table_menu(self, position):
        """ Context menu for displaying table rows in differing order """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()
        if row == -1 or col == -1:
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        text_ = str(self.ui.tableWidget.item(row, col).text())
        action_to_character = None
        if col == 2 and text_ == _("numeric"):
            action_to_character = menu.addAction(_("Change to character"))
        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_to_character:
            attr_name = str(self.ui.tableWidget.item(row, 0).text())
            cur = self.app.conn.cursor()
            print(attr_name)
            cur.execute('update attribute_type set valuetype="character" where name=?', [attr_name])
            self.app.conn.commit()
            self.get_attributes()
            self.fill_table_widget()

    def cell_modified(self):
        """ If the attribute name has been changed in the table widget and update the database. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:
            new_name = str(self.ui.tableWidget.item(x, y).text()).strip()
            # Check that no other attribute has this text and this is not empty
            update = True
            if new_name == "":
                update = False
            for att in self.attributes:
                if att['name'] == new_name:
                    update = False
            if update:
                # Update attribute type list and database
                cur = self.app.conn.cursor()
                cur.execute("update attribute_type set name=? where name=?", (new_name, self.attributes[x]['name']))
                cur.execute("update attribute set name=? where name=?", (new_name, self.attributes[x]['name']))
                self.app.conn.commit()
                self.parent_textEdit.append(
                    _("Attribute renamed from: ") + self.attributes[x]['name'] + _(" to ") + new_name)
                self.attributes[x]['name'] = new_name
            else:  # Put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.attributes[x]['name'])

    def fill_table_widget(self):
        """ Fill the table widget with attribute details. """

        self.ui.label.setText(_("Attributes: ") + str(len(self.attributes)))
        rows = self.ui.tableWidget.rowCount()
        for i in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        self.ui.tableWidget.setColumnCount(4)
        self.ui.tableWidget.setHorizontalHeaderLabels([_("Name"), _("Assigned to"), _("Type"), _("Memo")])
        for row, a in enumerate(self.attributes):
            self.ui.tableWidget.insertRow(row)
            item = QtWidgets.QTableWidgetItem(a['name'])
            item.setToolTip(a['date'] + "\n" + a['owner'])
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['caseOrFile'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.CASE_FILE_COLUMN, item)
            m_text = ""
            mtmp = a['memo']
            if mtmp is not None and mtmp != "":
                m_text = _("Yes")
            item = QtWidgets.QTableWidgetItem(m_text)
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.MEMO_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['valuetype'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.VALUETYPE_COLUMN, item)
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.resizeRowsToContents()
