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
https://qualcoder.wordpress.com/
"""

from PyQt6 import QtCore, QtWidgets
import logging
import os
import sys
import traceback

from .GUI.ui_report_attribute_parameters import Ui_Dialog_report_attribute_parameters
from .helpers import Message

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
    mb.exec()


class DialogSelectAttributeParameters(QtWidgets.QDialog):
    """ Select parameters for attributes to limit coding report results.
    Parameters are either case-based or file-based.
    The English SQL operators: not, between, etc. cannot be exchanged for another language.
    """

    NAME_COLUMN = 0
    CASE_OR_FILE_COLUMN = 1
    TYPE_COLUMN = 2
    OPERATOR_COLUMN = 3
    VALUE_LIST_COLUMN = 4

    app = None
    attribute_type = []
    parameters = []
    limiter = "all"  # all for cases and files, file = file attributes, case = case attributes

    def __init__(self, app, limiter="all", parent=None):
        """ limiter can be 'all', 'file' or 'case' This restricts the attributes to be displayed. """

        super(DialogSelectAttributeParameters, self).__init__(parent)
        sys.excepthook = exception_handler
        self.app = app
        self.limiter = limiter
        self.parameters = []
        cur = self.app.conn.cursor()
        sql = "select name, valuetype, memo, caseOrFile from attribute_type"
        if limiter == "case":
            sql = "select name, valuetype, memo, 'case' from attribute_type where caseOrFile='case'"
        if limiter == "file":
            sql = "select name, valuetype, memo, 'file' from attribute_type where caseOrFile='file'"
        cur.execute(sql)
        self.attribute_type = []
        keys = 'name', 'valuetype', 'memo', 'caseOrFile'
        for row in cur.fetchall():
            self.attribute_type.append(dict(zip(keys, row)))
        # Add the case name as an 'attribute' to files attributes
        if self.limiter == "file":
            casenames = {'name': 'case name', 'valuetype': 'character', 'memo': '', 'caseOrFile': 'case'}
            self.attribute_type.append(casenames)
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_report_attribute_parameters()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.fill_table_widget()
        self.ui.tableWidget.cellChanged.connect(self.cell_modified)
        self.ui.pushButton_clear.pressed.connect(self.clear_parameters)

    def clear_parameters(self):
        """ Clear attribute_list and empty table cells. """

        for x in range(0, self.ui.tableWidget.rowCount()):
            val_text = ""
            self.ui.tableWidget.item(x, self.VALUE_LIST_COLUMN).setText(val_text)
            self.ui.tableWidget.cellWidget(x, self.OPERATOR_COLUMN).setCurrentText("")

    def fill_parameters(self, attribute_list):
        """ Pre fill attributes in Dialog from a previous selection.
        Called by parent class. """

        if not attribute_list:
            return
        for a in attribute_list:
            for x in range(0, self.ui.tableWidget.rowCount()):
                if self.ui.tableWidget.item(x, self.NAME_COLUMN).text() == a[0]:
                    val_text = ""
                    if len(a[4]) == 1:
                        val_text = str(a[4][0])
                    if len(a[4]) > 1:
                        val_text = ";".join(a[4])
                    # Character values are apostrophe quoted, so remove those '
                    val_text = val_text.replace("'", "")
                    self.ui.tableWidget.item(x, self.VALUE_LIST_COLUMN).setText(val_text)
                    self.ui.tableWidget.cellWidget(x, self.OPERATOR_COLUMN).setCurrentText(a[3])

    def accept(self):
        """ Make a parameter list where operator and value are entered.
        Check that values are acceptable for operator and for numeric type. """

        self.parameters = []
        for x in range(0, self.ui.tableWidget.rowCount()):
            values = self.ui.tableWidget.item(x, self.VALUE_LIST_COLUMN).text()
            values = values.split(';')
            tmp = [i for i in values if i != '']
            values = tmp
            operator = self.ui.tableWidget.cellWidget(x, self.OPERATOR_COLUMN).currentText()
            if operator == '':
                values = []
            if operator in ('<', '<=', '>', '>=', '=', 'like') and len(values) > 1:
                values = [values[0]]
            if operator == 'between' and len(values) > 2:
                values = values[:2]
            if operator == 'between' and len(values) < 2:
                operator = ''
                values = []
            # Check numeric type
            type_ = self.ui.tableWidget.item(x, self.TYPE_COLUMN).text()
            not_numeric = False
            if type_ == "numeric":
                for v in values:
                    try:
                        float(v)
                    except ValueError:
                        not_numeric = True
            if not_numeric:
                values = []
            # add single quotes to character values
            if type_ == "character":
                for i in range(0, len(values)):
                    values[i] = "'" + values[i] + "'"
            if values:
                self.parameters.append([self.ui.tableWidget.item(x, self.NAME_COLUMN).text(),
                                        self.ui.tableWidget.item(x, self.CASE_OR_FILE_COLUMN).text(),
                                        self.ui.tableWidget.item(x, self.TYPE_COLUMN).text(),
                                        operator, values])
        super(DialogSelectAttributeParameters, self).accept()

    def reject(self):
        self.parameters = []
        super(DialogSelectAttributeParameters, self).reject()

    def cell_modified(self):
        """ Values entered or changed in the values_list column. Allow value entry
        only if the operator has been selected. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        self.ui.tableWidget.resizeColumnsToContents()
        if y != self.VALUE_LIST_COLUMN:
            return
        self.ui.tableWidget.blockSignals(True)  # Prevent double opening of Messages on widget changes
        values = self.ui.tableWidget.item(x, y).text()
        values = values.split(';')
        tmp = [i for i in values if i != '']
        values = tmp
        operator = self.ui.tableWidget.cellWidget(x, self.OPERATOR_COLUMN).currentText()
        if operator == '':
            Message(self.app, _('Warning'), _("No operator was selected"), "warning").exec()
            self.ui.tableWidget.item(x, y).setText('')
        # Enforce that value list is only one item for selected operators
        if operator in ('<', '<=', '>', '>=', '=', 'like') and len(values) > 1:
            Message(self.app, _('Warning'), _("Too many values given for this operator"), "warning").exec()
            self.ui.tableWidget.item(x, y).setText(values[0])
        if operator == 'between' and len(values) != 2:
            Message(self.app, _('Warning'), _("Need 2 values for between"), "warning").exec()
        # Check numeric type
        type_ = self.ui.tableWidget.item(x, self.TYPE_COLUMN).text()
        if type_ == "numeric":
            for v in values:
                try:
                    float(v)
                except ValueError:
                    Message(self.app, _('Warning'), v + _(" is not a number"), "warning").exec()
                    self.ui.tableWidget.item(x, y).setText("")
        self.ui.tableWidget.blockSignals(False)

    def get_tooltip_values(self, name, case_or_file, valuetype):
        """ Get values to display in tooltips for the value list column. """

        tt = ""
        cur = self.app.conn.cursor()
        if valuetype == "numeric":
            sql = "select min(cast(value as real)), max(cast(value as real)) from attribute where name=? and attr_type=?"
            cur.execute(sql, [name, case_or_file])
            res = cur.fetchone()
            tt = _("Minimum: ") + str(res[0]) + "\n"
            tt += _("Maximum: ") + str(res[1])
        if valuetype == "character":
            sql = "select distinct value from attribute where name=? and attr_type=? and length(value)>0 limit 10"
            cur.execute(sql, [name, case_or_file])
            res = cur.fetchall()
            for r in res:
                tt += "\n" + r[0]
            if len(tt) > 1:
                tt = tt[1:]
        return tt

    def fill_table_widget(self):
        """ Fill the table widget with attribute name and type. """

        for row, a in enumerate(self.attribute_type):
            self.ui.tableWidget.insertRow(row)
            item = QtWidgets.QTableWidgetItem(a['name'])
            item.setToolTip(a['memo'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['caseOrFile'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.CASE_OR_FILE_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['valuetype'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.TYPE_COLUMN, item)
            cb = QtWidgets.QComboBox()
            cb.setMinimumWidth(100)  # To show 'between' wording
            items = ['', '<', '>', '<=', '>=', '=', '!=', 'in', 'not in', 'between', 'like']
            if self.limiter == "file" and a['caseOrFile'] == "case":
                items = ['', '=', '!=', 'like']
            cb.addItems(items)
            self.ui.tableWidget.setCellWidget(row, self.OPERATOR_COLUMN, cb)
            item = QtWidgets.QTableWidgetItem('')
            tt = self.get_tooltip_values(a['name'], a['caseOrFile'], a['valuetype'])
            item.setToolTip(tt)
            self.ui.tableWidget.setItem(row, self.VALUE_LIST_COLUMN, item)
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
