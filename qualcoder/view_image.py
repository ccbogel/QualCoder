# -*- coding: utf-8 -*-

"""Copyright (c) 2020 Colin Curtain

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
import platform
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
from helpers import msecs_to_mins_and_secs, Message
from information import DialogInformation
from memo import DialogMemo
from select_items import DialogSelectItems

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


class DialogCodeImage(QtWidgets.QDialog):
    """ View and code images. Create codes and categories.  """

    app = None
    dialog_list = None
    parent_textEdit = None
    filename = None
    pixmap = None
    scene = None
    files = []
    file_ = None
    codes = []
    categories = []
    selection = None  # Initial code rectangle point
    scale = 1.0
    code_areas = []

    def __init__(self, app, parent_textEdit, dialog_list):
        """ Show list of image files.
        On select, Show a scaleable and scrollable image.
        Can add a memo to image
        The slider values range from 9 to 99 with intervals of 3.
        """

        super(DialogCodeImage,self).__init__()
        sys.excepthook = exception_handler
        self.app = app
        self.dialog_list = dialog_list
        self.parent_textEdit = parent_textEdit
        self.codes = []
        self.categories = []
        self.files = []
        self.file_ = None
        self.log = ""
        self.scale = 1.0
        self.selection = None
        self.get_image_files()
        self.get_codes_and_categories()
        self.get_coded_areas()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_image()
        self.ui.setupUi(self)
        self.ui.checkBox_show_coders.hide()
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.ui.splitter.setSizes([100, 300])
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        # Need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.scene.installEventFilter(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        tree_font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        tree_font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        self.ui.label_code.setStyleSheet(tree_font)  # usually smaller font
        self.ui.label_coder.setText("Coder: " + self.app.settings['codername'])
        self.setWindowTitle(_("Image coding"))
        self.ui.horizontalSlider.valueChanged[int].connect(self.change_scale)
        # Icon images are 32x32 pixels within 36x36 pixel button
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/notepad_2_icon.png'))
        self.ui.pushButton_memo.setIcon(icon)
        self.ui.pushButton_memo.pressed.connect(self.file_memo)
        self.ui.pushButton_memo.setEnabled(False)
        self.ui.listWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.viewfile_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.ui.listWidget.itemClicked.connect(self.listwidgetitem_view_file)
        self.ui.checkBox_show_coders.stateChanged.connect(self.show_or_hide_coders)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label)
        # The buttons in the splitter are smaller 24x24 pixels
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/playback_next_icon_24.png'))
        self.ui.pushButton_latest.setIcon(icon)
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/playback_play_icon_24.png'))
        self.ui.pushButton_next_file.setIcon(icon)
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/notepad_2_icon_24.png'))
        self.ui.pushButton_document_memo.setIcon(icon)
        self.ui.pushButton_document_memo.pressed.connect(self.file_memo)
        self.ui.label_coded_area_icon.setPixmap(QtGui.QPixmap('GUI/2x2_color_grid_icon_24.png'))
        try:
            s0 = int(self.app.settings['dialogcodeimage_splitter0'])
            s1 = int(self.app.settings['dialogcodeimage_splitter1'])
            # 30 is for the button box
            self.ui.splitter.setSizes([s0, 30, s1])
            h0 = int(self.app.settings['dialogcodeimage_splitter_h0'])
            h1 = int(self.app.settings['dialogcodeimage_splitter_h1'])
            if h0 > 10 and h1 > 10:
                self.ui.splitter_2.setSizes([h0, h1])
        except:
            pass
        self.fill_tree()

    def closeEvent(self, event):
        """ Save dialog and splitter dimensions. """

        self.app.settings['dialogcodeimage_w'] = self.size().width()
        self.app.settings['dialogcodeimage_h'] = self.size().height()
        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodeimage_splitter0'] = sizes[0]
        self.app.settings['dialogcodeimage_splitter1'] = sizes[2]
        sizes = self.ui.splitter_2.sizes()
        self.app.settings['dialogcodeimage_splitter_h0'] = sizes[0]
        self.app.settings['dialogcodeimage_splitter_h1'] = sizes[1]

    def get_codes_and_categories(self):
        """ Called from init, delete category/code, event_filter """

        self.codes, self.categories = self.app.get_data()

    def get_coded_areas(self):
        """ Get the coded area details for the rectangles.
        Called by init and by unmark. """

        self.code_areas = []
        sql = "select imid,id,x1, y1, width, height, memo, date, owner, cid from code_image"
        cur = self.app.conn.cursor()
        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            self.code_areas.append({'imid': row[0], 'id': row[1], 'x1': row[2], 'y1': row[3],
            'width': row[4], 'height': row[5], 'memo': row[6], 'date': row[7], 'owner': row[8],
            'cid': row[9]})

    def get_image_files(self):
        """ Load the image file data. Exclude those image file data where there are bad links."""

        bad_links = self.app.check_bad_file_links()
        bl_sql = ""
        for bl in bad_links:
            bl_sql += "," + str(bl['id'])
        if len(bl_sql) > 0:
            bl_sql = " and id not in (" + bl_sql[1:] + ") "

        self.files = []
        cur = self.app.conn.cursor()
        sql = "select name, id, memo, owner, date, mediapath from source where "
        sql += "substr(mediapath,1,7) in ('/images', 'images:') " + bl_sql + " order by name"
        cur.execute(sql)
        result = cur.fetchall()
        self.files = []
        keys = 'name', 'id', 'memo', 'owner', 'date', 'mediapath'
        for row in result:
            self.files.append(dict(zip(keys, row)))

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
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
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "" and c['memo'] is not None:
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(2, c['memo'])
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
            count = 0
            while item and count < 10000:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "" and c['memo'] is not None:
                        memo = "Memo"
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setToolTip(2, c['memo'])
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.ui.treeWidget.expandAll()
        self.fill_code_counts_in_tree()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code for current coder and in the selected file.
        Called by: fill_tree """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_image where cid=? and id=? and owner=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                cur.execute(sql, [cid, self.file_['id'], self.app.settings['codername']])
                result = cur.fetchone()
                if result[0] > 0:
                    item.setText(3, str(result[0]))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def file_memo(self):
        """ Open file memo to view or edit. """

        if self.file_ is None:
            return
        ui = DialogMemo(self.app, _("Memo for file: ") + self.file_['name'], self.file_['memo'])
        ui.exec_()
        memo = ui.memo
        if memo == self.file_['memo']:
            return
        self.file_['memo'] = memo
        cur = self.app.conn.cursor()
        cur.execute("update source set memo=? where id=?", (memo, self.file_['id']))
        self.app.conn.commit()
        self.get_image_files()
        self.ui.listWidget.clear()
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.app.delete_backup = False

    def go_to_latest_coded_file(self):
        """ Vertical splitter button activates this """

        sql = "SELECT id FROM code_image where owner=? order by date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql, [self.app.settings['codername'], ])
        result = cur.fetchone()
        if result is None:
            return
        for i, f in enumerate(self.files):
            if f['id'] == result[0]:
                self.file_ = f
                self.ui.listWidget.setCurrentRow(i)
                self.load_file()
                break

    def go_to_next_file(self):
        """ Vertical splitter button activates this.
         Assumes one or more items in the list widget.
         As the coding dialog will not open with no AV files. """

        if self.file_ is None:
            self.file_ = self.files[0]
            self.ui.listWidget.setCurrentRow(0)
            self.load_file()
            return
        for i in range(0, len(self.files) - 1):
            if self.file_ == self.files[i]:
                found = self.files[i + 1]
                self.file_ = found
                self.ui.listWidget.setCurrentRow(i + 1)
                self.load_file()
                return

    def viewfile_menu(self, position):
        """ Context menu to select the next image alphabetically, or
         to select the image that was most recently coded """

        if len(self.files) < 2:
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_next = menu.addAction(_("Next file"))
        action_latest = menu.addAction(_("File with latest coding"))
        action = menu.exec_(self.ui.listWidget.mapToGlobal(position))
        if action == action_next:
            self.go_to_next_file()
            return
        if action == action_latest:
            self.go_to_latest_coded_file()
            return

    def listwidgetitem_view_file(self):
        """ Item selected so fill current file variable and load. """

        if len(self.files) == 0:
            return
        itemname = self.ui.listWidget.currentItem().text()
        for f in self.files:
            if f['name'] == itemname:
                self.file_ = f
                self.load_file()
                break

    def load_file(self):
        """ Add image to scene if it exists. If not exists clear the GUI and variables.
        Called by: select_image_menu, listwidgetitem_view_file
        """

        self.ui.label_coded_area.setText("Coded area")
        self.ui.label_coded_area.setToolTip("")
        source = self.app.project_path + self.file_['mediapath']
        if self.file_['mediapath'][0:7] == "images:":
            source = self.file_['mediapath'][7:]
        image = QtGui.QImage(source)
        if image.isNull():
            Message(self.app, _("Image Error"), _("Cannot open: ", "warning") + source).exec_()
            logger.warning("Cannot open image: " + source)
            # Must remove any existing loaded images and clear variables
            self.file_ = None
            self.filename = None
            self.selection = None
            self.scale = 1.0
            items = list(self.scene.items())
            for i in range(items.__len__()):
                self.scene.removeItem(items[i])
            self.setWindowTitle(_("Image coding"))
            self.ui.pushButton_memo.setEnabled(False)
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
        self.fill_code_counts_in_tree()

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree in DialogCodeImage, DialogCodeAV,
        DialogCodeText, DialogReportCodes.
        Not using isinstance for other classes as could not import the classes to test
        against. There was an import error.
        Using try except blocks for each instance, as instance may have been deleted.
        """

        for d in self.dialog_list:
            if str(type(d)) == "<class 'code_text.DialogCodeText'>":
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.unlight()
                    d.highlight()
                    d.get_coded_text_update_eventfilter_tooltips()
                except RuntimeError as e:
                    pass
            if str(type(d)) == "<class 'view_av.DialogCodeAV'>":
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.load_segments()
                    d.unlight()
                    d.highlight()
                    d.get_coded_text_update_eventfilter_tooltips()
                except RuntimeError as e:
                    pass
            if isinstance(d, DialogCodeImage):
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.get_coded_areas()
                    d.draw_coded_areas()
                except RuntimeError as e:
                    pass
            if str(type(d)) == "<class 'reports.DialogReportCodes'>":
                try:
                    d.get_data()
                    d.fill_tree()
                except RuntimeError as e:
                    pass

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
        self.ui.horizontalSlider.setToolTip(_("Scale: ") + str(int(self.scale * 100)) + "%")

    def show_or_hide_coders(self):
        """ When checked call on draw_coded_areas to either show all coders codings,
        otherwise only show current coder.
        Change scale is called becuase all items need to be removed and then added to the
        scene. pixmap being the first item added then the codings.
        """

        self.change_scale()

    def draw_coded_areas(self):
        """ Draw coded areas with scaling. This coder is shown in dashed rectangles.
        Other coders are shown via dotline rectangles.
        Remove items first, as this is called after a coded area is unmarked. """

        if self.file_ is None:
            return
        for item in self.code_areas:
            if item['id'] == self.file_['id']:
                color = QtGui.QColor('#AA0000')  # Default color
                color = None
                tooltip = ""
                for c in self.codes:
                    if c['cid'] == item['cid']:
                        tooltip = c['name'] + " (" + item['owner'] + ")"
                        tooltip += "\nMemo: " + item['memo']
                        color = QtGui.QColor(c['color'])
                x = item['x1'] * self.scale
                y = item['y1'] * self.scale
                width = item['width'] * self.scale
                height = item['height'] * self.scale
                rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
                rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.DashLine))
                rect_item.setToolTip(tooltip)
                if item['owner'] == self.app.settings['codername']:
                    self.scene.addItem(rect_item)
                if self.ui.checkBox_show_coders.isChecked() and item['owner'] != self.app.settings['codername']:
                    rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.DotLine))
                    self.scene.addItem(rect_item)

    def fill_code_label(self):
        """ Fill code label with currently selected item's code name. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.setText(_("NO CODE SELECTED"))
            return
        self.ui.label_code.setText(_("Code: ") + current.text(0))
        # update background colour of label
        for c in self.codes:
            if current.text(0) == c['name']:
                palette = self.ui.label_code.palette()
                code_color = QtGui.QColor(c['color'])
                palette.setColor(QtGui.QPalette.Window, code_color)
                self.ui.label_code.setPalette(palette)
                self.ui.label_code.setAutoFillBackground(True)
                break

    def tree_menu(self, position):
        """ Context menu for treewidget items.
        Add, rename, memo, move or delete code or category. Change code color. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        selected = self.ui.treeWidget.currentItem()
        #print(selected.parent())
        #index = self.ui.treeWidget.currentIndex()
        ActionItemAddCode = menu.addAction(_("Add a new code"))
        ActionItemAddCategory = menu.addAction(_("Add a new category"))
        ActionItemRename = menu.addAction(_("Rename"))
        ActionItemEditMemo = menu.addAction(_("View or edit memo"))
        ActionItemDelete = menu.addAction(_("Delete"))
        ActionItemChangeColor = None
        ActionShowCodedMedia = None
        ActionMoveCode = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            ActionItemChangeColor = menu.addAction(_("Change code color"))
            ActionMoveCode = menu.addAction(_("Move code to"))
            ActionShowCodedMedia = menu.addAction(_("Show coded text and media"))
        ActionShowCodesLike = menu.addAction(_("Show codes like"))

        action = menu.exec_(self.ui.treeWidget.mapToGlobal(position))
        if selected is not None and selected.text(1)[0:3] == 'cid' and action == ActionItemChangeColor:
            self.change_code_color(selected)
        if selected is not None and action == ActionMoveCode:
            self.move_code(selected)
        if action == ActionItemAddCategory:
            self.add_category()
        if action == ActionItemAddCode:
            self.add_code()
        if action == ActionShowCodesLike:
            self.show_codes_like()
            return
        if selected is not None and action == ActionItemRename:
            self.rename_category_or_code(selected)
        if selected is not None and action == ActionItemEditMemo:
            self.add_edit_code_memo(selected)
        if selected is not None and action == ActionItemDelete:
            self.delete_category_or_code(selected)
        if selected is not None and action == ActionShowCodedMedia:
            found = None
            tofind = int(selected.text(1)[4:])
            for code in self.codes:
                if code['cid'] == tofind:
                    found = code
                    break
            if found:
                self.coded_media_dialog(found)

    def coded_media_dialog(self, data):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Called from tree_menu
        param:
            data: code dictionary
        """
        ui = DialogInformation(self.app, "Coded text and media: " + data['name'], " ")
        cur = self.app.conn.cursor()
        COLOR = 1
        SOURCE_NAME = 2
        POS0 = 3
        POS1 = 4
        SELTEXT = 5
        sql = "select code_name.name, color, source.name, pos0, pos1, seltext from "
        sql += "code_text "
        sql += " join code_name on code_name.cid = code_text.cid join source on fid = source.id "
        sql += " where code_name.cid=? and code_text.owner=?"
        sql += " order by source.name, pos0"
        cur.execute(sql, [data['cid'], self.app.settings['codername']])
        results = cur.fetchall()
        # Text
        for row in results:
            title = '<span style=\"background-color:' + row[COLOR] + '\">'
            title += " File: <em>" + row[SOURCE_NAME] + "</em></span>"
            title += ", " + str(row[POS0]) + " - " + str(row[POS1])
            ui.ui.textEdit.insertHtml(title)
            ui.ui.textEdit.append(row[SELTEXT] + "\n\n")

        # Images
        sql = "select code_name.name, color, source.name, x1, y1, width, height,"
        sql += " source.mediapath, source.id, code_image.memo "
        sql += " from code_image join code_name "
        sql += "on code_name.cid = code_image.cid join source on code_image.id = source.id "
        sql += "where code_name.cid =? and code_image.owner=? "
        sql += " order by source.name"
        cur.execute(sql, [data['cid'], self.app.settings['codername']])
        results = cur.fetchall()
        for counter, row in enumerate(results):
            ui.ui.textEdit.insertHtml('<span style=\"background-color:' + row[COLOR] + '\">File: ' + row[7] + '</span>')
            img = {'mediapath': row[7], 'x1': row[3], 'y1': row[4], 'width': row[5], 'height': row[6]}
            self.put_image_into_textedit(img, counter, ui.ui.textEdit)
            ui.ui.textEdit.append("\nMemo: " + row[9] + "\n\n")

        # Media
        sql = "select code_name.name, color, source.name, pos0, pos1, code_av.memo, "
        sql += "source.mediapath, source.id from code_av join code_name "
        sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
        sql += "where code_name.cid = " + str(data['cid']) + " "
        sql += " order by source.name"
        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            ui.ui.textEdit.insertHtml('<span style=\"background-color:' + row[COLOR] + '\">File: ' + row[6] + '</span>')
            start = msecs_to_mins_and_secs(row[3])
            end = msecs_to_mins_and_secs(row[4])
            ui.ui.textEdit.insertHtml('<br />[' + start + ' - ' + end + '] ')
            ui.ui.textEdit.append("Memo: " + row[5] + "\n\n")
        ui.exec_()

    def put_image_into_textedit(self, img, counter, text_edit):
        """ Scale image, add resource to document, insert image.
        A counter is important as each image slice needs a unique name, counter adds
        the uniqueness to the name.
        Called by: coded_media_dialog
        param:
            img: image data dictionary with file location and width, height, position data
            counter: a changing counter is needed to make discrete different images
            text_edit:  the widget that shows the data
        """

        path = self.app.project_path
        if img['mediapath'][0] == "/":
            path = path + img['mediapath']
        else:
            path = img['mediapath'][7:]
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
        imagename = self.app.project_path + '/images/' + str(counter) + '-' + img['mediapath']
        url = QtCore.QUrl(imagename)
        document.addResource(QtGui.QTextDocument.ImageResource, url, QtCore.QVariant(image))
        cursor = text_edit.textCursor()
        image_format = QtGui.QTextImageFormat()
        image_format.setWidth(image.width() * scaler)
        image_format.setHeight(image.height() * scaler)
        image_format.setName(url.toString())
        cursor.insertImage(image_format)
        text_edit.insertHtml("<br />")

    def move_code(self, selected):
        """ Move code to another category or to no category.
        Uses a list selection.
        param:
            selected : QTreeWidgetItem
         """

        cid = int(selected.text(1)[4:])
        cur = self.app.conn.cursor()
        cur.execute("select name, catid from code_cat order by name")
        res = cur.fetchall()
        category_list = [{'name':"", 'catid': None}]
        for r in res:
            category_list.append({'name':r[0], 'catid': r[1]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec_()
        if not ok:
            return
        category = ui.get_selected()
        cur.execute("update code_name set catid=? where cid=?", [category['catid'], cid])
        self.update_dialog_codes_and_categories()

    def show_codes_like(self):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text. """

        # Input dialog narrow, so code below
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show codes containing"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog.setLabelText(_("Show codes containing text.\n(Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec_()
        if not ok:
            return
        text = str(dialog.textValue())
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, text)

    def recursive_traverse(self, item, text):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories.
        Called by: show_codes_like
        param:
            item: a QTreeWidgetItem
            text:  Text string for matching with code names
        """

        #logger.debug("recurse this item:" + item.text(0) + "|" item.text(1))
        child_count = item.childCount()
        for i in range(child_count):
            #print(item.child(i).text(0) + "|" + item.child(i).text(1))
            if "cid:" in item.child(i).text(1) and len(text) > 0 and text not in item.child(i).text(0):
                item.child(i).setHidden(True)
            if "cid:" in item.child(i).text(1) and text == "":
                item.child(i).setHidden(False)
            self.recursive_traverse(item.child(i), text)

    def eventFilter(self, object, event):
        """ Using this event filter to identify treeWidgetItem drop events.
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
                self.update_dialog_codes_and_categories()

        if object is self.scene:
            #logger.debug(event.type(), type(event))
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == 1:  # left mouse
                #
                pos = event.buttonDownScenePos(1)
                self.fill_coded_area_label(self.find_coded_areas_for_pos(pos))
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
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        menu.addAction(_('Memo'))
        menu.addAction(_('Unmark'))
        global_pos = QtGui.QCursor.pos()
        item = self.find_coded_areas_for_pos(pos)
        # no coded area item in this mouse position
        if item is None:
            return
        self.fill_coded_area_label(item)
        action = menu.exec_(global_pos)
        if action is None:
            return
        if action.text() == _('Memo'):
            self.coded_area_memo(item)
            self.app.delete_backup = False
        if action.text() == _('Unmark'):
            self.unmark(item)
            self.app.delete_backup = False

    def find_coded_areas_for_pos(self, pos):
        """ Find any coded areas for this position AND for this coder.

        param: pos
        returns: None or coded item
        """

        for item in self.code_areas:
            if item['id'] == self.file_['id'] and item['owner'] == self.app.settings['codername']:
                #print(pos, item['x1'], item['y1'], item['width'], item['height'])
                if pos.x() >= item['x1'] * self.scale and pos.x() <= (item['x1'] + item['width']) * self.scale \
                    and pos.y() >= item['y1'] * self.scale and pos.y() <= (item['y1'] + item['height']) * self.scale:
                    #print(pos, item['x1'] * self.scale, item['y1'] * self.scale, item['width'] * self.scale, item['height'] * self.scale)
                    return item
        return None

    def fill_coded_area_label(self, item):
        """ Fill details of label about the currently clicked on coded area.
        Called by: right click scene menu, """

        if item is None:
            return
        #TODO if multiple items ?
        code_name = ""
        for c in self.codes:
            if c['cid'] == item['cid']:
                codename = c['name']
                break
        msg = codename
        msg += "\nx:" +str(int(item['x1'])) + " y:" + str(int(item['y1']))
        msg += " w:" + str(int(item['width'])) + " h:" + str(int(item['height']))
        area = item['width'] * item['height']
        pic_area = self.pixmap.width() * self.pixmap.height()
        percent_area = round(area / pic_area * 100, 2)
        msg += " area: " + str(percent_area) + "%"
        #print(item)
        self.ui.label_coded_area.setText(msg)
        self.ui.label_coded_area.setToolTip(item['memo'])

    def coded_area_memo(self, item):
        """ Add memo to this coded area.
        param:
            item : dictionary of coded area """

        ui = DialogMemo(self.app, _("Memo for coded area of ") + self.file_['name'],
            item['memo'])
        ui.exec_()
        memo = ui.memo
        if memo != item['memo']:
            item['memo'] = memo
            cur = self.app.conn.cursor()
            cur.execute('update code_image set memo=? where imid=?', (ui.memo, item['imid']))
            self.app.conn.commit()
        # re-draw to update memos in tooltips
        self.draw_coded_areas()

    def unmark(self, item):
        """ Remove coded area.
        param:
            item : dictionary of coded area """

        cur = self.app.conn.cursor()
        cur.execute("delete from code_image where imid=?", [item['imid'], ])
        self.app.conn.commit()
        self.get_coded_areas()
        self.change_scale()
        self.fill_code_counts_in_tree()

    def code_area(self, p1):
        """ Create coded area coordinates from mouse release.
        The point and width and height must be based on the original image size,
        so add in scale factor.
        param:
            p1 : QPoint of mouse release """

        code_ = self.ui.treeWidget.currentItem()
        if code_ is None:
            return
        if code_.text(1)[0:3] == 'cat':
            return
        cid = int(code_.text(1)[4:])  # must be integer
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
        'width': width_unscaled, 'height':height_unscaled, 'owner': self.app.settings['codername'],
         'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'cid': cid,'memo': ''}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,date,owner) values(?,?,?,?,?,?,?,?,?)"
            , (item['id'], item['x1'], item['y1'], item['width'], item['height'], cid, item['memo'],
            item['date'],item['owner']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        imid = cur.fetchone()[0]
        item['imid'] = imid
        self.code_areas.append(item)
        rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
        color = None
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(cid):
                color = QtGui.QColor(self.codes[i]['color'])
        if color is None:
            print("ERROR")
            return
        rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.DashLine))
        rect_item.setToolTip(code_.text(0))
        self.scene.addItem(rect_item)
        self.selection = None
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code.
        param:
            item : QTreeWidgetItem
            parent : QTreeWidgetItem """

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
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
            [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False
            return

        # Find the code in the list
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
            cur = self.app.conn.cursor()
            cur.execute("update code_name set catid=? where cid=?",
            [self.codes[found]['catid'], self.codes[found]['cid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False

    def merge_codes(self, item, parent):
        """ Merge code or category with another code or category.
        Called by item_moved_update_data when a code is moved onto another code.
        param:
            item : QTreeWidgetItem
            parent : QTreeWidgetItem """

        msg = _("Merge code: ") + item['name'] + " ==> " + parent.text(0)
        #TODO might need to add font size
        reply = QtWidgets.QMessageBox.question(None, _('Merge codes'),
        msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        try:
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            self.app.conn.commit()
        except Exception as e:
            e = str(e)
            msg = _("Cannot merge codes. Unmark overlapping text.") + "\n" + e
            QtWidgets.QInformationDialog(None, "Cannot merge", msg)
            return
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.app.conn.commit()
        self.parent_textEdit.append(msg)
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_code(self):
        """ Use add_item dialog to get new code text.
        Add_code_name dialog checks for duplicate code name.
        New code is added to data and database. """

        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
        ui.exec_()
        new_code_name = ui.get_new_name()
        if new_code_name is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': new_code_name, 'memo': "", 'owner': self.app.settings['codername'],
        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),'catid': None, 'color': code_color}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("New code: ") + item['name'])
        self.app.delete_backup = False

    def add_category(self):
        """ Add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        Add the new category as a top level item. """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec_()
        newCatText = ui.get_new_name()
        if newCatText is None:
            return
        # add to database
        item = {'name': newCatText, 'cid': None, 'memo': "",
        'owner': self.app.settings['codername'],
        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], None))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("New category: ") + item['name'])
        self.app.delete_backup = False

    def delete_category_or_code(self, selected):
        """ Delete the selected category or code.
        If category deleted, sub-level items are retained.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code_name data and fill
        treeWidget.
        param:
            selected : QTreeWidgetItem """

        # find the code_in the list, check to delete
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                found = i
        if found == -1:
            return
        code_ = self.codes[found]
        ui = DialogConfirmDelete(self.app, _("Code: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'])
        cur = self.app.conn.cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        selected = None
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget. Sub-level items are retained.
        param:
            selected : QTreeWidgetItem """

        found = -1
        for i in range(0, len(self.categories)):
            if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                found = i
        if found == -1:
            return
        category = self.categories[found]
        ui = DialogConfirmDelete(self.app, _("Category: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])
        cur = self.app.conn.cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.app.conn.commit()
        selected = None
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_edit_code_memo(self, selected):
        """ View and edit a memo.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Code ") + self.codes[found]['name'],
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
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False

        if selected.text(1)[0:3] == 'cat':
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Category: ") + self.categories[found]['name'],
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
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
        self.update_dialog_codes_and_categories()

    def rename_category_or_code(self, selected):
        """ Rename a code or category. Checks that the proposed code or category name is
        not currently in use.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"), _("New code name:"),
            QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other code has this text
            for c in self.codes:
                if c['name'] == new_name:
                    Message(self.app, _("Name in use"), new_name + _(" Choose another name"), "warning").exec_()
                    return
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # Update codes list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.app.conn.commit()
            old_name = self.codes[found]['name']
            self.update_dialog_codes_and_categories()
            #self.codes[found]['name'] = new_name
            #selected.setData(0, QtCore.Qt.DisplayRole, new_name)
            self.parent_textEdit.append(_("Code renamed: ") + \
                old_name + " ==> " + new_name)
            self.app.delete_backup = False
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
                    Message(self.app, _("Duplicate category name"), msg, "warning").exec_()
                    return
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            # update category list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set name=? where catid=?",
            (new_name, self.categories[found]['catid']))
            self.app.conn.commit()
            old_name = self.categories[found]['name']
            #self.categories[found]['name'] = new_name
            #selected.setData(0, QtCore.Qt.DisplayRole, new_name)
            self.parent_textEdit.append(_("Category renamed from: ") + \
                old_name + " ==> " + new_name)
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False

    def change_code_color(self, selected):
        """ Change the color of the currently selected code.
        param:
            selected : QTreeWidgetItem """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.app, self.codes[found]['color'])
        ok = ui.exec_()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        selected.setBackground(0, QBrush(QtGui.QColor(new_color), Qt.SolidPattern))
        #update codes list and database
        self.codes[found]['color'] = new_color
        cur = self.app.conn.cursor()
        cur.execute("update code_name set color=? where cid=?",
        (self.codes[found]['color'], self.codes[found]['cid']))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False


class DialogViewImage(QtWidgets.QDialog):
    """ View image. View and edit displayed memo.
    Show a scaleable and scrollable image.
    The slider values range from 10 to 99.

    Linked images have 'image:' at start of mediapath
    """

    app = None
    image_data = None
    pixmap = None
    label = None

    def __init__(self, app, image_data, parent=None):
        """ Image_data contains: {name, mediapath, owner, id, date, memo, fulltext}
        mediapath may be a link as: 'images:path'
        """

        sys.excepthook = exception_handler
        self.app = app
        self.image_data = image_data
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_view_image()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogviewimage_w'])
            h = int(self.app.settings['dialogviewimage_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except:
            pass
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        abs_path = ""
        if "images:" in self.image_data['mediapath']:
            abs_path = self.image_data['mediapath'].split(':')[1]
        else:
            abs_path = self.app.project_path + self.image_data['mediapath']
        self.setWindowTitle(abs_path)
        image = QtGui.QImage(abs_path)
        if image.isNull():
            Message(self.app, _('Image error'), _("Cannot open: ") + abs_path, "warning").exec_()
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

    def closeEvent(self, event):
        """ Save dialog and splitter dimensions. """

        self.app.settings['dialogviewimage_w'] = self.size().width()
        self.app.settings['dialogviewimage_h'] = self.size().height()

    def change_scale(self):
        """ Resize image. Idea from:
        https://github.com/baoboa/pyqt5/blob/master/examples/widgets/imageviewer.py
        """

        scale = (self.ui.horizontalSlider.value() + 1) / 100
        new_label = self.label.resize(scale * self.label.pixmap().size())
        self.label.setFixedWidth(scale * self.pixmap.width())
        self.label.setFixedHeight(scale * self.pixmap.height())
        self.ui.scrollArea.setWidget(new_label)





