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

from copy import copy
import logging
import os
import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets

from .helpers import ExportDirectoryPathDialog, Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class Codebook:
    """ Create a codebook and export to file. """

    app = None
    parent_textEdit = None
    code_names = []
    categories = []
    memos = False
    tree = None

    def __init__(self, app, parent_textedit, memos=False):

        self.app = app
        self.parent_textEdit = parent_textedit
        self.memos = memos
        self.code_names, self.categories = self.app.get_codes_categories()
        self.get_code_frequencies()
        self.tree = QtWidgets.QTreeWidget()
        self.fill_tree()
        self.export_odt()

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes
        """

        cats = copy(self.categories)
        codes = copy(self.code_names)
        self.tree.clear()
        self.tree.setColumnCount(4)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                self.tree.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child then remove matched categories from the list. '''

        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.tree)
                item = it.value()
                while item:  # while there is an item in the list
                    if item.text(1) == f'catid:{c["supercatid"]}':
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], f'catid:{c["catid"]}', memo])
                        item.addChild(child)
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
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo, str(c['freq'])])
                self.tree.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)
        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.tree)
            item = it.value()
            while item:
                if item.text(1) == f'catid:{c["catid"]}':
                    memo = ""
                    if c['memo'] != "":
                        memo = "Memo"
                    child = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo, str(c['freq'])])
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()

    def export_odt(self):
        """ Export ODT version of the codebook """

        filename = "Codebook.odt"
        exp_path = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_path.filepath
        if filepath is None:
            return
        # Create TextEdit document
        text_edit = QtWidgets.QTextEdit()
        fmt1 = QtGui.QTextBlockFormat()
        fmt1.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        cursor = QtGui.QTextCursor()
        text_edit.textCursor().beginEditBlock()
        text_edit.textCursor().setBlockFormat(fmt1)
        text_edit.textCursor().insertHtml(
            f"<p style=font-size:16pt;font-weight:400>Codebook: {self.app.project_name}</p><br/>")
        text_edit.textCursor().endEditBlock()
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        item = it.value()
        while item:
            self.depthgauge(item)
            cat = False
            if item.text(1).split(':')[0] == "catid":
                cat = True
            id_ = int(item.text(1).split(':')[1])
            prefix = ""
            for i in range(0, self.depthgauge(item)):
                prefix += "..."
            if cat:
                category_text = f'<br/><span style=font-size:14pt>{prefix}Category: {self.convert_entities(item.text(0))}</span><br/>'
                memo = ""
                for i in self.categories:
                    if i['catid'] == id_:
                        memo = self.convert_entities(i['memo'])
                text_edit.textCursor().beginEditBlock()
                text_edit.textCursor().setBlockFormat(fmt1)
                text_edit.textCursor().insertHtml(category_text)
                if self.memos and memo != "":
                    text_edit.insertHtml(f"<span style=font-size:8pt>MEMO: {memo}</span><br/>")
                text_edit.textCursor().endEditBlock()
            else:  # Code
                memo = ""
                color = "#999999"
                for i in self.code_names:
                    if i['cid'] == id_:
                        color = i['color']
                        memo = self.convert_entities(i['memo'])
                code_text = prefix + f'<span style="color:{color}">&#9608;</span>Code: '
                code_text += self.convert_entities(item.text(0))
                code_text += f", Count: {item.text(3)}<br/>"
                text_edit.textCursor().beginEditBlock()
                text_edit.textCursor().setBlockFormat(fmt1)
                text_edit.textCursor().insertHtml(code_text)
                if self.memos and memo != "":
                    text_edit.insertHtml(f"<span style=font-size:8pt>MEMO: {memo}</span><br/>")
                text_edit.textCursor().endEditBlock()
            it += 1
            item = it.value()
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(text_edit.document())
        Message(self.app, _('Codebook exported'),f"Codebook exported:\n{filepath}").exec()
        self.parent_textEdit.append(_("Codebook exported to ") + filepath)

    def export_plaintext(self):
        """ Export codes to a plain text file, filename will have .txt ending. """

        filename = "codebook.txt"
        options = QtWidgets.QFileDialog.Option.DontResolveSymlinks | QtWidgets.QFileDialog.Option.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                               _("Select directory to save file"),
                                                               self.app.settings['directory'], options)
        if directory == "":
            return
        filepath = os.path.join(directory,filename)
        data = f"{_('Codebook for')} {self.app.project_name}\n========"
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        item = it.value()
        while item:
            self.depthgauge(item)
            cat = False
            if item.text(1).split(':')[0] == "catid":
                cat = True
            id_ = int(item.text(1).split(':')[1])
            memo = ""
            owner = ""
            prefix = ""
            for i in range(0, self.depthgauge(item)):
                prefix += "--"
            if cat:
                data += f"\n{prefix}{_('Category:')}{item.text(0)}, {item.text(1)}"
                for i in self.categories:
                    if i['catid'] == id_:
                        memo = i['memo']
                        owner = i['owner']
            else:
                data += f"\n{prefix}{_('Code:')} {item.text(0)}, {item.text(1)}"
                data += f", Frq: {item.text(3)}"
                for i in self.code_names:
                    if i['cid'] == id_:
                        memo = i['memo']
                        owner = i['owner']
            data += f", Owner: {owner}\n{prefix}Memo: {memo}"
            it += 1
            item = it.value()
        with open(filepath, 'w', encoding='utf-8') as file_:
            file_.write(data)
        Message(self.app, _('Codebook exported'), f"Codebook exported:\n{filepath}").exec()
        self.parent_textEdit.append(_("Codebook exported to ") + filepath)

    def depthgauge(self, item):
        """ Get depth for treewidget item. """

        depth = 0
        while item.parent() is not None:
            item = item.parent()
            depth += 1
        return depth

    def get_code_frequencies(self):
        """ Called from init. For each code, get the
        frequency from coded text, images and audio/video. """

        cur = self.app.conn.cursor()
        for c in self.code_names:
            c['freq'] = 0
            cur.execute("select count(cid) from code_text where cid=?", [c['cid'], ])
            result = cur.fetchone()
            if result is not None:
                c['freq'] += result[0]
            cur.execute("select count(imid) from code_image where cid=?", [c['cid'], ])
            result = cur.fetchone()
            if result is not None:
                c['freq'] += result[0]
            cur.execute("select count(avid) from code_av where cid=?", [c['cid'], ])
            result = cur.fetchone()
            if result is not None:
                c['freq'] += result[0]

    @staticmethod
    def convert_entities(text):
        """ Helper function to convert predefiend xml entnties " ' < > &
        into numeric equivalents #nnn;
        Also convert None type into ""
        param: text : String - usually a memo, description, code or category
        """

        if text is None:
            return ""
        text = text.replace('&', '&#038;')  # &#x26; &amp;
        text = text.replace('"', '&#034;')  # &#x22; &quot;
        text = text.replace("'", '&#039;')  # &#x27; &apos;
        text = text.replace('<', '&#060;')  # &#x3C; &lt;
        text = text.replace('>', '&#062;')  # &#x3E; &gt;
        return text
