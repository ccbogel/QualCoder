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
https://qualcoder.wordpress.com/
'''

from PyQt5 import QtCore, QtGui, QtWidgets
import datetime
from GUI.ui_report_attribute_parameters import Ui_Dialog_report_attribute_parameters
import os
import sys
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


class DialogSelectAttributeParameters(QtWidgets.QDialog):
    ''' Select parameters for attributes to limit coding report results.
    Parameters are either case-based or file-based.
    The English SQL operators: not, between, etc. cannot be exchanged for another language.
    '''

    NAME_COLUMN = 0
    CASE_OR_FILE_COLUMN = 1
    TYPE_COLUMN = 2
    OPERATOR_COLUMN = 3
    VALUE_LIST_COLUMN = 4

    settings = None
    attribute_type = []
    parameters = []

    def __init__(self, settings, parent=None):

        super(DialogSelectAttributeParameters, self).__init__(parent)  # overrride accept method
        sys.excepthook = exception_handler
        self.settings = settings
        self.parameters = []
        cur = self.settings['conn'].cursor()
        sql = "select name, valuetype, memo, caseOrFile from attribute_type"
        cur.execute(sql)
        result = cur.fetchall()
        self.attribute_type = []
        for row in result:
            self.attribute_type.append({'name': row[0], 'valuetype': row[1],
                'memo': row[2], 'caseOrFile': row[3]})
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_report_attribute_parameters()
        self.ui.setupUi(self)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)
        self.fill_tableWidget()
        #self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.tableWidget.cellChanged.connect(self.cell_modified)

    def accept(self):
        ''' Make a parameter list where operator and value are entered.
        Check that values are acceptable for operator and for numeric type. '''

        self.parameters = []
        for x in range(0, self.ui.tableWidget.rowCount()):
            values = self.ui.tableWidget.item(x, self.VALUE_LIST_COLUMN).text()
            values = values.split(';')
            tmp = [i for i in values if i != '']
            values = tmp
            operator = self.ui.tableWidget.cellWidget(x, self.OPERATOR_COLUMN).currentText()
            if operator == '':
                values = []
            if operator in ('<','<=','>','>=','==','like') and len(values) > 1:
               values = [values[0]]
            if operator == 'between' and len(values) > 2:
                values = values[:2]
            if operator == 'between' and len(values) < 2:
                operator = ''
                values = []
            # check numeric type
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
                for i in range (0, len(values)):
                    values[i] = "'" + values[i] + "'"
            if values != []:
                self.parameters.append([self.ui.tableWidget.item(x, self.NAME_COLUMN).text(),
                self.ui.tableWidget.item(x, self.CASE_OR_FILE_COLUMN).text(),
                self.ui.tableWidget.item(x, self.TYPE_COLUMN).text(),
                operator, values])

        super(DialogSelectAttributeParameters, self).accept()

    def reject(self):
        self.parameters = []
        super(DialogSelectAttributeParameters, self).reject()

    def cell_modified(self):
        ''' Values entered or changed in the values_list column. Allow value entry
        only if the operator has been selected. '''

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        self.ui.tableWidget.resizeColumnsToContents()
        if y != self.VALUE_LIST_COLUMN:
            return
        values = self.ui.tableWidget.item(x, y).text()
        values = values.split(';')
        tmp = [i for i in values if i != '']
        values = tmp
        operator = self.ui.tableWidget.cellWidget(x, self.OPERATOR_COLUMN).currentText()
        if operator == '':
            self.ui.tableWidget.item(x, y).setText('')
            QtWidgets.QMessageBox.warning(None, _('Warning'),_("No operator was selected"), QtWidgets.QMessageBox.Ok)
            return
        # enforce that value list is only one item for selected operators
        if operator in ('<','<=','>','>=','==','like') and len(values) > 1:
            QtWidgets.QMessageBox.warning(None, _('Warning'), _("Too many values given for this operator"),
                QtWidgets.QMessageBox.Ok)
            self.ui.tableWidget.item(x, y).setText(values[0])
        if operator == 'between' and len(values) != 2:
            QtWidgets.QMessageBox.warning(None, _('Warning'), _("Need 2 values for between"), QtWidgets.QMessageBox.Ok)
        # check numeric type
        type_ = self.ui.tableWidget.item(x, self.TYPE_COLUMN).text()
        if type_ == "numeric":
            for v in values:
                try:
                    float(v)
                except ValueError:
                    QtWidgets.QMessageBox.warning(None, _('Warning'), v + _(" is not a number"), QtWidgets.QMessageBox.Ok)
                    self.ui.tableWidget.item(x, y).setText("")

    def fill_tableWidget(self):
        ''' Fill the table widget with attribute name and type. '''

        for row, a in enumerate(self.attribute_type):
            self.ui.tableWidget.insertRow(row)
            item = QtWidgets.QTableWidgetItem(a['name'])
            item.setToolTip(a['memo'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['caseOrFile'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.CASE_OR_FILE_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(a['valuetype'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.TYPE_COLUMN, item)
            item = QtWidgets.QComboBox()
            item.addItems(['', '<', '>', '<=', '>=', '==', '!=', 'in', 'not in', 'between', 'like'])
            self.ui.tableWidget.setCellWidget(row, self.OPERATOR_COLUMN, item)
            item = QtWidgets.QTableWidgetItem('')
            #item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.VALUE_LIST_COLUMN, item)
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogSelectAttributeParameters()
    ui.show()
    sys.exit(app.exec_())

