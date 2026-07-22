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
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import logging
import math

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QDialog

from .helpers import Message
from .select_items import DialogSelectItems
from .GUI.ui_dialog_graph_models import Ui_DialogGraphModels

logger = logging.getLogger(__name__)

# Model index constants
MODEL_CAT_HIER = 0
MODEL_FILE_HIER = 1
MODEL_FILE_COMP = 2
MODEL_CASE_HIER = 3
MODEL_CASE_COMP = 4
MODEL_COOC_NET = 5

_DESCRIPTIONS = [
    "Category hierarchy: Categories > Subcategories > Codes > Coded segments.",
    "File > Categories > Codes hierarchy. Shows coding structure within selected files.",
    "Compare exactly 2 files side by side. Shared codes/categories appear in the center.",
    "Case > Categories > Codes hierarchy. Shows how codes are structured within selected cases.",
    "Compare exactly 2 cases side by side. Shared codes/categories appear in the center.",
    "Network of code co-occurrences with configurable overlap types and edge weights.",
]


class DialogGraphModels(QDialog):
    """
    Modal dialog to select and configure analytical graph models.
    Triggered by pushButton_graph_models in ViewGraph.
    """

    def __init__(self, app, view_graph, parent=None):
        """
        param: app : Main App
        param: view_graph : ViewGraph instance (to access scene and helper methods)
        param: parent : parent widget
        """
        super().__init__(parent)
        self.app = app
        self.view_graph = view_graph
        self.ui = Ui_DialogGraphModels()
        self.ui.setupUi(self)
        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self._cases_data = []  # Store case dicts for combobox index mapping
        self._files_data = []  # Store file dicts for combobox index mapping
        self._setup_ui()

    def _setup_ui(self):
        """
        Connect UI signals and populate comboboxes.
        """

        # Model selector items
        self.ui.comboBox_model.addItems([
            _("1. Category hierarchical"),
            _("2. File hierarchical"),
            _("3. File comparative (2 files)"),
            _("4. Case hierarchical"),
            _("5. Case comparative (2 cases)"),
            _("6. Co-occurrence network"),
        ])
        self.ui.comboBox_model.currentIndexChanged.connect(self._on_model_changed)

        # Comparison level items
        self.ui.comboBox_case_comp_level.addItems([_("Codes"), _("Categories")])
        self.ui.comboBox_file_comp_level.addItems([_("Codes"), _("Categories")])

        # Agrupar las casillas de co-ocurrencia para que se comporten como "Radio Buttons" (selección única)
        self.cooc_group = QtWidgets.QButtonGroup(self)
        self.cooc_group.setExclusive(True)
        self.cooc_group.addButton(self.ui.checkBox_overlap)
        self.cooc_group.addButton(self.ui.checkBox_inclusion)
        self.cooc_group.addButton(self.ui.checkBox_exact)
        self.cooc_group.addButton(self.ui.checkBox_proximity)
        self.ui.checkBox_overlap.setChecked(True) # Asegura que siempre haya una seleccionada por defecto

        # Proximity checkbox enables/disables spinbox
        self.ui.checkBox_proximity.toggled.connect(self.ui.spinBox_proximity.setEnabled)

        # Buttons
        self.ui.pushButton_generate.clicked.connect(self._on_generate)
        self.ui.pushButton_cancel.clicked.connect(self.reject)

        # Populate case comboboxes for comparative model
        self._cases_data = self._get_cases()
        self._populate_case_combos()
        self.ui.comboBox_case_a.currentIndexChanged.connect(self._on_case_a_changed)

        # Populate file comboboxes for comparative model
        self._files_data = self._get_files()
        self._populate_file_combos()
        self.ui.comboBox_file_a.currentIndexChanged.connect(self._on_file_a_changed)

        # Init description
        self._on_model_changed(0)

    def _populate_case_combos(self):
        """
        Fill both case comboboxes with all cases.
        """
        self.ui.comboBox_case_a.blockSignals(True)
        self.ui.comboBox_case_b.blockSignals(True)
        self.ui.comboBox_case_a.clear()
        self.ui.comboBox_case_b.clear()
        for c in self._cases_data:
            self.ui.comboBox_case_a.addItem(c['name'], c['id'])
            self.ui.comboBox_case_b.addItem(c['name'], c['id'])
        self.ui.comboBox_case_a.blockSignals(False)
        self.ui.comboBox_case_b.blockSignals(False)
        # Trigger filter for case B
        if self._cases_data:
            self._on_case_a_changed(0)

    def _on_case_a_changed(self, index):
        """
        Filter case B combobox to exclude the case selected in A.
        """
        selected_id = self.ui.comboBox_case_a.currentData()
        self.ui.comboBox_case_b.blockSignals(True)
        self.ui.comboBox_case_b.clear()
        for c in self._cases_data:
            if c['id'] != selected_id:
                self.ui.comboBox_case_b.addItem(c['name'], c['id'])
        self.ui.comboBox_case_b.blockSignals(False)

    def _populate_file_combos(self):
        """
        Fill both file comboboxes with all files
        """
        self.ui.comboBox_file_a.blockSignals(True)
        self.ui.comboBox_file_b.blockSignals(True)
        self.ui.comboBox_file_a.clear()
        self.ui.comboBox_file_b.clear()
        for f in self._files_data:
            self.ui.comboBox_file_a.addItem(f['name'], f['id'])
            self.ui.comboBox_file_b.addItem(f['name'], f['id'])
        self.ui.comboBox_file_a.blockSignals(False)
        self.ui.comboBox_file_b.blockSignals(False)
        if self._files_data:
            self._on_file_a_changed(0)

    def _on_file_a_changed(self, index):
        """
        Filter file B combobox to exclude the file selected in A.
        """
        selected_id = self.ui.comboBox_file_a.currentData()
        self.ui.comboBox_file_b.blockSignals(True)
        self.ui.comboBox_file_b.clear()
        for f in self._files_data:
            if f['id'] != selected_id:
                self.ui.comboBox_file_b.addItem(f['name'], f['id'])
        self.ui.comboBox_file_b.blockSignals(False)

    def accept(self):
        """
        Limpia el lienzo antes de generar el nuevo modelo.
        """
        self.view_graph.scene.clear()
        self.view_graph.scene.setSceneRect(QtCore.QRectF(0, 0, 990, 650))
        self.view_graph.scene.set_width(990)
        self.view_graph.scene.set_height(650)
        self.view_graph.ui.label_loaded_graph.setText("")
        self.view_graph.ui.label_loaded_graph.setToolTip("")
        # el modelo generado es un grafo nuevo.
        self.view_graph.loaded_graph = None
        # el historial de undo es por grafo; un modelo nuevo lo reinicia.
        if hasattr(self.view_graph, '_undo_stack'):
            self.view_graph._undo_stack.clear()
        super().accept()

    # Config panel builders

    def _build_config_case_hierarchical(self):
        """
        Panel 0: Case Hierarchical and segment limit
        """
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        vl.addWidget(QtWidgets.QLabel(_("Max coded segments per code (0 = none):")))
        self.spin_case_hier_limit = QtWidgets.QSpinBox()
        self.spin_case_hier_limit.setRange(0, 500)
        self.spin_case_hier_limit.setValue(5)
        vl.addWidget(self.spin_case_hier_limit)
        vl.addStretch()
        self.config_stack.addWidget(w)

    def _build_config_case_comparative(self):
        """
        Panel 1: Case Comparative - comparison level.
        """
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        vl.addWidget(QtWidgets.QLabel(_("Comparison level:")))
        self.combo_case_comp_level = QtWidgets.QComboBox()
        self.combo_case_comp_level.addItems([_("Codes"), _("Categories")])
        vl.addWidget(self.combo_case_comp_level)
        vl.addWidget(QtWidgets.QLabel(_("You will select 2 cases after clicking Generate.")))
        vl.addStretch()
        self.config_stack.addWidget(w)

    def _build_config_file_hierarchical(self):
        """
        Panel 2: File Hierarchical and segment limit.
        """
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        vl.addWidget(QtWidgets.QLabel(_("Max coded segments per code (0 = none):")))
        self.spin_file_hier_limit = QtWidgets.QSpinBox()
        self.spin_file_hier_limit.setRange(0, 500)
        self.spin_file_hier_limit.setValue(5)
        vl.addWidget(self.spin_file_hier_limit)
        vl.addStretch()
        self.config_stack.addWidget(w)

    def _build_config_file_comparative(self):
        """
        Panel 3: File comparative, comparison level.
        """
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        vl.addWidget(QtWidgets.QLabel(_("Comparison level:")))
        self.combo_file_comp_level = QtWidgets.QComboBox()
        self.combo_file_comp_level.addItems([_("Codes"), _("Categories")])
        vl.addWidget(self.combo_file_comp_level)
        vl.addWidget(QtWidgets.QLabel(_("You will select 2 files after clicking Generate.")))
        vl.addStretch()
        self.config_stack.addWidget(w)

    def _build_config_cooccurrence_net(self):
        """
        Panel 4: Co-occurrence network, type checkboxes + proximity threshold.
        """
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        vl.addWidget(QtWidgets.QLabel(_("Co-occurrence types:")))
        self.chk_overlap = QtWidgets.QCheckBox(_("Overlap (partial intersection)"))
        self.chk_overlap.setChecked(True)
        vl.addWidget(self.chk_overlap)
        self.chk_inclusion = QtWidgets.QCheckBox(_("Inclusion (one inside another)"))
        vl.addWidget(self.chk_inclusion)
        self.chk_exact = QtWidgets.QCheckBox(_("Exact (identical span)"))
        vl.addWidget(self.chk_exact)
        self.chk_proximity = QtWidgets.QCheckBox(_("Proximity (within N characters)"))
        vl.addWidget(self.chk_proximity)
        h_prox = QtWidgets.QHBoxLayout()
        h_prox.addWidget(QtWidgets.QLabel(_("  Proximity threshold (characters):")))
        self.spin_proximity = QtWidgets.QSpinBox()
        self.spin_proximity.setRange(1, 5000)
        self.spin_proximity.setValue(100)
        self.spin_proximity.setEnabled(False)
        h_prox.addWidget(self.spin_proximity)
        vl.addLayout(h_prox)
        self.chk_proximity.toggled.connect(self.spin_proximity.setEnabled)
        self.chk_cooc_cats = QtWidgets.QCheckBox(_("Show categories as parent nodes"))
        vl.addWidget(self.chk_cooc_cats)
        vl.addStretch()
        self.config_stack.addWidget(w)

    def _build_config_cooccurrence_seg(self):
        """
        Panel 5: Co-occurrence segment-centered and segment limit.
        """
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        vl.addWidget(QtWidgets.QLabel(_("Select 2 or more categories after clicking Generate.")))
        vl.addWidget(QtWidgets.QLabel(_("Max segments to display:")))
        self.spin_seg_limit = QtWidgets.QSpinBox()
        self.spin_seg_limit.setRange(1, 40)
        self.spin_seg_limit.setValue(5)
        vl.addWidget(self.spin_seg_limit)
        vl.addStretch()
        self.config_stack.addWidget(w)

    # Event handlers

    def _on_model_changed(self, index):
        """
        Update description and config panel when model selection changes.
        """
        _page_map = {0: 5, 1: 2, 2: 3, 3: 0, 4: 1, 5: 4}
        self.ui.stackedWidget.setCurrentIndex(_page_map.get(index, 0))
        if 0 <= index < len(_DESCRIPTIONS):
            self.ui.label_description.setText(_(_DESCRIPTIONS[index]))

    def _on_generate(self):
        """
        Dispatch to the appropriate model builder.
        """
        index = self.ui.comboBox_model.currentIndex()
        try:
            if index == MODEL_CAT_HIER:
                self._generate_category_hierarchical()
            elif index == MODEL_FILE_HIER:
                self._generate_file_hierarchical()
            elif index == MODEL_FILE_COMP:
                self._generate_file_comparative()
            elif index == MODEL_CASE_HIER:
                self._generate_case_hierarchical()
            elif index == MODEL_CASE_COMP:
                self._generate_case_comparative()
            elif index == MODEL_COOC_NET:
                self._generate_cooccurrence_network()
        except Exception as e:
            logger.error(f"Error generating graph model {index}: {e}")
            Message(self.app, _("Error"), str(e)).exec()

    # Shared helper utilities

    def _get_cases(self):
        """
        Get list of cases from database.
        return: list of dict with keys 'id', 'name'
        """
        cur = self.app.conn.cursor()
        cur.execute("select caseid, name from cases order by name asc")
        return [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]

    def _get_files(self):
        """
        Get list of text files from database.
        return: list of dict with keys 'id', 'name'
        """
        cur = self.app.conn.cursor()
        cur.execute("select id, name from source order by name asc")
        return [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]

    def _get_codes_for_case(self, case_id):
        """
        Get distinct code cids applied to text, image, and A/V segments linked to a case.
        param: case_id : Integer
        return: set of cid integers
        """  # extended to image and A/V codings
        cur = self.app.conn.cursor()
        # Text segments inside case range
        sql_text = ("select distinct ct.cid from code_text ct "
                    "join case_text cas on cas.fid = ct.fid "
                    "and ct.pos0 >= cas.pos0 and ct.pos1 <= cas.pos1 "
                    "where cas.caseid=?")
        # Image codings: case_text links a case to a file; if the file has image codings,
        # consider them belonging to that case (no positional sub-range for images).
        sql_image = ("select distinct ci.cid from code_image ci "
                     "join case_text cas on cas.fid = ci.id "
                     "where cas.caseid=?")
        # A/V codings: same logic, segment belongs to file linked to case.
        sql_av = ("select distinct cav.cid from code_av cav "
                  "join case_text cas on cas.fid = cav.id "
                  "where cas.caseid=?")
        cids = set()
        cur.execute(sql_text, [case_id])
        cids.update(r[0] for r in cur.fetchall())
        cur.execute(sql_image, [case_id])
        cids.update(r[0] for r in cur.fetchall())
        cur.execute(sql_av, [case_id])
        cids.update(r[0] for r in cur.fetchall())
        return cids

    def _get_codes_for_file(self, file_id):
        """
        Get distinct code cids applied to a file across text, image, and A/V codings.
        param: file_id : Integer
        return: set of cid integers
        """
        cur = self.app.conn.cursor()
        cids = set()
        cur.execute("select distinct cid from code_text where fid=?", [file_id])
        cids.update(r[0] for r in cur.fetchall())
        cur.execute("select distinct cid from code_image where id=?", [file_id])
        cids.update(r[0] for r in cur.fetchall())
        cur.execute("select distinct cid from code_av where id=?", [file_id])
        cids.update(r[0] for r in cur.fetchall())
        return cids

    def _get_code_frequencies_for_case(self, case_id):
        """
        Frecuencia de codificaciones por codigo (texto, imagen y A/V) aplicadas a un caso.
        Coding frequency per code (text, image and A/V) applied to a case.
        param: case_id : Integer
        return: dict cid -> Integer count
        """
        cur = self.app.conn.cursor()
        freq = {}
        # count(distinct pk): un caso puede enlazar el mismo archivo por varios rangos
        # de case_text; el distinct evita contar la misma codificacion dos veces.
        # count(distinct pk): a case may link the same file through several case_text
        # ranges; distinct avoids counting the same coding twice.
        sql_text = ("select ct.cid, count(distinct ct.ctid) from code_text ct "
                    "join case_text cas on cas.fid = ct.fid "
                    "and ct.pos0 >= cas.pos0 and ct.pos1 <= cas.pos1 "
                    "where cas.caseid=? group by ct.cid")
        sql_image = ("select ci.cid, count(distinct ci.imid) from code_image ci "
                     "join case_text cas on cas.fid = ci.id "
                     "where cas.caseid=? group by ci.cid")
        sql_av = ("select cav.cid, count(distinct cav.avid) from code_av cav "
                  "join case_text cas on cas.fid = cav.id "
                  "where cas.caseid=? group by cav.cid")
        for sql in (sql_text, sql_image, sql_av):
            cur.execute(sql, [case_id])
            for cid, n in cur.fetchall():
                freq[cid] = freq.get(cid, 0) + n
        return freq

    def _get_code_frequencies_for_file(self, file_id):
        """
        Frecuencia de codificaciones por codigo (texto, imagen y A/V) en un archivo.
        Coding frequency per code (text, image and A/V) in a file.
        param: file_id : Integer
        return: dict cid -> Integer count
        """
        cur = self.app.conn.cursor()
        freq = {}
        for sql in ("select cid, count(*) from code_text where fid=? group by cid",
                    "select cid, count(*) from code_image where id=? group by cid",
                    "select cid, count(*) from code_av where id=? group by cid"):
            cur.execute(sql, [file_id])
            for cid, n in cur.fetchall():
                freq[cid] = freq.get(cid, 0) + n
        return freq

    def _get_code_info(self, cid):
        """
        Get code name and color from code_name table.
        param: cid : Integer
        return: dict with 'cid', 'name', 'color', 'catid' or None
        """
        cur = self.app.conn.cursor()
        # supercid included so sub-code chains can be resolved
        cur.execute("select cid, name, color, ifnull(catid, ''), supercid from code_name where cid=?", [cid])
        r = cur.fetchone()
        if r is None:
            return None
        return {'cid': r[0], 'name': r[1], 'color': r[2],
                'catid': r[3] if r[3] != '' else None, 'supercid': r[4]}

    def _get_category_info(self, catid):
        """
        Get category name from code_cat table.
        param: catid : Integer
        return: dict with 'catid', 'name', 'supercatid' or None
        """
        cur = self.app.conn.cursor()
        cur.execute("select catid, name, supercatid from code_cat where catid=?", [catid])
        r = cur.fetchone()
        if r is None:
            return None
        return {'catid': r[0], 'name': r[1], 'supercatid': r[2]}

    def _get_category_chain(self, catid):
        """
        Walk up the category hierarchy from catid to root.
        return: list of category dicts from leaf to root
        """
        chain = []
        visited = set()
        current = catid
        while current is not None and current not in visited:
            visited.add(current)
            info = self._get_category_info(current)
            if info is None:
                break
            chain.append(info)
            current = info['supercatid']
        return chain

    def _find_scene_node_by_cid(self, cid):
        """
        Find an existing TextGraphicsItem in the scene by cid.
        """
        from .view_graph import TextGraphicsItem
        for item in self.view_graph.scene.items():
            if isinstance(item, TextGraphicsItem):
                if item.code_or_cat.get('cid') == cid:
                    return item
        return None

    def _find_scene_node_by_catid(self, catid):
        """
        Find an existing TextGraphicsItem in the scene by catid (category only).
        """
        from .view_graph import TextGraphicsItem
        for item in self.view_graph.scene.items():
            if isinstance(item, TextGraphicsItem):
                if item.code_or_cat.get('cid') is None and item.code_or_cat.get('catid') == catid:
                    return item
        return None

    def _find_scene_case_node(self, case_id):
        """
        Find an existing CaseTextGraphicsItem by case_id.
        """
        from .view_graph import CaseTextGraphicsItem
        for item in self.view_graph.scene.items():
            if isinstance(item, CaseTextGraphicsItem):
                if item.case_id == case_id:
                    return item
        return None

    def _find_scene_file_node(self, file_id):
        """
        Find an existing FileTextGraphicsItem by file_id.
        """
        from .view_graph import FileTextGraphicsItem
        for item in self.view_graph.scene.items():
            if isinstance(item, FileTextGraphicsItem):
                if item.file_id == file_id:
                    return item
        return None

    def _add_code_node(self, cid, x, y):
        """
        Add a TextGraphicsItem for a code if not already in scene.
        """
        from .view_graph import TextGraphicsItem
        existing = self._find_scene_node_by_cid(cid)
        if existing:
            return existing
        info = self._get_code_info(cid)
        if info is None:
            return None
        code_data = {'name': info['name'], 'supercatid': info['catid'], 'catid': info['catid'],
                     'cid': info['cid'], 'x': x, 'y': y, 'color': info['color'],
                     'memo': '', 'child_names': [],
                     'supercid': info.get('supercid')}
        # child names enable collapse on codes that have sub-codes
        code_data['child_names'] = self.view_graph.named_children_of_node(code_data)
        node = TextGraphicsItem(self.app, code_data)
        self.view_graph.scene.addItem(node)
        return node

    def _add_category_node(self, catid, x, y):
        """
        Add a TextGraphicsItem for a category if not already in scene 
        """
        from .view_graph import TextGraphicsItem
        existing = self._find_scene_node_by_catid(catid)
        if existing:
            return existing
        info = self._get_category_info(catid)
        if info is None:
            return None
        cat_data = {'name': info['name'], 'supercatid': info['supercatid'], 'catid': info['catid'],
                    'cid': None, 'x': x, 'y': y, 'color': '#FFFFFF',
                    'memo': '', 'child_names': []}
        cat_data['child_names'] = self.view_graph.named_children_of_node(cat_data)
        node = TextGraphicsItem(self.app, cat_data)
        self.view_graph.scene.addItem(node)
        return node

    def _add_case_node(self, case_id, case_name, x, y):
        """
        Add a CaseTextGraphicsItem if not already in scene.
        """
        from .view_graph import CaseTextGraphicsItem
        existing = self._find_scene_case_node(case_id)
        if existing:
            return existing
        node = CaseTextGraphicsItem(self.app, case_name, case_id, x, y)
        node.setToolTip(_("Case"))
        self.view_graph.scene.addItem(node)
        return node

    def _add_file_node(self, file_id, file_name, x, y):
        """
        Add a FileTextGraphicsItem if not already in scene.
        """
        from .view_graph import FileTextGraphicsItem
        existing = self._find_scene_file_node(file_id)
        if existing:
            return existing
        node = FileTextGraphicsItem(self.app, file_name, file_id, x, y)
        node.setToolTip(_("File"))
        self.view_graph.scene.addItem(node)
        return node

    def _add_link(self, from_node, to_node, line_width=2, line_type="solid", color="gray"):
        """
        Add a LinkGraphicsItem between two nodes if not already connected
        """
        from .view_graph import LinkGraphicsItem
        for item in self.view_graph.scene.items():
            if isinstance(item, LinkGraphicsItem):
                if (item.from_widget == from_node and item.to_widget == to_node) or \
                   (item.from_widget == to_node and item.to_widget == from_node):
                    return item
        line = LinkGraphicsItem(from_node, to_node, line_width, line_type, color, True)
        self.view_graph.scene.addItem(line)
        return line

    def _add_free_line(self, from_node, to_node, color="gray", line_width=2, line_type="dotted", label=""):
        """
        Add a FreeLineGraphicsItem between two nodes if not already connected
        """
        from .view_graph import FreeLineGraphicsItem
        for item in self.view_graph.scene.items():
            if isinstance(item, FreeLineGraphicsItem):
                if (item.from_widget == from_node and item.to_widget == to_node) or \
                   (item.from_widget == to_node and item.to_widget == from_node):
                    return item
        line = FreeLineGraphicsItem(from_node, to_node, color, line_width, line_type, label)
        self.view_graph.scene.addItem(line)
        return line

    def _finalize_graph(self):
        """
        Recalculate scene size and fit view after generating a model
        """
        self.view_graph.scene.suggested_scene_size()
        rect = self.view_graph.scene.itemsBoundingRect()
        if not rect.isEmpty():
            rect.adjust(-50, -50, 50, 50)
            self.view_graph.ui.graphicsView.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            current_scale = self.view_graph.ui.graphicsView.transform().m11()
            if current_scale > 2.0:
                self.view_graph.ui.graphicsView.resetTransform()
                self.view_graph.ui.graphicsView.scale(2.0, 2.0)
            self.view_graph.ui.graphicsView.centerOn(rect.center())
        self.view_graph.scene.update()

    # Model 1: Case Hierarchical

    # shared taxonomy engine for the hierarchical models.
    # Structure: cases > files > cats > sub-cats > codes > sub-codes > segments.

    def _collect_taxonomy(self, cids, allowed_catids, include_all):
        """
        build the taxonomy needed to display the given coded cids.
        Sub-code ancestors are included even without codings, so every sub-code
        hangs from its parent code. The category filter is applied on the category
        of the TOP code of each sub-code chain. Codes without category are always
        shown (uncategorized).
        Args:
            cids : iterable of cid integers with codings
            allowed_catids : set of permitted catids
            include_all : boolean, True when "All categories" was selected
        return: dict with codes, cats, children maps, roots, uncategorized, seg_cids
        """

        codes = {}     # cid -> info (with supercid)
        cats = {}      # catid -> info
        seg_cids = set()
        for cid in cids:
            # Walk up the sub-code chain to the top code
            chain = []
            current = self._get_code_info(cid)
            guard = 0
            while current is not None and guard < 50:
                guard += 1
                chain.append(current)
                if current.get('supercid') is None:
                    break
                current = self._get_code_info(current['supercid'])
            if not chain:
                continue
            top = chain[-1]
            catid = top.get('catid')
            if not include_all and catid is not None and catid not in allowed_catids:
                continue  # filtered out by the category selection
            for info in chain:
                codes[info['cid']] = info
            seg_cids.add(cid)
            if catid is not None:
                for cat_info in self._get_category_chain(catid):
                    cats[cat_info['catid']] = cat_info
        # Children maps
        code_children = {}
        top_codes_by_cat = {}
        uncategorized = []
        for cid, info in codes.items():
            sup = info.get('supercid')
            if sup is not None and sup in codes:
                code_children.setdefault(sup, []).append(cid)
            else:
                catid = info.get('catid')
                if catid is not None and catid in cats:
                    top_codes_by_cat.setdefault(catid, []).append(cid)
                else:
                    uncategorized.append(cid)
        cat_children = {}
        root_catids = []
        for catid, info in cats.items():
            sup = info.get('supercatid')
            if sup is not None and sup in cats:
                cat_children.setdefault(sup, []).append(catid)
            else:
                root_catids.append(catid)
        # Stable alphabetical ordering at every level
        for k in code_children:
            code_children[k].sort(key=lambda c: codes[c]['name'].lower())
        for k in top_codes_by_cat:
            top_codes_by_cat[k].sort(key=lambda c: codes[c]['name'].lower())
        for k in cat_children:
            cat_children[k].sort(key=lambda c: cats[c]['name'].lower())
        root_catids.sort(key=lambda c: cats[c]['name'].lower())
        uncategorized.sort(key=lambda c: codes[c]['name'].lower())
        return {'codes': codes, 'cats': cats, 'code_children': code_children,
                'cat_children': cat_children, 'top_codes_by_cat': top_codes_by_cat,
                'root_catids': root_catids, 'uncategorized': uncategorized,
                'seg_cids': seg_cids}

    def _layout_and_render_taxonomy(self, tax, x_origin, y_cat_base, row_h=90, col_w=150):
        """
        tidy-tree placement in global level rows:
        cats (top) > sub-cats (by depth) > codes (one row) > sub-codes (by depth).
        Leaf codes take one column each; parents are centred over their children.
        Creates nodes (reusing existing ones) and the hierarchy links.
        return: dict with cat_nodes, code_nodes, x_max, y_seg_base
        """

        cats, codes = tax['cats'], tax['codes']
        cat_children = tax['cat_children']
        top_by_cat = tax['top_codes_by_cat']
        code_children = tax['code_children']

        def cat_depth(catid, guard=0):
            sup = cats[catid].get('supercatid')
            if guard > 50 or sup is None or sup not in cats:
                return 0
            return 1 + cat_depth(sup, guard + 1)

        def code_depth(cid, guard=0):
            sup = codes[cid].get('supercid')
            if guard > 50 or sup is None or sup not in codes:
                return 0
            return 1 + code_depth(sup, guard + 1)

        max_cat_depth = max([cat_depth(c) for c in cats], default=-1)
        y_code_base = y_cat_base + (max_cat_depth + 1) * row_h
        max_code_depth = max([code_depth(c) for c in codes], default=0)
        y_seg_base = y_code_base + (max_code_depth + 1) * row_h

        cursor = [x_origin]
        pos_code = {}
        pos_cat = {}

        def place_code(cid, depth):
            children = code_children.get(cid, [])
            if children:
                xs = [place_code(c, depth + 1) for c in children]
                x = sum(xs) / len(xs)
            else:
                x = cursor[0]
                cursor[0] += col_w
            pos_code[cid] = (x, y_code_base + depth * row_h)
            return x

        def place_cat(catid, depth):
            xs = [place_cat(sc, depth + 1) for sc in cat_children.get(catid, [])]
            xs += [place_code(c, 0) for c in top_by_cat.get(catid, [])]
            if xs:
                x = sum(xs) / len(xs)
            else:
                x = cursor[0]
                cursor[0] += col_w
            pos_cat[catid] = (x, y_cat_base + depth * row_h)
            return x

        for root in tax['root_catids']:
            place_cat(root, 0)
        for cid in tax['uncategorized']:
            place_code(cid, 0)

        cat_nodes = {}
        for catid, (x, y) in pos_cat.items():
            node = self._add_category_node(catid, x, y)
            if node:
                cat_nodes[catid] = node
        code_nodes = {}
        for cid, (x, y) in pos_code.items():
            node = self._add_code_node(cid, x, y)
            if node:
                code_nodes[cid] = node
        for catid, subcats in cat_children.items():
            for sc in subcats:
                if catid in cat_nodes and sc in cat_nodes:
                    self._add_link(cat_nodes[catid], cat_nodes[sc], 2, "solid", "gray")
        for catid, cid_list in top_by_cat.items():
            for cid in cid_list:
                if catid in cat_nodes and cid in code_nodes:
                    self._add_link(cat_nodes[catid], code_nodes[cid], 2, "solid", "gray")
        for pcid, kids in code_children.items():
            for kid in kids:
                if pcid in code_nodes and kid in code_nodes:
                    self._add_link(code_nodes[pcid], code_nodes[kid], 2, "solid", "gray")
        x_max = max(cursor[0], x_origin + col_w)
        return {'cat_nodes': cat_nodes, 'code_nodes': code_nodes,
                'x_max': x_max, 'y_seg_base': y_seg_base}

    def _top_cid_for_cid(self, cid, tax):
        """
        top-most visible code of the sub-code chain containing cid.
        """

        info = tax['codes'].get(cid)
        guard = 0
        while info is not None and info.get('supercid') in tax['codes'] and guard < 50:
            info = tax['codes'][info['supercid']]
            guard += 1
        return info['cid'] if info else None

    def _root_catid_for_cid(self, cid, tax):
        """
        top-most visible category over the chain containing cid, or None.
        """

        top_cid = self._top_cid_for_cid(cid, tax)
        if top_cid is None:
            return None
        catid = tax['codes'][top_cid].get('catid')
        if catid is None or catid not in tax['cats']:
            return None
        guard = 0
        while guard < 50:
            sup = tax['cats'][catid].get('supercatid')
            if sup is None or sup not in tax['cats']:
                return catid
            catid = sup
            guard += 1
        return catid

    def _generate_case_hierarchical(self):
        """
        Cases > Files > Categories > Sub-categories > Codes >
        Sub-codes > Segments, placed in global level rows (one row per level).
        """

        seg_limit = self.ui.spinBox_case_hier_limit.value()
        cases = self._get_cases()
        if not cases:
            Message(self.app, _("No cases"), _("No cases in this project.")).exec()
            return

        ui = DialogSelectItems(self.app, cases, _("Select cases"), "multi")
        if not ui.exec():
            return
        selected_cases = ui.get_selected()
        if not selected_cases:
            return

        codes, categories = self.app.get_codes_categories()
        if not codes:
            Message(self.app, _("No codes"), _("No codes in this project.")).exec()
            return

        cat_list = [{'name': _('All categories')}]
        for cat in categories:
            cat_list.append({'name': cat['name'], 'catid': cat['catid']})
        ui = DialogSelectItems(self.app, cat_list, _("Filter by categories (or select All)"), "multi")
        if not ui.exec():
            return
        selected_cats = ui.get_selected()

        include_all = any(s['name'] == _('All categories') for s in selected_cats)
        if include_all:
            allowed_catids = {cat['catid'] for cat in categories}
        else:
            allowed_catids = set()
            for s in selected_cats:
                if 'catid' in s:
                    allowed_catids.add(s['catid'])
                    # full descendant sub-categories (was direct children only)
                    self._collect_descendant_catids(s['catid'], categories, allowed_catids)

        self.accept()

        row_h = 90
        y_case = 30
        y_file = y_case + row_h
        y_cat_base = y_file + row_h
        x_cursor = 50
        case_gap = 260
        cur = self.app.conn.cursor()

        for case in selected_cases:
            case_cids = self._get_codes_for_case(case['id'])
            tax = self._collect_taxonomy(case_cids, allowed_catids, include_all)
            x_origin = x_cursor
            layout = self._layout_and_render_taxonomy(tax, x_origin, y_cat_base, row_h)

            # Files of the case that contain relevant codings
            cur.execute("select distinct cas.fid, source.name from case_text cas "
                        "join source on source.id = cas.fid where cas.caseid=? "
                        "order by source.name", [case['id']])
            case_files = [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]
            file_entries = []
            for f in case_files:
                f_cids = self._get_codes_for_file(f['id']) & tax['seg_cids']
                if f_cids:
                    file_entries.append((f, f_cids))

            width = max(layout['x_max'] - x_origin, max(len(file_entries), 1) * 180)
            # Case node centred over its taxonomy
            case_node = self._add_case_node(case['id'], case['name'],
                                            x_origin + width / 2 - 40, y_case)
            # File row, evenly distributed; links case > file and file > root cats
            n_files = max(len(file_entries), 1)
            for i, (f, f_cids) in enumerate(file_entries):
                fx = x_origin + (i + 0.5) * (width / n_files) - 40
                file_node = self._add_file_node(f['id'], f['name'], fx, y_file)
                if file_node is None:
                    continue
                self._add_link(case_node, file_node, 2, "solid", "gray")
                root_cats = set()
                top_uncat = set()
                for cid in f_cids:
                    root = self._root_catid_for_cid(cid, tax)
                    if root is not None:
                        root_cats.add(root)
                    else:
                        top = self._top_cid_for_cid(cid, tax)
                        if top is not None:
                            top_uncat.add(top)
                for catid in root_cats:
                    if catid in layout['cat_nodes']:
                        self._add_link(file_node, layout['cat_nodes'][catid], 2, "solid", "gray")
                for cid in top_uncat:
                    if cid in layout['code_nodes']:
                        self._add_link(file_node, layout['code_nodes'][cid], 2, "solid", "gray")
            # Segments under their codes, in the global segment row
            if seg_limit > 0:
                for cid in sorted(tax['seg_cids']):
                    node = layout['code_nodes'].get(cid)
                    if node is None:
                        continue
                    self._add_segments_for_code_in_case(
                        node, cid, case['id'], seg_limit,
                        node.pos().x(), layout['y_seg_base'])
            x_cursor = max(layout['x_max'], x_origin + width) + case_gap

        self._finalize_graph()

    def _add_segments_for_code_in_case(self, code_node, cid, case_id, limit, x, y):
        """
        Add segment nodes (text/image/A/V) for a code within a case 
        """  # multi-modal support
        from .view_graph import FreeTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem  # added PixmapGraphicsItem and AVGraphicsItem

        cur = self.app.conn.cursor()
        seg_index = 0  # global ordering across modalities

        # 1. Text segments inside case range
        sql_text = ("select ct.ctid, ct.seltext, ifnull(ct.memo,''), source.name "
                    "from code_text ct "
                    "join case_text cas on cas.fid = ct.fid "
                    "and ct.pos0 >= cas.pos0 and ct.pos1 <= cas.pos1 "
                    "join source on source.id = ct.fid "
                    "where ct.cid=? and cas.caseid=? "
                    "order by ct.pos0 limit ?")
        cur.execute(sql_text, [cid, case_id, limit])
        for r in cur.fetchall():
            ctid = r[0]
            already = any(isinstance(it, FreeTextGraphicsItem) and it.ctid == ctid
                          for it in self.view_graph.scene.items())
            if already:
                continue
            seg_y = y + seg_index * 40
            freetextid = 1
            for item in self.view_graph.scene.items():
                if isinstance(item, FreeTextGraphicsItem) and item.freetextid >= freetextid:
                    freetextid = item.freetextid + 1
            text = r[1]
            if len(text) > 80:
                text = text[:80] + "..."
            seg_node = FreeTextGraphicsItem(self.app, freetextid, x, seg_y, text, 9, "black", False, ctid)
            msg = _("File: ") + f"{r[3]}\n" + _("Code: ") + code_node.code_or_cat['name']
            if r[2]:
                msg += "\n" + _("Memo: ") + r[2]
            seg_node.setToolTip(msg)
            seg_node.code_or_cat['cid'] = cid
            self.view_graph.scene.addItem(seg_node)
            self._add_free_line(code_node, seg_node, "gray", 2, "dotted")
            seg_index += 1

        # 2. Image segments in files linked to the case
        sql_img = ("select distinct ci.imid, ci.x1, ci.y1, ci.width, ci.height, "
                   "ifnull(ci.memo,''), source.name, source.mediapath, ci.pdf_page "
                   "from code_image ci "
                   "join case_text cas on cas.fid = ci.id "
                   "join source on source.id = ci.id "
                   "where ci.cid=? and cas.caseid=? limit ?")
        cur.execute(sql_img, [cid, case_id, limit])
        for r in cur.fetchall():
            imid, x1, y1, w_img, h_img, memo, fname, fpath, pdf_page = r
            already = any(isinstance(it, PixmapGraphicsItem) and it.imid == imid
                          for it in self.view_graph.scene.items())
            if already:
                continue
            seg_y = y + seg_index * 40
            try:  # defensive: PixmapGraphicsItem ctor reads files
                seg_node = PixmapGraphicsItem(self.app, imid, x, seg_y,
                                              int(x1), int(y1), int(w_img), int(h_img),
                                              fpath if fpath else "", None, pdf_page)
                msg = f"IMID:{imid} " + _("File: ") + f"{fname}\n" + _("Code: ") + code_node.code_or_cat['name']
                if memo:
                    msg += "\n" + _("Memo: ") + memo
                seg_node.setToolTip(msg)
                seg_node.code_or_cat['cid'] = cid
                self.view_graph.scene.addItem(seg_node)
                self._add_free_line(code_node, seg_node, "gray", 2, "dotted")
                seg_index += 1
            except Exception as e:
                logger.warning(f"Could not load image segment imid={imid}: {e}")

        # 3. A/V segments in files linked to the case
        sql_av = ("select distinct cav.avid, cav.pos0, cav.pos1, ifnull(cav.memo,''), "
                  "source.name, source.mediapath "
                  "from code_av cav "
                  "join case_text cas on cas.fid = cav.id "
                  "join source on source.id = cav.id "
                  "where cav.cid=? and cas.caseid=? order by cav.pos0 limit ?")
        cur.execute(sql_av, [cid, case_id, limit])
        for r in cur.fetchall():
            avid, pos0, pos1, memo, fname, fpath = r
            already = any(isinstance(it, AVGraphicsItem) and it.avid == avid
                          for it in self.view_graph.scene.items())
            if already:
                continue
            seg_y = y + seg_index * 40
            seg_node = AVGraphicsItem(self.app, avid, x, seg_y, int(pos0), int(pos1),
                                      fpath if fpath else "")
            msg = f"AVID:{avid} " + _("File: ") + f"{fname}\n" + _("Code: ") + code_node.code_or_cat['name']
            msg += f"\n{int(pos0)} - {int(pos1)} " + _("msecs")
            if memo:
                msg += "\n" + _("Memo: ") + memo
            seg_node.setToolTip(msg)
            seg_node.code_or_cat['cid'] = cid
            self.view_graph.scene.addItem(seg_node)
            self._add_free_line(code_node, seg_node, "gray", 2, "dotted")
            seg_index += 1

    # Model 2: Case comparative 

    def _generate_case_comparative(self):
        """
        Compare exactly 2 cases. Shared codes/categories in center.
        """

        compare_by_cats = self.ui.comboBox_case_comp_level.currentIndex() == 1

        # Read selections from comboboxes
        case_a_id = self.ui.comboBox_case_a.currentData()
        case_b_id = self.ui.comboBox_case_b.currentData()
        case_a_name = self.ui.comboBox_case_a.currentText()
        case_b_name = self.ui.comboBox_case_b.currentText()

        if case_a_id is None or case_b_id is None:
            Message(self.app, _("Selection error"), _("Select both cases.")).exec()
            return
        if case_a_id == case_b_id:
            Message(self.app, _("Selection error"), _("Both cases are the same. Select two different cases.")).exec()
            return

        self.accept()

        case_a = {'id': case_a_id, 'name': case_a_name}
        case_b = {'id': case_b_id, 'name': case_b_name}
        cids_a = self._get_codes_for_case(case_a['id'])
        cids_b = self._get_codes_for_case(case_b['id'])
        # Frecuencias por codigo, mostradas como etiqueta en las lineas de conexion.
        # Per-code frequencies, shown as label on the connection lines.
        freq_a = self._get_code_frequencies_for_case(case_a['id'])
        freq_b = self._get_code_frequencies_for_case(case_b['id'])

        if compare_by_cats:
            items_a = set()
            items_b = set()
            catfreq_a = {}
            catfreq_b = {}
            for cid in cids_a:
                info = self._get_code_info(cid)
                if info and info['catid']:
                    items_a.add(info['catid'])
                    catfreq_a[info['catid']] = catfreq_a.get(info['catid'], 0) + freq_a.get(cid, 0)
            for cid in cids_b:
                info = self._get_code_info(cid)
                if info and info['catid']:
                    items_b.add(info['catid'])
                    catfreq_b[info['catid']] = catfreq_b.get(info['catid'], 0) + freq_b.get(cid, 0)
            # Al comparar por categorias la frecuencia es la suma de sus codigos.
            # When comparing by categories the frequency is the sum over its codes.
            freq_a = catfreq_a
            freq_b = catfreq_b
        else:
            items_a = cids_a
            items_b = cids_b

        shared = items_a & items_b
        only_a = items_a - shared
        only_b = items_b - shared

        left_x = 50
        center_x = 450
        right_x = 850
        top_y = 30

        node_a = self._add_case_node(case_a['id'], case_a['name'], left_x, top_y)
        node_b = self._add_case_node(case_b['id'], case_b['name'], right_x, top_y)

        # Cada linea lleva como etiqueta la frecuencia respecto a su caso.
        # Each line is labelled with the frequency relative to its case.
        shared_y = top_y + 100
        for si, item_id in enumerate(sorted(shared)):
            ny = shared_y + si * 50
            if compare_by_cats:
                node = self._add_category_node(item_id, center_x, ny)
            else:
                node = self._add_code_node(item_id, center_x, ny)
            if node:
                self._add_free_line(node_a, node, "blue", 2, "solid", str(freq_a.get(item_id, 0)))
                self._add_free_line(node_b, node, "blue", 2, "solid", str(freq_b.get(item_id, 0)))

        excl_y = top_y + 100
        for si, item_id in enumerate(sorted(only_a)):
            ny = excl_y + si * 50
            if compare_by_cats:
                node = self._add_category_node(item_id, left_x, ny)
            else:
                node = self._add_code_node(item_id, left_x, ny)
            if node:
                self._add_free_line(node_a, node, "cyan", 2, "dotted", str(freq_a.get(item_id, 0)))

        for si, item_id in enumerate(sorted(only_b)):
            ny = excl_y + si * 50
            if compare_by_cats:
                node = self._add_category_node(item_id, right_x, ny)
            else:
                node = self._add_code_node(item_id, right_x, ny)
            if node:
                self._add_free_line(node_b, node, "magenta", 2, "dotted", str(freq_b.get(item_id, 0)))

        self._finalize_graph()

    # Model 3: File hierarchical 

    def _generate_file_hierarchical(self):
        """
        Files > Categories > Sub-categories > Codes >
        Sub-codes > Segments, placed in global level rows (one row per level).
        """

        seg_limit = self.ui.spinBox_file_hier_limit.value()
        files = self._get_files()
        if not files:
            Message(self.app, _("No files"), _("No files in this project.")).exec()
            return

        ui = DialogSelectItems(self.app, files, _("Select files"), "multi")
        if not ui.exec():
            return
        selected_files = ui.get_selected()
        if not selected_files:
            return

        codes, categories = self.app.get_codes_categories()
        if not codes:
            Message(self.app, _("No codes"), _("No codes in this project.")).exec()
            return

        cat_list = [{'name': _('All categories')}]
        for cat in categories:
            cat_list.append({'name': cat['name'], 'catid': cat['catid']})
        ui = DialogSelectItems(self.app, cat_list, _("Filter by categories (or select All)"), "multi")
        if not ui.exec():
            return
        selected_cats = ui.get_selected()

        include_all = any(s['name'] == _('All categories') for s in selected_cats)
        if include_all:
            allowed_catids = {cat['catid'] for cat in categories}
        else:
            allowed_catids = set()
            for s in selected_cats:
                if 'catid' in s:
                    allowed_catids.add(s['catid'])
                    # full descendant sub-categories (was direct children only)
                    self._collect_descendant_catids(s['catid'], categories, allowed_catids)

        self.accept()

        row_h = 90
        y_file = 30
        y_cat_base = y_file + row_h
        x_cursor = 50
        file_gap = 260

        for file_ in selected_files:
            file_cids = self._get_codes_for_file(file_['id'])
            tax = self._collect_taxonomy(file_cids, allowed_catids, include_all)
            x_origin = x_cursor
            layout = self._layout_and_render_taxonomy(tax, x_origin, y_cat_base, row_h)
            width = max(layout['x_max'] - x_origin, 180)
            # File node centred over its taxonomy; links file > root cats
            file_node = self._add_file_node(file_['id'], file_['name'],
                                            x_origin + width / 2 - 40, y_file)
            if file_node is not None:
                for catid in tax['root_catids']:
                    if catid in layout['cat_nodes']:
                        self._add_link(file_node, layout['cat_nodes'][catid], 2, "solid", "gray")
                for cid in tax['uncategorized']:
                    if cid in layout['code_nodes']:
                        self._add_link(file_node, layout['code_nodes'][cid], 2, "solid", "gray")
            # Segments under their codes, in the global segment row
            if seg_limit > 0:
                for cid in sorted(tax['seg_cids']):
                    node = layout['code_nodes'].get(cid)
                    if node is None:
                        continue
                    self._add_segments_for_code_in_file(
                        node, cid, file_['id'], seg_limit,
                        node.pos().x(), layout['y_seg_base'])
            x_cursor = max(layout['x_max'], x_origin + width) + file_gap

        self._finalize_graph()

    def _add_segments_for_code_in_file(self, code_node, cid, file_id, limit, x, y):
        """
        Add segment nodes (text/image/A/V) for a code applied within a file.
        """  # multi-modal support
        from .view_graph import FreeTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem  # added PixmapGraphicsItem and AVGraphicsItem

        cur = self.app.conn.cursor()
        seg_index = 0  # global ordering across modalities

        # 1. Text segments
        sql_text = ("select ct.ctid, ct.seltext, ifnull(ct.memo,''), source.name "
                    "from code_text ct "
                    "join source on source.id = ct.fid "
                    "where ct.cid=? and ct.fid=? "
                    "order by ct.pos0 limit ?")
        cur.execute(sql_text, [cid, file_id, limit])
        for r in cur.fetchall():
            ctid = r[0]
            already = any(isinstance(it, FreeTextGraphicsItem) and it.ctid == ctid
                          for it in self.view_graph.scene.items())
            if already:
                continue
            seg_y = y + seg_index * 40
            freetextid = 1
            for item in self.view_graph.scene.items():
                if isinstance(item, FreeTextGraphicsItem) and item.freetextid >= freetextid:
                    freetextid = item.freetextid + 1
            text = r[1]
            if len(text) > 80:
                text = text[:80] + "..."
            seg_node = FreeTextGraphicsItem(self.app, freetextid, x, seg_y, text, 9, "black", False, ctid)
            msg = _("File: ") + f"{r[3]}\n" + _("Code: ") + code_node.code_or_cat['name']
            if r[2]:
                msg += "\n" + _("Memo: ") + r[2]
            seg_node.setToolTip(msg)
            seg_node.code_or_cat['cid'] = cid
            self.view_graph.scene.addItem(seg_node)
            self._add_free_line(code_node, seg_node, "gray", 2, "dotted")
            seg_index += 1

        # 2. Image segments
        sql_img = ("select ci.imid, ci.x1, ci.y1, ci.width, ci.height, "
                   "ifnull(ci.memo,''), source.name, source.mediapath, ci.pdf_page "
                   "from code_image ci join source on source.id = ci.id "
                   "where ci.cid=? and ci.id=? limit ?")
        cur.execute(sql_img, [cid, file_id, limit])
        for r in cur.fetchall():
            imid, x1, y1, w_img, h_img, memo, fname, fpath, pdf_page = r
            already = any(isinstance(it, PixmapGraphicsItem) and it.imid == imid
                          for it in self.view_graph.scene.items())
            if already:
                continue
            seg_y = y + seg_index * 40
            try:  # defensive: PixmapGraphicsItem ctor reads files; skip on failure
                seg_node = PixmapGraphicsItem(self.app, imid, x, seg_y,
                                              int(x1), int(y1), int(w_img), int(h_img),
                                              fpath if fpath else "", None, pdf_page)
                msg = f"IMID:{imid} " + _("File: ") + f"{fname}\n" + _("Code: ") + code_node.code_or_cat['name']
                if memo:
                    msg += "\n" + _("Memo: ") + memo
                seg_node.setToolTip(msg)
                seg_node.code_or_cat['cid'] = cid
                self.view_graph.scene.addItem(seg_node)
                self._add_free_line(code_node, seg_node, "gray", 2, "dotted")
                seg_index += 1
            except Exception as e:
                logger.warning(f"Could not load image segment imid={imid}: {e}")

        # 3. A/V segments
        sql_av = ("select cav.avid, cav.pos0, cav.pos1, ifnull(cav.memo,''), "
                  "source.name, source.mediapath "
                  "from code_av cav join source on source.id = cav.id "
                  "where cav.cid=? and cav.id=? order by cav.pos0 limit ?")
        cur.execute(sql_av, [cid, file_id, limit])
        for r in cur.fetchall():
            avid, pos0, pos1, memo, fname, fpath = r
            already = any(isinstance(it, AVGraphicsItem) and it.avid == avid
                          for it in self.view_graph.scene.items())
            if already:
                continue
            seg_y = y + seg_index * 40
            seg_node = AVGraphicsItem(self.app, avid, x, seg_y, int(pos0), int(pos1),
                                      fpath if fpath else "")
            msg = f"AVID:{avid} " + _("File: ") + f"{fname}\n" + _("Code: ") + code_node.code_or_cat['name']
            msg += f"\n{int(pos0)} - {int(pos1)} " + _("msecs")
            if memo:
                msg += "\n" + _("Memo: ") + memo
            seg_node.setToolTip(msg)
            seg_node.code_or_cat['cid'] = cid
            self.view_graph.scene.addItem(seg_node)
            self._add_free_line(code_node, seg_node, "gray", 2, "dotted")
            seg_index += 1

    # Model 4: File comparative

    def _generate_file_comparative(self):
        """
        Compare exactly 2 files. Shared codes/categories in center.
        """

        compare_by_cats = self.ui.comboBox_file_comp_level.currentIndex() == 1

        # Read selections from comboboxes
        file_a_id = self.ui.comboBox_file_a.currentData()
        file_b_id = self.ui.comboBox_file_b.currentData()
        file_a_name = self.ui.comboBox_file_a.currentText()
        file_b_name = self.ui.comboBox_file_b.currentText()

        if file_a_id is None or file_b_id is None:
            Message(self.app, _("Selection error"), _("Select both files.")).exec()
            return
        if file_a_id == file_b_id:
            Message(self.app, _("Selection error"), _("Both files are the same. Select two different files.")).exec()
            return

        self.accept()

        file_a = {'id': file_a_id, 'name': file_a_name}
        file_b = {'id': file_b_id, 'name': file_b_name}
        cids_a = self._get_codes_for_file(file_a['id'])
        cids_b = self._get_codes_for_file(file_b['id'])
        # Frecuencias por codigo, mostradas como etiqueta en las lineas de conexion.
        # Per-code frequencies, shown as label on the connection lines.
        freq_a = self._get_code_frequencies_for_file(file_a['id'])
        freq_b = self._get_code_frequencies_for_file(file_b['id'])

        if compare_by_cats:
            items_a = set()
            items_b = set()
            catfreq_a = {}
            catfreq_b = {}
            for cid in cids_a:
                info = self._get_code_info(cid)
                if info and info['catid']:
                    items_a.add(info['catid'])
                    catfreq_a[info['catid']] = catfreq_a.get(info['catid'], 0) + freq_a.get(cid, 0)
            for cid in cids_b:
                info = self._get_code_info(cid)
                if info and info['catid']:
                    items_b.add(info['catid'])
                    catfreq_b[info['catid']] = catfreq_b.get(info['catid'], 0) + freq_b.get(cid, 0)
            # Al comparar por categorias la frecuencia es la suma de sus codigos.
            # When comparing by categories the frequency is the sum over its codes.
            freq_a = catfreq_a
            freq_b = catfreq_b
        else:
            items_a = cids_a
            items_b = cids_b

        shared = items_a & items_b
        only_a = items_a - shared
        only_b = items_b - shared

        left_x = 50
        center_x = 450
        right_x = 850
        top_y = 30

        node_a = self._add_file_node(file_a['id'], file_a['name'], left_x, top_y)
        node_b = self._add_file_node(file_b['id'], file_b['name'], right_x, top_y)

        # Cada linea lleva como etiqueta la frecuencia respecto a su archivo.
        # Each line is labelled with the frequency relative to its file.
        shared_y = top_y + 100
        for si, item_id in enumerate(sorted(shared)):
            ny = shared_y + si * 50
            if compare_by_cats:
                node = self._add_category_node(item_id, center_x, ny)
            else:
                node = self._add_code_node(item_id, center_x, ny)
            if node:
                self._add_free_line(node_a, node, "blue", 2, "solid", str(freq_a.get(item_id, 0)))
                self._add_free_line(node_b, node, "blue", 2, "solid", str(freq_b.get(item_id, 0)))

        excl_y = top_y + 100
        for si, item_id in enumerate(sorted(only_a)):
            ny = excl_y + si * 50
            if compare_by_cats:
                node = self._add_category_node(item_id, left_x, ny)
            else:
                node = self._add_code_node(item_id, left_x, ny)
            if node:
                self._add_free_line(node_a, node, "cyan", 2, "dotted", str(freq_a.get(item_id, 0)))

        for si, item_id in enumerate(sorted(only_b)):
            ny = excl_y + si * 50
            if compare_by_cats:
                node = self._add_category_node(item_id, right_x, ny)
            else:
                node = self._add_code_node(item_id, right_x, ny)
            if node:
                self._add_free_line(node_b, node, "magenta", 2, "dotted", str(freq_b.get(item_id, 0)))

        self._finalize_graph()

    # Model 5: Co-occurrence network

    def _generate_cooccurrence_network(self):
        """
        Network of code co-occurrences with configurable types.
        """

        use_overlap = self.ui.checkBox_overlap.isChecked()
        use_inclusion = self.ui.checkBox_inclusion.isChecked()
        use_exact = self.ui.checkBox_exact.isChecked()
        use_proximity = self.ui.checkBox_proximity.isChecked()
        proximity_threshold = self.ui.spinBox_proximity.value()
        show_cats = self.ui.checkBox_show_cats.isChecked()

        if not (use_overlap or use_inclusion or use_exact or use_proximity):
            Message(self.app, _("No type selected"),
                    _("Select at least one co-occurrence type.")).exec()
            return

        codes, categories = self.app.get_codes_categories()
        if not codes:
            Message(self.app, _("No codes"), _("No codes in this project.")).exec()
            return

        ui = DialogSelectItems(self.app, codes, _("Select codes for co-occurrence network"), "multi")
        if not ui.exec():
            return
        selected_codes = ui.get_selected()
        if len(selected_codes) < 2:
            Message(self.app, _("Selection error"),
                    _("Select at least 2 codes to build a co-occurrence network.")).exec()
            return

        self.accept()

        selected_cids = {c['cid'] for c in selected_codes}
        cur = self.app.conn.cursor()

        # Build co-occurrence pairs with frequency
        cooc_pairs = {}

        sql = "select cid, fid, pos0, pos1 from code_text where cid in ({}) order by fid, pos0".format(
            ','.join('?' * len(selected_cids)))
        cur.execute(sql, list(selected_cids))
        all_codings = cur.fetchall()

        file_codings = {}
        for row in all_codings:
            cid, fid, pos0, pos1 = row
            if fid not in file_codings:
                file_codings[fid] = []
            file_codings[fid].append({'cid': cid, 'pos0': pos0, 'pos1': pos1})

        for fid, codings in file_codings.items():
            for i in range(len(codings)):
                for j in range(i + 1, len(codings)):
                    a = codings[i]
                    b = codings[j]
                    if a['cid'] == b['cid']:
                        continue

                    cooc_type = self._classify_cooccurrence(
                        a['pos0'], a['pos1'], b['pos0'], b['pos1'], proximity_threshold)

                    if cooc_type is None:
                        continue
                    if cooc_type == 'overlap' and not use_overlap:
                        continue
                    if cooc_type == 'inclusion' and not use_inclusion:
                        continue
                    if cooc_type == 'exact' and not use_exact:
                        continue
                    if cooc_type == 'proximity' and not use_proximity:
                        continue

                    pair_key = (min(a['cid'], b['cid']), max(a['cid'], b['cid']))
                    if pair_key not in cooc_pairs:
                        cooc_pairs[pair_key] = {'count': 0, 'types': set()}
                    cooc_pairs[pair_key]['count'] += 1
                    cooc_pairs[pair_key]['types'].add(cooc_type)

        if not cooc_pairs:
            Message(self.app, _("No co-occurrences"),
                    _("No co-occurrences found for the selected codes and types.")).exec()
            return

        all_cids_in_network = set()
        for (cid_a, cid_b) in cooc_pairs:
            all_cids_in_network.add(cid_a)
            all_cids_in_network.add(cid_b)

        cid_list = sorted(all_cids_in_network)
        n = len(cid_list)
        radius = max(200, n * 40)
        center_x = 450
        center_y = 350
        angle_step = (2 * math.pi) / max(1, n)

        cid_to_node = {}
        for idx, cid in enumerate(cid_list):
            angle = idx * angle_step
            nx = center_x + radius * math.cos(angle)
            ny = center_y + radius * math.sin(angle)
            node = self._add_code_node(cid, nx, ny)
            if node:
                cid_to_node[cid] = node

        if show_cats:
            cat_nodes = {}
            for cid in cid_list:
                info = self._get_code_info(cid)
                if info and info['catid'] and info['catid'] not in cat_nodes:
                    catid = info['catid']
                    code_node = cid_to_node.get(cid)
                    if code_node:
                        cx = code_node.pos().x()
                        cy = code_node.pos().y() - 100
                    else:
                        cx = center_x
                        cy = center_y - radius - 100
                    cat_node = self._add_category_node(catid, cx, cy)
                    if cat_node:
                        cat_nodes[catid] = cat_node

            for cid in cid_list:
                info = self._get_code_info(cid)
                if info and info['catid'] and info['catid'] in cat_nodes:
                    code_node = cid_to_node.get(cid)
                    cat_node = cat_nodes[info['catid']]
                    if code_node and cat_node:
                        self._add_link(cat_node, code_node, 1, "solid", "gray")

        for (cid_a, cid_b), data in cooc_pairs.items():
            node_a = cid_to_node.get(cid_a)
            node_b = cid_to_node.get(cid_b)
            if node_a and node_b:
                width = max(1, min(6, data['count']))
                types_str = ", ".join(sorted(data['types']))
                label = f"{data['count']} ({types_str})"
                color = "blue"
                if 'exact' in data['types']:
                    color = "red"
                elif 'inclusion' in data['types']:
                    color = "green"
                elif 'proximity' in data['types']:
                    color = "orange"
                self._add_free_line(node_a, node_b, color, width, "solid", label)

        self._finalize_graph()

    def _classify_cooccurrence(self, pos0_a, pos1_a, pos0_b, pos1_b, proximity_threshold):
        """
        Classify the co-occurrence relationship between two coded segments.
        Logic aligned with DialogReportRelations.relation() method.
        return: 'exact', 'inclusion', 'overlap', 'proximity' or None
        """  # docstring updated

        # Check Exact first (same as report_code_relations: E)
        if pos0_a == pos0_b and pos1_a == pos1_b:
            return 'exact'

        # Check Proximity before Inclusion/Overlap (same as report_code_relations: P)
        # Proximity = no overlap at all, segments are apart
        if pos1_a <= pos0_b:  # a ends before b starts
            gap = pos0_b - pos1_a
            if gap <= proximity_threshold:
                return 'proximity'
            return None
        if pos1_b <= pos0_a:  # b ends before a starts
            gap = pos0_a - pos1_b
            if gap <= proximity_threshold:
                return 'proximity'
            return None

        # Check Inclusion (same as report_code_relations: I)
        # a inside b, or b inside a (Exact already handled above)
        if (pos0_a >= pos0_b and pos1_a <= pos1_b) or (pos0_b >= pos0_a and pos1_b <= pos1_a):
            return 'inclusion'

        # Check Overlap: partial intersection (same as report_code_relations: O)
        # At this point segments do intersect but neither contains the other
        if pos0_a < pos1_b and pos1_a > pos0_b:
            return 'overlap'

        return None  # should not reach here but safety fallback

    # Model 1: category hierarchical

    def _generate_category_hierarchical(self):
        """
        Categories > Sub-categories > Codes > Sub-codes > Segments,
        placed in global level rows via the shared taxonomy engine.
        """

        seg_limit = self.ui.spinBox_seg_limit.value()
        codes, categories = self.app.get_codes_categories()
        if not categories:
            Message(self.app, _("No categories"),
                    _("No categories in this project.")).exec()
            return

        cat_list = [{'name': _('All categories')}]  # option to select all
        for cat in categories:
            cat_list.append({'name': cat['name'], 'catid': cat['catid']})
        ui = DialogSelectItems(self.app, cat_list, _("Select categories"), "multi")
        if not ui.exec():
            return
        selected_cats = ui.get_selected()
        if not selected_cats:
            return

        # Determine allowed catids including subcategories
        include_all = any(s['name'] == _('All categories') for s in selected_cats)
        if include_all:
            allowed_catids = {cat['catid'] for cat in categories}
        else:
            allowed_catids = set()
            for s in selected_cats:
                if 'catid' in s:
                    allowed_catids.add(s['catid'])
                    # Also include all descendant subcategories
                    self._collect_descendant_catids(s['catid'], categories, allowed_catids)

        if not codes:
            Message(self.app, _("No codes"), _("No codes in this project.")).exec()
            return

        self.accept()

        # the taxonomy engine resolves sub-code chains, filters by the
        # category of the top code, lays out level rows and draws hierarchy links.
        all_cids = {c['cid'] for c in codes}
        tax = self._collect_taxonomy(all_cids, allowed_catids, include_all)
        layout = self._layout_and_render_taxonomy(tax, 50, 30)
        if seg_limit > 0:
            for cid in sorted(tax['seg_cids']):
                node = layout['code_nodes'].get(cid)
                if node is None:
                    continue
                self._add_segments_for_code(node, cid, seg_limit,
                                            node.pos().x(), layout['y_seg_base'])

        self._finalize_graph()

    def _collect_descendant_catids(self, parent_catid, categories, result_set):
        """
        Recursively collect all descendant category IDs.
        """
        for cat in categories:
            if cat.get('supercatid') == parent_catid and cat['catid'] not in result_set:
                result_set.add(cat['catid'])
                self._collect_descendant_catids(cat['catid'], categories, result_set)

    def _add_segments_for_code(self, code_node, cid, limit, x, y):
        """
        Add FreeTextGraphicsItem nodes for all coded text segments of a code.
        """
        from .view_graph import FreeTextGraphicsItem

        cur = self.app.conn.cursor()
        sql = ("select ct.ctid, ct.seltext, ifnull(ct.memo,''), source.name "
               "from code_text ct "
               "join source on source.id = ct.fid "
               "where ct.cid=? "
               "order by ct.pos0 limit ?")
        cur.execute(sql, [cid, limit])
        results = cur.fetchall()

        for si, r in enumerate(results):
            ctid = r[0]
            already = False
            for item in self.view_graph.scene.items():
                if isinstance(item, FreeTextGraphicsItem) and item.ctid == ctid:
                    already = True
                    break
            if already:
                continue

            seg_y = y + si * 40
            freetextid = 1
            for item in self.view_graph.scene.items():
                if isinstance(item, FreeTextGraphicsItem):
                    if item.freetextid >= freetextid:
                        freetextid = item.freetextid + 1

            text = r[1]
            if len(text) > 80:
                text = text[:80] + "..."
            seg_node = FreeTextGraphicsItem(self.app, freetextid, x, seg_y, text, 9, "black", False, ctid)
            msg = _("File: ") + f"{r[3]}\n" + _("Code: ") + code_node.code_or_cat['name']
            if r[2]:
                msg += "\n" + _("Memo: ") + r[2]
            seg_node.setToolTip(msg)
            seg_node.code_or_cat['cid'] = cid
            self.view_graph.scene.addItem(seg_node)
            self._add_free_line(code_node, seg_node, "gray", 2, "dotted")
