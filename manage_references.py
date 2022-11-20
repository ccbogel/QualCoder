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
"""

#import datetime
import os
#import re
import sys
import logging
import traceback

from PyQt6 import QtWidgets, QtCore, QtGui
#from PyQt6.QtCore import Qt

from .GUI.ui_reference_manager import Ui_Dialog_reference_manager
#from .confirm_delete import DialogConfirmDelete
#from .helpers import Message
from .ris import Ris
#from .view_av import DialogViewAV
#from .view_image import DialogViewImage

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


class DialogReferenceManager(QtWidgets.QDialog):
    """ Dialog to manipulate files for a case.
    Add files to case, add all text or text portions from a text file.
    Remove file from a case. View file.
    """

    app = None
    parent_textEdit = None
    files = []
    refs = []

    def __init__(self, app_, parent_text_edit):

        sys.excepthook = exception_handler
        self.app = app_
        self.parent_textEdit = parent_text_edit
        self.files = []
        self.refs = []
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_reference_manager()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font2 = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font2 += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget_files.setStyleSheet(font2)
        self.ui.tableWidget_files.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        #self.ui.tableWidget_files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        #self.ui.tableWidget_files.customContextMenuRequested.connect(self.table_menu)
        self.ui.tableWidget_refs.setStyleSheet(font2)
        self.ui.tableWidget_refs.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui.tableWidget_refs.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        #self.ui.tableWidget_refs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        #self.ui.tableWidget_refs.customContextMenuRequested.connect(self.table_menu)

        self.get_data()

        self.ui.tableWidget_refs.installEventFilter(self)
        self.ui.tableWidget_files.installEventFilter(self)


    def get_data(self):
        """ Get data for files and references. """

        cur = self.app.conn.cursor()
        cur.execute("select id, name, risid, memo, date from source order by lower(name)")
        result = cur.fetchall()
        self.files = []
        keys = 'id', 'name', 'risid', 'memo', 'date'
        for row in result:
            self.files.append(dict(zip(keys, row)))
        self.fill_table_files()
        r = Ris(self.app)
        r.get_references()
        self.refs = r.refs
        self.fill_table_refs()

    def fill_table_files(self):
        """ Fill widget with file details. """

        rows = self.ui.tableWidget_files.rowCount()
        for c in range(0, rows):
            self.ui.tableWidget_files.removeRow(0)
        header_labels = ["id", "File name", "Ref Id"]
        self.ui.tableWidget_files.setColumnCount(len(header_labels))
        self.ui.tableWidget_files.setHorizontalHeaderLabels(header_labels)
        for row, f in enumerate(self.files):
            self.ui.tableWidget_files.insertRow(row)
            item = QtWidgets.QTableWidgetItem(str(f['id']))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_files.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(f['name'])
            memo = f['memo']
            if not memo:
                memo = ""
            item.setToolTip(memo)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_files.setItem(row, 1, item)
            risid = ""
            if f['risid'] is not None:
                risid = str(f['risid'])
            item = QtWidgets.QTableWidgetItem(risid)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_files.setItem(row, 2, item)
        self.ui.tableWidget_files.hideColumn(0)
        if self.app.settings['showids']:
            self.ui.tableWidget_files.showColumn(0)
        self.ui.tableWidget_files.resizeColumnsToContents()
        if self.ui.tableWidget_files.columnWidth(1) > 600:
            self.ui.tableWidget_files.setColumnWidth(1, 600)
        self.ui.tableWidget_files.resizeRowsToContents()

    def fill_table_refs(self):
        """ Fill widget with ref details. """

        rows = self.ui.tableWidget_refs.rowCount()
        for c in range(0, rows):
            self.ui.tableWidget_refs.removeRow(0)
        header_labels = ["RIS id", "Reference"]
        self.ui.tableWidget_refs.setColumnCount(len(header_labels))
        self.ui.tableWidget_refs.setHorizontalHeaderLabels(header_labels)
        for row, f in enumerate(self.refs):
            self.ui.tableWidget_refs.insertRow(row)
            item = QtWidgets.QTableWidgetItem(str(f['risid']))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(f['formatted'])
            item.setToolTip(f['details'])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, 1, item)
        if self.app.settings['showids']:
            self.ui.tableWidget_refs.showColumn(0)
        self.ui.tableWidget_refs.resizeColumnsToContents()
        if self.ui.tableWidget_refs.columnWidth(1) > 600:
            self.ui.tableWidget_refs.setColumnWidth(1, 600)
        self.ui.tableWidget_refs.resizeRowsToContents()

    def eventFilter(self, object_, event):
        """ Ctrl + L Link file(s) to reference.
        Ctrl + U to Unlink file
        Note. Fires multiple times very quickly.
        """

        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            mod = event.modifiers()
            if key == QtCore.Qt.Key.Key_L and (self.ui.tableWidget_refs.hasFocus() or self.ui.tableWidget_files.hasFocus()):
                self.link_files_to_reference()
                return True
        return False

    def link_files_to_reference(self):
        """ Link the selected files to the selected reference.
         """

        ref_row = self.ui.tableWidget_refs.currentRow()
        ref_row_obj = self.ui.tableWidget_refs.selectionModel().selectedRows()
        if not ref_row_obj:
            return
        ris_id = int(ref_row_obj[0].data()) # Only One index returned. Column 0 data
        file_row_objs = self.ui.tableWidget_files.selectionModel().selectedRows()
        if not file_row_objs:
            return
        fids = []
        for index in file_row_objs:
            fids.append(int(index.data()))   # Column 0 data

        print(ris_id, fids)





