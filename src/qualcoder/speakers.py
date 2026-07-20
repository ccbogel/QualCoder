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
from PyQt6 import QtCore, QtGui, QtWidgets
import qtawesome as qta
from random import randint
import sqlite3

from .GUI.ui_dialog_speakers import Ui_Dialog_speakers
from .color_selector import colors, colour_ranges
from .helpers import Message
from .select_items import DialogSelectItems  # for the select-files button

logger = logging.getLogger(__name__)
max_name_len: int = 63
# Letras mayusculas (ASCII + Latin-1 acentuadas: incluye A-Z y Á É Í Ó Ú Ñ Ü, etc.)
# para detectar "Nombre:" a mitad de parrafo. El modulo re no soporta \p{Lu}, de ahi el rango.
# Uppercase letters (ASCII + accented Latin-1: A-Z and Á É Í Ó Ú Ñ Ü, ...) for mid-paragraph
# "Name:" detection. The re module has no \p{Lu}, hence the explicit range.
_UPPER = "A-ZÀ-ÖØ-Þ"
speaker_coder_name = '📌 Speaker coding'
gray_range = next(r for r in colour_ranges if r['name'] == 'gray')
speaker_colors = colors[gray_range['min']:gray_range['max']+1]

# Bloquea marcadores http/https en el formato "name:" para evitar falsos positivos
# (por ejemplo "https://example.com" no debe tratarse como turno de hablante).
# Block http/https markers to avoid false positives (e.g. a URL is not a speaker turn).
http_scheme_tail_re = re.compile(r"(?:^|\s)https?$", flags=re.IGNORECASE)


def identifier_regex(key: str, anchored: bool = True):
    """ 
    Devuelve el patron compilado para una clave de identificador, o None.
    El nombre del hablante siempre queda en el grupo 1.
    anchored=False quita el ancla inicial para poder detectar el marcador en
    cualquier punto de la linea (modo multi-identificador).
    
    Return the compiled pattern for an identifier key, or None (auto/custom).
    The name is always group 1.
    anchored=False drops the leading anchor so the marker can be detected anywhere
    in the line (multi-identifier mode).
    """
    
    m = str(max_name_len)
    a = r"^\s*" if anchored else r""  # ancla opcional. optional anchor
    if key == 'name':      # Name:
        return re.compile(a + r"(.{1," + m + r"}?)\s*:\s*", flags=re.UNICODE)
    if key == 'hash':      # #Name:
        return re.compile(a + r"#\s*(.{1," + m + r"}?)\s*:\s*", flags=re.UNICODE)
    if key == 'at':        # @Name:
        return re.compile(a + r"@\s*(.{1," + m + r"}?)\s*:\s*", flags=re.UNICODE)
    if key == 'bracket':   # [Name]
        return re.compile(a + r"\[([^\]\r\n]{1," + m + r"})\]\s*", flags=re.UNICODE)
    if key == 'brace':     # {Name}
        return re.compile(a + r"\{([^}\r\n]{1," + m + r"})\}\s*", flags=re.UNICODE)
    return None


def _looks_like_url(code_as: str, line: str, marker_end: int) -> bool:
    """ 
    True si el marcador es en realidad una URL http(s) y no un hablante.
    True if the marker is actually an http(s) URL, not a speaker. 
    """
    
    rest = line[marker_end:]
    return http_scheme_tail_re.search(code_as) is not None and rest.lstrip().startswith("//")


def iter_speaker_turns(pattern, line: str, anywhere: bool = False):
    """ 
    Genera (nombre, inicio_del_marcador, fin_del_marcador) por cada marcador valido en la linea.
    Yield (name, marker_start, marker_end) for each valid marker on the line.

    'pattern' puede ser:
      - un patron compilado (formatos fijos o regex custom), o
      - una lista de patrones (modo multi-identificador): en cada posicion se toma el
        marcador que empieza antes; implica escaneo en cualquier punto de la linea.
    'pattern' may be:
      - a single compiled pattern (fixed formats or custom regex), or
      - a list of patterns (multi-identifier mode): at each position the earliest-starting
        marker wins; this implies scanning anywhere in the line.

    anywhere=False (formatos fijos): un solo marcador, anclado al inicio de la linea.
    anywhere=True (regex custom): el patron puede casar en cualquier punto de la linea
    y puede haber varios marcadores por linea. Con lista, siempre se escanea anywhere.
    
    anywhere=False (fixed formats): a single marker, anchored at the start of the line.
    anywhere=True (custom regex): the pattern may match anywhere in the line and there
    may be several markers per line. With a list, scanning is always anywhere.

    Nombre: grupo 1 si el patron define uno; si no, el texto completo casado
    (asi ~\\w+: funciona tal cual, sin grupo).
    Name: group 1 if the pattern defines one, else the whole matched text
    (so ~\\w+: works as-is, without a group).
    
    Criterio unico compartido por la auto-deteccion y el parseo real:
    normaliza espacios, descarta nombres vacios y filtra URLs http(s).
    Single criterion shared by auto-detect and the real parse:
    collapses whitespace, discards empty names and filters http(s) URLs.
    """
    
    patterns = list(pattern) if isinstance(pattern, (list, tuple)) else None
    is_multi = patterns is not None
    scan_anywhere = anywhere or is_multi  # la lista siempre escanea anywhere. a list always scans anywhere
    pos = 0
    while pos <= len(line):
        if is_multi:
            # Marcador que empieza antes entre todos los patrones (en empate, el mas largo).
            # Earliest-starting marker among all patterns (on a tie, the longest).
            m = None
            for pat in patterns:
                cand = pat.search(line, pos)
                if cand is None or cand.end() == cand.start():
                    continue
                if m is None or cand.start() < m.start() or (cand.start() == m.start() and cand.end() > m.end()):
                    m = cand
        else:
            m = pattern.search(line, pos) if scan_anywhere else pattern.match(line)
        if m is None:
            return
        if m.end() == m.start():  # evita bucles con coincidencias vacias. guard against zero-length matches
            if not scan_anywhere:
                return
            pos = m.end() + 1
            continue
        # Con regex custom el grupo 1 puede no participar (p. ej. alternancias) y ser None.
        # With a custom regex, group 1 may not participate (e.g. alternations) and be None.
        raw = m.group(1) if m.re.groups >= 1 else m.group(0)  # m.re: patron que caso. sin grupo: todo el match
        code_as = re.sub(r"\s+", " ", raw or "").strip()
        # Evita falsos positivos tipo "https://..." # avoid URL false positives.
        if code_as and not _looks_like_url(code_as, line, m.end()):
            yield code_as, m.start(), m.end()
        pos = m.end()
        if not scan_anywhere:
            return


def match_speaker_turn(pattern, line: str):
    """ 
    Compatibilidad: primer marcador de la linea como (nombre, fin_del_marcador), o None.
    Compat: first marker on the line as (name, marker_end), or None.
    """
    
    for code_as, _marker_start, marker_end in iter_speaker_turns(pattern, line):
        return code_as, marker_end
    return None


class DialogSpeakers(QtWidgets.QDialog):
    """Extracts speaker names from a transcript of an interview or a focus group, lets the user select
    which to keep, and creates codes for each speaker in the "Speakers" category.

    Turn detection:
    - The "Identifier" control is a multi-select checklist: Name: , #Name: , @Name: , [Name] ,
    {Name} , and Custom (regex). Any combination can be checked at once, and Custom can be
    combined with the fixed formats. Name: is checked by default.
    - One format checked: only that format applies. Fixed formats are anchored at the start of the
    line (a marker starts a turn only at the beginning of a line). The custom regex may match
    ANYWHERE in the line, and several markers on one line each start their own turn.
    - Two or more items checked (mixed mode): all checked formats are detected in a single pass.
    The delimiter-based markers (#Name:, @Name:, [Name], {Name}) and the custom regex are found
    ANYWHERE in the line, so speaker markers embedded mid-paragraph are detected; several markers
    on one line each start their own turn, and text before the first marker stays with the
    previous turn. The bare "Name:" format is detected at the START of a line (the ideal case)
    and also MID-PARAGRAPH under strict conditions: the name must start with an uppercase letter
    and be glued to the colon (Palabra: or La palabra:); if there is a period or comma before it,
    the name is the words between that separator and the colon. Mid-paragraph "Name:" can surface
    phrase-like candidates (e.g. a sentence starting "Note:"), which the user simply leaves
    unticked in the table.
    - Custom regex: if the pattern has a capturing group, group 1 is the speaker name; otherwise
    the whole match is used, e.g. ~\\w+: detects ~QknowSubject:.
    - The captured name is trimmed and internal whitespace is collapsed; case is preserved.

    Multi-line support:
    - Lines following a speaker line belong to the same speaker until the next valid speaker
    marker starts or the file ends. Blank lines do NOT end a turn, so a turn may span several
    paragraphs; trailing blank lines are not included in the coded segment.

    Coding options:
    - The "code as" cell accepts several code names separated by ';' so the same turns are
    coded to more than one code, e.g. the speaker name plus attribute codes.
    - Right-click a row and choose "Preview segments" to review every segment of that speaker
    and untick the ones that should not be coded. The Count column shows ticked/total when
    some segments are unticked. Re-scanning (changing identifiers or files) resets the ticks.

    Multi-file support:
    - The dialog opens on the given file, and the "Select files" button lets the user scan several
    text files at once. Each coded segment keeps its own file id, so codes span all selected files.

    Parameters:
    fid (int | list | dict): document id (initial file), a list of {'id', 'name'} dicts, or one dict
    filename (str): name of the document (only with the classic (app, fid, filename) form)
    """

    def __init__(self, app, fid, filename=None):
        self.app = app
        # Acepta ambas formas de llamada, por compatibilidad con distintos llamadores.
        # Accept both call styles, for compatibility with different callers:
        #   DialogSpeakers(app, fid, filename)          -> un archivo. single file
        #   DialogSpeakers(app, [{'id','name'}, ...])   -> lista de archivos. list of files
        #   DialogSpeakers(app, {'id','name'})          -> un dict. a single dict
        if filename is None and isinstance(fid, (list, tuple)):
            self.files: List[Dict[str, Any]] = [dict(f) for f in fid]
        elif filename is None and isinstance(fid, dict):
            self.files = [dict(fid)]
        else:  # forma clasica (app, fid, filename). classic form
            self.files = [{'id': fid, 'name': filename}]
        # Si el llamador no aporta una seleccion usable, la preseleccion pasa a ser
        # todos los archivos de texto del proyecto (retroalimentacion de Van: nunca
        # abrir con "No files selected").
        # If the caller passed no usable selection, preselect every project text file
        # (Van's feedback: never open with "No files selected").
        self.files = [f for f in self.files if f.get('id') is not None]
        if not self.files:
            self.files = self._fetch_text_files()
        self._info_note = ""   # nota o error a mostrar en label_info. note or error for label_info
        self._additional_vocab: List[str] = []  # <- L  vocabulario acumulado de codigos adicionales. shared additional-codes vocab
        self._additional_combos: Dict[int, QtWidgets.QComboBox] = {}  # <- L  combo por fila. per-row combo
        self.speakers_category_name = '📌 ' + _('Speakers')
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_speakers()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        headers = [_("Name"), _("code as"), _("Additional codes"), _("Count"), _("Files"), _("Example")]  # <- L  nueva columna tras code as
        self.ui.tableWidget.setColumnCount(len(headers))
        self.ui.tableWidget.setHorizontalHeaderLabels(headers)
        self._setup_identifier_combo()
        self.ui.lineEdit_custom.setVisible(False)  # solo visible en modo Custom. only in Custom mode
        # Ejemplo visible y ayuda del patron custom, pedido en la retroalimentacion de Van.
        # Visible example and help for the custom pattern, requested in Van's feedback.
        self.ui.lineEdit_custom.setPlaceholderText(_("e.g.") + "  ~\\w+:   " + _("or") + "  ~(\\w+):")
        self.ui.lineEdit_custom.setToolTip(_(
            "The pattern may match anywhere in the line.\n"
            "With a capturing group, group 1 is the speaker name: ~(\\w+): detects QknowSubject\n"
            "Without a group, the whole match is the name: ~\\w+: detects ~QknowSubject:\n"
            "Several markers on one line each start their own turn."))
        self.ui.pushButton_select_files.clicked.connect(self.select_files)
        # La seleccion de identificadores es por casillas del modelo (ver _setup_identifier_combo).
        # Identifier selection is via model checkboxes (see _setup_identifier_combo).
        self.ui.lineEdit_custom.editingFinished.connect(self.reparse)  # reanaliza al terminar de editar
        self.codings: List[Dict[str, Any]] = []
        self.speaker_summary: List[Dict[str, Any]] = []
        self._update_title()
        self._update_files_label()
        self.collect_names()
        self.fill_table()
        self.ui.tableWidget.itemChanged.connect(self.on_item_changed)
        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.buttonBox.accepted.connect(self.ok)
        # Enter/Return no debe activar OK: se desactiva el boton por defecto y (mas abajo) se  # <- L
        # ignora Enter en keyPressEvent, para evitar aplicaciones accidentales al confirmar la
        # edicion de un codigo con Enter. OK solo con clic manual.
        # Enter/Return must not trigger OK: no default button, and Enter is swallowed in
        # keyPressEvent, to avoid accidental application when confirming a code edit with Enter.
        for button in self.ui.buttonBox.buttons():  # <- L
            button.setAutoDefault(False)  # <- L
            button.setDefault(False)  # <- L
        # rejected -> reject() queda conectado desde Designer. rejected -> reject() is wired in Designer.
        # Boton de ayuda arriba a la derecha, con icono, como en el resto de modulos.
        # Help button top-right, icon-only, consistent with the other modules.
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.pressed.connect(self.help)

    def _setup_identifier_combo(self):
        """ 
        Configura el combo como una lista de seleccion multiple con casillas.
        Name: viene marcado por defecto. Custom (regex) es una casilla mas que puede
        combinarse con los formatos fijos.
        
        Set up the combo as a multi-select checklist. Name: is checked by default.
        Custom (regex) is another checkbox that can be combined with the fixed formats. 
        """
        
        # El orden pone Name: primero, luego los formatos con simbolo y al final Custom.
        # Order puts Name: first, then the symbol formats, and Custom last.
        self._identifiers: List[Tuple[str, str]] = [
            ('name',    'Name:'),
            ('hash',    '#Name:'),
            ('at',      '@Name:'),
            ('bracket', '[Name]'),
            ('brace',   '{Name}'),
            ('custom',  _('Custom (regex)')),
        ]
        combo = self.ui.comboBox_identifier
        model = QtGui.QStandardItemModel(self)
        for key, label in self._identifiers:
            item = QtGui.QStandardItem(label)
            item.setData(key, QtCore.Qt.ItemDataRole.UserRole)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            state = QtCore.Qt.CheckState.Checked if key == 'name' else QtCore.Qt.CheckState.Unchecked  # Name: por defecto
            item.setData(state, QtCore.Qt.ItemDataRole.CheckStateRole)
            model.appendRow(item)
        combo.setModel(model)
        # Editable con lineEdit de solo lectura para mostrar el resumen de lo marcado.
        # Editable with a read-only line edit to show a summary of the checked items.
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setPlaceholderText(_("Select identifiers"))
        combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        combo.setToolTip(_(
            "Click a format name to use only that one. Click its checkbox to add or remove it\n"
            "from a combination. Check 'Custom (regex)' to add your own pattern to the mix."))
        # Clic en el nombre: usar solo ese identificador. Clic en la casilla: combinar.
        # Click on the name: use only that identifier. Click on the checkbox: combine.
        combo.view().viewport().installEventFilter(self)
        combo.lineEdit().installEventFilter(self)
        self._update_identifier_text()

    def keyPressEvent(self, event):  # <- L
        """ 
        Enter/Return no cierra el dialogo (OK solo con clic manual). El editor de la celda o el
        combo ya procesan Enter para confirmar el texto; aqui solo se evita que Enter aplique todo
        y cierre la ventana por accidente. Escape se mantiene (cierra sin aplicar).
        
        Enter/Return does not close the dialog (OK only via manual click). The cell editor or the
        combo already handle Enter to commit the text; here Enter is just prevented from applying
        everything and closing the window by accident. Escape is left as is (closes without applying). 
        """
        
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            event.accept()  # se traga Enter para que no active el boton por defecto. swallow Enter
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """ 
        En el desplegable de identificadores:
        - clic sobre la CASILLA: alterna ese identificador (combinacion), sin cerrar el desplegable.
        - clic sobre el NOMBRE: usa solo ese identificador (cambio directo) y cierra el desplegable.
        Y abre el desplegable al pulsar el campo de texto.
        
        In the identifier popup:
        - click on the CHECKBOX: toggle that identifier (combination), keeping the popup open.
        - click on the NAME: use only that identifier (direct switch) and close the popup.
        Also open the popup when the read-only text field is pressed. 
        """
        
        combo = self.ui.comboBox_identifier
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            view = combo.view()
            if obj is view.viewport():
                pos = event.position().toPoint()
                index = view.indexAt(pos)
                if index.isValid():
                    item = combo.model().itemFromIndex(index)
                    if item is not None and (item.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable):
                        key = item.data(QtCore.Qt.ItemDataRole.UserRole)
                        if self._point_on_checkbox(view, index, pos):  # casilla: combinar. checkbox: combine
                            self._toggle_identifier(key)
                            return True  # el desplegable permanece abierto. keep the popup open
                        # nombre: usar solo ese identificador y cerrar. name: use only this one and close
                        self._select_single_identifier(key)
                        combo.hidePopup()
                return True
            if obj is combo.lineEdit():
                combo.showPopup()
                return True
        return super().eventFilter(obj, event)

    def _point_on_checkbox(self, view, index, pos) -> bool:
        """ 
        True si el punto cae sobre el indicador de casilla del item.
        
        True if the point is over the item's check indicator. 
        """
        
        style = view.style()
        try:
            opt = QtWidgets.QStyleOptionViewItem()
            opt.initFrom(view.viewport())
            opt.rect = view.visualRect(index)
            opt.features |= QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
            rect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, view.viewport())
            if rect.isValid() and rect.width() > 0:
                return rect.contains(pos)
        except Exception:  # pragma: no cover  estilos que no soportan la consulta. styles that do not support the query
            pass
        # Respaldo: ancho del indicador mas margenes desde el borde izquierdo del item.
        # Fallback: indicator width plus margins from the item's left edge.
        item_rect = view.visualRect(index)
        indicator = style.pixelMetric(QtWidgets.QStyle.PixelMetric.PM_IndicatorWidth, None, view)
        margin = style.pixelMetric(QtWidgets.QStyle.PixelMetric.PM_FocusFrameHMargin, None, view) * 2 + 4
        return pos.x() <= item_rect.left() + indicator + margin

    def _after_identifier_change(self):
        """ 
        Tras cambiar la seleccion de identificadores: muestra u oculta el campo de regex,
        refresca el texto del combo y reanaliza una sola vez.
        
        After changing the identifier selection: show/hide the regex field, refresh the combo
        text and re-scan once. 
        """
        
        self.ui.lineEdit_custom.setVisible(self._is_checked('custom'))
        self._update_identifier_text()
        self.reparse()

    def _select_single_identifier(self, key: str):
        """ 
        Deja marcado solo 'key' (cambio directo de identificador).
        
        Leave only 'key' checked (direct identifier switch). 
        """
        
        model = self.ui.comboBox_identifier.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            k = item.data(QtCore.Qt.ItemDataRole.UserRole)
            item.setCheckState(QtCore.Qt.CheckState.Checked if k == key else QtCore.Qt.CheckState.Unchecked)
        self._after_identifier_change()

    def _toggle_identifier(self, key: str):
        """ 
        Alterna la casilla de 'key' (agrega o quita de la combinacion).
        
        Toggle the checkbox of 'key' (add to or remove from the combination). 
        """
        
        model = self.ui.comboBox_identifier.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == key:
                checked = item.checkState() == QtCore.Qt.CheckState.Checked
                item.setCheckState(QtCore.Qt.CheckState.Unchecked if checked else QtCore.Qt.CheckState.Checked)
                break
        self._after_identifier_change()

    def _is_checked(self, key: str) -> bool:
        """ True si la casilla del identificador esta marcada. True if the identifier is checked. """
        model = self.ui.comboBox_identifier.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == key:
                return item.checkState() == QtCore.Qt.CheckState.Checked
        return False

    def _checked_keys(self) -> List[str]:
        """ Claves de los identificadores marcados, en orden. Checked identifier keys, in order. """
        keys = []
        model = self.ui.comboBox_identifier.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                keys.append(item.data(QtCore.Qt.ItemDataRole.UserRole))
        return keys

    def _update_identifier_text(self):
        """ 
        Muestra en el campo del combo un resumen de los identificadores marcados.
        
        Show a summary of the checked identifiers in the combo's text field. 
        """
        
        labels = [lbl for (k, lbl) in self._identifiers if self._is_checked(k)]
        line_edit = self.ui.comboBox_identifier.lineEdit()
        if line_edit is not None:
            line_edit.setText(", ".join(labels))

    def _update_title(self):
        """ 
        Titulo con el archivo unico o el numero de archivos. 
        
        Title with file or file count. 
        """
        
        base = _("Mark Speakers")
        if not self.files:  # guardia: llamador con lista vacia. Guard: caller passed an empty list
            self.setWindowTitle(base)
            return
        n = len(self.files)
        suffix = self.files[0]['name'] if n == 1 else f"{n} " + _("files")
        self.setWindowTitle(f"{base} - {suffix}")

    def _fetch_text_files(self) -> List[Dict[str, Any]]:
        """ 
        Archivos de texto del proyecto para el selector. 
        
        Project text files for the picker. 
        """
        
        cur = self.app.conn.cursor()
        cur.execute("select id, name from source where fulltext is not null and "
                    "(mediapath is null or mediapath like '/docs/%' or mediapath like 'docs:%') "
                    "order by name collate nocase")
        return [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]

    def select_files(self):
        """ 
        Abre el selector estandar de archivos, mostrando MARCADA la seleccion actual
        para poder revisarla y ajustarla (retroalimentacion de Van), y reanaliza el
        conjunto elegido.
        
        Open the standard file picker with the CURRENT selection shown selected, so
        the user can check and adjust it (Van's feedback), and re-scan the chosen set. 
        """
        
        text_files = self._fetch_text_files()
        if not text_files:
            Message(self.app, _('Mark speakers'), _('No text files found.'), 'warning').exec()
            return
        current_ids = {f['id'] for f in self.files}
        preselected = [f for f in text_files if f['id'] in current_ids]
        ui = DialogSelectItems(self.app, text_files, _("Select files to scan for speakers"), "many",
                               preselected=preselected, with_checkboxes=True)
        if not ui.exec():
            return
        selected = ui.get_selected()
        if not selected:
            return
        self.files = [{'id': s['id'], 'name': s['name']} for s in selected]
        self._update_title()
        self._update_files_label()
        self.reparse()

    def _update_files_label(self):
        """ 
        Muestra la lista actual de archivos junto al boton "Select files", con
        elipsis si es larga; el tooltip lista todos los archivos (retroalimentacion
        de Van: una forma simple de comprobar la seleccion actual).
        
        Show the current file list next to the "Select files" button, elided when
        long; the tooltip lists every file (Van's feedback: a simple way to check
        the current selection). 
        """
        
        label = getattr(self.ui, 'label_files', None)
        if label is None:  # UI file not regenerated: degrade gracefully
            return
        names = [f['name'] for f in self.files]
        if not names:
            label.setText(_("No files selected"))
            label.setToolTip("")
            return
        text = ", ".join(names)
        if len(names) > 1:
            text = f"({len(names)}) " + text
        metrics = QtGui.QFontMetrics(label.font())
        label.setText(metrics.elidedText(text, QtCore.Qt.TextElideMode.ElideRight, 420))
        label.setToolTip("\n".join(names))

    def reparse(self):
        """ 
        Reanaliza los archivos con la configuracion actual y refresca la tabla.
        
        Re-scan files with the current settings and refresh the table. 
        """
        
        self.collect_names()
        self.fill_table()

    def _name_patterns(self, delimiter_safe: bool):
        """ 
        Patrones del identificador "Nombre:": una lista con
          1) inicio de linea (caso ideal), y
          2) a mitad de parrafo, con condiciones estrictas para evitar falsos positivos.

        Inicio de linea:
          - delimiter_safe=False (Nombre: solo): voraz hasta los primeros dos puntos (clasico).
          - delimiter_safe=True (Nombre: combinado): el nombre no incluye # @ [ { para no
            tragarse un marcador con simbolo.
        A mitad de parrafo (pedido por el usuario): el nombre debe empezar con mayuscula y
        estar pegado a los dos puntos (Palabra: o La palabra:), y si hay un punto o una coma
        antes, el nombre son las palabras entre ese separador y los dos puntos.

        "Name:" identifier patterns: a list with
          1) line start (the ideal case), and
          2) mid-paragraph, with strict conditions to avoid false positives.

        Line start:
          - delimiter_safe=False (Name: alone): greedy up to the first colon (classic).
          - delimiter_safe=True (Name: combined): the name excludes # @ [ { so it does not
            swallow a symbol marker.
        Mid-paragraph (as requested): the name must start with an uppercase letter and be glued
        to the colon (Palabra: or La palabra:); if there is a period or comma before, the name is
        the words between that separator and the colon. 
        """
        
        mlen = str(max_name_len)
        # El nombre de inicio de linea NO incluye punto ni coma: asi, si antes de los dos puntos
        # hay una frase (con punto/coma), este patron no matchea y cede al de mitad de parrafo,
        # que extrae solo el nombre en mayuscula tras el separador.
        # The line-start name excludes period and comma: if there is a phrase (with a period/comma)
        # before the colon, this pattern does not match and defers to the mid-paragraph one, which
        # extracts only the capitalised name after the separator.
        if delimiter_safe:  # combinado: ademas excluye # @ [ {. combined: also excludes # @ [ {
            line_start = re.compile(r"^\s*([^.,#@\[{\r\n]{1," + mlen + r"}?)\s*:\s*", flags=re.UNICODE)
        else:  # Nombre: solo. Name: alone
            line_start = re.compile(r"^\s*([^.,\r\n]{1," + mlen + r"}?)\s*:\s*", flags=re.UNICODE)
        # Tras un punto o coma y espacios: palabra(s) que empiezan en mayuscula, pegadas a ":".
        # After a period or comma and spaces: word(s) starting with an uppercase letter, glued to ":".
        mid_paragraph = re.compile(
            r"(?<=[.,])\s+([" + _UPPER + r"][^\W\d_]*(?:[ \t]+[^\W\d_]+){0,5}):",
            flags=re.UNICODE)
        return [line_start, mid_paragraph]

    def _resolve_pattern(self):
        """ 
        Construye el patron a partir de las casillas marcadas.
        Devuelve (patron, anywhere, nota):
          - patron None: no hay nada que analizar (nota explica por que).
          - un patron unico: un solo identificador fijo (salvo Nombre:) o la regex sola.
          - una lista de patrones: Nombre: (inicio de linea + mitad de parrafo) o dos o mas
            identificadores (modo mixto).
        anywhere indica si el escaneo es en cualquier punto de la linea.
        
        Build the pattern from the checked boxes.
        Return (pattern, anywhere, note):
          - pattern None: nothing to parse (note explains why).
          - a single pattern: exactly one fixed identifier (except Name:) or the custom regex.
          - a list of patterns: Name: (line start + mid-paragraph) or two or more identifiers.
        anywhere says whether scanning is done anywhere in the line. 
        """
        
        keys = self._checked_keys()
        note = ""
        if not keys:
            return None, False, _("Select at least one identifier.")
        fixed = [k for k in keys if k != 'custom']
        use_custom = 'custom' in keys
        custom_regex = None
        if use_custom:
            text = self.ui.lineEdit_custom.text().strip()
            if text == "":
                use_custom = False
                note = _("Enter a custom regular expression.")
            else:
                try:
                    custom_regex = re.compile(text, flags=re.UNICODE)
                except re.error as err:
                    use_custom = False
                    custom_regex = None
                    note = _("Invalid regex: ") + str(err)
        total = len(fixed) + (1 if use_custom else 0)
        if total == 0:  # solo Custom marcado pero vacio/invalido. only Custom checked but empty/invalid
            return None, False, note or _("Enter a custom regular expression.")
        if total == 1:
            if use_custom:  # regex sola: casa en cualquier punto. single custom: matches anywhere
                return custom_regex, True, note
            key = fixed[0]
            if key == 'name':  # Nombre: inicio de linea + mitad de parrafo (lista, anywhere)
                return self._name_patterns(delimiter_safe=False), True, note
            return identifier_regex(key), False, note  # otro formato fijo: anclado. other fixed: anchored
        # Dos o mas identificadores: modo mixto (lista de patrones, escaneo anywhere)
        # Two or more identifiers: mixed mode (list of patterns, scanned anywhere).
        patterns = []
        for k in fixed:
            if k == 'name':  # Nombre: inicio de linea (sin tragarse simbolos) + mitad de parrafo
                patterns.extend(self._name_patterns(delimiter_safe=True))
            else:  # marcadores con delimitador en cualquier punto. delimiter markers anywhere
                patterns.append(identifier_regex(k, anchored=False))
        if use_custom:  # la regex custom se une a la combinacion. the custom regex joins the mix
            patterns.append(custom_regex)
        return patterns, True, note

    def collect_names(self):
        """
        Build a list (self.codings) for each speaker turn (across all selected files), including
        multi-line turns. Also creates a summary in self.speaker_summary for the QTableWidget.
        """

        self.codings = []
        name_counts: Dict[str, int] = {}
        name_example: Dict[str, str] = {}
        name_files: Dict[str, set] = {}  # archivos por hablante. Ffiles per speaker
        name_file_counts: Dict[str, Dict[str, int]] = {}  # turnos por (hablante, archivo). turns per (speaker, file)
        # Conserva los codigos adicionales por nombre al reanalizar (no se pierden al cambiar  # <- L
        # identificadores o archivos). Carry over additional codes by name across re-scans.
        prev_additional = {sp['name']: list(sp.get('additional_codes', []))  # <- L
                           for sp in getattr(self, 'speaker_summary', [])}  # <- L
        # Lee cada archivo una sola vez
        transcripts = [(f['id'], f['name'], self.app.get_text_fulltext(f['id']) or "") for f in self.files]
        pattern, anywhere, note = self._resolve_pattern()
        self._info_note = note
        if pattern is not None:
            for fid, filename, transcript in transcripts:
                self._parse_one_file(fid, filename, transcript, pattern, anywhere, name_counts, name_example, name_files, name_file_counts)

        # Build summary for table
        self.speaker_summary = []
        for name, count in name_counts.items():
            self.speaker_summary.append(
                {
                    "selected": True,
                    "name": name,
                    "code_as": name,
                    "additional_codes": prev_additional.get(name, []),  # <- L  codigos adicionales conservados
                    "count": count,
                    "example": name_example.get(name, ''),
                    "files": len(name_files.get(name, set())),
                    "files_list": sorted(name_files.get(name, set())),  # procedencia. provenance
                    "file_counts": name_file_counts.get(name, {}),  # turnos por archivo. turns per file
                }
            )
        self._rebuild_additional_vocab()  # <- L  recalcula el vocabulario compartido. recompute shared vocab

    def _split_codes(self, text) -> List[str]:  # <- L
        """ 
        Divide una cadena por ';' en codigos limpios, sin vacios ni duplicados (preserva orden).
        
        Split a string on ';' into clean code names, no empties or duplicates (order preserved). 
        """
        
        out: List[str] = []
        for part in str(text).split(';'):
            clean = re.sub(r"\s+", " ", part).strip()
            if clean and clean not in out:
                out.append(clean)
        return out

    def _rebuild_additional_vocab(self):  # <- L
        """ 
        Vocabulario compartido = union de todos los codigos adicionales ya escritos (crece,
        no encoge, para que las opciones ya usadas sigan disponibles en el desplegable).
        
        Shared vocabulary = union of every additional code entered so far (grows, does not
        shrink, so previously used options stay available in the dropdown). 
        """
        
        vocab = set(self._additional_vocab)
        for sp in self.speaker_summary:
            for code in sp.get('additional_codes', []):
                vocab.add(code)
        self._additional_vocab = sorted(vocab, key=str.lower)

    def _parse_one_file(self, fid, filename, transcript, pattern, anywhere, name_counts, name_example, name_files, name_file_counts):
        """ 
        Analiza un archivo con un unico patron y agrega sus turnos a los acumuladores.
        anywhere=True (regex custom): marcadores en cualquier punto de la linea, varios por linea.
        
        Parse one file with a single pattern and append its turns to the accumulators.
        anywhere=True (custom regex): markers anywhere in the line, several per line. 
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
            content_start = current_content_start or current_start  # inicio de la respuesta (tras el marcador)
            seltext_full = transcript[current_start:current_end]        # con el nombre. with the label
            seltext_response = transcript[content_start:current_end]    # solo la respuesta. response only
            self.codings.append(
                {
                    "name": current_name,
                    "fid": fid,           # fid del archivo actual. current file id
                    "filename": filename,
                    "selected": True,      # casilla del previsualizador de segmentos. segment preview tick
                    "seltext": seltext_full,               # compat: texto con el nombre
                    "seltext_full": seltext_full,          # con nombre. with label
                    "seltext_response": seltext_response,  # sin nombre. without label
                    "pos0": current_start,
                    "pos1": current_end,
                    "content_pos0": content_start,         #inicio de la respuesta. Response start
                    "owner": speaker_coder_name,
                    "memo": "",
                    "date": datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            name_counts[current_name] = name_counts.get(current_name, 0) + 1
            name_file_counts.setdefault(current_name, {})  # turnos por (hablante, archivo)
            name_file_counts[current_name][filename] = name_file_counts[current_name].get(filename, 0) + 1
            if name_example.get(current_name, "") == "":
                name_example[current_name] = seltext_response.strip()  # ejemplo = respuesta
            name_files.setdefault(current_name, set()).add(filename)
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

            # Las lineas en blanco YA NO cierran el turno: este continua hasta el proximo
            # marcador valido o el fin del archivo (pedido en la retroalimentacion). No se
            # extiende current_end, de modo que las lineas en blanco finales quedan fuera
            # del segmento codificado.
            # Blank lines NO LONGER close the turn: it continues until the next valid marker
            # or EOF (requested in the feedback). current_end is not extended, so trailing
            # blank lines stay out of the coded segment.
            if line_is_blank:
                continue

            turns = list(iter_speaker_turns(pattern, line_wo_eol, anywhere))  # nombre normalizado y filtro de URLs. normalized name and URL filter
            if turns:
                # Texto antes del primer marcador: continua el turno anterior (solo posible
                # en modo anywhere). Text before the first marker continues the previous turn
                # (only possible in anywhere mode).
                prefix = line_wo_eol[:turns[0][1]]
                if current_name is not None and prefix.strip() != "":
                    current_end = line_start + len(prefix.rstrip())
                for i, (code_as, marker_start, marker_end) in enumerate(turns):
                    finalize_current_turn()
                    current_name = code_as
                    current_start = line_start + marker_start  # antes line_start fijo. was fixed line_start
                    current_content_start = line_start + marker_end
                    if i + 1 < len(turns):  # el turno termina donde inicia el siguiente marcador
                        # the turn ends where the next marker on the same line starts
                        current_end = line_start + len(line_wo_eol[:turns[i + 1][1]].rstrip())
                    else:
                        current_end = line_start + len(line_wo_eol)  # exclude EOL
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
            self._additional_combos = {}  # <- L  se recrean los combos en cada refresco. combos are recreated each refresh

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
                # Pista de codigos multiples separados por ';'. Hint for ';'-separated codes
                code_as_item.setToolTip(_("Use ';' to code these turns to more than one code, e.g. Ana; woman; migrant"))
                self.ui.tableWidget.setItem(row, 1, code_as_item)

                # additional codes (combo editable con vocabulario compartido).  # <- L
                # additional codes (editable combo with the shared vocabulary).
                combo = self._make_additional_combo(row, data)  # <- L
                self.ui.tableWidget.setCellWidget(row, 2, combo)  # <- L
                self._additional_combos[row] = combo  # <- L

                # count (elegidos/total si hay segmentos desmarcados en el previsualizador)
                # (ticked/total when some segments are unticked in the preview)
                total = data['count']
                ticked = sum(1 for c in self.codings
                             if c['name'] == data['name'] and c.get('selected', True))
                count_text = str(total) if ticked == total else f"{ticked}/{total}"
                count_item = QtWidgets.QTableWidgetItem(count_text)
                if ticked != total:
                    count_item.setToolTip(_("Ticked segments / total. Right-click the row to preview."))
                count_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
                count_item.setFlags(count_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, 3, count_item)  # <- L  antes col 2. was col 2

                # files (numero de archivos donde aparece el hablante). files where the speaker appears
                files_item = QtWidgets.QTableWidgetItem(str(data.get('files', 1)))
                files_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
                files_item.setFlags(files_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                files_item.setToolTip("\n".join(data.get('files_list', [])))  # procedencia. provenance
                self.ui.tableWidget.setItem(row, 4, files_item)  # <- L  antes col 3. was col 3

                # example
                example_item = QtWidgets.QTableWidgetItem(str(data['example']))
                example_item.setFlags(example_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, 5, example_item)  # <- L  antes col 4. was col 4

            for col in (0, 1, 3, 4):  # <- L  ajusta a contenido salvo la columna de combos. resize all but the combo column
                self.ui.tableWidget.resizeColumnToContents(col)
            if self.ui.tableWidget.columnWidth(2) < 200:  # <- L  ancho comodo para Additional codes. comfortable width
                self.ui.tableWidget.setColumnWidth(2, 200)  # <- L
        finally:
            self.ui.tableWidget.blockSignals(False)
            QtCore.QTimer.singleShot(0, lambda: self.ui.tableWidget.verticalScrollBar().setValue(vertical_scroll))
            self._update_info_label()

    def _make_additional_combo(self, row, speaker):  # <- L
        """ 
        Combo editable para la columna Additional codes de una fila.
        - Se pueden escribir codigos nuevos, varios separados por ';'.
        - El desplegable ofrece el vocabulario ya usado en otras filas; elegir uno lo SUMA a
          los de esta celda (no lo reemplaza).
        Editable combo for a row's Additional codes cell.
        - New codes can be typed, several separated by ';'.
        - The dropdown offers the vocabulary already used in other rows; picking one ADDS it to
          this cell (it does not replace). 
        """
        
        combo = QtWidgets.QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        combo.lineEdit().setPlaceholderText(_("Attribute codes, ';' separated"))
        combo.setToolTip(_(
            "Extra codes applied to this speaker's turns, in addition to 'code as'.\n"
            "Type new ones (separate several with ';') or pick a previous one from the list to add it."))
        self._reload_combo_items(combo)
        self._set_combo_tokens(combo, list(speaker.get('additional_codes', [])))
        combo.activated.connect(lambda idx, r=row, c=combo: self._on_additional_pick(r, c, idx))  # <- L  elegir del desplegable
        combo.lineEdit().editingFinished.connect(lambda r=row, c=combo: self._on_additional_edited(r, c))  # <- L  terminar de escribir
        return combo

    def _reload_combo_items(self, combo):  # <- L
        """ 
        Recarga las opciones del desplegable con el vocabulario compartido, conservando el
        texto que el usuario tenga escrito en la celda.
        
        Reload the dropdown options with the shared vocabulary, keeping whatever text the user
        has typed in the cell. 
        """
        
        text = combo.lineEdit().text()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(self._additional_vocab)
        combo.setCurrentIndex(-1)
        combo.lineEdit().setText(text)
        combo.blockSignals(False)

    def _set_combo_tokens(self, combo, tokens):  # <- L
        """ 
        Escribe en la celda los codigos 'tokens' unidos por '; ' sin disparar señales.
        
        Write 'tokens' joined by '; ' into the cell without triggering signals. 
        """
        
        combo.blockSignals(True)
        combo.lineEdit().blockSignals(True)
        combo.setCurrentIndex(-1)
        combo.lineEdit().setText("; ".join(tokens))
        combo.lineEdit().blockSignals(False)
        combo.blockSignals(False)

    def _on_additional_pick(self, row, combo, idx):  # <- L
        """ 
        Al elegir una opcion del desplegable: se agrega a los codigos de esta celda (se suma).
        
        On picking a dropdown option: it is added to this cell's codes (accumulates). 
        """
        
        if idx < 0 or not (0 <= row < len(self.speaker_summary)):
            return
        picked = combo.itemText(idx).strip()
        tokens = list(self.speaker_summary[row].get('additional_codes', []))
        if picked and picked not in tokens:
            tokens.append(picked)
        self._set_combo_tokens(combo, tokens)
        self._commit_additional(row, tokens)

    def _on_additional_edited(self, row, combo):  # <- L
        """ 
        Al terminar de escribir: se interpretan los codigos separados por ';' de la celda.
        
        On finishing typing: the ';'-separated codes in the cell are parsed. 
        """
        
        if not (0 <= row < len(self.speaker_summary)):
            return
        tokens = self._split_codes(combo.lineEdit().text())
        self._set_combo_tokens(combo, tokens)  # normaliza el texto mostrado. normalise the shown text
        self._commit_additional(row, tokens)

    def _commit_additional(self, row, tokens):  # <- L
        """ 
        Guarda los codigos adicionales de la fila, actualiza el vocabulario compartido y
        refresca las opciones de todos los combos.
        
        Store the row's additional codes, update the shared vocabulary and refresh every
        combo's dropdown options. 
        """
        
        self.speaker_summary[row]['additional_codes'] = tokens
        self._rebuild_additional_vocab()
        for combo in self._additional_combos.values():
            self._reload_combo_items(combo)

    def _update_info_label(self):
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
        self.ui.label_info.setText(info)

    def on_item_changed(self, item):
        # Valida tambien el caso de solo separadores, p. ej. " ; ".
        # Also validate the separators-only case, e.g. " ; ".
        has_code = any(part.strip() for part in item.text().split(';'))
        if not has_code:
            Message(self.app, _('Speakers'), _('The speaker name cannot be empty. If you want to exclude a speaker from being marked, deselect the check box on the left.')).exec()
        else:
            code_as = self.ui.tableWidget.item(item.row(), 1).text()
            self.speaker_summary[item.row()]['code_as'] = code_as
            sel_state = self.ui.tableWidget.item(item.row(), 0).checkState() == QtCore.Qt.CheckState.Checked
            self.speaker_summary[item.row()]['selected'] = (sel_state)
        QtCore.QTimer.singleShot(0, lambda: self.fill_table())

    def table_menu(self, position):
        """ Context menu for segment preview and quick visibility toggles. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        row = self.ui.tableWidget.indexAt(position).row()  # -1 si el click no cae en una fila. -1 if not on a row
        action_preview = menu.addAction(_("Preview segments")) if row >= 0 else None
        action_select_all = menu.addAction(_("Select all"))
        action_deselect_all = menu.addAction(_("Deselect all"))
        action = menu.exec(self.ui.tableWidget.viewport().mapToGlobal(position))
        if action is None:  # menu cerrado sin elegir. menu dismissed
            return
        if action_preview is not None and action == action_preview:
            self.preview_segments(row)
            return
        if action == action_select_all:
            self.select_all()
        if action == action_deselect_all:
            self.deselect_all()

    def preview_segments(self, row):
        """ 
        Previsualiza los segmentos del hablante de la fila; cada segmento tiene una casilla
        y los desmarcados no se codifican al aceptar el dialogo principal.
        
        Preview the segments of the speaker in the row; each segment has a tick box and
        unticked segments are not coded when the main dialog is accepted. 
        """
        
        if not 0 <= row < len(self.speaker_summary):
            return
        speaker = self.speaker_summary[row]
        segments = [c for c in self.codings if c['name'] == speaker['name']]
        if not segments:
            Message(self.app, _('Mark speakers'), _('No segments for this speaker.')).exec()
            return
        dialog, table = self._build_preview_dialog(speaker, segments)
        if dialog.exec():
            self._apply_preview(segments, table)
            self.fill_table()  # refresca la columna Count (elegidos/total). refresh Count column

    def _build_preview_dialog(self, speaker, segments):
        """ 
        Construye el dialogo de previsualizacion (separado para poder probarlo).
        
        Build the preview dialog (separate so it can be tested). 
        """
        
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(_("Segments") + f": {speaker['code_as']}")
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        dialog.setStyleSheet(font)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel(_("Ticked segments will be coded. Untick the ones to skip.")))
        table = QtWidgets.QTableWidget(dialog)
        headers = ["#", _("File"), _("Position"), _("Segment")]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(segments))
        # Sin edicion de celdas; las casillas siguen siendo interactivas
        # No cell editing; tick boxes remain interactive.
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        # La columna Segment ajusta el texto y crece con la ventana; las filas ajustan su alto
        # The Segment column wraps text and grows with the window; rows auto-fit their height.
        table.setWordWrap(True)
        table.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for r, seg in enumerate(segments):
            check_item = QtWidgets.QTableWidgetItem(str(r + 1))
            check_item.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            state = QtCore.Qt.CheckState.Checked if seg.get('selected', True) else QtCore.Qt.CheckState.Unchecked
            check_item.setCheckState(state)
            check_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignHCenter)
            table.setItem(r, 0, check_item)
            file_item = QtWidgets.QTableWidgetItem(seg.get('filename', ''))
            file_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
            table.setItem(r, 1, file_item)
            pos_item = QtWidgets.QTableWidgetItem(f"{seg['pos0']}-{seg['pos1']}")
            pos_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight)
            table.setItem(r, 2, pos_item)
            full_text = seg.get('seltext_full', seg.get('seltext', ''))
            excerpt = re.sub(r"\s+", " ", full_text).strip()
            if len(excerpt) > 300:  # se muestra mas texto; el completo va en el tooltip. show more; full text in tooltip
                excerpt = excerpt[:300] + "..."
            text_item = QtWidgets.QTableWidgetItem(excerpt)
            text_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
            text_item.setToolTip(full_text[:2000])  # texto completo (acotado) en el tooltip. full (capped) text in the tooltip
            table.setItem(r, 3, text_item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # 
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # File
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # Position
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)  # Segment ocupa el resto. Segment takes the rest
        header.setStretchLastSection(True)
        # Alto de fila segun el contenido: al reajustar el ancho, el texto se reacomoda.
        # Row height follows content: as the width changes, the text rewraps.
        table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)  # el numero de segmento ya esta en la columna #
        layout.addWidget(table)
        buttons_layout = QtWidgets.QHBoxLayout()
        btn_all = QtWidgets.QPushButton(_("Select all"), dialog)
        btn_none = QtWidgets.QPushButton(_("Deselect all"), dialog)

        def set_all(state):
            for r_ in range(table.rowCount()):
                table.item(r_, 0).setCheckState(state)

        btn_all.clicked.connect(lambda: set_all(QtCore.Qt.CheckState.Checked))
        btn_none.clicked.connect(lambda: set_all(QtCore.Qt.CheckState.Unchecked))
        buttons_layout.addWidget(btn_all)
        buttons_layout.addWidget(btn_none)
        buttons_layout.addStretch()
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=dialog)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        buttons_layout.addWidget(button_box)
        layout.addLayout(buttons_layout)
        dialog.resize(760, 420)
        return dialog, table

    @staticmethod
    def _apply_preview(segments, table):
        """ 
        Copia el estado de las casillas del dialogo a los segmentos.
        
        Copy the tick states from the dialog back to the segments. 
        """
        
        for r, seg in enumerate(segments):
            seg['selected'] = (table.item(r, 0).checkState() == QtCore.Qt.CheckState.Checked)

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
        include_name = self.ui.checkBox_include_name.isChecked()  # codificar con nombre o solo la respuesta
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
                raise ValueError(_('Speakers category could not be found or created.'))  # typo del upstream corregido. upstream typo fixed
            speakers_catid = speakers_cat[4]

            # for each speaker name, find a suitable code or add a new
            used_colors = []
            inserted_codings = 0  # para marcar delete_backup solo si hubo cambios. to flag delete_backup only on real changes
            for speaker in self.speaker_summary:
                if not speaker['selected']:
                    continue
                # Archivos del hablante para el memo del codigo. speaker files for the code memo
                file_counts = speaker.get('file_counts', {})  # turnos por archivo. turns per file
                # Codigos a aplicar a los turnos de este hablante: los de "code as" (separados por  # <- L
                # ';') mas los de "additional codes". Los mismos turnos se codifican a cada uno,
                # sin vacios ni duplicados. Codes applied to this speaker's turns: those in
                # "code as" (';'-separated) plus those in "additional codes". The same turns are
                # coded to each, no empties or duplicates.
                code_names: List[str] = self._split_codes(speaker['code_as'])  # <- L
                for extra in speaker.get('additional_codes', []):  # <- L  codigos adicionales de la columna nueva
                    if extra not in code_names:  # <- L
                        code_names.append(extra)  # <- L
                for code_name in code_names:
                    speaker_code_cid = self._get_or_create_speaker_code(
                        cur, code_name, speakers_catid, used_colors, file_counts)

                    # add all corresponding text segments as codings
                    for coding in self.codings:
                        if coding['name'] != speaker['name']:
                            continue
                        if not coding.get('selected', True):  # desmarcado en el previsualizador. unticked in the preview
                            continue
                        if include_name:  # todo el turno, con el nombre. Whole turn, with label
                            c_pos0, c_pos1 = coding['pos0'], coding['pos1']
                            c_text = coding.get('seltext_full', coding.get('seltext', ''))
                        else:  # solo la respuesta, sin el nombre. Response only
                            c_pos0, c_pos1 = coding.get('content_pos0', coding['pos0']), coding['pos1']
                            c_text = coding.get('seltext_response', '')
                            if c_text.strip() == "":  # turno sin respuesta: nada que codificar
                                continue
                        try:
                            cur.execute("insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo, important) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (speaker_code_cid,
                                         coding['fid'],  # fid por segmento. per-segment file id
                                         c_text,
                                         c_pos0,
                                         c_pos1,
                                         coding['owner'],
                                         coding['date'],
                                         coding['memo'],
                                         None
                                        ))
                            inserted_codings += 1
                        except sqlite3.IntegrityError:  # variable 'e' sin uso eliminada. Unused 'e' removed
                            pass  # skip duplicates

            if inserted_codings > 0:  # hubo codificaciones nuevas # new codings were written
                self.app.delete_backup = False
            self.app.conn.commit()
        except Exception as e_:
            logger.exception(e_)  # antes print(); registra el traceback.  Was print(); logs the traceback
            self.app.conn.rollback()  # Revert all changes
            raise

    def _get_or_create_speaker_code(self, cur, code_name, speakers_catid, used_colors, file_counts):
        """ 
        Devuelve el cid del codigo con ese nombre; lo crea en la categoria Speakers si no existe.
        Logica extraida de ok() para reutilizarla con varios codigos por hablante (';').
        
        Return the cid of the code with that name; create it in the Speakers category if missing.
        Logic extracted from ok() so it can be reused with several codes per speaker (';'). 
        """
        
        cur.execute("select cid, name, ifnull(memo,''), catid, owner, date, color from code_name where name == ?",
                    (code_name, ))
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
            item = {'cid': None, 'name': code_name, 'memo': self._memo_blocks(file_counts),  # memo estructurado File/Turns
                    'catid': speakers_catid, 'owner': speaker_coder_name,
                    'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    'color': code_color}
            cur.execute("insert into code_name (name, memo, catid, owner, date, color) values(?,?,?,?,?,?)",
                        (item['name'], item['memo'], item['catid'], item['owner'], item['date'], item['color']))
            self.app.delete_backup = False
            cur.execute("select cid, name, ifnull(memo,''), catid, owner, date, color from code_name where catid == ? and name == ?",
                        (speakers_catid, code_name))
            speaker_code = cur.fetchone()
            used_colors.append(code_color)
        else:
            merged_memo = self._append_memo(speaker_code[2], file_counts)  # acumula sin duplicar archivos
            cur.execute("update code_name set memo = ? where cid = ?",
                        (merged_memo, speaker_code[0]))
            used_colors.append(speaker_code[6])
        if speaker_code is None:
            raise ValueError(_('Speaker code could not be found or created.'))  # typo del upstream corregido. upstream typo fixed
        return speaker_code[0]

    def _memo_blocks(self, file_counts):
        """ 
        Bloque de memo File:/Turns: por archivo para esta ejecucion.
        
        File:/Turns: memo block per file for this run.
        """
        
        blocks = []
        for filename in sorted(file_counts):
            blocks.append(f"File: {filename}\nTurns: {file_counts[filename]}")
        return "\n\n".join(blocks)

    def _append_memo(self, existing_memo, file_counts):
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
