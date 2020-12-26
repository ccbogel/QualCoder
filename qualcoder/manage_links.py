# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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
import sys
import traceback

from PyQt5 import QtCore, QtWidgets, QtGui

from code_text import DialogCodeText  # for isinstance()
from confirm_delete import DialogConfirmDelete
from GUI.ui_dialog_manage_links import Ui_Dialog_manage_links
from view_image import DialogCodeImage  # DialogCodeImage for isinstance()
from view_av import DialogCodeAV  # DialogCodeAV for isinstance()


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


class DialogManageLinks(QtWidgets.QDialog):
    """ Fix bad file links. Can browse to correct location to set a new file path.
    """

    parent_textEdit = None
    tab_coding = None  # Tab widget coding tab

    def __init__(self, app, parent_textEdit, tab_coding):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.tab_coding = tab_coding

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_links()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogmanagelinks_w'])
            h = int(self.app.settings['dialogmanagelinks_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        #self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        #self.ui.tableWidget.cellDoubleClicked.connect(self.cell_double_clicked)
        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.links = self.app.check_bad_file_links()
        self.fill_table()

    def closeEvent(self, event):
        """ Save dialog dimensions. """

        self.app.settings['dialogmanagelinks_w'] = self.size().width()
        self.app.settings['dialogmanagelinks_h'] = self.size().height()

    def table_menu(self, position):
        """ Context menu for opening file select dialog. """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()

        menu = QtWidgets.QMenu()
        action_open_file_dialog = menu.addAction(_("Select file"))
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action = menu.exec_(self.ui.tableWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_open_file_dialog:
            self.file_selection(row)

    def file_selection(self, x):
        """ Select a file to replace the bad link.
        Called by: table_menu, filename cell clicked.
        The path can be different but the file name must match.
        """

        file_path, ok = QtWidgets.QFileDialog.getOpenFileName(None, _('Select file'),
            self.app.settings['directory'])
        if not ok or file_path == []:
            return
        if len(file_path) < 4:
            return

        new_file_name = file_path.split('/')[-1]
        if self.links[x]['name'] != new_file_name:
            msg = _("Filename does not match.") + "\n" + self.links[x]['name'] + "\n" + new_file_name
            mb = QtWidgets.QMessageBox()
            mb.setIcon(QtWidgets.QMessageBox.Warning)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Wrong file'))
            mb.setText(msg)
            mb.exec_()
            return

        # All seems good so update link and database
        self.links[x]['mediapath'] = self.links[x]['mediapath'].split(':')[0] + ':' + file_path
        cur = self.app.conn.cursor()
        sql = "update source set mediapath=? where id=?"
        cur.execute(sql, [self.links[x]['mediapath'], self.links[x]['id']])
        self.app.conn.commit()
        self.fill_table()

        # Add file to file list in any opened coding dialog
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
        self.app.delete_backup = False

    def cell_selected(self):
        """ When the table widget cell is selected open file select dialog.
        """

        self.file_selection(self.ui.tableWidget.currentRow())

    def fill_table(self):
        """ Fill the table widget with file details. """

        self.ui.tableWidget.blockSignals(True)
        self.ui.tableWidget.setColumnCount(3)
        self.ui.tableWidget.setHorizontalHeaderLabels([_("Filename"), _("Current path"), _("Type")])
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        for row, item in enumerate(self.links):
            self.ui.tableWidget.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(item['name'])
            name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, 0, name_item)
            link = item['mediapath'].split(':')
            path_item = QtWidgets.QTableWidgetItem(link[1])
            path_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemIsEditable)
            if not os.path.exists(link[1]):
                # path_item.setBackground(QtGui.QBrush(QtGui.QColor("Red")))
                path_item.setForeground(QtGui.QBrush(QtGui.QColor("Red")))
            self.ui.tableWidget.setItem(row, 1, path_item)
            type_item = QtWidgets.QTableWidgetItem(link[0])
            type_item.setFlags(type_item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, 2, type_item)
        self.ui.tableWidget.hideColumn(2)
        self.ui.tableWidget.resizeColumnsToContents()
        if self.ui.tableWidget.columnWidth(0) > 450:
            self.ui.tableWidget.setColumnWidth(0, 450)
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.blockSignals(False)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = Ui_Dialog_manage_links()
    ui.show()
    sys.exit(app.exec_())

