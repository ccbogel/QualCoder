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

import networkx as nx
import qtawesome as qta
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PyQt6 import QtCore, QtGui, QtWidgets

from .helpers import ExportDirectoryPathDialog, Message
from .irastats import (
    available_variables,
    build_lexical_table,
    build_segments,
    descendant_statistics,
    export_iramuteq,
    frequency_rows,
    hapax_rows,
    specificities,
    specificity_rows,
    variable_rows,
)
from .irastats.similarity import build_graph, cooccurrence, detect_communities, draw_similarity_graph, similarity_matrix
from .irastats.ca import ca_coordinate_rows, correspondence_analysis, lexical_table_by_variable, plot_ca
from .irastats.reinert import draw_dendrogram, reinert_from_segments
from .topic_model import (
    AI_MODEL,
    DEFAULT_MODEL,
    bertopic_analysis,
    plot_topic_distribution,
    plot_topic_sizes,
    topic_by_variable,
)
from .irastats.report_html import descstats_html, specificites_html
from .irastats.report_odt import descstats_odt
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
        self.setWindowTitle(_("Lexicometry (text statistics)"))
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
        self._build_specificites_tab()
        self._build_similarity_tab()
        self._build_ca_tab()
        self._build_reinert_tab()
        self._build_bertopic_tab()
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
        self.pushButton_export_iramuteq = QtWidgets.QPushButton(_("Export IRaMuTeQ"))
        self.pushButton_export_iramuteq.setIcon(qta.icon("mdi6.export"))
        self.pushButton_export_iramuteq.setToolTip(
            _("Export the corpus (coded segments, plus whole documents if checked) in the IRaMuTeQ text format"))
        self.pushButton_export_iramuteq.clicked.connect(self.export_iramuteq_dialog)
        buttons.addWidget(self.pushButton_export_iramuteq)
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
        normalisation parameters. Sets self.lexical_table. The segments are
        rebuilt from the database on every call, so that changing the corpus
        parameters (language, stopwords, stemming, whole documents, selection)
        and pressing Calculate is always taken into account. """

        if not self.get_segments():
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
        self._refresh_variable_combos()
        return self.lexical_table

    def _refresh_variable_combos(self):
        """ Refill the partition variable combos after a corpus rebuild, keeping
        the current selection when it still exists. """

        for name in ("comboBox_descstats_variable", "comboBox_spec_variable", "comboBox_ca_variable",
                     "comboBox_bertopic_variable"):
            combo = getattr(self, name, None)
            if combo is None:
                continue
            current = combo.currentData()
            self._fill_variable_combo(combo)
            if name == "comboBox_ca_variable":
                combo.insertItem(0, _("Segments"), "__segments__")
            if current:
                index = combo.findData(current)
                if index >= 0:
                    combo.setCurrentIndex(index)

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
        self.pushButton_descstats_odt = QtWidgets.QPushButton(_("Export ODT"))
        self.pushButton_descstats_odt.setIcon(qta.icon("mdi6.file-document-outline"))
        self.pushButton_descstats_odt.setToolTip(
            _("Export the text statistics report as an ODT document (LibreOffice/OpenOffice)"))
        self.pushButton_descstats_odt.clicked.connect(self.export_descstats_odt)
        params.addWidget(self.pushButton_descstats_odt)
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

    def export_descstats_odt(self):
        if self.descstats is None:
            self.run_descstats()
        if self.descstats is None:
            return
        variable = self.comboBox_descstats_variable.currentData() or None
        e = ExportDirectoryPathDialog(self.app, "Text_statistics.odt")
        filepath = e.filepath
        if filepath is None:
            return
        if not filepath.lower().endswith(".odt"):
            filepath += ".odt"
        try:
            doc = descstats_odt(self.descstats, variable=variable)
            doc.save(filepath)
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return
        msg = _("Text statistics ODT exported to: ") + filepath
        Message(self.app, _("ODT export"), msg).exec()
        self.parent_textEdit.append(msg)

    # --- Specificities (chi-square) tab ---

    def _build_specificites_tab(self):
        self.tab_specificites = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tab_specificites)

        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel(_("Partition variable:")))
        self.comboBox_spec_variable = QtWidgets.QComboBox()
        self._fill_variable_combo(self.comboBox_spec_variable)
        params.addWidget(self.comboBox_spec_variable, 1)
        params.addWidget(QtWidgets.QLabel(_("Minimum frequency:")))
        self.spinBox_spec_min_freq = QtWidgets.QSpinBox()
        self.spinBox_spec_min_freq.setRange(1, 9999)
        self.spinBox_spec_min_freq.setValue(1)
        params.addWidget(self.spinBox_spec_min_freq)
        params.addWidget(QtWidgets.QLabel(_("Probability threshold:")))
        self.doubleSpinBox_spec_p = QtWidgets.QDoubleSpinBox()
        self.doubleSpinBox_spec_p.setRange(0.0001, 1.0)
        self.doubleSpinBox_spec_p.setSingleStep(0.01)
        self.doubleSpinBox_spec_p.setDecimals(4)
        self.doubleSpinBox_spec_p.setValue(0.05)
        params.addWidget(self.doubleSpinBox_spec_p)
        self.pushButton_spec_run = QtWidgets.QPushButton(_("Calculate"))
        self.pushButton_spec_run.setIcon(qta.icon("mdi6.play"))
        self.pushButton_spec_run.clicked.connect(self.run_specificites)
        params.addWidget(self.pushButton_spec_run)
        self.pushButton_spec_csv = QtWidgets.QPushButton(_("Export CSV"))
        self.pushButton_spec_csv.setIcon(qta.icon("mdi6.file-delimited-outline"))
        self.pushButton_spec_csv.clicked.connect(self.export_specificites_csv)
        params.addWidget(self.pushButton_spec_csv)
        self.pushButton_spec_html = QtWidgets.QPushButton(_("Export HTML"))
        self.pushButton_spec_html.setIcon(qta.icon("mdi6.file-code-outline"))
        self.pushButton_spec_html.clicked.connect(self.export_specificites_html)
        params.addWidget(self.pushButton_spec_html)
        layout.addLayout(params)

        splitter = QtWidgets.QSplitter()
        self.tableWidget_spec = QtWidgets.QTableWidget()
        self.tableWidget_spec.setColumnCount(7)
        self.tableWidget_spec.setHorizontalHeaderLabels(
            [_("Form"), _("Modality"), _("Count"), _("Expected count"), "chi2", _("Signed value"), "p"])
        self.tableWidget_spec.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.tableWidget_spec)
        self.textBrowser_spec = QtWidgets.QTextBrowser()
        splitter.addWidget(self.textBrowser_spec)
        splitter.setSizes([400, 400])
        layout.addWidget(splitter)
        self.tabWidget.addTab(self.tab_specificites, _("Specificities"))
        self.specificites_results = None

    def run_specificites(self):
        """ Compute the chi-square specificities for the selected variable. """

        variable = self.comboBox_spec_variable.currentData()
        if not variable:
            Message(self.app, _("No variable"), _("Select a partition variable")).exec()
            return
        table = self.get_lexical_table(min_freq=1)
        if table is None:
            return
        try:
            self.specificites_results = specificities(
                table, variable,
                min_freq=self.spinBox_spec_min_freq.value(),
                p_threshold=self.doubleSpinBox_spec_p.value())
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return
        rows = specificity_rows(self.specificites_results)
        self.tableWidget_spec.setRowCount(len(rows))
        for row, values in enumerate(rows):
            signe = self.specificites_results[row]["signe"]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if col == 5 and signe != 0:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#0a7d00" if signe > 0 else "#b00000")))
                self.tableWidget_spec.setItem(row, col, item)
        self.tableWidget_spec.resizeColumnsToContents()
        self.textBrowser_spec.setHtml(specificites_html(
            self.specificites_results, variable=variable, p_threshold=self.doubleSpinBox_spec_p.value()))
        msg = _("Specificities: ") + str(len(self.specificites_results)) + " " + _("rows for variable ") + variable
        self.parent_textEdit.append(msg)

    def export_specificites_csv(self):
        if self.specificites_results is None:
            self.run_specificites()
        if self.specificites_results is None:
            return
        e = ExportDirectoryPathDialog(self.app, "Specificities.csv")
        filepath = e.filepath
        if filepath is None:
            return
        with open(filepath, "w", encoding="utf-8-sig", newline="") as file_:
            writer = csv.writer(file_)
            writer.writerow([_("Form"), _("Modality"), _("Count"), _("Expected count"), "chi2",
                             _("Signed value"), "p"])
            writer.writerows(specificity_rows(self.specificites_results))
        msg = _("Specificities CSV exported to: ") + filepath
        Message(self.app, _("CSV export"), msg).exec()
        self.parent_textEdit.append(msg)

    def export_specificites_html(self):
        if self.specificites_results is None:
            self.run_specificites()
        if self.specificites_results is None:
            return
        variable = self.comboBox_spec_variable.currentData()
        e = ExportDirectoryPathDialog(self.app, "Specificities.html")
        filepath = e.filepath
        if filepath is None:
            return
        with open(filepath, "w", encoding="utf-8") as file_:
            file_.write(specificites_html(self.specificites_results, variable=variable,
                                          p_threshold=self.doubleSpinBox_spec_p.value()))
        msg = _("Specificities HTML exported to: ") + filepath
        Message(self.app, _("HTML export"), msg).exec()
        self.parent_textEdit.append(msg)

    def export_iramuteq_dialog(self):
        """ Export the current corpus (coded segments, plus whole documents when
        the checkbox is set) in the IRaMuTeQ text format: each segment is preceded
        by a "****" line with the starred variables (*code_<modality>, *cas_<modality>,
        *doc_<modality>, and one *<attribute>_<modality> per file/case attribute). """

        if not self.get_segments():  # always rebuild: the selection may have changed
            return
        if not self.segments:
            Message(self.app, _("Nothing found"), _("No coded segments or documents found")).exec()
            return
        filepath, _selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, _("Save IRaMuTeQ file"), self.app.settings.get("directory", ""), "Text Files (*.txt)")
        if not filepath:
            return
        if not filepath.lower().endswith(".txt"):
            filepath += ".txt"
        try:
            count = export_iramuteq(self.segments, filepath)
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return
        msg = _("Corpus exported in IRaMuTeQ format: ") + f"{filepath} ({count} " + _("segments") + ")"
        Message(self.app, _("IRaMuTeQ export"), msg).exec()
        self.parent_textEdit.append(msg)


    # --- Correspondence analysis (CA) tab ---

    def _build_ca_tab(self):
        self.tab_ca = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tab_ca)

        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel(_("Columns:")))
        self.comboBox_ca_variable = QtWidgets.QComboBox()
        self._fill_variable_combo(self.comboBox_ca_variable)
        self.comboBox_ca_variable.insertItem(0, _("Segments"), "__segments__")
        params.addWidget(self.comboBox_ca_variable, 1)
        self.pushButton_ca_run = QtWidgets.QPushButton(_("Calculate"))
        self.pushButton_ca_run.setIcon(qta.icon("mdi6.play"))
        self.pushButton_ca_run.clicked.connect(self.run_ca)
        params.addWidget(self.pushButton_ca_run)
        self.pushButton_ca_csv = QtWidgets.QPushButton(_("Export coordinates CSV"))
        self.pushButton_ca_csv.setIcon(qta.icon("mdi6.file-delimited-outline"))
        self.pushButton_ca_csv.clicked.connect(self.export_ca_csv)
        params.addWidget(self.pushButton_ca_csv)
        self.pushButton_ca_png = QtWidgets.QPushButton(_("Export PNG"))
        self.pushButton_ca_png.setIcon(qta.icon("mdi6.image-outline"))
        self.pushButton_ca_png.clicked.connect(self.export_ca_png)
        params.addWidget(self.pushButton_ca_png)
        layout.addLayout(params)

        splitter = QtWidgets.QSplitter()
        self.tableWidget_ca = QtWidgets.QTableWidget()
        self.tableWidget_ca.setColumnCount(4)
        self.tableWidget_ca.setHorizontalHeaderLabels([_("Axis"), _("Eigenvalue"), _("% inertia"), _("Cumulative %")])
        self.tableWidget_ca.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.tableWidget_ca)
        self.label_ca_info = QtWidgets.QLabel("")
        self.label_ca_info.setWordWrap(True)
        splitter.addWidget(self.label_ca_info)
        splitter.setSizes([300, 500])
        layout.addWidget(splitter)
        self.tabWidget.addTab(self.tab_ca, _("Correspondence analysis"))
        self.ca_result = None
        self.ca_figure = None

    def _compute_ca(self):
        """ Compute the correspondence analysis and a fresh factor-map Figure.
        Returns (result, figure) or None on error. A fresh Figure is returned each
        time because the Figure shown in a DialogFigure cannot be saved once its
        Qt canvas has been closed/deleted. """

        table = self.get_lexical_table(min_freq=1)
        if table is None:
            return None
        variable = self.comboBox_ca_variable.currentData()
        if not variable:
            Message(self.app, _("No variable"), _("Select a partition variable")).exec()
            return None
        try:
            if variable == "__segments__":
                matrix = table.active_matrix
                row_labels = list(table.active_forms)
                col_labels = [f"seg{i + 1}" for i in range(matrix.shape[1])]
            else:
                row_labels, col_labels, matrix = lexical_table_by_variable(table, variable)
            result = correspondence_analysis(matrix, row_labels=row_labels, col_labels=col_labels)
            figure = plot_ca(result, axes=(0, 1))
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return None
        return result, figure

    def run_ca(self):
        """ Correspondence analysis of the lexical table (forms x variable
        modalities, or forms x segments) and display of the factor map. """

        computed = self._compute_ca()
        if computed is None:
            return
        self.ca_result, self.ca_figure = computed
        result = self.ca_result
        n_axes = len(result["eigenvalues"])
        self.tableWidget_ca.setRowCount(n_axes)
        for axis in range(n_axes):
            values = [axis + 1, round(float(result["eigenvalues"][axis]), 6),
                      round(float(result["percent"][axis]), 2), round(float(result["cumulative"][axis]), 2)]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_ca.setItem(axis, col, item)
        self.tableWidget_ca.resizeColumnsToContents()
        self.label_ca_info.setText(
            _("Total inertia: ") + f"{result['inertia']:.6f} | " + _("Forms: ") + str(len(result["row_labels"]))
            + " | " + _("Columns: ") + str(len(result["col_labels"])))
        msg = _("Correspondence analysis: ") + str(n_axes) + " " + _("axes")
        self.parent_textEdit.append(msg)
        dialog = DialogFigure(self.app, self.ca_figure, _("Correspondence analysis"))
        dialog.show()
        self._ca_dialog = dialog

    def export_ca_csv(self):
        if self.ca_result is None:
            computed = self._compute_ca()
            if computed is None:
                return
            self.ca_result, self.ca_figure = computed
        if self.ca_result is None:
            return
        e = ExportDirectoryPathDialog(self.app, "CA_coordinates.csv")
        filepath = e.filepath
        if filepath is None:
            return
        result = self.ca_result
        n_axes = len(result["eigenvalues"])
        with open(filepath, "w", encoding="utf-8-sig", newline="") as file_:
            writer = csv.writer(file_)
            header = [_("Form"), _("Frequency")] + [f"F{a + 1}" for a in range(n_axes)]                 + [f"contrib{a + 1}" for a in range(n_axes)] + [f"cos2_{a + 1}" for a in range(n_axes)]
            writer.writerow(header)
            writer.writerows(ca_coordinate_rows(result, n_axes=n_axes))
            writer.writerow([])
            writer.writerow([_("Modality"), _("Frequency")] + [f"G{a + 1}" for a in range(n_axes)])
            for k, label in enumerate(result["col_labels"]):
                writer.writerow([label, int(result["col_freq"][k])]
                                + [round(float(result["col_coords"][k, a]), 6) for a in range(n_axes)])
        msg = _("CA coordinates exported to: ") + filepath
        Message(self.app, _("CSV export"), msg).exec()
        self.parent_textEdit.append(msg)

    def export_ca_png(self):
        # recompute a fresh figure: the one shown in a closed DialogFigure has a
        # deleted Qt canvas and cannot be saved again
        computed = self._compute_ca()
        if computed is None:
            return
        figure = computed[1]
        e = ExportDirectoryPathDialog(self.app, "CA_factor_map.png")
        filepath = e.filepath
        if filepath is None:
            return
        figure.savefig(filepath, dpi=150)
        msg = _("CA factor map exported to: ") + filepath
        Message(self.app, _("PNG export"), msg).exec()
        self.parent_textEdit.append(msg)


    # --- Reinert classification (CHD) tab ---

    def _build_reinert_tab(self):
        self.tab_reinert = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tab_reinert)

        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel(_("UCI size (occurrences):")))
        self.spinBox_reinert_size = QtWidgets.QSpinBox()
        self.spinBox_reinert_size.setRange(10, 500)
        self.spinBox_reinert_size.setValue(40)
        params.addWidget(self.spinBox_reinert_size)
        params.addWidget(QtWidgets.QLabel(_("Min frequency of active forms:")))
        self.spinBox_reinert_min_freq = QtWidgets.QSpinBox()
        self.spinBox_reinert_min_freq.setRange(1, 999)
        self.spinBox_reinert_min_freq.setValue(3)
        params.addWidget(self.spinBox_reinert_min_freq)
        params.addWidget(QtWidgets.QLabel(_("Max classes:")))
        self.spinBox_reinert_max_classes = QtWidgets.QSpinBox()
        self.spinBox_reinert_max_classes.setRange(2, 50)
        self.spinBox_reinert_max_classes.setValue(10)
        params.addWidget(self.spinBox_reinert_max_classes)
        params.addWidget(QtWidgets.QLabel(_("Min UCI per class:")))
        self.spinBox_reinert_min_size = QtWidgets.QSpinBox()
        self.spinBox_reinert_min_size.setRange(1, 200)
        self.spinBox_reinert_min_size.setValue(3)
        params.addWidget(self.spinBox_reinert_min_size)
        self.pushButton_reinert_run = QtWidgets.QPushButton(_("Calculate"))
        self.pushButton_reinert_run.setIcon(qta.icon("mdi6.play"))
        self.pushButton_reinert_run.clicked.connect(self.run_reinert)
        params.addWidget(self.pushButton_reinert_run)
        self.pushButton_reinert_csv = QtWidgets.QPushButton(_("Export CSV"))
        self.pushButton_reinert_csv.setIcon(qta.icon("mdi6.file-delimited-outline"))
        self.pushButton_reinert_csv.clicked.connect(self.export_reinert_csv)
        params.addWidget(self.pushButton_reinert_csv)
        self.pushButton_reinert_ca = QtWidgets.QPushButton(_("CA forms x classes"))
        self.pushButton_reinert_ca.setIcon(qta.icon("mdi6.chart-scatter-plot"))
        self.pushButton_reinert_ca.clicked.connect(self.show_reinert_ca)
        params.addWidget(self.pushButton_reinert_ca)
        self.pushButton_reinert_dendro = QtWidgets.QPushButton(_("Dendrogram"))
        self.pushButton_reinert_dendro.setIcon(qta.icon("mdi6.chart-tree"))
        self.pushButton_reinert_dendro.clicked.connect(self.show_reinert_dendrogram)
        params.addWidget(self.pushButton_reinert_dendro)
        layout.addLayout(params)

        self.label_reinert_info = QtWidgets.QLabel("")
        self.label_reinert_info.setWordWrap(True)
        layout.addWidget(self.label_reinert_info)

        splitter = QtWidgets.QSplitter()
        self.treeWidget_reinert = QtWidgets.QTreeWidget()
        self.treeWidget_reinert.setColumnCount(4)
        self.treeWidget_reinert.setHeaderLabels([_("Class"), _("UCI"), "chi2", _("Characteristic forms")])
        self.treeWidget_reinert.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.treeWidget_reinert.itemClicked.connect(self.reinert_class_selected)
        splitter.addWidget(self.treeWidget_reinert)
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.tableWidget_reinert_profile = QtWidgets.QTableWidget()
        self.tableWidget_reinert_profile.setColumnCount(4)
        self.tableWidget_reinert_profile.setHorizontalHeaderLabels(
            [_("Form"), _("Frequency"), "chi2", _("Signed value")])
        self.tableWidget_reinert_profile.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        right_layout.addWidget(self.tableWidget_reinert_profile)
        right_layout.addWidget(QtWidgets.QLabel(_("Most representative UCI:")))
        self.textBrowser_reinert_uci = QtWidgets.QTextBrowser()
        right_layout.addWidget(self.textBrowser_reinert_uci)
        splitter.addWidget(right)
        splitter.setSizes([350, 550])
        layout.addWidget(splitter)
        self.tabWidget.addTab(self.tab_reinert, _("Reinert classification"))
        self.reinert_result = None

    def run_reinert(self):
        """ Reinert CHD on the corpus: UCI segmentation, forms x UCI matrix of the
        active forms, then top-down dichotomic classification maximizing the
        chi-square between classes. """

        if not self.get_segments():  # always rebuild: the selection may have changed
            return
        if not self.segments:
            Message(self.app, _("Nothing found"), _("No coded segments or documents found")).exec()
            return
        try:
            self.reinert_result = reinert_from_segments(
                self.segments,
                size=self.spinBox_reinert_size.value(),
                min_freq=self.spinBox_reinert_min_freq.value(),
                max_classes=self.spinBox_reinert_max_classes.value(),
                min_class_size=self.spinBox_reinert_min_size.value(),
                language=self.comboBox_language.currentText(),
                stem=self.checkBox_stem.isChecked(),
                custom_stopwords_path=self.lineEdit_stopwords.text() or None,
            )
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return
        result = self.reinert_result
        self.treeWidget_reinert.clear()
        for cls in result["classes"]:
            top_forms = ", ".join(p["forme"] for p in cls["profile"][:5])
            item = QtWidgets.QTreeWidgetItem([f"class {cls['id']}", str(cls["size"]),
                                              f"{cls['chi2']:.2f}", top_forms])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, cls["id"])
            self.treeWidget_reinert.addTopLevelItem(item)
        self.treeWidget_reinert.resizeColumnToContents(0)
        self.label_reinert_info.setText(
            _("Classes: ") + str(result["n_classes"])
            + " | " + _("UCI: ") + str(len(result["uci_texts"]))
            + " | chi2 = " + f"{result['chi2']:.2f}" + " (df = " + str(result["df"])
            + ", " + _("chi2/df ratio: ") + f"{result['chi2_ratio']:.3f}" + ")")
        msg = _("Reinert classification: ") + str(result["n_classes"]) + " " + _("classes")
        self.parent_textEdit.append(msg)

    def reinert_class_selected(self, item, _column):
        class_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if self.reinert_result is None or class_id is None:
            return
        cls = next((c for c in self.reinert_result["classes"] if c["id"] == class_id), None)
        if cls is None:
            return
        self.tableWidget_reinert_profile.setRowCount(len(cls["profile"]))
        for row, p in enumerate(cls["profile"]):
            values = [p["forme"], p["frequence"], round(p["chi2"], 4), round(p["valeur"], 4)]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if col == 3 and p["valeur"] != 0:
                    cell.setForeground(QtGui.QBrush(QtGui.QColor("#0a7d00" if p["valeur"] > 0 else "#b00000")))
                self.tableWidget_reinert_profile.setItem(row, col, cell)
        self.tableWidget_reinert_profile.resizeColumnsToContents()
        self.textBrowser_reinert_uci.setPlainText(
            "\n\n".join(rep["text"] for rep in cls["representative_ucis"]))

    def export_reinert_csv(self):
        if self.reinert_result is None:
            self.run_reinert()
        if self.reinert_result is None:
            return
        e = ExportDirectoryPathDialog(self.app, "Reinert_classification.csv")
        filepath = e.filepath
        if filepath is None:
            return
        result = self.reinert_result
        with open(filepath, "w", encoding="utf-8-sig", newline="") as file_:
            writer = csv.writer(file_)
            writer.writerow([_("Classes"), result["n_classes"]])
            writer.writerow(["chi2", round(result["chi2"], 6), "df", result["df"],
                             _("chi2/df ratio"), round(result["chi2_ratio"], 6)])
            writer.writerow([])
            writer.writerow([_("Class"), _("UCI"), "chi2", _("Characteristic forms")])
            for cls in result["classes"]:
                writer.writerow([f"class {cls['id']}", cls["size"], round(cls["chi2"], 6),
                                 " | ".join(f"{p['forme']} ({p['valeur']:.2f})" for p in cls["profile"][:20])])
            writer.writerow([])
            writer.writerow([_("Class"), _("Form"), _("Frequency"), "chi2", _("Signed value")])
            for cls in result["classes"]:
                for p in cls["profile"]:
                    writer.writerow([f"class {cls['id']}", p["forme"], p["frequence"],
                                     round(p["chi2"], 6), round(p["valeur"], 6)])
            writer.writerow([])
            writer.writerow([_("Class"), _("Representative UCI")])
            for cls in result["classes"]:
                for rep in cls["representative_ucis"]:
                    writer.writerow([f"class {cls['id']}", rep["text"]])
        msg = _("Reinert classification exported to: ") + filepath
        Message(self.app, _("CSV export"), msg).exec()
        self.parent_textEdit.append(msg)

    def show_reinert_dendrogram(self):
        """ Show the dendrogram of the CHD binary tree (leaves = classes, internal
        nodes at height = chi2 of the split) in a non-blocking matplotlib window. """

        if self.reinert_result is None:
            self.run_reinert()
        if self.reinert_result is None:
            return
        figure = draw_dendrogram(self.reinert_result)
        dialog = DialogFigure(self.app, figure, _("Reinert classification dendrogram"))
        dialog.show()
        self._reinert_dendro_dialog = dialog

    def show_reinert_ca(self):
        """ Show the correspondence analysis of forms x classes in a non-blocking
        matplotlib window, with PNG export. """

        if self.reinert_result is None:
            self.run_reinert()
        if self.reinert_result is None:
            return
        figure = plot_ca(self.reinert_result["ca"], axes=(0, 1))
        dialog = DialogFigure(self.app, figure, _("Reinert classification: CA forms x classes"))
        dialog.show()
        self._reinert_ca_dialog = dialog
        self._reinert_ca_figure = figure


    # --- BERTopic tab (BERT-based topic modeling) ---

    def _build_bertopic_tab(self):
        self.tab_bertopic = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tab_bertopic)

        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel(_("Unit of analysis:")))
        self.comboBox_bertopic_unit = QtWidgets.QComboBox()
        self.comboBox_bertopic_unit.addItem(_("Coded segments"), "segments")
        self.comboBox_bertopic_unit.addItem(_("Whole documents"), "documents")
        self.comboBox_bertopic_unit.addItem(_("UCI (~40 occurrences)"), "uci")
        params.addWidget(self.comboBox_bertopic_unit)
        params.addWidget(QtWidgets.QLabel(_("Embedding model:")))
        self.comboBox_bertopic_model = QtWidgets.QComboBox()
        self.comboBox_bertopic_model.setEditable(True)
        self.comboBox_bertopic_model.addItems([DEFAULT_MODEL, AI_MODEL])
        params.addWidget(self.comboBox_bertopic_model, 1)
        params.addWidget(QtWidgets.QLabel(_("Min documents per topic:")))
        self.spinBox_bertopic_min_size = QtWidgets.QSpinBox()
        self.spinBox_bertopic_min_size.setRange(2, 500)
        self.spinBox_bertopic_min_size.setValue(5)
        params.addWidget(self.spinBox_bertopic_min_size)
        params.addWidget(QtWidgets.QLabel(_("Top words per topic:")))
        self.spinBox_bertopic_top_words = QtWidgets.QSpinBox()
        self.spinBox_bertopic_top_words.setRange(3, 50)
        self.spinBox_bertopic_top_words.setValue(10)
        params.addWidget(self.spinBox_bertopic_top_words)
        self.pushButton_bertopic_run = QtWidgets.QPushButton(_("Calculate"))
        self.pushButton_bertopic_run.setIcon(qta.icon("mdi6.play"))
        self.pushButton_bertopic_run.clicked.connect(self.run_bertopic)
        params.addWidget(self.pushButton_bertopic_run)
        self.pushButton_bertopic_chart = QtWidgets.QPushButton(_("Topic sizes"))
        self.pushButton_bertopic_chart.setIcon(qta.icon("mdi6.chart-bar"))
        self.pushButton_bertopic_chart.clicked.connect(self.show_bertopic_chart)
        params.addWidget(self.pushButton_bertopic_chart)
        self.pushButton_bertopic_csv = QtWidgets.QPushButton(_("Export CSV"))
        self.pushButton_bertopic_csv.setIcon(qta.icon("mdi6.file-delimited-outline"))
        self.pushButton_bertopic_csv.clicked.connect(self.export_bertopic_csv)
        params.addWidget(self.pushButton_bertopic_csv)
        layout.addLayout(params)

        dist_params = QtWidgets.QHBoxLayout()
        dist_params.addWidget(QtWidgets.QLabel(_("Distribution by variable:")))
        self.comboBox_bertopic_variable = QtWidgets.QComboBox()
        self._fill_variable_combo(self.comboBox_bertopic_variable)
        dist_params.addWidget(self.comboBox_bertopic_variable, 1)
        self.pushButton_bertopic_dist = QtWidgets.QPushButton(_("Topics x variable chart"))
        self.pushButton_bertopic_dist.setIcon(qta.icon("mdi6.chart-bar-stacked"))
        self.pushButton_bertopic_dist.clicked.connect(self.show_bertopic_distribution)
        dist_params.addWidget(self.pushButton_bertopic_dist)
        layout.addLayout(dist_params)

        self.label_bertopic_info = QtWidgets.QLabel("")
        self.label_bertopic_info.setWordWrap(True)
        layout.addWidget(self.label_bertopic_info)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.tableWidget_bertopic = QtWidgets.QTableWidget()
        self.tableWidget_bertopic.setColumnCount(4)
        self.tableWidget_bertopic.setHorizontalHeaderLabels(
            [_("Topic"), _("Size"), _("Top words"), _("Representative segment")])
        self.tableWidget_bertopic.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.tableWidget_bertopic)
        self.tableWidget_bertopic_dist = QtWidgets.QTableWidget()
        self.tableWidget_bertopic_dist.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        splitter.addWidget(self.tableWidget_bertopic_dist)
        splitter.setSizes([400, 200])
        layout.addWidget(splitter)
        self.tabWidget.addTab(self.tab_bertopic, "BERTopic")
        self.bertopic_result = None
        self.bertopic_distribution = None

    def run_bertopic(self):
        """ BERTopic-style analysis of the corpus: BERT embeddings
        (sentence-transformers), clustering, c-TF-IDF topic words. """

        if not self.get_segments():  # always rebuild: the selection may have changed
            return
        if not self.segments:
            Message(self.app, _("Nothing found"), _("No coded segments or documents found")).exec()
            return
        model_name = self.comboBox_bertopic_model.currentText().strip() or DEFAULT_MODEL
        unit = self.comboBox_bertopic_unit.currentData()
        if unit == "documents":
            from .irastats.corpus import build_document_segments
            segments = build_document_segments(self.app.conn, file_ids=self.file_ids or None)
        elif unit == "uci":
            from .irastats.reinert import build_uci_segments
            segments = build_uci_segments(self.segments, size=40)
        else:
            segments = self.segments
        if not segments:
            Message(self.app, _("Nothing found"), _("No coded segments or documents found")).exec()
            return
        try:
            self.bertopic_result = bertopic_analysis(
                segments,
                model_name=model_name,
                min_cluster_size=self.spinBox_bertopic_min_size.value(),
                top_n=self.spinBox_bertopic_top_words.value(),
                language=self.comboBox_language.currentText(),
                stem=self.checkBox_stem.isChecked(),
                custom_stopwords_path=self.lineEdit_stopwords.text() or None,
            )
        except ImportError as err:
            Message(self.app, _("BERT embeddings unavailable"), str(err), "warning").exec()
            return
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return
        result = self.bertopic_result
        self.tableWidget_bertopic.setRowCount(len(result["topics"]))
        for row, topic in enumerate(result["topics"]):
            words = ", ".join(f"{w} ({s:.3f})" for w, s in topic["top_words"])
            rep = topic["representative_texts"][0][:120] if topic["representative_texts"] else ""
            values = [f"topic {topic['topic']}", topic["size"], words, rep]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_bertopic.setItem(row, col, item)
        self.tableWidget_bertopic.resizeColumnsToContents()
        self.label_bertopic_info.setText(
            _("Documents: ") + str(result["n_docs"]) + " | " + _("Topics: ") + str(result["n_topics"])
            + " | " + _("Noise documents: ") + str(result["n_noise"]) + " | " + _("Unit: ")
            + self.comboBox_bertopic_unit.currentText() + " | " + _("Model: ") + result["model"])
        variable = self.comboBox_bertopic_variable.currentData()
        self.bertopic_distribution = None
        if variable:
            self.bertopic_distribution = topic_by_variable(
                result["labels"], [s["variables"] for s in segments], variable)
            modalities, topic_ids, counts = self.bertopic_distribution
            self.tableWidget_bertopic_dist.setColumnCount(1 + len(topic_ids))
            self.tableWidget_bertopic_dist.setHorizontalHeaderLabels(
                [variable] + [f"topic {topic}" for topic in topic_ids])
            self.tableWidget_bertopic_dist.setRowCount(len(modalities))
            for i, modality in enumerate(modalities):
                item = QtWidgets.QTableWidgetItem(modality)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_bertopic_dist.setItem(i, 0, item)
                for j in range(len(topic_ids)):
                    cell = QtWidgets.QTableWidgetItem(str(int(counts[i, j])))
                    cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    self.tableWidget_bertopic_dist.setItem(i, 1 + j, cell)
            self.tableWidget_bertopic_dist.resizeColumnsToContents()
        msg = "BERTopic: " + str(result["n_topics"]) + " " + _("topics") + " (" + model_name + ")"
        self.parent_textEdit.append(msg)

    def show_bertopic_chart(self):
        """ Bar chart of the topic sizes in a non-blocking matplotlib window. """

        if self.bertopic_result is None:
            self.run_bertopic()
        if self.bertopic_result is None:
            return
        figure = plot_topic_sizes(self.bertopic_result)
        dialog = DialogFigure(self.app, figure, "BERTopic: " + _("topic sizes"))
        dialog.show()
        self._bertopic_chart_dialog = dialog

    def show_bertopic_distribution(self):
        """ Stacked bar chart of the topic distribution per modality of the selected
        variable (code, case, document, attribute) in a non-blocking window. """

        if self.bertopic_result is None:
            self.run_bertopic()
        if self.bertopic_result is None or self.bertopic_distribution is None:
            Message(self.app, _("No variable"), _("Select a partition variable")).exec()
            return
        modalities, topic_ids, counts = self.bertopic_distribution
        figure = plot_topic_distribution(modalities, topic_ids, counts)
        dialog = DialogFigure(self.app, figure, "BERTopic: " + _("topic distribution"))
        dialog.show()
        self._bertopic_dist_dialog = dialog

    def export_bertopic_csv(self):
        if self.bertopic_result is None:
            self.run_bertopic()
        if self.bertopic_result is None:
            return
        e = ExportDirectoryPathDialog(self.app, "BERTopic_topics.csv")
        filepath = e.filepath
        if filepath is None:
            return
        result = self.bertopic_result
        with open(filepath, "w", encoding="utf-8-sig", newline="") as file_:
            writer = csv.writer(file_)
            writer.writerow([_("Model"), result["model"]])
            writer.writerow([_("Unit of analysis"), self.comboBox_bertopic_unit.currentText()])
            writer.writerow([_("Documents"), result["n_docs"], _("Topics"), result["n_topics"],
                             _("Noise documents"), result["n_noise"]])
            writer.writerow([])
            writer.writerow([_("Topic"), _("Size"), _("Top words"), _("Representative segment")])
            for topic in result["topics"]:
                words = " | ".join(f"{w} ({s:.4f})" for w, s in topic["top_words"])
                rep = topic["representative_texts"][0] if topic["representative_texts"] else ""
                writer.writerow([f"topic {topic['topic']}", topic["size"], words, rep])
            if self.bertopic_distribution is not None:
                variable = self.comboBox_bertopic_variable.currentData()
                modalities, topic_ids, counts = self.bertopic_distribution
                writer.writerow([])
                writer.writerow([_("Distribution by variable") + ": " + variable]
                                + [f"topic {topic}" for topic in topic_ids])
                for i, modality in enumerate(modalities):
                    writer.writerow([modality] + [int(c) for c in counts[i]])
        msg = _("BERTopic topics exported to: ") + filepath
        Message(self.app, _("CSV export"), msg).exec()
        self.parent_textEdit.append(msg)


    # --- Similarity graph tab ---

    def _build_similarity_tab(self):
        self.tab_similarity = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tab_similarity)

        params = QtWidgets.QHBoxLayout()
        params.addWidget(QtWidgets.QLabel(_("Association measure:")))
        self.comboBox_sim_method = QtWidgets.QComboBox()
        self.comboBox_sim_method.addItem(_("Jaccard index (default)"), "jaccard")
        self.comboBox_sim_method.addItem("chi2 (phi-squared)", "chi2")
        params.addWidget(self.comboBox_sim_method)
        params.addWidget(QtWidgets.QLabel(_("Minimum frequency:")))
        self.spinBox_sim_min_freq = QtWidgets.QSpinBox()
        self.spinBox_sim_min_freq.setRange(1, 9999)
        self.spinBox_sim_min_freq.setValue(1)
        params.addWidget(self.spinBox_sim_min_freq)
        params.addWidget(QtWidgets.QLabel(_("Edge threshold:")))
        self.doubleSpinBox_sim_threshold = QtWidgets.QDoubleSpinBox()
        self.doubleSpinBox_sim_threshold.setRange(0.0, 1.0)
        self.doubleSpinBox_sim_threshold.setSingleStep(0.05)
        self.doubleSpinBox_sim_threshold.setDecimals(3)
        self.doubleSpinBox_sim_threshold.setValue(0.2)
        params.addWidget(self.doubleSpinBox_sim_threshold)
        self.checkBox_sim_communities = QtWidgets.QCheckBox(_("Detect communities (Louvain)"))
        self.checkBox_sim_communities.setChecked(True)
        params.addWidget(self.checkBox_sim_communities)
        params.addWidget(QtWidgets.QLabel(_("Halo:")))
        self.comboBox_sim_halo = QtWidgets.QComboBox()
        self.comboBox_sim_halo.addItem("")
        params.addWidget(self.comboBox_sim_halo)
        self.pushButton_sim_run = QtWidgets.QPushButton(_("Calculate"))
        self.pushButton_sim_run.setIcon(qta.icon("mdi6.play"))
        self.pushButton_sim_run.clicked.connect(self.run_similarity)
        params.addWidget(self.pushButton_sim_run)
        self.pushButton_sim_png = QtWidgets.QPushButton(_("Export PNG"))
        self.pushButton_sim_png.setIcon(qta.icon("mdi6.image-outline"))
        self.pushButton_sim_png.clicked.connect(self.export_similarity_png)
        params.addWidget(self.pushButton_sim_png)
        layout.addLayout(params)

        self.label_sim_info = QtWidgets.QLabel("")
        self.label_sim_info.setWordWrap(True)
        layout.addWidget(self.label_sim_info)
        self.textBrowser_sim = QtWidgets.QTextBrowser()
        layout.addWidget(self.textBrowser_sim)
        self.tabWidget.addTab(self.tab_similarity, _("Similarity graph"))
        self.similarity_graph = None
        self.similarity_figure = None
        self.similarity_communities = []


    def _compute_similarity(self):
        """ Compute the similarity graph, communities and a fresh Figure.
        Returns (graph, communities, figure) or None on error. A fresh Figure is
        returned each time because the Figure shown in a DialogFigure cannot be
        saved once its Qt canvas has been closed/deleted. """

        table = self.get_lexical_table(min_freq=1)
        if table is None:
            return None
        try:
            labels, cooc, doc_freq, freq = cooccurrence(
                table, min_freq=self.spinBox_sim_min_freq.value())
            sim = similarity_matrix(labels, cooc, doc_freq, len(table.segment_texts),
                                    method=self.comboBox_sim_method.currentData())
            graph = build_graph(labels, sim, freq,
                                threshold=self.doubleSpinBox_sim_threshold.value())
            communities = []
            if self.checkBox_sim_communities.isChecked():
                communities = detect_communities(graph, seed=42)
            halo = self.comboBox_sim_halo.currentText() or None
            figure = draw_similarity_graph(graph, halo=halo)
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return None
        return graph, communities, figure

    def run_similarity(self):
        """ Build the co-occurrence similarity graph and show it in a non-blocking
        matplotlib window. """

        computed = self._compute_similarity()
        if computed is None:
            return
        self.similarity_graph, self.similarity_communities, self.similarity_figure = computed
        graph = self.similarity_graph
        edges = sorted(graph.edges(data=True), key=lambda e: -e[2]["weight"])[:20]
        lines = [f"{u} - {v}: {data['weight']:.3f}" for u, v, data in edges]
        info = _("Nodes: ") + str(graph.number_of_nodes()) + " | " + _("Edges: ") + str(graph.number_of_edges())
        if self.similarity_communities:
            info += " | " + _("Communities: ") + str(len(self.similarity_communities))
            for i, community in enumerate(self.similarity_communities):
                lines.append(f"community {i + 1}: " + ", ".join(sorted(community)))
        self.textBrowser_sim.setPlainText("\n".join(lines))
        self.label_sim_info.setText(info)
        # refill the halo combo with the graph forms, keeping the current selection if possible
        current_halo = self.comboBox_sim_halo.currentText()
        freqs = nx.get_node_attributes(graph, "freq")
        self.comboBox_sim_halo.clear()
        self.comboBox_sim_halo.addItem("")
        for node in sorted(graph.nodes, key=lambda n: -freqs.get(n, 0)):
            self.comboBox_sim_halo.addItem(node)
        if current_halo:
            index = self.comboBox_sim_halo.findText(current_halo)
            if index >= 0:
                self.comboBox_sim_halo.setCurrentIndex(index)
        msg = _("Similarity graph: ") + str(graph.number_of_nodes()) + " " + _("nodes") + ", " \
            + str(graph.number_of_edges()) + " " + _("edges")
        self.parent_textEdit.append(msg)
        dialog = DialogFigure(self.app, self.similarity_figure, _("Similarity graph"))
        dialog.show()
        self._similarity_dialog = dialog  # keep a reference


    def export_similarity_png(self):
        # recompute a fresh figure: the one shown in a closed DialogFigure has a
        # deleted Qt canvas and cannot be saved again
        computed = self._compute_similarity()
        if computed is None:
            return
        figure = computed[2]
        e = ExportDirectoryPathDialog(self.app, "Similarity_graph.png")
        filepath = e.filepath
        if filepath is None:
            return
        figure.savefig(filepath, dpi=150)
        msg = _("Similarity graph exported to: ") + filepath
        Message(self.app, _("PNG export"), msg).exec()
        self.parent_textEdit.append(msg)

class DialogFigure(QtWidgets.QDialog):
    """ Non-blocking dialog showing a matplotlib Figure (canvas + Save PNG button). """

    def __init__(self, app, figure, title=""):
        QtWidgets.QDialog.__init__(self)
        self.app = app
        self.figure = figure
        self.setWindowTitle(title)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        self.canvas = FigureCanvas(figure)
        layout.addWidget(self.canvas)
        buttons = QtWidgets.QHBoxLayout()
        self.pushButton_save = QtWidgets.QPushButton(_("Save PNG"))
        self.pushButton_save.setIcon(qta.icon("mdi6.image-outline"))
        self.pushButton_save.clicked.connect(self.save_png)
        buttons.addWidget(self.pushButton_save)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.resize(900, 700)

    def save_png(self):
        filepath, _selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, _("Save figure"), self.app.settings.get("directory", ""), "PNG (*.png)")
        if filepath:
            self.figure.savefig(filepath, dpi=150)
            Message(self.app, _("Figure saved"), _("Figure saved to: ") + filepath).exec()
