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

Authors: Colin Curtain C, Kai Droege, Justin Missaghieh--Poncet, Lorenzo Salomao
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import csv
import logging

import qtawesome as qta
from PyQt6 import QtCore, QtWidgets

from .helpers import ExportDirectoryPathDialog, Message
from .irastats import (
    available_variables,
    build_lexical_table,
    build_segments,
    descendant_statistics,
    frequency_rows,
    hapax_rows,
    variable_rows,
)
from .irastats.report_html import descstats_html
from .select_items import DialogSelectItems

logger = logging.getLogger(__name__)

LANGUAGES = ["fr", "en", "de", "es", "it", "pt"]


class DialogTextStats(QtWidgets.QDialog):
    """ Text statistics in the style of the IRaMuTeQ software, computed on the
    coded segments (or the whole documents) of the current project.

    Opened from the Reports menu. The analysable corpus is built with
    irastats.corpus from the project database (self.app.conn); every computation
    engine lives in the pure-Python irastats package and is unit-tested without
    a GUI. The UI is built in code so that no .ui file has to be regenerated.
    """

    def __init__(self, app, parent_textedit):
        QtWidgets.QDialog.__init__(self)
        self.app = app
        self.parent_textEdit = parent_textedit
        self.setWindowTitle(_("Text statistics (IRaMuTeQ methods)"))
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)

        self.file_ids = []
        self.case_ids = []
        self.code_ids = []
        self.segments = []
        self.lexical_table = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._build_selection_group())
        self.tabWidget = QtWidgets.QTabWidget()
        self._build_corpus_tab()
        self._build_descstats_tab()
        layout.addWidget(self.tabWidget)

    # --- Selection (same helpers as the other Reports dialogs) ---

    def _build_selection_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox(_("Selection"))
        hlayout = QtWidgets.QHBoxLayout(group)
        self.pushButton_select_files = QtWidgets.QPushButton(_("Select files"))
        self.pushButton_select_files.setIcon(qta.icon("mdi6.file-outline"))
        self.pushButton_select_files.clicked.connect(self.select_files)
        self.pushButton_select_cases = QtWidgets.QPushButton(_("Select cases"))
        self.pushButton_select_cases.setIcon(qta.icon("mdi6.account-outline"))
        self.pushButton_select_cases.clicked.connect(self.select_cases)
        self.pushButton_select_codes = QtWidgets.QPushButton(_("Select codes"))
        self.pushButton_select_codes.setIcon(qta.icon("mdi6.text"))
        self.pushButton_select_codes.clicked.connect(self.select_codes)
        self.label_selection = QtWidgets.QLabel(_("All files, cases and codes"))
        self.label_selection.setWordWrap(True)
        for button in (self.pushButton_select_files, self.pushButton_select_cases, self.pushButton_select_codes):
            hlayout.addWidget(button)
        hlayout.addWidget(self.label_selection, 1)
        return group

    def select_files(self):
        """ Restrict the corpus to the selected text files. """

        filenames = self.app.get_text_filenames()
        if not filenames:
            return
        selection_list = [{"id": -1, "name": ""}] + filenames
        ui = DialogSelectItems(self.app, selection_list, _("Select files"), "many",
                               preselected=self.file_ids)
        if not ui.exec():
            return
        selected = ui.get_selected()
        if not selected or any(row["id"] == -1 for row in selected):
            self.file_ids = []
        else:
            self.file_ids = [row["id"] for row in selected]
        self._update_selection_label()

    def select_cases(self):
        """ Restrict the corpus to the segments of the selected cases. """

        cases = self.app.get_casenames()
        if not cases:
            Message(self.app, _("No cases"), _("No cases")).exec()
            return
        selection_list = [{"id": -1, "name": ""}] + cases
        ui = DialogSelectItems(self.app, selection_list, _("Select cases"), "many",
                               preselected=self.case_ids)
        if not ui.exec():
            return
        selected = ui.get_selected()
        if not selected or any(row["id"] == -1 for row in selected):
            self.case_ids = []
        else:
            self.case_ids = [row["id"] for row in selected]
        self._update_selection_label()

    def select_codes(self):
        """ Restrict the corpus to the selected codes. """

        cur = self.app.conn.cursor()
        cur.execute("select cid, name from code_name order by lower(name)")
        codes = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
        if not codes:
            return
        selection_list = [{"id": -1, "name": ""}] + codes
        ui = DialogSelectItems(self.app, selection_list, _("Select codes"), "many",
                               preselected=self.code_ids)
        if not ui.exec():
            return
        selected = ui.get_selected()
        if not selected or any(row["id"] == -1 for row in selected):
            self.code_ids = []
        else:
            self.code_ids = [row["id"] for row in selected]
        self._update_selection_label()

    def _update_selection_label(self):
        parts = []
        parts.append(_("Files: ") + (str(len(self.file_ids)) if self.file_ids else _("all")))
        parts.append(_("Cases: ") + (str(len(self.case_ids)) if self.case_ids else _("all")))
        parts.append(_("Codes: ") + (str(len(self.code_ids)) if self.code_ids else _("all")))
        self.label_selection.setText(" | ".join(parts))

    # --- Corpus tab ---

    def _build_corpus_tab(self):
        self.tab_corpus = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tab_corpus)

        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel(_("Language:")))
        self.comboBox_language = QtWidgets.QComboBox()
        self.comboBox_language.addItems(LANGUAGES)
        lang = self.app.settings.get("language", "fr")
        if lang in LANGUAGES:
            self.comboBox_language.setCurrentText(lang)
        params.addWidget(self.comboBox_language)
        params.addWidget(QtWidgets.QLabel(_("Custom stopwords file:")))
        self.lineEdit_stopwords = QtWidgets.QLineEdit()
        self.lineEdit_stopwords.setPlaceholderText(_("Optional text file, one word per line"))
        self.pushButton_stopwords = QtWidgets.QPushButton(_("Browse"))
        self.pushButton_stopwords.clicked.connect(self.browse_stopwords)
        params.addWidget(self.lineEdit_stopwords, 1)
        params.addWidget(self.pushButton_stopwords)
        self.checkBox_stem = QtWidgets.QCheckBox(_("Light stemming"))
        params.addWidget(self.checkBox_stem)
        self.checkBox_documents = QtWidgets.QCheckBox(_("Include whole documents"))
        params.addWidget(self.checkBox_documents)
        layout.addLayout(params)

        buttons = QtWidgets.QHBoxLayout()
        self.pushButton_build_corpus = QtWidgets.QPushButton(_("Build corpus"))
        self.pushButton_build_corpus.setIcon(qta.icon("mdi6.play"))
        self.pushButton_build_corpus.clicked.connect(self.build_corpus)
        buttons.addWidget(self.pushButton_build_corpus)
        self.label_corpus_info = QtWidgets.QLabel("")
        buttons.addWidget(self.label_corpus_info, 1)
        layout.addLayout(buttons)

        self.tableWidget_segments = QtWidgets.QTableWidget()
        self.tableWidget_segments.setColumnCount(4)
        self.tableWidget_segments.setHorizontalHeaderLabels([_("Document"), _("Case"), _("Code"), _("Text")])
        self.tableWidget_segments.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.tableWidget_segments)
        self.tabWidget.addTab(self.tab_corpus, _("Corpus"))

    def browse_stopwords(self):
        filepath, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self, _("Custom stopwords file"), self.app.settings.get("directory", ""), "Text Files (*.txt)")
        if filepath:
            self.lineEdit_stopwords.setText(filepath)

    def get_segments(self) -> bool:
        """ Build the segment list from the current selection. Sets self.segments. """

        try:
            self.segments = build_segments(
                self.app.conn,
                file_ids=self.file_ids or None,
                case_ids=self.case_ids or None,
                code_ids=self.code_ids or None,
                include_documents=self.checkBox_documents.isChecked(),
            )
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return False
        return True

    def get_lexical_table(self, min_freq: int = 1):
        """ Build (or rebuild) the lexical table from the current corpus and
        normalisation parameters. Sets self.lexical_table. """

        if not self.segments and not self.get_segments():
            return None
        try:
            self.lexical_table = build_lexical_table(
                self.segments,
                language=self.comboBox_language.currentText(),
                min_freq=min_freq,
                stem=self.checkBox_stem.isChecked(),
                custom_stopwords_path=self.lineEdit_stopwords.text() or None,
            )
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return None
        return self.lexical_table

    def build_corpus(self):
        """ Build the corpus, show a preview and the corpus size. """

        if not self.get_segments():
            return
        if not self.segments:
            Message(self.app, _("Nothing found"), _("No coded segments or documents found")).exec()
            return
        table = self.get_lexical_table(min_freq=1)
        self.tableWidget_segments.setRowCount(min(len(self.segments), 200))
        for row, segment in enumerate(self.segments[:200]):
            values = [segment["document"], segment["case"], segment["variables"].get("code", ""),
                      segment["text"][:120]]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_segments.setItem(row, col, item)
        self.tableWidget_segments.resizeColumnsToContents()
        info = _("Segments: ") + str(len(self.segments))
        if table is not None:
            info += " | " + _("Forms: ") + str(len(table.forms)) \
                + " | " + _("Active forms: ") + str(len(table.active_forms)) \
                + " | " + _("Occurrences: ") + str(int(table.matrix.sum()))
        self.label_corpus_info.setText(info)
        msg = _("Corpus built: ") + info
        self.parent_textEdit.append(msg)

    def available_variables(self):
        """ Variables available in the current corpus, for the analysis tabs. """

        if not self.segments and not self.get_segments():
            return []
        return available_variables(self.segments)

    # --- Descending statistics tab (IRaMuTeQ "rapport descendant") ---

    def _build_descstats_tab(self):
        self.tab_descstats = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tab_descstats)

        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel(_("Minimum frequency of active forms:")))
        self.spinBox_descstats_min_freq = QtWidgets.QSpinBox()
        self.spinBox_descstats_min_freq.setRange(1, 9999)
        self.spinBox_descstats_min_freq.setValue(1)
        params.addWidget(self.spinBox_descstats_min_freq)
        params.addWidget(QtWidgets.QLabel(_("Partition variable:")))
        self.comboBox_descstats_variable = QtWidgets.QComboBox()
        self._fill_variable_combo(self.comboBox_descstats_variable)
        params.addWidget(self.comboBox_descstats_variable, 1)
        self.pushButton_descstats_run = QtWidgets.QPushButton(_("Calculate"))
        self.pushButton_descstats_run.setIcon(qta.icon("mdi6.play"))
        self.pushButton_descstats_run.clicked.connect(self.run_descstats)
        params.addWidget(self.pushButton_descstats_run)
        self.pushButton_descstats_csv = QtWidgets.QPushButton(_("Export CSV"))
        self.pushButton_descstats_csv.setIcon(qta.icon("mdi6.file-delimited-outline"))
        self.pushButton_descstats_csv.clicked.connect(self.export_descstats_csv)
        params.addWidget(self.pushButton_descstats_csv)
        self.pushButton_descstats_html = QtWidgets.QPushButton(_("Export HTML"))
        self.pushButton_descstats_html.setIcon(qta.icon("mdi6.file-code-outline"))
        self.pushButton_descstats_html.clicked.connect(self.export_descstats_html)
        params.addWidget(self.pushButton_descstats_html)
        layout.addLayout(params)

        splitter = QtWidgets.QSplitter()
        self.tableWidget_descstats = QtWidgets.QTableWidget()
        self.tableWidget_descstats.setColumnCount(3)
        self.tableWidget_descstats.setHorizontalHeaderLabels([_("Form"), _("Frequency"), _("%")])
        self.tableWidget_descstats.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.tableWidget_descstats)
        self.textBrowser_descstats = QtWidgets.QTextBrowser()
        splitter.addWidget(self.textBrowser_descstats)
        splitter.setSizes([400, 400])
        layout.addWidget(splitter)
        self.tabWidget.addTab(self.tab_descstats, _("Text statistics"))
        self.descstats = None

    def _fill_variable_combo(self, combo: QtWidgets.QComboBox):
        """ Fill a partition variable combo: "none" plus the corpus variables. """

        combo.clear()
        combo.addItem(_("None"), "")
        for variable in self.available_variables():
            combo.addItem(variable, variable)

    def run_descstats(self):
        """ Compute the descending statistics and show them. """

        table = self.get_lexical_table(min_freq=self.spinBox_descstats_min_freq.value())
        if table is None:
            return
        variable = self.comboBox_descstats_variable.currentData() or None
        try:
            self.descstats = descendant_statistics(table, variable=variable)
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return
        rows = frequency_rows(self.descstats)
        self.tableWidget_descstats.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_descstats.setItem(row, col, item)
        self.tableWidget_descstats.resizeColumnsToContents()
        self.textBrowser_descstats.setHtml(descstats_html(self.descstats, variable=variable))
        msg = (_("Text statistics: ") + _("Segments: ") + str(len(table.segment_texts))
               + " | " + _("Occurrences: ") + str(self.descstats["total_occurrences"])
               + " | " + _("Forms: ") + str(self.descstats["distinct_forms"]))
        self.parent_textEdit.append(msg)

    def _descstats_csv_rows(self):
        rows = [[_("Form"), _("Frequency"), _("%")]]
        rows += frequency_rows(self.descstats)
        rows.append([])
        rows.append([_("Hapax")])
        rows += hapax_rows(self.descstats)
        if self.descstats["by_variable"]:
            rows.append([])
            rows.append([_("Modality"), _("Segments"), _("Occurrences"), _("Distinct forms")])
            rows += variable_rows(self.descstats)
        return rows

    def export_descstats_csv(self):
        if self.descstats is None:
            self.run_descstats()
        if self.descstats is None:
            return
        e = ExportDirectoryPathDialog(self.app, "Text_statistics.csv")
        filepath = e.filepath
        if filepath is None:
            return
        with open(filepath, "w", encoding="utf-8-sig", newline="") as file_:
            csv.writer(file_).writerows(self._descstats_csv_rows())
        msg = _("Text statistics CSV exported to: ") + filepath
        Message(self.app, _("CSV export"), msg).exec()
        self.parent_textEdit.append(msg)

    def export_descstats_html(self):
        if self.descstats is None:
            self.run_descstats()
        if self.descstats is None:
            return
        variable = self.comboBox_descstats_variable.currentData() or None
        e = ExportDirectoryPathDialog(self.app, "Text_statistics.html")
        filepath = e.filepath
        if filepath is None:
            return
        with open(filepath, "w", encoding="utf-8") as file_:
            file_.write(descstats_html(self.descstats, variable=variable))
        msg = _("Text statistics HTML exported to: ") + filepath
        Message(self.app, _("HTML export"), msg).exec()
        self.parent_textEdit.append(msg)
