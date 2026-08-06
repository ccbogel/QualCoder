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

import datetime
import logging

import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from PyQt6 import QtWidgets, QtCore

from .GUI.ui_dialog_memo import Ui_Dialog_memo
from .GUI.ui_dialog_select_quote import Ui_Dialog_select_quote
from .helpers import MarkdownHighlighter, msecs_to_hours_mins_secs


logger = logging.getLogger(__name__)


class DialogMemo(QtWidgets.QDialog):

    """ Dialog to view and edit memo text.
    entity_type / entity_id identify the memo owner ('project', 'file', 'case',
    'code', 'category') and enable the Insert quotes button. """


    def __init__(self, app, title:str="", memo:str="", clear_button:str="show", tooltip:str="",
                 entity_type:str="", entity_id=None):
        super(DialogMemo, self).__init__(parent=None)  # Overrride accept method

        self.app = app
        self.memo = memo
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.ui = Ui_Dialog_memo()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowTitle(title)
        self.ui.textEdit.setPlainText(self.memo)
        self.ui.textEdit.setFocus()
        if tooltip != "":
            self.ui.textEdit.setToolTip(tooltip)
        if clear_button == "hide":
            self.ui.pushButton_clear.hide()
            # Reused as a bare container (e.g. date selector), hide the toolbar
            self.ui.groupBox_toolbar.hide()
        self.ui.pushButton_clear.pressed.connect(self.clear_contents)
        self.ui.pushButton_insert_datetime.setIcon(qta.icon('mdi6.clock-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_insert_datetime.pressed.connect(self.insert_date)
        self.ui.pushButton_insert_coded_segment.setIcon(
            qta.icon('mdi6.format-quote-close', options=[{'scale_factor': 1.4}]))
        if self.entity_type == "":
            self.ui.pushButton_insert_coded_segment.hide()
        else:
            self.ui.pushButton_insert_coded_segment.pressed.connect(self.insert_quote)
        highlighter = MarkdownHighlighter(self.ui.textEdit, self.app)

    def clear_contents(self):
        """ Clear all text """
        self.ui.textEdit.setPlainText("")

    def insert_date(self):
        """ Insert current date and time at the cursor position. """

        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        cursor = self.ui.textEdit.textCursor()
        if cursor.positionInBlock() > 0:
            cursor.insertText("\n")
        cursor.insertText(now + "\n")
        self.ui.textEdit.setFocus()

    def insert_quote(self):
        """ Select coded segments scoped to the memo owner and insert them at the cursor. """

        ui = DialogSelectQuote(self.app, self.entity_type, self.entity_id)
        if not ui.quotes:
            QtWidgets.QMessageBox.information(self, _("Insert quotes"),
                                              _("No coded segments found for this item."))
            return
        if ui.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        selected = ui.get_selected()
        if not selected:
            return
        cursor = self.ui.textEdit.textCursor()
        if cursor.positionInBlock() > 0:
            cursor.insertText("\n")
        cursor.insertText("\n\n".join(selected) + "\n")
        self.ui.textEdit.setFocus()

    def accept(self):
        """ Accepted button overridden method. """

        self.memo = self.ui.textEdit.toPlainText()
        super(DialogMemo, self).accept()


class DialogSelectQuote(QtWidgets.QDialog):

    """ List coded segments (text, image, A/V) filtered by the memo owner entity,
    for insertion into a memo. Multi-selection allowed. """

    TYPE_COL = 0
    CODE_COL = 1
    FILE_COL = 2
    POS_COL = 3
    TEXT_COL = 4

    def __init__(self, app, entity_type:str, entity_id=None):
        super(DialogSelectQuote, self).__init__(parent=None)

        self.app = app
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.quotes = []
        self.ui = Ui_Dialog_select_quote()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        scope = {"project": _("Project"), "file": _("File"), "case": _("Case"),
                 "code": _("Code"), "category": _("Category")}
        self.ui.label_scope.setText(_("Coded segments") + " - " + scope.get(entity_type, entity_type))
        self.ui.lineEdit_filter.textChanged.connect(self.apply_filters)
        self.ui.tableWidget.doubleClicked.connect(self.accept)
        self.load_quotes()
        self.fill_table()
        self.fill_type_combobox()
        self.ui.comboBox_type.currentIndexChanged.connect(self.apply_filters)

    def category_code_ids(self):
        """ Collect code ids under a category: sub-categories recursively,
        their codes, and sub-code (supercid) descendants. """

        cat_ids = {self.entity_id}
        for _i in range(50):
            added = {c[0] for c in self.cats if c[2] in cat_ids and c[0] not in cat_ids}
            if not added:
                break
            cat_ids |= added
        code_ids = {c[0] for c in self.codes if c[2] in cat_ids}
        for _i in range(50):
            added = {c[0] for c in self.codes if c[3] in code_ids and c[0] not in code_ids}
            if not added:
                break
            code_ids |= added
        return code_ids

    def code_descendant_ids(self, cid):
        """ The code plus all its sub-code (supercid) descendants. Cycle safe. """

        code_ids = {cid}
        for _i in range(50):
            added = {c[0] for c in self.codes if c[3] in code_ids and c[0] not in code_ids}
            if not added:
                break
            code_ids |= added
        return code_ids

    def code_path(self, cid):
        """ Full hierarchy path: Category > ... > Code > ... > Sub-code. Cycle safe. """

        code_map = {c[0]: c for c in self.codes}  # cid: (cid, name, catid, supercid)
        cat_map = {c[0]: c for c in self.cats}  # catid: (catid, name, supercatid)
        chain = []
        node = code_map.get(cid)
        seen = set()
        while node is not None and node[0] not in seen:
            seen.add(node[0])
            chain.insert(0, node[1])
            top = node
            node = code_map.get(node[3])
        catid = top[2] if chain else None
        seen = set()
        while catid is not None and catid not in seen and catid in cat_map:
            seen.add(catid)
            chain.insert(0, cat_map[catid][1])
            catid = cat_map[catid][2]
        return " > ".join(chain)

    def segment_cases(self, fid, pos0=None, pos1=None):
        """ Names of cases containing this segment. Text by range overlap,
        image/AV (pos None) by file assignment to the case. """

        case_ids = set()
        for row in self.case_text:  # (caseid, fid, pos0, pos1)
            if row[1] != fid:
                continue
            if pos0 is None or (pos0 <= row[3] and pos1 >= row[2]):
                case_ids.add(row[0])
        names = sorted(self.case_names[i] for i in case_ids if i in self.case_names)
        return "; ".join(names)

    def load_quotes(self):
        """ Fill self.quotes with dictionaries: type, code, file, pos, text, insert.
        Insert pattern: "Quote" newline [position] Category path, Case:, File:, Coder. """

        cur = self.app.conn.cursor()
        cur.execute("select catid, name, supercatid from code_cat")
        self.cats = cur.fetchall()
        cur.execute("select cid, name, catid, supercid from code_name")
        self.codes = cur.fetchall()
        cur.execute("select caseid, fid, pos0, pos1 from case_text")
        self.case_text = cur.fetchall()
        cur.execute("select caseid, name from cases")
        self.case_names = dict(cur.fetchall())

        text_sql = "select code_name.name, source.name, code_text.pos0, code_text.pos1, code_text.seltext, " \
                   "code_text.cid, code_text.fid, ifnull(code_text.owner,''), ifnull(code_text.memo,'') " \
                   "from code_text join code_name on code_name.cid=code_text.cid " \
                   "join source on source.id=code_text.fid"
        image_sql = "select code_name.name, source.name, code_image.x1, code_image.y1, " \
                    "code_image.width, code_image.height, ifnull(code_image.memo,''), " \
                    "code_image.cid, code_image.id, ifnull(code_image.owner,'') " \
                    "from code_image join code_name on code_name.cid=code_image.cid " \
                    "join source on source.id=code_image.id"
        av_sql = "select code_name.name, source.name, code_av.pos0, code_av.pos1, ifnull(code_av.memo,''), " \
                 "code_av.cid, code_av.id, ifnull(code_av.owner,'') " \
                 "from code_av join code_name on code_name.cid=code_av.cid " \
                 "join source on source.id=code_av.id"
        order_t = " order by code_name.name, source.name, code_text.pos0"
        order_i = " order by code_name.name, source.name, code_image.imid"
        order_a = " order by code_name.name, source.name, code_av.pos0"
        params_t, params_i, params_a = [], [], []
        where_t = where_i = where_a = ""
        if self.entity_type == "file":
            where_t = " where code_text.fid=?"
            where_i = " where code_image.id=?"
            where_a = " where code_av.id=?"
            params_t = params_i = params_a = [self.entity_id]
        if self.entity_type == "case":
            # Text: overlap with case_text ranges. Image/AV: whole file assigned to case
            text_sql = "select distinct " + text_sql[len("select "):]
            where_t = " join case_text on case_text.fid=code_text.fid where case_text.caseid=? " \
                      "and code_text.pos0<=case_text.pos1 and code_text.pos1>=case_text.pos0"
            where_i = " where code_image.id in (select fid from case_text where caseid=?)"
            where_a = " where code_av.id in (select fid from case_text where caseid=?)"
            params_t = params_i = params_a = [self.entity_id]
        if self.entity_type in ("code", "category"):
            if self.entity_type == "code":
                ids = list(self.code_descendant_ids(self.entity_id))
            else:
                ids = list(self.category_code_ids())
                if not ids:
                    return
            placeholders = ",".join(["?"] * len(ids))
            where_t = f" where code_text.cid in ({placeholders})"
            where_i = f" where code_image.cid in ({placeholders})"
            where_a = f" where code_av.cid in ({placeholders})"
            params_t = params_i = params_a = ids
        cur.execute(text_sql + where_t + order_t, params_t)
        for r in cur.fetchall():
            pos = f"{r[2]}-{r[3]}"
            text_ = r[4] if r[4] is not None else ""
            insert = f'{_("CODED SEGMENT")}: "{text_}"\n'
            if r[8] != "":
                insert += f'{_("CODED MEMO")}: "{r[8]}"\n'
            insert += self.detail_line(f"[{pos}]", r[5], r[6], r[1], r[7],
                                       self.segment_cases(r[6], r[2], r[3]))
            self.quotes.append({"type": _("Text"), "code": r[0], "file": r[1], "pos": pos,
                                "text": text_, "memo": r[8], "insert": insert})
        cur.execute(image_sql + where_i + order_i, params_i)
        for r in cur.fetchall():
            pos = f"x:{r[2]} y:{r[3]} w:{r[4]} h:{r[5]}"
            insert = f'{_("CODED MEMO")}: "{r[6]}"\n' if r[6] != "" else ""
            insert += self.detail_line(f'[{_("Image")} {pos}]', r[7], r[8], r[1], r[9],
                                       self.segment_cases(r[8]))
            self.quotes.append({"type": _("Image"), "code": r[0], "file": r[1], "pos": pos,
                                "text": r[6], "memo": r[6], "insert": insert})
        cur.execute(av_sql + where_a + order_a, params_a)
        for r in cur.fetchall():
            pos = f"{msecs_to_hours_mins_secs(r[2])} - {msecs_to_hours_mins_secs(r[3])}"
            insert = f'{_("CODED MEMO")}: "{r[4]}"\n' if r[4] != "" else ""
            insert += self.detail_line(f"[A/V {pos}]", r[5], r[6], r[1], r[7],
                                       self.segment_cases(r[6]))
            self.quotes.append({"type": "A/V", "code": r[0], "file": r[1], "pos": pos,
                                "text": r[4], "memo": r[4], "insert": insert})

    def detail_line(self, pos_bracket, cid, fid, file_name, owner, cases_):
        """ Compose: [position] Category path, Case: x, File: y, Coder: z.
        Only parts that exist are added. """

        parts = [self.code_path(cid)]
        if cases_ != "":
            parts.append(_("Case: ") + cases_)
        parts.append(_("File: ") + file_name)
        if owner != "":
            parts.append(_("Coder: ") + owner)
        return f"{pos_bracket} " + ", ".join(parts) + "."

    def fill_table(self):
        """ Fill table rows from self.quotes. """

        tw = self.ui.tableWidget
        tw.setColumnCount(5)
        tw.setHorizontalHeaderLabels([_("Type"), _("Code"), _("File"), _("Position"), _("Text / Memo")])
        tw.setRowCount(len(self.quotes))
        for row, q in enumerate(self.quotes):
            tw.setItem(row, self.TYPE_COL, QtWidgets.QTableWidgetItem(q["type"]))
            tw.setItem(row, self.CODE_COL, QtWidgets.QTableWidgetItem(q["code"]))
            tw.setItem(row, self.FILE_COL, QtWidgets.QTableWidgetItem(q["file"]))
            tw.setItem(row, self.POS_COL, QtWidgets.QTableWidgetItem(q["pos"]))
            text_ = q["text"].replace("\n", " ")
            if len(text_) > 200:
                text_ = text_[:200] + "..."
            item = QtWidgets.QTableWidgetItem(text_)
            tip = q["text"]
            if q["type"] == _("Text") and q["memo"] != "":
                tip += "\n\n" + _("CODED MEMO") + ": " + q["memo"]
            item.setToolTip(tip)
            tw.setItem(row, self.TEXT_COL, item)
        tw.resizeColumnsToContents()
        if tw.columnWidth(self.TEXT_COL) > 450:
            tw.setColumnWidth(self.TEXT_COL, 450)

    def fill_type_combobox(self):
        """ Type filter: All plus the segment types present in the results.
        The last column header follows the selection: Text, Memo, or both. """

        types = []
        for q in self.quotes:
            if q["type"] not in types:
                types.append(q["type"])
        self.ui.comboBox_type.addItems([_("All")] + types)
        if len(types) < 2:
            self.ui.comboBox_type.hide()

    def apply_filters(self):
        """ Hide rows not matching the type combobox and the filter text. """

        text_ = self.ui.lineEdit_filter.text().lower()
        type_ = self.ui.comboBox_type.currentText()
        tw = self.ui.tableWidget
        for row in range(tw.rowCount()):
            match = type_ in (_("All"), "", self.quotes[row]["type"])
            if match and text_ != "":
                match = any(text_ in tw.item(row, col).text().lower()
                            for col in range(tw.columnCount()))
            tw.setRowHidden(row, not match)
        # Header of the last column follows the selected type
        if type_ == _("Text"):
            header = _("Text")
        elif type_ in (_("Image"), "A/V"):
            header = _("Memo")
        else:
            header = _("Text / Memo")
        tw.setHorizontalHeaderItem(self.TEXT_COL, QtWidgets.QTableWidgetItem(header))

    def get_selected(self):
        """ Return the insert strings of the selected rows, in table order. """

        rows = sorted({i.row() for i in self.ui.tableWidget.selectedIndexes()})
        return [self.quotes[r]["insert"] for r in rows if r < len(self.quotes)]
