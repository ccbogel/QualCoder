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

import logging
import os
import qtawesome as qta

from PyQt6 import QtCore, QtWidgets

from .GUI.ui_dialog_cooccurrence import Ui_Dialog_Coocurrence
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogReportCooccurrence(QtWidgets.QDialog):
    """ Provide a co-occurrence report.
    """

    app = None
    parent_tetEdit = None
    files = []

    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_textEdit = parent_text_edit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_Coocurrence()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_run.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_run.pressed.connect(self.process_data)
        #docfont = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        #self.ui.textEdit.setStyleSheet(docfont)
        treefont = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        tablefont = f'font: 7pt "{self.app.settings["font"]}";'
        self.ui.tableWidget.setStyleSheet(tablefont)  # should be smaller

        Message(self.app, "Co-occurrence", "Work in progress").exec()
        self.codes = []
        self.categories = []

    def process_data(self):
        """ Calculate the relations for selected codes for ALL coders (or THIS coder - TODO).
        For text codings only. """

        code_names_str = ""
        code_ids_str = ""

        self.codes, self.categories = self.app.get_codes_categories()
        code_names_list = []
        for c in self.codes:
            code_names_list.append(c['name'])
            code_names_str += f"{c['name']}|"
            code_ids_str += f",{c['cid']}"
        code_ids_str = code_ids_str[1:]
        self.result_relations = []
        self.calculate_relations(code_ids_str)
        for r in self.result_relations:
            #print(r)
            print(r['cid0'], r['c0_name'], r['ctid0'], r['cid1'], r['c1_name'], r['ctid1'], r['fid'], r['file_name'])

        # Create data matrix zeroed, codes are ordered alphabetically by name
        self.data = []
        for row in self.codes:
            self.data.append([0] * len(self.codes))

        for r in self.result_relations:
            row_pos = code_names_list.index(r['c0_name'])
            col_pos = code_names_list.index(r['c1_name'])
            self.data[row_pos][col_pos] += 1


        for d in self.data:
            print(d)

        self.fill_table()

    def fill_table(self):
        """ Fill table using code names alphabetically (case insensitive), using self.data """

        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)

        header_labels = []
        for code_ in self.codes:
            header_labels.append(code_['name'])
        self.ui.tableWidget.setColumnCount(len(header_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(header_labels)
        self.ui.tableWidget.setRowCount(len(header_labels))
        self.ui.tableWidget.setVerticalHeaderLabels(header_labels)
        for row, row_data in enumerate(self.data):
            for col, cell_data in enumerate(row_data):
                item = QtWidgets.QTableWidgetItem()
                #if cell_data > 0:
                item.setData(QtCore.Qt.ItemDataRole.DisplayRole, cell_data)
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, col, item)



    def calculate_relations(self, code_ids_str):
        """ Calculate the relations for selected codes for all coders.
        For codings in code_text only.

        id1, id2, overlapindex, unionindex, distance, whichmin, whichmax, fid
        relation is 1 character: Inclusion, Overlap, Exact, (Proximity - not used)
        """

        selected_relations = ['E', 'I', 'O']

        # Select File ids
        selected_fids = ""
        file_ids_names = self.app.get_text_filenames()

        '''for f in file_ids_names:
            selected_fids += f",{f['id']}"
        try:
            selected_fids = selected_fids[1:]
        except IndexError:
            return'''

        cur = self.app.conn.cursor()
        # Get codings for each selected text file
        for fid in file_ids_names:
            sql = "select fid, code_text.cid, pos0, pos1, name, ctid,seltext, ifnull(code_text.memo,'') from code_text " \
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
                        relation['owner'] = "TODO"  # coder_name
                        relation['ctid0'] = c0[ctid]
                        relation['ctid0_text'] = c0[seltext]
                        relation['ctid1'] = c1[ctid]
                        relation['ctid1_text'] = c1[seltext]
                        relation['coded_memo0'] = c0[coded_memo]
                        relation['coded_memo1'] = c1[coded_memo]
                        # Append relation based on comboBox selection
                        if relation['relation'] in selected_relations:
                            self.result_relations.append(relation)

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