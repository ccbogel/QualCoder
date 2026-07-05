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
https://qualcoder.org/
"""

import logging
import re
import datetime
from typing import Any, Dict, List, Tuple, Optional
from PyQt6 import QtCore, QtWidgets
import qtawesome as qta  # <- L
from random import randint
import sqlite3

from .GUI.ui_dialog_speakers import Ui_Dialog_speakers
from .color_selector import colors, colour_ranges
from .helpers import Message
from .select_items import DialogSelectItems  # <- L  for the select-files button

logger = logging.getLogger(__name__)
max_name_len: int = 63
speaker_coder_name = '📌 Speaker coding'
gray_range = next(r for r in colour_ranges if r['name'] == 'gray')
speaker_colors = colors[gray_range['min']:gray_range['max']+1]

# Bloquea marcadores http/https en el formato "name:" para evitar falsos positivos  # <- L
# (por ejemplo "https://example.com" no debe tratarse como turno de hablante).
# Block http/https markers to avoid false positives (e.g. a URL is not a speaker turn).
http_scheme_tail_re = re.compile(r"(?:^|\s)https?$", flags=re.IGNORECASE)


def identifier_regex(key: str):  # <- L
    """ 
    Devuelve el patron compilado para una clave de identificador, o None.
    El nombre del hablante siempre queda en el grupo 1
    
    Return the compiled pattern for an identifier key, or None (auto/custom).
    The name is always group 1
    """
    
    m = str(max_name_len)
    if key == 'name':      # Name:
        return re.compile(r"^\s*(.{1," + m + r"}?)\s*:\s*", flags=re.UNICODE)
    if key == 'hash':      # #Name:
        return re.compile(r"^\s*#\s*(.{1," + m + r"}?)\s*:\s*", flags=re.UNICODE)
    if key == 'at':        # @Name:
        return re.compile(r"^\s*@\s*(.{1," + m + r"}?)\s*:\s*", flags=re.UNICODE)
    if key == 'bracket':   # [Name]
        return re.compile(r"^\s*\[([^\]\r\n]{1," + m + r"})\]\s*", flags=re.UNICODE)
    if key == 'brace':     # {Name}
        return re.compile(r"^\s*\{([^}\r\n]{1," + m + r"})\}\s*", flags=re.UNICODE)
    return None


def match_speaker_turn(pattern, line: str):  # <- L
    """ 
    Si la linea inicia un turno valido devuelve (nombre, fin_del_marcador); si no, None.
    If the line starts a valid turn, return (name, marker_end), else None.
    
    Criterio unico compartido por la auto-deteccion y el parseo real:
    normaliza espacios, descarta nombres vacios y filtra URLs http(s).
    
    Single criterion shared by auto-detect and the real parse:
    collapses whitespace, discards empty names and filters http(s) URLs. 
    """
    
    m = pattern.match(line)
    if not m:
        return None
    # Con regex custom el grupo 1 puede no participar (p. ej. alternancias) y ser None.  # <- L
    # With a custom regex, group 1 may not participate (e.g. alternations) and be None.
    code_as = re.sub(r"\s+", " ", m.group(1) or "").strip()  # <- L
    if not code_as:
        return None
    # Evita falsos positivos tipo "https://..." # avoid URL false positives.
    rest = line[m.end():]
    if http_scheme_tail_re.search(code_as) is not None and rest.lstrip().startswith("//"):
        return None
    return code_as, m.end()


class DialogSpeakers(QtWidgets.QDialog):
    """Extracts speaker names from a transcript of an interview or a focus group, lets the user select
    which to keep, and creates codes for each speaker in the "Speakers" category.

    Turn detection:
    - The speaker identifier format is chosen in the "Identifier" combo box: Name: , #Name: , @Name: ,
    [Name] , {Name} , a custom regular expression, or Auto-detect (the format with the most turns).
    - A single format applies to the whole scan; lines in any other format are treated as
    continuation lines, not as new turns.
    - A new turn starts when a (non-empty) line begins with the chosen speaker marker; the captured
    name is trimmed and internal whitespace is collapsed; case is preserved.

    Multi-line support:
    - Lines following a speaker line belong to the same speaker until:
        (a) the next valid speaker line starts, or
        (b) a blank line occurs (blank lines act as separators and are NOT coded).

    Multi-file support:
    - The dialog opens on the given file, and the "Select files" button lets the user scan several
    text files at once. Each coded segment keeps its own file id, so codes span all selected files.

    Parameters:
    fid (int | list | dict): document id (initial file), a list of {'id', 'name'} dicts, or one dict
    filename (str): name of the document (only with the classic (app, fid, filename) form)
    """

    def __init__(self, app, fid, filename=None):
        self.app = app
        # Acepta ambas formas de llamada, por compatibilidad con distintos llamadores.  # <- L
        # Accept both call styles, for compatibility with different callers:
        #   DialogSpeakers(app, fid, filename)          -> un archivo. single file
        #   DialogSpeakers(app, [{'id','name'}, ...])   -> lista de archivos. list of files
        #   DialogSpeakers(app, {'id','name'})          -> un dict. a single dict
        if filename is None and isinstance(fid, (list, tuple)):  # <- L
            self.files: List[Dict[str, Any]] = [dict(f) for f in fid]  # <- L
        elif filename is None and isinstance(fid, dict):  # <- L
            self.files = [dict(fid)]  # <- L
        else:  # <- L  forma clasica (app, fid, filename). classic form
            self.files = [{'id': fid, 'name': filename}]  # <- L
        self._auto_key = None  # formato elegido por Auto-detect. format chosen by auto-detect  # <- L
        self._info_note = ""   # nota o error a mostrar en label_info. note or error for label_info  # <- L
        self.speakers_category_name = '📌 ' + _('Speakers')
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_speakers()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        headers = [_("Name"), _("code as"), _("Count"), _("Files"), _("Example")]  # <- L  se agrega Files
        self.ui.tableWidget.setColumnCount(len(headers))
        self.ui.tableWidget.setHorizontalHeaderLabels(headers)
        self._setup_identifier_combo()  # <- L
        self.ui.lineEdit_custom.setVisible(False)  # <- L  solo visible en modo Custom. only in Custom mode
        self.ui.pushButton_select_files.clicked.connect(self.select_files)  # <- L
        self.ui.comboBox_identifier.currentIndexChanged.connect(self.on_identifier_changed)  # <- L
        self.ui.lineEdit_custom.editingFinished.connect(self.reparse)  # <- L  reanaliza al terminar de editar
        self.codings: List[Dict[str, Any]] = []
        self.speaker_summary: List[Dict[str, Any]] = []
        self._update_title()  # <- L
        self.collect_names()
        self.fill_table()
        self.ui.tableWidget.itemChanged.connect(self.on_item_changed)
        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.buttonBox.accepted.connect(self.ok)
        # rejected -> reject() queda conectado desde Designer. rejected -> reject() is wired in Designer.  # <- L
        # Boton de ayuda arriba a la derecha, con icono, como en el resto de modulos.  # <- L
        # Help button top-right, icon-only, consistent with the other modules.
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))  # <- L
        self.ui.pushButton_help.pressed.connect(self.help)  # <- L

    def _setup_identifier_combo(self):  # <- L
        """ 
        Llena el combo de identificadores (clave, etiqueta)
        
        Fill the identifier combo. 
        """
        
        # El orden pone primero lo mas común. 
        # order puts the most common first.
        self._identifiers: List[Tuple[str, str]] = [
            ('auto',    _('Auto-detect')),
            ('name',    'Name :'),
            ('hash',    '# Name :'),
            ('at',      '@ Name :'),
            ('bracket', '[ Name ]'),
            ('brace',   '{ Name }'),
            ('custom',  _('Custom (regex)')),
        ]
        self.ui.comboBox_identifier.blockSignals(True)
        for key, label in self._identifiers:
            self.ui.comboBox_identifier.addItem(label, key)
        self.ui.comboBox_identifier.blockSignals(False)

    def _identifier_label(self, key: str) -> str:  # <- L
        return dict(getattr(self, '_identifiers', [])).get(key, key)

    def _update_title(self):  # <- L
        """ 
        Titulo con el archivo unico o el numero de archivos. 
        
        Title with file or file count. 
        """
        
        base = _("Mark Speakers")
        if not self.files:  # <- L  guardia: llamador con lista vacia. Guard: caller passed an empty list
            self.setWindowTitle(base)
            return
        n = len(self.files)
        suffix = self.files[0]['name'] if n == 1 else f"{n} " + _("files")
        self.setWindowTitle(f"{base} - {suffix}")

    def _fetch_text_files(self) -> List[Dict[str, Any]]:  # <- L
        """ 
        Archivos de texto del proyecto para el selector. 
        
        Project text files for the picker. 
        """
        
        cur = self.app.conn.cursor()
        cur.execute("select id, name from source where fulltext is not null and "
                    "(mediapath is null or mediapath like '/docs/%' or mediapath like 'docs:%') "
                    "order by name collate nocase")
        return [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]

    def select_files(self):  # <- L
        """ 
        Abre el selector estandar de archivos y reanaliza el conjunto elegido.
        
        Open the standard file picker and re-scan the chosen set. 
        """
        
        text_files = self._fetch_text_files()
        if not text_files:
            Message(self.app, _('Mark speakers'), _('No text files found.'), 'warning').exec()
            return
        ui = DialogSelectItems(self.app, text_files, _("Select files to scan for speakers"), "many")
        if not ui.exec():
            return
        selected = ui.get_selected()
        if not selected:
            return
        self.files = [{'id': s['id'], 'name': s['name']} for s in selected]
        self._update_title()
        self.reparse()

    def on_identifier_changed(self):  # <- L
        """ 
        Cambia el formato de identificador y reanaliza. 
        
        Change identifier format and re-scan. 
        """
        key = self.ui.comboBox_identifier.currentData()
        self.ui.lineEdit_custom.setVisible(key == 'custom')
        self.reparse()

    def reparse(self):  # <- L
        """ 
        Reanaliza los archivos con la configuracion actual y refresca la tabla.
        
        Re-scan files with the current settings and refresh the table. 
        """
        
        self.collect_names()
        self.fill_table()

    def _detect_best_key(self, transcripts) -> str:  # <- L
        """ 
        Prueba cada formato concreto y elige el de mas turnos. 
        
        Try each concrete format, pick the one with most turns. 
        """
        
        best, best_count = 'name', 0  # <- L  con 0 coincidencias se conserva 'name'. with 0 matches keep 'name'
        # Evalua los formatos especificos (con simbolo o corchetes) ANTES que el generico  # <- L
        # "Name:", porque este ultimo tambien casa "#Name:"/"@Name:" (incluiria el simbolo
        # en el nombre). En empate gana el mas especifico. Specific before generic on ties.
        for key in ('hash', 'at', 'bracket', 'brace', 'name'):  # <- L
            regex = identifier_regex(key)
            count = 0
            for _fid, _name, transcript in transcripts:
                for line in transcript.splitlines():
                    if match_speaker_turn(regex, line) is not None:  # <- L  mismo criterio que el parseo. Ssame criterion as the parse
                        count += 1
            if count > best_count:
                best, best_count = key, count
        return best

    def _resolve_pattern(self, transcripts):  # <- L
        """ 
        Devuelve (patron, nota). patron None indica que no se puede analizar.
        
        Return (pattern, note). A None pattern means it cannot parse. 
        """
        
        key = self.ui.comboBox_identifier.currentData()
        self._auto_key = None
        if key == 'custom':
            text = self.ui.lineEdit_custom.text().strip()
            if text == "":
                return None, _("Enter a custom regular expression.")
            try:
                regex = re.compile(text, flags=re.UNICODE)
            except re.error as err:
                return None, _("Invalid regex: ") + str(err)
            if regex.groups < 1:
                return None, _("The regex must contain one group capturing the name.")
            return regex, ""
        if key == 'auto':
            self._auto_key = self._detect_best_key(transcripts)
            return identifier_regex(self._auto_key), ""
        return identifier_regex(key), ""

    def collect_names(self):
        """
        Build a list (self.codings) for each speaker turn (across all selected files), including
        multi-line turns. Also creates a summary in self.speaker_summary for the QTableWidget.
        """

        self.codings = []
        name_counts: Dict[str, int] = {}
        name_example: Dict[str, str] = {}
        name_files: Dict[str, set] = {}  # <- L  archivos por hablante. Ffiles per speaker
        name_file_counts: Dict[str, Dict[str, int]] = {}  # <- L  turnos por (hablante, archivo). turns per (speaker, file)
        # Lee cada archivo una sola vez (sirve para deteccion y analisis).  # <- L
        transcripts = [(f['id'], f['name'], self.app.get_text_fulltext(f['id']) or "") for f in self.files]  # <- L
        pattern, note = self._resolve_pattern(transcripts)  # <- L
        self._info_note = note
        if pattern is not None:
            for fid, filename, transcript in transcripts:  # <- L
                self._parse_one_file(fid, filename, transcript, pattern, name_counts, name_example, name_files, name_file_counts)

        # Build summary for table
        self.speaker_summary = []
        for name, count in name_counts.items():
            self.speaker_summary.append(
                {
                    "selected": True,
                    "name": name,
                    "code_as": name,
                    "count": count,
                    "example": name_example.get(name, ''),
                    "files": len(name_files.get(name, set())),  # <- L
                    "files_list": sorted(name_files.get(name, set())),  # <- L  procedencia. provenance
                    "file_counts": name_file_counts.get(name, {}),  # <- L  turnos por archivo. turns per file
                }
            )

    def _parse_one_file(self, fid, filename, transcript, pattern, name_counts, name_example, name_files, name_file_counts):  # <- L
        """ 
        Analiza un archivo con un unico patron y agrega sus turnos a los acumuladores.
        
        Parse one file with a single pattern and append its turns to the accumulators. 
        """

        # State for the currently open speaker turn
        current_name: Optional[str] = None
        current_start: Optional[int] = None      # pos0
        current_end: Optional[int] = None        # pos1 (exclusive)
        current_content_start: Optional[int] = None  # start of the utterance (after marker)

        def finalize_current_turn():
            """Store the active turn and reset the state."""
            nonlocal current_name, current_start, current_end, current_content_start
            if current_name is None or current_start is None or current_end is None:
                return
            content_start = current_content_start or current_start  # <- L  inicio de la respuesta (tras el marcador)
            seltext_full = transcript[current_start:current_end]        # con el nombre. with the label
            seltext_response = transcript[content_start:current_end]    # <- L  solo la respuesta. response only
            self.codings.append(
                {
                    "name": current_name,
                    "fid": fid,           # <- L  fid del archivo actual. current file id
                    "filename": filename,  # <- L
                    "seltext": seltext_full,               # compat: texto con el nombre
                    "seltext_full": seltext_full,          # <- L  con nombre. with label
                    "seltext_response": seltext_response,  # <- L  sin nombre. without label
                    "pos0": current_start,
                    "pos1": current_end,
                    "content_pos0": content_start,         # <- L  inicio de la respuesta. Response start
                    "owner": speaker_coder_name,
                    "memo": "",
                    "date": datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            name_counts[current_name] = name_counts.get(current_name, 0) + 1
            name_file_counts.setdefault(current_name, {})  # <- L  turnos por (hablante, archivo)
            name_file_counts[current_name][filename] = name_file_counts[current_name].get(filename, 0) + 1  # <- L
            if name_example.get(current_name, "") == "":
                name_example[current_name] = seltext_response.strip()  # <- L  ejemplo = respuesta
            name_files.setdefault(current_name, set()).add(filename)  # <- L
            current_name = None
            current_start = None
            current_end = None
            current_content_start = None

        offset = 0
        for line in transcript.splitlines(keepends=True):
            line_start = offset
            offset += len(line)

            if line.endswith("\r\n"):
                eol_len = 2
            elif line.endswith("\n") or line.endswith("\r"):
                eol_len = 1
            else:
                eol_len = 0

            line_wo_eol = line[:-eol_len] if eol_len else line
            line_is_blank = (line_wo_eol.strip() == "")

            # Blank lines are separators, not coded.
            if line_is_blank:
                finalize_current_turn()
                continue

            turn = match_speaker_turn(pattern, line_wo_eol)  # <- L  nombre normalizado y filtro de URLs. normalized name and URL filter
            if turn is not None:  # <- L
                code_as, marker_end = turn  # <- L
                finalize_current_turn()
                current_name = code_as
                current_start = line_start
                current_end = line_start + len(line_wo_eol)  # exclude EOL
                current_content_start = line_start + marker_end  # <- L
                continue

            # Continuation line: attach only if inside a speaker turn.
            if current_name is not None and current_start is not None:
                current_end = line_start + len(line_wo_eol)

        # Close a trailing open turn at EOF.
        finalize_current_turn()

    def fill_table(self):
        """
        Fill the table widget in the dialog and update the summary label.
        """
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
                name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)  # non editable
                if data['selected']:
                    name_item.setCheckState(QtCore.Qt.CheckState.Checked)
                else:
                    name_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
                self.ui.tableWidget.setItem(row, 0, name_item)

                # code as
                code_as_item = QtWidgets.QTableWidgetItem(str(data['code_as']))
                code_as_item.setFlags(code_as_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)  # make editable
                self.ui.tableWidget.setItem(row, 1, code_as_item)

                # count
                count_item = QtWidgets.QTableWidgetItem(str(data['count']))
                count_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
                count_item.setFlags(count_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, 2, count_item)

                # files (numero de archivos donde aparece el hablante). files where the speaker appears  # <- L
                files_item = QtWidgets.QTableWidgetItem(str(data.get('files', 1)))  # <- L
                files_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)  # <- L
                files_item.setFlags(files_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)  # <- L
                files_item.setToolTip("\n".join(data.get('files_list', [])))  # <- L  procedencia. provenance
                self.ui.tableWidget.setItem(row, 3, files_item)  # <- L

                # example
                example_item = QtWidgets.QTableWidgetItem(str(data['example']))
                example_item.setFlags(example_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, 4, example_item)  # <- L  example ahora en col 4

            for col in range(0, 4):  # <- L  una sola pasada, fuera del bucle de filas. one pass, outside the row loop
                self.ui.tableWidget.resizeColumnToContents(col)
        finally:
            self.ui.tableWidget.blockSignals(False)
            QtCore.QTimer.singleShot(0, lambda: self.ui.tableWidget.verticalScrollBar().setValue(vertical_scroll))
            self._update_info_label()  # <- L

    def _update_info_label(self):  # <- L
        """ 
        Resumen de deteccion en label_info (o la nota/error si lo hay).
        
        Detection summary in label_info (or the note/error, if any). 
        """
        
        if self._info_note:
            self.ui.label_info.setText(self._info_note)
            return
        speakers = len(self.speaker_summary)
        turns = sum(s['count'] for s in self.speaker_summary)
        n_files = len(self.files)
        info = f"{speakers} " + _("speakers") + f", {turns} " + _("turns") + f", {n_files} " + _("files")
        if self.ui.comboBox_identifier.currentData() == 'auto' and self._auto_key and turns > 0:  # <- L  sin sufijo si no hay turnos. no suffix when no turns
            info += "  (" + _("detected") + f": {self._identifier_label(self._auto_key)})"
        self.ui.label_info.setText(info)

    def on_item_changed(self, item):
        if item.text() == '':
            Message(self.app, _('Speakers'), _('The speaker name cannot be empty. If you want to exclude a speaker from being marked, deselect the check box on the left.')).exec()
        else:
            code_as = self.ui.tableWidget.item(item.row(), 1).text()
            self.speaker_summary[item.row()]['code_as'] = code_as
            sel_state = self.ui.tableWidget.item(item.row(), 0).checkState() == QtCore.Qt.CheckState.Checked
            self.speaker_summary[item.row()]['selected'] = (sel_state)
        QtCore.QTimer.singleShot(0, lambda: self.fill_table())

    def table_menu(self, position):
        """ Context menu for quick visibility toggles. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_select_all = menu.addAction(_("Select all"))
        action_deselect_all = menu.addAction(_("Deselect all"))
        action = menu.exec(self.ui.tableWidget.viewport().mapToGlobal(position))
        if action == action_select_all:
            self.select_all()
        if action == action_deselect_all:
            self.deselect_all()

    def select_all(self):
        """ Select all speakers. """

        for speaker in self.speaker_summary:
            speaker['selected'] = True
        self.fill_table()

    def deselect_all(self):
        """ Deselect all speakers. """

        for speaker in self.speaker_summary:
            speaker['selected'] = False
        self.fill_table()

    def ok(self):
        cur = self.app.conn.cursor()
        include_name = self.ui.checkBox_include_name.isChecked()  # <- L  codificar con nombre o solo la respuesta
        try:
            # search speakers category or create it
            cur.execute("select name, ifnull(memo,''), owner, date, catid, supercatid from code_cat where name = ? and supercatid is NULL",
                        (self.speakers_category_name,))
            speakers_cat = cur.fetchone()
            if speakers_cat is None:
                speakers_memo = _("This contains all the speakers that have been marked in documents.")
                item = {'name': self.speakers_category_name, 'cid': None, 'memo': speakers_memo,
                        'owner': speaker_coder_name,
                        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                            (item['name'], item['memo'], item['owner'], item['date'], None))
                self.app.delete_backup = False
                cur.execute("select name, ifnull(memo,''), owner, date, catid, supercatid from code_cat where name = ? and supercatid is NULL",
                            (self.speakers_category_name,))
                speakers_cat = cur.fetchone()
            if speakers_cat is None:
                raise ValueError(_('Speakers category could not be found or created.'))  # <- L  typo del upstream corregido. upstream typo fixed
            speakers_catid = speakers_cat[4]

            # for each speaker name, find a suitable code or add a new
            used_colors = []
            inserted_codings = 0  # <- L  para marcar delete_backup solo si hubo cambios. to flag delete_backup only on real changes
            for speaker in self.speaker_summary:
                if not speaker['selected']:
                    continue
                # Archivos del hablante para el memo del codigo. speaker files for the code memo  <- L
                file_counts = speaker.get('file_counts', {})  # <- L  turnos por archivo. turns per file
                run_memo = self._memo_blocks(file_counts)  # <- L  bloque File/Turns de esta ejecucion
                speaker_code = None
                cur.execute("select cid, name, ifnull(memo,''), catid, owner, date, color from code_name where name == ?",
                            (speaker['code_as'], ))
                speaker_code = cur.fetchone()
                if speaker_code is None:
                    # search for unused color if possible
                    code_color = None
                    for color in speaker_colors:
                        if color not in used_colors:
                            code_color = color
                            break
                    if code_color is None:
                        code_color = speaker_colors[randint(0, len(speaker_colors) - 1)]
                    item = {'cid': None, 'name': speaker['code_as'], 'memo': run_memo,  # <- L  memo estructurado File/Turns
                            'catid': speakers_catid, 'owner': speaker_coder_name,
                            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                            'color': code_color}
                    cur.execute("insert into code_name (name, memo, catid, owner, date, color) values(?,?,?,?,?,?)",
                                (item['name'], item['memo'], item['catid'], item['owner'], item['date'], item['color']))
                    self.app.delete_backup = False
                    cur.execute("select cid, name, ifnull(memo,''), catid, owner, date, color from code_name where catid == ? and name == ?",
                                (speakers_catid, speaker['code_as']))
                    speaker_code = cur.fetchone()
                    used_colors.append(code_color)
                else:
                    merged_memo = self._append_memo(speaker_code[2], file_counts)  # <- L  acumula sin duplicar archivos
                    cur.execute("update code_name set memo = ? where cid = ?",
                                (merged_memo, speaker_code[0]))  # <- L
                    used_colors.append(speaker_code[6])
                if speaker_code is None:
                    raise ValueError(_('Speaker code could not be found or created.'))  # <- L  typo del upstream corregido. upstream typo fixed
                speaker_code_cid = speaker_code[0]

                # add all corresponding text segments as codings
                for coding in self.codings:
                    if coding['name'] == speaker['name']:
                        if include_name:  # <- L  todo el turno, con el nombre. Whole turn, with label
                            c_pos0, c_pos1 = coding['pos0'], coding['pos1']  # <- L
                            c_text = coding.get('seltext_full', coding.get('seltext', ''))  # <- L
                        else:  # <- L  solo la respuesta, sin el nombre. Response only
                            c_pos0, c_pos1 = coding.get('content_pos0', coding['pos0']), coding['pos1']  # <- L
                            c_text = coding.get('seltext_response', '')  # <- L
                            if c_text.strip() == "":  # <- L  turno sin respuesta: nada que codificar
                                continue
                        try:
                            cur.execute("insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo, important) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (speaker_code_cid,
                                         coding['fid'],  # <- L  fid por segmento. per-segment file id
                                         c_text,  # <- L
                                         c_pos0,  # <- L
                                         c_pos1,  # <- L
                                         coding['owner'],
                                         coding['date'],
                                         coding['memo'],
                                         None
                                        ))
                            inserted_codings += 1
                        except sqlite3.IntegrityError:  # <- L  variable 'e' sin uso eliminada. Unused 'e' removed
                            pass  # skip duplicates

            if inserted_codings > 0:  # <- L  hubo codificaciones nuevas # new codings were written
                self.app.delete_backup = False
            self.app.conn.commit()
        except Exception as e_:
            logger.exception(e_)  # <- L  antes print(); registra el traceback.  Was print(); logs the traceback
            self.app.conn.rollback()  # Revert all changes
            raise

    def _memo_blocks(self, file_counts):  # <- L
        """ 
        Bloque de memo File:/Turns: por archivo para esta ejecucion.
        
        File:/Turns: memo block per file for this run.
        """
        
        blocks = []
        for filename in sorted(file_counts):
            blocks.append(f"File: {filename}\nTurns: {file_counts[filename]}")
        return "\n\n".join(blocks)

    def _append_memo(self, existing_memo, file_counts):  # <- L
        """ 
        Añade al memo solo los archivos que aun no aparecen, sin duplicar.
        Append to the memo only files not already listed, without duplicating.
        
        Nota: los conteos (Turns) de archivos ya listados no se actualizan.
        Note: counts (Turns) for already-listed files are not updated. 
        """
        
        existing = existing_memo or ""
        present = set(m.strip() for m in re.findall(r"^File:\s*(.+)$", existing, flags=re.MULTILINE))
        to_add = {f: c for f, c in file_counts.items() if f not in present}
        if not to_add:
            return existing
        added = self._memo_blocks(to_add)
        if existing.strip() == "":
            return added
        return existing.rstrip() + "\n\n" + added

    def help(self):
        """ 
        Open help in browser (Coding Text page describes Mark speakers and its formats). 
        """
        
        self.app.help_wiki("4.1.-Coding-Text") # Pendiente: ir a hipervinculo 
