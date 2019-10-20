# -*- coding: utf-8 -*-

'''
Copyright (c) 2019 Colin Curtain

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
'''

import datetime
import os
import sys
import logging
import traceback

from PyQt5 import QtCore, QtGui, QtWidgets

from add_item_name import DialogAddItemName
from confirm_delete import DialogConfirmDelete
from memo import DialogMemo
from GUI.ui_dialog_manage_attributes import Ui_Dialog_manage_attributes
from GUI.ui_dialog_attribute_type import Ui_Dialog_attribute_type
from GUI.ui_dialog_assign_attribute import Ui_Dialog_assignAttribute

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception:") + "\n" + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogManageAttributes(QtWidgets.QDialog):
    ''' Attribute management. Create and delete attributes in the attributes table.
    '''

    NAME_COLUMN = 0
    CASE_FILE_COLUMN = 1
    VALUETYPE_COLUMN = 2
    MEMO_COLUMN = 3

    app = None
    parent_tetEdit = None
    attributes = []

    def __init__(self, app, parent_textEdit):
        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.attribute_type = []

        cur = self.app.conn.cursor()
        cur.execute("select name, date, owner, memo, caseOrFile, valuetype from attribute_type")
        result = cur.fetchall()
        for row in result:
            self.attribute_type.append({'name': row[0], 'date': row[1], 'owner': row[2],
            'memo': row[3], 'caseOrFile': row[4],'valuetype': row[5]})

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_attributes()
        self.ui.setupUi(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.fill_tableWidget()
        self.ui.pushButton_add.clicked.connect(self.add_attribute)
        self.ui.pushButton_delete.clicked.connect(self.delete_attribute)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.tableWidget.cellChanged.connect(self.cell_modified)

    def add_attribute(self):
        ''' When add button pressed, open addItem dialog to get new attribute text.
        AddItem dialog checks for duplicate attribute name.
        New attribute is added to the model and database '''

        ui = DialogAddItemName(self.attribute_type, _("New attribute name"))
        ui.exec_()
        newText = ui.get_new_name()
        if newText is None or newText == "":
            return
        Dialog_type = QtWidgets.QDialog()
        ui = Ui_Dialog_attribute_type()
        ui.setupUi(Dialog_type)
        ok = Dialog_type.exec_()
        valuetype = "character"
        if ok and ui.radioButton_numeric.isChecked():
            valuetype = "numeric"
        Dialog_assign = QtWidgets.QDialog()
        ui = Ui_Dialog_assignAttribute()
        ui.setupUi(Dialog_assign)
        ok = Dialog_assign.exec_()
        case_or_file = "case"
        if ok and ui.radioButton_files.isChecked():
            case_or_file = "file"
        # update attribute_type list and database
        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        item = {'name': newText, 'memo': "", 'owner': self.app.settings['codername'],
            'date': now_date, 'valuetype': valuetype,
            'caseOrFile': case_or_file}
        self.attribute_type.append(item)
        cur = self.app.conn.cursor()
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)"
            ,(item['name'], item['date'], item['owner'], item['memo'], item['caseOrFile'], item['valuetype']))
        self.app.conn.commit()
        sql = "select id from source"
        cur.execute(sql)
        ids = cur.fetchall()
        if case_or_file == "case":
            sql = "select caseid from cases"
            cur.execute(sql)
            ids = cur.fetchall()
        for id_ in ids:
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            cur.execute(sql, (item['name'], "", id_[0], case_or_file, now_date, self.app.settings['codername']))
        self.app.conn.commit()
        self.fill_tableWidget()
        self.parent_textEdit.append(_("Attribute added: ") + item['name'])

    def delete_attribute(self):
        ''' When delete button pressed, attribute is deleted from database '''

        tableRowsToDelete = []  # for table widget ids
        namesToDelete = []
        for itemWidget in self.ui.tableWidget.selectedItems():
            tableRowsToDelete.append(int(itemWidget.row()))
            namesToDelete.append(self.ui.tableWidget.item(itemWidget.row(), 0).text())
        tableRowsToDelete.sort(reverse=True)
        if len(namesToDelete) == 0:
            return
        ui = DialogConfirmDelete("\n".join(namesToDelete))
        ok = ui.exec_()
        if not ok:
            return
        for name in namesToDelete:
            for attr in self.attribute_type:
                if attr['name'] == name:
                    self.parent_textEdit.append(_("Attribute deleted: ") + attr['name'])
                    cur = self.app.conn.cursor()
                    cur.execute("delete from attribute where name = ?", (name,))
                    cur.execute("delete from attribute_type where name = ?", (name,))
        self.app.conn.commit()
        self.attribute_type = []
        cur.execute("select name, date, owner, memo, caseOrFile, valuetype from attribute_type")
        result = cur.fetchall()
        for row in result:
            self.attribute_type.append({'name': row[0], 'date': row[1], 'owner': row[2],
            'memo': row[3], 'caseOrFile': row[4],'valuetype': row[5]})
        self.fill_tableWidget()

    def cell_selected(self):
        ''' When the table widget memo cell is selected display the memo.
        Update memo text, or delete memo by clearing text.
        If a new memo also show in table widget by displaying YES in the memo column '''

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.MEMO_COLUMN:
            ui = DialogMemo(self.settings, _("Memo for Attribute ") + self.attribute_type[x]['name'],
            self.attribute_type[x]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo != self.attribute_type[x]['memo']:
                self.attribute_type[x]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update attribute_type set memo=? where name=?", (memo, self.attribute_type[x]['name']))
                self.app.conn.commit()
            if memo == "":
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem(_("Yes")))
            self.attribute_type[x]['memo'] = str(memo)

    def cell_modified(self):
        ''' If the attribute name has been changed in the table widget and update the database '''
        NAME_COLUMN = 0
        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == NAME_COLUMN:
            newText = str(self.ui.tableWidget.item(x, y).text()).strip()
            # check that no other attribute has this text and this is is not empty
            update = True
            if newText == "":
                update = False
            for att in self.attribute_type:
                if att['name'] == newText:
                    update = False
            if update:
                # update attribute type list and database
                cur = self.app.conn.cursor()
                cur.execute("update attribute_type set name=? where name=?", (newText, self.attribute_type[x]['name']))
                cur.execute("update attribute set name=? where name=?", (newText, self.attribute_type[x]['name']))
                self.app.conn.commit()
                self.attribute_type[x]['name'] = newText
            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.attribute_type[x]['name'])

    def fill_tableWidget(self):
        ''' Fill the table widget with attribute details '''

        rows = self.ui.tableWidget.rowCount()
        for i in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        self.ui.tableWidget.setColumnCount(4)
        self.ui.tableWidget.setHorizontalHeaderLabels([_("name"), _("caseOrFile"), _("valuetype"), _("memo")])
        for row, a in enumerate(self.attribute_type):
            self.ui.tableWidget.insertRow(row)
            item = QtWidgets.QTableWidgetItem(a['name'])
            item.setToolTip(a['date'] + "\n" + a['owner'])
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['caseOrFile'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.CASE_FILE_COLUMN, item)
            mText = ""
            mtmp = a['memo']
            if mtmp is not None and mtmp != "":
                mText = _("Yes")
            item = QtWidgets.QTableWidgetItem(mText)
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.MEMO_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['valuetype'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.VALUETYPE_COLUMN, item)
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogManageAttributes()
    ui.show()
    sys.exit(app.exec_())

