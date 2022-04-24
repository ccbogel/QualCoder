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
        font_size_list = []
        for i in range(8, 22, 2):
            font_size_list.append(str(i))
        self.ui.comboBox_fontsize.addItems(font_size_list)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_export.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export.pressed.connect(self.export_image)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(zoom_icon), "png")
        self.ui.label_zoom.setPixmap(pm.scaled(26, 26))

        # Set the scene
        self.scene = GraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.DefaultContextMenu)

        self.ui.checkBox_blackandwhite.stateChanged.connect(self.show_graph_type)
        self.ui.checkBox_listview.stateChanged.connect(self.show_graph_type)
        self.ui.comboBox_fontsize.currentIndexChanged.connect(self.show_graph_type)
        self.codes, self.categories = app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "
        self.ui.comboBox.currentIndexChanged.connect(self.show_graph_type)
        combobox_list = ['All']
        for c in self.categories:
            combobox_list.append(c['name'])
        self.ui.comboBox.addItems(combobox_list)

    def show_graph_type(self):

        if self.ui.checkBox_listview.isChecked():
            self.list_graph()
        else:
            self.circular_graph()

    def export_image(self):
        """ Export the QGraphicsScene as a png image with transparent background.
        Called by QButton.
        """

        filename = "Graph.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        # Scene size is too big.
        max_x, max_y = self.scene.suggested_scene_size()
        rect_area = QtCore.QRectF(0.0, 0.0, max_x + 5, max_y + 5)
        image = QtGui.QImage(max_x, max_y, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect_area)
        painter.end()
        image.save(filepath)
        Message(self.app, _("Image exported"), filepath).exec()

    def create_initial_model(self):
        """ Create initial model

        return: categories, codes, model  """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)

        for c in codes:
            c['depth'] = 0
            c['x'] = None
            c['y'] = None
            c['supercatid'] = c['catid']
            c['angle'] = None
            if self.ui.checkBox_blackandwhite.isChecked():
                c['color'] = "#FFFFFF"
            c['fontsize'] = int(self.ui.comboBox_fontsize.currentText())
        for c in cats:
            c['depth'] = 0
            c['x'] = None
            c['y'] = None
            c['cid'] = None
            c['angle'] = None
            c['color'] = '#FFFFFF'
            c['fontsize'] = int(self.ui.comboBox_fontsize.currentText())
        model = cats + codes
        return cats, codes, model

    def get_refined_model_with_depth_and_category_counts(self, cats, model):
        """ The default model contains all categories and codes.
        Can limit to a selected category, via combo box selection.

        param: cats - list of categories
        param: model - model containing all categories and codes

        return: model
        """

        top_node = self.ui.comboBox.currentText()
        if top_node == "All":
            top_node = None
        for c in cats:
            if c['name'] == top_node:
                top_node = c
                top_node['supercatid'] = None  # must set this to None
        model = self.get_node_with_children(top_node, model)

        ''' Look at each category and determine the depth.
        Also determine the number of children for each catid. '''
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
        catid_counts = Counter(supercatid_list)

        return catid_counts, model

    def named_children_of_node(self, node):
        """ Get child categories and codes of this category node.
        Only keep the category or code name.  Used to reposition TextGraphicsItems on moving a category. """

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

    def list_graph(self):
        """ Create a list graph with the categories on the left and codes on the right
        """

        self.scene.clear()
        cats, codes, model = self.create_initial_model()
        catid_counts, model = self.get_refined_model_with_depth_and_category_counts(cats, model)

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
            ordered_model[i]['y'] = i * (int(self.ui.comboBox_fontsize.currentText()) * 3)
        model = ordered_model

        # Expand scene width and height if needed
        max_x = self.scene.get_width()
        max_y = self.scene.get_height()
        for m in model:
            m['child_names'] = self.named_children_of_node(m)
            if m['x'] > max_x - 50:
                max_x = m['x'] + 50
            if m['y'] > max_y - 20:
                max_y = m['y'] + 40
        self.scene.set_width(max_x)
        self.scene.set_height(max_y)

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
                        item = LinkGraphicsItem(self.app, m, n, True)  # corners only = True
                        self.scene.addItem(item)

    def circular_graph(self):
        """ Create a circular acyclic graph
        default font size is 8.  """

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
        ''' Calculate x y positions from central point outwards.
        The 'central' x value is towards the left side rather than true center, because
        the text boxes will draw to the right-hand side.
        '''
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
                        item = LinkGraphicsItem(self.app, m, n)
                        self.scene.addItem(item)

    def get_node_with_children(self, node, model):
        """ Return a short list of this top node and all its children.
        Note, maximum depth of 20. """

        if node is None:
            return model
        new_model = [node]
        i = 0  # for ensuring an exit from while loop
        new_model_changed = True
        while model != [] and new_model_changed and i < 20:
            new_model_changed = False
            append_list = []
            for n in new_model:
                for m in model:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
            for n in append_list:
                new_model.append(n)
                model.remove(n)
                new_model_changed = True
            i += 1
        return new_model

    def keyPressEvent(self, event):
        """ Plus to zoom in and Minus to zoom out. Needs focus on the QGraphicsView widget. """

        key = event.key()
        #mod = event.modifiers()
        if key == QtCore.Qt.Key.Key_Plus:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() > 10:
                return
            self.ui.graphicsView.scale(1.1, 1.1)
        if key == QtCore.Qt.Key.Key_Minus:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() < 0.1:
                return
            self.ui.graphicsView.scale(0.9, 0.9)

    def reject(self):

        super(ViewGraph, self).reject()

    def accept(self):

        super(ViewGraph, self).accept()


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
            if isinstance(item, LinkGraphicsItem):
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

    def suggested_scene_size(self):
        """ Calculate the maximum width and height from the current Text Items. """

        max_x = 0
        max_y = 0
        for i in self.items():
            if isinstance(i, TextGraphicsItem):
                if i.pos().x() + i.boundingRect().width() > max_x:
                    max_x = i.pos().x() + i.boundingRect().width()
                if i.pos().y() + i.boundingRect().height() > max_y:
                    max_y = i.pos().y() + i.boundingRect().height()
        return max_x, max_y


class TextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item show the name and color of the code or category
    Categories are typically shown white, and category font sizes can be enlarged using a
    checkbox and code colours can be ignored using a check box. A custom context menu
    allows selection of a code/category memo an displaying the information.
    """

    code_or_cat = None
    border_rect = None
    app = None
    font = None
    settings = None

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
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditable)
        # Foreground depends on the defined need_white_text color in color_selector
        if self.code_or_cat['cid'] is not None:
            self.font = QtGui.QFont(self.settings['font'], self.code_or_cat['fontsize'], QtGui.QFont.Weight.Normal)
            self.setFont(self.font)
            self.setPlainText(self.code_or_cat['name'])
        if self.code_or_cat['cid'] is None:
            self.font = QtGui.QFont(self.settings['font'], self.code_or_cat['fontsize'], QtGui.QFont.Weight.Bold)
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
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action.text() == 'Memo':
            self.add_edit_memo()
        if action.text() == 'Coded text and media':
            self.coded_media()
        if action.text() == 'Case text and media':
            self.case_media()

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
            cur.execute("update code_cat set memo=? where catid=?", (self.code_or_cat['memo'], self.code_or_cat['catid']))
            self.conn.commit()

    def case_media(self,):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders. """

        DialogCodeInAllFiles(self.app, self.code_or_cat, "Case")

    def coded_media(self,):
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
    line_width = 1.5
    line_type = QtCore.Qt.PenStyle.SolidLine
    line_color = QtCore.Qt.GlobalColor.black
    corners_only = False  # True for list graph

    def __init__(self, app, from_widget, to_widget, corners_only=False):
        super(LinkGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.corners_only = corners_only
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.calculate_points_and_draw()
        self.line_color = QtCore.Qt.GlobalColor.black
        if app.settings['stylesheet'] == "dark":
            self.line_color = QtCore.Qt.GlobalColor.white

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        menu.addAction('Thicker')
        menu.addAction('Thinner')
        menu.addAction('Dotted')
        menu.addAction('Red')
        action = menu.exec(QtGui.QCursor.pos())
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

        # fix from_x value to right-hand side of from widget if to_widget on the right of the from_widget
        if not x_overlap and to_x > from_x + self.from_widget.boundingRect().width():
            from_x = from_x + self.from_widget.boundingRect().width()
        # fix to_x value to right-hand side if from_widget on the right of the to widget
        elif not x_overlap and from_x > to_x + self.to_widget.boundingRect().width():
            to_x = to_x + self.to_widget.boundingRect().width()

        y_overlap = False
        if not self.corners_only:
            # fix from_y value to middle of from widget if to_widget overlaps in y position
            if to_y > from_y and to_y < from_y + self.from_widget.boundingRect().height():
                from_y = from_y + self.from_widget.boundingRect().height() / 2
                y_overlap = True
            # fix from_y value to middle of to widget if from_widget overlaps in y position
            if from_y > to_y and from_y < to_y + self.to_widget.boundingRect().height():
                to_y = to_y + self.to_widget.boundingRect().height() / 2
                y_overlap = True

        # fix from_y value if to_widget is above the from_widget
        if not y_overlap and to_y > from_y:
            from_y = from_y + self.from_widget.boundingRect().height()
        # fix to_y value if from_widget is below the to widget
        elif not y_overlap and from_y > to_y:
            to_y = to_y + self.to_widget.boundingRect().height()

        self.setPen(QtGui.QPen(self.line_color, self.line_width, self.line_type))
        self.setLine(from_x, from_y, to_x, to_y)
