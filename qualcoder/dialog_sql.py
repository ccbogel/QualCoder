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

#from Dialog_QueryDetails import Dialog_QueryDetails
from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from highlighter import Highlighter
import sqlite3
import os
import sys
from datetime import datetime
from GUI.ui_dialog_SQL import Ui_Dialog_sql
import logging
import traceback

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


class DialogSQL(QtWidgets.QDialog):
    ''' Uses single inheritance, sub-class QDialog and set up the user interface in
    the __init__() method.
    A gui to allow the user to enter sql queries and return results.
    Data outputs are as tab (or other) separated files. '''

    settings = None
    parent_textEdit = None
    sql = ""
    joinData = []
    delimiter = "\t"  # default delimiter for file exports
    file_data = []  # for file exports
    results = None  # SQL results
    queryTime = ""  # for label tooltip
    queryFilters = ""  # for label tooltip

    def __init__(self, settings, parent_textEdit):

        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.queryTime = ""
        self.queryFilters = ""
        textEditSql = ""

        # Set up the user interface from Designer.
        self.ui = Ui_Dialog_sql()
        self.ui.setupUi(self)
        #self.setWindowTitle("Query: " + self.queryname)
        self.ui.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        highlighter = Highlighter(self.ui.textEdit_sql)
        self.ui.textEdit_sql.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textEdit_sql.customContextMenuRequested.connect(self.sql_menu)
        # fill textEdit_sql from queryname
        self.ui.textEdit_sql.setText(textEditSql)
        self.ui.tableWidget_results.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.tableWidget_results.customContextMenuRequested.connect(self.table_menu)

        # Add tables and fields to treeWidget
        self.get_schema_update_treeWidget()
        self.ui.treeWidget.itemClicked.connect(self.get_item)
        self.ui.pushButton_runSQL.clicked.connect(self.run_SQL)
        self.ui.pushButton_export.clicked.connect(self.export_file)
        self.ui.splitter.setSizes([20, 180])
        self.ui.splitter_2.setSizes([10, 290])

    def export_file(self):
        ''' Load resultset.
        Export results to a delimited .csv file using \r\n as line separators. '''

        cur = self.settings['conn'].cursor()
        sql = self.ui.textEdit_sql.toPlainText()
        try:
            cur.execute(sql)
        except Exception as e:
            QtWidgets.QMessageBox.error(None, 'SQL error', str(e))
            return

        results = cur.fetchall()
        col_names = []
        if cur.description is not None:
            col_names = list(map(lambda x: x[0], cur.description))  # gets column names
        # os.getenv('HOME') does not work on Windows
        tmp_name = os.path.expanduser('~') + "/Desktop/TEMP.csv"
        file_tuple = QtWidgets.QFileDialog.getSaveFileName(None, "Save text file", tmp_name)
        if file_tuple[0] == "":
            return
        file_name = file_tuple[0]
        self.delimiter = str(self.ui.comboBox_delimiter.currentText())
        if self.delimiter == "tab":
            self.delimiter = "\t"
        f = open(file_name, 'w')
        # write the header row
        file_line = ""
        for item in col_names:
            file_line += item + self.delimiter
        file_line = file_line[:len(file_line) - 1]
        f.write(file_line + "\r\n")
        # write the data rows
        for r, row in enumerate(results):
            file_line = ""
            for item in row:
                if item is None:
                    file_line += self.delimiter
                else:
                    file_line += str(item) + self.delimiter
            file_line = file_line[:len(file_line) - 1]
            f.write(file_line + "\r\n")
        f.close()
        self.parent_textEdit.append(_("SQL Results exported to: ") + file_name)
        self.parent_textEdit.append(_("Query:") + "\n" + sql)
        QtWidgets.QMessageBox.information(None, _("Text file export"), file_name)

    def get_item(self):
        ''' Get the selected table name or tablename.fieldname and add to the sql text
        at the current cursor position. '''

        item_text = self.ui.treeWidget.currentItem().text(0)
        index = self.ui.treeWidget.currentIndex()
        #logger.debug("item index:" + index.row(), index.parent().row())
        if index.parent().row() != -1:  # there is a parent if not -1
            item_parent = self.ui.treeWidget.itemFromIndex(index.parent())
            item_parent_text = item_parent.text(0)
            if item_parent_text != "-- Joins --":
                item_text = item_parent_text + "." + item_text
        cursor = self.ui.textEdit_sql.textCursor()
        #logger.debug("Cursor position:" + cursor.position())
        cursor.insertText(" " + item_text + " ")

    def run_SQL(self):
        ''' Run the sql text and add the results to the results text edit. '''

        # clear tableWidget and file data
        numRows = self.ui.tableWidget_results.rowCount()
        for row in range(0, numRows):
            self.ui.tableWidget_results.removeRow(0)
        self.ui.tableWidget_results.setHorizontalHeaderLabels([""])
        self.file_data = []
        self.ui.label.setText(_("Running query. Please wait."))
        QtWidgets.QApplication.processEvents()  # stops gui freeze
        self.sql = self.ui.textEdit_sql.toPlainText()
        cur = self.settings['conn'].cursor()
        self.sql = str(self.sql)
        QtWidgets.QApplication.processEvents()  # stops gui freeze
        try:
            time0 = datetime.now()
            cur.execute(self.sql)
            self.ui.label.setToolTip("")
            self.results = cur.fetchall()
            time1 = datetime.now()
            timediff = time1 - time0
            self.queryTime = "Time:" + str(timediff)
            self.ui.label.setToolTip(self.queryTime)
            self.ui.label.setText(str(len(self.results)) + _(" rows"))
            #extra messaging where rows will be zero
            if self.sql[0:12].upper() == "CREATE TABLE":
                self.ui.label.setText(_("Table created"))
            if self.sql[0:12].upper() == "CREATE INDEX":
                self.ui.label.setText(_("Index created"))
                self.settings['conn'].commit()
            if self.sql[0:6].upper() == "DELETE":
                self.ui.label.setText(str(cur.rowcount) + _(" rows deleted"))
                self.settings['conn'].commit()
            if self.sql[0:6].upper() == "UPDATE":
                self.ui.label.setText(str(cur.rowcount) + _(" rows updated"))
                self.settings['conn'].commit()
            colNames = []
            if cur.description is not None:
                colNames = list(map(lambda x: x[0], cur.description))  # gets column names
            self.ui.tableWidget_results.setColumnCount(len(colNames))
            self.ui.tableWidget_results.setHorizontalHeaderLabels(colNames)
            self.file_data.append(colNames)
            for row, row_results in enumerate(self.results):
                self.file_data.append(row_results)
                self.ui.tableWidget_results.insertRow(row)
                for col, value in enumerate(row_results):
                    if value is None:
                        value = ""
                    cell = QtWidgets.QTableWidgetItem(str(value))
                    cell.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                    self.ui.tableWidget_results.setItem(row, col, cell)
            self.ui.tableWidget_results.resizeColumnsToContents()
            self.ui.tableWidget_results.resizeRowsToContents()
            sqlString = str(self.sql).upper()
            if sqlString.find("CREATE ") == 0 or sqlString.find("DROP ") == 0 or sqlString.find("ALTER ") == 0:
                self.getSchemaUpdateTreeWidget()
        except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
            QtWidgets.QMessageBox.critical(None, _('Error'), str(e), QtWidgets.QMessageBox.Ok)
            self.ui.label.setText(_("SQL Error"))
            self.ui.label.setToolTip(str(e))
        self.results = None
        self.settings['conn'].commit()

    def get_schema_update_treeWidget(self):
        ''' Get table schema from database, and update the tables_an_views tree widget.
        The schema needs to be updated when drop table or create queries are run. '''

        # get schema
        self.settings["schema"] = []
        tableDict = {}
        cur = self.settings["conn"]
        result = cur.execute("SELECT sql, type, name FROM sqlite_master WHERE type IN ('table', 'view') ")
        for row in result:
            tableName = row[2]
            fields = []
            fieldResults = cur.execute("PRAGMA table_info(" + tableName + ")")
            # each field is a tuple of cid, name, type (integer, text, ), notNull (1=notNull),
            # defaultValue(None usually), primaryKey(as integers 1 up, or 0)
            for field in fieldResults:
                fields.append(field)
            tableDict[tableName] = fields
        self.settings["schema"] = tableDict

        # update tables and views in tree widget
        tablesAndViews = []
        for k in self.settings["schema"].keys():
            tablesAndViews.append(k)
        tablesAndViews.sort()
        self.ui.treeWidget.clear()
        for tableName in tablesAndViews:
            topItem = QtWidgets.QTreeWidgetItem()
            topItem.setText(0, tableName)
            result = cur.execute("SELECT type FROM sqlite_master WHERE name='" + tableName + "' ")
            tableOrView = result.fetchone()[0]
            if tableOrView == "view":
                topItem.setBackground(0, QtGui.QBrush(Qt.yellow, Qt.Dense6Pattern))
            self.ui.treeWidget.addTopLevelItem(topItem)
            for field in self.settings["schema"][tableName]:
                fieldItem = QtWidgets.QTreeWidgetItem()
                if tableOrView == "view":
                    fieldItem.setBackground(0, QtGui.QBrush(Qt.yellow, Qt.Dense6Pattern))
                if field[5] > 0:
                    fieldItem.setForeground(0, QtGui.QBrush(Qt.red))
                fieldItem.setText(0, field[1])
                topItem.addChild(fieldItem)

        # add join syntax
        joinItem = QtWidgets.QTreeWidgetItem()
        joinItem.setText(0, "-- Joins --")
        self.ui.treeWidget.addTopLevelItem(joinItem)
        for join in self.joinData:
            jItem = QtWidgets.QTreeWidgetItem()
            jItem.setText(0, join)
            joinItem.addChild(jItem)

    # sql text edit widget context menu
    def sql_menu(self, position):
        ''' add context menu to textedit_sql
         includes:cut ctrlX copy ctrlC paste ctrlV delete select_all ctrlA  '''
        menu = QtWidgets.QMenu()
        action_SelectAll = menu.addAction(_("Select all"))
        action_copy = menu.addAction(_("Copy"))
        action_paste = menu.addAction(_("Paste"))
        action_delete = menu.addAction(_("Delete"))
        action_SQL_SelectAllFrom = menu.addAction("SELECT * FROM ")
        action = menu.exec_(self.ui.textEdit_sql.mapToGlobal(position))
        cursor = self.ui.textEdit_sql.textCursor()

        if action == action_delete:
            text = cursor.selectedText()
            text = str(text)
            clipboard = QtGui.QApplication.clipboard()
            clipboard.setText(text)
            start = cursor.position()
            end = cursor.anchor()
            if start > end:
                tmp = end
                end = start
                start = tmp
            beginText = self.ui.textEdit_sql.toPlainText()[0:start]
            endText = self.ui.textEdit_sql.toPlainText()[end:len(self.ui.textEdit_sql.toPlainText())]
            self.ui.textEdit_sql.setText(beginText + endText)

        if action == action_paste:
            clipboard = QtWidgets.QApplication.clipboard()
            text = clipboard.text()
            cursor.insertText(text)

        if action == action_copy:
            text = cursor.selectedText()
            text = str(text)
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(text)

        if action == action_SelectAll:
            clipboard = QtWidgets.QApplication.clipboard()
            cursor.setPosition(0)
            cursor.setPosition(len(self.ui.textEdit_sql.toPlainText()),
                QtGui.QTextCursor.KeepAnchor)
            self.ui.textEdit_sql.setTextCursor(cursor)

        if action == action_SQL_SelectAllFrom:
            cursor.insertText("SELECT * FROM ")

    # start table results context menu section
    def table_menu(self, position):
        ''' Context menu for table_results '''

        menu = QtWidgets.QMenu()
        try:
            self.row = self.ui.tableWidget_results.currentRow()
            self.col = self.ui.tableWidget_results.currentColumn()
            #print(self.row, self.col)
            self.cellValue = str(self.ui.tableWidget_results.item(self.row, self.col).text())
        except AttributeError as e:
            logger.warning("No table for table menu: " + str(e))
            return

        ActionShowAllRows = menu.addAction(_("Clear filter"))
        ActionShowAllRows.triggered.connect(self.show_all_rows)
        ActionFilterOnCellValue = menu.addAction(_("Filter equals: ") + str(self.cellValue))
        ActionFilterOnCellValue.triggered.connect(self.filter_cell_value)
        ActionFilterOnTextLike = menu.addAction(_("Filter on text like"))
        ActionFilterOnTextLike.triggered.connect(self.filter_text_like)
        ActionFilterOnTextStartsWith = menu.addAction(_("Filter on text starts with"))
        ActionFilterOnTextStartsWith.triggered.connect(self.filter_text_starts_with)
        ActionSortAscending = menu.addAction(_("Sort ascending"))
        ActionSortAscending.triggered.connect(self.sort_ascending)
        ActionSortDescending = menu.addAction(_("Sort descending"))
        ActionSortDescending.triggered.connect(self.sort_descending)
        action = menu.exec_(self.ui.tableWidget_results.mapToGlobal(position))

    #TODO need to add numerical filters
    #TODO need to store or determine type of data to do this

    def sort_ascending(self):
        ''' Sort rows on selected column in ascending order '''

        self.ui.tableWidget_results.sortItems(self.col, QtCore.Qt.AscendingOrder)
        self.ui.label.setText(str(len(self.file_data)-1) + _(" rows [") + self.file_data[0][self.col] + _(" asc]"))

    def sort_descending(self):
        ''' Sort rows on selected column in descending order '''

        self.ui.tableWidget_results.sortItems(self.col, QtCore.Qt.DescendingOrder)
        self.ui.label.setText(str(len(self.file_data)-1) + _(" rows [") + self.file_data[0][self.col] + _(" desc]"))

    def filter_text_like(self):
        ''' Hide rows where cells in the column do not contain the text fragment '''

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cellValue))
        if ok and text != '':
            for r in range(0, self.ui.tableWidget_results.rowCount()):
                if self.ui.tableWidget_results.item(r, self.col).text().find(text) == -1:
                    self.ui.tableWidget_results.setRowHidden(r, True)
        self.ui.label.setText(str(len(self.file_data) - 1) + _(" rows [filtered]"))
        self.queryFilters += "\n" + self.ui.tableWidget_results.horizontalHeaderItem(self.col).text() + " like: " + text
        self.ui.label.setToolTip(self.queryTime + self.queryFilters)

    def filter_text_starts_with(self):
        ''' Hide rows where cells in the column do not contain the text start fragment. '''

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cellValue))
        if ok and text != '':
            for r in range(0, self.ui.tableWidget_results.rowCount()):
                if self.ui.tableWidget_results.item(r, self.col).text().startswith(text) is False:
                    self.ui.tableWidget_results.setRowHidden(r, True)
        self.ui.label.setText(str(len(self.file_data) - 1) + _(" rows [filtered]"))
        self.ui.label.setToolTip(self.queryTime)
        self.queryFilters += "\n" + self.ui.tableWidget_results.horizontalHeaderItem(self.col).text() + _(" starts with: ") + text
        self.ui.label.setToolTip(self.queryTime + self.queryFilters)

    def filter_cell_value(self):
        ''' Hide rows that do not have the selected cell value '''

        for r in range(0, self.ui.tableWidget_results.rowCount()):
            if self.ui.tableWidget_results.item(r, self.col).text() != self.cellValue:
                self.ui.tableWidget_results.setRowHidden(r, True)
        self.ui.label.setText(str(len(self.file_data) - 1) + _(" rows [filtered]"))
        self.queryFilters += "\n" + str(self.ui.tableWidget_results.horizontalHeaderItem(self.col).text()) + _(" equals: ") + str(self.cellValue)
        self.ui.label.setToolTip(self.queryTime + self.queryFilters)

    def show_all_rows(self):
        ''' Remove all hidden rows '''

        for r in range(0, self.ui.tableWidget_results.rowCount()):
                self.ui.tableWidget_results.setRowHidden(r, False)
        self.ui.label.setText(str(len(self.file_data) - 1) + _(" rows"))
        self.queryFilters = ""
        self.ui.label.setToolTip(self.queryTime + self.queryFilters)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_sql = QtWidgets.QDialog()
    ui = Ui_Dialog_sql()
    ui.setupUi(Dialog_sql)
    Dialog_sql.show()
    sys.exit(app.exec_())


class NewTableWidget(QtWidgets.QTableWidget):
    ''' This extends the table widget by adding a context menu and associated actions. '''

    row = None
    col = None
    cellValue = None

    def __init__(self, parent=None):
        super(NewTableWidget, self).__init__(parent)


    def contextMenuEvent(self, event):

        menu = QtWidgets.QMenu(self)
        try:
            self.row = self.currentRow()
            self.col = self.currentColumn()
            self.cellValue = str(self.item(self.row, self.col).text())
        except AttributeError as e:
            logger.warning("No table for menu: " + str(e))
            return

        ActionShowAllRows = menu.addAction(_("Clear filter"))
        ActionShowAllRows.triggered.connect(self.show_all_rows)
        ActionFilterOnCellValue = menu.addAction(_("Filter equals: ") + str(self.cellValue))
        ActionFilterOnCellValue.triggered.connect(self.filter_cell_value)
        ActionFilterOnTextLike = menu.addAction(_("Filter on text like"))
        ActionFilterOnTextLike.triggered.connect(self.filter_text_like)
        ActionFilterOnTextStartsWith = menu.addAction(_("Filter on text starts with"))
        ActionFilterOnTextStartsWith.triggered.connect(self.filter_text_starts_with)
        ActionSortAscending = menu.addAction(_("Sort ascending"))
        ActionSortAscending.triggered.connect(self.sort_ascending)
        ActionSortDescending = menu.addAction(_("Sort descending"))
        ActionSortDescending.triggered.connect(self.sort_descending)
        menu.exec_(event.globalPos())

    def sort_ascending(self):
        ''' Sort rows on selected column in ascending order. '''

        self.sortItems(self.col, QtCore.Qt.AscendingOrder)

    def sort_descending(self):
        ''' Sort rows on selected column in descending order. '''

        self.sortItems(self.col, QtCore.Qt.DescendingOrder)

    def filter_text_like(self):
        ''' Hide rows where cells in the column do not contain the text fragment. '''

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cellValue))
        if ok and text != '':
            #logger.debug(text)
            for r in range(0, self.rowCount()):
                if str(self.item(r, self.col).text()).find(text) == -1:
                    self.setRowHidden(r, True)

    def filter_text_starts_with(self):
        ''' Hide rows where cells in the column do not contain the text start fragment. '''

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cellValue))
        if ok and text != '':
            #logger.debug(text)
            for r in range(0, self.rowCount()):
                if str(self.item(r, self.col).text()).startswith(text) is False:
                    self.setRowHidden(r, True)

    def filter_cell_value(self):
        ''' Hide rows that do not have the selected cell value. '''

        for r in range(0, self.rowCount()):
            if str(self.item(r, self.col).text()) != self.cellValue:
                self.setRowHidden(r, True)

    def show_all_rows(self):
        ''' Remove all hidden rows. '''

        for r in range(0, self.rowCount()):
                self.setRowHidden(r, False)


class TableWidgetItem(QtWidgets.QTableWidgetItem):
    ''' A sorting method that works. From:
        http://www.tagwith.com/question_868979_sort-string-column-in-pyqtqtablewidget-based-on-non-string-value
        With some modification for unicode and numerics '''

    def __init__(self, value):
        super(TableWidgetItem, self).__init__(value)

    def __lt__(self, other):
        ''' not sure about the if statement ?'''

        if (isinstance(other, TableWidgetItem)):
            try:
                selfValue = float(str(self.data(QtCore.Qt.EditRole)))
                otherValue = float(str(other.data(QtCore.Qt.EditRole)))
                return selfValue < otherValue
            except:
                selfValue = str(self.data(QtCore.Qt.EditRole))
                otherValue = str(other.data(QtCore.Qt.EditRole))
                return selfValue < otherValue
        else:
            return QtWidgets.QTableWidgetItem.__lt__(self, other)
