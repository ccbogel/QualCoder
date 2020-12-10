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

import datetime
import os
import sys
import logging
import traceback

from PyQt5 import QtCore, QtGui, QtWidgets

from add_attribute import DialogAddAttribute
from confirm_delete import DialogConfirmDelete
from memo import DialogMemo
from GUI.ui_dialog_manage_attributes import Ui_Dialog_manage_attributes
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
    """ Attribute management. Create and delete attributes in the attributes table.
    """

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
        self.attributes = []
        cur = self.app.conn.cursor()
        cur.execute("select name, date, owner, memo, caseOrFile, valuetype from attribute_type")
        result = cur.fetchall()
        for row in result:
            self.attributes.append({'name': row[0], 'date': row[1], 'owner': row[2],
            'memo': row[3], 'caseOrFile': row[4],'valuetype': row[5]})

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_attributes()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogmanageattributes_w'])
            h = int(self.app.settings['dialogmanageattributes_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.fill_tableWidget()
        self.ui.pushButton_add.setStyleSheet("background-image : url(GUI/plus_icon.png);")
        self.ui.pushButton_add.clicked.connect(self.add_attribute)
        self.ui.pushButton_delete.setStyleSheet("background-image : url(GUI/delete_icon.png);")
        self.ui.pushButton_delete.clicked.connect(self.delete_attribute)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.tableWidget.cellChanged.connect(self.cell_modified)
        self.ui.tableWidget.itemSelectionChanged.connect(self.count_selected_items)

    def resizeEvent(self, new_size):
        """ Update the widget size details in the app.settings variables """

        self.app.settings['dialogmanageattributes_w'] = new_size.size().width()
        self.app.settings['dialogmanageattributes_h'] = new_size.size().height()

    def count_selected_items(self):
        """ Update label with the count of selected items """
        indexes = self.ui.tableWidget.selectedIndexes()
        ix = []
        for i in indexes:
            ix.append(i.row())
        i = set(ix)
        self.ui.label.setText(_("Attributes: ") + str(len(i)) + "/" + str(len(self.attributes)))

    def add_attribute(self):
        """ When add button pressed, open addItem dialog to get new attribute text.
        AddItem dialog checks for duplicate attribute name.
        New attribute is added to the model and database """

        check_names = self.attributes + [{'name': 'name'}, {'name':'memo'}, {'name':'id'}, {'name':'date'}]
        ui = DialogAddAttribute(self.app, check_names)
        ui.exec_()  # ok = ui.exec_() does not pick up pressing the cancel button
        name = ui.new_name
        value_type = ui.value_type
        if name == "":
            return
        Dialog_assign = QtWidgets.QDialog()
        ui = Ui_Dialog_assignAttribute()
        ui.setupUi(Dialog_assign)
        Dialog_assign.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        Dialog_assign.setStyleSheet(font)
        Dialog_assign.exec_()
        case_or_file = "case"
        if ui.radioButton_files.isChecked():
            case_or_file = "file"
        # update attributes list and database
        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        item = {'name': name, 'memo': "", 'owner': self.app.settings['codername'],
            'date': now_date, 'valuetype': value_type,
            'caseOrFile': case_or_file}
        self.attributes.append(item)
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
        self.parent_textEdit.append(_("Attribute added: ") + item['name'] + _(" to ") + _(case_or_file))

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
        ok = ui.exec_()
        if not ok:
            return
        for name in names_to_delete:
            for attr in self.attributes:
                if attr['name'] == name:
                    self.parent_textEdit.append(_("Attribute deleted: ") + attr['name'])
                    cur = self.app.conn.cursor()
                    cur.execute("delete from attribute where name = ?", (name,))
                    cur.execute("delete from attribute_type where name = ?", (name,))
        self.app.conn.commit()
        self.attributes = []
        cur.execute("select name, date, owner, memo, caseOrFile, valuetype from attribute_type")
        result = cur.fetchall()
        for row in result:
            self.attributes.append({'name': row[0], 'date': row[1], 'owner': row[2],
            'memo': row[3], 'caseOrFile': row[4],'valuetype': row[5]})
        self.fill_tableWidget()
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
            ui.exec_()
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

    def cell_modified(self):
        """ If the attribute name has been changed in the table widget and update the database. """

        NAME_COLUMN = 0
        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == NAME_COLUMN:
            new_name = str(self.ui.tableWidget.item(x, y).text()).strip()
            # check that no other attribute has this text and this is is not empty
            update = True
            if new_name == "":
                update = False
            for att in self.attributes:
                if att['name'] == new_name:
                    update = False
            if update:
                # update attribute type list and database
                cur = self.app.conn.cursor()
                cur.execute("update attribute_type set name=? where name=?", (new_name, self.attributes[x]['name']))
                cur.execute("update attribute set name=? where name=?", (new_name, self.attributes[x]['name']))
                self.app.conn.commit()
                self.parent_textEdit.append(_("Attribute renamed from: ") + self.attributes[x]['name'] + _(" to ") + new_name)
                self.attributes[x]['name'] = new_name

            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.attributes[x]['name'])

    def fill_tableWidget(self):
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

