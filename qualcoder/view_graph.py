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
from .helpers import DialogCodeInAV, DialogCodeInImage, DialogCodeInAllFiles, DialogCodeInText, \
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
    load_graph_menu_option = "Alphabet ascending"

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
        self.ui.pushButton_loadgraph.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.pushButton_loadgraph.customContextMenuRequested.connect(self.load_graph_menu)
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
        self.ui.pushButton_codes_of_text.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_codes_of_text.pressed.connect(self.show_codes_of_text_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(picture), "png")
        self.ui.pushButton_codes_of_images.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_codes_of_images.pressed.connect(self.show_codes_of_image_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
        self.ui.pushButton_codes_of_av.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_codes_of_av.pressed.connect(self.show_codes_of_av_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_grid_icon_24), "png")
        self.ui.pushButton_memos_of_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_memos_of_file.pressed.connect(self.show_memos_of_file)

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
        model = self.get_refined_model_with_category_counts(cats, model, node_text)
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

        # Determine the number of children for each catid.
        # catcounts not used
        '''supercatid_list = []
        for c in model:
            supercatid = c['supercatid']
            supercatid_list.append(c['supercatid'])
            count = 0
            while not (supercatid is None or count > 10000):
                for s in cats:
                    if supercatid == s['catid']:
                        supercatid = s['supercatid']
                count += 1
        catid_counts = Counter(supercatid_list)'''
        return model

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
                        item = LinkGraphicsItem(self.app, m, n, 2, True)
                        self.scene.addItem(item)
        # Add links from Codes to Categories
        for m in self.scene.items():
            if isinstance(m, TextGraphicsItem):
                for n in self.scene.items():
                    # Link the n Codes to m Categories
                    if isinstance(n, TextGraphicsItem) and n.code_or_cat['cid'] is not None and \
                            m.code_or_cat['cid'] is None and \
                            m.code_or_cat['catid'] == n.code_or_cat['catid']:
                        item = LinkGraphicsItem(self.app, m, n, 2, True)
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
        action_add_coded_text = menu.addAction(_("Insert coded text items"))
        action_add_coded_image = menu.addAction(_("Insert coded image items"))
        action_add_coded_av = menu.addAction(_("Insert coded A/V items"))
        action_add_files = menu.addAction(_("Show files"))
        action_add_cases = menu.addAction(_("Show cases"))
        action_memos = menu.addAction(_("Show memos of coded segments"))
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        if action == action_add_text_item:
            self.add_text_item_to_graph(position.x(), position.y())
        if action == action_add_coded_text:
            self.show_codes_of_text_files(position.x(), position.y())
        if action == action_add_coded_image:
            self.show_codes_of_image_files(position.x(), position.y())
        if action == action_add_coded_av:
            self.show_codes_of_av_files(position.x(), position.y())
        if action == action_memos:
            self.show_memos_of_file(position.x(), position.y())
        if action == action_add_line:
            self.add_lines_to_graph()
        if action == action_add_files:
            self.add_files_to_graph()
        if action == action_add_cases:
            self.add_cases_to_graph()

    def show_codes_of_av_files(self, x=10, y=10):
        """ Show selected codes of selected audio/video files as av graphics items. """

        # Select files
        files_wth_names = self.app.get_av_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select audio/video files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_files = ui.get_selected()
        # Select codes
        code_names = self.app.get_code_names()
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []
        cur = self.app.conn.cursor()
        for file_ in selected_files:
            cur.execute("select mediapath from source where id=?", [file_['id']])
            file_['path'] = ""
            pth = cur.fetchone()
            if pth:
                file_['path'] = pth[0]
            for code in selected_codes:
                sql = "select cid,id,pos0,pos1, memo, avid from code_av where cid=? and id=?"
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    name = file_['name'] + ' x:' + str(int(r[2])) + ' y:' + str(int(r[3]))

                    codings.append({'cid': r[0], 'fid': r[1], 'pos0': int(r[2]), 'pos1': int(r[3]),
                                    'memo': r[4], 'filename': file_['name'],
                                    'codename': code['name'], 'name': name,
                                    'path': file_['path'], 'avid': r[5]})
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
            msg = "AVID:" + str(s['avid']) + " " + _("File: ") + s['filename'] + "\n" + _("Code: ") + s['codename']
            msg += "\n" + str(s['pos0']) + " - " + str(s['pos1']) + _("msecs")
            if s['memo'] != "":
                msg += "\n" + _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)

    def show_codes_of_image_files(self, x=10, y=10):
        """ Show selected codes of selected image files as pixmap graphics items. """

        # Select files
        files_wth_names = self.app.get_image_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select image files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_files = ui.get_selected()
        # Select codes
        code_names = self.app.get_code_names()
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []
        cur = self.app.conn.cursor()
        for file_ in selected_files:
            cur.execute("select mediapath from source where id=?", [file_['id']])
            file_['path'] = ""
            p = cur.fetchone()
            if p:
                file_['path'] = p[0]
            for code in selected_codes:
                sql = "select cid,id,x1,y1,width,height,memo, imid from code_image where cid=? and id=?"
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    name = file_['name'] + ' x:' + str(int(r[2])) + ' y:' + str(int(r[3]))
                    name += _(" width") + str(int(r[4])) + _(" height:") + str(int(r[5]))
                    codings.append({'cid': r[0], 'fid': r[1], 'x': int(r[2]), 'y': int(r[3]), 'width': int(r[4]),
                                    'height': int(r[5]), 'memo': r[6], 'filename': file_['name'],
                                    'codename': code['name'], 'name': name,
                                    'path': file_['path'], 'imid': r[7]})
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
            item = PixmapGraphicsItem(self.app, s['imid'], x, y, s['x'], s['y'], s['width'], s['height'], s['path'])
            msg = "IMID:" + str(s['imid']) + " " + _("File: ") + s['filename'] + "\n" + _("Code: ") + s['codename']
            if s['memo'] != "":
                msg += "\n" + _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)

    def show_codes_of_text_files(self, x=10, y=10):
        """ Show selected codes of selected text files as free text graphics items. """

        # Select files
        files_wth_names = self.app.get_text_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select text files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_files = ui.get_selected()
        # Select codes
        code_names = self.app.get_code_names()
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []
        cur = self.app.conn.cursor()
        for file_ in selected_files:
            for code in selected_codes:
                sql = "select cid,fid,seltext,memo, ctid from code_text where cid=? and fid=?"
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    codings.append({'cid': r[0], 'fid': r[1], 'name': r[2], 'memo': r[3], 'filename': file_['name'],
                                    'codename': code['name'], 'ctid': r[4]})
        if not codings:
            Message(self.app, _("No codes"), _("No coded segments for selection")).exec()
            return
        ui = DialogSelectItems(self.app, codings, _("Select coded text"), "multi")
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
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, color, 0, s['ctid'])
            item.ctid = s['ctid']
            msg = _("File: ") + s['filename'] + "\n" + _("Code: ") + s['codename']
            if s['memo'] != "":
                msg += "\n" + _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)

    def show_memos_of_file(self, x=10, y=10):
        """ Show selected memos of coded segments of selected files in free text items. """

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
                sql = 'select cid,fid,seltext,memo,ctid from code_text where cid=? and fid=? and memo !="" order by pos0 asc'
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    memos.append({'cid': r[0], 'fid': r[1], 'tooltip': r[2], 'name': r[3], 'filetype': 'text',
                                  'codename': code['name'], 'filename': file_['name'], 'ctid': r[4]})
                sql_img = 'select cid,id,x1,y1,width,height,memo from code_image where cid=? and id=? and memo !=""'
                cur.execute(sql_img, [code['cid'], file_['id']])
                res_img = cur.fetchall()
                for r in res_img:
                    tt = "x:" + str(int(r[2])) + " y:" + str(int(r[3])) + " " + _("width:") + str(int(r[4])) + " " +\
                         _("height:") + str(int(r[5]))
                    memos.append({'cid': r[0], 'fid': r[1], 'tooltip': tt, 'name': r[6], 'filetype': 'image',
                                  'codename': code['name'], 'filename': file_['name']})
                sql_av = 'select cid,id,pos0,pos1,memo from code_av where cid=? and id=? and memo !="" order by pos0 asc'
                cur.execute(sql_av, [code['cid'], file_['id']])
                res_av = cur.fetchall()
                for r in res_av:
                    tt = str(r[2]) + " - " + str(r[3]) + " " + _("msecs")
                    memos.append({'cid': r[0], 'fid': r[1], 'tooltip': tt, 'name': r[4], 'filetype': 'A/V',
                                  'codename': code['name'], 'filename': file_['name']})
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
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, color)
            msg = _("File: ") + s['filename'] + "\n" + _("Code: ") + s['codename']
            if s['tooltip'] != "":
                msg += "\n" + _("Memo for: ") + s['tooltip']
            item.setToolTip(msg)
            self.scene.addItem(item)

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
                    isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) or \
                    isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
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
        color = self.color_selection("line")

        # Create Free Item lines
        for s in selected:
            text_to = s['name']
            to_item = None
            for item in self.scene.items():
                if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                        isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) or \
                        isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                    if item.text == text_to:
                        to_item = item
            if from_item != to_item and not (from_item is None or to_item is None):
                line_item = FreeLineGraphicsItem(self.app, from_item, to_item, color)
                self.scene.addItem(line_item)

    def color_selection(self, obj_type="line"):
        """ Get a color for Free text items and Free lines.
         Called by: add_lines_to_graph, show_codes, show_memos.
         Ifobj_type is line, limit choices, otherwise include black and white.
         param: obj_type : String

         return: color : String """

        # Line color selection
        names = [_("gray"), _("blue"), _("cyan"), _("magenta"), _("green"), _("red"), _("yellow"), _("orange")]
        if obj_type != "line":
            names = [_("gray"), _("blue"), _("cyan"), _("magenta"), _("green"), _("red"), _("yellow"), _("orange"),
                     _("white"), _("black")]
        names_dict_list = []
        for n in names:
            names_dict_list.append({'name': n})
        ui = DialogSelectItems(self.app, names_dict_list, _("Colour"), "single")
        ok = ui.exec()
        if not ok:
            return ""
        selected_color = ui.get_selected()
        return selected_color['name']

    def add_text_item_to_graph(self, x=20, y=20):
        """ Add text item to graph. """

        freetextid = 1
        for item in self.scene.items():
            if isinstance(item, FreeTextGraphicsItem):
                if item.freetextid > freetextid:
                    freetextid = item.freetextid + 1
        text_, ok = QtWidgets.QInputDialog.getText(self, _('Text object'), _('Enter text:'))
        if ok:
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, text_)
            self.scene.addItem(item)

    def named_text_items(self):
        """ Used to get a list of all named FreeText and Case and File graphics items.
         Use to show names in a dialog, to allow links between these items.
         Called by: add_lines_to_graph

         return: names : List of Strings
         """

        names = []
        for item in self.scene.items():
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                    isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) or \
                    isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
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
                sql = "insert into gr_cdct_text_item (grid,x,y,supercatid,catid,cid,font_size,bold,isvisible," \
                      "displaytext) values (?,?,?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.pos().x(), i.pos().y(), i.code_or_cat['supercatid'], i.code_or_cat['catid'],
                                  i.code_or_cat['cid'], i.font_size, i.bold, i.isVisible(), i.toPlainText()])
                self.app.conn.commit()
            if isinstance(i, FreeTextGraphicsItem):
                sql = "insert into gr_free_text_item (grid,freetextid, x,y,free_text,font_size,bold,color,tooltip, " \
                      "ctid) values (?,?,?,?,?,?,?,?,?,?)"
                tt = i.toolTip()
                cur.execute(sql, [grid, i.freetextid, i.pos().x(), i.pos().y(), i.text, i.font_size, i.bold, i.color,
                                  tt, i.ctid])
                self.app.conn.commit()
            if isinstance(i, CaseTextGraphicsItem):
                sql = "insert into gr_case_text_item (grid,x,y,caseid,font_size,bold,color, displaytext) " \
                      "values (?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.pos().x(), i.pos().y(), i.case_id, i.font_size, i.bold, i.color, i.toPlainText()])
                self.app.conn.commit()
            if isinstance(i, FileTextGraphicsItem):
                sql = "insert into gr_file_text_item (grid,x,y,fid,font_size,bold,color, displaytext) " \
                      "values (?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.pos().x(), i.pos().y(), i.file_id, i.font_size, i.bold, i.color, i.toPlainText()])
                self.app.conn.commit()
            if isinstance(i, PixmapGraphicsItem):
                sql = "insert into gr_pix_item (grid,imid,x,y,px,py,w,h,filepath,tooltip) values " \
                      "(?,?,?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.imid, i.pos().x(), i.pos().y(), i.px, i.py, i.pwidth, i.pheight, i.path_,
                                  i.toolTip()])
                self.app.conn.commit()
            if isinstance(i, AVGraphicsItem):
                sql = "insert into gr_av_item (grid,avid,x,y,pos0,pos1,filepath,tooltip, color) values " \
                      "(?,?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.avid, i.pos().x(), i.pos().y(), i.pos0, i.pos1, i.path_, i.toolTip(), i.color])
                self.app.conn.commit()
            if isinstance(i, LinkGraphicsItem):
                sql = "insert into gr_cdct_line_item (grid,fromcatid,fromcid,tocatid,tocid,color,linewidth,linetype," \
                      "isvisible) values (?,?,?,?,?,?,?,?,?)"
                cur.execute(sql, [grid, i.from_widget.code_or_cat['catid'], i.from_widget.code_or_cat['cid'],
                                  i.to_widget.code_or_cat['catid'], i.to_widget.code_or_cat['cid'],
                                  i.color, i.line_width, self.line_type_to_text(i.line_type),
                                  i.isVisible()])
                self.app.conn.commit()
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
        self.app.delete_backup = False

    def line_type_to_text(self, line_type):
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

    def load_graph(self):
        """ Load a saved graph.
        Load each text component first then link then the cdct_line_items then the free_lines_items.
        For cdct_text_items, fill extra details:
        eg name, memo, date?, owner?, color, child_names?
        """

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
        grid = graph['grid']
        self.scene.clear()
        self.scene.set_width(graph['width'])
        self.scene.set_height(graph['height'])
        err_msg = ""
        err_msg = self.load_code_or_cat_text_graphics_items(grid)
        err_msg += self.load_file_text_graphics_items(grid)
        err_msg += self.load_case_text_graphics_items(grid)
        err_msg += self.load_free_text_graphics_items(grid)
        err_msg += self.load_pixmap_graphics_items(grid)
        err_msg += self.load_av_graphics_items(grid)
        # Now load lines
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
            # Add link which includes the scene text items and associated data, add links before text_items
            from_item = None
            to_item = None
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    if from_item is None and i.code_or_cat['catid'] == line[0] and i.code_or_cat['cid'] == line[1]:
                        from_item = i
                    if to_item is None and i.code_or_cat['catid'] == line[2] and i.code_or_cat['cid'] == line[3]:
                        to_item = i
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
        Several matching options: catid and cid; fileid; caseid; imid; avid; freetextid.
        Then when found add the free line item. """

        err_msg = ""
        sql = "select fromfreetextid,fromcatid,fromcid,fromcaseid,fromfileid,fromimid,fromavid," \
              "tofreetextid,tocatid,tocid, tocaseid,tofileid, toimid, toavid,color, linewidth,linetype " \
              "from gr_free_line_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        result = cur.fetchall()
        res = []
        keys = "fromfreetextid", "fromcatid", "fromcid", "fromcaseid", "fromfileid", "fromimid","fromavid", \
               "tofreetextid", "tocatid", "tocid", "tocaseid", "tofileid", "toimid", "toavid", "color", \
               "linewidth", "linetype"
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
        sql_case = "select x, y, caseid,font_size, color, bold, displaytext from gr_case_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_case, [grid])
        res = cur.fetchall()
        for i in res:
            cur.execute("select name, memo from cases where caseid=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(CaseTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5], i[6]))
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
            cur.execute("select name, memo from source where id=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(FileTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5], i[6]))
            else:
                err_msg += _("File: ") + str(i[2]) + " "
        return err_msg

    def load_free_text_graphics_items(self, grid):
        """ Load the free text graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql = "select freetextid, x, y, free_text, font_size, color, bold, tooltip, ctid from gr_free_text_item " \
              "where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        res = cur.fetchall()
        for i in res:
            item = FreeTextGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[8])
            if i[7] != "":
                item.setToolTip(i[7])
            self.scene.addItem(item)
        return err_msg

    def load_pixmap_graphics_items(self, grid):
        """ Load pixmap graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql = "select imid, x, y, px,py,w,h,filepath, tooltip from gr_pix_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        res = cur.fetchall()
        for i in res:
            item = PixmapGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7])
            if i[8] != "":
                item.setToolTip(i[8])
            self.scene.addItem(item)
        return err_msg

    def load_av_graphics_items(self, grid):
        """ Load audio/video graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql = "select avid, x, y, pos0,pos1,filepath, tooltip, color from gr_av_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
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
            cur.execute("delete from gr_pix_item where grid = ?", [s['grid']])
            cur.execute("delete from gr_av_item where grid = ?", [s['grid']])
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
                    or isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) \
                    or isinstance(item, PixmapGraphicsItem):
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
        """ Calculate the maximum width and height from the current Items. """

        max_x = 0
        max_y = 0
        for i in self.items():
            if isinstance(i, TextGraphicsItem) or isinstance(i, FreeTextGraphicsItem) or \
                    isinstance(i, FileTextGraphicsItem) or isinstance(i, CaseTextGraphicsItem) or \
                    isinstance(i, PixmapGraphicsItem):
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
        cur.execute("select memo from cases where caseid=?", [case_id])
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
        edit_action = menu.addAction((_("Edit text")))
        font_larger_action = menu.addAction(_("Larger font"))
        font_smaller_action = menu.addAction(_("Smaller font"))
        bold_action = menu.addAction(_("Bold toggle"))
        red_action = menu.addAction(_("Red text"))
        green_action = menu.addAction(_("Green text"))
        yellow_action = menu.addAction(_("Yellow text"))
        blue_action = menu.addAction(_("Blue text"))
        orange_action = menu.addAction(_("Orange text"))
        cyan_action = menu.addAction(_("Cyan text"))
        magenta_action = menu.addAction(_("Magenta text"))
        gray_action = menu.addAction(_("Gray text"))
        black_action = menu.addAction(_("Black text"))
        white_action = menu.addAction(_("White text"))
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
            self.color = "blue"
        if action == gray_action:
            self.color = "gray"
        if action == black_action:
            self.color = "black"
        if action == white_action:
            self.color = "white"
        self.setDefaultTextColor(colors[self.color])
        if action == remove_action:
            self.remove = True
        if action == show_att_action:
            self.show_attributes = True
            self.setHtml(self.text + self.get_attributes())
        if action == hide_att_action:
            self.show_attributes = False
            self.setPlainText(self.text)
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
        cur.execute("select memo from source where id=?", [file_id])
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
        font_larger_action = menu.addAction(_("Larger font"))
        font_smaller_action = menu.addAction(_("Smaller font"))
        red_action = menu.addAction(_("Red text"))
        green_action = menu.addAction(_("Green text"))
        yellow_action = menu.addAction(_("Yellow text"))
        blue_action = menu.addAction(_("Blue text"))
        magenta_action = menu.addAction(_("Magenta text"))
        cyan_action = menu.addAction(_("Cyan text"))
        orange_action = menu.addAction(_("Orange text"))
        gray_action = menu.addAction(_("Gray text"))
        black_action = menu.addAction(_("Black text"))
        white_action = menu.addAction(_("White text"))
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
        if action == show_att_action:
            self.setHtml(self.text + self.get_attributes())
            self.show_attributes = True
        if action == hide_att_action:
            self.setPlainText(self.text)
            self.show_attributes = False
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
            attribute_text += '<br>' + r[0] + ": " + r[1]
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
    font_size = 9
    color = "black"
    bold = False
    MAX_WIDTH = 300
    MAX_HEIGHT = 300

    def __init__(self, app, freetextid=-1, x=10, y=10, text_="text", font_size=9, color="black", bold=False, ctid=-1):
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

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        edit_action = menu.addAction(_("Edit text"))
        context_action = None
        if self.ctid != -1:
            context_action = menu.addAction(_("Code in context"))
        bold_action = menu.addAction(_("Bold toggle"))
        font_larger_action = menu.addAction(_("Larger font"))
        font_smaller_action = menu.addAction(_("Smaller font"))
        remove_action = menu.addAction(_('Remove'))
        red_action = menu.addAction(_("Red text"))
        green_action = menu.addAction(_("Green text"))
        yellow_action = menu.addAction(_("Yellow text"))
        blue_action = menu.addAction(_("Blue text"))
        cyan_action = menu.addAction(_("Cyan text"))
        magenta_action = menu.addAction(_("Magenta text"))
        orange_action = menu.addAction(_("Orange text"))
        gray_action = menu.addAction(_("Gray text"))
        black_action = menu.addAction(_("Black text"))
        white_action = menu.addAction(_("White text"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == context_action:
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_text.owner,code_text.memo,"
                        "pos0, pos1, source.name, source.id "
                        "from code_text join code_name on code_name.cid=code_text.cid join source on "
                        "source.id=code_text.fid where code_text.ctid=?",
                        [self.ctid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find text coding in database")).exec()
                return
            data = {'coder': res[3], 'codename': res[1], 'cid': res[2], 'color': res[2], 'memo': res[4],
                    'pos0': res[5], 'pos1': res[6], 'file_or_casename': res[7], 'fid': res[8], 'file_or_case': 'File'}
            DialogCodeInText(self.app, data).exec()
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
        if action == edit_action:
            ui = DialogMemo(self.app, _("Edit text"), self.text)
            ui.exec()
            self.text = ui.memo
            self.setPlainText(self.text)
            if self.boundingRect().width() > self.MAX_WIDTH:
                self.setTextWidth(self.MAX_WIDTH)

    def paint(self, painter, option, widget=None):
        painter.save()
        if self.color in("black", "gray"):
            color = QtGui.QColor("#fafafa")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        if self.color == "white":
            color = QtGui.QColor("#101010")
            painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
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
    color = "gray"
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
        self.color = color
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine
        color_obj = colors[color]
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))

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
        orange_action = menu.addAction(_("Orange"))
        gray_action = menu.addAction(_("Gray"))
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == thicker_action:
            self.line_width = self.line_width + 1
            if self.line_width > 8:
                self.line_width = 8
            self.redraw()
        if action == thinner_action:
            self.line_width = self.line_width - 1
            if self.line_width < 2:
                self.line_width = 2
            self.redraw()
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
            self.redraw()
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
        color_obj = colors[self.color]
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))
        self.setLine(from_x, from_y, to_x, to_y)


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
        self.text = "AVID:" + str(self.avid)
        self.pos0 = pos0
        self.pos1 = pos1
        self.path_ = path_
        self.color = color
        self.abs_path_ = self.app.project_path + path_
        if path_[0:7] in("audio:", "video:"):
            self.abs_path_ = path_[7:]
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
        self.setPixmap(pm)
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
        remove_action = menu.addAction(_('Remove'))
        red_action = menu.addAction(_("Red"))
        green_action = menu.addAction(_("Green"))
        yellow_action = menu.addAction(_("Yellow"))
        blue_action = menu.addAction(_("Blue"))
        magenta_action = menu.addAction(_("Magenta"))
        cyan_action = menu.addAction(_("Cyan"))
        orange_action = menu.addAction(_("Orange"))
        gray_action = menu.addAction(_("Gray"))
        white_action = menu.addAction(_("White"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == context_action:
            '''{codename, color, file_or_casename, pos0, pos1, coder, text,
                    mediapath, fid, memo, file_or_case}'''
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_av.owner,code_av.memo "
                        "from code_av join code_name on code_name.cid=code_av.cid where code_av.avid=?",
                        [self.avid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find audio/video coding in database")).exec()
                return
            data = {'pos0': self.pos0, 'pos1': self.pos1, 'file_or_casename': self.path_, 'mediapath': self.path_,
                    'coder': res[3], 'codename': res[1], 'cid': res[2], 'color': res[2], 'memo': res[4]}
            DialogCodeInAV(self.app, data).exec()
        if action == remove_action:
            self.remove = True
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
    """ Coded pixmap.
    Maximum size of 200 pixels high and wide. """

    app = None
    font = None
    settings = None
    remove = False
    # For graph item storage
    text = ""
    imid = -1  # code_image table imid i=unique fo r the coded image area
    px = 0
    py = 0
    pwidth = 0
    pheight = 0
    path_ = ""
    MAX_WIDTH = 300
    MAX_HEIGHT = 300

    def __init__(self, app, imid=-1, x=10, y=10, px=0, py=0, pwidth=0, pheight=0, path_=""):
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
        abs_path_ = self.app.project_path + path_
        if path_[0:7] == "images:":
            abs_path_ = path_[7:]
        image = QtGui.QImageReader(abs_path_).read()
        image = image.copy(px, py, pwidth, pheight)
        # Scale to max 200 wide or high. perhaps add option to change maximum limit?
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
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == context_action:
            '''{codename, color, file_or_casename, x1, y1, width, height, coder,
             mediapath, fid, memo, file_or_case}'''
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_image.owner,code_image.memo "
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
        if action == remove_action:
            self.remove = True

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
        self.text = displayed_text
        if self.text == "":
            self.text = self.code_or_cat['name']
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        #self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
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
            cur.execute("select memo from code_name where name=?", [self.code_or_cat['name']])
            res = cur.fetchone()
            if res:
                self.code_or_cat['memo'] = res[0]
                self.setToolTip(_("Code") + ": " + res[0])
            else:
                self.setToolTip(_("Code"))
        else:
            cur.execute("select memo from code_cat where name=?", [self.code_or_cat['name']])
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
            self.get_memo()
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
    text = ""
    color = "gray"

    def __init__(self, app, from_widget, to_widget, line_width=2, line_type="solid",
                 color="gray", isvisible=True):
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
        self.color = color
        if not isvisible:
            self.hide()
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine
        self.redraw()

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
        orange_action = menu.addAction(_("Orange"))
        gray_action = menu.addAction(_("Gray"))
        hide_action = menu.addAction(_('Hide'))

        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == thicker_action:
            self.line_width = self.line_width + 1
            if self.line_width > 8:
                self.line_width = 8
        if action == thinner_action:
            self.line_width = self.line_width - 1
            if self.line_width < 2:
                self.line_width = 2
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
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
            self.color = ".cyan"
            self.redraw()
        if action == magenta_action:
            self.color = "magenta"
        if action == gray_action:
            self.color = "gray"
        if action == hide_action:
            self.hide()
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
        color_obj = colors[self.color]
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))
        self.setLine(from_x, from_y, to_x, to_y)

