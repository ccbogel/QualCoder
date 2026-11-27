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

from .GUI.ui_dialog_text_stats import Ui_DialogTextStats
from .helpers import ExportDirectoryPathDialog, Message
from .information import DialogInformation, lexicometry_information
from .irastats import (
    available_variables,
    build_document_segments,
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
from .irastats.report_html import descstats_html, specificites_html, statistics_html
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
    a GUI. The UI is defined in src/GUI_UIs/ui_dialog_text_stats.ui (compiled to
    qualcoder/GUI/ui_dialog_text_stats.py with pyuic6, as the other dialogs); only the
    dynamic parts (icons, combo contents, signal connections) are set in code.
    """

    def __init__(self, app, parent_textedit):
        QtWidgets.QDialog.__init__(self)
        self.app = app
        self.parent_textEdit = parent_textedit

        self.file_ids = []
        self.case_ids = []
        self.code_ids = []
        self.segments = []
        self.lexical_table = None
        self.descstats = None
        self.specificites_results = None
        self.ca_result = None
        self.ca_figure = None
        self.reinert_result = None
        self.bertopic_result = None
        self.bertopic_distribution = None
        self.similarity_graph = None
        self.similarity_figure = None
        self.similarity_communities = []

        self.ui = Ui_DialogTextStats()
        self.ui.setupUi(self)
        # expose the widgets of the .ui as attributes (self.pushButton_...) so the
        # rest of this class keeps working unchanged
        for name, widget in vars(self.ui).items():
            if isinstance(widget, QtWidgets.QWidget):
                setattr(self, name, widget)

        self.setWindowTitle(_("Lexicometry (text statistics)"))
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)

        self._setup_icons()
        self._init_combos()
        self._connect_signals()
        self.splitter_graphs.setSizes([500, 500])
        self.splitter_reinert.setSizes([350, 550])
        self.splitter_bertopic.setSizes([400, 200])
        self.splitter_reinert_plots.setSizes([500, 500])
        self.splitter_topics_plots.setSizes([500, 500])
        # embedded matplotlib canvases (replaced on each run)
        self._sim_canvas = None
        self._ca_canvas = None
        self._reinert_dendro_canvas = None
        self._reinert_ca_canvas = None
        self._topics_canvas = None
        self._topics_dist_canvas = None
        self._popout_dialogs = []
        self._icon_only_buttons()
        # embedded in the Reports tab: do not force the main window minimum size
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                           QtWidgets.QSizePolicy.Policy.Ignored)
        self.resize(1100, 750)

    def _setup_icons(self):
        """qtawesome icons for the buttons. """

        icons = {
            "pushButton_select_files": "mdi6.file-outline",
            "pushButton_select_cases": "mdi6.account-multiple",
            "pushButton_select_codes": "mdi6.text",
            "pushButton_build_corpus": "mdi6.play",
            "pushButton_export_iramuteq": "mdi6.export",
            "pushButton_descstats_run": "mdi6.play",
            "pushButton_descstats_csv": "mdi6.file-export-outline",
            "pushButton_descstats_html": "mdi6.export",
            "pushButton_descstats_odt": "mdi6.file-document-outline",
            "pushButton_spec_csv": "mdi6.file-export-outline",
            "pushButton_spec_html": "mdi6.export",
            "pushButton_sim_run": "mdi6.play",
            "pushButton_sim_png": "mdi6.image-outline",
            "pushButton_ca_run": "mdi6.play",
            "pushButton_ca_csv": "mdi6.file-export-outline",
            "pushButton_ca_png": "mdi6.image-outline",
            "pushButton_reinert_run": "mdi6.play",
            "pushButton_reinert_csv": "mdi6.file-export-outline",
            "pushButton_reinert_ca": "mdi6.grid",
            "pushButton_reinert_dendro": "mdi6.sitemap",
            "pushButton_bertopic_run": "mdi6.play",
            "pushButton_bertopic_chart": "mdi6.chart-bar",
            "pushButton_bertopic_csv": "mdi6.file-export-outline",
            "pushButton_bertopic_dist": "mdi6.table",
            "pushButton_sim_popout": "mdi6.open-in-new",
            "pushButton_ca_popout": "mdi6.open-in-new",
            "pushButton_reinert_dendro_popout": "mdi6.open-in-new",
            "pushButton_reinert_ca_popout": "mdi6.open-in-new",
            "pushButton_bertopic_chart_popout": "mdi6.open-in-new",
            "pushButton_bertopic_dist_popout": "mdi6.open-in-new",
            "pushButton_info": "mdi6.help",
            "pushButton_info_2": "mdi6.help",
            "pushButton_info_3": "mdi6.help",
            "pushButton_info_4": "mdi6.help"
        }
        for name, icon in icons.items():
            getattr(self, name).setIcon(qta.icon(icon, options=[{'scale_factor': 1.4}]))

    def _init_combos(self):
        """Static combo contents; the partition variable combos are filled from the
        project database by _fill_variable_combo / _refresh_variable_combos. """

        self.comboBox_language.addItems(LANGUAGES)
        lang = self.app.settings.get("language", "fr")
        if lang in LANGUAGES:
            self.comboBox_language.setCurrentText(lang)
        self.comboBox_sim_method.addItem(_("Jaccard index (default)"), "jaccard")
        self.comboBox_sim_method.addItem("chi2 (phi-squared)", "chi2")
        self.comboBox_sim_halo.addItem("")
        self.comboBox_bertopic_unit.addItem(_("Coded segments"), "segments")
        self.comboBox_bertopic_unit.addItem(_("Whole documents"), "documents")
        self.comboBox_bertopic_unit.addItem(_("Initial context unit (~40 occurrences)"), "uci")
        self.comboBox_bertopic_model.addItems([DEFAULT_MODEL, AI_MODEL])
        self._fill_variable_combo(self.comboBox_stats_variable)
        self._fill_variable_combo(self.comboBox_ca_variable)
        self.comboBox_ca_variable.insertItem(0, _("Segments"), "__segments__")
        self._fill_variable_combo(self.comboBox_bertopic_variable)

    def _connect_signals(self):
        """Signal connections of the .ui widgets. """

        self.pushButton_select_files.clicked.connect(self.select_files)
        self.pushButton_select_cases.clicked.connect(self.select_cases)
        self.pushButton_select_codes.clicked.connect(self.select_codes)
        self.pushButton_build_corpus.clicked.connect(self.build_corpus)
        self.pushButton_export_iramuteq.clicked.connect(self.export_iramuteq_dialog)
        self.pushButton_descstats_run.clicked.connect(self.run_statistics)
        self.pushButton_descstats_csv.clicked.connect(self.export_descstats_csv)
        self.pushButton_descstats_html.clicked.connect(self.export_descstats_html)
        self.pushButton_descstats_odt.clicked.connect(self.export_descstats_odt)
        self.pushButton_spec_csv.clicked.connect(self.export_specificites_csv)
        self.pushButton_spec_html.clicked.connect(self.export_specificites_html)
        self.pushButton_sim_run.clicked.connect(self.run_similarity)
        self.pushButton_sim_png.clicked.connect(self.export_similarity_png)
        self.pushButton_ca_run.clicked.connect(self.run_ca)
        self.pushButton_ca_csv.clicked.connect(self.export_ca_csv)
        self.pushButton_ca_png.clicked.connect(self.export_ca_png)
        self.pushButton_reinert_run.clicked.connect(self.run_reinert)
        self.pushButton_reinert_csv.clicked.connect(self.export_reinert_csv)
        self.pushButton_reinert_ca.clicked.connect(self.show_reinert_ca)
        self.pushButton_reinert_dendro.clicked.connect(self.show_reinert_dendrogram)
        self.treeWidget_reinert.itemClicked.connect(self.reinert_class_selected)
        self.pushButton_bertopic_run.clicked.connect(self.run_bertopic)
        self.pushButton_bertopic_chart.clicked.connect(self.show_bertopic_chart)
        self.pushButton_bertopic_csv.clicked.connect(self.export_bertopic_csv)
        self.pushButton_bertopic_dist.clicked.connect(self.show_bertopic_distribution)
        self.pushButton_sim_popout.clicked.connect(self.popout_similarity)
        self.pushButton_ca_popout.clicked.connect(self.popout_ca)
        self.pushButton_reinert_dendro_popout.clicked.connect(self.popout_reinert_dendrogram)
        self.pushButton_reinert_ca_popout.clicked.connect(self.popout_reinert_ca)
        self.pushButton_bertopic_chart_popout.clicked.connect(self.popout_topics_chart)
        self.pushButton_bertopic_dist_popout.clicked.connect(self.popout_topics_distribution)
        self.pushButton_info.clicked.connect(self.analysis_information)
        self.pushButton_info_2.clicked.connect(self.analysis_information)
        self.pushButton_info_3.clicked.connect(self.analysis_information)
        self.pushButton_info_4.clicked.connect(self.analysis_information)

    def analysis_information(self):
        ui = DialogInformation(self.app, _("Text analysis"), lexicometry_information)
        ui.exec()


    def _fit_table(self, table, max_col_width: int = 500):
        """ Resize the columns to their contents but cap them at max_col_width,
        then wrap the rows so long cell texts stay readable and fit. """

        table.setWordWrap(True)
        table.resizeColumnsToContents()
        for col in range(table.columnCount()):
            if table.columnWidth(col) > max_col_width:
                table.setColumnWidth(col, max_col_width)
        table.resizeRowsToContents()

    def _embed_figure(self, placeholder_name: str, figure, canvas_attr: str):
        """Embed a matplotlib Figure in a placeholder widget of the .ui, replacing
        any previous canvas (the figures are recomputed on each run). """

        placeholder = getattr(self, placeholder_name)
        layout = placeholder.layout()
        old = getattr(self, canvas_attr, None)
        if old is not None:
            layout.removeWidget(old)
            old.deleteLater()
        canvas = FigureCanvas(figure)
        layout.addWidget(canvas)
        setattr(self, canvas_attr, canvas)

    def _popout(self, figure, title: str):
        """Open a figure in a separate non-blocking window (kept referenced). """

        dialog = DialogFigure(self.app, figure, title)
        dialog.show()
        self._popout_dialogs.append(dialog)

    def popout_similarity(self):
        computed = self._compute_similarity()
        if computed is None:
            return
        self._popout(computed[2], _("Similarity graph"))

    def popout_ca(self):
        computed = self._compute_ca()
        if computed is None:
            return
        self._popout(computed[1], _("Correspondence analysis"))

    def popout_reinert_dendrogram(self):
        if self.reinert_result is None:
            self.run_reinert()
        if self.reinert_result is None:
            return
        self._popout(draw_dendrogram(self.reinert_result), _("Reinert classification dendrogram"))

    def popout_reinert_ca(self):
        if self.reinert_result is None:
            self.run_reinert()
        if self.reinert_result is None:
            return
        self._popout(plot_ca(self.reinert_result["ca"], axes=(0, 1)),
                      _("Reinert classification: correspondence analysis (forms x classes)"))

    def popout_topics_chart(self):
        if self.bertopic_result is None:
            self.run_bertopic()
        if self.bertopic_result is None:
            return
        self._popout(plot_topic_sizes(self.bertopic_result), _("Topics") + ": " + _("topic sizes"))

    def popout_topics_distribution(self):
        if self.bertopic_result is None:
            self.run_bertopic()
        if self.bertopic_result is None or self.bertopic_distribution is None:
            return
        modalities, topic_ids, counts = self.bertopic_distribution
        self._popout(plot_topic_distribution(modalities, topic_ids, counts),
                      _("Topics") + ": " + _("topic distribution"))

    def _icon_only_buttons(self):
        """Icon-only buttons (as in Reports > Code Retrieval): the text label of
        each button moves to its tooltip, so the rows stay compact with larger
        fonts. """

        for button in self.findChildren(QtWidgets.QPushButton):
            label = button.text()
            if not label:
                continue
            tooltip = button.toolTip()
            if tooltip and label.lower() not in tooltip.lower():
                tooltip = f"{label} - {tooltip}"
            elif not tooltip:
                tooltip = label
            button.setToolTip(tooltip)
            button.setText("")

    # --- Selection (same helpers as the other Reports dialogs) ---

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
        parts.append(_("Codes: ") + (str(len(self.code_ids)) if self.code_ids else _("all (whole documents)")))
        self.label_selection.setText(" | ".join(parts))

    def get_segments(self) -> bool:
        """ Build the segment list from the current selection. Sets self.segments. """

        try:
            if self.code_ids:
                # specific codes selected: only their coded texts
                self.segments = build_segments(
                    self.app.conn,
                    file_ids=self.file_ids or None,
                    case_ids=self.case_ids or None,
                    code_ids=self.code_ids,
                )
            else:
                # no code filter (all codes): the whole documents
                # (only the file selection applies, not the case selection)
                self.segments = build_document_segments(
                    self.app.conn, file_ids=self.file_ids or None)
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

        for name in ("comboBox_stats_variable", "comboBox_ca_variable",
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

    def _fill_variable_combo(self, combo: QtWidgets.QComboBox):
        """ Fill a partition variable combo: "none" plus the corpus variables. """

        combo.clear()
        combo.addItem(_("None"), "")
        for variable in self.available_variables():
            combo.addItem(variable, variable)

    def run_descstats(self) -> bool:
        """ Compute and store the descending statistics. Returns True on success. """

        table = self.get_lexical_table(min_freq=self.spinBox_stats_min_freq.value())
        if table is None:
            return False
        variable = self.comboBox_stats_variable.currentData() or None
        try:
            self.descstats = descendant_statistics(table, variable=variable)
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return False
        msg = (_("Text statistics: ") + _("Segments: ") + str(len(table.segment_texts))
               + " | " + _("Occurrences: ") + str(self.descstats["total_occurrences"])
               + " | " + _("Forms: ") + str(self.descstats["distinct_forms"]))
        self.parent_textEdit.append(msg)
        return True

    def run_statistics(self):
        """ Calculate all the statistics (descending statistics and, when a partition
        variable is selected, the chi-square specificities) and show them in a
        single report. """

        if not self.run_descstats():
            return
        variable = self.comboBox_stats_variable.currentData() or None
        if variable:
            self.run_specificites()
        self.textBrowser_stats.setHtml(statistics_html(
            self.descstats,
            self.specificites_results if variable else None,
            variable=variable,
            p_threshold=self.doubleSpinBox_spec_p.value()))

    def _descstats_csv_rows(self):
        rows = [[_("Form"), _("Frequency"), _("%")]]
        rows += frequency_rows(self.descstats)
        rows.append([])
        rows.append([_("Hapax")])
        rows += hapax_rows(self.descstats)
        if self.descstats["by_variable"]:
            rows.append([])
            rows.append([_("Category"), _("Segments"), _("Occurrences"), _("Distinct forms")])
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
        variable = self.comboBox_stats_variable.currentData() or None
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
        variable = self.comboBox_stats_variable.currentData() or None
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

    def run_specificites(self) -> bool:
        """ Compute and store the chi-square specificities for the selected variable.
        Returns True on success. """

        variable = self.comboBox_stats_variable.currentData()
        if not variable:
            Message(self.app, _("No variable"), _("Select a partition variable")).exec()
            return False
        table = self.get_lexical_table(min_freq=self.spinBox_stats_min_freq.value())
        if table is None:
            return False
        try:
            self.specificites_results = specificities(
                table, variable,
                min_freq=self.spinBox_stats_min_freq.value(),
                p_threshold=self.doubleSpinBox_spec_p.value())
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Error"), str(err), "warning").exec()
            return False
        msg = _("Specificities: ") + str(len(self.specificites_results)) + " " + _("rows for variable ") + variable
        self.parent_textEdit.append(msg)
        return True

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
            writer.writerow([_("Form"), _("Category"), _("Count"), _("Expected count"), "chi2",
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
        variable = self.comboBox_stats_variable.currentData()
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

    def _compute_ca(self):
        """ Compute the correspondence analysis and a fresh factor-map Figure.
        Returns (result, figure) or None on error. A fresh Figure is returned each
        time because the Figure shown in a DialogFigure cannot be saved once its
        Qt canvas has been closed/deleted. """

        table = self.get_lexical_table(min_freq=self.spinBox_graph_min_freq.value())
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
        self._embed_figure("widget_ca_plot", self.ca_figure, "_ca_canvas")

    def export_ca_csv(self):
        if self.ca_result is None:
            computed = self._compute_ca()
            if computed is None:
                return
            self.ca_result, self.ca_figure = computed
        if self.ca_result is None:
            return
        e = ExportDirectoryPathDialog(self.app, "correspondence_analysis_coordinates.csv")
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
            writer.writerow([_("Category"), _("Frequency")] + [f"G{a + 1}" for a in range(n_axes)])
            for k, label in enumerate(result["col_labels"]):
                writer.writerow([label, int(result["col_freq"][k])]
                                + [round(float(result["col_coords"][k, a]), 6) for a in range(n_axes)])
        msg = _("Correspondence analysis coordinates exported to: ") + filepath
        Message(self.app, _("CSV export"), msg).exec()
        self.parent_textEdit.append(msg)

    def export_ca_png(self):
        # recompute a fresh figure: the one shown in a closed DialogFigure has a
        # deleted Qt canvas and cannot be saved again
        computed = self._compute_ca()
        if computed is None:
            return
        figure = computed[1]
        e = ExportDirectoryPathDialog(self.app, "correspondence_analysis_factor_map.png")
        filepath = e.filepath
        if filepath is None:
            return
        figure.savefig(filepath, dpi=150)
        msg = _("Correspondence analysis factor map exported to: ") + filepath
        Message(self.app, _("PNG export"), msg).exec()
        self.parent_textEdit.append(msg)

    def run_reinert(self):
        """ Reinert CHD on the corpus: initial context unit segmentation, forms x initial context unit matrix of the
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
            + " | " + _("Initial context units: ") + str(len(result["uci_texts"]))
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
            writer.writerow([_("Class"), _("Initial context unit"), "chi2", _("Characteristic forms")])
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
            writer.writerow([_("Class"), _("Representative initial context units")])
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
        self._embed_figure("widget_reinert_dendro_plot", figure, "_reinert_dendro_canvas")

    def show_reinert_ca(self):
        """ Show the correspondence analysis of forms x classes in a non-blocking
        matplotlib window, with PNG export. """

        if self.reinert_result is None:
            self.run_reinert()
        if self.reinert_result is None:
            return
        figure = plot_ca(self.reinert_result["ca"], axes=(0, 1))
        self._reinert_ca_figure = figure
        self._embed_figure("widget_reinert_ca_plot", figure, "_reinert_ca_canvas")

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
        # busy pop-up: the first run downloads the BERT model and can take minutes
        progress = QtWidgets.QProgressDialog(
            _("Loading the BERT model and computing the topics.\n"
              "The first run downloads the model and can take several minutes - please wait..."),
            "", 0, 0, self)
        progress.setWindowTitle(_("Topics"))
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QtWidgets.QApplication.processEvents()
        try:
            try:
                if unit == "documents":
                    segments = build_document_segments(self.app.conn, file_ids=self.file_ids or None)
                elif unit == "uci":
                    from .irastats.reinert import build_uci_segments
                    segments = build_uci_segments(self.segments, size=40)
                else:
                    segments = self.segments
                if not segments:
                    Message(self.app, _("Nothing found"), _("No coded segments or documents found")).exec()
                    return
                self.bertopic_result = bertopic_analysis(
                    segments,
                    model_name=model_name,
                    min_cluster_size=self.spinBox_bertopic_min_size.value(),
                    top_n=self.spinBox_bertopic_top_words.value(),
                    language=self.comboBox_language.currentText(),
                    stem=self.checkBox_stem.isChecked(),
                )
            except ImportError as err:
                logger.error(err)
                Message(self.app, _("BERT embeddings unavailable"),
                        _("BERTopic needs the sentence-transformers and torch packages "
                          "(pip install sentence-transformers torch).") + "\n" + str(err),
                        "warning").exec()
                return
            except Exception as err:
                logger.error(err)
                Message(self.app, _("Error"), str(err), "warning").exec()
                return
        finally:
            progress.close()
            QtWidgets.QApplication.processEvents()
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
        self._fit_table(self.tableWidget_bertopic)
        self.label_bertopic_info.setText(
            _("Documents: ") + str(result["n_docs"]) + " | " + _("Topics: ") + str(result["n_topics"])
            + " | " + _("Noise documents: ") + str(result["n_noise"]) + " | " + _("Unit: ")
            + self.comboBox_bertopic_unit.currentText() + " | " + _("Model: ") + result["model"])
        variable = self.comboBox_bertopic_variable.currentData()
        self.bertopic_distribution = None
        if variable:
            try:
                self.bertopic_distribution = topic_by_variable(
                    result["labels"], [s["variables"] for s in segments], variable)
            except Exception as err:
                logger.error(err)
                self.bertopic_distribution = None
            else:
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
                self._fit_table(self.tableWidget_bertopic_dist)
        msg = "BERTopic: " + str(result["n_topics"]) + " " + _("topics") + " (" + model_name + ")"
        self.parent_textEdit.append(msg)

    def show_bertopic_chart(self):
        """ Bar chart of the topic sizes in a non-blocking matplotlib window. """

        if self.bertopic_result is None:
            self.run_bertopic()
        if self.bertopic_result is None:
            return
        figure = plot_topic_sizes(self.bertopic_result)
        self._embed_figure("widget_topics_plot", figure, "_topics_canvas")

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
        self._embed_figure("widget_topics_dist_plot", figure, "_topics_dist_canvas")

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
                table, min_freq=self.spinBox_graph_min_freq.value())
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
        self._embed_figure("widget_sim_plot", self.similarity_figure, "_sim_canvas")

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
        self.pushButton_save = QtWidgets.QPushButton("")
        self.pushButton_save.setIcon(qta.icon("mdi6.image-outline"))
        self.pushButton_save.setToolTip(_("Save PNG"))
        # same square icon-button size as the .ui dialogs (32x32)
        self.pushButton_save.setMinimumSize(32, 32)
        self.pushButton_save.setMaximumSize(32, 32)
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
