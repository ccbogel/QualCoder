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

from copy import deepcopy
import logging
import openpyxl
import os
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/

from PyQt6 import QtCore, QtWidgets, QtGui

from .GUI.ui_comparison_table import Ui_Dialog_Comparisons
from .helpers import ExportDirectoryPathDialog, Message, DialogCodeInText, DialogCodeInImage, DialogCodeInAV, msecs_to_hours_mins_secs
from .select_items import DialogSelectItems


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogReportComparisonTable(QtWidgets.QDialog):
    """ Provide a co-occurrence report.
    """

    app = None
    parent_tetEdit = None

    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_textEdit = parent_text_edit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_Comparisons()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_export.pressed.connect(self.export_to_excel)
        self.ui.pushButton_select_files.setIcon(qta.icon('mdi6.file-multiple', options=[{'scale_factor': 1.2}]))
        self.ui.pushButton_select_files.pressed.connect(self.select_files)
        self.ui.pushButton_select_cases.setIcon(qta.icon('mdi6.briefcase-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_select_cases.pressed.connect(self.select_cases)
        self.ui.pushButton_select_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_select_attributes.pressed.connect(self.select_attributes)
        self.ui.pushButton_select_codes.setIcon(qta.icon('mdi6.text', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_select_codes.pressed.connect(self.select_codes)
        self.ui.pushButton_select_categories.setIcon(qta.icon('mdi6.file-tree', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_select_categories.pressed.connect(self.select_categories)
        self.ui.checkBox_hide_blanks.stateChanged.connect(self.show_or_hide_empty_rows_and_cols)
        self.ui.listWidget.itemPressed.connect(self.show_list_item)
        #self.ui.listWidget.setSelectionMode()
        tablefont = f'font: 10pt "{self.app.settings["font"]}";'
        self.ui.tableWidget.setStyleSheet(tablefont)  # should be smaller
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        #self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        #self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.splitter.setSizes([500, 0])

        self.codes, self.categories = self.app.get_codes_categories()
        self.files = self.app.get_text_filenames()

        self.data = []
        self.max_count = 0
        self.data_counts = []
        self.data_colors = []
        self.data_list_widget = []   # Used with listed widget display and with sleected lis widget item

    def select_attributes(self):
        """  """

        pass

    def select_categories(self):
        """  """
        pass

    def select_files(self):
        """ Select files, stored in self.file_ids_names, then load data and fill table. """

        selection_list = [{'id': -1, 'name': ''}]
        for file_name in self.app.get_filenames():
            selection_list.append(file_name)
        ui = DialogSelectItems(self.app, selection_list, _("Select files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected or selected[0]['name'] == '':
            self.files = self.app.get_filenames()
            Message(self.app, _("Files selected"), _("All files selected")).exec()
        else:
            self.files = selected
            msg = ""
            for item in self.files:
                msg += f"{item['name']}\n"
            Message(self.app, _("Files selected"), msg).exec()

        # Prep
        print("Files\n", self.files)

        print("Codes\n")
        for c in self.codes:
            print(c['cid'], c['name'])

        self.process_files_data()

    def process_files_data(self):
        """ Calculate the relations for selected codes for ALL coders (or only THIS coder - TODO).
        For text? codings only.
        Rows as codes, columns as files.

        Data items:
        For DialogCodeInText
                dictionary {codename, color, file_or_casename, pos0, pos1, text, coder, fid, file_or_case,
                            textedit_start, textedit_end}
        For DialogCodeInImage
                dictionary {codename, color, file_or_casename, x1, y1, width, height, coder,
                 mediapath, fid, memo, file_or_case}

        """

        self.ui.checkBox_hide_blanks.setChecked(False)
        self.ui.splitter.setSizes([500, 0])

        # Create data matrices zeroed, codes are ordered alphabetically by name
        self.data_counts = []
        self.max_count = 0
        self.data_colors = []
        self.data = []
        for row in self.codes:
            self.data_counts.append([0] * len(self.files))
            self.data_colors.append([""] * len(self.files))
            self.data.append(["."] * len(self.files))

        cur = self.app.conn.cursor()
        for row, code_ in enumerate(self.codes):
            for col, file_ in enumerate(self.files):
                # Text results
                sql = "select source.id,source.name, code_text.cid, code_name.name, code_name.color, pos0, pos1," \
                      "ctid,seltext, ifnull(code_text.memo,''), " \
                      "code_text.owner, 'file', 'text' from code_text " \
                      "join code_name on code_name.cid=code_text.cid " \
                      "join source on code_text.fid=source.id " \
                      "where code_text.fid=? and code_text.cid=? order by code_text.ctid"
                cur.execute(sql, [file_['id'], code_['cid']])
                results_text = cur.fetchall()
                keys_text = 'fid', 'file_or_casename', 'cid', 'codename', 'color', 'pos0', 'pos1', 'ctid', 'text', \
                    'memo', 'owner', 'file_or_case', 'result_type'
                text_data = []
                for res in results_text:
                    text_data.append(dict(zip(keys_text, res)))

                # Image results
                sql = "select source.id,source.name, code_image.cid, code_name.name, code_name.color, x1,y1," \
                      "width,height, ifnull(code_image.memo,''), " \
                      "code_image.owner, mediapath, 'file', 'image' from code_image " \
                      "join code_name on code_name.cid=code_image.cid " \
                      "join source on code_image.id=source.id " \
                      "where code_image.id=? and code_image.cid=? order by code_image.imid"
                cur.execute(sql, [file_['id'], code_['cid']])
                results_image = cur.fetchall()
                keys_image = 'fid', 'file_or_casename', 'cid', 'codename', 'color', 'x1', 'y1', 'width', 'height', \
                    'memo', 'owner', 'mediapath', 'file_or_case', 'result_type'
                image_data = []
                for res in results_image:
                    image_data.append(dict(zip(keys_image, res)))

                # Audio /video results
                sql = "select source.id,source.name, code_av.cid, code_name.name, code_name.color, pos0,pos1, " \
                      "ifnull(code_av.memo,''), " \
                      "code_av.owner, mediapath, 'file', 'av' from code_av " \
                      "join code_name on code_name.cid=code_av.cid " \
                      "join source on code_av.id=source.id " \
                      "where code_av.id=? and code_av.cid=? order by code_av.avid"
                cur.execute(sql, [file_['id'], code_['cid']])
                results_av = cur.fetchall()
                keys_av = 'fid', 'file_or_casename', 'cid', 'codename', 'color', 'pos0', 'pos1', \
                    'memo', 'owner', 'mediapath', 'file_or_case', 'result_type'
                av_data = []
                for res in results_av:
                    av_data.append(dict(zip(keys_av, res)))


                result_length = len(results_text) + len(results_image) + len(results_av)
                if result_length > self.max_count:
                    self.max_count = result_length
                self.data_counts[row][col] = result_length

                self.data[row][col] = text_data + image_data + av_data

        '''print("===============")
        print("Data counts POST")
        for r in self.data_counts:
            print(r)
        print("===============")'''

        # Color heat map for spread across 5 colours
        colors = ["#F8E0E0", "#F6CECE", "#F5A9A9", "#F78181", "#FA5858"]  # light to dark red
        for row, row_data in enumerate(self.data_counts):
            for col, item_data in enumerate(row_data):
                if self.data_counts[row][col] > 0:
                    color_range_index = int(self.data_counts[row][col] / self.max_count * 5) - 1
                    if color_range_index < 0:
                        color_range_index = 0
                    self.data_colors[row][col] = colors[color_range_index]

        self.fill_table(self.files)

    def select_cases(self):
        """  """
        pass

    def select_codes(self):
        """ Select codes. """

        selection_list = [{'id': -1, 'name': ''}]
        codes, categories = self.app.get_codes_categories()
        for code_ in codes:
            selection_list.append(code_)
        ui = DialogSelectItems(self.app, selection_list, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected or selected[0]['name'] == '':
            #selected = deepcopy(self.codes)
            self.codes = codes
            Message(self.app, _("Codes selected"), _("All codes selected")).exec()
        else:
            msg = ""
            self.codes = []
            for selected_code in selected:
                self.codes.append(selected_code)
                msg += f"{selected_code['name']}\n"
            Message(self.app, _("Codes selected"), msg).exec()

        '''self.code_ids_str = ""
        self.code_ids = []
        #self.code_names_str = ""
        self.code_names_list = []
        for code_ in selected:
            self.code_names_list.append(code_['name'])
            #self.code_names_str += f"{code_['name']}|"
            self.code_ids_str += f",{code_['cid']}"
            self.code_ids.append(code_['cid'])
        self.code_ids_str = self.code_ids_str[1:]'''
        #self.process_files_data()

    def export_to_excel(self):
        """ Export to Excel file. """

        filename = "Code_comarisons.xlsx"
        export_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = export_dir.filepath
        if filepath is None:
            return

        # Excel vertical and horizontal headers
        header = []
        for code_ in self.codes:
            name_split_50 = [code_['name'][y - 50:y] for y in range(50, len(code_['name']) + 50, 50)]
            # header_labels.append(code_['name'])  # OLD, need line separators
            header.append("\n".join(name_split_50))
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Counts"
        wb.create_sheet("Details")
        ws2 = wb["Details"]
        for col, col_name in enumerate(header):
            h_cell = ws.cell(row=1, column=col + 2)
            h_cell.value = col_name
            h_cell2 = ws2.cell(row=1, column=col + 2)
            h_cell2.value = col_name
            v_cell = ws.cell(row=col + 2, column=1)
            v_cell.value = col_name
            v_cell2 = ws2.cell(row=col + 2, column=1)
            v_cell2.value = col_name
        # Co-occurrence counts
        for row, row_data in enumerate(self.data_counts):
            for col, col_data in enumerate(row_data):
                cell = ws.cell(row=row + 2, column=col + 2)
                cell.value = col_data
                # Details list
                if self.data_details[row][col] == ".":
                    continue
                details = ""
                for data in self.data_details[row][col]:
                    '''
                    0 - 5 [r['cid0'], r['c0_name'], r['ctid0'], r['cid1'], r['c1_name'], r['ctid1'], 
                    6 - 8 r['fid'], r['file_name'], r['owners'], 
                    9 - 12 r['c0_pos0'], r['c0_pos1'], r['c1_pos0'], r['c1_pos1'],
                    13 - 16 r['text_before'], r['text_overlap'], r['text_after'], r['relation']]
                    '''
                    details += f"Codes: {data[1]} ({data[9]} - {data[10]})| {data[4]} ({data[11]} - {data[12]})\n"
                    details += f"Coders: {data[8]}. (ctid0: {data[2]} | ctid1: {data[5]})\n"
                    details += f"File (fid {data[6]}): {data[7]}\n"
                    details += f"{data[13]}[[{data[14]}]]{data[15]}\n========\n"
                d_cell = ws2.cell(row=row + 2, column=col + 2)
                d_cell.value = details

        wb.save(filepath)
        msg = _('Co-occurrence exported: ') + filepath
        Message(self.app, _('Co-occurrence exported'), msg, "information").exec()
        self.parent_textEdit.append(msg)

    def fill_table(self, column_header):
        """ Fill table using code names alphabetically (case insensitive) as rows
        header columns can be files, or ... MORE ?
        using self.data

        args:
            header: List of dictionary containing 'name'
        """

        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        column_header_labels = []
        for item in column_header:
            column_header_labels.append(item['name'])
        self.ui.tableWidget.setColumnCount(len(column_header_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(column_header_labels)
        row_header = []
        for code_ in self.codes:
            row_header.append(code_['name'])
        self.ui.tableWidget.setRowCount(len(row_header))
        self.ui.tableWidget.setVerticalHeaderLabels(row_header)
        for row, row_data in enumerate(self.data_counts):
            for col, cell_data in enumerate(row_data):
                item = QtWidgets.QTableWidgetItem()
                if self.data_colors[row][col] != "":
                    item.setBackground(QtGui.QBrush(QtGui.QColor(self.data_colors[row][col])))
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#000000")))
                if cell_data > 0:
                    item.setData(QtCore.Qt.ItemDataRole.DisplayRole, cell_data)
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, col, item)
        # self.ui.tableWidget.resizeColumnsToContents()  # Doesnt look great
        self.ui.tableWidget.resizeRowsToContents()

    def show_or_hide_empty_rows_and_cols(self):
        """ Unchecked - show all rows and columns.
        Checked - hide rows and columns with no code co-occurrences. """

        if self.ui.checkBox_hide_blanks.isChecked():
            for row, row_data in enumerate(self.data_counts):
                if sum(row_data) == 0:
                    self.ui.tableWidget.hideRow(row)

            for col in range(len(self.data_counts[0])):
                col_sum = 0
                for row, row_data in enumerate(self.data_counts):
                    col_sum += row_data[col]
                if col_sum == 0:
                    self.ui.tableWidget.hideColumn(col)
        if not self.ui.checkBox_hide_blanks.isChecked():
            for row, row_data in enumerate(self.data_counts):
                self.ui.tableWidget.showRow(row)
                self.ui.tableWidget.showColumn(row)

    def cell_selected(self):
        """ When the table widget memo cell is selected display the memo.
        Update memo text, or delete memo by clearing text.
        If a new memo, also show in table widget by displaying MEMO in the memo column.

        Text data keys = 'fid', 'file_or_casename', 'cid', 'codename', 'color', 'pos0', 'pos1', 'ctid', 'text',
                    'memo', 'owner', 'file_or_case', 'result_type'

        """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()
        text = self.ui.tableWidget.item(row, col).text()
        if text == "":
            self.ui.listWidget.clear()
            self.data_list_widget = []
            return
        self.data_list_widget = self.data[row][col]
        self.ui.listWidget.clear()
        for row, data in enumerate(self.data_list_widget):
            print("DATA", data)
            display = f"{data['file_or_casename']} | {data['codename']}\n"
            if data['result_type'] == "text":
                display += f"{data['pos0']} - {data['pos1']}. Coder: {data['owner']}\n"
                display += f"{data['text']}"
            if data['result_type'] == "image":
                display += f"Image X: {data['x1']}, Y: {data['y1']}. Width: {data['width']}, Height: {data['height']}. "
                display += f"Coder: {data['owner']}\nMemo: {data['memo']}"
            if data['result_type'] == "av":
                display += f"A/V: {msecs_to_hours_mins_secs(data['pos0'])} - {msecs_to_hours_mins_secs(data['pos1'])}. Coder: {data['owner']}\n"
                display += f"{data['memo']}"
            list_item = QtWidgets.QListWidgetItem()
            list_item.setText(display)
            self.ui.listWidget.insertItem(row, display)
        self.ui.splitter.setSizes([300, 200])

    def show_list_item(self):
        """  """

        row = self.ui.listWidget.currentIndex().row()
        data = self.data_list_widget[row]
        if data['result_type'] == "text":
            ui = DialogCodeInText(self.app, data)
            ui.exec()
        if data['result_type'] == "image":
            ui = DialogCodeInImage(self.app, data)
            ui.exec()
        if data['result_type'] == "av":
            ui = DialogCodeInAV(self.app, data)
            ui.exec()



    ''' TODO for future expansion maybe.
    def table_menu(self, position):
        """ Context menu for displaying table cell coding details.
        """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()
        text = self.ui.tableWidget.item(row, col).text()
        print(row, col, text)

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_view = menu.addAction(_("View"))'''

    # OLD
    def calculate_relations(self, code_ids_str):
        """ Calculate the relations for selected codes for all coders.
        For codings in code_text only.

        id1, id2, overlapindex, unionindex, distance, whichmin, whichmax, fid
        relation is 1 character: Inclusion, Overlap, Exact, (Proximity - not used)
        owners is a combination of: owner of ctid0 pipe owner of ctid1

        Args:
            code_ids_str (String): comma separated code ids
        """

        selected_relations = ['E', 'I', 'O']
        if self.file_ids_names is None:
            self.file_ids_names = self.app.get_text_filenames()

        # Get codings for each selected text file
        cur = self.app.conn.cursor()
        for fid in self.file_ids_names:
            sql = "select fid, code_text.cid, pos0, pos1, name, ctid,seltext, ifnull(code_text.memo,''), " \
                  "code_text.owner from code_text " \
                  "join code_name on code_name.cid=code_text.cid where fid=? " \
                  "and code_text.cid in (" + code_ids_str + ") order by code_text.cid"
            cur.execute(sql, [fid['id']])
            result = cur.fetchall()
            coded = [row for row in result if row[0] == fid['id']]

            # Look at each code again other codes, when done remove from list of codes
            cid = 1
            pos0 = 2
            pos1 = 3
            name = 4
            ctid = 5
            seltext = 6
            coded_memo = 7
            owner = 8
            while len(coded) > 0:
                c0 = coded.pop()
                for c1 in coded:
                    if c0[cid] != c1[cid]:
                        relation = self.relation(c0, c1)
                        # Add extra details for output
                        relation['c0_name'] = c0[name]
                        relation['c1_name'] = c1[name]
                        relation['fid'] = fid['id']
                        relation['file_name'] = fid['name']
                        relation['c0_pos0'] = c0[pos0]
                        relation['c0_pos1'] = c0[pos1]
                        relation['c1_pos0'] = c1[pos0]
                        relation['c1_pos1'] = c1[pos1]
                        relation['owners'] = f"{c0[owner]}|{c1[owner]}"
                        relation['ctid0'] = c0[ctid]
                        relation['ctid0_text'] = c0[seltext]
                        relation['ctid1'] = c1[ctid]
                        relation['ctid1_text'] = c1[seltext]
                        relation['coded_memo0'] = c0[coded_memo]
                        relation['coded_memo1'] = c1[coded_memo]
                        # Append relation based on comboBox selection
                        if relation['relation'] in selected_relations:
                            self.result_relations.append(relation)

    # OLD
    def relation(self, c0, c1):
        """ Relation function as in RQDA

        whichmin is the code with the lowest pos0, or None if equal
        whichmax is the code with the highest pos1 or None if equal
        operlapindex is the combined lowest to the highest positions. Only used for E, O, P
        unionindex is the lowest and highest positions of the union of overlap. Only used for E, O

        Called by:
            calculate_relations_for_coder_and_selected_codes

        Returns:
        id1, id2, overlapindex, unionindex, distance, whichmin, min, whichmax, max, fid
        relation is 1 character: Inclusion, Overlap, Exact, Proximity
        actual text as before, overlap, after
        """

        # fid = 0
        cid = 1
        pos0 = 2
        pos1 = 3
        result = {"cid0": c0[cid], "cid1": c1[cid], "relation": "", "whichmin": None, "min": 0,
                  "whichmax": None, "max": 0, "overlapindex": None, "unionindex": None, "distance": None,
                  "text_before": "", "text_overlap": "", "text_after": ""}

        cur = self.app.conn.cursor()

        # Which min
        if c0[pos0] < c1[pos0]:
            result['whichmin'] = c0[cid]
            result['min'] = c0[pos0]
        if c1[pos0] < c0[pos0]:
            result['whichmin'] = c1[cid]
            result['min'] = c1[pos0]

        # Which max
        if c0[pos1] > c1[pos1]:
            result['whichmax'] = c0[cid]
            result['max'] = c0[pos1]
        if c1[pos1] > c0[pos1]:
            result['whichmax'] = c1[cid]
            result['max'] = c1[pos1]

        # Check for Exact
        if c0[pos0] == c1[pos0] and c0[pos1] == c1[pos1]:
            result['relation'] = "E"
            result['overlapindex'] = [c0[pos0], c0[pos1]]
            result['unionindex'] = [c0[pos0], c0[pos1]]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c0[pos0] + 1, c0[pos1] - c0[pos0], c0[0]])
            txt = cur.fetchone()
            if txt is not None:
                result['text_overlap'] = txt[0]
                result['text_before'] = ""
                result['text_after'] = ""
                result['distance'] = 0
            return result

        # Check for Proximity
        if c0[pos1] < c1[pos0]:
            result['relation'] = "P"
            result['distance'] = c1[pos0] - c0[pos1]
            result['text_overlap'] = ""
            result['text_before'] = ""
            result['text_after'] = ""
            return result
        if c0[pos0] > c1[pos1]:
            result['relation'] = "P"
            result['distance'] = c0[pos0] - c1[pos1]
            result['text_overlap'] = ""
            result['text_before'] = ""
            result['text_after'] = ""
            return result

        # Check for Inclusion
        # Exact has been resolved above
        # c0 inside c1
        if c0[pos0] >= c1[pos0] and c0[pos1] <= c1[pos1]:
            result['relation'] = "I"
            result['overlapindex'] = [c0[pos0], c0[pos1]]
            result['unionindex'] = [c0[pos0], c0[pos1]]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c0[pos0] + 1, c0[pos1] - c0[pos0], c0[0]])
            txt = cur.fetchone()
            if txt is not None:
                result['text_overlap'] = txt[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c1[pos0] + 1, c0[pos0] - c1[pos0], c0[0]])
            txt_before = cur.fetchone()
            if txt_before is not None:
                result['text_before'] = txt_before[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c0[pos1] + 1, c1[pos1] - c0[pos1], c0[0]])
            txt_after = cur.fetchone()
            if txt_after is not None:
                result['text_after'] = txt_after[0]
            result['distance'] = 0
            return result

        # c1 inside c0
        if c1[pos0] >= c0[pos0] and c1[pos1] <= c0[pos1]:
            result['relation'] = "I"
            result['overlapindex'] = [c1[pos0], c1[pos1]]
            result['unionindex'] = [c1[pos0], c1[pos1]]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c1[pos0] + 1, c1[pos1] - c1[pos0], c0[0]])
            txt = cur.fetchone()
            if txt is not None:
                result['text_overlap'] = txt[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c0[pos0] + 1, c1[pos0] - c0[pos0], c0[0]])
            txt_before = cur.fetchone()
            if txt_before is not None:
                result['text_before'] = txt_before[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c1[pos1] + 1, c0[pos1] - c1[pos1], c0[0]])
            txt_after = cur.fetchone()
            if txt_after is not None:
                result['text_after'] = txt_after[0]
            result['distance'] = 0
            return result

        # Check for Overlap
        # Should be all that is remaining
        # c0 overlaps on the right side, left side is not overlapping
        if c0[pos0] < c1[pos0] and c0[pos1] < c1[pos1]:
            '''print("c0 overlaps on the right side, left side is not overlapping")
            print("c0", c0)
            print("C1", c1)'''
            result['relation'] = "O"
            # Reorder lowest to highest
            result['overlapindex'] = sorted([c0[pos0], c1[pos1]])
            result['unionindex'] = sorted([c0[pos1], c1[pos0]])
            overlap_length = result['unionindex'][1] - result['unionindex'][0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c1[pos0] + 1, overlap_length, c0[0]])
            txt = cur.fetchone()
            if txt is not None:
                result['text_overlap'] = txt[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c0[pos0] + 1, c1[pos0] - c0[pos0], c0[0]])
            txt_before = cur.fetchone()
            if txt_before is not None:
                result['text_before'] = txt_before[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c0[pos1] + 1, c1[pos1] - c0[pos1], c0[0]])
            txt_after = cur.fetchone()
            if txt_after is not None:
                result['text_after'] = txt_after[0]
            result['distance'] = 0
            return result

        # c1 overlaps on the right side, left side is not overlapping
        if c1[pos0] < c0[pos0] and c1[pos1] < c0[pos1]:
            result['relation'] = "O"
            result['overlapindex'] = sorted([c1[pos0], c0[pos1]])
            result['unionindex'] = sorted([c1[pos1], c0[pos0]])
            overlap_length = result['unionindex'][1] - result['unionindex'][0]
            '''print("TODO c1 overlaps on the right, the left side is not overlapping")
            print("C0", c0)
            print("C1", c1)'''
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c0[pos0] + 1, overlap_length, c0[0]])
            txt = cur.fetchone()
            if txt is not None:
                result['text_overlap'] = txt[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c1[pos0] + 1, c0[pos0] - c1[pos0], c0[0]])
            txt_before = cur.fetchone()
            if txt_before is not None:
                result['text_before'] = txt_before[0]
            cur.execute("select substr(fulltext,?,?) from source where source.id=?",
                        [c1[pos1] + 1, c0[pos1] - c1[pos1], c0[0]])
            txt_after = cur.fetchone()
            if txt_after is not None:
                result['text_after'] = txt_after[0]
            result['distance'] = 0
            return result

    # OLD
    def process_data(self):
        """ Calculate the relations for selected codes for ALL coders (or only THIS coder - TODO).
        For text codings only. """

        # OLD
        return

        self.ui.checkBox_hide_blanks.setChecked(False)
        self.ui.splitter.setSizes([500, 0])

        self.result_relations = []
        self.calculate_relations(self.code_ids_str)

        # Create data matrices zeroed, codes are ordered alphabetically by name
        self.data_counts = []
        self.data_colors = []
        self.data_details = []
        for row in self.codes:
            self.data_counts.append([0] * len(self.codes))
            self.data_colors.append([""] * len(self.codes))
            self.data_details.append(["."] * len(self.codes))

        '''print("Data details")
        for r in self.data_details:
            print(r)'''

        self.max_count = 0
        for r in self.result_relations:
            row_pos = self.code_names_list.index(r['c0_name'])
            col_pos = self.code_names_list.index(r['c1_name'])
            self.data_counts[row_pos][col_pos] += 1
            if self.data_counts[row_pos][col_pos] > self.max_count:
                self.max_count = self.data_counts[row_pos][col_pos]
            '''print(r['cid0'], r['c0_name'], r['ctid0'], r['cid1'], r['c1_name'], r['ctid1'], r['fid'], r['file_name'],
                  r['owners'], r['c0_pos0'], r['c0_pos1'], r['c1_pos0'], r['c1_pos1'])'''
            res_list = [r['cid0'], r['c0_name'], r['ctid0'], r['cid1'], r['c1_name'], r['ctid1'], r['fid'],
                        r['file_name'], r['owners'], r['c0_pos0'], r['c0_pos1'], r['c1_pos0'], r['c1_pos1'],
                        r['text_before'], r['text_overlap'], r['text_after'], r['relation']]
            if self.data_details[row_pos][col_pos] == ".":
                self.data_details[row_pos][col_pos] = [res_list]
            else:
                self.data_details[row_pos][col_pos].append(res_list)

        # Color heat map for spread across 5 colours
        colors = ["#F8E0E0", "#F6CECE", "#F5A9A9", "#F78181", "#FA5858"]  # light to dark red
        for row, row_data in enumerate(self.data_counts):
            for col, item_data in enumerate(row_data):
                if self.data_counts[row][col] > 0:
                    color_range_index = int(self.data_counts[row][col] / self.max_count * 5) - 1
                    if color_range_index < 0:
                        color_range_index = 0
                    self.data_colors[row][col] = colors[color_range_index]

        self.fill_table()
