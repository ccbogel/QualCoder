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
"""

import os
from rispy import TAG_KEY_MAPPING
import logging
from operator import itemgetter
import qtawesome as qta
import re

from PyQt6 import QtWidgets, QtCore, QtGui

from .GUI.ui_reference_editor import Ui_DialogReferenceEditor
from .GUI.ui_manage_references import Ui_Dialog_manage_references
from .confirm_delete import DialogConfirmDelete
from .information import DialogInformation
from .helpers import Message
from .ris import Ris, RisImport
from .view_av import DialogViewAV
from .view_image import DialogViewImage

# If VLC not installed, it will not crash
vlc = None
try:
    import vlc
except Exception as e:
    print(e)

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

REF_ID = 0
REF_DETAIL = 1
REF_TYPE = 2
REF_YEAR = 3
REF_AUTHORS = 4
REF_JOURNAL = 5
REF_VOLUME = 6
REF_ISSUE = 7
REF_KEYWORDS = 8


class DialogReferenceManager(QtWidgets.QDialog):
    """ Dialog to manipulate files for a case.
    Add files to case, add all text or text portions from a text file.
    Remove file from a case. View file.
    """

    app = None
    parent_text_edit = None
    files = []
    refs = []

    def __init__(self, app_, parent_text_edit):

        self.app = app_
        self.parent_text_edit = parent_text_edit
        self.files = []
        self.av_dialog_open = None
        self.refs = []
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_references()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        font2 = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.tableWidget_files.setStyleSheet(font2)
        self.ui.tableWidget_files.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui.tableWidget_files.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget_files.customContextMenuRequested.connect(self.table_files_menu)
        self.ui.tableWidget_files.horizontalHeader().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget_files.horizontalHeader().customContextMenuRequested.connect(self.table_files_header_menu)
        self.ui.tableWidget_refs.setStyleSheet(font2)
        self.ui.tableWidget_refs.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui.tableWidget_refs.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.ui.tableWidget_refs.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget_refs.customContextMenuRequested.connect(self.table_refs_menu)
        self.ui.tableWidget_refs.horizontalHeader().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget_refs.horizontalHeader().customContextMenuRequested.connect(self.table_refs_header_menu)
        self.ui.pushButton_import.setIcon(qta.icon('mdi.file-import-outline'))
        self.ui.pushButton_import.pressed.connect(self.import_references)
        self.ui.pushButton_link.setIcon(QtGui.QIcon(qta.icon('mdi6.link')))
        self.ui.pushButton_link.pressed.connect(self.link_reference_to_files)
        self.ui.pushButton_unlink_files.setIcon(qta.icon('mdi6.undo'))
        self.ui.pushButton_unlink_files.pressed.connect(self.unlink_files)
        self.ui.pushButton_edit_ref.setIcon(qta.icon('mdi6.pencil-outline'))
        self.ui.pushButton_edit_ref.pressed.connect(self.edit_reference)
        self.ui.pushButton_delete_ref.setIcon(qta.icon('mdi6.delete-outline'))
        self.ui.pushButton_delete_ref.pressed.connect(self.delete_reference)
        self.ui.pushButton_delete_unused_refs.setIcon(qta.icon('mdi6.file-document-remove-outline'))
        self.ui.pushButton_delete_unused_refs.setEnabled(False)
        self.ui.pushButton_delete_unused_refs.hide()
        self.ui.pushButton_auto_link.setIcon(qta.icon('mdi6.magic-staff'))
        self.ui.pushButton_auto_link.pressed.connect(self.auto_link_files_to_references)

        self.get_data()
        self.ui.tableWidget_refs.setTabKeyNavigation(False)
        self.ui.tableWidget_refs.installEventFilter(self)
        self.ui.tableWidget_files.setTabKeyNavigation(False)
        self.ui.tableWidget_files.installEventFilter(self)
        self.ui.checkBox_hide_files.toggled.connect(self.fill_table_files)
        self.ui.checkBox_hide_refs.toggled.connect(self.fill_table_refs)
        self.ui.splitter.setSizes([500, 200])
        self.table_files_rows_hidden = False
        self.table_refs_rows_hidden = False

    def get_data(self):
        """ Get data for files and references. """

        cur = self.app.conn.cursor()
        cur.execute("select id, name, risid, memo, date, mediapath, av_text_id, fulltext from source order by lower(name)")
        result = cur.fetchall()
        self.files = []
        keys = 'id', 'name', 'risid', 'memo', 'date', 'mediapath', 'av_text_id', 'fulltext'
        for row in result:
            self.files.append(dict(zip(keys, row)))
        # This is used for auto-linking files to references
        for file_ in self.files:
            temp_name = file_['name'].lower()
            if len(temp_name) > 4 and temp_name[-4:].lower() in (".txt", ".png", ".jpg", ".pdf", ".mp3", ".mp4",
                                                                 ".odt", ".htm", ".wav", ".m4a", ".mov", ".ogg",
                                                                 ".wmv"):
                temp_name = temp_name[:-4]
            elif len(temp_name) > 5 and temp_name[-5:].lower() in (".html", ".docx", ".jpeg"):
                temp_name = temp_name[:-5]
            split_name = re.split(';|,| |:|_|-', temp_name)
            split_name = list(filter(''.__ne__, split_name))
            file_['split_name'] = split_name
        r = Ris(self.app)
        r.get_references()
        self.refs = r.refs
        sorted_list = sorted(self.refs, key=lambda x: x['details'])
        self.refs = sorted_list
        # This is used for auto-linking files to references
        for ref in self.refs:
            temp_title = ref['TI'].lower()
            split_title = re.split(';|,| |:|_|-', temp_title)
            split_title = list(filter(''.__ne__, split_title))
            ref['split_title'] = split_title
        self.fill_table_refs()
        self.fill_table_files()  # Do after refs filled, as uses ref title in files tooltips, if linked

    def fill_table_files(self):
        """ Fill widget with file details. """

        rows = self.ui.tableWidget_files.rowCount()
        for c in range(0, rows):
            self.ui.tableWidget_files.removeRow(0)
        header_labels = ["id", "File name", "Ref Id"]
        self.ui.tableWidget_files.setColumnCount(len(header_labels))
        self.ui.tableWidget_files.setHorizontalHeaderLabels(header_labels)
        for row, file_ in enumerate(self.files):
            self.ui.tableWidget_files.insertRow(row)
            item = QtWidgets.QTableWidgetItem(str(file_['id']))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_files.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(file_['name'])
            memo = file_['memo']
            if not memo:
                memo = ""
            item.setToolTip(memo)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_files.setItem(row, 1, item)
            risid = ""
            tooltip = ""
            if file_['risid'] is not None:
                risid = file_['risid']
                linked_ref = next((ref_item for ref_item in self.refs if ref_item['risid'] == risid), None)
                if linked_ref:
                    tooltip = f"{linked_ref['TI']}\n{linked_ref['PY']} {linked_ref['TY']}"
                if self.ui.checkBox_hide_files.isChecked():
                    self.ui.tableWidget_files.setRowHidden(row, True)
                else:
                    self.ui.tableWidget_files.setRowHidden(row, False)
            item = QtWidgets.QTableWidgetItem(str(risid))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            item.setToolTip(tooltip)
            self.ui.tableWidget_files.setItem(row, 2, item)
        self.ui.tableWidget_files.hideColumn(0)
        if self.app.settings['showids']:
            self.ui.tableWidget_files.showColumn(0)
        self.ui.tableWidget_files.resizeColumnsToContents()
        if self.ui.tableWidget_files.columnWidth(1) > 600:
            self.ui.tableWidget_files.setColumnWidth(1, 600)
        self.ui.tableWidget_files.resizeRowsToContents()

    def table_files_header_menu(self, position):
        """ Sort ascending or descending. Open file to view. """

        if not self.files:
            return
        # index_at = self.ui.tableWidget_refs.indexAt(position)
        # col = int(index_at.column())
        menu = QtWidgets.QMenu(self)
        action_files_asc = menu.addAction(_("Ascending"))
        action_files_desc = menu.addAction(_("Descending"))
        action = menu.exec(self.ui.tableWidget_files.mapToGlobal(position))
        if action == action_files_asc:
            sorted_list = sorted(self.files, key=lambda x: x['name'])
            self.files = sorted_list
            self.fill_table_files()
            return
        if action == action_files_desc:
            sorted_list = sorted(self.files, key=lambda x: x['name'], reverse=True)
            self.files = sorted_list
            self.fill_table_files()
            return

    def table_files_menu(self, position):
        """ Context menu for showing specific rows. """

        # row = self.ui.tableWidget_files.currentRow()
        menu = QtWidgets.QMenu()
        action_show_value_like = menu.addAction(_("Show value like"))
        action_file_view = menu.addAction(_("View file"))
        action_files_asc = menu.addAction(_("Ascending"))
        action_files_desc = menu.addAction(_("Descending"))
        action_show_all_rows = None
        if self.table_files_rows_hidden:
            action_show_all_rows = menu.addAction(_("Show all rows"))
        action = menu.exec(self.ui.tableWidget_files.mapToGlobal(position))
        if action == action_show_all_rows:
            for r in range(0, self.ui.tableWidget_files.rowCount()):
                self.ui.tableWidget_files.setRowHidden(r, False)
            self.table_files_rows_hidden = False
            return
        if action == action_show_value_like:
            text_value, ok = QtWidgets.QInputDialog.getText(self, _("Text filter"), _("Show value like:"),
                                                            QtWidgets.QLineEdit.EchoMode.Normal)
            if not ok or text_value == '':
                return
            for r in range(0, self.ui.tableWidget_files.rowCount()):
                if self.ui.tableWidget_files.item(r, 1).text().find(text_value) == -1:
                    self.ui.tableWidget_files.setRowHidden(r, True)
            self.table_files_rows_hidden = True
            return
        if action == action_files_desc:
            sorted_list = sorted(self.files, key=lambda x: x['name'], reverse=True)
            self.files = sorted_list
            self.fill_table_files()
            return
        if action == action_files_asc:
            sorted_list = sorted(self.files, key=lambda x: x['name'])
            self.files = sorted_list
            self.fill_table_files()
            return
        if action == action_file_view:
            self.view()

    def view(self):
        """ View a text, image, audio or video media. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        row = self.ui.tableWidget_files.currentRow()
        if self.files[row]['mediapath'] is not None and 'docs:' != self.files[row]['mediapath'][0:5]:
            if len(self.files[row]['mediapath']) > 6 and self.files[row]['mediapath'][:7] in ("/images", "images:"):
                self.view_image(row)
                return
            if len(self.files[row]['mediapath']) > 5 and self.files[row]['mediapath'][:6] in ("/video", "video:"):
                self.view_av(row)
                return
            if len(self.files[row]['mediapath']) > 5 and self.files[row]['mediapath'][:6] in ("/audio", "audio:"):
                self.view_av(row)
                return
        ui = DialogInformation(self.app, self.files[row]['name'], self.files[row]['fulltext'])
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def view_av(self, row):
        """ View an audio or video file. Edit the memo. Edit the transcript file.
        Added try block in case VLC bindings do not work.
        Uses a non-modal dialog.

        param:
            x  :  row number Integer
        """

        if not vlc:
            msg = _("VLC not installed cannot play audio or video.")
            Message(self.app, _('View AV error'), msg, "warning").exec()
            return
        # Check media exists
        abs_path = ""
        if self.files[row]['mediapath'][0:6] in ('/audio', '/video'):
            abs_path = self.app.project_path + self.files[row]['mediapath']
        if self.files[row]['mediapath'][0:6] in ('audio:', 'video:'):
            abs_path = self.files[row]['mediapath'][6:]
        if not os.path.exists(abs_path):
            self.parent_text_edit.append(_("Bad link or non-existent file ") + abs_path)
            return
        try:
            ui = DialogViewAV(self.app, self.files[row])
            ui.ui.textEdit.setReadOnly(True)
            # ui.exec()  # this dialog does not display well on Windows 10 so trying .show()
            # The vlc window becomes unmovable and not resizable
            self.av_dialog_open = ui
            ui.show()
        except Exception as err:
            logger.warning(str(err))
            Message(self.app, _('view AV error'), str(err), "warning").exec()
            self.av_dialog_open = None
            return

    def view_image(self, row):
        """ View an image file and edit the image memo.

        param:
            x  :  row number Integer
        """

        # Check image exists
        abs_path = ""
        if self.files[row]['mediapath'][:7] == "images:":
            abs_path = self.files[row]['mediapath'][7:]
        else:
            abs_path = self.app.project_path + self.files[row]['mediapath']
        if not os.path.exists(abs_path):
            self.parent_text_edit.append(_("Bad link or non-existent file ") + abs_path)
            return
        ui = DialogViewImage(self.app, self.files[row])
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def auto_link_files_to_references(self):
        """ Auto link references to file names.
         Uses words (as lowercase) from reference title and words (as lowercase) from file name.
         Looks at each unlinked file. Then matches the words in the title to the words in the file name.
         Highest match links the risid to the file. Minimum numer of words match threshold of 0.7
         """

        files_linked_count = 0
        files_unlinked = []
        for file_ in self.files:
            if not file_['risid']:
                files_unlinked.append(file_)
        for file_ in files_unlinked:
            # print(file_['split_name'])
            match_stats = []
            for ref in self.refs:
                ref_words_set = set(ref['split_title'])
                proportion_matching = len(ref_words_set.intersection(file_['split_name'])) / len(ref_words_set)
                if proportion_matching > 0.7:
                    match_stats.append([ref['risid'], proportion_matching, ref['split_title']])
                if int(proportion_matching) == 1:
                    break
            match_stats = sorted(match_stats, key=itemgetter(1), reverse=True)
            if not match_stats:
                continue
            best_match = match_stats[0]
            # print(best_match)
            ris_id = best_match[0]
            fid = file_['id']
            self.link_reference_to_files(ris_id, fid)
            files_linked_count += 1
        msg = _("Matches: ") + f"          {files_linked_count} / {len(files_unlinked)}          "
        Message(self.app, _("Files linked to references"), msg).exec()

    def fill_table_refs(self):
        """ Fill widget with ref details. """

        rows = self.ui.tableWidget_refs.rowCount()
        for c in range(0, rows):
            self.ui.tableWidget_refs.removeRow(0)
        header_labels = ["Ref id", _("Reference"), _("Type"), _("Year"), _("Authors"), _("Journal or Publication Title"),
                         _("Volume"), _("Issue"), _("Keywords")]
        self.ui.tableWidget_refs.setColumnCount(len(header_labels))
        self.ui.tableWidget_refs.setHorizontalHeaderLabels(header_labels)
        for row, ref in enumerate(self.refs):
            self.ui.tableWidget_refs.insertRow(row)
            item = QtWidgets.QTableWidgetItem(str(ref['risid']))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_ID, item)
            item = QtWidgets.QTableWidgetItem(ref['vancouver'])
            item.setToolTip(ref['details'])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_DETAIL, item)
            type_of_ref = ""
            if 'TY' in ref:
                type_of_ref = ref['TY']
            item = QtWidgets.QTableWidgetItem(type_of_ref)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_TYPE, item)
            year_of_ref = ""
            if 'PY' in ref:
                year_of_ref = ''.join(ch for ch in ref['PY'] if ch.isdigit())  # Digits only
            item = QtWidgets.QTableWidgetItem(year_of_ref)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_YEAR, item)
            authors = ""
            if 'authors' in ref:
                authors = ref['authors']
            item = QtWidgets.QTableWidgetItem(authors)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_AUTHORS, item)
            journal_or_secondary = ""
            if 'journal_or_secondary' in ref:
                journal_or_secondary = ref['journal_or_secondary']
            item = QtWidgets.QTableWidgetItem(journal_or_secondary)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_JOURNAL, item)
            volume = ""
            if 'volume' in ref:
                volume = ref['volume']
            item = QtWidgets.QTableWidgetItem(volume)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_VOLUME, item)
            issue = ""
            if 'issue' in ref:
                issue = ref['issue']
            item = QtWidgets.QTableWidgetItem(issue)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_ISSUE, item)
            keywords = ""
            if 'KW' in ref:
                keywords = ref['KW']
            item = QtWidgets.QTableWidgetItem(keywords)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget_refs.setItem(row, REF_KEYWORDS, item)

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
            self.ui.tableWidget_refs.showColumn(REF_ID)
        self.ui.tableWidget_refs.resizeColumnsToContents()
        if self.ui.tableWidget_refs.columnWidth(REF_DETAIL) > 500:
            self.ui.tableWidget_refs.setColumnWidth(REF_DETAIL, 500)
        if self.ui.tableWidget_refs.columnWidth(REF_AUTHORS) > 400:
            self.ui.tableWidget_refs.setColumnWidth(REF_AUTHORS, 400)
        if self.ui.tableWidget_refs.columnWidth(REF_JOURNAL) > 350:
            self.ui.tableWidget_refs.setColumnWidth(REF_JOURNAL, 350)
        self.ui.tableWidget_refs.resizeRowsToContents()

    def table_refs_header_menu(self, position):
        """ Sort ascending or descending. """

        if not self.refs:
            return
        index_at = self.ui.tableWidget_refs.indexAt(position)
        col = int(index_at.column())
        menu = QtWidgets.QMenu(self)
        action_id_asc = None
        action_id_desc = None
        if col == REF_ID:
            action_id_asc = menu.addAction(_("Ascending"))
            action_id_desc = menu.addAction(_("Descending"))
        action_detail_asc = None
        action_detail_desc = None
        if col == REF_DETAIL:
            action_detail_asc = menu.addAction(_("Ascending"))
            action_detail_desc = menu.addAction(_("Descending"))
        action_type_ascending = None
        action_type_descending = None
        if col == REF_TYPE:
            action_type_ascending = menu.addAction(_("Ascending"))
            action_type_descending = menu.addAction(_("Descending"))
        action_year_ascending = None
        action_year_descending = None
        if col == REF_YEAR:
            action_year_ascending = menu.addAction(_("Ascending"))
            action_year_descending = menu.addAction(_("Descending"))
        action_authors_ascending = None
        action_authors_descending = None
        if col == REF_AUTHORS:
            action_authors_ascending = menu.addAction(_("Ascending"))
            action_authors_descending = menu.addAction(_("Descending"))
        action_journal_ascending = None
        action_journal_descending = None
        if col == REF_JOURNAL:
            action_journal_ascending = menu.addAction(_("Ascending"))
            action_journal_descending = menu.addAction(_("Descending"))
        action_volume_ascending = None
        action_volume_descending = None
        if col == REF_VOLUME:
            action_volume_ascending = menu.addAction(_("Ascending"))
            action_volume_descending = menu.addAction(_("Descending"))
        action_keywords_ascending = None
        action_keywords_descending = None
        if col == REF_KEYWORDS:
            action_keywords_ascending = menu.addAction(_("Ascending"))
            action_keywords_descending = menu.addAction(_("Descending"))

        action = menu.exec(self.ui.tableWidget_refs.mapToGlobal(position))
        if action == action_id_asc:
            sorted_list = sorted(self.refs, key=lambda x: x['risid'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_id_desc:
            sorted_list = sorted(self.refs, key=lambda x: x['risid'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_detail_asc:
            sorted_list = sorted(self.refs, key=lambda x: x['details'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_detail_desc:
            sorted_list = sorted(self.refs, key=lambda x: x['details'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_type_ascending:
            sorted_list = sorted(self.refs, key=lambda x: x['TY'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_type_descending:
            sorted_list = sorted(self.refs, key=lambda x: x['TY'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_year_ascending:
            sorted_list = sorted(self.refs, key=lambda x: x['PY'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_year_descending:
            sorted_list = sorted(self.refs, key=lambda x: x['PY'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_authors_ascending:
            sorted_list = sorted(self.refs, key=lambda x: x['authors'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_authors_descending:
            sorted_list = sorted(self.refs, key=lambda x: x['authors'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_journal_ascending:
            sorted_list = sorted(self.refs, key=lambda x: x['journal_or_secondary'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_journal_descending:
            sorted_list = sorted(self.refs, key=lambda x: x['journal_or_secondary'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_volume_ascending:
            sorted_list = sorted(self.refs, key=lambda x: x['volume'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_volume_descending:
            sorted_list = sorted(self.refs, key=lambda x: x['volume'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_keywords_ascending:
            sorted_list = sorted(self.refs, key=lambda x: x['keywords'])
            self.refs = sorted_list
            self.fill_table_refs()
            return
        if action == action_keywords_descending:
            sorted_list = sorted(self.refs, key=lambda x: x['keywords'], reverse=True)
            self.refs = sorted_list
            self.fill_table_refs()
            return

    def table_refs_menu(self, position):
        """ Context menu for displaying table rows in differing order,
        copying a reference style to clipboard, edit reference.
        Show specific rows.
        """

        row = self.ui.tableWidget_refs.currentRow()
        col = self.ui.tableWidget_refs.currentColumn()
        item = self.ui.tableWidget_refs.item(row, col)
        item_text = ""
        if item is not None:
            item_text = item.text()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_show_this_value = menu.addAction(_("Show this value"))
        action_show_value_like = menu.addAction(_("Show value like"))
        action_show_all_rows = None
        if self.table_refs_rows_hidden:
            action_show_all_rows = menu.addAction(_("Show all rows"))
        action_copy_to_clipboard = menu.addAction(_("Copy to clipboard"))
        action_copy_apa_to_clipboard = menu.addAction(_("Copy to clipboard.  APA style"))
        action_edit_reference = menu.addAction(_("Edit reference"))
        action = menu.exec(self.ui.tableWidget_refs.mapToGlobal(position))
        if action == action_show_all_rows:
            for r in range(0, self.ui.tableWidget_refs.rowCount()):
                self.ui.tableWidget_refs.setRowHidden(r, False)
            self.table_refs_rows_hidden = False
            return
        if action == action_show_this_value:
            for r in range(0, self.ui.tableWidget_refs.rowCount()):
                if self.ui.tableWidget_refs.item(r, col).text() != item_text:
                    self.ui.tableWidget_refs.setRowHidden(r, True)
            self.table_refs_rows_hidden = True
            return
        if action == action_show_value_like:
            text_value, ok = QtWidgets.QInputDialog.getText(self, _("Text filter"), _("Show value like:"),
                                                            QtWidgets.QLineEdit.EchoMode.Normal)
            if not ok or text_value == '':
                return
            for r in range(0, self.ui.tableWidget_refs.rowCount()):
                if self.ui.tableWidget_refs.item(r, col).text().find(text_value) == -1:
                    self.ui.tableWidget_refs.setRowHidden(r, True)
            self.table_refs_rows_hidden = True
            return
        if action == action_copy_to_clipboard:
            reference_text = self.ui.tableWidget_refs.item(row, 1).text()
            cb = QtWidgets.QApplication.clipboard()
            cb.setText(reference_text.replace("\n", " "))
            return
        if action == action_copy_apa_to_clipboard:
            ref_id = self.ui.tableWidget_refs.item(row, REF_ID).text()
            for ref in self.refs:
                if int(ref_id) == ref['risid']:
                    cb = QtWidgets.QApplication.clipboard()
                    cb.setText(ref['apa'].replace("\n", " "))
                    return
        if action == action_edit_reference:
            self.edit_reference()

    def import_references(self):
        """ Import RIS formatted references from .ris or .txt files """

        RisImport(self.app, self.parent_text_edit)
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

    def eventFilter(self, object_, event):
        """ L Link files to reference.
        U to unlink selected files
        Note. Fires multiple times very quickly.
        """

        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            # mod = event.modifiers()
            if key == QtCore.Qt.Key.Key_L and (self.ui.tableWidget_refs.hasFocus() or self.ui.tableWidget_files.hasFocus()):
                self.link_reference_to_files()
                return True
            if key == QtCore.Qt.Key.Key_U and (self.ui.tableWidget_refs.hasFocus() or self.ui.tableWidget_files.hasFocus()):
                self.unlink_files()
                return True
        return False

    def unlink_files(self, fid=None):
        """ Remove linked reference from selected files.
        Called by:
            pushButton_unlink: Uses selected rows in files table. Does not use parameters.
            Method: edit_reference. Uses parameter.

        :param: fid Integer source table id, or None
        """

        # Get selected file id from parameter or selected table_files rows
        fid_list = []
        if fid:
            fid_list.append(fid)
        else:
            # Use selected table_file rows
            file_row_model_index = self.ui.tableWidget_files.selectionModel().selectedRows()
            if not file_row_model_index:
                return
            for i in file_row_model_index:
                fid_list.append(i.data())
        if not fid_list:
            return

        cur = self.app.conn.cursor()
        for fid in fid_list:
            cur.execute("update source set risid=null where id=?", [fid])
            self.app.conn.commit()
            # Clear Ref attributes
            attributes = ["Ref_Authors", "Ref_Title", "Ref_Type", "Ref_Year", "Ref_Journal"]
            sql = "update attribute set value='' where id=? and name=?"
            for attribute in attributes:
                cur.execute(sql, [fid, attribute])
                self.app.conn.commit()
        self.get_data()

    def link_reference_to_files(self, ris_id=None, fid=None):
        """ Link the selected files to the selected reference.

        Called by:
            pushButton_link: Uses selected rows in references and files tables. Does not use parameters.
            Method: auto_link_files_to_references. Uses parameters.

        :param: ris_id Integer reference id , or None
        :param: fid Integer source table id, or None
        """

        # Get reference id from first selected row, or via parameter ris_id
        if not ris_id:
            ref_row_model_index = self.ui.tableWidget_refs.selectionModel().selectedRows()
            if not ref_row_model_index:
                return
            # Only get the first reference selected index. Column 0 data.
            ris_id = int(ref_row_model_index[0].data())
        ref = None
        for r in self.refs:
            if r['risid'] == ris_id:
                ref = r
                break
        # Get selected file id from parameter or selected table_files rows
        fid_list = []
        if fid:
            fid_list.append(fid)
        else:
            # Use selected table_file rows
            file_row_model_index = self.ui.tableWidget_files.selectionModel().selectedRows()
            if not file_row_model_index:
                return
            for i in file_row_model_index:
                fid_list.append(i.data())

        attr_values = {"Ref_Authors": "", "Ref_Title": "", "Ref_Type": "", "Ref_Year": "", "Ref_Journal": ""}
        # Get list of authors
        if 'AU' in ref:
            attr_values['Ref_Authors'] = ref['AU']
        if 'A1' in ref:
            attr_values['Ref_Authors'] += " " + ref['A1']
        if 'A2' in ref:
            attr_values['Ref_Authors'] += " " + ref['A2']
        if 'A3' in ref:
            attr_values['Ref_Authors'] += " " + ref['A3']
        if 'A4' in ref:
            attr_values['Ref_Authors'] += " " + ref['A4']
        # Get reference type, e.g. Journal, book
        if 'TY' in ref:
            attr_values['Ref_Type'] = ref['TY']
        # Get the first title based on this order from several tags
        for tag in ("TI", "T1", "ST", "TT"):
            try:
                attr_values['Ref_Title'] = ref[tag]
                break
            except KeyError:
                pass
        # Get reference year from examining several tags
        if 'PY' in ref:
            attr_values['Ref_Year'] = ref['PY']
        if attr_values['Ref_Year'] == "" and 'Y1' in ref:
            attr_values['Ref_Year'] = ref['Y1']
        attr_values['Ref_Journal'] = ref['journal_vol_issue']

        cur = self.app.conn.cursor()
        for fid in fid_list:  # file_row_model_index:
            cur.execute("update source set risid=? where id=?", [ris_id, fid])
            self.app.conn.commit()
            sql = "update attribute set value=? where id=? and name=?"
            for attribute in attr_values:
                cur.execute(sql, [attr_values[attribute], fid, attribute])
                self.app.conn.commit()
        self.get_data()

    def edit_reference(self):
        """ Edit selected reference.
         Also, update source attributes for this reference. """

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
                # print(tk, TAG_KEY_MAPPING[tk])
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
        cur = self.app.conn.cursor()
        ref_edited = False
        for row, key in enumerate(short_dict):
            if ui_re.tableWidget.item(row, 1).text() != short_dict[key]:
                cur.execute("update ris set value=? where risid=? and tag=?",
                            [ui_re.tableWidget.item(row, 1).text(), ris_id, key])
                self.app.conn.commit()
                ref_edited = True
        # Update Reference attributes
        for file_ in self.files:
            if file_['risid'] == ris_id:
                self.unlink_files(file_['id'])
                self.link_reference_to_files(ris_id, file_['id'])
        if ref_edited:
            self.parent_text_edit.append(_("Reference edited."))
        self.get_data()
        self.fill_table_refs()

    def delete_reference(self):
        """ Delete the selected reference.
        Remove reference risid from source tavble and remove source attribute values.
        """

        ref_row_obj = self.ui.tableWidget_refs.selectionModel().selectedRows()
        if not ref_row_obj:
            return
        # Only use first reference index row. Column 0 data
        ris_id = int(ref_row_obj[0].data())
        note = _("Delete this reference.") + f" Ref id: {ris_id}\n"
        for r in self.refs:
            if r['risid'] == ris_id:
                note += r['vancouver']
        ui = DialogConfirmDelete(self.app, note)
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("select id from source where risid=?", [ris_id])
        source_ids = cur.fetchall()
        cur.execute("update source set risid=null where risid=?", [ris_id])
        cur.execute("delete from ris where risid=?", [ris_id])
        self.app.conn.commit()
        # Clear Refeence attributes
        attributes = ["Ref_Authors", "Ref_Title", "Ref_Type", "Ref_Year", "Ref_Journal"]
        sql = "update attribute set value='' where id=? and name=?"
        for source in source_ids:
            for attribute in attributes:
                cur.execute(sql, [source[0], attribute])
                self.app.conn.commit()
        self.get_data()
        self.fill_table_refs()
        self.fill_table_files()
        self.parent_text_edit.append(_("Reference deleted."))

