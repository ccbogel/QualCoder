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

from PyQt6 import QtCore, QtWidgets
import logging
import os

from .GUI.ui_report_attribute_parameters import Ui_Dialog_report_attribute_parameters
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogSelectAttributeParameters(QtWidgets.QDialog):
    """ Select parameters for attributes to limit coding report results.
    Parameters are from either case-based or file-based, or both.
    The English SQL operators: not, between, etc. cannot be exchanged for another language.
    sqls are NOT parameterised.

    Select files based on attribute selections.
    Attribute results are a dictionary of:
    [0] attribute name,
    [1] attribute type: character, numeric
    [2] modifier: > < == != like between
    [3] comparison value as list, one item or two items for between

    The first parameter is a flag for the BOOLEAN_AND or BOOLEAN_OR

    Each parameter selected of:
    attribute name, file or case, character or numeric, operator, list of one or two comparator values
    two comparator values are used with the 'between' operator
    ['source', 'file', 'character', '==', ["'interview'"]]
    ['case name', 'case', 'character', '==', ["'ID1'"]]

    Results are intersected, with AND boolean function, or with union OR function.
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

    result_file_ids = []
    result_case_ids = []
    result_tooltip_msg = ""

    def __init__(self, app, limiter="all", parent=None):
        """ limiter can be 'all', 'file' or 'case' This restricts the attributes to be displayed. """

        super(DialogSelectAttributeParameters, self).__init__(parent)
        self.app = app
        self.limiter = limiter
        self.parameters = []
        self.result_file_ids = []
        self.result_case_ids = []
        self.result_tooltip_msg = ""
        self.tooltip_msg = ""
        cur = self.app.conn.cursor()
        sql = "select name, valuetype, ifnull(memo,''), caseOrFile from attribute_type where caseOrFile!='journal'"
        if limiter == "case":
            sql = "select name, valuetype, ifnull(memo,''), 'case' from attribute_type where caseOrFile='case'"
        if limiter == "file":
            sql = "select name, valuetype, ifnull(memo,''), 'file' from attribute_type where caseOrFile='file'"
        cur.execute(sql)
        self.attribute_type = []
        keys = 'name', 'valuetype', 'memo', 'caseOrFile'
        for row in cur.fetchall():
            self.attribute_type.append(dict(zip(keys, row)))
        # Add the case name as an 'attribute' attributes - reivew this
        cur.execute("select count(*) from cases")
        cases_present = cur.fetchone()
        if cases_present:
            casenames = {'name': 'case name', 'valuetype': 'character', 'memo': '', 'caseOrFile': 'case'}
            self.attribute_type.append(casenames)
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_report_attribute_parameters()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
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
        """ Pre-fill attributes in Dialog from a previous selection.
        Called by parent class. """

        if not attribute_list:
            return
        first_attr = attribute_list.pop(0)
        radio_bool = first_attr[0]
        if radio_bool == "BOOLEAN_OR":
            self.ui.radioButton_or.setChecked(True)
        else:
            self.ui.radioButton_and.setChecked(True)
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
        if self.ui.radioButton_or.isChecked():
            self.parameters.append(["BOOLEAN_OR"])
        else:
            self.parameters.append(["BOOLEAN_AND"])
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
            # Add single quotes to character values
            if type_ == "character":
                for i in range(0, len(values)):
                    values[i] = f"'{values[i]}'"
            if values:
                self.parameters.append([self.ui.tableWidget.item(x, self.NAME_COLUMN).text(),
                                        self.ui.tableWidget.item(x, self.CASE_OR_FILE_COLUMN).text(),
                                        self.ui.tableWidget.item(x, self.TYPE_COLUMN).text(),
                                        operator, values])
        self.get_results_case_ids()
        self.get_results_file_ids()
        self.get_results_message()
        super(DialogSelectAttributeParameters, self).accept()

    def get_results_case_ids(self):
        """ Consolidate list of case ids from case parameters. """

        #print("get results case ids")
        self.result_case_ids = []
        boolean_and_or = self.parameters[0][0]
        cur = self.app.conn.cursor()
        if boolean_and_or == "BOOLEAN_OR":
            for a in self.parameters:
                # case name attribute
                if len(a) > 1 and a[0] == 'case name' and a[1] == 'case':
                    case_sql = "select distinct cases.caseid from cases where "
                    case_sql += f"cases.name {a[3]} "
                    if a[3] == 'between':
                        case_sql += f"{a[4][0]} and {a[4][1]} "
                    if a[3] in ('in', 'not in'):
                        case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                    if a[3] not in ('between', 'in', 'not in'):
                        case_sql += a[4][0]
                    cur.execute(case_sql)
                    result = cur.fetchall()
                    #print("case name Res", result)
                    for i in result:
                        self.result_case_ids.append(i[0])
                # Most case attributes
                if len(a) > 1 and a[0] != 'case name' and a[1] == 'case':
                    # Case text table also links av and images
                    case_sql = "select distinct cases.caseid from cases "
                    case_sql += "join attribute on cases.caseid=attribute.id "
                    case_sql += " where "
                    case_sql += f"attribute.name = '{a[0]}' "
                    case_sql += f" and attribute.value {a[3]} "
                    if a[3] == 'between':
                        case_sql += f"{a[4][0]} and {a[4][1]} "
                    if a[3] in ('in', 'not in'):
                        case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                    if a[3] not in ('between', 'in', 'not in'):
                        case_sql += a[4][0]
                    if a[2] == 'numeric':
                        case_sql = case_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                    case_sql += " and attribute.attr_type='case'"
                    #print("Attribute selected: ", a)
                    cur.execute(case_sql)
                    result = cur.fetchall()
                    #print("Res", result)
                    for i in result:
                        self.result_case_ids.append(i[0])
            #print("Case ids", self.result_case_ids)
            return
        # Boolean and
        list_of_sets = []
        for a in self.parameters:
            # case name attribute
            if len(a) > 1 and a[0] == 'case name' and a[1] == 'case':
                case_sql = "select distinct cases.caseid from cases where "
                case_sql += f"cases.name {a[3]} "
                if a[3] == 'between':
                    case_sql += f"{a[4][0]} and {a[4][1]} "
                if a[3] in ('in', 'not in'):
                    case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    case_sql += a[4][0]
                cur.execute(case_sql)
                result = cur.fetchall()
                #print("case name Res", result)
                for i in result:
                    self.result_case_ids.append(i[0])
            # All other case attributes
            if len(a) > 1 and a[1] == 'case':
                attribute_set = set()
                # Case text table also links av and images
                case_sql = "select distinct cases.caseid from cases "
                case_sql += "join attribute on cases.caseid=attribute.id "
                case_sql += " where "
                case_sql += f"attribute.name = '{a[0]}' "
                case_sql += f" and attribute.value {a[3]} "
                if a[3] == 'between':
                    case_sql += f"{a[4][0]} and {a[4][1]} "
                if a[3] in ('in', 'not in'):
                    case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    case_sql += a[4][0]
                if a[2] == 'numeric':
                    case_sql = case_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                case_sql += " and attribute.attr_type='case'"
                # print("Attribute selected: ", a)
                # print(case_sql)
                cur.execute(case_sql)
                result = cur.fetchall()
                for res in result:
                    attribute_set.add(res[0])
                if attribute_set != {}:
                    list_of_sets.append(attribute_set)
        if len(list_of_sets) == 1:
            self.result_case_ids = list(list_of_sets[0])
        if len(list_of_sets) > 1:
            result_set = set.intersection(*list_of_sets)
            self.result_case_ids = list(result_set)

    def get_results_file_ids(self):
        """ Consolidate list of file ids from file and case parameters. """

        #print("get file ids")
        # Get file id's for case attributes and for file attributes
        file_ids = self.select_attributes_file_ids()
        case_file_ids = self.select_attributes_case_file_ids()
        #print("file ids", file_ids)
        #print("case ids", case_file_ids)
        # Consolidate case and file ids, using 'and' or 'or'
        if file_ids == [] and case_file_ids == []:
            return
        set_ids = {}
        set_file_ids = set(file_ids)
        set_case_file_ids = set(case_file_ids)
        # 'and' attribute radio button selected
        #print("get results file ids Files: ", set_file_ids)
        #print("get results file ids Cases: ", set_case_file_ids)
        if file_ids != [] and case_file_ids != [] and self.parameters[0][0] == "BOOLEAN_AND":
            set_ids = set_file_ids.intersection(set_case_file_ids)
        # 'or' attribute radio button selected
        if file_ids != [] and case_file_ids != [] and self.parameters[0][0] == "BOOLEAN_OR":
            set_ids = set_file_ids.union(set_case_file_ids)
        if file_ids != [] and case_file_ids == []:
            set_ids = set_file_ids
        if file_ids == [] and case_file_ids != []:
            set_ids = set_case_file_ids
        #print("set ids: ", set_ids)
        self.result_file_ids = list(set_ids)

    def get_results_message(self):
        """ Prepare message for label tooltip. """

        self.tooltip_msg = _("Show files:")
        file_msg = ""
        case_msg = ""
        bool_msg = " or "
        for a in self.parameters:
            if len(a) == 1 and a[0] == "BOOLEAN_AND":
                bool_msg = " and "
            if len(a) > 1 and a[1] == 'file':
                file_msg += bool_msg + a[0] + " " + a[3] + " " + ",".join(a[4])
        if len(file_msg) > len(bool_msg):
            file_msg = "(" + _("File: ") + file_msg[len(bool_msg):] + ")"
        for a in self.parameters:
            if len(a) > 1 and a[1] == 'case':
                case_msg += bool_msg + a[0] + " " + a[3] + " " + ",".join(a[4])
        if len(case_msg) > len(bool_msg):
            case_msg = "(" + _("Case: ") + case_msg[len(bool_msg):] + ")"
        if file_msg != "" and case_msg != "":
            self.tooltip_msg += file_msg + " and " + case_msg
        else:
            self.tooltip_msg += file_msg + case_msg

    def select_attributes_file_ids(self):
        """ Attribute search. Get file ids for attribute parameters using a boolean or / boolean and """

        file_ids = []
        boolean_and_or = self.parameters[0][0]
        cur = self.app.conn.cursor()
        if boolean_and_or == "BOOLEAN_OR":
            for a in self.parameters:
                # File attributes
                file_sql = "select id from attribute where "
                if len(a) > 1 and a[1] == 'file':
                    file_sql += "attribute.name = '" + a[0] + "' "
                    file_sql += " and attribute.value " + a[3] + " "
                    if a[3] == 'between':
                        file_sql += a[4][0] + " and " + a[4][1] + " "
                    if a[3] in ('in', 'not in'):
                        file_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                    if a[3] not in ('between', 'in', 'not in'):
                        file_sql += a[4][0]
                    if a[2] == 'numeric':
                        file_sql = file_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                    file_sql += " and attribute.attr_type='file'"
                    cur.execute(file_sql)
                    result = cur.fetchall()
                    for i in result:
                        file_ids.append(i[0])
            return file_ids
        # boolean and
        list_of_sets = []
        for a in self.parameters:
            # File attributes
            file_sql = "select id from attribute where "
            if len(a) > 1 and a[1] == 'file':
                attribute_set = set()
                file_sql += "attribute.name = '" + a[0] + "' "
                file_sql += " and attribute.value " + a[3] + " "
                if a[3] == 'between':
                    file_sql += a[4][0] + " and " + a[4][1] + " "
                if a[3] in ('in', 'not in'):
                    file_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    file_sql += a[4][0]
                if a[2] == 'numeric':
                    file_sql = file_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                file_sql += " and attribute.attr_type='file'"
                cur.execute(file_sql)
                result = cur.fetchall()
                for i in result:
                    attribute_set.add(i[0])
                if attribute_set != {}:
                    list_of_sets.append(attribute_set)
        if len(list_of_sets) == 1:
            return list(list_of_sets[0])
        if len(list_of_sets) > 1:
            result_set = set.intersection(*list_of_sets)
            return list(result_set)
        return []

    def select_attributes_case_file_ids(self):
        """ Attribute search. Get case ids for attribute parameters using a boolean or / boolean and  """

        case_file_ids = []
        boolean_and_or = self.parameters[0][0]
        cur = self.app.conn.cursor()
        if boolean_and_or == "BOOLEAN_OR":
            for a in self.parameters:
                # case name attribute
                if len(a) > 1 and a[0] == 'case name' and a[1] == 'case':
                    case_sql = "select distinct case_text.fid from cases "
                    case_sql += "join case_text on case_text.caseid=cases.caseid where "
                    case_sql += f"cases.name {a[3]} "
                    if a[3] == 'between':
                        case_sql += f"{a[4][0]} and {a[4][1]} "
                    if a[3] in ('in', 'not in'):
                        case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                    if a[3] not in ('between', 'in', 'not in'):
                        case_sql += a[4][0]
                    cur.execute(case_sql)
                    result = cur.fetchall()
                    #print("select case file ids OR: case name Res", result)
                    for i in result:
                        case_file_ids.append(i[0])
                # Other case attributes
                if len(a) > 1 and a[0] != 'case name' and a[1] == 'case':
                    # Case text table also links av and images
                    case_sql = "select distinct case_text.fid from cases "
                    case_sql += "join case_text on case_text.caseid=cases.caseid "
                    case_sql += "join attribute on cases.caseid=attribute.id "
                    case_sql += " where "
                    case_sql += f"attribute.name = '{a[0]}' "
                    case_sql += f" and attribute.value {a[3]} "
                    if a[3] == 'between':
                        case_sql += f"{a[4][0]} and {a[4][1]} "
                    if a[3] in ('in', 'not in'):
                        case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                    if a[3] not in ('between', 'in', 'not in'):
                        case_sql += a[4][0]
                    if a[2] == 'numeric':
                        case_sql = case_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                    case_sql += " and attribute.attr_type='case'"
                    # print("Attribute selected: ", a)
                    # print(case_sql)
                    cur.execute(case_sql)
                    case_results = cur.fetchall()
                    for res in case_results:
                        case_file_ids.append(res[0])
            return case_file_ids
        # Boolean and
        list_of_sets = []
        for a in self.parameters:
            # case name attribute
            if len(a) > 1 and a[0] == 'case name' and a[1] == 'case':
                attribute_set = set()
                case_sql = "select distinct case_text.fid from cases "
                case_sql += "join case_text on case_text.caseid=cases.caseid where "
                case_sql += f"cases.name {a[3]} "
                if a[3] == 'between':
                    case_sql += f"{a[4][0]} and {a[4][1]} "
                if a[3] in ('in', 'not in'):
                    case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    case_sql += a[4][0]
                cur.execute(case_sql)
                results = cur.fetchall()
                #print("select case file ids AND: case name Res", results)
                for res in results:
                    attribute_set.add(res[0])
                if attribute_set != {}:
                    list_of_sets.append(attribute_set)
            # All other case attributes
            if len(a) > 1 and a[0] != 'case name' and a[1] == 'case':
                attribute_set = set()
                # Case text table also links av and images
                case_sql = "select distinct case_text.fid from cases "
                case_sql += "join case_text on case_text.caseid=cases.caseid "
                case_sql += "join attribute on cases.caseid=attribute.id "
                case_sql += " where "
                case_sql += f"attribute.name = '{a[0]}' "
                case_sql += f" and attribute.value {a[3]} "
                if a[3] == 'between':
                    case_sql += f"{a[4][0]} and {a[4][1]} "
                if a[3] in ('in', 'not in'):
                    case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    case_sql += a[4][0]
                if a[2] == 'numeric':
                    case_sql = case_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                case_sql += " and attribute.attr_type='case'"
                # print("Attribute selected: ", a)
                # print(case_sql)
                cur.execute(case_sql)
                results = cur.fetchall()
                for res in results:
                    attribute_set.add(res[0])
                if attribute_set != {}:
                    list_of_sets.append(attribute_set)
        if len(list_of_sets) == 1:
            return list(list_of_sets[0])
        if len(list_of_sets) > 1:
            result_set = set.intersection(*list_of_sets)
            return list(result_set)
        return []

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
            tt = f'{_("Minimum:")} {res[0]}\n{_("Maximum:")} {res[1]}'
        if valuetype == "character":
            sql = "select distinct value from attribute where name=? and attr_type=? and length(value)>0 limit 20"
            cur.execute(sql, [name, case_or_file])
            res = cur.fetchall()
            for r in res:
                tt += f"\n{r[0]}"
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
