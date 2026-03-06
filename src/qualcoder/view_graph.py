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
import datetime
import fitz
import logging
from math import atan2, pi
import os
# from PIL import Image, ImageFont, ImageDraw
# from PIL.ImageQt import ImageQt
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import sqlite3

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog
from PyQt6.QtGui import QPdfWriter

from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import TextColor
from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_graph import Ui_DialogGraph
from .helpers import DialogCodeInAV, DialogCodeInImage, DialogCodeInText, \
    ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .save_sql_query import DialogSaveSql
from .select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

colors = {"red": QtCore.Qt.GlobalColor.red, "green": QtCore.Qt.GlobalColor.green,
          "cyan": QtCore.Qt.GlobalColor.cyan, "magenta": QtCore.Qt.GlobalColor.magenta,
          "yellow": QtGui.QColor("#FFD700"), "blue": QtGui.QColor("#6495ED"),
          "orange": QtGui.QColor("#FFA500"), "gray": QtGui.QColor("#808080"),
          "black": QtCore.Qt.GlobalColor.black, "white": QtCore.Qt.GlobalColor.white}

# --- class DialogSelectCodedSegments (NEW)
class DialogSelectCodedSegments(QDialog):
    """
    Unified window to select coded segments from text, image, and A/V.
    Displays three lists (QListWidget) in a single interface with checkboxes..
    """

    def __init__(self, app, code_name, text_codings, image_codings, av_codings, parent=None):
        """
        param: app : Main App
        param: code_name : String - nombre del código
        param: text_codings : list of dict con keys: name, cid, fid, memo, ctid, filename, codename
        param: image_codings : list of dict con keys: name, cid, fid, memo, imid, filename, codename, x, y, width, height, path, pdf_page
        param: av_codings : list of dict con keys: name, cid, fid, memo, avid, filename, codename, pos0, pos1, path
        """
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(f"Import coded segments: {code_name}")
        self.setMinimumSize(700, 520)
        self.text_codings = text_codings
        self.image_codings = image_codings
        self.av_codings = av_codings
        self.selected_text = []
        self.selected_image = []
        self.selected_av = []

        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)

        layout = QtWidgets.QVBoxLayout(self)

        # --- Sección TEXTO 
        label_text = QtWidgets.QLabel(f"Text segments ({len(text_codings)})")
        label_text.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(label_text)
        self.list_text = QtWidgets.QListWidget()
        self.list_text.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        for tc in text_codings:
            display = tc['name']
            if len(display) > 120:
                display = display[:120] + "..."
            display = f"[{tc['filename']}] {display}"
            item = QtWidgets.QListWidgetItem(display)
            item.setToolTip(f"File: {tc['filename']}\n{tc['name'][:300]}")
            self.list_text.addItem(item)
        layout.addWidget(self.list_text, stretch=3)

        # --- Sección horizontal inferior: IMAGEN y A/V lado a lado
        h_layout = QtWidgets.QHBoxLayout()

        # --- Sub-sección IMAGEN
        v_img = QtWidgets.QVBoxLayout()
        label_img = QtWidgets.QLabel(f"Image segments ({len(image_codings)})")
        label_img.setStyleSheet("font-weight: bold; margin-top: 4px;")
        v_img.addWidget(label_img)
        self.list_image = QtWidgets.QListWidget()
        self.list_image.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        for ic in image_codings:
            display = f"[{ic['filename']}] x:{ic['x']} y:{ic['y']} w:{ic['width']} h:{ic['height']}"
            item = QtWidgets.QListWidgetItem(display)
            item.setToolTip(f"File: {ic['filename']}\nArea: x:{ic['x']} y:{ic['y']} width:{ic['width']} height:{ic['height']}")
            self.list_image.addItem(item)
        v_img.addWidget(self.list_image)
        h_layout.addLayout(v_img)

        # --- Sub-sección A/V
        v_av = QtWidgets.QVBoxLayout()
        label_av = QtWidgets.QLabel(f"A/V segments ({len(av_codings)})")
        label_av.setStyleSheet("font-weight: bold; margin-top: 4px;")
        v_av.addWidget(label_av)
        self.list_av = QtWidgets.QListWidget()
        self.list_av.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        for ac in av_codings:
            display = f"[{ac['filename']}] {ac['pos0']} - {ac['pos1']} msecs"
            item = QtWidgets.QListWidgetItem(display)
            item.setToolTip(f"File: {ac['filename']}\nDuration: {ac['pos0']} - {ac['pos1']} msecs")
            self.list_av.addItem(item)
        v_av.addWidget(self.list_av)
        h_layout.addLayout(v_av)

        layout.addLayout(h_layout, stretch=2)

        # --- Botones Select All / Import / Cancel ---
        btn_layout = QtWidgets.QHBoxLayout()

        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_select_all.clicked.connect(self.select_all)
        btn_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = QtWidgets.QPushButton("Deselect All")
        self.btn_deselect_all.clicked.connect(self.deselect_all)
        btn_layout.addWidget(self.btn_deselect_all)

        btn_layout.addStretch()

        self.btn_import = QtWidgets.QPushButton("Import selected")
        self.btn_import.setDefault(True)
        self.btn_import.clicked.connect(self.do_import)
        btn_layout.addWidget(self.btn_import)

        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def select_all(self):
        self.list_text.selectAll()
        self.list_image.selectAll()
        self.list_av.selectAll()

    def deselect_all(self):
        self.list_text.clearSelection()
        self.list_image.clearSelection()
        self.list_av.clearSelection()

    def do_import(self):
        self.selected_text = [self.text_codings[idx.row()] for idx in self.list_text.selectedIndexes()]
        self.selected_image = [self.image_codings[idx.row()] for idx in self.list_image.selectedIndexes()]
        self.selected_av = [self.av_codings[idx.row()] for idx in self.list_av.selectedIndexes()]
        if not self.selected_text and not self.selected_image and not self.selected_av:
            return
        self.accept()
# ---

class ViewGraph(QDialog):
    """ Dialog to view code and categories in an acyclic graph. Provides options for
    colors and amount of nodes to display (based on category selection).
    """

    app = None
    conn = None
    settings = None
    scene = None
    categories = []
    codes = []
    font_size = 9
    load_graph_menu_option = "Alphabet ascending"

    def __init__(self, app):
        """ Set up the dialog. """

        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogGraph()
        self.ui.setupUi(self)
        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.pushButton_export_pdf.setIcon(qta.icon('mdi6.file-pdf-box', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export_pdf.pressed.connect(self.export_pdf_graph)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.image-move', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export.pressed.connect(self.export_image)
        
        # NUEVO: Conectar botón de Draw.io
        if hasattr(self.ui, 'pushButton_export_drawio'):
            self.ui.pushButton_export_drawio.setIcon(qta.icon('mdi6.sitemap', options=[{'scale_factor': 1.3}]))
            self.ui.pushButton_export_drawio.pressed.connect(self.export_drawio)
        # ---    
        self.ui.label_zoom.setPixmap(qta.icon('mdi6.magnify').pixmap(22, 22))
        self.ui.pushButton_reveal.setIcon(qta.icon('mdi6.eye', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_reveal.pressed.connect(self.reveal_hidden_items)
        self.ui.pushButton_clear.setIcon(qta.icon('mdi6.undo', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_clear.pressed.connect(self.clear_items)
        self.ui.pushButton_selectbranch.setIcon(qta.icon('mdi6.file-tree', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_selectbranch.pressed.connect(self.select_tree_branch)
        self.ui.pushButton_freetextitem.setIcon(qta.icon('mdi6.text-box-edit-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_freetextitem.pressed.connect(self.add_text_item_to_graph)
        self.ui.pushButton_addfile.setIcon(qta.icon('mdi6.file-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_addfile.pressed.connect(self.add_files_to_graph)
        self.ui.pushButton_addcase.setIcon(qta.icon('mdi6.briefcase-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_addcase.pressed.connect(self.add_cases_to_graph)
        self.ui.pushButton_addline.setIcon(qta.icon('mdi6.chart-line-variant', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_addline.pressed.connect(self.add_lines_to_graph)
        self.ui.pushButton_loadgraph.setIcon(qta.icon('mdi6.file-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_loadgraph.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.pushButton_loadgraph.customContextMenuRequested.connect(self.load_graph_menu)
        self.ui.pushButton_loadgraph.pressed.connect(self.load_graph)
        self.ui.pushButton_savegraph.setIcon(qta.icon('mdi6.file-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_savegraph.pressed.connect(self.save_graph)
        self.ui.pushButton_deletegraph.setIcon(qta.icon('mdi6.file-minus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_deletegraph.pressed.connect(self.delete_saved_graph)
        self.ui.pushButton_codes_of_text.setIcon(qta.icon('mdi6.text', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_codes_of_text.pressed.connect(self.add_coded_text_of_text_files)
        if not self.app.get_image_and_pdf_filenames():
            self.ui.pushButton_codes_of_images.setEnabled(False)
        self.ui.pushButton_codes_of_images.setIcon(qta.icon('mdi6.image-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_codes_of_images.pressed.connect(self.add_codes_of_image_files)
        if not self.app.get_av_filenames():
            self.ui.pushButton_codes_of_av.setEnabled(False)
        self.ui.pushButton_codes_of_av.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_codes_of_av.pressed.connect(self.add_codes_of_av_files)
        self.ui.pushButton_memos_of_file.setIcon(qta.icon('mdi6.text-long', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_memos_of_file.pressed.connect(self.add_memos_of_coded)

        # Set the scene
        self.scene = GraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)
        # Configurar selección múltiple por arrastre (clic izquierdo sostenido)
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        #---
        self.codes, self.categories = app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "
        # Variables para controlar el arrastre del lienzo
        self._space_pressed = False
        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        # --- ADD Frequencies
        self.show_frequencies = False
        # ---        
        

    def clear_items(self):
        """ Clear all items from scene.
        Called by pushButton_clear. """

        msg = _("Are you sure you want to clear the graph?")
        ui = DialogConfirmDelete(self.app, msg)
        ok = ui.exec()
        if not ok:
            return
        self.scene.clear()
        self.scene.set_width(990)
        self.scene.set_height(650)
        self.ui.label_loaded_graph.setText("")
        self.ui.label_loaded_graph.setToolTip("")

    def select_tree_branch(self):
        """ Selected tree branch for model of codes and categories.
        Called by pushButton_selectbranch
        """

        selection_list = [{'name': 'All'}]
        for category in self.categories:
            selection_list.append({'name': category['name']})
        ui = DialogSelectItems(self.app, selection_list, _("Select code tree branch"), "multi")
        ok = ui.exec()
        if not ok:
            return
        # --- mejorar seleccion multiple    
        selected = ui.get_selected()
        if not selected:
            cats, codes, model = self.create_initial_model()
            model = self.get_refined_model_with_category_counts(cats, model, "All")
            self.list_graph(model)
            return
        # Import each selected branch
        for sel in selected:
            node_text = sel['name']
            cats, codes, model = self.create_initial_model()
            model = self.get_refined_model_with_category_counts(cats, model, node_text)
            self.list_graph(model)
        # ---

    def create_initial_model(self):
        """ Create initial model of codes and categories.
        model contains categories and codes combined.

        return: categories : List of Dictionaries of categories
        return: codes : List of Dictionaries of codes
        return: model : List of Dictionaries of codes and categories
        """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)

        for code_ in codes:
            code_['x'] = None
            code_['y'] = None
            code_['supercatid'] = code_['catid']
        for cat in cats:
            cat['x'] = None
            cat['y'] = None
            cat['cid'] = None
            cat['color'] = '#FFFFFF'
        model = cats + codes
        return cats, codes, model

    def get_refined_model_with_category_counts(self, cats, model, top_node_text):
        """ The initial model contains all categories and codes.
        The refined model method is called and based on a selected category, via QButton_selection.
        The refined model also gets counts for nodes of each category

        param: cats : List of Dictionaries of categories
        param: model : List of Dictionaries of combined categories and codes
        param: top_node_text : String name of the top category

        return: model : List of Dictionaries
        """

        top_node = None
        if top_node_text == "All":
            top_node = None
        else:
            for cat in cats:
                if cat['name'] == top_node_text:
                    top_node = cat
                    top_node['supercatid'] = None  # Must set this to None
        model = self.get_refined_model(top_node, model)
        return model

    @staticmethod
    def get_refined_model(node, model):
        """ Return a refined model of this top node and all its children.
        Called by: get_refined_model_with_category_counts

        param: node : Dictionary of category, or None
        param: model : List of Dictionaries - of categories and codes

        return: new_model : List of Dictionaries of categories and codes
        """

        if node is None:
            return model
        refined_model = [node]
        i = 0  # Ensure an exit from while loop
        model_changed = True
        while model != [] and model_changed and i < 20:
            model_changed = False
            append_list = []
            for refined_item in refined_model:
                for model_item in model:
                    if model_item['supercatid'] == refined_item['catid']:
                        append_list.append(model_item)
            for append_item in append_list:
                refined_model.append(append_item)
                model.remove(append_item)
                model_changed = True
            i += 1
        return refined_model

    def named_children_of_node(self, node):
        """ Get child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.

        param: node : Dictionary of category

        return: child_names : List
        """

        if node['cid'] is not None:
            return []
        child_names = []
        codes, categories = self.app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in codes:
            for cat in categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in categories:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for n in append_list:
                selected_categories.append(n)
                categories.remove(n)
                new_model_changed = True
            i += 1
        categories = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in categories:
            for code in codes:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        codes = selected_codes
        for c in codes:
            child_names.append(c['name'])
        return child_names

    def list_graph(self, model):
        """ Create a list graph with the categories on the left and codes on the right.
        Additive, adds another model of nodes to the scene.
        Does not add nodes that are already existing in the scene.

        param: model : List of Dictionaries of categories and codes
        """

        # Order the model by supercatid, subcats, codes
        ordered_model = []
        # Top level categories
        for code_or_category in model:
            if code_or_category['x'] is None and code_or_category['supercatid'] is None:
                code_or_category['x'] = 10
                ordered_model.append(code_or_category)
        for om in ordered_model:
            model.remove(om)

        # Sub-categories and codes
        i = 0
        while i < 1000 and len(model) > 0:
            for om in ordered_model:
                for sub_cat in model:
                    # subordinate categories
                    if sub_cat['supercatid'] == om['catid'] and sub_cat['x'] is None:
                        sub_cat['x'] = om['x'] + 120
                        ordered_model.insert(ordered_model.index(om), sub_cat)
            i += 1

        for item in range(0, len(ordered_model)):
            ordered_model[item]['y'] = item * self.font_size * 3
        model = ordered_model

        # Add text items to the scene, providing they are not already in the scene.
        for code_or_category in model:
            code_or_category['child_names'] = self.named_children_of_node(code_or_category)
            add_to_scene = True
            for scene_item in self.scene.items():
                if isinstance(scene_item, TextGraphicsItem):
                    if scene_item.code_or_cat['name'] == code_or_category['name'] and \
                            scene_item.code_or_cat['catid'] == code_or_category['catid'] and \
                            scene_item.code_or_cat['cid'] == code_or_category['cid']:
                        add_to_scene = False
            if add_to_scene:
                self.scene.addItem(TextGraphicsItem(self.app, code_or_category))

        # Add link from Category to Category, which includes the scene text items and associated data
        for scene_item in self.scene.items():
            if isinstance(scene_item, TextGraphicsItem):
                for scene_item2 in self.scene.items():
                    if isinstance(scene_item2, TextGraphicsItem) and \
                            scene_item.code_or_cat['supercatid'] is not None and \
                            scene_item.code_or_cat['supercatid'] == scene_item2.code_or_cat['catid'] and \
                            (scene_item.code_or_cat['cid'] is None and scene_item2.code_or_cat['cid'] is None):
                        item = LinkGraphicsItem(scene_item, scene_item2, 2, "solid", "gray", True)
                        self.scene.addItem(item)
        # Add links from Codes to Categories
        for scene_item in self.scene.items():
            if isinstance(scene_item, TextGraphicsItem):
                for scene_item2 in self.scene.items():
                    # Link the n Codes to m Categories
                    if isinstance(scene_item2, TextGraphicsItem) and \
                            scene_item2.code_or_cat['cid'] is not None and \
                            scene_item.code_or_cat['cid'] is None and \
                            scene_item.code_or_cat['catid'] == scene_item2.code_or_cat['catid']:
                        item = LinkGraphicsItem(scene_item, scene_item2, 2, "solid", "gray", True)
                        self.scene.addItem(item)
        # Expand scene width and height if needed
        max_x, max_y = self.scene.suggested_scene_size()
        self.scene.set_width(max_x)
        self.scene.set_height(max_y)

    def reveal_hidden_items(self):
        """ Show list of hidden items to be revealed on selection """

        hidden = []
        for item in self.scene.items():
            if not item.isVisible():
                if isinstance(item, TextGraphicsItem):
                    hidden.append({"name": _("Text: ") + item.text, "item": item})
                if isinstance(item, LinkGraphicsItem):
                    hidden.append({"name": _("Link: ") + item.text, "item": item})
        if not hidden:
            return
        ui = DialogSelectItems(self.app, hidden, _("Reveal hidden items"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        for s in selected:
            s['item'].show()
            
        # Refrescar automáticamente para reconectar líneas de nodos ahora visibles
        self.refresh_lines_visibility()

    def keyPressEvent(self, event):
        """ Plus, W to zoom in and Minus, Q to zoom out. Space for panning. """
        key = event.key()
        
        # Paneo: Activar modo mano al presionar espacio
        if key == QtCore.Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            # CAMBIO: Cambiar a modo de arrastre de mano
            self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            self.ui.graphicsView.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            return

        if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() > 10:
                return
            self.ui.graphicsView.scale(1.1, 1.1)
        if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() < 0.1:
                return
            self.ui.graphicsView.scale(0.9, 0.9)
        if key == QtCore.Qt.Key.Key_H:
            # print item x y
            for i in self.scene.items():
                print(i.__class__, i.pos())

    def keyReleaseEvent(self, event):
        """ Soltar espacio para desactivar el paneo. """
        if event.key() == QtCore.Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            # CAMBIO: Volver al modo de selección por cuadro
            self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.ui.graphicsView.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)

    def reject(self):
        super(ViewGraph, self).reject()

    def accept(self):
        super(ViewGraph, self).accept()

    def eventFilter(self, obj, event):
        if obj == self.ui.graphicsView.viewport():
            # ZOOM: Rueda del ratón
            if event.type() == QtCore.QEvent.Type.Wheel:
                self.ui.graphicsView.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
                if event.angleDelta().y() > 0:
                    if not (self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() > 10):
                        self.ui.graphicsView.scale(1.1, 1.1)
                else:
                    if not (self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() < 0.1):
                        self.ui.graphicsView.scale(0.9, 0.9)
                return True
                
            # PANEO: Solo se activa con Botón Central o (Espacio + Clic Izquierdo)
            elif event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.MiddleButton or (event.button() == QtCore.Qt.MouseButton.LeftButton and getattr(self, '_space_pressed', False)):
                    self._is_panning = True
                    self._pan_start_x = event.position().x()
                    self._pan_start_y = event.position().y()
                    return True
                    
            # PANEO: Arrastrar ratón
            elif event.type() == QtCore.QEvent.Type.MouseMove and getattr(self, '_is_panning', False):
                dx = event.position().x() - self._pan_start_x
                dy = event.position().y() - self._pan_start_y
                
                # AJUSTE FINO INDEPENDIENTE: Suma (+) para X y Resta (-) para Y
                self.ui.graphicsView.horizontalScrollBar().setValue(int(self.ui.graphicsView.horizontalScrollBar().value() + dx))
                self.ui.graphicsView.verticalScrollBar().setValue(int(self.ui.graphicsView.verticalScrollBar().value() - dy))
                
                self._pan_start_x = event.position().x()
                self._pan_start_y = event.position().y()
                return True
                
            # PANEO: Soltar ratón
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                if getattr(self, '_is_panning', False) and (event.button() == QtCore.Qt.MouseButton.MiddleButton or event.button() == QtCore.Qt.MouseButton.LeftButton):
                    self._is_panning = False
                    cursor = QtCore.Qt.CursorShape.OpenHandCursor if getattr(self, '_space_pressed', False) else QtCore.Qt.CursorShape.ArrowCursor
                    self.ui.graphicsView.viewport().setCursor(cursor)
                    return True

            # MENÚ CONTEXTUAL
            elif event.type() == event.Type.ContextMenu:
                self.ui.graphicsView.contextMenuEvent(event)
                return event.isAccepted()
                
        return super().eventFilter(obj, event)

    def graphicsview_menu(self, position):
        item = self.ui.graphicsView.itemAt(position)
        if item is not None:
            self.scene.sendEvent(item)
            return
        # Menu for blank graphics view area
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_add_text_item = menu.addAction(_("Insert Text"))
        action_add_line = menu.addAction(_("Insert Line"))
        action_add_coded_text = menu.addAction(_("Insert coded text items"))
        action_add_coded_image = menu.addAction(_("Insert coded image items"))
        action_add_coded_av = menu.addAction(_("Insert coded A/V items"))
        # -- DELETE: action_add_files = menu.addAction(_("Show files"))
        # -- DELETE: action_add_cases = menu.addAction(_("Show cases"))
        action_memos = menu.addAction(_("Show memos of coded segments"))
        
        # --- NUEVAS VISTAS ANALÍTICAS ---
        menu.addSeparator()
        action_fit_and_center = menu.addAction("Fit and Center View")
        menu.addSeparator()
        action_import_cooc = menu.addAction("Import Code(s) with Co-occurrences")
        
        # NUEVO: Sub-menú para agrupar los modelos visuales
        layout_menu = menu.addMenu("Organize graph")
        action_radial_layout = layout_menu.addAction("Radial")
        action_tree_layout = layout_menu.addAction("Top to Bottom")
        action_lr_layout = layout_menu.addAction("Left to Right")
        action_rl_layout = layout_menu.addAction("Right to Left")
        
        menu.addSeparator()
        action_refresh_lines = menu.addAction("Refresh view")
        # --
        menu.addSeparator()
        if self.show_frequencies:
            action_toggle_freq = menu.addAction("Hide frequencies")
        else:
            action_toggle_freq = menu.addAction("Display frequencies")        
        # --
        
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        
        if action == action_add_text_item:
            self.add_text_item_to_graph(position.x(), position.y())
        if action == action_add_coded_text:
            self.add_coded_text_of_text_files(position.x(), position.y())
        if action == action_add_coded_image:
            self.add_codes_of_image_files(position.x(), position.y())
        if action == action_add_coded_av:
            self.add_codes_of_av_files(position.x(), position.y())
        if action == action_memos:
            self.add_memos_of_coded(position.x(), position.y())
        if action == action_add_line:
            self.add_lines_to_graph()
        # --- DELETE: if action == action_add_files:
        # --- DELETE:     self.add_files_to_graph()
        # --- DELETE: if action == action_add_cases:
        # --- DELETE:     self.add_cases_to_graph()
            
        # --- EJECUCIÓN DE VISTAS ANALÍTICAS Y AJUSTES ---
        if action == action_fit_and_center:
            rect = self.scene.itemsBoundingRect()
            rect.adjust(-100, -100, 100, 100)
            self.scene.setSceneRect(rect)
            self.ui.graphicsView.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            self.ui.graphicsView.centerOn(rect.center())
            
        if action == action_import_cooc:
            self.import_codes_and_cooccurrences(position.x(), position.y())
        if action == action_radial_layout:
            self.organize_radially()
        if action == action_tree_layout:
            self.organize_hierarchically()
        if action == action_lr_layout:
            self.organize_horizontal("LR")
        if action == action_rl_layout:
            self.organize_horizontal("RL")
        if action == action_refresh_lines:
            self.refresh_lines_visibility()
        # ---
        if action == action_toggle_freq:
            self.toggle_frequencies()
        # ---
    # --- add frequency    
    def toggle_frequencies(self):
        """ Toggle display of coding frequencies on code and category nodes. """
        self.show_frequencies = not self.show_frequencies
        cur = self.app.conn.cursor()
        for item in self.scene.items():
            if isinstance(item, TextGraphicsItem):
                base_name = item.code_or_cat['name']
                if self.show_frequencies:
                    count = 0
                    if item.code_or_cat['cid'] is not None:
                        # Count across ALL three coding tables
                        cid = item.code_or_cat['cid']
                        cur.execute("select count(*) from code_text where cid=?", [cid])
                        res = cur.fetchone()
                        if res:
                            count += res[0]
                        cur.execute("select count(*) from code_image where cid=?", [cid])
                        res = cur.fetchone()
                        if res:
                            count += res[0]
                        cur.execute("select count(*) from code_av where cid=?", [cid])
                        res = cur.fetchone()
                        if res:
                            count += res[0]
                    else:
                        # Category: sum of all codes underneath across all tables
                        child_names = item.code_or_cat.get('child_names', [])
                        if child_names:
                            for cn in child_names:
                                cur.execute("select cid from code_name where name=?", [cn])
                                res_cid = cur.fetchone()
                                if res_cid:
                                    cid = res_cid[0]
                                    cur.execute("select count(*) from code_text where cid=?", [cid])
                                    r = cur.fetchone()
                                    if r:
                                        count += r[0]
                                    cur.execute("select count(*) from code_image where cid=?", [cid])
                                    r = cur.fetchone()
                                    if r:
                                        count += r[0]
                                    cur.execute("select count(*) from code_av where cid=?", [cid])
                                    r = cur.fetchone()
                                    if r:
                                        count += r[0]
                    item.text = f"{base_name} [{count}]"
                else:
                    # Remove frequency suffix
                    item.text = base_name
                item.setPlainText(item.text)
        self.scene.update()
    # --- 
    # --- FUNCIONES DE ORGANIZACIÓN ESPACIAL 
    def import_codes_and_cooccurrences(self, x, y):
        """ Importa un código y sus co-ocurrencias sin duplicados (Solución str estricta) """
        if not self.codes:
            Message(self.app, _("No codes"), _("There are no codes in this project.")).exec()
            return
            
        ui = DialogSelectItems(self.app, self.codes, "Select Code(s) to import", "multi")
        if not ui.exec():
            return
            
        selected_codes = ui.get_selected()
        
        import math
        cur = self.app.conn.cursor()

        for idx, sc in enumerate(selected_codes):
            cx = x + (idx * 350)
            cy = y
            
            # CORRECCIÓN: str() para evitar error de int vs string y prevenir duplicados del Nodo Principal
            main_node = next((item for item in self.scene.items() if type(item).__name__ == "TextGraphicsItem" and str(item.code_or_cat.get('cid')) == str(sc['cid'])), None)
            
            if not main_node:
                code_data = {'name': sc['name'], 'supercatid': sc.get('supercatid'), 'catid': sc.get('catid'), 'cid': sc['cid'], 
                             'x': cx, 'y': cy, 'color': sc['color'], 'memo': sc.get('memo', ''), 'child_names': []}
                main_node = TextGraphicsItem(self.app, code_data)
                self.scene.addItem(main_node)
            else:
                cx, cy = main_node.pos().x(), main_node.pos().y()

            sql = """
            SELECT c2.cid, n2.name, n2.color, COUNT(c2.cid) as overlap_count
            FROM code_text c1
            JOIN code_text c2 ON c1.fid = c2.fid AND c1.cid != c2.cid AND c1.pos0 < c2.pos1 AND c1.pos1 > c2.pos0
            JOIN code_name n2 ON c2.cid = n2.cid
            WHERE c1.cid = ?
            GROUP BY c2.cid, n2.name, n2.color
            """
            cur.execute(sql, [sc['cid']])
            res = cur.fetchall()

            if res:
                radius = max(120, len(res) * 20) 
                angle_step = (2 * math.pi) / max(1, len(res))

                for i, r in enumerate(res):
                    cooc_cid, cooc_name, cooc_color, overlap_count = r
                    
                    # str() para evitar duplicados en los Nodos Destino
                    target_node = next((item for item in self.scene.items() if type(item).__name__ == "TextGraphicsItem" and str(item.code_or_cat.get('cid')) == str(cooc_cid)), None)
                    
                    if not target_node:
                        nx = cx + radius * math.cos(i * angle_step)
                        ny = cy + radius * math.sin(i * angle_step)
                        cooc_data = {'name': cooc_name, 'supercatid': None, 'catid': None, 'cid': cooc_cid, 
                                     'x': nx, 'y': ny, 'color': cooc_color, 'memo': "", 'child_names': []}
                        # Cambiamos 'code_data' por 'cooc_data'             
                        target_node = TextGraphicsItem(self.app, cooc_data)
                        self.scene.addItem(target_node)

                    # Verificar que la LÍNEA no exista ya en ninguna de las dos direcciones
                    line_exists = any(type(link).__name__ == "LinkGraphicsItem" and 
                                      ((link.from_widget == main_node and link.to_widget == target_node) or 
                                       (link.from_widget == target_node and link.to_widget == main_node)) 
                                      for link in self.scene.items())
                                      
                    if not line_exists:
                        line_item = LinkGraphicsItem(main_node, target_node, line_width=2, line_type="dotted", color="blue", isvisible=True)
                        self.scene.addItem(line_item)
                        
        self.scene.suggested_scene_size()
        self.scene.update()


    def refresh_lines_visibility(self):
        """ Oculta líneas conectadas a nodos invisibles """
        for item in self.scene.items():
            if isinstance(item, LinkGraphicsItem) or isinstance(item, FreeLineGraphicsItem):
                if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                    if not item.from_widget.isVisible() or not item.to_widget.isVisible():
                        item.hide()
                    else:
                        item.show()
        self.scene.update()

    def organize_hierarchically(self):
        """
        Top-Down Tree Layout (v2)
        ─────────────────────────
        Mejoras sobre la versión original:
          1. Raíz inteligente: prioriza categorías sin supercatid (raíz semántica real).
          2. Espaciado vertical adaptativo según la altura real de cada nivel.
          3. Gap explícito entre subárboles/componentes desconectados.
          4. Segunda pasada de centrado para que los padres queden alineados
             sobre el centro exacto de sus hijos (sin desvíos por colisión).
          5. Ancho de subárbol calculado recursivamente para evitar solapamientos.
        """
        # ── 0. Recolectar nodos y enlaces visibles ──────────────────────
        nodes = []
        links = []
        for item in self.scene.items():
            if not item.isVisible():
                continue
            if isinstance(item, (TextGraphicsItem, FreeTextGraphicsItem,
                                 CaseTextGraphicsItem, FileTextGraphicsItem,
                                 PixmapGraphicsItem, AVGraphicsItem)):
                nodes.append(item)
            elif isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                links.append(item)

        if not nodes:
            return

        # ── 1. Grafo no dirigido ────────────────────────────────────────
        adjacency = {n: set() for n in nodes}
        for link in links:
            if hasattr(link, 'from_widget') and hasattr(link, 'to_widget'):
                u, v = link.from_widget, link.to_widget
                if u in adjacency and v in adjacency:
                    adjacency[u].add(v)
                    adjacency[v].add(u)

        # ── 2. Componentes conectados ───────────────────────────────────
        visited_global = set()
        components = []
        for n in nodes:
            if n not in visited_global:
                comp = []
                queue = [n]
                visited_global.add(n)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for nb in adjacency[curr]:
                        if nb not in visited_global:
                            visited_global.add(nb)
                            queue.append(nb)
                components.append(comp)

        # ── 3. Selección inteligente de raíz por componente ─────────────
        #    Prioridad: categoría sin supercatid > más conexiones > primero en lista
        def pick_root(comp_nodes):
            # Buscar categorías raíz reales (supercatid == None y cid == None)
            top_cats = [
                n for n in comp_nodes
                if isinstance(n, TextGraphicsItem)
                and n.code_or_cat is not None
                and n.code_or_cat.get('cid') is None
                and n.code_or_cat.get('supercatid') is None
            ]
            if top_cats:
                # Si hay varias, elegir la más conectada
                return max(top_cats, key=lambda x: len(adjacency[x]))
            # Fallback: nodo con más conexiones
            return max(comp_nodes, key=lambda x: len(adjacency[x]))

        # ── 4. Árbol expansivo (BFS) por componente ────────────────────
        tree_children = {n: [] for n in nodes}
        roots = []
        for comp in components:
            root = pick_root(comp)
            roots.append(root)
            visited_tree = {root}
            queue = [root]
            while queue:
                curr = queue.pop(0)
                # Ordenar vecinos para obtener un layout determinista
                # (categorías primero, luego códigos, ambos alfabéticos)
                sorted_neighbors = sorted(
                    adjacency[curr],
                    key=lambda n: (
                        0 if (isinstance(n, TextGraphicsItem) and n.code_or_cat
                              and n.code_or_cat.get('cid') is None) else 1,
                        getattr(n, 'text', '')
                    )
                )
                for nb in sorted_neighbors:
                    if nb not in visited_tree:
                        visited_tree.add(nb)
                        tree_children[curr].append(nb)
                        queue.append(nb)

        # ── 5. Calcular dimensiones reales de cada nodo ─────────────────
        H_PAD = 30    # Espacio horizontal mínimo entre nodos hermanos
        V_PAD = 40    # Espacio vertical extra sobre la altura máxima del nivel
        COMP_GAP = 80 # Espacio horizontal entre componentes desconectados

        def node_width(n):
            if hasattr(n, 'boundingRect'):
                return n.boundingRect().width()
            return 100

        def node_height(n):
            if hasattr(n, 'boundingRect'):
                return n.boundingRect().height()
            return 30

        # ── 6. Calcular la altura máxima por nivel (profundidad) ────────
        level_max_height = {}

        def compute_level_heights(node, depth):
            h = node_height(node)
            if depth not in level_max_height or h > level_max_height[depth]:
                level_max_height[depth] = h
            for child in tree_children.get(node, []):
                compute_level_heights(child, depth + 1)

        for r in roots:
            compute_level_heights(r, 0)

        # Convertir alturas máximas en posiciones Y acumuladas
        max_depth = max(level_max_height.keys()) if level_max_height else 0
        level_y = {}
        cumulative_y = 0
        for d in range(max_depth + 1):
            level_y[d] = cumulative_y
            cumulative_y += level_max_height.get(d, 30) + V_PAD

        # ── 7. Calcular ancho de subárbol (recursivo, bottom-up) ────────
        subtree_width = {}

        def compute_subtree_width(node):
            children = tree_children.get(node, [])
            if not children:
                w = node_width(node)
                subtree_width[node] = w
                return w
            children_total = sum(compute_subtree_width(c) for c in children)
            # Añadir gaps entre hijos
            children_total += H_PAD * (len(children) - 1)
            # El subárbol es al menos tan ancho como el propio nodo
            w = max(node_width(node), children_total)
            subtree_width[node] = w
            return w

        for r in roots:
            compute_subtree_width(r)

        # ── 8. Posicionar nodos ─────────────────────────────────────────
        def set_pos(n, x, y):
            if hasattr(n, 'code_or_cat') and n.code_or_cat is not None:
                n.code_or_cat['x'] = x
                n.code_or_cat['y'] = y
            n.setPos(x, y)

        def layout_subtree(node, left_x, depth):
            """
            Posiciona 'node' y todos sus descendientes.
            'left_x' es el borde izquierdo del espacio asignado a este subárbol.
            Retorna el centro X del nodo para que el padre se centre sobre sus hijos.
            """
            children = tree_children.get(node, [])
            my_width = subtree_width[node]
            y = level_y[depth]

            if not children:
                # Hoja: centrar el nodo dentro de su espacio asignado
                node_x = left_x + (my_width - node_width(node)) / 2
                set_pos(node, node_x, y)
                return left_x + my_width / 2  # Devolver el centro

            # Distribuir hijos dentro del espacio del subárbol
            children_total_width = (
                sum(subtree_width[c] for c in children)
                + H_PAD * (len(children) - 1)
            )
            # Centrar el bloque de hijos dentro del espacio del padre
            child_left = left_x + (my_width - children_total_width) / 2

            child_centers = []
            for child in children:
                cx = layout_subtree(child, child_left, depth + 1)
                child_centers.append(cx)
                child_left += subtree_width[child] + H_PAD

            # Centrar el padre sobre el promedio de los centros de sus hijos
            parent_center = sum(child_centers) / len(child_centers)
            parent_x = parent_center - node_width(node) / 2
            set_pos(node, parent_x, y)
            return parent_center

        # Recorrer cada componente con un gap entre ellos
        rect = self.scene.itemsBoundingRect()
        current_left = rect.left() + 50

        for root in roots:
            layout_subtree(root, current_left, 0)
            current_left += subtree_width[root] + COMP_GAP

        # --- 9. Redibujar conexiones 
        for link in links:
            if hasattr(link, 'redraw'):
                link.redraw()

        self.scene.suggested_scene_size()
        self.scene.update()

    def organize_horizontal(self, direction="LR"):
        """ Horizontal Tree Layout: Usa grafos no dirigidos. LR (Izquierda-Derecha) o RL (Derecha-Izquierda). """
        nodes = []
        links = []
        for item in self.scene.items():
            if not item.isVisible(): continue
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
               isinstance(item, CaseTextGraphicsItem) or isinstance(item, FileTextGraphicsItem) or \
               isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                nodes.append(item)
            elif isinstance(item, LinkGraphicsItem) or isinstance(item, FreeLineGraphicsItem):
                links.append(item)

        if not nodes: return

        # 1. Grafo no dirigido
        adjacency = {n: set() for n in nodes}
        for link in links:
            if hasattr(link, 'from_widget') and hasattr(link, 'to_widget'):
                u, v = link.from_widget, link.to_widget
                if u in adjacency and v in adjacency:
                    adjacency[u].add(v)
                    adjacency[v].add(u)

        # 2. Encontrar familias conectadas y raíces
        visited_global = set()
        components = []
        for n in nodes:
            if n not in visited_global:
                comp_nodes = []
                queue = [n]
                visited_global.add(n)
                while queue:
                    curr = queue.pop(0)
                    comp_nodes.append(curr)
                    for neighbor in adjacency[curr]:
                        if neighbor not in visited_global:
                            visited_global.add(neighbor)
                            queue.append(neighbor)
                components.append(comp_nodes)

        # 3. Construir árbol BFS
        tree_children = {n: [] for n in nodes}
        roots = []
        for comp in components:
            root = max(comp, key=lambda x: len(adjacency[x]))
            roots.append(root)
            visited_tree = set([root])
            queue = [root]
            while queue:
                curr = queue.pop(0)
                for neighbor in adjacency[curr]:
                    if neighbor not in visited_tree:
                        visited_tree.add(neighbor)
                        tree_children[curr].append(neighbor)
                        queue.append(neighbor)

        # 4. Asignar posiciones espaciales
        rect = self.scene.itemsBoundingRect()
        start_y = rect.center().y() - (len(nodes) * 20)

        start_x = rect.left() + 50 if direction == "LR" else rect.right() - 50
        x_multiplier = 1 if direction == "LR" else -1

        def set_pos(n, x, y):
            if hasattr(n, 'code_or_cat') and n.code_or_cat is not None:
                n.code_or_cat['x'], n.code_or_cat['y'] = x, y
            n.setPos(x, y)

        current_y = start_y
        def layout_node(node, depth):
            nonlocal current_y
            node_h = node.boundingRect().height() if hasattr(node, 'boundingRect') else 40
            node_x = start_x + (depth * 280 * x_multiplier)

            ch = tree_children.get(node, [])
            if not ch:
                y = current_y
                set_pos(node, node_x, y)
                current_y += node_h + 20
                return y

            c_ys = [layout_node(c, depth + 1) for c in ch]
            parent_y = sum(c_ys) / len(c_ys) if c_ys else current_y
            set_pos(node, node_x, parent_y)

            expected_bottom = parent_y + node_h + 20
            if current_y < expected_bottom: current_y = expected_bottom
            return parent_y

        for r in roots:
            layout_node(r, 0)

        for link in links:
            if hasattr(link, 'redraw'): link.redraw()

        self.scene.suggested_scene_size()
        self.scene.update()

    def organize_radially(self):
        """ Radial Tree Layout: Pone el nodo más conectado en el centro absoluto y abre sus conexiones en estrella. """
        nodes = []
        links = []
        for item in self.scene.items():
            if not item.isVisible(): continue
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
               isinstance(item, CaseTextGraphicsItem) or isinstance(item, FileTextGraphicsItem) or \
               isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                nodes.append(item)
            elif isinstance(item, LinkGraphicsItem) or isinstance(item, FreeLineGraphicsItem):
                links.append(item)
                
        if not nodes: return

        import math
        rect = self.scene.itemsBoundingRect()
        center_x, center_y = rect.center().x(), rect.center().y()

        def set_pos(n, x, y):
            w = n.boundingRect().width() / 2 if hasattr(n, 'boundingRect') else 0
            h = n.boundingRect().height() / 2 if hasattr(n, 'boundingRect') else 0
            nx, ny = x - w, y - h
            if hasattr(n, 'code_or_cat') and n.code_or_cat is not None:
                n.code_or_cat['x'], n.code_or_cat['y'] = nx, ny
            n.setPos(nx, ny)

        # 1. Construir grafo no dirigido para encontrar el centro real sin importar dirección de flechas
        adjacency = {n: set() for n in nodes}
        for link in links:
            if hasattr(link, 'from_widget') and hasattr(link, 'to_widget'):
                u, v = link.from_widget, link.to_widget
                if u in adjacency and v in adjacency:
                    adjacency[u].add(v)
                    adjacency[v].add(u)
                    
        # 2. Encontrar el nodo más conectado (El centro absoluto o "Rey")
        main_root = max(nodes, key=lambda n: len(adjacency[n]))
        
        # 3. Construir un árbol en abanico (BFS) desde el main_root
        tree_children = {n: [] for n in nodes}
        visited_tree = set([main_root])
        queue = [main_root]
        
        while queue:
            current = queue.pop(0)
            for neighbor in adjacency[current]:
                if neighbor not in visited_tree:
                    visited_tree.add(neighbor)
                    tree_children[current].append(neighbor)
                    queue.append(neighbor)

        # 4. Calcular "hojas" para distribuir el ángulo del círculo equitativamente
        leaves_count = {}
        def calc_leaves(node):
            ch = tree_children.get(node, [])
            if not ch:
                leaves_count[node] = 1
                return 1
            count = sum(calc_leaves(c) for c in ch)
            leaves_count[node] = count
            return count

        calc_leaves(main_root)

        radius_step = 280 # Distancia entre anillos ampliada para que se vea limpio

        # 5. Dibujar la estrella principal
        drawn_nodes = set()
        def layout_radial(node, depth, angle_start, angle_end):
            drawn_nodes.add(node)
            mid_angle = (angle_start + angle_end) / 2
            
            if depth == 0:
                set_pos(node, center_x, center_y)
            else:
                current_radius = max(200, depth * radius_step)
                x = center_x + current_radius * math.cos(mid_angle)
                y = center_y + current_radius * math.sin(mid_angle)
                set_pos(node, x, y)

            ch = tree_children.get(node, [])
            if ch:
                angle_per_leaf = (angle_end - angle_start) / leaves_count[node]
                current_angle = angle_start
                for child in ch:
                    child_leaves = leaves_count[child]
                    child_angle_end = current_angle + (child_leaves * angle_per_leaf)
                    layout_radial(child, depth + 1, current_angle, child_angle_end)
                    current_angle = child_angle_end

        layout_radial(main_root, 0, 0, 2 * math.pi)

        # 6. Acomodar nodos sueltos o sub-grafos desconectados en un anillo exterior
        unvisited = [n for n in nodes if n not in drawn_nodes]
        if unvisited:
            max_depth = 0
            def get_depth(node, d):
                nonlocal max_depth
                max_depth = max(max_depth, d)
                for c in tree_children.get(node, []): get_depth(c, d + 1)
            get_depth(main_root, 0)
            
            outer_radius = (max_depth + 1) * radius_step + 150
            angle_step = (2 * math.pi) / len(unvisited)
            for i, node in enumerate(unvisited):
                angle = i * angle_step
                x = center_x + outer_radius * math.cos(angle)
                y = center_y + outer_radius * math.sin(angle)
                set_pos(node, x, y)

        # 7. Redibujar las líneas y refrescar vista
        for link in links:
            if hasattr(link, 'redraw'): link.redraw()
            
        self.scene.suggested_scene_size()
        self.scene.update()
    # ---
    def add_codes_of_av_files(self, x=10, y=10):
        """ Show selected codes of selected audio/video files as av graphics items.
        Args:
            x: Integer
            y: Integer
        """

        # Select file
        files_wth_names = self.app.get_av_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select audio/video files"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected_file = ui.get_selected()
        cur = self.app.conn.cursor()
        cur.execute("select mediapath from source where id=?", [selected_file['id']])
        selected_file['path'] = ""
        res_path = cur.fetchone()
        if res_path:
            selected_file['path'] = res_path[0]

        # Select from codes that are assigned to this audio/video file
        cur.execute("select cid from code_av where id=?", [selected_file['id']])
        res_assigned_codes = cur.fetchall()
        cids = [r[0] for r in res_assigned_codes]
        code_names = self.app.get_code_names(cids)
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []
        for code in selected_codes:
            sql = "select cid,id,pos0,pos1, ifnull(memo,''), avid from code_av where cid=? and id=?"
            cur.execute(sql, [code['cid'], selected_file['id']])
            res = cur.fetchall()
            for r in res:
                coding_displayed = False
                for item in self.scene.items():
                    if isinstance(item, AVGraphicsItem):
                        if item.avid == r[5]:
                            coding_displayed = True
                if not coding_displayed:
                    name = selected_file['name'] + ': ' + str(int(r[2])) + ' to ' + str(int(r[3])) + _(" msecs")
                    codings.append({'cid': r[0], 'fid': r[1], 'pos0': int(r[2]), 'pos1': int(r[3]),
                                    'memo': r[4], 'filename': selected_file['name'],
                                    'codename': code['name'], 'name': name,
                                    'path': selected_file['path'], 'avid': r[5]})
        if not codings:
            Message(self.app, _("No codes"), _("No coded segments for selection")).exec()
            return
        ui = DialogSelectItems(self.app, codings, _("Select coded segment"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codings = ui.get_selected()
        for s in selected_codings:
            x += 10
            y += 10
            item = AVGraphicsItem(self.app, s['avid'], x, y, s['pos0'], s['pos1'], s['path'])
            msg = f"AVID:{s['avid']} " + _("File: ") + f"{s['filename']}\n" + _("Code: ") + s['codename']
            msg += f"\n{s['pos0']} - {s['pos1']}" + _("msecs")
            if s['memo'] != "":
                msg += "\n" + _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)

    def add_codes_of_image_files(self, x=10, y=10):
        """ Show selected codes of selected image file as pixmap graphics items.
        Args:
            x: Integer
            y: Integer
        """

        # Select image file
        files_wth_names = self.app.get_image_and_pdf_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select image files"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected_file = ui.get_selected()
        cur = self.app.conn.cursor()
        cur.execute("select mediapath from source where id=?", [selected_file['id']])
        selected_file['path'] = ""
        res_path = cur.fetchone()
        if res_path:
            selected_file['path'] = res_path[0]

        # Select from codes that are assigned to this image
        cur.execute("select cid from code_image where id=?", [selected_file['id']])
        res_assigned_codes = cur.fetchall()
        cids = [r[0] for r in res_assigned_codes]
        code_names = self.app.get_code_names(cids)
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []

        for code in selected_codes:
            sql = "select cid,id,x1,y1,width,height,ifnull(memo,''), imid, pdf_page from code_image where cid=? and id=?"
            cur.execute(sql, [code['cid'], selected_file['id']])
            res = cur.fetchall()
            for r in res:
                coding_displayed = False
                for item in self.scene.items():
                    if isinstance(item, PixmapGraphicsItem):
                        if item.imid == r[7]:
                            coding_displayed = True
                if not coding_displayed:
                    name = f"{selected_file['name']} x:{int(r[2])} y:{int(r[3])}"
                    name += _(" width") + str(int(r[4])) + _(" height:") + str(int(r[5]))
                    codings.append({'cid': r[0], 'fid': r[1], 'x': int(r[2]), 'y': int(r[3]), 'width': int(r[4]),
                                    'height': int(r[5]), 'memo': r[6], 'filename': selected_file['name'],
                                    'codename': code['name'], 'name': name,
                                    'path': selected_file['path'], 'imid': r[7], 'pdf_page': r[8]})
        if not codings:
            Message(self.app, _("No codes"), _("No coded segments for selection")).exec()
            return
        ui = DialogSelectItems(self.app, codings, _("Select coded area"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codings = ui.get_selected()
        for s in selected_codings:
            x += 10
            y += 10
            item = PixmapGraphicsItem(self.app, s['imid'], x, y, s['x'], s['y'], s['width'], s['height'], s['path'],
                                      None, s['pdf_page'])
            msg = f"IMID:{s['imid']} " + _("File: ") + f"{s['filename']}\n" + _("Code: ") + f"{s['codename']}\n"
            msg += _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)

    def add_coded_text_of_text_files(self, x=10, y=10):
        """ Show selected codes of selected text files as free text graphics items.
        Args:
            x: Integer
            y: Integer
        """

        # --- Select files
        files_wth_names = self.app.get_text_filenames()
        if not files_wth_names:
            Message(self.app, _("No files"), _("No text files in this project.")).exec()
            return
        ui = DialogSelectItems(self.app, files_wth_names, _("Step 1/3: Select text files"), "multi")
        # ---
        ok = ui.exec()
        if not ok:
            return
        selected_files = ui.get_selected()
        # Select codes
        code_names = self.app.get_code_names()
        ui = DialogSelectItems(self.app, code_names, _("Step 2/3: Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []
        cur = self.app.conn.cursor()
        for file_ in selected_files:
            for code in selected_codes:
                sql = "select cid,fid,seltext,ifnull(memo,''), ctid from code_text where cid=? and fid=?"
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    coding_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            if item.ctid == r[4]:
                                coding_displayed = True
                    if not coding_displayed:
                        codings.append({'cid': r[0], 'fid': r[1], 'name': r[2], 'memo': r[3], 'filename': file_['name'],
                                        'codename': code['name'], 'ctid': r[4]})
        if not codings:
            Message(self.app, _("No codes"), _("No coded segments for selection")).exec()
            return
        ui = DialogSelectItems(self.app, codings, _("Step 3/3: Select coded text segments"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codings = ui.get_selected()
        color = self.color_selection("text")
        for s in selected_codings:
            x += 10
            y += 10
            freetextid = 1
            for item in self.scene.items():
                if isinstance(item, FreeTextGraphicsItem):
                    if item.freetextid > freetextid:
                        freetextid = item.freetextid + 1
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, color, False, s['ctid'])
            item.ctid = s['ctid']
            msg = _("File: ") + f"{s['filename']}\n" + _("Code: ") + s['codename']
            if s['memo'] != "":
                msg += "\n" + _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)

    def add_memos_of_coded(self, x=10, y=10):
        """ Show selected memos of coded segments of selected files in free text items.
        Args:
            x: Integer
            y: Integer
        """

        files_wth_names = self.app.get_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_files = ui.get_selected()
        code_names = self.app.get_code_names()
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        memos = []
        cur = self.app.conn.cursor()
        for file_ in selected_files:
            for code in selected_codes:
                sql = "select cid,fid,seltext,ifnull(memo,''),ctid from code_text where cid=? and fid=? and memo !='' order by pos0 asc"
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    coding_memo_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            if item.memo_ctid is not None and item.memo_ctid == r[4]:
                                coding_memo_displayed = True
                    if not coding_memo_displayed:
                        memos.append({'cid': r[0], 'fid': r[1], 'tooltip': r[2], 'name': r[3], 'filetype': 'text',
                                      'codename': code['name'], 'filename': file_['name'], 'ctid': r[4], 'imid': None,
                                      'avid': None})
                sql_img = "select cid,id,x1,y1,width,height,memo,imid from code_image where cid=? and id=? and memo !='' and memo is not null"
                cur.execute(sql_img, [code['cid'], file_['id']])
                res_img = cur.fetchall()
                for r in res_img:
                    coding_memo_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            if item.memo_imid == r[7]:
                                coding_memo_displayed = True
                    if not coding_memo_displayed:
                        tt = _("Memo for area: ") + "x:" + f"{r[2]}" + " y:" + f"{r[3]}" + " " + _("width:") \
                             + f"{r[4]} " + _("height:") + f"{r[5]}"
                        memos.append({'cid': r[0], 'fid': r[1], 'tooltip': tt, 'name': r[6], 'filetype': 'image',
                                      'codename': code['name'], 'filename': file_['name'], 'imid': r[7], 'avid': None,
                                      'ctid': None})
                sql_av = "select cid,id,pos0,pos1,memo, avid from code_av where cid=? and id=? and memo !='' and " \
                         "memo is not null order by pos0 asc"
                cur.execute(sql_av, [code['cid'], file_['id']])
                res_av = cur.fetchall()
                for r in res_av:
                    coding_memo_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            # if item.text == r[4]:
                            if item.memo_avid == r[5]:
                                coding_memo_displayed = True
                    if not coding_memo_displayed:
                        tt = _("Memo for duration: ") + f"{r[2]} - {r[3]} " + _("msecs")
                        memos.append({'cid': r[0], 'fid': r[1], 'tooltip': tt, 'name': r[4], 'filetype': 'A/V',
                                      'codename': code['name'], 'filename': file_['name'], 'avid': r[5], 'imid': None,
                                      'ctid': None})
        if not memos:
            Message(self.app, _("No memos"), _("No memos for selection")).exec()
            return
        ui = DialogSelectItems(self.app, memos, _("Select coding memo"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_memos = ui.get_selected()
        color = self.color_selection("text")
        for s in selected_memos:
            x += 10
            y += 10
            freetextid = 1
            for item in self.scene.items():
                if isinstance(item, FreeTextGraphicsItem):
                    if item.freetextid > freetextid:
                        freetextid = item.freetextid + 1
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, color, False, -1,
                                        s['ctid'], s['imid'], s['avid'])
            msg = _("File: ") + f"{s['filename']}\n" + _("Code: ") + s['codename']
            if s['tooltip'] != "":
                msg += "\n" + _("Memo for: ") + s['tooltip']
            item.setToolTip(msg)
            self.scene.addItem(item)

    def add_lines_to_graph(self):
        """ Add one or more free lines from an item to one or more destination items. """

        # From item selection
        texts_and_groups = self.graphics_items_text_and_group()
        ui = DialogSelectItems(self.app, texts_and_groups, _("Line start item"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            return
        text_from = selected['name']
        from_item = None
        for item in self.scene.items():
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                    isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) or \
                    isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                if item.text == text_from:
                    from_item = item
        # To Items selection, remove the from item, and remove matching text items
        texts_and_groups.remove(selected)
        for i in texts_and_groups[:]:
            if i['name'] == text_from:
                texts_and_groups.remove(i)
        ui = DialogSelectItems(self.app, texts_and_groups, _("Line end item(s)"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            return
        color = self.color_selection("line")

        # Create Free Item lines
        for s in selected:
            text_to = s['name']
            to_item = None
            for item in self.scene.items():
                if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                        isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) or \
                        isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                    # Cannot link same text items
                    if item.text == text_to:
                        to_item = item
            if from_item != to_item and not (from_item is None or to_item is None):
                line_item = FreeLineGraphicsItem(from_item, to_item, color)
                self.scene.addItem(line_item)

    def color_selection(self, obj_type="line"):
        """ Get a color for Free text items and Free lines.
         Called by: add_lines_to_graph, show_codes, show_memos.
         If obj_type is line, limit choices, otherwise include black and white.
         Args:
             obj_type : String
         Returns:
             color : String
        """

        # Line color selection
        colours = [{"name": _("gray"), "english": "gray"}, {"name": _("blue"), "english": "blue"},
                   {"name": _("cyan"), "english": "cyan"}, {"name": _("magenta"), "english": "magenta"},
                   {"name": _("green"), "english": "green"}, {"name": _("red"), "english": "red"},
                   {"name": _("yellow"), "english": "yellow"}, {"name": _("orange"), "english": "orange"}]
        if obj_type != "line":
            colours.append({"name": _("white"), "english": "white"})
            colours.append({"name": _("black"), "english": "black"})
        ui = DialogSelectItems(self.app, colours, _("Colour"), "single")
        ok = ui.exec()
        if not ok:
            return ""
        selected_color = ui.get_selected()
        return selected_color['english']

    def add_text_item_to_graph(self, x=20, y=20):
        """ Add text item to graph.
        Args:
            x: Integer
            y: integer
        """

        freetextid = 1
        for item in self.scene.items():
            if isinstance(item, FreeTextGraphicsItem):
                if item.freetextid > freetextid:
                    freetextid = item.freetextid + 1
        text_, ok = QtWidgets.QInputDialog.getText(self, _('Text object'), _('Enter text:'))
        if not ok:
            return
        texts = self.graphics_items_text_and_group()
        for t in texts:
            if text_ == t['name']:
                Message(self.app, _("Warning"), _("Another item has this exact text")).exec()
                return
        item = FreeTextGraphicsItem(self.app, freetextid, x, y, text_)
        self.scene.addItem(item)

    def graphics_items_text_and_group(self):
        """ Used to get a list of all FreeText and Case and File graphics items text.
        Adds a group key to be able to groups the text items for the selection dialog.
        Use to show text in a dialog, to allow links between these items.
        Called by: add_lines_to_graph, add_text_item_to_graph

         return: names_groups : List of Dictionaries of Name Strings, Group strings
         """

        names_and_groups = []
        cur = self.app.conn.cursor()

        # By code
        for item in self.scene.items():
            if isinstance(item, FreeTextGraphicsItem) and item.ctid > -1:
                cur.execute(
                    "select code_name.name from code_name join code_text on code_text.cid=code_name.cid where ctid=?",
                    [item.ctid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_ctid is not None:
                cur.execute(
                    "select code_name.name from code_name join code_text on code_text.cid=code_name.cid where ctid=?",
                    [item.memo_ctid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_imid is not None:
                cur.execute(
                    "select code_name.name from code_name join code_image on code_image.cid=code_name.cid where imid=?",
                    [item.memo_imid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_avid is not None:
                cur.execute(
                    "select code_name.name from code_name join code_av on code_av.cid=code_name.cid where avid=?",
                    [item.memo_avid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, PixmapGraphicsItem):
                cur.execute(
                    "select code_name.name from code_name join code_image on code_image.cid=code_name.cid where imid=?",
                    [item.imid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, AVGraphicsItem):
                cur.execute(
                    "select code_name.name from code_name join code_av on code_av.cid=code_name.cid where avid=?",
                    [item.avid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, TextGraphicsItem):
                names_and_groups.append({'name': item.text, 'group': item.text})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_ctid is None and \
                    item.memo_imid is None and item.memo_avid is None:
                names_and_groups.append({'name': item.text, 'group': _('Free text item')})
            if isinstance(item, CaseTextGraphicsItem):
                names_and_groups.append({'name': item.text, 'group': _('Case item')})
            if isinstance(item, FileTextGraphicsItem):
                names_and_groups.append({'name': item.text, 'group': _('File item')})
        sorted_names_and_groups = sorted(names_and_groups, key=lambda d: d['name'])
        return sorted_names_and_groups

    def add_files_to_graph(self):
        """ Add Text file items to graph. """

        files = self.get_files()
        # Do not show items that are already displayed
        to_remove = []
        for f in files:
            for item in self.scene.items():
                if isinstance(item, FileTextGraphicsItem):
                    if item.file_id == f['id']:
                        to_remove.append(f)
        for tr in to_remove:
            files.remove(tr)

        ui = DialogSelectItems(self.app, files, _("Select files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        for i, s in enumerate(selected):
            file_item = FileTextGraphicsItem(self.app, s['name'], s['id'], i * 10, i * 10)
            file_item.setToolTip(_("File"))  # Need to add tooltip here, for some unknown reason
            self.scene.addItem(file_item)

    def get_files(self):
        """ Get list of files.
        Called by add_files_to_graph.
        return: list of dictionary of id and name"""

        cur = self.app.conn.cursor()
        sql = "select id, name from source order by source.name asc"
        cur.execute(sql)
        result = cur.fetchall()
        keys = 'id', 'name'
        res = []
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def add_cases_to_graph(self):
        """ Add Text case items to graph. """

        cases = self.get_cases()
        # Do not show items that are already displayed
        to_remove = []
        for c in cases:
            for item in self.scene.items():
                if isinstance(item, CaseTextGraphicsItem):
                    if item.case_id == c['id']:
                        to_remove.append(c)
        for tr in to_remove:
            cases.remove(tr)
        ui = DialogSelectItems(self.app, cases, _("Select cases"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        for i, s in enumerate(selected):
            case_item = CaseTextGraphicsItem(self.app, s['name'], s['id'], i * 10, i * 10)
            case_item.setToolTip(_("Case"))  # Need to add tooltip here, for some unknown reason
            self.scene.addItem(case_item)

    def get_cases(self):
        """ Get list of cases.
        Called by: add_cases_to_graph
        return: list of dictionary of id and name"""

        cur = self.app.conn.cursor()
        sql = "select caseid, name from cases order by cases.name asc"
        cur.execute(sql)
        result = cur.fetchall()
        keys = 'id', 'name'
        res = []
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def export_image(self):
        """ Export the QGraphicsScene as a png image with transparent background. """
        filename = "Graph.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return

        # REPARACIÓN: Obtener el rectángulo real que envuelve a TODOS los elementos (incluso coordenadas negativas)
        rect = self.scene.itemsBoundingRect()
        rect.adjust(-30, -30, 30, 30) # Añadir un margen seguro de 30px alrededor de la imagen

        # Crear la imagen con el tamaño exacto del rectángulo detectado
        image = QtGui.QImage(int(rect.width()), int(rect.height()), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.transparent) # Asegurar fondo transparente

        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        # Renderizar especificando el área objetivo (la imagen) y el área de origen (el rectángulo exacto de la escena)
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect)
        painter.end()
        
        image.save(filepath)
        Message(self.app, _("Image exported"), filepath).exec()
    # --- Nueva función para exportar grafo a proyecto de Draw.io
    def export_drawio(self):
        """ Escanea el lienzo actual y exporta un archivo editable nativo para Draw.io (.drawio) """
        filename = "QualCoder_graph.drawio"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return

        # 1. Cabecera estándar requerida por Draw.io
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<mxfile>\n  <diagram id="qualcoder_graph" name="QualCoder Graph">\n'
        xml += '    <mxGraphModel dx="1000" dy="1000" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">\n'
        xml += '      <root>\n        <mxCell id="0" />\n        <mxCell id="1" parent="0" />\n'

        item_ids = {}
        current_id = 2

        # 2. Procesar Nodos (Categorías y Códigos)
        for item in self.scene.items():
            if not item.isVisible(): continue
            
            if type(item).__name__ in ("TextGraphicsItem", "FreeTextGraphicsItem", "CaseTextGraphicsItem", "FileTextGraphicsItem"):
                item_ids[item] = str(current_id)
                x = item.pos().x()
                y = item.pos().y()
                w = item.boundingRect().width()
                h = item.boundingRect().height()
                
                label = ""
                color = "#FFFFFF" 
                is_ellipse = getattr(item, 'is_ellipse', False)
                
                if hasattr(item, 'code_or_cat') and item.code_or_cat is not None:
                    label = item.code_or_cat.get('name', '')
                    color = item.code_or_cat.get('color', '#FFFFFF')
                elif hasattr(item, 'text'):
                    label = item.text
                
                # Limpiar caracteres conflictivos en XML
                label = str(label).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
                
                # Definir forma y estilo
                shape = "ellipse" if is_ellipse else "rounded=1"
                style = f"{shape};whiteSpace=wrap;html=1;fillColor={color};strokeColor=#333333;fontColor=#000000;"
                
                xml += f'        <mxCell id="{current_id}" value="{label}" style="{style}" vertex="1" parent="1">\n'
                xml += f'          <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
                xml += '        </mxCell>\n'
                current_id += 1

        # 3. Procesar Conexiones (Líneas) asegurando que queden vinculadas dinámicamente a los nodos
        for item in self.scene.items():
            if not item.isVisible(): continue
            
            if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if not hasattr(item, 'from_widget') or not hasattr(item, 'to_widget'): continue
                    
                source_id = item_ids.get(item.from_widget)
                target_id = item_ids.get(item.to_widget)
                
                if source_id and target_id:
                    line_color = item.color if hasattr(item, 'color') else "gray"
                    dashed = "1" if hasattr(item, 'line_type') and item.line_type != QtCore.Qt.PenStyle.SolidLine else "0"
                    width = item.line_width if hasattr(item, 'line_width') else 2
                    
                    label = item.label if hasattr(item, 'label') else ""
                    label = str(label).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
                    
                    # Definir flecha dependiendo del tipo de conexión original
                    arrow = "classic" if type(item).__name__ == "FreeLineGraphicsItem" else "none"
                    style = f"endArrow={arrow};html=1;strokeColor={line_color};strokeWidth={width};dashed={dashed};labelBackgroundColor=none;"
                    
                    xml += f'        <mxCell id="{current_id}" value="{label}" style="{style}" edge="1" parent="1" source="{source_id}" target="{target_id}">\n'
                    xml += '          <mxGeometry relative="1" as="geometry" />\n'
                    xml += '        </mxCell>\n'
                    current_id += 1

        # 4. Cerrar XML y guardar
        xml += '      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>'

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml)
            Message(self.app, "Export Successful", f"Graph successfully exported natively for Draw.io to:\n{filepath}", "information").exec()
        except Exception as e:
            logger.error(f"Error exporting to Draw.io: {e}")
            Message(self.app, _("Error"), f"No se pudo guardar el archivo:\n{e}", "warning").exec()        

    def export_pdf_graph(self):
        filename = "Graph.pdf"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return

        bounding_rect = self.scene.itemsBoundingRect()
        margin = 2
        bounding_rect = bounding_rect.adjusted(-margin, -margin, margin, margin)

        pdf_writer = QtGui.QPdfWriter(filepath)
        pdf_writer.setResolution(300)

        # Create the custom page size in mm
        width_mm = bounding_rect.width() / pdf_writer.resolution() * 30
        height_mm = bounding_rect.height() / pdf_writer.resolution() * 30
        page_size = QtGui.QPageSize(QtCore.QSizeF(width_mm, height_mm), QtGui.QPageSize.Millimeter)
        pdf_writer.setPageSize(page_size)

        painter = QtGui.QPainter(pdf_writer)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.scene.render(
            painter,
            QtCore.QRectF(0, 0, bounding_rect.width(), bounding_rect.height()),
            bounding_rect
        )
        painter.end()

        Message(self.app, ("PDF exported (cropped)"), filepath).exec()

    def save_graph(self):
        """ Save graph items. """

        ui_save = DialogSaveSql(self.app)
        ui_save.setWindowTitle(_("Save graph"))
        ui_save.ui.label_name.setText(_("Graph name"))
        ui_save.ui.label.hide()
        ui_save.ui.lineEdit_group.hide()
        ui_save.exec()
        name = ui_save.name
        if name == "":
            msg = _("Must have a name")
            Message(self.app, _("Cannot save"), msg).exec()
            return
        description = ui_save.description
        cur = self.app.conn.cursor()
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.scene.adjust_for_negative_positions()
        width, height = self.scene.suggested_scene_size()
        self.scene.set_width(width)
        self.scene.set_height(height)
        try:
            try:
                cur.execute("insert into graph (name, description, date, scene_width, scene_height) values(?,?,?,?,?)",
                            [name, description, now_date, width, height])
            except sqlite3.IntegrityError:
                Message(self.app, _("Name error"), _("This name already used. Choose another name.")).exec()
                self.app.conn.rollback()
                return
            cur.execute("select last_insert_rowid()")
            grid = cur.fetchone()[0]
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    sql = "insert into gr_cdct_text_item (grid,x,y,supercatid,catid,cid,font_size,bold,isvisible," \
                        "displaytext) values (?,?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql, [grid, i.pos().x(), i.pos().y(), i.code_or_cat['supercatid'], i.code_or_cat['catid'],
                                    i.code_or_cat['cid'], i.font_size, i.bold, i.isVisible(), i.toPlainText()])
                if isinstance(i, FreeTextGraphicsItem):
                    sql = "insert into gr_free_text_item (grid,freetextid, x,y,free_text,font_size,bold,color,tooltip, " \
                        "ctid, memo_ctid, memo_imid, memo_avid) values (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    tt = i.toolTip()
                    cur.execute(sql, [grid, i.freetextid, i.pos().x(), i.pos().y(), i.text, i.font_size, i.bold, i.color,
                                    tt, i.ctid, i.memo_ctid, i.memo_imid, i.memo_avid])
                if isinstance(i, CaseTextGraphicsItem):
                    sql = "insert into gr_case_text_item (grid,x,y,caseid,font_size,bold,color, displaytext) " \
                        "values (?,?,?,?,?,?,?,?)"
                    cur.execute(sql,
                                [grid, i.pos().x(), i.pos().y(), i.case_id, i.font_size, i.bold, i.color, i.toPlainText()])
                if isinstance(i, FileTextGraphicsItem):
                    sql = "insert into gr_file_text_item (grid,x,y,fid,font_size,bold,color, displaytext) " \
                        "values (?,?,?,?,?,?,?,?)"
                    cur.execute(sql,
                                [grid, i.pos().x(), i.pos().y(), i.file_id, i.font_size, i.bold, i.color, i.toPlainText()])
                if isinstance(i, PixmapGraphicsItem):
                    sql = "insert into gr_pix_item (grid,imid,x,y,px,py,w,h,filepath,tooltip,pdf_page) values " \
                        "(?,?,?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql, [grid, i.imid, i.pos().x(), i.pos().y(), i.px, i.py, i.pwidth, i.pheight, i.path_,
                                    i.toolTip(), i.pdf_page])
                if isinstance(i, AVGraphicsItem):
                    sql = "insert into gr_av_item (grid,avid,x,y,pos0,pos1,filepath,tooltip, color) values " \
                        "(?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql,
                                [grid, i.avid, i.pos().x(), i.pos().y(), i.pos0, i.pos1, i.path_, i.toolTip(), i.color])
                if isinstance(i, LinkGraphicsItem):
                    sql = "insert into gr_cdct_line_item (grid,fromcatid,fromcid,tocatid,tocid,color,linewidth,linetype," \
                        "isvisible) values (?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql, [grid, i.from_widget.code_or_cat['catid'], i.from_widget.code_or_cat['cid'],
                                    i.to_widget.code_or_cat['catid'], i.to_widget.code_or_cat['cid'],
                                    i.color, i.line_width, self.line_type_to_text(i.line_type),
                                    i.isVisible()])
                if isinstance(i, FreeLineGraphicsItem):
                    from_catid = None
                    try:
                        from_catid = i.from_widget.code_or_cat['catid']
                    except AttributeError:
                        pass
                    from_cid = None
                    try:
                        from_cid = i.from_widget.code_or_cat['cid']
                    except AttributeError:
                        pass
                    to_catid = None
                    try:
                        to_catid = i.to_widget.code_or_cat['catid']
                    except AttributeError:
                        pass
                    to_cid = None
                    try:
                        to_cid = i.to_widget.code_or_cat['cid']
                    except AttributeError:
                        pass
                    from_case_id = None
                    try:
                        from_case_id = i.from_widget.case_id
                    except AttributeError:
                        pass
                    from_file_id = None
                    try:
                        from_file_id = i.from_widget.file_id
                    except AttributeError:
                        pass
                    from_freetextid = None
                    try:
                        from_freetextid = i.from_widget.freetextid
                    except AttributeError:
                        pass
                    from_imid = None
                    try:
                        from_imid = i.from_widget.imid
                    except AttributeError:
                        pass
                    from_avid = None
                    try:
                        from_avid = i.from_widget.avid
                    except AttributeError:
                        pass
                    to_imid = None
                    try:
                        to_imid = i.to_widget.imid
                    except AttributeError:
                        pass
                    to_avid = None
                    try:
                        to_avid = i.to_widget.avid
                    except AttributeError:
                        pass
                    to_case_id = None
                    try:
                        to_case_id = i.to_widget.case_id
                    except AttributeError:
                        pass
                    to_file_id = None
                    try:
                        to_file_id = i.to_widget.file_id
                    except AttributeError:
                        pass
                    to_freetextid = None
                    try:
                        to_freetextid = i.to_widget.freetextid
                    except AttributeError:
                        pass
                    """ Free line linking options use catid/cid or caseid or fileid and last match text e.g. freetextitem """
                    sql = "insert into gr_free_line_item (grid,fromfreetextid,fromcatid,fromcid,fromcaseid,fromfileid, " \
                        "fromimid,fromavid,tofreetextid,tocatid,tocid,tocaseid,tofileid, toimid,toavid,color, " \
                        "linewidth,linetype) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql, [grid, from_freetextid, from_catid, from_cid, from_case_id, from_file_id, from_imid,
                                    from_avid, to_freetextid, to_catid, to_cid, to_case_id, to_file_id, to_imid, to_avid,
                                    i.color, i.line_width, self.line_type_to_text(i.line_type)])
            self.app.conn.commit()
        except:
            self.app.conn.rollback() # revert all changes 
            raise
        self.app.delete_backup = False

    @staticmethod
    def line_type_to_text(line_type):
        """ Convert line type to text. for graph line items. """

        text_ = "solid"
        if line_type == QtCore.Qt.PenStyle.DotLine:
            text_ = "dotted"
        return text_

    def load_graph_menu(self):
        """ Menu on load graph button to choose load order of graph names. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        alphabet_asc_action = menu.addAction((_("Alphabet ascending")))
        alphabet_desc_action = menu.addAction((_("Alphabet descending")))
        date_asc_action = menu.addAction((_("Oldest to newest")))
        date_desc_action = menu.addAction((_("Newest to oldest")))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == alphabet_asc_action:
            self.load_graph_menu_option = _("Alphabet ascending")
        if action == alphabet_desc_action:
            self.load_graph_menu_option = _("Alphabet descending")
        if action == date_desc_action:
            self.load_graph_menu_option = _("Oldest to newest")
        if action == date_asc_action:
            self.load_graph_menu_option = _("Newest to oldest")
        self.ui.pushButton_loadgraph.setToolTip(_("Load graph") + "\n" + self.load_graph_menu_option)

    def remove_expired_graph_items(self):
        """ Some items may no longer exist in the database and need to be removed from the saved graph objects.
        Applies to: gr_case_text_item, gr_file_text_item, gr_pix_item, gr_av_item and
        gr_text_item for coded text, and for memos of coded text, av, images.
        """

        cur = self.app.conn.cursor()
        sql_pix = "SELECT imid FROM  gr_pix_item where imid not in (select imid from code_image)"
        cur.execute(sql_pix)
        res_pix = cur.fetchall()
        for r in res_pix:
            cur.execute("delete from gr_pix_item where imid=?", [r[0]])
            self.app.conn.commit()
        sql_av = "select avid from gr_av_item where avid not in (select avid from code_av)"
        cur.execute(sql_av)
        res_av = cur.fetchall()
        for r in res_av:
            cur.execute("delete from gr_av_item where avid=?", [r[0]])
            self.app.conn.commit()
        sql_case = "select caseid from gr_case_text_item where caseid not in (select caseid from cases)"
        cur.execute(sql_case)
        res_case = cur.fetchall()
        for r in res_case:
            cur.execute("delete from gr_case_item where caseid=?", [r[0]])
            self.app.conn.commit()
        sql_file = "select fid from gr_file_text_item where fid not in (select id from source)"
        cur.execute(sql_file)
        res_file = cur.fetchall()
        for r in res_file:
            cur.execute("delete from gr_file_item where fid=?", [r[0]])
            self.app.conn.commit()
        # Text codings
        sql_text = "select ctid from gr_free_text_item where ctid is not null and ctid != -1 and ctid not in " \
                   "(select ctid from code_text)"
        cur.execute(sql_text)
        res_text = cur.fetchall()
        for r in res_text:
            cur.execute("delete from gr_free_text_item where ctid=?", [r[0]])
            self.app.conn.commit()
        # Text coding memos
        sql_memo_text = "select memo_ctid from gr_free_text_item where memo_ctid is not null and memo_ctid not in " \
                        "(select ctid from code_text)"
        cur.execute(sql_memo_text)
        res_memo_text = cur.fetchall()
        for r in res_memo_text:
            cur.execute("delete from gr_free_text_item where memo_ctid=?", [r[0]])
            self.app.conn.commit()
        # Image coding memos
        sql_memo_image = "select memo_imid from gr_free_text_item where memo_imid is not null and memo_imid not in " \
                         "(select imid from code_image)"
        cur.execute(sql_memo_image)
        res_memo_image = cur.fetchall()
        for r in res_memo_image:
            cur.execute("delete from gr_free_text_item where memo_imid=?", [r[0]])
            self.app.conn.commit()
        # AV coding memos
        sql_memo_av = "select memo_avid from gr_free_text_item where memo_avid is not null and memo_avid not in " \
                      "(select avid from code_av)"
        cur.execute(sql_memo_av)
        res_memo_av = cur.fetchall()
        for r in res_memo_av:
            cur.execute("delete from gr_free_text_item where memo_avid=?", [r[0]])
            self.app.conn.commit()

    def update_coded_image_areas(self):
        """ Update coding area and memo the current information in gr_pix_item.
        """

        cur = self.app.conn.cursor()
        cur.execute("update gr_pix_item set px=(select x1 from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set py=(select y1 from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set w=(select width from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set h=(select height from code_image where code_image.imid=gr_pix_item.imid)")
        # Tooltips
        cur.execute("select grpixid, source.name, code_name.name, ifnull(code_image.memo,''), code_image.imid from "
                    "gr_pix_item join code_image on code_image.imid=gr_pix_item.imid "
                    "join code_name on code_name.cid= code_image.cid "
                    "join source on source.id=code_image.id")
        res = cur.fetchall()
        for r in res:
            tt = _("File: ") + r[1] + "\n"
            tt += _("Code: ") + r[2] + "\n"
            if self.app.settings['showids']:
                tt += f"imid: {r[4]}\n"
            tt += _("Memo: ") + r[3]
            cur.execute("update gr_pix_item set tooltip=? where grpixid=?", [tt, r[0]])
        self.app.conn.commit()

    def update_coded_av_segments(self):
        """ Update coding segment and memo to the current information in gr_av_item.
        """

        cur = self.app.conn.cursor()
        cur.execute("update gr_av_item set pos0=(select pos0 from code_av where code_av.avid=gr_av_item.avid)")
        cur.execute("update gr_av_item set pos1=(select pos1 from code_av where code_av.avid=gr_av_item.avid)")
        self.app.conn.commit()
        # Tooltips
        cur.execute("select gr_avid, source.name, code_name.name, gr_av_item.pos0, gr_av_item.pos1, "
                    "ifnull(code_av.memo,''), code_av.avid from gr_av_item "
                    "join code_av on code_av.avid=gr_av_item.avid "
                    "join code_name on code_name.cid= code_av.cid "
                    "join source on source.id=code_av.id")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                tt += f"{r[3]} - {r[4]}\n"
                if self.app.settings['showids']:
                    tt += f"avid: {r[6]}\n"
                tt += _("Memo: ") + r[5]
                cur.execute("update gr_av_item set tooltip=? where gr_avid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass

    def update_coded_text_tooltip_files_codes_and_memos(self):
        """ Update the text coding codename and memo to the current information in gr_free_text_item.
        """

        cur = self.app.conn.cursor()
        # Tooltips
        cur.execute("select gfreeid, source.name, code_name.name, ifnull(code_text.memo,''), code_text.ctid "
                    "from gr_free_text_item "
                    "join code_text on code_text.ctid=gr_free_text_item.ctid "
                    "join code_name on code_name.cid= code_text.cid "
                    "join source on source.id=code_text.fid "
                    "where gr_free_text_item.ctid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"ctid: {r[4]}\n"
                tt += _("Memo: ") + r[3]
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass

    def update_memo_tooltip_files_and_codes(self):
        """ For the text memo items. Update the tooltip file name, code name and memo to the current information
        in gr_free_text_item.
        """

        cur = self.app.conn.cursor()
        # Tooltips for memo text codings
        cur.execute("select gfreeid, source.name, code_name.name, code_text.seltext, code_text.ctid "
                    "from gr_free_text_item "
                    "join code_text on code_text.ctid=gr_free_text_item.memo_ctid "
                    "join code_name on code_name.cid= code_text.cid "
                    "join source on source.id=code_text.fid "
                    "where gr_free_text_item.memo_ctid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"ctid: {r[4]}\n"
                tt += _("Memo for: ") + r[3]
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass
        # Tooltips for memo image codings
        cur.execute("select gfreeid, source.name, code_name.name, x1,y1,width,height, code_image.imid "
                    "from gr_free_text_item "
                    "join code_image on code_image.imid=gr_free_text_item.memo_imid "
                    "join code_name on code_name.cid= code_image.cid "
                    "join source on source.id=code_image.id "
                    "where gr_free_text_item.memo_imid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"imid: {r[7]}\n"
                tt += _("Memo for area: ") + f"x:{int(r[3])} y:{int(r[4])} " + _("width:") + \
                      str(int(r[5])) + " " + _("height:") + str(int(r[6]))
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass
        # Tooltips for memo AV codings
        cur.execute(
            "select gfreeid, source.name, code_name.name, code_av.pos0, code_av.pos1, code_av.avid "
            "from gr_free_text_item "
            "join code_av on code_av.avid=gr_free_text_item.memo_avid "
            "join code_name on code_name.cid= code_av.cid "
            "join source on source.id=code_av.id "
            "where gr_free_text_item.memo_avid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"avid: {r[5]}\n"
                tt += _("Memo for duration: ") + f"{int(r[3])}  - {int(r[4])}" + _("msecs")
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass

    def load_graph(self):
        """ Load a saved graph.
        Load each text component first, then link the cdct_line_items then the free_lines_items.
        For cdct_text_items, fill extra details:
        eg name, memo, date?, owner?, color, child_names?
        """

        self.update_coded_image_areas()
        self.update_coded_av_segments()
        self.update_coded_text_tooltip_files_codes_and_memos()
        self.update_memo_tooltip_files_and_codes()
        cur = self.app.conn.cursor()
        sql = "select name, grid, description, scene_width, scene_height from graph order by upper(name) asc"
        if self.load_graph_menu_option == "Alphabet descending":
            sql = "select name, grid, description, scene_width, scene_height from graph order by upper(name) desc"
        if self.load_graph_menu_option == "Oldest to newest":
            sql = "select name, grid, description, scene_width, scene_height from graph order by date desc"
        if self.load_graph_menu_option == "Newest to oldest":
            sql = "select name, grid, description, scene_width, scene_height from graph order by date asc"
        cur.execute(sql)
        res = cur.fetchall()
        names_list = []
        for r in res:
            names_list.append({'name': r[0], 'grid': r[1], 'description': r[2], 'width': r[3], 'height': r[4]})
        ui = DialogSelectItems(self.app, names_list, _("Load graph"), "single")
        ok = ui.exec()
        if not ok:
            return
        graph = ui.get_selected()
        if not graph:
            return
        self.remove_expired_graph_items()
        self.scene.clear()
        self.scene.set_width(graph['width'])
        self.scene.set_height(graph['height'])
        grid = graph['grid']
        err_msg = self.load_code_or_cat_text_graphics_items(grid)
        err_msg += self.load_file_text_graphics_items(grid)
        err_msg += self.load_case_text_graphics_items(grid)
        err_msg += self.load_free_text_graphics_items(grid)
        err_msg += self.load_pixmap_graphics_items(grid)
        err_msg += self.load_av_graphics_items(grid)
        # Load lines
        self.load_cdct_line_graphics_items(grid)
        self.load_free_line_graphics_items(grid)
        if err_msg != "":
            Message(self.app, _("Load graph errors"), err_msg).exec()
        label = _("Changing to another report will lose unsaved graph.") + "\n" + graph['name']
        self.ui.label_loaded_graph.setText(label)
        self.ui.label_loaded_graph.setToolTip(graph['description'])

    def load_cdct_line_graphics_items(self, grid):
        """ Find the to and from widgets using matching catid and cid.
          Then when found add the line item. """

        sql = "select fromcatid,fromcid,tocatid,tocid,linewidth,linetype,color," \
              "isvisible,glineid from gr_cdct_line_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        result = cur.fetchall()
        res = []
        keys = "fromcatid", "fromcid", "tocatid", "tocid", "linewidth", "linetype", "color", "isvisible", "glineid"
        for row in result:
            res.append(dict(zip(keys, row)))
        for line in res:
            # Add link which includes the scene text items and associated data, add links before text_items
            from_item = None
            to_item = None
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    if from_item is None and i.code_or_cat['catid'] == line['fromcatid'] and \
                            i.code_or_cat['cid'] == line['fromcid']:
                        from_item = i
                    if to_item is None and i.code_or_cat['catid'] == line['tocatid'] and \
                            i.code_or_cat['cid'] == line['tocid']:
                        to_item = i
            if from_item is not None and to_item is not None:
                item = LinkGraphicsItem(from_item, to_item, line['linewidth'], line['linetype'],
                                        line['color'], line['isvisible'])
                self.scene.addItem(item)
            else:
                cur.execute("delete from gr_cdct_line_item where glineid=?", [line['glineid']])
                self.app.conn.commit()
        return

    def load_free_line_graphics_items(self, grid):
        """ Find the to and from widgets.
        Several matching options: catid and cid; fileid; caseid; imid; avid; freetextid.
        Then when found add the free line item. """

        sql = "select fromfreetextid,fromcatid,fromcid,fromcaseid,fromfileid,fromimid,fromavid," \
              "tofreetextid,tocatid,tocid, tocaseid,tofileid, toimid, toavid,color, linewidth,linetype,gflineid " \
              "from gr_free_line_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        result = cur.fetchall()
        res = []
        keys = "fromfreetextid", "fromcatid", "fromcid", "fromcaseid", "fromfileid", "fromimid", "fromavid", \
               "tofreetextid", "tocatid", "tocid", "tocaseid", "tofileid", "toimid", "toavid", "color", \
               "linewidth", "linetype", "gflineid"
        for row in result:
            res.append(dict(zip(keys, row)))
        for line in res:
            # Add link which includes the scene text items and associated data, add links before text_items
            from_item = None
            to_item = None
            # Check for each text item type and try to get a matching characteristic
            for i in self.scene.items():
                if from_item is None and line['fromcaseid'] is not None and isinstance(i, CaseTextGraphicsItem):
                    if i.case_id == line['fromcaseid']:
                        from_item = i
                if from_item is None and line['fromfileid'] is not None and isinstance(i, FileTextGraphicsItem):
                    if i.file_id == line['fromfileid']:
                        from_item = i
                if from_item is None and (line['fromcatid'] is not None or line['fromcid'] is not None) \
                        and isinstance(i, TextGraphicsItem):
                    if i.code_or_cat['catid'] == line['fromcatid'] and i.code_or_cat['cid'] == line['fromcid']:
                        from_item = i
                if from_item is None and line['fromfreetextid'] is not None and isinstance(i, FreeTextGraphicsItem):
                    if i.freetextid == line['fromfreetextid']:
                        from_item = i
                if from_item is None and line['fromimid'] is not None and isinstance(i, PixmapGraphicsItem):
                    if i.imid == line['fromimid']:
                        from_item = i
                if from_item is None and line['fromavid'] is not None and isinstance(i, AVGraphicsItem):
                    if i.avid == line['fromavid']:
                        from_item = i
                if to_item is None and line['tocaseid'] is not None and isinstance(i, CaseTextGraphicsItem):
                    if i.case_id == line['tocaseid']:
                        to_item = i
                if to_item is None and line['tofileid'] is not None and isinstance(i, FileTextGraphicsItem):
                    if i.file_id == line['tofileid']:
                        to_item = i
                if to_item is None and (line['tocatid'] is not None or line['tocid'] is not None) \
                        and isinstance(i, TextGraphicsItem):
                    if i.code_or_cat['catid'] == line['tocatid'] and i.code_or_cat['cid'] == line['tocid']:
                        to_item = i
                if to_item is None and line['tofreetextid'] is not None and isinstance(i, FreeTextGraphicsItem):
                    if i.freetextid == line['tofreetextid']:
                        to_item = i
                if to_item is None and line['toimid'] is not None and isinstance(i, PixmapGraphicsItem):
                    if i.imid == line['toimid']:
                        to_item = i
                if to_item is None and line['toavid'] is not None and isinstance(i, AVGraphicsItem):
                    if i.avid == line['toavid']:
                        to_item = i
            # Add line graphics item OR remove database entry
            if from_item is not None and to_item is not None:
                line_item = FreeLineGraphicsItem(from_item, to_item, line['color'], line['linewidth'],
                                                 line['linetype'])
                self.scene.addItem(line_item)
            else:
                cur.execute("delete from gr_free_line_item where gflineid=?", [line['gflineid']])
                self.app.conn.commit()
        return

    def load_case_text_graphics_items(self, grid):
        """ Load the case graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_case = "select x, y, caseid,font_size, color, bold, displaytext from gr_case_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_case, [grid])
        res = cur.fetchall()
        for i in res:
            cur.execute("select name, ifnull(memo,'') from cases where caseid=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(
                    CaseTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5], i[6]))
            else:
                err_msg += _("Case: ") + str(i[2]) + " "
        return err_msg

    def load_file_text_graphics_items(self, grid):
        """ Load the file graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_file = "select x, y, fid, font_size, color, bold, displaytext from gr_file_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_file, [grid])
        res = cur.fetchall()
        for i in res:
            cur.execute("select name, ifnull(memo, '') from source where id=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(
                    FileTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5], i[6]))
            else:
                err_msg += _("File: ") + str(i[2]) + " "
        return err_msg

    def load_free_text_graphics_items(self, grid):
        """ Load the free text graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql = "select freetextid, x, y, free_text, font_size, color, bold, tooltip, ctid, memo_ctid, memo_imid, " \
              "memo_avid, gfreeid from gr_free_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        res = cur.fetchall()
        for i in res:
            item = FreeTextGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[8], i[9], i[10], i[11],
                                        i[12])
            if i[7] != "":
                item.setToolTip(i[7])
            self.scene.addItem(item)
        return err_msg

    def load_pixmap_graphics_items(self, grid):
        """ Load pixmap graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_pix = "select imid, x,y, px,py ,w,h, filepath, tooltip, pdf_page from gr_pix_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_pix, [grid])
        res = cur.fetchall()
        for i in res:
            # app, imid=-1, x=10, y=10, px=0, py=0, pwidth=0, pheight=0, path_="", grpixid=None, pdf_page=None
            item = PixmapGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7], grid, i[9])
            if i[8] != "":
                item.setToolTip(i[8])
            self.scene.addItem(item)
        return err_msg

    def load_av_graphics_items(self, grid):
        """ Load audio/video graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_av = "select avid, x, y, pos0,pos1,filepath, tooltip, color from gr_av_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_av, [grid])
        res = cur.fetchall()
        for i in res:
            item = AVGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[7])
            if i[6] != "":
                item.setToolTip(i[6])
            self.scene.addItem(item)
        return err_msg

    def load_code_or_cat_text_graphics_items(self, grid):
        """ Load the code or category graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_cdct = "select x, y, supercatid, catid, cid, font_size, bold, isvisible, displaytext " \
                   "from gr_cdct_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_cdct, [grid])
        res_cdct = cur.fetchall()
        for i in res_cdct:
            name = ""
            color = '#FFFFFF'  # Default / needed for category items
            if i[4] is not None:
                cur.execute("select name, color from code_name where cid=?", [i[4]])
                res = cur.fetchone()
                if res is not None:
                    name = res[0]
                    color = res[1]
            else:
                cur.execute("select name from code_cat where catid=?", [i[3]])
                res = cur.fetchone()
                if res is not None:
                    name = res[0]
                    color = '#FFFFFF'
            if name != "":
                cdct = {'name': name, 'supercatid': i[2], 'catid': i[3], 'cid': i[4], 'x': i[0], 'y': i[1],
                        'color': color, 'displaytext': i[8]}
                cdct['child_names'] = self.named_children_of_node(cdct)
                self.scene.addItem(TextGraphicsItem(self.app, cdct, i[5], i[6], i[7]))
            else:
                # Code or category has been deleted
                cdcat = _("Category")
                if i[4] is not None:
                    cdcat = _("Code")
                err_msg += cdcat + _(" does not exist: ") + f"{i[3]} {i[4]} "
                cur.execute("delete from gr_cdct_text_item where grid=? and supercatid=? and catid=? and cid=?",
                            [grid, i[2], i[3], i[4]])
                self.app.conn.commit()
        return err_msg

    def delete_saved_graph(self):
        """ Delete saved graph and its items.
        Need a list of dictionaries with a dictionary item called 'name'. """

        cur = self.app.conn.cursor()
        cur.execute("select name, grid from graph order by upper(name)")
        res = cur.fetchall()
        names_list = []
        for r in res:
            names_list.append({'name': r[0], 'grid': r[1]})
        ui = DialogSelectItems(self.app, names_list, _("Delete stored graphs"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        names = ""
        for s in selection:
            names = names + s['name'] + "\n"
        ui = DialogConfirmDelete(self.app, names)
        ok = ui.exec()
        if not ok:
            return
        # Delete graph entry and all its items
        try:
            for s in selection:
                cur.execute("delete from graph where grid = ?", [s['grid']])
                cur.execute("delete from gr_case_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_file_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_free_line_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_free_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_cdct_line_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_cdct_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_pix_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_av_item where grid = ?", [s['grid']])
            self.app.conn.commit()
        except Exception as e_:
            print(e_)
            self.app.conn.rollback() # revert all changes 
            raise
        self.app.delete_backup = False


class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    scene_width = 990
    scene_height = 650
    parent = None

    def __init__(self, parent=None):
        super(GraphicsScene, self).__init__(parent)
        self.parent = parent
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def set_width(self, width):
        """ Resize scene width. """

        self.scene_width = width
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def set_height(self, height):
        """ Resize scene height. """

        self.scene_height = height
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def get_width(self):
        """ Return scene width. """

        return self.scene_width

    def get_height(self):
        """ Return scene height. """

        return self.scene_height

    def mouseMoveEvent(self, mouse_event):
        super(GraphicsScene, self).mouseMoveEvent(mouse_event)

        # Actualizar datos de posición para TODOS los elementos que se movieron
        for item in self.items():
            # Solo procesamos la posición de los nodos reales (que son los que tienen 'code_or_cat')
            if item.isSelected() and hasattr(item, 'code_or_cat'): # Solo procesamos lo que está seleccionado para ganar velocidad
                if item.code_or_cat is not None:
                    item.code_or_cat['x'] = item.pos().x()
                    item.code_or_cat['y'] = item.pos().y()
            
            # Redibujar líneas conectadas
            if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                item.redraw()
        
        self.update()

    '''def mousePressEvent(self, mouseEvent):
    super(GraphicsScene, self).mousePressEvent(mouseEvent)
    #position = QtCore.QPointF(event.scenePos())
    #logger.debug("pressed here: " + str(position.x()) + ", " + str(position.y()))
    for item in self.items(): # item is QGraphicsProxyWidget
        if isinstance(item, LinkItem):
            item.redraw()
    self.update(self.sceneRect())'''

    """def mouseReleaseEvent(self, mouseEvent):
        ''' On mouse release, an item might be repositioned so need to redraw all the
        link_items '''

        super(GraphicsScene, self).mouseReleaseEvent(mouseEvent)
        for item in self.items():
            if isinstance(item, LinkGraphicsItem):
                item.redraw()
        self.update(self.sceneRect())"""

    def adjust_for_negative_positions(self):
        """ Move all items if negative positions. """

        min_adjust_x = 0
        min_adjust_y = 0
        for i in self.items():
            if i.pos().x() < min_adjust_x:
                min_adjust_x = i.pos().x()
            if i.pos().y() < min_adjust_x:
                min_adjust_y = i.pos().y()
        if min_adjust_x < 0 or min_adjust_y < 0:
            for i in self.items():
                if not (isinstance(i, LinkGraphicsItem) or isinstance(i, FreeLineGraphicsItem)):
                    i.setPos(i.pos().x() - min_adjust_x, i.pos().y() - min_adjust_y)

    def suggested_scene_size(self):
        """ Calcula el tamaño real de la escena permitiendo márgenes para el paneo libre. """
        rect = self.itemsBoundingRect()
        rect.adjust(-600, -600, 600, 600)  # Añade espacio libre en todas direcciones
        self.setSceneRect(rect)
        self.scene_width = rect.width()
        self.scene_height = rect.height()
        return self.scene_width, self.scene_height


class CaseTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item shows the case name and optionally attributes.
    A custom context menu
    """

    app = None
    settings = None
    text = ""
    show_attributes = False
    remove = False
    case_name = ""
    # For graph item storage
    font_size = 9
    case_id = -1
    color = "black"
    bold = False

    def __init__(self, app, case_name, case_id, x=0, y=0, font_size=9, color="black", bold=False, displaytext=""):
        """ Show name and optionally attributes.
        param: app  : the main App class
        param: case_name : String
        param: case_id : Integer
        param: x : Integer
        param: y : Integer
        param: color : String
        param: bold : boolean
        param: displaytext : Integer
        """

        super(CaseTextGraphicsItem, self).__init__(None)
        self.setToolTip(_("Case"))
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.case_id = case_id
        self.case_name = case_name
        self.text = displaytext
        if displaytext == "":
            self.text = case_name
        self.setPlainText(self.text)
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.show_attributes = False
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPos(x, y)
        cur = self.app.conn.cursor()
        cur.execute("select ifnull(memo,'') from cases where caseid=?", [case_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("Case") + ": " + res[0])
        self.setDefaultTextColor(colors[color])

    def paint(self, painter, option, widget):
        """ """

        painter.save()
        if self.color in ("black", "gray"):
            color = QtGui.QColor("#fafafa")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        if self.color == "white":
            color = QtGui.QColor("#101010")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """        
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        show_att_action = None
        hide_att_action = None
        edit_action = menu.addAction(_("Edit text"))
        bold_action = menu.addAction(_("Bold toggle"))
        menu.addSeparator()
        # --- Sub-menú para el tamaño de fuente ---
        font_size_menu = menu.addMenu("Font size")
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        # --- Sub-menú para el color de texto ---
        color_menu = menu.addMenu(_("Text color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        orange_action = color_menu.addAction(_("Orange"))
        cyan_action = color_menu.addAction(_("Cyan"))
        magenta_action = color_menu.addAction(_("Magenta"))
        gray_action = color_menu.addAction(_("Gray"))
        color_menu.addSeparator()
        black_action = color_menu.addAction(_("Black"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        if self.show_attributes:
            hide_att_action = menu.addAction(_('Hide attributes'))
        else:
            show_att_action = menu.addAction(_('Show attributes'))
        menu.addSeparator()
        remove_action = menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # Font size
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Bold
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Colors
        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == magenta_action:
            self.color = "magenta"
        if action == cyan_action:
            self.color = "cyan"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == black_action:
            self.color = "black"
        if action == white_action:
            self.color = "white"
        self.setDefaultTextColor(colors[self.color])
        # Remove
        if action == remove_action:
            ui_confirm = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui_confirm.exec():
                return
            self.remove = True
            scene = self.scene()
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        # Attributes
        if action == show_att_action:
            self.show_attributes = True
            self.setHtml(self.text + self.get_attributes())
        if action == hide_att_action:
            self.show_attributes = False
            self.setPlainText(self.text)
        # Edit
        if action == edit_action:
            ui = DialogMemo(self.app, _("Edit text"), self.text)
            ui.exec()
            self.text = ui.memo
            self.setPlainText(self.text)

    def get_attributes(self):
        """ Get attributes for the file.  Add to text document. """
        attribute_text = ""
        cur = self.app.conn.cursor()
        sql = "SELECT name, value FROM  attribute where attr_type='case' and id=? order by name"
        cur.execute(sql, [self.case_id])
        result = cur.fetchall()
        for r in result:
            attribute_text += '<br>' + r[0] + ": " + r[1]
        return attribute_text


class FileTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item shows the file name and optionally attributes.
    A custom context menu
    """

    app = None
    settings = None
    file_name = ""
    remove = False
    show_attributes = False
    text = ""
    # For graph item storage
    file_id = -1
    font_size = 9
    color = "black"
    bold = False

    def __init__(self, app, file_name, file_id, x=0, y=0, font_size=9, color="black", bold=False, displaytext=""):
        """ Show name and optionally attributes.
        param: app  : the main App class
        param: file_name : String
        param: file_od : Integer
        param: x : Integer
        param: y : Integer
        param: color : String
        bold : boolean
        """

        super(FileTextGraphicsItem, self).__init__(None)
        self.setToolTip(_("File"))
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.file_id = file_id
        self.file_name = file_name
        self.text = displaytext
        if displaytext == "":
            self.text = file_name
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.show_attributes = False
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPos(x, y)
        cur = self.app.conn.cursor()
        cur.execute("select ifnull(memo,'') from source where id=?", [file_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("File") + ": " + res[0])
        self.setPlainText(self.text)
        self.setDefaultTextColor(colors[color])

    def paint(self, painter, option, widget):
        """ """

        painter.save()
        if self.color in ("black", "gray"):
            color = QtGui.QColor("#fafafa")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        if self.color == "white":
            color = QtGui.QColor("#101010")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        show_att_action = None
        hide_att_action = None
        edit_action = menu.addAction(_("Edit text"))
        bold_action = menu.addAction(_("Bold toggle"))
        menu.addSeparator()
        # --- Sub-menú para el tamaño de fuente ---
        font_size_menu = menu.addMenu("Font size")
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        # --- Sub-menú para el color de texto ---
        color_menu = menu.addMenu(_("Text color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        orange_action = color_menu.addAction(_("Orange"))
        cyan_action = color_menu.addAction(_("Cyan"))
        magenta_action = color_menu.addAction(_("Magenta"))
        gray_action = color_menu.addAction(_("Gray"))
        color_menu.addSeparator()
        black_action = color_menu.addAction(_("Black"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        if self.show_attributes:
            hide_att_action = menu.addAction(_('Hide attributes'))
        else:
            show_att_action = menu.addAction(_('Show attributes'))
        menu.addSeparator()
        remove_action = menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # Font size
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Bold
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Colors
        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == black_action:
            self.color = "black"
        if action == white_action:
            self.color = "white"
        self.setDefaultTextColor(colors[self.color])
        # Remove
        if action == remove_action:
            from .confirm_delete import DialogConfirmDelete
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            self.remove = True
            scene = self.scene()
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        # Attributes
        if action == show_att_action:
            self.setHtml(self.text + self.get_attributes())
            self.show_attributes = True
        if action == hide_att_action:
            self.setPlainText(self.text)
            self.show_attributes = False
        # Edit
        if action == edit_action:
            ui = DialogMemo(self.app, _("Edit text"), self.text)
            ui.exec()
            self.text = ui.memo
            self.setPlainText(self.text)

    def get_attributes(self):
        """ Get attributes for the file.  Add to text document. """

        attribute_text = ""
        cur = self.app.conn.cursor()
        sql = "SELECT name, value FROM  attribute where attr_type='file' and id=? order by name"
        cur.execute(sql, [self.file_id])
        result = cur.fetchall()
        for r in result:
            attribute_text += f"<br>{r[0]}: {r[1]}"
        return attribute_text


class FreeTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ Free text to add to the scene. """

    app = None
    font = None
    settings = None
    remove = False
    # For graph item storage
    freetextid = -1
    text = "text"
    ctid = -1  # Used for a coded text display to show code in context
    memo_ctid = None
    memo_imid = None
    memo_avid = None
    font_size = 9
    color = "black"
    bold = False
    MAX_WIDTH = 300
    MAX_HEIGHT = 300
    # For db stored free text graph items
    gfreeid = None
    updated_text = ""

    def __init__(self, app, freetextid=-1, x=10, y=10, text_="text", font_size=9, color="black", bold=False, ctid=-1,
                 memo_ctid=None, memo_imid=None, memo_avid=None, gfreeid=None):
        """ Free text object.
         param:
            app  : the main App class
            freetextid : Integer
            x : Integer x position
            y : Integer y position
            text_ : String
            color : String
            bold : boolean
            ctid : Integer : code_text identifier for coded file and memo segments
            memo_ctid : Integer or None
            memo_imid : Integer or None
            memo_avid : Integer or None
            gfreeid : Integer or None
         """

        super(FreeTextGraphicsItem, self).__init__(None)
        self.app = app
        self.freetextid = freetextid
        self.setPos(x, y)
        self.text = text_
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.ctid = ctid
        self.memo_ctid = memo_ctid
        self.memo_imid = memo_imid
        self.memo_avid = memo_avid
        self.gfreeid = gfreeid
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, QtGui.QFont.Weight.Normal))
        if bold:
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, QtGui.QFont.Weight.Bold))
        self.setPlainText(self.text)
        self.setDefaultTextColor(colors[color])
        if self.boundingRect().width() > self.MAX_WIDTH:
            self.setTextWidth(self.MAX_WIDTH)
        self.check_coding()

    def check_coding(self):
        """ Check text coding segment is current.
        Flag if so, but do not automatically update. """

        # Free text item - not a coded text, nor a memo text, so no disparity
        self.updated_text = self.text
        # Get current coded text
        if self.ctid > 0:
            cur = self.app.conn.cursor()
            cur.execute("select seltext from code_text where ctid=?", [self.ctid])
            res = cur.fetchone()
            current_text = res[0]
            if res is None:
                self.updated_text = self.text
                return
            self.updated_text = current_text
            return
        # Get current coded text memo text
        if self.memo_ctid is not None:
            cur = self.app.conn.cursor()
            cur.execute("select ifnull(memo,'') from code_text where ctid=?", [self.memo_ctid])
            res = cur.fetchone()
            current_text = res[0]
            if res is None:
                self.updated_text = self.text
                return
            self.updated_text = current_text
            return
        # Get current coded image memo text
        if self.memo_imid is not None:
            cur = self.app.conn.cursor()
            cur.execute("select ifnull(memo,'') from code_image where imid=?", [self.memo_imid])
            res = cur.fetchone()
            current_text = res[0]
            if res is None:
                self.updated_text = self.text
                return
            self.updated_text = current_text
            return
        # Get current coded av memo text
        if self.memo_avid is not None:
            cur = self.app.conn.cursor()
            cur.execute("select ifnull(memo,'') from code_av where avid=?", [self.memo_avid])
            res = cur.fetchone()
            current_text = res[0]
            if res is None:
                self.updated_text = self.text
                return
            self.updated_text = current_text

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        update_text_action = None
        if self.gfreeid is not None and self.text != self.updated_text:
            update_text_action = menu.addAction(_("Update text"))
        edit_action = menu.addAction(_("Edit text"))
        text_context_action = None
        if (self.ctid is not None and self.ctid != -1) or (self.memo_ctid is not None and self.memo_ctid != -1):
            text_context_action = menu.addAction(_("Segment in context"))
        image_context_action = None
        if self.memo_imid is not None and self.memo_imid != -1:
            image_context_action = menu.addAction(_("Segment in context"))
        av_context_action = None
        if self.memo_avid is not None and self.memo_avid != -1:
            av_context_action = menu.addAction(_("Segment in context"))
        menu.addSeparator()
        bold_action = menu.addAction(_("Bold toggle"))
        # --- Sub-menú para el tamaño de fuente ---
        font_size_menu = menu.addMenu("Font size")
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        # --- Sub-menú para el color de texto ---
        color_menu = menu.addMenu(_("Text color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        cyan_action = color_menu.addAction(_("Cyan"))
        magenta_action = color_menu.addAction(_("Magenta"))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        color_menu.addSeparator()
        black_action = color_menu.addAction(_("Black"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == update_text_action:
            ui = DialogMemo(self.app, _("Update text to"), self.updated_text)
            ui.ui.pushButton_clear.setVisible(False)
            ui.setFixedSize(QtCore.QSize(450, 220))
            ui.ui.textEdit.setReadOnly(True)
            accepted = ui.exec()
            if not accepted:
                return
            self.text = self.updated_text
            cur = self.app.conn.cursor()
            cur.execute("update gr_free_text_item set free_text=? where gfreeid=?",
                        [self.updated_text, self.gfreeid])
            self.app.conn.commit()
            self.setPlainText(self.text)
            return
        if action == image_context_action:
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_image.owner,"
                        "ifnull(code_image.memo,''), x1, y1,width,height, source.name, source.id, source.mediapath "
                        "from code_image join code_name on code_name.cid=code_image.cid join source on "
                        "source.id=code_image.id where code_image.imid=?",
                        [self.memo_imid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find image coding in database")).exec()
                return
            data = {'cid': res[0], 'codename': res[1], 'color': res[2], 'coder': res[3], 'memo': res[4],
                    'x1': res[5], 'y1': res[6], 'width': res[7], 'height': res[8], 'file_or_casename': res[9],
                    'fid': res[10], 'file_or_case': 'File', 'mediapath': res[11]}
            DialogCodeInImage(self.app, data).exec()
        if action == av_context_action:
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_av.owner,ifnull(code_av.memo,''),"
                        "pos0, pos1, source.name, source.id, source.mediapath "
                        "from code_av join code_name on code_name.cid=code_av.cid join source on "
                        "source.id=code_av.id where code_av.avid=?",
                        [self.memo_avid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find A/V coding in database")).exec()
                return
            data = {'cid': res[0], 'codename': res[1], 'color': res[2], 'coder': res[3], 'memo': res[4],
                    'pos0': res[5], 'pos1': res[6], 'file_or_casename': res[7],
                    'fid': res[8], 'file_or_case': 'File', 'mediapath': res[9]}
            DialogCodeInAV(self.app, data).exec()
        if action == text_context_action:
            text_id = self.ctid
            if text_id == -1:
                text_id = self.memo_ctid
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_text.owner,"
                        "ifnull(code_text.memo,''), pos0, pos1, source.name, source.id "
                        "from code_text join code_name on code_name.cid=code_text.cid join source on "
                        "source.id=code_text.fid where code_text.ctid=?",
                        [text_id])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find text coding in database")).exec()
                return
            data = {'cid': res[0], 'codename': res[1], 'color': res[2], 'coder': res[3], 'memo': res[4],
                    'pos0': res[5], 'pos1': res[6], 'file_or_casename': res[7], 'fid': res[8], 'file_or_case': 'File'}
            DialogCodeInText(self.app, data).exec()
        # Remove
        if action == remove_action:
            from .confirm_delete import DialogConfirmDelete
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            self.remove = True
            scene = self.scene()
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        # Bold
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Font size
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Colors
        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == black_action:
            self.color = "black"
        if action == white_action:
            self.color = "white"
        self.setDefaultTextColor(colors[self.color])
        # Edit
        if action == edit_action:
            ui = DialogMemo(self.app, _("Edit text"), self.text)
            ui.exec()
            self.text = ui.memo
            self.setPlainText(self.text)
            if self.boundingRect().width() > self.MAX_WIDTH:
                self.setTextWidth(self.MAX_WIDTH)

    def paint(self, painter, option, widget=None):
        painter.save()
        if self.color in ("black", "gray"):
            color = QtGui.QColor("#fafafa")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        if self.color == "white":
            color = QtGui.QColor("#101010")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class FreeLineGraphicsItem(QtWidgets.QGraphicsPolygonItem):
    """ Polygon with arrow head. """

    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None
    line_width = 2
    line_type = QtCore.Qt.PenStyle.SolidLine
    color = "gray"
    tooltip = ""
    remove = False

    def __init__(self, from_widget, to_widget, color="gray", line_width=2, line_type="solid"):
        """ User created connecting line, with arrow.
         param:
            from_widget : FreeTextGraphicsItem, TextGraphicsItem, AVGraphicsItem, PixmapGraphicsItem,
                FileTextGraphicsItem, CaseTextGraphicsItem
            to_widget : FreeTextGraphicsItem, TextGraphicsItem, AVGraphicsItem, PixmapGraphicsItem,
                FileTextGraphicsItem, CaseTextGraphicsItem
            color : String
            line_width : Integer
            line_type : String
        """

        super(FreeLineGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.line_width = line_width
        self.remove = False
        # --- Bloquear selección y hacer que ignore el clic izquierdo (pero permita el derecho para el menú)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.RightButton)
        self.calculate_points_and_draw()
        # ---
        self.color = color
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine
        color_obj = colors[color]
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        # --- Sub-menú de grosor y estilo de línea ---
        line_menu = menu.addMenu(_('Line style'))
        width1_action = line_menu.addAction(_('Thin (1px)'))
        width2_action = line_menu.addAction(_('Normal (2px)'))
        width4_action = line_menu.addAction(_('Thick (4px)'))
        width6_action = line_menu.addAction(_('Extra thick (6px)'))
        line_menu.addSeparator()
        dotted_action = line_menu.addAction(_('Dotted'))
        solid_action = line_menu.addAction(_('Solid'))
        # --- Sub-menú de color ---
        color_menu = menu.addMenu(_('Line color'))
        red_action = color_menu.addAction(_('Red'))
        yellow_action = color_menu.addAction(_('Yellow'))
        green_action = color_menu.addAction(_('Green'))
        blue_action = color_menu.addAction(_('Blue'))
        cyan_action = color_menu.addAction(_('Cyan'))
        magenta_action = color_menu.addAction(_('Magenta'))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # Grosor
        if action == width1_action:
            self.line_width = 1
            self.redraw()
        if action == width2_action:
            self.line_width = 2
            self.redraw()
        if action == width4_action:
            self.line_width = 4
            self.redraw()
        if action == width6_action:
            self.line_width = 6
            self.redraw()
        # Estilo
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
            self.redraw()
        if action == solid_action:
            self.line_type = QtCore.Qt.PenStyle.SolidLine
            self.redraw()
        # Color
        if action == red_action:
            self.color = "red"
            self.redraw()
        if action == yellow_action:
            self.color = "yellow"
            self.redraw()
        if action == green_action:
            self.color = "green"
            self.redraw()
        if action == blue_action:
            self.color = "blue"
            self.redraw()
        if action == orange_action:
            self.color = "orange"
            self.redraw()
        if action == cyan_action:
            self.color = "cyan"
            self.redraw()
        if action == magenta_action:
            self.color = "magenta"
            self.redraw()
        if action == gray_action:
            self.color = "gray"
            self.redraw()
        if action == remove_action:
            from .confirm_delete import DialogConfirmDelete
            ui = DialogConfirmDelete(self.from_widget.app, _("Remove this line from the graph?"))
            if not ui.exec():
                return
            self.remove = True
            scene = self.scene()
            if scene:
                scene.removeItem(self)
                scene.update()
            return

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculate_points_and_draw()

    def calculate_points_and_draw(self):
        """ Cálculo fluido con punta de flecha giratoria. """
        import math
        
        c1 = self.from_widget.sceneBoundingRect().center()
        c2 = self.to_widget.sceneBoundingRect().center()
        self.setZValue(-1)

        is_ellipse_from = getattr(self.from_widget, 'is_ellipse', False)
        is_ellipse_to = getattr(self.to_widget, 'is_ellipse', False)
        
        rect1 = self.from_widget.sceneBoundingRect()
        rect2 = self.to_widget.sceneBoundingRect()
        
        def get_edge_point(center_source, center_target, rect, is_ellipse):
            dx = center_target.x() - center_source.x()
            dy = center_target.y() - center_source.y()
            if dx == 0 and dy == 0: return center_source
            
            w = rect.width() / 2
            h = rect.height() / 2
            
            if is_ellipse:
                angle = math.atan2(dy, dx)
                return QtCore.QPointF(center_source.x() + w * math.cos(angle), center_source.y() + h * math.sin(angle))
            else:
                if dx == 0: return QtCore.QPointF(center_source.x(), center_source.y() + math.copysign(h, dy))
                if dy == 0: return QtCore.QPointF(center_source.x() + math.copysign(w, dx), center_source.y())
                
                tx = w / abs(dx)
                ty = h / abs(dy)
                t = min(tx, ty)
                return QtCore.QPointF(center_source.x() + dx * t, center_source.y() + dy * t)

        if rect1.intersects(rect2):
            p1, p2 = c1, c2
        else:
            p1 = get_edge_point(c1, c2, rect1, is_ellipse_from)
            p2 = get_edge_point(c2, c1, rect2, is_ellipse_to)

        color_obj = colors[self.color]
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))

        # --- DIBUJO DE FLECHA TRIGONOMETRICA FLUIDA ---
        dx = p1.x() - p2.x()
        dy = p1.y() - p2.y()
        theta = math.atan2(dy, dx)
        
        polygon = QtGui.QPolygonF()
        polygon.append(p1)
        polygon.append(p2)
        
        # Puntas de flecha a 30 grados (pi/6) del eje de la línea
        arrow_size = 12
        p3 = QtCore.QPointF(p2.x() + arrow_size * math.cos(theta + math.pi / 6),
                            p2.y() + arrow_size * math.sin(theta + math.pi / 6))
        p4 = QtCore.QPointF(p2.x() + arrow_size * math.cos(theta - math.pi / 6),
                            p2.y() + arrow_size * math.sin(theta - math.pi / 6))
        
        polygon.append(p3)
        polygon.append(p2)
        polygon.append(p4)
        polygon.append(p2)
        
        self.setPolygon(polygon)

class AVGraphicsItem(QtWidgets.QGraphicsPixmapItem):
    """ Coded audio video item.
    """

    app = None
    font = None
    settings = None
    remove = False
    # For graph item storage
    text = ""
    avid = -1  # code_av
    pos0 = 0
    pos1 = 0
    path_ = ""
    abs_path = ""
    color = "white"

    def __init__(self, app, avid=-1, x=10, y=10, pos0=0, pos1=0, path_="", color="white"):
        """ A/V graphics object.
         param:
            app  : the main App class
            avid : Integer  code_av primary key
            x : Integer x position of graphics item
            y : Integer y position of graphics item
            pos0 : Integer
            pos1 : Integer
            path : String
            color : String
         """

        super(AVGraphicsItem, self).__init__(None)
        self.app = app
        self.avid = avid
        self.text = f"AVID:{self.avid}"
        self.pos0 = pos0
        self.pos1 = pos1
        self.path_ = path_
        self.color = color
        self.abs_path_ = self.app.project_path + path_
        if path_[0:7] in ("audio:", "video:"):
            self.abs_path_ = path_[7:]
        self.setPixmap(qta.icon('mdi6.play').pixmap(28, 28))
        self.setPos(x, y)
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        context_action = menu.addAction(_("View in context"))
        menu.addSeparator()
        # --- Sub-menú de color ---
        color_menu = menu.addMenu(_("Color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        magenta_action = color_menu.addAction(_("Magenta"))
        cyan_action = color_menu.addAction(_("Cyan"))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == context_action:
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_av.owner,ifnull(code_av.memo,'') "
                        "from code_av join code_name on code_name.cid=code_av.cid where code_av.avid=?",
                        [self.avid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find audio/video coding in database")).exec()
                return
            data = {'pos0': self.pos0, 'pos1': self.pos1, 'file_or_casename': self.path_, 'mediapath': self.path_,
                    'coder': res[3], 'codename': res[1], 'cid': res[2], 'color': res[2], 'memo': res[4]}
            DialogCodeInAV(self.app, data).exec()
        # ---    
        if action == remove_action:
            from .confirm_delete import DialogConfirmDelete
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            self.remove = True
            scene = self.scene()
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        # ---    
        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == white_action:
            self.color = "white"

    def paint(self, painter, option, widget=None):
        painter.save()
        color_obj = colors[self.color]
        painter.setBrush(QtGui.QBrush(color_obj, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class PixmapGraphicsItem(QtWidgets.QGraphicsPixmapItem):
    """ Coded pixmap. Uses Images and PDF image files.
    Maximum size of 200 pixels high and wide. """

    app = None
    font = None
    settings = None
    remove = False
    # For graph item storage
    text = ""
    imid = -1  # code_image table imid i=unique for the coded image area
    px = 0
    py = 0
    pwidth = 0
    pheight = 0
    path_ = ""
    pdf_page = None
    MAX_WIDTH = 300
    MAX_HEIGHT = 300
    grpixid = None  # id for database stored free pixmap graph items

    def __init__(self, app, imid=-1, x=10, y=10, px=0, py=0, pwidth=0, pheight=0, path_="", grpixid=None, pdf_page=None):
        """ pixmap object.
         param:
            app  : the main App class
            pixid : Integer
            x : Integer x position of graphics item
            y : Integer y position of graphics item
            px : Integer
            py + Integer
            pwidth : Integer
            pheight : Integer
            imid : Integer code_image primary key
            grpixid : None or Integer from gr_pix_item table
            pdf_page : For Pdf images
         """

        super(PixmapGraphicsItem, self).__init__(None)
        self.app = app
        self.imid = imid
        self.text = "IMID:" + str(self.imid)
        self.px = px
        self.py = py
        self.pwidth = pwidth
        self.pheight = pheight
        self.path_ = path_
        self.grpixid = grpixid  # gr_pix_item table id
        self.pdf_page = pdf_page

        # Image jpg, png
        abs_path_ = self.app.project_path + path_
        if path_[0:7] == "images:":
            abs_path_ = path_[7:]

        # Pdf image
        if self.pdf_page is not None:
            source_path = ""
            if path_[:6] == "/docs/":
                source_path = f"{self.app.project_path}/documents/{path_[6:]}"
            if path_[:5] == "docs:":
                source_path = path_[5:]
            fitz_pdf = fitz.open(source_path)
            page = fitz_pdf[self.pdf_page]
            pixmap = page.get_pixmap()
            abs_path_ = os.path.join(self.app.confighome, f"tmp_pdf_page.png")
            pixmap.save(abs_path_)

        image = QtGui.QImageReader(abs_path_).read()
        image = image.copy(int(px), int(py), int(pwidth), int(pheight))

        # Scale to max 200 wide or high. (TODO Perhaps add option to change maximum limits)
        scaler_w = 1.0
        scaler_h = 1.0
        if image.width() > 200:
            scaler_w = 200 / image.width()
        if image.height() > 200:
            scaler_h = 200 / image.height()
        if scaler_w < scaler_h:
            scaler = scaler_w
        else:
            scaler = scaler_h
        pixmap = QtGui.QPixmap().fromImage(image)
        pixmap = pixmap.scaled(int(image.width() * scaler), int(image.height() * scaler))
        self.setPixmap(pixmap)
        self.setPos(x, y)
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        context_action = menu.addAction(_("View in context"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == context_action:
            '''{codename, color, file_or_casename, x1, y1, width, height, coder,
             mediapath, fid, memo, file_or_case}'''
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_image.owner,"
                        "ifnull(code_image.memo,'') "
                        "from code_image join code_name on code_name.cid=code_image.cid where code_image.imid=?",
                        [self.imid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find image coding in database")).exec()
                return
            data = {'x1': self.px, 'y1': self.py, 'width': self.pwidth, 'height': self.pheight,
                    'file_or_casename': self.path_, 'mediapath': self.path_, 'coder': res[3],
                    'codename': res[1], 'cid': res[2], 'color': res[2], 'memo': res[4]}
            DialogCodeInImage(self.app, data).exec()
        # ---    
        if action == remove_action:
            from .confirm_delete import DialogConfirmDelete
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            self.remove = True
            scene = self.scene()
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        #---    

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class TextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item show the name and color of the code or category
    Categories are shown white. A custom context menu
    allows selection of a code/category memo and displaying the information.
    """

    code_or_cat = None
    border_rect = None
    app = None
    settings = None
    text = ""
    # For graph item storage
    font_size = 9
    bold = False

    def __init__(self, app, code_or_cat, font_size=9, bold=False, isvisible=True, displayed_text=""):
        """ Show name and colour of text. Has context menu for various options.
         param: app  : the main App class
         param: code_or_cat  : Dictionary of the code details: name, memo, color etc
         param: font_size : Integer
         param: bold : boolean
         param: isvisible : boolean
         """

        super(TextGraphicsItem, self).__init__(None)
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.code_or_cat = code_or_cat
        self.font_size = font_size
        self.bold = bold
        self.is_ellipse = False # NUEVO: Controla si es elipse o cuadrado
        self.is_collapsed = False # NUEVO: Controla si sus hijos están ocultos
        self.setPos(self.code_or_cat['x'], self.code_or_cat['y'])
        self.text = displayed_text
        if self.text == "":
            self.text = self.code_or_cat['name']
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        self.setDefaultTextColor(QtGui.QColor(TextColor(self.code_or_cat['color']).recommendation))
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPlainText(self.code_or_cat['name'])
        if not isvisible:
            self.hide()
        self.code_or_cat['memo'] = ""
        self.get_memo()

    def get_memo(self):
        cur = self.app.conn.cursor()
        if self.code_or_cat['cid'] is not None:
            cur.execute("select ifnull(memo,'') from code_name where name=?", [self.code_or_cat['name']])
            res = cur.fetchone()
            if res:
                self.code_or_cat['memo'] = res[0]
                self.setToolTip(_("Code") + ": " + res[0])
            else:
                self.setToolTip(_("Code"))
        else:
            cur.execute("select ifnull(memo,'') from code_cat where name=?", [self.code_or_cat['name']])
            res = cur.fetchone()
            if res:
                self.code_or_cat['memo'] = res[0]
                self.setToolTip(_("Category") + ": " + res[0])
            else:
                self.setToolTip(_("Category"))

    def paint(self, painter, option, widget):
        """  """

        painter.save()
        color = QtGui.QColor(self.code_or_cat['color'])
        painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        
        # Propuesta: Renderizado condicional basado en la bandera de estado visual.
        if getattr(self, 'is_ellipse', False):
            painter.drawEllipse(self.boundingRect())
        else:
            painter.drawRect(self.boundingRect())
            
        painter.restore()
        super().paint(painter, option, widget)

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        memo_action = menu.addAction('View Memo')
        collapse_action = None
        if self.code_or_cat.get('child_names'):
            if getattr(self, 'is_collapsed', False):
                collapse_action = menu.addAction('Expand category')
            else:
                collapse_action = menu.addAction('Collapse category')
        shape_action = menu.addAction('Toggle Shape (Ellipse/Rectangle)')
        # ---
        coded_action = None
        case_action = None
        show_memo_action = None
        add_segments_action = None
        add_cooc_action = None
        # ---
        # --- (NEW)
        if self.code_or_cat['cid'] is not None:
            add_segments_action = menu.addAction('Import segments and link them')
        # ---    
            add_cooc_action = menu.addAction('Import Co-occurrences')
            coded_action = menu.addAction('View text and media')
            case_action = menu.addAction('Case text and media')
        hide_memo_action = None
        if self.code_or_cat['memo'] != "":
            if "\nMEMO:" in self.text:
                hide_memo_action = menu.addAction("Hide memo")
            else:
                show_memo_action = menu.addAction(_("Display memo"))
        menu.addSeparator()
        bold_action = menu.addAction(_("Bold toggle"))
        # --- Sub-menú para el tamaño de fuente ---
        font_size_menu = menu.addMenu("Font size")
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        menu.addSeparator()
        hide_action = menu.addAction('Hide')
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == shape_action:
            self.is_ellipse = not self.is_ellipse
            self.update()
        if collapse_action and action == collapse_action:
            self.toggle_collapse()
        # --- (NEW)   
        if action == add_segments_action:
            self.add_coded_segments()
        # ---    
        if action == add_cooc_action:
            self.add_cooccurring_codes()
        if action == show_memo_action:
            self.text = f"{self.code_or_cat['name']}\nMEMO: {self.code_or_cat['memo']}"
            self.setPlainText(self.text)
        if action == hide_memo_action:
            self.text = self.code_or_cat['name']
            self.setPlainText(self.text)
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == memo_action:
            self.add_edit_memo()
            self.get_memo()
        if action == coded_action:
            self.coded_media()
        if action == case_action:
            self.case_media()
        # ---    
        if action == hide_action:
            ui_confirm = DialogConfirmDelete(self.app, _("Hide this item?"))
            if not ui_confirm.exec():
                return
            self.hide()
            for item in self.scene().items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if not item.from_widget.isVisible() or not item.to_widget.isVisible():
                            item.hide()
            self.scene().update()
        # ---   
    # --- Modificado, antes: "add_coded_text_segments"
    def add_coded_segments(self):
        """
        Unified window to import coded segments from text, image, and A/V
        associated with this code. Generates automatic dotted connections.
        """
        cur = self.app.conn.cursor()
        cid = self.code_or_cat['cid']
        code_name = self.code_or_cat['name']

        # --- Collect TEXT segments
        sql_text = ("select code_text.cid, code_text.fid, code_text.seltext, "
                    "ifnull(code_text.memo,''), code_text.ctid, source.name "
                    "from code_text join source on source.id = code_text.fid "
                    "where code_text.cid=?")
        cur.execute(sql_text, [cid])
        res_text = cur.fetchall()
        text_codings = []
        for r in res_text:
            already = any(isinstance(item, FreeTextGraphicsItem) and item.ctid == r[4]
                          for item in self.scene().items())
            if not already:
                text_codings.append({
                    'cid': r[0], 'fid': r[1], 'name': r[2], 'memo': r[3],
                    'ctid': r[4], 'filename': r[5], 'codename': code_name
                })

        # --- Collect IMAGE segments
        sql_img = ("select code_image.cid, code_image.id, x1, y1, width, height, "
                   "ifnull(code_image.memo,''), code_image.imid, code_image.pdf_page, "
                   "source.name, source.mediapath "
                   "from code_image join source on source.id = code_image.id "
                   "where code_image.cid=?")
        cur.execute(sql_img, [cid])
        res_img = cur.fetchall()
        image_codings = []
        for r in res_img:
            already = any(isinstance(item, PixmapGraphicsItem) and item.imid == r[7]
                          for item in self.scene().items())
            if not already:
                image_codings.append({
                    'cid': r[0], 'fid': r[1], 'x': int(r[2]), 'y': int(r[3]),
                    'width': int(r[4]), 'height': int(r[5]), 'memo': r[6],
                    'imid': r[7], 'pdf_page': r[8], 'filename': r[9],
                    'path': r[10] if r[10] else '', 'codename': code_name,
                    'name': f"{r[9]} x:{int(r[2])} y:{int(r[3])} w:{int(r[4])} h:{int(r[5])}"
                })

        # --- Collect A/V segments
        sql_av = ("select code_av.cid, code_av.id, code_av.pos0, code_av.pos1, "
                  "ifnull(code_av.memo,''), code_av.avid, source.name, source.mediapath "
                  "from code_av join source on source.id = code_av.id "
                  "where code_av.cid=?")
        cur.execute(sql_av, [cid])
        res_av = cur.fetchall()
        av_codings = []
        for r in res_av:
            already = any(isinstance(item, AVGraphicsItem) and item.avid == r[5]
                          for item in self.scene().items())
            if not already:
                av_codings.append({
                    'cid': r[0], 'fid': r[1], 'pos0': int(r[2]), 'pos1': int(r[3]),
                    'memo': r[4], 'avid': r[5], 'filename': r[6],
                    'path': r[7] if r[7] else '', 'codename': code_name,
                    'name': f"{r[6]}: {int(r[2])} to {int(r[3])} msecs"
                })

        # --- Validate that there is something to import
        if not text_codings and not image_codings and not av_codings:
            Message(self.app, "No segments",
                    "There are no new coded segments for this code.").exec()
            return

        # --- Show unified dialog
        ui = DialogSelectCodedSegments(
            self.app, code_name, text_codings, image_codings, av_codings, self.scene().views()[0]
        )
        if not ui.exec():
            return

        x = self.pos().x() + 180
        y = self.pos().y()

        # --- Import selected TEXT segments
        for s in ui.selected_text:
            y += 40
            freetextid = 1
            for item in self.scene().items():
                if isinstance(item, FreeTextGraphicsItem) and item.freetextid >= freetextid:
                    freetextid = item.freetextid + 1
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, "black", False, s['ctid'])
            msg = f"File: {s['filename']}\nCode: {s['codename']}"
            if s['memo']:
                msg += f"\nMemo: {s['memo']}"
            item.setToolTip(msg)
            self.scene().addItem(item)
            line_item = LinkGraphicsItem(self, item, line_width=2, line_type="dotted",
                                         color="gray", isvisible=True)
            self.scene().addItem(line_item)

        # --- Import selected IMAGE segments
        for s in ui.selected_image:
            y += 40
            item = PixmapGraphicsItem(self.app, s['imid'], x, y,
                                       s['x'], s['y'], s['width'], s['height'],
                                       s['path'], None, s['pdf_page'])
            msg = f"IMID:{s['imid']} File: {s['filename']}\nCode: {s['codename']}"
            if s['memo']:
                msg += f"\nMemo: {s['memo']}"
            item.setToolTip(msg)
            self.scene().addItem(item)
            line_item = LinkGraphicsItem(self, item, line_width=2, line_type="dotted",
                                         color="gray", isvisible=True)
            self.scene().addItem(line_item)

        # --- Import selected A/V segments
        for s in ui.selected_av:
            y += 40
            item = AVGraphicsItem(self.app, s['avid'], x, y,
                                   s['pos0'], s['pos1'], s['path'])
            msg = f"AVID:{s['avid']} File: {s['filename']}\nCode: {s['codename']}"
            msg += f"\n{s['pos0']} - {s['pos1']} msecs"
            if s['memo']:
                msg += f"\nMemo: {s['memo']}"
            item.setToolTip(msg)
            self.scene().addItem(item)
            line_item = LinkGraphicsItem(self, item, line_width=2, line_type="dotted",
                                         color="gray", isvisible=True)
            self.scene().addItem(line_item)
    # ---        

    def add_cooccurring_codes(self):
        """ Importa códigos co-ocurrentes desde un nodo específico sin duplicados """
        cur = self.app.conn.cursor()
        sql = """
        SELECT c2.cid, n2.name, n2.color, COUNT(c2.cid) as overlap_count
        FROM code_text c1
        JOIN code_text c2 ON c1.fid = c2.fid AND c1.cid != c2.cid AND c1.pos0 < c2.pos1 AND c1.pos1 > c2.pos0
        JOIN code_name n2 ON c2.cid = n2.cid
        WHERE c1.cid = ?
        GROUP BY c2.cid, n2.name, n2.color
        """
        cur.execute(sql, [self.code_or_cat['cid']])
        res = cur.fetchall()
        
        if not res:
            Message(self.app, "Sin co-ocurrencias", "No hay códigos que se sobrepongan con este en los textos.").exec()
            return
            
        cooc_list = [{'cid': r[0], 'name': f"{r[1]} (Co-occ freq: {r[3]})", 'raw_name': r[1], 'color': r[2], 'count': r[3]} for r in res]
            
        ui = DialogSelectItems(self.app, cooc_list, "Select codes", "multi")
        if not ui.exec():
            return
            
        selected = ui.get_selected()
        
        import math
        radius = 250 
        angle_step = (2 * math.pi) / max(1, len(selected))
        
        for i, s in enumerate(selected):
            # CORRECCIÓN: Uso estricto de str()
            target_node = next((item for item in self.scene().items() if type(item).__name__ == "TextGraphicsItem" and str(item.code_or_cat.get('cid')) == str(s['cid'])), None)
                    
            if not target_node:
                angle = i * angle_step
                cx = self.pos().x() + radius * math.cos(angle)
                cy = self.pos().y() + radius * math.sin(angle)
                
                code_data = {'name': s['raw_name'], 'supercatid': None, 'catid': None, 'cid': s['cid'], 
                             'x': cx, 'y': cy, 'color': s['color'], 'memo': "", 'child_names': []}
                target_node = TextGraphicsItem(self.app, code_data)
                self.scene().addItem(target_node)
                
            line_exists = any(type(link).__name__ == "LinkGraphicsItem" and 
                              ((link.from_widget == self and link.to_widget == target_node) or 
                               (link.from_widget == target_node and link.to_widget == self)) 
                              for link in self.scene().items())
                              
            if not line_exists:
                line_item = LinkGraphicsItem(self, target_node, line_width=2, line_type="dotted", color="blue", isvisible=True)
                self.scene().addItem(line_item)

    def add_edit_memo(self):
        """ Add or edit memos for codes and categories. """

        if self.code_or_cat['cid'] is not None:
            ui = DialogMemo(self.app, "Memo for Code " + self.code_or_cat['name'], self.code_or_cat['memo'])
            ui.exec()
            self.code_or_cat['memo'] = ui.memo
            cur = self.conn.cursor()
            cur.execute("update code_name set memo=? where cid=?", (self.code_or_cat['memo'], self.code_or_cat['cid']))
            self.conn.commit()
        if self.code_or_cat['catid'] is not None and self.code_or_cat['cid'] is None:
            ui = DialogMemo(self.app, "Memo for Category " + self.code_or_cat['name'], self.code_or_cat['memo'])
            ui.exec()
            self.code_or_cat['memo'] = ui.memo
            cur = self.conn.cursor()
            cur.execute("update code_cat set memo=? where catid=?",
                        (self.code_or_cat['memo'], self.code_or_cat['catid']))
            self.conn.commit()
    def toggle_collapse(self):
        """ Oculta o muestra todos los nodos descendientes y actualiza las líneas """
        self.is_collapsed = not getattr(self, 'is_collapsed', False)
        
        # 1. Ocultar/Mostrar nodos hijos en cascada
        for item in self.scene().items():
            if type(item).__name__ == "TextGraphicsItem" and item != self:
                if item.code_or_cat['name'] in self.code_or_cat.get('child_names', []):
                    if self.is_collapsed:
                        item.hide()
                    else:
                        item.show()
                        item.is_collapsed = False # Reinicia el estado de los hijos para evitar errores lógicos
                        
        # 2. Refrescar las líneas (Ocultar las que queden sueltas)
        for item in self.scene().items():
            if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                    if not item.from_widget.isVisible() or not item.to_widget.isVisible():
                        item.hide()
                    else:
                        item.show()
                        
        self.scene().update()            

    def case_media(self, ):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders. """

        DialogCodeInAllFiles(self.app, self.code_or_cat, "Case")

    def coded_media(self, ):
        """ Display all coded media for this code.
        Coded media comes from ALL files and current coder.
        """

        DialogCodeInAllFiles(self.app, self.code_or_cat)


class LinkGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Takes the coordinate from the two TextGraphicsItems. """

    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None
    line_width = 2
    line_type = QtCore.Qt.PenStyle.SolidLine
    text = ""
    color = "gray"

    # Propuesta: Se amplía la firma del constructor con el parámetro opcional 'label=""' 
    # para permitir que las conexiones (aristas) puedan renderizar información analítica (ej. frecuencias).
    def __init__(self, from_widget, to_widget, line_width=2, line_type="solid",
                 color="gray", isvisible=True, label=""):
        """ Links codes and categories. Called when codes or categories of categories are inserted.
         param: from_widget  : TextGraphicsItem
         param: to_widget : TextGraphicsItem
         param: line_width : Real
         param: line_type : String
         param: color : String
         param: isvisible : boolean
        """
        # ---
        super(LinkGraphicsItem, self).__init__(None)

        self.app = from_widget.app
        self.from_widget = from_widget   
        # ---
        self.from_widget = from_widget
        self.to_widget = to_widget
        self.text = from_widget.text + " - " + to_widget.text
        self.line_width = line_width
        # --- La línea no se puede seleccionar y no responde al arrastre del mouse izquierdo
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.RightButton)
        # ---
        self.calculate_points_and_draw()
        self.color = color
        if not isvisible:
            self.hide()
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine
            
        # garantiza que el texto nunca sufrirá desincronización física si los nodos conectados son arrastrados rápidamente.
        self.label = str(label)
        self.text_item = None
        if self.label:
            self.text_item = QtWidgets.QGraphicsTextItem(self.label, self)
            font = QtGui.QFont()
            font.setPointSize(9)
            font.setBold(True)
            self.text_item.setFont(font)
            self.text_item.setDefaultTextColor(QtGui.QColor("#0000CD")) # Azul para destacar atributos relacionales
            
        self.redraw()

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        # --- Sub-menú de grosor y estilo de línea ---
        line_menu = menu.addMenu(_('Line style'))
        width1_action = line_menu.addAction(_('Thin (1px)'))
        width2_action = line_menu.addAction(_('Normal (2px)'))
        width4_action = line_menu.addAction(_('Thick (4px)'))
        width6_action = line_menu.addAction(_('Extra thick (6px)'))
        line_menu.addSeparator()
        dotted_action = line_menu.addAction(_('Dotted'))
        solid_action = line_menu.addAction(_('Solid'))
        # --- Sub-menú de color ---
        color_menu = menu.addMenu(_('Line color'))
        red_action = color_menu.addAction(_('Red'))
        yellow_action = color_menu.addAction(_('Yellow'))
        green_action = color_menu.addAction(_('Green'))
        blue_action = color_menu.addAction(_('Blue'))
        cyan_action = color_menu.addAction(_('Cyan'))
        magenta_action = color_menu.addAction(_('Magenta'))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        menu.addSeparator()
        hide_action = menu.addAction(_('Hide'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # Grosor
        if action == width1_action:
            self.line_width = 1
        if action == width2_action:
            self.line_width = 2
        if action == width4_action:
            self.line_width = 4
        if action == width6_action:
            self.line_width = 6
        # Estilo
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
        if action == solid_action:
            self.line_type = QtCore.Qt.PenStyle.SolidLine
        # Color
        if action == red_action:
            self.color = "red"
        if action == yellow_action:
            self.color = "yellow"
        if action == green_action:
            self.color = "green"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == gray_action:
            self.color = "gray"
        # ---    
        if action == hide_action:
            ui_confirm = DialogConfirmDelete(self.app, _("Hide this line?"))
            if not ui_confirm.exec():
                return
            self.hide()
        # ---    
        self.redraw()

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculate_points_and_draw()

    def calculate_points_and_draw(self):
        """ Cálculo fluido de intersección perimetral. """
        import math
        
        c1 = self.from_widget.sceneBoundingRect().center()
        c2 = self.to_widget.sceneBoundingRect().center()
        
        # Enviar la línea detrás de los nodos visualmente
        self.setZValue(-1)

        is_ellipse_from = getattr(self.from_widget, 'is_ellipse', False)
        is_ellipse_to = getattr(self.to_widget, 'is_ellipse', False)
        
        rect1 = self.from_widget.sceneBoundingRect()
        rect2 = self.to_widget.sceneBoundingRect()
        
        def get_edge_point(center_source, center_target, rect, is_ellipse):
            dx = center_target.x() - center_source.x()
            dy = center_target.y() - center_source.y()
            if dx == 0 and dy == 0: return center_source
            
            w = rect.width() / 2
            h = rect.height() / 2
            
            if is_ellipse:
                angle = math.atan2(dy, dx)
                return QtCore.QPointF(center_source.x() + w * math.cos(angle), center_source.y() + h * math.sin(angle))
            else:
                if dx == 0: return QtCore.QPointF(center_source.x(), center_source.y() + math.copysign(h, dy))
                if dy == 0: return QtCore.QPointF(center_source.x() + math.copysign(w, dx), center_source.y())
                
                tx = w / abs(dx)
                ty = h / abs(dy)
                t = min(tx, ty)
                return QtCore.QPointF(center_source.x() + dx * t, center_source.y() + dy * t)

        if rect1.intersects(rect2):
            p1 = c1
            p2 = c2
        else:
            p1 = get_edge_point(c1, c2, rect1, is_ellipse_from)
            p2 = get_edge_point(c2, c1, rect2, is_ellipse_to)

        color_obj = colors[self.color]
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
        
        if hasattr(self, 'text_item') and self.text_item:
            mid_x = (p1.x() + p2.x()) / 2
            mid_y = (p1.y() + p2.y()) / 2
            br = self.text_item.boundingRect()
            self.text_item.setPos(mid_x - br.width() / 2, mid_y - br.height() / 2)
  
