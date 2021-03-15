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
https://qualcoder.wordpress.com/
"""

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt

import csv
import datetime
import logging
from shutil import copyfile

openpyxl_module = True
try:
    from openpyxl import load_workbook
except Exception as e:
    openpyxl_module = False
import os
import re
import sqlite3
import sys
import traceback

from GUI.ui_dialog_import import Ui_Dialog_Import
from helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()


class DialogImportSurvey(QtWidgets.QDialog):
    """ Import case and file attributes from a csv file. EXTEND LATER
    The first row must contain a header row of the attribute names.
    The first column must contain unique identifiers for each response (the cases)
    this then allows automatic assignment of attributes to each case
    Each column can be categorised as an attribute OR as qualitative.
    Text from each qualitative colums are treated as individual files and loaded into the
    source table.
    Some GUI elements cannot be changed to anotherlanguage:
    Quote format: NONE, MINIMAL, ALL
    Field type: character, numeric qualitative
    """

    app = None
    fields = []
    fields_type = []
    delimiter = ""
    filepath = ""
    headerIndex = 0  # table column index for header context menu actions
    data = []  # obtained from csv file
    preexisting_fields = []  # atribute names already in database
    parent_textEdit = None
    success = False  # ability to load file and has individual ids in first column
    fail_msg = ""

    def __init__(self, app, parent_textEdit):
        """ Need to comment out the connection accept signal line in ui_Dialog_Import.py.
         Otherwise get a double-up of accept signals. """

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.delimiter = ","
        self.fields = []
        self.filepath = ""
        self.success = True

        # Set up the user interface from Designer.
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_Import()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.lineEdit_delimiter.setText(self.delimiter)
        self.ui.lineEdit_delimiter.textChanged.connect(self.options_changed)
        self.ui.comboBox_quote.currentIndexChanged['QString'].connect(self.options_changed)
        self.ui.tableWidget.setHorizontalHeaderLabels([""])
        self.ui.tableWidget.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.tableWidget.horizontalHeader().customContextMenuRequested.connect(self.table_menu)

        cur = self.app.conn.cursor()
        cur.execute("select name from attribute_type where caseOrFile='case'")
        result = cur.fetchall()
        self.preexisting_fields = []
        for row in result:
            self.preexisting_fields.append({'name': row[0]})
        self.select_file()

        #self.success = self.prepare_fields()
        self.prepare_fields()
        self.fill_tableWidget()

        '''if not self.success:
            self.ui.groupBox.setTitle("")
            self.ui.tableWidget.hide()
            self.ui.lineEdit_delimiter.hide()
            self.ui.comboBox_quote.hide()
            self.ui.label_delimiter.hide()
            self.ui.label_quotefmt.hide()
            self.ui.label_information.hide()
            self.ui.label_msg.setText(self.fail_msg)
            self.parent_textEdit.append(_("Survey not imported."))
            super(DialogImportSurvey, self).reject()
            self.close()
        else:
            self.fill_tableWidget()'''

    def select_file(self):
        """ Select csv or Excel file """

        self.filepath, ok = QtWidgets.QFileDialog.getOpenFileName(None,
                                                                  _('Select survey file'),
                                                                  self.app.settings['directory'], "(*.csv *.xlsx)")
        if not ok or self.filepath == "":
            self.parent_textEdit.append(_("Survey not imported. Survey not a csv or xlsx file: ") + self.filepath)
            self.success = False
            return
        # Copy file into project folder
        name_split = self.filepath.split("/")
        filename = name_split[-1]
        destination = self.app.project_path + "/documents/" + filename
        copyfile(self.filepath, destination)

    def read_xlsx_file(self):
        """ Read the data from the xlsx file.
        Fill Class variables self.fields, self.data """

        if openpyxl_module is False:
            self.fail_msg = _(
                "Please install the openpyxl module.\nsudo python3 -m pip install openpyxl OR\npython -m pip install openpyxl")
            return False
        self.data = []
        wb = load_workbook(filename=self.filepath)
        # To work with the first sheet (by name)
        sheets = wb.sheetnames
        ws = wb[sheets[0]]
        sheet = ws
        for value in sheet.iter_rows(values_only=True):
            # some rows may be complete blank so ignore importation
            if (set(value)) != {None}:
                # values are tuples, convert to list, and remove 'None' string
                row = []
                for item in value:
                    if item is None:
                        row.append("")
                    else:
                        row.append(item)
                self.data.append(row)
        # Get field names and replace blacks with a placeholder
        self.fields = []
        for i, f in enumerate(self.data[0]):
            if f != '':
                # Using str() method as f may be an Integer or Float
                self.fields.append(str(f))
            else:
                self.fields.append("Field_" + str(i))
        self.data = self.data[1:]
        # Widgets are not needed
        self.ui.lineEdit_delimiter.hide()
        self.ui.comboBox_quote.hide()
        self.ui.label_delimiter.hide()
        self.ui.label_quotefmt.hide()
        self.ui.label_information.hide()
        self.ui.groupBox.setMinimumSize(QtCore.QSize(0, 30))
        self.ui.groupBox.setMaximumSize(QtCore.QSize(16777215, 30))
        return True

    def read_csv_file(self):
        """ Read the data from the csv file.
         Fill Class variables self.fields, self.data """

        self.data = []
        with open(self.filepath, 'r', newline='') as f:
            delimiter_ = self.ui.lineEdit_delimiter.text()
            if delimiter_ == '':
                msg = _("A column delimiter has not been set.")
                Message(self.app, _("Warning"), msg, "warning").exec_()
                return False
            if delimiter_ in ('ta', 'tab'):
                delimiter_ = "\t"
            # The English text is in the GUI - do not translate with qt linguist
            quoting_ = csv.QUOTE_MINIMAL
            quote_type = self.ui.comboBox_quote.currentText()
            if quote_type == "NONE":
                quoting_ = csv.QUOTE_NONE
            if quote_type == "ALL":
                quoting_ = csv.QUOTE_ALL
            reader = csv.reader(f, delimiter=delimiter_, quoting=quoting_)
            try:
                for row in reader:
                    self.data.append(row)
            except csv.Error as e:
                logger.error(('file %s, line %d: %s' % (self.filepath, reader.line_num, e)))
                self.parent_textEdit.append(_("Row error: ") + str(reader.line_num) + "  " + str(e))
                self.fail_msg(_("Row error: ") + str(e))
                return False
        # Get field names and replace blacks with a placeholder
        self.fields = []
        for i, f in enumerate(self.data[0]):
            if f != '':
                self.fields.append(str(f))
            else:
                self.fields.append("Field_" + str(i))
        self.data = self.data[1:]
        return True

    def prepare_fields(self):
        """ Check for a .csv or .xlsx extension.
        Determine number of fields. Load the data.
        Also called when import options changed. """

        self.fields = []
        self.fields_type = []
        self.data = []
        self.fail_msg = ""

        if self.filepath[-4:].lower() == ".csv":
            success = self.read_csv_file()
            if not success:
                self.parent_textEdit.append(_("Survey not imported.") + self.filepath)
                return False
        else:
            success = self.read_xlsx_file()
            if not success:
                self.parent_textEdit.append(_("Survey not imported.") + self.filepath)
                return False
        self.setWindowTitle(_(_("Importing from: ")) + self.filepath.split('/')[-1])

        # clean field names
        removes = "!@#$%^&*()-+=[]{}\|;:,.<>/?~`"
        for i in range(0, len(self.fields)):
            self.fields[i] = self.fields[i].replace('\t', '')
            self.fields[i] = self.fields[i].replace('\xa0', '')
            for r in removes:
                self.fields[i] = self.fields[i].replace(r, '')
            if self.fields[i] in self.preexisting_fields:
                self.fields[i] += "_DUPLICATED"

        # default field type is character
        self.fields_type = ["character"] * len(self.fields)

        # determine if field type is numeric
        for field in range(0, len(self.fields)):
            numeric = True
            for row in range(0, len(self.data)):
                try:
                    float(self.data[row][field])
                except:
                    numeric = False
            if numeric:
                self.fields_type[field] = "numeric"

        # estimate if field type is qualitative, based on at least 20 different character entries
        for field in range(1, len(self.fields)):
            if self.fields_type[field] == 'character':
                set_of_values = set()
                for row in range(0, len(self.data)):
                    value = ""
                    try:
                        value = self.data[row][field]
                    except IndexError as e:
                        msg = "IndexError: [row] " + str(row) + "   [field] " + str(field)
                        msg += "\nlen(self.data) " + str(len(self.data))
                        msg += "\n" + str(e)
                        logger.debug(msg)
                    set_of_values.add(value)
                if len(set_of_values) > 19:
                    self.fields_type[field] = "qualitative"

        # check first column has unique identifiers
        ids = []
        for row in self.data:
            try:
                ids.append(row[0])
            except IndexError as e:
                # Occurs with csv import if wrong quote type selected
                ids.append("")

        ids_set = set(ids)
        if len(ids) > len(ids_set):
            self.fail_msg = _("There are duplicated identifiers in the first column.\nFile not imported")
            self.parent_textEdit.append(self.filepath + " " + self.fail_msg)
            return False

        msg = _("Survey file: ") + self.filepath + "\n"
        msg += _("Fields: ") + str(len(self.fields)) + ". "
        msg += _("Rows: ") + str(len(self.data))
        logger.info(msg)
        self.parent_textEdit.append(msg)
        return True

    def accept(self):
        """ Check the table details are valid and import the data into a new table or
        append to an existing table. """

        if not self.success:
            super(DialogImportSurvey, self).accept()
            return

        # check for duplicate field names
        if len(self.fields) != len(set(self.fields)):
            msg = "There are duplicate attribute names."
            Message(self.app, _("Attribute name error"), msg, "warning").exec_()
            logger.info(_("Survey Not Imported. Attribute duplicate name error: ") + msg)
            self.parent_textEdit.append(msg)
            self.fields = []
            return

        # check for appropriate quote format
        # inappropriate may produce error IndexError: list index out of range
        quote_format_error = False
        for val in self.data:
            if len(val) != len(self.fields_type):
                quote_format_error = True
        if quote_format_error:
            msg = _("Number of fields does not match header\nPossible wrong quote format")
            logger.error(_("Survey not loaded: ") + msg)
            Message(self.app, _("Survey not loaded"), msg, "warning").exec_()
            return
        self.insert_data()
        super(DialogImportSurvey, self).accept()

    def insert_data(self):
        """ Insert case, attributes, attribute values and qualitative text. """

        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        name_and_caseids = []
        for i, c in enumerate(self.data):
            try:
                self.ui.label_msg.setText(_("Inserting cases: " + str(i)))
                cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)",
                            (c[0], "", self.app.settings['codername'], now_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                name_and_caseids.append([c[0], cur.fetchone()[0]])
                QtWidgets.QApplication.processEvents()
            except sqlite3.IntegrityError as e:
                self.fail_msg = str(e) + _(
                    " - Duplicate case names, either in the file, or duplicates with existing cases in the project")
                logger.error(_("Survey not loaded: ") + self.fail_msg)
                mb = QtWidgets.QMessageBox()
                mb.setIcon(QtWidgets.QMessageBox.Warning)
                mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
                mb.setWindowTitle(_('Survey not loaded'))
                mb.setText(self.fail_msg)
                mb.exec_()
                self.parent_textEdit.append(_("Survey not loaded: ") + self.fail_msg)
                return
        # insert non-qualitative attribute types, except if they are already present
        sql = "select name from attribute_type where caseOrFile='case'"
        cur.execute(sql)
        result = cur.fetchall()
        existing_attr_names = []
        for r in result:
            existing_attr_names.append(r[0])
        sql = "insert into attribute_type (name,date,owner,memo, valueType, caseOrFile) values(?,?,?,?,?,?)"
        for col, name in enumerate(self.fields):
            if self.fields_type[col] != "qualitative" and col > 0:  # col==0 is the case identifier
                if name not in existing_attr_names:
                    logger.debug(name + " is not in case attribute_types. Adding.")
                    cur.execute(sql, (name, now_date, self.app.settings['codername'], "",
                                      self.fields_type[col], 'case'))
        self.app.conn.commit()

        # Look for pre-existing attributes that are not in the survey and insert blank value rows if present
        survey_field_names = []
        for col, fld_name in enumerate(self.fields):
            if self.fields_type[col] != "qualitative" and col > 0:
                survey_field_names.append(fld_name)
        for name in existing_attr_names:
            if name not in survey_field_names:
                for name_id in name_and_caseids:
                    sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,'',?,?,?,?)"
                    cur.execute(sql, (name, name_id[1], 'case', now_date, self.app.settings['codername']))
        self.app.conn.commit()

        # insert non-qualitative values to each case using caseids
        sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
        for i, name_id in enumerate(name_and_caseids):
            self.ui.label_msg.setText(_("Inserting attributes to cases: ") + str(i))
            for val in self.data:
                if name_id[0] == val[0]:
                    for col in range(1, len(val)):
                        if self.fields_type[col] != "qualitative":
                            cur.execute(sql, (self.fields[col], val[col], name_id[1], 'case',
                                              now_date, self.app.settings['codername']))
            QtWidgets.QApplication.processEvents()
        self.app.conn.commit()

        # insert qualitative data into source table
        self.ui.label_msg.setText(_("Creating qualitative text file"))
        source_sql = "insert into source(name,fulltext,memo,owner,date, mediapath) values(?,?,?,?,?, Null)"
        for field in range(1, len(self.fields)):  # column 0 is for identifiers
            case_text_list = []
            if self.fields_type[field] == "qualitative":
                self.fields[field]
                # create one text file combining each row, prefix [case identifier] to each row.
                pos0 = 0
                pos1 = 0
                fulltext = ""
                for row in range(0, len(self.data)):
                    if self.data[row][field] != "":
                        fulltext += "[" + str(self.data[row][0]) + "] "
                        pos0 = len(fulltext) - 1
                        fulltext += str(self.data[row][field]) + "\n\n"
                        pos1 = len(fulltext) - 2
                        case_text = [self.app.settings['codername'], now_date, "", pos0, pos1, name_and_caseids[row][1]]
                        case_text_list.append(case_text)
                # add the current time to the file name to ensure uniqueness and to
                # prevent sqlite Integrity Error. Do not use now_date which contains colons
                now = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H-%M-%S"))
                cur.execute(source_sql,
                            (self.fields[field] + "_" + now, fulltext, "", self.app.settings['codername'], now_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                fid = cur.fetchone()[0]
                case_text_sql = "insert into case_text (owner, date, memo, pos0, pos1, caseid, fid) values(?,?,?,?,?,?,?)"
                for case_text in case_text_list:
                    case_text.append(fid)
                    cur.execute(case_text_sql, case_text)
                self.app.conn.commit()
        logger.info(_("Survey imported"))
        self.parent_textEdit.append(_("Survey imported."))
        Message(self.app, _("Survey imported"), _("Survey imported")).exec_()
        self.app.delete_backup = False

    def options_changed(self):
        """ When import options are changed
        fill the table.
         Import options are: delimiter
         The delimiter can only be one character long """

        self.delimiter = str(self.ui.lineEdit_delimiter.text())
        if self.delimiter == "tb" or self.delimiter == "ta" or self.delimiter == "tab":
            self.delimiter = "\t"
        if len(self.delimiter) > 1 and self.delimiter != "\t":
            self.ui.lineEdit_delimiter.setText(self.delimiter[0:1])
            self.delimiter = self.delimiter[0:1]
        self.read_csv_file()
        self.fill_tableWidget()

    def fill_tableWidget(self):
        """ Fill table widget with data. """

        numRows = self.ui.tableWidget.rowCount()
        for row in range(0, numRows):
            self.ui.tableWidget.removeRow(0)
        self.ui.tableWidget.setColumnCount(len(self.fields))
        for c, field in enumerate(self.fields):
            item = QtWidgets.QTableWidgetItem(field + "\n" + self.fields_type[c] + "\n")
            msg = "Right click to change column name or to change from character to qualitative"
            item.setToolTip(_(msg))
            self.ui.tableWidget.setHorizontalHeaderItem(c, item)
        self.ui.tableWidget.setRowCount(len(self.data))
        for row in range(0, len(self.data)):
            for col in range(0, len(self.fields)):
                value = "MISSING VALUE"
                try:
                    value = str(self.data[row][col])
                except IndexError:
                    pass
                item = QtWidgets.QTableWidgetItem(value)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)  # Not editable
                self.ui.tableWidget.setItem(row, col, item)
        self.ui.tableWidget.resizeColumnsToContents()
        for col in range(0, self.ui.tableWidget.columnCount()):
            if self.ui.tableWidget.columnWidth(col) > 200:
                self.ui.tableWidget.setColumnWidth(col, 200)

    def table_menu(self, pos):
        """ Header context menu to change data types and set primary key(s) and change field names.
        The header index idea came from:
        http://stackoverflow.com/questions/7782071/how-can-i-get-right-click-context-menus-for-clicks-in-qtableview-header
        """

        self.headerIndex = self.ui.tableWidget.indexAt(pos)
        self.headerIndex = int(self.headerIndex.column())

        menu = QtWidgets.QMenu(self)
        ActionChangeFieldName = menu.addAction(_('Change fieldname'))
        ActionChangeFieldName.triggered.connect(self.change_fieldname)
        if self.fields_type[self.headerIndex] == "character" and self.headerIndex != 0:
            ActionChangeFieldName = menu.addAction(_('Change to Qualitative'))
            ActionChangeFieldName.triggered.connect(self.qualitative_field_type)
        if self.fields_type[self.headerIndex] in ('numeric', 'qualitative'):
            ActionChangeFieldName = menu.addAction(_('Change to Character'))
            ActionChangeFieldName.triggered.connect(self.character_field_type)

        menu.popup(self.ui.tableWidget.mapToGlobal(pos))

    # NOTE changes to fields types are overwritten if quote type changed

    def qualitative_field_type(self):
        """ If the current field is listed as character, redefine it as qualitative.
        Qualitative data is stored in the source table """

        self.fields_type[self.headerIndex] = 'qualitative'
        item = QtWidgets.QTableWidgetItem(self.fields[self.headerIndex] + "\n" + \
                                          self.fields_type[self.headerIndex] + "\n")
        self.ui.tableWidget.setHorizontalHeaderItem(self.headerIndex, item)

    def character_field_type(self):
        """ If the current field is listed as numeric or qualitative, redefine it as character.
        """

        self.fields_type[self.headerIndex] = 'character'
        item = QtWidgets.QTableWidgetItem(self.fields[self.headerIndex] + "\n" + \
                                          self.fields_type[self.headerIndex] + "\n")
        self.ui.tableWidget.setHorizontalHeaderItem(self.headerIndex, item)

    def change_fieldname(self):
        """ change the fieldname """

        fieldname, ok = QtWidgets.QInputDialog.getText(None, _("Change field name"), _("New name:"),
                                                       QtWidgets.QLineEdit.Normal, self.fields[self.headerIndex])
        if not ok:
            return
        # check valid values
        if re.match("^[a-zA-Z_\s][a-zA-Z0-9_\s]*$", fieldname) is None or fieldname == "":
            msg = _("Name must contain only letters and numbers or '_' and must not start with a number")
            Message(self.app, _("Field name invalid"), msg, "warning").exec_()
            return
        if fieldname in self.preexisting_fields or fieldname in self.fields:
            msg = fieldname + _(" Already in use")
            Message(self.app, _("Field name invalid."), msg, "warning").exec_()
            return

        self.fields[self.headerIndex] = fieldname
        item = QtWidgets.QTableWidgetItem(self.fields[self.headerIndex] + "\n" + \
                                          self.fields_type[self.headerIndex])
        self.ui.tableWidget.setHorizontalHeaderItem(self.headerIndex, item)
