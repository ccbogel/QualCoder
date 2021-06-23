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
"""

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
import sqlite3
import os
import sys
from datetime import datetime
import logging
import traceback

from .GUI.base64_helper import *
from .GUI.ui_dialog_SQL import Ui_Dialog_sql
from .helpers import ExportDirectoryPathDialog, Message
from .highlighter import Highlighter

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
    """ Uses single inheritance, sub-class QDialog and set up the user interface in
    the __init__() method.
    A gui to allow the user to enter sql queries and return results.
    Data outputs are as tab (or other) separated files.
    EXTRA_SQL is listed at end of module for additional complex queries. """

    app = None
    schema = None
    parent_textEdit = None
    sql = ""
    delimiter = "\t"  # default delimiter for file exports
    file_data = []  # for file exports
    results = None  # SQL results
    queryTime = ""  # for label tooltip
    queryFilters = ""  # for label tooltip
    cell_value = ""

    def __init__(self, app, parent_textEdit):

        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.queryTime = ""
        self.queryFilters = ""
        textEditSql = ""

        # Set up the user interface from Designer.
        self.ui = Ui_Dialog_sql()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        highlighter = Highlighter(self.ui.textEdit_sql)
        if self.app.settings['stylesheet'] == "dark":
            highlighter.create_rules(dark=True)
        self.ui.textEdit_sql.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textEdit_sql.customContextMenuRequested.connect(self.sql_menu)
        # Fill textEdit_sql from queryname
        self.ui.textEdit_sql.setText(textEditSql)
        self.ui.tableWidget_results.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.tableWidget_results.customContextMenuRequested.connect(self.table_menu)

        # Add tables and fields to treeWidget
        self.get_schema_update_treeWidget()
        self.ui.treeWidget.itemClicked.connect(self.get_item)
        self.ui.pushButton_runSQL.clicked.connect(self.run_SQL)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/cogs_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_runSQL.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export.clicked.connect(self.export_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_csv_icon), "png")
        self.ui.pushButton_export.setIcon(QtGui.QIcon(pm))
        self.ui.splitter.setSizes([20, 180])
        try:
            s0 = int(self.app.settings['dialogsql_splitter_h0'])
            s1 = int(self.app.settings['dialogsql_splitter_h1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except:
            pass
        self.ui.splitter_2.setSizes([10, 290])
        try:
            s0 = int(self.app.settings['dialogsql_splitter_v0'])
            s1 = int(self.app.settings['dialogsql_splitter_v1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter_2.setSizes([s0, s1])
        except:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.splitter_2.splitterMoved.connect(self.update_sizes)

    def update_sizes(self):
        """ Called by splitter resized """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogsql_splitter_h0'] = sizes[0]
        self.app.settings['dialogsql_splitter_h1'] = sizes[1]
        sizes = self.ui.splitter_2.sizes()
        self.app.settings['dialogsql_splitter_v0'] = sizes[0]
        self.app.settings['dialogsql_splitter_v1'] = sizes[1]

    def export_file(self):
        """ Load result set and export results to a delimited .csv file
        using \r\n as line separators. """

        cur = self.app.conn.cursor()
        sql = self.ui.textEdit_sql.toPlainText()
        try:
            cur.execute(sql)
        except Exception as e:
            Message(self.app, _("SQL error"), str(e), "warning").exec_()
            return
        results = cur.fetchall()
        col_names = []
        if cur.description is not None:
            col_names = list(map(lambda x: x[0], cur.description))  # gets column names
        filename = "sql_report.csv"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        self.delimiter = str(self.ui.comboBox_delimiter.currentText())
        if self.delimiter == "tab":
            self.delimiter = "\t"
        ''' https://stackoverflow.com/questions/39422573/python-writing-weird-unicode-to-csv
        Using a byte order mark so that other software recognised UTF-8 '''
        f = open(filepath, 'w', encoding='utf-8-sig')
        # Write the header row
        file_line = ""
        for item in col_names:
            file_line += item + self.delimiter
        file_line = file_line[:len(file_line) - 1]
        f.write(file_line + "\r\n")
        # Write data rows
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
        msg = _("SQL Results exported to: ") + filepath
        self.parent_textEdit.append(msg)
        self.parent_textEdit.append(_("Query:") + "\n" + sql)
        Message(self.app, _("CSV file export"), msg, "information").exec_()

    def get_item(self):
        """ Get the selected table name or tablename.fieldname and add to the sql text
        at the current cursor position.
        Also get a prepared query and replace sql text in the text edit. """

        item_text = self.ui.treeWidget.currentItem().text(0)
        index = self.ui.treeWidget.currentIndex()
        if index.parent().row() != -1:  # there is a parent if not -1
            item_parent = self.ui.treeWidget.itemFromIndex(index.parent())
            item_parent_text = item_parent.text(0)
            if item_parent_text != "-- Query --":
                item_text = item_parent_text + "." + item_text
            if item_parent_text == "-- Query --":
                self.ui.textEdit_sql.clear()
        cursor = self.ui.textEdit_sql.textCursor()
        cursor.insertText(" " + item_text + " ")

    def run_SQL(self):
        """ Run the sql text and add the results to the results text edit. """

        # Clear tableWidget and file data
        num_rows = self.ui.tableWidget_results.rowCount()
        for row in range(0, num_rows):
            self.ui.tableWidget_results.removeRow(0)
        self.ui.tableWidget_results.setHorizontalHeaderLabels([""])
        self.file_data = []
        self.ui.label.setText(_("Running query. Please wait."))
        QtWidgets.QApplication.processEvents()  # stops gui freeze
        self.sql = self.ui.textEdit_sql.toPlainText()
        cur = self.app.conn.cursor()
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
            # Extra messaging where rows will be zero
            if self.sql[0:12].upper() == "CREATE TABLE":
                self.ui.label.setText(_("Table created"))
                self.app.delete_backup = False
            if self.sql[0:12].upper() == "CREATE INDEX":
                self.ui.label.setText(_("Index created"))
                self.app.delete_backup = False
                self.app.conn.commit()
            if self.sql[0:6].upper() == "DELETE":
                self.ui.label.setText(str(cur.rowcount) + _(" rows deleted"))
                self.app.delete_backup = False
                self.app.conn.commit()
            if self.sql[0:6].upper() == "UPDATE":
                self.ui.label.setText(str(cur.rowcount) + _(" rows updated"))
                self.app.delete_backup = False
                self.app.conn.commit()
            col_names = []
            if cur.description is not None:
                col_names = list(map(lambda x: x[0], cur.description))  # gets column names
            self.ui.tableWidget_results.setColumnCount(len(col_names))
            self.ui.tableWidget_results.setHorizontalHeaderLabels(col_names)
            self.file_data.append(col_names)
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
            sql_string = str(self.sql).upper()
            if sql_string.find("CREATE ") == 0 or sql_string.find("DROP ") == 0 or sql_string.find("ALTER ") == 0:
                self.get_schema_update_treeWidget()
        except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
            Message(self.app, _("Error"), str(e), "warning").exec_()
            self.ui.label.setText(_("SQL Error"))
            self.ui.label.setToolTip(str(e))
        self.results = None
        self.app.conn.commit()

    def get_schema_update_treeWidget(self):
        """ Get table schema from database, and update the tables_an_views tree widget.
        The schema needs to be updated when drop table or create queries are run. """

        self.schema = []
        table_dict = {}
        cur = self.app.conn.cursor()
        cur.execute("SELECT sql, type, name FROM sqlite_master WHERE type IN ('table', 'view') ")
        result = cur.fetchall()
        for row in result:
            table_name = row[2]
            fields = []
            field_results = cur.execute("PRAGMA table_info(" + table_name + ")")
            # each field is a tuple of cid, name, type (integer, text, ), notNull (1=notNull),
            # defaultValue(None usually), primaryKey(as integers 1 up, or 0)
            for field in field_results:
                fields.append(field)
            table_dict[table_name] = fields
        self.schema = table_dict

        # Fill tree widget with tables and views
        tables_and_views = []
        for k in self.schema.keys():
            tables_and_views.append(k)
        tables_and_views.sort()
        self.ui.treeWidget.clear()
        for table_name in tables_and_views:
            top_item = QtWidgets.QTreeWidgetItem()
            top_item.setText(0, table_name)
            result = cur.execute("SELECT type FROM sqlite_master WHERE name='" + table_name + "' ")
            table_or_view = result.fetchone()[0]
            if table_or_view == "view":
                top_item.setBackground(0, QtGui.QBrush(Qt.yellow, Qt.Dense6Pattern))
            self.ui.treeWidget.addTopLevelItem(top_item)
            for field in self.schema[table_name]:
                field_item = QtWidgets.QTreeWidgetItem()
                if table_or_view == "view":
                    field_item.setBackground(0, QtGui.QBrush(Qt.yellow, Qt.Dense6Pattern))
                if field[5] > 0:
                    field_item.setForeground(0, QtGui.QBrush(Qt.red))
                field_item.setText(0, field[1])
                top_item.addChild(field_item)

        # Add prepared query sqls
        query_item = QtWidgets.QTreeWidgetItem()
        query_item.setText(0, "-- Query --")
        self.ui.treeWidget.addTopLevelItem(query_item)
        for query in EXTRA_SQL:
            item = QtWidgets.QTreeWidgetItem()
            item.setText(0, query)
            query_item.addChild(item)

    def sql_menu(self, position):
        """ Context menu to textedit_sql
         Cut Ctrl + X, Copy Ctrl + C, Paste Ctrl + V, Delete, Ctrl + A selectall. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_select_all = menu.addAction(_("Select all"))
        action_copy = menu.addAction(_("Copy"))
        action_paste = menu.addAction(_("Paste"))
        action_delete = menu.addAction(_("Delete"))
        action_select_all_from = menu.addAction("SELECT * FROM ")
        action = menu.exec_(self.ui.textEdit_sql.mapToGlobal(position))
        cursor = self.ui.textEdit_sql.textCursor()

        if action == action_delete:
            text = cursor.selectedText()
            if text is None or text == "":
                return
            start = cursor.position()
            end = cursor.anchor()
            if start > end:
                tmp = end
                end = start
                start = tmp
            start_text = self.ui.textEdit_sql.toPlainText()[0:start]
            end_text = self.ui.textEdit_sql.toPlainText()[end:len(self.ui.textEdit_sql.toPlainText())]
            self.ui.textEdit_sql.setText(start_text + end_text)
        if action == action_paste:
            clipboard = QtWidgets.QApplication.clipboard()
            text = clipboard.text()
            cursor.insertText(text)
        if action == action_copy:
            text = cursor.selectedText()
            text = str(text)
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(text)
        if action == action_select_all:
            clipboard = QtWidgets.QApplication.clipboard()
            cursor.setPosition(0)
            cursor.setPosition(len(self.ui.textEdit_sql.toPlainText()),
                QtGui.QTextCursor.KeepAnchor)
            self.ui.textEdit_sql.setTextCursor(cursor)
        if action == action_select_all_from:
            cursor.insertText("SELECT * FROM ")

    # Start of table results context menu section
    def table_menu(self, position):
        """ Context menu for table_results. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        try:
            self.row = self.ui.tableWidget_results.currentRow()
            self.col = self.ui.tableWidget_results.currentColumn()
            self.cell_value = str(self.ui.tableWidget_results.item(self.row, self.col).text())
        except AttributeError as e:
            logger.warning("No table for table menu: " + str(e))
            return

        ActionShowAllRows = menu.addAction(_("Clear filter"))
        ActionShowAllRows.triggered.connect(self.show_all_rows)
        ActionFilterOnCellValue = menu.addAction(_("Filter equals: ") + str(self.cell_value))
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
        """ Sort rows on selected column in ascending order. """

        self.ui.tableWidget_results.sortItems(self.col, QtCore.Qt.AscendingOrder)
        self.ui.label.setText(str(len(self.file_data)-1) + _(" rows [") + self.file_data[0][self.col] + _(" asc]"))

    def sort_descending(self):
        """ Sort rows on selected column in descending order. """

        self.ui.tableWidget_results.sortItems(self.col, QtCore.Qt.DescendingOrder)
        self.ui.label.setText(str(len(self.file_data)-1) + _(" rows [") + self.file_data[0][self.col] + _(" desc]"))

    def filter_text_like(self):
        """ Hide rows where cells in the column do not contain the text fragment. """

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cell_value))
        if ok and text != '':
            for r in range(0, self.ui.tableWidget_results.rowCount()):
                if self.ui.tableWidget_results.item(r, self.col).text().find(text) == -1:
                    self.ui.tableWidget_results.setRowHidden(r, True)
        self.ui.label.setText(str(len(self.file_data) - 1) + _(" rows [filtered]"))
        self.queryFilters += "\n" + self.ui.tableWidget_results.horizontalHeaderItem(self.col).text() + " like: " + text
        self.ui.label.setToolTip(self.queryTime + self.queryFilters)

    def filter_text_starts_with(self):
        """ Hide rows where cells in the column do not contain the text start fragment. """

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cell_value))
        if ok and text != '':
            for r in range(0, self.ui.tableWidget_results.rowCount()):
                if self.ui.tableWidget_results.item(r, self.col).text().startswith(text) is False:
                    self.ui.tableWidget_results.setRowHidden(r, True)
        self.ui.label.setText(str(len(self.file_data) - 1) + _(" rows [filtered]"))
        self.ui.label.setToolTip(self.queryTime)
        self.queryFilters += "\n" + self.ui.tableWidget_results.horizontalHeaderItem(self.col).text() + _(" starts with: ") + text
        self.ui.label.setToolTip(self.queryTime + self.queryFilters)

    def filter_cell_value(self):
        """ Hide rows that do not have the selected cell value. """

        for r in range(0, self.ui.tableWidget_results.rowCount()):
            if self.ui.tableWidget_results.item(r, self.col).text() != self.cell_value:
                self.ui.tableWidget_results.setRowHidden(r, True)
        self.ui.label.setText(str(len(self.file_data) - 1) + _(" rows [filtered]"))
        self.queryFilters += "\n" + str(self.ui.tableWidget_results.horizontalHeaderItem(self.col).text()) + _(" equals: ") + str(self.cell_value)
        self.ui.label.setToolTip(self.queryTime + self.queryFilters)

    def show_all_rows(self):
        """ Remove all hidden rows. """

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
    """ This extends the table widget by adding a context menu and associated actions. """

    row = None
    col = None
    cell_value = None

    def __init__(self, parent=None):
        super(NewTableWidget, self).__init__(parent)

    def contextMenuEvent(self, event):

        menu = QtWidgets.QMenu(self)
        try:
            self.row = self.currentRow()
            self.col = self.currentColumn()
            self.cell_value = str(self.item(self.row, self.col).text())
        except AttributeError as e:
            logger.warning("No table for menu: " + str(e))
            return

        ActionShowAllRows = menu.addAction(_("Clear filter"))
        ActionShowAllRows.triggered.connect(self.show_all_rows)
        ActionFilterOnCellValue = menu.addAction(_("Filter equals: ") + str(self.cell_value))
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
        """ Sort rows on selected column in ascending order. """

        self.sortItems(self.col, QtCore.Qt.AscendingOrder)

    def sort_descending(self):
        """ Sort rows on selected column in descending order. """

        self.sortItems(self.col, QtCore.Qt.DescendingOrder)

    def filter_text_like(self):
        """ Hide rows where cells in the column do not contain the text fragment. """

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cell_value))
        if ok and text != '':
            #logger.debug(text)
            for r in range(0, self.rowCount()):
                if str(self.item(r, self.col).text()).find(text) == -1:
                    self.setRowHidden(r, True)

    def filter_text_starts_with(self):
        """ Hide rows where cells in the column do not contain the text start fragment. """

        text, ok = QtWidgets.QInputDialog.getText(None, _("Text filter"), _("Text contains:"),
        QtWidgets.QLineEdit.Normal, str(self.cell_value))
        if ok and text != '':
            #logger.debug(text)
            for r in range(0, self.rowCount()):
                if str(self.item(r, self.col).text()).startswith(text) is False:
                    self.setRowHidden(r, True)

    def filter_cell_value(self):
        """ Hide rows that do not have the selected cell value. """

        for r in range(0, self.rowCount()):
            if str(self.item(r, self.col).text()) != self.cell_value:
                self.setRowHidden(r, True)

    def show_all_rows(self):
        """ Remove all hidden rows. """

        for r in range(0, self.rowCount()):
                self.setRowHidden(r, False)


class TableWidgetItem(QtWidgets.QTableWidgetItem):
    """ A sorting method that works. From:
        http://www.tagwith.com/question_868979_sort-string-column-in-pyqtqtablewidget-based-on-non-string-value
        With some modification for unicode and numerics """

    def __init__(self, value):
        super(TableWidgetItem, self).__init__(value)

    def __lt__(self, other):
        """ Not sure about the if isinstance statement. """

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

# Extra queries
EXTRA_SQL = ["-- CASE TEXT\nselect cases.name ,  substr(source.fulltext, case_text.pos0, case_text.pos1 -  case_text.pos0 ) as casetext \
from cases join case_text on  cases.caseid = case_text.caseid join source on source.id= case_text.fid \
where case_text.pos1 >0",
'-- CODES, FILEID, CODED TEXT\nselect  code_name.name as "codename",  \
code_text.fid, code_text.pos0, code_text.pos1,  code_text.seltext  from  code_name \
join  code_text on  code_name.cid = code_text.cid',
'-- GET_CODING_TABLE\n-- Implementation of RQDA function\n\
select code_text.cid, code_text.fid, code_name.name as "codename", \
source.name as "filename" , code_text.pos1 - code_text.pos0 as "CodingLength",\
code_text.pos0 as "index1", code_text.pos1 as "index2" \
from code_text join code_name on code_text.cid = code_name.cid \
join source on code_text.fid = source.id',
'-- CODED TEXT WITH EACH CASE\nselect code_name.name as codename, cases.name as casename,\
 code_text.pos0, code_text.pos1, code_text.fid, seltext as "coded text", code_text.owner \
 from code_text join code_name on code_name.cid = code_text.cid \
join (case_text join cases on cases.caseid = case_text.caseid) on code_text.fid = case_text.fid \
where \n\
-- code_name.cid in ( code_ids ) -- provide your code ids \n\
-- and case_text.caseid in ( case_ids ) -- provide your case ids \n\
-- and \n\
(code_text.pos0 >= case_text.pos0 and code_text.pos1 <= case_text.pos1)',
'-- ALL OR SELECTED ANNOTATIONS\nselect annotation.anid as "Annotation ID" , annotation.memo as "Annotation text", \n\
annotation.fid as "File ID" , source.name as "File name", annotation.pos0 as "Start position", \n\
annotation.pos1 as "End position", annotation.owner as "Coder name", annotation.date as "Date" from annotation \n\
left join source on source.id = annotation.fid \n\
-- DISPLAY ANNOTATIONS FOR SELECTED FILE, UNCOMMENT THE FOLLOWING: \n\
-- AND source.name = "FILE NAME"',
'-- ALL OR SELECTED CODINGS MEMOS\nselect code_text.memo as "Coding memo", code_text.cid as "Code ID", code_name.name as "Code name", \n\
code_text.fid as "File ID", source.name as "File name", code_text.owner as "Coder name", code_text.date as "Date", \n\
code_text.important as "Important(yes=1, no=0)" from source left join code_text on code_text.fid = source.id \n\
left join code_name on code_name.cid = code_text.cid where code_text.memo != "" \n\
-- TO DISPLAY CODING FOR SELECTED CODE OR FILE, UNCOMMENT THE FOLLOWING:\n\
-- AND code_name.name = "CODE NAME"  -- TO SELECT SPECIFIC CODE\n\
-- AND source.name = "FILE NAME" -- TO SELECT SPECIFIC FILE'
]
