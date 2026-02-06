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
https://qualcoder-org.github.io/
"""

from copy import deepcopy
import fitz
import logging
import os
from PIL import Image
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import re

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from .GUI.ui_dialog_report_code_summary import Ui_Dialog_code_summary
from .color_selector import TextColor
from .simple_wordcloud import stopwords as cloud_stopwords

# If VLC not installed, it will not crash
vlc = None
try:
    import vlc
except Exception as e:
    print(e)


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogReportCodeSummary(QtWidgets.QDialog):
    """ Provide a summary report for selected code.
    """

    app = None
    parent_tetEdit = None
    categories = []
    codes = []

    def __init__(self, app, parent_textedit):
        self.app = app
        self.parent_textEdit = parent_textedit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_summary()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        docfont = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.textEdit.setStyleSheet(docfont)
        treefont = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        try:
            s0 = int(self.app.settings['dialogreport_code_summary_splitter0'])
            s1 = int(self.app.settings['dialogreport_code_summary_splitter1'])
            self.ui.splitter.setSizes([s0, s1])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.splitter_sizes)
        self.ui.pushButton_search_next.setIcon(qta.icon('mdi6.play'))
        self.ui.pushButton_search_next.pressed.connect(self.search_results_next)
        self.ui.treeWidget.setStyleSheet(treefont)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.fill_tree()
        # These signals after the tree is filled the first time
        self.ui.treeWidget.itemCollapsed.connect(self.get_collapsed)
        self.ui.treeWidget.itemExpanded.connect(self.get_collapsed)

        self.ui.treeWidget.itemClicked.connect(self.fill_text_edit)
        self.ui.textEdit.setTabChangesFocus(True)

    def splitter_sizes(self):
        """ Detect size changes in splitter and store in app.settings variable. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogreport_code_summary_splitter0'] = sizes[0]
        self.app.settings['dialogreport_code_summary_splitter1'] = sizes[1]

    def get_codes_and_categories(self):
        """ Called from init, delete category/code.
        Also called on other coding dialogs in the dialog_list. """

        self.codes, self.categories = self.app.get_codes_categories()

    def get_collapsed(self, item):
        """ On category collapse or expansion signal, find the collapsed parent category items.
        This will fill the self.app.collapsed_categories and is the expanded/collapsed tree is then replicated across
        other areas of the app. """

        if item.text(1)[:3] == "cid":
            return
        if not item.isExpanded() and item.text(1) not in self.app.collapsed_categories:
            self.app.collapsed_categories.append(item.text(1))
        if item.isExpanded() and item.text(1) in self.app.collapsed_categories:
            self.app.collapsed_categories.remove(item.text(1))

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column counts the number of times that code has been used by selected coder in selected file. """

        self.get_codes_and_categories()
        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if not self.app.settings['showids']:
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f'catid:{c["catid"]}', memo])
                top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if f"catid:{c['catid']}" in self.app.collapsed_categories:
                    top_item.setExpanded(False)
                else:
                    top_item.setExpanded(True)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)
        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child, then remove matched categories from the list '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == f'catid:{c["supercatid"]}':
                        memo = ""
                        if c['memo'] != "":
                            memo = _("Memo")
                        child = QtWidgets.QTreeWidgetItem([c['name'], f'catid:{c["catid"]}', memo])
                        child.setToolTip(0, c['name'])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        if f"catid:{c['catid']}" in self.app.collapsed_categories:
                            child.setExpanded(False)
                        else:
                            child.setExpanded(True)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo])
                top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QtGui.QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                                  Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == f'catid:{c["catid"]}':
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo])
                    child.setBackground(0, QtGui.QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
                    child.setToolTip(0, c['name'])
                    child.setToolTip(2, c['memo'])
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                                   Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        # self.ui.treeWidget.expandAll()
        self.fill_code_counts_in_tree()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code.
        Called by: fill_tree
        """

        cur = self.app.conn.cursor()
        sql_text = "select count(cid) from code_text where cid=?"
        sql_img = "select count(cid) from code_image where cid=?"
        sql_av = "select count(cid) from code_av where cid=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = int(item.text(1)[4:])
                coding_count = 0
                cur.execute(sql_text, [cid])
                res_text = cur.fetchone()
                if res_text:
                    coding_count = res_text[0]
                cur.execute(sql_img, [cid])
                res_img = cur.fetchone()
                if res_img:
                    coding_count += res_img[0]
                cur.execute(sql_av, [cid])
                res_av = cur.fetchone()
                if res_av:
                    coding_count += res_av[0]
                if coding_count > 0:
                    item.setText(3, str(coding_count))
                else:
                    item.setText(3, "")

            it += 1
            item = it.value()
            count += 1

    def fill_text_edit(self):
        """ Get data about file and fill text edit. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] != 'cid':
            self.ui.textEdit.setText("")
            return
        code_ = None
        for c in self.codes:
            if c['name'] == current.text(0):
                code_ = c
        if code_ is None:
            return
        cur = self.app.conn.cursor()
        text = _("CODE: ") + f"{code_['name']}  {current.text(1)}  "
        text += _("COLOUR: ") + f"{code_['color']}  " + _("CREATED BY: ") + f"{code_['owner']}\n\n"
        text += _("MEMO: ") + f"\n{code_['memo']}\n"

        # Coding statistics
        coders = []
        sources = []
        text_sql = "select fid, seltext, pos0, pos1, owner, ifnull(memo,''), avid from code_text where cid=?"
        cur.execute(text_sql, [code_['cid']])
        text_res = cur.fetchall()
        for r in text_res:
            coders.append(r[4])
            sources.append(r[0])
        img_sql = "select id, x1, y1, width, height, owner, ifnull(memo,''), pdf_page from code_image where cid=?"
        cur.execute(img_sql, [code_['cid']])
        img_res = cur.fetchall()
        for r in img_res:
            coders.append(r[5])
            sources.append(r[0])
        av_sql = "select id, pos0, pos1, owner, ifnull(memo,'') from code_av where cid=?"
        cur.execute(av_sql, [code_['cid']])
        av_res = cur.fetchall()
        for r in av_res:
            coders.append(r[3])
            sources.append(r[0])

        # Coders total and names
        coders = list(set(coders))
        text += _("CODERS: ") + f" {len(coders)}"
        for c in coders:
            text += f" | {c}"
        text += "\n\n"

        # Sources total and names
        sources = list(set(sources))
        text += _("FILES: ") + f" {len(sources)}"
        for s in sources:
            cur.execute("select name from source where id=?", [s])
            sourcename = cur.fetchone()
            if sourcename is None:
                sourcename = [""]
                msg_ = _("Report code summary. Code_text, code_image or code_av had a coding to a deleted file")
                self.ui.textEdit.append(msg_)
            text += f" | {sourcename[0]}"
        text += "\n"
        text += self.text_statistics(text_res)
        text += self.image_statistics(img_res)
        text += self.av_statistics(av_res)
        self.ui.textEdit.setText(text)

    def text_statistics(self, text_res):
        """ Get the average segment length, total characters, word counts for the text results for the code.
        param:
            text_res: list of fid, seltext, pos0, pos1, owner, memo, avid
        """

        text = "\n" + _("TEXT CODINGS: ") + f"{len(text_res)}\n"
        if not text_res:
            return text
        total_chars = 0
        fulltext = ""
        for t in text_res:
            total_chars += len(t[1])
            fulltext += f"{t[1]} "
        avg_chars = total_chars / len(text_res)
        text += _("Total characters: ") + f"{total_chars:,d}"
        text += "  " + _("Average characters: ") + f"{int(avg_chars)}\n"

        # Get stopwords from user created list or default to simple_wordcloud stopwords
        stopwords_file_path = os.path.join(os.path.expanduser('~'), ".qualcoder", "stopwords.txt")
        user_created_stopwords = []
        try:
            # Can get UnicodeDecode Error on Windows so using error handler
            with open(stopwords_file_path, "r", encoding="utf-8", errors="backslashreplace") as stopwords_file:
                while 1:
                    stopword = stopwords_file.readline()
                    if stopword[0:6] == "\ufeff":  # Associated with notepad files
                        stopword = stopword[6:]
                    if not stopword:
                        break
                    user_created_stopwords.append(stopword.strip())  # Remove line ending
            stopwords = user_created_stopwords
        except FileNotFoundError as err:
            stopwords = cloud_stopwords

        # Remove punctuation. Convert to lower case
        chars = ""
        for c in range(0, len(fulltext)):
            if fulltext[c].isalpha() or fulltext[c] == "'":
                chars += fulltext[c]
            else:
                chars += " "
        chars = chars.lower()
        word_list_with_stopwords = chars.split()
        word_list = []
        for word in word_list_with_stopwords:
            if word not in stopwords:
                word_list.append(word)
        msg = _(
            "Word calculations: Words use alphabet characters and include the apostrophe. "
            "All other characters are word separators. Excludes English stopwords")
        text += f"{msg}\n"
        text += _("Words: ") + f"{len(word_list):,d}\n"

        # Word frequency
        d = {}
        for word in word_list:
            d[word] = d.get(word, 0) + 1  # get(key, value if not present)
        word_freq = []
        for key, value in d.items():
            word_freq.append((value, key))
        word_freq.sort(reverse=True)

        text += _("Unique words: ") + f"{len(word_freq)}\n"
        # Top 100 or maximum of less than 100
        max_count = len(word_freq)
        if max_count > 100:
            max_count = 100
        text += _("Top 100 words") + "\n"
        for i in range(0, max_count):
            text += f"{word_freq[i][1]}   {word_freq[i][0]} | "
        text += "\n"
        return text

    def image_statistics(self, img_res):
        """ Get image statistics (code count, image size, average coded area) for code results.
        param:
            img_res: list of id, x1, y1, width, height, owner, memo, pdf_page
        """

        text = "\n" + _("IMAGE CODINGS: ") + f"{len(img_res)}\n"
        if not img_res:
            return text
        cur = self.app.conn.cursor()
        sql = "select id, mediapath from source where "\
              "(mediapath like '/images%' or mediapath like 'images:%' or lower(mediapath) like '%.pdf') "
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

            # Pdf images
            pdf_width = 0
            pdf_height = 0
            pdf_path = ""
            if r[1][:6] == "/docs/":
                pdf_path = f"{self.app.project_path}/documents/{r[1][6:]}"
            if r[1][:5] == "docs:":
                pdf_path = r[1][5:]
            if pdf_path != "":
                fitz_pdf = fitz.open(pdf_path)
                page = fitz_pdf[0]  # Use first page and assume the remainder are the same size
                pixmap = page.get_pixmap()
                pdf_width = pixmap.width
                pdf_height = pixmap.height

            # Image size and area
            if pdf_path == "":
                image['abspath'] = abs_path
                img = Image.open(abs_path)
                w, h = img.size
                image['area'] = w * h
            else:
                image['abspath'] = pdf_path
                image['area'] = pdf_height * pdf_width
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
            except ZeroDivisionError:
                pass
            percent_of_image = round(avg_area / image['area'] * 100, 3)
            if count > 0:
                text += _("Image: ") + abs_path.split("/")[-1] + "  "
                text += _("Count: ") + f"{count}   " + _("Average coded area: ") + f"{avg_area:,d}" + _(" pixels")
                text += "  " + _("Average area of image: ") + f"{percent_of_image}%\n"
        return text

    def av_statistics(self, av_results):
        """ Get video statistics for image file
        param:
            av_results: List of id, pos0, pos1, owner, memo
        """

        text_ = "\n" + _("A/V CODINGS: ") + f"{len(av_results)}\n"
        cur = self.app.conn.cursor()
        sql = "select id, mediapath from source where (mediapath like '/video%' or mediapath like 'video:%' or " \
              "mediapath like '/audio%' or mediapath like 'audio:%') "
        cur.execute(sql)
        res = cur.fetchall()
        for r in res:
            abs_path = ""
            if r[1][0:6] in ('video:', 'audio:'):
                abs_path = r[1][6:]
            else:
                abs_path = self.app.project_path + r[1]
            # Media duration
            media_secs = None
            if vlc:
                try:
                    instance = vlc.Instance()
                except NameError as name_err:
                    logger.error(f"vlc.Instance: {name_err}")
                    instance = None
                if instance:
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
            for a in av_results:
                if a[0] == r[0]:
                    total_coded_secs += int((a[2] - a[1]) / 1000)
                    count += 1
            try:
                avg_coded_secs = int(total_coded_secs / count)
            except ZeroDivisionError:
                pass
            if count > 0:
                text_ += _("Media: ") + abs_path.split("/")[-1] + "  "
                text_ += _("Count: ") + f"{count}   "
                text_ += _("Average coded duration: ") + f"{avg_coded_secs:,d}" + _(" secs") + " "
                if media_secs:
                    text_ += _("Average percent of media: ") + f"{round(avg_coded_secs / media_secs * 100, 3)}%\n"
        return text_

    def search_results_next(self):
        """ Search textedit for text """

        search_text = self.ui.lineEdit_search_results.text()
        if search_text == "":
            return
        if self.ui.textEdit.toPlainText() == "":
            return
        if self.ui.textEdit.textCursor().position() >= len(self.ui.textEdit.toPlainText()):
            cursor = self.ui.textEdit.textCursor()
            cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
            self.ui.textEdit.setTextCursor(cursor)
        te_text = self.ui.textEdit.toPlainText()
        pattern = None
        flags = 0
        try:
            pattern = re.compile(search_text, flags)
        except re.error as e_:
            logger.warning(f"re error Bad escape {e_}")
        if pattern is None:
            return
        for match in pattern.finditer(te_text):
            if match.start() > self.ui.textEdit.textCursor().position():
                cursor = self.ui.textEdit.textCursor()
                cursor.setPosition(match.start(), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(match.start() + len(search_text), QtGui.QTextCursor.MoveMode.KeepAnchor)
                self.ui.textEdit.setTextCursor(cursor)
                break
