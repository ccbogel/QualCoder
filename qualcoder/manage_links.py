# -*- coding: utf-8 -*-

"""
Copyright (c) 2024 Colin Curtain

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

import logging
import os
import time

from PyQt6 import QtCore, QtWidgets, QtGui

from .code_text import DialogCodeText  # for isinstance()
from .GUI.ui_dialog_manage_links import Ui_Dialog_manage_links
from .helpers import Message
from .view_av import DialogCodeAV  # for isinstance()
from .view_image import DialogCodeImage  # DialogCodeImage for isinstance()

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogManageLinks(QtWidgets.QDialog):
    """ Fix bad file links. Can browse to correct location to set a new file path.
    """

    parent_textEdit = None
    tab_coding = None  # Tab widget coding tab for updates
    links = []

    def __init__(self, app, parent_text_edit, tab_coding):

        self.app = app
        self.parent_textEdit = parent_text_edit
        self.tab_coding = tab_coding
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_links()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogmanagelinks_w'])
            h = int(self.app.settings['dialogmanagelinks_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except KeyError:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.links = self.app.check_bad_file_links()
        for link in self.links:
            link['filepaths'] = []
        self.home = os.path.expanduser('~')
        self.fill_table()
        self.ui.pushButton_search_folders.pressed.connect(self.find_filepaths)

    def find_filepaths(self):
        """ Get file paths of this file name. """
        pd = QtWidgets.QProgressDialog(labelText=self.home[-30:], minimum=0, maximum=0, parent=self)
        pd.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        pd.setWindowTitle(_('Search folders'))
        pd.show()
        last_msg_update = time.time()
        for link in self.links:
            paths = []
            for root, dirs, files in os.walk(self.home):
                QtWidgets.QApplication.processEvents() # necessary to update the progress dialog
                if time.time() - last_msg_update > 0.1:  
                    pd.setLabelText(f'...{root[-30:]}')
                    last_msg_update = time.time()
                if link['name'] in files:
                    paths.append(os.path.join(root, link['name']))
                if pd.wasCanceled() or len(paths) > 2:
                    break
            link['filepaths'] = paths
        self.fill_table()
        pd.close()

    def closeEvent(self, event):
        """ Save dialog dimensions. """

        self.app.settings['dialogmanagelinks_w'] = self.size().width()
        self.app.settings['dialogmanagelinks_h'] = self.size().height()

    def table_menu(self, position):
        """ Context menu for opening file select dialog. """

        row = self.ui.tableWidget.currentRow()
        menu = QtWidgets.QMenu()
        action_open_file_dialog = menu.addAction(_("Select file"))
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_open_file_dialog:
            self.file_dialog_selection(row)

    def file_dialog_selection(self, row):
        """ Select a file using  a file dialog to replace the bad link.
        Called by: table_menu, filename cell clicked.
        The path can be different but the file name must match.
        param: row : Integer of selected QTableWidget row
        """

        file_path, ok = QtWidgets.QFileDialog.getOpenFileName(None, _('Select file'),
                                                              self.app.settings['directory'])
        if not ok or file_path == []:
            return
        if len(file_path) < 4:
            return
        new_file_name = file_path.split('/')[-1]
        if self.links[row]['name'] != new_file_name:
            msg = _("Filename does not match.") + f"\n{self.links[row]['name']}\n{new_file_name}"
            Message(self.app, _('Wrong file'), msg, "warning").exec()
            return
        self.update_database(file_path, row)

    def update_database(self, new_file_path, row):
        """ Update database and links list.
         Called by: file_dialog_selection, cell_selected. """

        new_file_name = new_file_path.split('/')[-1]
        # Use split ':',1 as can have ':' as a part of the file path
        self.links[row]['mediapath'] = self.links[row]['mediapath'].split(':', 1)[0] + ':' + new_file_path
        cur = self.app.conn.cursor()
        sql = "update source set mediapath=? where id=?"
        cur.execute(sql, [self.links[row]['mediapath'], self.links[row]['id']])
        self.app.conn.commit()
        self.fill_table()
        # Update file in file list in any opened coding dialog
        contents = self.tab_coding.layout()
        if contents:
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogCodeImage):
                    c.get_files()
                if isinstance(c, DialogCodeAV):
                    c.get_files()
                if isinstance(c, DialogCodeText):
                    c.get_files()
        self.parent_textEdit.append(_("Bad link fixed for file: ") + new_file_name + _(" Path: ") + new_file_path)
        self.app.delete_backup = False

    def cell_selected(self):
        """ When the table widget cell is selected open file select dialog.
        Or select suggested file path.
        """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()
        if col < 3:  # type, filename, current filepath
            self.file_dialog_selection(self.ui.tableWidget.currentRow())
            return
        try:
            file_path = self.ui.tableWidget.item(row, col).text()
        except AttributeError:  # NoneType
            return
        if file_path == "":
            return
        self.update_database(file_path, row)

    def fill_table(self):
        """ Fill the table widget with file details.
         Also contains two columns for filepath suggestions. """

        self.ui.tableWidget.blockSignals(True)
        self.ui.tableWidget.setColumnCount(5)
        self.ui.tableWidget.setHorizontalHeaderLabels(
            [_("Type"), _("Filename"), _("Current path"), _("Suggestion 1"), _("Suggestion 2")])
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        for row, item in enumerate(self.links):
            self.ui.tableWidget.insertRow(row)
            type_and_path = item['mediapath'].split(':', 1)
            type_item = QtWidgets.QTableWidgetItem(type_and_path[0])
            type_item.setFlags(type_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, 0, type_item)
            name_item = QtWidgets.QTableWidgetItem(item['name'])
            name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, 1, name_item)
            path_item = QtWidgets.QTableWidgetItem(type_and_path[1])
            path_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            if not os.path.exists(type_and_path[1]):
                path_item.setForeground(QtGui.QBrush(QtGui.QColor("Red")))
            self.ui.tableWidget.setItem(row, 2, path_item)
            if 'filepaths' in item:
                if len(item['filepaths']) > 0:
                    suggestion1 = QtWidgets.QTableWidgetItem(item['filepaths'][0])
                    suggestion1.setFlags(name_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                    self.ui.tableWidget.setItem(row, 3, suggestion1)
                if len(item['filepaths']) > 1:
                    suggestion2 = QtWidgets.QTableWidgetItem(item['filepaths'][1])
                    suggestion2.setFlags(name_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                    self.ui.tableWidget.setItem(row, 4, suggestion2)
        self.ui.tableWidget.hideColumn(0)
        self.ui.tableWidget.resizeColumnsToContents()
        if self.ui.tableWidget.columnWidth(0) > 450:
            self.ui.tableWidget.setColumnWidth(0, 450)
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.blockSignals(False)
