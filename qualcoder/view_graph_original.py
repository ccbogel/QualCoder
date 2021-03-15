# -*- coding: utf-8 -*-

"""
Copyright (c) 2021 Colin Curtain

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

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QDialog

from GUI.ui_visualise_graph_original import Ui_Dialog_visualiseGraph_original
from helpers import msecs_to_mins_and_secs, DialogCodeInAllFiles
from information import DialogInformation
from memo import DialogMemo


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()


class ViewGraphOriginal(QDialog):
    """ Dialog to view code and categories in an acyclic graph. Provides options for
    colors and amount of nodes to display (based on category selection).
    """

    app = None

    conn = None
    settings = None
    categories = []
    code_names = []

    def __init__(self, app):
        """ Set up the dialog. """

        sys.excepthook = exception_handler
        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_Dialog_visualiseGraph_original()
        self.ui.setupUi(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        fsize_list = []
        for i in range(8, 22, 2):
            fsize_list.append(str(i))
        self.ui.comboBox_fontsize.addItems(fsize_list)
        # set the scene
        self.scene = GraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.ui.checkBox_blackandwhite.stateChanged.connect(self.show_graph_type)
        self.ui.checkBox_listview.stateChanged.connect(self.show_graph_type)
        self.ui.comboBox_fontsize.currentIndexChanged.connect(self.show_graph_type)
        self.code_names, self.categories = app.get_data()

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

    """def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        menu.addAction('sample')
        menu.exec_(event.globalPos())"""

    def create_initial_model(self):
        """ Create inital model

        return: categories, oces, model  """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.code_names)

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
            supercatid = 0
            depth = 0
            supercatid = c['supercatid']
            supercatid_list.append(c['supercatid'])
            while supercatid is not None:
                for s in cats:
                    if supercatid == s['catid']:
                        depth += 1
                        supercatid = s['supercatid']
                c['depth'] = depth
        catid_counts = Counter(supercatid_list)

        return catid_counts, model

    def list_graph(self):
        """ Create a list graph with the categories on the left and codes on the right
        """

        self.scene.clear()
        cats, codes, model = self.create_initial_model()
        catid_counts, model = self.get_refined_model_with_depth_and_category_counts(cats, model)

        # order the model by supercatid, subcats, codes
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

        # expand scene width and height if needed
        max_x = self.scene.getWidth()
        max_y = self.scene.getHeight()
        for m in model:
             if m['x'] > max_x - 50:
                 max_x = m['x'] + 50
             if m['y'] > max_y - 20:
                 max_y = m['y'] + 40
        self.scene.setWidth(max_x)
        self.scene.setHeight(max_y)

        # Add text items to the scene
        for m in model:
            self.scene.addItem(TextGraphicsItem(self.app, m))
        # Add link which includes the scene text items and associated data, add links before text_items
        for m in self.scene.items():
            if isinstance(m, TextGraphicsItem):
                for n in self.scene.items():
                    if isinstance(n, TextGraphicsItem) and m.data['supercatid'] is not None and m.data['supercatid'] == n.data['catid'] and n.data['depth'] < m.data['depth']:
                        #item = QtWidgets.QGraphicsLineItem(m['x'], m['y'], super_m['x'], super_m['y'])  # xy xy
                        item = LinkGraphicsItem(m, n, True)  # corners only = True
                        self.scene.addItem(item)

    def circular_graph(self):
        """ Create a circular acyclic graph
        default font size is 8.  """

        self.scene.clear()
        cats, codes, model = self.create_initial_model()
        catid_counts, model = self.get_refined_model_with_depth_and_category_counts(cats, model)

        # assign angles to each item segment
        for cat_key in catid_counts.keys():
            #logger.debug("cat_key:" + cat_key + "", catid_counts[cat_key]:" + str(catid_counts[cat_key]))
            segment = 1
            for m in model:
                if m['angle'] is None and m['supercatid'] == cat_key:
                    m['angle'] = (2 * math.pi / catid_counts[m['supercatid']]) * (segment + 1)
                    segment += 1
        ''' Calculate x y positions from central point outwards.
        The 'central' x value is towards the left side rather than true center, because
        the text boxes will draw to the right-hand side.
        '''
        c_x = self.scene.getWidth() / 3
        c_y = self.scene.getHeight() / 2
        r = 220
        rx_expander = c_x / c_y  # screen is landscape, so stretch x position
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
                    if isinstance(n, TextGraphicsItem) and m.data['supercatid'] is not None and m.data['supercatid'] == n.data['catid'] and n.data['depth'] < m.data['depth']:
                        #item = QtWidgets.QGraphicsLineItem(m['x'], m['y'], super_m['x'], super_m['y'])  # xy xy
                        item = LinkGraphicsItem(m, n)
                        self.scene.addItem(item)

    def get_node_with_children(self, node, model):
        """ Return a short list of this top node and all its children.
        Note, maximum depth of 10. """
        if node is None:
            return model
        new_model = [node]
        i = 0  # not really needed, but keep for ensuring an exit from while loop
        new_model_changed = True
        while model != [] and new_model_changed and i < 10:
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

    def reject(self):

        self.dialog_list = []
        super(ViewGraphOriginal, self).reject()

    def accept(self):

        self.dialog_list = []
        super(ViewGraphOriginal, self).accept()


# http://stackoverflow.com/questions/17891613/pyqt-mouse-events-for-qgraphicsview
class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    # matches the initial designer file graphics view
    sceneWidth = 982
    sceneHeight = 647

    def __init__ (self, parent=None):
        super(GraphicsScene, self).__init__ (parent)
        self.setSceneRect(QtCore.QRectF(0, 0, self.sceneWidth, self.sceneHeight))

    def setWidth(self, width):
        """ Resize scene width. """

        self.sceneWidth = width
        self.setSceneRect(QtCore.QRectF(0, 0, self.sceneWidth, self.sceneHeight))

    def setHeight(self, height):
        """ Resize scene height. """

        self.sceneHeight = height
        self.setSceneRect(QtCore.QRectF(0, 0, self.sceneWidth, self.sceneHeight))

    def getWidth(self):
        """ Return scene width. """

        return self.sceneWidth

    def getHeight(self):
        """ Return scene height. """

        return self.sceneHeight

    def mouseMoveEvent(self, mouseEvent):
        """ On mouse move, an item might be repositioned so need to redraw all the link_items.
        This slows re-drawing down, but is more dynamic. """

        super(GraphicsScene, self).mousePressEvent(mouseEvent)

        for item in self.items():
            if isinstance(item, TextGraphicsItem):
                item.data['x'] = item.pos().x()
                item.data['y'] = item.pos().y()
                #logger.debug("item pos:" + str(item.pos()))
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


class TextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item show the name and color of the code or category
    Categories are typically shown white, and category font sizes can be enlarged using a
    checkbox and code colours can be ignores using a check box. A custom context menu
    allows selection of a code/category memo an displaying the information.
    """

    data = None
    border_rect = None
    app = None
    font = None
    settings = None

    def __init__(self, app, data):
        super(TextGraphicsItem, self).__init__(None)

        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.data = data
        self.setFlags (QtWidgets.QGraphicsItem.ItemIsMovable | QtWidgets.QGraphicsItem.ItemIsFocusable | QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setTextInteractionFlags(QtCore.Qt.TextEditable)
        if self.data['cid'] is not None:
            self.font = QtGui.QFont(self.settings['font'], self.data['fontsize'], QtGui.QFont.Normal)
            self.setFont(self.font)
            self.setPlainText(self.data['name'])
        if self.data['cid'] is None:
            self.font = QtGui.QFont(self.settings['font'], self.data['fontsize'], QtGui.QFont.Bold)
            self.setFont(self.font)
            self.setPlainText(self.data['name'])
        self.setPos(self.data['x'], self.data['y'])
        self.document().contentsChanged.connect(self.text_changed)
        #self.border_rect = QtWidgets.QGraphicsRectItem(0, 0, rect.width(), rect.height())
        #self.border_rect.setParentItem(self)

    def paint(self, painter, option, widget):
        """ see paint override method here:
            https://github.com/jsdir/giza/blob/master/giza/widgets/nodeview/node.py
            see:
            https://doc.qt.io/qt-5/qpainter.html """

        color = QtGui.QColor(self.data['color'])
        painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.SolidPattern))
        painter.drawRect(self.boundingRect())
        #logger.debug("bounding rect:" + str(self.boundingRect()))
        painter.setFont(self.font)
        #fi = painter.fontInfo()
        #logger.debug("Font:", fi.family(), " Pixelsize:",fi.pixelSize(), " Pointsize:", fi.pointSize(), " Style:", fi.style())
        fm = painter.fontMetrics()
        #logger.debug("Font height: ", fm.height())
        painter.setPen(QtCore.Qt.black)
        lines = self.data['name'].split('\n')
        for row in range(0, len(lines)):
            #painter.drawText(5,fm.height(),self.data['name'])
            painter.drawText(5, fm.height() * (row + 1), lines[row])

    def text_changed(self):
        """ Text changed in a node. Redraw the border rectangle item to match. """

        #rect = self.boundingRect()
        #self.border_rect.setRect(0, 0, rect.width(), rect.height())
        self.data['name'] = self.toPlainText()
        #logger.debug("self.data[name]:" + self.data['name'])

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        menu.addAction('Memo')
        if self.data['cid'] is not None:
            menu.addAction('Coded text and media')
            menu.addAction('Case text and media')
        action = menu.exec_(QtGui.QCursor.pos())
        if action is None:
            return
        if action.text() == 'Memo':
            self.add_edit_memo(self.data)
        if action.text() == 'Coded text and media':
            self.coded_media(self.data)
        if action.text() == 'Case text and media':
            self.case_media(self.data)

    def add_edit_memo(self, data):
        """ Add or edit memos for codes and categories. """

        if data['cid'] is not None:
            ui = DialogMemo(self.app, "Memo for Code " + data['name'], data['memo'])
            ui.exec_()
            self.data['memo'] = ui.memo
            cur = self.conn.cursor()
            cur.execute("update code_name set memo=? where cid=?", (self.data['memo'], self.data['cid']))
            self.conn.commit()
        if data['catid'] is not None and data['cid'] is None:
            ui = DialogMemo(self.app, "Memo for Category " + data['name'], data['memo'])
            ui.exec_()
            self.data['memo'] = ui.memo
            cur = self.conn.cursor()
            cur.execute("update code_cat set memo=? where catid=?", (self.data['memo'], self.data['catid']))
            self.conn.commit()

    def case_media(self, code_dict):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders. """

        DialogCodeInAllFiles(self.app, code_dict, "Case")

    def coded_media(self, code_dict):
        """ Display all coded media for this code.
        Coded media comes from ALL files and current coder.
        param:
            code_dict : dictionary of code {name, memo, owner, date, cid, catid, color, depth, x, y, supercatid, angle, fontsize} """

        DialogCodeInAllFiles(self.app, code_dict)


class LinkGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Takes the coordinate from the two TextGraphicsItems. """

    from_widget = None
    from_pos = None
    to_widget = None
    to_pos = None
    line_width = 1.5
    line_type = QtCore.Qt.SolidLine
    line_color = QtCore.Qt.black
    corners_only = False  # True for list graph

    def __init__(self, from_widget, to_widget, corners_only=False):
        super(LinkGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.corners_only = corners_only
        #self.setFlag(self.ItemIsSelectable, True)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.calculatePointsAndDraw()

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        menu.addAction('Thicker')
        menu.addAction('Thinner')
        menu.addAction('Dotted')
        menu.addAction('Red')
        action = menu.exec_(QtGui.QCursor.pos())
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
            self.line_type = QtCore.Qt.DotLine
            self.redraw()
        if action.text() == 'Red':
            self.line_color = QtCore.Qt.red
            self.redraw()

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculatePointsAndDraw()

    def calculatePointsAndDraw(self):
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


