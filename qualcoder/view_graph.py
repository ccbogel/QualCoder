# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

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

from collections import Counter
from copy import deepcopy
import logging
import math
import os
import sys
import traceback

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog

from .color_selector import TextColor
from .GUI.base64_helper import *
from .GUI.ui_dialog_graph import Ui_DialogGraph
from .helpers import DialogCodeInAllFiles, ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .save_sql_query import DialogSaveSql
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

    def __init__(self, app):
        """ Set up the dialog. """

        sys.excepthook = exception_handler
        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogGraph()
        self.ui.setupUi(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
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
        pm.loadFromData(QtCore.QByteArray.fromBase64(eye_icon), "png")
        self.ui.pushButton_reveal.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_reveal.pressed.connect(self.reveal_hidden_items)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(clear_icon), "png")
        self.ui.pushButton_clear.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_clear.pressed.connect(self.clear_items)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(plus_icon), "png")
        self.ui.pushButton_selectbranch.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_selectbranch.pressed.connect(self.select_tree_branch)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_2_icon), "png")
        self.ui.pushButton_freetextitem.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_freetextitem.pressed.connect(self.add_text_item_to_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(sq_plus_icon), "png")
        self.ui.pushButton_addfile.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_addfile.pressed.connect(self.add_files_to_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(sq_plus_icon), "png")
        self.ui.pushButton_addcase.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_addcase.pressed.connect(self.add_cases_to_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(line_icon), "png")
        self.ui.pushButton_addline.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_addline.pressed.connect(self.add_lines_to_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(arrow_up_icon), "png")
        self.ui.pushButton_loadgraph.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_loadgraph.pressed.connect(self.load_saved_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(arrow_down_icon), "png")
        self.ui.pushButton_savegraph.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_savegraph.pressed.connect(self.save_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(delete_icon), "png")
        self.ui.pushButton_deletegraph.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_deletegraph.pressed.connect(self.delete_saved_graph)

        # Set the scene
        self.scene = GraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)
        self.codes, self.categories = app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

    def clear_items(self):
        """ Clear all items from scene.
        Called by pushButton_clear. """

        self.scene.clear()

    def select_tree_branch(self):
        """ Selected tree branch for model of codes and categories.
        Called by pushButton_selectbranch
        """

        selection_list = [{'name': 'All'}]
        for c in self.categories:
            selection_list.append({'name': c['name']})
        ui = DialogSelectItems(self.app, selection_list, _("Select files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            node_text = "All"
        else:
            node_text = selected[0]['name']
        cats, codes, model = self.create_initial_model()
        # TODO is catid_count used ?
        model, catid_counts = self.get_refined_model_with_category_counts(cats, model, node_text)
        self.list_graph(model)

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
            code_['depth'] = 0
            code_['x'] = None
            code_['y'] = None
            code_['supercatid'] = code_['catid']
            code_['angle'] = None
        for cat in cats:
            cat['depth'] = 0
            cat['x'] = None
            cat['y'] = None
            cat['cid'] = None
            cat['angle'] = None
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

        # Look at each category and determine the depth.
        # Also determine the number of children for each catid.
        supercatid_list = []
        for c in model:
            depth = 0
            supercatid = c['supercatid']
            supercatid_list.append(c['supercatid'])
            count = 0
            while not (supercatid is None or count > 10000):
                for s in cats:
                    if supercatid == s['catid']:
                        depth += 1
                        supercatid = s['supercatid']
                c['depth'] = depth
                count += 1
        # TODO is catid_counts used ?
        catid_counts = Counter(supercatid_list)
        return model, catid_counts

    def get_refined_model(self, node, model):
        """ Return a refined model of this top node and all its children.
        Maximum depth is 20.
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
        Note, maximum depth of 100. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories != [] and new_model_changed and i < 100:
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
        for m in model:
            if m['x'] is None and m['supercatid'] is None:
                m['x'] = 10
                ordered_model.append(m)
        for om in ordered_model:
            model.remove(om)

        # sub-categories and codes
        i = 0
        while i < 1000 and len(model) > 0:
            for om in ordered_model:
                for sub_cat in model:
                    # subordinate categories
                    if sub_cat['supercatid'] == om['catid'] and sub_cat['x'] is None:
                        sub_cat['x'] = om['x'] + 120
                        ordered_model.insert(ordered_model.index(om), sub_cat)
            i += 1

        for i in range(0, len(ordered_model)):
            ordered_model[i]['y'] = i * self.font_size * 3
        model = ordered_model

        # Add text items to the scene, providing they are not already in the scene.
        for m in model:
            m['child_names'] = self.named_children_of_node(m)
            add_to_scene = True
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    if i.code_or_cat['name'] == m['name'] and \
                            i.code_or_cat['catid'] == m['catid'] and \
                            i.code_or_cat['cid'] == m['cid']:
                        add_to_scene = False
            if add_to_scene:
                self.scene.addItem(TextGraphicsItem(self.app, m))
                print(m)

        # Add link which includes the scene text items and associated data, add links before text_items
        for m in self.scene.items():
            if isinstance(m, TextGraphicsItem):
                for n in self.scene.items():
                    if isinstance(n, TextGraphicsItem) and m.code_or_cat['supercatid'] is not None and \
                            m.code_or_cat['supercatid'] == n.code_or_cat['catid'] and \
                            n.code_or_cat['depth'] < m.code_or_cat['depth']:
                        item = LinkGraphicsItem(self.app, m, n, 1, True)  # corners only = True
                        self.scene.addItem(item)

        # Expand scene width and height if needed
        max_x, max_y = self.scene.suggested_scene_size()
        '''max_x = self.scene.get_width()
        max_y = self.scene.get_height()
        for m in model:
            m['child_names'] = self.named_children_of_node(m)
            if m['x'] > max_x - 50:
                max_x = m['x'] + 50
            if m['y'] > max_y - 20:
                max_y = m['y'] + 40'''
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

    def save_graph(self):
        """ Save graph items. """

        #TODO uncomment later
        '''ui_save = DialogSaveSql(self.app)
        ui_save.setWindowTitle(_("Save graph"))
        ui_save.ui.label_name.setText(_("Graph name"))
        ui_save.ui.label.hide()
        ui_save.ui.lineEdit_group.hide()
        ui_save.exec()
        title = ui_save.name
        if title == "":
            msg = _("Must have a name")
            Message(self.app, _("Cannot save"), msg).exec()
            return
        description = ui_save.description'''

        print("TODO save graph items")
        for i in self.scene.items():
            if isinstance(i, TextGraphicsItem):
                print("TextGraphicsItem")
            if isinstance(i, FreeTextGraphicsItem):
                print("FreeTextGraphicsItem")
            if isinstance(i, FreeTextGraphicsItem):
                print("CaseTextGraphicsItem")
            if isinstance(i, FreeTextGraphicsItem):
                print("FileTextGraphicsItem")
            if isinstance(i, FreeTextGraphicsItem):
                print("FreeLineGraphicsItem")
            if isinstance(i, FreeTextGraphicsItem):
                print("LineGraphicsItem")

    def load_saved_graph(self):
        """ Load saved graph. """

        print("TODO load saved graph")

    def delete_saved_graph(self):
        """ Delete saved graph items. """

        print("TODO delete saved graph ")

    def keyPressEvent(self, event):
        """ Plus to zoom in and Minus to zoom out. Needs focus on the QGraphicsView widget. """

        key = event.key()
        # mod = event.modifiers()
        if key == QtCore.Qt.Key.Key_Plus:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() > 10:
                return
            self.ui.graphicsView.scale(1.1, 1.1)
        if key == QtCore.Qt.Key.Key_Minus:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() < 0.1:
                return
            self.ui.graphicsView.scale(0.9, 0.9)
        if key == QtCore.Qt.Key.Key_H:
            # print item x y
            for i in self.scene.items():
                print(i.__class__, i.pos())

    def reject(self):

        super(ViewGraph, self).reject()

    def accept(self):

        super(ViewGraph, self).accept()

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
            self.scene.sendEvent(item)
            return
        # Menu for blank graphics view area
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_add_text_item = QtGui.QAction(_("Insert Text"))
        menu.addAction(action_add_text_item)
        action_add_line = QtGui.QAction(_("Insert Line"))
        menu.addAction(action_add_line)
        action_add_files = QtGui.QAction(_("Show files"))
        menu.addAction(action_add_files)
        action_add_cases = QtGui.QAction(_("Show cases"))
        menu.addAction(action_add_cases)
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        if action == action_add_text_item:
            self.add_text_item_to_graph(position.x(), position.y())
        if action == action_add_line:
            self.add_lines_to_graph()
        if action == action_add_files:
            self.add_files_to_graph()
        if action == action_add_cases:
            self.add_cases_to_graph()

    def add_lines_to_graph(self):
        """ Add one or more lines from an item to one or more destination items. """

        # From item
        names = self.named_text_items()
        names_dict_list = []
        for n in names:
            names_dict_list.append({'name': n})
        ui = DialogSelectItems(self.app, names_dict_list, _("Line start item"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        text_from = selected['name']
        from_item = None
        for item in self.scene.items():
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                    isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem):
                if item.text == text_from:
                    from_item = item
        # To Items selection
        names_dict_list.remove(selected)
        ui = DialogSelectItems(self.app, names_dict_list, _("Line end item(s)"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            return

        # Line color selection
        names = [_("gray"), _("blue"), _("cyan"), _("magenta"), _("green"), _("red"), _("yellow")]
        names_dict_list = []
        for n in names:
            names_dict_list.append({'name': n})
        ui = DialogSelectItems(self.app, names_dict_list, _("Line colour"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected_color = ui.get_selected()
        color = selected_color['name']

        # Create To Item lines
        for s in selected:
            text_to = s['name']
            to_item = None
            for item in self.scene.items():
                if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                        isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem):
                    if item.text == text_to:
                        to_item = item
            if from_item != to_item and not (from_item is None or to_item is None):
                line_item = FreeLineGraphicsItem(self.app, from_item, to_item, color)
                self.scene.addItem(line_item)

    def add_text_item_to_graph(self, x=20, y=20):
        """ Add text item to graph. Ensure text is unique. """

        text_, ok = QtWidgets.QInputDialog.getText(self, _('Text object'), _('Enter text:'))
        if ok and text_ not in self.named_text_items():
            item = FreeTextGraphicsItem(self.app, x, y, text_)
            self.scene.addItem(item)

    def named_text_items(self):
        """ Used to get a list of all named FreeText and Case and File graphics items.
         Use to allow links between these items based on the text name.
         Called by: add_text_item_to_graph

         return: names : List of Strings
         """

        names = []
        for item in self.scene.items():
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                    isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem):
                names.append(item.text)
        names.sort()
        return names

    def add_files_to_graph(self):
        """ Add Text file items to graph. """

        files = self.get_files()
        ui = DialogSelectItems(self.app, files, _("Select files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        for i, s in enumerate(selected):
            file_item = FileTextGraphicsItem(self.app, s['name'], s['id'], i * 10, i * 10)
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
        ui = DialogSelectItems(self.app, cases, _("Select cases"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        for i, s in enumerate(selected):
            case_item = CaseTextGraphicsItem(self.app, s['name'], s['id'], i * 10, i * 10)
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
        rect_area = QtCore.QRectF(0.0, 0.0, max_x + 5, max_y + 5)
        image = QtGui.QImage(int(max_x + 5), int(max_y + 5), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect
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
        for item in self.items():
            if isinstance(item, LinkGraphicsItem) or isinstance(item, FreeLineGraphicsItem):
                # isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem):
                item.redraw()
        for item in self.items():
            if isinstance(item, FreeLineGraphicsItem) or isinstance(item, FreeTextGraphicsItem) \
                    or isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem):
                if item.remove is True:
                    self.removeItem(item)
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

    def adjust_for_negative_positions(self):
        """ Move all items if negative positions """

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
        """ Calculate the maximum width and height from the current Text Items. """

        max_x = 0
        max_y = 0
        for i in self.items():
            if isinstance(i, TextGraphicsItem) or isinstance(i, FreeTextGraphicsItem) or \
                    isinstance(i, FileTextGraphicsItem) or isinstance(i, CaseTextGraphicsItem):
                if i.pos().x() + i.boundingRect().width() > max_x:
                    max_x = i.pos().x() + i.boundingRect().width()
                if i.pos().y() + i.boundingRect().height() > max_y:
                    max_y = i.pos().y() + i.boundingRect().height()
        self.setSceneRect(0, 0, max_x, max_y)
        return max_x, max_y


class CaseTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item shows the case name and optionally attributes.
    A custom context menu
    """

    border_rect = None
    app = None
    font = None
    settings = None
    case_name = ""
    case_id = -1
    attribute_text = ""
    remove = False
    text = ""

    def __init__(self, app, case_name, case_id, x=0, y=0):
        """ Show name and optionally attributes.
         param: app  : the main App class
         param:  """

        super(CaseTextGraphicsItem, self).__init__(None)
        self.setToolTip(_("Case"))
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.case_id = case_id
        self.case_name = case_name
        self.attribute_text = ""
        self.text = self.case_name + self.attribute_text
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        # Foreground depends on the defined need_white_text color in color_selector
        self.font = QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Normal)
        self.setFont(self.font)
        self.setPlainText(self.text)
        self.setPos(50 + x, 50 + y)
        cur = self.app.conn.cursor()
        cur.execute("select memo from cases where caseid=?", [case_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("Case") + ": " + res[0])

    def paint(self, painter, option, widget):
        """ see paint override method here:
            https://github.com/jsdir/giza/blob/master/giza/widgets/nodeview/node.py
            see:
            https://doc.qt.io/qt-5/qpainter.html """

        color = QtCore.Qt.GlobalColor.white
        if self.app.settings['stylesheet'] == 'dark':
            color = QtCore.Qt.GlobalColor.black
        painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.setFont(self.font)
        fm = painter.fontMetrics()
        painter.setPen(QtGui.QColor(QtCore.Qt.GlobalColor.black))
        if self.app.settings['stylesheet'] == 'dark':
            painter.setPen(QtGui.QColor(QtCore.Qt.GlobalColor.white))
        lines = self.text.split('<br>')
        for row in range(0, len(lines)):
            painter.drawText(5, fm.height() * (row + 1), lines[row])

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        if self.attribute_text == "":
            menu.addAction(_('Show attributes'))
        else:
            menu.addAction(_('Hide attributes'))
        menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action.text() == "Remove":
            self.remove = True
        if action.text() == "Show attributes":
            self.get_attributes()
        if action.text() == "Hide attributes":
            self.attribute_text = ""
            self.text = self.case_name

    def get_attributes(self):
        """ Get attributes for the file.  Add to text document. """
        self.attribute_text = ""
        cur = self.app.conn.cursor()
        sql = "SELECT name, value FROM  attribute where attr_type='case' and id=? order by name"
        cur.execute(sql, [self.case_id])
        result = cur.fetchall()
        for r in result:
            self.attribute_text += '<br>' + r[0] + ": " + r[1]
        self.text = self.case_name + self.attribute_text


class FileTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item shows the file name and optionally attributes.
    A custom context menu
    """

    border_rect = None
    app = None
    font = None
    settings = None
    file_name = ""
    file_id = -1
    attribute_text = ""
    remove = False
    text = ""

    def __init__(self, app, file_name, file_id, x=0, y=0):
        """ Show name and optionally attributes.
         param: app  : the main App class
         param:  """

        super(FileTextGraphicsItem, self).__init__(None)
        self.setToolTip(_("File"))
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.file_id = file_id
        self.file_name = file_name
        self.attribute_text = ""
        self.text = self.file_name + self.attribute_text
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        # Foreground depends on the defined need_white_text color in color_selector
        self.font = QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Normal)
        self.setFont(self.font)
        self.setPlainText(self.text)
        self.setPos(50 + x, 50 + y)
        cur = self.app.conn.cursor()
        cur.execute("select memo from source where id=?", [file_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("File") + ": " + res[0])

    def paint(self, painter, option, widget):
        """ see paint override method here:
            https://github.com/jsdir/giza/blob/master/giza/widgets/nodeview/node.py
            see:
            https://doc.qt.io/qt-5/qpainter.html """

        color = QtCore.Qt.GlobalColor.white
        if self.app.settings['stylesheet'] == 'dark':
            color = QtCore.Qt.GlobalColor.black
        painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.setFont(self.font)
        fm = painter.fontMetrics()
        painter.setPen(QtGui.QColor(QtCore.Qt.GlobalColor.black))
        if self.app.settings['stylesheet'] == 'dark':
            painter.setPen(QtGui.QColor(QtCore.Qt.GlobalColor.white))
        lines = self.text.split('<br>')
        for row in range(0, len(lines)):
            painter.drawText(5, fm.height() * (row + 1), lines[row])

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        if self.attribute_text == "":
            menu.addAction(_('Show attributes'))
        else:
            menu.addAction(_('Hide attributes'))
        menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action.text() == "Remove":
            self.remove = True
        if action.text() == "Show attributes":
            self.get_attributes()
        if action.text() == "Hide attributes":
            self.attribute_text = ""
            self.text = self.file_name

    def get_attributes(self):
        """ Get attributes for the file.  Add to text document. """
        self.attribute_text = ""
        cur = self.app.conn.cursor()
        sql = "SELECT name, value FROM  attribute where attr_type='file' and id=? order by name"
        cur.execute(sql, [self.file_id])
        result = cur.fetchall()
        for r in result:
            self.attribute_text += '<br>' + r[0] + ": " + r[1]
        self.text = self.file_name + self.attribute_text


class FreeTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ Free text to add to the scene. """

    app = None
    font = None
    settings = None
    x = 10
    y = 10
    text = "text"
    remove = False

    def __init__(self, app, x, y, text_):
        """ Free text object.
         param:
            app  : the main App class
            x : Integer x position
            y : Intger y position
            text_ : String
         """

        super(FreeTextGraphicsItem, self).__init__(None)
        self.app = app
        self.x = x
        self.y = y
        self.text = text_
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        self.setFont(QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Normal))
        self.setPlainText(self.text)
        self.setPos(self.x, self.y)
        self.setDefaultTextColor(QtCore.Qt.GlobalColor.black)
        if self.app.settings['stylesheet'] == 'dark':
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.white)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        bold_action = menu.addAction(_("Bold"))
        large_font_action = menu.addAction(_("Large font"))
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == remove_action:
            self.remove = True
        if action == bold_action:
            self.setFont(QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Bold))
        if action == large_font_action:
            self.setFont(QtGui.QFont(self.settings['font'], 12, QtGui.QFont.Weight.Normal))

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class FreeLineGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Takes the coordinate from the two TextGraphicsItems. """

    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None
    line_width = 2
    line_type = QtCore.Qt.PenStyle.SolidLine
    line_color = QtCore.Qt.GlobalColor.gray
    corners_only = False  # True for list graph
    weighting = 1
    tooltip = ""
    remove = False

    def __init__(self, app, from_widget, to_widget, color="gray", corners_only=False):
        super(FreeLineGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.corners_only = corners_only
        self.weighting = 1
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_points_and_draw()
        self.line_color = QtCore.Qt.GlobalColor.gray
        if color == "red":
            self.line_color = QtCore.Qt.GlobalColor.red
        if color == "blue":
            self.line_color = QtCore.Qt.GlobalColor.blue
        if color == "green":
            self.line_color = QtCore.Qt.GlobalColor.green
        if color == "cyan":
            self.line_color = QtCore.Qt.GlobalColor.cyan
        if color == "magenta":
            self.line_color = QtCore.Qt.GlobalColor.magenta
        if color == "yellow":
            self.line_color = QtCore.Qt.GlobalColor.yellow

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        menu.addAction(_('Thicker'))
        menu.addAction(_('Thinner'))
        menu.addAction(_('Dotted'))
        menu.addAction(_('Red'))
        menu.addAction(_('Yellow'))
        menu.addAction(_('Green'))
        menu.addAction(_('Blue'))
        menu.addAction(_('Cyan'))
        menu.addAction(_('Magenta'))
        menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action.text() == 'Thicker':
            self.line_width = self.line_width + 0.5
            if self.line_width > 5:
                self.line_width = 5
            self.redraw()
        if action.text() == 'Thinner':
            self.line_width = self.line_width - 0.5
            if self.line_width < 1:
                self.line_width = 1
            self.redraw()
        if action.text() == 'Dotted':
            self.line_type = QtCore.Qt.PenStyle.DotLine
            self.redraw()
        if action.text() == 'Red':
            self.line_color = QtCore.Qt.GlobalColor.red
            self.redraw()
        if action.text() == 'Yellow':
            self.line_color = QtCore.Qt.GlobalColor.yellow
            self.redraw()
        if action.text() == 'Green':
            self.line_color = QtCore.Qt.GlobalColor.green
            self.redraw()
        if action.text() == 'Blue':
            self.line_color = QtCore.Qt.GlobalColor.blue
            self.redraw()
        if action.text() == 'Cyan':
            self.line_color = QtCore.Qt.GlobalColor.cyan
            self.redraw()
        if action.text() == 'Magenta':
            self.line_color = QtCore.Qt.GlobalColor.magenta
            self.redraw()
        if action.text() == "Remove":
            self.remove = True

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
        if not self.corners_only:
            # fix from_x value to middle of from widget if to_widget overlaps in x position
            if to_x > from_x and to_x < from_x + self.from_widget.boundingRect().width():
                from_x = from_x + self.from_widget.boundingRect().width() / 2
                x_overlap = True
            # fix to_x value to middle of to widget if from_widget overlaps in x position
            if from_x > to_x and from_x < to_x + self.to_widget.boundingRect().width():
                to_x = to_x + self.to_widget.boundingRect().width() / 2
                x_overlap = True

        # Fix from_x value to right-hand side of from widget if to_widget on the right of the from_widget
        if not x_overlap and to_x > from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width()
        # Fix to_x value to right-hand side if from_widget on the right of the to widget
        elif not x_overlap and from_x > to_x + self.to_widget.boundingRect().width():
            to_x = to_x + self.to_widget.boundingRect().width()

        y_overlap = False
        if not self.corners_only:
            # Fix from_y value to middle of from widget if to_widget overlaps in y position
            if to_y > from_y and to_y < from_y + self.from_widget.boundingRect().height():
                from_y = from_y + self.from_widget.boundingRect().height() / 2
                y_overlap = True
            # Fix from_y value to middle of to widget if from_widget overlaps in y position
            if from_y > to_y and from_y < to_y + self.to_widget.boundingRect().height():
                to_y = to_y + self.to_widget.boundingRect().height() / 2
                y_overlap = True

        # Fix from_y value if to_widget is above the from_widget
        if not y_overlap and to_y > from_y:
            from_y = from_y + self.from_widget.boundingRect().height()
        # Fix to_y value if from_widget is below the to widget
        elif not y_overlap and from_y > to_y:
            to_y = to_y + self.to_widget.boundingRect().height()

        self.setPen(QtGui.QPen(self.line_color, self.line_width, self.line_type))
        self.setLine(from_x, from_y, to_x, to_y)


class TextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item show the name and color of the code or category
    Categories are typically shown white. A custom context menu
    allows selection of a code/category memo an displaying the information.
    """

    code_or_cat = None
    border_rect = None
    app = None
    font = None
    settings = None
    text = ""

    def __init__(self, app, code_or_cat):
        """ Show name and colour of text. Has context menu for various options.
         param: app  : the main App class
         param: code_or_cat  : Dictionary of the code details: name, memo, color etc """

        super(TextGraphicsItem, self).__init__(None)
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.code_or_cat = code_or_cat
        self.text = self.code_or_cat['name']
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        # Foreground depends on the defined need_white_text color in color_selector
        if self.code_or_cat['cid'] is not None:
            self.font = QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Normal)
            self.setFont(self.font)
            self.setPlainText(self.code_or_cat['name'])
        if self.code_or_cat['cid'] is None:
            self.font = QtGui.QFont(self.settings['font'], 9, QtGui.QFont.Weight.Bold)
            self.setFont(self.font)
            self.setPlainText(self.code_or_cat['name'])
        self.setPos(self.code_or_cat['x'], self.code_or_cat['y'])
        self.document().contentsChanged.connect(self.text_changed)

    def paint(self, painter, option, widget):
        """ see paint override method here:
            https://github.com/jsdir/giza/blob/master/giza/widgets/nodeview/node.py
            see:
            https://doc.qt.io/qt-5/qpainter.html """

        color = QtGui.QColor(self.code_or_cat['color'])
        painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.setFont(self.font)
        fm = painter.fontMetrics()
        painter.setPen(QtGui.QColor(TextColor(self.code_or_cat['color']).recommendation))
        lines = self.code_or_cat['name'].split('\n')
        for row in range(0, len(lines)):
            painter.drawText(5, fm.height() * (row + 1), lines[row])

    def text_changed(self):
        """ Text changed in a node. Redraw the border rectangle item to match. """

        self.code_or_cat['name'] = self.toPlainText()

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        menu.addAction('Memo')
        if self.code_or_cat['cid'] is not None:
            menu.addAction('Coded text and media')
            menu.addAction('Case text and media')
        menu.addAction('Hide')
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action.text() == 'Memo':
            self.add_edit_memo()
        if action.text() == 'Coded text and media':
            self.coded_media()
        if action.text() == 'Case text and media':
            self.case_media()
        if action.text() == "Hide":
            self.hide()

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
    line_color = QtCore.Qt.GlobalColor.gray
    corners_only = False  # True for list graph
    weighting = 1
    text = ""

    def __init__(self, app, from_widget, to_widget, weighting, corners_only=False):
        super(LinkGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.text = from_widget.text + " - " + to_widget.text
        self.corners_only = corners_only
        self.weighting = weighting
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_points_and_draw()
        self.line_color = QtCore.Qt.GlobalColor.gray

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        menu.addAction(_('Thicker'))
        menu.addAction(_('Thinner'))
        menu.addAction(_('Dotted'))
        menu.addAction(_('Red'))
        menu.addAction(_('Yellow'))
        menu.addAction(_('Green'))
        menu.addAction(_('Blue'))
        menu.addAction(_('Cyan'))
        menu.addAction(_('Magenta'))
        menu.addAction(_("Hide"))

        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action.text() == 'Thicker':
            self.line_width = self.line_width + 0.5
            if self.line_width > 5:
                self.line_width = 5
            self.redraw()
        if action.text() == 'Thinner':
            self.line_width = self.line_width - 0.5
            if self.line_width < 1:
                self.line_width = 1
            self.redraw()
        if action.text() == 'Dotted':
            self.line_type = QtCore.Qt.PenStyle.DotLine
            self.redraw()
        if action.text() == 'Red':
            self.line_color = QtCore.Qt.GlobalColor.red
            self.redraw()
        if action.text() == 'Yellow':
            self.line_color = QtCore.Qt.GlobalColor.yellow
            self.redraw()
        if action.text() == 'Green':
            self.line_color = QtCore.Qt.GlobalColor.green
            self.redraw()
        if action.text() == 'Blue':
            self.line_color = QtCore.Qt.GlobalColor.blue
            self.redraw()
        if action.text() == 'Cyan':
            self.line_color = QtCore.Qt.GlobalColor.cyan
            self.redraw()
        if action.text() == 'Magenta':
            self.line_color = QtCore.Qt.GlobalColor.magenta
            self.redraw()
        if action.text() == "Hide":
            self.hide()

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
        if not self.corners_only:
            # fix from_x value to middle of from widget if to_widget overlaps in x position
            if to_x > from_x and to_x < from_x + self.from_widget.boundingRect().width():
                from_x = from_x + self.from_widget.boundingRect().width() / 2
                x_overlap = True
            # fix to_x value to middle of to widget if from_widget overlaps in x position
            if from_x > to_x and from_x < to_x + self.to_widget.boundingRect().width():
                to_x = to_x + self.to_widget.boundingRect().width() / 2
                x_overlap = True

        # Fix from_x value to right-hand side of from widget if to_widget on the right of the from_widget
        if not x_overlap and to_x > from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width()
        # Fix to_x value to right-hand side if from_widget on the right of the to widget
        elif not x_overlap and from_x > to_x + self.to_widget.boundingRect().width():
            to_x = to_x + self.to_widget.boundingRect().width()

        y_overlap = False
        if not self.corners_only:
            # Fix from_y value to middle of from widget if to_widget overlaps in y position
            if to_y > from_y and to_y < from_y + self.from_widget.boundingRect().height():
                from_y = from_y + self.from_widget.boundingRect().height() / 2
                y_overlap = True
            # Fix from_y value to middle of to widget if from_widget overlaps in y position
            if from_y > to_y and from_y < to_y + self.to_widget.boundingRect().height():
                to_y = to_y + self.to_widget.boundingRect().height() / 2
                y_overlap = True

        # Fix from_y value if to_widget is above the from_widget
        if not y_overlap and to_y > from_y:
            from_y = from_y + self.from_widget.boundingRect().height()
        # Fix to_y value if from_widget is below the to widget
        elif not y_overlap and from_y > to_y:
            to_y = to_y + self.to_widget.boundingRect().height()

        self.setPen(QtGui.QPen(self.line_color, self.line_width, self.line_type))
        self.setLine(from_x, from_y, to_x, to_y)


'''def circular_graph(self):
    """ Create a circular acyclic graph
    """

    self.scene.clear()
    cats, codes, model = self.create_initial_model()
    catid_counts, model = self.get_refined_model_with_depth_and_category_counts(cats, model)

    # assign angles to each item segment
    for cat_key in catid_counts.keys():
        segment = 1
        for m in model:
            if m['angle'] is None and m['supercatid'] == cat_key:
                m['angle'] = (2 * math.pi / catid_counts[m['supercatid']]) * (segment + 1)
                segment += 1
    # Calculate x y positions from central point outwards.
    # The 'central' x value is towards the left side rather than true center, because
    # the text boxes will draw to the right-hand side.
    c_x = self.scene.get_width() / 3
    c_y = self.scene.get_height() / 2
    r = 220
    rx_expander = c_x / c_y  # Screen is landscape, so stretch x position
    x_is_none = True
    i = 0
    while x_is_none and i < 1000:
        x_is_none = False
        for m in model:
            if m['x'] is None and m['supercatid'] is None:
                m['x'] = c_x + (math.cos(m['angle']) * (r * rx_expander))
                m['y'] = c_y + (math.sin(m['angle']) * r)
            if m['x'] is None and m['supercatid'] is not None:
                for super_m in model:
                    if super_m['catid'] == m['supercatid'] and super_m['x'] is not None:
                        m['x'] = super_m['x'] + (math.cos(m['angle']) * (r * rx_expander) / (m['depth'] + 2))
                        m['y'] = super_m['y'] + (math.sin(m['angle']) * r / (m['depth'] + 2))
                        if abs(super_m['x'] - m['x']) < 20 and abs(super_m['y'] - m['y']) < 20:
                            m['x'] += 20
                            m['y'] += 20
            if m['x'] is None:
                x_is_none = True
        i += 1

    # Fix out of view items
    for m in model:
        m['child_names'] = self.named_children_of_node(m)
        if m['x'] < 2:
            m['x'] = 2
        if m['y'] < 2:
            m['y'] = 2
        if m['x'] > c_x * 2 - 20:
            m['x'] = c_x * 2 - 20
        if m['y'] > c_y * 2 - 20:
            m['y'] = c_y * 2 - 20

    # Add text items to the scene
    for m in model:
        self.scene.addItem(TextGraphicsItem(self.app, m))
    # Add link which includes the scene text items and associated data, add links before text_items
    for m in self.scene.items():
        if isinstance(m, TextGraphicsItem):
            for n in self.scene.items():
                if isinstance(n, TextGraphicsItem) and m.code_or_cat['supercatid'] is not None and \
                        m.code_or_cat['supercatid'] == n.code_or_cat['catid'] and \
                        n.code_or_cat['depth'] < m.code_or_cat['depth']:
                    item = LinkGraphicsItem(self.app, m, n, 1)
                    self.scene.addItem(item)

def show_graph_type(self):

    if self.ui.checkBox_listview.isChecked():
        self.list_graph()
    else:
        self.circular_graph()'''
