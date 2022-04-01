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

from copy import copy
import csv
import logging
import os
import sys
import traceback

from PyQt6 import QtGui, QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush

from .color_selector import TextColor
from .GUI.base64_helper import *
from .GUI.ui_dialog_code_relations import Ui_Dialog_CodeRelations
from .helpers import DialogCodeInText, ExportDirectoryPathDialog, Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    txt = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(txt)
    logger.error(_("Uncaught exception: ") + txt)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), txt)


class DialogReportRelations(QtWidgets.QDialog):
    """ Show code relations/crossovers for one coder.
    This is for text only. """

    app = None
    parent_textEdit = None
    coder_names = []
    categories = []
    codes = []
    result_relations = []

    def __init__(self, app, parent_textedit):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textedit
        self.get_code_data()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_CodeRelations()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        try:
            s0 = int(self.app.settings['dialogcodecrossovers_splitter0'])
            s1 = int(self.app.settings['dialogcodecrossovers_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except KeyError:
            pass
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(font)
        self.ui.label_codes.setStyleSheet(font)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.ExtendedSelection)
        self.fill_tree()
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_csv_icon), "png")
        self.ui.pushButton_exportcsv.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_exportcsv.pressed.connect(self.export_csv_file)
        self.ui.pushButton_calculate.pressed.connect(self.coder_code_relations)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_calculate.setIcon(QtGui.QIcon(pm))
        self.ui.tableWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)

    def get_code_data(self):
        """ Called from init. gets code_names, categories and owner names.
        """

        self.coder_names = self.app.get_coder_names_in_project()
        self.codes, self.categories = self.app.get_codes_categories()

    def coder_code_relations(self):
        """ Calculate the relations for selected codes for THIS coder or ALL coders.
        For codings in code_text only. """

        sel_codes = []
        codes_str = ""
        code_ids = ""
        items = self.ui.treeWidget.selectedItems()
        for i in items:
            if i.text(1)[:3] == "cid":
                sel_codes.append({"name": i.text(0), "cid": int(i.text(1)[4:])})
                codes_str += i.text(0) + "|"
                code_ids += "," + i.text(1)[4:]
        if len(sel_codes) < 2:
            msg = _("Select 2 or more codes\nUse Ctrl or Shift and mouse click")
            Message(self.app, _('Selection warning'), msg, "warning").exec()
            return
        code_ids = code_ids[1:]
        self.ui.label_codes.setText(_("Codes: ") + codes_str)
        self.result_relations = []
        if self.ui.radioButton_this.isChecked():
            self.calculate_relations_for_coder(self.app.settings['codername'], code_ids)
        else:
            for coder_name in self.coder_names:
                self.calculate_relations_for_coder(coder_name, code_ids)
        self.display_relations()

    def calculate_relations_for_coder(self, coder_name, code_ids):
        """ Calculate the relations for selected codes for selected coder.
        For codings in code_text only.

        id1, id2, overlapindex, unionindex, distance, whichmin, whichmax, fid
        relation is 1 character: Inclusion, Overlap, Exact, Proximity
        """

        cur = self.app.conn.cursor()
        sql = "select distinct fid from code_text where owner=? and code_text.cid in (" + code_ids + ") \
            order by fid"
        cur.execute(sql, [coder_name, ])
        result = cur.fetchall()
        file_ids = []
        file_ids_str = ""
        for r in result:
            file_ids.append(r[0])
            file_ids_str += "," + str(r[0])
        if not file_ids:
            return

        # To add file names to relation result - makes easier for diplaying results
        file_ids_str = file_ids_str[1:]
        sql = "select distinct id, name from source where id in (" + file_ids_str + ")"
        cur.execute(sql)
        file_id_names = cur.fetchall()

        # Look at each text file separately,
        for fid in file_ids:
            filename = ""
            for f in file_id_names:
                if f[0] == fid:
                    filename = f[1]

            sql = "select fid, code_text.cid, pos0, pos1, name from code_text join code_name on \
             code_name.cid=code_text.cid where code_text.owner=? and fid=? \
             and code_text.cid in (" + code_ids + ") \
            order by code_text.cid"
            cur.execute(sql, [coder_name, fid])
            result = cur.fetchall()
            coded = []
            for row in result:
                if row[0] in file_ids or file_ids == []:
                    coded.append(row)

            # TODO later, find the closest Other code for relation analysis

            # Look at each code again other codes, when done remove from list of codes
            cid = 1
            pos0 = 2
            pos1 = 3
            name = 4
            while len(coded) > 0:
                c0 = coded.pop()
                for c1 in coded:
                    if c0[cid] != c1[cid]:
                        relation = self.relation(c0, c1)
                        # Add extra details for output
                        relation['c0_name'] = c0[name]
                        relation['c1_name'] = c1[name]
                        relation['fid'] = fid
                        relation['file_name'] = filename
                        relation['c0_pos0'] = c0[pos0]
                        relation['c0_pos1'] = c0[pos1]
                        relation['c1_pos0'] = c1[pos0]
                        relation['c1_pos1'] = c1[pos1]
                        relation['owner'] = coder_name
                        self.result_relations.append(relation)
        self.display_relations()

    def closest_relation(self, c0, c1):
        # TODO later
        pass

    def relation(self, c0, c1):
        """ Relation function as in RQDA

        whichmin is the code with the lowest pos0, or None if equal
        whichmax is the code with the highest pos1 or None if equal
        operlapindex is the combined lowest to highest positions. Only used for E, O, P
        unionindex is the lowest and highest positions of the union of overlap. Only used for E, O

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
            return result

    def table_menu(self, position):
        """ Context menu to show row text in original context. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        try:
            row = self.ui.tableWidget.currentRow()
        except AttributeError:
            # No table for table menu
            return
        action_show_context = menu.addAction(_("View in context"))
        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action == action_show_context:
            self.show_context()

    def show_context(self):
        """ Show context of coding in dialog.
        Called by table_menu.
        """

        row = self.ui.tableWidget.currentRow()
        d = self.result_relations[row]
        codename0 = ""
        codename1 = ""
        color0 = ""
        color1 = ""
        for c in self.codes:
            if c['cid'] == d['cid0']:
                codename0 = c['name']
                color0 = c['color']
            if c['cid'] == d['cid1']:
                codename1 = c['name']
                color1 = c['color']
        # data: dictionary: codename, color, file_or_casename, pos0, pos1, text, coder, fid, file_or_case,
        # textedit_start, textedit_end
        data0 = {'codename': codename0, 'color': color0, 'file_or_casename': d['file_name'],
                 'pos0': d['c0_pos0'], 'pos1': d['c0_pos1'],
                 'text': '', 'coder': d['owner'], 'fid': d['fid'], 'file_or_case': 'File'}
        data1 = {'codename': codename1, 'color': color1, 'file_or_casename': d['file_name'],
                 'pos0': d['c1_pos0'], 'pos1': d['c1_pos1'],
                 'text': '', 'coder': d['owner'], 'fid': d['fid'], 'file_or_case': 'File'}
        ui = DialogCodeInText(self.app, data0)
        ui.add_coded_text(data1)
        ui.exec()
        return

    def display_relations(self):
        """ A table of:
        Tooltips with codenames on id1,id2, relation,fid - to minimise screen use
        id1, id2, overlapindex, unionindex, distance, whichmin, whichmax, fid
        relation is: inclusion, overlap, exact, proximity
        """

        fid = 0
        code0 = 1
        code1 = 2
        relation_type = 3
        min_ = 4
        max_ = 5
        overlap0 = 6
        overlap1 = 7
        union0 = 8
        union1 = 9
        distance = 10
        text_before = 11
        text_overlap = 12
        text_after = 13
        owner = 14
        col_names = ["FID", _("Code") + " 0", _("Code") + " 1", "Rel", "Min", "Max", _("Overlap") + " 0",
                     _("Overlap") + " 1",
                     _("Union") + " 0", _("Union") + " 1",
                     _("Distance"), _("Text before"), _("Overlap"), _("Text after"), _("Owner")]
        self.ui.tableWidget.setColumnCount(len(col_names))
        self.ui.tableWidget.setHorizontalHeaderLabels(col_names)
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        for r, i in enumerate(self.result_relations):
            self.ui.tableWidget.insertRow(r)
            item = QtWidgets.QTableWidgetItem(str(i['fid']))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(i['file_name'])
            self.ui.tableWidget.setItem(r, fid, item)
            item = QtWidgets.QTableWidgetItem(str(i['cid0']))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(i['c0_name'] + "\n" + str(i['c0_pos0']) + " - " + str(i['c0_pos1']))
            self.ui.tableWidget.setItem(r, code0, item)
            item = QtWidgets.QTableWidgetItem(str(i['cid1']))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(i['c1_name'] + "\n" + str(i['c1_pos0']) + " - " + str(i['c1_pos1']))
            self.ui.tableWidget.setItem(r, code1, item)
            item = QtWidgets.QTableWidgetItem(str(i['relation']))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            ttip = _("Proximity")
            if i['relation'] == "O":
                ttip = _("Overlap")
            if i['relation'] == "E":
                ttip = _("Exact")
            if i['relation'] == "I":
                ttip = _("Inclusion")
            item.setToolTip(ttip)
            self.ui.tableWidget.setItem(r, relation_type, item)
            item = QtWidgets.QTableWidgetItem(str(i['whichmin']).replace("None", ""))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            if i['whichmin'] is not None:
                ttip = i['c0_name']
                if i['whichmin'] == i['cid1']:
                    ttip = i['c1_name']
                item.setToolTip(ttip)
            self.ui.tableWidget.setItem(r, min_, item)

            item = QtWidgets.QTableWidgetItem(str(i['whichmax']).replace("None", ""))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            if i['whichmax'] is not None:
                ttip = i['c0_name']
                if i['whichmax'] == i['cid1']:
                    ttip = i['c1_name']
                item.setToolTip(ttip)
            self.ui.tableWidget.setItem(r, max_, item)
            if i['overlapindex'] is not None:
                item = QtWidgets.QTableWidgetItem(str(i['overlapindex'][0]))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(r, overlap0, item)
                item = QtWidgets.QTableWidgetItem(str(i['overlapindex'][1]))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(r, overlap1, item)
            if i['unionindex'] is not None:
                item = QtWidgets.QTableWidgetItem(str(i['unionindex'][0]))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(r, union0, item)
                item = QtWidgets.QTableWidgetItem(str(i['unionindex'][1]))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(r, union1, item)
            item = QtWidgets.QTableWidgetItem(str(i['distance']).replace("None", ""))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(r, distance, item)
            item = QtWidgets.QTableWidgetItem(str(i['owner']))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(r, owner, item)
            item = QtWidgets.QTableWidgetItem(i['text_before'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(r, text_before, item)
            item = QtWidgets.QTableWidgetItem(i['text_overlap'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(r, text_overlap, item)
            item = QtWidgets.QTableWidgetItem(i['text_after'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(r, text_after, item)
        self.ui.tableWidget.resizeColumnsToContents()

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        """

        self.ui.treeWidget.clear()

        cats = copy(self.categories)
        codes = copy(self.codes)
        self.ui.treeWidget.clear()
        header = [_("Code Tree"), _("Id")]
        self.ui.treeWidget.setColumnCount(len(header))
        self.ui.treeWidget.setHeaderLabels(header)
        '''if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)'''
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid'])])  # check this
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            # try:
            cats.remove(item)
            # except Exception as e:
            #    logger.debug(str(e) + " item:" + str(item))

        ''' Add child categories. Look at each unmatched category, iterate through tree to
        add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    # logger.debug("While: ", item.text(0), item.text(1), c['catid'], c['supercatid'])
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid'])])
                        item.addChild(child)
                        # logger.debug("Adding: " + c['name'])
                        remove_list.append(c)
                    it += 1
                    item = it.value()
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid'])])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                if item.text(1) == 'catid:' + str(c['catid']):
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid'])])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()

    def export_csv_file(self):
        """ Export data as csv, called projectname_relations.csv.
        The csv is comma delimited and all fields quoted. """

        if not self.result_relations:
            return

        shortname = self.app.project_name.split(".qda")[0]
        filename = shortname + "_relations.csv"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        col_names = ["Fid", _("Filename"), "Code0", "Code0 " + _("name"), "Code0_pos0", "Code0_pos1",
                     "Code1", "Code1 " + _("name"),
                     "Code1_pos0", "Code1_pos1", _("Relation"), _("Minimum"), _("Maximum"),
                     _("Overlap") + " 0", _("Overlap") + " 1", _("Union") + " 0",
                     _("Union") + " 1", _("Distance"), _("Text before"), _("Text overlap"), _("Text after"), _("Owner")]
        with open(filepath, 'w', encoding='UTF8') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(col_names)
            for r in self.result_relations:
                row = [r['fid'], r['file_name'], r['cid0'], r['c0_name'], r['c0_pos0'], r['c0_pos1'], r['cid1'],
                       r['c1_name'], r['c1_pos0'], r['c1_pos1'], r['relation'], str(r['whichmin']).replace('None', ''),
                       str(r['whichmax']).replace('None', '')]
                if r['overlapindex']:
                    row.append(r['overlapindex'][0])
                    row.append(r['overlapindex'][1])
                else:
                    row.append('')
                    row.append('')
                if r['unionindex']:
                    row.append(r['unionindex'][0])
                    row.append(r['unionindex'][1])
                else:
                    row.append('')
                    row.append('')
                row.append(str(r['distance']).replace('None', ''))
                row.append(r['text_before'])
                row.append(r['text_overlap'])
                row.append(r['text_after'])
                row.append(r['owner'])
                writer.writerow(row)

        msg = _("Code relations csv file exported to: ") + filepath
        Message(self.app, _('Csv file Export'), msg, "information").exec()
        self.parent_textEdit.append(msg)

    def closeEvent(self, event):
        """ Save splitter dimensions. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodecrossovers_splitter0'] = sizes[0]
        self.app.settings['dialogcodecrossovers_splitter1'] = sizes[1]
