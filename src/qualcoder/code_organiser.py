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
https://qualcoder.org/
"""
import csv  # codebook import
import logging  # was missing; apply/transaction paths log debug and errors
import math  # perimeter line geometry
import sqlite3
from copy import deepcopy
import datetime
import os
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from random import randint
import xml.etree.ElementTree as etree  # QDC codebook import

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import TextColor, colors as valid_colors
from .GUI.ui_dialog_organiser import Ui_DialogOrganiser
from .helpers import ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)  # was commented out

# Easier to modify these variables across classes
model = []
update_graphics_item_models = False


class CodeOrganiser(QDialog):
    """ Dialog to organise code and categories in an acyclic graph.
    Add new categories, move codes and categories to other categories.
    Merge codes and categories
    Delete categories
    """

    app = None
    parent_text_edit = None
    conn = None
    settings = None
    scene = None
    font_size = 9

    def __init__(self, app, text_edit):
        """ Set up the dialog and graphics scene. """

        QDialog.__init__(self)
        self.app = app
        self.parent_text_edit = text_edit
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogOrganiser()
        self.ui.setupUi(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export.pressed.connect(self.export_image)
        self.ui.label_zoom.setPixmap(qta.icon('mdi6.magnify').pixmap(26, 26))
        # the loupe is now clickable: fit and center the whole graph
        self.ui.label_zoom.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.ui.label_zoom.setToolTip(_("Click to fit and center the graph. In the graph, "
                                        "press + or W to zoom in, - or Q to zoom out."))
        self.ui.label_zoom.installEventFilter(self)
        self.ui.pushButton_selectbranch.setIcon(qta.icon('mdi6.file-tree', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_selectbranch.pressed.connect(self.select_tree_branch)
        self.ui.pushButton_create_category.setIcon(qta.icon('mdi6.pencil-plus-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_create_category.pressed.connect(self.create_category)
        self.ui.pushButton_apply.setEnabled(False)
        self.ui.pushButton_apply.pressed.connect(self.apply_model_changes)
        # free code creation and codebook import (model-first: nothing
        # touches the database until Apply)
        self.ui.pushButton_create_code.setIcon(qta.icon('mdi6.tag-plus-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_create_code.pressed.connect(self.create_code)
        self.ui.pushButton_import_codebook.setIcon(qta.icon('mdi6.book-arrow-down-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_import_codebook.pressed.connect(self.import_codebook)
        self.show_frequencies = False  # [n] coding frequency labels

        # Set the scene
        self.scene = GraphicsScene(self)  # scene knows its dialog
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)
        # canvas fluidity ported from view_graph: rubber-band multi-selection
        # by default; holding spacebar switches to hand panning (keyPress/keyRelease).
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        self._space_pressed = False
        self._is_panning = False  # middle-button / space+drag panning
        # hierarchical drag-to-connect handle (same UX as the relations
        # handle in view_graph). Click a selected node's blue handle, move, then click
        # the parent: the first node becomes a sub-code / sub-category / code-in-category.
        self._connect_state = 'idle'
        self._connect_source = None
        self.scene.selectionChanged.connect(self._sync_connection_handles)
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = False
        global model  # noqa: F824
        model = []
        text_ = _("BACK UP PROJECT before applying changes to the codes tree.\n"
                  "The Code organiser is used mainly with grounded theory to help you develop and organise"
                  " the coding concepts and their hierarchy.\n"
                  "Select a code branch or All, then right click to:\n"
                  "Add categories, rename codes and categories, update memos, merge codes, "
                  "merge categories, delete categories.\n"
                  "\n"
                  "Potential for unexpected errors could occur.\n"
                  "THERE IS NO UNDO OPTION AFTER APPLYING CHANGES WITH THE APPLY BUTTON.")
        Message(self.app, "Code organiser", text_).exec()

    def create_category(self):
        """ Create a new category, via push button. """

        cat_ids_list = []
        categories = []
        for item in model:
            if item['cid'] is None:
                cat_ids_list.append(item['catid'])
                categories.append(item)
        ui = DialogAddItemName(self.app, categories, _("Category"), _("Category name"))
        ui.exec()
        new_category_name = ui.get_new_name()
        if new_category_name is None:
            return

        temp_cat_id = randint(-1000, -1)
        while temp_cat_id in cat_ids_list:
            temp_cat_id = randint(-1000, -1)
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        new_category = {'name': new_category_name, 'catid': temp_cat_id, 'owner': self.settings['codername'],
                        'date': now_date, 'memo': '', 'supercatid': None,
                        'x': 10 + randint(0, 6), 'y': 10 + randint(0, 6), 'color': "#FFFFFF",
                        'cid': None, 'original_cid': None, 'original_catid': temp_cat_id,
                        'original_memo': '', 'child_names': []}
        model.append(new_category)
        self.scene.addItem(TextGraphicsItem(self.app, new_category))

    def select_tree_branch(self):
        """ Select the code tree branch to organise.
        uses a TREE selector (so a suub-code, code, sub-category or
        category can be chosen, not just a top-level category), and can be used again
        to SWITCH branches. If there are unsaved changes, re-selecting asks first,
        because rebuilding the model from the database would discard them.
        Called by pushButton_selectbranch.
        """

        # switching branches would rebuild the model and drop unsaved edits
        if self.build_pending_changes():
            resp = QtWidgets.QMessageBox.question(
                self, _("Select branch"),
                _("Selecting a different branch will discard unsaved changes to the "
                  "code tree. Continue?"),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No)
            if resp != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        codes, categories = self.app.get_codes_categories()
        ui = DialogSelectBranch(self.app, codes, categories, self)
        if not ui.exec():
            return
        root_key = ui.selected_key  # None (All) or ('cat', catid) or ('code', cid)
        # Clear the scene so a re-selection does not leave the previous branch behind.
        self.scene.clear()
        self.create_initial_model()
        self.get_refined_model(root_key)
        self.list_graph()
        # snapshot of the on-screen model for the Apply change preview.
        # Keyed by stable original ids; immune to actions that overwrite original_*
        # fields (e.g. link_code_under_code rewrites original_supercid).
        self._initial_model = {}
        global model  # noqa: F824
        for item in model:
            key = ('code', item['original_cid']) if item['original_cid'] is not None \
                else ('cat', item['original_catid'])
            self._initial_model[key] = {
                'name': item['name'], 'memo': item['memo'], 'catid': item['catid'],
                'supercatid': item['supercatid'], 'supercid': item.get('supercid')}
        # keep the button ENABLED so the user can switch to another branch
        self.ui.pushButton_selectbranch.setToolTip(_("Select a different code tree branch"))
        self.ui.pushButton_apply.setEnabled(True)
        self.fit_and_center_view()

    def create_initial_model(self):
        """ Create initial model of all codes and categories.
        model contains categories and codes combined.

        return: categories : List of Dictionaries of categories
        """

        codes, categories = self.app.get_codes_categories()
        code_name_equals_category_name = False
        for code in codes:
            code['original_cid'] = code['cid']
            code['original_catid'] = code['catid']
            code['original_memo'] = code['memo']
            code['original_supercid'] = code['supercid']
            code['x'] = None
            code['y'] = None
            code['delete'] = False
            code['supercatid'] = code['catid']

            """ This causes hierarchy to not work correctly.
            Solution, add space after the code_name to separate it out. 
            Trim on database update """
            for cat in categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "
            code['original_name'] = code['name']

        for category in categories:
            category['original_cid'] = None
            category['original_catid'] = category['catid']
            category['original_supercatid'] = category['supercatid']
            category['original_name'] = category['name']
            category['original_memo'] = category['memo']
            category['x'] = None
            category['y'] = None
            category['cid'] = None
            category['supercid'] = None
            category['color'] = '#FFFFFF'
            category['delete'] = False  # True if merged
        global model  # noqa: F824
        model = categories + codes

    def get_refined_model(self, root_key):
        """ Refine the full model down to a selected branch.
        Rroot_key is now a stable key rather than a name, so ANY node can
        be the root, not only a top-level category:
            None (or "All") : keep the full model
            ('cat', catid)  : that category + its sub-categories + their codes + sub-codes
            ('code', cid)   : that code + all its sub-codes (recursive)
        Real parent links (supercatid / supercid) are left intact; list_graph renders the
        root at the top because its parent is not present in the kept set. This means
        Apply never accidentally detaches the chosen sub-branch from its real parent.

        param: root_key : None | "All" | tuple(kind, id)
        """

        global model  # noqa: F824
        if root_key is None or root_key == "All":
            return
        # Backwards tolerance: a bare name still selects a top-level category.
        if isinstance(root_key, str):
            for item in model:
                if item['cid'] is None and item['name'] == root_key:
                    root_key = ('cat', item['catid'])
                    break
            else:
                return
        kind, rid = root_key
        codes = [m for m in model if m['cid'] is not None]
        cats = [m for m in model if m['cid'] is None]

        def descendant_code_ids(seed_cids):
            ids = set()
            frontier = set(seed_cids)
            guard = 0
            while frontier and guard < 100000:
                guard += 1
                nxt = set()
                for c in list(frontier):
                    if c in ids:
                        continue
                    ids.add(c)
                    for code in codes:
                        if code.get('supercid') == c:
                            nxt.add(code['cid'])
                frontier = nxt
            return ids

        keep_catids = set()
        keep_cids = set()
        if kind == 'cat':
            frontier = {rid}
            guard = 0
            while frontier and guard < 100000:
                guard += 1
                nxt = set()
                for cid_ in list(frontier):
                    if cid_ in keep_catids:
                        continue
                    keep_catids.add(cid_)
                    for cat in cats:
                        if cat['supercatid'] == cid_:
                            nxt.add(cat['catid'])
                frontier = nxt
            seed = {code['cid'] for code in codes
                    if code['catid'] in keep_catids and code.get('supercid') is None}
            keep_cids = descendant_code_ids(seed)
        else:  # 'code'
            keep_cids = descendant_code_ids({rid})

        model = [m for m in model
                 if (m['cid'] is None and m.get('catid') in keep_catids)
                 or (m['cid'] is not None and m['cid'] in keep_cids)]

    def named_children_of_node(self, node):
        """ Get child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.

        param: node : Dictionary of category

        return: child_names : List
        """

        if node['cid'] is not None:
            # A code may now have sub-codes (supercid). Return descendant sub-code names
            # so they move together with the parent code when it is dragged.
            all_codes, _cats = self.app.get_codes_categories()
            child_names = []
            frontier = [node['cid']]
            guard = 0
            while frontier and guard < 1000:
                guard += 1
                current = frontier.pop()
                for code in all_codes:
                    if code.get('supercid') == current and code['name'] not in child_names:
                        child_names.append(code['name'])
                        frontier.append(code['cid'])
            return child_names
        child_names = []
        codes_, categories_ = self.app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in codes_:
            for cat in categories_:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories_ != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in categories_:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for n in append_list:
                selected_categories.append(n)
                categories_.remove(n)
                new_model_changed = True
            i += 1
        categories_ = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in categories_:
            for code in codes_:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        codes_ = selected_codes
        for c in codes_:
            child_names.append(c['name'])
        return child_names

    def list_graph(self):
        """ Create a list graph with the categories on the left and codes on the right.

        param: global model : List of Dictionaries of categories and codes
        """

        global model  # noqa: F824
        # Order the model by supercatid, subcats, codes
        ordered_model = []
        # a node is "top level" for layout when its PARENT is not present
        # in the current model. For the full tree this matches the old rule (supercatid
        # None, no supercid); for a selected sub-branch it also lets the chosen root
        # (a sub-category or sub-code, whose real parent is outside the view) sit at the
        # top WITHOUT clearing its real parent link (so Apply never detaches it).
        present_catids = {m['catid'] for m in model
                          if m['cid'] is None and m.get('catid') is not None}
        present_cids = {m['cid'] for m in model if m['cid'] is not None}

        def _is_top(item):
            if item['cid'] is None:  # category
                return item['supercatid'] is None or item['supercatid'] not in present_catids
            if item.get('supercid'):  # sub-code
                return item['supercid'] not in present_cids
            if item.get('catid') is not None:  # code inside a category
                return item['catid'] not in present_catids
            return True  # free code

        for code_or_cat in model:
            if code_or_cat['x'] is None and _is_top(code_or_cat):
                code_or_cat['x'] = 10
                ordered_model.append(code_or_cat)
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
                    # sub-codes nested under their parent code
                    if sub_cat.get('supercid') is not None and sub_cat['supercid'] == om.get('cid') \
                            and sub_cat['x'] is None:
                        sub_cat['x'] = om['x'] + 120
                        ordered_model.insert(ordered_model.index(om), sub_cat)
            i += 1

        # safety net. Anything still unplaced (odd data) is kept, never dropped.
        for leftover in model:
            if not any(leftover is o for o in ordered_model):
                if leftover['x'] is None:
                    leftover['x'] = 10
                ordered_model.append(leftover)

        for item in range(0, len(ordered_model)):
            ordered_model[item]['y'] = item * self.font_size * 3
        model = ordered_model

        # Add text items to the scene, providing they are not already in the scene.
        for code_or_cat in model:
            code_or_cat['child_names'] = self.named_children_of_node(code_or_cat)
            add_to_scene = True
            for scene_item in self.scene.items():
                if isinstance(scene_item, TextGraphicsItem):
                    if scene_item.code_or_cat['name'] == code_or_cat['name'] and \
                            scene_item.code_or_cat['catid'] == code_or_cat['catid'] and \
                            scene_item.code_or_cat['cid'] == code_or_cat['cid']:
                        add_to_scene = False
            if add_to_scene:
                self.scene.addItem(TextGraphicsItem(self.app, code_or_cat))

        # build the hierarchy lines now. The old code relied on the next
        # mouseMoveEvent rebuilding ALL links unconditionally; links are created
        # explicitly here, deterministic and independent of mouse movement.
        self.scene.remove_links()
        self.scene.create_links()
        # size the scene to the items bounding rect (negatives allowed),
        # consistent with dragging; avoids re-clipping to (0,0) on a structural refresh.
        self.scene.update_scene_bounds()

    def keyPressEvent(self, event):
        """ Plus, W to zoom in and Minus, Q to zoom out.
        M to print Model
        Needs focus on the QGraphicsView widget. """

        key = event.key()
        # mod = event.modifiers()
        # Escape cancels an in-progress hierarchical conexión
        if key == QtCore.Qt.Key.Key_Escape and self._connect_state != 'idle':
            self._cancel_connection()
            return
        # spacebar panning (ported from view_graph)
        if key == QtCore.Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
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
        if key == QtCore.Qt.Key.Key_I:
            for i in self.scene.items():
                print(i.__class__, i.pos())
        if key == QtCore.Qt.Key.Key_M:  # and mod == QtCore.Qt.KeyboardModifier.ControlModifier:
            # Display model
            global model  # noqa: F824
            print("^^^^ MODEL ^^^^")
            for m in model:
                print(m)
            print("^^^^^^^ CATS ^^^^^^^^^")
            for category in model:
                if category['cid'] is None:
                    print(category)
            print("^^^^^^^ CODES ^^^^^^^^^")
            for code in model:
                if code['cid'] is not None:
                    print(code)
            print("^^^^^^^^^^^^^^^^")

    def keyReleaseEvent(self, event):  # end spacebar panning
        if event.key() == QtCore.Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.ui.graphicsView.viewport().unsetCursor()
            return
        super().keyReleaseEvent(event)

    def reject(self):

        super(CodeOrganiser, self).reject()

    def accept(self):

        super(CodeOrganiser, self).accept()

    def eventFilter(self, obj, event):
        """ Forwards context menu events to graphics view items, and implements
        mouse-wheel zoom anchored under the cursor (ported from view_graph)
        https://stackoverflow.com/questions/71993533/ """

        # clicking the loupe fits and centers the graph
        if obj == self.ui.label_zoom:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                self.fit_and_center_view()
                return True
            return super().eventFilter(obj, event)

        if obj == self.ui.graphicsView.viewport():
            # ZOOM with the mouse wheel, anchored under the cursor
            if event.type() == QtCore.QEvent.Type.Wheel:
                self.ui.graphicsView.setTransformationAnchor(
                    QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                self.ui.graphicsView.setResizeAnchor(
                    QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                zoom_in_factor = 1.15
                zoom_out_factor = 1.0 / zoom_in_factor
                current_det = self.ui.graphicsView.transform().determinant()
                if event.angleDelta().y() > 0:
                    if current_det < 25:  # cap at ~5x linear zoom
                        self.ui.graphicsView.scale(zoom_in_factor, zoom_in_factor)
                else:
                    if current_det > 0.04:  # cap at ~0.2x linear zoom
                        self.ui.graphicsView.scale(zoom_out_factor, zoom_out_factor)
                return True

            # hierarchical DRAG-TO-CONNECT. Active whenever a node is selected
            # (its handle is showing) or a connection is already in progress. Left click
            # on the handle starts it; moving updates the dashed preview; the next left
            # click on a node completes it. Right/middle clicks fall through untouched.
            if self.scene.selectedItems() or self._connect_state != 'idle':
                if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                    if event.button() == QtCore.Qt.MouseButton.LeftButton:
                        scene_pos = self.ui.graphicsView.mapToScene(event.position().toPoint())
                        if self._find_handle_at(scene_pos) is not None:
                            self._handle_connect_click(scene_pos)
                            return True
                        if self._connect_state == 'dragging_preview':
                            self._handle_connect_click(scene_pos)
                            return True
                elif event.type() == QtCore.QEvent.Type.MouseMove:
                    if self._connect_state == 'dragging_preview':
                        scene_pos = self.ui.graphicsView.mapToScene(event.position().toPoint())
                        self.scene.set_connection_preview(self._connect_source, scene_pos)
                        return True

            # PAN with the middle mouse button, or left button while the
            # spacebar is held. Ported from view_graph (identical mechanism).
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.MiddleButton or (
                        event.button() == QtCore.Qt.MouseButton.LeftButton
                        and getattr(self, '_space_pressed', False)):
                    self._is_panning = True
                    self._pan_start_x = event.position().x()
                    self._pan_start_y = event.position().y()
                    self.ui.graphicsView.viewport().setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    return True

            elif event.type() == QtCore.QEvent.Type.MouseMove and getattr(self, '_is_panning', False):
                dx = event.position().x() - self._pan_start_x
                dy = event.position().y() - self._pan_start_y
                self.ui.graphicsView.horizontalScrollBar().setValue(
                    int(self.ui.graphicsView.horizontalScrollBar().value() + dx))
                self.ui.graphicsView.verticalScrollBar().setValue(
                    int(self.ui.graphicsView.verticalScrollBar().value() - dy))
                self._pan_start_x = event.position().x()
                self._pan_start_y = event.position().y()
                return True

            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                if getattr(self, '_is_panning', False) and (
                        event.button() == QtCore.Qt.MouseButton.MiddleButton
                        or event.button() == QtCore.Qt.MouseButton.LeftButton):
                    self._is_panning = False
                    cursor = (QtCore.Qt.CursorShape.OpenHandCursor
                              if getattr(self, '_space_pressed', False)
                              else QtCore.Qt.CursorShape.ArrowCursor)
                    self.ui.graphicsView.viewport().setCursor(cursor)
                    return True

            elif event.type() == event.Type.ContextMenu:
                self.ui.graphicsView.contextMenuEvent(event)
                return event.isAccepted()
        return super().eventFilter(obj, event)

    def graphicsview_menu(self, position):
        item = self.ui.graphicsView.itemAt(position)
        if item is not None:
            # sendEvent(item) lacked the event argument (TypeError on
            # every right-click over an item). The item's own context menu already
            # arrives through the eventFilter ContextMenu forwarding; nothing to do.
            return
        # Menu for blank graphics view area
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        #action_print_items = menu.addAction(_("Print items"))
        action_add_category = menu.addAction(_("Add category"))
        # coding frequency labels toggle
        freq_text = _("Hide frequencies") if self.show_frequencies else _("Show frequencies")
        action_frequencies = menu.addAction(freq_text)
        menu.addSeparator()
        action_fit_center = menu.addAction(_("Fit and center view"))
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        if action == action_fit_center:
            self.fit_and_center_view()
            return
        if action == action_frequencies:
            self.show_frequencies = not self.show_frequencies
            self.apply_frequency_labels()
            return
        '''if action == action_print_items:
            print("\nPrint graphics items\n========")
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    print(f"Graphics item: {i.code_or_cat['name']} cid:{i.code_or_cat['cid']} "
                          f"ocid:{i.code_or_cat['original_cid']}"
                          f" catid:{i.code_or_cat['catid']} ocatid:{i.code_or_cat['original_catid']} "
                          f"supercatid:{i.code_or_cat['supercatid']} child names{i.code_or_cat['child_names']}")'''
        if action == action_add_category:
            global model  # noqa: F824
            cat_ids_list = []
            categories_ = []
            for item in model:
                if item['cid'] is None:
                    cat_ids_list.append(item['catid'])
            ui = DialogAddItemName(self.app, categories_, _("Category"), _("Category name"))
            ui.exec()
            new_category_name = ui.get_new_name()
            if new_category_name is None:
                return

            temp_cat_id = randint(-1000, -1)
            while temp_cat_id in cat_ids_list:
                temp_cat_id = randint(-1000, -1)
            now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            # No original_name, original_catid, original_supercatid, orignal-memo
            new_category = {'name': new_category_name, 'original_name': '', 'catid': temp_cat_id,
                            'owner': self.settings['codername'], 'date': now_date, 'memo': '', 'original_memo': '',
                            'supercatid': None, 'original_supercatid': None, 'x': 10 + randint(0, 6),
                            'y': 10 + randint(0, 6), 'color': "#FFFFFF", 'cid': None, 'child_names': [],
                            'original_cid': None,  'original_catid': temp_cat_id}
            model.append(new_category)
            self.scene.addItem(TextGraphicsItem(self.app, new_category))  # codes, categories))

    # ----- hierarchical drag-to-connect handle + fit/center view -----
    # The handle mirrors the relations handle in view_graph, but instead of drawing a
    # relationship line it establishes a HIERARCHY: dragging node A's handle onto node
    # B files A under B (sub-code, sub-category, or code-in-category). Purely a model
    # edit, exactly like the right-click "Link ..." actions; Apply persists it.

    def _sync_connection_handles(self):
        """ Show the blue connect handle on a node only while it is the SOLE selected
        item (identical behaviour to the graph view). Idempotent, tolerant to the
        C++ item having been destroyed. """
        try:
            selected = [it for it in self.scene.items()
                        if isinstance(it, TextGraphicsItem) and it.isSelected()]
        except RuntimeError:
            return
        sole = selected[0] if len(selected) == 1 else None
        for it in self.scene.items():
            if not isinstance(it, TextGraphicsItem):
                continue
            handle = getattr(it, '_conn_handle', None)
            if it is sole:
                if handle is None or handle.scene() is None:
                    it._conn_handle = ConnectionHandleItem(it)
            elif handle is not None:
                try:
                    if handle.scene() == self.scene:
                        self.scene.removeItem(handle)
                except RuntimeError:
                    pass
                it._conn_handle = None

    def _find_handle_at(self, scene_pos):
        """ Return the node owning a ConnectionHandleItem under scene_pos, or None. """
        for item in self.scene.items(scene_pos):
            if isinstance(item, ConnectionHandleItem):
                return item.parent_item
        return None

    def _cancel_connection(self):
        """ Reset the connect state machine and clear the dashed preview line. """
        self._connect_state = 'idle'
        self._connect_source = None
        self.scene.clear_connection_preview()

    def _handle_connect_click(self, scene_pos):
        """ Two-click state machine (click handle, move, click parent), mirroring the
        graph view. On completion, SOURCE becomes a child of the clicked node. """
        if self._connect_state == 'idle':
            src = self._find_handle_at(scene_pos)
            if src is not None:
                self._connect_source = src
                self._connect_state = 'dragging_preview'
                self.scene.set_connection_preview(src, scene_pos)
            return
        if self._connect_state == 'dragging_preview':
            target = None
            for item in self.scene.items(scene_pos):
                if isinstance(item, TextGraphicsItem) and item.code_or_cat.get('name', '') != "":
                    target = item
                    break
            source = self._connect_source
            self._cancel_connection()
            if target is None or target is source:
                return
            self._apply_hierarchy_connection(source, target)

    def _apply_hierarchy_connection(self, source, target):
        """ Establish a hierarchical link: drag SOURCE's handle onto TARGET reads as
        'file SOURCE under TARGET' (SOURCE becomes the child). Reuses the exact model
        mutations of the right-click link operations, so the outcome is identical and
        the same circular-nesting guards apply. Model only; Apply writes to the DB. """
        global model  # noqa: F824
        global update_graphics_item_models  # noqa: F824
        s = source.code_or_cat
        t = target.code_or_cat
        if s is t or s.get('name', '') == "" or t.get('name', '') == "":
            return
        s_is_code = s.get('cid') is not None
        t_is_code = t.get('cid') is not None

        if not s_is_code and t_is_code:
            # No such relation: a category cannot live under a code.
            Message(self.app, _("Code organiser"),
                    _("A category cannot be nested under a code."), "warning").exec()
            return

        if s_is_code and t_is_code:
            # Sub-code: source nested under target (supercid). Block cycles.
            if t['cid'] == s['cid'] or t['cid'] in descendant_cids(model, s['cid']):
                Message(self.app, _("Code organiser"),
                        _("Cannot nest a code under one of its own sub-codes."), "warning").exec()
                return
            for item in model:
                if item.get('cid') == s['cid']:
                    item['supercid'] = t['cid']
                    item['original_supercid'] = t['cid']
                    item['catid'] = None
                    item['supercatid'] = None
        elif s_is_code and not t_is_code:
            # Code into category (catid). Exclusivity: a categorised code is not a sub-code.
            for item in model:
                if item.get('cid') == s['cid']:
                    item['catid'] = t['catid']
                    item['supercid'] = None
        else:
            # Sub-category: source category under target category (supercatid). Block cycles.
            if t['catid'] == s['catid'] or t['catid'] in descendant_catids(model, s['catid']):
                Message(self.app, _("Code organiser"),
                        _("Cannot nest a category under one of its own sub-categories."), "warning").exec()
                return
            for item in model:
                if item.get('cid') is None and item.get('catid') == s['catid']:
                    item['supercatid'] = t['catid']

        update_graphics_item_models = True
        self.scene.remove_links()
        self.scene.create_links()
        if getattr(self, 'show_frequencies', False):
            self.apply_frequency_labels()
        self.scene.update()

    def _fit_view_to_items(self):
        """ Fit the items bounding rect into the viewport and center it, clamping the
        zoom-in to 2.0x for small graphs. Ported from view_graph. """
        rect = self.scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        rect.adjust(-80, -80, 80, 80)
        max_scene = 50000
        if rect.width() > max_scene or rect.height() > max_scene:
            rect.setWidth(min(rect.width(), max_scene))
            rect.setHeight(min(rect.height(), max_scene))
        self.scene.setSceneRect(rect)
        self.ui.graphicsView.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        if self.ui.graphicsView.transform().m11() > 2.0:
            self.ui.graphicsView.resetTransform()
            self.ui.graphicsView.scale(2.0, 2.0)
        self.ui.graphicsView.centerOn(rect.center())

    def fit_and_center_view(self):
        """ Deferred fit + center via the event loop, so it works even right after the
        dialog opens (before the viewport has its final geometry). Ported from view_graph. """
        def _do_fit():
            try:
                self._fit_view_to_items()
            except RuntimeError:
                pass  # dialog closed before the deferred fit ran
        QtCore.QTimer.singleShot(0, _do_fit)

    # ----- free code creation and codebook import (model-first) -----
    # Nothing below writes to the database. New codes and categories live in the
    # model with temporary NEGATIVE ids and are inserted inside the single Apply
    # transaction (rolled back completely on any failure).

    def _next_temp_cid(self):
        """ Deterministic unique temporary negative cid. """
        global model  # noqa: F824
        negatives = [it['cid'] for it in model if it.get('cid') is not None and it['cid'] < 0]
        return (min(negatives) - 1) if negatives else -1

    def _next_temp_catid(self):
        """ Deterministic unique temporary negative catid. """
        global model  # noqa: F824
        negatives = [it['catid'] for it in model if it.get('catid') is not None and it['catid'] < 0]
        return (min(negatives) - 1) if negatives else -1

    def _collect_existing_item_names(self):
        """ Names from the model AND the whole database (codes and categories), so a
        new code cannot collide with anything, in or out of the selected branch. """
        global model  # noqa: F824
        names = set(it.get('name', '') for it in model)
        cur = self.app.conn.cursor()
        cur.execute("select name from code_name")
        names.update(row[0] for row in cur.fetchall())
        cur.execute("select name from code_cat")
        names.update(row[0] for row in cur.fetchall())
        names.discard('')
        return [{'name': n} for n in sorted(names)]

    def _lock_branch_selection(self):
        """ Previously this DISABLED the branch button after new items
        were added (to stop a re-select silently discarding them). The button now stays
        enabled so the user can switch branches; select_tree_branch asks for confirmation
        first when there are unsaved changes, which covers the same risk. """
        if not hasattr(self, '_initial_model'):
            self._initial_model = {}
        self.ui.pushButton_apply.setEnabled(True)

    def _new_code_entry(self, name, memo, catid=None, supercid=None, x=10, y=10, color=None):
        """ Model entry for a NEW code with a temporary negative cid. """
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if color is None:
            color = valid_colors[randint(0, len(valid_colors) - 1)]
        temp_cid = self._next_temp_cid()
        return {
            'name': name, 'original_name': name,
            'cid': temp_cid, 'original_cid': temp_cid,
            'catid': catid, 'original_catid': catid,
            'supercid': supercid, 'original_supercid': supercid,
            'supercatid': catid,
            'owner': self.app.settings['codername'], 'date': now_date,
            'memo': memo, 'original_memo': '',
            'x': x, 'y': y, 'color': color,
            'delete': False, 'child_names': []}

    def _new_category_entry(self, name, memo, supercatid=None, x=None, y=None):
        """ Model entry for a NEW category with a temporary negative catid. """
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        temp_catid = self._next_temp_catid()
        return {
            'name': name, 'catid': temp_catid, 'original_catid': temp_catid,
            'cid': None, 'original_cid': None, 'supercid': None,
            'supercatid': supercatid,
            'owner': self.app.settings['codername'], 'date': now_date,
            'memo': memo, 'original_memo': '', 'original_name': '',
            'x': x, 'y': y, 'color': '#FFFFFF',
            'delete': False, 'child_names': []}

    def create_code(self):
        """ Create a new unlinked (free) code via push button. Model only. """

        global model  # noqa: F824
        ui = DialogAddItemName(self.app, self._collect_existing_item_names(),
                               _("Code"), _("Code name"))
        ui.exec()
        new_code_name = ui.get_new_name()
        if new_code_name is None:
            return
        # no memo editor on creation; memos are added later via the
        # node's context menu
        new_code = self._new_code_entry(new_code_name, "",
                                        x=10 + randint(0, 60), y=10 + randint(0, 60))
        model.append(new_code)
        self.scene.addItem(TextGraphicsItem(self.app, new_code))
        self._lock_branch_selection()

    def import_codebook(self):
        """ Import a codebook from QDC (REFI-QDA XML), TXT, or CSV into the canvas
        model. Imported items get temporary negative ids; the database is only
        written on Apply, inside its transaction. """

        global model  # noqa: F824
        file_filter = "Codebook files (*.qdc *.txt *.csv)"
        filepath, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, _("Import codebook"), self.app.settings.get('directory', ''), file_filter)
        if not filepath:
            return
        # collision pre-check. If names in the file already exist, the
        # user chooses: reuse existing items (refi.py semantics, no duplicates) or
        # import them as copies with a numeric suffix.
        policy = 'reuse'
        try:
            incoming = self._collect_incoming_names(filepath)
        except Exception as e_:
            logger.error(f"Codebook read failed: {e_}")
            Message(self.app, _("Import error"), str(e_), "warning").exec()
            return
        collisions = [n for n in sorted(incoming)
                      if self._find_existing_code(n) is not None
                      or self._find_existing_category(n) is not None]
        if collisions:
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle(_("Codebook import"))
            box.setText(str(len(collisions)) + _(" names in the codebook already exist in the project."))
            box.setInformativeText(_("Reuse the existing codes and categories (no duplicates), "
                                     "or import them as copies with a numeric suffix?"))
            box.setDetailedText("\n".join(collisions))
            reuse_btn = box.addButton(_("Reuse existing"), QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            copy_btn = box.addButton(_("Import as copies"), QtWidgets.QMessageBox.ButtonRole.ActionRole)
            box.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is copy_btn:
                policy = 'copy'
            elif clicked is not reuse_btn:
                return
        stats = {'codes': 0, 'cats': 0, 'reused': 0}
        try:
            if filepath.lower().endswith('.qdc'):
                self._import_qdc_codebook(filepath, stats, policy)
            elif filepath.lower().endswith('.txt'):
                self._import_txt_codebook(filepath, stats, policy)
            elif filepath.lower().endswith('.csv'):
                self._import_csv_codebook(filepath, stats, policy)
        except Exception as e_:
            logger.error(f"Codebook import failed: {e_}")
            Message(self.app, _("Import error"), str(e_), "warning").exec()
            return
        if stats['codes'] + stats['cats'] == 0:
            msg = _("No new items were imported.")
            if stats['reused']:
                msg += " " + str(stats['reused']) + _(" names already exist and were reused.")
            Message(self.app, _("Codebook import"), msg).exec()
            return
        # Full relayout: list_graph positions the whole model (including the new
        # items, which arrive with x/y None), then every graphics item is moved to
        # its computed position.
        self.list_graph()
        for gr_item in self.scene.items():
            if isinstance(gr_item, TextGraphicsItem) and gr_item.code_or_cat.get('x') is not None:
                gr_item.setPos(gr_item.code_or_cat['x'], gr_item.code_or_cat['y'])
        self.scene.remove_links()
        self.scene.create_links()
        self._lock_branch_selection()
        msg = str(stats['codes']) + _(" codes and ") + str(stats['cats']) \
            + _(" categories imported into canvas.")
        if stats['reused']:
            msg += " " + str(stats['reused']) + _(" existing names reused (not duplicated).")
        Message(self.app, _("Codebook imported"), msg).exec()

    def _collect_incoming_names(self, filepath):
        """ All code/category names present in the codebook file, for the
        collision pre-check (no model mutation). """

        names = set()
        if filepath.lower().endswith('.qdc'):
            tree = etree.parse(filepath)
            for el in tree.iter():
                if isinstance(el.tag, str) and el.tag.endswith('}Code'):
                    n = el.get('name')
                    if n:
                        names.add(n.strip())
        else:
            for path_part, _memo in self._read_path_rows(filepath):
                for seg in path_part.split('>>'):
                    if seg.strip():
                        names.add(seg.strip())
        return names

    def _suffixed_name(self, base):
        """ first free 'base_N' name, checked against model and database. """

        base = base.strip()
        counter = 2
        candidate = f"{base}_{counter}"
        while self._find_existing_code(candidate) is not None \
                or self._find_existing_category(candidate) is not None:
            counter += 1
            candidate = f"{base}_{counter}"
        return candidate

    def _find_existing_category(self, name):
        """ catid for an exact category name, model first, then database.
        Mirrors refi.py: existing names are REUSED so children still nest, never
        duplicated. Returns None if absent. """

        global model  # noqa: F824
        for it in model:
            if it.get('cid') is None and it.get('name', '').strip() == name.strip() \
                    and not it.get('delete'):
                return it['catid']
        cur = self.app.conn.cursor()
        cur.execute("select catid from code_cat where name=?", [name.strip()])
        row = cur.fetchone()
        return row[0] if row else None

    def _find_existing_code(self, name):
        """ cid for an exact code name, model first (including the
        trailing-space variant of the code/category name workaround), then database.
        Returns None if absent. """

        global model  # noqa: F824
        for it in model:
            if it.get('cid') is not None and it.get('name') in (name, name + " ") \
                    and it.get('name', '') != "":
                return it['cid']
        cur = self.app.conn.cursor()
        cur.execute("select cid from code_name where name=?", [name.strip()])
        row = cur.fetchone()
        return row[0] if row else None

    def _code_display_name(self, name):
        """  """

        global model  # noqa: F824
        for it in model:
            if it.get('cid') is None and it.get('name', '').strip() == name \
                    and not it.get('delete'):
                return name + " "
        cur = self.app.conn.cursor()
        cur.execute("select catid from code_cat where name=?", [name])
        if cur.fetchone() is not None:
            return name + " "
        return name

    def _color_for_import(self, raw_color):
        """ Map an arbitrary hex color to the closest palette color; random if absent
        or unparseable. """
        if raw_color in valid_colors:
            return raw_color
        if raw_color and isinstance(raw_color, str) and raw_color.startswith('#') \
                and len(raw_color) == 7:
            try:
                r, g, b = (int(raw_color[i:i + 2], 16) for i in (1, 3, 5))
                best, best_d = None, None
                for vc in valid_colors:
                    vr, vg, vb = (int(vc[i:i + 2], 16) for i in (1, 3, 5))
                    d = (r - vr) ** 2 + (g - vg) ** 2 + (b - vb) ** 2
                    if best_d is None or d < best_d:
                        best, best_d = vc, d
                return best
            except ValueError:
                pass
        return valid_colors[randint(0, len(valid_colors) - 1)]

    def _import_qdc_codebook(self, filepath, stats, policy='reuse'):
        """ REFI-QDA .qdc parser aligned with refi.py semantics.
        Per the standard, isCodable defaults to true; a node is a CATEGORY only when
        explicitly isCodable="false". A codable node - even with child Code elements -
        is a CODE, and its codable children become SUB-CODES (supercid), preserving
        the nested hierarchy (MAXQDA exports everything as nested codable Codes).
        Existing names are reused (their real id anchors the children), never
        duplicated. Model only; nothing is written to the database here. """

        global model  # noqa: F824
        tree = etree.parse(filepath)
        root = tree.getroot()
        codes_element = None
        for child in root:
            if isinstance(child.tag, str) and child.tag.endswith('}Codes'):
                codes_element = child
                break
        if codes_element is None:
            return

        def is_code_tag(el):
            return isinstance(el.tag, str) and el.tag.endswith('}Code')

        def parse_code_element(element, cat_id, super_cid):
            name = element.get("name")
            if name is None:
                return
            description = ""
            children = []
            for el in list(element):
                if isinstance(el.tag, str) and el.tag.endswith('}Description') and el.text:
                    description = el.text
                if is_code_tag(el):
                    children.append(el)

            # A node is a category only if explicitly non-codable (refi.py rule)
            if element.get("isCodable") == "false":
                catid = self._find_existing_category(name)
                if catid is not None and policy == 'copy':  # import as copy
                    name = self._suffixed_name(name)
                    catid = None
                if catid is None:
                    new_cat = self._new_category_entry(name, description, cat_id)
                    model.append(new_cat)
                    catid = new_cat['catid']
                    stats['cats'] += 1
                else:
                    stats['reused'] += 1
                # Children of a category attach to the category, never to a code
                for el in children:
                    parse_code_element(el, catid, None)
                return

            # Codable Code: a leaf, or a code with sub-codes
            cid = self._find_existing_code(name)
            if cid is not None and policy == 'copy':  # import as copy
                name = self._suffixed_name(name)
                cid = None
            if cid is None:
                display_name = self._code_display_name(name)
                # supercid and catid are mutually exclusive
                link_catid = cat_id if super_cid is None else None
                new_code = self._new_code_entry(
                    display_name, description, catid=link_catid, supercid=super_cid,
                    x=None, y=None, color=self._color_for_import(element.get("color")))
                model.append(new_code)
                cid = new_code['cid']
                stats['codes'] += 1
            else:
                stats['reused'] += 1
            # Child Codes of a codable code become its sub-codes (supercid)
            for el in children:
                parse_code_element(el, None, cid)

        for el in list(codes_element):
            if is_code_tag(el):
                parse_code_element(el, None, None)

    def _parse_path_rows(self, rows, stats, policy='reuse'):
        """ Shared TXT/CSV engine with refi.py-style reuse. Each row:
        (path, memo); path uses Category>>SubCategory>>Code; no >> means a free code.
        Existing category names anchor nesting via their real id; existing code
        names are skipped (reused), never duplicated. """

        global model  # noqa: F824
        for path_part, memo in rows:
            segments = [s.strip() for s in path_part.split('>>') if s.strip()]
            if not segments:
                continue
            parent_catid = None
            for i in range(len(segments) - 1):
                cat_name = segments[i]
                catid = self._find_existing_category(cat_name)
                if catid is not None and policy == 'copy':  # import as copy
                    cat_name = self._suffixed_name(cat_name)
                    catid = None
                if catid is None:
                    new_cat = self._new_category_entry(cat_name, '', parent_catid)
                    model.append(new_cat)
                    catid = new_cat['catid']
                    stats['cats'] += 1
                parent_catid = catid
            code_name = segments[-1]
            if self._find_existing_code(code_name) is not None:
                if policy != 'copy':
                    stats['reused'] += 1
                    continue
                code_name = self._suffixed_name(code_name)  # import as copy
            display_name = self._code_display_name(code_name)
            new_code = self._new_code_entry(
                display_name, memo,
                catid=parent_catid if len(segments) > 1 else None, x=None, y=None)
            model.append(new_code)
            stats['codes'] += 1

    def _read_path_rows(self, filepath):
        """ Read TXT/CSV codebook rows as (path, memo) pairs; shared by the
        collision pre-check and the importer. """

        rows = []
        if filepath.lower().endswith('.txt'):
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                for line in f.readlines():
                    line = line.rstrip('\n\r')
                    if not line.strip():
                        continue
                    parts = line.split('\t', 1)
                    memo = parts[1].strip().strip('"') if len(parts) > 1 else ""
                    if parts[0].strip():
                        rows.append((parts[0].strip(), memo))
        else:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                for row in csv.reader(f):
                    if not row or not row[0].strip():
                        continue
                    memo = row[1].strip().strip('"') if len(row) > 1 else ""
                    rows.append((row[0].strip(), memo))
        return rows

    def _import_txt_codebook(self, filepath, stats, policy='reuse'):
        """ QualCoder plain-text codebook: Category>>Code[TAB]"Memo" per line. """

        self._parse_path_rows(self._read_path_rows(filepath), stats, policy)

    def _import_csv_codebook(self, filepath, stats, policy='reuse'):
        """ CSV codebook: column 1 = Category>>Code path, column 2 = memo. """

        self._parse_path_rows(self._read_path_rows(filepath), stats, policy)

    def apply_frequency_labels(self):
        """ Show or hide coding-frequency suffixes "[n]" on every node.
        Counts reflect the hierarchy ON SCREEN (the model being organised) and are
        UNIQUE per node: a code counts its own codings plus codes already merged into
        it (never its sub-code descendants); a category totals its whole on-screen
        subtree, each coding counted exactly once.
        code_or_cat['name'] is never modified (Apply writes names to the database);
        only the displayed text carries the suffix. """

        global model  # noqa: F824
        cur = self.app.conn.cursor()
        own = {}
        for table in ('code_text', 'code_image', 'code_av'):
            cur.execute(f"select cid, count(*) from {table} group by cid")
            for cid_, n_ in cur.fetchall():
                own[cid_] = own.get(cid_, 0) + n_

        def code_own(code_item):
            base = own.get(code_item['original_cid'], 0)
            for m_ in model:
                if m_ is not code_item and m_.get('cid') == code_item['cid'] \
                        and m_.get('name') == "" and m_.get('original_cid') is not None:
                    base += own.get(m_['original_cid'], 0)
            return base

        def code_total(code_item):
            total = code_own(code_item)
            for sub in model:
                if sub.get('cid') is not None and sub.get('name') != "" \
                        and sub.get('supercid') == code_item['cid']:
                    total += code_total(sub)
            return total

        totals = {}
        for item in model:
            if item.get('name') == "":
                continue
            if item['original_cid'] is not None:
                # unique per node - own codings (plus codes already
                # merged INTO this one, which become its codings on Apply); descendant
                # sub-codes are NOT added, consistent with the graph view
                totals[('code', item['original_cid'])] = code_own(item)
        for item in model:
            if item.get('name') == "" or item['original_cid'] is not None:
                continue
            tree = descendant_catids(model, item['catid'])
            tree.add(item['catid'])
            total = 0
            for code_item in model:
                if code_item.get('cid') is not None and code_item.get('name') != "" \
                        and code_item.get('catid') in tree:
                    total += code_total(code_item)
            totals[('cat', item['original_catid'])] = total

        for gr_item in self.scene.items():
            if not isinstance(gr_item, TextGraphicsItem):
                continue
            coc = gr_item.code_or_cat
            if coc.get('name') == "":
                continue
            key = ('code', coc['original_cid']) if coc['original_cid'] is not None \
                else ('cat', coc['original_catid'])
            if self.show_frequencies and key in totals:
                gr_item.setPlainText(f"{coc['name']} [{totals[key]}]")
            else:
                gr_item.setPlainText(coc['name'])
        self.scene.update()

    def export_image(self):
        """ Export the QGraphicsScene as a PNG image with a transparent background.
        Render the exact rectangle that encloses ALL items, including
        nodes dragged to negative coordinates. The previous version sized the image from
        suggested_scene_size() with a source rect anchored at (0,0), so anything above or
        left of the origin (now possible with free dragging) was cropped. The connect
        handle is hidden and the drag preview cleared so they never appear in the file.
        The background is left transparent (alpha 0). """

        filename = "Graph.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        # Hide the blue connect handle(s) and clear any preview so they are not exported.
        hidden_handles = []
        for it in self.scene.items():
            if isinstance(it, ConnectionHandleItem) and it.isVisible():
                it.setVisible(False)
                hidden_handles.append(it)
        self.scene.clear_connection_preview()

        # Tight bounds of the real content (nodes + links, arrowheads included), ignoring
        # the handles; works with negative coordinates.
        content = [it for it in self.scene.items()
                   if isinstance(it, (TextGraphicsItem, LinkGraphicsItem))]
        if not content:
            for it in hidden_handles:
                it.setVisible(True)
            Message(self.app, _("Code organiser"), _("Nothing to export.")).exec()
            return
        rect = content[0].sceneBoundingRect()
        for it in content[1:]:
            rect = rect.united(it.sceneBoundingRect())
        margin = 20
        rect.adjust(-margin, -margin, margin, margin)

        image = QtGui.QImage(max(1, int(rect.width())), max(1, int(rect.height())),
                             QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.transparent)  # transparent background
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # painter, target area (whole image), source area (scene rect, may be negative)
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect)
        painter.end()
        image.save(filepath)

        for it in hidden_handles:  # restore the handle on the still-selected node
            it.setVisible(True)
        Message(self.app, _("Image exported"), filepath).exec()

    def build_pending_changes(self):
        """ Derive the list of pending operations by comparing the current
        model against the snapshot taken when the branch was selected. Returns a list
        of human-readable strings (also written to the project journal on Apply). """

        global model  # noqa: F824
        snapshot = getattr(self, '_initial_model', {})

        def cat_name(catid):
            if catid is None:
                return _("(no category)")
            for it in model:
                if it.get('cid') is None and it.get('catid') == catid and it.get('name') != "":
                    return it['name'].strip()
            snap = snapshot.get(('cat', catid))
            if snap:
                return snap['name'].strip()
            return f"catid {catid}"

        def code_name(cid):
            if cid is None:
                return _("(none)")
            for it in model:
                if it.get('cid') == cid and it.get('name') != "":
                    return it['name'].strip()
            snap = snapshot.get(('code', cid))
            if snap:
                return snap['name'].strip()
            return f"cid {cid}"

        changes = []
        for item in model:
            is_code = item['original_cid'] is not None
            key = ('code', item['original_cid']) if is_code else ('cat', item['original_catid'])
            snap = snapshot.get(key)
            # New categories (ignore nameless merged-away new ones)
            if snap is None:
                if not is_code and item.get('name') != "" and not item.get('delete'):
                    parent = cat_name(item.get('supercatid')) if item.get('supercatid') is not None else _("top level")
                    changes.append(_("New category: ") + f"'{item['name'].strip()}' ({parent})")
                elif is_code and item.get('name') != "":  # new codes
                    if item.get('supercid') is not None:
                        location = _("sub-code of ") + f"'{code_name(item['supercid'])}'"
                    elif item.get('catid') is not None:
                        location = _("in category ") + f"'{cat_name(item['catid'])}'"
                    else:
                        location = _("unlinked")
                    changes.append(_("New code: ") + f"'{item['name'].strip()}' ({location})")
                continue
            # Merges
            if item.get('delete') and not is_code:
                target = cat_name(item.get('merged_into_catid'))
                changes.append(_("Category merged: ") + f"'{snap['name'].strip()}' → '{target}'")
                continue
            if is_code and item.get('name') == "":
                changes.append(_("Code merged: ") + f"'{snap['name'].strip()}' → '{code_name(item['cid'])}'")
                continue
            # Renames
            if item['name'] != snap['name']:
                changes.append(_("Renamed: ") + f"'{snap['name'].strip()}' → '{item['name'].strip()}'")
            # Memo edits
            if item['memo'] != snap['memo']:
                changes.append(_("Memo updated: ") + f"'{item['name'].strip()}'")
            # Re-parenting. report ONE line describing the move, using the
            # correct wording for each parent type (a category's parent is "top level",
            # not "(no category)"), and folding a code's catid + supercid change (e.g.
            # category -> sub-code) into a single message instead of two.
            if is_code:
                def code_location(catid_, supercid_):
                    if supercid_ is not None:
                        return _("sub-code of ") + f"'{code_name(supercid_)}'"
                    if catid_ is not None:
                        return _("category ") + f"'{cat_name(catid_)}'"
                    return _("top level")
                old_loc = code_location(snap['catid'], snap.get('supercid'))
                new_loc = code_location(item['catid'], item.get('supercid'))
                if old_loc != new_loc:
                    changes.append(_("Code ") + f"'{item['name'].strip()}': " + old_loc + " → " + new_loc)
            else:
                def cat_location(supercatid_):
                    if supercatid_ is not None:
                        return _("under ") + f"'{cat_name(supercatid_)}'"
                    return _("top level")
                old_loc = cat_location(snap['supercatid'])
                new_loc = cat_location(item['supercatid'])
                if old_loc != new_loc:
                    changes.append(_("Category ") + f"'{item['name'].strip()}': " + old_loc + " → " + new_loc)
        return changes

    def confirm_changes_dialog(self, changes):
        """ Preview dialog listing the pending operations before anything is
        written to the database. Returns True to proceed. """

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(_("Apply changes to code tree"))
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel(
            _("The following changes will be applied to the database:")))
        text_edit = QtWidgets.QPlainTextEdit("\n".join(f"• {c}" for c in changes))
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Apply |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(620, 420)
        return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted

    def apply_model_changes(self):
        """ Apply changes to database from model.
        Shows a change preview first; runs as ONE transaction (any
        failure rolls everything back, no half-applied tree); writes the applied
        operations to the project journal; emits the project event bus so open
        dialogs (graph, reports) resynchronise. SQL logic itself is unchanged. """

        global model  # noqa: F824
        changes = self.build_pending_changes()
        if not changes:
            Message(self.app, _("Code organiser"), _("No changes to apply.")).exec()
            return
        if not self.confirm_changes_dialog(changes):
            return
        code_merges_present = any(
            item['cid'] is not None and item['name'] == "" for item in model)

        # Merged new categories are not used. They are nameless. Remove from model.
        merged_new_categories = []
        for item in model:
            if item['catid'] is not None and item['catid'] < 0 and item['cid'] is None and item['name'] == "":
                merged_new_categories.append(item)
        for item in merged_new_categories:
            model.remove(item)
        # New categories to insert into database
        new_categories = []
        for item in model:
            if item['catid'] is not None and item['catid'] < 0 and item['cid'] is None:
                new_categories.append(item)
        cur = self.app.conn.cursor()
        try:
            # Insert new categories, update links to codes and pre-existing categories
            for category in new_categories:
                model.remove(category)
                try:
                    cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                                (category['name'], category['memo'], category['owner'], category['date'],
                                 category['supercatid']))
                except sqlite3.IntegrityError:
                    # previously logged and continued with a corrupt
                    # insert_id; now the whole transaction aborts cleanly.
                    raise ValueError(_("Category name already in use: ") + category['name'])
                cur.execute("select last_insert_rowid()")
                category['insert_id'] = cur.fetchone()[0]
                logger.debug(f"New category insert {category['name']} {category['catid']} "
                             f"-> {category['insert_id']}")
                # Update remaining model code catids and pre-existing category supercatids
                for model_item in model:
                    if model_item['catid'] == category['catid']:
                        model_item['catid'] = category['insert_id']
                    if model_item['supercatid'] == category['catid']:
                        model_item['supercatid'] = category['insert_id']

            # Delete pre-existing categories from database, if merged into other categories
            categories_to_delete = []
            for item in model:
                if item['delete'] is True and item['cid'] is None:
                    categories_to_delete.append(item)
            for item in categories_to_delete:
                model.remove(item)
            for item in categories_to_delete:
                logger.debug(f"Category to delete {item['original_name']} {item['catid']}")
                cur.execute("delete from code_cat where catid=?", [item['catid']])

            # Get inserted new categories where supercatid is < 0 and update with insert_id
            cur.execute("select catid, supercatid, name from code_cat where supercatid < 0")
            res = cur.fetchall()
            for category_to_update in res:
                for new_category in new_categories:
                    if category_to_update[1] == new_category['catid']:
                        cur.execute("update code_cat set supercatid=? where catid=?",
                                    [new_category['insert_id'], category_to_update[0]])

            # insert NEW codes (temporary negative cid). Their catid values
            # were already remapped by the new-category pass above; supercid is written
            # by the general update pass below, once this remap fixes the ids.
            new_codes = [it for it in model
                         if it.get('cid') is not None and it['cid'] < 0 and it.get('name', '') != ""]
            for code in new_codes:
                code_name_ = code['name']
                if code_name_[-1] == " ":
                    code_name_ = code_name_[:-1]
                try:
                    cur.execute("insert into code_name (name, memo, owner, date, catid, color) "
                                "values(?,?,?,?,?,?)",
                                (code_name_, code.get('memo', ''), code.get('owner', ''),
                                 code.get('date', ''), code['catid'], code.get('color', '#999999')))
                except sqlite3.IntegrityError:
                    raise ValueError(_("Code name already in use: ") + code_name_)
                cur.execute("select last_insert_rowid()")
                insert_id = cur.fetchone()[0]
                logger.debug(f"New code insert {code_name_} {code['cid']} -> {insert_id}")
                old_cid = code['cid']
                for model_item in model:
                    if model_item.get('cid') == old_cid:
                        model_item['cid'] = insert_id  # includes merge targets
                    if model_item.get('supercid') == old_cid:
                        model_item['supercid'] = insert_id
                    if model_item.get('original_supercid') == old_cid:
                        model_item['original_supercid'] = insert_id
                    if model_item.get('original_cid') == old_cid:
                        model_item['original_cid'] = insert_id

            # Update codes and categories in model - catid, supercatid, name, memo
            for item in model:
                # Update pre-existing categories
                if item['catid'] is not None and item['cid'] is None:
                    cur.execute("update code_cat set name=?, memo=?, supercatid=? where catid=?",
                                [item['name'], item['memo'], item['supercatid'], item['catid']])
                # Update codes, but avoid merged codes which are nameless
                if item['cid'] is not None and item['name'] != "":
                    # A space was added to differentiate matching code - category names
                    code_name = item['name']
                    if item['name'][-1] == " ":
                        code_name = item['name'][:-1]
                    # Keep sub-code nesting consistent: a code in a category cannot also be a
                    # sub-code. If it has a category now, clear supercid; otherwise preserve the
                    # code's existing parent code (supercid).
                    new_supercid = None if item['catid'] is not None else item.get('original_supercid')
                    cur.execute("update code_name set name=?, memo=?, catid=?, supercid=? where cid=?",
                                [code_name, item['memo'], item['catid'], new_supercid, item['cid']])

            # Update merged codes: coded text, images and A/V. Using new cid and original_cid
            for item in model:
                if item['cid'] is not None and item['name'] == "":
                    logger.debug(f"Merging code: {item['original_name']} into {item['cid']}")
                    self.update_merged_coded_segments(item['original_cid'], item['cid'])

            # An extra check. Fix 'lost' categories if present.
            sql = "update code_cat set supercatid=null where supercatid is not null and supercatid not in " \
                  "(select catid from code_cat)"
            cur.execute(sql)

            # Repair dangling and cyclic supercid (mirrors project-open repair)
            # Needed mainly after merging a PARENT code: its sub-codes would otherwise
            # keep a supercid pointing at the deleted code until the next project open.
            # Kept inside this transaction (no intermediate commit) so Apply stays atomic
            cur.execute("update code_name set supercid=null where supercid is not null and supercid not in "
                        "(select cid from code_name)")  # dangling parent / padre borrado
            cur.execute("update code_name set catid=null where supercid is not null and catid is not null")  # supercid wins
            cur.execute("select cid, supercid from code_name")  # break cycles / romper ciclos
            code_parent = {row[0]: row[1] for row in cur.fetchall()}
            for start in list(code_parent.keys()):
                seen = set()
                node = start
                while node is not None and node in code_parent:
                    if node in seen:
                        cur.execute("update code_name set supercid=null where cid=?", [node])
                        code_parent[node] = None
                        break
                    seen.add(node)
                    node = code_parent[node]

            # write the applied operations to the project journal (audit trail)
            now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            jentry = _("Code organiser - applied changes:") + "\n" + "\n".join(changes)
            cur.execute("insert into journal (name, jentry, owner, date) values (?,?,?,?)",
                        [_("Code organiser ") + now_date, jentry,
                         self.app.settings['codername'], now_date])

            self.app.conn.commit()  # single transaction commit
        except Exception as e_:
            self.app.conn.rollback()  # nothing half-applied
            logger.error(f"Code organiser apply failed, rolled back: {e_}")
            Message(self.app, _("Code organiser"),
                    _("Applying changes failed. Nothing was changed.") + f"\n{e_}", "warning").exec()
            return

        # notify the project event bus so the graph and reports resync live
        if self.app.project_events is not None:
            tables = ['code_cat', 'code_name']
            if code_merges_present:
                tables += ['code_text', 'code_image', 'code_av']
            self.app.project_events.emit_table_changes(tables, source=self)

        # Wrap up
        self.app.delete_backup = False
        self.parent_text_edit.append(_("Code tree re-organised."))
        self.hide()
        Message(self.app, _("Code organiser"), _("Changes applied to the codes tree")).exec()

    def update_merged_coded_segments(self, old_cid, new_cid):
        """ Update cid for each coded segment in text, A/V, image.
        Delete where there is a duplicate Integrity error.
        """

        cur = self.app.conn.cursor()
        ct_sql = "select ctid from code_text where cid=?"
        cur.execute(ct_sql, [old_cid])
        ct_res = cur.fetchall()
        for ct in ct_res:
            try:
                cur.execute("update code_text set cid=? where ctid=?", [new_cid, ct[0]])
            except sqlite3.IntegrityError as e_:
                # print(ct, e_)
                cur.execute("delete from code_text where ctid=?", [ct[0]])
        av_sql = "select avid from code_av where cid=?"
        cur.execute(av_sql, [old_cid])
        av_res = cur.fetchall()
        for av in av_res:
            try:
                cur.execute("update code_av set cid=? where avid=?", [new_cid, av[0]])
            except sqlite3.IntegrityError as e_:
                # print(e_)
                cur.execute("delete from code_av where avid=?", [av[0]])
        img_sql = "select imid from code_image where cid=?"
        cur.execute(img_sql, [old_cid])
        img_res = cur.fetchall()
        for img in img_res:
            try:
                cur.execute("update code_image set cid=? where imid=?", [new_cid, img[0]])
            except sqlite3.IntegrityError as e_:
                # print(e_)
                cur.execute("delete from code_image where imid=?", [img[0]])
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        # no commit here; runs inside apply_model_changes' transaction


class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    scene_width = 990
    scene_height = 650
    parent = None

    def __init__(self, parent=None):
        super(GraphicsScene, self).__init__(parent)
        self.parent = parent
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))
        self._preview_source = None  # drag-to-connect preview line
        self._preview_pos = None

    def set_connection_preview(self, source_item, mouse_scene_pos):
        """ Show the dashed line from the source node to the cursor. """
        self._preview_source = source_item
        self._preview_pos = mouse_scene_pos
        self.update()

    def clear_connection_preview(self):
        """ Remove the dashed preview line. """
        self._preview_source = None
        self._preview_pos = None
        self.update()

    def drawForeground(self, painter, rect):
        """ Paint the dashed connection preview (no scene item, never persists). """
        super().drawForeground(painter, rect)
        source = getattr(self, '_preview_source', None)
        pos = getattr(self, '_preview_pos', None)
        if source is None or pos is None:
            return
        try:
            p1 = source.sceneBoundingRect().center()
        except RuntimeError:
            return
        pen = QtGui.QPen(QtGui.QColor(self._link_color()), 2, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(p1, pos)

    def _link_color(self):
        """ theme-aware hierarchy line colour. The default gray is nearly
        invisible on the dark themes, so use a light gray there (and on any native
        theme whose base colour is dark). """
        try:
            sheet = self.parent.app.settings.get('stylesheet', 'original')
        except Exception:
            sheet = 'original'
        if sheet in ('dark', 'rainbow'):
            return '#b0b0b0'
        if sheet == 'native':
            try:
                base = QtWidgets.QApplication.instance().palette().color(
                    QtGui.QPalette.ColorRole.Base)
                if base.lightness() < 128:
                    return '#b0b0b0'
            except Exception:
                pass
        return '#555555'

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

    def named_children_of_node(self, node):
        """ Get names of child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.
        All category and code names are unique.

        param: node : Dictionary of category

        return: child_names : List
        """

        global model  # noqa: F824
        if node['cid'] is not None:
            # A code may have sub-codes (supercid); return descendant sub-code names so
            # they move together with the parent code when it is dragged.
            child_names = []
            frontier = [node['cid']]
            guard = 0
            while frontier and guard < 1000:
                guard += 1
                current = frontier.pop()
                for m_item in model:
                    if m_item.get('cid') is not None and m_item.get('supercid') == current \
                            and m_item['name'] not in child_names:
                        child_names.append(m_item['name'])
                        frontier.append(m_item['cid'])
            return child_names
        child_names = []
        codes_ = []
        categories_ = []
        model_copy = deepcopy(model)
        for item in model_copy:
            if item['cid'] is None:
                categories_.append(item)
            else:
                codes_.append(item)

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories_ != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for sel_category in selected_categories:
                for m in categories_:
                    if m['supercatid'] == sel_category['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for append_item in append_list:
                selected_categories.append(append_item)
                categories_.remove(append_item)
                new_model_changed = True
            i += 1
        categories_ = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for category in categories_:
            for code in codes_:
                if code['catid'] == category['catid']:
                    selected_codes.append(code)
        codes_ = selected_codes
        for code_ in codes_:
            child_names.append(code_['name'])
        return child_names

    def mouseMoveEvent(self, mouse_event):
        """ On mouse move, an item might be repositioned so need to redraw all the link_items.
        This slows re-drawing down, but is dynamic.
        """

        # this propagated the move as mousePressEvent (long-standing
        # typo) which broke smooth native dragging and multi-selection moves.
        super(GraphicsScene, self).mouseMoveEvent(mouse_event)

        # Garbage items for removal
        for item in self.items():
            if isinstance(item, TextGraphicsItem) and item.code_or_cat['name'] == "":
                self.removeItem(item)
        # Update code.catid or category.supercatid if a category has been merged into another category
        global model  # noqa: F824
        global update_graphics_item_models  # noqa: F824
        if update_graphics_item_models:
            for m_item in model:
                if m_item['original_cid'] is None:
                    m_item['child_names'] = self.named_children_of_node(m_item)
            for gr_item in self.items():
                if isinstance(gr_item, TextGraphicsItem):
                    for m_item in model:
                        # Update graphics codes items
                        if gr_item.code_or_cat['original_cid'] is not None and \
                                gr_item.code_or_cat['original_cid'] == m_item['original_cid']:
                            gr_item.code_or_cat = m_item
                            gr_item.set_text()
                        # Update graphics categories items
                        if gr_item.code_or_cat['original_cid'] is None and \
                                gr_item.code_or_cat['original_catid'] == m_item['original_catid']:
                            gr_item.set_text()
            # set_text above wipes the "[n]" suffixes; reapply them
            if self.parent is not None and getattr(self.parent, 'show_frequencies', False):
                self.parent.apply_frequency_labels()

        # independent node movement. Qt natively moves the dragged
        # node (or the whole selection); here we only keep the stored model x/y in
        # sync. Children no longer follow their parent automatically: to move a
        # branch, select it with the rubber band (or Ctrl+click) and drag the group.
        for item in self.items():
            if isinstance(item, TextGraphicsItem):
                if item.code_or_cat['x'] != item.pos().x() or item.code_or_cat['y'] != item.pos().y():
                    item.code_or_cat['x'] = item.pos().x()
                    item.code_or_cat['y'] = item.pos().y()

        # canvas fluidity. Destroying and recreating every line on each
        # mouse move caused flicker and lag; existing lines are now just redrawn, and
        # full recreation happens only when the model structure changed.
        if update_graphics_item_models:
            self.remove_links()
            self.create_links()
            update_graphics_item_models = False  # processed; avoid perpetual rebuilds
        else:
            for item in self.items():
                if isinstance(item, LinkGraphicsItem):
                    item.redraw()
        # match view_graph exactly. During a drag NOTHING about the scene
        # rect changes, so the viewport never follows the node: only the dragged item
        # moves. The scene rect is grown (never re-anchored or shrunk) on drop, in
        # mouseReleaseEvent. The old adjust/suggested/update_scene_bounds calls here made
        # the whole canvas track the item.
        self.update()

    '''def mousePressEvent(self, mouseEvent):
    super(GraphicsScene, self).mousePressEvent(mouseEvent)
    #position = QtCore.QPointF(event.scenePos())
    #logger.debug("pressed here: " + str(position.x()) + ", " + str(position.y()))
    for item in self.items(): # item is QGraphicsProxyWidget
        if isinstance(item, LinkItem):
            item.redraw()
    self.update(self.sceneRect())'''

    def mouseReleaseEvent(self, mouse_event):
        """ On drop, GROW the scene rect only if a node was dragged outside it
        (clamped) so it stays reachable. Ported in spirit from view_graph: the rect is
        never re-anchored or shrunk, so the view does not jump. """
        super(GraphicsScene, self).mouseReleaseEvent(mouse_event)
        self._grow_scene_rect_to_items()
        for item in self.items():
            if isinstance(item, LinkGraphicsItem):
                item.redraw()
        self.update()

    def _grow_scene_rect_to_items(self):
        """grow-only scene rect update (never shrink / re-anchor), clamped. """
        items_rect = self.itemsBoundingRect()
        if items_rect.isEmpty():
            return
        current = self.sceneRect()
        items_rect.adjust(-100, -100, 100, 100)
        if current.contains(items_rect):
            return
        max_scene = 50000
        candidate = current.united(items_rect)
        if candidate.width() > max_scene:
            candidate.setWidth(max_scene)
        if candidate.height() > max_scene:
            candidate.setHeight(max_scene)
        self.setSceneRect(candidate)
        self.scene_width = candidate.width()
        self.scene_height = candidate.height()

    def remove_links(self):
        """ Clean up by removing all links and points. """

        for scene_item in self.items():
            # PointGraphicsItem end markers removed (obsolete with
            # the perimeter line geometry)
            if isinstance(scene_item, LinkGraphicsItem):
                self.removeItem(scene_item)

    def create_links(self):
        """ Add links from Codes to Categories. And Categories to categories. """

        link_color = self._link_color()  # theme-aware, visible on dark themes
        # Link from code to category
        for cat_item in self.items():
            if isinstance(cat_item, TextGraphicsItem):
                for code_item in self.items():
                    if isinstance(code_item, TextGraphicsItem) and code_item.code_or_cat['cid'] is not None and \
                            cat_item.code_or_cat['cid'] is None and \
                            cat_item.code_or_cat['catid'] == code_item.code_or_cat['catid']:
                        link_item = LinkGraphicsItem(cat_item, code_item, color=link_color)
                        self.addItem(link_item)

        # Link from Category to Category
        for item1 in self.items():
            if isinstance(item1, TextGraphicsItem):
                for item2 in self.items():
                    if isinstance(item2, TextGraphicsItem) and item1.code_or_cat['supercatid'] is not None and \
                            item1.code_or_cat['supercatid'] == item2.code_or_cat['catid'] and \
                            (item1.code_or_cat['cid'] is None and item2.code_or_cat['cid'] is None):
                        item = LinkGraphicsItem(item2, item1, color=link_color)
                        if item1.isVisible() and item2.isVisible():
                            self.addItem(item)

        # Link from parent code to sub-code (supercid). Parent -> child.
        for parent_item in self.items():
            if isinstance(parent_item, TextGraphicsItem):
                for child_item in self.items():
                    if isinstance(child_item, TextGraphicsItem) and \
                            child_item.code_or_cat.get('cid') is not None and \
                            child_item.code_or_cat.get('supercid') is not None and \
                            child_item.code_or_cat.get('catid') is None and \
                            parent_item.code_or_cat.get('cid') is not None and \
                            child_item.code_or_cat['supercid'] == parent_item.code_or_cat['cid']:
                        link_item = LinkGraphicsItem(parent_item, child_item, color=link_color)
                        if parent_item.isVisible() and child_item.isVisible():
                            self.addItem(link_item)

    def update_scene_bounds(self):
        """
        Set the scene rect to the items bounding rect plus a GENEROUS margin
        for free panning (mirrors view_graph.suggested_scene_size). Used for the initial
        layout only; during a drag the rect is left alone (see mouseMoveEvent) and only
        grown on drop (see mouseReleaseEvent), so the viewport never follows the node. 
        """
        rect = self.itemsBoundingRect()
        if rect.isEmpty():
            self.setSceneRect(0, 0, self.scene_width, self.scene_height)
            return
        rect.adjust(-600, -600, 600, 600)
        self.scene_width = rect.width()
        self.scene_height = rect.height()
        self.setSceneRect(rect)

    def adjust_for_negative_positions(self):
        """ Move all items if negative positions. """

        min_adjust_x = 0
        min_adjust_y = 0
        for i in self.items():
            if i.pos().x() < min_adjust_x:
                min_adjust_x = i.pos().x()
            # was compared against min_adjust_x (typo), so the y
            # adjustment almost never triggered correctly
            if i.pos().y() < min_adjust_y:
                min_adjust_y = i.pos().y()
        if min_adjust_x < 0 or min_adjust_y < 0:
            for i in self.items():
                if not isinstance(i, LinkGraphicsItem):
                    i.setPos(i.pos().x() - min_adjust_x, i.pos().y() - min_adjust_y)
                    # keep the stored model position in sync, otherwise the
                    # next mouseMoveEvent sees every item as "moved" and drags all
                    # children again by the adjustment delta (cascading double moves)
                    if isinstance(i, TextGraphicsItem):
                        i.code_or_cat['x'] = i.pos().x()
                        i.code_or_cat['y'] = i.pos().y()

    def suggested_scene_size(self):
        """ Calculate the maximum width and height from the current Items. """

        max_x = 0
        max_y = 0
        for i in self.items():
            if isinstance(i, TextGraphicsItem):
                if i.pos().x() + i.boundingRect().width() > max_x:
                    max_x = i.pos().x() + i.boundingRect().width()
                if i.pos().y() + i.boundingRect().height() > max_y:
                    max_y = i.pos().y() + i.boundingRect().height()
        self.setSceneRect(0, 0, max_x, max_y)
        return max_x, max_y


class TextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item show the name and color of the code or category
    Categories are shown white. A custom context menu
    allows selection of a code/category memo and displaying the information.
    """

    code_or_cat = None
    border_rect = None
    app = None
    settings = None

    def __init__(self, app, code_or_cat):
        """ Show name and colour of text. Has context menu for various options.
         :param: app  : the main App class
         :param: code_or_cat  : Dictionary of the code details: name, memo, color etc
         """

        super(TextGraphicsItem, self).__init__(None)
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.code_or_cat = code_or_cat
        self.setPos(self.code_or_cat['x'], self.code_or_cat['y'])
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        self.setDefaultTextColor(QtGui.QColor(TextColor(self.code_or_cat['color']).recommendation))
        # categories in bold, consistent with the graph view
        weight = QtGui.QFont.Weight.Bold if self.code_or_cat.get('cid') is None \
            else QtGui.QFont.Weight.Normal
        self.setFont(QtGui.QFont(self.settings['font'], 9, weight))
        self.setToolTip(self.code_or_cat['memo'])
        self.text = self.code_or_cat['name']
        if self.app.settings['showids']:
            self.text += "\n"
            if self.code_or_cat['cid'] is not None:
                self.text += f"catid[{self.code_or_cat['catid']}] cid[{self.code_or_cat['cid']}]"
            if self.code_or_cat['cid'] is None:
                self.text += f"catid[{self.code_or_cat['catid']}]"
                self.text += f" supercatid[{self.code_or_cat['supercatid']}]"
        self.set_text()

    def set_text(self):
        """ Set viewable text """

        self.setPlainText(self.text)

    def paint(self, painter, option, widget):
        """  """

        painter.save()
        color = QtGui.QColor(self.code_or_cat['color'])
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
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        # every action variable initialised once (the dispatch below
        # compares against all of them regardless of node type)
        show_memo_action = None
        coded_action = None
        case_action = None
        link_code_to_category_action = None
        link_code_under_code_action = None
        remove_code_from_parent_code_action = None
        merge_code_into_code_action = None
        remove_code_from_category_action = None
        link_category_under_category_action = None
        merge_category_into_category_action = None
        remove_category_from_category_action = None
        add_code_action = None
        add_sub_code_action = None
        if self.code_or_cat['cid'] is not None:
            link_code_to_category_action = menu.addAction(_('Link code to category'))
            link_code_under_code_action = menu.addAction(_('Link code under code'))
            merge_code_into_code_action = menu.addAction(_('Merge code into code'))
            if self.code_or_cat['catid'] is not None:
                remove_code_from_category_action = menu.addAction(_('Remove code from category'))
            if self.code_or_cat.get('supercid') is not None:
                remove_code_from_parent_code_action = menu.addAction(_('Remove code from parent code'))
            add_sub_code_action = menu.addAction(_('Add sub-code'))
            coded_action = menu.addAction(_('Coded text and media'))
            case_action = menu.addAction(_('Case text and media'))
        if self.code_or_cat['cid'] is None:
            link_category_under_category_action = menu.addAction(_('Link category under category'))
            merge_category_into_category_action = menu.addAction(_('Merge category into category'))
            if self.code_or_cat['supercatid'] is not None:
                remove_category_from_category_action = menu.addAction(_('Remove category from category'))
            add_code_action = menu.addAction(_('Add code to category'))
        memo_action = menu.addAction(_('Memo'))
        rename_action = menu.addAction(_('Rename'))
        if self.code_or_cat['memo'] != "":
            show_memo_action = menu.addAction(_("Display memo"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == show_memo_action:
            self.text = self.code_or_cat['name']
            if self.app.settings['showids']:
                self.text += "\n"
                if self.code_or_cat['cid'] is not None:
                    self.text += f"catid[{self.code_or_cat['catid']}] cid[{self.code_or_cat['cid']}]"
                if self.code_or_cat['cid'] is None:
                    self.text += f"catid[{self.code_or_cat['catid']}]"
                    self.text += f" supercatid[{self.code_or_cat['supercatid']}]"
            self.text += f"\nMEMO: {self.code_or_cat['memo']}"
            self.set_text()
        if action == memo_action:
            self.update_memo()
        if action == rename_action:
            self.update_name()
        # Codes
        if action == coded_action:
            self.coded_media()
        if action == case_action:
            self.case_media()
        if action == link_code_to_category_action:
            self.link_code_to_category()
        if action == link_code_under_code_action:
            self.link_code_under_code()
        if action == remove_code_from_parent_code_action:
            self.remove_code_from_parent_code()
        if action == merge_code_into_code_action:
            self.merge_code_into_code()
        if action == remove_code_from_category_action:
            self.remove_code_from_category()
        # Categories
        if action == link_category_under_category_action:
            self.link_category_under_category()
        if action == merge_category_into_category_action:
            self.merge_category_into_category()
        if action == remove_category_from_category_action:
            self.remove_category_from_category()
        if action == add_code_action:
            self.add_code_to_category()
        if action == add_sub_code_action:
            self.add_sub_code()

    def update_name(self):
        """ Update name of code or category.
        Do not use allow use of any existing names, as these are also used for determining
         sub_categories, sub_codes of a node. """

        existing_names = []
        global model  # noqa: F824
        for item in model:
            existing_names.append({'name': item['name']})

        ui = DialogAddItemName(self.app, existing_names, _("Update name"), _("Name"))
        ui.ui.lineEdit.setText(self.code_or_cat['name'])
        ok = ui.exec()
        if not ok:
            return
        name = ui.get_new_name()
        if name is None:
            return False
        self.code_or_cat['name'] = name
        self.text = name
        self.set_text()
        for item in model:
            if item['cid'] == self.code_or_cat['cid'] and item['catid'] == self.code_or_cat['catid']:
                item['name'] = name
                break
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def update_memo(self):
        """ Add or edit memos for codes and categories. """

        ui = DialogMemo(self.app, "Memo for Code " + self.code_or_cat['name'], self.code_or_cat['memo'])
        ok = ui.exec()
        if not ok:
            return
        self.code_or_cat['memo'] = ui.memo
        self.setToolTip(ui.memo)
        for item in model:
            if item['cid'] == self.code_or_cat['cid'] and item['catid'] == self.code_or_cat['catid']:
                item['memo'] = ui.memo
                break
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def link_code_to_category(self):
        """ Link selected code to selected category. """

        categories_ = []
        global model  # noqa: F824
        for item in model:
            if item['cid'] is None and item['name'] != "":
                categories_.append(item)
        ui = DialogSelectItems(self.app, categories_, _('Link code: Select category'), 'single')
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        if not category:
            return
        for item in model:
            if item['cid'] == self.code_or_cat['cid']:
                item['catid'] = category['catid']
                # exclusivity. A code linked to a category cannot remain a
                # sub-code; without this the model kept BOTH parents and the canvas
                # drew the old parent-code line alongside the new category line.
                item['supercid'] = None
                break
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True
        self.code_or_cat['catid'] = category['catid']
        self.code_or_cat['supercid'] = None  # exclusivity (see above)

    def link_code_under_code(self):
        """ Nest this code under another code as a sub-code (supercid).
         Uses child_names to prevent circular nesting. """

        codes_ = []
        global model  # noqa: F824
        # circular-nesting check by ids, not names
        blocked_cids = descendant_cids(model, self.code_or_cat['cid'])
        for item in model:
            if item['cid'] is not None and item['cid'] != self.code_or_cat['cid'] and item['name'] != "" \
                    and item['cid'] not in blocked_cids:
                codes_.append(item)
        codes_ = sorted(codes_, key=lambda d: d['name'])
        ui = DialogSelectItems(self.app, codes_, _('Nest under: Select parent code'), 'single')
        ok = ui.exec()
        if not ok:
            return
        parent_code = ui.get_selected()
        if not parent_code:
            return
        self.code_or_cat['supercid'] = parent_code['cid']
        self.code_or_cat['original_supercid'] = parent_code['cid']
        self.code_or_cat['catid'] = None
        self.code_or_cat['supercatid'] = None
        for item in model:
            if item['cid'] == self.code_or_cat['cid']:
                item['supercid'] = parent_code['cid']
                item['original_supercid'] = parent_code['cid']
                item['catid'] = None
                item['supercatid'] = None
                break
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def remove_code_from_parent_code(self):
        """ Detach this sub-code from its parent code, making it a top level code. """

        self.code_or_cat['supercid'] = None
        self.code_or_cat['original_supercid'] = None
        global model  # noqa: F824
        for item in model:
            if item['cid'] == self.code_or_cat['cid']:
                item['supercid'] = None
                item['original_supercid'] = None
                break
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def merge_code_into_code(self):
        """ Merge code into another code.
         Keep nameless code in model. """

        unsorted_codes = []
        global model  # noqa: F824
        for item in model:
            if item['cid'] is not None and item['cid'] != self.code_or_cat['cid'] and item['name'] != "":
                unsorted_codes.append(item)
        # Sort codes alphabetically
        codes = sorted(unsorted_codes, key=lambda d: d['name'])
        ui = DialogSelectItems(self.app, codes, _('Merge into: Select code'), 'single')
        ok = ui.exec()
        if not ok:
            return
        merge_code = ui.get_selected()
        if not merge_code:
            return
        # merge memos; the merged code's memo is appended to the target's
        merged_memo = self.code_or_cat.get('memo', '')
        if merged_memo:
            for item in model:
                if item.get('cid') == merge_code['cid'] and item.get('name', '') != "":
                    prefix = (item['memo'] + "\n") if item.get('memo') else ""
                    item['memo'] = prefix + _("Merged from code ") \
                        + f"'{self.code_or_cat['name'].strip()}': " + merged_memo
                    break
        placeholder_cid = self.code_or_cat['cid']
        # When a PARENT code is merged, move its sub-codes to the merge target
        # so the hierarchy is preserved (previously they were left dangling and the
        # project-open / apply repair silently detached them to the top level). Done
        # before the cid rewrite below, keyed on the parent's original cid.
        for item in model:
            if item.get('cid') is not None and item.get('supercid') == placeholder_cid:
                item['supercid'] = merge_code['cid']
                item['original_supercid'] = merge_code['cid']
        # Multiple codes can be affected.
        # e.g. code1 merged into code2. Then code2 merged into code3/
        for item in model:
            if item['cid'] == placeholder_cid: #self.code_or_cat['cid']:
                item['cid'] = merge_code['cid']
                item['name'] = ""

        self.code_or_cat['cid'] = merge_code['cid']
        self.code_or_cat['name'] = ""
        self.hide()
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def remove_code_from_category(self):
        """ Remove code from category as top level item. """

        self.code_or_cat['catid'] = None
        global model  # noqa: F824
        for item in model:
            if item['cid'] == self.code_or_cat['cid']:
                item['catid'] = None
                break
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def add_code_to_category(self):
        """
        Create a new code directly under this category. Model only;
        the database is written on Apply, inside its single transaction
        """

        dialog = self.scene().parent  # CodeOrganiser; GraphicsScene(self) in __init__
        if dialog is None:
            return
        global model  # noqa: F824
        ui = DialogAddItemName(dialog.app, dialog._collect_existing_item_names(),
                               _("Code"), _("Code name"))
        ui.exec()
        new_code_name = ui.get_new_name()
        if new_code_name is None:
            return
        new_code = dialog._new_code_entry(
            new_code_name, "", catid=self.code_or_cat['catid'],
            x=self.pos().x() + 150, y=self.pos().y() + 40)
        model.append(new_code)
        self.scene().addItem(TextGraphicsItem(self.app, new_code))
        self.scene().remove_links()
        self.scene().create_links()
        dialog._lock_branch_selection()

    def add_sub_code(self):
        """
        Create a new code nested under this code (supercid). Model
        only; written to the database on Apply, inside its single transaction
        """

        dialog = self.scene().parent
        if dialog is None:
            return
        global model  # noqa: F824
        ui = DialogAddItemName(dialog.app, dialog._collect_existing_item_names(),
                               _("Sub-code"), _("Sub-code name"))
        ui.exec()
        new_code_name = ui.get_new_name()
        if new_code_name is None:
            return
        new_code = dialog._new_code_entry(
            new_code_name, "", supercid=self.code_or_cat['cid'],
            x=self.pos().x() + 150, y=self.pos().y() + 40)
        model.append(new_code)
        self.scene().addItem(TextGraphicsItem(self.app, new_code))
        self.scene().remove_links()
        self.scene().create_links()
        dialog._lock_branch_selection()

    def case_media(self, ):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders.
        TODO Will not be current if codes are merged in. """

        DialogCodeInAllFiles(self.app, self.code_or_cat, "Case")

    def coded_media(self, ):
        """ Display all coded media for this code.
        Coded media comes from ALL files and current coder.
        TODO Will not be current of codes are merged it. """

        DialogCodeInAllFiles(self.app, self.code_or_cat)

    def link_category_under_category(self):
        """ Link category under another category.
         Use child_names list to prevent circular linkages. """

        categories_ = []
        global model  # noqa: F824
        # circular-nesting check by ids, not names
        blocked_catids = descendant_catids(model, self.code_or_cat['catid'])
        for item in model:
            if item['catid'] != self.code_or_cat['catid'] and item['name'] != "" and item['cid'] is None and \
                    item['catid'] not in blocked_catids:
                categories_.append(item)

        ui = DialogSelectItems(self.app, categories_, _('Link under: Select category'), 'single')
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        if not category:
            return
        self.code_or_cat['supercatid'] = category['catid']
        for item in model:
            if item['catid'] == self.code_or_cat['catid']:
                item['supercatid'] = category['catid']
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def merge_category_into_category(self):
        """ Merge category into another category.
         Use child_names list to prevent circular linkages. """

        categories = []
        global model  # noqa: F824
        # circular-nesting check by ids, not names
        blocked_catids = descendant_catids(model, self.code_or_cat['catid'])
        for item in model:
            if item['catid'] != self.code_or_cat['catid'] and item['name'] != "" and item['cid'] is None and \
                    item['catid'] not in blocked_catids:
                categories.append(item)
        ui = DialogSelectItems(self.app, categories, _('Merge into: Select category'), 'single')
        ok = ui.exec()
        if not ok:
            return
        merge_category = ui.get_selected()
        if not merge_category:
            return
        # merge memos; the merged category's memo is appended to the target's
        merged_memo = self.code_or_cat.get('memo', '')
        if merged_memo:
            for item in model:
                if item.get('cid') is None and item.get('catid') == merge_category['catid'] \
                        and item.get('name', '') != "":
                    prefix = (item['memo'] + "\n") if item.get('memo') else ""
                    item['memo'] = prefix + _("Merged from category ") \
                        + f"'{self.code_or_cat['name'].strip()}': " + merged_memo
                    break
        # Update subcategories and codes of this category
        for item in model:
            if item['supercatid'] == self.code_or_cat['catid']:
                item['supercatid'] = merge_category['catid']
            if item['catid'] == self.code_or_cat['catid'] and item['cid'] is not None:
                item['catid'] = merge_category['catid']

        # Update this item in model
        for item in model:
            if item['catid'] == self.code_or_cat['catid'] and item['cid'] is None:
                item['name'] = ""
                item['delete'] = True  # Flag to delete from database, if pre-exisitng category
                item['merged_into_catid'] = merge_category['catid']  # for change preview
                break
        self.code_or_cat['name'] = ""
        self.hide()
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True

    def remove_category_from_category(self):
        """ Remove category from category as top level item. """

        self.code_or_cat['supercatid'] = None
        for item in model:
            if item['catid'] == self.code_or_cat['catid']:
                item['supercatid'] = None
        global update_graphics_item_models  # noqa: F824
        update_graphics_item_models = True


# id-based descendant collection. The circular-nesting checks used to
# compare by NAME (child_names), which breaks with duplicate names across branches.
def descendant_catids(model_list, catid):
    """ All descendant category ids of catid (BFS over supercatid). """
    result = set()
    frontier = {catid}
    guard = 0
    while frontier and guard < 1000:
        guard += 1
        next_frontier = set()
        for item in model_list:
            if item.get('cid') is None and item.get('supercatid') in frontier \
                    and item.get('catid') is not None and item['catid'] not in result:
                result.add(item['catid'])
                next_frontier.add(item['catid'])
        frontier = next_frontier
    return result


def descendant_cids(model_list, cid):
    """ All descendant sub-code ids of cid (BFS over supercid). """
    result = set()
    frontier = {cid}
    guard = 0
    while frontier and guard < 1000:
        guard += 1
        next_frontier = set()
        for item in model_list:
            if item.get('cid') is not None and item.get('supercid') in frontier \
                    and item['cid'] not in result:
                result.add(item['cid'])
                next_frontier.add(item['cid'])
        frontier = next_frontier
    return result


def compute_edge_point(center_source, center_target, rect, is_ellipse):
    """ 
    Perimeter intersection point of the line from center_source towards
    center_target, on a rectangle or ellipse
    """
    
    dx = center_target.x() - center_source.x()
    dy = center_target.y() - center_source.y()
    if dx == 0 and dy == 0:
        return center_source
    w = rect.width() / 2
    h = rect.height() / 2
    if is_ellipse:
        angle = math.atan2(dy, dx)
        return QtCore.QPointF(center_source.x() + w * math.cos(angle),
                              center_source.y() + h * math.sin(angle))
    if dx == 0:
        return QtCore.QPointF(center_source.x(), center_source.y() + math.copysign(h, dy))
    if dy == 0:
        return QtCore.QPointF(center_source.x() + math.copysign(w, dx), center_source.y())
    tx = w / abs(dx)
    ty = h / abs(dy)
    t = min(tx, ty)
    return QtCore.QPointF(center_source.x() + dx * t, center_source.y() + dy * t)


class LinkGraphicsItem(QtWidgets.QGraphicsLineItem):
    """
    line between two TextGraphicsItems, rebuilt on the view_graph
    style: smooth perimeter-to-perimeter geometry (rect or ellipse aware), drawn
    behind the nodes, never intercepting mouse interaction. The old side-snapping
    logic and the PointGraphicsItem end markers are gone. 
    """

    def __init__(self, from_widget, to_widget, line_width=2, color="gray"):
        """ param: from_widget / to_widget : TextGraphicsItem """

        super(LinkGraphicsItem, self).__init__(None)
        self.from_widget = from_widget
        self.to_widget = to_widget
        self.line_width = line_width
        self.color = color
        # Lines are decorative here: not selectable, no mouse buttons
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.calculate_points_and_draw()

    def redraw(self):
        """ Called from mouse move events. """

        self.calculate_points_and_draw()

    def calculate_points_and_draw(self):
        """
        Smooth perimeter intersection between both widgets
        """

        c1 = self.from_widget.sceneBoundingRect().center()
        c2 = self.to_widget.sceneBoundingRect().center()
        self.setZValue(-1)  # behind the nodes
        rect1 = self.from_widget.sceneBoundingRect()
        rect2 = self.to_widget.sceneBoundingRect()
        if rect1.intersects(rect2):
            p1, p2 = c1, c2
        else:
            p1 = compute_edge_point(c1, c2, rect1,
                                    getattr(self.from_widget, 'is_ellipse', False))
            p2 = compute_edge_point(c2, c1, rect2,
                                    getattr(self.to_widget, 'is_ellipse', False))
        self.setPen(QtGui.QPen(QtGui.QColor(self.color), self.line_width,
                               QtCore.Qt.PenStyle.SolidLine))
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())

    # directionality. Every hierarchy link is drawn from parent (from_widget)
    # to child (to_widget), so an arrowhead at the child end (p2) shows at a glance which
    # node is the parent and which is the child. Uses the same triangle geometry and the
    # theme-aware line colour as the graph view.
    ARROW_SIZE = 11

    def boundingRect(self):
        # Widen so the arrowhead near the child end is never clipped.
        m = self.ARROW_SIZE + 2
        return super().boundingRect().adjusted(-m, -m, m, m)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)  # the line itself
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        if dx == 0 and dy == 0:
            return
        back = math.atan2(dy, dx) + math.pi  # from the child end back toward the parent
        color = QtGui.QColor(self.color)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setBrush(QtGui.QBrush(color))
        painter.setPen(QtGui.QPen(color, 1))
        tri = QtGui.QPolygonF([
            p2,
            QtCore.QPointF(p2.x() + self.ARROW_SIZE * math.cos(back + math.pi / 6),
                           p2.y() + self.ARROW_SIZE * math.sin(back + math.pi / 6)),
            QtCore.QPointF(p2.x() + self.ARROW_SIZE * math.cos(back - math.pi / 6),
                           p2.y() + self.ARROW_SIZE * math.sin(back - math.pi / 6))])
        painter.drawPolygon(tri)
        painter.restore()


class ConnectionHandleItem(QtWidgets.QGraphicsEllipseItem):
    """
    small blue handle shown above the sole selected node, used as the
    start point for the hierarchical drag-to-connect. 
    The connect gesture itself is driven from thedialog's eventFilter; 
    this item only marks the grab point
    """

    SIZE = 14

    def __init__(self, parent_item):
        super().__init__(parent_item)
        self.parent_item = parent_item
        r = self.SIZE / 2
        self.setRect(-r, -r, self.SIZE, self.SIZE)
        self.setBrush(QtGui.QBrush(QtGui.QColor("#2196F3")))
        self.setPen(QtGui.QPen(QtGui.QColor("#0D47A1"), 2))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton)
        self.setToolTip(_("Drag onto a parent code or category to nest this item"))
        self._reposition()

    def _reposition(self):
        br = self.parent_item.boundingRect()
        self.setPos(br.center().x(), br.top() - 10)

    def mousePressEvent(self, event):
        # The dialog eventFilter handles the actual connect; just accept left clicks
        # so they do not fall through to node dragging.
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
        else:
            event.ignore()

    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QBrush(QtGui.QColor("#42A5F5")))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtGui.QColor("#2196F3")))
        super().hoverLeaveEvent(event)


class DialogSelectBranch(QtWidgets.QDialog):
    """
    tree selector for the Code organiser branch. Shows the full
    category / code / sub-code hierarchy so ANY node (or All) can be chosen as the
    root of the organiser view, including sub-codes and sub-categories, which the old
    flat list could not reach. Returns a stable key in self.selected_key:
        None            : All
        ('cat', catid)  : a category (top level or nested)
        ('code', cid)   : a code or sub-code
    """

    def __init__(self, app, codes, categories, parent=None):
        super().__init__(parent)
        self.app = app
        self.selected_key = None
        self.setWindowTitle(_("Select code tree branch"))
        try:
            self.setStyleSheet("* {font-size:" + str(app.settings['fontsize']) + "pt} ")
        except Exception:
            pass
        self.resize(440, 560)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(_("Select a branch to organise (a category, a "
                                            "code, or a sub-code), or All:")))
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)
        # "All" as the first, pre-selected item
        all_item = QtWidgets.QTreeWidgetItem([_("All")])
        all_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, None)
        self.tree.addTopLevelItem(all_item)
        self._build_tree(codes, categories)
        self.tree.expandAll()
        self.tree.setCurrentItem(all_item)
        self.tree.itemDoubleClicked.connect(lambda *_a: self.accept())
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_item(self, parent, text, key, color=None):
        it = QtWidgets.QTreeWidgetItem([text])
        it.setData(0, QtCore.Qt.ItemDataRole.UserRole, key)
        # show the code colour (categories stay neutral), matching the main
        # code tree: coloured background with a light/dark text for contrast
        if color:
            it.setBackground(0, QtGui.QBrush(QtGui.QColor(color)))
            it.setForeground(0, QtGui.QBrush(QtGui.QColor(TextColor(color).recommendation)))
        if parent is None:
            self.tree.addTopLevelItem(it)
        else:
            parent.addChild(it)
        return it

    def _build_tree(self, codes, categories):
        """ Categories (recursively), with their codes, and codes' sub-codes. Free
        codes (no category, no parent code) are added at the top level too. """

        def add_subcodes(parent_item, parent_cid):
            for code in codes:
                if code.get('supercid') == parent_cid:
                    it = self._add_item(parent_item, code['name'].strip(), ('code', code['cid']),
                                        color=code.get('color'))
                    add_subcodes(it, code['cid'])

        def add_codes_of_category(parent_item, catid):
            for code in codes:
                if code.get('catid') == catid and code.get('supercid') is None:
                    it = self._add_item(parent_item, code['name'].strip(), ('code', code['cid']),
                                        color=code.get('color'))
                    add_subcodes(it, code['cid'])

        def add_categories(parent_item, supercatid):
            for cat in categories:
                if cat.get('supercatid') == supercatid:
                    it = self._add_item(parent_item, cat['name'].strip(), ('cat', cat['catid']))
                    add_categories(it, cat['catid'])
                    add_codes_of_category(it, cat['catid'])

        add_categories(None, None)  # top-level categories and their subtrees
        for code in codes:  # free codes: no category and not a sub-code
            if code.get('catid') is None and code.get('supercid') is None:
                it = self._add_item(None, code['name'].strip(), ('code', code['cid']),
                                    color=code.get('color'))
                add_subcodes(it, code['cid'])

    def accept(self):
        item = self.tree.currentItem()
        if item is not None:
            self.selected_key = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        super().accept()
