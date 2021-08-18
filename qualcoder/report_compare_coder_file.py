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

from copy import copy
import csv
import datetime
import logging
import os
import platform
from shutil import copyfile
import sys
import traceback

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.Qt import QHelpEvent
from PyQt5.QtCore import Qt, QTextCodec
from PyQt5.QtGui import QBrush

import qualcoder.vlc as vlc
from .color_selector import TextColor
from .GUI.base64_helper import *
from .GUI.ui_dialog_report_compare_coder_file import Ui_Dialog_reportCompareCoderFile
from .helpers import Message, msecs_to_mins_and_secs, DialogCodeInImage, DialogCodeInAV, DialogCodeInText, ExportDirectoryPathDialog

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


class DialogCompareCoderByFile(QtWidgets.QDialog):
    """ Compare two coders for:
    Coded text sequences for one code and one text file. Apply Cohen's Kappa for text files.
    Coded image areas for one code and one text file.

    Used to help advise coders / second coder on howto improve accuracy of coding.
    """

    app = None
    parent_textEdit = None
    coders = []
    selected_coders = []
    categories = []
    code_ = None  # Selected code
    file_ = None  # Selected file
    files = []
    codes = []
    comparisons = ""

    def __init__(self, app, parent_textEdit):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.comparisons = ""
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_reportCompareCoderFile()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.get_data()
        self.ui.pushButton_run.setEnabled(False)
        self.ui.pushButton_run.pressed.connect(self.results)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_run.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_clear.pressed.connect(self.clear_selection)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(clear_icon), "png")
        self.ui.pushButton_clear.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_exporttext.pressed.connect(self.export_text_file)
        # TODO temoprarioly hide this button
        self.ui.pushButton_exporttext.hide(True)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_exporttext.setIcon(QtGui.QIcon(pm))
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(font)
        self.ui.listWidget_files.setStyleSheet(font)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SingleSelection)
        self.ui.comboBox_coders.insertItems(0, self.coders)
        self.ui.comboBox_coders.currentTextChanged.connect(self.coder_selected)
        self.fill_tree()
        self.ui.treeWidget.itemSelectionChanged.connect(self.code_selected)
        self.ui.listWidget_files.itemClicked.connect(self.file_selected)

    def get_data(self):
        """ Called from init. gets coders, code_names, categories, files.
        Images are not loaded. """

        self.codes, self.categories = self.app.get_codes_categories()
        cur = self.app.conn.cursor()
        sql = "select owner from  code_image union select owner from code_text union select owner from code_av"
        cur.execute(sql)
        result = cur.fetchall()
        self.coders = [""]
        for row in result:
            self.coders.append(row[0])
        self.get_files()

    def get_files(self):
        """ Get source files with additional details and fill list widget.
        Add file type to dictionarty for each file.
        """

        self.ui.listWidget_files.clear()
        self.files = self.app.get_filenames()
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), mediapath from source where id=?"
        sql_text_codings = "select count(cid) from code_text where fid=?"
        sql_av_codings = "select count(cid) from code_av where id=?"
        sql_image_codings = "select count(cid) from code_image where id=?"
        for f in self.files:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # safety catch
                res = [0]
            tt = ""
            if res[1] is None or res[1][0:5] == "docs:":
                tt += _("Text file\n")
                tt += _("Characters: ") + str(res[0])
                f['type'] = 'text'
            if res[1] is not None and (res[1][0:7] == "images:" or res[1][0:7] == "/images"):
                tt += _("Image")
                f['type'] = 'image'
            if res[1] is not None and (res[1][0:6] == "audio:" or res[1][0:6] == "/audio"):
                tt += _("Audio")
                f['type'] = 'audio'
            if res[1] is not None and (res[1][0:6] == "video:" or res[1][0:6] == "/video"):
                tt += _("Video")
                f['type'] = 'video'
            cur.execute(sql_text_codings, [f['id']])
            txt_res = cur.fetchone()
            cur.execute(sql_av_codings, [f['id']])
            av_res = cur.fetchone()
            cur.execute(sql_image_codings, [f['id']])
            img_res = cur.fetchone()
            tt += _("\nCodings: ")
            if txt_res[0] > 0:
                tt += str(txt_res[0])
            if av_res[0] > 0:
                tt += str(av_res[0])
            if img_res[0] > 0:
                tt += str(img_res[0])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] is not None and f['memo'] != "":
                tt += _("\nMemo: ") + f['memo']
            item.setToolTip(tt)
            self.ui.listWidget_files.addItem(item)

    def coder_selected(self):
        """ Select coders for comparison - only two coders can be selected. """

        coder = self.ui.comboBox_coders.currentText()
        if coder == "":
            return
        if len(self.selected_coders) == 0:
            self.selected_coders.append(coder)
            self.ui.label_selections.setText(coder)
        if len(self.selected_coders) == 1 and self.selected_coders[0] != coder:
            self.selected_coders.append(coder)
            coder1 = self.ui.label_selections.text()
            self.ui.label_selections.setText(coder1 + " , " + coder)
        if len(self.selected_coders) == 2 and self.file_ is not None and self.code_ is not None:
            self.ui.pushButton_run.setEnabled(True)

    def file_selected(self):
        """ May activate run button if file, code and coders selected """

        itemname = self.ui.listWidget_files.currentItem().text()
        for f in self.files:
            if f['name'] == itemname:
                self.file_ = f
        if len(self.selected_coders) == 2 and self.file_ is not None and self.code_ is not None:
            self.ui.pushButton_run.setEnabled(True)

    def code_selected(self):
        """ May activate run button if file, code and coders selected """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] != 'cid':
            return
        code_= None
        for c in self.codes:
            if c['name'] == current.text(0):
                self.code_ = c
        if self.code_ is None:
            return
        if len(self.selected_coders) == 2 and self.file_ is not None and self.code_ is not None:
            self.ui.pushButton_run.setEnabled(True)

    def clear_selection(self):
        """ Clear the coder selection and tree widget statistics. """

        self.selected_coders = []
        self.ui.pushButton_run.setEnabled(False)
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:  # while there is an item in the list
            if item.text(1)[0:4] == 'cid:':
                item.setText(2, "")
                item.setText(3, "")
                item.setText(4, "")
                item.setText(5, "")
                item.setText(6, "")
            it += 1
            item = it.value()
        self.ui.label_selections.setText(_("No coders selected"))

    def export_text_file(self):
        """ Export coding comparison statistics to text file. """

        filename = "Coder_comparison.txt"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        f = open(filepath, 'w', encoding="'utf-8-sig'")
        f.write(self.app.project_name + "\n")
        f.write(_("Date: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        f.write(self.comparisons)
        f.close()
        msg = _("Coder comparison text file exported to: ") + filepath
        Message(self.app, _('Text file export'), msg, "information").exec_()
        self.parent_textEdit.append(msg)

    def results(self):
        """ Iterate through tree widget, for all cids
        For each code_name calculate the two-coder comparison statistics.

        {'id': 7, 'name': 'Brighton_Storm.mp4.transcribed', 'memo': 'A transcription of the Optus video'}
        {'name': 'enthusiastic', 'memo': 'very entuistic suggeses', 'owner': 'colin', 'date': '2019-08-05 08:20:48', 'cid': 12, 'catid': -1, 'color': '#F781F3'}
        ['colin', 'jemima']
        """

        #TMP
        print(self.file_)
        print(self.code_)
        print(self.selected_coders)

        txt = _("CODER COMPARISON FOR FILE") + "\n====\n" + _("CODERS: ")
        c1_pos0 = len(txt)
        txt += self.selected_coders[0] + " " + _("(YELLOW)")
        c1_pos1 = len(txt)
        txt += ", " + self.selected_coders[1] + " " + _("(BLUE)") + "\n"
        c2_pos1 = len(txt)
        txt += _("FILE: ") + self.file_['name'] + "\n"
        txt += _("CODE: ") + self.code_['name'] + "\n"
        self.ui.textEdit.setText(txt)
        # Format the first coder color, yellow
        cursor = self.ui.textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        cursor.setPosition(c1_pos0, QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(c1_pos1, QtGui.QTextCursor.KeepAnchor)
        color = "#F4FA58"
        brush = QBrush(QtGui.QColor(color))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)
        # Format the second coder color, blue
        cursor.setPosition(c1_pos1, QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(c2_pos1, QtGui.QTextCursor.KeepAnchor)
        color = "#81BEF7"
        brush = QBrush(QtGui.QColor(color))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)

        if self.file_['type'] == 'text':
            self.ui.textEdit.append(self.agreement_text_file())
        if self.file_['type'] == 'image':
            self.ui.textEdit.append(self.agreement_image_file())

    def agreement_image_file(self):
        """ Calculate the two-coder statistics for this code_
        Percentage agreement, disgreement and kappa.
        Get the start and end positions in all files (source table) for this cid
        Look at each file separately to ge the commonly coded text.
        Each character that is coded by coder 1 or coder 2 is incremented, resulting in a list of 0, 1, 2
        where 0 is no codings at all, 1 is coded by only one coder and 2 is coded by both coders.
        'Disagree%':'','A not B':'','B not A':'','K':''
        """

        cid = self.code_['cid']
        # coded0 and coded1 are the total pixels coded by coder 0 and coder 1
        total = {'dual_coded': 0, 'single_coded': 0, 'uncoded': 0, 'pixels': 0, 'coded0': 0, 'coded1': 0}
        cur = self.app.conn.cursor()
        print("Image agreement")

    def agreement_text_file(self):
        """ Calculate the two-coder statistics for this code_
        Percentage agreement, disgreement and kappa.
        Get the start and end positions in all files (source table) for this cid
        Look at each file separately to ge the commonly coded text.
        Each character that is coded by coder 1 or coder 2 is incremented, resulting in a list of 0, 1, 2
        where 0 is no codings at all, 1 is coded by only one coder and 2 is coded by both coders.
        'Disagree%':'','A not B':'','B not A':'','K':''
        """

        cid = self.code_['cid']
        # coded0 and coded1 are the total characters coded by coder 0 and coder 1
        total = {'dual_coded': 0, 'single_coded': 0, 'uncoded': 0, 'characters': 0, 'coded0': 0, 'coded1': 0}
        cur = self.app.conn.cursor()
        sql = "select fulltext from source where id=?"
        cur.execute(sql, [self.file_['id']])
        fulltext = cur.fetchone()
        if fulltext[0] is None or fulltext[0] == "":
            return None
        sql = "select pos0,pos1,fid from code_text where fid=? and cid=? and owner=?"
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[0]])
        res0 = cur.fetchall()
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[1]])
        res1 = cur.fetchall()
        # Determine the same characters coded by both coders, by adding 1 to each coded character
        char_list = [0] * len(fulltext[0])
        # List of which coders coded this char: 1 = coder 1, 2= coder2, 12 = coders 1 and 2
        char_list_coders = [''] * len(fulltext[0])
        for coded in res0:
            #print(coded[0], coded[1])  # tmp
            for char in range(coded[0], coded[1]):
                char_list[char] += 1
                total['coded0'] += 1
                char_list_coders[char] = 'y'
        for coded in res1:
            for char in range(coded[0], coded[1]):
                char_list[char] += 1
                total['coded1'] += 1
                if char_list_coders[char] == 'y':
                    char_list_coders[char] = 'g'
                else:
                    char_list_coders[char] = 'b'
        uncoded = 0
        single_coded = 0
        dual_coded = 0
        for char in char_list:
            if char == 0:
                uncoded += 1
            if char == 1:
                single_coded += 1
            if char == 2:
                dual_coded += 1
        #logger.debug("file:" + f[0] + " dual:" + str(dual_coded) + " single:" + str(single_coded) + " uncoded:" + str(uncoded))
        total['dual_coded'] += dual_coded
        total['single_coded'] += single_coded
        total['uncoded'] += uncoded
        total['characters'] += len(fulltext[0])

        total['agreement'] = round(100 * (total['dual_coded'] + total['uncoded']) / total['characters'], 2)
        total['dual_percent'] = round(100 * total['dual_coded'] / total['characters'], 2)
        total['uncoded_percent'] = round(100 * total['uncoded'] / total['characters'], 2)
        total['disagreement'] = round(100 - total['agreement'], 2)
        # Cohen's Kappa
        '''
        https://en.wikipedia.org/wiki/Cohen%27s_kappa

        k = Po - Pe     Po is proportionate agreement (both coders coded this text / all coded text))
            -------     Pe is probability of random agreement
            1  - Pe

            Pe = Pyes + Pno
            Pyes = proportion Yes by A multiplied by proportion Yes by B
                 = total['coded0']/total_coded * total['coded1]/total_coded

            Pno = proportion No by A multiplied by proportion No by B
                = (total_coded - total['coded0']) / total_coded * (total_coded - total['coded1]) / total_coded

        IMMEDIATE BELOW IS INCORRECT - RESULTS IN THE TOTAL AGREEMENT SCORE
        Po = total['agreement'] / 100
        Pyes = total['coded0'] / total['characters'] * total['coded1'] / total['characters']
        Pno = (total['characters'] - total['coded0']) / total['characters'] * (total['characters'] - total['coded1']) / total['characters']

        BELOW IS BETTER - ONLY LOOKS AT PROPORTIONS OF CODED CHARACTERS
        NEED TO CONFIRM THIS IS THE CORRECT APPROACH
        '''
        total['kappa'] = "zerodiv"
        try:
            unique_codings = total['coded0'] + total['coded1'] - total['dual_coded']
            Po = total['dual_coded'] / unique_codings
            Pyes = total['coded0'] / unique_codings * total['coded1'] / unique_codings
            Pno = (unique_codings - total['coded0']) / unique_codings * (unique_codings - total['coded1']) / unique_codings
            Pe = Pyes * Pno
            kappa = round((Po - Pe) / (1 - Pe), 4)
            total['kappa'] = kappa
        except ZeroDivisionError:
            msg = _("ZeroDivisionError. unique_codings:") + str(unique_codings)
            logger.debug(msg)

        overall = "\nOVERALL SUMMARY\n"
        overall += _("Total characters: ") + str(total['characters']) + ", "
        overall += _("Dual coded: ") + str(total['dual_coded']) + ", "
        overall += _("Single coded: ") + str(total['single_coded']) + ", "
        overall += _("Uncoded: ") + str(total['uncoded']) + ", "
        overall += _("Coder 0: ") + str(total['coded0']) + ", "
        overall += _("Coder 1: ") + str(total['coded1']) + "\n"
        overall += _("Agreement between coders: ") + str(total['agreement']) + "%\n"
        overall += _("Total text dual coded: ") + str(total['dual_percent']) + "%, "
        overall += _("Total text uncoded: ") + str(total['uncoded_percent']) + "%, "
        overall += _("Total text disagreement (single coded): ") + str(total['disagreement']) + "%\n"
        overall += _("Kappa: ") + str(total['kappa']) + "\n\n"
        overall += "FULLTEXT"
        self.ui.textEdit.append(overall)

        cursor = self.ui.textEdit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        pos = cursor.position()
        self.ui.textEdit.append(fulltext[0])
        # Apply brush, yellow for coder 1, blue for coder 2 and green for dual coded
        #print("\nCHARLIST CODERS\n", char_list_coders)  # tmp
        cursor = self.ui.textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        # Foreground depends on the defined need_white_text color in color_selector
        for i, c in enumerate(char_list_coders):
            if c == 'b':
                cursor.setPosition(pos + i, QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(pos + i + 1, QtGui.QTextCursor.KeepAnchor)
                color = "#81BEF7"
                brush = QBrush(QtGui.QColor(color))
                fmt.setBackground(brush)
                text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                cursor.setCharFormat(fmt)
            if c == 'g':
                cursor.setPosition(pos + i, QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(pos + i + 1, QtGui.QTextCursor.KeepAnchor)
                color = "#81F781"
                brush = QBrush(QtGui.QColor(color))
                fmt.setBackground(brush)
                text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                cursor.setCharFormat(fmt)
            if c == 'y':
                cursor.setPosition(pos + i, QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(pos + i + 1, QtGui.QTextCursor.KeepAnchor)
                color = "#F4FA58"
                brush = QBrush(QtGui.QColor(color))
                fmt.setBackground(brush)
                text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                cursor.setCharFormat(fmt)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = copy(self.categories)
        codes = copy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(2)
        self.ui.treeWidget.setHeaderLabels([_("Code Tree"), "Id"])
        self.ui.treeWidget.hideColumn(1)
        if self.app.settings['showids'] == 'True':
            self.ui.treeWidget.showColumn(1)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']) ])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            #try:
            cats.remove(item)
            #except Exception as e:
            #    logger.debug(str(e) + " item:" + str(item))

        ''' Add child categories. Look at each unmatched category, iterate through tree to
        add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            #logger.debug("cats:" + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    #logger.debug("While: ", item.text(0), item.text(1), c['catid'], c['supercatid'])
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']) ])
                        item.addChild(child)
                        #logger.debug("Adding: " + c['name'])
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
                #logger.debug("c[catid] is None: new top item c[name]:" + c['name'])
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']) ])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                #logger.debug("for c in codes, item:" + item.text(0) +"|" + item.text(1) + ", c[cid]:" + str(c['cid']) +", c[catid]:" + str(c['catid']))
                if item.text(1) == 'catid:' + str(c['catid']):
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']) ])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()

