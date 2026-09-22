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

Authors: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

from copy import copy
import csv
import datetime
import html
import logging
import os
from pathlib import Path
from random import randint
import re
import sqlite3

from PyQt6 import QtCore, QtGui, QtWidgets

from .color_selector import colors
from .helpers import ExportDirectoryPathDialog, Message

path = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

# Plain text codebook format, shared by every importer and exporter:
#   category>>category>>code[TAB]memo      >> = the segment before is a category
#   code>>>subcode>>>subcode[TAB]memo      >>> = the segment before is a code
#   category>>code>>>subcode               mixed paths are allowed
# The last segment is always a code. A category cannot hang under a code.
CAT_SEP = ">>"
CODE_SEP = ">>>"
_SEP_RE = re.compile(r"(>{3,}|>>)")


def parse_codebook_path(path_text):
    """ Split a codebook path into [(name, kind), ...], kind is 'cat' or 'code'.
    Returns [] for an empty path. A >> after a code is read as >>> (no category under a code). """

    tokens = [t.strip() for t in _SEP_RE.split(path_text.strip())]
    names = tokens[0::2]
    seps = tokens[1::2]
    result = []
    under_code = False
    for i, name in enumerate(names):
        if name == "":
            continue
        if i == len(names) - 1:
            kind = "code"
        else:
            kind = "code" if (under_code or seps[i].startswith(CODE_SEP)) else "cat"
        if kind == "code":
            under_code = True
        result.append((name, kind))
    return result


def read_codebook_rows(filepath):
    """ Read a .txt (tab separated) or .csv codebook file as [(path, memo), ...].
    In .txt, the memo follows a tab; two or more spaces also work as separator. """

    rows = []
    with open(filepath, 'r', encoding='utf-8-sig') as file_:
        if filepath.lower().endswith('.csv'):
            for row in csv.reader(file_):
                if not row or not row[0].strip():
                    continue
                memo = row[1].strip().strip('"') if len(row) > 1 else ""
                rows.append((row[0].strip(), memo))
            return rows
        for line in file_:
            line = line.rstrip('\n\r')
            if not line.strip():
                continue
            parts = line.split('\t', 1)
            if len(parts) == 1:
                parts = re.split(r"\s{2,}", line.strip(), maxsplit=1)
            memo = parts[1].strip().strip('"') if len(parts) > 1 else ""
            if parts[0].strip():
                rows.append((parts[0].strip(), memo))
    return rows


def build_codebook_path(code, codes, categories):
    """ Path string for a code dict: categories joined with >>, parent codes with >>>.
    codes and categories are the lists from app.get_codes_categories(). """

    by_cid = {c['cid']: c for c in codes}
    by_catid = {c['catid']: c for c in categories}
    code_chain = [code['name']]
    node = code
    guard = 0
    while node.get('supercid') is not None and guard < 1000:
        node = by_cid.get(node['supercid'])
        if node is None:
            break
        code_chain.insert(0, node['name'])
        guard += 1
    cat_chain = []
    catid = node['catid'] if node is not None else None
    guard = 0
    while catid is not None and guard < 1000:
        cat = by_catid.get(catid)
        if cat is None:
            break
        cat_chain.insert(0, cat['name'])
        catid = cat['supercatid']
        guard += 1
    text = CODE_SEP.join(code_chain)
    if cat_chain:
        text = CAT_SEP.join(cat_chain) + CAT_SEP + text
    return text


class ImportPlainTextCodes:
    """ Import a plain text (.txt or .csv) codebook into the open project.
    See the format notes at the top of this module. Existing names are reused so
    later rows can nest under them; duplicate codes are reported and skipped. """

    def __init__(self, app, text_edit):
        self.app = app
        self.text_edit = text_edit
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select plain text codes file'),
                                                          self.app.settings['directory'], "Text (*.txt *.csv)",
                                                          options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                          )
        filepath = response[0]
        if not filepath:
            self.text_edit.append(_("Codes list text file not imported"))
            return
        filepath = filepath[0]  # List to string of file path
        self.text_edit.append("\n" + _("Importing codes from: ") + filepath)
        try:
            rows = read_codebook_rows(filepath)
        except Exception as e_:
            logger.error(f"Codebook read failed: {e_}")
            Message(self.app, _("Import error"), str(e_), "warning").exec()
            return
        self.cur = self.app.conn.cursor()
        self.imported_tables = set()  # only tables that really got a row
        for path_text, memo in rows:
            self.import_row(path_text, memo)
        # One event for the whole import, not one per row
        if self.imported_tables:
            self._emit_project_table_changes(sorted(self.imported_tables))

    def import_row(self, path_text, memo):
        """ Insert the categories, parent codes and the final code of one row. """

        segments = parse_codebook_path(path_text)
        if not segments:
            return
        parent_catid = None
        parent_cid = None
        for name, kind in segments[:-1]:
            if kind == "cat":
                parent_catid = self.get_or_create_category(name, parent_catid)
            else:
                parent_cid = self.get_or_create_code(name, "", parent_catid, parent_cid, is_parent=True)
                parent_catid = None
        name = segments[-1][0]
        self.get_or_create_code(name, memo, parent_catid, parent_cid)

    def get_or_create_category(self, name, supercatid):
        """ Return catid for name, inserting the category if absent. """

        self.cur.execute("select catid from code_cat where name=?", [name])
        res = self.cur.fetchone()
        if res:
            return res[0]
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.cur.execute("insert into code_cat (name,memo,owner,date,supercatid) values(?,?,?,?,?)",
                             (name, "", self.app.settings['codername'], now_date, supercatid))
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            return None
        self.imported_tables.add('code_cat')
        self.text_edit.append(_("Imported category: ") + name)
        return self.cur.lastrowid

    def get_or_create_code(self, name, memo, catid, supercid, is_parent=False):
        """ Return cid for name, inserting the code if absent.
        catid and supercid are mutually exclusive: a sub-code only keeps supercid. """

        self.cur.execute("select cid from code_name where name=?", [name])
        res = self.cur.fetchone()
        if res:
            if not is_parent:
                self.text_edit.append(_("Duplicate code not imported: ") + name)
            return res[0]
        if supercid is not None:
            catid = None
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        color = colors[randint(0, len(colors) - 1)]
        try:
            self.cur.execute("insert into code_name (name,memo,owner,date,catid,color,supercid) values(?,?,?,?,?,?,?)",
                             (name, memo, self.app.settings['codername'], now_date, catid, color, supercid))
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            self.text_edit.append(_("Duplicate code not imported: ") + name)
            return None
        self.imported_tables.add('code_name')
        self.text_edit.append(_("Imported code: ") + name)
        return self.cur.lastrowid

    def _emit_project_table_changes(self, tables):
        """ Notify other open dialogs about changed project tables. """

        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(tables, source=self)


class Codebook:
    """ Create a codebook and export to file. """

    memos = False

    def __init__(self, app, parent_textedit, memos=False):

        self.app = app
        self.parent_textEdit = parent_textedit
        self.memos = memos
        self.code_names, self.categories = self.app.get_codes_categories()
        self.get_code_frequencies()
        self.tree = QtWidgets.QTreeWidget()
        self.fill_tree()
        self.export_odt()

    def _nest_subcodes_in_tree(self):
        """ Re-parent code tree items so sub-codes (supercid) nest under their parent
        code. Runs after fill_tree has placed every code. Preserves item flags,
        checkboxes, colour and count because the existing item is moved, not rebuilt.
        No-op for projects without sub-codes. """
        tree = getattr(getattr(self, 'ui', None), 'treeWidget', None) or getattr(self, 'tree', None)
        if tree is None:
            return
        code_list = getattr(self, 'code_names', None)
        if code_list is None:
            code_list = getattr(self, 'codes', [])
        supercid_of = {c['cid']: c.get('supercid') for c in code_list}
        if not any(supercid_of.values()):
            return
        guard = 0
        moved = True
        while moved and guard < 10000:
            moved = False
            guard += 1
            cid_item = {}
            it = QtWidgets.QTreeWidgetItemIterator(tree)
            while it.value():
                node = it.value()
                t = node.text(1)
                if t.startswith('cid:'):
                    try:
                        cid_item[int(t[4:])] = node
                    except ValueError:
                        pass
                it += 1
            for cid_, node in cid_item.items():
                sup = supercid_of.get(cid_)
                if sup is None:
                    continue
                parent_node = cid_item.get(sup)
                if parent_node is None or node.parent() is parent_node:
                    continue
                cur_parent = node.parent()
                if cur_parent is None:
                    idx = tree.indexOfTopLevelItem(node)
                    taken = tree.takeTopLevelItem(idx)
                else:
                    taken = cur_parent.takeChild(cur_parent.indexOfChild(node))
                parent_node.addChild(taken)
                parent_node.setExpanded(True)  # show the nested sub-code from the start <- L
                taken.setExpanded(True)
                moved = True
                break

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes
        """

        cats = copy(self.categories)
        codes = copy(self.code_names)
        self.tree.clear()
        self.tree.setColumnCount(4)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f"catid:{c['catid']}", memo])
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
                while item:
                    if item.text(1) == f"catid:{c['supercatid']}":
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
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f"cid:{c['cid']}", memo, str(c['freq'])])
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
                    child = QtWidgets.QTreeWidgetItem([c['name'], f"cid:{c['cid']}", memo, str(c['freq'])])
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
        self._nest_subcodes_in_tree()

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
        # cursor = QtGui.QTextCursor()
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
                category_text = f'<br/><span style=font-size:14pt>{prefix}Category: {html.escape(item.text(0))}</span><br/>'
                memo = ""
                for i in self.categories:
                    if i['catid'] == id_:
                        memo = html.escape(i['memo'])
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
                        memo = html.escape(i['memo'])
                code_text = prefix + f'<span style="color:{color}">&#9608;</span>Code: '
                code_text += html.escape(item.text(0))
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
        """ Export the codebook as an importable plain text file (codebook.txt).
        One code per line: category>>code>>>subcode[TAB]memo. Not called by the menu. """

        filename = "codebook.txt"
        exp_path = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_path.filepath
        if filepath is None:
            return
        lines = []
        for code in self.code_names:
            memo = str(code.get('memo', '')).replace('\n', ' ').strip() if self.memos else ""
            lines.append(build_codebook_path(code, self.code_names, self.categories) + "\t" + memo)
        lines.sort()
        with open(filepath, 'w', encoding='utf-8') as file_:
            file_.write("\n".join(lines))
        Message(self.app, _('Codebook exported'), f"Codebook exported:\n{filepath}").exec()
        self.parent_textEdit.append(_("Codebook exported to ") + filepath)

    @staticmethod
    def depthgauge(item):
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

