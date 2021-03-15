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

from copy import deepcopy
#import datetime
import logging
import os
from PIL import Image
#import platform
import sys
import traceback
import vlc

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from GUI.ui_dialog_report_code_summary import Ui_Dialog_code_summary


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception:") + "\n" + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogReportCodeSummary(QtWidgets.QDialog):
    """ Provide a summary report for selected code.
    """

    app = None
    parent_tetEdit = None
    categories = []
    codes = []
    #files = []

    def __init__(self, app, parent_textEdit):
        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_summary()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        docfont = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        docfont += '"' + self.app.settings['font'] + '";'
        self.ui.textEdit.setStyleSheet(docfont)
        treefont = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        treefont += '"' + self.app.settings['font'] + '";'
        try:
            s0 = int(self.app.settings['dialogreport_code_summary_splitter0'])
            s1 = int(self.app.settings['dialogreport_code_summary_splitter1'])
            self.ui.splitter.setSizes([s0, s1])
        except:
            pass
        self.ui.splitter.splitterMoved.connect(self.splitter_sizes)
        self.ui.treeWidget.setStyleSheet(treefont)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.fill_tree()
        self.ui.treeWidget.itemClicked.connect(self.fill_text_edit)

    def splitter_sizes(self, pos, index):
        """ Detect size changes in splitter and store in app.settings variable. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogreport_code_summary_splitter0'] = sizes[0]
        self.app.settings['dialogreport_code_summary_splitter1'] = sizes[1]

    #TODO UPDATE CODES CATEGORIES WHEN CHANGED IN CODING DIALOG

    def get_codes_and_categories(self):
        """ Called from init, delete category/code.
        Also called on other coding dialogs in the dialog_list. """

        self.codes, self.categories = self.app.get_data()

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column counts the number of times that code has been used by selected coder in selected file. """

        self.get_codes_and_categories()
        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            #try:
            cats.remove(item)
            #except Exception as e:
            #    logger.debug(e, item)

        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child, then remove matched categories from the list '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            #logger.debug("Cats: " + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "" and c['memo'] is not None:
                            memo = _("Memo")
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QtGui.QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "" and c['memo'] is not None:
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QtGui.QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setToolTip(2, c['memo'])
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.ui.treeWidget.expandAll()


    def fill_text_edit(self):
        """ Get data about file and fill text edit. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] != 'cid':
            return
        code_= None
        for c in self.codes:
            if c['name'] == current.text(0):
                code_ = c
        if code_ is None:
            return
        cur = self.app.conn.cursor()
        text = _("CODE: ") + code_['name'] + "  " + current.text(1)
        text += "  " + _("COLOUR: ") + code_['color'] + "  " + _("CREATED BY: ") + code_['owner'] + "\n\n"
        text += _("MEMO: ") + "\n" + code_['memo'] + "\n"

        # Coding statistics
        coders = []
        sources = []
        text_sql = "select fid, seltext, pos0, pos1, owner, memo, avid from code_text where cid=?"
        cur.execute(text_sql, [code_['cid']])
        text_res = cur.fetchall()
        for r in text_res:
            coders.append(r[4])
            sources.append(r[0])
        img_sql = "select id, x1, y1, width, height, owner, memo from code_image where cid=?"
        cur.execute(img_sql, [code_['cid']])
        img_res = cur.fetchall()
        for r in img_res:
            coders.append(r[5])
            sources.append(r[0])
        av_sql = "select id, pos0, pos1, owner, memo from code_av where cid=?"
        cur.execute(av_sql, [code_['cid']])
        av_res = cur.fetchall()
        for r in av_res:
            coders.append(r[3])
            sources.append(r[0])

        # Coders total and names
        coders = list(set(coders))
        text += _("CODERS: ") + " " + str(len(coders))
        for c in coders:
            text += " | " + c
        text += "\n\n"

        # Sources total and names
        sources = list(set(sources))
        text += _("FILES: ") + " " + str(len(sources))
        for s in sources:
            cur.execute("select name from source where id=?", [s])
            sourcename = cur.fetchone()
            if sourcename is None:
                sourcename = [""]
                self.ui.textEdit.append(_("Report code summary. Code_text, code_image or code_av had a coding to a deleted file"))
            text += " | " + sourcename[0]
        text += "\n"
        text += self.text_statistics(code_, text_res)
        text += self.image_statistics(code_, img_res)
        text += self.av_statistics(code_, av_res)
        self.ui.textEdit.setText(text)

    def text_statistics(self, code_, text_res):
        """ Get text statistics for code.
        param:
            code_ : dictionary {name, color, cid,}
            text_res: list of text results
        """

        text = "\n" + _("TEXT CODINGS: ") + str(len(text_res)) + "\n"
        if text_res == []:
            return text
        total_chars = 0
        fulltext = ""
        for t in text_res:
            total_chars += len(t[1])
            fulltext += t[1] + " "
        avg_chars = total_chars / len(text_res)
        # Remove punctuation. Convert to lower case
        chars = ""
        for c in range(0, len(fulltext)):
            if fulltext[c].isalpha() or fulltext[c] == "'":
                chars += fulltext[c]
            else:
                chars += " "
        chars = chars.lower()
        word_list = chars.split()
        # print(word_list)
        msg = _(
            "Word calculations: Words use alphabet characters and include the apostrophe. All other characters are word separators")
        text += msg + "\n"
        # TODO use word list for word proximity

        text += _("Words: ") + f"{len(word_list):,d}" + "\n"
        # Word frequency
        d = {}
        for word in word_list:
            d[word] = d.get(word, 0) + 1  # get(key, value if not present)
        # https://codeburst.io/python-basics-11-word-count-filter-out-punctuation-dictionary-manipulation-and-sorting-lists-3f6c55420855
        word_freq = []
        for key, value in d.items():
            word_freq.append((value, key))
        word_freq.sort(reverse=True)
        # print(word_freq)
        text += _("Unique words: ") + str(len(word_freq)) + "\n"
        # Top 100 or maximum of less than 100
        max_count = len(word_freq)
        if max_count > 100:
            max_count = 100
        text += _("Top 100 words") + "\n"
        for i in range(0, max_count):
            text += word_freq[i][1] + "   " + str(word_freq[i][0]) + " | "
        text += "\n" + _("Total characters: ") + f"{total_chars:,d}"
        text += "  " + _("Average characters: ") + str(int(avg_chars)) + "\n"
        return text

    def image_statistics(self, code_, img_res):
        """ Get image statistics for code
        param:
            code_ : dictionary {name, color, cid,}
            img_res: list of text results
        """

        text = "\n" + _("IMAGE CODINGS: ") + str(len(img_res)) + "\n"
        if img_res == []:
            return text
        cur = self.app.conn.cursor()
        image_areas = []  # list of list of id, area
        sql = "select id, mediapath from source where (mediapath like '/images%' or mediapath like 'images:%') "
        cur.execute(sql)
        res = cur.fetchall()
        images = []
        for r in res:
            image = {"id": r[0], "mediapath": r[1]}
            abs_path = ""
            if 'images:' == r[1][0:7]:
                abs_path = r[1][7:]
            else:
                abs_path = self.app.project_path + r[1]
            image['abspath'] = abs_path
            # Image size
            img = Image.open(abs_path)
            w, h = img.size
            image['area'] = w * h
            images.append(image)
            total_area = 0
            count = 0
            avg_area = 0
            for i in img_res:
                if i[0] == r[0]:
                    total_area += int(i[3] * i[4])
                    count += 1
            try:
                avg_area = int(total_area / count)
            except:
                pass
            percent_of_image = round(avg_area / image['area'] * 100, 3)
            if count > 0:
                text += _("Image: ") + abs_path.split("/")[-1] + "  "
                text += _("Count: ") + str(count) + "   " + _("Average coded area: ") + f"{avg_area:,d}" + _(" pixels")
                text += "  " + _("Average area of image: ") + str(percent_of_image) + "%\n"
        return text

    def av_statistics(self, code_, av_res):
        """ Get video statistics for image file
        param: id : Integer """

        text = "\n" + _("A/V CODINGS: ") + str(len(av_res)) + "\n"
        cur = self.app.conn.cursor()
        image_areas = []  # list of list of id, area
        sql = "select id, mediapath from source where (mediapath like '/video%' or mediapath like 'video:%' or mediapath like '/audio%' or mediapath like 'audio:%') "
        cur.execute(sql)
        res = cur.fetchall()
        for r in res:
            abs_path = ""
            if r[1][0:6] in ('video:', 'audio:'):
                abs_path = r[1][6:]
            else:
                abs_path = self.app.project_path + r[1]
            # media duration
            instance = vlc.Instance()
            mediaplayer = instance.media_player_new()
            media = instance.media_new(abs_path)
            media.parse()
            mediaplayer.play()
            mediaplayer.pause()
            msecs = media.get_duration()
            media_secs = int(msecs / 1000)
            total_coded_secs = 0
            count = 0
            avg_coded_secs = 0
            for a in av_res:
                if a[0] == r[0]:
                    total_coded_secs += int((a[2] - a[1]) / 1000)
                    count += 1
            try:
                avg_coded_secs = int(total_coded_secs / count)
            except:
                pass
            percent_of_media = round(avg_coded_secs / media_secs * 100, 3)
            if count > 0:
                text += _("Media: ") + abs_path.split("/")[-1] + "  "
                text += _("Count: ") + str(count) + "   "
                text += _("Average coded duration: ") + f"{avg_coded_secs:,d}" + _(" secs")
                text += "  " + _("Average percent of media: ") + str(percent_of_media) + "%\n"
        return text


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogReportCodeSummary()
    ui.show()
    sys.exit(app.exec_())

