# -*- coding: utf-8 -*-

'''
Copyright (c) 2019 Colin Curtain

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
'''

from collections import Counter, defaultdict
from copy import deepcopy
import logging
import time
import math
import os
import sys
import traceback

from PyQt5 import QtCore, QtWidgets, QtGui

from .GUI.ui_visualise_graph import Ui_Dialog_visualiseGraph
from .information import DialogInformation
from .memo import DialogMemo
from .helpers import CodedMediaMixin

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def get_cats_from_supercats(node,cats):
    cats = deepcopy(cats)
    for x in cats:
        if x['supercatid'] == node['catid']:
            yield x
            yield from get_cats_from_supercats(x,cats)

def calc_supercats(cats):
    per_supercat = defaultdict(list)
    for cat in cats:
        per_supercat[cat['supercatid']].append(cat)
    return per_supercat

def recurse_supercats(node,per_supercat,func):
    for x in per_supercat.pop(node['catid'],[]):
        func(node,x)
        yield x
        yield from recurse_supercats(x,per_supercat,func=func)

def visit_cats_from_supercats(cats,node=None,func=None):
    if func is None:
        func = lambda a,b:(a,b)
    per_supercat = calc_supercats(cats)
    if node is not None:
        yield from recurse_supercats(node,per_supercat,func=func)
    else:
        per_cats = {x['catid']:x for x in cats}
        for supercatid,scats in per_supercat.items():
            if supercatid in per_cats:
                supercat = per_cats[supercatid]
                for cat in scats:
                    func(supercat,cat)
                    yield cat
            else:
                for cat in cats:
                    func(None,cat)
                    yield cat


def get_codes_from_cats(cats,codes):
    for cat in cats:
        for c in codes:
            if c['catid'] == cat['catid']:
                yield c

def visit_codes_from_cats(cats,codes,func=None):
    if func is None:
        func = lambda a,b:(a,b)
    for cat in cats:
        for c in codes:
            if c['catid'] == cat['catid'] and c != cat:
                func(cat,c)
                yield c


def get_first_with_attr(cats,**attrs):
    get_cats = lambda x:set(sorted(x[k] for k in attrs))
    search_cats = get_cats(attrs)
    for x in cats:
        if get_cats(x) == search_cats:
            return x


def plot_with_pygraphviz(cats,codes,topnode=None,prog='neato',rankdir='LR'):
    import pygraphviz as pgv

    tocatid = lambda x:'catid:%s'%x['catid']
    tocid = lambda x:'cid:%s'%x['cid']

    graph = pgv.AGraph(overlap=False,splines=True,dpi=96,rankdir=rankdir) 
    if topnode is not None:
        graph.add_node(tocatid(topnode),label=topnode['name'])
    
    def draw_connection_cats(top,b):
        graph.add_node(tocatid(b),label=b['name'],type='cat')
        if top is not None:
            graph.add_edge(tocatid(top),tocatid(b),label='')

    def draw_connection_codes(top,b):
        attrs = {}
        if 'color' in b:
            attrs['fillcolor'] = b['color']
            attrs['style'] = 'filled'
        graph.add_node(tocid(b),label=b['name'],type='code',**attrs)
        if top is not None:
            graph.add_edge(tocatid(top),tocid(b),label='')

    mycats = list(visit_cats_from_supercats(cats,node=topnode,func=draw_connection_cats))
    mycodes = list(visit_codes_from_cats(mycats,codes,draw_connection_codes))
    graph.layout(prog=prog) # layout with default (neato)
    path = os.path.abspath('simple.pdf')
    print('saved to: %s'%path)
    graph.draw(path) # draw png
    return graph


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


def msecs_to_mins_and_secs(msecs):
    """ Convert milliseconds to minutes and seconds.
    msecs is an integer. Minutes and seconds output is a string."""

    secs = int(msecs / 1000)
    mins = int(secs / 60)
    remainder_secs = str(secs - mins * 60)
    if len(remainder_secs) == 1:
        remainder_secs = "0" + remainder_secs
    return str(mins) + "." + remainder_secs

def get_node_with_children(node, model):
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

class ViewGraph(QtWidgets.QWidget):
    """ Dialog to view code and categories in an acyclic graph. Provides options for
    colors and amount of nodes to display (based on category selection).
    """

    categories = []
    code_names = []

    def __init__(self, app,parent=None):
        """ Set up the dialog. """
        super(ViewGraph,self).__init__(parent=parent)
        sys.excepthook = exception_handler
        self.setLayout(QtWidgets.QVBoxLayout())
        self.app = app
        combobox_list = ['All']
        for c in self.app.categories:
            combobox_list.append(c['name'])

        self.graphicsView = GraphViewer(self.app,parent=self)
        self.layout().addWidget(self.graphicsView)
        self.groupBox_2 = QtWidgets.QGroupBox(self)
        self.groupBox_2.setMinimumSize(QtCore.QSize(0, 40))
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.pushButton_view = QtWidgets.QPushButton('View',self.groupBox_2)
        self.pushButton_view.setGeometry(QtCore.QRect(0, 0, 161, 27))
        self.pushButton_view.setObjectName("pushButton_view")
        self.comboBox = QtWidgets.QComboBox(self.groupBox_2)
        self.comboBox.setGeometry(QtCore.QRect(660, 0, 421, 30))
        self.comboBox.setObjectName("comboBox")
        self.checkBox_neato = QtWidgets.QCheckBox('neato',self.groupBox_2)
        self.checkBox_neato.setGeometry(QtCore.QRect(170, 0, 191, 22))
        self.checkBox_neato.setObjectName("checkBox_blackandwhite")
        self.layout().addWidget(self.groupBox_2)
        self.pushButton_view.pressed.connect(self.do_graph)
        self.comboBox.addItems(combobox_list)
        self.resize(1098, 753)
        # self.graphicsView.setGeometry(QtCore.QRect(10, 40, 601, 411))

    def do_graph(self):
        name = self.comboBox.currentText()
        topnode = get_first_with_attr(self.app.categories,name=name)
        if self.checkBox_neato.isChecked():
            prog = 'neato'
        else:
            prog = 'dot'
        graph = plot_with_pygraphviz(
            self.app.categories,self.app.codes,topnode=topnode,prog=prog)
        self.graphicsView.drawGraph(graph)


class GVEdgeGraphicsItem(QtWidgets.QGraphicsPathItem):
    """ cudos to: http://www.mupuf.org/blog/2010/07/08/how_to_use_graphviz_to_draw_graphs_in_a_qt_graphics_scene/ """
    def __init__(self):
        super(GVEdgeGraphicsItem, self).__init__(None)
        self.setFlag(self.ItemIsSelectable, False)
        linkWidth = 1
        self.setPen(QtGui.QPen(QtCore.Qt.black, linkWidth, QtCore.Qt.SolidLine))

    def setPath(self,edge,yoffset,scaler):
        path = QtGui.QPainterPath()
        start = edge[0].attr['pos'].split(',')
        controlpoints = []
        for cp in edge.attr['pos'].split(' '):
            txt = cp.split(',')
            controlpoints.append((float(txt[0]),float(txt[1])))
        path.moveTo(controlpoints[0][0]*scaler,yoffset-controlpoints[0][1]*scaler)
        i = 1
        while i < len(controlpoints):
            path.cubicTo(
                controlpoints[i][0]*scaler,yoffset-controlpoints[i][1]*scaler,
                controlpoints[i+1][0]*scaler,yoffset-controlpoints[i+1][1]*scaler,
                controlpoints[i+2][0]*scaler,yoffset-controlpoints[i+2][1]*scaler,
            )
            i += 3
        super(GVEdgeGraphicsItem,self).setPath(path)


class ZoomedViewer(QtWidgets.QGraphicsView):
    """ zooming and panning from https://stackoverflow.com/questions/35508711/how-to-enable-pan-and-zoom-in-a-qgraphicsview"""

    def __init__(self, parent=None):
        super(ZoomedViewer, self).__init__(parent)
        self._zoom = 0
        self._bb = None
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        # self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        # self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(30, 30, 30)))
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

    def has_bb(self):
        return self._bb is not None

    def fitInView(self, scale=True):
        if self.has_bb():
            rect = QtCore.QRectF(*self._bb)
            if not rect.isNull():
                self.setSceneRect(rect)
                unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
                self.scale(1 / unity.width(), 1 / unity.height())
                viewrect = self.viewport().rect()
                scenerect = self.transform().mapRect(rect)
                factor = min(viewrect.width() / scenerect.width(),
                             viewrect.height() / scenerect.height())
                self.scale(factor, factor)
                self._zoom = 0

    def wheelEvent(self, event):
        if QtCore.Qt.ControlModifier & event.modifiers():
            self.zoom(event)
            event.accept()
        else:
            self.scroll(event)
            event.accept()

    def scroll(self,event):
        if False: # Not working
            height = self._bb[3] - self._bb[1]
            if event.angleDelta().y() > 0:
                val = 10
            else:
                val = -10
            print(height,val)
            self.translate(0,val)


    def zoom(self,event):
        if self.has_bb():
            if event.angleDelta().y() > 0:
                factor = 1.25
                self._zoom += 1
            else:
                factor = 0.8
                self._zoom -= 1
            if self._zoom > 0:
                self.scale(factor, factor)
            elif self._zoom == 0:
                self.fitInView()
            else:
                self._zoom = 0

    def toggleDragMode(self):
        if self.dragMode() == QtWidgets.QGraphicsView.ScrollHandDrag:
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        elif self.has_bb():
            self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)

    def resizeEvent(self,event):
        if self._zoom == 0:
            self.fitInView()
        super(ZoomedViewer, self).resizeEvent(event)


class GraphViewer(ZoomedViewer):
    DEFAULTDPI = 72 
    
    def __init__(self,app=None,parent=None):
        super(GraphViewer,self).__init__(parent=parent)
        self.app = app
        self.setScene(QtWidgets.QGraphicsScene(self))

    def calc_node_pos(self,node):
        pos = node.attr['pos'].split(',')
        x = float(pos[0])
        y = float(pos[1])
        width = float(node.attr['width'])*self.dpi
        height = float(node.attr['height'])*self.dpi
        return (
            x*(self.dpi/self.DEFAULTDPI)-width/2,
            self._bb[3]-y*(self.dpi/self.DEFAULTDPI)-height/2,
            width,
            height,
        )

    def calcbb(self,graph):
        for x in graph.graph_attr['bb'].split(','):
            yield float(x)*(self.dpi/self.DEFAULTDPI)

    def drawGraph(self,graph):
        self.scene().clear()
        self._zoom = 0
        if graph is not None:
            self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
            self.dpi = int(graph.graph_attr.get('dpi',96))
            self._bb = tuple(self.calcbb(graph))

            for node in graph.nodes():
                item = NodeGraphicsItem(
                    *self.calc_node_pos(node),node,app=self.app)
                self.scene().addItem(item)
            for edge in graph.edges():
                x = self.app.get_node_from_graph(edge[0])
                y = self.app.get_node_from_graph(edge[1])
                item = GVEdgeGraphicsItem()
                item.setPath(edge,self._bb[3],(self.dpi/self.DEFAULTDPI))
                self.scene().addItem(item)
        else:
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self._bb = None
        self.fitInView()
   

class NodeGraphicsItem(CodedMediaMixin,QtWidgets.QGraphicsEllipseItem):

    def __init__(self,x,y,width,height,node,app=None):
        super(NodeGraphicsItem,self).__init__(x,y,width,height)
        self.node = node
        self.settings = app.settings
        self.data = app.get_node_from_graph(node)
        self.app = app
        if 'fillcolor' in dict(node.attr):
            color = QtGui.QColor(node.attr['fillcolor'])
            self.setBrush(QtGui.QBrush(color, style=QtCore.Qt.SolidPattern))
        self.textitem = QtWidgets.QGraphicsTextItem(node.attr['label'],parent=self)
        self.textitem.setPos(x+width/4,y+height/4)

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.addAction('Memo')
        if self.data.get('cid') is not None:
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
            ui = DialogMemo(self.settings,"Memo for Code " + data['name'], data['memo'])
            ui.exec_()
            self.data['memo'] = ui.memo
            cur = self.app.conn.cursor()
            cur.execute("update code_name set memo=? where cid=?", (self.data['memo'], self.data['cid']))
            self.app.conn.commit()
        if data['catid'] is not None and data['cid'] is None:
            ui = DialogMemo(self.settings,"Memo for Category " + data['name'], data['memo'])
            ui.exec_()
            self.data['memo'] = ui.memo
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set memo=? where catid=?", (self.data['memo'], self.data['catid']))
            self.app.conn.commit()

    def case_media(self, data):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders. """

        ui = DialogInformation("Coded media for cases: " + self.data['name'], "")
        cur = self.app.conn.cursor()
        CODENAME = 0
        COLOR = 1
        CASE_NAME = 2
        POS0 = 3
        POS1 = 4
        SELTEXT = 5
        OWNER = 6
        # Text
        sql = "select code_name.name, color, cases.name, "
        sql += "code_text.pos0, code_text.pos1, seltext, code_text.owner from code_text "
        sql += " join code_name on code_name.cid = code_text.cid "
        sql += " join (case_text join cases on cases.caseid = case_text.caseid) on "
        sql += " code_text.fid = case_text.fid "
        sql += "and (code_text.pos0 between case_text.pos0 and case_text.pos1) "
        sql += "and (code_text.pos1 between case_text.pos0 and case_text.pos1) "
        sql += " where code_name.cid=" + str(self.data['cid'])
        sql += " order by cases.name, code_text.pos0, code_text.owner "

        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            color = row[COLOR]
            title = '<br /><span style=\"background-color:' + color + '\">'
            title += " Case: <em>" + row[CASE_NAME] + "</em></span>"
            title += ", Coder: <em>" + row[OWNER] + "</em> "
            title += ", " + str(row[POS0]) + " - " + str(row[POS1])
            title += "<br />"
            tmp_html = row[SELTEXT].replace("&", "&amp;")
            tmp_html = tmp_html.replace("<", "&lt;")
            tmp_html = tmp_html.replace(">", "&gt;")
            html = title + tmp_html + "</p><br />"
            ui.ui.textEdit.insertHtml(html)

        # Images
        sql = "select code_name.name, color, cases.name, "
        sql += "x1, y1, width, height, code_image.owner,source.mediapath, source.id, "
        sql += "code_image.memo from "
        sql += "code_image join code_name on code_name.cid = code_image.cid "
        sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
        sql += "code_image.id = case_text.fid "
        sql += " join source on case_text.fid = source.id "
        sql += "where code_name.cid = " + str(self.data['cid']) + " "
        sql += " order by cases.name, code_image.owner "
        cur.execute(sql)
        results = cur.fetchall()
        for counter, row in enumerate(results):
            color = row[COLOR]
            title = '<br /><span style=\"background-color:' + color + '\">'
            title += " Case: <em>" + row[CASE_NAME] + "</em></span>, File:" + row[8] + ", "
            title += "Coder: " + row[7]
            ui.ui.textEdit.insertHtml(title)
            img = {'mediapath': row[8], 'x1': row[3], 'y1': row[4], 'width': row[5], 'height': row[6]}
            self.put_image_into_textedit(img, counter, ui.ui.textEdit)
            ui.ui.textEdit.append("Memo: " + row[10] + "\n\n")

        # A/V Media
        sql = "select code_name.name, color, cases.name, "
        sql += "code_av.pos0, code_av.pos1, code_av.memo, code_av.owner,source.mediapath, "
        sql += "source.id from "
        sql += "code_av join code_name on code_name.cid = code_av.cid "
        sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
        sql += "code_av.id = case_text.fid "
        sql += " join source on case_text.fid = source.id "
        sql += "where code_name.cid = " + str(self.data['cid'])
        sql += " order by source.name, code_av.owner "
        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            html = '<span style=\"background-color:' + row[COLOR] + '\">Case: ' + row[CASE_NAME]
            html += ', File: ' + row[7] + '</span>'
            ui.ui.textEdit.insertHtml(html)
            start = msecs_to_mins_and_secs(row[3])
            end = msecs_to_mins_and_secs(row[4])
            ui.ui.textEdit.insertHtml('<br />[' + start + ' - ' + end + '] Coder: ' + row[6])
            ui.ui.textEdit.append("Memo: " + row[5] + "\n\n")

        ui.exec_()

    def put_image_into_textedit(self, img, counter, text_edit):
        """ Scale image, add resource to document, insert image.
        A counter is important as each image slice needs a unique name, counter adds
        the uniqueness to the name.
        """

        path = self.settings['path'] + img['mediapath']
        document = text_edit.document()
        image = QtGui.QImageReader(path).read()
        image = image.copy(img['x1'], img['y1'], img['width'], img['height'])
        # scale to max 300 wide or high. perhaps add option to change maximum limit?
        scaler = 1.0
        scaler_w = 1.0
        scaler_h = 1.0
        if image.width() > 300:
            scaler_w = 300 / image.width()
        if image.height() > 300:
            scaler_h = 300 / image.height()
        if scaler_w < scaler_h:
            scaler = scaler_w
        else:
            scaler = scaler_h
        # need unique image names or the same image from the same path is reproduced
        imagename = self.settings['path'] + '/images/' + str(counter) + '-' + img['mediapath']
        url = QtCore.QUrl(imagename)
        document.addResource(QtGui.QTextDocument.ImageResource, url, QtCore.QVariant(image))
        cursor = text_edit.textCursor()
        image_format = QtGui.QTextImageFormat()
        image_format.setWidth(image.width() * scaler)
        image_format.setHeight(image.height() * scaler)
        image_format.setName(url.toString())
        cursor.insertImage(image_format)
        text_edit.insertHtml("<br />")

class MainWindow(QtWidgets.QWidget):

    def __init__(self,app):
        super(MainWindow, self).__init__()
        self.app = app 
        self.view = GraphViewer(app,parent=self)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(self.view)                       
        button = QtWidgets.QPushButton('View',self)
        self.layout().addWidget(button)
        button.pressed.connect(self.do_graph)

    def do_graph(self):
        # name = self.comboBox.currentText()
        topnode = get_first_with_attr(self.app.categories,catid=12)
        # topnode = get_first_with_attr(self.app.categories,name=name)
        graph = plot_with_pygraphviz(
            self.app.categories,self.app.codes,topnode=topnode)
        self.view.drawGraph(graph)

    def wheelEvent(self,event):
        self.view.wheelEvent(event)
        event.accept()

