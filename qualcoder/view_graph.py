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
import datetime
import logging
import os
import sqlite3
import sys
import traceback

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog

from .color_selector import TextColor
from .confirm_delete import DialogConfirmDelete
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
        self.ui.pushButton_loadgraph.pressed.connect(self.load_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(arrow_down_icon), "png")
        self.ui.pushButton_savegraph.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_savegraph.pressed.connect(self.save_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(delete_icon), "png")
        self.ui.pushButton_deletegraph.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_deletegraph.pressed.connect(self.delete_saved_graph)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.pushButton_codes_of_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_codes_of_file.pressed.connect(self.show_codes_of_file)

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
        # TODO catid_count is NOT used
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
            #code_['depth'] = 0
            code_['x'] = None
            code_['y'] = None
            code_['supercatid'] = code_['catid']
        for cat in cats:
            #cat['depth'] = 0
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

        # Determine the number of children for each catid.
        supercatid_list = []
        for c in model:
            #depth = 0
            supercatid = c['supercatid']
            supercatid_list.append(c['supercatid'])
            count = 0
            while not (supercatid is None or count > 10000):
                for s in cats:
                    if supercatid == s['catid']:
                        #depth += 1
                        supercatid = s['supercatid']
                #c['depth'] = depth
                count += 1
        # TODO  catid_counts not used
        catid_counts = Counter(supercatid_list)
        return model, catid_counts

    def get_refined_model(self, node, model):
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
        for m in model:
            if m['x'] is None and m['supercatid'] is None:
                m['x'] = 10
                ordered_model.append(m)
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

        # Add link from Category to Category, which includes the scene text items and associated data
        for m in self.scene.items():
            if isinstance(m, TextGraphicsItem):
                for n in self.scene.items():
                    if isinstance(n, TextGraphicsItem) and m.code_or_cat['supercatid'] is not None and \
                            m.code_or_cat['supercatid'] == n.code_or_cat['catid'] and \
                            (m.code_or_cat['cid'] is None and n.code_or_cat['cid'] is None):
                        item = LinkGraphicsItem(self.app, m, n, 1, True)
                        self.scene.addItem(item)
        # Add links from Codes to Categories
        for m in self.scene.items():
            if isinstance(m, TextGraphicsItem):
                for n in self.scene.items():
                    # Link the n Codes to m Categories
                    if isinstance(n, TextGraphicsItem) and n.code_or_cat['cid'] is not None and \
                            m.code_or_cat['cid'] is None and \
                            m.code_or_cat['catid'] == n.code_or_cat['catid']:
                        item = LinkGraphicsItem(self.app, m, n, 1, True)
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
        action_add_text_item = menu.addAction(_("Insert Text"))
        action_add_line = menu.addAction(_("Insert Line"))
        action_add_files = menu.addAction(_("Show files"))
        action_add_cases = menu.addAction(_("Show cases"))
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        if action == action_add_text_item:
            self.add_text_item_to_graph(position.x(), position.y())
        if action == action_add_line:
            self.add_lines_to_graph()
        if action == action_add_files:
            self.add_files_to_graph()
        if action == action_add_cases:
            self.add_cases_to_graph()

    def show_codes_of_file(self):
        """ Show selected codes of selected file in free text items. """

        print("TODO show codes of files")

    def add_lines_to_graph(self):
        """ Add one or more free lines from an item to one or more destination items. """

        # From item selection
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

        # Create Free Item lines
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
            cur.execute("insert into graph (name, description, date, scene_width, scene_height) values(?,?,?,?,?)",
                        [name, description, now_date, width, height])
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            Message(self.app, _("Name error"), _("This name already used. Choose another name.")).exec()
            return
        cur.execute("select last_insert_rowid()")
        grid = cur.fetchone()[0]
        for i in self.scene.items():
            if isinstance(i, TextGraphicsItem):
                sql = "insert into gr_cdct_text_item (grid,x,y,supercatid,catid,cid,font_size,bold,isvisible) values (?,?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid,i.pos().x(), i.pos().y(), i.code_or_cat['supercatid'], i.code_or_cat['catid'],
                                  i.code_or_cat['cid'], i.font_size, i.bold, i.isVisible()])
                self.app.conn.commit()
            if isinstance(i, FreeTextGraphicsItem):
                sql = "insert into gr_free_text_item (grid,x,y,free_text,font_size,bold,color) values (?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.pos().x(), i.pos().y(), i.text, i.font_size, i.bold, i.color])
                self.app.conn.commit()
            if isinstance(i, CaseTextGraphicsItem):
                sql = "insert into gr_case_text_item (grid,x,y,caseid,font_size,bold,color) values (?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.pos().x(), i.pos().y(), i.case_id, i.font_size, i.bold, i.color])
                self.app.conn.commit()
            if isinstance(i, FileTextGraphicsItem):
                sql = "insert into gr_file_text_item (grid,x,y,fid,font_size,bold,color) values (?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.pos().x(), i.pos().y(), i.file_id, i.font_size, i.bold, i.color])
                self.app.conn.commit()
            if isinstance(i, LinkGraphicsItem):
                '''print("LinkGraphicsItem grid:", grid, "fromcatid", i.from_widget.code_or_cat['catid'],
                      "fromcid", i.from_widget.code_or_cat['cid'], "tocatid", i.to_widget.code_or_cat['catid'],
                      "tocid", i.to_widget.code_or_cat['cid'],
                      "color", i.color, "width", i.line_width, "type", i.line_type, "isvisible", i.isVisible())'''
                sql = "insert into gr_cdct_line_item (grid,fromcatid,fromcid,tocatid,tocid,color,linewidth,linetype," \
                      "isvisible) values (?,?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.from_widget.code_or_cat['catid'], i.from_widget.code_or_cat['cid'],
                                  i.to_widget.code_or_cat['catid'], i.to_widget.code_or_cat['cid'],
                                  self.color_to_text(i.color), i.line_width, self.line_type_to_text(i.line_type),
                                  i.isVisible()])
                self.app.conn.commit()
                
            if isinstance(i, FreeLineGraphicsItem):
                print("Saving FreeLineGraphicsItem")
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
                """ Free line linking options use catid/cid or caseid or fileid and last match text e.g. freetextitem """
                sql = "insert into gr_free_line_item (grid,fromtext,fromcatid,fromcid,fromcaseid,fromfileid, " \
                      "totext,tocatid,tocid,tocaseid,tofileid,color, linewidth,linetype) " \
                      "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.from_widget.text, from_catid, from_cid, from_case_id, from_file_id,
                                  i.to_widget.text, to_catid, to_cid, to_case_id, to_file_id,
                                  self.color_to_text(i.color), i.line_width, self.line_type_to_text(i.line_type)])
                self.app.conn.commit()
        self.app.delete_backup = False

    def color_to_text(self, global_color):
        """ Convert global color to text.
        For graph_line_items. """

        text_color = "gray"
        if global_color == QtCore.Qt.GlobalColor.blue:
            text_color = "blue"
        if global_color == QtCore.Qt.GlobalColor.cyan:
            text_color = "cyan"
        if global_color == QtCore.Qt.GlobalColor.green:
            text_color = "green"
        if global_color == QtCore.Qt.GlobalColor.magenta:
            text_color = "magenta"
        if global_color == QtCore.Qt.GlobalColor.red:
            text_color = "red"
        if global_color == QtCore.Qt.GlobalColor.yellow:
            text_color = "yellow"
        return text_color

    def line_type_to_text(self, line_type):
        """ Convert line type to text. for graph line items. """

        text_ = "solid"
        if line_type == QtCore.Qt.PenStyle.DotLine:
            text_ = "dotted"
        return text_

    def load_graph(self):
        """ Load a saved graph.
        Load each text component first then link then the cdct_line_items then the free_lines_items.
        For cdct_text_items, fill extra details:
        eg name, memo, date?, owner?, color, child_names?
        """

        cur = self.app.conn.cursor()
        cur.execute("select name, grid, description, scene_width, scene_height from graph order by upper(name)")
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
        grid = graph['grid']
        self.scene.clear()
        self.scene.set_width(graph['width'])
        self.scene.set_height(graph['height'])
        err_msg = ""
        err_msg = self.load_code_or_cat_text_graphics_items(grid)
        err_msg += self.load_file_text_graphics_items(grid)
        err_msg += self.load_case_text_graphics_items(grid)
        err_msg += self.load_free_text_graphics_items(grid)
        err_msg += self.load_cdct_line_graphics_items(grid)
        err_msg += self.load_free_line_graphics_items(grid)
        if err_msg != "":
            Message(self.app, _("Load graph errors"), err_msg).exec()
        self.ui.label_loaded_graph.setText(graph['name'])
        self.ui.label_loaded_graph.setToolTip(graph['description'])

    def load_cdct_line_graphics_items(self, grid):
        """ Find the to and from widgets using matching catid and cid.
          Then when found add the line item. """

        err_msg = ""
        sql = "select fromcatid,fromcid,tocatid,tocid,linewidth,linetype,color," \
              "isvisible from gr_cdct_line_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        res = cur.fetchall()
        for line in res:
            #print("CDCT_LINE:", line)
            # Add link which includes the scene text items and associated data, add links before text_items
            from_item = None
            to_item = None
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    if from_item is None and i.code_or_cat['catid'] == line[0] and i.code_or_cat['cid'] == line[1]:
                        from_item = i
                    if to_item is None and i.code_or_cat['catid'] == line[2] and i.code_or_cat['cid'] == line[3]:
                        to_item = i
            #print(from_item, to_item)
            if from_item is not None and to_item is not None:
                item = LinkGraphicsItem(self.app, from_item, to_item, line[4], line[5], line[6], line[7])
                self.scene.addItem(item)
            if from_item is None:
                err_msg += "\n" + _("Link line. No from item. ") + "Catid:" + str(line[0]) + " Cid:" + str(line[1])
            if to_item is None:
                err_msg += "\n" + _("Link line. No to item. ") + "Catid:" + str(line[2]) + " Cid:" + str(line[3])
        return err_msg

    def load_free_line_graphics_items(self, grid):
        """ Find the to and from widgets.
        Several matching options: catid and cid; fileid; caseid; text (last option).
        Then when found add the free line item. """

        err_msg = ""
        sql = "select fromtext,fromcatid,fromcid,fromcaseid,fromfileid,totext,tocatid,tocid,tocaseid,tofileid," \
              "color, linewidth,linetype from gr_free_line_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        result = cur.fetchall()
        res = []
        keys = "fromtext", "fromcatid", "fromcid", "fromcaseid", "fromfileid", "totext", "tocatid", "tocid", \
               "tocaseid", "tofileid", "color", "linewidth", "linetype"
        for row in result:
            res.append(dict(zip(keys, row)))
        for line in res:
            # Add link which includes the scene text items and associated data, add links before text_items
            from_item = None
            to_item = None
            # Check for each text item type and try to get a mathing characteristic
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
                if from_item is None and line['fromcaseid'] is None and line['fromfileid'] is None and \
                        line['fromcatid'] is None and line['fromcid'] is None and isinstance(i, FreeTextGraphicsItem):
                    if line['fromtext'] == i.text:
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
                if to_item is None and line['tocaseid'] is None and line['tofileid'] is None and \
                        line['tocatid'] is None and line['tocid'] is None and isinstance(i, FreeTextGraphicsItem):
                    if line['totext'] == i.text:
                        to_item = i
            if from_item is not None and to_item is not None:
                line_item = FreeLineGraphicsItem(self.app, from_item, to_item, line['color'], line['linewidth'],
                                                 line['linetype'])
                self.scene.addItem(line_item)
            if from_item is None:
                err_msg += "\n" + _("Link Line. No From item. ")
            if to_item is None:
                err_msg += "\n" + _("Link line. No To item. ")
        return err_msg

    def load_case_text_graphics_items(self, grid):
        """ Load the case graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_case = "select x, y, caseid,font_size, color, bold from gr_case_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_case, [grid])
        res_case = cur.fetchall()
        for i in res_case:
            cur.execute("select name, memo from cases where caseid=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(CaseTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5]))
            else:
                err_msg += _("Case: ") + str(i[2]) + " "
        return err_msg

    def load_file_text_graphics_items(self, grid):
        """ Load the file graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_file = "select x, y, fid, font_size, bold, color from gr_file_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_file, [grid])
        res_file = cur.fetchall()
        for i in res_file:
            cur.execute("select name, memo from source where id=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(FileTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5]))
            else:
                err_msg += _("File: ") + str(i[2]) + " "
        return err_msg

    def load_free_text_graphics_items(self, grid):
        """ Load the free text graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql = "select x, y, free_text, font_size, color, bold from gr_free_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        res = cur.fetchall()
        for i in res:
            #TODO check for duplicated text
            self.scene.addItem(FreeTextGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5]))
        return err_msg

    def load_code_or_cat_text_graphics_items(self, grid):
        """ Load the code or category graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_cdct = "select x, y, supercatid, catid, cid, font_size, bold, isvisible from gr_cdct_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_cdct, [grid])
        res_cdct = cur.fetchall()
        for i in res_cdct:
            name = ""
            color = '#FFFFFF'  # Default / needed for category items
            memo = ""
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
                        'color': color}
                cdct['child_names'] = self.named_children_of_node(cdct)
                self.scene.addItem(TextGraphicsItem(self.app, cdct, i[5], i[6], i[7]))
            else:
                # Code or category has been deleted
                cdcat = _("Category")
                if i[4] is not None:
                    cdcat = _("Code")
                err_msg += cdcat + _(" does not exist: ") + str(i[3]) + " " + str(i[4]) + " "
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
        for s in selection:
            cur.execute("delete from graph where grid = ?", [s['grid']])
            cur.execute("delete from gr_case_text_item where grid = ?", [s['grid']])
            cur.execute("delete from gr_file_text_item where grid = ?", [s['grid']])
            cur.execute("delete from gr_free_line_item where grid = ?", [s['grid']])
            cur.execute("delete from gr_free_text_item where grid = ?", [s['grid']])
            cur.execute("delete from gr_cdct_line_item where grid = ?", [s['grid']])
            cur.execute("delete from gr_cdct_text_item where grid = ?", [s['grid']])
            self.app.conn.commit()
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

    app = None
    settings = None
    text = ""
    show_attributes = False
    remove = False
    # For graph item storage
    font_size = 9
    case_id = -1
    color = ""
    bold = False

    def __init__(self, app, case_name, case_id, x=0, y=0, font_size=9, color="", bold=False):
        """ Show name and optionally attributes.
        param: app  : the main App class
        param: case_name : String
        param: case_id : Integer
        param: x : Integer
        param: y : Integer
        param: color : String
        param: bold : boolean
        """

        super(CaseTextGraphicsItem, self).__init__(None)
        self.setToolTip(_("Case"))
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.case_id = case_id
        self.text = case_name
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.show_attributes = False
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPlainText(self.text)
        self.setPos(x, y)
        cur = self.app.conn.cursor()
        cur.execute("select memo from cases where caseid=?", [case_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("Case") + ": " + res[0])
        self.setDefaultTextColor(QtCore.Qt.GlobalColor.black)
        if self.app.settings['stylesheet'] == 'dark':
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.white)
        if self.color == "red":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
        if self.color == "green":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.green)
        if self.color == "blue":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.blue)
        if self.color == "yellow":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.yellow)

    def paint(self, painter, option, widget):
        """ """

        painter.save()
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
        font_larger_action = menu.addAction(_("Larger font"))
        font_smaller_action = menu.addAction(_("Smaller font"))
        bold_action = menu.addAction(_("Bold toggle"))
        red_action = menu.addAction(_("Red text"))
        green_action = menu.addAction(_("Green text"))
        yellow_action = menu.addAction(_("Yellow text"))
        blue_action = menu.addAction(_("Blue text"))
        default_color_action = menu.addAction(_("Default colour text"))
        if self.show_attributes:
            hide_att_action = menu.addAction(_('Hide attributes'))
        else:
            show_att_action = menu.addAction(_('Show attributes'))
        remove_action = menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == font_larger_action:
            self.font_size += 2
            if self.font_size > 40:
                self.font_size = 40
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, QtGui.QFont.Weight.Normal))
        if action == font_smaller_action:
            self.font_size -= 2
            if self.font_size < 6:
                self.font_size = 6
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, QtGui.QFont.Weight.Normal))
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == red_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
            self.color = "red"
        if action == green_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.green)
            self.color = "green"
        if action == yellow_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.yellow)
            self.color = "yellow"
        if action == blue_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.blue)
            self.color = "blue"
        if action == default_color_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.black)
            if self.app.settings['stylesheet'] == 'dark':
                self.setDefaultTextColor(QtCore.Qt.GlobalColor.white)
        if action == remove_action:
            self.remove = True
        if action == show_att_action:
            self.show_attributes = True
            self.setHtml(self.text + self.get_attributes())
        if action == hide_att_action:
            self.show_attributes = False
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
    color = ""
    bold = False

    def __init__(self, app, file_name, file_id, x=0, y=0, font_size=9, color="", bold=False):
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
        self.text = file_name
        self.font_size = font_size
        self.color = color
        self.show_attributes = False
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPos(x, y)
        cur = self.app.conn.cursor()
        cur.execute("select memo from source where id=?", [file_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("File") + ": " + res[0])
        self.setPlainText(self.text)
        self.setDefaultTextColor(QtCore.Qt.GlobalColor.black)
        if self.app.settings['stylesheet'] == 'dark':
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.white)
        if self.color == "red":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
        if self.color == "green":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.green)
        if self.color == "blue":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.blue)
        if self.color == "yellow":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.yellow)

    def paint(self, painter, option, widget):
        """ """

        painter.save()
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
        bold_action = menu.addAction(_("Bold toggle"))
        font_larger_action = menu.addAction(_("Larger font"))
        font_smaller_action = menu.addAction(_("Smaller font"))
        red_action = menu.addAction(_("Red text"))
        green_action = menu.addAction(_("Green text"))
        yellow_action = menu.addAction(_("Yellow text"))
        blue_action = menu.addAction(_("Blue text"))
        default_color_action = menu.addAction(_("Default colour text"))
        if self.show_attributes:
            hide_att_action = menu.addAction(_('Hide attributes'))
        else:
            show_att_action = menu.addAction(_('Show attributes'))
        remove_action = menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == font_larger_action:
            self.font_size += 2
            if self.font_size > 40:
                self.font_size = 40
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == font_smaller_action:
            self.font_size -= 2
            if self.font_size < 6:
                self.font_size = 6
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == remove_action:
            self.remove = True
        if action == red_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
            self.color = "red"
        if action == green_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.green)
            self.color = "green"
        if action == yellow_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.yellow)
            self.color = "yellow"
        if action == blue_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.blue)
            self.color = "blue"
        if action == default_color_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.black)
            if self.app.settings['stylesheet'] == 'dark':
                self.setDefaultTextColor(QtCore.Qt.GlobalColor.white)
        if action == show_att_action:
            self.setHtml(self.text + self.get_attributes())
            self.show_attributes = True
        if action == hide_att_action:
            self.setPlainText(self.text)
            self.show_attributes = False

    def get_attributes(self):
        """ Get attributes for the file.  Add to text document. """

        attribute_text = ""
        cur = self.app.conn.cursor()
        sql = "SELECT name, value FROM  attribute where attr_type='file' and id=? order by name"
        cur.execute(sql, [self.file_id])
        result = cur.fetchall()
        for r in result:
            attribute_text += '<br>' + r[0] + ": " + r[1]
        return attribute_text


class FreeTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ Free text to add to the scene. """

    app = None
    font = None
    settings = None
    remove = False
    # For graph item storage
    text = "text"
    font_size = 9
    color = ""
    bold = False
    MAX_WIDTH = 300
    MAX_HEIGHT = 300

    def __init__(self, app, x=10, y=10, text_="text", font_size=9, color="", bold=False):
        """ Free text object.
         param:
            app  : the main App class
            x : Integer x position
            y : Intger y position
            text_ : String
            color : String
            bold : boolean
         """

        super(FreeTextGraphicsItem, self).__init__(None)
        self.app = app
        self.setPos(x, y)
        self.text = text_
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, QtGui.QFont.Weight.Normal))
        self.setPlainText(self.text)
        self.setDefaultTextColor(QtCore.Qt.GlobalColor.black)
        if self.app.settings['stylesheet'] == 'dark':
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.white)
        if self.color == "red":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
        if self.color == "green":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.green)
        if self.color == "blue":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.blue)
        if self.color == "yellow":
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.yellow)
        if self.boundingRect().width() > self.MAX_WIDTH:
            self.setTextWidth(self.MAX_WIDTH)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        bold_action = menu.addAction(_("Bold toggle"))
        font_larger_action = menu.addAction(_("Larger font"))
        font_smaller_action = menu.addAction(_("Smaller font"))
        remove_action = menu.addAction(_('Remove'))
        red_action = menu.addAction(_("Red text"))
        green_action = menu.addAction(_("Green text"))
        yellow_action = menu.addAction(_("Yellow text"))
        blue_action = menu.addAction(_("Blue text"))
        default_color_action = menu.addAction(_("Default colour text"))

        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == remove_action:
            self.remove = True
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == font_larger_action:
            self.font_size += 2
            if self.font_size > 40:
                self.font_size = 40
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == font_smaller_action:
            self.font_size -= 2
            if self.font_size < 6:
                self.font_size = 6
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == red_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.red)
            self.color = "red"
        if action == green_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.green)
            self.color = "green"
        if action == yellow_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.yellow)
            self.color = "yellow"
        if action == blue_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.blue)
            self.color = "blue"
        if action == default_color_action:
            self.setDefaultTextColor(QtCore.Qt.GlobalColor.black)
            if self.app.settings['stylesheet'] == 'dark':
                self.setDefaultTextColor(QtCore.Qt.GlobalColor.white)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class FreeLineGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Takes the coordinate from two TextGraphicsItems. """

    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None
    line_width = 2
    line_type = QtCore.Qt.PenStyle.SolidLine
    color = QtCore.Qt.GlobalColor.gray
    tooltip = ""
    remove = False

    def __init__(self, app, from_widget, to_widget, color="gray", line_width=2, line_type="solid"):
        super(FreeLineGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.line_width = line_width
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_points_and_draw()
        self.color = QtCore.Qt.GlobalColor.gray
        if color == "red":
            self.color = QtCore.Qt.GlobalColor.red
        if color == "blue":
            self.color = QtCore.Qt.GlobalColor.blue
        if color == "green":
            self.color = QtCore.Qt.GlobalColor.green
        if color == "cyan":
            self.color = QtCore.Qt.GlobalColor.cyan
        if color == "magenta":
            self.color = QtCore.Qt.GlobalColor.magenta
        if color == "yellow":
            self.color = QtCore.Qt.GlobalColor.yellow
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        thicker_action = menu.addAction(_('Thicker'))
        thinner_action = menu.addAction(_('Thinner'))
        dotted_action = menu.addAction(_('Dotted'))
        red_action = menu.addAction(_('Red'))
        yellow_action = menu.addAction(_('Yellow'))
        green_action = menu.addAction(_('Green'))
        blue_action = menu.addAction(_('Blue'))
        cyan_action = menu.addAction(_('Cyan'))
        magenta_action = menu.addAction(_('Magenta'))
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == thicker_action:
            self.line_width = self.line_width + 0.5
            if self.line_width > 5:
                self.line_width = 5
            self.redraw()
        if action == thinner_action:
            self.line_width = self.line_width - 0.5
            if self.line_width < 2:
                self.line_width = 2
            self.redraw()
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
            self.redraw()
        if action == red_action:
            self.color = QtCore.Qt.GlobalColor.red
            self.redraw()
        if action == yellow_action:
            self.color = QtCore.Qt.GlobalColor.yellow
            self.redraw()
        if action == green_action:
            self.color = QtCore.Qt.GlobalColor.green
            self.redraw()
        if action == blue_action:
            self.color = QtCore.Qt.GlobalColor.blue
            self.redraw()
        if action == cyan_action:
            self.color = QtCore.Qt.GlobalColor.cyan
            self.redraw()
        if action == magenta_action:
            self.color = QtCore.Qt.GlobalColor.magenta
            self.redraw()
        if action == remove_action:
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

        self.setPen(QtGui.QPen(self.color, self.line_width, self.line_type))
        self.setLine(from_x, from_y, to_x, to_y)


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

    def __init__(self, app, code_or_cat, font_size=9, bold=False, isvisible=True):
        """ Show name and colour of text. Has context menu for various options.
         param: app  : the main App class
         param: code_or_cat  : Dictionary of the code details: name, memo, color etc
         param: font_size : Integer
         param: bold : boolean
         parap: isvisible : boolean
         """

        super(TextGraphicsItem, self).__init__(None)
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.code_or_cat = code_or_cat
        self.font_size = font_size
        self.bold = bold
        self.setPos(self.code_or_cat['x'], self.code_or_cat['y'])
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
        cur = self.app.conn.cursor()
        if self.code_or_cat['cid'] is not None:
            cur.execute("select memo from code_name where name=?", [self.code_or_cat['name']])
            res = cur.fetchone()
            if res:
                self.setToolTip(_("Code") + ": " + res[0])
            else:
                self.setToolTip(_("Code"))
        else:
            cur.execute("select memo from code_cat where name=?", [self.code_or_cat['name']])
            res = cur.fetchone()
            if res:
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
        memo_action = menu.addAction('Memo')
        coded_action = None
        case_action = None
        if self.code_or_cat['cid'] is not None:
            coded_action = menu.addAction('Coded text and media')
            case_action = menu.addAction('Case text and media')
        font_larger_action = menu.addAction(_("Larger font"))
        font_smaller_action = menu.addAction(_("Smaller font"))
        bold_action = menu.addAction(_("Bold toggle"))
        hide_action = menu.addAction('Hide')
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == font_larger_action:
            self.font_size += 2
            if self.font_size > 40:
                self.font_size = 40
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == font_smaller_action:
            self.font_size -= 2
            if self.font_size < 6:
                self.font_size = 6
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == memo_action:
            self.add_edit_memo()
        if action == coded_action:
            self.coded_media()
        if action == case_action:
            self.case_media()
        if action == hide_action:
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

    app = None  # not used yet
    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None
    line_width = 2
    line_type = QtCore.Qt.PenStyle.SolidLine
    color = QtCore.Qt.GlobalColor.gray
    text = ""

    def __init__(self, app, from_widget, to_widget, line_width=2, line_type="solid",
                 color="", isvisible=True):
        """ app is not used yet.
        param: app  : the main App class
         param: from_widget  : TextGraphicsItem
         param: to_widget : TextGraphicsItem
         param: line_width : Real
         param: line_type : String
         param: color : String
         param: isvisible : boolean
        """
        super(LinkGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.text = from_widget.text + " - " + to_widget.text
        self.line_width = line_width
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_points_and_draw()
        self.color = QtCore.Qt.GlobalColor.gray
        if color == "blue":
            self.color = QtCore.Qt.GlobalColor.blue
        if color == "cyan":
            self.color = QtCore.Qt.GlobalColor.cyan
        if color == "green":
            self.color = QtCore.Qt.GlobalColor.green
        if color == "magenta":
            self.color = QtCore.Qt.GlobalColor.magenta
        if color == "red":
            self.color = QtCore.Qt.GlobalColor.red
        if color == "yellow":
            self.color = QtCore.Qt.GlobalColor.yellow
        if not isvisible:
            self.hide()
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()

        thicker_action = menu.addAction(_('Thicker'))
        thinner_action = menu.addAction(_('Thinner'))
        dotted_action = menu.addAction(_('Dotted'))
        red_action = menu.addAction(_('Red'))
        yellow_action = menu.addAction(_('Yellow'))
        green_action = menu.addAction(_('Green'))
        blue_action = menu.addAction(_('Blue'))
        cyan_action = menu.addAction(_('Cyan'))
        magenta_action = menu.addAction(_('Magenta'))
        hide_action = menu.addAction(_('Hide'))

        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == thicker_action:
            self.line_width = self.line_width + 0.5
            if self.line_width > 5:
                self.line_width = 5
            self.redraw()
        if action == thinner_action:
            self.line_width = self.line_width - 0.5
            if self.line_width < 2:
                self.line_width = 2
            self.redraw()
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
            self.redraw()
        if action == red_action:
            self.color = QtCore.Qt.GlobalColor.red
            self.redraw()
        if action == yellow_action:
            self.color = QtCore.Qt.GlobalColor.yellow
            self.redraw()
        if action == green_action:
            self.color = QtCore.Qt.GlobalColor.green
            self.redraw()
        if action == blue_action:
            self.color = QtCore.Qt.GlobalColor.blue
            self.redraw()
        if action == cyan_action:
            self.color = QtCore.Qt.GlobalColor.cyan
            self.redraw()
        if action == magenta_action:
            self.color = QtCore.Qt.GlobalColor.magenta
            self.redraw()
        if action == hide_action:
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
        #if True:
        # Fix from_x value to middle of from widget if to_widget overlaps in x position
        if to_x > from_x and to_x < from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width() / 2
            x_overlap = True
        # Fix to_x value to middle of to widget if from_widget overlaps in x position
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
        #if True:
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

        self.setPen(QtGui.QPen(self.color, self.line_width, self.line_type))
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
