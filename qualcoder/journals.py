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
"""

from PyQt6 import QtCore, QtWidgets, QtGui
import datetime
import os
import re
import logging
# from spellchecker import SpellChecker
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import webbrowser

from .add_item_name import DialogAddItemName
from .add_attribute import DialogAddAttribute
from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_journals import Ui_Dialog_journals
from .helpers import Message, ExportDirectoryPathDialog, MarkdownHighlighter
from .memo import DialogMemo

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

NAME_COLUMN = 0
DATE_COLUMN = 1
OWNER_COLUMN = 2
JID_COLUMN = 3
ATTRIBUTE_START_COLUMN = 4


class DialogJournals(QtWidgets.QDialog):
    """  View, create, export, rename and delete journals. """

    journals = []
    header_labels = []
    jid = None  # journal database jid
    app = None
    parent_text_edit = None
    textDialog = None
    # variables for searching through journal(s)
    search_indices = []  # A list of tuples of (journal name, match.start, match length)
    search_index = 0
    text_changed_flag = False
    rows_hidden = False
    qtimer = None
    timer_msecs = 1500

    # Timer to reduce overly sensitive key events
    keypress_timer = 0

    def __init__(self, app, parent_text_edit, parent=None):

        super(DialogJournals, self).__init__(parent)  # overrride accept method
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.qtimer = QtCore.QTimer()
        self.qtimer.timeout.connect(self.update_database_text)
        self.keypress_timer = datetime.datetime.now()
        self.text_changed_flag = False
        self.rows_hidden = False
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_journals()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        try:
            s0 = int(self.app.settings['dialogjournals_splitter0'])
            s1 = int(self.app.settings['dialogjournals_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except KeyError:
            pass
        self.journals = []
        self.current_jid = None
        self.search_indices = []
        self.search_index = 0
        self.attribute_labels_ordered = []
        self.load_journals()
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.tableWidget.itemSelectionChanged.connect(self.table_selection_changed)
        self.ui.pushButton_create.setIcon(qta.icon('mdi6.pencil-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_create.clicked.connect(self.create_journal)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export.clicked.connect(self.export)
        self.ui.pushButton_delete.setIcon(qta.icon('mdi6.delete-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_delete.clicked.connect(self.delete_journal)
        self.ui.pushButton_export_all.setIcon(qta.icon('mdi6.export-variant', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export_all.clicked.connect(self.export_all_journals_as_one_file)
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.pushButton_add_attribute.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_add_attribute.clicked.connect(self.add_attribute)

        # Search text in journals
        self.ui.label_search_regex.setPixmap(qta.icon('mdi6.text-search').pixmap(22, 22))
        self.ui.label_search_all_journals.setPixmap(qta.icon('mdi6.text-box-multiple-outline').pixmap(22, 22))
        self.ui.pushButton_previous.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        self.ui.pushButton_next.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.checkBox_search_all_journals.stateChanged.connect(self.search_for_text)
        self.ui.textEdit.textChanged.connect(self.text_changed)
        self.ui.textEdit.installEventFilter(self)
        self.ui.textEdit.setTabChangesFocus(True)
        #spell = SpellChecker()  # Was testing this out Dont use
        # spell = SpellChecker(language='de')
        # spell = SpellChecker(language='es')
        # spell = SpellChecker(language='fr')
        # spell = SpellChecker(language='pt')
        highlighter = MarkdownHighlighter(self.ui.textEdit, self.app)
        self.ui.tableWidget.setTabKeyNavigation(False)

        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.tableWidget.horizontalHeader().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.horizontalHeader().customContextMenuRequested.connect(self.table_header_menu)

        self.ui.textEdit.hide()
        self.attribute_names = []  # For AddAttribute dialog

    def load_journals(self, order="name asc"):
        """ Load journals.
        Order by Name asc/desc date asc/desc.
        param: order: String for name, modified; or attributename + '| asc' or '|desc' suffix.
        """

        # Check for attribute ordering
        att_ordering = None
        att_name = None
        if order[-5] == "|":
            att_ordering = " " + order[-4:]
            att_name = order[:-5]
        self.check_attribute_placeholders()
        self.journals = []
        cur = self.app.conn.cursor()
        if not att_ordering:
            sql = "select name, date, jentry, owner, jid from journal order by "
            sql += order
            cur.execute(sql)
            result = cur.fetchall()
            for row in result:
                self.journals.append({'name': row[0], 'date': row[1], 'jentry': row[2], 'owner': row[3], 'jid': row[4],
                                      'attributes': []})
        else:
            # Get attribute value type
            cur.execute("select valuetype from attribute_type where name=?", [att_name])
            res = cur.fetchone()
            valuetype = res[0]
            sql = "select journal.name, journal.date, jentry, journal.owner, journal.jid from journal "
            sql += "join attribute on attribute.id=journal.jid where attribute.attr_type='journal' "
            sql += f"and attribute.name='{att_name}'"
            if valuetype == "numeric":
                sql += f" order by cast(attribute.value as real) {att_ordering}"
            else:
                sql += f" order by attribute.value {att_ordering}"
            cur.execute(sql)
            result = cur.fetchall()
            for row in result:
                self.journals.append({'name': row[0], 'date': row[1], 'jentry': row[2], 'owner': row[3], 'jid': row[4],
                                      'attributes': []})
        # Attributes and attributes in table header labels
        self.header_labels = [_("Name"), _("Modified"), _("Coder"), _("jid")]
        self.header_value_type = ["character", "character", "character", "numeric"]

        sql = "select name, valuetype from attribute_type where caseOrFile='journal' order by upper(name)"
        cur.execute(sql)
        attribute_names_res = cur.fetchall()
        self.attribute_names = []  # For AddAttribute dialog
        self.attribute_labels_ordered = []  # Help filling table more quickly
        for att_name in attribute_names_res:
            self.attribute_names.append({"name": att_name[0]})
            self.header_labels.append(att_name[0])
            self.header_value_type.append(att_name[1])
            self.attribute_labels_ordered.append(att_name[0])
        # Add list of attribute values to files, order matches header columns
        sql = "select ifnull(value, '') from attribute where attr_type='journal' and attribute.name=? and id=?"
        for j in self.journals:
            for att_name in self.attribute_labels_ordered:
                cur.execute(sql, [att_name, j['jid']])
                res = cur.fetchone()
                if res:
                    j['attributes'].append(res[0])
        self.fill_table()
        # To prevent text entry errors, after re-ordering, clear journal area
        self.ui.label_jname.setText(_("Journal: "))
        self.jid = None
        self.ui.textEdit.clear()
        self.ui.textEdit.hide()

    def add_attribute(self):
        """ When add button pressed, opens the AddAtribute dialog to get new attribute text.
        Then get the attribute type through a dialog.
        AddAttribute dialog checks for duplicate attribute name.
        New attribute is added to the model and database.
        Reserved attribute words - used for imported references:
        Ref_Type (Type of Reference) – character variable
        Ref_Author (authors list) – character
        Ref_Title – character
        Ref_Year (of publication) – numeric
        """

        ui = DialogAddAttribute(self.app)
        ok = ui.exec()
        if not ok:
            return
        name = ui.new_name
        value_type = ui.value_type
        if name == "":
            return

        self.attribute_names.append({'name': name})
        # Update attribute_type list and database
        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                    (name, now_date, self.app.settings['codername'], "", 'journal', value_type))
        self.app.conn.commit()
        self.app.delete_backup = False
        sql = "select jid from journal"
        cur.execute(sql)
        jids = cur.fetchall()
        for jid_ in jids:
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            cur.execute(sql, (name, "", jid_[0], 'journal', now_date, self.app.settings['codername']))
        self.app.conn.commit()
        self.load_journals()
        self.fill_table()
        self.parent_text_edit.append(f'{_("Attribute added to journals:")} {name}, {_("type")}: {value_type}')

    def check_attribute_placeholders(self):
        """ Journals can be added after attributes are in the project.
         Need to add placeholder attribute values for these, if missing.
         Also,if a journal is deleted, check and remove any isolated attribute values. """

        cur = self.app.conn.cursor()
        sql = "select jid from journal "
        cur.execute(sql)
        journal_jids_res = cur.fetchall()
        sql = 'select name from attribute_type where caseOrFile ="journal"'
        cur.execute(sql)
        attr_types = cur.fetchall()
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'journal','',?,?,?)"
        for jid in journal_jids_res:
            for attribute in attr_types:
                sql = "select value from attribute where id=? and name=?"
                cur.execute(sql, (jid[0], attribute[0]))
                res = cur.fetchone()
                if res is None:
                    placeholders = [attribute[0], jid[0], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    self.app.settings['codername']]
                    cur.execute(insert_sql, placeholders)
        self.app.conn.commit()

        # Check and delete attribute values where journal has been deleted
        attribute_to_del_sql = "SELECT distinct attribute.id FROM attribute where \
        attribute.id not in (select journal.jid from journal) order by attribute.id asc"
        cur.execute(attribute_to_del_sql)
        res = cur.fetchall()
        for r in res:
            cur.execute("delete from attribute where attr_type='journal' and id=?", [r[0], ])
            self.app.conn.commit()

    @staticmethod
    def help():
        """ Open help for transcribe section in browser. """

        url = "https://github.com/ccbogel/QualCoder/wiki/5.2.-Journals"
        webbrowser.open(url)

    def keyPressEvent(self, event):
        """ Used to activate buttons. """
        key = event.key()
        mods = QtWidgets.QApplication.keyboardModifiers()

        # Ctrl + F jump to search box
        if key == QtCore.Qt.Key.Key_F and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.ui.lineEdit_search.setFocus()
            return
        # Ctrl 0 to 4
        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            if key == QtCore.Qt.Key.Key_1:
                self.create_journal()
                return
            if key == QtCore.Qt.Key.Key_2:
                self.export()
                return
            if key == QtCore.Qt.Key.Key_3:
                self.export_all_journals_as_one_file()
                return
            if key == QtCore.Qt.Key.Key_4:
                self.delete_journal()
                return
            if key == QtCore.Qt.Key.Key_0:
                self.help()
                return

    def fill_table(self):
        """ Fill journals table. Update journal count label. """

        self.ui.tableWidget.blockSignals(True)
        self.ui.tableWidget.setColumnCount(len(self.header_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(self.header_labels)
        self.ui.tableWidget.horizontalHeader().setStretchLastSection(False)
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        for row, data in enumerate(self.journals):
            self.ui.tableWidget.insertRow(row)
            self.ui.tableWidget.setItem(row, NAME_COLUMN, QtWidgets.QTableWidgetItem(data['name']))
            item = QtWidgets.QTableWidgetItem(data['date'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, DATE_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(data['owner'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, OWNER_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(str(data['jid']))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, JID_COLUMN, item)
            # Add attributes
            for offset, attribute in enumerate(data['attributes']):
                item = QtWidgets.QTableWidgetItem(attribute)
                self.ui.tableWidget.setItem(row, ATTRIBUTE_START_COLUMN + offset, item)

        self.ui.tableWidget.verticalHeader().setVisible(False)
        if self.app.settings['showids']:
            self.ui.tableWidget.showColumn(JID_COLUMN)
        else:
            self.ui.tableWidget.hideColumn(JID_COLUMN)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
        self.jid = None
        self.ui.tableWidget.clearSelection()
        self.ui.tableWidget.blockSignals(False)
        self.ui.textEdit.setText("")
        self.ui.label_jcount.setText(_("Journals: ") + str(len(self.journals)))

    def table_header_menu(self, position):

        if not self.journals:
            return
        index_at = self.ui.tableWidget.indexAt(position)
        col = int(index_at.column())
        menu = QtWidgets.QMenu(self)
        action_name_asc = None
        action_name_desc = None
        if col == NAME_COLUMN:
            action_name_asc = menu.addAction(_("Ascending"))
            action_name_desc = menu.addAction(_("Descending"))
        action_modified_date_asc = None
        action_modified_date_desc = None
        if col == DATE_COLUMN:
            action_modified_date_asc = menu.addAction(_("Ascending"))
            action_modified_date_desc = menu.addAction(_("Descending"))
        action_attribute_ascending = None
        action_attribute_descending = None
        if col >= ATTRIBUTE_START_COLUMN:
            action_attribute_ascending = menu.addAction(_("Ascending"))
            action_attribute_descending = menu.addAction(_("Descending"))

        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action == action_modified_date_asc:
            self.load_journals("date asc")
            return
        if action == action_modified_date_desc:
            self.load_journals("date desc")
            return
        if action == action_name_asc:
            self.load_journals("name asc")
            return
        if action == action_name_desc:
            self.load_journals("name desc")
            return
        if action == action_attribute_ascending:
            attribute_name = self.header_labels[col]
            self.load_journals(f"{attribute_name}| asc")
            return
        if action == action_attribute_descending:
            attribute_name = self.header_labels[col]
            self.load_journals(f"{attribute_name}|desc")
            return

    def table_menu(self, position):
        """ Context menu for displaying table rows in differing order,
            Showing specific rows, adding dates to Character Attributes that contain 'date' in the name.
        """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()
        item = self.ui.tableWidget.item(row, col)
        item_text = ""
        if item is not None:
            item_text = item.text()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_name_asc = None
        action_name_desc = None
        action_show_name_like = None
        if col == NAME_COLUMN:
            action_name_asc = menu.addAction(_("Ascending"))
            action_name_desc = menu.addAction(_("Descending"))
            action_show_name_like = menu.addAction(_("Show name like"))
        action_modified_date_asc = None
        action_modified_date_desc = None
        if col == DATE_COLUMN:
            action_modified_date_asc = menu.addAction(_("Ascending"))
            action_modified_date_desc = menu.addAction(_("Descending"))
        action_show_this_coder = None
        coder_names = []
        for j in self.journals:
            coder_names.append(j['owner'])
        coder_name_set = set(coder_names)
        if len(coder_name_set) > 1 and col == OWNER_COLUMN:
            action_show_this_coder = menu.addAction(_("Show this coder"))
        action_show_values_like = None
        action_date_picker = None
        action_attribute_ascending = None
        action_attribute_descending = None
        if col >= ATTRIBUTE_START_COLUMN:
            action_show_values_like = menu.addAction(_("Show values like"))
            if self.header_value_type[col] == "character" and "date" in self.header_labels[col].lower():
                action_date_picker = menu.addAction(_("Enter date"))
            action_attribute_ascending = menu.addAction(_("Ascending"))
            action_attribute_descending = menu.addAction(_("Descending"))
        action_show_all = None
        if self.rows_hidden:
            action_show_all = menu.addAction(_("Show all rows Ctrl A"))
            self.rows_hidden = False

        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action == action_modified_date_asc:
            self.load_journals("date asc")
            return
        if action == action_modified_date_desc:
            self.load_journals("date desc")
            return
        if action == action_name_asc:
            self.load_journals("name asc")
            return
        if action == action_name_desc:
            self.load_journals("name desc")
            return
        if action == action_attribute_ascending:
            attribute_name = self.header_labels[col]
            self.load_journals(f"{attribute_name}| asc")
            return
        if action == action_attribute_descending:
            attribute_name = self.header_labels[col]

            self.load_journals(f"{attribute_name}|desc")
            return
        if action == action_show_all:
            for r in range(0, self.ui.tableWidget.rowCount()):
                self.ui.tableWidget.setRowHidden(r, False)
            self.rows_hidden = False
            return
        if action == action_show_name_like:
            text_value, ok = QtWidgets.QInputDialog.getText(self, _("Text filter"), _("Show names like:"),
                                                            QtWidgets.QLineEdit.EchoMode.Normal, item_text)
            if ok and text_value != '':
                if ok and text_value != '':
                    for r in range(0, self.ui.tableWidget.rowCount()):
                        if self.ui.tableWidget.item(r, NAME_COLUMN).text().find(text_value) == -1:
                            self.ui.tableWidget.setRowHidden(r, True)
                    self.rows_hidden = True
            # To prevent text entry errors clear journal area
            self.ui.label_jname.setText(_("Journal: "))
            self.jid = None
            self.ui.textEdit.clear()
            self.ui.textEdit.hide()
            return
        if action == action_show_values_like:
            text_value, ok = QtWidgets.QInputDialog.getText(self, _("Text filter"), _("Show values like:"),
                                                            QtWidgets.QLineEdit.EchoMode.Normal, item_text)
            if ok and text_value != '':
                if ok and text_value != '':
                    for r in range(0, self.ui.tableWidget.rowCount()):
                        if self.ui.tableWidget.item(r, col).text().find(text_value) == -1:
                            self.ui.tableWidget.setRowHidden(r, True)
                    self.rows_hidden = True
            # To prevent text entry errors clear journal area
            self.ui.label_jname.setText(_("Journal: "))
            self.jid = None
            self.ui.textEdit.clear()
            self.ui.textEdit.hide()
            return
        if action == action_date_picker:
            ui = DialogMemo(self.app, "Date selector", "", "hide")
            ui.ui.textEdit.hide()
            calendar = QtWidgets.QCalendarWidget()
            ui.ui.gridLayout.addWidget(calendar, 0, 0, 1, 1)
            ok = ui.exec()
            if ok:
                selected_date = calendar.selectedDate().toString("yyyy-MM-dd")
                self.ui.tableWidget.setItem(row, col, QtWidgets.QTableWidgetItem(selected_date))
            return
        if action == action_show_this_coder:
            coder_selected = self.ui.tableWidget.item(row, OWNER_COLUMN).text()
            for r in range(0, self.ui.tableWidget.rowCount()):
                coder_name = self.ui.tableWidget.item(r, OWNER_COLUMN).text()
                if coder_selected != coder_name:
                    self.ui.tableWidget.setRowHidden(r, True)
            self.rows_hidden = True
            # To prevent text entry errors clear journal area
            self.ui.label_jname.setText(_("Journal: "))
            self.jid = None
            self.ui.textEdit.clear()
            self.ui.textEdit.hide()
            return

    def export_all_journals_as_one_file(self):
        """ Export a collation of all journals as one text file. """

        text_ = ""
        for j in self.journals:
            text_ += _("Journal: ") + j['name'] + "\n"
            text_ += j['jentry'] + "\n========\n\n"
        filename = "Collated_journals.txt"
        exp_directory = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_directory.filepath
        if filepath is None:
            return
        ''' https://stackoverflow.com/questions/39422573/python-writing-weird-unicode-to-csv
        Using a byte order mark so that other software recognises UTF-8
        '''
        with open(filepath, 'w', encoding='utf-8-sig') as outfile:
            outfile.write(text_)
        msg = _("Collated journals exported as text file to: ") + filepath
        self.parent_text_edit.append(msg)
        Message(self.app, _("Journals exported"), msg).exec()

    def view(self):
        """ View and edit journal contents in the textEdit """

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            self.jid = None
            self.ui.textEdit.setPlainText("")
            return
        self.jid = int(self.ui.tableWidget.item(row, JID_COLUMN).text())
        self.ui.textEdit.blockSignals(True)
        self.ui.textEdit.setPlainText(self.journals[row]['jentry'])
        self.ui.textEdit.blockSignals(False)
        self.qtimer.start(self.timer_msecs)

    def update_database_text(self):
        """ Journals list entry and database is updated from changes to text edit.
        The signal is switched off when a different journal is loaded.
        Called via qtimer every 2 seconds.
        """

        if self.jid is None:
            return
        if not self.text_changed_flag:
            return
        self.text_changed_flag = False
        self.journals[self.ui.tableWidget.currentRow()]['jentry'] = self.ui.textEdit.toPlainText()
        # Update database as text is edited
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        cur.execute("update journal set jentry=?, date=? where jid=?",
                    (self.journals[self.ui.tableWidget.currentRow()]['jentry'], now_date, self.jid))
        self.app.conn.commit()
        self.app.delete_backup = False
        # TODO update the visual table entry for the date

    def text_changed(self):
        """ Used in combination with timer to update database entry. """

        self.text_changed_flag = True

    def closeEvent(self, event):
        """ Save splitter dimensions. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogjournals_splitter0'] = sizes[0]
        self.app.settings['dialogjournals_splitter1'] = sizes[1]

    def create_journal(self):
        """ Create a new journal by entering text into the dialog. """

        self.jid = None
        self.ui.textEdit.setPlainText("")
        self.ui.tableWidget.clearSelection()
        reg_exp = QtCore.QRegularExpression(r"^[\ \w-]+$")
        ui = DialogAddItemName(self.app, self.journals, _('New Journal'), _('Journal name'), reg_exp)
        ui.exec()
        name = ui.get_new_name()
        if name is None:
            return
        # Update database
        journal = {'name': name, 'jentry': '', 'owner': self.app.settings['codername'],
                   'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'jid': None}
        cur = self.app.conn.cursor()
        cur.execute("insert into journal(name,jentry,owner,date) values(?,?,?,?)",
                    (journal['name'], journal['jentry'], journal['owner'], journal['date']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        jid = cur.fetchone()[0]
        journal['jid'] = jid

        sql = 'select count(name) from attribute_type where caseOrFile ="journal"'
        cur.execute(sql)
        attribute_count = cur.fetchone()[0]
        journal['attributes'] = [''] * attribute_count
        self.check_attribute_placeholders()
        self.parent_text_edit.append(_("Journal created: ") + journal['name'])
        self.journals.append(journal)
        self.fill_table()
        newest = len(self.journals) - 1
        if newest < 0:
            return
        self.ui.tableWidget.setCurrentCell(newest, 0)
        self.jid = jid
        self.ui.textEdit.setFocus()
        self.qtimer.start(self.timer_msecs)
        self.app.delete_backup = False

    def export(self):
        """ Export journal to a plain text file, filename will have .txt ending. """

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        filename = f"{self.journals[row]['name']}.txt"
        export_dlg = ExportDirectoryPathDialog(self.app, filename)
        filepath = export_dlg.filepath
        if filepath is None:
            return
        data = self.journals[row]['jentry']
        with open(filepath, 'w', encoding='utf-8') as file_:
            file_.write(data)
        msg = f'{_("Journal exported to:")} {filepath}'
        Message(self.app, _("Journal export"), msg, "information").exec()
        self.parent_text_edit.append(msg)

    def delete_journal(self):
        """ Delete journal from database and update model and widget. """

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        journal_name = self.journals[row]['name']
        ui = DialogConfirmDelete(self.app, self.journals[row]['name'])
        ok = ui.exec()
        if ok:
            cur = self.app.conn.cursor()
            cur.execute("delete from journal where name = ?", [journal_name])
            self.app.conn.commit()
            for item in self.journals:
                if item['name'] == journal_name:
                    self.journals.remove(item)
            self.fill_table()
            self.parent_text_edit.append(_("Journal deleted: ") + journal_name)
        self.check_attribute_placeholders()
        self.app.delete_backup = False

    def table_selection_changed(self):
        """ Present the journal text for the current selection. """

        row = self.ui.tableWidget.currentRow()
        self.ui.label_jname.setText(_("Journal: ") + self.journals[row]['name'])
        self.jid = int(self.ui.tableWidget.item(row, JID_COLUMN).text())
        self.ui.textEdit.show()
        self.view()

    def cell_modified(self):
        """ If the journal name has been changed in the table widget update the database
        """

        row = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        self.jid = int(self.ui.tableWidget.item(row, JID_COLUMN).text())
        if y == NAME_COLUMN:
            new_name = self.ui.tableWidget.item(row, y).text().strip()
            # check that no other journal has this name and it is not empty
            update = True
            if new_name == "":
                Message(self.app, _('Warning'), _("No name was entered"), "warning").exec()
                update = False
            for c in self.journals:
                if c['name'] == new_name:
                    Message(self.app, _('Warning'), _("Journal name in use"), "warning").exec()
                    update = False
            # Check for unusual characters in filename that would affect exporting
            valid = re.match(r'^[\ \w-]+$', new_name) is not None
            if not valid:
                Message(self.app, _('Warning - invalid characters'),
                        _("In the journal name use only: a-z, A-z 0-9 - space"), "warning").exec()
                update = False
            if update:
                # update journals list and database
                cur = self.app.conn.cursor()
                cur.execute("update journal set name=? where name=?",
                            (new_name, self.journals[row]['name']))
                self.app.conn.commit()
                self.parent_text_edit.append(
                    _("Journal name changed from: ") + f"{self.journals[row]['name']} -> {new_name}")
                self.journals[row]['name'] = new_name
                self.ui.label_jname.setText(_("Journal: ") + self.journals[row]['name'])
            else:  # Put the original text in the cell
                self.ui.tableWidget.item(row, y).setText(self.journals[row]['name'])

        # Update attribute value
        if y >= ATTRIBUTE_START_COLUMN:
            value = str(self.ui.tableWidget.item(row, y).text()).strip()
            attribute_name = self.header_labels[y]
            cur = self.app.conn.cursor()

            # Check numeric for numeric attributes, clear "" if it cannot be cast
            cur.execute("select valuetype from attribute_type where caseOrFile='journal' and name=?",
                        (attribute_name,))
            result = cur.fetchone()
            if result is None:
                return
            if result[0] == "numeric":
                try:
                    float(value)
                except ValueError:
                    self.ui.tableWidget.item(row, y).setText("")
                    value = ""
                    msg = _("This attribute is numeric")
                    Message(self.app, _("Warning"), msg, "warning").exec()

            cur.execute("update attribute set value=? where id=? and name=? and attr_type='journal'",
                        (value, self.journals[row]['jid'], attribute_name))
            self.app.conn.commit()

            # Update self.journals[attributes]
            # Add list of attribute values to journals, order matches header columns
            sql = "select ifnull(value, '') from attribute where attr_type='journal' and attribute.name=? and id=?"
            self.journals[row]['attributes'] = []
            for att_name in self.attribute_labels_ordered:
                cur.execute(sql, [att_name, self.journals[row]['jid']])
                res = cur.fetchone()
                if res:
                    self.journals[row]['attributes'].append(res[0])

        self.app.delete_backup = False
        self.ui.tableWidget.resizeColumnsToContents()

    # Functions to search though the journal(s) text
    def search_for_text(self):
        """ On text changed in lineEdit_search, find indices of matching text.
        Only where text is three or more characters long.
        Resets current search_index.
        If all files is checked then searches for all matching text across all text files
        and displays the file text and current position to user.
        NOT IMPLEMENTED If case-sensitive is checked then text searched is matched for case sensitivity.
        """

        if self.jid is None and not (self.ui.checkBox_search_all_journals.isChecked()):
            return
        if not self.search_indices:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(search_term) < 3:
            return
        pattern = None
        flags = 0
        try:
            pattern = re.compile(search_term, flags)
        except re.error:
            logger.warning('Bad escape')
        if pattern is None:
            return
        self.search_indices = []
        if self.ui.checkBox_search_all_journals.isChecked():
            """ Search for this text across all journals. """
            for jdata in self.app.get_journal_texts():
                try:
                    text_ = jdata['jentry']
                    for match in pattern.finditer(text_):
                        self.search_indices.append((jdata, match.start(), len(match.group(0))))
                except Exception as e:
                    print(e)
                    logger.exception('Failed searching text %s for %s', jdata['name'], search_term)
        else:  # Current journal only
            row = self.ui.tableWidget.currentRow()
            try:
                for match in pattern.finditer(self.journals[row]['jentry']):
                    # Get result as first dictionary item
                    j_name = self.app.get_journal_texts([self.jid, ])[0]
                    self.search_indices.append((j_name, match.start(), len(match.group(0))))
            except Exception as e:
                print(e)
                logger.exception('Failed searching current journal for %s', search_term)
        if len(self.search_indices) > 0:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        if not self.search_indices:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        cursor = self.ui.textEdit.textCursor()
        prev_result = self.search_indices[self.search_index]
        # prev_result is a tuple containing a dictionary of
        # {name, jid, jentry, owner, date} and char position and search string length
        if self.jid is None or self.jid != prev_result[0]['jid']:
            self.jid = prev_result[0]['jid']
            for row in range(0, self.ui.tableWidget.rowCount()):
                if int(self.ui.tableWidget.item(row, JID_COLUMN).text()) == self.jid:
                    self.ui.tableWidget.setCurrentCell(row, NAME_COLUMN)
                    # This will also load the jentry into the textEdit
                    break
        cursor.setPosition(prev_result[1])
        cursor.setPosition(cursor.position() + prev_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(f"{self.search_index + 1} / {len(self.search_indices)}")

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        if not self.search_indices:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cursor = self.ui.textEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        # next_result is a tuple containing a dictionary of
        # {name, jid, jentry, owner, date} and char position and search string length
        if self.jid is None or self.jid != next_result[0]['jid']:
            self.jid = next_result[0]['jid']
            for row in range(0, self.ui.tableWidget.rowCount()):
                if int(self.ui.tableWidget.item(row, JID_COLUMN).text()) == self.jid:
                    self.ui.tableWidget.setCurrentCell(row, NAME_COLUMN)
                    # This will also load the jentry into the textEdit
                    break
        cursor.setPosition(next_result[1])
        cursor.setPosition(cursor.position() + next_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(f"{self.search_index + 1} / {len(self.search_indices)}")
