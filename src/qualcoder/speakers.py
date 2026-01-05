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

import logging
import re
import datetime
from typing import Any, Dict, List, Tuple, Optional
from PyQt6 import QtCore, QtWidgets
import webbrowser
from random import randint
import sqlite3

from .GUI.ui_dialog_speakers import Ui_Dialog_speakers
from .color_selector import colors
from .helpers import Message

logger = logging.getLogger(__name__)
max_name_len: int = 63

class DialogSpeakers(QtWidgets.QDialog):
    """Extracts speaker names from a transcript of an interview or a focus group, lets the user select
    which to keep, and creates codes for each speaker in the "Speakers" category.

    Turn detection:
    - A new turn starts when a (non-empty) line begins with a speaker name followed by ":" where the ":"
    occurs within the first `max_name_len` characters (after optional leading whitespace).
    - The speaker name is everything up to ":" and is trimmed (whitespace-tolerant); case is preserved.

    Multi-line support:
    - Lines following a speaker line belong to the same speaker until:
        (a) the next valid speaker line starts, or
        (b) a blank line occurs (blank lines act as separators and are NOT coded).    
    
    Parameters: 
    fid (int): Id of the document in the database
    filename (str): name of the document
    """

    def __init__(self, app, fid, filename):
        self.app = app
        self.fid = fid
        self.filename = filename
        self.speakers_category_name = '📌 ' + _('Speakers')
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_speakers()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowTitle(f'{self.windowTitle()} - {filename}') 
        headers = [_("Name"), _("code as"), _("Count"), _("Example")]
        self.ui.tableWidget.setColumnCount(len(headers))
        self.ui.tableWidget.setHorizontalHeaderLabels(headers)
        self.codings: List[Dict[str, Any]] = []
        self.speaker_summary: List[Dict[str, Any]] = []
        self.collect_names()
        self.fill_table()
        self.ui.tableWidget.itemChanged.connect(self.on_item_changed)
        self.ui.buttonBox.accepted.connect(self.ok)
        # self.ui.buttonBox.rejected.connect(self.cancel) 
        self.ui.buttonBox.helpRequested.connect(self.help)

    def collect_names(self):
        """
        Build a list (self.codings) for each speaker turn, including multi-line turns.
        ALso creates a summary in self.speaker_summary to be shown in the QTableWidget.
        """

        transcript = self.app.get_text_fulltext(self.fid)
        codername = self.app.settings['codername']
        self.codings = []
        name_counts: Dict[str, int] = {}
        name_example: Dict[str, str] = {}

        # Regexes for supported speaker markers ("name:", "[name]", "{name}").
        speaker_res = [
            re.compile(r"^\s*(.{1," + str(max_name_len) + r"}?)\s*:\s*", flags=re.UNICODE),
            re.compile(r"^\s*\[([^\]\r\n]{1," + str(max_name_len) + r"})\]\s*", flags=re.UNICODE),
            re.compile(r"^\s*\{([^}\r\n]{1," + str(max_name_len) + r"})\}\s*", flags=re.UNICODE),
        ]

        # State for the currently open speaker turn
        current_name: Optional[str] = None
        current_start: Optional[int] = None  # pos0
        current_end: Optional[int] = None    # pos1 (exclusive), updated as we consume lines
        current_content_start: Optional[int] = None  # start of actual utterance (after marker)

        def finalize_current_turn():
            """Store the active turn and reset the state."""

            nonlocal current_name, current_start, current_end, current_content_start
            if current_name is None or current_start is None or current_end is None:
                return

            seltext = transcript[current_start:current_end]
            self.codings.append(
                {
                    "name": current_name,
                    "fid": self.fid,
                    "seltext": seltext,
                    "pos0": current_start,
                    "pos1": current_end,
                    "owner": codername,
                    "memo": "",
                    "date": datetime.datetime.now()
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            name_counts[current_name] = name_counts.get(current_name, 0) + 1
            if name_example.get(current_name, "") == "":
                content_start = current_content_start or current_start
                example_text = transcript[content_start:current_end].strip()
                name_example[current_name] = example_text

            current_name = None
            current_start = None
            current_end = None
            current_content_start = None

        # Iterate over the transcript while keeping absolute positions.
        offset = 0
        for line in transcript.splitlines(keepends=True):
            line_start = offset
            offset += len(line)

            # Determine end-of-line length to compute "content end" excluding EOL characters.
            if line.endswith("\r\n"):
                eol_len = 2
            elif line.endswith("\n") or line.endswith("\r"):
                eol_len = 1
            else:
                eol_len = 0

            line_wo_eol = line[:-eol_len] if eol_len else line
            line_is_blank = (line_wo_eol.strip() == "")

            # If we hit a blank line, close any open turn and reset (blank lines are separators, not coded).
            if line_is_blank:
                finalize_current_turn()
                continue

            # Check whether this non-empty line starts a new speaker turn
            m = None
            for regex in speaker_res:
                m = regex.match(line_wo_eol)
                if m:
                    break
            if m:
                code_as = m.group(1).strip()
                if code_as:
                    # Close the previous turn (if any) before starting a new one
                    finalize_current_turn()

                    # Start new turn at the beginning of this line
                    current_name = code_as
                    current_start = line_start
                    current_end = line_start + len(line_wo_eol)  # exclude EOL
                    current_content_start = line_start + m.end()
                    continue

            # Continuation line: only attach it if we're currently inside a speaker turn
            if current_name is not None and current_start is not None:
                # Extend end to include this line (excluding its EOL),
                # but keep the exact original substring boundaries.
                current_end = line_start + len(line_wo_eol)

            # If no speaker has started yet, we ignore these lines as "header" / uncoded intro.

        # Close a trailing open turn at EOF (if any)
        finalize_current_turn()

        # Build summary for table
        self.speaker_summary = []
        for name, count in name_counts.items():
            self.speaker_summary.append(
                {
                    "selected": True,
                    "name": name,
                    "code_as": name,
                    "count": count,
                    "example": name_example.get(name, '')
                }
            )

    def fill_table(self):
        self.ui.tableWidget.blockSignals(True)
        vertical_scroll = self.ui.tableWidget.verticalScrollBar().value()
        try:
            # clear
            rows = self.ui.tableWidget.rowCount()
            for r in range(0, rows):
                self.ui.tableWidget.removeRow(0)

            # update table
            for row, data in enumerate(self.speaker_summary):
                self.ui.tableWidget.insertRow(row)
                
                # name
                name_item = QtWidgets.QTableWidgetItem(data['name'])
                name_item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsUserCheckable |
                    QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable) # non editable
                if data['selected']:
                    name_item.setCheckState(QtCore.Qt.CheckState.Checked)
                else:
                    name_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
                self.ui.tableWidget.setItem(row, 0, name_item)
                
                # code as
                code_as_item = QtWidgets.QTableWidgetItem(str(data['code_as']))
                code_as_item.setFlags(code_as_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable) # make editable
                self.ui.tableWidget.setItem(row, 1, code_as_item)
                
                # count
                count_item = QtWidgets.QTableWidgetItem(str(data['count']))
                count_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
                count_item.setFlags(count_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, 2, count_item)

                # example
                example_item = QtWidgets.QTableWidgetItem(str(data['example']))
                example_item.setFlags(example_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, 3, example_item)
                
                self.ui.tableWidget.resizeColumnToContents(0)
                self.ui.tableWidget.resizeColumnToContents(1)
                self.ui.tableWidget.resizeColumnToContents(2)
        finally:
            self.ui.tableWidget.blockSignals(False)
            QtCore.QTimer.singleShot(0, lambda: self.ui.tableWidget.verticalScrollBar().setValue(vertical_scroll))

    def on_item_changed(self, item):
        if item.text() == '':
            Message(self.app, _('Speakers'), _('The speaker name cannot be empty. If you want to exclude a speaker from being marked, deselect the check box on the left.')).exec()
        else:
            code_as = self.ui.tableWidget.item(item.row(), 1).text()
            self.speaker_summary[item.row()]['code_as'] = code_as
            sel_state = self.ui.tableWidget.item(item.row(), 0).checkState() == QtCore.Qt.CheckState.Checked
            self.speaker_summary[item.row()]['selected'] = (sel_state)
        QtCore.QTimer.singleShot(0, lambda: self.fill_table())

    def ok(self):
        cur = self.app.conn.cursor()
        try: 
            # search speakers category or create it
            speakers_cat = None
            cur.execute("select name, ifnull(memo,''), owner, date, catid, supercatid from code_cat where name = ? and supercatid is NULL",
                        (self.speakers_category_name,))
            speakers_cat = cur.fetchone()
            if speakers_cat is None:
                speakers_memo = _("This contains all the speakers that have been marked in documents.")
                item = {'name': self.speakers_category_name, 'cid': None, 'memo': speakers_memo,
                        'owner': self.app.settings['codername'],
                        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                            (item['name'], item['memo'], item['owner'], item['date'], None))   
                self.app.delete_backup = False 
                cur.execute("select name, ifnull(memo,''), owner, date, catid, supercatid from code_cat where name = ? and supercatid is NULL",
                            (self.speakers_category_name,))
                speakers_cat = cur.fetchone()
            if speakers_cat is None:
                raise ValueError(_('Speakers category could not be found found or created.'))
            speakers_catid = speakers_cat[4]
            
            # for each speaker name, find a suitabe code or add a new
            for speaker in self.speaker_summary:
                if not speaker['selected']:
                    continue
                speaker_code = None
                cur.execute("select cid, name, ifnull(memo,''), catid, owner, date, color from code_name where catid == ? and name == ?",
                            (speakers_catid, speaker['code_as']))
                speaker_code = cur.fetchone()
                if speaker_code is None:
                    code_color = colors[randint(0, len(colors) - 1)]
                    item = {'cid': None, 'name': speaker['code_as'], 'memo': self.filename,
                            'catid': speakers_catid, 'owner': self.app.settings['codername'],
                            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                            'color': code_color}
                    cur.execute("insert into code_name (name, memo, catid, owner, date, color) values(?,?,?,?,?,?)",
                                (item['name'], item['memo'], item['catid'], item['owner'], item['date'], item['color']))   
                    self.app.delete_backup = False 
                    cur.execute("select cid, name, ifnull(memo,''), catid, owner, date, color from code_name where catid == ? and name == ?",
                                (speakers_catid, speaker['code_as']))
                    speaker_code = cur.fetchone()
                else:
                    cur.execute("update code_name set memo = ? where cid = ?", 
                                (f'{speaker_code[2]}\n{self.filename}', speaker_code[0]))    
                if speaker_code is None:
                    raise ValueError(_('Speaker code could not be found found or created.'))
                speaker_code_cid = speaker_code[0]
                
                # add all corresponding text segments as codings 
                for coding in self.codings:
                    if coding['name'] == speaker['name']:
                        try:
                            cur.execute("insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo, important) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (speaker_code_cid, 
                                         self.fid, 
                                         coding['seltext'], 
                                         coding['pos0'], 
                                         coding['pos1'], 
                                         coding['owner'],
                                         coding['date'],
                                         coding['memo'], 
                                         None
                                        ))
                        except sqlite3.IntegrityError as e:
                            pass # skip ducplicates            
            
            self.app.conn.commit()
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # Revert all changes
            raise

    @staticmethod
    def help(self):
        """ Open help in browser. """
        webbrowser.open(self.app.help_wiki(""))
