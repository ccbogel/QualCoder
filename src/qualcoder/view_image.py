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
https://qualcoder-org.github.io
https://qualcoder.org/
"""

from copy import deepcopy, copy
import datetime
import fitz
import html
from io import BytesIO
import logging
import os
import PIL.Image
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import sqlite3
from typing import Any

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QBuffer
from PyQt6.QtGui import QBrush

from .code_in_all_files import DialogCodeInAllFiles
from .code_tree import CodeTreeController
from .coder_names import DialogCoderNames
from .color_selector import DialogColorSelect
from .color_selector import colour_ranges, show_codes_of_colour_range
from .GUI.ui_dialog_code_image import Ui_Dialog_code_image
from .GUI.ui_dialog_view_image import Ui_Dialog_view_image
from .move_resize_rectangle import DialogMoveResizeRectangle
from .helpers import ExportDirectoryPathDialog, Message, init_persistent_tree_header
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .ris import Ris
from .select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCodeImage(QtWidgets.QDialog):
    """ View and code images. Create codes and categories.  """

    def __init__(self, app, parent_textedit, tab_reports):
        """ Show list of image files.
        On select, Show a scalable and scrollable image.
        Can add a memo to image
        The slider values range from 9 to 99 with intervals of 3.
        """

        super(DialogCodeImage, self).__init__()
        self.app = app
        self.tab_reports = tab_reports  # Tab widget reports, used for updates to codes
        self.parent_textEdit = parent_textedit
        self.codes = []
        self.categories = []
        self.files = []
        self.code_areas = []
        self.undo_deleted_code = None  # Undo last deleted code
        self.file_ = None    # Dictionary with name, memo, id, mediapath
        self.pixmap = None
        self.log = ""
        self.scale = 1.0  # Image scaling
        self.selection = None  # Initial code rectangle point
        # State variables for interactive resizing functionality
        self.item_to_resize = None         # Stores the segment dictionary selected for resizing
        self.is_dragging_handle = False    # Flag indicating if a resize handle is being dragged
        self.active_handle = None          # Identifies the active corner ("TL", "TR", "BL", "BR")
        self.interactive_rect_item = None  # Visual dashed rectangle shown during drag
        self.original_resize_geom = None   # Stores original geometry (x, y, w, h) before drag
        self.important = False  # Show/hide important flagged codes
        self.attributes = []
        self.degrees = 0  # For image rotation
        self.get_codes_and_categories()
        self.show_code_captions = 0  # 0 = no, 1 = code name, 2 = codename + memo
        self.default_new_code_color = None
        self.show_codes_like_filter = ""  # gets filled when text strings are used to show specific code names
        self.show_codes_colour_filter = ""  # gets filled when a code colur is selected

        self.pdf_page = None  # display at 1
        self.pdf_total_pages = None

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_image()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.splitter.setSizes([100, 300])
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        # Need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.scene.installEventFilter(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        self.ui.label_image.setStyleSheet(tree_font)  # Usually smaller font
        self.setWindowTitle(_("Image coding"))
        self.ui.horizontalSlider.valueChanged[int].connect(self.redraw_scene)
        self.ui.horizontalSlider.setToolTip(_("Key + or W zoom in. Key - or Q zoom out"))

        self.ui.lineEdit_coder.setText(self.app.settings['codername'])
        self.ui.pushButton_coder.clicked.connect(self.edit_coder_names)
        self.ui.pushButton_default_new_code_color.setIcon(qta.icon('mdi6.palette', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_default_new_code_color.pressed.connect(self.set_default_new_code_color)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_export.pressed.connect(self.export_html_file)
        self.ui.pushButton_export.setEnabled(False)
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.file_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        self.get_files()
        self.ui.listWidget.selectionModel().selectionChanged.connect(self.file_selection_changed)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.listWidget.installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Shared code tree controller: tree loading, common context menu, drag and drop
        # reparenting, F2-F6 shortcuts and category branch deletion live in code_tree.py,
        # so the four coding pages no longer duplicate this logic by hand.
        self.code_tree = CodeTreeController(self.app, self.ui.treeWidget, self)
        self.ui.treeWidget.customContextMenuRequested.connect(self.code_tree.tree_menu)
        self.code_tree.fill_counts_callback = self.fill_code_counts_in_tree
        self.code_tree.coded_files_callback = self.coded_media_dialog
        self.code_tree.find_code_callback = self.find_code_in_tree
        self.code_tree.show_codes_like_callback = self.show_codes_like
        self.code_tree.show_codes_of_colour_callback = self.show_codes_of_color
        self.code_tree.codes_changed.connect(self.update_dialog_codes_and_categories)
        self.ui.treeWidget.itemClicked.connect(self.tree_item_clicked)
        init_persistent_tree_header(self.ui.treeWidget, self.app, 'dialogcodeimage_tree_widths')
        # Header widgets
        self.ui.pushButton_zoom_in.setIcon(qta.icon('mdi6.magnify-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_zoom_in.pressed.connect(self.zoom_in)
        self.ui.pushButton_zoom_out.setIcon(qta.icon('mdi6.magnify-minus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_zoom_out.pressed.connect(self.zoom_out)
        self.ui.pushButton_rotate_counter.setIcon(
            qta.icon('mdi6.file-rotate-left-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rotate_counter.pressed.connect(self.rotate_counter)
        self.ui.pushButton_rotate_clock.setIcon(
            qta.icon('mdi6.file-rotate-right-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rotate_clock.pressed.connect(self.rotate_clockwise)
        self.ui.label_coded_area_icon.setPixmap(qta.icon('mdi6.grid').pixmap(22, 22))
        self.ui.pushButton_captions.setIcon(qta.icon('mdi6.closed-caption-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_captions.pressed.connect(self.captions_options)
        self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        self.ui.pushButton_find_code.setIcon(qta.icon('mdi6.card-search-outline', options=[{'scale-factor': 1.2}]))
        self.ui.pushButton_find_code.pressed.connect(self.find_code_in_tree)

        # Widgets under File list
        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-box-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_document_memo.pressed.connect(self.active_file_memo)
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        self.ui.pushButton_clear_filter_file.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))  # for clear filter file
        self.ui.pushButton_clear_filter_file.pressed.connect(self.clear_file_filter)
        self.ui.pushButton_clear_filter_file.setToolTip(_("Clear file filter"))
        self.ui.pushButton_clear_filter_file.setVisible(False)  # hidden until a filter is active        
        # Widgets under codes tree
        self.ui.lineEdit_code_filter.textChanged.connect(lambda textchanged: self.show_codes_like(self.ui.lineEdit_code_filter.text()))
        self.ui.pushButton_clear_filter_code.setIcon(
            qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))  # for clear filter code
        self.ui.pushButton_clear_filter_code.pressed.connect(self.clear_code_filter)
        self.ui.pushButton_clear_filter_code.setToolTip(_("Clear code filter"))
        self.ui.pushButton_clear_filter_code.setVisible(False)  # hidden until a filter is active

        # Header - Pdf widgets
        self.pdf_controls_toggle()
        self.ui.pushButton_next_page.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_page.pressed.connect(self.next_page)
        self.ui.pushButton_previous_page.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_previous_page.pressed.connect(self.previous_page)
        self.ui.pushButton_last_page.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_last_page.pressed.connect(self.last_page)
        self.ui.pushButton_goto_page.setIcon(qta.icon('mdi6.book-search-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_goto_page.pressed.connect(self.goto_page)
        self.ui.label_pdf.setPixmap(qta.icon('mdi6.file-pdf-box').pixmap(26, 26))

        try:
            s0 = int(self.app.settings['dialogcodeimage_splitter0'])
            s1 = int(self.app.settings['dialogcodeimage_splitter1'])
            # 30 is for the button box
            self.ui.splitter.setSizes([s0, 30, s1, 30])
            h0 = int(self.app.settings['dialogcodeimage_splitter_h0'])
            h1 = int(self.app.settings['dialogcodeimage_splitter_h1'])
            if h0 > 1 and h1 > 1:
                self.ui.splitter_2.setSizes([h0, h1])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.splitter_2.splitterMoved.connect(self.update_sizes)
        self.app.project_events.project_data_changed.connect(self._on_project_data_changed)
        self.code_tree.fill_tree()
        # These signals after the tree is filled the first time
        self.ui.treeWidget.itemCollapsed.connect(self.get_collapsed)
        self.ui.treeWidget.itemExpanded.connect(self.get_collapsed)

    def update_sizes(self):
        """ Called by changed splitter sizes """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodeimage_splitter0'] = sizes[0]
        self.app.settings['dialogcodeimage_splitter1'] = sizes[2]
        sizes = self.ui.splitter_2.sizes()
        self.app.settings['dialogcodeimage_splitter_h0'] = sizes[0]
        self.app.settings['dialogcodeimage_splitter_h1'] = sizes[1]

    def get_codes_and_categories(self):
        """ Called from init, delete category/code, event_filter """

        self.codes, self.categories = self.app.get_codes_categories()

    def edit_coder_names(self):
        ui_coder_names = DialogCoderNames(self.app, extended_options=False)
        if (ui_coder_names.exec() == QtWidgets.QDialog.DialogCode.Accepted and 
            ui_coder_names.coder_names_changed):
            # Update UI as coders visibility may have changed
            self.get_coded_areas()
            self.redraw_scene()
            self.fill_code_counts_in_tree()
            self.ui.lineEdit_coder.setText(self.app.settings['codername'])
            # close contents in tab_reports since they must update coder names as well 
            contents = self.tab_reports.layout()
            if contents:
                for i in reversed(range(contents.count())):
                    contents.itemAt(i).widget().close()
                    contents.itemAt(i).widget().setParent(None)

    def set_default_new_code_color(self):
        """ New code colours are usually generated randomly.
         This overrides the random approach, by setting a colout. """

        tmp_code = {'name': 'new', 'color': None}
        ui = DialogColorSelect(self.app, tmp_code)
        ok = ui.exec()
        if not ok:
            return
        color = ui.get_color()
        if color is not None:
            self.ui.pushButton_default_new_code_color.setStyleSheet(f'background-color: {color}')
        self.default_new_code_color = color

    def find_code_in_tree(self):
        """ Find a code by name in the codes tree and select it. """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Search for code"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        msg = _("Find and select first code that matches text.") + "\n"
        msg += _("Enter text to match all or partial code:")
        dialog.setLabelText(msg)
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        search_text = dialog.textValue()
        # Remove selections and search for matching item text
        self.ui.treeWidget.setCurrentItem(None)
        self.ui.treeWidget.clearSelection()
        item = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        matches = []
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                code_ = next((code_ for code_ in self.codes if code_['cid'] == cid), None)
                if search_text in code_['name']:
                    matches.append(code_)
            iterator += 1
        if not matches:
            Message(self.app, _("Match not found"), _("No code with matching text found.")).exec()
            return
        # Get one selected code from one or more codes.
        selected = None
        if len(matches) > 1:
            ui = DialogSelectItems(self.app, matches, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            selected = ui.get_selected()
            if not selected:
                return
        else:
            selected = matches[0]
        # Set selected in tree
        item = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                if cid == selected['cid']:
                    self.ui.treeWidget.setCurrentItem(item)
                    break
            iterator += 1
        # Expand parents
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

    def show_important_coded(self):
        """ Show codes flagged as important. """

        self.important = not self.important
        if self.important:
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star'))
        else:
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline'))
        self.redraw_scene()

    def get_coded_areas(self):
        """ Get the coded area details for the rectangles for the image file by all visible coders.
        Order by area descending so when items are drawn to the scene. First largest to smallest on top.
        Called by load file, update_dialog_codes_and_categories,coded_media_dialog, undo_last_unmarked_code.
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        self.code_areas = []
        if self.pdf_page is not None:
            sql = "select imid,id,x1, y1, width, height, code_image_visible.memo, code_image_visible.date, " \
                  "code_image_visible.owner, code_image_visible.cid, " \
                  "important, code_name.name, code_name.color, pdf_page from code_image_visible " \
                  "join code_name on code_name.cid=code_image_visible.cid " \
                  " where code_image_visible.id=? and width > 0 and height > 0 and pdf_page=?" \
                  " order by width*height desc"
            cur.execute(sql, [self.file_['id'], self.pdf_page])
        else:  # Images, jpg, png
            sql = "select imid,id,x1, y1, width, height, code_image_visible.memo, code_image_visible.date, " \
                  "code_image_visible.owner, code_image_visible.cid, " \
                  "important, code_name.name, code_name.color, pdf_page from code_image_visible " \
                  "join code_name on code_name.cid=code_image_visible.cid " \
                  " where code_image_visible.id=? and width > 0 and height > 0" \
                  " order by width*height desc"
            cur.execute(sql, [self.file_['id']])
        results = cur.fetchall()
        keys = 'imid', 'id', 'x1', 'y1', 'width', 'height', 'memo', 'date', 'owner', 'cid', 'important', 'name', \
            'color', 'pdf_page'
        for row in results:
            self.code_areas.append(dict(zip(keys, row)))

    def get_files(self, ids=None, sort="name asc"):
        """ Load the image and pdf file data.
        Exclude those image and pdf file data where there are bad links.
        Fill List widget with the files.
        args:
            ids : list of Integer ids to restrict files
            sort : String Sort options, name asc, name, desc, case asc, case desc
        """

        if ids is None:
            ids = []
        bad_links = self.app.check_bad_file_links()
        bad_link_sql = ""
        for bad_link in bad_links:
            bad_link_sql += f",{bad_link['id']}"
        if len(bad_link_sql) > 0:
            bad_link_sql = f' and id not in ({bad_link_sql[1:]}) '

        selection_model = self.ui.listWidget.selectionModel()
        selection_blocker = QtCore.QSignalBlocker(selection_model) if selection_model is not None else None
        self.ui.listWidget.clear()
        cur = self.app.conn.cursor()
        sql = "select name, id, memo, owner, date, mediapath, risid from source where "
        sql += "((substr(mediapath,1,7) in ('/images', 'images:')) or "  # added outer opening parenthesis to group OR conditions
        sql += "(lower(substr(mediapath, -4)) = '.pdf')) "  # added closing parenthesis so AND id IN(...) applies to both branches
        sql += bad_link_sql + " "
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += " order by name"
        cur.execute(sql)
        result = cur.fetchall()
        self.files = []
        keys = 'name', 'id', 'memo', 'owner', 'date', 'mediapath', 'risid'
        for row in result:
            self.files.append(dict(zip(keys, row)))
        sql_case = "SELECT group_concat(cases.name) from cases join case_text on case_text.caseid=cases.caseid " \
                   "where case_text.fid=?"
        for file_ in self.files:
            tt = _("Date: ") + file_['date'].split()[0]
            file_['case'] = ""
            cur.execute(sql_case, [file_['id']])
            res_cases = cur.fetchone()
            if res_cases and res_cases[0] is not None:
                tt += "\n" + _("Case: ") + f"{res_cases[0]}"
                file_['case'] = f"{res_cases[0]}"
            tt += f"\n{file_['memo']}"

            if file_['risid']:
                ris = Ris(self.app)
                ris.get_references(file_['risid'])
                if ris.refs:
                    reference = ris.refs[0]['vancouver']
                    tt += f"\nREF: {reference}"

            file_['tooltip'] = tt
        # Sorting the file list
        if sort == "name asc":
            self.files = sorted(self.files, key=lambda x: x['name'])
        if sort == "name desc":
            self.files = sorted(self.files, key=lambda x: x['name'], reverse=True)
        if sort == "case asc":
            self.files = sorted(self.files, key=lambda x: x['case'])
        if sort == "case desc":
            self.files = sorted(self.files, key=lambda x: x['case'], reverse=True)
        if sort == "date asc":
            self.files = sorted(self.files, key=lambda x: x['date'])
        if sort == "date desc":
            self.files = sorted(self.files, key=lambda x: x['date'], reverse=True)
        # Fill list widget
        for file_ in self.files:
            item = QtWidgets.QListWidgetItem(file_['name'])
            item.setToolTip(file_['tooltip'])
            self.ui.listWidget.addItem(item)
        self.clear_file()
        del selection_blocker

    def get_files_from_attributes(self, refresh_only: bool = False):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        first item is a Boolean AND or OR list item
        Followed by each attribute list item

        Args:
            refresh_only: Recompute an already active attribute filter without reopening
                the selection dialog.
        """

        if refresh_only and len(self.attributes) <= 1:
            return

        # Clear ui
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        ui = DialogSelectAttributeParameters(self.app)
        previous_attributes = deepcopy(self.attributes)
        ui.fill_parameters(deepcopy(self.attributes))
        temp_attributes = deepcopy(self.attributes)
        if refresh_only:
            ui.make_parameter_list()
            ui.get_results_case_ids()
            ui.get_results_file_ids()
            ui.get_results_message()
        else:
            self.attributes = []
            ok = ui.exec()
            if not ok:
                self.attributes = temp_attributes
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
                self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
                if self.attributes:
                    self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box'))
                return
        self.attributes = ui.parameters
        if len(self.attributes) == 1:
            if refresh_only and len(previous_attributes) > 1:
                self.clear_file_filter()
                return
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.get_files()
            return
        if not ui.result_file_ids:
            if not refresh_only:
                Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
                self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
                return
            selection_model = self.ui.listWidget.selectionModel()
            selection_blocker = QtCore.QSignalBlocker(selection_model) if selection_model is not None else None
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
            self.ui.listWidget.clear()
            self.files = []
            self.clear_file()
            self.ui.pushButton_clear_filter_file.setVisible(True)
            self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")
            del selection_blocker
            return
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

    def fill_code_counts_in_tree(self):
        """ Calculate the frequency of each code and category for all visible coders and the selected file.
        Add a list item to each code that can be used to display in treeWidget.
        If the tab 'AI assisted coding' is active, the codings will be counted
        across all files, not only the currently selected one, because the AI assisted
        coding is not working on a per-file basis.
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        code_counts = []
        for c in self.codes:
            parameters = [c['cid'], self.file_['id']]
            sql = "select code_name.catid, count(code_image_visible.cid) from code_image_visible join code_name " \
                "on code_name.cid=code_image_visible.cid where code_image_visible.cid=? " \
                "and code_image_visible.id=?"
            cur.execute(sql, parameters)
            result = cur.fetchone()
            code_counts.append([c['cid'], result[0], result[1]])

        # Sub-code roll-up. Build own counts, the parent/children maps and an effective
        # category for each code (a sub-code is attributed to its top ancestor's category).
        own_count = {cc[0]: cc[2] for cc in code_counts}
        code_by_cid = {c['cid']: c for c in self.codes}
        children_of = {}
        for c in self.codes:
            sup = c.get('supercid')
            if sup is not None:
                children_of.setdefault(sup, []).append(c['cid'])

        def _effective_catid(cid):
            """ Resolve a (possibly nested) code to the catid of its top ancestor code. """
            seen = set()
            cur_c = code_by_cid.get(cid)
            while cur_c is not None and cur_c['cid'] not in seen:
                seen.add(cur_c['cid'])
                if cur_c['catid'] is not None:
                    return cur_c['catid']
                sup_ = cur_c.get('supercid')
                if sup_ is None:
                    return None
                cur_c = code_by_cid.get(sup_)
            return None

        eff_catid = {cc[0]: _effective_catid(cc[0]) for cc in code_counts}

        total_cache = {}

        def _code_total(cid):
            """ Code count rolled up with all descendant sub-codes. Memoized, cycle-safe. """
            if cid in total_cache:
                return total_cache[cid]
            total_cache[cid] = own_count.get(cid, 0)  # seed guards against cycles
            t = own_count.get(cid, 0)
            for child_cid in children_of.get(cid, []):
                t += _code_total(child_cid)
            total_cache[cid] = t
            return t

        categories = deepcopy(self.categories)
        # Set up category counts
        for category in categories:
            category['count'] = 0
        # Add each code's own count to its effective category (sub-codes roll up to the
        # category of their top ancestor code, not to a raw catid that is None).
        for category in categories:
            for code in code_counts:
                if eff_catid.get(code[0]) == category['catid']:
                    category['count'] += code[2]
        # Find leaf categories, add to above categories, and gradually remove leaves
        # until only top categories are left
        sub_categories = copy(categories)
        counter = 0
        # 'and', not 'or': with 'or' the 10,000 guard never fires (cycle in code_cat =
        # infinite loop) and healthy data still spins 10,000 empty passes.
        while len(sub_categories) > 0 and counter < 10000:
            leaf_list = []
            branch_list = []
            for cat in sub_categories:
                for cat2 in sub_categories:
                    if cat['catid'] == cat2['supercatid']:
                        branch_list.append(cat)
            for category in sub_categories:
                if category not in branch_list:
                    leaf_list.append(category)
            # Add totals higher category
            for leaf_category in leaf_list:
                for category in categories:
                    if category['catid'] == leaf_category['supercatid']:
                        category['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1

        # Fill tree item counts
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if item.text(1).startswith("catid"):
                catid = int(item.text(1)[6:])
                for category in categories:
                    if catid == category['catid']:
                        item.setText(3, str(category['count']))
            else:
                cid = int(item.text(1)[4:])
                own_n = own_count.get(cid, 0)
                if cid in children_of:
                    total_n = _code_total(cid)
                    item.setText(3, f"{own_n} ({total_n})" if total_n != own_n else str(own_n))
                else:
                    item.setText(3, str(own_n))
            iterator += 1  # Move to the next item

    def tree_item_clicked(self, item, column):
        """ Use to quicky open memo. """

        if column == 2:
            self.code_tree.add_edit_cat_or_code_memo(item)

    def get_collapsed(self, item):
        """ On category collapse or expansion signal, find the collapsed parent category items.
        This will fill the self.app.collapsed_categories and is the expanded/collapsed tree is then replicated across
        other areas of the app. """

        if item.text(1)[:3] == "cid":
            return
        if not item.isExpanded() and item.text(1) not in self.app.collapsed_categories:
            self.app.collapsed_categories.append(item.text(1))
        if item.isExpanded() and item.text(1) in self.app.collapsed_categories:
            self.app.collapsed_categories.remove(item.text(1))

    def active_file_memo(self):
        """ Send active file to file_memo method.
        Called by pushButton_document_memo for loaded text.
        """

        self.file_memo(self.file_)

    def file_memo(self, file_):
        """ Open file memo to view or edit.
        Called by pushButton_document_memo for loaded text, via active_file_memo
        and through file_menu for any file.
        param: file_ : Dictionary of file values
        """

        if file_ is None:
            return
        ui = DialogMemo(self.app, _("Memo for file: ") + file_['name'], file_['memo'])
        ui.exec()
        memo = ui.memo
        if memo == file_['memo']:
            return
        file_['memo'] = memo
        cur = self.app.conn.cursor()
        cur.execute("update source set memo=? where id=?", (memo, file_['id']))
        self.app.conn.commit()
        self.get_files()
        self.ui.listWidget.clear()
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.app.delete_backup = False

    def go_to_latest_coded_file(self):
        """ Vertical splitter button activates this """

        sql = "SELECT id FROM code_image_visible order by date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql)
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

    def file_menu(self, position):
        """ Context menu to select the next image alphabetically, or
         to select the image that was most recently coded """

        selected = self.ui.listWidget.currentItem()
        if not selected:
            return
        file_ = next((f for f in self.files if f['name'] == selected.text()), None)
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_memo = menu.addAction(_("Open memo"))
        action_next = menu.addAction(_("Next file"))
        action_latest = menu.addAction(_("File with latest coding"))
        action_show_files_like = menu.addAction(_("Show files like"))
        action_show_case_files = menu.addAction(_("Show case files"))
        action_show_by_attribute = menu.addAction(_("Show files by attributes"))
        sort_menu = QtWidgets.QMenu(_("Sort"))
        sort_menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_sort_name_asc = sort_menu.addAction(_("Sort by name ascending"))
        action_sort_name_desc = sort_menu.addAction(_("Sort by name descending"))
        action_sort_case_asc = sort_menu.addAction(_("Sort by case ascending"))
        action_sort_case_desc = sort_menu.addAction(_("Sort by case descending"))
        action_sort_date_asc = sort_menu.addAction(_("Sort by date ascending"))
        action_sort_date_desc = sort_menu.addAction(_("Sort by date descending"))
        menu.addMenu(sort_menu)
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action == action_memo:
            self.file_memo(file_)
        if action == action_next:
            self.go_to_next_file()
            return
        if action == action_latest:
            self.go_to_latest_coded_file()
            return
        if action == action_show_files_like:
            self.show_files_like()
        if action == action_show_case_files:
            self.show_case_files()
        if action == action_show_by_attribute:
            self.get_files_from_attributes()
        if action == action_sort_name_asc:
            self.get_files(None, "name asc")
        if action == action_sort_name_desc:
            self.get_files(None, "name desc")
        if action == action_sort_case_asc:
            self.get_files(None, "case asc")
        if action == action_sort_case_desc:
            self.get_files(None, "case desc")
        if action == action_sort_date_asc:
            self.get_files(None, "date asc")
        if action == action_sort_date_desc:
            self.get_files(None, "date desc")

    def show_case_files(self):
        """ Show files of specified case.
        Or show all files. """

        cases = self.app.get_casenames()
        cases.insert(0, {"name": _("Show all files"), "id": -1})
        ui = DialogSelectItems(self.app, cases, _("Select case"), "single")
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        if selection['id'] == -1:
            self.get_files()
            self.ui.pushButton_clear_filter_file.setVisible(False)  # reset filter button when showing all
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute('select fid from case_text where caseid=?', [selection['id']])
        res = cur.fetchall()
        file_ids = []
        for r in res:
            file_ids.append(r[0])
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

    def show_files_like(self):
        """ Show files that contain specified filename text.
        If blank, show all files. """

        dialog = QtWidgets.QInputDialog(None) #correct: dialog embedded in workspace instead of floating
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Show files like"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show files containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        if text_ == "":
            self.get_files()
            self.ui.pushButton_clear_filter_file.setVisible(False)  # hide filter button when showing all
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute("select id from source where name like ? and "  # restrict to image/pdf files only
                    "((substr(mediapath,1,7) in ('/images', 'images:')) or "
                    "(lower(substr(mediapath, -4)) = '.pdf'))",
                    ['%' + text_ + '%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter file
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

    def file_selection_changed(self):
        """ Item selected so fill current file variable and load. """

        if len(self.files) == 0:
            return
        current_item = self.ui.listWidget.currentItem()
        if current_item is None:
            return
        item_name = current_item.text()
        for f in self.files:
            if f['name'] == item_name:
                self.file_ = f
                self.load_file()
                break

    def clear_file(self):
        """ When image removed clear all details.
        Called by null file in load_file, and from ManageFiles.delete. """

        self.file_ = None
        self.selection = None
        self.scale = 1.0
        # Clear handle states on image change/close to prevent ghost handles or memory errors
        self.item_to_resize = None
        self.is_dragging_handle = False
        self.active_handle = None
        self.interactive_rect_item = None
        self.original_resize_geom = None
        items = list(self.scene.items())
        for i in range(items.__len__()):
            self.scene.removeItem(items[i])
        self.setWindowTitle(_("Image coding"))

    def pdf_controls_toggle(self, active=False):
        """ Toggle pdf controls on or off depending on file selection. """

        self.ui.pushButton_goto_page.setEnabled(active)
        self.ui.pushButton_last_page.setEnabled(active)
        self.ui.label_pages.setEnabled(active)
        self.ui.pushButton_next_page.setEnabled(active)
        self.ui.pushButton_previous_page.setEnabled(active)

    def goto_page(self):
        text, ok = QtWidgets.QInputDialog.getInt(None, 'Go to page', f'1 - {self.pdf_total_pages}')
        if not ok or not text:
            return
        self.pdf_page = int(text) - 1
        if self.pdf_page < 1:
            self.pdf_page = 0
        if self.pdf_page > self.pdf_total_pages - 1:
            self.pdf_page = self.pdf_total_pages - 1
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def last_page(self):
        self.pdf_page = self.pdf_total_pages - 1
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def next_page(self):
        self.pdf_page += 1
        if self.pdf_page > self.pdf_total_pages - 1:
            self.pdf_page = self.pdf_total_pages - 1
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def previous_page(self):
        self.pdf_page -= 1
        if self.pdf_page < 0:
            self.pdf_page = 0
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def load_file(self):
        """ Add image to scene if it exists. If not exists clear the GUI and variables.
        Called by: select_image_menu, file_selection_changed, pdf page changed
        """

        self.degrees = 0
        self.ui.label_coded_area.setText("Coded area")
        self.ui.label_coded_area.setToolTip("")
        image = None
        source_path = ""
        # Images source
        if self.file_['mediapath'][0:7] == "/images":
            source_path = self.app.project_path + self.file_['mediapath']  # Internal
            image = QtGui.QImage(source_path)
            self.pdf_controls_toggle()
            self.pdf_page = None
            self.pdf_total_pages = None
            self.ui.label_pages.setText("")
        if self.file_['mediapath'][0:7] == "images:":
            source_path = self.file_['mediapath'][7:]  # Linked
            image = QtGui.QImage(source_path)
            self.pdf_controls_toggle()
            self.pdf_page = None
            self.pdf_total_pages = None
            self.ui.label_pages.setText("")

        # PDF source
        if self.file_['mediapath'][-4:].lower() == ".pdf":
            if self.file_['mediapath'][:6] == "/docs/":
                source_path = f"{self.app.project_path}/documents/{self.file_['mediapath'][6:]}"
            if self.file_['mediapath'][:5] == "docs:":
                source_path = self.file_['mediapath'][5:]
            fitz_pdf = fitz.open(source_path)  # Use pymupdf to get page images
            if not self.pdf_page:
                self.pdf_page = 0
            self.pdf_total_pages = 0
            for page in fitz_pdf:
                self.pdf_total_pages += 1
                if page.number == self.pdf_page:
                    # Only need the current page image of interest
                    pixmap = page.get_pixmap()
                    pixmap.save(os.path.join(self.app.confighome, f"tmp_pdf_page.png"))

            source_path = os.path.join(self.app.confighome, f"tmp_pdf_page.png")
            image = QtGui.QImage(source_path)
            self.pdf_controls_toggle(True)
            self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")

        if image.isNull():
            self.clear_file()
            Message(self.app, _("Image Error"), _("Cannot open: ") + source_path).exec()
            logger.warning("Cannot open image: " + source_path)
            return

        items = list(self.scene.items())
        for i in range(items.__len__()):
            self.scene.removeItem(items[i])
        self.setWindowTitle(_("Image: ") + self.file_['name'])
        self.ui.pushButton_export.setEnabled(True)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)

        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        # - 30 - 100   are slider and groupbox approx heights
        if self.pixmap.height() > self.height() - 30 - 100:
            scale = (self.height() - 30 - 100) / self.pixmap.height()
            slider_value = int(scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)
        self.get_coded_areas()
        self.draw_coded_areas()
        self.fill_code_counts_in_tree()

    def update_dialog_codes_and_categories(self, tables: list[str]|None = None):
        """Refresh the local dialog after code/category changes and optionally notify other dialogs.

        Args:
            tables: Optional list of changed database table names to emit to the project event bus.
                Use an empty list for a local-only refresh without notifying other dialogs.
        """

        self.get_codes_and_categories()
        self.code_tree.fill_tree()
        self.get_coded_areas()
        self.draw_coded_areas()

        if self.app.project_events is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def _on_project_data_changed(self, tables, source):
        """Handle project change events from other dialogs.

        Args:
            tables: Changed database table names.
            source: Event emitter, ignored when it is this dialog.
        """

        if source is self or not isinstance(tables, list):
            return
        tables = set(tables)
        if ("attribute" in tables or "attribute_type" in tables) and len(self.attributes) > 1:
            self.get_files_from_attributes(refresh_only=True)

        code_tree_changed = "code_cat" in tables or "code_name" in tables
        refresh_areas = "code_image" in tables or ("code_name" in tables and bool(self.code_areas))
        refresh_counts = "code_image" in tables
        reload_areas = "code_image" in tables

        if code_tree_changed:
            self.get_codes_and_categories()
            self.code_tree.fill_tree()
        elif not refresh_areas and not refresh_counts:
            return

        if reload_areas:
            self.get_coded_areas()
        if refresh_areas:
            self.redraw_scene()
        if refresh_counts and not code_tree_changed:
            self.fill_code_counts_in_tree()

    def redraw_scene(self):
        """ Resize image. Triggered by user change in slider. Or resize or move of a coded area.
        Called by unmark, and Menu rotate action, as all items need to be redrawn. """

        if self.pixmap is None:
            return
        # If the user uses keyboard shortcuts to zoom/rotate WHILE dragging, safely cancel the drag
        if hasattr(self, 'is_dragging_handle') and self.is_dragging_handle:
            self.is_dragging_handle = False
            self.interactive_rect_item = None
            self.active_handle = None
            self.original_resize_geom = None
            self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)    
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = int(self.scale * self.pixmap.height())
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        transform = QtGui.QTransform().rotate(self.degrees)
        pixmap = pixmap.transformed(transform)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_areas()
        scale_text = _("Scale: ") + f"{int(self.scale * 100)}%"
        self.ui.horizontalSlider.setToolTip(scale_text)
        msg = _("Width") + f": {self.pixmap.width()} " + _("Height") + f": {self.pixmap.height()}\n"
        msg += f"{scale_text} " + _("Rotation") + f": {self.degrees}\u00b0"
        self.ui.label_image.setText(msg)

    def draw_coded_areas(self):
        """ Draw coded areas with scaling. This coder is shown in dashed rectangles.
        Other coders are shown via dotline rectangles.
        Remove items first, as this is called after a coded area is unmarked. """

        if self.file_ is None:
            return
        # Error catch re pdf coded areas. some coded areas still present even if page changed by 1
        if self.pdf_page is not None:
            tmp_coded_areas = []
            for area in self.code_areas:
                if area['pdf_page'] == self.pdf_page:
                    tmp_coded_areas.append(area)
            self.code_areas = tmp_coded_areas

        for coded in self.code_areas:
            if coded['id'] == self.file_['id']:
                color = None
                tooltip = ""
                code_name = ""
                code_memo = ""
                for c in self.codes:
                    if c['cid'] == coded['cid']:
                        code_name = c['name']
                        code_memo = c['memo']
                        tooltip = f"{c['name']} ({coded['owner']})"
                        if self.app.settings['showids']:
                            tooltip += f"[imid:{coded['imid']}]"
                        if coded['memo'] != "":
                            tooltip += f"\nMemo: {coded['memo']}"
                            code_memo = f"\nMemo: {coded['memo']}"
                        if coded['important'] == 1:
                            tooltip += "\n" + _("IMPORTANT")
                        color = QtGui.QColor(c['color'])
                # Warn of exact overlapping code(s)
                overlaps = ""
                for coded2 in self.code_areas:
                    if coded2['x1'] == coded['x1'] and coded2['y1'] == coded['y1'] and \
                            coded2['width'] == coded['width'] and coded2['height'] == coded['height'] and \
                            coded2['owner'] == coded['owner'] and coded2['cid'] != coded['cid']:
                        code_name2 = ""
                        for c2 in self.codes:
                            if c2['cid'] == coded2['cid']:
                                code_name2 = c2['name']
                                break
                        overlaps += "\n" + _("Overlaps exactly with") + f": {code_name2}\n"
                if overlaps:
                    tooltip += overlaps

                # Degrees 0
                x = coded['x1'] * self.scale
                y = coded['y1'] * self.scale
                width = coded['width'] * self.scale
                height = coded['height'] * self.scale
                if self.degrees == 90:
                    y = (coded['x1']) * self.scale
                    x = (self.pixmap.height() - coded['y1'] - coded['height']) * self.scale
                    height = coded['width'] * self.scale
                    width = coded['height'] * self.scale
                if self.degrees == 180:
                    x = (self.pixmap.width() - coded['x1'] - coded['width']) * self.scale
                    y = (self.pixmap.height() - coded['y1'] - coded['height']) * self.scale
                    width = coded['width'] * self.scale
                    height = coded['height'] * self.scale
                if self.degrees == 270:
                    y = (self.pixmap.width() - coded['x1'] - coded['width']) * self.scale
                    x = (coded['y1']) * self.scale
                    height = coded['width'] * self.scale
                    width = coded['height'] * self.scale
                rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
                if coded['owner'] == self.app.settings['codername']:
                    rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.PenStyle.DashLine))
                else:
                    rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.PenStyle.DotLine))
                rect_item.setToolTip(tooltip)
                if self.important and coded['important'] == 1:
                    self.scene.addItem(rect_item)
                if not self.important:
                    self.scene.addItem(rect_item)
                # Draw 4 handles (red squares) on the corners of the active segment
                if hasattr(self, 'item_to_resize') and self.item_to_resize and self.item_to_resize['imid'] == coded['imid']:
                    handle_size = 12
                    # Dictionary with relative X, Y coordinates for the 4 corners:
                    # Top-Left (TL), Top-Right (TR), Bottom-Left (BL), Bottom-Right (BR)
                    handles = {
                        "TL": (x, y),
                        "TR": (x + width - handle_size, y),
                        "BL": (x, y + height - handle_size),
                        "BR": (x + width - handle_size, y + height - handle_size)
                    }
                    # Iterate through corners to create interactive square items in the scene
                    for h_type, (hx, hy) in handles.items():
                        handle_item = QtWidgets.QGraphicsRectItem(hx, hy, handle_size, handle_size)
                        handle_item.setBrush(QBrush(QtGui.QColor("#ff0000")))  # Red color for visibility
                        handle_item.setData(0, "resize_handle")  # Main tag to detect clicks
                        handle_item.setData(1, h_type)          # Identifies the specific corner
                        handle_item.setZValue(1000)  # keep handles above all coded rectangles so they are always clickable
                        self.scene.addItem(handle_item)
                if self.show_code_captions == 1:
                    self.caption(x, y, code_name)
                if self.show_code_captions == 2:
                    self.caption(x, y, code_name + code_memo)

    def captions_options(self):
        """ Hide captions (0). Show captions (1). Show captions with memos (2) """

        self.show_code_captions += 1
        if self.show_code_captions > 2:
            self.show_code_captions = 0
        self.redraw_scene()

    def caption(self, x, y, code_name):
        """ Add captions to coded areas. """

        text_item = QtWidgets.QGraphicsTextItem()
        text_item.setDefaultTextColor(QtGui.QColor("#000000"))
        html_text = code_name.replace('\n', '<br />')
        text_item.setHtml(f"<div style='background-color:#FFFFFF;'>{html_text}</div>")
        # Style.StyleNormal 400  Segoe UI 9
        text_item.setPos(x, y)
        self.scene.addItem(text_item)

    def export_html_file(self):
        """ Export the QGraphicsScene as a png image with transparent background.
               Called by QButton_export.
               """

        filename = self.file_['name'].replace(".", "_") + ".html"
        export_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = export_dir.filepath
        if filepath is None:
            return
        pic_width = self.pixmap.width() * self.scale
        pic_height = self.pixmap.height() * self.scale
        if self.degrees in (90, 270):
            pic_width, pic_height = pic_height, pic_width
        rect_area = QtCore.QRectF(0.0, 0.0, pic_width, pic_height)
        image = QtGui.QImage(int(pic_width), int(pic_height), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect_area)
        painter.end()
        # Convert to base64 as String not bytes
        byte_array = QtCore.QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'PNG')
        base64_string = byte_array.toBase64().data().decode("UTF-8")
        # Create html file
        h = "<!DOCTYPE html>\n<html>\n<head>\n<title>Coded Image</title>\n</head>\n"
        h += "<body>\n<div>\n"
        h += f"<h1>{html.escape(filename)}</h1>\n"
        h += '<img src="data:image/png;base64,' + base64_string + '" usemap="#coded_areas" />'
        # Create image map
        h += "<map name='coded_areas'>\n"
        for c in self.code_areas:
            # Coordinates are x1,y1 to x2,y2 for a rectangle. Adjust for scale and rotation.
            # Degrees 0
            x1 = c['x1'] * self.scale
            y1 = c['y1'] * self.scale
            x2 = x1 + c['width'] * self.scale
            y2 = y1 + c['height'] * self.scale
            if self.degrees == 90:
                y1 = (c['x1']) * self.scale
                x1 = (self.pixmap.height() - c['y1'] - c['height']) * self.scale
                y2 = y1 + c['width'] * self.scale
                x2 = x1 + c['height'] * self.scale
            if self.degrees == 180:
                x1 = (self.pixmap.width() - c['x1'] - c['width']) * self.scale
                y1 = (self.pixmap.height() - c['y1'] - c['height']) * self.scale
                x2 = x1 + c['width'] * self.scale
                y2 = y1 + c['height'] * self.scale
            if self.degrees == 270:
                y1 = (self.pixmap.width() - c['x1'] - c['width']) * self.scale
                x1 = (c['y1']) * self.scale
                y2 = y1 + c['width'] * self.scale
                x2 = x1 + c['height'] * self.scale
            tag = '<area shape="rect" coords="' + str(x1) + "," + str(y1) + ","
            tag += str(x2) + "," + str(y2) + '" '
            tag += 'title="' + html.escape(c['name'])
            if c['memo'] != "":
                tag += html.escape('\n' + c['memo'])
            tag += '" href="#1" >\n'
            h += tag
        h += "</map>\n"
        if self.file_['memo'] != "":
            h += '<h2>Image memo</h2>\n'
            h += f"<p>{html.escape(self.file_['memo'])}</p>\n"
        h += "</div>\n</body>\n</html>"
        with open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(h)
        Message(self.app, _("Image exported"), filepath).exec()

    def coded_media_dialog(self, code_dict, category_name:str = ""):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Need to store textedit start and end positions so that code in context can be used.
        Called from tree_menu.
        Re-load the codings may have changed.
        Args:
            code_dict : code dictionary
            category_name : if a category selected, the category name
        """

        DialogCodeInAllFiles(self.app, code_dict, "File", category_name)
        self.get_coded_areas()
        self.redraw_scene()

    def show_codes_like(self, preset:str|None=None):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text.
         The input dialog is too narrow, so it is re-created.
         Args:
             preset: None of called from tree_menu, or a string value if called from filer_code_text line edit
        """

        case_sensitive = True
        if preset is None:
            dialog = QtWidgets.QDialog(None)
            dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
            dialog.setWindowTitle(_("Show some codes"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
            dlg_text = _("Show codes containing the text. (Blank for all)") + "\n"
            if self.show_codes_like_filter:
                dlg_text += _("Filter: ") + self.show_codes_like_filter
            lbl = QtWidgets.QLabel(dlg_text)
            line = QtWidgets.QLineEdit()
            chkbox = QtWidgets.QCheckBox(_("Case sensitive"))
            btn_box = QtWidgets.QDialogButtonBox()
            btn_box.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Ok|QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(lbl)
            layout.addWidget(chkbox)
            layout.addWidget(line)
            layout.addWidget(btn_box)
            dialog.setLayout(layout)
            btn_box.rejected.connect(dialog.reject)
            btn_box.accepted.connect(dialog.accept)
            dialog.resize(200, 60)
            ok = dialog.exec()
            if not ok:
                return
            self.show_codes_colour_filter = ""
            case_sensitive = chkbox.isChecked()
            self.show_codes_like_filter = line.text()
        else:
            self.show_codes_like_filter = preset
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, "")  # Show all codes in tree
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, self.show_codes_like_filter, case_sensitive)
        if self.show_codes_like_filter == "":  # for clear filter code
            self.ui.pushButton_clear_filter_code.setVisible(False)
            self.ui.pushButton_clear_filter_code.setStyleSheet("")
        else:
            self.ui.pushButton_clear_filter_code.setVisible(True)
            self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")

    def show_codes_of_color(self):
        """ Show all codes in colour range in code tree., ir all codes if no selection.
        Show selected codes that are of a selected colour.
        """

        ui = DialogSelectItems(self.app, colour_ranges, _("Select code colors"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        self.show_codes_colour_filter = selected['name']  # colour range name
        if self.show_codes_colour_filter == "all":
            self.show_codes_colour_filter = ""
        show_codes_of_colour_range(self.app, self.ui.treeWidget, self.codes, selected)
        self.show_codes_like_filter = ""
        if self.show_codes_colour_filter == "":  # for clear filter code
            self.ui.pushButton_clear_filter_code.setVisible(False)
            self.ui.pushButton_clear_filter_code.setStyleSheet("")
        else:
            self.ui.pushButton_clear_filter_code.setVisible(True)
            self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")

    def clear_code_filter(self):
        """ Clear any active code filter (show codes like or show codes of colour)
        and restore all codes in the tree. """
        self.show_codes_like_filter = ""
        self.show_codes_colour_filter = ""
        self.ui.lineEdit_code_filter.setText("")
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, "")  # Show all codes
        self.ui.pushButton_clear_filter_code.setVisible(False)
        self.ui.pushButton_clear_filter_code.setStyleSheet("")  # reset style

    def clear_file_filter(self):
        """ Clear any active file filter (show files like, case files, attributes)
        and reload all files. """ 
        self.attributes = []
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        self.get_files()  # reload all files without filter
        self.ui.treeWidget.setCurrentItem(None)  # clear code selection to prevent unintended coding
        self.ui.pushButton_clear_filter_file.setVisible(False)
        self.ui.pushButton_clear_filter_file.setStyleSheet("")  # reset blue style

    def recursive_traverse(self, item, text_:str="", case_sensitive=False):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories and sub-codes. A code stays visible if it matches or
        if any of its descendant sub-codes matches, so a match is never hidden under a
        non-matching parent code. Returns True if this item or any descendant matches.
        Called by: show_codes_like
        Args:
            item: a QTreeWidgetItem
            text_:  Text string for matching with code names
            case_sensitive:  Bool
        """

        child_count = item.childCount()
        any_visible_descendant = False
        for i in range(child_count):
            child = item.child(i)
            is_code = "cid:" in child.text(1)
            # Recurse first so we know whether any descendant matches.
            descendant_match = self.recursive_traverse(child, text_, case_sensitive)
            if text_ == "":
                if is_code:
                    child.setHidden(False)
                any_visible_descendant = True
                continue
            self_match = False
            if is_code:
                cid = int(child.text(1)[4:])
                c = next((cc for cc in self.codes if cc['cid'] == cid), None)
                if c is not None:
                    if case_sensitive:
                        self_match = text_ in c['name']
                    else:
                        self_match = text_.lower() in c['name'].lower()
            visible = self_match or descendant_match
            if is_code:
                child.setHidden(not visible)
            if visible:
                any_visible_descendant = True
        return any_visible_descendant

    def keyPressEvent(self, event):
        """
        C New Category
        H hide / show top group box
        Ctrl 0 to Ctrl 9 - button presses
        + or W  Zoom out
        - or Q Zoom in
        Ctrl 0 to Ctrl 5 Buttons and Help
        Ctrl G - Gray image with highlighted codings
        L Show codes like
        Ctrl Z Undo last unmarking
        Code Tree:
            F2 Rename code or category
            F3 Code / Cat Memo
            F4 Delete
            F5 Change Colour
            F6 Move under
        """

        key = event.key()
        mods = event.modifiers()

        # New category
        if key == QtCore.Qt.Key.Key_C:
            # if category already selected, add new category to that
            supercatid = None
            selected = self.ui.treeWidget.currentItem()
            if selected is not None and selected.text(1)[0:3] == 'cat':
                supercatid = int(selected.text(1)[6:])
            self.code_tree.add_category(supercatid)
            return
        if key == QtCore.Qt.Key.Key_H:
            self.ui.groupBox_2.setHidden(not (self.ui.groupBox_2.isHidden()))
            return
        # Show codes like
        if key == QtCore.Qt.Key.Key_L:
            self.show_codes_like()
        # Ctrl Z undo last unmarked coding
        if key == QtCore.Qt.Key.Key_Z and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.undo_last_unmarked_code()
            return
        if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
            self.zoom_out()
            return
        if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
            self.zoom_in()
            return

        # Tree widget menu item keys F2 - F6, handled by the shared controller.
        if self.ui.treeWidget.hasFocus():
            if self.code_tree.handle_key_press(event):
                return

        # Ctrl 0 to 9, G
        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            if key == QtCore.Qt.Key.Key_G:
                self.image_highlight("gray")
                return
            if key == QtCore.Qt.Key.Key_1:
                self.go_to_next_file()
                return
            if key == QtCore.Qt.Key.Key_2:
                self.go_to_latest_coded_file()
                return
            if key == QtCore.Qt.Key.Key_3:
                self.file_memo(self.file_)
                return
            if key == QtCore.Qt.Key.Key_4:
                self.get_files_from_attributes()
                return
            if key == QtCore.Qt.Key.Key_5:
                self.show_important_coded()
                return
            if key == QtCore.Qt.Key.Key_0:
                self.help()
                return

    def zoom_out(self):
        v = self.ui.horizontalSlider.value()
        v -= 3
        if v < self.ui.horizontalSlider.minimum():
            return
        self.ui.horizontalSlider.setValue(v)

    def zoom_in(self):
        v = self.ui.horizontalSlider.value()
        v += 3
        if v > self.ui.horizontalSlider.maximum():
            return
        self.ui.horizontalSlider.setValue(v)

    def image_highlight(self, image_operation:str="gray", coded_area=None, code_id:int|None=None):
        """ Gray, blurred or solarised image with coloured coded highlight(s).
        Highlight all coded area, or selected coded area, or all areas coded by one specific code.
        Takes a few seconds to build and show image.
        Args:
            image_operation: gray, blurred, solarised
            coded_area: Dictionary of coded area
            coded_id: Integer code id
        """

        img = self.pixmap.toImage()
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        img.save(buffer, "PNG")
        try:
            pil_img = Image.open(BytesIO(buffer.data()))
        except PIL.Image.DecompressionBombError:
            msg = _("Cannot open image with PIL. The image it too large.")
            Message(self.app, _("Image highlight error"), msg).exec()
            return
        background = ImageOps.grayscale(pil_img)  # Default gray
        if image_operation == "solarize":
            background = ImageOps.solarize(pil_img)  # Invert all pixel values above a threshold.
        if image_operation == "blur":
            background = pil_img.filter(ImageFilter.GaussianBlur(radius=10))
        highlights = Image.new('RGB', (background.width, background.height))
        highlights.paste(background, (0, 0))
        draw = ImageDraw.Draw(highlights)
        if coded_area:
            # Highlight ONE coded area
            try:
                # Needs tuple of left, top, right, bottom
                coded_img = pil_img.crop((coded_area['x1'], coded_area['y1'], coded_area['x1'] + coded_area['width'],
                                          coded_area['y1'] + coded_area['height']))
                img_with_border = ImageOps.expand(coded_img, border=3, fill=coded_area['color'])
                # highlights.paste(coded_img, (int(ca['x1']), int(ca['y1']))) # No border
                highlights.paste(img_with_border, (int(coded_area['x1']), int(coded_area['y1'])))
                self.text_box(draw, background.width, (coded_area['x1'], coded_area['y1']), coded_area['name'],
                              coded_area['memo'])
            except SystemError as e_:
                logger.debug(e_)
        else:
            # Highlight all coded areas
            for coded in self.code_areas:
                try:
                    # Needs tuple of left, top, right, bottom
                    coded_img = pil_img.crop(
                        (coded['x1'], coded['y1'], coded['x1'] + coded['width'], coded['y1'] + coded['height']))
                    img_with_border = ImageOps.expand(coded_img, border=3, fill=coded['color'])
                    if code_id == coded['cid']:
                        # Specific code id selected to highlight all of this code
                        highlights.paste(img_with_border, (int(coded['x1']), int(coded['y1'])))
                        self.text_box(draw, background.width, (coded['x1'], coded['y1']), coded['name'], coded['memo'])
                    if not code_id:
                        # No specific code or coded area selected.
                        highlights.paste(img_with_border, (int(coded['x1']), int(coded['y1'])))
                        self.text_box(draw, background.width, (coded['x1'], coded['y1']), coded['name'], coded['memo'])
                except SystemError as e_:
                    logger.debug(e_)
                    print(e_)
                    print("Crop img: x1", coded['x1'], "y1", coded['y1'], "x2", coded['x1'] + coded['width'], "y2",
                          coded['y1'] + coded['height'])
                    print("Main img: w", background.width, "h", background.height)
        highlights.show()

        exp_dlg = ExportDirectoryPathDialog(self.app, "Image_highlights.jpg")
        filepath = exp_dlg.filepath
        if filepath is None:
            return
        highlights.save(filepath)
        msg = _('Image exported: ') + filepath
        Message(self.app, _('Image saved'), msg, "information").exec()
        self.parent_textEdit.append(msg)

    def text_box(self, draw, background_width, position, text:str, memo:str):
        """ Draw codename caption if show_code_captions=1, or codename plus memo if show_code_captions=2. """

        if self.show_code_captions == 0:
            return
        font = ImageFont.load_default()
        try:
            font_path = os.path.join(self.app.confighome, 'DroidSansMono.ttf')
            font = ImageFont.truetype(font_path, size=int(background_width / 90))
        except OSError:
            pass
        if self.show_code_captions == 2 and memo != "":
            text += "\n" + memo
        bounding_box = draw.textbbox(position, text, font=font)
        draw.rectangle(bounding_box, fill="white")
        draw.text(position, text, font=font, fill="black")

    def help(self):
        """ Open help for transcribe section in browser. """
        self.app.help_wiki("4.4.-Coding-Images")

    def eventFilter(self, object_, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop	63	A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop
        Also use eventFilter for QGraphicsView.
        """

        if object_ is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                # event position is QPointF, itemAt requires toPoint
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                self.code_tree.item_moved_update_data(item, parent)
                return True
            # Scroll the tree when dragged item it as top or bottom edges
            if event.type() == QtCore.QEvent.Type.DragMove:
                vsb = self.ui.treeWidget.verticalScrollBar()
                item = self.ui.treeWidget.currentItem()
                top = self.ui.treeWidget.visualRect(
                    self.ui.treeWidget.indexAt(self.ui.treeWidget.rect().topLeft())).bottom()
                bottom = self.ui.treeWidget.viewport().height()
                y = event.position().toPoint().y()
                if y < top + 8:  # Margin 0f 8
                    vsb.setValue(vsb.value() - 1)
                if y > bottom - 8:  # Margin of 8
                    vsb.setValue(vsb.value() + 1)
                return True
        if object_ is self.scene:
            # Detect mouse movement on the scene to update the dashed rectangle in real-time
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.type() == QtCore.QEvent.Type.GraphicsSceneMouseMove:
                if hasattr(self, 'is_dragging_handle') and self.is_dragging_handle:
                    # Call function to recalculate boundaries based on cursor movement
                    self.update_interactive_resize(event.scenePos())
                    return True
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == Qt.MouseButton.LeftButton:
                pos = event.buttonDownScenePos(Qt.MouseButton.LeftButton)
                # Intercept left click to initiate handle dragging or cancel it
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMousePress:
                    item_at = self.scene.itemAt(pos, QtGui.QTransform())
                    # Check if the click is exactly on one of the 4 handles...
                    if hasattr(self, 'item_to_resize') and self.item_to_resize and item_at and item_at.data(0) == "resize_handle":
                        self.is_dragging_handle = True
                        self.active_handle = item_at.data(1)  # Store which corner was clicked
                        
                        # Extract absolute data from the active segment, scaled to screen
                        it = self.item_to_resize
                        vx = it['x1'] * self.scale
                        vy = it['y1'] * self.scale
                        vw = it['width'] * self.scale
                        vh = it['height'] * self.scale
                        
                        # Calculate exact visual position applying rotations manually (90, 180, 270 degrees)
                        if self.degrees == 90:
                            vy = it['x1'] * self.scale
                            vx = (self.pixmap.height() - it['y1'] - it['height']) * self.scale
                            vh = it['width'] * self.scale
                            vw = it['height'] * self.scale
                        if self.degrees == 180:
                            vx = (self.pixmap.width() - it['x1'] - it['width']) * self.scale
                            vy = (self.pixmap.height() - it['y1'] - it['height']) * self.scale
                            vw = it['width'] * self.scale
                            vh = it['height'] * self.scale
                        if self.degrees == 270:
                            vy = (self.pixmap.width() - it['x1'] - it['width']) * self.scale
                            vx = it['y1'] * self.scale
                            vh = it['width'] * self.scale
                            vw = it['height'] * self.scale

                        # Store this starting geometric position
                        self.original_resize_geom = (vx, vy, vw, vh)
                        # Create the temporary rectangle that guides the user visually (live feedback)
                        self.interactive_rect_item = QtWidgets.QGraphicsRectItem(vx, vy, vw, vh)
                        pen = QtGui.QPen(QtGui.QColor("#ff0000"), 2, QtCore.Qt.PenStyle.DashLine)
                        self.interactive_rect_item.setPen(pen)
                        self.scene.addItem(self.interactive_rect_item)
                        
                        # Temporarily disable standard selection rubber band
                        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
                        return True
                    # If we didn't click a handle, but a segment was active, cancel the process
                    elif hasattr(self, 'item_to_resize') and self.item_to_resize:
                        self.item_to_resize = None
                        self.redraw_scene()  # Redraw clears the handles from the screen
                self.fill_coded_area_label(self.find_coded_areas_for_pos(pos))
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMousePress:
                    p0 = event.buttonDownScenePos(Qt.MouseButton.LeftButton)
                    self.selection = p0
                    return True
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMouseRelease:
                    p1 = event.lastScenePos()
                    # On button release, process and save the final change if dragging a handle
                    if hasattr(self, 'is_dragging_handle') and self.is_dragging_handle:
                        self.execute_interactive_resize(p1)
                        return True
                    self.create_code_area(p1)
                    return True
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == Qt.MouseButton.RightButton:
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMousePress:
                    p = event.buttonDownScenePos(Qt.MouseButton.RightButton)
                    self.scene_context_menu(p)
                    return True
        return False

    def scene_context_menu(self, pos):
        """ Scene context menu for setting importance, unmarking coded areas and adding memos. """

        # Outside image area, no context menu
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                if pos.x() > item.boundingRect().width() or pos.y() > item.boundingRect().height():
                    self.selection = None
                    return
        global_pos = QtGui.QCursor.pos()
        items = self.find_coded_areas_for_pos(pos)
        # Menu for show/hide top panel
        if not items:
            menu = QtWidgets.QMenu()
            menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            action_rotate = menu.addAction(_("Rotate clockwise"))
            action_rotate_counter = menu.addAction(_("Rotate counter-clockwise"))
            action_highlight_gray = menu.addAction(_("Highlight area - gray"))
            action_highlight_solarize = menu.addAction(_("Highlight area - solarize"))
            action_highlight_blur = menu.addAction(_("Highlight area - blur"))
            action_hide_top_groupbox = None
            action_show_top_groupbox = None
            if self.ui.groupBox_2.isHidden():
                action_show_top_groupbox = menu.addAction(_("Show control panel"))
            if not self.ui.groupBox_2.isHidden():
                action_hide_top_groupbox = menu.addAction(_("Hide control panel"))
            action = menu.exec(global_pos)
            if action is None:
                return
            if action == action_highlight_gray:
                self.image_highlight()
            if action == action_highlight_solarize:
                self.image_highlight("solarize")
            if action == action_highlight_blur:
                self.image_highlight("blur")
            if action == action_show_top_groupbox:
                self.ui.groupBox_2.setVisible(True)
            if action == action_hide_top_groupbox:
                self.ui.groupBox_2.setVisible(False)
            if action == action_rotate:
                self.rotate_clockwise()
            if action == action_rotate_counter:
                self.rotate_counter()
            return
        # build and show the context menu FIRST, before resolving which
        # segment to act on. The segment is only disambiguated after an action that
        # needs a specific segment is chosen (see below).
        item = items[0]  # used only for important-mark menu options when a single segment

        # Determine importance state for menu construction when there is only one segment.
        # With multiple segments we show both important options, since the target is not yet known.
        single_segment = len(items) == 1
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo'))
        action_unmark = menu.addAction(_('Unmark'))
        action_move_resize = menu.addAction(_("Move or resize"))
        # Add the option Interactive resize
        action_interactive_resize = menu.addAction(_("Interactive resize"))
        action_important = None
        action_not_important = None
        if single_segment:  # only filter important options when the target segment is unambiguous
            if item['important'] is None or item['important'] != 1:
                action_important = menu.addAction(_("Add important mark"))
            if item['important'] == 1:
                action_not_important = menu.addAction(_("Remove important mark"))
        else:  # multiple segments: offer both, decide after segment is selected
            action_important = menu.addAction(_("Add important mark"))
            action_not_important = menu.addAction(_("Remove important mark"))
        action_highlight_gray = menu.addAction(_("Highlight this area - gray"))
        action_highlight_solarize = menu.addAction(_("Highlight this area - solarize"))
        action_highlight_blur = menu.addAction(_("Highlight this area - blur"))
        action_highlight_code_gray = menu.addAction(_("Highlight this code - gray"))
        action_highlight_code_solarize = menu.addAction(_("Highlight this code - solarize"))
        action_highlight_code_blur = menu.addAction(_("Highlight this code - blur"))

        action = menu.exec(global_pos)
        if action is None:
            return

        # after an action is chosen, if it acts on a specific segment and there is
        # more than one segment under the cursor, ask which segment now.
        # include "Highlight this code" actions so the user picks which code's
        # cid is used when several segments overlap
        segment_actions = (action_memo, action_unmark, action_move_resize, action_interactive_resize,
                           action_important, action_not_important, action_highlight_gray,
                           action_highlight_solarize, action_highlight_blur,
                           action_highlight_code_gray, action_highlight_code_solarize,
                           action_highlight_code_blur)
        if len(items) > 1 and action in segment_actions:
            items_for_select = []
            for it in items:
                it_view = it.copy()
                it_view['name'] = f"{it['name']} ({it['owner']})"
                items_for_select.append(it_view)
            ui = DialogSelectItems(self.app, items_for_select, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            selected = ui.get_selected()
            if selected is None:
                return
            # Map back to original item (so we keep full dict as stored)
            for it in items:
                if it['imid'] == selected['imid']:
                    item = it
                    break
        if action == action_highlight_gray:
            self.image_highlight("gray", item)
        if action == action_highlight_code_gray:
            self.image_highlight("gray", None, item['cid'])
        if action == action_highlight_solarize:
            self.image_highlight("solarize", item)
        if action == action_highlight_code_solarize:
            self.image_highlight("solarize", None, item['cid'])
        if action == action_highlight_blur:
            self.image_highlight("blur", item)
        if action == action_highlight_code_blur:
            self.image_highlight("blur", None, item['cid'])

        if action == action_memo:
            self.coded_area_memo(item)
        if action == action_unmark:
            self.unmark(item)
        if action == action_important:
            self.set_coded_importance(item)
        if action == action_not_important:
            self.set_coded_importance(item, False)
        if action == action_move_resize:
            self.move_or_resize_coding(item)
        # If the user selects the new option, store the segment to be resized
        if action == action_interactive_resize:
            self.item_to_resize = item
            self.redraw_scene()  # Redrawing triggers draw_coded_areas, showing the handles
        items = self.find_coded_areas_for_pos(pos)
        self.fill_coded_area_label(items)

    def rotate_clockwise(self):
        self.degrees += 90
        if self.degrees > 270:
            self.degrees = 0
        self.redraw_scene()

    def rotate_counter(self):
        self.degrees -= 90
        if self.degrees < 0:
            self.degrees = 270
        self.redraw_scene()

    def move_or_resize_coding(self, item:dict[str,Any]):
        """ Move or resize a coding rectangle, in pixels.
        Args:
            item: Dictionary of image id, x1, y1, width, height, memo, date, owner, cid, important
        """

        ui = DialogMoveResizeRectangle(self.app)
        ui.exec()
        item['x1'] += ui.move_x
        if item['x1'] < 0:
            item['x1'] = 0
        # x is past the image size, so resize to 10 wide and 11 back from image x edge
        if item['x1'] + 11 > self.pixmap.width():
            item['x1'] = self.pixmap.width() - 11
            item['width'] = 10
        item['y1'] += ui.move_y
        if item['y1'] < 0:
            item['y1'] = 0
        # y is past the image size, so resize to 10 wide and 11 back from image y edge
        if item['y1'] + 11 > self.pixmap.height():
            item['y1'] = self.pixmap.height() - 11
            item['height'] = 10
        item['width'] += ui.resize_x
        if item['width'] < 10:
            item['width'] = 10
        if item['x1'] + item['width'] > self.pixmap.width():
            overreach = item['x1'] + item['width'] - self.pixmap.width()
            item['width'] -= overreach + 1
        item['height'] += ui.resize_y
        if item['height'] < 10:
            item['height'] = 10
        if item['y1'] + item['height'] > self.pixmap.height():
            overreach = item['y1'] + item['height'] - self.pixmap.height()
            item['height'] -= overreach + 1
        cur = self.app.conn.cursor()
        cur.execute("update code_image set x1=?,y1=?,width=?,height=? where imid=?",
                    (item['x1'], item['y1'], item['width'], item['height'], item['imid']))
        self.app.conn.commit()
        self.redraw_scene()
        self.app.delete_backup = False

    def find_coded_areas_for_pos(self, pos):
        """ Find any coded areas for this position AND for all visible coders.
        Args:
           pos:
        Returns: [] or coded items
        """

        if self.file_ is None:
            return
        # Reposition pos based on rotation
        pix_h_scaled = self.pixmap.height() * self.scale
        pix_w_scaled = self.pixmap.width() * self.scale
        if self.degrees == 90:
            pos = QtCore.QPointF(pos.y(), pix_h_scaled - pos.x())
        if self.degrees == 180:
            pos = QtCore.QPointF(pix_w_scaled - pos.x(), pix_h_scaled - pos.y())
        if self.degrees == 270:
            pos = QtCore.QPointF(pix_w_scaled - pos.y(), pos.x())
        items = []
        for item in self.code_areas:
            if item['id'] == self.file_['id']:
                if item['x1'] * self.scale <= pos.x() <= (item['x1'] + item['width']) * self.scale \
                        and item['y1'] * self.scale <= pos.y() <= (
                        item['y1'] + item['height']) * self.scale:
                    items.append(item)
        return items

    def fill_coded_area_label(self, items):
        """ Fill details of label about the currently clicked on coded area.
        Called by: right click scene menu.
        Args:
            items :  
        """

        if not items:
            return
        msg = ""
        tooltip = ""
        for i in items:
            for c in self.codes:
                if c['cid'] == i['cid']:
                    codename = c['name']
                    msg += codename
                    msg += f" ({i['owner']})"
            msg += f"\nx:{int(i['x1'])} y:{int(i['y1'])}"
            msg += f" w:{int(i['width'])} h:{int(i['height'])}"
            area = i['width'] * i['height']
            pic_area = self.pixmap.width() * self.pixmap.height()
            percent_area = round(area / pic_area * 100, 2)
            msg += f" area: {percent_area}%\n"
            tooltip = msg + "\n" + i['memo']
        self.ui.label_coded_area.setText(msg)
        self.ui.label_coded_area.setToolTip(tooltip)

    def set_coded_importance(self, item, important=True):
        """ Set or unset importance to coded image item.
        Importance is denoted using '1'
        params:
            item: dictionary of coded area
            important: boolean, default True """

        importance = None
        if important:
            importance = 1
        item['important'] = importance
        cur = self.app.conn.cursor()
        cur.execute('update code_image set important=? where imid=?', (importance, item['imid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.draw_coded_areas()

    def coded_area_memo(self, item:dict[str,Any]):
        """ Add memo to this coded area.
        Args:
            item : dictionary of coded area """

        ui = DialogMemo(self.app, _("Memo for code: ") + item['name'],
                        item['memo'])
        ui.exec()
        memo = ui.memo
        if memo != item['memo']:
            item['memo'] = memo
            cur = self.app.conn.cursor()
            cur.execute('update code_image set memo=? where imid=?', (ui.memo, item['imid']))
            self.app.conn.commit()
            self.app.delete_backup = False
        # Re-draw to update memos in tooltips
        self.draw_coded_areas()

    def undo_last_unmarked_code(self):
        """ Restore the last deleted code.
        Requires self.undo_deleted_code """

        if not self.undo_deleted_code:
            return
        item = self.undo_deleted_code
        cur = self.app.conn.cursor()
        cur.execute(
            "insert into code_image (id,x1,y1,width,height,cid,memo,date,owner, important, pdf_page) "
            "values(?,?,?,?,?,?,?,?,?,?,?)",
            (item['id'], item['x1'], item['y1'], item['width'], item['height'], item['cid'], item['memo'],
             item['date'], item['owner'], item['important'], item['pdf_page']))
        self.app.conn.commit()
        self.undo_deleted_code = []
        self.get_coded_areas()
        self.redraw_scene()
        self.fill_code_counts_in_tree()
        self.app.delete_backup = False

    def unmark(self, item):
        """ Remove coded area.
        Args:
            item : dictionary of coded area """

        self.undo_deleted_code = deepcopy(item)
        cur = self.app.conn.cursor()
        cur.execute("delete from code_image where imid=?", [item['imid'], ])
        self.app.conn.commit()
        self.get_coded_areas()
        self.redraw_scene()
        self.fill_code_counts_in_tree()
        self.app.delete_backup = False

    def create_code_area(self, p1):
        """ Create coded area coordinates from mouse release.
        The point and width and height must be based on the original image size,
        so add in scale factor.
        param:
            p1 : QtCore.QPointF of mouse release """

        if self.pixmap is None:
            return
        code_ = self.ui.treeWidget.currentItem()
        if code_ is None:
            Message(self.app, _("Coded area"), _("Select a code in the list first."), "warning").exec()
            return
        if code_.text(1)[0:3] == 'cat':
            Message(self.app, _("Coded area"), _("Select a code in the list first."), "warning").exec()
            return
        cid = int(code_.text(1)[4:])  # must be integer
        code_name = code_.text(0)
        pix_h_scaled = self.pixmap.height() * self.scale
        pix_w_scaled = self.pixmap.width() * self.scale
        width = p1.x() - self.selection.x()
        height = p1.y() - self.selection.y()
        x = self.selection.x()
        y = self.selection.y()
        # Reposition x and y and width, height based on rotation
        if self.degrees == 90:
            x = y
            # Need to use the p1 x point (mouse release point) as the y low values are reversed on the right hand side
            y = pix_h_scaled - p1.x()
            width, height = height, width
        if self.degrees == 180:
            x = pix_w_scaled - p1.x()
            y = pix_h_scaled - p1.y()
        if self.degrees == 270:
            y = x
            # Need to use the p1 y point (mouse release point) as the y low values are reversed on the left hand side
            x = pix_w_scaled - p1.y()
            width, height = height, width
        if width < 0:
            x = x + width
            width = abs(width)
        if height < 0:
            y = y + height
            height = abs(height)
        # instead of cancelling when the selection goes outside the image,
        # clamp it to the image bounds so it cannot exceed the limits but still codes
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                max_w = item.boundingRect().width()
                max_h = item.boundingRect().height()
                # Clamp top-left corner inside the image
                if x < 0:
                    width += x  # reduce width by the part that fell off the left edge
                    x = 0
                if y < 0:
                    height += y  # reduce height by the part that fell off the top edge
                    y = 0
                # Clamp bottom-right corner to the image edges
                if x + width > max_w:
                    width = max_w - x
                if y + height > max_h:
                    height = max_h - y
                break
        x_unscaled = round(x / self.scale)
        y_unscaled = round(y / self.scale)
        width_unscaled = round(width / self.scale)
        height_unscaled = round(height / self.scale)
        if width_unscaled < 10 or height_unscaled < 10:
            return
        item = {'imid': None, 'id': self.file_['id'], 'x1': x_unscaled, 'y1': y_unscaled,
                'width': width_unscaled, 'height': height_unscaled, 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                'cid': cid, 'memo': '', 'important': None, 'name': code_name, 'color': '#777777',
                'pdf_page': self.pdf_page}
        for c in self.codes:
            if c['cid'] == cid:
                item['color'] = c['color']
        cur = self.app.conn.cursor()
        cur.execute(
            "insert into code_image (id,x1,y1,width,height,cid,memo,date,owner, important, pdf_page) values(?,?,?,?,?,?"
            ",?,?,?,null,?)",
            (item['id'], item['x1'], item['y1'], item['width'], item['height'], cid, item['memo'],
             item['date'], item['owner'], self.pdf_page))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        imid = cur.fetchone()[0]
        item['imid'] = imid
        self.code_areas.append(item)
        self.redraw_scene()
        self.selection = None
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()

    # Functions responsible for mathematically processing the interactive resizing
    def update_interactive_resize(self, pos):
        """ Update the visual dashed rectangle during mouse movement. """ 
        if not self.interactive_rect_item or not self.original_resize_geom:
            return
            
        # Extract original boundaries (X, Y, Right, Bottom)
        orig_x, orig_y, orig_w, orig_h = self.original_resize_geom
        orig_right = orig_x + orig_w
        orig_bottom = orig_y + orig_h
        
        # Initialize new boundaries based on the original ones
        new_x, new_y = orig_x, orig_y
        new_right, new_bottom = orig_right, orig_bottom
        
        mouse_x, mouse_y = pos.x(), pos.y()
        min_size = 10 * self.scale  # Prevents the box from shrinking to near invisibility

        # clamp the mouse position to the visible image bounds before using it,
        # so dragging outside the image cannot push the rectangle past the edges
        # and removes the "jump" / over-reach when leaving the image area
        scaled_w = self.pixmap.width() * self.scale
        scaled_h = self.pixmap.height() * self.scale
        # When rotated 90/270 the visible image swaps width/height on screen
        if self.degrees in (90, 270):
            scaled_w, scaled_h = scaled_h, scaled_w
        if mouse_x < 0:
            mouse_x = 0
        if mouse_x > scaled_w:
            mouse_x = scaled_w
        if mouse_y < 0:
            mouse_y = 0
        if mouse_y > scaled_h:
            mouse_y = scaled_h

        # Logic to push the rectangle walls depending on the dragged corner
        if self.active_handle == "TL":  # Top-Left: Modifies left X and top Y
            new_x = min(mouse_x, orig_right - min_size)
            new_y = min(mouse_y, orig_bottom - min_size)
        elif self.active_handle == "TR":  # Top-Right: Modifies right X and top Y
            new_right = max(mouse_x, orig_x + min_size)
            new_y = min(mouse_y, orig_bottom - min_size)
        elif self.active_handle == "BL":  # Bottom-Left: Modifies left X and bottom Y
            new_x = min(mouse_x, orig_right - min_size)
            new_bottom = max(mouse_y, orig_y + min_size)
        elif self.active_handle == "BR":  # Bottom-Right: Modifies right X and bottom Y
            new_right = max(mouse_x, orig_x + min_size)
            new_bottom = max(mouse_y, orig_y + min_size)

        # Apply the new calculated size to the red dashed rectangle (Live feedback)
        self.interactive_rect_item.setRect(new_x, new_y, new_right - new_x, new_bottom - new_y)

    def execute_interactive_resize(self, release_pos):
        """ Calculate final size based on the interactive rect and update DB. """
        self.is_dragging_handle = False
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)  # Restore standard mode
        
        if not self.item_to_resize or not self.interactive_rect_item:
            self.item_to_resize = None
            self.redraw_scene()
            return
            
        final_rect = self.interactive_rect_item.rect()
        item = self.item_to_resize
        
        # Unscale back to the pixmap's real pixels
        v_x = final_rect.x() / self.scale
        v_y = final_rect.y() / self.scale
        v_w = final_rect.width() / self.scale
        v_h = final_rect.height() / self.scale
        
        px_w = self.pixmap.width()
        px_h = self.pixmap.height()
        
        # Inverse mapping: Translate the rotated screen coordinates back to the original 
        # 0-degree coordinates of the image to save them correctly in the DB.
        x_unscaled, y_unscaled = 0, 0
        width_unscaled, height_unscaled = 0, 0
        if self.degrees == 0:
            x_unscaled, y_unscaled = v_x, v_y
            width_unscaled, height_unscaled = v_w, v_h
        elif self.degrees == 90:
            x_unscaled = v_y
            y_unscaled = px_h - v_x - v_w
            width_unscaled = v_h
            height_unscaled = v_w
        elif self.degrees == 180:
            x_unscaled = px_w - v_x - v_w
            y_unscaled = px_h - v_y - v_h
            width_unscaled = v_w
            height_unscaled = v_h
        elif self.degrees == 270:
            x_unscaled = px_w - v_y - v_h
            y_unscaled = v_x
            width_unscaled = v_h
            height_unscaled = v_w

        x_unscaled = round(x_unscaled)
        y_unscaled = round(y_unscaled)
        width_unscaled = round(width_unscaled)
        height_unscaled = round(height_unscaled)
        
        # Strict boundaries: Prevent the user from expanding the box beyond the real image dimensions
        if x_unscaled < 0: x_unscaled = 0
        if y_unscaled < 0: y_unscaled = 0
        if x_unscaled + width_unscaled > px_w:
            width_unscaled = px_w - x_unscaled
        if y_unscaled + height_unscaled > px_h:
            height_unscaled = px_h - y_unscaled
            
        item['x1'] = x_unscaled
        item['y1'] = y_unscaled
        item['width'] = width_unscaled
        item['height'] = height_unscaled
        
        # Execute SQL statement to permanently update SQLite
        cur = self.app.conn.cursor()
        # Prevent app crash if the user resizes the segment to perfectly match an existing identical one
        try:
            cur.execute("update code_image set x1=?, y1=?, width=?, height=? where imid=?",
                        (item['x1'], item['y1'], item['width'], item['height'], item['imid']))
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            self.app.conn.rollback()
            Message(self.app, _("Duplicate Error"), _("This exact coded area already exists."), "warning").exec()
        
        # Clean up state variables and remove the dashed rectangle
        self.scene.removeItem(self.interactive_rect_item)
        self.interactive_rect_item = None
        self.active_handle = None
        self.original_resize_geom = None
        self.item_to_resize = None
        
        self.redraw_scene()
        self.app.delete_backup = False

class DialogViewImage(QtWidgets.QDialog):
    """ View image. View and edit displayed memo.
    Show a scalable and scrollable image.
    The slider values range from 10 to 99.
    Linked images have 'image:' at start of mediapath
    """

    def __init__(self, app, image_data):
        """ Image_data contains: {name, mediapath, owner, id, date, memo, fulltext}
        mediapath may be a link as: 'images:path'
        """

        self.app = app
        self.image_data = image_data
        self.degrees = 0  # For rotation
        self.pixmap = None
        self.scene = None
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_view_image()
        self.ui.setupUi(self)
        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        abs_path = ""
        if "images:" in self.image_data['mediapath']:
            abs_path = self.image_data['mediapath'][7:]  # Remove images:
        else:
            abs_path = self.app.project_path + self.image_data['mediapath']
        self.setWindowTitle(abs_path)
        image = QtGui.QImage(abs_path)
        if image.isNull():
            Message(self.app, _('Image error'), _("Cannot open: ") + abs_path, "warning").exec()
            self.close()
            return

        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        # Need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.scene.installEventFilter(self)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)
        self.ui.horizontalSlider.valueChanged[int].connect(self.redraw_scene)
        self.ui.horizontalSlider.setToolTip(_("Key + or W zoom in. Key - or Q zoom out"))
        self.ui.textEdit.setText(self.image_data['memo'])
        tt = _("L rotate clockwise\nR rotate anti-clockwise\n+ - zoom in and out")
        self.ui.graphicsView.setToolTip(tt)

        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        # - 30 - 80  are slider and textedit heights
        if self.pixmap.height() > self.height() - 30 - 80:
            scale = (self.height() - 30 - 80) / self.pixmap.height()
            slider_value = int(scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)

    def redraw_scene(self):
        """ Resize image. Triggered by user change in slider or + - keys
        """

        if self.pixmap is None:
            return
        scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = int(scale * self.pixmap.height())
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        transform = QtGui.QTransform().rotate(self.degrees)
        pixmap = pixmap.transformed(transform)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.ui.graphicsView.update()
        w_h = _("Width: ") + str(pixmap.size().width()) + _(" Height: ") + str(pixmap.size().height())
        msg = w_h + _(" Scale: ") + str(int(scale * 100)) + "%"
        self.ui.horizontalSlider.setToolTip(msg)

    def zoom_out(self):
        v = self.ui.horizontalSlider.value()
        v -= 3
        if v < self.ui.horizontalSlider.minimum():
            return
        self.ui.horizontalSlider.setValue(v)

    def zoom_in(self):
        v = self.ui.horizontalSlider.value()
        v += 3
        if v > self.ui.horizontalSlider.maximum():
            return
        self.ui.horizontalSlider.setValue(v)

    def eventFilter(self, object_, event):
        """ Using this event filter to apply key events.
        Key events on scene
        + and- keys
        L and R rotation
        """

        # Hide / unHide top groupbox
        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
                self.zoom_out()
                return True
            if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
                self.zoom_in()
                return True
            if key == QtCore.Qt.Key.Key_L:
                self.degrees -= 90
                if self.degrees < 0:
                    self.degrees = 270
                self.redraw_scene()
                return True
            if key == QtCore.Qt.Key.Key_R:
                self.degrees += 90
                if self.degrees > 270:
                    self.degrees = 0
                self.redraw_scene()
                return True
        return False
