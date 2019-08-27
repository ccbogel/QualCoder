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

from copy import deepcopy
import datetime
import logging
import os
from random import randint
import sys
import traceback

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush

from add_item_name import DialogAddItemName
from confirm_delete import DialogConfirmDelete
from color_selector import DialogColorSelect
from color_selector import colors
from GUI.ui_dialog_code_image import Ui_Dialog_code_image
from GUI.ui_dialog_view_image import Ui_Dialog_view_image
from memo import DialogMemo
from select_file import DialogSelectFile


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogCodeImage(QtWidgets.QDialog):
    """ View and code images. Create codes and categories.  """

    settings = None
    parent_textEdit = None
    filename = None
    pixmap = None
    scene = None
    files = []
    file_ = None
    codes = []
    categories = []
    selection = None  # initial code rectangle point
    scale = 1.0
    code_areas = []

    def __init__(self, settings, parent_textEdit):
        """ Show list of image files.
        On select, Show a scaleable and scrollable image.
        Can add a memo to image
        The slider values range from 9 to 99 with intervals of 3.
        """

        sys.excepthook = exception_handler
        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.codes = []
        self.categories = []
        self.files = []
        self.file_ = None
        self.log = ""
        self.scale = 1.0
        self.selection = None
        self.get_image_files()
        self.get_codes_categories()
        self.get_coded_areas()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_image()
        self.ui.setupUi(self)
        self.ui.splitter.setSizes([100, 300])
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        # need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.scene.installEventFilter(self)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)
        treefont = QtGui.QFont(settings['font'], settings['treefontsize'], QtGui.QFont.Normal)
        self.ui.treeWidget.setFont(treefont)
        self.ui.label_coder.setText("Coder: " + settings['codername'])
        self.setWindowTitle("Image coding")
        self.ui.horizontalSlider.valueChanged[int].connect(self.change_scale)
        self.ui.pushButton_memo.setEnabled(False)
        self.ui.pushButton_memo.pressed.connect(self.image_memo)
        self.ui.pushButton_select.pressed.connect(self.select_image)
        self.ui.checkBox_show_coders.stateChanged.connect(self.show_or_hide_coders)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label)
        self.fill_tree()

    def get_codes_categories(self):
        """ Called from init, delete category/code. """

        self.categories = []
        cur = self.settings['conn'].cursor()
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat")
        result = cur.fetchall()
        for row in result:
            self.categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
            'date': row[3], 'memo': row[4], 'supercatid': row[5]})
        self.codes = []
        cur = self.settings['conn'].cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        for row in result:
            self.codes.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'cid': row[4], 'catid': row[5], 'color': row[6]})

    def get_coded_areas(self):
        """ Get the coded area details for the rectangles.
        Called by init and by unmark. """

        self.code_areas = []
        sql = "select imid,id,x1, y1, width, height, memo, date, owner, cid from code_image"
        cur = self.settings['conn'].cursor()
        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            self.code_areas.append({'imid': row[0], 'id': row[1], 'x1': row[2], 'y1': row[3],
            'width': row[4], 'height': row[5], 'memo': row[6], 'date': row[7], 'owner': row[8],
            'cid': row[9]})

    def get_image_files(self):
        """ Load the image file data. """

        self.files = []
        cur = self.settings['conn'].cursor()
        sql = "select name, id, memo, owner, date, mediapath from source where "
        sql += "substr(mediapath,1,7) = '/images' order by name"
        cur.execute(sql)
        result = cur.fetchall()
        for row in result:
            self.files.append({'name': row[0], 'id': row[1], 'memo': row[2],
            'owner': row[3], 'date': row[4], 'mediapath': row[5]})

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(3)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo")])
        self.ui.treeWidget.setColumnHidden(1, True)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
                top_item.setToolTip(0, c['owner'] + "\n" + c['date'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            #try:
            cats.remove(item)
            #except Exception as e:
            #    print(e, item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child, then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            #logger.debug("cats:" + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
                        child.setToolTip(0, c['owner'] + "\n" + c['date'])
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
                top_item.setToolTip(0, c['owner'] + "\n" + c['date'])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children to categories
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "":
                        memo = "Memo"
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
                    child.setToolTip(0, c['owner'] + "\n" + c['date'])
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()

    def select_image(self):
        """  A dialog of filenames is presented to the user.
        The selected image file is then displayed for coding. """

        ui = DialogSelectFile(self.files, _("Select file to view"), "single")
        ok = ui.exec_()
        if ok:
            self.file_ = ui.get_selected()
            self.load_image()

    def load_image(self):
        """ Add image to scene if it exists. """

        #try:
        source = self.settings['path'] + self.file_['mediapath']
        #except Exception as e:
        #    QtWidgets.QMessageBox.warning(None, "Image error", "Image file not found. %s\n" + str(e), self.file_['name'])
        #    logger.warning(str(e) + ".  " + source)
        image = QtGui.QImage(source)
        if image.isNull():
            QtWidgets.QMessageBox.warning(None, _("Image Error"), _("Cannot open: ") + source)
            self.close()
            logger.warning("Cannot open image: " + source)
            return
        items = list(self.scene.items())
        for i in range(items.__len__()):
            self.scene.removeItem(items[i])
        self.setWindowTitle(_("Image: ") + self.file_['name'])
        self.ui.pushButton_memo.setEnabled(True)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)
        self.draw_coded_areas()

    def change_scale(self):
        """ Resize image. Triggered by user change in slider.
        Also called by unmark, as all items need to be redrawn. """

        if self.pixmap is None:
            return
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = self.scale * self.pixmap.height()
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.FastTransformation)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_areas()

    def show_or_hide_coders(self):
        """ When checked call on draw_coded_areas to either show all coders codings,
        otherwise only show current coder.
        Change scale is called becuase all items need to be removed and then added to the
        scene. pixmap being the first item added then the codings.
        """

        self.change_scale()

    def draw_coded_areas(self):
        """ draw coded areas with scaling.
        Remove items first, as this is called after a coded area is unmarked. """

        for item in self.code_areas:
            if item['id'] == self.file_['id']:
                tooltip = ""
                for c in self.codes:
                    if c['cid'] == item['cid']:
                        tooltip = c['name'] + " (" + item['owner'] + ")"
                x = item['x1'] * self.scale
                y = item['y1'] * self.scale
                width = item['width'] * self.scale
                height = item['height'] * self.scale
                rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
                rect_item.setPen(QtGui.QPen(QtCore.Qt.red, 2, QtCore.Qt.DashLine))
                rect_item.setToolTip(tooltip)
                if self.ui.checkBox_show_coders.isChecked():
                    self.scene.addItem(rect_item)
                else:
                    if item['owner'] == self.settings['codername']:
                        self.scene.addItem(rect_item)

    def fill_code_label(self):
        """ Fill code label with curently selected item's code name. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.setText(_("NO CODE SELECTED"))
            return
        self.ui.label_code.setText(_("Code: ") + current.text(0))

    def image_memo(self):
        """ Create a memo for the image file. """

        ui = DialogMemo(self.settings, _("Memo for image ") + self.file_['name'],
            self.file_['memo'])
        ui.exec_()
        cur = self.settings['conn'].cursor()
        cur.execute('update source set memo=? where id=?', (ui.memo, self.file_['id']))
        self.settings['conn'].commit()
        self.file_['memo'] = ui.memo

    def tree_menu(self, position):
        """ Context menu for treewidget items.
        Add, rename, memo, move or delete code or category. Change code color. """

        menu = QtWidgets.QMenu()
        selected = self.ui.treeWidget.currentItem()
        #print(selected.parent())
        #index = self.ui.treeWidget.currentIndex()
        ActionItemAddCode = menu.addAction(_("Add a new code"))
        ActionItemAddCategory = menu.addAction(_("Add a new category"))
        ActionItemRename = menu.addAction(_("Rename"))
        ActionItemEditMemo = menu.addAction(_("View or edit memo"))
        ActionItemDelete = menu.addAction(_("Delete"))
        if selected is not None and selected.text(1)[0:3] == 'cid':
            ActionItemChangeColor = menu.addAction(_("Change code color"))

        action = menu.exec_(self.ui.treeWidget.mapToGlobal(position))
        if selected is not None and selected.text(1)[0:3] == 'cid' and action == ActionItemChangeColor:
            self.change_code_color(selected)
        if action == ActionItemAddCategory:
            self.add_category()
        if action == ActionItemAddCode:
            self.add_code()
        if selected is not None and action == ActionItemRename:
            self.rename_category_or_code(selected)
        if selected is not None and action == ActionItemEditMemo:
            self.add_edit_code_memo(selected)
        if selected is not None and action == ActionItemDelete:
            self.delete_category_or_code(selected)

    def eventFilter(self, object, event):
        """ Using this event filter to identfiy treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop	63	A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop
        Also use eventFilter for QGraphicsView.
        """

        if object is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Drop:
                item = self.ui.treeWidget.currentItem()
                parent = self.ui.treeWidget.itemAt(event.pos())
                self.item_moved_update_data(item, parent)
                self.get_codes_categories()
                self.fill_tree()

        if object is self.scene:
            #logger.debug(event.type(), type(event))
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == 1:  # left mouse
                #logger.debug(event.type(), type(event))
                if event.type() == QtCore.QEvent.GraphicsSceneMousePress:
                    p0 = event.buttonDownScenePos(1)  # left mouse button
                    #logger.debug("rectangle press:" + str(p0.x()) + ", " + str(p0.y()))
                    self.selection = p0
                    return True
                if event.type() == QtCore.QEvent.GraphicsSceneMouseRelease:
                    p1 = event.lastScenePos()
                    #logger.debug("rectangle release: " + str(p1.x()) +", " + str(p1.y()))
                    self.code_area(p1)
                    return True
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == 2:  # right mouse
                if event.type() == QtCore.QEvent.GraphicsSceneMousePress:
                    p = event.buttonDownScenePos(2)
                    self.scene_context_menu(p)
                    return True
        return False

    def scene_context_menu(self, pos):
        """ Scene context menu for unmarking coded areas and adding memos. """

        # outside image area, no context menu
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                if pos.x() > item.boundingRect().width() or pos.y() > item.boundingRect().height():
                    self.selection = None
                    return

        menu = QtWidgets.QMenu()
        menu.addAction(_('Memo'))
        menu.addAction(_('Unmark'))
        global_pos = QtGui.QCursor.pos()
        item = self.find_coded_areas_for_pos(pos)
        # no coded area item in this mouse position
        if item is None:
            return
        action = menu.exec_(global_pos)
        if action is None:
            return
        if action.text() == _('Memo'):
            self.coded_area_memo(item)
        if action.text() == _('Unmark'):
            self.unmark(item)

    def find_coded_areas_for_pos(self, pos):
        """ Find any coded areas for this position. """

        for item in self.code_areas:
            if item['id'] == self.file_['id']:
                #print(pos, item['x1'], item['y1'], item['width'], item['height'])
                if pos.x() >= item['x1'] * self.scale and pos.x() <= (item['x1'] + item['width']) * self.scale \
                    and pos.y() >= item['y1'] * self.scale and pos.y() <= (item['y1'] + item['height']) * self.scale:
                    #print(pos, item['x1'] * self.scale, item['y1'] * self.scale, item['width'] * self.scale, item['height'] * self.scale)
                    return item
        return None

    def coded_area_memo(self, item):
        """ Add memo to this coded area. """

        ui = DialogMemo(self.settings, _("Memo for coded area of ") + self.file_['name'],
            item['memo'])
        ui.exec_()
        memo = ui.memo
        if memo != item['memo']:
            item['memo'] = memo
            cur = self.settings['conn'].cursor()
            cur.execute('update code_image set memo=? where imid=?', (ui.memo, item['imid']))
            self.settings['conn'].commit()

    def unmark(self, item):
        """ Remove coded area. """

        cur = self.settings['conn'].cursor()
        cur.execute("delete from code_image where imid=?", [item['imid'], ])
        self.settings['conn'].commit()
        self.get_coded_areas()
        self.change_scale()

    def code_area(self, p1):
        """ Created coded area coordinates from mouse release.
        The point and width and height mush be based on the original image size,
        so add in scale factor. """

        code_ = self.ui.treeWidget.currentItem()
        if code_ is None:
            return
        if code_.text(1)[0:3] == 'cat':
            return
        cid = code_.text(1)[4:]
        x = self.selection.x()
        y = self.selection.y()
        #print("x", x, "y", y, "scale", self.scale)
        width = p1.x() - x
        height = p1.y() - y
        if width < 0:
            x = x + width
            width = abs(width)
        if height < 0:
            y = y + height
            height = abs(height)
        #print("SCALED x", x, "y", y, "w", width, "h", height)
        # outside image area, do not code
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                if x + width > item.boundingRect().width() or y + height > item.boundingRect().height():
                    self.selection = None
                    return

        x_unscaled = x / self.scale
        y_unscaled = y / self.scale
        width_unscaled = width / self.scale
        height_unscaled = height / self.scale
        #print("UNSCALED x", x, "y", y, "w", width, "h", height)
        item = {'imid': None, 'id': self.file_['id'], 'x1': x_unscaled, 'y1': y_unscaled,
        'width': width_unscaled, 'height':height_unscaled, 'owner': self.settings['codername'],
         'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'cid': cid,'memo': ''}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,date,owner) values(?,?,?,?,?,?,?,?,?)"
            , (item['id'], item['x1'], item['y1'], item['width'], item['height'], cid, item['memo'],
            item['date'],item['owner']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        imid = cur.fetchone()[0]
        item['imid'] = imid
        self.code_areas.append(item)
        rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
        rect_item.setPen(QtGui.QPen(QtCore.Qt.red, 2, QtCore.Qt.DashLine))
        rect_item.setToolTip(code_.text(0))
        self.scene.addItem(rect_item)
        self.selection = None

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code. """

        # find the category in the list
        if item.text(1)[0:3] == 'cat':
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(item.text(1)[6:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.categories[found]['supercatid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child
                    return
                supercatid = int(parent.text(1).split(':')[1])
                if supercatid == self.categories[found]['catid']:
                    # something went wrong
                    logger.debug("supercatid== self.categories[found][catid]")
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.settings['conn'].cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
            [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.settings['conn'].commit()

        # find the code in the list
        if item.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(item.text(1)[4:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.codes[found]['catid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child, but can merge
                    self.merge_codes(self.codes[found], parent)
                    return
                catid = int(parent.text(1).split(':')[1])
                self.codes[found]['catid'] = catid

            cur = self.settings['conn'].cursor()
            cur.execute("update code_name set catid=? where cid=?",
            [self.codes[found]['catid'], self.codes[found]['cid']])
            self.settings['conn'].commit()

    def merge_codes(self, item, parent):
        """ Merge code or category with another code or category.
        Called by item_moved_update_data when a code is moved onto another code. """

        msg = _("Merge code: ") + item['name'] + " ==> " + parent.text(0)
        reply = QtWidgets.QMessageBox.question(None, _('Merge codes'),
        msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return
        cur = self.settings['conn'].cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        try:
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            self.settings['conn'].commit()
        except Exception as e:
            e = str(e)
            msg = _("Cannot merge codes. Unmark overlapping text.") + "\n" + e
            QtWidgets.QInformationDialog(None, "Cannot merge", msg)
            return
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.settings['conn'].commit()
        self.parent_textEdit.append(msg)

    def add_code(self):
        """ Use add_item dialog to get new code text.
        Add_code_name dialog checks for duplicate code name.
        New code is added to data and database. """

        ui = DialogAddItemName(self.codes, _("Add new code"))
        ui.exec_()
        newCodeText = ui.get_new_name()
        if newCodeText is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': newCodeText, 'memo': "", 'owner': self.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),'catid': None, 'color': code_color}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        cid = cur.fetchone()[0]
        item['cid'] = cid
        self.codes.append(item)
        top_item = QtWidgets.QTreeWidgetItem([item['name'], 'cid:' + str(item['cid']), ""])
        top_item.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
        color = item['color']
        top_item.setBackground(0, QBrush(QtGui.QColor(color), Qt.SolidPattern))
        self.ui.treeWidget.addTopLevelItem(top_item)
        self.ui.treeWidget.setCurrentItem(top_item)
        self.parent_textEdit.append(_("New code: ") + item['name'])

    def add_category(self):
        """ Add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        Add the new category as a top level item. """

        ui = DialogAddItemName(self.categories, _("Category"))
        ui.exec_()
        newCatText = ui.get_new_name()
        if newCatText is None:
            return
        # add to database
        item = {'name': newCatText, 'cid': None, 'memo': "",
        'owner': self.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], None))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        catid = cur.fetchone()[0]
        item['catid'] = catid
        self.categories.append(item)
        # update widget
        top_item = QtWidgets.QTreeWidgetItem([item['name'], 'catid:' + str(item['catid']), ""])
        top_item.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
        self.ui.treeWidget.addTopLevelItem(top_item)
        self.parent_textEdit.append(_("New category: ") + item['name'])

    def delete_category_or_code(self, selected):
        """ Delete the selected category or code.
        If category deleted, sub-level items are retained. """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code_name data and fill
        treeWidget. """

        # find the code_in the list, check to delete
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                found = i
        if found == -1:
            return
        code_ = self.codes[found]
        ui = DialogConfirmDelete(_("Code: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'])
        cur = self.settings['conn'].cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        self.settings['conn'].commit()
        selected = None
        self.get_codes_categories()
        self.fill_tree()

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget. Sub-level items are retained. """

        found = -1
        for i in range(0, len(self.categories)):
            if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                found = i
        if found == -1:
            return
        category = self.categories[found]
        ui = DialogConfirmDelete(_("Category: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])
        cur = self.settings['conn'].cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.settings['conn'].commit()
        selected = None
        self.get_codes_categories()
        self.fill_tree()

    def add_edit_code_memo(self, selected):
        """ View and edit a memo. """

        if selected.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.settings, _("Memo for Code ") + self.codes[found]['name'],
            self.codes[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
            # update codes list and database
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.settings['conn'].cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.settings['conn'].commit()

        if selected.text(1)[0:3] == 'cat':
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.settings, _("Memo for Category: ") + self.categories[found]['name'],
            self.categories[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
            # update codes list and database
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.settings['conn'].cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.settings['conn'].commit()

    def rename_category_or_code(self, selected):
        """ Rename a code or category. Checks that the proposed code or category name is
        not currently in use. """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"), _("New code name:"),
            QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other code has this text
            for c in self.codes:
                if c['name'] == new_name:
                    QtWidgets.QMessageBox.warning(None, _("Name in use"),
                    new_name + _(" Choose another name"), QtWidgets.QMessageBox.Ok)
                    return
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # Update codes list and database
            cur = self.settings['conn'].cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.settings['conn'].commit()
            old_name = self.codes[found]['name']
            self.codes[found]['name'] = new_name
            selected.setData(0, QtCore.Qt.DisplayRole, new_name)
            self.parent_textEdit.append(_("Code renamed: ") + \
                old_name + " ==> " + new_name)
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
            QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other category has this text
            for c in self.categories:
                if c['name'] == new_name:
                    msg = _("This category name is already in use")
                    QtWidgets.QMessageBox.warning(None, _("Duplicate category name"), msg, QtWidgets.QMessageBox.Ok)
                    return
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            # update category list and database
            cur = self.settings['conn'].cursor()
            cur.execute("update code_cat set name=? where catid=?",
            (new_name, self.categories[found]['catid']))
            self.settings['conn'].commit()
            old_name = self.categories[found]['name']
            self.categories[found]['name'] = new_name
            selected.setData(0, QtCore.Qt.DisplayRole, new_name)
            self.parent_textEdit.append(_("Category renamed from: ") + \
                old_name + " ==> " + new_name)

    def change_code_color(self, selected):
        """ Change the color of the currently selected code. """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.codes[found]['color'])
        ok = ui.exec_()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        #print(new_color)
        selected.setBackground(0, QBrush(QtGui.QColor(new_color), Qt.SolidPattern))
        #update codes list and database
        self.codes[found]['color'] = new_color
        cur = self.settings['conn'].cursor()
        cur.execute("update code_name set color=? where cid=?",
        (self.codes[found]['color'], self.codes[found]['cid']))
        self.settings['conn'].commit()


class DialogViewImage(QtWidgets.QDialog):
    """ View image. View and edit displayed memo.
    Show a scaleable and scrollable image.
    The slider values range from 10 to 99.
    """

    settings = None
    image_data = None
    pixmap = None
    label = None

    def __init__(self, settings, image_data, parent=None):
        """ Image_data contains: {name, mediapath, owner, id, date, memo, fulltext}
        """

        sys.excepthook = exception_handler
        self.settings = settings
        self.image_data = image_data
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_view_image()
        self.ui.setupUi(self)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)
        self.setWindowTitle(self.image_data['mediapath'])
        try:
            source = self.settings['path'] + self.image_data['mediapath']
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, _("Image error"), _("Image file not found: ") + source + "\n" + str(e))
        image = QtGui.QImage(source)
        if image.isNull():
            QtWidgets.QMessageBox.warming(None, _("Image Error"), _("Cannot open: ") + source)
            self.close()
            return
        self.pixmap = QtGui.QPixmap.fromImage(image)
        self.label = QtWidgets.QLabel()
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.label.setFixedWidth(self.pixmap.width())
        self.label.setFixedHeight(self.pixmap.height())
        self.label.setScaledContents(True)
        self.label.setPixmap(self.pixmap)
        self.ui.scrollArea.setWidget(self.label)
        self.ui.horizontalSlider.valueChanged[int].connect(self.change_scale)
        self.ui.textEdit.setText(self.image_data['memo'])

    def change_scale(self):
        """ Resize image. Idea from:
        https://github.com/baoboa/pyqt5/blob/master/examples/widgets/imageviewer.py
        """

        scale = (self.ui.horizontalSlider.value() + 1) / 100
        new_label = self.label.resize(scale * self.label.pixmap().size())
        self.label.setFixedWidth(scale * self.pixmap.width())
        self.label.setFixedHeight(scale * self.pixmap.height())
        self.ui.scrollArea.setWidget(new_label)





