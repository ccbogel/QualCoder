# -*- coding: utf-8 -*-

"""
Copyright (c) 2024 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

from copy import deepcopy
import datetime
import logging
import os
from random import randint
import sqlite3
import sys
import traceback

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import TextColor
from .confirm_delete import DialogConfirmDelete
from .GUI.base64_helper import *
from .GUI.ui_dialog_organiser import Ui_DialogOrganiser
from .helpers import DialogCodeInAV, DialogCodeInImage, DialogCodeInText, \
    ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    txt = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(txt)
    logger.error(_("Uncaught exception: ") + txt)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(txt)
    mb.exec()

categories_merged_update_graphics_items = []  # [old_catid, new_catid]
categories_linked_update_graphics_items = []  # [catid, new_supercatid]


class CodeOrganiser(QDialog):
    """ Dialog to organise code and categories in an acyclic graph.
    Add new categories, move codes and categories to other categories.
    Merge codes and categories
    Delete categories
    """

    app = None
    conn = None
    settings = None
    scene = None
    categories = []
    codes = []
    font_size = 9

    def __init__(self, app):
        """ Set up the dialog. """

        sys.excepthook = exception_handler
        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogOrganiser()
        self.ui.setupUi(self)
        font = f"font: {self.app.settings['fontsize']}pt "
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_export.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export.pressed.connect(self.export_image)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(zoom_icon), "png")
        self.ui.label_zoom.setPixmap(pm.scaled(26, 26))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(plus_icon), "png")
        self.ui.pushButton_selectbranch.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_selectbranch.pressed.connect(self.select_tree_branch)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(sq_plus_icon), "png")
        self.ui.pushButton_create_category.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_create_category.pressed.connect(self.create_category)

        # Set the scene
        self.scene = GraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)
        self.codes, self.categories = app.get_codes_categories()
        for code in self.codes:
            code['original_catid'] = code['catid']
            code['original_name'] = code['name']
        for category in self.categories:
            category['original_catid'] = category['catid']
            category['original_supercatid'] = category['supercatid']
            category['original_name'] = category['name']
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

    def create_category(self):
        """ Create a new category. """

        cat_ids_list = []
        for cat in self.categories:
            cat_ids_list.append(cat['catid'])

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec()
        new_category_name = ui.get_new_name()
        if new_category_name is None:
            return

        temp_cat_id = randint(-1000, -1)
        while temp_cat_id in cat_ids_list:
            temp_cat_id = randint(-1000, -1)
        now_date = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H-%S")
        # No original_name, original_catid, original_supercatid
        new_category = {'name': new_category_name, 'catid': temp_cat_id, 'owner': self.settings['codername'],
                        'date': now_date, 'memo': '', 'supercatid': None,
                        'x': 10 + randint(0, 6), 'y': 10 + randint(0, 6), 'color': "#FFFFFF", 'cid': None, 'child_names': []}
        self.categories.append(new_category)
        self.scene.addItem(TextGraphicsItem(self.app, new_category, self.codes, self.categories))

    def select_tree_branch(self):
        """ Selected tree branch for model of codes and categories.
        Called by pushButton_selectbranch
        """

        selection_list = [{'name': 'All'}]
        for category in self.categories:
            if category['name'] != "":
                selection_list.append({'name': category['name']})
        ui = DialogSelectItems(self.app, selection_list, _("Select code tree branch"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            node_text = "All"
        else:
            node_text = selected[0]['name']
        cats, codes, model = self.create_initial_model()
        model = self.get_refined_model_with_category_counts(cats, model, node_text)
        self.list_graph(model)
        self.ui.pushButton_selectbranch.setEnabled(False)
        self.ui.pushButton_selectbranch.setText(_("Branch has been selected"))

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
            for n in refined_model:
                for m in model:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
            for n in append_list:
                refined_model.append(n)
                model.remove(n)
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
        for code_or_cat in model:
            if code_or_cat['x'] is None and code_or_cat['supercatid'] is None:
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
            i += 1

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
                self.scene.addItem(TextGraphicsItem(self.app, code_or_cat, self.codes, self.categories))

        '''# Add link from Category to Category, which includes the scene text items and associated data
        for scene_item in self.scene.items():
            if isinstance(scene_item, TextGraphicsItem):
                for n in self.scene.items():
                    if isinstance(n, TextGraphicsItem) and scene_item.code_or_cat['supercatid'] is not None and \
                            scene_item.code_or_cat['supercatid'] == n.code_or_cat['catid'] and \
                            (scene_item.code_or_cat['cid'] is None and n.code_or_cat['cid'] is None):
                        item = LinkGraphicsItem(scene_item, n)
                        self.scene.addItem(item)'''

        # Expand scene width and height if needed
        max_x, max_y = self.scene.suggested_scene_size()
        self.scene.set_width(max_x)
        self.scene.set_height(max_y)

    def keyPressEvent(self, event):
        """ Plus, W to zoom in and Minus, Q to zoom out. Needs focus on the QGraphicsView widget. """

        key = event.key()
        # mod = event.modifiers()
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

    def reject(self):

        super(CodeOrganiser, self).reject()

    def accept(self):

        super(CodeOrganiser, self).accept()

    def eventFilter(self, obj, event):
        """ https://stackoverflow.com/questions/71993533/
        how-to-initiate-context-menu-event-in-qgraphicsitem-from-qgraphicsview-context-m/72002453#72002453
        This is required to forward context menu event to graphics view items.
        I dont understand how it works yet! """

        if obj == self.ui.graphicsView.viewport() and event.type() == event.Type.ContextMenu:
            self.ui.graphicsView.contextMenuEvent(event)
            return event.isAccepted()
        return super().eventFilter(obj, event)

    def graphicsview_menu(self, position):
        item = self.ui.graphicsView.itemAt(position)
        if item is not None:
            print(item, type(item))
            # Error with LinkGraphicsItem
            self.scene.sendEvent(item)
            return
        # Menu for blank graphics view area
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_print_items = menu.addAction(_("Print items"))
        #action_add_line = menu.addAction(_("Insert Line"))
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        if action == action_print_items:
            for i in self.scene.items():
                print(item)


    def export_image(self):
        """ Export the QGraphicsScene as a png image with transparent background.
        Called by QButton_export.
        """

        filename = "Graph.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        # Scene size is too big.
        max_x, max_y = self.scene.suggested_scene_size()
        rect_area = QtCore.QRectF(0.0, 0.0, max_x + 10, max_y + 10)  # Source area
        image = QtGui.QImage(int(max_x + 10), int(max_y + 10), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect. painter, target area, source area
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect_area)
        painter.end()
        image.save(filepath)
        Message(self.app, _("Image exported"), filepath).exec()


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
        """ On mouse move, an item might be repositioned so need to redraw all the link_items.
        This slows re-drawing down, but is dynamic. """

        super(GraphicsScene, self).mousePressEvent(mouse_event)

        x_diff = 0
        y_diff = 0
        child_names = []
        # Garbage items for removal
        for item in self.items():
            if isinstance(item, TextGraphicsItem) and item.code_or_cat['name'] == "":
                self.removeItem(item)
        # Update code.catid or category.supercatid if a category has been merged into another category
        global categories_merged_update_graphics_items
        if len(categories_merged_update_graphics_items) > 0:
            #print("global values", categories_merged_update_graphics_items)
            for item in self.items():
                # a Code item
                if isinstance(item, TextGraphicsItem) and item.code_or_cat['cid'] and \
                        item.code_or_cat['catid'] == categories_merged_update_graphics_items[0]:
                    #print("Match", item.code_or_cat['name'])
                    item.code_or_cat['catid'] = categories_merged_update_graphics_items[1]
                # Category item
                if isinstance(item, TextGraphicsItem) and item.code_or_cat['supercatid'] and \
                        item.code_or_cat['supercatid'] == categories_merged_update_graphics_items[0]:
                    #print("Match", item.code_or_cat['name'])
                    item.code_or_cat['supercatid'] = categories_merged_update_graphics_items[1]
            categories_merged_update_graphics_items = []

        # Update category.supercatid if a category has been linked under another category
        global categories_linked_update_graphics_items
        if len(categories_linked_update_graphics_items) > 0:
            for item in self.items():
                if isinstance(item, TextGraphicsItem) and item.code_or_cat['supercatid'] and \
                        item.code_or_cat['catid'] == categories_linked_update_graphics_items[0]:
                    print("Match cat", item.code_or_cat['name'])
                    item.code_or_cat['supercatid'] = categories_linked_update_graphics_items[1]
                    categories_linked_update_graphics_items = []
                    break

        # Check and update stored positions
        for item in self.items():
            if isinstance(item, TextGraphicsItem):
                if item.code_or_cat['x'] != item.pos().x() or item.code_or_cat['y'] != item.pos().y():
                    x_diff = item.pos().x() - item.code_or_cat['x']
                    item.code_or_cat['x'] = item.pos().x()
                    y_diff = item.pos().y() - item.code_or_cat['y']
                    item.code_or_cat['y'] = item.pos().y()
                    item.setPos(item.code_or_cat['x'], item.code_or_cat['y'])
                    child_names = item.code_or_cat['child_names']
                    break
        # Move child items of category
        if x_diff != 0 or y_diff != 0:
            for item in self.items():
                if isinstance(item, TextGraphicsItem) and item.code_or_cat['name'] in child_names:
                    item.code_or_cat['x'] += x_diff
                    item.code_or_cat['y'] += y_diff
                    item.setPos(item.code_or_cat['x'], item.code_or_cat['y'])

        self.remove_links()
        self.create_links()
        self.adjust_for_negative_positions()
        self.suggested_scene_size()
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

    def remove_links(self):
        """ Clean up by removing all links """

        for scene_item in self.items():
            if isinstance(scene_item, LinkGraphicsItem):
                self.removeItem(scene_item)

    def create_links(self):
        """ Add links from Codes to Categories. And Categories to categories. """

        # Link from code to category
        for cat_item in self.items():
            #print(cat_item.code_or_cat['name'], cat_item.code_or_cat['catid'])
            if isinstance(cat_item, TextGraphicsItem):
                for code_item in self.items():
                    # Link the Codes to Categories
                    if isinstance(code_item, TextGraphicsItem) and code_item.code_or_cat['cid'] is not None and \
                            cat_item.code_or_cat['cid'] is None and \
                            cat_item.code_or_cat['catid'] == code_item.code_or_cat['catid']:
                        link_item = LinkGraphicsItem(cat_item, code_item)
                        #if cat_item.isVisible() and code_item.isVisible():
                        self.addItem(link_item)

        # Link from Category to Category, which includes the scene text items and associated data
        for item1 in self.items():
            if isinstance(item1, TextGraphicsItem):
                for item2 in self.items():
                    if isinstance(item2, TextGraphicsItem) and item1.code_or_cat['supercatid'] is not None and \
                            item1.code_or_cat['supercatid'] == item2.code_or_cat['catid'] and \
                            (item1.code_or_cat['cid'] is None and item2.code_or_cat['cid'] is None):
                        item = LinkGraphicsItem(item1, item2)
                        if item1.isVisible() and item2.isVisible():
                            self.addItem(item)

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
                if not isinstance(i, LinkGraphicsItem):  # or isinstance(i, FreeLineGraphicsItem)):
                    i.setPos(i.pos().x() - min_adjust_x, i.pos().y() - min_adjust_y)

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
    codes = []
    categories = []

    def __init__(self, app, code_or_cat, codes, categories):
        """ Show name and colour of text. Has context menu for various options.
         :param: app  : the main App class
         :param: code_or_cat  : Dictionary of the code details: name, memo, color etc
         :param: codes : List of codes
         :param: categories : List of categories
         """

        super(TextGraphicsItem, self).__init__(None)
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.code_or_cat = code_or_cat
        self.codes = codes
        self.categories = categories
        self.setPos(self.code_or_cat['x'], self.code_or_cat['y'])
        self.text = f"{self.code_or_cat['name']} catid[{self.code_or_cat['catid']}]"
        if self.code_or_cat['supercatid']:
            self.text += f" supid[{self.code_or_cat['supercatid']}]"
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        self.setDefaultTextColor(QtGui.QColor(TextColor(self.code_or_cat['color']).recommendation))
        self.setFont(QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Normal))
        self.setPlainText(self.text)
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
        coded_action = None
        case_action = None
        link_code_to_category_action = None
        merge_code_into_code_action = None
        remove_code_from_category_action = None
        link_category_under_category_action = None
        merge_category_into_category_action = None
        remove_category_from_category_action = None
        if self.code_or_cat['cid'] is not None:
            link_code_to_category_action = menu.addAction('Link code to category')
            merge_code_into_code_action = menu.addAction('Merge code into code')
            if self.code_or_cat['catid'] is not None:
                remove_code_from_category_action = menu.addAction('Remove code from category')
            coded_action = menu.addAction('Coded text and media')
            case_action = menu.addAction('Case text and media')
        if self.code_or_cat['cid'] is None:
            link_category_under_category_action = menu.addAction('Link category under category')
            merge_category_into_category_action = menu.addAction('Merge category into category')
            if self.code_or_cat['supercatid'] is not None:
                remove_category_from_category_action = menu.addAction('Remove category from category')
        memo_action = menu.addAction('Memo')
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # Codes
        if action == memo_action:
            self.add_edit_memo()
            self.get_memo()
        if action == coded_action:
            self.coded_media()
        if action == case_action:
            self.case_media()
        if action == link_code_to_category_action:
            self.link_code_to_category()
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

    def link_code_to_category(self):
        """ Link selected code to selected category. """

        categories = []
        for cat in self.categories:
            if cat['name'] != "":
                categories.append(cat)
        ui = DialogSelectItems(self.app, categories, 'Select category', 'single')
        ui.exec()
        category= ui.get_selected()
        if not category:
            return
        #print(category)
        self.code_or_cat['catid'] = category['catid']

    def merge_code_into_code(self):
        """ """

        codes = []
        for c in self.codes:
            if c['cid'] != self.code_or_cat['cid'] and c['name'] != "":
                codes.append(c)
        ui = DialogSelectItems(self.app, codes, 'Select code', 'single')
        ui.exec()
        merge_code = ui.get_selected()
        if not merge_code:
            return
        for c in self.codes:
            if c['cid'] == self.code_or_cat['cid']:
                c['name'] = ""
        self.code_or_cat['cid'] = merge_code['cid']
        self.hide()

    def remove_code_from_category(self):
        """ Remove code from category as top level item. """

        self.code_or_cat['catid'] = None

    def case_media(self, ):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders. """

        DialogCodeInAllFiles(self.app, self.code_or_cat, "Case")

    def coded_media(self, ):
        """ Display all coded media for this code.
        Coded media comes from ALL files and current coder.
        """

        DialogCodeInAllFiles(self.app, self.code_or_cat)

    def link_category_under_category(self):

        # Check if category is child - cannot have circular referencing
        #children = self.child_categories(self.code_or_cat)
        child_ids = self.child_categories(self.code_or_cat, [])
        print(child_ids)
        #print(f"Linking {self.code_or_cat['name']}\n--Child cats: {children}")
        #return ("Print testing link category. End")
        categories = []
        for cat in self.categories:
            if cat['catid'] != self.code_or_cat['catid'] and cat['name'] != "":
                # Check if category is child - cannot have circular referencing
                #TODO
                categories.append(cat)
        ui = DialogSelectItems(self.app, categories, 'Select category', 'single')
        ui.exec()
        category = ui.get_selected()
        if not category:
            return
        self.code_or_cat['supercatid'] = category['catid']
        global categories_linked_update_graphics_items
        categories_linked_update_graphics_items =[self.code_or_cat['catid'], category['catid']]

    def child_categories(self, parent, child_ids):
        """ Get child categories of this category parent.
        Create a list of this category (node) and all its category children.
        Maximum depth of 200.
        :param : node : Dictionary of category
        :return : child_category_ids : List of catid
        """

        #categories = deepcopy(self.categories)
        for category in self.categories:
            print(parent['catid'], category)
            if parent['catid'] == category['supercatid']:
                child_ids += self.child_categories(category, child_ids)
                print(category['name'], "child of", parent['name'])
        return child_ids

    def merge_category_into_category(self):
        categories = []
        for c in self.categories:
            if c['catid'] != self.code_or_cat['catid'] and c['name'] != "":
                categories.append(c)
        ui = DialogSelectItems(self.app, categories, 'Select category', 'single')
        ui.exec()
        merge_category = ui.get_selected()
        if not merge_category:
            return
        for c in self.categories:
            if c['catid'] == self.code_or_cat['catid']:
                c['name'] = ""
            if c['supercatid'] == self.code_or_cat['catid']:
                c['supercatid'] = merge_category['catid']
        for c in self.codes:
            if c['catid'] == self.code_or_cat['catid']:
                c['catid'] = merge_category['catid']
        # old, new_catid
        global categories_merged_update_graphics_items
        categories_merged_update_graphics_items = [self.code_or_cat['catid'], merge_category['catid']]
        self.code_or_cat['catid'] = merge_category['catid']
        self.code_or_cat['name'] = ""
        self.hide()

    def remove_category_from_category(self):
        """ Remove category from category as top level item. """

        self.code_or_cat['supercatid'] = None


class LinkGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Takes the coordinate from the two TextGraphicsItems. """

    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None

    def __init__(self, from_widget, to_widget):
        """ Links codes and categories. Called when codes or categories of categories are inserted.
         param: from_widget  : TextGraphicsItem
         param: to_widget : TextGraphicsItem
        """
        super(LinkGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.text = from_widget.text + " - " + to_widget.text
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_points_and_draw()
        self.redraw()

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()

        thicker_action = menu.addAction(_('Thicker'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        '''if action == thicker_action:
            self.line_width = self.line_width + 1
            if self.line_width > 8:
                self.line_width = 8'''
        self.redraw()

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculate_points_and_draw()

    def calculate_points_and_draw(self):
        """ Calculate the to x and y and from x and y points. Draw line between the
        widgets. Join the line to appropriate side of widget. """

        to_x = self.to_widget.pos().x()
        to_y = self.to_widget.pos().y()
        from_x = self.from_widget.pos().x()
        from_y = self.from_widget.pos().y()

        x_overlap = False
        # Fix from_x value to middle of from widget if to_widget overlaps in x position
        if from_x < to_x < from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width() / 2
            x_overlap = True
        # Fix to_x value to middle of to widget if from_widget overlaps in x position
        if to_x < from_x < to_x + self.to_widget.boundingRect().width():
            to_x = to_x + self.to_widget.boundingRect().width() / 2
            x_overlap = True

        # Fix from_x value to right-hand side of from widget if to_widget on the right of the from_widget
        if not x_overlap and to_x > from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width()
        # Fix to_x value to right-hand side if from_widget on the right of the to widget
        elif not x_overlap and from_x > to_x + self.to_widget.boundingRect().width():
            to_x = to_x + self.to_widget.boundingRect().width()

        y_overlap = False
        # Fix from_y value to middle of from widget if to_widget overlaps in y position
        if from_y < to_y < from_y + self.from_widget.boundingRect().height():
            from_y = from_y + self.from_widget.boundingRect().height() / 2
            y_overlap = True
        # Fix from_y value to middle of to widget if from_widget overlaps in y position
        if to_y < from_y < to_y + self.to_widget.boundingRect().height():
            to_y = to_y + self.to_widget.boundingRect().height() / 2
            y_overlap = True
        # Fix from_y value if to_widget is above the from_widget
        if not y_overlap and to_y > from_y:
            from_y = from_y + self.from_widget.boundingRect().height()
        # Fix to_y value if from_widget is below the to widget
        elif not y_overlap and from_y > to_y:
            to_y = to_y + self.to_widget.boundingRect().height()
        self.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 1, QtCore.Qt.PenStyle.SolidLine))
        self.setLine(from_x, from_y, to_x, to_y)
