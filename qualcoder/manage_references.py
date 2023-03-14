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

import os
from rispy import TAG_KEY_MAPPING
import sys
import logging
import traceback

from PyQt6 import QtWidgets, QtCore, QtGui

from .GUI.base64_helper import *
from .GUI.ui_reference_editor import Ui_DialogReferenceEditor
from .GUI.ui_manage_references import Ui_Dialog_manage_references
from .confirm_delete import DialogConfirmDelete
from .ris import Ris, RisImport

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text_)


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
        self.ui = Ui_Dialog_manage_references()
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
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_import_icon), "png")
        self.ui.pushButton_import.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_import.pressed.connect(self.import_references)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(link_icon), "png")
        self.ui.pushButton_link.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_link.pressed.connect(self.link_files_to_reference)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(undo_icon), "png")
        self.ui.pushButton_unlink_files.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_unlink_files.pressed.connect(self.unlink_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(pencil_icon), "png")
        self.ui.pushButton_edit_ref.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_edit_ref.pressed.connect(self.edit_reference)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(delete_icon), "png")
        self.ui.pushButton_delete_ref.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_delete_ref.pressed.connect(self.delete_reference)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_delete_icon), "png")
        self.ui.pushButton_delete_unused_refs.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_delete_unused_refs.setEnabled(False)
        self.ui.pushButton_delete_unused_refs.hide()
        self.get_data()
        self.ui.tableWidget_refs.setTabKeyNavigation(False)
        self.ui.tableWidget_refs.installEventFilter(self)
        self.ui.tableWidget_files.setTabKeyNavigation(False)
        self.ui.tableWidget_files.installEventFilter(self)
        self.ui.checkBox_hide_files.toggled.connect(self.fill_table_files)
        self.ui.checkBox_hide_refs.toggled.connect(self.fill_table_refs)

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
                if self.ui.checkBox_hide_files.isChecked():
                    self.ui.tableWidget_files.setRowHidden(row, True)
                else:
                    self.ui.tableWidget_files.setRowHidden(row, False)
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
        header_labels = ["Ref id", _("Reference")]
        self.ui.tableWidget_refs.setColumnCount(len(header_labels))
        self.ui.tableWidget_refs.setHorizontalHeaderLabels(header_labels)
        for row, ref in enumerate(self.refs):
            self.ui.tableWidget_refs.insertRow(row)
            item = QtWidgets.QTableWidgetItem(str(ref['risid']))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(ref['formatted'])
            item.setToolTip(ref['details'])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, 1, item)
            # Check if files assigned to this ref
            files_assigned = False
            for f in self.files:
                if f['risid'] == ref['risid']:
                    files_assigned = True
                    break
            if self.ui.checkBox_hide_refs.isChecked() and files_assigned:
                self.ui.tableWidget_refs.setRowHidden(row, True)
            else:
                self.ui.tableWidget_refs.setRowHidden(row, False)
        if self.app.settings['showids']:
            self.ui.tableWidget_refs.showColumn(0)
        self.ui.tableWidget_refs.resizeColumnsToContents()
        if self.ui.tableWidget_refs.columnWidth(1) > 600:
            self.ui.tableWidget_refs.setColumnWidth(1, 600)
        self.ui.tableWidget_refs.resizeRowsToContents()

    def import_references(self):
        """ Import RIS formatted references from .ris or .txt files """

        RisImport(self.app, self.parent_textEdit)
        self.get_data()

    def keyPressEvent(self, event):
        """ Used to activate buttons.
        Ctrl 2 to 5
        """
        key = event.key()
        mods = QtWidgets.QApplication.keyboardModifiers()
        # Ctrl 2 to 5
        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            if key == QtCore.Qt.Key.Key_2:
                self.unlink_files()
                return
            if key == QtCore.Qt.Key.Key_3:
                self.edit_reference()
                return
            if key == QtCore.Qt.Key.Key_4:
                self.import_references()
                return
            if key == QtCore.Qt.Key.Key_5:
                self.delete_reference()
                return
            '''if key == QtCore.Qt.Key.Key_0:
                self.help()
                return'''

    def eventFilter(self, object_, event):
        """ L Link files to reference.
        U to unlink selected files
        Note. Fires multiple times very quickly.
        """

        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            #mod = event.modifiers()
            if key == QtCore.Qt.Key.Key_L and (self.ui.tableWidget_refs.hasFocus() or self.ui.tableWidget_files.hasFocus()):
                self.link_files_to_reference()
                return True
            if key == QtCore.Qt.Key.Key_U and (self.ui.tableWidget_refs.hasFocus() or self.ui.tableWidget_files.hasFocus()):
                self.unlink_files()
                return True
        return False

    def unlink_files(self):
        """ Remove linked reference from selected files. """

        file_row_objs = self.ui.tableWidget_files.selectionModel().selectedRows()
        if not file_row_objs:
            return
        cur = self.app.conn.cursor()
        for index in file_row_objs:
            fid = int(index.data())  # Column 0 data
            #print(fid)
            cur.execute("update source set risid=null where id=?", [fid])
            self.app.conn.commit()
            self.ui.tableWidget_files.item(index.row(), 2).setText("")
        self.get_data()

    def link_files_to_reference(self):
        """ Link the selected files to the selected reference.
         """

        ref_row_obj = self.ui.tableWidget_refs.selectionModel().selectedRows()
        if not ref_row_obj:
            return
        ris_id = int(ref_row_obj[0].data())  # Only One index returned. Column 0 data
        file_row_objs = self.ui.tableWidget_files.selectionModel().selectedRows()
        if not file_row_objs:
            return
        ref = None
        attr_values = {"Ref_Authors": "", "Ref_Title": "", "Ref_Type": "", "Ref_Year": ""}
        for r in self.refs:
            if r['risid'] == ris_id:
                ref = r
        try:
            attr_values['Ref_Authors'] = ref['AU']
        except KeyError:
            pass
        try:
            attr_values['Ref_Authors'] += " " + ref['A1']
        except KeyError:
            pass
        try:
            attr_values['Ref_Authors'] += " " + ref['A2']
        except KeyError:
            pass
        try:
            attr_values['Ref_Authors'] += " " + ref['A3']
        except KeyError:
            pass
        try:
            attr_values['Ref_Authors'] += " " + ref['A4']
        except KeyError:
            pass
        try:
            attr_values['Ref_Title'] = ref['TI']
        except KeyError:
            pass
        try:
            attr_values['Ref_Type'] = ref['TY']
        except KeyError:
            pass
        try:
            attr_values['Ref_Year'] = ref['PY']
        except KeyError:
            pass
        cur = self.app.conn.cursor()
        for index in file_row_objs:
            fid = int(index.data())  # Column 0 data
            cur.execute("update source set risid=? where id=?", [ris_id, fid])
            self.app.conn.commit()
            self.ui.tableWidget_files.item(index.row(), 2).setText(str(ris_id))
            sql = "update attribute set value=? where id=? and name=?"
            for attribute in attr_values:
                cur.execute(sql, [attr_values[attribute], fid, attribute])
                self.app.conn.commit()
        self.get_data()

    def edit_reference(self):
        """ Edit selected reference. """

        ref_row_obj = self.ui.tableWidget_refs.selectionModel().selectedRows()
        if not ref_row_obj:
            return
        ris_id = int(ref_row_obj[0].data())  # Only One index returned. Column 0 data
        ref_data = None
        for r in self.refs:
            if r['risid'] == ris_id:
                ref_data = r
        short_dict = {}
        for k in ref_data:
            if len(k) == 2:
                short_dict[k] = ref_data[k]
        reference_editor = QtWidgets.QDialog()
        ui_re = Ui_DialogReferenceEditor()
        ui_re.setupUi(reference_editor)
        ui_re.tableWidget.setColumnCount(2)
        ui_re.tableWidget.setHorizontalHeaderLabels(["RIS", "Data"])
        for row, key in enumerate(short_dict):
            ui_re.tableWidget.insertRow(row)
            ris_item = QtWidgets.QTableWidgetItem(key)
            ris_item.setFlags(ris_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            for tagkey in TAG_KEY_MAPPING:
                #print(tk, TAG_KEY_MAPPING[tk])
                if key == tagkey:
                    ris_item.setToolTip(TAG_KEY_MAPPING[tagkey])
            ui_re.tableWidget.setItem(row, 0, ris_item)
            value_item = QtWidgets.QTableWidgetItem(short_dict[key])
            ui_re.tableWidget.setItem(row, 1, value_item)
        ui_re.tableWidget.resizeColumnsToContents()
        if ui_re.tableWidget.columnWidth(1) > 600:
            ui_re.tableWidget.setColumnWidth(1, 600)
        ui_re.tableWidget.resizeRowsToContents()
        ok = reference_editor.exec()
        if not ok:
            return
        rows = ui_re.tableWidget.rowCount()
        for i in range(0, rows):
            print()
        cur = self.app.conn.cursor()
        ref_edited = False
        for row, key in enumerate(short_dict):
            if ui_re.tableWidget.item(row, 1).text() != short_dict[key]:
                cur.execute("update ris set value=? where risid=? and tag=?",
                            [ui_re.tableWidget.item(row, 1).text(), ris_id, key])
                self.app.conn.commit()
                ref_edited = True
        if ref_edited:
            self.parent_textEdit.append(_("Reference edited."))
        self.get_data()
        self.fill_table_refs()

    def delete_reference(self):
        """ Delete the selected reference.
        Remove reference risid from files.
        """

        ref_row_obj = self.ui.tableWidget_refs.selectionModel().selectedRows()
        if not ref_row_obj:
            return
        ris_id = int(ref_row_obj[0].data())  # Only One index returned. Column 0 data
        note = _("Delete this reference.") + " Ref id {" + str(ris_id) + "}  \n"
        for r in self.refs:
            if r['risid'] == ris_id:
                note += r['formatted']
        ui = DialogConfirmDelete(self.app, note)
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("update source set risid=null where risid=?", [ris_id])
        cur.execute("delete from ris where risid=?", [ris_id])
        self.app.conn.commit()
        self.get_data()
        self.fill_table_refs()
        self.fill_table_files()
        self.parent_textEdit.append(_("Reference deleted."))

