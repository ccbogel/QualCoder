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
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

from copy import deepcopy
import datetime
import fitz
import logging
import math
import os
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import sqlite3

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog

from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import TextColor
from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_graph import Ui_DialogGraph
from .helpers import DialogCodeInAV, DialogCodeInImage, DialogCodeInText, \
    ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .save_sql_query import DialogSaveSql
from .select_items import DialogSelectItems
# new modules 
from .view_graph_relations import DialogNodeRelations
from .view_graph_models import DialogGraphModels
# ODF imports for the analytical graph summary export (.odt)
from odf.opendocument import OpenDocumentText
from odf.text import P, H, Span
from odf.table import Table, TableColumn, TableRow, TableCell
from odf.draw import Frame, Image as OdfImage
from odf.style import Style, TextProperties, ParagraphProperties, TableCellProperties

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

colors = {"red": QtCore.Qt.GlobalColor.red, "green": QtCore.Qt.GlobalColor.green,
          "cyan": QtCore.Qt.GlobalColor.cyan, "magenta": QtCore.Qt.GlobalColor.magenta,
          "yellow": QtGui.QColor("#FFD700"), "blue": QtGui.QColor("#6495ED"),
          "orange": QtGui.QColor("#FFA500"), "gray": QtGui.QColor("#808080"),
          "black": QtCore.Qt.GlobalColor.black, "white": QtCore.Qt.GlobalColor.white}

# hex equivalents of named colors, single source of truth for exporters (Draw.io, ODT)
COLORS_HEX = {"red": "#FF0000", "green": "#00FF00", "cyan": "#00FFFF",
              "magenta": "#FF00FF", "yellow": "#FFD700", "blue": "#6495ED",
              "orange": "#FFA500", "gray": "#808080", "black": "#000000",
              "white": "#FFFFFF"}

# sentinel offset to encode MemoGraphicsItem endpoints into the legacy
# fromfreetextid / tofreetextid columns of gr_free_line_item without altering the schema.
# Values >= offset are read as (gmemoid + offset) and resolved against gr_memo_item on load.
_MEMO_LINE_ID_OFFSET = 1_000_000_000


# tolerant accessor for the colors dict (legacy/hex/misspelled values fall back safely)
def safe_color(name):
    if name in colors:
        return colors[name]
    try:
        qc = QtGui.QColor(name)
        if qc.isValid():
            return qc
    except Exception:
        pass
    return colors["gray"]


# shared geometry helper for FreeLineGraphicsItem and LinkGraphicsItem.
# Intersection of line (center_source -> center_target) with the perimeter of rect.
def compute_edge_point(center_source, center_target, rect, is_ellipse):
    dx = center_target.x() - center_source.x()
    dy = center_target.y() - center_source.y()
    if dx == 0 and dy == 0:
        return center_source
    w = rect.width() / 2
    h = rect.height() / 2
    if is_ellipse:
        angle = math.atan2(dy, dx)
        return QtCore.QPointF(center_source.x() + w * math.cos(angle),
                              center_source.y() + h * math.sin(angle))
    if dx == 0:
        return QtCore.QPointF(center_source.x(), center_source.y() + math.copysign(h, dy))
    if dy == 0:
        return QtCore.QPointF(center_source.x() + math.copysign(w, dx), center_source.y())
    tx = w / abs(dx)
    ty = h / abs(dy)
    t = min(tx, ty)
    return QtCore.QPointF(center_source.x() + dx * t, center_source.y() + dy * t)


# DialogMemo doubles as QualCoder's generic plain-text editor; the graph
# uses it for "Edit text" on nodes. Hide the memo-specific toolbar (clear, insert
# date/quote/memo-link, export linked), which makes no sense on a node text.
# Tolerant to older DialogMemo builds that lack some of these buttons.
def configure_plain_text_editor(dialog):
    for btn_name in ('pushButton_clear', 'pushButton_insert_datetime',
                     'pushButton_insert_coded_segment',
                     'pushButton_insert_memo_link', 'pushButton_export_linked'):
        btn = getattr(dialog.ui, btn_name, None)
        if btn is not None:
            btn.hide()


# shared bridge to ViewGraph.toggle_segment_cooccurrence_lines from any coded segment
def invoke_segment_cooc_toggle(scene_item):
    scene = scene_item.scene()
    if scene is None:
        return False
    parent = getattr(scene, 'parent', None)
    if parent is not None and hasattr(parent, 'toggle_segment_cooccurrence_lines'):
        parent.toggle_segment_cooccurrence_lines()
        return True
    if scene.views():
        widget = scene.views()[0].parent()
        while widget is not None:
            if hasattr(widget, 'toggle_segment_cooccurrence_lines'):
                widget.toggle_segment_cooccurrence_lines()
                return True
            widget = widget.parent()
    return False


# shared helper for "Add and link memo". Creates a MemoGraphicsItem linked to a
# node via a green dotted FreeLineGraphicsItem, with duplicate detection by (type, id).
def link_memo_to_segment(app, segment_node, memo_source_type, memo_source_id, memo_text):
    if not memo_text:
        return
    scene = segment_node.scene()
    if scene is None:
        return
    for item in scene.items():
        if isinstance(item, MemoGraphicsItem):
            if item.memo_source_type == memo_source_type and item.memo_source_id == memo_source_id:
                Message(app, _("Memo already imported"),
                        _("This memo is already displayed in the graph.")).exec()
                return
    x = segment_node.pos().x() + 150
    y = segment_node.pos().y()
    memo_node = MemoGraphicsItem(app, memo_source_type, memo_source_id, x, y)
    scene.addItem(memo_node)
    line_item = FreeLineGraphicsItem(segment_node, memo_node, color="green",
                                     line_width=2, line_type="dotted")
    line_item.arrow_mode = "none"
    scene.addItem(line_item)


# anti-overlap label positioner shared by FreeLineGraphicsItem and LinkGraphicsItem.
def detach_line_label(line_item):
    """ Remove the label text item (and its child bg) from the scene without
    destroying the python objects, so it can be re-attached on redraw. """
    ti = getattr(line_item, 'text_item', None)
    if ti is None:
        return
    try:
        if ti.scene() is not None:
            ti.scene().removeItem(ti)
    except RuntimeError:
        line_item.text_item = None
        line_item._label_bg = None


def build_line_label(line_item, label=None):
    """ Shared implementation of _create_label_item for FreeLineGraphicsItem and
    LinkGraphicsItem: create, update or remove the top-level italic label.
    Returns the text item (or None when the label is empty). """
    if label is not None:
        line_item.label = str(label).strip()
    if not line_item.label:
        detach_line_label(line_item)
        line_item.text_item = None
        line_item._label_bg = None
        return None
    if line_item.text_item is not None:
        try:
            # Display translated; line_item.label keeps the canonical name (data).
            line_item.text_item.setPlainText(_(line_item.label))
            return line_item.text_item
        except RuntimeError:
            line_item.text_item = None
            line_item._label_bg = None
    # Translate at display time only: the DB stores the canonical English name, so
    # the graph follows the interface language and custom labels pass through
    # unchanged (gettext returns the string as-is when no translation exists).
    ti = QtWidgets.QGraphicsTextItem(_(line_item.label))
    ti._is_line_label = True  # marker for the anti-overlap positioner
    font = QtGui.QFont()
    font.setPointSize(9)
    font.setBold(False)
    font.setItalic(True)
    ti.setFont(font)
    # Blue to highlight relational attributes.
    ti.setDefaultTextColor(QtGui.QColor("#0000CD"))
    ti.setZValue(5)  # above nodes (z=0), below handles (z=10)
    line_item.text_item = ti
    line_item._label_bg = None  # (re)built by position_line_label
    return ti


def sync_line_label_on_item_change(line_item, change, value):
    """ Shared itemChange body for both line classes: keep the top-level label's
    visibility and scene membership in sync with the line. """
    if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged:
        ti = getattr(line_item, 'text_item', None)
        if ti is not None:
            try:
                ti.setVisible(bool(value) and bool(line_item.label))
            except RuntimeError:
                pass
    if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged \
            and value is None:
        detach_line_label(line_item)


def position_line_label(line_item, p1, p2):
    ti = getattr(line_item, 'text_item', None)
    if ti is None or not getattr(line_item, 'label', ''):
        detach_line_label(line_item)
        return
    scene = line_item.scene()
    try:
        br = ti.boundingRect()
    except RuntimeError:
        # C++ object destroyed (e.g. scene cleared); rebuild if possible
        line_item.text_item = None
        line_item._label_bg = None
        if hasattr(line_item, '_create_label_item'):
            line_item._create_label_item()
        ti = line_item.text_item
        if ti is None:
            return
        br = ti.boundingRect()
    if scene is not None and ti.scene() is not scene:
        scene.addItem(ti)
    ti.setVisible(line_item.isVisible())
    best_t = 0.5
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    if scene:
        for t_offset in [0.0, 0.15, -0.15, 0.25, -0.25, 0.35, -0.35]:
            t = 0.5 + t_offset
            test_x = p1.x() + dx * t
            test_y = p1.y() + dy * t
            test_rect = QtCore.QRectF(test_x - br.width() / 2,
                                      test_y - br.height() / 2,
                                      br.width(), br.height())
            collision = False
            for item in scene.items(test_rect):
                if item is ti or item is line_item or item.parentItem() is ti:
                    continue
                # other relation labels (top-level, flagged) and node text items
                if getattr(item, '_is_line_label', False) or \
                        isinstance(item, (TextGraphicsItem, FreeTextGraphicsItem,
                                          CaseTextGraphicsItem, FileTextGraphicsItem)):
                    collision = True
                    break
            if not collision:
                best_t = t
                break
    mid_x = p1.x() + dx * best_t
    mid_y = p1.y() + dy * best_t
    # top-level item: position directly in scene coordinates
    ti.setPos(mid_x - br.width() / 2, mid_y - br.height() / 2)
    if not hasattr(line_item, '_label_bg') or line_item._label_bg is None:
        bg = QtWidgets.QGraphicsRectItem(ti)  # child of the text item
        # a child is drawn ON TOP of its parent regardless of zValue unless
        # ItemStacksBehindParent is set; without it the white chip covered the text
        bg.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)
        bg.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 235)))
        bg.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))  # no border on the chip
        line_item._label_bg = bg
    # padded chip in the text item's local coordinates
    line_item._label_bg.setRect(br.adjusted(-4, -1, 4, 1))


# shared handle-sync logic for every node class with per-item handles.
def sync_handles_with_selection(node):
    """ Show ConnectionHandle + ResizeHandle on `node` only if it is the SOLE selected item.
    Idempotent and tolerant against C++ object destruction. """
    scene = node.scene()
    if scene is None:
        return
    try:
        should_show = node.isSelected() and len(scene.selectedItems()) == 1
    except RuntimeError:
        return
    if should_show:
        if not hasattr(node, '_conn_handle') or node._conn_handle is None:
            node._conn_handle = ConnectionHandleItem(node)
        if not hasattr(node, '_resize_handle') or node._resize_handle is None:
            node._resize_handle = ResizeHandleItem(node, "bottom_right")
        return
    if hasattr(node, '_conn_handle') and node._conn_handle is not None:
        try:
            if node._conn_handle.scene() == scene:
                scene.removeItem(node._conn_handle)
        except RuntimeError:
            pass
        node._conn_handle = None
    if hasattr(node, '_resize_handle') and node._resize_handle is not None:
        try:
            if node._resize_handle.scene() == scene:
                scene.removeItem(node._resize_handle)
        except RuntimeError:
            pass
        node._resize_handle = None


# shared add_linked_categories logic for Case and File items.
# The SQL that pulls catids and the line color are parameters (orange=Case, blue=File).
def add_linked_categories_to_node(node, sql, sql_params, line_color):
    """ Add categories that contain codes applied to this node (Case or File),
    skipping those already in the scene. """
    cur = node.app.conn.cursor()
    cur.execute(sql, sql_params)
    catids = {r[0] for r in cur.fetchall()}
    if not catids:
        Message(node.app, _("No categories"),
                _("No categories linked to codes in this item.")).exec()
        return
    existing_catids = {it.code_or_cat.get('catid') for it in node.scene().items()
                       if isinstance(it, TextGraphicsItem) and it.code_or_cat.get('cid') is None}
    catids_to_add = catids - existing_catids
    if not catids_to_add:
        Message(node.app, _("No categories"),
                _("All linked categories are already in the graph.")).exec()
        return
    cat_list = []
    for catid in catids_to_add:
        cur.execute("select name, ifnull(memo,''), supercatid from code_cat where catid=?", [catid])
        res = cur.fetchone()
        if res:
            cat_list.append({'catid': catid, 'name': res[0], 'memo': res[1], 'supercatid': res[2]})
    if not cat_list:
        return
    ui = DialogSelectItems(node.app, cat_list, _("Select categories to add"), "multi")
    if not ui.exec():
        return
    selected = ui.get_selected()
    if not selected:
        return
    scene = node.scene()
    if scene is not None and getattr(scene, 'parent', None) is not None:
        if hasattr(scene.parent, '_save_undo_state'):
            scene.parent._save_undo_state()
    radius = 200
    angle_step = (2 * math.pi) / max(1, len(selected))
    for i, s in enumerate(selected):
        already_present = any(isinstance(it, TextGraphicsItem)
                              and it.code_or_cat.get('cid') is None
                              and it.code_or_cat.get('catid') == s['catid']
                              for it in scene.items())
        if already_present:
            continue
        angle = i * angle_step
        cx = node.pos().x() + radius * math.cos(angle)
        cy = node.pos().y() + radius * math.sin(angle)
        cat_data = {'name': s['name'], 'supercatid': s.get('supercatid'),
                    'catid': s['catid'], 'cid': None, 'x': cx, 'y': cy,
                    'color': '#FFFFFF', 'memo': s.get('memo', ''), 'child_names': []}
        new_node = TextGraphicsItem(node.app, cat_data)
        scene.addItem(new_node)
        line = FreeLineGraphicsItem(node, new_node, color=line_color, line_width=1, line_type="dotted")
        line.arrow_mode = "none"
        scene.addItem(line)
    # Walk up to ViewGraph to refresh
    if scene.views():
        widget = scene.views()[0].parent()
        while widget is not None:
            if hasattr(widget, 'finalize_graph_operation'):
                widget.finalize_graph_operation(fit_view=False)
                break
            widget = widget.parent()


# receiver side of the project event bus (PR #1232), rebuilt clean.
# One entry point per path: schedule() coalesces external bus events through a
# single-shot timer; sync_now() serves internal callers that need an immediate
# refresh. The SQL workers of phases 1-3 below are unchanged.
class GraphSynchronizer:
    """ Reactive synchronization for the graph view.

    Reception design:
      schedule(tables, source) <- event bus. Filters irrelevant events, accumulates
          the changed tables and arms a 200 ms single-shot timer, so bursts of
          signals (e.g. merge or auto-code emitting after several commits) run the
          pipeline ONCE, after the database has settled.
      sync_now() <- internal callers (finalize_graph_operation). Immediate run.

    Pipeline (per run):
      Phase 1: gr_* metadata in the DB, only while a saved graph is loaded
      Phase 2: in-scene items (codes, categories, segments, memos, files, cases)
      Phase 3: relations (hierarchy lines, segment lines, case/file links, visibility)
      Tail:    frequency labels (no undo snapshot) and minimap.

    Safety: never re-enters (overlapping runs are re-queued), every run is wrapped
    so one failure cannot break the dialog, and detach() stops the timer so no
    event can fire into a destroyed dialog.
    """

    RELEVANT_TABLES = {"code_cat", "code_name", "code_text", "code_image",
                       "code_av", "cases", "case_text", "source"}

    def __init__(self, view_graph):
        """ Args:
            view_graph : ViewGraph instance hosting this synchronizer.
        """
        self.vg = view_graph
        self._pending_tables = set()
        self._pending_full = False
        self._syncing = False
        self._detached = False
        # Per-run flags consumed by the pipeline
        self._code_tree_changed = True
        self._coding_changed = True
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._run_scheduled)

    # ----- Reception -----
    def schedule(self, tables=None, source=None):
        """ Event-bus entry point. Coalesces bursts into one deferred run. """
        if self._detached or source is self.vg:
            return
        if isinstance(tables, list):
            relevant = set(tables) & self.RELEVANT_TABLES
            if not relevant:
                return
            self._pending_tables.update(relevant)
        else:
            self._pending_full = True  # unknown payload: full sync
        self._timer.start()  # restart: wait until the burst settles

    def sync_now(self):
        """ Internal entry point: immediate full pipeline (no event filtering). """
        if self._detached:
            return
        self._timer.stop()
        self._pending_tables.clear()
        self._pending_full = False
        self._execute(None)

    def detach(self):
        """ Stop any pending run; called when the dialog closes. Idempotent. """
        self._detached = True
        self._timer.stop()

    def _run_scheduled(self):
        """ Timer slot: run once for everything accumulated during the burst. """
        if self._detached:
            return
        if self._syncing:
            self._timer.start()  # a run is in progress: try again shortly
            return
        tables = None if self._pending_full else set(self._pending_tables)
        self._pending_tables.clear()
        self._pending_full = False
        self._execute(tables)

    # ----- Pipeline -----
    def _execute(self, tables_set):
        """ Run the pipeline once. tables_set None means full sync. """
        if self._syncing:
            return
        self._syncing = True
        try:
            if tables_set is None:
                self._code_tree_changed = True
                self._coding_changed = True
            else:
                self._code_tree_changed = bool({"code_cat", "code_name"} & tables_set)
                self._coding_changed = bool({"code_text", "code_image", "code_av"}
                                            & tables_set)
            self._reload_codes_and_categories()
            if getattr(self.vg, 'loaded_graph', None) is not None:
                self._sync_saved_graph_metadata()
            self._refresh_scene_items()
            self._sync_lines_and_relations()
            if self.vg.show_frequencies:
                # Recount labels directly; toggling would consume an undo level
                self.vg._apply_frequency_labels()
            self.vg._refresh_minimap()
        except RuntimeError as e:
            # A scene item was deleted mid-run (dialog closing, heavy edits)
            logger.warning(f"Graph sync skipped, item no longer alive: {e}")
        except Exception as e:
            logger.error(f"Graph sync failed: {e}")
        finally:
            self._syncing = False

    def _reload_codes_and_categories(self):
        """ Reload codes/categories from DB and apply the qdpx name-collision workaround. """
        self.vg.codes, self.vg.categories = self.vg.app.get_codes_categories()
        for code in self.vg.codes:
            for cat in self.vg.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

    # ----- PHASE 1: DB metadata sync (saved-graph tables only) -----
    def _sync_saved_graph_metadata(self):
        """ Sync gr_* tables when a saved graph is currently loaded. """
        self._sync_image_areas()
        self._sync_av_segments()
        self._sync_text_codings_tooltips()
        self._sync_memo_tooltips()
        self.vg.app.conn.commit()

    def _sync_image_areas(self):
        """ Sync coding area + tooltips for gr_pix_item. """
        cur = self.vg.app.conn.cursor()
        cur.execute("update gr_pix_item set px=(select x1 from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set py=(select y1 from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set w=(select width from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set h=(select height from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("select grpixid, source.name, code_name.name, ifnull(code_image.memo,''), code_image.imid "
                    "from gr_pix_item join code_image on code_image.imid=gr_pix_item.imid "
                    "join code_name on code_name.cid=code_image.cid "
                    "join source on source.id=code_image.id")
        for r in cur.fetchall():
            tt = _("File: ") + r[1] + "\n" + _("Code: ") + r[2] + "\n"
            if self.vg.app.settings['showids']:
                tt += f"imid: {r[4]}\n"
            tt += _("Memo: ") + r[3]
            cur.execute("update gr_pix_item set tooltip=? where grpixid=?", [tt, r[0]])

    def _sync_av_segments(self):
        """ Sync coding segments + tooltips for gr_av_item. """
        cur = self.vg.app.conn.cursor()
        cur.execute("update gr_av_item set pos0=(select pos0 from code_av where code_av.avid=gr_av_item.avid)")
        cur.execute("update gr_av_item set pos1=(select pos1 from code_av where code_av.avid=gr_av_item.avid)")
        cur.execute("select gr_avid, source.name, code_name.name, gr_av_item.pos0, gr_av_item.pos1, "
                    "ifnull(code_av.memo,''), code_av.avid from gr_av_item "
                    "join code_av on code_av.avid=gr_av_item.avid "
                    "join code_name on code_name.cid=code_av.cid "
                    "join source on source.id=code_av.id")
        for r in cur.fetchall():
            tt = _("File: ") + r[1] + "\n" + _("Code: ") + r[2] + "\n" + f"{r[3]} - {r[4]}\n"
            if self.vg.app.settings['showids']:
                tt += f"avid: {r[6]}\n"
            tt += _("Memo: ") + r[5]
            cur.execute("update gr_av_item set tooltip=? where gr_avid=?", [tt, r[0]])

    def _sync_text_codings_tooltips(self):
        """ Sync tooltips for text codings stored in gr_free_text_item. """
        cur = self.vg.app.conn.cursor()
        cur.execute("select gfreeid, source.name, code_name.name, ifnull(code_text.memo,''), code_text.ctid "
                    "from gr_free_text_item "
                    "join code_text on code_text.ctid=gr_free_text_item.ctid "
                    "join code_name on code_name.cid=code_text.cid "
                    "join source on source.id=code_text.fid where gr_free_text_item.ctid > 0")
        for r in cur.fetchall():
            tt = _("File: ") + r[1] + "\n" + _("Code: ") + r[2] + "\n"
            if self.vg.app.settings['showids']:
                tt += f"ctid: {r[4]}\n"
            tt += _("Memo: ") + r[3]
            cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])

    def _sync_memo_tooltips(self):
        """ Sync tooltips for memo nodes (text/image/av memos in gr_free_text_item). """
        cur = self.vg.app.conn.cursor()
        # Memo (text)
        cur.execute("select gfreeid, source.name, code_name.name, code_text.seltext, code_text.ctid "
                    "from gr_free_text_item "
                    "join code_text on code_text.ctid=gr_free_text_item.memo_ctid "
                    "join code_name on code_name.cid=code_text.cid "
                    "join source on source.id=code_text.fid where gr_free_text_item.memo_ctid > 0")
        for r in cur.fetchall():
            tt = _("File: ") + r[1] + "\n" + _("Code: ") + r[2] + "\n"
            if self.vg.app.settings['showids']:
                tt += f"ctid: {r[4]}\n"
            tt += _("Memo for: ") + r[3]
            cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
        # Memo (image)
        cur.execute("select gfreeid, source.name, code_name.name, x1,y1,width,height, code_image.imid "
                    "from gr_free_text_item "
                    "join code_image on code_image.imid=gr_free_text_item.memo_imid "
                    "join code_name on code_name.cid=code_image.cid "
                    "join source on source.id=code_image.id where gr_free_text_item.memo_imid > 0")
        for r in cur.fetchall():
            tt = _("File: ") + r[1] + "\n" + _("Code: ") + r[2] + "\n"
            if self.vg.app.settings['showids']:
                tt += f"imid: {r[7]}\n"
            tt += _("Memo for area: ") + f"x:{int(r[3])} y:{int(r[4])} " + _("width:") + str(int(r[5])) + " " + _("height:") + str(int(r[6]))
            cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
        # Memo (A/V)
        cur.execute("select gfreeid, source.name, code_name.name, code_av.pos0, code_av.pos1, code_av.avid "
                    "from gr_free_text_item "
                    "join code_av on code_av.avid=gr_free_text_item.memo_avid "
                    "join code_name on code_name.cid=code_av.cid "
                    "join source on source.id=code_av.id where gr_free_text_item.memo_avid > 0")
        for r in cur.fetchall():
            tt = _("File: ") + r[1] + "\n" + _("Code: ") + r[2] + "\n"
            if self.vg.app.settings['showids']:
                tt += f"avid: {r[5]}\n"
            tt += _("Memo for duration: ") + f"{int(r[3])}  - {int(r[4])}" + _("msecs")
            cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])

    # ----- PHASE 2: scene items refresh -----
    def _refresh_scene_items(self):
        """ Walk all items in the scene, refresh their state from the DB,
        collect orphans, and remove them along with their connected lines. """
        cur = self.vg.app.conn.cursor()
        items_to_remove = []
        for item in self.vg.scene.items():
            if isinstance(item, TextGraphicsItem):
                if not self._refresh_text_graphics_item(item, cur):
                    items_to_remove.append(item)
            elif isinstance(item, MemoGraphicsItem):
                if not self._refresh_memo_graphics_item(item, cur):
                    items_to_remove.append(item)
            elif isinstance(item, FreeTextGraphicsItem):
                if not self._refresh_free_text_item(item, cur):
                    items_to_remove.append(item)
            elif isinstance(item, PixmapGraphicsItem):
                if not self._refresh_pixmap_item(item, cur):
                    items_to_remove.append(item)
            elif isinstance(item, AVGraphicsItem):
                if not self._refresh_av_item(item, cur):
                    items_to_remove.append(item)
            elif isinstance(item, FileTextGraphicsItem):
                if not self._refresh_file_item(item, cur):
                    items_to_remove.append(item)
            elif isinstance(item, CaseTextGraphicsItem):
                if not self._refresh_case_item(item, cur):
                    items_to_remove.append(item)
        self._remove_orphaned_items(items_to_remove)

    def _refresh_text_graphics_item(self, item, cur):
        """ Refresh a code/category node. Returns False if orphaned (must be removed). """
        cid = item.code_or_cat.get('cid')
        catid = item.code_or_cat.get('catid')
        base_name = ""
        new_memo = ""
        if cid is not None:
            # (sub-codes): also read supercid so re-parented codes stay in sync
            cur.execute("select name, color, ifnull(memo,''), catid, supercid from code_name where cid=?", [cid])
            res = cur.fetchone()
            if not res:
                return False
            item.code_or_cat['name'] = res[0]
            item.code_or_cat['color'] = res[1]
            item.code_or_cat['memo'] = res[2]
            item.code_or_cat['catid'] = res[3]
            item.code_or_cat['supercid'] = res[4]  # (sub-codes)
            item.setDefaultTextColor(QtGui.QColor(TextColor(res[1]).recommendation))
            item.setToolTip(_("Code") + ": " + res[2])
            base_name = res[0]
            new_memo = res[2]
            if self._code_tree_changed:
                for c in self.vg.codes:
                    if c['cid'] == cid:
                        item.code_or_cat['color'] = c['color']
                        item.code_or_cat['name'] = c['name']
                        item.code_or_cat['supercid'] = c.get('supercid')  # (sub-codes)
                        item.setDefaultTextColor(QtGui.QColor(TextColor(c['color']).recommendation))
                        base_name = c['name']
                        break
            item.update()
        elif catid is not None:
            cur.execute("select name, ifnull(memo,''), supercatid from code_cat where catid=?", [catid])
            res = cur.fetchone()
            if not res:
                return False
            item.code_or_cat['name'] = res[0]
            item.code_or_cat['memo'] = res[1]
            item.code_or_cat['supercatid'] = res[2]
            item.code_or_cat['child_names'] = self.vg.named_children_of_node(item.code_or_cat)
            item.setToolTip(_("Category") + ": " + res[1])
            base_name = res[0]
            new_memo = res[1]
            if self._code_tree_changed:
                for cat in self.vg.categories:
                    if cat['catid'] == catid:
                        item.code_or_cat['name'] = cat['name']
                        base_name = cat['name']
                        break
            item.update()
        if base_name:
            if "\nMEMO:" in item.text:
                item.text = f"{base_name}\nMEMO: {new_memo}"
            elif self.vg.show_frequencies:
                count_str = item.text.split('[')[-1].split(']')[0] if '[' in item.text else "0"
                item.text = f"{base_name} [{count_str}]"
            else:
                item.text = base_name
            item.setPlainText(item.text)
        return True

    def _refresh_memo_graphics_item(self, item, cur):
        """ Refresh a live memo node. Returns False if source row was deleted. """
        select_sql, _update_sql, params = item._get_sql_and_params()
        if not select_sql:
            return True
        cur.execute(select_sql, params)
        if cur.fetchone() is None:
            return False
        item._refresh_memo()
        item.update()
        return True

    def _refresh_free_text_item(self, item, cur):
        """ Refresh a coded text segment OR a legacy memo (text/image/av).
        Returns False if orphaned. """
        ctid = getattr(item, 'ctid', -1)
        memo_ctid = getattr(item, 'memo_ctid', None)
        memo_imid = getattr(item, 'memo_imid', None)
        memo_avid = getattr(item, 'memo_avid', None)
        if ctid is not None and ctid > -1:
            cur.execute("select code_name.name, code_text.seltext, ifnull(code_text.memo,''), source.name, code_text.cid "
                        "from code_text join code_name on code_text.cid=code_name.cid "
                        "join source on source.id=code_text.fid where code_text.ctid=?", [ctid])
            res = cur.fetchone()
            if not res:
                return False
            old_text = item.text
            old_width = item.textWidth()
            item.text = res[1]
            item.setTextWidth(-1)
            item.setPlainText(res[1])
            if old_width > 0:
                item.setTextWidth(old_width)
            elif item.boundingRect().width() > item.MAX_WIDTH:
                item.setTextWidth(item.MAX_WIDTH)
            msg = _("File: ") + f"{res[3]}\n" + _("Code: ") + res[0]
            if res[2] != "":
                msg += "\n" + _("Memo: ") + res[2]
            item.setToolTip(msg)
            if not hasattr(item, 'code_or_cat') or item.code_or_cat is None:
                item.code_or_cat = {'cid': None, 'catid': None}
            item.code_or_cat['name'] = res[0]
            item.code_or_cat['cid'] = res[4]
            item.check_coding()
            if old_text != item.text:
                item.prepareGeometryChange()
                item.update()
                for ln in self.vg.scene.items():
                    if isinstance(ln, (LinkGraphicsItem, FreeLineGraphicsItem)):
                        if hasattr(ln, 'from_widget') and hasattr(ln, 'to_widget'):
                            if ln.from_widget == item or ln.to_widget == item:
                                ln.redraw()
            return True
        if memo_ctid is not None and memo_ctid > -1:
            cur.execute("select ifnull(memo,'') from code_text where ctid=?", [memo_ctid])
            res = cur.fetchone()
            if not res:
                return False
            item.text = res[0]
            item.setPlainText(res[0])
            return True
        if memo_imid is not None and memo_imid > -1:
            cur.execute("select ifnull(memo,'') from code_image where imid=?", [memo_imid])
            res = cur.fetchone()
            if not res:
                return False
            item.text = res[0]
            item.setPlainText(res[0])
            return True
        if memo_avid is not None and memo_avid > -1:
            cur.execute("select ifnull(memo,'') from code_av where avid=?", [memo_avid])
            res = cur.fetchone()
            if not res:
                return False
            item.text = res[0]
            item.setPlainText(res[0])
            return True
        return True

    def _refresh_pixmap_item(self, item, cur):
        """ Refresh an image segment (with visual regeneration on geometry change). """
        imid = getattr(item, 'imid', -1)
        if imid is None or imid <= -1:
            return True
        cur.execute("select code_name.name, ifnull(code_image.memo,''), source.name, code_image.cid, x1, y1, width, height "
                    "from code_image join code_name on code_image.cid=code_name.cid "
                    "join source on source.id=code_image.id where code_image.imid=?", [imid])
        res = cur.fetchone()
        if not res:
            return False
        msg = f"IMID:{imid} " + _("File: ") + f"{res[2]}\n" + _("Code: ") + res[0]
        if res[1] != "":
            msg += "\n" + _("Memo: ") + res[1]
        item.setToolTip(msg)
        if not hasattr(item, 'code_or_cat') or item.code_or_cat is None:
            item.code_or_cat = {'cid': None, 'catid': None}
        item.code_or_cat['cid'] = res[3]
        if item.px != res[4] or item.py != res[5] or item.pwidth != res[6] or item.pheight != res[7]:
            old_width = item.boundingRect().width()
            item.px, item.py, item.pwidth, item.pheight = res[4], res[5], res[6], res[7]
            try:
                abs_path_ = item.app.project_path + item.path_
                if item.path_[0:7] == "images:":
                    abs_path_ = item.path_[7:]
                if item.pdf_page is not None:
                    source_path = ""
                    if item.path_[:6] == "/docs/":
                        source_path = f"{item.app.project_path}/documents/{item.path_[6:]}"
                    elif item.path_[:5] == "docs:":
                        source_path = item.path_[5:]
                    if os.path.exists(source_path):
                        fitz_pdf = fitz.open(source_path)
                        page = fitz_pdf[item.pdf_page]
                        pixmap_pdf = page.get_pixmap(annots=False)  # PDF highlights/notes not painted
                        abs_path_ = os.path.join(item.app.confighome, "tmp_pdf_page.png")
                        pixmap_pdf.save(abs_path_)
                        fitz_pdf.close()
                if os.path.exists(abs_path_):
                    image = QtGui.QImageReader(abs_path_).read()
                    image = image.copy(int(item.px), int(item.py), int(item.pwidth), int(item.pheight))
                    scaler_w = 200 / image.width() if image.width() > 200 else 1.0
                    scaler_h = 200 / image.height() if image.height() > 200 else 1.0
                    scaler = min(scaler_w, scaler_h)
                    pixmap = QtGui.QPixmap().fromImage(image)
                    pixmap = pixmap.scaled(int(image.width() * scaler), int(image.height() * scaler))
                    item.setPixmap(pixmap)
                    item._original_pixmap = item.pixmap()
                    if old_width > 0 and old_width != item.boundingRect().width():
                        scale_factor = old_width / item._original_pixmap.width()
                        scaled = item._original_pixmap.scaled(
                            int(item._original_pixmap.width() * scale_factor),
                            int(item._original_pixmap.height() * scale_factor),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                            QtCore.Qt.TransformationMode.SmoothTransformation)
                        item.setPixmap(scaled)
                    item.update()
            except Exception as e:
                logger.error(f"Error regenerating pixmap in GraphSynchronizer: {e}")
        return True

    def _refresh_av_item(self, item, cur):
        """ Refresh an A/V segment. """
        avid = getattr(item, 'avid', -1)
        if avid is None or avid <= -1:
            return True
        cur.execute("select code_name.name, ifnull(code_av.memo,''), source.name, code_av.pos0, code_av.pos1, code_av.cid "
                    "from code_av join code_name on code_av.cid=code_name.cid "
                    "join source on source.id=code_av.id where code_av.avid=?", [avid])
        res = cur.fetchone()
        if not res:
            return False
        old_pos0, old_pos1 = item.pos0, item.pos1
        item.pos0, item.pos1 = res[3], res[4]
        msg = f"AVID:{avid} " + _("File: ") + f"{res[2]}\n" + _("Code: ") + res[0]
        msg += f"\n{res[3]} - {res[4]} " + _("msecs")
        if res[1] != "":
            msg += "\n" + _("Memo: ") + res[1]
        item.setToolTip(msg)
        if not hasattr(item, 'code_or_cat') or item.code_or_cat is None:
            item.code_or_cat = {'cid': None, 'catid': None}
        item.code_or_cat['cid'] = res[5]
        if old_pos0 != item.pos0 or old_pos1 != item.pos1:
            item.text = f"AVID:{avid}"
            item.update()
        return True

    def _refresh_file_item(self, item, cur):
        """ Verify file still exists in `source`. """
        fid = getattr(item, 'file_id', -1)
        if fid is None or fid <= -1:
            return True
        cur.execute("select id from source where id=?", [fid])
        return cur.fetchone() is not None

    def _refresh_case_item(self, item, cur):
        """ Verify case still exists in `cases`. """
        ca_id = getattr(item, 'case_id', -1)
        if ca_id is None or ca_id <= -1:
            return True
        cur.execute("select caseid from cases where caseid=?", [ca_id])
        return cur.fetchone() is not None

    def _remove_orphaned_items(self, items_to_remove):
        """ Remove orphaned nodes and all their connected lines. """
        for item in items_to_remove:
            for line in list(self.vg.scene.items()):
                if type(line).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if getattr(line, 'from_widget', None) == item or getattr(line, 'to_widget', None) == item:
                        self.vg.scene.removeItem(line)
            if item.scene() == self.vg.scene:
                self.vg.scene.removeItem(item)

    # ----- PHASE 3: lines and relations -----
    def _sync_lines_and_relations(self):
        """ Synchronize hierarchical and segment-to-code lines, then case/file links,
        and finally update line visibility based on endpoint visibility. """
        self._sync_hierarchical_lines()
        self._sync_segment_to_code_lines()
        self._sync_case_and_file_links()
        self._sync_line_visibility()

    def _sync_hierarchical_lines(self):
        """ Sync LinkGraphicsItem lines: category->category, code->category and
        sub-code->parent code (supercid). """
        text_nodes = [n for n in self.vg.scene.items() if isinstance(n, TextGraphicsItem)]

        # (sub-codes): a code may be the parent of another code via supercid
        def is_parent_child(c, p):
            if p.code_or_cat.get('cid') is not None:
                # Parent is a code: child must be a sub-code pointing to it
                return c.code_or_cat.get('cid') is not None and \
                    c.code_or_cat.get('supercid') is not None and \
                    c.code_or_cat.get('supercid') == p.code_or_cat.get('cid')
            p_catid = p.code_or_cat.get('catid')
            if c.code_or_cat.get('cid') is not None:
                if c.code_or_cat.get('supercid'):
                    return False  # Sub-codes hang from their parent code, not from the category
                return c.code_or_cat.get('catid') == p_catid
            return c.code_or_cat.get('supercatid') == p_catid and c.code_or_cat.get('supercatid') is not None

        # Prune obsolete hierarchical lines
        for line in list(self.vg.scene.items()):
            if type(line).__name__ == "LinkGraphicsItem":
                fw = line.from_widget
                tw = line.to_widget
                if isinstance(fw, TextGraphicsItem) and isinstance(tw, TextGraphicsItem):
                    if getattr(line, 'label', '') != '':
                        continue
                    if not (is_parent_child(fw, tw) or is_parent_child(tw, fw)):
                        self.vg.scene.removeItem(line)
        # Add missing hierarchical lines
        # (sub-codes): resolve the parent as code (supercid) or category
        for child in text_nodes:
            parent_node = None
            child_cid = child.code_or_cat.get('cid')
            child_supercid = child.code_or_cat.get('supercid') if child_cid is not None else None
            if child_supercid is not None:
                parent_node = next((n for n in text_nodes
                                    if n.code_or_cat.get('cid') == child_supercid), None)
            else:
                parent_catid = child.code_or_cat.get('catid') if child_cid is not None \
                    else child.code_or_cat.get('supercatid')
                if parent_catid is not None:
                    parent_node = next((n for n in text_nodes
                                        if n.code_or_cat.get('cid') is None
                                        and n.code_or_cat.get('catid') == parent_catid), None)
            if parent_node:
                line_exists = any(type(line).__name__ == "LinkGraphicsItem" and
                                  ((line.from_widget == child and line.to_widget == parent_node) or
                                   (line.from_widget == parent_node and line.to_widget == child))
                                  for line in self.vg.scene.items())
                if not line_exists:
                    new_line = LinkGraphicsItem(child, parent_node, 2, "solid", "gray",
                                                child.isVisible() and parent_node.isVisible())
                    self.vg.scene.addItem(new_line)

    def _sync_segment_to_code_lines(self):
        """ Sync FreeLineGraphicsItem lines between coded segments and their code nodes. """
        segment_types = ("FreeTextGraphicsItem", "PixmapGraphicsItem", "AVGraphicsItem")
        text_nodes = [n for n in self.vg.scene.items() if isinstance(n, TextGraphicsItem)]
        # Prune obsolete segment-to-code lines
        for line in list(self.vg.scene.items()):
            if type(line).__name__ == "FreeLineGraphicsItem":
                fw = getattr(line, 'from_widget', None)
                tw = getattr(line, 'to_widget', None)
                if not (fw and tw):
                    continue
                is_seg_fw = type(fw).__name__ in segment_types
                is_code_tw = type(tw).__name__ == "TextGraphicsItem" and tw.code_or_cat.get('cid') is not None
                is_seg_tw = type(tw).__name__ in segment_types
                is_code_fw = type(fw).__name__ == "TextGraphicsItem" and fw.code_or_cat.get('cid') is not None
                if (is_seg_fw and is_code_tw) or (is_seg_tw and is_code_fw):
                    if (getattr(line, 'label', '') or '') != '':
                        continue
                    seg = fw if is_seg_fw else tw
                    code = tw if is_code_tw else fw
                    seg_cid = seg.code_or_cat.get('cid') if hasattr(seg, 'code_or_cat') and seg.code_or_cat else None
                    if seg_cid is not None and code.code_or_cat.get('cid') != seg_cid:
                        keep_line = False
                        code_cid = code.code_or_cat.get('cid')
                        cur_c = self.vg.app.conn.cursor()
                        if type(seg).__name__ == "FreeTextGraphicsItem" and getattr(seg, 'ctid', -1) > 0:
                            cur_c.execute("select ct1.fid, ct1.pos0, ct1.pos1 from code_text ct1 where ct1.ctid=?", [seg.ctid])
                            seg_info = cur_c.fetchone()
                            if seg_info:
                                cur_c.execute("select count(*) from code_text where fid=? and cid=? and pos0 < ? and pos1 > ?",
                                              [seg_info[0], code_cid, seg_info[2], seg_info[1]])
                                if cur_c.fetchone()[0] > 0:
                                    keep_line = True
                        elif type(seg).__name__ == "PixmapGraphicsItem" and getattr(seg, 'imid', -1) > 0:
                            cur_c.execute("select id, x1, y1, width, height from code_image where imid=?", [seg.imid])
                            seg_info = cur_c.fetchone()
                            if seg_info:
                                cur_c.execute("select count(*) from code_image where id=? and cid=? "
                                              "and x1 < ? and (x1+width) > ? and y1 < ? and (y1+height) > ?",
                                              [seg_info[0], code_cid,
                                               seg_info[1] + seg_info[3], seg_info[1],
                                               seg_info[2] + seg_info[4], seg_info[2]])
                                if cur_c.fetchone()[0] > 0:
                                    keep_line = True
                        elif type(seg).__name__ == "AVGraphicsItem" and getattr(seg, 'avid', -1) > 0:
                            cur_c.execute("select id, pos0, pos1 from code_av where avid=?", [seg.avid])
                            seg_info = cur_c.fetchone()
                            if seg_info:
                                cur_c.execute("select count(*) from code_av where id=? and cid=? and pos0 < ? and pos1 > ?",
                                              [seg_info[0], code_cid, seg_info[2], seg_info[1]])
                                if cur_c.fetchone()[0] > 0:
                                    keep_line = True
                        if not keep_line:
                            self.vg.scene.removeItem(line)
        # Add missing segment-to-code lines
        segment_nodes = [n for n in self.vg.scene.items() if type(n).__name__ in segment_types]
        for seg in segment_nodes:
            is_real_segment = False
            if type(seg).__name__ == "FreeTextGraphicsItem" and getattr(seg, 'ctid', -1) > 0:
                is_real_segment = True
            elif type(seg).__name__ == "PixmapGraphicsItem" and getattr(seg, 'imid', -1) > 0:
                is_real_segment = True
            elif type(seg).__name__ == "AVGraphicsItem" and getattr(seg, 'avid', -1) > 0:
                is_real_segment = True
            if not is_real_segment:
                continue
            seg_cid = seg.code_or_cat.get('cid') if hasattr(seg, 'code_or_cat') and seg.code_or_cat else None
            if seg_cid is None:
                continue
            code_node = next((n for n in text_nodes if n.code_or_cat.get('cid') == seg_cid), None)
            if not code_node:
                continue
            line_exists = any(type(line).__name__ == "FreeLineGraphicsItem" and
                              ((line.from_widget == seg and line.to_widget == code_node) or
                               (line.from_widget == code_node and line.to_widget == seg))
                              for line in self.vg.scene.items())
            if not line_exists:
                new_line = FreeLineGraphicsItem(code_node, seg, line_width=2, line_type="dotted", color="gray")
                if not code_node.isVisible():
                    new_line.hide()
                    seg.hide()
                self.vg.scene.addItem(new_line)

    def _sync_case_and_file_links(self):
        """ Auto-link Case/File nodes to code nodes (and category nodes) based on coded contents.
        Removes obsolete connections and adds missing ones. """
        cur = self.vg.app.conn.cursor()
        case_nodes = [n for n in self.vg.scene.items() if type(n).__name__ == "CaseTextGraphicsItem"]
        file_nodes = [n for n in self.vg.scene.items() if type(n).__name__ == "FileTextGraphicsItem"]
        code_nodes = [n for n in self.vg.scene.items()
                      if type(n).__name__ == "TextGraphicsItem" and n.code_or_cat.get('cid') is not None]
        # Remove obsolete Case/File <-> Code lines
        for line in list(self.vg.scene.items()):
            if type(line).__name__ == "FreeLineGraphicsItem":
                fw = getattr(line, 'from_widget', None)
                tw = getattr(line, 'to_widget', None)
                if not (fw and tw):
                    continue
                is_case_fw = type(fw).__name__ == "CaseTextGraphicsItem"
                is_code_tw = type(tw).__name__ == "TextGraphicsItem" and tw.code_or_cat.get('cid') is not None
                is_case_tw = type(tw).__name__ == "CaseTextGraphicsItem"
                is_code_fw = type(fw).__name__ == "TextGraphicsItem" and fw.code_or_cat.get('cid') is not None
                if (is_case_fw and is_code_tw) or (is_case_tw and is_code_fw):
                    case_node = fw if is_case_fw else tw
                    code_node = tw if is_code_tw else fw
                    sql = ("select sum(c) from ("
                           "select count(ct.cid) as c from code_text ct "
                           "join case_text cas on cas.fid=ct.fid "
                           "and ct.pos0 >= cas.pos0 and ct.pos1 <= cas.pos1 "
                           "where cas.caseid=? and ct.cid=? "
                           "union all select count(ci.cid) as c from code_image ci "
                           "join case_text cas on cas.fid=ci.id where cas.caseid=? and ci.cid=? "
                           "union all select count(cav.cid) as c from code_av cav "
                           "join case_text cas on cas.fid=cav.id where cas.caseid=? and cav.cid=? )")
                    caseid = case_node.case_id
                    cid = code_node.code_or_cat.get('cid')
                    cur.execute(sql, [caseid, cid, caseid, cid, caseid, cid])
                    res = cur.fetchone()
                    if not res or res[0] is None or res[0] == 0:
                        self.vg.scene.removeItem(line)
                is_file_fw = type(fw).__name__ == "FileTextGraphicsItem"
                is_file_tw = type(tw).__name__ == "FileTextGraphicsItem"
                if (is_file_fw and is_code_tw) or (is_file_tw and is_code_fw):
                    file_node = fw if is_file_fw else tw
                    code_node = tw if is_code_tw else fw
                    sql_files = ("select sum(c) from ("
                                 "select count(cid) as c from code_text where fid=? and cid=? "
                                 "union all select count(cid) as c from code_image where id=? and cid=? "
                                 "union all select count(cid) as c from code_av where id=? and cid=? )")
                    fid = file_node.file_id
                    cid = code_node.code_or_cat.get('cid')
                    cur.execute(sql_files, [fid, cid, fid, cid, fid, cid])
                    res = cur.fetchone()
                    if not res or res[0] is None or res[0] == 0:
                        self.vg.scene.removeItem(line)
        # Cases -> Codes
        for case_node in case_nodes:
            cur.execute("select distinct ct.cid from code_text ct "
                        "join case_text cas on cas.fid=ct.fid "
                        "and ct.pos0 >= cas.pos0 and ct.pos1 <= cas.pos1 where cas.caseid=?", [case_node.case_id])
            case_cids = {r[0] for r in cur.fetchall()}
            for code_node in code_nodes:
                cid = code_node.code_or_cat.get('cid')
                if cid in case_cids:
                    line_exists = any(type(item).__name__ == "FreeLineGraphicsItem" and
                                      ((item.from_widget == case_node and item.to_widget == code_node) or
                                       (item.from_widget == code_node and item.to_widget == case_node))
                                      for item in self.vg.scene.items())
                    if not line_exists:
                        line = FreeLineGraphicsItem(case_node, code_node, color="orange",
                                                    line_width=1, line_type="dotted")
                        if not code_node.isVisible():
                            line.hide()
                        self.vg.scene.addItem(line)
        # Files -> Codes
        for file_node in file_nodes:
            cur.execute("select distinct cid from code_text where fid=? "
                        "union select distinct cid from code_image where id=? "
                        "union select distinct cid from code_av where id=?",
                        [file_node.file_id, file_node.file_id, file_node.file_id])
            file_cids = {r[0] for r in cur.fetchall()}
            for code_node in code_nodes:
                cid = code_node.code_or_cat.get('cid')
                if cid in file_cids:
                    line_exists = any(type(item).__name__ == "FreeLineGraphicsItem" and
                                      ((item.from_widget == file_node and item.to_widget == code_node) or
                                       (item.from_widget == code_node and item.to_widget == file_node))
                                      for item in self.vg.scene.items())
                    if not line_exists:
                        line = FreeLineGraphicsItem(file_node, code_node, color="blue",
                                                    line_width=1, line_type="dotted")
                        if not code_node.isVisible():
                            line.hide()
                        self.vg.scene.addItem(line)
        # Cases/Files -> Categories
        cat_nodes = [n for n in self.vg.scene.items()
                     if type(n).__name__ == "TextGraphicsItem"
                     and n.code_or_cat.get('cid') is None
                     and n.code_or_cat.get('catid') is not None]
        for case_node in case_nodes:
            cur.execute("select distinct cn.catid from code_name cn where cn.catid is not null and cn.cid in "
                        "(select distinct ct.cid from code_text ct "
                        "join case_text cas on cas.fid=ct.fid "
                        "and ct.pos0 >= cas.pos0 and ct.pos1 <= cas.pos1 where cas.caseid=?)",
                        [case_node.case_id])
            case_catids = {r[0] for r in cur.fetchall()}
            for cat_node in cat_nodes:
                if cat_node.code_or_cat.get('catid') in case_catids:
                    line_exists = any(type(item).__name__ == "FreeLineGraphicsItem" and
                                      ((item.from_widget == case_node and item.to_widget == cat_node) or
                                       (item.from_widget == cat_node and item.to_widget == case_node))
                                      for item in self.vg.scene.items())
                    if not line_exists:
                        line = FreeLineGraphicsItem(case_node, cat_node, color="orange",
                                                    line_width=1, line_type="dotted")
                        line.arrow_mode = "none"
                        if not cat_node.isVisible():
                            line.hide()
                        self.vg.scene.addItem(line)
        for file_node in file_nodes:
            cur.execute("select distinct cn.catid from code_name cn where cn.catid is not null and cn.cid in "
                        "(select distinct cid from code_text where fid=? "
                        "union select distinct cid from code_image where id=? "
                        "union select distinct cid from code_av where id=?)",
                        [file_node.file_id, file_node.file_id, file_node.file_id])
            file_catids = {r[0] for r in cur.fetchall()}
            for cat_node in cat_nodes:
                if cat_node.code_or_cat.get('catid') in file_catids:
                    line_exists = any(type(item).__name__ == "FreeLineGraphicsItem" and
                                      ((item.from_widget == file_node and item.to_widget == cat_node) or
                                       (item.from_widget == cat_node and item.to_widget == file_node))
                                      for item in self.vg.scene.items())
                    if not line_exists:
                        line = FreeLineGraphicsItem(file_node, cat_node, color="blue",
                                                    line_width=1, line_type="dotted")
                        line.arrow_mode = "none"
                        if not cat_node.isVisible():
                            line.hide()
                        self.vg.scene.addItem(line)

    def _sync_line_visibility(self):
        """ Update line visibility based on endpoint visibility, and redraw if coding changed. """
        for item in self.vg.scene.items():
            if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                    if not item.from_widget.isVisible() or not item.to_widget.isVisible():
                        item.hide()
                    else:
                        item.show()
        for item in self.vg.scene.items():
            if isinstance(item, FreeTextGraphicsItem):
                item.check_coding()
        if self._coding_changed:
            for item in self.vg.scene.items():
                if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                    if hasattr(item, 'redraw'):
                        item.redraw()


class DialogSelectCodedSegments(QDialog):
    """ Unified window to select coded segments from text, image, and A/V.
    Displays three lists (QListWidget) in a single interface. """

    def __init__(self, app, code_name, text_codings, image_codings, av_codings, parent=None):
        """
        param: app : Main App
        param: code_name : String - code name
        param: text_codings : list of dict with keys: name, cid, fid, memo, ctid, filename, codename
        param: image_codings : list of dict with keys: name, cid, fid, memo, imid, filename, codename, x, y, width, height, path, pdf_page
        param: av_codings : list of dict with keys: name, cid, fid, memo, avid, filename, codename, pos0, pos1, path
        """
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(f"Import coded segments: {code_name}")
        self.setMinimumSize(700, 520)
        self.text_codings = text_codings
        self.image_codings = image_codings
        self.av_codings = av_codings
        self.selected_text = []
        self.selected_image = []
        self.selected_av = []

        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)

        layout = QtWidgets.QVBoxLayout(self)

        # --- TEXT section
        label_text = QtWidgets.QLabel(f"Text segments ({len(text_codings)})")
        label_text.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(label_text)
        self.list_text = QtWidgets.QListWidget()
        self.list_text.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        for tc in text_codings:
            display = tc['name']
            if len(display) > 120:
                display = display[:120] + "..."
            display = f"[{tc['filename']}] {display}"
            item = QtWidgets.QListWidgetItem(display)
            item.setToolTip(f"File: {tc['filename']}\n{tc['name'][:300]}")
            self.list_text.addItem(item)
        layout.addWidget(self.list_text, stretch=3)

        # --- Bottom horizontal section: IMAGE and A/V side by side
        h_layout = QtWidgets.QHBoxLayout()

        # --- IMAGE sub-section
        v_img = QtWidgets.QVBoxLayout()
        label_img = QtWidgets.QLabel(f"Image segments ({len(image_codings)})")
        label_img.setStyleSheet("font-weight: bold; margin-top: 4px;")
        v_img.addWidget(label_img)
        self.list_image = QtWidgets.QListWidget()
        self.list_image.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        for ic in image_codings:
            display = f"[{ic['filename']}] x:{ic['x']} y:{ic['y']} w:{ic['width']} h:{ic['height']}"
            item = QtWidgets.QListWidgetItem(display)
            item.setToolTip(
                f"File: {ic['filename']}\nArea: x:{ic['x']} y:{ic['y']} width:{ic['width']} height:{ic['height']}")
            self.list_image.addItem(item)
        v_img.addWidget(self.list_image)
        h_layout.addLayout(v_img)

        # --- A/V sub-section
        v_av = QtWidgets.QVBoxLayout()
        label_av = QtWidgets.QLabel(f"A/V segments ({len(av_codings)})")
        label_av.setStyleSheet("font-weight: bold; margin-top: 4px;")
        v_av.addWidget(label_av)
        self.list_av = QtWidgets.QListWidget()
        self.list_av.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        for ac in av_codings:
            display = f"[{ac['filename']}] {ac['pos0']} - {ac['pos1']} msecs"
            item = QtWidgets.QListWidgetItem(display)
            item.setToolTip(f"File: {ac['filename']}\nDuration: {ac['pos0']} - {ac['pos1']} msecs")
            self.list_av.addItem(item)
        v_av.addWidget(self.list_av)
        h_layout.addLayout(v_av)

        layout.addLayout(h_layout, stretch=2)

        # --- Select All / Import / Cancel buttons
        btn_layout = QtWidgets.QHBoxLayout()

        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_select_all.clicked.connect(self.select_all)
        btn_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = QtWidgets.QPushButton("Deselect All")
        self.btn_deselect_all.clicked.connect(self.deselect_all)
        btn_layout.addWidget(self.btn_deselect_all)

        btn_layout.addStretch()

        self.btn_import = QtWidgets.QPushButton("Import selected")
        self.btn_import.setDefault(True)
        self.btn_import.clicked.connect(self.do_import)
        btn_layout.addWidget(self.btn_import)

        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def select_all(self):
        self.list_text.selectAll()
        self.list_image.selectAll()
        self.list_av.selectAll()

    def deselect_all(self):
        self.list_text.clearSelection()
        self.list_image.clearSelection()
        self.list_av.clearSelection()

    def do_import(self):
        self.selected_text = [self.text_codings[idx.row()] for idx in self.list_text.selectedIndexes()]
        self.selected_image = [self.image_codings[idx.row()] for idx in self.list_image.selectedIndexes()]
        self.selected_av = [self.av_codings[idx.row()] for idx in self.list_av.selectedIndexes()]
        if not self.selected_text and not self.selected_image and not self.selected_av:
            return
        self.accept()


class ViewGraph(QDialog):
    """ Dialog to view code and categories in an acyclic graph. Provides options for
    colors and amount of nodes to display (based on category selection).
    """

    app = None
    conn = None
    settings = None
    scene = None
    categories = []
    codes = []
    font_size = 9
    load_graph_menu_option = "Alphabet ascending"

    def __init__(self, app):
        """ Set up the dialog. """

        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogGraph()
        self.ui.setupUi(self)
        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.pushButton_export_pdf.setIcon(qta.icon('mdi6.file-pdf-box', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export_pdf.pressed.connect(self.export_pdf_graph)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.image-move', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export.pressed.connect(self.export_image)
        self.ui.pushButton_export_drawio.setIcon(qta.icon('mdi6.sitemap', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_export_drawio.pressed.connect(self.export_drawio)
        self.ui.label_zoom.setPixmap(qta.icon('mdi6.magnify').pixmap(22, 22))
        self.ui.pushButton_reveal.setIcon(qta.icon('mdi6.eye', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_reveal.pressed.connect(self.reveal_hidden_items)
        # icon changed 'undo' -> 'reload'; pushButton_undo_changes now owns undo
        self.ui.pushButton_clear.setIcon(qta.icon('mdi6.reload', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_clear.pressed.connect(self.clear_items)
        self.ui.pushButton_selectbranch.setIcon(qta.icon('mdi6.file-tree', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_selectbranch.pressed.connect(self.select_tree_branch)
        self.ui.pushButton_freetextitem.setIcon(qta.icon('mdi6.text-box-edit-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_freetextitem.pressed.connect(self.add_text_item_to_graph)
        self.ui.pushButton_addfile.setIcon(qta.icon('mdi6.file-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_addfile.pressed.connect(self.add_files_to_graph)
        self.ui.pushButton_addcase.setIcon(qta.icon('mdi6.briefcase-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_addcase.pressed.connect(self.add_cases_to_graph)
        self.ui.pushButton_addline.setIcon(qta.icon('mdi6.chart-line-variant', options=[{'scale_factor': 1.4}]))
        # dialog-based connection, complementary to the drag-to-connect handles
        self.ui.pushButton_addline.setCheckable(False)
        self.ui.pushButton_addline.setToolTip(_("Add relationship line"))
        self.ui.pushButton_addline.pressed.connect(self.add_lines_to_graph)
        self.ui.pushButton_loadgraph.setIcon(qta.icon('mdi6.file-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_loadgraph.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.pushButton_loadgraph.customContextMenuRequested.connect(self.load_graph_menu)
        self.ui.pushButton_loadgraph.pressed.connect(self.load_graph)
        self.ui.pushButton_savegraph.setIcon(qta.icon('mdi6.file-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_savegraph.pressed.connect(self.save_graph)
        self.ui.pushButton_deletegraph.setIcon(qta.icon('mdi6.file-minus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_deletegraph.pressed.connect(self.delete_saved_graph)
        self.ui.pushButton_codes_of_text.setIcon(qta.icon('mdi6.text', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_codes_of_text.pressed.connect(self.add_coded_text_of_text_files)
        if not self.app.get_image_and_pdf_filenames():
            self.ui.pushButton_codes_of_images.setEnabled(False)
        self.ui.pushButton_codes_of_images.setIcon(qta.icon('mdi6.image-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_codes_of_images.pressed.connect(self.add_codes_of_image_files)
        if not self.app.get_av_filenames():
            self.ui.pushButton_codes_of_av.setEnabled(False)
        self.ui.pushButton_codes_of_av.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_codes_of_av.pressed.connect(self.add_codes_of_av_files)
        self.ui.pushButton_memos_of_file.setIcon(qta.icon('mdi6.text-long', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_memos_of_file.pressed.connect(self.add_memos_of_coded)
        # Graph Models dialog (analytical model generators)
        self.ui.pushButton_graph_models.setIcon(qta.icon('mdi6.hubspot', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_graph_models.pressed.connect(self.open_graph_models)
        # Organize graph dialog (radial / hierarchical / LR / RL)
        self.ui.pushButton_org_graph.setIcon(qta.icon('mdi6.auto-fix', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_org_graph.pressed.connect(self.open_organization_menu)
        # Minimap toggle (checkable, syncs both directions via _on_minimap_toggled)
        self.ui.pushButton_minimap.setIcon(qta.icon('mdi6.picture-in-picture-bottom-right', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_minimap.setCheckable(True)
        self.ui.pushButton_minimap.toggled.connect(self._on_minimap_toggled)
        # alignment and distribution of selected nodes
        self.ui.pushButton_align_vertical.setIcon(qta.icon('mdi6.align-vertical-center', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_align_vertical.pressed.connect(lambda: self.align_selected("vertical"))
        self.ui.pushButton_align_horizontal.setIcon(qta.icon('mdi6.align-horizontal-center', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_align_horizontal.pressed.connect(lambda: self.align_selected("horizontal"))
        self.ui.pushButton_distribute_vertical.setIcon(qta.icon('mdi6.distribute-vertical-center', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_distribute_vertical.pressed.connect(lambda: self.distribute_selected("vertical"))
        self.ui.pushButton_distribute_horizontal.setIcon(qta.icon('mdi6.distribute-horizontal-center', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_distribute_horizontal.pressed.connect(lambda: self.distribute_selected("horizontal"))
        # scale graph (expand / compact)
        self.ui.pushButton_expand_graph.setIcon(qta.icon('mdi6.arrow-expand-all', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_expand_graph.pressed.connect(lambda: self._scale_graph(1.10))
        self.ui.pushButton_compact_graph.setIcon(qta.icon('mdi6.arrow-collapse-all', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_compact_graph.pressed.connect(lambda: self._scale_graph(0.90))
        # remove selected nodes (with their connected lines)
        self.ui.pushButton_remove_nodes.setIcon(qta.icon('mdi6.delete-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_remove_nodes.pressed.connect(self.remove_selected_nodes)
        self.ui.pushButton_remove_nodes.setToolTip(_("Remove selected items from the graph"))
        # export analytical summary (.odt)
        self.ui.pushButton_export_graph_summary.setIcon(qta.icon('mdi6.file-document-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_export_graph_summary.pressed.connect(self.export_graph_summary)
        self.ui.pushButton_export_graph_summary.setToolTip(_("Export graph summary"))
        # undo last change (3 level depth)
        self.ui.pushButton_undo_changes.setIcon(qta.icon('mdi6.undo', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_undo_changes.pressed.connect(self.undo_last_change)
        self.ui.pushButton_undo_changes.setToolTip(_("Undo last change"))

        # Set the scene
        # pass self as parent so GraphicsScene.parent points to this dialog,
        # activating drag-undo snapshots and item-menu undo (both check scene.parent).
        self.scene = GraphicsScene(self)
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)
        # Multi-selection drag and hold.
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        self.codes, self.categories = app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "
        # Variables to control canvas dragging
        self._space_pressed = False
        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        self.show_frequencies = False  # Coded segment frequencies
        # undo history stack (scene snapshots, full visual + structural state)
        self._undo_stack = []
        self._undo_max_depth = 3  # 3 undo levels
        # minimap state
        self._minimap_widget = None
        self._minimap_visible = False
        # connection-drag state machine ('idle' | 'dragging_preview')
        self._connect_mode = False
        self._right_press_selection = []  # multi-selection snapshot for the context menu
        self._connect_state = 'idle'
        self._connect_source = None
        self._connect_preview_pos = None

        # connect to project_data_changed; fallback supports older app builds
        # where the signal lives directly on self.app. Connection target tracked for cleanup.
        self._event_bus_signal = None
        if hasattr(self.app, 'project_events'):
            self.app.project_events.project_data_changed.connect(self._on_project_data_changed)
            self._event_bus_signal = self.app.project_events.project_data_changed
        elif hasattr(self.app, 'project_data_changed'):
            self.app.project_data_changed.connect(self._on_project_data_changed)
            self._event_bus_signal = self.app.project_data_changed
        # loaded graph reference (None until load_graph is called)
        self.loaded_graph = None
        # centralized synchronizer; all reactive sync logic lives in GraphSynchronizer
        self._synchronizer = GraphSynchronizer(self)

    def clear_items(self):
        """ Clear all items from scene.
        Called by pushButton_clear. """

        msg = _("Are you sure you want to clear the graph?")
        ui = DialogConfirmDelete(self.app, msg)
        ok = ui.exec()
        if not ok:
            return
        self._save_undo_state()  # snapshot before clearing
        self.scene.clear()
        self.scene.set_width(990)
        self.scene.set_height(650)
        self.ui.label_loaded_graph.setText("")
        self.ui.label_loaded_graph.setToolTip("")
        # clear loaded_graph so Phase 1 of the synchronizer skips DB sync
        self.loaded_graph = None

    def remove_selected_nodes(self):
        """ Remove every selected node and its connected lines, with undo snapshot.
        Equivalent to pressing Delete with selection. """

        selected = self.scene.selectedItems()
        if not selected:
            Message(self.app, _("No selection"), _("No items selected to remove.")).exec()
            return
        ui_confirm = DialogConfirmDelete(self.app, _("Remove selected items from the graph?"))
        if not ui_confirm.exec():
            return
        self._save_undo_state()
        for item in selected:
            item.remove = True
            # remove connected lines first to avoid orphan references
            for line in list(self.scene.items()):
                if type(line).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if getattr(line, 'from_widget', None) == item or getattr(line, 'to_widget', None) == item:
                        if line.scene() == self.scene:
                            self.scene.removeItem(line)
            if item.scene() == self.scene:
                self.scene.removeItem(item)
        self.scene.update()

    def _save_undo_state(self):
        """ Capture a full snapshot of the scene state and push it (3 undo levels). """

        self._push_undo_snapshot(self._build_undo_snapshot())

    def _push_undo_snapshot(self, snapshot):
        """ Append a snapshot honouring the 3-level depth limit. """

        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._undo_max_depth:
            self._undo_stack.pop(0)

    def _build_undo_snapshot(self):
        """ Capture a full snapshot of the scene state for undo.
        Stores positions, visibility, visual properties and structural attributes
        of every node and line so undo can fully revert any kind of change. """

        snapshot = {'nodes': [], 'lines': []}
        for item in self.scene.items():
            cls_name = type(item).__name__
            # Nodes
            if cls_name in ("TextGraphicsItem", "FreeTextGraphicsItem", "CaseTextGraphicsItem",
                            "FileTextGraphicsItem", "PixmapGraphicsItem", "AVGraphicsItem",
                            "MemoGraphicsItem"):
                node_data = {
                    'class': cls_name,
                    'item_ref': item,
                    'pos': (item.pos().x(), item.pos().y()),
                    'visible': item.isVisible(),
                    'in_scene': item.scene() == self.scene,
                }
                if hasattr(item, 'code_or_cat') and item.code_or_cat is not None:
                    node_data['code_or_cat'] = deepcopy(item.code_or_cat)
                for attr in ('text', 'color', 'font_size', 'bold', 'is_ellipse',
                             'is_collapsed', 'show_attributes'):
                    if hasattr(item, attr):
                        try:
                            node_data[attr] = getattr(item, attr)
                        except Exception:
                            pass
                if hasattr(item, 'textWidth'):
                    try:
                        node_data['text_width'] = item.textWidth()
                    except Exception:
                        pass
                if cls_name in ("PixmapGraphicsItem", "AVGraphicsItem"):
                    try:
                        if hasattr(item, 'pixmap') and item.pixmap() is not None:
                            pm = item.pixmap()
                            node_data['pixmap_size'] = (pm.width(), pm.height())
                    except Exception:
                        pass
                snapshot['nodes'].append(node_data)
            # Lines
            elif cls_name in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                    line_data = {
                        'class': cls_name,
                        'item_ref': item,
                        'from_widget': item.from_widget,
                        'to_widget': item.to_widget,
                        'visible': item.isVisible(),
                        'in_scene': item.scene() == self.scene,
                    }
                    for attr in ('color', 'line_width', 'line_type', 'arrow_mode',
                                 'label', '_is_cooc_line'):
                        if hasattr(item, attr):
                            try:
                                line_data[attr] = getattr(item, attr)
                            except Exception:
                                pass
                    snapshot['lines'].append(line_data)
        return snapshot

    def undo_last_change(self):
        """ Restore the most recent snapshot (visual + structural).
        Robust against removed/destroyed items via _is_alive probe; nodes restored before lines. """

        if not self._undo_stack:
            Message(self.app, _("Nothing to undo"), _("No previous changes to undo.")).exec()
            return
        snapshot = self._undo_stack.pop()

        def _is_alive(_it):
            if _it is None:
                return False
            try:
                _it.scene()
                return True
            except RuntimeError:
                return False

        snapshot_items = {n['item_ref'] for n in snapshot['nodes']}
        snapshot_items.update({l['item_ref'] for l in snapshot['lines']})
        _ConnHandle = globals().get('ConnectionHandleItem')
        _ResizeHandle = globals().get('ResizeHandleItem')
        # Drop everything that was not in the snapshot, except handles and labels-as-children
        for item in list(self.scene.items()):
            try:
                if item in snapshot_items:
                    continue
                if _ConnHandle is not None and isinstance(item, _ConnHandle):
                    continue
                if _ResizeHandle is not None and isinstance(item, _ResizeHandle):
                    continue
                if item.parentItem() is not None and item.parentItem() in snapshot_items:
                    continue
                # Line labels are top-level items managed by their line: removing the line
                # already detaches them via itemChange, but they remain in this frozen
                # list; removing them again triggered the QGraphicsScene::removeItem
                # warning (scene 0x0).
                if getattr(item, '_is_line_label', False):
                    continue
                if item.scene() is not self.scene:
                    continue
                self.scene.removeItem(item)
            except RuntimeError:
                continue
        # PHASE 1: restore NODES first (so lines find valid endpoints)
        for node_data in snapshot['nodes']:
            item = node_data['item_ref']
            if not _is_alive(item):
                continue
            try:
                if node_data.get('in_scene', True) and item.scene() != self.scene:
                    self.scene.addItem(item)
                if hasattr(item, 'remove'):
                    item.remove = False
                item.setPos(node_data['pos'][0], node_data['pos'][1])
                if node_data.get('visible', True):
                    item.show()
                else:
                    item.hide()
                if 'code_or_cat' in node_data and hasattr(item, 'code_or_cat'):
                    item.code_or_cat = node_data['code_or_cat']
                for attr in ('text', 'color', 'font_size', 'bold', 'is_ellipse',
                             'is_collapsed', 'show_attributes'):
                    if attr in node_data and hasattr(item, attr):
                        try:
                            setattr(item, attr, node_data[attr])
                        except Exception:
                            pass
                if isinstance(item, QtWidgets.QGraphicsTextItem):
                    fontweight = QtGui.QFont.Weight.Bold if node_data.get('bold', False) \
                        else QtGui.QFont.Weight.Normal
                    fsize = node_data.get('font_size', 9)
                    try:
                        item.setFont(QtGui.QFont(self.app.settings['font'], fsize, fontweight))
                    except Exception:
                        pass
                    if 'text' in node_data:
                        try:
                            item.setPlainText(node_data['text'])
                        except Exception:
                            pass
                    if 'text_width' in node_data:
                        try:
                            item.setTextWidth(node_data['text_width'])
                        except Exception:
                            pass
                    if 'color' in node_data and node_data['color'] in colors:
                        try:
                            if isinstance(item, TextGraphicsItem):
                                item.setDefaultTextColor(QtGui.QColor(
                                    TextColor(item.code_or_cat['color']).recommendation))
                            else:
                                item.setDefaultTextColor(colors[node_data['color']])
                        except Exception:
                            pass
                if 'pixmap_size' in node_data and hasattr(item, '_original_pixmap'):
                    try:
                        target_w, target_h = node_data['pixmap_size']
                        orig = item._original_pixmap
                        if orig is not None and orig.width() > 0:
                            scaled = orig.scaled(int(target_w), int(target_h),
                                                 QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                                 QtCore.Qt.TransformationMode.SmoothTransformation)
                            item.setPixmap(scaled)
                    except Exception:
                        pass
                item.update()
            except RuntimeError:
                continue
        # PHASE 2: restore LINES after endpoints exist in scene
        for line_data in snapshot['lines']:
            item = line_data['item_ref']
            if not _is_alive(item):
                continue
            try:
                fw = line_data.get('from_widget')
                tw = line_data.get('to_widget')
                if line_data.get('in_scene', True) and item.scene() != self.scene:
                    if _is_alive(fw) and _is_alive(tw) \
                            and fw.scene() == self.scene and tw.scene() == self.scene:
                        self.scene.addItem(item)
                if hasattr(item, 'remove'):
                    item.remove = False
                if line_data.get('visible', True):
                    item.show()
                else:
                    item.hide()
                if 'color' in line_data and hasattr(item, 'color'):
                    item.color = line_data['color']
                if 'line_width' in line_data and hasattr(item, 'line_width'):
                    item.line_width = line_data['line_width']
                if 'line_type' in line_data and hasattr(item, 'line_type'):
                    item.line_type = line_data['line_type']
                if 'arrow_mode' in line_data and hasattr(item, 'arrow_mode'):
                    item.arrow_mode = line_data['arrow_mode']
                if 'label' in line_data and hasattr(item, 'label'):
                    item.label = line_data['label']
                    # both line classes expose _create_label_item;
                    # it creates, updates or removes the top-level label as needed
                    if hasattr(item, '_create_label_item'):
                        try:
                            item._create_label_item()
                        except Exception:
                            pass
                if '_is_cooc_line' in line_data:
                    item._is_cooc_line = line_data['_is_cooc_line']
                if hasattr(item, 'redraw'):
                    item.redraw()
            except RuntimeError:
                continue
        # Final pass: redraw all lines to re-anchor on restored bounding rects
        for it in self.scene.items():
            if isinstance(it, (LinkGraphicsItem, FreeLineGraphicsItem)):
                try:
                    it.redraw()
                except RuntimeError:
                    continue
        self.scene.update()

    # bus slot. External events are coalesced and deferred by the
    # synchronizer; internal refreshes go through finalize_graph_operation instead.
    def _on_project_data_changed(self, tables=None, source=None):
        self._synchronizer.schedule(tables=tables, source=source)

    def finalize_graph_operation(self, fit_view=True):
        """ Centralized post-operation hook: sync data, fit/clamp view, refresh minimap.
        Called after any operation that mutates the graph (organize, import, etc). """

        self._synchronizer.sync_now()  # immediate internal path
        if fit_view:
            self._fit_view_to_items()  # fit logic extracted (shared)
        self.scene.update()
        self._refresh_minimap()

    def _fit_view_to_items(self):
        """ Fit the scene bounding rect into the viewport and center it,
        clamping the zoom-in to 2.0x for small graphs. """

        rect = self.scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        rect.adjust(-80, -80, 80, 80)
        MAX_SCENE = 50000
        if rect.width() > MAX_SCENE or rect.height() > MAX_SCENE:
            rect.setWidth(min(rect.width(), MAX_SCENE))
            rect.setHeight(min(rect.height(), MAX_SCENE))
        self.scene.setSceneRect(rect)
        self.ui.graphicsView.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        current_scale = self.ui.graphicsView.transform().m11()
        if current_scale > 2.0:
            self.ui.graphicsView.resetTransform()
            self.ui.graphicsView.scale(2.0, 2.0)
        self.ui.graphicsView.centerOn(rect.center())

    def fit_and_center_view(self):
        """ Deferred fit + center via the event loop. On the very first import the
        viewport may not have its final geometry yet, so an immediate fitInView
        computes a wrong scale; deferring one event-loop cycle fixes that. """

        def _do_fit():
            try:
                self._fit_view_to_items()
                self._refresh_minimap()
            except RuntimeError:
                pass  # Dialog was closed before the deferred fit ran
        QtCore.QTimer.singleShot(0, _do_fit)

    def toggle_segment_cooccurrence_lines(self):
        """ Global toggle for co-occurrence lines on coded segments. Invoked by
        invoke_segment_cooc_toggle from any coded segment menu; applies to ALL cooc lines. """

        cur = self.app.conn.cursor()
        segment_classes = (FreeTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem)
        existing_cooc_lines = [ln for ln in self.scene.items()
                               if isinstance(ln, FreeLineGraphicsItem)
                               and getattr(ln, '_is_cooc_line', False)]
        # TOGGLE OFF: remove all flagged cooc lines
        if existing_cooc_lines:
            self._save_undo_state()
            for ln in existing_cooc_lines:
                if ln.scene() == self.scene:
                    self.scene.removeItem(ln)
            self.scene.update()
            self._refresh_minimap()
            return
        # TOGGLE ON: gather coded segments
        coded_segments = []
        for seg in self.scene.items():
            if not isinstance(seg, segment_classes):
                continue
            if isinstance(seg, FreeTextGraphicsItem) and getattr(seg, 'ctid', -1) > 0:
                coded_segments.append(seg)
            elif isinstance(seg, PixmapGraphicsItem) and getattr(seg, 'imid', -1) > 0:
                coded_segments.append(seg)
            elif isinstance(seg, AVGraphicsItem) and getattr(seg, 'avid', -1) > 0:
                coded_segments.append(seg)
        if not coded_segments:
            Message(self.app, _("No coded segments"),
                    _("There are no coded segments in the graph.")).exec()
            return
        code_nodes = [n for n in self.scene.items()
                      if isinstance(n, TextGraphicsItem) and n.code_or_cat.get('cid') is not None]
        if not code_nodes:
            Message(self.app, _("No code nodes"),
                    _("There are no code nodes in the graph to connect co-occurrences to.")).exec()
            return
        self._save_undo_state()
        added = 0
        for seg in coded_segments:
            seg_cid = seg_fid = seg_pos0 = seg_pos1 = None
            if isinstance(seg, FreeTextGraphicsItem):
                cur.execute("select cid, fid, pos0, pos1 from code_text where ctid=?", [seg.ctid])
                res = cur.fetchone()
                if res:
                    seg_cid, seg_fid, seg_pos0, seg_pos1 = res
            elif isinstance(seg, PixmapGraphicsItem):
                cur.execute("select cid, id from code_image where imid=?", [seg.imid])
                res = cur.fetchone()
                if res:
                    seg_cid, seg_fid = res[0], res[1]
            elif isinstance(seg, AVGraphicsItem):
                cur.execute("select cid, id, pos0, pos1 from code_av where avid=?", [seg.avid])
                res = cur.fetchone()
                if res:
                    seg_cid, seg_fid, seg_pos0, seg_pos1 = res
            if seg_cid is None or seg_fid is None:
                continue
            cooc_cids = set()
            if isinstance(seg, FreeTextGraphicsItem) and seg_pos0 is not None:
                cur.execute("select distinct cid from code_text where fid=? and cid!=? "
                            "and pos0 < ? and pos1 > ?",
                            [seg_fid, seg_cid, seg_pos1, seg_pos0])
                cooc_cids = {r[0] for r in cur.fetchall()}
            elif isinstance(seg, PixmapGraphicsItem):
                cur.execute("select x1, y1, width, height from code_image where imid=?", [seg.imid])
                dims = cur.fetchone()
                if dims:
                    cur.execute("select distinct cid from code_image where id=? and cid!=? "
                                "and x1 < ? and (x1+width) > ? and y1 < ? and (y1+height) > ?",
                                [seg_fid, seg_cid,
                                 dims[0] + dims[2], dims[0],
                                 dims[1] + dims[3], dims[1]])
                    cooc_cids = {r[0] for r in cur.fetchall()}
            elif isinstance(seg, AVGraphicsItem) and seg_pos0 is not None:
                cur.execute("select distinct cid from code_av where id=? and cid!=? "
                            "and pos0 < ? and pos1 > ?",
                            [seg_fid, seg_cid, seg_pos1, seg_pos0])
                cooc_cids = {r[0] for r in cur.fetchall()}
            for cooc_cid in cooc_cids:
                for code_node in code_nodes:
                    if code_node.code_or_cat.get('cid') != cooc_cid:
                        continue
                    line_exists = any(
                        isinstance(ln, FreeLineGraphicsItem) and
                        ((ln.from_widget == seg and ln.to_widget == code_node) or
                         (ln.from_widget == code_node and ln.to_widget == seg))
                        for ln in self.scene.items())
                    if line_exists:
                        continue
                    cooc_line = FreeLineGraphicsItem(code_node, seg, color="blue",
                                                     line_width=1, line_type="dotted")
                    cooc_line.arrow_mode = "none"
                    cooc_line._is_cooc_line = True  # mark for future detection/removal
                    self.scene.addItem(cooc_line)
                    added += 1
        if added == 0:
            Message(self.app, _("No co-occurrences"),
                    _("No co-occurring codes found for the segments in the graph.")).exec()
        self.scene.update()
        self._refresh_minimap()

    def open_organization_menu(self):
        """ Single dialog dispatching to the four organize_* layouts. """

        models = [
            {'name': _("Radial"), 'id': 'radial'},
            {'name': _("Top to Bottom"), 'id': 'hierarchical'},
            {'name': _("Left to Right"), 'id': 'lr'},
            {'name': _("Right to Left"), 'id': 'rl'},
        ]
        ui = DialogSelectItems(self.app, models, _("Select organization model"), "single")
        if not ui.exec():
            return
        selected = ui.get_selected()
        if not selected:
            return
        self._save_undo_state()
        dispatch = {
            'radial':       self.organize_radially,
            'hierarchical': self.organize_hierarchically,
            'lr':           lambda: self.organize_horizontal("LR"),
            'rl':           lambda: self.organize_horizontal("RL"),
        }
        fn = dispatch.get(selected['id'])
        if fn:
            fn()

    def open_graph_models(self):
        """ Open the Graph Models dialog and refresh the view afterwards. """

        msg = _("Are you sure you want to generate an analytical model?\n\n"
                "This action will clear the current graph view and all unsaved nodes will be lost.")
        ui_confirm = DialogConfirmDelete(self.app, msg)
        if not ui_confirm.exec():
            return
        ui = DialogGraphModels(self.app, self, self)
        ui.exec()
        self.finalize_graph_operation()

    def select_tree_branch(self):
        """ Selected tree branch for model of codes and categories.
        Called by pushButton_selectbranch
        hierarchical tree with sub-codes and their colors, multi-selection.
        Any node is selectable: a
        category imports its whole branch; a code (or sub-code) imports that
        code and its sub-code descendants.
        """

        ui = DialogSelectGraphBranch(self.app, self.codes, self.categories)
        if not ui.exec():
            return
        selected_keys = ui.selected_keys
        # one snapshot per import, so a single undo reverts the whole branch
        self._save_undo_state()
        if not selected_keys or selected_keys == [None]:
            cats, codes, model = self.create_initial_model()
            model = self.get_refined_model_with_category_counts(cats, model, "All")
            self.list_graph(model)
            self.finalize_graph_operation()
            self.fit_and_center_view()
            return
        # Import each selected branch
        for key in selected_keys:
            kind, id_ = key
            cats, codes, model = self.create_initial_model()
            if kind == 'cat':
                top_node = None
                for cat in cats:
                    if cat['catid'] == id_:
                        top_node = cat
                        top_node['supercatid'] = None  # Must set this to None
                        break
                if top_node is None:
                    continue
                model = self.get_refined_model(top_node, model)
                self.list_graph(model)
            elif kind == 'code':
                # the code plus its whole sub-code descendancy (supercid chains)
                top_code = next((c for c in codes if c['cid'] == id_), None)
                if top_code is None:
                    continue
                branch = [top_code]
                included = {id_}
                frontier = [id_]
                guard = 0
                while frontier and guard < 2000:
                    guard += 1
                    current = frontier.pop()
                    for code in codes:
                        if code.get('supercid') == current and code['cid'] not in included:
                            included.add(code['cid'])
                            branch.append(code)
                            frontier.append(code['cid'])
                self.list_graph(branch)
        # centralized refresh + fit after branch import. The deferred fit
        # guarantees the FIRST import is fitted and centred even before the viewport
        # has its final layout geometry.
        self.finalize_graph_operation()
        self.fit_and_center_view()

    def create_initial_model(self):
        """ Create initial model of codes and categories.
        model contains categories and codes combined.

        return: categories : List of Dictionaries of categories
        return: codes : List of Dictionaries of codes
        return: model : List of Dictionaries of codes and categories
        """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)

        for code_ in codes:
            code_['x'] = None
            code_['y'] = None
            code_['supercatid'] = code_['catid']
        for cat in cats:
            cat['x'] = None
            cat['y'] = None
            cat['cid'] = None
            cat['color'] = '#FFFFFF'
            cat['supercid'] = None  # (sub-codes) categories never hang from a code
        model = cats + codes
        return cats, codes, model

    def get_refined_model_with_category_counts(self, cats, model, top_node_text):
        """ The initial model contains all categories and codes.
        The refined model method is called and based on a selected category, via QButton_selection.
        The refined model also gets counts for nodes of each category

        param: cats : List of Dictionaries of categories
        param: model : List of Dictionaries of combined categories and codes
        param: top_node_text : String name of the top category

        return: model : List of Dictionaries
        """

        top_node = None
        if top_node_text == "All":
            top_node = None
        else:
            for cat in cats:
                if cat['name'] == top_node_text:
                    top_node = cat
                    top_node['supercatid'] = None  # Must set this to None
        model = self.get_refined_model(top_node, model)
        return model

    @staticmethod
    def get_refined_model(node, model):
        """ Return a refined model of this top node and all its children.
        Called by: get_refined_model_with_category_counts

        param: node : Dictionary of category, or None
        param: model : List of Dictionaries - of categories and codes

        return: new_model : List of Dictionaries of categories and codes
        """

        if node is None:
            return model
        refined_model = [node]
        i = 0  # Ensure an exit from while loop
        model_changed = True
        while model != [] and model_changed and i < 20:
            model_changed = False
            append_list = []
            for refined_item in refined_model:
                for model_item in model:
                    if model_item['supercatid'] == refined_item['catid']:
                        append_list.append(model_item)
            for append_item in append_list:
                refined_model.append(append_item)
                model.remove(append_item)
                model_changed = True
            i += 1
        return refined_model

    def named_children_of_node(self, node):
        """ Get child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.

        param: node : Dictionary of category (or code, for sub-codes)

        return: child_names : List
        """

        if node['cid'] is not None:
            # (sub-codes): a code may have sub-codes (supercid). Return all
            # descendant sub-code names so they move/collapse together with the parent code.
            all_codes, _cats = self.app.get_codes_categories()
            child_names = []
            frontier = [node['cid']]
            guard = 0
            while frontier and guard < 1000:
                guard += 1
                current = frontier.pop()
                for code in all_codes:
                    if code.get('supercid') == current and code['name'] not in child_names:
                        child_names.append(code['name'])
                        frontier.append(code['cid'])
            return child_names
        child_names = []
        codes, categories = self.app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in codes:
            for cat in categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "
        all_codes_q = list(codes)  # full quirked list for sub-code descendancy

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in categories:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for n in append_list:
                selected_categories.append(n)
                categories.remove(n)
                new_model_changed = True
            i += 1
        categories = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in categories:
            for code in codes:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        codes = selected_codes
        for c in codes:
            child_names.append(c['name'])
        # (sub-codes): include the full sub-code descendancy of every code in
        # the branch, so collapse / move / frequency views cover the whole subtree.
        included = {c['cid'] for c in codes}
        frontier = list(included)
        guard = 0
        while frontier and guard < 2000:
            guard += 1
            current = frontier.pop()
            for code in all_codes_q:
                if code.get('supercid') == current and code['cid'] not in included:
                    included.add(code['cid'])
                    child_names.append(code['name'])
                    frontier.append(code['cid'])
        return child_names

    def list_graph(self, model):
        """ Create a list graph with the categories on the left and codes on the right.
        Additive, adds another model of nodes to the scene.
        Does not add nodes that are already existing in the scene.

        param: model : List of Dictionaries of categories and codes
        """

        # depth-first ordering. Each parent is placed first and its
        # children (sub-categories, codes, then sub-codes) go directly below it with
        # one indent level. The legacy loop inserted children BEFORE their parent
        # while iterating, which interleaved sub-codes between unrelated codes.
        ordered_model = []

        def _attach_children(parent, depth):
            """ Append parent's children depth-first, right below it. """
            if depth > 50:  # guard against cyclic hierarchies
                return
            for child in model:
                if child['x'] is not None:
                    continue
                is_child = False
                if parent['cid'] is None:
                    # Children of a category: sub-categories and its codes.
                    # Sub-codes are excluded here; they hang from their parent code.
                    if child['supercatid'] == parent['catid'] and not child.get('supercid'):
                        is_child = True
                else:
                    # Children of a code: its sub-codes (supercid)
                    if child.get('supercid') is not None and child['supercid'] == parent['cid']:
                        is_child = True
                if is_child:
                    child['x'] = parent['x'] + 120
                    ordered_model.append(child)
                    _attach_children(child, depth + 1)

        # Top level: categories without parent, and codes without category nor parent code
        for code_or_category in model:
            if code_or_category['x'] is None and code_or_category['supercatid'] is None \
                    and not code_or_category.get('supercid'):
                code_or_category['x'] = 10
                ordered_model.append(code_or_category)
                _attach_children(code_or_category, 1)
        # orphans (e.g. a sub-code whose parent code is outside the selected
        # branch) are appended at the end instead of being silently dropped.
        for code_or_category in model:
            if code_or_category['x'] is None:
                code_or_category['x'] = 10
                ordered_model.append(code_or_category)
                _attach_children(code_or_category, 1)

        for item in range(0, len(ordered_model)):
            ordered_model[item]['y'] = item * self.font_size * 3
        model = ordered_model

        # Add text items to the scene, providing they are not already in the scene.
        for code_or_category in model:
            code_or_category['child_names'] = self.named_children_of_node(code_or_category)
            add_to_scene = True
            for scene_item in self.scene.items():
                if isinstance(scene_item, TextGraphicsItem):
                    if scene_item.code_or_cat['name'] == code_or_category['name'] and \
                            scene_item.code_or_cat['catid'] == code_or_category['catid'] and \
                            scene_item.code_or_cat['cid'] == code_or_category['cid']:
                        add_to_scene = False
            if add_to_scene:
                self.scene.addItem(TextGraphicsItem(self.app, code_or_category))

        # Add link from Category to Category, which includes the scene text items and associated data
        for scene_item in self.scene.items():
            if isinstance(scene_item, TextGraphicsItem):
                for scene_item2 in self.scene.items():
                    if isinstance(scene_item2, TextGraphicsItem) and \
                            scene_item.code_or_cat['supercatid'] is not None and \
                            scene_item.code_or_cat['supercatid'] == scene_item2.code_or_cat['catid'] and \
                            (scene_item.code_or_cat['cid'] is None and scene_item2.code_or_cat['cid'] is None):
                        item = LinkGraphicsItem(scene_item, scene_item2, 2, "solid", "gray", True)
                        self.scene.addItem(item)
        # Add links from Codes to Categories
        for scene_item in self.scene.items():
            if isinstance(scene_item, TextGraphicsItem):
                for scene_item2 in self.scene.items():
                    # Link the n Codes to m Categories
                    if isinstance(scene_item2, TextGraphicsItem) and \
                            scene_item2.code_or_cat['cid'] is not None and \
                            scene_item.code_or_cat['cid'] is None and \
                            scene_item.code_or_cat['catid'] == scene_item2.code_or_cat['catid']:
                        item = LinkGraphicsItem(scene_item, scene_item2, 2, "solid", "gray", True)
                        self.scene.addItem(item)
        # Add links from sub-codes to their parent code (supercid). Parent -> child.
        for scene_item in self.scene.items():
            if isinstance(scene_item, TextGraphicsItem):
                for scene_item2 in self.scene.items():
                    if isinstance(scene_item2, TextGraphicsItem) and \
                            scene_item.code_or_cat.get('cid') is not None and \
                            scene_item.code_or_cat.get('supercid') is not None and \
                            scene_item2.code_or_cat.get('cid') is not None and \
                            scene_item.code_or_cat['supercid'] == scene_item2.code_or_cat['cid']:
                        item = LinkGraphicsItem(scene_item2, scene_item, 2, "solid", "gray", True)
                        self.scene.addItem(item)
        # Expand scene width and height if needed
        max_x, max_y = self.scene.suggested_scene_size()
        self.scene.set_width(max_x)
        self.scene.set_height(max_y)

    def reveal_hidden_items(self):
        """ Show list of hidden items to be revealed on selection """

        hidden = []
        for item in self.scene.items():
            if not item.isVisible():
                if isinstance(item, TextGraphicsItem):
                    hidden.append({"name": _("Text: ") + item.text, "item": item})
                if isinstance(item, LinkGraphicsItem):
                    hidden.append({"name": _("Link: ") + item.text, "item": item})
        if not hidden:
            return
        ui = DialogSelectItems(self.app, hidden, _("Reveal hidden items"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        for s in selected:
            s['item'].show()
        # centralized hook also syncs tooltips/data, lines and minimap
        self.finalize_graph_operation(fit_view=False)

    def keyPressEvent(self, event):
        """ Plus, W to zoom in. Minus, Q to zoom out. Space for panning.
        Delete / Backspace remove selected nodes. Ctrl+Z undoes last change. """

        key = event.key()
        modifiers = event.modifiers()
        # Panning activated by space key press
        if key == QtCore.Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            self.ui.graphicsView.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            return
        # Delete / Backspace remove selected nodes
        if key in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            if self.scene.selectedItems():
                self.remove_selected_nodes()
            return
        # Ctrl+Z for undo
        if key == QtCore.Qt.Key.Key_Z and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.undo_last_change()
            return
        if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() > 10:
                return
            self.ui.graphicsView.scale(1.1, 1.1)
        if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
            if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() < 0.1:
                return
            self.ui.graphicsView.scale(0.9, 0.9)
        if key == QtCore.Qt.Key.Key_H:
            for i in self.scene.items():
                logger.debug(f"ITEM: {i.__class__}, POS: {int(i.scenePos().x())}, {int(i.scenePos().y())}")
                logger.debug(f"DETAILS: {i.__repr__()}")

    def keyReleaseEvent(self, event):
        """ Drop space to disable panning """

        if event.key() == QtCore.Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            # Return to frame selection mode
            self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.ui.graphicsView.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)

    def hideEvent(self, event):
        """ Cancel any in-progress connection drag and release pan locks. """
        self.cancel_connection_drag()
        self.scene.clear_connection_preview()
        self._space_pressed = False
        self._is_panning = False
        super().hideEvent(event)

    def resizeEvent(self, event):
        """ Reposition minimap overlay on dialog resize. """
        super().resizeEvent(event)
        if self._minimap_visible and self._minimap_widget is not None:
            self._minimap_widget.reposition()
            self._minimap_widget.update_viewport_rect()

    def _disconnect_event_bus(self):
        """ Disconnect from the bus and stop any pending deferred sync. Idempotent. """
        if getattr(self, '_synchronizer', None) is not None:
            self._synchronizer.detach()  # no timer may fire after closing
        sig = getattr(self, '_event_bus_signal', None)
        if sig is None:
            return
        try:
            sig.disconnect(self._on_project_data_changed)
        except (TypeError, RuntimeError):
            pass  # Already disconnected
        self._event_bus_signal = None

    def closeEvent(self, event):  # covers closing via the window X
        self._disconnect_event_bus()
        super(ViewGraph, self).closeEvent(event)

    def reject(self):
        self._disconnect_event_bus()
        super(ViewGraph, self).reject()

    def accept(self):
        self._disconnect_event_bus()
        super(ViewGraph, self).accept()

    def eventFilter(self, obj, event):
        if obj == self.ui.graphicsView.viewport():
            # QGraphicsView clears the selection during the right-button
            # press, but the context menu fires afterwards, so the multi-selection
            # menu never saw the selected nodes. Snapshot them here; the menu
            # handler restores the selection before deciding what to show.
            if event.type() == QtCore.QEvent.Type.MouseButtonPress and \
                    event.button() == QtCore.Qt.MouseButton.RightButton:
                node_types = (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                              FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem,
                              MemoGraphicsItem)
                self._right_press_selection = [
                    i for i in self.scene.selectedItems() if isinstance(i, node_types)]
            # ZOOM: mouse wheel, anchored under mouse for natural interaction
            if event.type() == QtCore.QEvent.Type.Wheel:
                # AnchorUnderMouse keeps the point under the cursor stable
                self.ui.graphicsView.setTransformationAnchor(
                    QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                self.ui.graphicsView.setResizeAnchor(
                    QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                # zoom factors are reciprocals so in/out cancel exactly
                zoom_in_factor = 1.15
                zoom_out_factor = 1.0 / zoom_in_factor
                current_det = self.ui.graphicsView.transform().determinant()
                if event.angleDelta().y() > 0:
                    if current_det < 25:  # cap at ~5x linear zoom
                        self.ui.graphicsView.scale(zoom_in_factor, zoom_in_factor)
                else:
                    if current_det > 0.04:  # cap at ~0.2x linear zoom
                        self.ui.graphicsView.scale(zoom_out_factor, zoom_out_factor)
                self._refresh_minimap()
                return True

            # drag-to-connect handling. Active when connect mode is on OR scene has
            # selection (handles on a freshly selected node also activate the connection flow).
            _has_selection = bool(self.scene.selectedItems())
            if self._connect_mode or _has_selection:
                if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                    if event.button() == QtCore.Qt.MouseButton.LeftButton:
                        scene_pos = self.ui.graphicsView.mapToScene(event.position().toPoint())
                        hit_handle = self._find_handle_at(scene_pos)
                        if hit_handle is not None:
                            self._handle_connect_click(scene_pos)
                            return True
                        if self._connect_state == 'dragging_preview':
                            self._handle_connect_click(scene_pos)
                            return True
                    # right/middle clicks fall through to default Qt handling
                elif event.type() == QtCore.QEvent.Type.MouseMove:
                    if self._connect_state == 'dragging_preview':
                        scene_pos = self.ui.graphicsView.mapToScene(event.position().toPoint())
                        self._connect_preview_pos = scene_pos
                        self.scene.set_connection_preview(self._connect_source, scene_pos)
                        return True

            # `if` (not elif) so PAN starts a fresh chain after connect handling
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.MiddleButton or (
                        event.button() == QtCore.Qt.MouseButton.LeftButton and getattr(self, '_space_pressed', False)):
                    self._is_panning = True
                    self._pan_start_x = event.position().x()
                    self._pan_start_y = event.position().y()
                    return True

            elif event.type() == QtCore.QEvent.Type.MouseMove and getattr(self, '_is_panning', False):
                dx = event.position().x() - self._pan_start_x
                dy = event.position().y() - self._pan_start_y
                self.ui.graphicsView.horizontalScrollBar().setValue(
                    int(self.ui.graphicsView.horizontalScrollBar().value() + dx))
                self.ui.graphicsView.verticalScrollBar().setValue(
                    int(self.ui.graphicsView.verticalScrollBar().value() - dy))
                self._pan_start_x = event.position().x()
                self._pan_start_y = event.position().y()
                return True

            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                if getattr(self, '_is_panning', False) and (
                        event.button() == QtCore.Qt.MouseButton.MiddleButton
                        or event.button() == QtCore.Qt.MouseButton.LeftButton):
                    self._is_panning = False
                    # cursor priority, space pan > connect cross > default arrow
                    if getattr(self, '_space_pressed', False):
                        cursor = QtCore.Qt.CursorShape.OpenHandCursor
                    else:
                        cursor = (QtCore.Qt.CursorShape.CrossCursor
                                  if getattr(self, '_connect_mode', False)
                                  else QtCore.Qt.CursorShape.ArrowCursor)
                    self.ui.graphicsView.viewport().setCursor(cursor)
                    self._refresh_minimap()  # sync minimap after pan
                    return True

            elif event.type() == event.Type.ContextMenu:
                # route ALL context menus through graphicsview_menu
                # (single dispatcher: multi-selection menu, item menus, blank menu).
                # event.pos() is already in viewport coordinates, which is what
                # itemAt() expects.
                self.graphicsview_menu(event.pos())
                return True
        return super().eventFilter(obj, event)

    def graphicsview_menu(self, position):
        # restore the multi-selection captured at right-press time
        # (the view clears it before this handler runs), then, with 2+ nodes
        # selected, show only the reduced menu: Connect to + appearance.
        snapshot = getattr(self, '_right_press_selection', [])
        self._right_press_selection = []
        if len(snapshot) > 1:
            for it in snapshot:
                try:
                    it.setSelected(True)
                except RuntimeError:
                    pass
        if self.multi_selection_menu(position):
            return
        item = self.ui.graphicsView.itemAt(position)
        if item is not None:
            # scene.sendEvent(item, QContextMenuEvent) delivers a
            # WIDGET event (type ContextMenu) that graphics items ignore, items
            # expect a QGraphicsSceneContextMenuEvent. QGraphicsView's own
            # contextMenuEvent() performs that conversion (viewport -> scene
            # coordinates included) and routes it to the item under the cursor,
            # so the per-item menus open exactly as before.
            event = QtGui.QContextMenuEvent(
                QtGui.QContextMenuEvent.Reason.Mouse,
                position,
                self.ui.graphicsView.viewport().mapToGlobal(position)
            )
            self.ui.graphicsView.contextMenuEvent(event)
            return
        # Menu for blank graphics view area
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        # insert actions grouped under one submenu; "Free text" wording
        insert_menu = menu.addMenu(_("Insert"))
        action_add_text_item = insert_menu.addAction(_("Free text"))
        action_add_line = insert_menu.addAction(_("Relationship line"))
        action_add_coded_text = insert_menu.addAction(_("Coded text segments"))
        action_add_coded_image = insert_menu.addAction(_("Coded image segments"))
        action_add_coded_av = insert_menu.addAction(_("Coded A/V segments"))
        action_memos = insert_menu.addAction(_("Memos of coded segments"))
        menu.addSeparator()
        action_fit_and_center = menu.addAction(_("Fit and Center View"))
        # single "Organize graph" entry; co-occurrence import lives in Graph Models
        action_organize_graph = menu.addAction(_("Organize graph"))
        action_refresh_lines = menu.addAction(_("Refresh view"))
        menu.addSeparator()
        if self.show_frequencies:
            action_toggle_freq = menu.addAction(_("Hide frequencies"))
        else:
            action_toggle_freq = menu.addAction(_("Display frequencies"))
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))

        if action == action_add_text_item:
            self.add_text_item_to_graph(position.x(), position.y())
        if action == action_add_coded_text:
            self.add_coded_text_of_text_files(position.x(), position.y())
        if action == action_add_coded_image:
            self.add_codes_of_image_files(position.x(), position.y())
        if action == action_add_coded_av:
            self.add_codes_of_av_files(position.x(), position.y())
        if action == action_memos:
            self.add_memos_of_coded(position.x(), position.y())
        if action == action_add_line:
            self.add_lines_to_graph()
        if action == action_organize_graph:
            self.open_organization_menu()
        # fit/refresh delegated to the centralized hook
        if action == action_fit_and_center:
            self.finalize_graph_operation()
        if action == action_refresh_lines:
            self.finalize_graph_operation(fit_view=False)
        if action == action_toggle_freq:
            self.toggle_frequencies()

    def multi_selection_menu(self, position):
        """ Reduced context menu for multi-selection.
        With 2 or more node items selected: "Connect to..." plus appearance
        options (Bold toggle and Font size) applied to every selected node.
        Returns True when the reduced menu was shown (handled), False otherwise. """

        node_types = (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                      FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem,
                      MemoGraphicsItem)
        selected_nodes = [i for i in self.scene.selectedItems() if isinstance(i, node_types)]
        if len(selected_nodes) < 2:
            return False
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_connect_to = menu.addAction(_("Connect to..."))
        menu.addSeparator()
        # appearance, applied to the whole selection (text nodes only)
        action_bold = menu.addAction(_("Bold toggle"))
        font_size_menu = menu.addMenu(_("Font size"))
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        if action is None:
            return True
        if action == action_connect_to:
            self.connect_selected_to_node(selected_nodes)
            return True
        if action == action_bold:
            self.apply_appearance_to_nodes(selected_nodes, toggle_bold=True)
            return True
        if action in font_size_actions:
            self.apply_appearance_to_nodes(selected_nodes, font_size=font_size_actions[action])
        return True

    def apply_appearance_to_nodes(self, nodes, toggle_bold=False, font_size=None):
        """ Apply Bold / Font size to every text node in nodes,
        mirroring the per-item context menu behavior (item.bold + item.font_size
        + setFont). Bold on a mixed selection unifies: if any node is not bold,
        all become bold; if all are bold, all become normal. """

        text_nodes = [n for n in nodes if hasattr(n, 'setFont')
                      and (hasattr(n, 'bold') or hasattr(n, 'font_size'))]
        if not text_nodes:
            return
        self._save_undo_state()
        new_bold = None
        if toggle_bold:
            new_bold = any(not getattr(n, 'bold', False) for n in text_nodes)
        for node in text_nodes:
            if new_bold is not None and hasattr(node, 'bold'):
                node.bold = new_bold
            if font_size is not None and hasattr(node, 'font_size'):
                node.font_size = font_size
            size = getattr(node, 'font_size', 9) or 9
            weight = QtGui.QFont.Weight.Bold if getattr(node, 'bold', False) \
                else QtGui.QFont.Weight.Normal
            try:
                node.setFont(QtGui.QFont(self.app.settings['font'], size, weight))
            except Exception:
                continue
        # bounding rects changed: redraw lines, labels, minimap
        self.finalize_graph_operation(fit_view=False)

    def connect_selected_to_node(self, selected_nodes):
        """ create relation lines from every selected node to ONE
        target node chosen from the non-selected nodes. """

        node_types = (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                      FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem,
                      MemoGraphicsItem)
        candidates = []
        for item in self.scene.items():
            if isinstance(item, node_types) and item not in selected_nodes \
                    and item.isVisible():
                name = getattr(item, 'text', None)
                if name is None:
                    name = getattr(item, 'toolTip', lambda: '')() or type(item).__name__
                candidates.append({'name': str(name), 'item': item})
        if not candidates:
            Message(self.app, _("Connect to"),
                    _("There is no unselected node to connect to.")).exec()
            return
        candidates.sort(key=lambda c: c['name'].lower())
        ui = DialogSelectItems(self.app, candidates, _("Connect selected items to"), "single")
        if not ui.exec():
            return
        chosen = ui.get_selected()
        if not chosen:
            return
        target = chosen['item']
        # define the relation once, applied to every created line
        ui_rel = DialogNodeRelations(self.app, self)
        if not ui_rel.exec():
            return
        color = ui_rel.selected_color
        label = ui_rel.selected_relation
        line_type_str, arrow_mode_str = self._resolve_line_type_key(ui_rel.selected_line_type)
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        for node in selected_nodes:
            if node is target:
                continue
            # replace any existing free line between the same pair
            for existing in list(self.scene.items()):
                if isinstance(existing, FreeLineGraphicsItem):
                    if (existing.from_widget is node and existing.to_widget is target) or \
                            (existing.from_widget is target and existing.to_widget is node):
                        self.scene.removeItem(existing)
            line_item = FreeLineGraphicsItem(node, target, color,
                                             line_type=line_type_str, label=label)
            line_item.arrow_mode = arrow_mode_str
            self.scene.addItem(line_item)
        self.finalize_graph_operation(fit_view=False)

    def toggle_frequencies(self):
        """ Toggle display of coding frequencies on code and category nodes. """

        # snapshot before changing text labels (undo reverts to clean names)
        self._save_undo_state()
        self.show_frequencies = not self.show_frequencies
        # reload codes/categories so counts are not stale
        self.codes, self.categories = self.app.get_codes_categories()
        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "
        self._apply_frequency_labels()

    def _apply_frequency_labels(self):
        """ (re)compute and apply the [n] frequency suffixes on code and
        category nodes from the current self.codes/self.categories, WITHOUT touching
        the undo stack. """

        cur = self.app.conn.cursor()
        own_total = {}
        for table in ("code_text", "code_image", "code_av"):
            cur.execute(f"select cid, count(*) from {table} group by cid")
            for cid_v, n in cur.fetchall():
                own_total[cid_v] = own_total.get(cid_v, 0) + n
        children_by_supercid = {}
        codes_by_catid = {}
        for code in self.codes:
            sup = code.get('supercid')
            if sup is not None:
                children_by_supercid.setdefault(sup, []).append(code['cid'])
            elif code.get('catid') is not None:
                codes_by_catid.setdefault(code['catid'], []).append(code['cid'])
        cat_children = {}
        for cat in self.categories:
            sup = cat.get('supercatid')
            if sup is not None:
                cat_children.setdefault(sup, []).append(cat['catid'])

        def code_total(cid_v, guard=0):
            """ Own codings plus all descendant sub-codes. Used ONLY for the
            category aggregate; code nodes display own_total. """
            total = own_total.get(cid_v, 0)
            if guard > 50:
                return total
            for child in children_by_supercid.get(cid_v, []):
                total += code_total(child, guard + 1)
            return total

        def category_total(catid_v, guard=0):
            """ Aggregated totals of top codes across the category descendancy. """
            total = 0
            if guard > 50:
                return total
            for cid_v in codes_by_catid.get(catid_v, []):
                total += code_total(cid_v)
            for sub in cat_children.get(catid_v, []):
                total += category_total(sub, guard + 1)
            return total

        for item in self.scene.items():
            if isinstance(item, TextGraphicsItem):
                item.code_or_cat['child_names'] = self.named_children_of_node(item.code_or_cat)
                base_name = item.code_or_cat['name']
                if self.show_frequencies:
                    if item.code_or_cat['cid'] is not None:
                        # unique per node - own codings only
                        count = own_total.get(item.code_or_cat['cid'], 0)
                    else:
                        count = category_total(item.code_or_cat.get('catid'))
                    item.text = f"{base_name} [{count}]"
                else:
                    # Remove frequency suffix
                    item.text = base_name
                item.setPlainText(item.text)
        self.scene.update()

    def node_organize_rank(self, n):
        """ Shared priority for the organization layouts.
        Order: cases (0) < files (1) < supercategories (2, top-level categories)
        < categories (3) < codes (4) < sub-codes (5) < everything else (6).
        Used for root selection and sibling ordering in the three layouts. """

        if isinstance(n, CaseTextGraphicsItem):
            return 0
        if isinstance(n, FileTextGraphicsItem):
            return 1
        if isinstance(n, TextGraphicsItem) and n.code_or_cat is not None:
            if n.code_or_cat.get('cid') is None:
                # category: top-level (no supercatid) outranks nested
                return 2 if n.code_or_cat.get('supercatid') is None else 3
            # code: plain code outranks sub-code (supercid)
            return 5 if n.code_or_cat.get('supercid') is not None else 4
        return 6

    def organize_sort_key(self, n, adjacency):
        """ Deterministic sort key for the organization layouts.
        Priority rank first, then most connected, then alphabetical. """

        return (self.node_organize_rank(n),
                -len(adjacency.get(n, ())),
                str(getattr(n, 'text', '')))

    def organize_hierarchically(self):
        """ Top-Down Tree Layout
          1. Smart root: prioritize categories without supercatid (real semantic root).
          2. Adaptive vertical spacing based on the actual height of each level.
          3. Explicit gap between disconnected subtrees/components.
          4. Second centering pass so parents align on the exact center of their children.
          5. Subtree width calculated recursively to avoid overlaps.
        """

        # 0. Collect visible nodes and links.
        nodes = []
        links = []
        for item in self.scene.items():
            if not item.isVisible():
                continue
            if isinstance(item, (TextGraphicsItem, FreeTextGraphicsItem,
                                 CaseTextGraphicsItem, FileTextGraphicsItem,
                                 PixmapGraphicsItem, AVGraphicsItem)):
                nodes.append(item)
            elif isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                links.append(item)

        if not nodes:
            return

        # 1. Undirected graph
        adjacency = {n: set() for n in nodes}
        for link in links:
            if hasattr(link, 'from_widget') and hasattr(link, 'to_widget'):
                u, v = link.from_widget, link.to_widget
                if u in adjacency and v in adjacency:
                    adjacency[u].add(v)
                    adjacency[v].add(u)

        # 2. Connected components
        visited_global = set()
        components = []
        for n in nodes:
            if n not in visited_global:
                comp = []
                queue = [n]
                visited_global.add(n)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for nb in adjacency[curr]:
                        if nb not in visited_global:
                            visited_global.add(nb)
                            queue.append(nb)
                components.append(comp)

        # 3. Smart root selection by component
        # priority order cases > files > supercategories >
        # categories > codes > sub-codes; ties broken by connection count.
        def pick_root(comp_nodes):
            return min(comp_nodes, key=lambda x: self.organize_sort_key(x, adjacency))

        # 4. Spanning Tree (BFS) by component
        tree_children = {n: [] for n in nodes}
        roots = []
        for comp in components:
            root = pick_root(comp)
            roots.append(root)
            visited_tree = {root}
            queue = [root]
            while queue:
                curr = queue.pop(0)
                # deterministic layout by priority rank
                # (cases > files > supercats > cats > codes > sub-codes), then name
                sorted_neighbors = sorted(
                    adjacency[curr],
                    key=lambda n: self.organize_sort_key(n, adjacency)
                )
                for nb in sorted_neighbors:
                    if nb not in visited_tree:
                        visited_tree.add(nb)
                        tree_children[curr].append(nb)
                        queue.append(nb)

        # 5. Actual dimensions of each node
        H_PAD = 30  # Minimum horizontal spacing between sibling nodes
        V_PAD = 40  # Extra space above the maximum level height
        COMP_GAP = 80  # Horizontal space between disconnected components

        def node_width(n):
            if hasattr(n, 'boundingRect'):
                return n.boundingRect().width()
            return 100

        def node_height(n):
            if hasattr(n, 'boundingRect'):
                return n.boundingRect().height()
            return 30

        # 6. Maximum height per level (depth)
        level_max_height = {}

        def compute_level_heights(node, depth):
            h = node_height(node)
            if depth not in level_max_height or h > level_max_height[depth]:
                level_max_height[depth] = h
            for child in tree_children.get(node, []):
                compute_level_heights(child, depth + 1)

        for r in roots:
            compute_level_heights(r, 0)

        # Convert max heights into cumulative Y positions
        max_depth = max(level_max_height.keys()) if level_max_height else 0
        level_y = {}
        cumulative_y = 0
        for d in range(max_depth + 1):
            level_y[d] = cumulative_y
            cumulative_y += level_max_height.get(d, 30) + V_PAD

        # 7. Subtree width (recursive, bottom-up)
        subtree_width = {}

        def compute_subtree_width(node):
            children = tree_children.get(node, [])
            if not children:
                w = node_width(node)
                subtree_width[node] = w
                return w
            children_total = sum(compute_subtree_width(c) for c in children)
            children_total += H_PAD * (len(children) - 1)
            w = max(node_width(node), children_total)
            subtree_width[node] = w
            return w

        for r in roots:
            compute_subtree_width(r)

        # 8. Position nodes
        def set_pos(n, x, y):
            if hasattr(n, 'code_or_cat') and n.code_or_cat is not None:
                n.code_or_cat['x'] = x
                n.code_or_cat['y'] = y
            n.setPos(x, y)

        def layout_subtree(node, left_x, depth):
            """ Positions 'node' and all its descendants.
            'left_x' is the left edge of the space allocated to this subtree.
            Returns the center X of the node so that the parent centers over its children. """
            children = tree_children.get(node, [])
            my_width = subtree_width[node]
            y = level_y[depth]

            if not children:
                # Leaf: center the node within its assigned space.
                node_x = left_x + (my_width - node_width(node)) / 2
                set_pos(node, node_x, y)
                return left_x + my_width / 2  # Return the center

            # Put children within subtree space
            children_total_width = (
                    sum(subtree_width[c] for c in children)
                    + H_PAD * (len(children) - 1)
            )
            # Center child block within parent's space
            child_left = left_x + (my_width - children_total_width) / 2

            child_centers = []
            for child in children:
                cx = layout_subtree(child, child_left, depth + 1)
                child_centers.append(cx)
                child_left += subtree_width[child] + H_PAD

            # Center parent on the avg of children's centers
            parent_center = sum(child_centers) / len(child_centers)
            parent_x = parent_center - node_width(node) / 2
            set_pos(node, parent_x, y)
            return parent_center

        # Walk each root with gap between components
        rect = self.scene.itemsBoundingRect()
        current_left = rect.left() + 50

        for root in roots:
            layout_subtree(root, current_left, 0)
            current_left += subtree_width[root] + COMP_GAP

        # 9. Redraw connections
        for link in links:
            if hasattr(link, 'redraw'):
                link.redraw()
        # centralized refresh hook (fit + clamp + minimap + DB sync)
        self.finalize_graph_operation()

    def organize_horizontal(self, direction="LR"):
        """ Horizontal Tree Layout over undirected graph. LR (Left-Right) or RL (Right-Left). """

        nodes = []
        links = []
        for item in self.scene.items():
            if not item.isVisible(): continue
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                    isinstance(item, CaseTextGraphicsItem) or isinstance(item, FileTextGraphicsItem) or \
                    isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                nodes.append(item)
            elif isinstance(item, LinkGraphicsItem) or isinstance(item, FreeLineGraphicsItem):
                links.append(item)

        if not nodes: return

        # 1. Undirected graph
        adjacency = {n: set() for n in nodes}
        for link in links:
            if hasattr(link, 'from_widget') and hasattr(link, 'to_widget'):
                u, v = link.from_widget, link.to_widget
                if u in adjacency and v in adjacency:
                    adjacency[u].add(v)
                    adjacency[v].add(u)

        # 2. Connected components and roots
        visited_global = set()
        components = []
        for n in nodes:
            if n not in visited_global:
                comp_nodes = []
                queue = [n]
                visited_global.add(n)
                while queue:
                    curr = queue.pop(0)
                    comp_nodes.append(curr)
                    for neighbor in adjacency[curr]:
                        if neighbor not in visited_global:
                            visited_global.add(neighbor)
                            queue.append(neighbor)
                components.append(comp_nodes)

        # 3. Build BFS tree
        tree_children = {n: [] for n in nodes}
        roots = []
        for comp in components:
            # root by priority (cases > files > supercats > cats
            # > codes > sub-codes), ties broken by connection count
            root = min(comp, key=lambda x: self.organize_sort_key(x, adjacency))
            roots.append(root)
            visited_tree = set([root])
            queue = [root]
            while queue:
                curr = queue.pop(0)
                # siblings in priority order, then name
                for neighbor in sorted(adjacency[curr],
                                       key=lambda n: self.organize_sort_key(n, adjacency)):
                    if neighbor not in visited_tree:
                        visited_tree.add(neighbor)
                        tree_children[curr].append(neighbor)
                        queue.append(neighbor)

        # 4. Assign spatial positions
        rect = self.scene.itemsBoundingRect()
        start_y = rect.center().y() - (len(nodes) * 20)

        start_x = rect.left() + 50 if direction == "LR" else rect.right() - 50
        x_multiplier = 1 if direction == "LR" else -1

        def set_pos(n, x, y):
            if hasattr(n, 'code_or_cat') and n.code_or_cat is not None:
                n.code_or_cat['x'], n.code_or_cat['y'] = x, y
            n.setPos(x, y)
        current_y = start_y

        def layout_node(node, depth):
            nonlocal current_y
            node_h = node.boundingRect().height() if hasattr(node, 'boundingRect') else 40
            node_x = start_x + (depth * 280 * x_multiplier)
            ch = tree_children.get(node, [])
            if not ch:
                y = current_y
                set_pos(node, node_x, y)
                current_y += node_h + 20
                return y

            c_ys = [layout_node(c, depth + 1) for c in ch]
            parent_y = sum(c_ys) / len(c_ys) if c_ys else current_y
            set_pos(node, node_x, parent_y)
            expected_bottom = parent_y + node_h + 20
            if current_y < expected_bottom: current_y = expected_bottom
            return parent_y

        for r in roots:
            layout_node(r, 0)
        for link in links:
            if hasattr(link, 'redraw'): link.redraw()
        # centralized refresh hook
        self.finalize_graph_operation()

    def organize_radially(self):
        """ Radial Tree Layout: most connected node at the absolute center,
        its connections opened as a star. """

        nodes = []
        links = []
        for item in self.scene.items():
            if not item.isVisible(): continue
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                    isinstance(item, CaseTextGraphicsItem) or isinstance(item, FileTextGraphicsItem) or \
                    isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                nodes.append(item)
            elif isinstance(item, LinkGraphicsItem) or isinstance(item, FreeLineGraphicsItem):
                links.append(item)

        if not nodes: return

        rect = self.scene.itemsBoundingRect()
        center_x, center_y = rect.center().x(), rect.center().y()

        def set_pos(n, x, y):
            w = n.boundingRect().width() / 2 if hasattr(n, 'boundingRect') else 0
            h = n.boundingRect().height() / 2 if hasattr(n, 'boundingRect') else 0
            nx, ny = x - w, y - h
            if hasattr(n, 'code_or_cat') and n.code_or_cat is not None:
                n.code_or_cat['x'], n.code_or_cat['y'] = nx, ny
            n.setPos(nx, ny)

        # 1. Undirected graph (true center regardless of arrow direction)
        adjacency = {n: set() for n in nodes}
        for link in links:
            if hasattr(link, 'from_widget') and hasattr(link, 'to_widget'):
                u, v = link.from_widget, link.to_widget
                if u in adjacency and v in adjacency:
                    adjacency[u].add(v)
                    adjacency[v].add(u)

        # 2. Center node
        connected_nodes = [n for n in nodes if len(adjacency[n]) > 0]
        candidates = connected_nodes if connected_nodes else nodes
        main_root = min(candidates, key=lambda n: self.organize_sort_key(n, adjacency))

        # 3. Fan tree (BFS) from the main_root
        tree_children = {n: [] for n in nodes}
        visited_tree = set([main_root])
        queue = [main_root]
        while queue:
            current = queue.pop(0)
            # fan the star in priority order, then name
            for neighbor in sorted(adjacency[current],
                                   key=lambda n: self.organize_sort_key(n, adjacency)):
                if neighbor not in visited_tree:
                    visited_tree.add(neighbor)
                    tree_children[current].append(neighbor)
                    queue.append(neighbor)

        # 4. Count "leaves" evenly
        leaves_count = {}

        def calc_leaves(node):
            ch = tree_children.get(node, [])
            if not ch:
                leaves_count[node] = 1
                return 1
            count = sum(calc_leaves(c) for c in ch)
            leaves_count[node] = count
            return count

        calc_leaves(main_root)
        radius_step = 280  # Distance between rings, increased for a cleaner look

        # 5. Draw the main star
        drawn_nodes = set()

        def layout_radial(node, depth, angle_start, angle_end):
            drawn_nodes.add(node)
            mid_angle = (angle_start + angle_end) / 2

            if depth == 0:
                set_pos(node, center_x, center_y)
            else:
                current_radius = max(200, depth * radius_step)
                x = center_x + current_radius * math.cos(mid_angle)
                y = center_y + current_radius * math.sin(mid_angle)
                set_pos(node, x, y)

            ch = tree_children.get(node, [])
            if ch:
                angle_per_leaf = (angle_end - angle_start) / leaves_count[node]
                current_angle = angle_start
                for child in ch:
                    child_leaves = leaves_count[child]
                    child_angle_end = current_angle + (child_leaves * angle_per_leaf)
                    layout_radial(child, depth + 1, current_angle, child_angle_end)
                    current_angle = child_angle_end

        layout_radial(main_root, 0, 0, 2 * math.pi)

        # 6. Outer ring for disconnected items
        unvisited = [n for n in nodes if n not in drawn_nodes]
        if unvisited:
            max_depth = 0

            def get_depth(node, d):
                nonlocal max_depth
                max_depth = max(max_depth, d)
                for c in tree_children.get(node, []): get_depth(c, d + 1)

            get_depth(main_root, 0)

            outer_radius = (max_depth + 1) * radius_step + 150
            angle_step = (2 * math.pi) / len(unvisited)
            for i, node in enumerate(unvisited):
                angle = i * angle_step
                x = center_x + outer_radius * math.cos(angle)
                y = center_y + outer_radius * math.sin(angle)
                set_pos(node, x, y)

        # 7. Redraw the lines
        for link in links:
            if hasattr(link, 'redraw'): link.redraw()
        # centralized refresh hook
        self.finalize_graph_operation()

    def add_codes_of_av_files(self, x=10, y=10):
        """ Show selected codes of selected audio/video files as av graphics items.
        Args:
            x: Integer
            y: Integer
        """

        # Select file
        files_wth_names = self.app.get_av_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select audio/video files"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected_file = ui.get_selected()
        cur = self.app.conn.cursor()
        cur.execute("select mediapath from source where id=?", [selected_file['id']])
        selected_file['path'] = ""
        res_path = cur.fetchone()
        if res_path:
            selected_file['path'] = res_path[0]

        # Select from codes that are assigned to this audio/video file
        cur.execute("select cid from code_av where id=?", [selected_file['id']])
        res_assigned_codes = cur.fetchall()
        cids = [r[0] for r in res_assigned_codes]
        code_names = self.app.get_code_names(cids)
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []
        for code in selected_codes:
            sql = "select cid,id,pos0,pos1, ifnull(memo,''), avid from code_av where cid=? and id=?"
            cur.execute(sql, [code['cid'], selected_file['id']])
            res = cur.fetchall()
            for r in res:
                coding_displayed = False
                for item in self.scene.items():
                    if isinstance(item, AVGraphicsItem):
                        if item.avid == r[5]:
                            coding_displayed = True
                if not coding_displayed:
                    name = selected_file['name'] + ': ' + str(int(r[2])) + ' to ' + str(int(r[3])) + _(" msecs")
                    codings.append({'cid': r[0], 'fid': r[1], 'pos0': int(r[2]), 'pos1': int(r[3]),
                                    'memo': r[4], 'filename': selected_file['name'],
                                    'codename': code['name'], 'name': name,
                                    'path': selected_file['path'], 'avid': r[5]})
        if not codings:
            Message(self.app, _("No codes"), _("No coded segments for selection")).exec()
            return
        ui = DialogSelectItems(self.app, codings, _("Select coded segment"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codings = ui.get_selected()
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        for s in selected_codings:
            x += 10
            y += 10
            item = AVGraphicsItem(self.app, s['avid'], x, y, s['pos0'], s['pos1'], s['path'])
            msg = f"AVID:{s['avid']} " + _("File: ") + f"{s['filename']}\n" + _("Code: ") + s['codename']
            msg += f"\n{s['pos0']} - {s['pos1']}" + _("msecs")
            if s['memo'] != "":
                msg += "\n" + _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)
        # re-center, sync DB metadata, refresh minimap
        self.finalize_graph_operation(fit_view=False)

    def add_codes_of_image_files(self, x=10, y=10):
        """ Show selected codes of selected image file as pixmap graphics items.
        Args:
            x: Integer
            y: Integer
        """

        # Select image file
        files_wth_names = self.app.get_image_and_pdf_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select image files"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected_file = ui.get_selected()
        cur = self.app.conn.cursor()
        cur.execute("select mediapath from source where id=?", [selected_file['id']])
        selected_file['path'] = ""
        res_path = cur.fetchone()
        if res_path:
            selected_file['path'] = res_path[0]

        # Select from codes that are assigned to this image
        cur.execute("select cid from code_image where id=?", [selected_file['id']])
        res_assigned_codes = cur.fetchall()
        cids = [r[0] for r in res_assigned_codes]
        code_names = self.app.get_code_names(cids)
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []

        for code in selected_codes:
            sql = "select cid,id,x1,y1,width,height,ifnull(memo,''), imid, pdf_page from code_image where cid=? and id=?"
            cur.execute(sql, [code['cid'], selected_file['id']])
            res = cur.fetchall()
            for r in res:
                coding_displayed = False
                for item in self.scene.items():
                    if isinstance(item, PixmapGraphicsItem):
                        if item.imid == r[7]:
                            coding_displayed = True
                if not coding_displayed:
                    name = f"{selected_file['name']} x:{int(r[2])} y:{int(r[3])}"
                    name += _(" width") + str(int(r[4])) + _(" height:") + str(int(r[5]))
                    codings.append({'cid': r[0], 'fid': r[1], 'x': int(r[2]), 'y': int(r[3]), 'width': int(r[4]),
                                    'height': int(r[5]), 'memo': r[6], 'filename': selected_file['name'],
                                    'codename': code['name'], 'name': name,
                                    'path': selected_file['path'], 'imid': r[7], 'pdf_page': r[8]})
        if not codings:
            Message(self.app, _("No codes"), _("No coded segments for selection")).exec()
            return
        ui = DialogSelectItems(self.app, codings, _("Select coded area"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codings = ui.get_selected()
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        for s in selected_codings:
            x += 10
            y += 10
            item = PixmapGraphicsItem(self.app, s['imid'], x, y, s['x'], s['y'], s['width'], s['height'], s['path'],
                                      None, s['pdf_page'])
            msg = f"IMID:{s['imid']} " + _("File: ") + f"{s['filename']}\n" + _("Code: ") + f"{s['codename']}\n"
            msg += _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)
        # re-center, sync DB metadata, refresh minimap
        self.finalize_graph_operation(fit_view=False)

    def add_coded_text_of_text_files(self, x=10, y=10):
        """ Show selected codes of selected text files as free text graphics items.
        Args:
            x: Integer
            y: Integer
        """

        # Select files
        files_wth_names = self.app.get_text_filenames()
        if not files_wth_names:
            Message(self.app, _("No files"), _("No text files in this project.")).exec()
            return
        ui = DialogSelectItems(self.app, files_wth_names, _("Step 1/3: Select text files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_files = ui.get_selected()
        # Select codes
        code_names = self.app.get_code_names()
        ui = DialogSelectItems(self.app, code_names, _("Step 2/3: Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        codings = []
        cur = self.app.conn.cursor()
        for file_ in selected_files:
            for code in selected_codes:
                sql = "select cid,fid,seltext,ifnull(memo,''), ctid from code_text where cid=? and fid=?"
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    coding_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            if item.ctid == r[4]:
                                coding_displayed = True
                    if not coding_displayed:
                        codings.append({'cid': r[0], 'fid': r[1], 'name': r[2], 'memo': r[3], 'filename': file_['name'],
                                        'codename': code['name'], 'ctid': r[4]})
        if not codings:
            Message(self.app, _("No codes"), _("No coded segments for selection")).exec()
            return
        ui = DialogSelectItems(self.app, codings, _("Step 3/3: Select coded text segments"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codings = ui.get_selected()
        color = self.color_selection("text")
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        for s in selected_codings:
            x += 10
            y += 10
            freetextid = 1
            for item in self.scene.items():
                if isinstance(item, FreeTextGraphicsItem):
                    if item.freetextid > freetextid:
                        freetextid = item.freetextid + 1
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, color, False, s['ctid'])
            item.ctid = s['ctid']
            msg = _("File: ") + f"{s['filename']}\n" + _("Code: ") + s['codename']
            if s['memo'] != "":
                msg += "\n" + _("Memo: ") + s['memo']
            item.setToolTip(msg)
            self.scene.addItem(item)
        # re-center, sync DB metadata, refresh minimap
        self.finalize_graph_operation(fit_view=False)

    def add_memos_of_coded(self, x=10, y=10):
        """ Show selected memos of coded segments of selected files in free text items.
        Args:
            x: Integer
            y: Integer
        """

        files_wth_names = self.app.get_filenames()
        ui = DialogSelectItems(self.app, files_wth_names, _("Select files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_files = ui.get_selected()
        code_names = self.app.get_code_names()
        ui = DialogSelectItems(self.app, code_names, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        # Select one or more codings, or coding memos
        memos = []
        cur = self.app.conn.cursor()
        for file_ in selected_files:
            for code in selected_codes:
                sql = "select cid,fid,seltext,ifnull(memo,''),ctid from code_text where cid=? and fid=? and memo !='' order by pos0 asc"
                cur.execute(sql, [code['cid'], file_['id']])
                res = cur.fetchall()
                for r in res:
                    coding_memo_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            if item.memo_ctid is not None and item.memo_ctid == r[4]:
                                coding_memo_displayed = True
                    if not coding_memo_displayed:
                        memos.append({'cid': r[0], 'fid': r[1], 'tooltip': r[2], 'name': r[3], 'filetype': 'text',
                                      'codename': code['name'], 'filename': file_['name'], 'ctid': r[4], 'imid': None,
                                      'avid': None})
                sql_img = "select cid,id,x1,y1,width,height,memo,imid from code_image where cid=? and id=? and memo !='' and memo is not null"
                cur.execute(sql_img, [code['cid'], file_['id']])
                res_img = cur.fetchall()
                for r in res_img:
                    coding_memo_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            if item.memo_imid == r[7]:
                                coding_memo_displayed = True
                    if not coding_memo_displayed:
                        tt = _("Memo for area: ") + "x:" + f"{r[2]}" + " y:" + f"{r[3]}" + " " + _("width:") \
                             + f"{r[4]} " + _("height:") + f"{r[5]}"
                        memos.append({'cid': r[0], 'fid': r[1], 'tooltip': tt, 'name': r[6], 'filetype': 'image',
                                      'codename': code['name'], 'filename': file_['name'], 'imid': r[7], 'avid': None,
                                      'ctid': None})
                sql_av = "select cid,id,pos0,pos1,memo, avid from code_av where cid=? and id=? and memo !='' and " \
                         "memo is not null order by pos0 asc"
                cur.execute(sql_av, [code['cid'], file_['id']])
                res_av = cur.fetchall()
                for r in res_av:
                    coding_memo_displayed = False
                    for item in self.scene.items():
                        if isinstance(item, FreeTextGraphicsItem):
                            if item.memo_avid == r[5]:
                                coding_memo_displayed = True
                    if not coding_memo_displayed:
                        tt = _("Memo for duration: ") + f"{r[2]} - {r[3]} " + _("msecs")
                        memos.append({'cid': r[0], 'fid': r[1], 'tooltip': tt, 'name': r[4], 'filetype': 'A/V',
                                      'codename': code['name'], 'filename': file_['name'], 'avid': r[5], 'imid': None,
                                      'ctid': None})
        if not memos:
            Message(self.app, _("No memos"), _("No memos for selection")).exec()
            return
        ui = DialogSelectItems(self.app, memos, _("Select coding memo"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_memos = ui.get_selected()
        color = self.color_selection("text")
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        for s in selected_memos:
            x += 10
            y += 10
            freetextid = 1
            for item in self.scene.items():
                if isinstance(item, FreeTextGraphicsItem):
                    if item.freetextid > freetextid:
                        freetextid = item.freetextid + 1
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, color, False, -1,
                                        s['ctid'], s['imid'], s['avid'])
            msg = _("File: ") + f"{s['filename']}\n" + _("Code: ") + s['codename']
            if s['tooltip'] != "":
                msg += "\n" + _("Memo for: ") + s['tooltip']
            item.setToolTip(msg)
            self.scene.addItem(item)
        # re-center, sync DB metadata, refresh minimap
        self.finalize_graph_operation(fit_view=False)

    def add_lines_to_graph(self):
        """ Add one or more free lines from an item to one or more destination items. """

        # From item selection
        texts_and_groups = self.graphics_items_text_and_group()
        ui = DialogSelectItems(self.app, texts_and_groups, _("Line start item"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            return
        text_from = selected['name']
        from_item = None
        for item in self.scene.items():
            if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                    isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) or \
                    isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                if item.text == text_from:
                    from_item = item
        # To Items selection, remove the from item, and remove matching text items
        texts_and_groups.remove(selected)
        for i in texts_and_groups[:]:
            if i['name'] == text_from:
                texts_and_groups.remove(i)
        ui = DialogSelectItems(self.app, texts_and_groups, _("Line end item(s)"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            return
        # open the Node Relations dialog (same flow as drag-to-connect)
        # so the relationship line is defined here: label, color, line type and arrow,
        # instead of the plain color picker that produced unlabelled lines.
        ui = DialogNodeRelations(self.app, self)
        if not ui.exec():
            return
        color = ui.selected_color
        label = ui.selected_relation
        line_type_str, arrow_mode_str = self._resolve_line_type_key(ui.selected_line_type)
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()

        # Create Free Item lines, one per selected target, replacing any existing
        # line between the same pair (mirrors the drag-to-connect behaviour)
        for s in selected:
            text_to = s['name']
            to_item = None
            for item in self.scene.items():
                if isinstance(item, TextGraphicsItem) or isinstance(item, FreeTextGraphicsItem) or \
                        isinstance(item, FileTextGraphicsItem) or isinstance(item, CaseTextGraphicsItem) or \
                        isinstance(item, PixmapGraphicsItem) or isinstance(item, AVGraphicsItem):
                    # Cannot link same text items
                    if item.text == text_to:
                        to_item = item
            if from_item != to_item and not (from_item is None or to_item is None):
                for existing in list(self.scene.items()):
                    if isinstance(existing, FreeLineGraphicsItem):
                        if (existing.from_widget == from_item and existing.to_widget == to_item) or \
                           (existing.from_widget == to_item and existing.to_widget == from_item):
                            self.scene.removeItem(existing)
                line_item = FreeLineGraphicsItem(from_item, to_item, color,
                                                 line_type=line_type_str, label=label)
                line_item.arrow_mode = arrow_mode_str
                self.scene.addItem(line_item)
        # refresh after batch line creation
        self.finalize_graph_operation(fit_view=False)

    def color_selection(self, obj_type="line"):
        """ Get a color for Free text items and Free lines.
         Called by: show_codes, show_memos.  # lines now use DialogNodeRelations
         If obj_type is line, limit choices, otherwise include black and white.
         Args:
             obj_type : String
         Returns:
             color : String
        """

        # Line color selection
        colours = [{"name": _("gray"), "english": "gray"}, {"name": _("blue"), "english": "blue"},
                   {"name": _("cyan"), "english": "cyan"}, {"name": _("magenta"), "english": "magenta"},
                   {"name": _("green"), "english": "green"}, {"name": _("red"), "english": "red"},
                   {"name": _("yellow"), "english": "yellow"}, {"name": _("orange"), "english": "orange"}]
        if obj_type != "line":
            colours.append({"name": _("white"), "english": "white"})
            colours.append({"name": _("black"), "english": "black"})
        ui = DialogSelectItems(self.app, colours, _("Colour"), "single")
        ok = ui.exec()
        if not ok:
            return ""
        selected_color = ui.get_selected()
        return selected_color['english']

    def _resolve_line_type_key(self, key):
        """ Translate DialogNodeRelations key into a (line_type, arrow_mode) pair. """
        mapping = {
            "dotted_arrow":         ("dotted", "forward"),
            "solid_arrow":          ("solid",  "forward"),
            "dotted_no_arrow":      ("dotted", "none"),
            "solid_no_arrow":       ("solid",  "none"),
            "dotted_bidirectional": ("dotted", "both"),
            "solid_bidirectional":  ("solid",  "both"),
        }
        return mapping.get(key, ("solid", "forward"))

    def cancel_connection_drag(self):
        """ Reset connection drag state. """
        self._connect_state = 'idle'
        self._connect_source = None
        self._connect_preview_pos = None
        self.scene.update()

    def _toggle_minimap(self):
        """ Toggle minimap, recreating the widget if its C++ side was destroyed. """
        self._minimap_visible = not self._minimap_visible
        if self._minimap_visible:
            if self._minimap_widget is not None:
                try:
                    self._minimap_widget.isVisible()
                except RuntimeError:
                    self._minimap_widget = None
            if self._minimap_widget is None:
                self._minimap_widget = MinimapGraphicsView(self.scene, self.ui.graphicsView, self)
            self._minimap_widget.show()
            self._minimap_widget.raise_()
            self._refresh_minimap()
        else:
            if self._minimap_widget is not None:
                try:
                    self._minimap_widget.hide()
                except RuntimeError:
                    self._minimap_widget = None
        if hasattr(self.ui, 'pushButton_minimap'):
            self.ui.pushButton_minimap.blockSignals(True)
            self.ui.pushButton_minimap.setChecked(self._minimap_visible)
            self.ui.pushButton_minimap.blockSignals(False)

    def _refresh_minimap(self):
        """ Refresh minimap, guarded against deleted C++ objects. """
        if self._minimap_visible and self._minimap_widget is not None:
            try:
                self._minimap_widget.update_viewport_rect()
            except RuntimeError:
                self._minimap_widget = None
                self._minimap_visible = False

    def _on_minimap_toggled(self, checked):
        """ Bridge for pushButton_minimap toggle. """
        if checked != self._minimap_visible:
            self._toggle_minimap()
        if self.ui.pushButton_minimap.isChecked() != self._minimap_visible:
            self.ui.pushButton_minimap.blockSignals(True)
            self.ui.pushButton_minimap.setChecked(self._minimap_visible)
            self.ui.pushButton_minimap.blockSignals(False)

    def align_selected(self, direction="vertical"):
        """ Align selected nodes to a vertical column or horizontal row.
        Uses Qt's BVH via selectedItems for O(K) lookup; clamps against collisions. """
        valid_classes = (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                         FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem, MemoGraphicsItem)
        selected = [it for it in self.scene.selectedItems() if isinstance(it, valid_classes)]
        if len(selected) < 2:
            return
        self._save_undo_state()
        is_vertical = (direction == "vertical")
        centers = [it.sceneBoundingRect().center().y() if is_vertical else it.sceneBoundingRect().center().x()
                   for it in selected]
        target_center = sum(centers) / len(selected)
        selected.sort(key=lambda it: it.scenePos().x() if is_vertical else it.scenePos().y())
        padding = 15 if is_vertical else 10
        last_edge = float('-inf')
        for it in selected:
            rect = it.boundingRect()
            pos = it.pos()
            if is_vertical:
                new_y = target_center - (rect.height() / 2.0)
                new_x = max(pos.x(), last_edge + padding)
                it.setPos(new_x, new_y)
                last_edge = new_x + rect.width()
            else:
                new_x = target_center - (rect.width() / 2.0)
                new_y = max(pos.y(), last_edge + padding)
                it.setPos(new_x, new_y)
                last_edge = new_y + rect.height()
            if getattr(it, 'code_or_cat', None) is not None:
                it.code_or_cat['x'], it.code_or_cat['y'] = it.pos().x(), it.pos().y()
        for item in self.scene.items():
            if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                item.redraw()
        self.scene.update()
        self._refresh_minimap()

    def distribute_selected(self, direction="vertical"):
        """ Distribute selected nodes uniformly along an axis. """
        valid_classes = (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                         FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem, MemoGraphicsItem)
        selected = [it for it in self.scene.selectedItems() if isinstance(it, valid_classes)]
        if len(selected) < 3:
            return
        self._save_undo_state()
        is_vertical = (direction == "vertical")
        selected.sort(key=lambda it: it.sceneBoundingRect().center().y() if is_vertical else it.sceneBoundingRect().center().x())
        if is_vertical:
            total_size = sum(it.boundingRect().height() for it in selected)
            start_pos = selected[0].sceneBoundingRect().top()
            end_pos = selected[-1].sceneBoundingRect().bottom()
        else:
            total_size = sum(it.boundingRect().width() for it in selected)
            start_pos = selected[0].sceneBoundingRect().left()
            end_pos = selected[-1].sceneBoundingRect().right()
        total_span = end_pos - start_pos
        gap = (total_span - total_size) / float(len(selected) - 1)
        min_gap = 15.0
        if gap < min_gap:
            gap = min_gap
        current_pos = start_pos
        for it in selected:
            rect = it.boundingRect()
            if is_vertical:
                it.setPos(it.pos().x(), current_pos)
                current_pos += rect.height() + gap
            else:
                it.setPos(current_pos, it.pos().y())
                current_pos += rect.width() + gap
            if getattr(it, 'code_or_cat', None) is not None:
                it.code_or_cat['x'], it.code_or_cat['y'] = it.pos().x(), it.pos().y()
        for item in self.scene.items():
            if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                item.redraw()
        self.scene.update()
        self._refresh_minimap()

    def _scale_graph(self, factor):
        """ Scale all node positions by `factor` relative to center of mass. """
        nodes = [it for it in self.scene.items()
                 if isinstance(it, (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                                    FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem, MemoGraphicsItem))]
        if not nodes:
            return
        self._save_undo_state()
        cx = sum(it.pos().x() for it in nodes) / len(nodes)
        cy = sum(it.pos().y() for it in nodes) / len(nodes)
        for it in nodes:
            dx = it.pos().x() - cx
            dy = it.pos().y() - cy
            new_x = cx + dx * factor
            new_y = cy + dy * factor
            it.setPos(new_x, new_y)
            if hasattr(it, 'code_or_cat') and it.code_or_cat is not None:
                it.code_or_cat['x'] = new_x
                it.code_or_cat['y'] = new_y
        for item in self.scene.items():
            if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                item.redraw()
        if factor > 1.0:
            rect = self.scene.itemsBoundingRect()
            rect.adjust(-100, -100, 100, 100)
            candidate = self.scene.sceneRect().united(rect)
            MAX_SCENE = 50000
            if candidate.width() > MAX_SCENE or candidate.height() > MAX_SCENE:
                candidate.setWidth(min(candidate.width(), MAX_SCENE))
                candidate.setHeight(min(candidate.height(), MAX_SCENE))
            self.scene.setSceneRect(candidate)
        self.scene.update()
        self._refresh_minimap()

    def _hide_all_handles(self):
        """ Hide all handles (used by exporters so PNG/PDF/Draw.io/ODT stay clean). """
        for item in self.scene.items():
            if isinstance(item, (ConnectionHandleItem, ResizeHandleItem)):
                item.setVisible(False)

    def _restore_all_handles(self):
        """ Restore handles only if their parent node is still selected. """
        for item in self.scene.items():
            if isinstance(item, (ConnectionHandleItem, ResizeHandleItem)):
                if hasattr(item, 'parent_item') and item.parent_item.isSelected():
                    item.setVisible(True)

    def _find_handle_at(self, scene_pos):
        """ Locate a ConnectionHandleItem under the scene position (returns its parent node). """
        for item in self.scene.items(scene_pos):
            if isinstance(item, ConnectionHandleItem):
                return item.parent_item
        return None

    def _handle_connect_click(self, scene_pos):
        """ Two-click connection state machine for drag-to-connect. """
        valid_types = (TextGraphicsItem, FreeTextGraphicsItem,
                       PixmapGraphicsItem, AVGraphicsItem,
                       CaseTextGraphicsItem, FileTextGraphicsItem,
                       MemoGraphicsItem)
        if self._connect_state == 'idle':
            clicked_item = self._find_handle_at(scene_pos)
            if clicked_item is not None:
                self._connect_source = clicked_item
                self._connect_state = 'dragging_preview'
                self.scene.set_connection_preview(clicked_item, scene_pos)
            return
        if self._connect_state == 'dragging_preview':
            clicked_item = None
            for item in self.scene.items(scene_pos):
                if isinstance(item, valid_types):
                    clicked_item = item
                    break
            if clicked_item is None or clicked_item is self._connect_source:
                self.cancel_connection_drag()
                self.scene.clear_connection_preview()
                return
            source = self._connect_source
            target = clicked_item
            self.cancel_connection_drag()
            self.scene.clear_connection_preview()
            ui = DialogNodeRelations(self.app, self)
            if not ui.exec():
                return
            color = ui.selected_color
            label = ui.selected_relation
            line_type_str, arrow_mode_str = self._resolve_line_type_key(ui.selected_line_type)
            self._save_undo_state()
            for existing in list(self.scene.items()):
                if isinstance(existing, FreeLineGraphicsItem):
                    if (existing.from_widget == source and existing.to_widget == target) or \
                       (existing.from_widget == target and existing.to_widget == source):
                        self.scene.removeItem(existing)
            line_item = FreeLineGraphicsItem(source, target, color,
                                             line_type=line_type_str, label=label)
            line_item.arrow_mode = arrow_mode_str
            self.scene.addItem(line_item)

    def add_text_item_to_graph(self, x=20, y=20):
        """ Add text item to graph.
        Args:
            x: Integer
            y: integer
        """

        freetextid = 1
        for item in self.scene.items():
            if isinstance(item, FreeTextGraphicsItem):
                if item.freetextid > freetextid:
                    freetextid = item.freetextid + 1
        text_, ok = QtWidgets.QInputDialog.getText(self, _('Text object'), _('Enter text:'))
        if not ok:
            return
        texts = self.graphics_items_text_and_group()
        for t in texts:
            if text_ == t['name']:
                Message(self.app, _("Warning"), _("Another item has this exact text")).exec()
                return
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        item = FreeTextGraphicsItem(self.app, freetextid, x, y, text_)
        self.scene.addItem(item)
        # refresh without fit (single item shouldn't refit the whole view)
        self.finalize_graph_operation(fit_view=False)

    def graphics_items_text_and_group(self):
        """ Used to get a list of all FreeText and Case and File graphics items text.
        Adds a group key to be able to groups the text items for the selection dialog.
        Use to show text in a dialog, to allow links between these items.
        Called by: add_lines_to_graph, add_text_item_to_graph

        return: names_groups : List of Dictionaries of Name Strings, Group strings
        """

        names_and_groups = []
        cur = self.app.conn.cursor()

        # By code
        for item in self.scene.items():
            if isinstance(item, FreeTextGraphicsItem) and item.ctid > -1:
                cur.execute(
                    "select code_name.name from code_name join code_text on code_text.cid=code_name.cid where ctid=?",
                    [item.ctid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_ctid is not None:
                cur.execute(
                    "select code_name.name from code_name join code_text on code_text.cid=code_name.cid where ctid=?",
                    [item.memo_ctid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_imid is not None:
                cur.execute(
                    "select code_name.name from code_name join code_image on code_image.cid=code_name.cid where imid=?",
                    [item.memo_imid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_avid is not None:
                cur.execute(
                    "select code_name.name from code_name join code_av on code_av.cid=code_name.cid where avid=?",
                    [item.memo_avid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, PixmapGraphicsItem):
                cur.execute(
                    "select code_name.name from code_name join code_image on code_image.cid=code_name.cid where imid=?",
                    [item.imid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, AVGraphicsItem):
                cur.execute(
                    "select code_name.name from code_name join code_av on code_av.cid=code_name.cid where avid=?",
                    [item.avid])
                res = cur.fetchone()[0]
                names_and_groups.append({'name': item.text, 'group': res})
            if isinstance(item, TextGraphicsItem):
                names_and_groups.append({'name': item.text, 'group': item.text})
            if isinstance(item, FreeTextGraphicsItem) and item.ctid == -1 and item.memo_ctid is None and \
                    item.memo_imid is None and item.memo_avid is None:
                names_and_groups.append({'name': item.text, 'group': _('Free text item')})
            if isinstance(item, CaseTextGraphicsItem):
                names_and_groups.append({'name': item.text, 'group': _('Case item')})
            if isinstance(item, FileTextGraphicsItem):
                names_and_groups.append({'name': item.text, 'group': _('File item')})
        sorted_names_and_groups = sorted(names_and_groups, key=lambda d: d['name'])
        return sorted_names_and_groups

    def add_files_to_graph(self):
        """ Add Text file items to graph. """

        files = self.get_files()
        # Do not show items that are already displayed
        to_remove = []
        for f in files:
            for item in self.scene.items():
                if isinstance(item, FileTextGraphicsItem):
                    if item.file_id == f['id']:
                        to_remove.append(f)
        for tr in to_remove:
            files.remove(tr)

        ui = DialogSelectItems(self.app, files, _("Select files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        for i, s in enumerate(selected):
            file_item = FileTextGraphicsItem(self.app, s['name'], s['id'], i * 10, i * 10)
            file_item.setToolTip(_("File"))  # Need to add tooltip here, for some unknown reason
            self.scene.addItem(file_item)
        # re-center, sync DB metadata, refresh minimap
        self.finalize_graph_operation(fit_view=False)

    def get_files(self):
        """ Get list of files.
        Called by add_files_to_graph.
        return: list of dictionary of id and name"""

        cur = self.app.conn.cursor()
        sql = "select id, name from source order by source.name asc"
        cur.execute(sql)
        result = cur.fetchall()
        keys = 'id', 'name'
        res = []
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def add_cases_to_graph(self):
        """ Add Text case items to graph. """

        cases = self.get_cases()
        # Do not show items that are already displayed
        to_remove = []
        for c in cases:
            for item in self.scene.items():
                if isinstance(item, CaseTextGraphicsItem):
                    if item.case_id == c['id']:
                        to_remove.append(c)
        for tr in to_remove:
            cases.remove(tr)
        ui = DialogSelectItems(self.app, cases, _("Select cases"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        # snapshot before adding, so one undo reverts the whole batch
        self._save_undo_state()
        for i, s in enumerate(selected):
            case_item = CaseTextGraphicsItem(self.app, s['name'], s['id'], i * 10, i * 10)
            case_item.setToolTip(_("Case"))  # Need to add tooltip here, for some unknown reason
            self.scene.addItem(case_item)
        # re-center, sync DB metadata, refresh minimap
        self.finalize_graph_operation(fit_view=False)

    def get_cases(self):
        """ Get list of cases.
        Called by: add_cases_to_graph
        return: list of dictionary of id and name"""

        cur = self.app.conn.cursor()
        sql = "select caseid, name from cases order by cases.name asc"
        cur.execute(sql)
        result = cur.fetchall()
        keys = 'id', 'name'
        res = []
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def export_image(self):
        """ Export the QGraphicsScene as a png image with transparent background. """

        filename = "Graph.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        # render the rect that encloses ALL items (handles negative coords)
        rect = self.scene.itemsBoundingRect()
        rect.adjust(-30, -30, 30, 30)
        image = QtGui.QImage(int(rect.width()), int(rect.height()), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect)
        painter.end()
        image.save(filepath)
        Message(self.app, _("Image exported"), filepath).exec()

    def export_drawio(self):
        """ export the canvas as a native editable Draw.io (.drawio) file. """

        filename = "QualCoder_graph.drawio"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        # Standard header required by Draw.io
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<mxfile>\n  <diagram id="qualcoder_graph" name="QualCoder Graph">\n'
        xml += '    <mxGraphModel dx="1000" dy="1000" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">\n'
        xml += '      <root>\n        <mxCell id="0" />\n        <mxCell id="1" parent="0" />\n'
        item_ids = {}
        current_id = 2
        # Nodes. Includes MemoGraphicsItem so live memo nodes are exported too.
        EXPORTABLE_NODE_TYPES = ("TextGraphicsItem", "FreeTextGraphicsItem",
                                 "CaseTextGraphicsItem", "FileTextGraphicsItem",
                                 "PixmapGraphicsItem", "AVGraphicsItem",
                                 "MemoGraphicsItem")
        for item in self.scene.items():
            if not item.isVisible():
                continue
            item_type = type(item).__name__
            if item_type in EXPORTABLE_NODE_TYPES:
                item_ids[item] = str(current_id)
                x = round(item.pos().x(), 2)
                y = round(item.pos().y(), 2)
                w = round(item.boundingRect().width(), 2)
                h = round(item.boundingRect().height(), 2)
                label = ""
                color = "#FFFFFF"
                # is_ellipse only applies to TextGraphicsItem (codes / categories)
                is_ellipse = (item_type == "TextGraphicsItem"
                              and getattr(item, 'is_ellipse', False))
                # Color source depends on the node class
                if item_type == "TextGraphicsItem" and hasattr(item, 'code_or_cat') \
                        and item.code_or_cat is not None:
                    color = item.code_or_cat.get('color', '#FFFFFF')
                elif item_type in ("CaseTextGraphicsItem", "FileTextGraphicsItem",
                                   "FreeTextGraphicsItem"):
                    color = getattr(item, 'color', '#FFFFFF')
                elif item_type == "MemoGraphicsItem":
                    color = "#E3F2FD"  # match the on-canvas memo background
                # Visible text or descriptive tooltip for media segments
                if item_type in ("PixmapGraphicsItem", "AVGraphicsItem"):
                    label = item.toolTip() if item.toolTip() else getattr(item, 'text', '')
                elif hasattr(item, 'toPlainText'):
                    label = item.toPlainText()
                elif hasattr(item, 'text'):
                    label = item.text
                label = str(label).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
                label = label.replace('\n', '&lt;br&gt;')
                # Sanitiza cualquier nombre de color a hex; mxGraph requiere #RRGGBB.
                # Sanitize any color name to hex; mxGraph requires #RRGGBB.
                def to_hex(value, default):
                    return COLORS_HEX.get(value, value
                                          if isinstance(value, str) and value.startswith('#')
                                          else default)
                # Contorno punteado gris para segmentos codificados. Dashed gray outline for coded segments.
                coded_outline = "strokeColor=#808080;dashed=1;dashPattern=4 3;"
                if item_type == "PixmapGraphicsItem":
                    buffer = QtCore.QBuffer()
                    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
                    item.pixmap().toImage().save(buffer, "PNG")
                    b64_data = buffer.data().toBase64().data().decode('ascii').replace('\n', '').replace('\r', '')
                    style = f"shape=image;html=1;verticalLabelPosition=bottom;verticalAlign=top;imageAspect=0;aspect=fixed;image=data:image/png,{b64_data};"
                    if getattr(item, 'imid', -1) is not None and getattr(item, 'imid', -1) > 0:
                        style += "imageBorder=#808080;dashed=1;dashPattern=4 3;"
                elif item_type == "AVGraphicsItem":
                    style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#E1BEE7;fontColor=#000000;"
                    if getattr(item, 'avid', -1) is not None and getattr(item, 'avid', -1) > 0:
                        style += coded_outline
                    else:
                        style += "strokeColor=#333333;"
                elif item_type == "FreeTextGraphicsItem":
                    font_hex = to_hex(color, "#000000")
                    if font_hex.upper() == "#FFFFFF":
                        font_hex = "#333333"
                    style = f"rounded=0;whiteSpace=wrap;html=1;fillColor=#FAFAFA;fontColor={font_hex};"
                    if getattr(item, 'ctid', -1) is not None and getattr(item, 'ctid', -1) > 0:
                        style += coded_outline
                    else:
                        style += "strokeColor=#333333;"
                elif item_type == "CaseTextGraphicsItem":
                    # Fiel al lienzo: caja redondeada con borde naranja. Faithful to canvas: rounded box, orange border.
                    style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#FAFAFA;strokeColor=#F57C00;strokeWidth=2;fontColor=#000000;"
                elif item_type == "FileTextGraphicsItem":
                    # Fiel al lienzo: nota con esquina doblada y borde azul. Faithful to canvas: folded-corner note, blue border.
                    style = "shape=note;whiteSpace=wrap;html=1;backgroundOutline=1;fillColor=#FAFAFA;strokeColor=#1976D2;strokeWidth=2;fontColor=#000000;"
                elif item_type == "MemoGraphicsItem":
                    # Fiel al lienzo: fondo azul claro con borde azul discontinuo. Faithful to canvas: light blue fill, dashed blue border.
                    style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#E3F2FD;strokeColor=#1565C0;dashed=1;fontColor=#000000;"
                else:
                    # Codigos y categorias: color real de fondo con fuente de contraste.
                    # Codes and categories: real fill color with contrast font color.
                    fill_hex = to_hex(color, "#FFFFFF")
                    font_hex = "#000000"
                    try:
                        font_hex = TextColor(fill_hex).recommendation
                    except Exception:
                        pass
                    shape = "ellipse" if is_ellipse else "rounded=1"
                    style = f"{shape};whiteSpace=wrap;html=1;fillColor={fill_hex};strokeColor=#333333;fontColor={font_hex};"
                xml += f'        <mxCell id="{current_id}" value="{label}" style="{style}" vertex="1" parent="1">\n'
                xml += f'          <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
                xml += '        </mxCell>\n'
                current_id += 1
        # Connections (lines)
        for item in self.scene.items():
            if not item.isVisible():
                continue
            if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if not hasattr(item, 'from_widget') or not hasattr(item, 'to_widget'):
                    continue
                source_id = item_ids.get(item.from_widget)
                target_id = item_ids.get(item.to_widget)
                if source_id and target_id:
                    line_color = item.color if hasattr(item, 'color') else "gray"
                    # Explicit DotLine check; anything else exports as solid
                    dashed = "1" if getattr(item, 'line_type', None) == QtCore.Qt.PenStyle.DotLine else "0"
                    width = item.line_width if hasattr(item, 'line_width') else 2
                    label = item.label if hasattr(item, 'label') else ""
                    # Exportar como se ve en pantalla: traducido; el dato sigue siendo canonico.
                    # Export as seen on screen: translated; the stored data stays canonical.
                    label = _(str(label)) if label else ""
                    label = str(label).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
                    # Respect arrow_mode (forward / backward / both / none)
                    if type(item).__name__ == "FreeLineGraphicsItem":
                        arrow_mode = getattr(item, 'arrow_mode', 'forward')
                    else:
                        arrow_mode = 'none'  # hierarchical lines are undirected
                    if arrow_mode == 'forward':
                        end_arrow, start_arrow = "classic", "none"
                    elif arrow_mode == 'backward':
                        end_arrow, start_arrow = "none", "classic"
                    elif arrow_mode == 'both':
                        end_arrow, start_arrow = "classic", "classic"
                    else:
                        end_arrow, start_arrow = "none", "none"
                    # Sanitize stroke color to hex
                    stroke_hex = COLORS_HEX.get(line_color, line_color
                                                if isinstance(line_color, str) and line_color.startswith('#')
                                                else "#808080")
                    style = (f"endArrow={end_arrow};startArrow={start_arrow};html=1;"
                             f"strokeColor={stroke_hex};strokeWidth={width};dashed={dashed};"
                             "labelBackgroundColor=none;")
                    xml += f'        <mxCell id="{current_id}" value="{label}" style="{style}" edge="1" parent="1" source="{source_id}" target="{target_id}">\n'
                    xml += '          <mxGeometry relative="1" as="geometry" />\n'
                    xml += '        </mxCell>\n'
                    current_id += 1
        xml += '      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>'
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml)
            Message(self.app, _("Export successful"),
                    _("Graph exported natively for Draw.io at:") + f"\n{filepath}", "information").exec()
        except Exception as e:
            logger.error(f"Error exporting to Draw.io: {e}")
            Message(self.app, _("Error"), _("The file could not be saved:") + f"\n{e}", "warning").exec()

    def export_pdf_graph(self):
        """ Export the graph cropped to its items as a PDF. """

        filename = "Graph.pdf"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        bounding_rect = self.scene.itemsBoundingRect()
        margin = 2
        bounding_rect = bounding_rect.adjusted(-margin, -margin, margin, margin)
        pdf_writer = QtGui.QPdfWriter(filepath)
        pdf_writer.setResolution(300)
        # Create the custom page size in mm
        width_mm = bounding_rect.width() / pdf_writer.resolution() * 30
        height_mm = bounding_rect.height() / pdf_writer.resolution() * 30
        page_size = QtGui.QPageSize(QtCore.QSizeF(width_mm, height_mm), QtGui.QPageSize.Millimeter)
        pdf_writer.setPageSize(page_size)
        painter = QtGui.QPainter(pdf_writer)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.scene.render(
            painter,
            QtCore.QRectF(0, 0, bounding_rect.width(), bounding_rect.height()),
            bounding_rect
        )
        painter.end()
        Message(self.app, _("PDF exported (cropped)"), filepath).exec()

    def export_graph_summary(self):
        """ export an analytical summary of the current graph as an .odt report.
        Sections: metadata + embedded snapshot, graph description, node counts,
        category > code hierarchy, labelled relations, coded segments, memos,
        coding frequencies per code, and a software citation.
        """

        # 1. Choose output path
        default_dir = getattr(self.app, 'last_export_directory', os.path.expanduser("~"))
        filename, ok = QtWidgets.QFileDialog.getSaveFileName(
            self,
            _("Save graph analytical summary"),
            default_dir,
            "OpenDocument Text (*.odt)"
        )
        if not ok or not filename:
            return
        if not filename.endswith('.odt'):
            filename += '.odt'
        if hasattr(self.app, 'last_export_directory'):
            self.app.last_export_directory = os.path.dirname(filename)

        # 2. Build the ODT document and register named styles
        doc = OpenDocumentText()
        bold_style = Style(name="BoldText", family="text")
        bold_style.addElement(TextProperties(fontweight="bold"))
        doc.styles.addElement(bold_style)
        heading_style = Style(name="SectionHeading", family="paragraph")
        heading_style.addElement(ParagraphProperties(margintop="0.4cm", marginbottom="0.15cm"))
        heading_style.addElement(TextProperties(fontsize="14pt", fontweight="bold"))
        doc.styles.addElement(heading_style)
        header_cell_style = Style(name="HeaderCell", family="table-cell")
        header_cell_style.addElement(TableCellProperties(backgroundcolor="#E8E8E8",
                                                         padding="0.05cm"))
        doc.automaticstyles.addElement(header_cell_style)

        # ODT builder helpers, closed over doc and the styles above
        def add_heading(text):
            doc.text.addElement(H(outlinelevel=2, stylename=heading_style, text=text))

        def add_paragraph(text):
            doc.text.addElement(P(text=text))

        def add_bold_paragraph(text):
            p = P()
            p.addElement(Span(stylename=bold_style, text=text))
            doc.text.addElement(p)

        def add_table_with_headers(headers, rows, col_count=None):
            if col_count is None:
                col_count = len(headers)
            tbl = Table()
            for _col in range(col_count):
                tbl.addElement(TableColumn())
            hr = TableRow()
            tbl.addElement(hr)
            for h in headers:
                tc = TableCell(stylename=header_cell_style)
                hp = P()
                hp.addElement(Span(stylename=bold_style, text=str(h)))
                tc.addElement(hp)
                hr.addElement(tc)
            for row in rows:
                tr = TableRow()
                tbl.addElement(tr)
                for cell in row:
                    tc = TableCell()
                    cell_text = str(cell).replace('\n', ' ').strip()
                    tc.addElement(P(text=cell_text))
                    tr.addElement(tc)
            doc.text.addElement(tbl)
            doc.text.addElement(P(text=""))

        # 3. Title and metadata
        title_p = P()
        title_p.addElement(Span(stylename=bold_style, text=_("Graph analytical summary")))
        doc.text.addElement(title_p)
        add_paragraph("")
        now_str = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        add_paragraph(_("Generated on: ") + now_str)
        if getattr(self, 'loaded_graph', None) is not None:
            graph_name = self.loaded_graph.get('name', '') or ''
            graph_description = self.loaded_graph.get('description', '') or ''
            if graph_name:
                add_paragraph(_("Loaded graph: ") + graph_name)
            if graph_description:
                add_paragraph(_("Description: ") + graph_description)
        add_paragraph("")

        # 4. Embed the graph snapshot. Hide handles before rendering, restore after.
        # uuid ensures concurrent exports never clash on the temp path.
        import tempfile
        import uuid
        temp_img = None
        rect = self.scene.itemsBoundingRect()
        if rect.width() > 0 and rect.height() > 0:
            self._hide_all_handles()
            try:
                pixmap = QtGui.QPixmap(int(rect.width() + 40), int(rect.height() + 40))
                pixmap.fill(QtCore.Qt.GlobalColor.white)
                painter = QtGui.QPainter(pixmap)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                self.scene.render(painter, QtCore.QRectF(pixmap.rect()), rect)
                painter.end()
                temp_img = os.path.join(tempfile.gettempdir(), f"qc_graph_{uuid.uuid4().hex}.png")
                if pixmap.save(temp_img, "PNG"):
                    try:
                        href = doc.addPicture(temp_img)
                        # Fit to a 16cm-wide content area, preserving aspect ratio
                        w_cm = 16.0
                        ratio = rect.height() / rect.width()
                        h_cm = w_cm * ratio
                        df = Frame(width=f"{w_cm}cm", height=f"{h_cm}cm", anchortype="paragraph")
                        df.addElement(OdfImage(href=href, type="simple", show="embed"))
                        p_img = P()
                        p_img.addElement(df)
                        doc.text.addElement(p_img)
                    except Exception as e:
                        logger.error(f"Could not embed graph image into ODT: {e}")
                        add_paragraph(_("[Notice: graph image could not be embedded in the report.]"))
                else:
                    logger.warning("Could not save the temporary graph snapshot.")
                    add_paragraph(_("[Notice: graph image could not be generated on this system.]"))
            finally:
                self._restore_all_handles()
        add_paragraph("")

        # Graph description block under the embedded image
        if getattr(self, 'loaded_graph', None) is not None:
            desc_text = (self.loaded_graph.get('description', '') or '').strip()
            if desc_text:
                add_heading(_("Graph description"))
                # Split on blank lines to preserve paragraph structure
                for para in desc_text.split("\n\n"):
                    para = para.strip()
                    if para:
                        add_paragraph(para)
                add_paragraph("")

        # 5. Walk the scene ONCE: counts, code/category lookups, relations, segments, memos
        node_counts = {
            "Codes": 0, "Sub-codes": 0, "Categories": 0, "Free text items": 0,
            "Coded text segments": 0, "Coded image segments": 0, "Coded A/V segments": 0,
            "Memos": 0, "Cases": 0, "Files": 0,
        }
        labelled_relations_rows = []  # (source, label, arrow_glyph, target)
        scene_code_cid_to_name = {}
        scene_cat_catid_to_name = {}
        scene_code_cid_to_catid = {}
        scene_code_cid_to_supercid = {}  # sub-code chains for hierarchy paths
        scene_coded_segments = []   # text/image/av coded segments
        scene_memo_entries = []     # MemoGraphicsItem (live) + legacy FreeText memos
        for item in self.scene.items():
            # hidden items are excluded so the summary matches the visible graph
            if not item.isVisible():
                continue
            cls_name = type(item).__name__
            if cls_name == "TextGraphicsItem":
                if item.code_or_cat.get('cid') is not None:
                    # sub-codes counted on their own row
                    if item.code_or_cat.get('supercid') is not None:
                        node_counts["Sub-codes"] += 1
                    else:
                        node_counts["Codes"] += 1
                    cid = item.code_or_cat['cid']
                    scene_code_cid_to_name[cid] = item.code_or_cat.get('name', '?')
                    scene_code_cid_to_catid[cid] = item.code_or_cat.get('catid')
                    scene_code_cid_to_supercid[cid] = item.code_or_cat.get('supercid')
                else:
                    node_counts["Categories"] += 1
                    catid = item.code_or_cat.get('catid')
                    if catid is not None:
                        scene_cat_catid_to_name[catid] = item.code_or_cat.get('name', '?')
            elif cls_name == "FreeTextGraphicsItem":
                ctid = getattr(item, 'ctid', -1)
                if ctid is not None and ctid > 0:
                    node_counts["Coded text segments"] += 1
                    scene_coded_segments.append({'kind': 'text', 'id': ctid, 'item_ref': item})
                elif (getattr(item, 'memo_ctid', None)
                      or getattr(item, 'memo_imid', None)
                      or getattr(item, 'memo_avid', None)):
                    node_counts["Memos"] += 1
                    scene_memo_entries.append({
                        'kind': 'legacy_freetext', 'item_ref': item,
                        'memo_ctid': getattr(item, 'memo_ctid', None),
                        'memo_imid': getattr(item, 'memo_imid', None),
                        'memo_avid': getattr(item, 'memo_avid', None),
                    })
                else:
                    node_counts["Free text items"] += 1
            elif cls_name == "PixmapGraphicsItem":
                imid = getattr(item, 'imid', -1)
                # count only items backed by a real coding id
                if imid is not None and imid > 0:
                    node_counts["Coded image segments"] += 1
                    scene_coded_segments.append({'kind': 'image', 'id': imid, 'item_ref': item})
            elif cls_name == "AVGraphicsItem":
                avid = getattr(item, 'avid', -1)
                # count only items backed by a real coding id
                if avid is not None and avid > 0:
                    node_counts["Coded A/V segments"] += 1
                    scene_coded_segments.append({'kind': 'av', 'id': avid, 'item_ref': item})
            elif cls_name == "MemoGraphicsItem":
                node_counts["Memos"] += 1
                scene_memo_entries.append({
                    'kind': 'live_memo', 'item_ref': item,
                    'memo_source_type': getattr(item, 'memo_source_type', None),
                    'memo_source_id': getattr(item, 'memo_source_id', None),
                })
            elif cls_name == "CaseTextGraphicsItem":
                node_counts["Cases"] += 1
            elif cls_name == "FileTextGraphicsItem":
                node_counts["Files"] += 1
            elif cls_name in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                    label = getattr(item, 'label', '') or ''
                    if label:
                        # Traducido al mostrar; el dato guardado sigue canonico.
                        # Translated at display time; stored data stays canonical.
                        label = _(str(label))
                        # Arrow rendered as glyph-only so it reads in any language
                        arrow = getattr(item, 'arrow_mode', 'none')
                        if arrow == 'forward':
                            arrow_glyph = "→"
                        elif arrow == 'backward':
                            arrow_glyph = "←"
                        elif arrow == 'both':
                            arrow_glyph = "↔"
                        else:
                            arrow_glyph = "—"  # em-dash for undirected
                        # column order source | relation | direction | target
                        labelled_relations_rows.append((
                            getattr(item.from_widget, 'text', '?'),
                            label,
                            arrow_glyph,
                            getattr(item.to_widget, 'text', '?'),
                        ))

        # 6. Node counts table
        add_heading(_("Node counts by type"))
        add_table_with_headers(
            headers=[_("Type"), _("Count")],
            rows=[(label, count) for label, count in node_counts.items() if count > 0],
        )

        # 7. Category lookup for the hierarchy + frequencies tables
        cur = self.app.conn.cursor()
        cur.execute("SELECT catid, name, supercatid FROM code_cat")
        all_cats = {row[0]: {'name': row[1], 'supercatid': row[2]} for row in cur.fetchall()}

        def get_scene_category_path(catid):
            """ Build a path of parent categories that are visually present in the graph. """
            # a code without category is not the same as a category
            # that exists but is hidden/absent from the graph.
            if catid is None:
                return _("(No category)")
            if catid not in all_cats:
                return _("(Category not shown in graph)")
            path = []
            curr = catid
            visited = set()  # guard against circular supercatid in corrupted DBs
            while curr is not None and curr in all_cats and curr not in visited:
                visited.add(curr)
                if curr in scene_cat_catid_to_name:
                    path.insert(0, all_cats[curr]['name'])
                curr = all_cats[curr]['supercatid']
            return " > ".join(path) if path else _("(Category not shown in graph)")

        def get_scene_code_path(cid):
            """ full hierarchy path of a code: visible parent categories of the
            TOP code of its sub-code chain, followed by its visible ancestor codes.
            E.g. a sub-sub-code reads: Cat A > code a1 > sub a1.1 """
            # Ancestor code chain (only codes visible in the graph)
            code_chain = []
            curr = scene_code_cid_to_supercid.get(cid)
            visited = set()
            while curr is not None and curr in scene_code_cid_to_name and curr not in visited:
                visited.add(curr)
                code_chain.insert(0, scene_code_cid_to_name[curr])
                curr = scene_code_cid_to_supercid.get(curr)
            # Effective category comes from the TOP code of the chain
            top_cid = cid
            visited = set()
            while scene_code_cid_to_supercid.get(top_cid) is not None \
                    and scene_code_cid_to_supercid[top_cid] in scene_code_cid_to_name \
                    and top_cid not in visited:
                visited.add(top_cid)
                top_cid = scene_code_cid_to_supercid[top_cid]
            cat_path = get_scene_category_path(scene_code_cid_to_catid.get(top_cid))
            parts = []
            if cat_path and not cat_path.startswith("("):
                parts.append(cat_path)
            parts.extend(code_chain)
            return " > ".join(parts) if parts else cat_path

        # 8. Category > Code hierarchy (only for codes/categories present in the scene)
        if scene_code_cid_to_catid:
            add_heading(_("Category to code hierarchy (graph subset)"))
            # the path now includes ancestor codes, so sub-codes read
            # coherently (Cat > parent code > sub-code) and sort right below their parent.
            hierarchy_rows = []
            for cid, name in scene_code_cid_to_name.items():
                path = get_scene_code_path(cid)
                # Placeholder paths "(...)" sort last, mirroring the canvas layout
                sort_key = (path.startswith("("), (path + " > " + name).lower())
                hierarchy_rows.append((sort_key, path, name))
            hierarchy_rows.sort(key=lambda r: r[0])
            add_table_with_headers(
                headers=[_("Hierarchy Path"), _("Code")],
                rows=[(path, name) for _key, path, name in hierarchy_rows],
            )

        # 9. Labelled relations: Source | Relation | arrow glyph | Target
        add_heading(_("Labelled relations"))
        if labelled_relations_rows:
            # stable ordering by source then relation name
            labelled_relations_rows.sort(key=lambda r: (r[0].lower(), r[1].lower()))
            add_table_with_headers(
                headers=[_("Source"), _("Relation"), _("Direction"), _("Target")],
                rows=labelled_relations_rows,
            )
        else:
            add_paragraph(_("No labelled relations were defined in this graph."))
            add_paragraph("")

        # 10. Coded segments present in the graph. Sorted by code, then file
        add_heading(_("Coded segments in the graph"))
        if scene_coded_segments:
            seg_rows = []
            EXCERPT_MAX = 240  # truncation limit for long text excerpts
            for seg in scene_coded_segments:
                code_name_str = "?"
                file_name_str = "?"
                content_str = ""
                memo_str = ""
                try:
                    if seg['kind'] == 'text':
                        cur.execute("select code_name.name, source.name, code_text.seltext, "
                                    "ifnull(code_text.memo,'') "
                                    "from code_text "
                                    "join code_name on code_name.cid=code_text.cid "
                                    "join source on source.id=code_text.fid "
                                    "where code_text.ctid=?", [seg['id']])
                        r = cur.fetchone()
                        if r:
                            code_name_str = r[0]
                            file_name_str = r[1]
                            excerpt = (r[2] or "").replace('\n', ' ').strip()
                            if len(excerpt) > EXCERPT_MAX:
                                excerpt = excerpt[:EXCERPT_MAX] + "..."
                            content_str = excerpt
                            memo_str = r[3]
                    elif seg['kind'] == 'image':
                        cur.execute("select code_name.name, source.name, x1, y1, width, height, "
                                    "ifnull(code_image.memo,'') "
                                    "from code_image "
                                    "join code_name on code_name.cid=code_image.cid "
                                    "join source on source.id=code_image.id "
                                    "where code_image.imid=?", [seg['id']])
                        r = cur.fetchone()
                        if r:
                            code_name_str = r[0]
                            file_name_str = r[1]
                            content_str = (_("Area: ")
                                           + f"x:{int(r[2])} y:{int(r[3])} "
                                           + _("width:") + f"{int(r[4])} "
                                           + _("height:") + f"{int(r[5])}")
                            memo_str = r[6]
                    elif seg['kind'] == 'av':
                        cur.execute("select code_name.name, source.name, code_av.pos0, code_av.pos1, "
                                    "ifnull(code_av.memo,'') "
                                    "from code_av "
                                    "join code_name on code_name.cid=code_av.cid "
                                    "join source on source.id=code_av.id "
                                    "where code_av.avid=?", [seg['id']])
                        r = cur.fetchone()
                        if r:
                            code_name_str = r[0]
                            file_name_str = r[1]
                            content_str = f"{int(r[2])} - {int(r[3])} " + _("msecs")
                            memo_str = r[4]
                except Exception as e:
                    logger.warning(f"Could not fetch segment {seg['kind']} id={seg['id']}: {e}")
                    continue
                # Type column uses a short letter so the column stays narrow
                type_letter = {'text': 'T', 'image': 'I', 'av': 'A/V'}.get(seg['kind'], '?')
                seg_rows.append((code_name_str, type_letter, file_name_str, content_str, memo_str))
            seg_rows.sort(key=lambda r: (r[0].lower(), r[2].lower(), r[3].lower()))
            add_table_with_headers(
                headers=[_("Code"), _("Type"), _("File"), _("Segment / Range"), _("Memo")],
                rows=seg_rows,
            )
        else:
            add_paragraph(_("No coded segments are currently displayed in the graph."))
            add_paragraph("")

        # 11. Memos present in the graph (live MemoGraphicsItem + legacy FreeText memos)
        add_heading(_("Memos in the graph"))
        if scene_memo_entries:
            memo_rows = []
            MEMO_MAX = 350  # truncation limit for long memo bodies
            for mem in scene_memo_entries:
                src_type_label = "?"
                src_name = "?"
                memo_body = ""
                try:
                    if mem['kind'] == 'live_memo':
                        st = mem.get('memo_source_type')
                        sid = mem.get('memo_source_id')
                        if st == 'code':
                            cur.execute("select name, ifnull(memo,'') from code_name where cid=?", [sid])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Code")
                                src_name = r[0]
                                memo_body = r[1]
                        elif st == 'category':
                            cur.execute("select name, ifnull(memo,'') from code_cat where catid=?", [sid])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Category")
                                src_name = r[0]
                                memo_body = r[1]
                        elif st == 'code_text':
                            cur.execute("select code_name.name, code_text.seltext, ifnull(code_text.memo,'') "
                                        "from code_text join code_name on code_name.cid=code_text.cid "
                                        "where code_text.ctid=?", [sid])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Coded text")
                                excerpt = (r[1] or "").replace('\n', ' ').strip()
                                if len(excerpt) > 80:
                                    excerpt = excerpt[:80] + "..."
                                src_name = f"{r[0]}: {excerpt}"
                                memo_body = r[2]
                        elif st == 'code_image':
                            cur.execute("select code_name.name, ifnull(code_image.memo,'') "
                                        "from code_image join code_name on code_name.cid=code_image.cid "
                                        "where code_image.imid=?", [sid])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Coded image")
                                src_name = r[0]
                                memo_body = r[1]
                        elif st == 'code_av':
                            cur.execute("select code_name.name, ifnull(code_av.memo,'') "
                                        "from code_av join code_name on code_name.cid=code_av.cid "
                                        "where code_av.avid=?", [sid])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Coded A/V")
                                src_name = r[0]
                                memo_body = r[1]
                        elif st == 'case':
                            cur.execute("select name, ifnull(memo,'') from cases where caseid=?", [sid])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Case")
                                src_name = r[0]
                                memo_body = r[1]
                        elif st == 'file':
                            cur.execute("select name, ifnull(memo,'') from source where id=?", [sid])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("File")
                                src_name = r[0]
                                memo_body = r[1]
                    elif mem['kind'] == 'legacy_freetext':
                        # Legacy memos carried as FreeTextGraphicsItem.memo_ctid / memo_imid / memo_avid
                        if mem.get('memo_ctid'):
                            cur.execute("select code_name.name, code_text.seltext, ifnull(code_text.memo,'') "
                                        "from code_text join code_name on code_name.cid=code_text.cid "
                                        "where code_text.ctid=?", [mem['memo_ctid']])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Coded text")
                                excerpt = (r[1] or "").replace('\n', ' ').strip()
                                if len(excerpt) > 80:
                                    excerpt = excerpt[:80] + "..."
                                src_name = f"{r[0]}: {excerpt}"
                                memo_body = r[2]
                        elif mem.get('memo_imid'):
                            cur.execute("select code_name.name, ifnull(code_image.memo,'') "
                                        "from code_image join code_name on code_name.cid=code_image.cid "
                                        "where code_image.imid=?", [mem['memo_imid']])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Coded image")
                                src_name = r[0]
                                memo_body = r[1]
                        elif mem.get('memo_avid'):
                            cur.execute("select code_name.name, ifnull(code_av.memo,'') "
                                        "from code_av join code_name on code_name.cid=code_av.cid "
                                        "where code_av.avid=?", [mem['memo_avid']])
                            r = cur.fetchone()
                            if r:
                                src_type_label = _("Coded A/V")
                                src_name = r[0]
                                memo_body = r[1]
                except Exception as e:
                    logger.warning(f"Could not fetch memo entry {mem.get('kind')}: {e}")
                    continue
                # Skip empty memos (no analytical value in the report)
                if not memo_body or not memo_body.strip():
                    continue
                memo_body = memo_body.strip()
                if len(memo_body) > MEMO_MAX:
                    memo_body = memo_body[:MEMO_MAX] + "..."
                memo_rows.append((src_type_label, src_name, memo_body))
            if memo_rows:
                memo_rows.sort(key=lambda r: (r[0].lower(), r[1].lower()))
                add_table_with_headers(
                    headers=[_("Source type"), _("Source"), _("Memo")],
                    rows=memo_rows,
                )
            else:
                add_paragraph(_("Memo nodes are present in the graph but their bodies are empty."))
                add_paragraph("")
        else:
            add_paragraph(_("No memos are currently displayed in the graph."))
            add_paragraph("")

        # 12. Coding frequencies per code
        if scene_code_cid_to_name:
            add_heading(_("Coding frequencies per code in the graph"))
            # per-code counts are the code's OWN codings; when sub-codes
            # are present an extra column aggregates each code with its visible
            # descendant sub-codes, so parent totals are unambiguous.
            own_counts = {}
            for cid in scene_code_cid_to_name:
                cur.execute("SELECT count(*) FROM code_text WHERE cid=?", [cid])
                t_count = cur.fetchone()[0] or 0
                cur.execute("SELECT count(*) FROM code_image WHERE cid=?", [cid])
                i_count = cur.fetchone()[0] or 0
                cur.execute("SELECT count(*) FROM code_av WHERE cid=?", [cid])
                a_count = cur.fetchone()[0] or 0
                own_counts[cid] = (t_count, i_count, a_count)
            has_subcodes = any(sup is not None and sup in scene_code_cid_to_name
                               for sup in scene_code_cid_to_supercid.values())
            children_of = {}
            for cid, sup in scene_code_cid_to_supercid.items():
                if sup is not None and sup in scene_code_cid_to_name:
                    children_of.setdefault(sup, []).append(cid)

            def total_with_descendants(cid, guard=0):
                """ Own total plus all visible descendant sub-code totals. """
                t, i, a = own_counts.get(cid, (0, 0, 0))
                total = t + i + a
                if guard > 50:
                    return total
                for child in children_of.get(cid, []):
                    total += total_with_descendants(child, guard + 1)
                return total

            freq_rows = []
            for cid, name in scene_code_cid_to_name.items():
                path = get_scene_code_path(cid)
                t_count, i_count, a_count = own_counts[cid]
                row = [path, name, t_count, i_count, a_count, t_count + i_count + a_count]
                if has_subcodes:
                    row.append(total_with_descendants(cid))
                # Placeholder paths "(...)" sort last, mirroring the canvas layout
                sort_key = (path.startswith("("), (path + " > " + name).lower())
                freq_rows.append((sort_key, tuple(row)))
            freq_rows.sort(key=lambda r: r[0])
            headers = [_("Hierarchy Path"), _("Code"), _("Text"), _("Image"), _("A/V"), _("Total")]
            if has_subcodes:
                headers.append(_("Total incl. sub-codes"))
            add_table_with_headers(
                headers=headers,
                rows=[row for _key, row in freq_rows],
            )
        else:
            add_heading(_("Coding frequencies per code in the graph"))
            add_paragraph(_("No code nodes present in the graph."))
            add_paragraph("")

        # 13. Software citation
        app_version = getattr(self.app, 'version', 'QualCoder')
        tag = app_version.split("QualCoder ")[1] if "QualCoder " in app_version else "latest"
        add_bold_paragraph(_("Software citation:"))
        add_paragraph(f"Curtain C, Dröge K, Missaghieh--Poncet J, Salomón L. (2026) "
                      f"{app_version} [Computer software].")
        add_paragraph(f"Retrieved from https://github.com/ccbogel/QualCoder/releases/tag/{tag}")
        add_paragraph("")

        # 14. Save; clean up temp image AFTER packaging (addPicture stores by path)
        try:
            doc.save(filename)
            Message(self.app, _("Export successful"),
                    _("Analytical summary exported to:\n") + filename,
                    "information").exec()
        except Exception as e:
            logger.error(f"Error exporting graph summary: {e}")
            Message(self.app, _("Error"),
                    _("The file could not be saved:\n") + str(e),
                    "warning").exec()
        finally:
            if temp_img and os.path.exists(temp_img):
                try:
                    os.remove(temp_img)
                except OSError as err:
                    logger.warning(f"Could not remove temporary graph image: {err}")

    def save_graph(self):
        """ Save graph items.
        If a graph is currently loaded, prompts Update / New / Cancel:
          - Update overwrites the loaded graph in place (with empty-canvas guard).
          - New asks for a fresh name via DialogSaveSql.
          - Cancel aborts.
        If no graph is loaded, falls through directly to the New flow.
        """

        name = ""
        description = ""
        # Tables wiped on Update. gr_memo_item included so memo rows of the
        # previous grid never linger as duplicates after overwriting.
        _GRID_TABLES = ("graph", "gr_case_text_item", "gr_file_text_item", "gr_free_line_item",
                        "gr_free_text_item", "gr_cdct_line_item", "gr_cdct_text_item",
                        "gr_pix_item", "gr_av_item", "gr_memo_item")

        # Branch 1: a graph is already loaded > offer Update / New / Cancel
        if getattr(self, 'loaded_graph', None) is not None:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle(_("Save Graph"))
            dialog.setWindowFlags(dialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
            layout = QtWidgets.QVBoxLayout(dialog)
            label = QtWidgets.QLabel(_("Graph '") + self.loaded_graph['name']
                                     + _("' is loaded.\nDo you want to update it or save as a new graph?"))
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            button_box = QtWidgets.QHBoxLayout()
            btn_update = QtWidgets.QPushButton(_("Update"))
            btn_new = QtWidgets.QPushButton(_("New"))
            btn_cancel = QtWidgets.QPushButton(_("Cancel"))
            button_box.addWidget(btn_update)
            button_box.addWidget(btn_new)
            button_box.addWidget(btn_cancel)
            layout.addLayout(button_box)
            # Capture the user's choice via a single-cell list (closure-safe)
            result_action = ["Cancel"]

            def set_action(act):
                result_action[0] = act
                dialog.accept()

            btn_update.clicked.connect(lambda: set_action("Update"))
            btn_new.clicked.connect(lambda: set_action("New"))
            btn_cancel.clicked.connect(dialog.reject)
            dialog.exec()
            if result_action[0] == "Cancel":
                return
            if result_action[0] == "Update":
                # Guard against saving an empty canvas over a real graph. Only
                # node classes count; handles/labels/previews are ornamental.
                _node_classes = (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                                 FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem,
                                 MemoGraphicsItem)
                has_real_nodes = any(isinstance(it, _node_classes) for it in self.scene.items())
                if not has_real_nodes:
                    confirm_msg = _("The graph has no nodes or elements.\n\n"
                                    "Updating now will overwrite '") + self.loaded_graph['name'] \
                                    + _("' with an empty graph.\n\nProceed anyway?")
                    if not DialogConfirmDelete(self.app, confirm_msg).exec():
                        return
                name = self.loaded_graph['name']
                description = self.loaded_graph['description']
                # Wipe previous rows for this grid in a single transaction
                cur = self.app.conn.cursor()
                grid_to_delete = self.loaded_graph['grid']
                try:
                    for tbl in _GRID_TABLES:
                        cur.execute(f"delete from {tbl} where grid = ?", [grid_to_delete])
                    self.app.conn.commit()
                except Exception as err:
                    self.app.conn.rollback()
                    Message(self.app, _("Update error"),
                            _("Could not delete previous graph:\n") + str(err)).exec()
                    return
            # If "New", fall through with name="" so DialogSaveSql requests a name.

        # Branch 2: no name yet (no loaded graph, or user clicked "New")
        if name == "":
            ui_save = DialogSaveSql(self.app)
            ui_save.setWindowTitle(_("Save graph"))
            ui_save.ui.label_name.setText(_("Graph name"))
            ui_save.ui.label.hide()
            ui_save.ui.lineEdit_group.hide()
            ui_save.exec()
            name = ui_save.name
            if name == "":
                msg = _("Must have a name")
                Message(self.app, _("Cannot save"), msg).exec()
                return
            description = ui_save.description

        cur = self.app.conn.cursor()
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.scene.adjust_for_negative_positions()
        width, height = self.scene.suggested_scene_size()
        self.scene.set_width(width)
        self.scene.set_height(height)
        # Insert graphics items first, but not the lines, as need the insertids
        try:
            try:
                cur.execute("insert into graph (name, description, date, scene_width, scene_height) values(?,?,?,?,?)",
                            [name, description, now_date, width, height])
            except sqlite3.IntegrityError:
                Message(self.app, _("Name error"), _("This name already used. Choose another name.")).exec()
                self.app.conn.rollback()
                return
            cur.execute("select last_insert_rowid()")
            grid = cur.fetchone()[0]
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    sql = "insert into gr_cdct_text_item (grid,x,y,supercatid,catid,cid,font_size,bold,isvisible," \
                          "displaytext) values (?,?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql,
                                [grid, i.pos().x(), i.pos().y(), i.code_or_cat['supercatid'], i.code_or_cat['catid'],
                                 i.code_or_cat['cid'], i.font_size, i.bold, i.isVisible(), i.toPlainText()])
                if isinstance(i, CaseTextGraphicsItem):
                    sql = "insert into gr_case_text_item (grid,x,y,caseid,font_size,bold,color, displaytext) " \
                          "values (?,?,?,?,?,?,?,?)"
                    cur.execute(sql,
                                [grid, i.pos().x(), i.pos().y(), i.case_id, i.font_size, i.bold, i.color,
                                 i.toPlainText()])
                if isinstance(i, FileTextGraphicsItem):
                    sql = "insert into gr_file_text_item (grid,x,y,fid,font_size,bold,color, displaytext) " \
                          "values (?,?,?,?,?,?,?,?)"
                    cur.execute(sql,
                                [grid, i.pos().x(), i.pos().y(), i.file_id, i.font_size, i.bold, i.color,
                                 i.toPlainText()])
                if isinstance(i, PixmapGraphicsItem):
                    sql = "insert into gr_pix_item (grid,imid,x,y,px,py,w,h,filepath,tooltip,pdf_page) values " \
                          "(?,?,?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql, [grid, i.imid, i.pos().x(), i.pos().y(), i.px, i.py, i.pwidth, i.pheight, i.path_,
                                      i.toolTip(), i.pdf_page])
                if isinstance(i, AVGraphicsItem):
                    sql = "insert into gr_av_item (grid,avid,x,y,pos0,pos1,filepath,tooltip, color) values " \
                          "(?,?,?,?,?,?,?,?,?)"
                    cur.execute(sql,
                                [grid, i.avid, i.pos().x(), i.pos().y(), i.pos0, i.pos1, i.path_, i.toolTip(), i.color])
                if isinstance(i, FreeTextGraphicsItem):
                    sql = "insert into gr_free_text_item (grid,freetextid, x,y,free_text,font_size,bold,color,tooltip, " \
                          "ctid, memo_ctid, memo_imid, memo_avid) values (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    tt = i.toolTip()
                    cur.execute(sql,
                                [grid, i.freetextid, i.pos().x(), i.pos().y(), i.text, i.font_size, i.bold, i.color,
                                 tt, i.ctid, i.memo_ctid, i.memo_imid, i.memo_avid])
                    cur.execute("select last_insert_rowid()")  # the gfreeid
                    i.freetextid = cur.fetchone()[0]
                    cur.execute("update gr_free_text_item set freetextid=? where gfreeid=?", [i.freetextid, i.freetextid])
                # persist live memo nodes into gr_memo_item (v17). The memo body
                # is NOT stored here, it is read live from the source table on load.
                # gmemoid is captured back so gr_free_line_item can reference this memo.
                if isinstance(i, MemoGraphicsItem):
                    sql_mem = ("insert into gr_memo_item (grid, memo_source_type, memo_source_id, "
                               "x, y, color, font_size) values (?,?,?,?,?,?,?)")
                    cur.execute(sql_mem, [grid, i.memo_source_type, i.memo_source_id,
                                          i.pos().x(), i.pos().y(),
                                          getattr(i, 'color', 'blue') or 'blue',
                                          getattr(i, 'font_size', 9) or 9])
                    cur.execute("select last_insert_rowid()")
                    i.gmemoid = cur.fetchone()[0]
            self.app.conn.commit()
        except Exception as err:
            logger.error(str(err))
            self.app.conn.rollback()  # revert all changes
            raise

        # Insert the lines - after the freetextids are obtained
        for i in self.scene.items():
            try:
                if isinstance(i, LinkGraphicsItem):
                    # persist label + arrow_mode (v17 columns), otherwise
                    # relation labels and direction toggles are silently dropped on save.
                    sql = ("insert into gr_cdct_line_item (grid,fromcatid,fromcid,tocatid,tocid,color,"
                           "linewidth,linetype,isvisible,label,arrow_mode) values (?,?,?,?,?,?,?,?,?,?,?)")
                    cur.execute(sql, [grid, i.from_widget.code_or_cat['catid'], i.from_widget.code_or_cat['cid'],
                                      i.to_widget.code_or_cat['catid'], i.to_widget.code_or_cat['cid'],
                                      i.color, i.line_width, self.line_type_to_text(i.line_type),
                                      i.isVisible(),
                                      getattr(i, 'label', '') or '',
                                      getattr(i, 'arrow_mode', 'none') or 'none'])
                if isinstance(i, FreeLineGraphicsItem):
                    from_catid = None
                    try:
                        from_catid = i.from_widget.code_or_cat['catid']
                    except AttributeError:
                        pass
                    from_cid = None
                    try:
                        from_cid = i.from_widget.code_or_cat['cid']
                    except AttributeError:
                        pass
                    to_catid = None
                    try:
                        to_catid = i.to_widget.code_or_cat['catid']
                    except AttributeError:
                        pass
                    to_cid = None
                    try:
                        to_cid = i.to_widget.code_or_cat['cid']
                    except AttributeError:
                        pass
                    from_case_id = None
                    try:
                        from_case_id = i.from_widget.case_id
                    except AttributeError:
                        pass
                    from_file_id = None
                    try:
                        from_file_id = i.from_widget.file_id
                    except AttributeError:
                        pass
                    from_freetextid = None
                    try:
                        from_freetextid = i.from_widget.freetextid
                    except AttributeError:
                        pass
                    # memo endpoints are encoded into from/to_freetextid using a
                    # sentinel offset so they never collide with real freetextid values.
                    # The loader reverses the offset and looks up gr_memo_item instead.
                    if isinstance(i.from_widget, MemoGraphicsItem) and i.from_widget.gmemoid is not None:
                        from_freetextid = _MEMO_LINE_ID_OFFSET + i.from_widget.gmemoid
                    from_imid = None
                    try:
                        from_imid = i.from_widget.imid
                    except AttributeError:
                        pass
                    from_avid = None
                    try:
                        from_avid = i.from_widget.avid
                    except AttributeError:
                        pass
                    to_imid = None
                    try:
                        to_imid = i.to_widget.imid
                    except AttributeError:
                        pass
                    to_avid = None
                    try:
                        to_avid = i.to_widget.avid
                    except AttributeError:
                        pass
                    to_case_id = None
                    try:
                        to_case_id = i.to_widget.case_id
                    except AttributeError:
                        pass
                    to_file_id = None
                    try:
                        to_file_id = i.to_widget.file_id
                    except AttributeError:
                        pass
                    to_freetextid = None
                    try:
                        to_freetextid = i.to_widget.freetextid
                    except AttributeError:
                        pass
                    # Same memo-endpoint encoding for the to_widget side
                    if isinstance(i.to_widget, MemoGraphicsItem) and i.to_widget.gmemoid is not None:
                        to_freetextid = _MEMO_LINE_ID_OFFSET + i.to_widget.gmemoid
                    """ Free line linking options use catid/cid or caseid or fileid and last match text e.g. freetextitem """
                    # persist label + arrow_mode (v17 columns)
                    sql = ("insert into gr_free_line_item (grid,fromfreetextid,fromcatid,fromcid,fromcaseid,"
                           "fromfileid,fromimid,fromavid,tofreetextid,tocatid,tocid,tocaseid,tofileid,toimid,"
                           "toavid,color,linewidth,linetype,label,arrow_mode) "
                           "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
                    cur.execute(sql,
                                [grid, from_freetextid, from_catid, from_cid, from_case_id, from_file_id, from_imid,
                                 from_avid, to_freetextid, to_catid, to_cid, to_case_id, to_file_id, to_imid, to_avid,
                                 i.color, i.line_width, self.line_type_to_text(i.line_type),
                                 getattr(i, 'label', '') or '',
                                 getattr(i, 'arrow_mode', 'forward') or 'forward'])
                self.app.conn.commit()
            except Exception as err:
                logger.error(str(err))
                self.app.conn.rollback()  # Revert all changes
                raise

        self.app.delete_backup = False
        # Track the just-saved graph as the loaded one, so the next Save click
        # offers Update/New again (the loop is closed).
        self.loaded_graph = {'name': name, 'grid': grid, 'description': description,
                             'width': width, 'height': height}
        self.ui.label_loaded_graph.setText(
            _("Changing to another report will lose unsaved graph.") + "\n" + name)
        self.ui.label_loaded_graph.setToolTip(description)
        # Re-center after save so the user sees the canonical persisted layout
        self.finalize_graph_operation(fit_view=True)

    @staticmethod
    def line_type_to_text(line_type):
        """ Convert line type to text. for graph line items. """

        text_ = "solid"
        if line_type == QtCore.Qt.PenStyle.DotLine:
            text_ = "dotted"
        return text_

    def load_graph_menu(self):
        """ Menu on load graph button to choose load order of graph names. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        alphabet_asc_action = menu.addAction((_("Alphabet ascending")))
        alphabet_desc_action = menu.addAction((_("Alphabet descending")))
        date_asc_action = menu.addAction((_("Oldest to newest")))
        date_desc_action = menu.addAction((_("Newest to oldest")))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == alphabet_asc_action:
            self.load_graph_menu_option = _("Alphabet ascending")
        if action == alphabet_desc_action:
            self.load_graph_menu_option = _("Alphabet descending")
        if action == date_asc_action:
            self.load_graph_menu_option = _("Oldest to newest")
        if action == date_desc_action:
            self.load_graph_menu_option = _("Newest to oldest")
        self.ui.pushButton_loadgraph.setToolTip(_("Load graph") + "\n" + self.load_graph_menu_option)

    def remove_expired_graph_items(self):
        """ Some items may no longer exist in the database and need to be removed from the saved graph objects.
        Applies to: gr_case_text_item, gr_file_text_item, gr_pix_item, gr_av_item and
        gr_text_item for coded text, and for memos of coded text, av, images.
        """

        cur = self.app.conn.cursor()
        sql_pix = "SELECT imid FROM  gr_pix_item where imid not in (select imid from code_image)"
        cur.execute(sql_pix)
        res_pix = cur.fetchall()
        for r in res_pix:
            cur.execute("delete from gr_pix_item where imid=?", [r[0]])
            self.app.conn.commit()
        sql_av = "select avid from gr_av_item where avid not in (select avid from code_av)"
        cur.execute(sql_av)
        res_av = cur.fetchall()
        for r in res_av:
            cur.execute("delete from gr_av_item where avid=?", [r[0]])
            self.app.conn.commit()
        sql_case = "select caseid from gr_case_text_item where caseid not in (select caseid from cases)"
        cur.execute(sql_case)
        res_case = cur.fetchall()
        for r in res_case:
            # table is gr_case_text_item (gr_case_item does not exist)
            cur.execute("delete from gr_case_text_item where caseid=?", [r[0]])
            self.app.conn.commit()
        sql_file = "select fid from gr_file_text_item where fid not in (select id from source)"
        cur.execute(sql_file)
        res_file = cur.fetchall()
        for r in res_file:
            # table is gr_file_text_item (gr_file_item does not exist)
            cur.execute("delete from gr_file_text_item where fid=?", [r[0]])
            self.app.conn.commit()
        # Text codings
        sql_text = "select ctid from gr_free_text_item where ctid is not null and ctid != -1 and ctid not in " \
                   "(select ctid from code_text)"
        cur.execute(sql_text)
        res_text = cur.fetchall()
        for r in res_text:
            cur.execute("delete from gr_free_text_item where ctid=?", [r[0]])
            self.app.conn.commit()
        # Text coding memos
        sql_memo_text = "select memo_ctid from gr_free_text_item where memo_ctid is not null and memo_ctid not in " \
                        "(select ctid from code_text)"
        cur.execute(sql_memo_text)
        res_memo_text = cur.fetchall()
        for r in res_memo_text:
            cur.execute("delete from gr_free_text_item where memo_ctid=?", [r[0]])
            self.app.conn.commit()
        # Image coding memos
        sql_memo_image = "select memo_imid from gr_free_text_item where memo_imid is not null and memo_imid not in " \
                         "(select imid from code_image)"
        cur.execute(sql_memo_image)
        res_memo_image = cur.fetchall()
        for r in res_memo_image:
            cur.execute("delete from gr_free_text_item where memo_imid=?", [r[0]])
            self.app.conn.commit()
        # AV coding memos
        sql_memo_av = "select memo_avid from gr_free_text_item where memo_avid is not null and memo_avid not in " \
                      "(select avid from code_av)"
        cur.execute(sql_memo_av)
        res_memo_av = cur.fetchall()
        for r in res_memo_av:
            cur.execute("delete from gr_free_text_item where memo_avid=?", [r[0]])
            self.app.conn.commit()

    def update_coded_image_areas(self):
        """ Update coding area and memo the current information in gr_pix_item.
        """

        cur = self.app.conn.cursor()
        cur.execute("update gr_pix_item set px=(select x1 from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set py=(select y1 from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set w=(select width from code_image where code_image.imid=gr_pix_item.imid)")
        cur.execute("update gr_pix_item set h=(select height from code_image where code_image.imid=gr_pix_item.imid)")
        # Tooltips
        cur.execute("select grpixid, source.name, code_name.name, ifnull(code_image.memo,''), code_image.imid from "
                    "gr_pix_item join code_image on code_image.imid=gr_pix_item.imid "
                    "join code_name on code_name.cid= code_image.cid "
                    "join source on source.id=code_image.id")
        res = cur.fetchall()
        for r in res:
            tt = _("File: ") + r[1] + "\n"
            tt += _("Code: ") + r[2] + "\n"
            if self.app.settings['showids']:
                tt += f"imid: {r[4]}\n"
            tt += _("Memo: ") + r[3]
            cur.execute("update gr_pix_item set tooltip=? where grpixid=?", [tt, r[0]])
        self.app.conn.commit()

    def update_coded_av_segments(self):
        """ Update coding segment and memo to the current information in gr_av_item.
        """

        cur = self.app.conn.cursor()
        cur.execute("update gr_av_item set pos0=(select pos0 from code_av where code_av.avid=gr_av_item.avid)")
        cur.execute("update gr_av_item set pos1=(select pos1 from code_av where code_av.avid=gr_av_item.avid)")
        self.app.conn.commit()
        # Tooltips
        cur.execute("select gr_avid, source.name, code_name.name, gr_av_item.pos0, gr_av_item.pos1, "
                    "ifnull(code_av.memo,''), code_av.avid from gr_av_item "
                    "join code_av on code_av.avid=gr_av_item.avid "
                    "join code_name on code_name.cid= code_av.cid "
                    "join source on source.id=code_av.id")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                tt += f"{r[3]} - {r[4]}\n"
                if self.app.settings['showids']:
                    tt += f"avid: {r[6]}\n"
                tt += _("Memo: ") + r[5]
                cur.execute("update gr_av_item set tooltip=? where gr_avid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass

    def update_coded_text_tooltip_files_codes_and_memos(self):
        """ Update the text coding codename and memo to the current information in gr_free_text_item.
        """

        cur = self.app.conn.cursor()
        # Tooltips
        cur.execute("select gfreeid, source.name, code_name.name, ifnull(code_text.memo,''), code_text.ctid "
                    "from gr_free_text_item "
                    "join code_text on code_text.ctid=gr_free_text_item.ctid "
                    "join code_name on code_name.cid= code_text.cid "
                    "join source on source.id=code_text.fid "
                    "where gr_free_text_item.ctid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"ctid: {r[4]}\n"
                tt += _("Memo: ") + r[3]
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass

    def update_memo_tooltip_files_and_codes(self):
        """ For the text memo items. Update the tooltip file name, code name and memo to the current information
        in gr_free_text_item.
        """

        cur = self.app.conn.cursor()
        # Tooltips for memo text codings
        cur.execute("select gfreeid, source.name, code_name.name, code_text.seltext, code_text.ctid "
                    "from gr_free_text_item "
                    "join code_text on code_text.ctid=gr_free_text_item.memo_ctid "
                    "join code_name on code_name.cid= code_text.cid "
                    "join source on source.id=code_text.fid "
                    "where gr_free_text_item.memo_ctid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"ctid: {r[4]}\n"
                tt += _("Memo for: ") + r[3]
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass
        # Tooltips for memo image codings
        cur.execute("select gfreeid, source.name, code_name.name, x1,y1,width,height, code_image.imid "
                    "from gr_free_text_item "
                    "join code_image on code_image.imid=gr_free_text_item.memo_imid "
                    "join code_name on code_name.cid= code_image.cid "
                    "join source on source.id=code_image.id "
                    "where gr_free_text_item.memo_imid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"imid: {r[7]}\n"
                tt += _("Memo for area: ") + f"x:{int(r[3])} y:{int(r[4])} " + _("width:") + \
                      str(int(r[5])) + " " + _("height:") + str(int(r[6]))
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass
        # Tooltips for memo AV codings
        cur.execute(
            "select gfreeid, source.name, code_name.name, code_av.pos0, code_av.pos1, code_av.avid "
            "from gr_free_text_item "
            "join code_av on code_av.avid=gr_free_text_item.memo_avid "
            "join code_name on code_name.cid= code_av.cid "
            "join source on source.id=code_av.id "
            "where gr_free_text_item.memo_avid > 0")
        res = cur.fetchall()
        for r in res:
            try:
                tt = _("File: ") + r[1] + "\n"
                tt += _("Code: ") + r[2] + "\n"
                if self.app.settings['showids']:
                    tt += f"avid: {r[5]}\n"
                tt += _("Memo for duration: ") + f"{int(r[3])}  - {int(r[4])}" + _("msecs")
                cur.execute("update gr_free_text_item set tooltip=? where gfreeid=?", [tt, r[0]])
                self.app.conn.commit()
            except IndexError:
                pass

    def load_graph(self):
        """ Load a saved graph.
        Load each text component first, then link the cdct_line_items then the free_lines_items.
        For cdct_text_items, fill extra details:
        eg name, memo, date?, owner?, color, child_names?
        """

        self.update_coded_image_areas()
        self.update_coded_av_segments()
        self.update_coded_text_tooltip_files_codes_and_memos()
        self.update_memo_tooltip_files_and_codes()
        # picker with preview (list left, preview right); the
        # ordering option from the load button menu is passed through.
        ui = DialogGraphPicker(self.app, _("Load graph"), multi=False,
                               order_option=self.load_graph_menu_option)
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            return
        graph = selected[0]
        # undo history is per-graph. Loading a graph starts a fresh
        # history; undo never restores content that belonged to another graph.
        self._undo_stack.clear()
        # track the loaded graph (used by saved-graph sync and Update flow)
        self.loaded_graph = graph
        self.remove_expired_graph_items()
        self.scene.clear()
        self.scene.set_width(graph['width'])
        self.scene.set_height(graph['height'])
        grid = graph['grid']
        err_msg = self.load_code_or_cat_text_graphics_items(grid)
        err_msg += self.load_file_text_graphics_items(grid)
        err_msg += self.load_case_text_graphics_items(grid)
        err_msg += self.load_free_text_graphics_items(grid)
        err_msg += self.load_pixmap_graphics_items(grid)
        err_msg += self.load_av_graphics_items(grid)
        # load memo nodes BEFORE lines so line endpoints resolve correctly
        err_msg += self.load_memo_graphics_items(grid)
        # Load lines
        self.load_cdct_line_graphics_items(grid)
        self.load_free_line_graphics_items(grid)
        # restore collapsed state and segment visibility after loading
        for item in self.scene.items():
            if type(item).__name__ == "TextGraphicsItem":
                children_names = item.code_or_cat.get('child_names', [])
                if children_names:
                    children_items = [child for child in self.scene.items()
                                      if type(child).__name__ == "TextGraphicsItem"
                                      and child != item
                                      and child.code_or_cat['name'] in children_names]
                    # All children hidden -> the parent was saved collapsed
                    if children_items and all(not child.isVisible() for child in children_items):
                        item.is_collapsed = True
            elif type(item).__name__ in ("FreeTextGraphicsItem", "PixmapGraphicsItem", "AVGraphicsItem"):
                if hasattr(item, 'code_or_cat') and item.code_or_cat is not None:
                    item_cid = item.code_or_cat.get('cid')
                    if item_cid is not None:
                        # Hide segment if its parent code node is hidden
                        parent_node = next((node for node in self.scene.items()
                                            if type(node).__name__ == "TextGraphicsItem"
                                            and node.code_or_cat.get('cid') == item_cid), None)
                        if parent_node and not parent_node.isVisible():
                            item.hide()
        if err_msg != "":
            Message(self.app, _("Load graph errors"), err_msg).exec()
        label = _("Changing to another report will lose unsaved graph.") + "\n" + graph['name']
        self.ui.label_loaded_graph.setText(label)
        self.ui.label_loaded_graph.setToolTip(graph['description'])
        # single consolidated refresh (sync + fit view + minimap)
        self.finalize_graph_operation(fit_view=True)

    def load_cdct_line_graphics_items(self, grid):
        """ Find the to and from widgets using matching catid and cid.
          Then when found add the line item. """

        # SELECT includes label and arrow_mode (v17 columns) so labels
        # and direction toggles persist across save/load cycles.
        sql = ("select fromcatid,fromcid,tocatid,tocid,linewidth,linetype,color,"
               "isvisible,glineid,ifnull(label,''),ifnull(arrow_mode,'none') "
               "from gr_cdct_line_item where grid=?")
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        result = cur.fetchall()
        res = []
        keys = ("fromcatid", "fromcid", "tocatid", "tocid", "linewidth", "linetype", "color",
                "isvisible", "glineid", "label", "arrow_mode")
        for row in result:
            res.append(dict(zip(keys, row)))
        for line in res:
            # Add link which includes the scene text items and associated data, add links before text_items
            from_item = None
            to_item = None
            for i in self.scene.items():
                if isinstance(i, TextGraphicsItem):
                    if from_item is None and i.code_or_cat['catid'] == line['fromcatid'] and \
                            i.code_or_cat['cid'] == line['fromcid']:
                        from_item = i
                    if to_item is None and i.code_or_cat['catid'] == line['tocatid'] and \
                            i.code_or_cat['cid'] == line['tocid']:
                        to_item = i
            if from_item is not None and to_item is not None:
                # pass label kwarg so LinkGraphicsItem builds its label widget
                item = LinkGraphicsItem(from_item, to_item, line['linewidth'], line['linetype'],
                                        line['color'], line['isvisible'], label=line['label'])
                # restore arrow_mode (not a ctor kwarg in LinkGraphicsItem)
                if line['arrow_mode']:
                    item.arrow_mode = line['arrow_mode']
                self.scene.addItem(item)
            else:
                cur.execute("delete from gr_cdct_line_item where glineid=?", [line['glineid']])
                self.app.conn.commit()
        return

    def load_free_line_graphics_items(self, grid):
        """ Find the to and from widgets.
        Several matching options: catid and cid; fileid; caseid; imid; avid; freetextid; gmemoid.
        Then when found add the free line item. """

        # SELECT includes label + arrow_mode (v17)
        sql = ("select fromfreetextid,fromcatid,fromcid,fromcaseid,fromfileid,fromimid,fromavid,"
               "tofreetextid,tocatid,tocid,tocaseid,tofileid,toimid,toavid,color,linewidth,linetype,gflineid,"
               "ifnull(label,''),ifnull(arrow_mode,'forward') "
               "from gr_free_line_item where grid=?")
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        result = cur.fetchall()
        res = []
        keys = ("fromfreetextid", "fromcatid", "fromcid", "fromcaseid", "fromfileid", "fromimid", "fromavid",
                "tofreetextid", "tocatid", "tocid", "tocaseid", "tofileid", "toimid", "toavid", "color",
                "linewidth", "linetype", "gflineid", "label", "arrow_mode")
        for row in result:
            res.append(dict(zip(keys, row)))
        for line in res:
            from_item = None
            to_item = None
            # detect memo endpoints using the sentinel offset BEFORE matching
            # regular freetextid values. gmemoid = stored value - offset.
            from_memo_gmemoid = None
            to_memo_gmemoid = None
            if line['fromfreetextid'] is not None and line['fromfreetextid'] >= _MEMO_LINE_ID_OFFSET:
                from_memo_gmemoid = line['fromfreetextid'] - _MEMO_LINE_ID_OFFSET
            if line['tofreetextid'] is not None and line['tofreetextid'] >= _MEMO_LINE_ID_OFFSET:
                to_memo_gmemoid = line['tofreetextid'] - _MEMO_LINE_ID_OFFSET
            for i in self.scene.items():
                if from_item is None and from_memo_gmemoid is not None and isinstance(i, MemoGraphicsItem):
                    if getattr(i, 'gmemoid', None) == from_memo_gmemoid:
                        from_item = i
                if from_item is None and line['fromcaseid'] is not None and isinstance(i, CaseTextGraphicsItem):
                    if i.case_id == line['fromcaseid']:
                        from_item = i
                if from_item is None and line['fromfileid'] is not None and isinstance(i, FileTextGraphicsItem):
                    if i.file_id == line['fromfileid']:
                        from_item = i
                if from_item is None and (line['fromcatid'] is not None or line['fromcid'] is not None) \
                        and isinstance(i, TextGraphicsItem):
                    if i.code_or_cat['catid'] == line['fromcatid'] and i.code_or_cat['cid'] == line['fromcid']:
                        from_item = i
                # skip freetextid match when value is in memo-sentinel range
                if from_item is None and line['fromfreetextid'] is not None \
                        and line['fromfreetextid'] < _MEMO_LINE_ID_OFFSET \
                        and isinstance(i, FreeTextGraphicsItem):
                    if i.freetextid == line['fromfreetextid']:
                        from_item = i
                if from_item is None and line['fromimid'] is not None and isinstance(i, PixmapGraphicsItem):
                    if i.imid == line['fromimid']:
                        from_item = i
                if from_item is None and line['fromavid'] is not None and isinstance(i, AVGraphicsItem):
                    if i.avid == line['fromavid']:
                        from_item = i
            for i in self.scene.items():
                if to_item is None and to_memo_gmemoid is not None and isinstance(i, MemoGraphicsItem):
                    if getattr(i, 'gmemoid', None) == to_memo_gmemoid:
                        to_item = i
                if to_item is None and line['tocaseid'] is not None and isinstance(i, CaseTextGraphicsItem):
                    if i.case_id == line['tocaseid']:
                        to_item = i
                if to_item is None and line['tofileid'] is not None and isinstance(i, FileTextGraphicsItem):
                    if i.file_id == line['tofileid']:
                        to_item = i
                if to_item is None and (line['tocatid'] is not None or line['tocid'] is not None) \
                        and isinstance(i, TextGraphicsItem):
                    if i.code_or_cat['catid'] == line['tocatid'] and i.code_or_cat['cid'] == line['tocid']:
                        to_item = i
                if to_item is None and line['tofreetextid'] is not None \
                        and line['tofreetextid'] < _MEMO_LINE_ID_OFFSET \
                        and isinstance(i, FreeTextGraphicsItem):
                    if i.freetextid == line['tofreetextid']:
                        to_item = i
                if to_item is None and line['toimid'] is not None and isinstance(i, PixmapGraphicsItem):
                    if i.imid == line['toimid']:
                        to_item = i
                if to_item is None and line['toavid'] is not None and isinstance(i, AVGraphicsItem):
                    if i.avid == line['toavid']:
                        to_item = i
            if from_item is not None and to_item is not None:
                # pass label kwarg + restore arrow_mode after construction
                line_item = FreeLineGraphicsItem(from_item, to_item, line['color'], line['linewidth'],
                                                 line['linetype'], label=line['label'])
                if line['arrow_mode']:
                    line_item.arrow_mode = line['arrow_mode']
                    line_item.redraw()  # apply new arrow_mode visually
                self.scene.addItem(line_item)
            else:
                cur.execute("delete from gr_free_line_item where gflineid=?", [line['gflineid']])
                self.app.conn.commit()
        return

    def load_case_text_graphics_items(self, grid):
        """ Load the case graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_case = "select x, y, caseid,font_size, color, bold, displaytext from gr_case_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_case, [grid])
        res = cur.fetchall()
        for i in res:
            cur.execute("select name, ifnull(memo,'') from cases where caseid=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(
                    CaseTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5], i[6]))
            else:
                err_msg += _("Case: ") + str(i[2]) + " "
        return err_msg

    def load_file_text_graphics_items(self, grid):
        """ Load the file graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_file = "select x, y, fid, font_size, color, bold, displaytext from gr_file_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_file, [grid])
        res = cur.fetchall()
        for i in res:
            cur.execute("select name, ifnull(memo, '') from source where id=?", [i[2]])
            res_name = cur.fetchone()
            if res_name is not None:
                self.scene.addItem(
                    FileTextGraphicsItem(self.app, res_name[0], i[2], i[0], i[1], i[3], i[4], i[5], i[6]))
            else:
                err_msg += _("File: ") + str(i[2]) + " "
        return err_msg

    def load_free_text_graphics_items(self, grid):
        """ Load the free text graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql = "select freetextid, x, y, free_text, font_size, color, bold, tooltip, ctid, memo_ctid, memo_imid, " \
              "memo_avid, gfreeid from gr_free_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [grid])
        res = cur.fetchall()
        for i in res:
            item = FreeTextGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[8], i[9], i[10], i[11],
                                        i[12])
            if i[7] != "":
                item.setToolTip(i[7])
            self.scene.addItem(item)
        return err_msg

    def load_pixmap_graphics_items(self, grid):
        """ Load pixmap graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_pix = "select imid, x,y, px,py ,w,h, filepath, tooltip, pdf_page from gr_pix_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_pix, [grid])
        res = cur.fetchall()
        for i in res:
            # app, imid=-1, x=10, y=10, px=0, py=0, pwidth=0, pheight=0, path_="", grpixid=None, pdf_page=None
            item = PixmapGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7], grid, i[9])
            if i[8] != "":
                item.setToolTip(i[8])
            self.scene.addItem(item)
        return err_msg

    def load_av_graphics_items(self, grid):
        """ Load audio/video graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_av = "select avid, x, y, pos0,pos1,filepath, tooltip, color from gr_av_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_av, [grid])
        res = cur.fetchall()
        for i in res:
            item = AVGraphicsItem(self.app, i[0], i[1], i[2], i[3], i[4], i[5], i[7])
            if i[6] != "":
                item.setToolTip(i[6])
            self.scene.addItem(item)
        return err_msg

    def load_memo_graphics_items(self, grid):
        """ load MemoGraphicsItem nodes from gr_memo_item (v17).
        Tolerant to schema absence: if the table doesn't exist yet (project not
        migrated), returns silently. The memo body is fetched live from the source
        table by MemoGraphicsItem._refresh_memo; only the anchor + position are
        recreated here. gmemoid is preserved so gr_free_line_item rows referencing
        memo endpoints (sentinel offset) resolve to the right node.
        param: grid : Integer
        """

        err_msg = ""
        cur = self.app.conn.cursor()
        try:
            cur.execute("select gmemoid, memo_source_type, memo_source_id, x, y, "
                        "ifnull(color,'blue'), ifnull(font_size,9) "
                        "from gr_memo_item where grid=?", [grid])
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Table doesn't exist yet (pre-v16 project), silently skip.
            return err_msg
        for r in rows:
            gmemoid, src_type, src_id, x, y, color, font_size = r
            try:
                memo_node = MemoGraphicsItem(self.app, src_type, src_id, x, y)
                memo_node.gmemoid = gmemoid
                if color:
                    memo_node.color = color
                if font_size:
                    memo_node.font_size = font_size
                # Verify the source still exists; if not, drop the row and skip the node
                select_sql, _u, params = memo_node._get_sql_and_params()
                if select_sql is not None:
                    cur.execute(select_sql, params)
                    if cur.fetchone() is None:
                        cur.execute("delete from gr_memo_item where gmemoid=?", [gmemoid])
                        self.app.conn.commit()
                        continue
                self.scene.addItem(memo_node)
            except Exception as e:
                logger.warning(f"Could not restore memo node gmemoid={gmemoid}: {e}")
                err_msg += _("Memo: ") + str(gmemoid) + " "
        return err_msg

    def load_code_or_cat_text_graphics_items(self, grid):
        """ Load the code or category graphics items.
        param: grid : Integer
        """

        err_msg = ""
        sql_cdct = "select x, y, supercatid, catid, cid, font_size, bold, isvisible, displaytext " \
                   "from gr_cdct_text_item where grid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql_cdct, [grid])
        res_cdct = cur.fetchall()
        for i in res_cdct:
            name = ""
            color = '#FFFFFF'  # Default / needed for category items
            supercid = None
            if i[4] is not None:
                # (sub-codes): also read supercid so sub-code -> parent code
                # lines survive the reactive sync after loading a saved graph.
                cur.execute("select name, color, supercid from code_name where cid=?", [i[4]])
                res = cur.fetchone()
                if res is not None:
                    name = res[0]
                    color = res[1]
                    supercid = res[2]
            else:
                cur.execute("select name from code_cat where catid=?", [i[3]])
                res = cur.fetchone()
                if res is not None:
                    name = res[0]
                    color = '#FFFFFF'
            if name != "":
                cdct = {'name': name, 'supercatid': i[2], 'catid': i[3], 'cid': i[4], 'x': i[0], 'y': i[1],
                        'color': color, 'displaytext': i[8], 'supercid': supercid}
                cdct['child_names'] = self.named_children_of_node(cdct)
                self.scene.addItem(TextGraphicsItem(self.app, cdct, i[5], i[6], i[7]))
            else:
                # Code or category has been deleted
                cdcat = _("Category")
                if i[4] is not None:
                    cdcat = _("Code")
                err_msg += cdcat + _(" does not exist: ") + f"{i[3]} {i[4]} "
                cur.execute("delete from gr_cdct_text_item where grid=? and supercatid=? and catid=? and cid=?",
                            [grid, i[2], i[3], i[4]])
                self.app.conn.commit()
        return err_msg

    def delete_saved_graph(self):
        """ Delete saved graph and its items.
        Need a list of dictionaries with a dictionary item called 'name'. """

        cur = self.app.conn.cursor()
        # picker with preview, multi-selection for batch delete
        ui = DialogGraphPicker(self.app, _("Delete stored graphs"), multi=True)
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        names = ""
        for s in selection:
            names = names + s['name'] + "\n"
        ui = DialogConfirmDelete(self.app, names)
        ok = ui.exec()
        if not ok:
            return
        # Delete graph entry and all its items
        try:
            for s in selection:
                cur.execute("delete from graph where grid = ?", [s['grid']])
                cur.execute("delete from gr_case_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_file_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_free_line_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_free_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_cdct_line_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_cdct_text_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_pix_item where grid = ?", [s['grid']])
                cur.execute("delete from gr_av_item where grid = ?", [s['grid']])
                # gr_memo_item rows (v17) are deleted with the graph too
                cur.execute("delete from gr_memo_item where grid = ?", [s['grid']])
            self.app.conn.commit()
        except Exception as err:
            logger.error(str(err))
            self.app.conn.rollback()  # revert all changes
            raise
        self.app.delete_backup = False


class DialogSelectGraphBranch(QDialog):
    """ self-contained branch selector for the graph
    Shows the full category / code / sub-code hierarchy with the
    code colors, multi-selection enabled. Returns stable keys in
    self.selected_keys:
        None            : All
        ('cat', catid)  : a category (top level or nested)
        ('code', cid)   : a code or sub-code
    """

    def __init__(self, app, codes, categories, parent=None):
        super().__init__(parent)
        self.app = app
        self.selected_keys = []
        self.setWindowTitle(_("Select code tree branch"))
        try:
            self.setStyleSheet("* {font-size:" + str(app.settings['fontsize']) + "pt} ")
        except Exception:
            pass
        self.resize(440, 560)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(
            _("Select branches to display (categories, codes or sub-codes), or All:")))
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.tree)
        # "All" as the first, pre-selected item
        all_item = QtWidgets.QTreeWidgetItem([_("All")])
        all_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, None)
        self.tree.addTopLevelItem(all_item)
        self._build_tree(codes, categories)
        self.tree.expandAll()
        self.tree.setCurrentItem(all_item)
        self.tree.itemDoubleClicked.connect(lambda *_a: self.accept())
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_item(self, parent, text, key, color=None):
        it = QtWidgets.QTreeWidgetItem([text])
        it.setData(0, QtCore.Qt.ItemDataRole.UserRole, key)
        # code colour as background with contrast text (categories stay neutral)
        if color:
            it.setBackground(0, QtGui.QBrush(QtGui.QColor(color)))
            it.setForeground(0, QtGui.QBrush(QtGui.QColor(TextColor(color).recommendation)))
        if parent is None:
            self.tree.addTopLevelItem(it)
        else:
            parent.addChild(it)
        return it

    def _build_tree(self, codes, categories):
        """ Categories (recursively), with their codes, and codes' sub-codes. Free
        codes (no category, no parent code) are added at the top level too. """

        def add_subcodes(parent_item, parent_cid):
            for code in codes:
                if code.get('supercid') == parent_cid:
                    it = self._add_item(parent_item, code['name'].strip(), ('code', code['cid']),
                                        color=code.get('color'))
                    add_subcodes(it, code['cid'])

        def add_codes_of_category(parent_item, catid):
            for code in codes:
                if code.get('catid') == catid and code.get('supercid') is None:
                    it = self._add_item(parent_item, code['name'].strip(), ('code', code['cid']),
                                        color=code.get('color'))
                    add_subcodes(it, code['cid'])

        def add_categories(parent_item, supercatid):
            for cat in categories:
                if cat.get('supercatid') == supercatid:
                    it = self._add_item(parent_item, cat['name'].strip(), ('cat', cat['catid']))
                    add_categories(it, cat['catid'])
                    add_codes_of_category(it, cat['catid'])

        add_categories(None, None)  # top-level categories and their subtrees
        for code in codes:  # free codes: no category and not a sub-code
            if code.get('catid') is None and code.get('supercid') is None:
                it = self._add_item(None, code['name'].strip(), ('code', code['cid']),
                                    color=code.get('color'))
                add_subcodes(it, code['cid'])

    def accept(self):
        # unique keys; "All" (None) collapses the rest
        self.selected_keys = []
        for it in self.tree.selectedItems():
            key = it.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if key not in self.selected_keys:
                self.selected_keys.append(key)
        if None in self.selected_keys:
            self.selected_keys = [None]
        super().accept()


class DialogGraphPicker(QDialog):
    """ Picker for Load graph / Delete graphs with live preview. """

    def __init__(self, app, title, multi=False, order_option="Alphabet ascending", parent=None):
        super().__init__(parent)
        self.app = app
        from .GUI.ui_dialog_graph_picker import Ui_Dialog_graph_picker
        self.ui = Ui_Dialog_graph_picker()
        self.ui.setupUi(self)
        self.setWindowTitle(title)
        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        if multi:
            self.ui.listWidget_graphs.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.preview_scene = QtWidgets.QGraphicsScene(self)
        self.ui.graphicsView_preview.setScene(self.preview_scene)
        # sort options now live inside the picker itself,
        # initialized from the load-button menu option and changeable on the fly.
        self._order_keys = ["Alphabet ascending", "Alphabet descending",
                            "Oldest to newest", "Newest to oldest"]
        for key in self._order_keys:
            self.ui.comboBox_order.addItem(_(key))
        if order_option in self._order_keys:
            self.ui.comboBox_order.setCurrentIndex(self._order_keys.index(order_option))
        self.ui.comboBox_order.currentIndexChanged.connect(self._populate_list)
        self.ui.listWidget_graphs.currentItemChanged.connect(self._on_current_changed)
        self.ui.listWidget_graphs.itemDoubleClicked.connect(lambda *_a: self.accept())
        self.ui.buttonBox.accepted.connect(self.accept)
        self.ui.buttonBox.rejected.connect(self.reject)
        self._populate_list()

    def _populate_list(self, *_args):
        """ Fill (or re-fill) the graph list using the selected sort order. """
        order_option = self._order_keys[self.ui.comboBox_order.currentIndex()]
        sql = "select name, grid, description, scene_width, scene_height from graph order by upper(name) asc"
        if order_option == "Alphabet descending":
            sql = "select name, grid, description, scene_width, scene_height from graph order by upper(name) desc"
        if order_option == "Oldest to newest":
            sql = "select name, grid, description, scene_width, scene_height from graph order by date asc"
        if order_option == "Newest to oldest":
            sql = "select name, grid, description, scene_width, scene_height from graph order by date desc"
        self.ui.listWidget_graphs.clear()
        cur = self.app.conn.cursor()
        cur.execute(sql)
        for r in cur.fetchall():
            item = QtWidgets.QListWidgetItem(r[0])
            item.setData(QtCore.Qt.ItemDataRole.UserRole,
                         {'name': r[0], 'grid': r[1], 'description': r[2],
                          'width': r[3], 'height': r[4]})
            self.ui.listWidget_graphs.addItem(item)
        if self.ui.listWidget_graphs.count() > 0:
            self.ui.listWidget_graphs.setCurrentRow(0)
        else:
            self.preview_scene.clear()
            self.ui.label_description.setText("")

    def get_selected(self):
        """ Return the list of selected graph dictionaries
        (name, grid, description, width, height). """
        selected = []
        for item in self.ui.listWidget_graphs.selectedItems():
            selected.append(item.data(QtCore.Qt.ItemDataRole.UserRole))
        return selected

    def _on_current_changed(self, current, _previous):
        if current is None:
            self.preview_scene.clear()
            self.ui.label_description.setText("")
            return
        data = current.data(QtCore.Qt.ItemDataRole.UserRole)
        self.ui.label_description.setText(data.get('description') or "")
        self._render_preview(data['grid'])

    def _preview_text(self, text, font_size=9, bold=False, text_color="#000000", max_len=40):
        text = str(text or "")
        if len(text) > max_len:
            text = text[:max_len - 2] + "\u2026"
        t = QtWidgets.QGraphicsSimpleTextItem(text)
        f = QtGui.QFont()
        f.setPointSize(max(6, int(font_size or 9)))
        f.setBold(bool(bold))
        t.setFont(f)
        try:
            t.setBrush(QtGui.QBrush(QtGui.QColor(text_color)))
        except Exception:
            t.setBrush(QtGui.QBrush(QtGui.QColor("#000000")))
        return t

    def _preview_code_or_cat(self, x, y, text, color_hex, font_size, bold, is_category):
        """ TextGraphicsItem look: solid color rect (white for categories),
        contrast text color, categories default to bold. """
        if is_category:
            color_hex = "#FFFFFF"
        try:
            contrast = TextColor(color_hex).recommendation
        except Exception:
            contrast = "#000000"
        t = self._preview_text(text, font_size, bold or is_category, contrast)
        br = t.boundingRect()
        rect = QtWidgets.QGraphicsRectItem(br.adjusted(-3, -2, 3, 2))
        rect.setBrush(QtGui.QBrush(QtGui.QColor(color_hex)))
        rect.setPen(QtGui.QPen(QtGui.QColor("#B0B0B0"), 0.5) if is_category
                    else QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
        rect.setPos(x, y)
        t.setParentItem(rect)
        rect.setZValue(1)
        self.preview_scene.addItem(rect)
        return rect.sceneBoundingRect()

    def _preview_case(self, x, y, text, font_size, bold, text_color):
        """ CaseTextGraphicsItem look: rounded rect, orange border, light bg. """
        t = self._preview_text(text, font_size, bold, text_color if text_color != "white" else "#FFFFFF")
        br = t.boundingRect().adjusted(-6, -4, 6, 4)
        path = QtGui.QPainterPath()
        path.addRoundedRect(br, 12, 12)
        shape = QtWidgets.QGraphicsPathItem(path)
        shape.setBrush(QtGui.QBrush(QtGui.QColor("#101010" if text_color == "white" else "#fafafa")))
        shape.setPen(QtGui.QPen(QtGui.QColor("#F57C00"), 2))
        shape.setPos(x, y)
        t.setParentItem(shape)
        shape.setZValue(1)
        self.preview_scene.addItem(shape)
        return shape.sceneBoundingRect()

    def _preview_file(self, x, y, text, font_size, bold, text_color):
        """ FileTextGraphicsItem look: folded-corner note, blue border. """
        t = self._preview_text(text, font_size, bold, text_color if text_color != "white" else "#FFFFFF")
        br = t.boundingRect().adjusted(-4, -3, 8, 3)
        w, h, fold = br.width(), br.height(), 8
        poly = QtGui.QPolygonF([
            QtCore.QPointF(br.left(), br.top()),
            QtCore.QPointF(br.left() + w - fold, br.top()),
            QtCore.QPointF(br.left() + w, br.top() + fold),
            QtCore.QPointF(br.left() + w, br.top() + h),
            QtCore.QPointF(br.left(), br.top() + h)])
        shape = QtWidgets.QGraphicsPolygonItem(poly)
        shape.setBrush(QtGui.QBrush(QtGui.QColor("#101010" if text_color == "white" else "#fafafa")))
        shape.setPen(QtGui.QPen(QtGui.QColor("#1976D2"), 2))
        shape.setPos(x, y)
        fold_line = QtWidgets.QGraphicsLineItem(
            br.left() + w - fold, br.top(), br.left() + w - fold, br.top() + fold, shape)
        fold_line.setPen(QtGui.QPen(QtGui.QColor("#1976D2"), 2))
        t.setParentItem(shape)
        shape.setZValue(1)
        self.preview_scene.addItem(shape)
        return shape.sceneBoundingRect()

    def _preview_free_text(self, x, y, text, font_size, bold, text_color):
        """ FreeTextGraphicsItem look: plain rect, #fafafa bg (dark if the text
        color is white), the stored color is the TEXT color. """
        tc = text_color or "black"
        t = self._preview_text(text, font_size, bold,
                               "#FFFFFF" if tc == "white" else tc, max_len=60)
        br = t.boundingRect().adjusted(-3, -2, 3, 2)
        rect = QtWidgets.QGraphicsRectItem(br)
        rect.setBrush(QtGui.QBrush(QtGui.QColor("#101010" if tc == "white" else "#fafafa")))
        rect.setPen(QtGui.QPen(QtGui.QColor("#909090"), 0.5))
        rect.setPos(x, y)
        t.setParentItem(rect)
        rect.setZValue(1)
        self.preview_scene.addItem(rect)
        return rect.sceneBoundingRect()

    def _preview_memo(self, x, y, memo_source_type, memo_source_id, font_size):
        """ MemoGraphicsItem look: light blue rounded rect, dashed blue border,
        blue text, body read live from the source table. """
        type_map = {
            'code': "select ifnull(memo,'') from code_name where cid=?",
            'category': "select ifnull(memo,'') from code_cat where catid=?",
            'code_text': "select ifnull(memo,'') from code_text where ctid=?",
            'code_image': "select ifnull(memo,'') from code_image where imid=?",
            'code_av': "select ifnull(memo,'') from code_av where avid=?",
            'case': "select ifnull(memo,'') from cases where caseid=?",
            'file': "select ifnull(memo,'') from source where id=?",
        }
        body = ""
        sql = type_map.get(memo_source_type)
        if sql:
            try:
                cur = self.app.conn.cursor()
                cur.execute(sql, [memo_source_id])
                res = cur.fetchone()
                body = res[0] if res else ""
            except Exception:
                body = ""
        t = QtWidgets.QGraphicsTextItem()  # wrapping text like the real memo node
        f = QtGui.QFont()
        f.setPointSize(max(6, int(font_size or 9)))
        t.setFont(f)
        t.setDefaultTextColor(safe_color("blue"))
        display = body[:120] + "\u2026" if len(body) > 120 else (body or _("Memo"))
        t.setPlainText(display)
        t.setTextWidth(180)
        br = t.boundingRect().adjusted(-4, -3, 4, 3)
        path = QtGui.QPainterPath()
        path.addRoundedRect(br, 6, 6)
        shape = QtWidgets.QGraphicsPathItem(path)
        shape.setBrush(QtGui.QBrush(QtGui.QColor("#E3F2FD")))
        pen = QtGui.QPen(QtGui.QColor("#1565C0"), 1)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        shape.setPen(pen)
        shape.setPos(x, y)
        t.setParentItem(shape)
        shape.setZValue(1)
        self.preview_scene.addItem(shape)
        return shape.sceneBoundingRect()

    def _preview_pixmap(self, x, y, px, py, w, h, filepath, pdf_page):
        """ PixmapGraphicsItem look: the actual image, cropped and scaled to a
        maximum of 200px like the real item. Falls back to a gray placeholder. """
        try:
            abs_path_ = self.app.project_path + (filepath or "")
            if (filepath or "")[0:7] == "images:":
                abs_path_ = filepath[7:]
            if pdf_page is not None:
                source_path = ""
                if (filepath or "")[:6] == "/docs/":
                    source_path = f"{self.app.project_path}/documents/{filepath[6:]}"
                if (filepath or "")[:5] == "docs:":
                    source_path = filepath[5:]
                fitz_pdf = fitz.open(source_path)
                page = fitz_pdf[pdf_page]
                pm = page.get_pixmap(annots=False)  # PDF highlights/notes not painted
                abs_path_ = os.path.join(self.app.confighome, "tmp_preview_pdf_page.png")
                pm.save(abs_path_)
            image = QtGui.QImageReader(abs_path_).read()
            if image.isNull():
                raise ValueError("null image")
            image = image.copy(int(px or 0), int(py or 0), int(w or image.width()), int(h or image.height()))
            scaler = min(1.0, 200 / image.width() if image.width() > 200 else 1.0,
                         200 / image.height() if image.height() > 200 else 1.0)
            pixmap = QtGui.QPixmap().fromImage(image)
            pixmap = pixmap.scaled(int(image.width() * scaler), int(image.height() * scaler))
            item = QtWidgets.QGraphicsPixmapItem(pixmap)
            item.setPos(x, y)
            item.setZValue(1)
            self.preview_scene.addItem(item)
            return item.sceneBoundingRect()
        except Exception:
            rect = QtWidgets.QGraphicsRectItem(0, 0, max(30, (w or 90) / 3), max(20, (h or 60) / 3))
            rect.setBrush(QtGui.QBrush(QtGui.QColor("#E8E8E8")))
            rect.setPen(QtGui.QPen(QtGui.QColor("#909090"), 0.5))
            rect.setPos(x, y)
            rect.setZValue(1)
            self.preview_scene.addItem(rect)
            return rect.sceneBoundingRect()

    def _preview_av(self, x, y, color):
        """ AVGraphicsItem look: colored chip with a play marker. """
        t = self._preview_text("\u25B6 A/V", 9, False, "#000000")
        br = t.boundingRect().adjusted(-4, -2, 4, 2)
        rect = QtWidgets.QGraphicsRectItem(br)
        try:
            rect.setBrush(QtGui.QBrush(QtGui.QColor(color if (color or "").startswith("#") else "#FFFFFF")))
        except Exception:
            rect.setBrush(QtGui.QBrush(QtGui.QColor("#FFFFFF")))
        rect.setPen(QtGui.QPen(QtGui.QColor("#909090"), 0.5))
        rect.setPos(x, y)
        t.setParentItem(rect)
        rect.setZValue(1)
        self.preview_scene.addItem(rect)
        return rect.sceneBoundingRect()

    @staticmethod
    def _trim_to_rect(p_from, rect_to):
        """ Move the endpoint from a node center to that node's border, like the
        real perimeter-intersection line drawing. """
        center = rect_to.center()
        dx = center.x() - p_from.x()
        dy = center.y() - p_from.y()
        if dx == 0 and dy == 0:
            return center
        # parametric intersection of segment (p_from -> center) with rect borders
        candidates = []
        if dx != 0:
            for edge_x in (rect_to.left(), rect_to.right()):
                t = (edge_x - p_from.x()) / dx
                if 0 < t <= 1:
                    y = p_from.y() + t * dy
                    if rect_to.top() - 0.5 <= y <= rect_to.bottom() + 0.5:
                        candidates.append(t)
        if dy != 0:
            for edge_y in (rect_to.top(), rect_to.bottom()):
                t = (edge_y - p_from.y()) / dy
                if 0 < t <= 1:
                    x = p_from.x() + t * dx
                    if rect_to.left() - 0.5 <= x <= rect_to.right() + 0.5:
                        candidates.append(t)
        if not candidates:
            return center
        t = min(candidates)
        return QtCore.QPointF(p_from.x() + t * dx, p_from.y() + t * dy)

    def _preview_line(self, rect1, rect2, color_name, line_width=2,
                      dotted=False, arrow_mode="none", label=""):
        if rect1 is None or rect2 is None:
            return
        c1, c2 = rect1.center(), rect2.center()
        p1 = self._trim_to_rect(c2, rect1)
        p2 = self._trim_to_rect(c1, rect2)
        color_obj = safe_color(color_name or "gray")
        pen = QtGui.QPen(color_obj, max(1.0, float(line_width or 2)))
        if dotted:
            pen.setStyle(QtCore.Qt.PenStyle.DotLine)
        line = QtWidgets.QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
        line.setPen(pen)
        line.setZValue(0)
        self.preview_scene.addItem(line)
        # arrowheads, same triangle geometry as the real lines (size 12)
        theta = math.atan2(p1.y() - p2.y(), p1.x() - p2.x())
        arrow_size = 12

        def _arrow(tip, angle):
            tri = QtGui.QPolygonF([
                tip,
                QtCore.QPointF(tip.x() + arrow_size * math.cos(angle + math.pi / 6),
                               tip.y() + arrow_size * math.sin(angle + math.pi / 6)),
                QtCore.QPointF(tip.x() + arrow_size * math.cos(angle - math.pi / 6),
                               tip.y() + arrow_size * math.sin(angle - math.pi / 6))])
            head = QtWidgets.QGraphicsPolygonItem(tri)
            head.setBrush(QtGui.QBrush(color_obj))
            head.setPen(QtGui.QPen(color_obj, 1))
            head.setZValue(0)
            self.preview_scene.addItem(head)

        if arrow_mode in ("forward", "both"):
            _arrow(p2, theta)
        if arrow_mode in ("backward", "both"):
            _arrow(p1, theta + math.pi)
        if arrow_mode == "circle":
            r = 4
            dot = QtWidgets.QGraphicsEllipseItem(p2.x() - r, p2.y() - r, 2 * r, 2 * r)
            dot.setBrush(QtGui.QBrush(color_obj))
            dot.setPen(QtGui.QPen(color_obj, 1))
            self.preview_scene.addItem(dot)
        # relation label: italic blue text on a borderless white chip, like the graph
        if label:
            # Traducido al mostrar, igual que en el lienzo. Translated at display time, as on the canvas.
            lt = QtWidgets.QGraphicsTextItem(_(str(label)))
            f = QtGui.QFont()
            f.setPointSize(9)
            f.setItalic(True)
            lt.setFont(f)
            lt.setDefaultTextColor(QtGui.QColor("#0000CD"))
            br = lt.boundingRect()
            mid = QtCore.QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            lt.setPos(mid.x() - br.width() / 2, mid.y() - br.height() / 2)
            lt.setZValue(3)
            chip = QtWidgets.QGraphicsRectItem(br.adjusted(-4, -1, 4, 1), lt)
            chip.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)
            chip.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 235)))
            chip.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
            self.preview_scene.addItem(lt)

    def _render_preview(self, grid):
        self.preview_scene.clear()
        self.preview_scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#FFFFFF")))
        cur = self.app.conn.cursor()
        code_pos, cat_pos, case_pos, file_pos = {}, {}, {}, {}
        free_pos, pix_pos, av_pos, memo_pos = {}, {}, {}, {}
        try:
            # codes and categories
            cur.execute("select x, y, catid, cid, font_size, bold, isvisible, ifnull(displaytext,'') "
                        "from gr_cdct_text_item where grid=?", [grid])
            for x, y, catid, cid, fsize, bold, isvisible, displaytext in cur.fetchall():
                if not isvisible or x is None or y is None:
                    continue
                if cid is not None:
                    cur.execute("select name, color from code_name where cid=?", [cid])
                    res = cur.fetchone()
                    if res is None:
                        continue
                    rect = self._preview_code_or_cat(x, y, displaytext or res[0], res[1],
                                                     fsize, bold, is_category=False)
                    code_pos[cid] = rect
                else:
                    cur.execute("select name from code_cat where catid=?", [catid])
                    res = cur.fetchone()
                    if res is None:
                        continue
                    rect = self._preview_code_or_cat(x, y, displaytext or res[0], "#FFFFFF",
                                                     fsize, bold, is_category=True)
                    cat_pos[catid] = rect
            # cases
            cur.execute("select x, y, caseid, font_size, bold, ifnull(color,'black'), "
                        "ifnull(displaytext,'') from gr_case_text_item where grid=?", [grid])
            for x, y, caseid, fsize, bold, color, displaytext in cur.fetchall():
                if x is None or y is None:
                    continue
                name = displaytext
                if not name:
                    cur.execute("select name from cases where caseid=?", [caseid])
                    res = cur.fetchone()
                    name = res[0] if res else "case"
                case_pos[caseid] = self._preview_case(x, y, name, fsize, bold, color)
            # files
            cur.execute("select x, y, fid, font_size, bold, ifnull(color,'black'), "
                        "ifnull(displaytext,'') from gr_file_text_item where grid=?", [grid])
            for x, y, fid, fsize, bold, color, displaytext in cur.fetchall():
                if x is None or y is None:
                    continue
                name = displaytext
                if not name:
                    cur.execute("select name from source where id=?", [fid])
                    res = cur.fetchone()
                    name = res[0] if res else "file"
                file_pos[fid] = self._preview_file(x, y, name, fsize, bold, color)
            # free text
            cur.execute("select freetextid, x, y, ifnull(free_text,''), font_size, bold, "
                        "ifnull(color,'black') from gr_free_text_item where grid=?", [grid])
            for freetextid, x, y, free_text, fsize, bold, color in cur.fetchall():
                if x is None or y is None:
                    continue
                free_pos[freetextid] = self._preview_free_text(x, y, free_text, fsize, bold, color)
            # images and A/V
            cur.execute("select imid, x, y, px, py, w, h, filepath, pdf_page "
                        "from gr_pix_item where grid=?", [grid])
            for imid, x, y, px, py, w, h, filepath, pdf_page in cur.fetchall():
                if x is None or y is None:
                    continue
                pix_pos[imid] = self._preview_pixmap(x, y, px, py, w, h, filepath, pdf_page)
            cur.execute("select avid, x, y, ifnull(color,'white') from gr_av_item where grid=?", [grid])
            for avid, x, y, color in cur.fetchall():
                if x is None or y is None:
                    continue
                av_pos[avid] = self._preview_av(x, y, color)
            # memo nodes (v17)
            try:
                cur.execute("select gmemoid, memo_source_type, memo_source_id, x, y, "
                            "ifnull(font_size,9) from gr_memo_item where grid=?", [grid])
                for gmemoid, src_type, src_id, x, y, fsize in cur.fetchall():
                    if x is None or y is None:
                        continue
                    memo_pos[gmemoid] = self._preview_memo(x, y, src_type, src_id, fsize)
            except sqlite3.OperationalError:
                pass  # pre-v17 project
            # hierarchy lines (label + arrow_mode are v17 columns, tolerate their absence)
            try:
                cur.execute("select fromcatid, fromcid, tocatid, tocid, ifnull(color,'gray'), "
                            "ifnull(linewidth,2), ifnull(linetype,'solid'), isvisible, "
                            "ifnull(label,''), ifnull(arrow_mode,'none') "
                            "from gr_cdct_line_item where grid=?", [grid])
                cdct_lines = cur.fetchall()
            except sqlite3.OperationalError:
                cur.execute("select fromcatid, fromcid, tocatid, tocid, ifnull(color,'gray'), "
                            "ifnull(linewidth,2), ifnull(linetype,'solid'), isvisible, "
                            "'', 'none' from gr_cdct_line_item where grid=?", [grid])
                cdct_lines = cur.fetchall()
            for fromcatid, fromcid, tocatid, tocid, color, lw, linetype, isvisible, label, arrow in cdct_lines:
                if not isvisible:
                    continue
                r1 = code_pos.get(fromcid) if fromcid is not None else cat_pos.get(fromcatid)
                r2 = code_pos.get(tocid) if tocid is not None else cat_pos.get(tocatid)
                self._preview_line(r1, r2, color, lw, linetype == "dotted", arrow, label)

            def free_endpoint(freetextid, catid, cid, caseid, fid, imid, avid):
                if freetextid is not None and freetextid >= _MEMO_LINE_ID_OFFSET:
                    return memo_pos.get(freetextid - _MEMO_LINE_ID_OFFSET)
                for value, positions in ((freetextid, free_pos), (cid, code_pos),
                                         (catid, cat_pos), (caseid, case_pos),
                                         (fid, file_pos), (imid, pix_pos), (avid, av_pos)):
                    if value is not None and value in positions:
                        return positions[value]
                return None

            # relation / free lines
            try:
                cur.execute("select fromfreetextid, fromcatid, fromcid, fromcaseid, fromfileid, "
                            "fromimid, fromavid, tofreetextid, tocatid, tocid, tocaseid, tofileid, "
                            "toimid, toavid, ifnull(color,'gray'), ifnull(linewidth,2), "
                            "ifnull(linetype,'solid'), ifnull(label,''), ifnull(arrow_mode,'forward') "
                            "from gr_free_line_item where grid=?", [grid])
                free_lines = cur.fetchall()
            except sqlite3.OperationalError:
                cur.execute("select fromfreetextid, fromcatid, fromcid, fromcaseid, fromfileid, "
                            "fromimid, fromavid, tofreetextid, tocatid, tocid, tocaseid, tofileid, "
                            "toimid, toavid, ifnull(color,'gray'), ifnull(linewidth,2), "
                            "ifnull(linetype,'solid'), '', 'forward' "
                            "from gr_free_line_item where grid=?", [grid])
                free_lines = cur.fetchall()
            for r in free_lines:
                r1 = free_endpoint(r[0], r[1], r[2], r[3], r[4], r[5], r[6])
                r2 = free_endpoint(r[7], r[8], r[9], r[10], r[11], r[12], r[13])
                self._preview_line(r1, r2, r[14], r[15], r[16] == "dotted", r[18], r[17])
        except Exception as err:
            logger.warning("Graph preview failed for grid %s: %s", grid, err)
        rect = self.preview_scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        if rect.isValid():
            self.preview_scene.setSceneRect(rect)
            self.ui.graphicsView_preview.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.preview_scene.sceneRect()
        if rect.isValid():
            self.ui.graphicsView_preview.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        # first fitInView only works once the view has real geometry
        super().showEvent(event)
        rect = self.preview_scene.sceneRect()
        if rect.isValid():
            QtCore.QTimer.singleShot(
                0, lambda: self.ui.graphicsView_preview.fitInView(
                    rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio))


class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    scene_width = 990
    scene_height = 650
    parent = None

    def __init__(self, parent=None):
        super(GraphicsScene, self).__init__(parent)
        self.parent = parent
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def set_width(self, width):
        """ Resize scene width. """

        self.scene_width = width
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def set_height(self, height):
        """ Resize scene height. """

        self.scene_height = height
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def get_width(self):
        """ Return scene width. """

        return self.scene_width

    def get_height(self):
        """ Return scene height. """

        return self.scene_height

    def mouseMoveEvent(self, mouse_event):
        super(GraphicsScene, self).mouseMoveEvent(mouse_event)
        # Update positions for ALL moved items
        for item in self.items():
            if item.isSelected() and hasattr(item, 'code_or_cat'):
                if item.code_or_cat is not None:
                    item.code_or_cat['x'] = item.pos().x()
                    item.code_or_cat['y'] = item.pos().y()
            if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                item.redraw()
        self.update()

    # snapshot pre-drag positions of selected nodes AND the node under the
    # cursor. Capturing the under-cursor item handles the click-on-unselected-then-drag
    # case, where selectedItems() still reflects the previous selection at press time.
    def mousePressEvent(self, mouse_event):
        self._drag_start_positions = {}
        valid_classes = (TextGraphicsItem, FreeTextGraphicsItem, CaseTextGraphicsItem,
                         FileTextGraphicsItem, PixmapGraphicsItem, AVGraphicsItem,
                         MemoGraphicsItem)
        for item in self.selectedItems():
            if isinstance(item, valid_classes):
                self._drag_start_positions[item] = (item.pos().x(), item.pos().y())
        try:
            scene_pos = mouse_event.scenePos()
            for it in self.items(scene_pos):
                if isinstance(it, valid_classes) and it not in self._drag_start_positions:
                    self._drag_start_positions[it] = (it.pos().x(), it.pos().y())
                    break  # only the topmost relevant item
        except Exception:
            pass
        right_sel_snapshot = []
        if mouse_event.button() == QtCore.Qt.MouseButton.RightButton:
            right_sel_snapshot = [i for i in self.selectedItems() if isinstance(i, valid_classes)]
        super(GraphicsScene, self).mousePressEvent(mouse_event)
        if len(right_sel_snapshot) > 1:
            for it in right_sel_snapshot:
                try:
                    it.setSelected(True)
                except RuntimeError:
                    pass

    # detect real movement (0.5px jitter tolerance) and emit a deferred undo
    # snapshot. Also expand sceneRect on drop (clamped) to avoid feedback-loop growth.
    def mouseReleaseEvent(self, mouse_event):
        moved = False
        if hasattr(self, '_drag_start_positions') and self._drag_start_positions:
            for item, (sx, sy) in self._drag_start_positions.items():
                try:
                    if item.scene() is self:
                        if abs(item.pos().x() - sx) > 0.5 or abs(item.pos().y() - sy) > 0.5:
                            moved = True
                            break
                except RuntimeError:
                    continue
        if moved and self.parent is not None and hasattr(self.parent, '_save_undo_state'):
            self._save_drag_undo(self._drag_start_positions)
        if hasattr(self, '_drag_start_positions'):
            self._drag_start_positions = {}
        super(GraphicsScene, self).mouseReleaseEvent(mouse_event)
        # Expand sceneRect after drop, clamped
        items_rect = self.itemsBoundingRect()
        if not items_rect.isEmpty():
            current = self.sceneRect()
            items_rect.adjust(-100, -100, 100, 100)
            if not current.contains(items_rect):
                MAX_SCENE = 50000
                candidate = current.united(items_rect)
                if candidate.width() > MAX_SCENE:
                    candidate.setWidth(MAX_SCENE)
                if candidate.height() > MAX_SCENE:
                    candidate.setHeight(MAX_SCENE)
                self.setSceneRect(candidate)
        # Final redraw of all lines
        for item in self.items():
            if isinstance(item, (LinkGraphicsItem, FreeLineGraphicsItem)):
                item.redraw()
        self.update()

    # build a complete pre-drag snapshot using start_positions for tracked
    # nodes and current pos for the rest. Pushes directly onto parent._undo_stack.
    # Mirrors _save_undo_state structurally; kept separate because the positional data
    # must come from the pre-drag dict, not item.pos() (already post-drag here).
    def _save_drag_undo(self, start_positions):
        if self.parent is None:
            return
        snapshot = {'nodes': [], 'lines': []}
        for item in self.items():
            try:
                cls_name = type(item).__name__
                if cls_name not in ("TextGraphicsItem", "FreeTextGraphicsItem",
                                    "CaseTextGraphicsItem", "FileTextGraphicsItem",
                                    "PixmapGraphicsItem", "AVGraphicsItem",
                                    "MemoGraphicsItem"):
                    continue
                if item.scene() is not self:
                    continue
                # use pre-drag pos if tracked, otherwise current
                px, py = start_positions.get(item, (item.pos().x(), item.pos().y()))
                node_data = {
                    'class': cls_name, 'item_ref': item,
                    'pos': (px, py), 'visible': item.isVisible(), 'in_scene': True,
                }
                if hasattr(item, 'code_or_cat') and item.code_or_cat is not None:
                    node_data['code_or_cat'] = deepcopy(item.code_or_cat)
                for attr in ('text', 'color', 'font_size', 'bold', 'is_ellipse',
                             'is_collapsed', 'show_attributes'):
                    if hasattr(item, attr):
                        try:
                            node_data[attr] = getattr(item, attr)
                        except Exception:
                            pass
                if hasattr(item, 'textWidth'):
                    try:
                        node_data['text_width'] = item.textWidth()
                    except Exception:
                        pass
                if cls_name in ("PixmapGraphicsItem", "AVGraphicsItem"):
                    try:
                        if hasattr(item, 'pixmap') and item.pixmap() is not None:
                            pm = item.pixmap()
                            node_data['pixmap_size'] = (pm.width(), pm.height())
                    except Exception:
                        pass
                snapshot['nodes'].append(node_data)
            except RuntimeError:
                continue
        for line in self.items():
            cls_name = type(line).__name__
            if cls_name in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if hasattr(line, 'from_widget') and hasattr(line, 'to_widget'):
                    line_data = {
                        'class': cls_name, 'item_ref': line,
                        'from_widget': line.from_widget, 'to_widget': line.to_widget,
                        'visible': line.isVisible(), 'in_scene': line.scene() == self,
                    }
                    for attr in ('color', 'line_width', 'line_type', 'arrow_mode',
                                 'label', '_is_cooc_line'):
                        if hasattr(line, attr):
                            try:
                                line_data[attr] = getattr(line, attr)
                            except Exception:
                                pass
                    snapshot['lines'].append(line_data)
        self.parent._undo_stack.append(snapshot)
        if len(self.parent._undo_stack) > self.parent._undo_max_depth:
            self.parent._undo_stack.pop(0)

    def adjust_for_negative_positions(self):
        """ Move all items if negative positions. """

        min_adjust_x = 0
        min_adjust_y = 0
        for i in self.items():
            if i.pos().x() < min_adjust_x:
                min_adjust_x = i.pos().x()
            if i.pos().y() < min_adjust_x:
                min_adjust_y = i.pos().y()
        if min_adjust_x < 0 or min_adjust_y < 0:
            for i in self.items():
                if not (isinstance(i, LinkGraphicsItem) or isinstance(i, FreeLineGraphicsItem)):
                    i.setPos(i.pos().x() - min_adjust_x, i.pos().y() - min_adjust_y)

    def suggested_scene_size(self):
        """ Calculate the actual size of the scene, allowing margins for free panning. """

        rect = self.itemsBoundingRect()
        rect.adjust(-600, -600, 600, 600)  # Adds free space in all directions
        self.setSceneRect(rect)
        self.scene_width = rect.width()
        self.scene_height = rect.height()
        return self.scene_width, self.scene_height

    # set ephemeral connection preview source + mouse position
    def set_connection_preview(self, source_item, mouse_scene_pos):
        self._preview_source = source_item
        self._preview_pos = mouse_scene_pos
        self.update()

    # clear connection preview
    def clear_connection_preview(self):
        self._preview_source = None
        self._preview_pos = None
        self.update()

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        source = getattr(self, '_preview_source', None)
        pos = getattr(self, '_preview_pos', None)
        if source is None or pos is None:
            return
        p1 = source.sceneBoundingRect().center()
        p2 = pos
        pen = QtGui.QPen(QtGui.QColor("#555555"), 2, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(p1, p2)


class MinimapGraphicsView(QtWidgets.QGraphicsView):
    """ floating minimap overview. Viewport indicator painted in
    drawForeground so it never pollutes the shared scene. Click/drag navigates
    the main view. """

    MINIMAP_W = 220
    MINIMAP_H = 160
    MARGIN = 10

    def __init__(self, scene, main_view, parent_dialog):
        super().__init__(scene, parent_dialog)
        self.main_view = main_view
        self.parent_dialog = parent_dialog
        self._is_dragging = False
        self._visible_scene_rect = QtCore.QRectF()
        self.setFixedSize(self.MINIMAP_W, self.MINIMAP_H)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        self.setOptimizationFlag(QtWidgets.QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setStyleSheet(
            "MinimapGraphicsView {"
            "  background-color: rgba(245, 245, 245, 220);"
            "  border: 2px solid rgba(100, 100, 100, 180);"
            "  border-radius: 6px;"
            "}"
        )
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.reposition()
        self.update_viewport_rect()

    def reposition(self):
        gv_rect = self.main_view.geometry()
        x = gv_rect.right() - self.MINIMAP_W - self.MARGIN
        y = gv_rect.bottom() - self.MINIMAP_H - self.MARGIN
        self.move(x, y)

    def update_viewport_rect(self):
        self._visible_scene_rect = self.main_view.mapToScene(
            self.main_view.viewport().rect()).boundingRect()
        scene_rect = self.scene().itemsBoundingRect()
        if not scene_rect.isEmpty():
            scene_rect.adjust(-50, -50, 50, 50)
            self.fitInView(scene_rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.viewport().update()

    def drawForeground(self, painter, rect):
        if self._visible_scene_rect.isEmpty():
            return
        painter.save()
        painter.setBrush(QtGui.QBrush(QtGui.QColor(33, 150, 243, 40)))
        painter.setPen(QtGui.QPen(QtGui.QColor(33, 150, 243, 200), 2))
        painter.drawRect(self._visible_scene_rect)
        painter.restore()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._is_dragging = True
            scene_pos = self.mapToScene(event.position().toPoint())
            self.main_view.centerOn(scene_pos)
            self.update_viewport_rect()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.main_view.centerOn(scene_pos)
            self.update_viewport_rect()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ConnectionHandleItem(QtWidgets.QGraphicsEllipseItem):
    """ small blue handle shown above a selected node, used as the start
    point for drag-to-connect. Right-clicks pass through to parent for context menu. """

    SIZE = 14

    def __init__(self, parent_item):
        super().__init__(parent_item)
        self.parent_item = parent_item
        r = self.SIZE / 2
        self.setRect(-r, -r, self.SIZE, self.SIZE)
        self.setBrush(QtGui.QBrush(QtGui.QColor("#2196F3")))
        self.setPen(QtGui.QPen(QtGui.QColor("#0D47A1"), 2))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton)
        self._reposition()

    def _reposition(self):
        br = self.parent_item.boundingRect()
        cx = br.center().x()
        cy = br.top() - 10
        self.setPos(cx, cy)


    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
        else:
            event.ignore()

    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QBrush(QtGui.QColor("#42A5F5")))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtGui.QColor("#2196F3")))
        super().hoverLeaveEvent(event)


class ResizeHandleItem(QtWidgets.QGraphicsRectItem):
    """ corner handle that resizes parent's textWidth or pixmap on drag. """

    SIZE = 10

    def __init__(self, parent_item, corner="bottom_right"):
        super().__init__(parent_item)
        self.parent_item = parent_item
        self.corner = corner
        self.setRect(0, 0, self.SIZE, self.SIZE)
        self.setBrush(QtGui.QBrush(QtGui.QColor("#FF9800")))
        self.setPen(QtGui.QPen(QtGui.QColor("#E65100"), 1))
        self.setZValue(11)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
        self._drag_start_pos = None
        self._drag_start_width = None
        self._reposition()

    def _reposition(self):
        br = self.parent_item.boundingRect()
        if self.corner == "bottom_right":
            self.setPos(br.right() - self.SIZE, br.bottom() - self.SIZE)
        elif self.corner == "bottom_left":
            self.setPos(br.left(), br.bottom() - self.SIZE)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.scenePos()
            if hasattr(self.parent_item, 'textWidth'):
                tw = self.parent_item.textWidth()
                self._drag_start_width = tw if tw > 0 else self.parent_item.boundingRect().width()
            elif hasattr(self.parent_item, 'pixmap'):
                self._drag_start_width = self.parent_item.boundingRect().width()
            # capture the pre-resize state; pushed on release only if changed
            self._pending_undo_snapshot = None
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None \
                    and hasattr(scene.parent, '_build_undo_snapshot'):
                self._pending_undo_snapshot = scene.parent._build_undo_snapshot()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is None:
            return
        delta_x = event.scenePos().x() - self._drag_start_pos.x()
        new_width = max(60, min(600, self._drag_start_width + delta_x))
        if hasattr(self.parent_item, 'setTextWidth'):
            self.parent_item.setTextWidth(new_width)
            self._reposition()
        elif hasattr(self.parent_item, 'pixmap') and hasattr(self.parent_item, '_original_pixmap'):
            orig_pixmap = self.parent_item._original_pixmap
            if orig_pixmap is None or orig_pixmap.isNull() or orig_pixmap.width() <= 0:
                event.accept()
                return
            scale_factor = new_width / orig_pixmap.width()
            scale_factor = max(0.1, min(scale_factor, 3.0))
            scaled = orig_pixmap.scaled(
                int(orig_pixmap.width() * scale_factor),
                int(orig_pixmap.height() * scale_factor),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
            self.parent_item.setPixmap(scaled)
            self._reposition()
        event.accept()

    def mouseReleaseEvent(self, event):
        # push the pre-resize snapshot only when the width really changed,
        # so touching the handle without dragging never consumes an undo level.
        pending = getattr(self, '_pending_undo_snapshot', None)
        if pending is not None and self._drag_start_width is not None:
            try:
                if hasattr(self.parent_item, 'textWidth'):
                    tw = self.parent_item.textWidth()
                    current_w = tw if tw > 0 else self.parent_item.boundingRect().width()
                else:
                    current_w = self.parent_item.boundingRect().width()
                if abs(current_w - self._drag_start_width) > 1:
                    scene = self.scene()
                    if scene is not None and getattr(scene, 'parent', None) is not None \
                            and hasattr(scene.parent, '_push_undo_snapshot'):
                        scene.parent._push_undo_snapshot(pending)
            except RuntimeError:
                pass
        self._pending_undo_snapshot = None
        self._drag_start_pos = None
        self._drag_start_width = None
        self._reposition()
        event.accept()

    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QBrush(QtGui.QColor("#FFB74D")))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtGui.QColor("#FF9800")))
        super().hoverLeaveEvent(event)


class MemoGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ live memo node, always reflects the current memo from the database.
    Double-click or context menu opens the memo editor; supports any memo source type
    (code, category, code_text, code_image, code_av, case, file).
    """

    MAX_WIDTH = 350

    def __init__(self, app, memo_source_type, memo_source_id, x=10, y=10):
        super().__init__(None)
        self.app = app
        self.settings = app.settings
        self.memo_source_type = memo_source_type
        self.memo_source_id = memo_source_id
        self.code_or_cat = {'cid': None, 'catid': None}  # for save_graph compatibility
        self.text = ""
        self.font_size = 9
        self.color = "blue"
        self.bold = False
        self.remove = False
        self.freetextid = None  # set after save -> gr_memo_item.gmemoid for line matching
        self.gmemoid = None
        self.setPos(x, y)
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size))
        self.setDefaultTextColor(safe_color("blue"))
        self._refresh_memo()

    # Map source type -> (select SQL, update SQL, params)
    def _get_sql_and_params(self):
        type_map = {
            'code':       ("select ifnull(memo,'') from code_name where cid=?",
                           "update code_name set memo=? where cid=?"),
            'category':   ("select ifnull(memo,'') from code_cat where catid=?",
                           "update code_cat set memo=? where catid=?"),
            'code_text':  ("select ifnull(memo,'') from code_text where ctid=?",
                           "update code_text set memo=? where ctid=?"),
            'code_image': ("select ifnull(memo,'') from code_image where imid=?",
                           "update code_image set memo=? where imid=?"),
            'code_av':    ("select ifnull(memo,'') from code_av where avid=?",
                           "update code_av set memo=? where avid=?"),
            'case':       ("select ifnull(memo,'') from cases where caseid=?",
                           "update cases set memo=? where caseid=?"),
            'file':       ("select ifnull(memo,'') from source where id=?",
                           "update source set memo=? where id=?"),
        }
        entry = type_map.get(self.memo_source_type)
        if entry is None:
            return (None, None, None)
        return (entry[0], entry[1], [self.memo_source_id])

    def _refresh_memo(self):
        select_sql, _update_sql, params = self._get_sql_and_params()
        if select_sql is None:
            return
        cur = self.app.conn.cursor()
        cur.execute(select_sql, params)
        res = cur.fetchone()
        self.text = res[0] if res else ""
        if self.text:
            display = self.text[:450] + "..." if len(self.text) > 450 else self.text
        else:
            display = _("(empty memo)")
        self.setPlainText(display)
        option = QtGui.QTextOption()
        option.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.document().setDefaultTextOption(option)
        self.setToolTip(self.text[:1000] if len(self.text) > 1000 else self.text)
        if self.boundingRect().width() > self.MAX_WIDTH:
            self.setTextWidth(self.MAX_WIDTH)

    def _edit_memo(self):
        select_sql, update_sql, params = self._get_sql_and_params()
        if select_sql is None:
            return
        cur = self.app.conn.cursor()
        cur.execute(select_sql, params)
        res = cur.fetchone()
        current_memo = res[0] if res else ""
        title = _("Memo for ") + f"{self.memo_source_type}: {self.memo_source_id}"
        ui = DialogMemo(self.app, title, current_memo)
        ui.exec()
        new_memo = ui.memo
        if new_memo != current_memo:
            cur.execute(update_sql, [new_memo] + params)
            self.app.conn.commit()
            # Sync the edited memo with TextGraphicsItem caches in the scene
            scene = self.scene()
            if scene:
                for item in scene.items():
                    if type(item).__name__ == "TextGraphicsItem":
                        if self.memo_source_type == 'code' and item.code_or_cat.get('cid') == self.memo_source_id:
                            item.code_or_cat['memo'] = new_memo
                            item.get_memo()
                        elif self.memo_source_type == 'category' \
                                and item.code_or_cat.get('catid') == self.memo_source_id \
                                and item.code_or_cat.get('cid') is None:
                            item.code_or_cat['memo'] = new_memo
                            item.get_memo()
            # Notify other views via the event bus AFTER commit
            if hasattr(self.app, 'project_events'):
                table_map = {
                    'code': 'code_name', 'category': 'code_cat',
                    'code_text': 'code_text', 'code_image': 'code_image', 'code_av': 'code_av',
                    'case': 'cases', 'file': 'source',
                }
                changed = table_map.get(self.memo_source_type)
                if changed:
                    self.app.project_events.emit_table_changes([changed], source=self)
        self._refresh_memo()

    def mouseDoubleClickEvent(self, event):
        self._edit_memo()
        event.accept()

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        edit_action = menu.addAction(_("Edit memo"))
        refresh_action = menu.addAction(_("Refresh memo"))
        menu.addSeparator()
        remove_action = menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == edit_action:
            self._edit_memo()
        if action == refresh_action:
            self._refresh_memo()
        if action == remove_action:
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.remove = True
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#E3F2FD")))  # light blue background
        painter.setPen(QtGui.QPen(QtGui.QColor("#1565C0"), 1, QtCore.Qt.PenStyle.DashLine))
        painter.drawRoundedRect(self.boundingRect(), 6, 6)
        painter.restore()
        super().paint(painter, option, widget)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._sync_handles_with_selection)
        return super().itemChange(change, value)

    # delegates to the module-level helper (single source of truth)
    def _sync_handles_with_selection(self):
        sync_handles_with_selection(self)


class CaseTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item shows the case name and optionally attributes.
    A custom context menu
    """

    def __init__(self, app, case_name, case_id, x=0, y=0, font_size=9, color="black", bold=False, displaytext=""):
        """ Show name and optionally attributes.
        param: app  : the main App class
        param: case_name : String
        param: case_id : Integer
        param: x : Integer
        param: y : Integer
        param: color : String
        param: bold : boolean
        param: displaytext : Integer
        """

        super(CaseTextGraphicsItem, self).__init__(None)
        self.setToolTip(_("Case"))
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.case_id = case_id
        # needed for save_graph and line compatibility
        self.code_or_cat = {'cid': None, 'catid': None}
        self.case_name = case_name
        self.text = displaytext
        if displaytext == "":
            self.text = case_name
        self.setPlainText(self.text)
        # center text alignment
        option = QtGui.QTextOption()
        option.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.document().setDefaultTextOption(option)
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.show_attributes = False
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPos(x, y)
        cur = self.app.conn.cursor()
        cur.execute("select ifnull(memo,'') from cases where caseid=?", [case_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("Case") + ": " + res[0])
        self.setDefaultTextColor(safe_color(color))

    def __repr__(self):
        txt = f"CaseTextGraphicsItem case_id:{self.case_id} case_name:{self.case_name}"
        return txt

    # trigger handle sync when selection changes (deferred for multi-selection)
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._sync_handles_with_selection)
        return super().itemChange(change, value)

    # delegates to module-level helper (single source of truth)
    def _sync_handles_with_selection(self):
        sync_handles_with_selection(self)

    # delegates to module helper, parametrized for the Case SQL + orange lines
    def add_linked_categories(self):
        sql = ("select distinct cn.catid from code_name cn where cn.catid is not null and cn.cid in "
               "(select distinct ct.cid from code_text ct "
               "join case_text cas on cas.fid = ct.fid "
               "and ct.pos0 >= cas.pos0 and ct.pos1 <= cas.pos1 "
               "where cas.caseid=?)")
        add_linked_categories_to_node(self, sql, [self.case_id], "orange")

    # distinctive Case look, orange border + rounded rectangle
    def paint(self, painter, option, widget):
        painter.save()
        bg_color = QtGui.QColor("#101010") if self.color == "white" else QtGui.QColor("#fafafa")
        painter.setBrush(QtGui.QBrush(bg_color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.setPen(QtGui.QPen(QtGui.QColor("#F57C00"), 2))
        painter.drawRoundedRect(self.boundingRect(), 12, 12)
        painter.restore()
        super().paint(painter, option, widget)

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        show_att_action = None
        hide_att_action = None
        edit_action = menu.addAction(_("Edit text"))
        bold_action = menu.addAction(_("Bold toggle"))
        menu.addSeparator()
        # Submenu for font size
        font_size_menu = menu.addMenu("Font size")
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        # Submenu for text color
        color_menu = menu.addMenu(_("Text color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        orange_action = color_menu.addAction(_("Orange"))
        cyan_action = color_menu.addAction(_("Cyan"))
        magenta_action = color_menu.addAction(_("Magenta"))
        gray_action = color_menu.addAction(_("Gray"))
        color_menu.addSeparator()
        black_action = color_menu.addAction(_("Black"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        if self.show_attributes:
            hide_att_action = menu.addAction(_('Hide attributes'))
        else:
            show_att_action = menu.addAction(_('Show attributes'))
        # import and link case memo (only if case has a non-empty memo)
        import_memo_action = None
        cur_memo = self.app.conn.cursor()
        cur_memo.execute("select ifnull(memo,'') from cases where caseid=?", [self.case_id])
        res_memo = cur_memo.fetchone()
        case_memo_text = res_memo[0] if res_memo else ""
        if case_memo_text:
            import_memo_action = menu.addAction(_("Memo"))
        # linked categories action
        add_categories_action = menu.addAction(_("Add categories"))
        menu.addSeparator()
        remove_action = menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # unified undo snapshot pattern
        _no_snapshot_actions = {remove_action, import_memo_action, add_categories_action}
        if action not in _no_snapshot_actions:
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
        # import-and-link case memo (delegates to module-level helper)
        if import_memo_action and action == import_memo_action:
            link_memo_to_segment(self.app, self, 'case', self.case_id, case_memo_text)
            return
        # linked categories
        if action == add_categories_action:
            self.add_linked_categories()
            return
        # Font size
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Bold
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Colors
        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == magenta_action:
            self.color = "magenta"
        if action == cyan_action:
            self.color = "cyan"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == black_action:
            self.color = "black"
        if action == white_action:
            self.color = "white"
        self.setDefaultTextColor(safe_color(self.color))
        # Remove
        if action == remove_action:
            ui_confirm = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui_confirm.exec():
                return
            # snapshot before removing
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.remove = True
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        # Attributes
        if action == show_att_action:
            self.show_attributes = True
            self.setHtml(self.text + self.get_attributes())
        if action == hide_att_action:
            self.show_attributes = False
            self.setPlainText(self.text)
        # Edit
        if action == edit_action:
            ui = DialogMemo(self.app, _("Edit text"), self.text)
            configure_plain_text_editor(ui)  # plain editor, no memo toolbar
            ui.exec()
            self.text = ui.memo
            self.setPlainText(self.text)

    def get_attributes(self):
        """ Get attributes for the file.  Add to text document. """
        attribute_text = ""
        cur = self.app.conn.cursor()
        sql = "SELECT name, value FROM  attribute where attr_type='case' and id=? order by name"
        cur.execute(sql, [self.case_id])
        result = cur.fetchall()
        for r in result:
            attribute_text += '<br>' + r[0] + ": " + r[1]
        return attribute_text


class FileTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item shows the file name and optionally attributes.
    A custom context menu
    """

    def __init__(self, app, file_name, file_id=-1, x=0, y=0, font_size=9, color="black", bold=False, displaytext=""):
        """ Show name and optionally attributes, in text graphic.
        Args:
            app  : the main App class
            file_name : String
            file_id : Integer
            x : Integer
            y : Integer
            color : String
            bold: boolean
            displaytext : String
        """

        super(FileTextGraphicsItem, self).__init__(None)
        self.setToolTip(_("File"))
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.file_id = file_id
        # needed for save_graph and line compatibility
        self.code_or_cat = {'cid': None, 'catid': None}
        self.file_name = file_name
        self.text = displaytext
        if displaytext == "":
            self.text = file_name
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.show_attributes = False
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPos(x, y)
        cur = self.app.conn.cursor()
        cur.execute("select ifnull(memo,'') from source where id=?", [file_id])
        res = cur.fetchone()
        if res:
            self.setToolTip(_("File") + ": " + res[0])
        self.setPlainText(self.text)
        # center text alignment
        option = QtGui.QTextOption()
        option.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.document().setDefaultTextOption(option)
        self.setDefaultTextColor(safe_color(color))

    def __repr__(self):
        txt = f"FileTextGraphicsItem file_id:{self.file_id} file_name:{self.file_name}"
        return txt

    # document shape with folded corner, distinguishes Files from Cases
    def paint(self, painter, option, widget):
        painter.save()
        bg_color = QtGui.QColor("#101010") if self.color == "white" else QtGui.QColor("#fafafa")
        painter.setBrush(QtGui.QBrush(bg_color, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1976D2"), 2))
        rect = self.boundingRect()
        w, h, fold = rect.width(), rect.height(), 8
        polygon = QtGui.QPolygonF([
            QtCore.QPointF(0, 0), QtCore.QPointF(w - fold, 0),
            QtCore.QPointF(w, fold), QtCore.QPointF(w, h),
            QtCore.QPointF(0, h)])
        painter.drawPolygon(polygon)
        painter.drawLine(QtCore.QPointF(w - fold, 0), QtCore.QPointF(w - fold, fold))
        painter.drawLine(QtCore.QPointF(w - fold, fold), QtCore.QPointF(w, fold))
        painter.restore()
        super().paint(painter, option, widget)

    # trigger handle sync when selection changes
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._sync_handles_with_selection)
        return super().itemChange(change, value)

    # delegates to module-level helper
    def _sync_handles_with_selection(self):
        sync_handles_with_selection(self)

    # parametrized for File SQL (across text/image/AV) + blue lines
    def add_linked_categories(self):
        sql = ("select distinct cn.catid from code_name cn where cn.catid is not null and cn.cid in "
               "(select distinct cid from code_text where fid=? "
               "union select distinct cid from code_image where id=? "
               "union select distinct cid from code_av where id=?)")
        add_linked_categories_to_node(self, sql, [self.file_id, self.file_id, self.file_id], "blue")

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size: 9pt} ")
        show_att_action = None
        hide_att_action = None
        edit_action = menu.addAction(_("Edit text"))
        bold_action = menu.addAction(_("Bold toggle"))
        menu.addSeparator()
        # Submenu for font size
        font_size_menu = menu.addMenu("Font size")
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        # Submenu for text color
        color_menu = menu.addMenu(_("Text color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        orange_action = color_menu.addAction(_("Orange"))
        cyan_action = color_menu.addAction(_("Cyan"))
        magenta_action = color_menu.addAction(_("Magenta"))
        gray_action = color_menu.addAction(_("Gray"))
        color_menu.addSeparator()
        black_action = color_menu.addAction(_("Black"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        if self.show_attributes:
            hide_att_action = menu.addAction(_('Hide attributes'))
        else:
            show_att_action = menu.addAction(_('Show attributes'))
        # import and link file memo
        import_memo_action = None
        cur_memo = self.app.conn.cursor()
        cur_memo.execute("select ifnull(memo,'') from source where id=?", [self.file_id])
        res_memo = cur_memo.fetchone()
        file_memo_text = res_memo[0] if res_memo else ""
        if file_memo_text:
            import_memo_action = menu.addAction(_("Memo"))
        add_categories_action = menu.addAction(_("Add categories"))
        menu.addSeparator()
        remove_action = menu.addAction(_("Remove"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # unified undo snapshot
        _no_snapshot_actions = {remove_action, import_memo_action, add_categories_action}
        if action not in _no_snapshot_actions:
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
        if import_memo_action and action == import_memo_action:
            link_memo_to_segment(self.app, self, 'file', self.file_id, file_memo_text)
            return
        if action == add_categories_action:
            self.add_linked_categories()
            return
        # Font size
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Bold
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Colors
        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == black_action:
            self.color = "black"
        if action == white_action:
            self.color = "white"
        self.setDefaultTextColor(safe_color(self.color))
        # Remove
        if action == remove_action:
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            self.remove = True
            scene = self.scene()
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        # Attributes
        if action == show_att_action:
            self.setHtml(self.text + self.get_attributes())
            self.show_attributes = True
        if action == hide_att_action:
            self.setPlainText(self.text)
            self.show_attributes = False
        # Edit
        if action == edit_action:
            ui = DialogMemo(self.app, _("Edit text"), self.text)
            configure_plain_text_editor(ui)  # plain editor, no memo toolbar
            ui.exec()
            self.text = ui.memo
            self.setPlainText(self.text)

    def get_attributes(self):
        """ Get attributes for the file.  Add to text document. """

        attribute_text = ""
        cur = self.app.conn.cursor()
        sql = "SELECT name, value FROM  attribute where attr_type='file' and id=? order by name"
        cur.execute(sql, [self.file_id])
        result = cur.fetchall()
        for r in result:
            attribute_text += f"<br>{r[0]}: {r[1]}"
        return attribute_text


class FreeTextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ Free text to add to the scene. """

    MAX_WIDTH = 300
    MAX_HEIGHT = 300

    def __init__(self, app, freetextid=-1, x=10, y=10, text_="text", font_size=9, color="black", bold=False, ctid=-1,
                 memo_ctid=None, memo_imid=None, memo_avid=None, gfreeid=None):
        """ Free text object.
         Args:
            app  : the main App class
            freetextid : Integer
            x : Integer x position
            y : Integer y position
            text_ : String
            color : String
            bold : boolean
            ctid : Integer : code_text identifier for coded file and memo segments
            memo_ctid : Integer or None
            memo_imid : Integer or None
            memo_avid : Integer or None
            gfreeid : Integer or None
         """

        super(FreeTextGraphicsItem, self).__init__(None)
        self.app = app
        self.freetextid = freetextid  # For graph item storage
        self.setPos(x, y)
        self.text = text_
        self.updated_text = ""  # for
        self.font_size = font_size
        self.color = color
        self.bold = bold
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.ctid = ctid  # Used for a coded text display to show code in context
        self.memo_ctid = memo_ctid  # For graph item storage
        self.memo_imid = memo_imid  # For graph item storage
        self.memo_avid = memo_avid  # For graph item storage
        self.code_or_cat = {'cid': None, 'catid': None}  # Catch for LinkGraphicsItem in save_graph
        # Recuperar el cid si es un segmento guardado (necesario para el colapso de categorías). Retrieve the cid if it is a saved segment (required for category collapsing).
        if self.ctid is not None and self.ctid != -1:
            cur = self.app.conn.cursor()
            cur.execute("select cid from code_text where ctid=?", [self.ctid])
            res = cur.fetchone()
            if res:
                self.code_or_cat['cid'] = res[0]
        self.gfreeid = gfreeid
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, QtGui.QFont.Weight.Normal))
        if bold:
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, QtGui.QFont.Weight.Bold))
        self.setPlainText(self.text)
        self.setDefaultTextColor(safe_color(color))  # tolerant color lookup
        if self.boundingRect().width() > self.MAX_WIDTH:
            self.setTextWidth(self.MAX_WIDTH)
        self.check_coding()

    def __repr__(self):
        txt = f"FreeTextGraphicsItem freetextid:{self.freetextid} gfreeid:{self.gfreeid} Font:{self.font_size} " \
              f"Bold:{self.bold} ctid:{self.ctid} memo_ctid:{self.memo_ctid} memo_imid:{self.memo_imid} " \
              f"memo_avid:{self.memo_avid}\n"
        txt += f"Text:{self.text}"
        return txt

    # trigger handle sync when selection changes (deferred for multi-selection)
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._sync_handles_with_selection)
        return super().itemChange(change, value)

    # delegates to module-level helper (single source of truth)
    def _sync_handles_with_selection(self):
        sync_handles_with_selection(self)

    def check_coding(self):
        """ Check text coding segment is current.
        Flag if so, but do not automatically update. """

        # Free text item - not a coded text, nor a memo text, so no disparity
        self.updated_text = self.text
        # Get current coded text
        if self.ctid > 0:
            cur = self.app.conn.cursor()
            cur.execute("select seltext from code_text where ctid=?", [self.ctid])
            res = cur.fetchone()
            # check res BEFORE indexing it (legacy crashed on deleted codings)
            if res is None:
                self.updated_text = self.text
                return
            self.updated_text = res[0]
            return
        # Get current coded text memo text
        if self.memo_ctid is not None:
            cur = self.app.conn.cursor()
            cur.execute("select ifnull(memo,'') from code_text where ctid=?", [self.memo_ctid])
            res = cur.fetchone()
            if res is None:  # None-check before indexing
                self.updated_text = self.text
                return
            self.updated_text = res[0]
            return
        # Get current coded image memo text
        if self.memo_imid is not None:
            cur = self.app.conn.cursor()
            cur.execute("select ifnull(memo,'') from code_image where imid=?", [self.memo_imid])
            res = cur.fetchone()
            if res is None:  # None-check before indexing
                self.updated_text = self.text
                return
            self.updated_text = res[0]
            return
        # Get current coded av memo text
        if self.memo_avid is not None:
            cur = self.app.conn.cursor()
            cur.execute("select ifnull(memo,'') from code_av where avid=?", [self.memo_avid])
            res = cur.fetchone()
            if res is None:  # None-check before indexing
                self.updated_text = self.text
                return
            self.updated_text = res[0]

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        update_text_action = None
        if self.gfreeid is not None and self.text != self.updated_text:
            update_text_action = menu.addAction(_("Update text"))
        edit_action = menu.addAction(_("Edit text"))
        text_context_action = None
        if (self.ctid is not None and self.ctid != -1) or (self.memo_ctid is not None and self.memo_ctid != -1):
            text_context_action = menu.addAction(_("Segment in context"))
        image_context_action = None
        if self.memo_imid is not None and self.memo_imid != -1:
            image_context_action = menu.addAction(_("Segment in context"))
        av_context_action = None
        if self.memo_avid is not None and self.memo_avid != -1:
            av_context_action = menu.addAction(_("Segment in context"))
        # import and link the memo of this coded text segment (if non-empty)
        import_memo_action = None
        segment_memo_text = ""
        if self.ctid is not None and self.ctid > 0:
            cur_memo = self.app.conn.cursor()
            cur_memo.execute("select ifnull(memo,'') from code_text where ctid=?", [self.ctid])
            res_memo = cur_memo.fetchone()
            segment_memo_text = res_memo[0] if res_memo else ""
            if segment_memo_text:
                import_memo_action = menu.addAction(_("Add and link memo"))
        # toggle co-occurrence lines for the coded segments in the graph
        toggle_cooc_action = None
        if self.ctid is not None and self.ctid > 0:
            toggle_cooc_action = menu.addAction(_("Toggle co-occurrence lines"))
        menu.addSeparator()
        bold_action = menu.addAction(_("Bold toggle"))
        # Submenu for font size
        font_size_menu = menu.addMenu("Font size")
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18, 20]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        # Submenu for text color.
        color_menu = menu.addMenu(_("Text color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        cyan_action = color_menu.addAction(_("Cyan"))
        magenta_action = color_menu.addAction(_("Magenta"))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        color_menu.addSeparator()
        black_action = color_menu.addAction(_("Black"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # unified undo snapshot pattern. Actions below either snapshot
        # themselves after user confirmation or are read-only dialogs.
        _no_snapshot_actions = {remove_action, import_memo_action, toggle_cooc_action,
                                text_context_action, image_context_action, av_context_action}
        if action not in _no_snapshot_actions:
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
        # import-and-link memo (delegates to module-level helper)
        if import_memo_action and action == import_memo_action:
            link_memo_to_segment(self.app, self, 'code_text', self.ctid, segment_memo_text)
            return
        # co-occurrence toggle (delegates to module-level helper)
        if toggle_cooc_action and action == toggle_cooc_action:
            invoke_segment_cooc_toggle(self)
            return
        if action == update_text_action:
            ui = DialogMemo(self.app, _("Update text to"), self.updated_text)
            configure_plain_text_editor(ui)  # hides the whole memo toolbar
            ui.setFixedSize(QtCore.QSize(450, 220))
            ui.ui.textEdit.setReadOnly(True)
            accepted = ui.exec()
            if not accepted:
                return
            self.text = self.updated_text
            cur = self.app.conn.cursor()
            cur.execute("update gr_free_text_item set free_text=? where gfreeid=?",
                        [self.updated_text, self.gfreeid])
            self.app.conn.commit()
            self.setPlainText(self.text)
            return
        if action == image_context_action:
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_image.owner,"
                        "ifnull(code_image.memo,''), x1, y1,width,height, source.name, source.id, "
                        "source.mediapath, pdf_page "
                        "from code_image join code_name on code_name.cid=code_image.cid join source on "
                        "source.id=code_image.id where code_image.imid=?",
                        [self.memo_imid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find image coding in database")).exec()
                return
            data = {'cid': res[0], 'codename': res[1], 'color': res[2], 'coder': res[3], 'memo': res[4],
                    'x1': res[5], 'y1': res[6], 'width': res[7], 'height': res[8], 'file_or_casename': res[9],
                    'fid': res[10], 'file_or_case': 'File', 'mediapath': res[11], 'pdf_page': res[12]}
            DialogCodeInImage(self.app, data).exec()
        if action == av_context_action:
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_av.owner,ifnull(code_av.memo,''),"
                        "pos0, pos1, source.name, source.id, source.mediapath "
                        "from code_av join code_name on code_name.cid=code_av.cid join source on "
                        "source.id=code_av.id where code_av.avid=?",
                        [self.memo_avid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find A/V coding in database")).exec()
                return
            data = {'cid': res[0], 'codename': res[1], 'color': res[2], 'coder': res[3], 'memo': res[4],
                    'pos0': res[5], 'pos1': res[6], 'file_or_casename': res[7],
                    'fid': res[8], 'file_or_case': 'File', 'mediapath': res[9]}
            DialogCodeInAV(self.app, data).exec()
        if action == text_context_action:
            text_id = self.ctid
            if text_id == -1:
                text_id = self.memo_ctid
            cur = self.app.conn.cursor()
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_text.owner,"
                        "ifnull(code_text.memo,''), pos0, pos1, source.name, source.id "
                        "from code_text join code_name on code_name.cid=code_text.cid join source on "
                        "source.id=code_text.fid where code_text.ctid=?",
                        [text_id])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find text coding in database")).exec()
                return
            data = {'cid': res[0], 'codename': res[1], 'color': res[2], 'coder': res[3], 'memo': res[4],
                    'pos0': res[5], 'pos1': res[6], 'file_or_casename': res[7], 'fid': res[8], 'file_or_case': 'File'}
            DialogCodeInText(self.app, data).exec()
        # Remove
        if action == remove_action:
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            # snapshot AFTER confirmation, so Cancel never pollutes the undo stack
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.remove = True
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return
        # Bold
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Font size
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        # Colors
        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == black_action:
            self.color = "black"
        if action == white_action:
            self.color = "white"
        self.setDefaultTextColor(safe_color(self.color))  # tolerant color lookup
        # Edit
        if action == edit_action:
            ui = DialogMemo(self.app, _("Edit text"), self.text)
            configure_plain_text_editor(ui)  # plain editor, no memo toolbar
            ui.exec()
            self.text = ui.memo
            self.setPlainText(self.text)
            if self.boundingRect().width() > self.MAX_WIDTH:
                self.setTextWidth(self.MAX_WIDTH)

    def paint(self, painter, option, widget=None):
        painter.save()
        # Fondo claro para cualquier color de texto; oscuro solo si el texto es blanco.
        # Light background for any text color; dark only when the text is white.
        bg_color = QtGui.QColor("#101010") if self.color == "white" else QtGui.QColor("#fafafa")
        painter.setBrush(QtGui.QBrush(bg_color, style=QtCore.Qt.BrushStyle.SolidPattern))
        if self.ctid is not None and self.ctid > 0:
            # Segmento codificado: contorno gris punteado. Coded segment: dotted gray outline.
            painter.setPen(QtGui.QPen(QtGui.QColor("#808080"), 1, QtCore.Qt.PenStyle.DotLine))
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class FreeLineGraphicsItem(QtWidgets.QGraphicsPolygonItem):
    """ Polygon line with arrow head. """

    def __init__(self, from_widget, to_widget, color="gray", line_width=2, line_type="solid", label=""):
        """ User created connecting line, with arrow.
         Args:
            from_widget : FreeTextGraphicsItem, TextGraphicsItem, AVGraphicsItem, PixmapGraphicsItem,
                FileTextGraphicsItem, CaseTextGraphicsItem, MemoGraphicsItem
            to_widget : FreeTextGraphicsItem, TextGraphicsItem, AVGraphicsItem, PixmapGraphicsItem,
                FileTextGraphicsItem, CaseTextGraphicsItem, MemoGraphicsItem
            color : String
            line_width : Integer
            line_type : String
            label : String  relation label shown at the line midpoint (v17, persisted)
        """

        super(FreeLineGraphicsItem, self).__init__(None)

        self.from_widget = from_widget
        self.to_widget = to_widget
        self.line_width = line_width
        self.remove = False
        # Bloquear selección y hacer que ignore el clic izquierdo (pero permita el derecho para el menú)
        # Lock selection and make it ignore left clicks (but allow right clicks for the menu)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.RightButton)
        self.color = color
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine
        # arrow direction, persisted in gr_free_line_item.arrow_mode (v17).
        # Values: forward / backward / both / none / circle. Lines touching Case or
        # File nodes default to "none" (membership, not direction).
        self.arrow_mode = "forward"
        if type(from_widget).__name__ in ("CaseTextGraphicsItem", "FileTextGraphicsItem") or \
                type(to_widget).__name__ in ("CaseTextGraphicsItem", "FileTextGraphicsItem"):
            self.arrow_mode = "none"
        # relation label (v17). text_item + white backing rect, positioned
        # by the shared position_line_label helper to avoid node overlaps.
        self.label = str(label) if label else ""
        self.text_item = None
        self._label_bg = None
        if self.label:
            self._create_label_item()
        # Cached endpoints/angle so paint() draws arrowheads without recomputing geometry
        self._both_p1 = None
        self._both_p2 = None
        self._both_theta = 0.0
        color_obj = safe_color(color)  # tolerant color lookup
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))
        self.calculate_points_and_draw()

    def __repr__(self):
        txt = f"FreeLineGraphicsItem From:{self.from_widget} To:{self.to_widget} Line_type:{self.line_type}\n"
        txt += f"Color:{self.color} Width:{self.line_width} Arrow:{self.arrow_mode} Label:{self.label}"
        return txt

    # build (or rebuild) the midpoint label widget; shared implementation with
    # LinkGraphicsItem in build_line_label (top-level italic item, z=5)
    def _create_label_item(self, label=None):
        return build_line_label(self, label)

    def itemChange(self, change, value):
        sync_line_label_on_item_change(self, change, value)
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        # edit the relation label directly on the line
        edit_label_action = menu.addAction(_('Edit label'))
        # arrow direction submenu (persisted as arrow_mode, v17)
        arrow_menu = menu.addMenu(_('Arrow'))
        arrow_forward_action = arrow_menu.addAction(_('Forward'))
        arrow_backward_action = arrow_menu.addAction(_('Backward'))
        arrow_both_action = arrow_menu.addAction(_('Both directions'))
        arrow_none_action = arrow_menu.addAction(_('No arrow'))
        arrow_circle_action = arrow_menu.addAction(_('Circle end'))
        # Submenu for line thickness and style
        line_menu = menu.addMenu(_('Line style'))
        width1_action = line_menu.addAction(_('Thin (1px)'))
        width2_action = line_menu.addAction(_('Normal (2px)'))
        width4_action = line_menu.addAction(_('Thick (4px)'))
        width6_action = line_menu.addAction(_('Extra thick (6px)'))
        line_menu.addSeparator()
        dotted_action = line_menu.addAction(_('Dotted'))
        solid_action = line_menu.addAction(_('Solid'))
        # Color submenu
        color_menu = menu.addMenu(_('Line color'))
        red_action = color_menu.addAction(_('Red'))
        yellow_action = color_menu.addAction(_('Yellow'))
        green_action = color_menu.addAction(_('Green'))
        blue_action = color_menu.addAction(_('Blue'))
        cyan_action = color_menu.addAction(_('Cyan'))
        magenta_action = color_menu.addAction(_('Magenta'))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # snapshot before style/label changes (drag-undo pattern)
        if action != remove_action:
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
        # label editing
        if action == edit_label_action:
            new_label, ok = QtWidgets.QInputDialog.getText(
                None, _('Relation label'), _('Label for this line:'),
                QtWidgets.QLineEdit.EchoMode.Normal, self.label)
            if not ok:
                return
            self.label = new_label.strip()
            self._create_label_item()
            self.redraw()
            return
        # arrow direction
        if action == arrow_forward_action:
            self.arrow_mode = "forward"
            self.redraw()
        if action == arrow_backward_action:
            self.arrow_mode = "backward"
            self.redraw()
        if action == arrow_both_action:
            self.arrow_mode = "both"
            self.redraw()
        if action == arrow_none_action:
            self.arrow_mode = "none"
            self.redraw()
        if action == arrow_circle_action:
            self.arrow_mode = "circle"
            self.redraw()
        # Grosor. Thickness
        if action == width1_action:
            self.line_width = 1
            self.redraw()
        if action == width2_action:
            self.line_width = 2
            self.redraw()
        if action == width4_action:
            self.line_width = 4
            self.redraw()
        if action == width6_action:
            self.line_width = 6
            self.redraw()
        # Style
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
            self.redraw()
        if action == solid_action:
            self.line_type = QtCore.Qt.PenStyle.SolidLine
            self.redraw()
        # Color
        if action == red_action:
            self.color = "red"
            self.redraw()
        if action == yellow_action:
            self.color = "yellow"
            self.redraw()
        if action == green_action:
            self.color = "green"
            self.redraw()
        if action == blue_action:
            self.color = "blue"
            self.redraw()
        if action == orange_action:
            self.color = "orange"
            self.redraw()
        if action == cyan_action:
            self.color = "cyan"
            self.redraw()
        if action == magenta_action:
            self.color = "magenta"
            self.redraw()
        if action == gray_action:
            self.color = "gray"
            self.redraw()
        if action == remove_action:
            ui = DialogConfirmDelete(self.from_widget.app, _("Remove this line from the graph?"))
            if not ui.exec():
                return
            # snapshot AFTER confirmation
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.remove = True
            if scene:
                scene.removeItem(self)
                scene.update()
            return

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculate_points_and_draw()

    def calculate_points_and_draw(self):
        """ Cálculo fluido con punta de flecha giratoria. """

        c1 = self.from_widget.sceneBoundingRect().center()
        c2 = self.to_widget.sceneBoundingRect().center()
        self.setZValue(-1)

        is_ellipse_from = getattr(self.from_widget, 'is_ellipse', False)
        is_ellipse_to = getattr(self.to_widget, 'is_ellipse', False)

        rect1 = self.from_widget.sceneBoundingRect()
        rect2 = self.to_widget.sceneBoundingRect()

        # edge-point math delegated to the module-level compute_edge_point
        # helper (shared with LinkGraphicsItem, single source of truth).
        if rect1.intersects(rect2):
            p1, p2 = c1, c2
        else:
            p1 = compute_edge_point(c1, c2, rect1, is_ellipse_from)
            p2 = compute_edge_point(c2, c1, rect2, is_ellipse_to)
        color_obj = safe_color(self.color)  # tolerant color lookup
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))

        # Trigonometric arrow drawing
        dx = p1.x() - p2.x()
        dy = p1.y() - p2.y()
        theta = math.atan2(dy, dx)
        # cache geometry; paint() reads it to fill the arrowheads
        self._both_p1 = p1
        self._both_p2 = p2
        self._both_theta = theta
        polygon = QtGui.QPolygonF()
        polygon.append(p1)
        polygon.append(p2)
        # arrow excursion points are appended per arrow_mode so the item's
        # boundingRect always encloses the heads (no trails when dragging nodes).
        # The hollow pen lines are covered by the solid fill drawn in paint().
        arrow_size = 12
        if self.arrow_mode in ("forward", "both"):
            # Arrowheads at 30 degrees from the line axis.
            p3 = QtCore.QPointF(p2.x() + arrow_size * math.cos(theta + math.pi / 6),
                                p2.y() + arrow_size * math.sin(theta + math.pi / 6))
            p4 = QtCore.QPointF(p2.x() + arrow_size * math.cos(theta - math.pi / 6),
                                p2.y() + arrow_size * math.sin(theta - math.pi / 6))
            polygon.append(p3)
            polygon.append(p2)
            polygon.append(p4)
            polygon.append(p2)
        if self.arrow_mode in ("backward", "both"):
            theta_b = theta + math.pi
            p5 = QtCore.QPointF(p1.x() + arrow_size * math.cos(theta_b + math.pi / 6),
                                p1.y() + arrow_size * math.sin(theta_b + math.pi / 6))
            p6 = QtCore.QPointF(p1.x() + arrow_size * math.cos(theta_b - math.pi / 6),
                                p1.y() + arrow_size * math.sin(theta_b - math.pi / 6))
            polygon.append(p1)
            polygon.append(p5)
            polygon.append(p1)
            polygon.append(p6)
            polygon.append(p1)
        if self.arrow_mode == "circle":
            r = 6
            polygon.append(QtCore.QPointF(p2.x() + r, p2.y() + r))
            polygon.append(p2)
            polygon.append(QtCore.QPointF(p2.x() - r, p2.y() - r))
            polygon.append(p2)
        self.setPolygon(polygon)
        # keep the relation label centered and collision-free
        position_line_label(self, p1, p2)

    # fill the arrowheads solid (the polygon outline alone reads as wires)
    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self._both_p1 is None or self._both_p2 is None or self.arrow_mode == "none":
            return
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        color_obj = safe_color(self.color)
        painter.setBrush(QtGui.QBrush(color_obj))
        painter.setPen(QtGui.QPen(color_obj, 1))
        arrow_size = 12
        p1 = self.mapFromScene(self._both_p1)
        p2 = self.mapFromScene(self._both_p2)
        theta = self._both_theta
        if self.arrow_mode in ("forward", "both"):
            tri = QtGui.QPolygonF([
                p2,
                QtCore.QPointF(p2.x() + arrow_size * math.cos(theta + math.pi / 6),
                               p2.y() + arrow_size * math.sin(theta + math.pi / 6)),
                QtCore.QPointF(p2.x() + arrow_size * math.cos(theta - math.pi / 6),
                               p2.y() + arrow_size * math.sin(theta - math.pi / 6))])
            painter.drawPolygon(tri)
        if self.arrow_mode in ("backward", "both"):
            theta_b = theta + math.pi
            tri = QtGui.QPolygonF([
                p1,
                QtCore.QPointF(p1.x() + arrow_size * math.cos(theta_b + math.pi / 6),
                               p1.y() + arrow_size * math.sin(theta_b + math.pi / 6)),
                QtCore.QPointF(p1.x() + arrow_size * math.cos(theta_b - math.pi / 6),
                               p1.y() + arrow_size * math.sin(theta_b - math.pi / 6))])
            painter.drawPolygon(tri)
        if self.arrow_mode == "circle":
            painter.drawEllipse(p2, 5, 5)
        painter.restore()


class AVGraphicsItem(QtWidgets.QGraphicsPixmapItem):
    """ Coded audio video item. """

    def __init__(self, app, avid=-1, x=10, y=10, pos0=0, pos1=0, path_="", color="white"):
        """ A/V graphics object.
         Args:
            app  : the main App class
            avid : Integer  code_av primary key
            x : Integer x position of graphics item
            y : Integer y position of graphics item
            pos0 : Integer
            pos1 : Integer
            path : String
            color : String
         """

        super(AVGraphicsItem, self).__init__(None)
        self.app = app
        self.avid = avid
        self.code_or_cat = {'cid': None, 'catid': None}
        # Retrieve the cid if it is a saved segment (required for category collapsing).
        if self.avid is not None and self.avid != -1:
            cur = self.app.conn.cursor()
            cur.execute("select cid from code_av where avid=?", [self.avid])
            res = cur.fetchone()
            if res:
                self.code_or_cat['cid'] = res[0]
        self.text = f"AVID:{self.avid}"
        self.pos0 = pos0
        self.pos1 = pos1
        self.path_ = path_
        self.color = color
        self.abs_path_ = self.app.project_path + path_
        if path_[0:7] in ("audio:", "video:"):
            self.abs_path_ = path_[7:]
        self.setPixmap(qta.icon('mdi6.play').pixmap(28, 28))
        self.setPos(x, y)
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def __repr__(self):
        txt = f"AVGraphicsItem avid:{self.avid} Path:{self.abs_path_} color:{self.color} code_cat:{self.code_or_cat}"
        txt += f"\ntext: {self.text}"
        return txt

    # trigger handle sync when selection changes (deferred for multi-selection)
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._sync_handles_with_selection)
        return super().itemChange(change, value)

    # delegates to module-level helper (single source of truth)
    def _sync_handles_with_selection(self):
        sync_handles_with_selection(self)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        context_action = menu.addAction(_("View in context"))
        # import and link the memo of this A/V coding (if non-empty)
        import_memo_action = None
        segment_memo_text = ""
        if self.avid is not None and self.avid > 0:
            cur_memo = self.app.conn.cursor()
            cur_memo.execute("select ifnull(memo,'') from code_av where avid=?", [self.avid])
            res_memo = cur_memo.fetchone()
            segment_memo_text = res_memo[0] if res_memo else ""
            if segment_memo_text:
                import_memo_action = menu.addAction(_("Add and link memo"))
        menu.addSeparator()
        # Color submenu
        color_menu = menu.addMenu(_("Color"))
        red_action = color_menu.addAction(_("Red"))
        green_action = color_menu.addAction(_("Green"))
        yellow_action = color_menu.addAction(_("Yellow"))
        blue_action = color_menu.addAction(_("Blue"))
        magenta_action = color_menu.addAction(_("Magenta"))
        cyan_action = color_menu.addAction(_("Cyan"))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        white_action = color_menu.addAction(_("White"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # snapshot for color changes only; view/import/remove handle their own state
        if action not in (context_action, import_memo_action, remove_action):
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
        # import-and-link memo (delegates to module-level helper)
        if import_memo_action and action == import_memo_action:
            link_memo_to_segment(self.app, self, 'code_av', self.avid, segment_memo_text)
            return
        if action == context_action:
            cur = self.app.conn.cursor()
            # join source so fid is available for the context dialog
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_av.owner,"
                        "ifnull(code_av.memo,''), source.id "
                        "from code_av join code_name on code_name.cid=code_av.cid "
                        "join source on source.id=code_av.id where code_av.avid=?",
                        [self.avid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find audio/video coding in database")).exec()
                return
            # cid was res[2] (the color) in legacy; correct index is res[0].
            # fid and file_or_case added, as DialogCodeInAV expects them.
            data = {'pos0': self.pos0, 'pos1': self.pos1, 'file_or_casename': self.path_, 'mediapath': self.path_,
                    'coder': res[3], 'codename': res[1], 'cid': res[0], 'color': res[2], 'memo': res[4],
                    'fid': res[5], 'file_or_case': 'File'}
            DialogCodeInAV(self.app, data).exec()

        if action == remove_action:
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            # snapshot AFTER confirmation
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.remove = True
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return

        if action == red_action:
            self.color = "red"
        if action == green_action:
            self.color = "green"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == yellow_action:
            self.color = "yellow"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == gray_action:
            self.color = "gray"
        if action == white_action:
            self.color = "white"

    def paint(self, painter, option, widget=None):
        painter.save()
        color_obj = safe_color(self.color)  # tolerant color lookup
        painter.setBrush(QtGui.QBrush(color_obj, style=QtCore.Qt.BrushStyle.SolidPattern))
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class PixmapGraphicsItem(QtWidgets.QGraphicsPixmapItem):
    """ Coded pixmap. Uses Images and PDF image files.
    Maximum size of 200 pixels high and wide. """

    MAX_WIDTH = 300
    MAX_HEIGHT = 300

    def __init__(self, app, imid=-1, x=10, y=10, px=0, py=0, pwidth=0, pheight=0, path_="", grpixid=None,
                 pdf_page=None):
        """ pixmap object.
         param:
            app  : the main App class
            imid : Integer code_image primary key
            x : Integer x position of graphics item
            y : Integer y position of graphics item
            px : Integer
            py + Integer
            pwidth : Integer
            pheight : Integer
            grpixid : None or Integer from gr_pix_item table
            pdf_page : For Pdf images
         """

        super(PixmapGraphicsItem, self).__init__(None)
        self.app = app
        self.imid = imid
        self.code_or_cat = {'cid': None, 'catid': None}
        # Retrieve the cid if it is a saved segment (required for category collapsing)
        if self.imid is not None and self.imid != -1:
            cur = self.app.conn.cursor()
            cur.execute("select cid from code_image where imid=?", [self.imid])
            res = cur.fetchone()
            if res:
                self.code_or_cat['cid'] = res[0]
        self.text = f"IMID: {self.imid}"
        self.px = px
        self.py = py
        self.pwidth = pwidth
        self.pheight = pheight
        self.path_ = path_
        self.grpixid = grpixid  # gr_pix_item table id. id for database stored free pixmap graph ite
        self.pdf_page = pdf_page

        # Image jpg, png
        abs_path_ = self.app.project_path + path_
        if path_[0:7] == "images:":
            abs_path_ = path_[7:]

        # Pdf image
        if self.pdf_page is not None:
            source_path = ""
            if path_[:6] == "/docs/":
                source_path = f"{self.app.project_path}/documents/{path_[6:]}"
            if path_[:5] == "docs:":
                source_path = path_[5:]
            # In-memory render of ONLY the needed page, range-guarded and with the
            # document always closed. The previous code indexed fitz_pdf[self.pdf_page]
            # without a guard (IndexError crashed loading a saved graph if the pdf
            # changed page count), never closed the handle (blocked pdf deletion on
            # Windows) and wrote a residual tmp_pdf_page.png.
            image = QtGui.QImage()
            try:
                fitz_pdf = fitz.open(source_path)
                try:
                    if 0 <= self.pdf_page < len(fitz_pdf):
                        page = fitz_pdf.load_page(self.pdf_page)
                        pix = page.get_pixmap(alpha=False, annots=False)  # PDF highlights/notes not painted
                        image = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride,
                                             QtGui.QImage.Format.Format_RGB888).copy()
                finally:
                    fitz_pdf.close()
            except Exception as err:
                logger.warning(f"Graph pdf area: {source_path} {err}")
        else:
            image = QtGui.QImageReader(abs_path_).read()
        image = image.copy(int(px), int(py), int(pwidth), int(pheight))

        # Scale to max 200 wide or high. (TODO Perhaps add option to change maximum limits)
        scaler_w = 1.0
        scaler_h = 1.0
        if image.width() > 200:
            scaler_w = 200 / image.width()
        if image.height() > 200:
            scaler_h = 200 / image.height()
        if scaler_w < scaler_h:
            scaler = scaler_w
        else:
            scaler = scaler_h
        pixmap = QtGui.QPixmap().fromImage(image)
        pixmap = pixmap.scaled(int(image.width() * scaler), int(image.height() * scaler))
        self.setPixmap(pixmap)
        # keep the base pixmap so _scale_graph can resize without quality loss
        self._original_pixmap = pixmap
        self.setPos(x, y)
        self.settings = app.settings
        self.project_path = app.project_path
        self.remove = False
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def __repr__(self):
        txt = f"PixmapGraphicsItem imid:{self.imid} grpxid:{self.grpixid} Path:{self.path_}"
        txt += f"\npx:{self.px} py:{self.py} w:{self.pwidth} h:{self.pheight}"
        txt += f"\nTexT:{self.text}"
        return txt

    # trigger handle sync when selection changes (deferred for multi-selection)
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._sync_handles_with_selection)
        return super().itemChange(change, value)

    # delegates to module-level helper (single source of truth)
    def _sync_handles_with_selection(self):
        sync_handles_with_selection(self)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        context_action = menu.addAction(_("View in context"))
        # import and link the memo of this image coding (if non-empty)
        import_memo_action = None
        segment_memo_text = ""
        if self.imid is not None and self.imid > 0:
            cur_memo = self.app.conn.cursor()
            cur_memo.execute("select ifnull(memo,'') from code_image where imid=?", [self.imid])
            res_memo = cur_memo.fetchone()
            segment_memo_text = res_memo[0] if res_memo else ""
            if segment_memo_text:
                import_memo_action = menu.addAction(_("Add and link memo"))
        menu.addSeparator()
        remove_action = menu.addAction(_('Remove'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # import-and-link memo (delegates to module-level helper)
        if import_memo_action and action == import_memo_action:
            link_memo_to_segment(self.app, self, 'code_image', self.imid, segment_memo_text)
            return
        if action == context_action:
            '''{codename, color, file_or_casename, x1, y1, width, height, coder,
             mediapath, fid, memo, file_or_case}'''
            cur = self.app.conn.cursor()
            # join source so fid is available for the context dialog
            cur.execute("select code_name.cid, code_name.name, code_name.color, code_image.owner,"
                        "ifnull(code_image.memo,''), source.id, pdf_page "
                        "from code_image join code_name on code_name.cid=code_image.cid "
                        "join source on source.id=code_image.id where code_image.imid=?",
                        [self.imid])
            res = cur.fetchone()
            if res is None:
                Message(self.app, _("Error"), _("Cannot find image coding in database")).exec()
                return
            # cid was res[2] (the color) in legacy; correct index is res[0].
            # fid and file_or_case added, as DialogCodeInImage expects them.
            data = {'x1': self.px, 'y1': self.py, 'width': self.pwidth, 'height': self.pheight,
                    'file_or_casename': self.path_, 'mediapath': self.path_, 'coder': res[3],
                    'codename': res[1], 'cid': res[0], 'color': res[2], 'memo': res[4],
                    'fid': res[5], 'file_or_case': 'File', 'pdf_page': res[6]}
            DialogCodeInImage(self.app, data).exec()

        if action == remove_action:
            ui = DialogConfirmDelete(self.app, _("Remove this item from the graph?"))
            if not ui.exec():
                return
            # snapshot AFTER confirmation
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.remove = True
            for item in scene.items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if item.from_widget == self or item.to_widget == self:
                            scene.removeItem(item)
            scene.removeItem(self)
            scene.update()
            return

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)


class TextGraphicsItem(QtWidgets.QGraphicsTextItem):
    """ The item show the name and color of the code or category
    Categories are shown white. A custom context menu
    allows selection of a code/category memo and displaying the information.
    """

    def __init__(self, app, code_or_cat, font_size=9, bold=None, isvisible=True, displayed_text=""):
        """ Show name and colour of text. Has context menu for various options.
         param: app  : the main App class
         param: code_or_cat  : Dictionary of the code details: name, memo, color etc
         param: font_size : Integer
         param: bold : boolean, or None = categories default to bold
         param: isvisible : boolean
         """

        super(TextGraphicsItem, self).__init__(None)
        self.app = app
        self.conn = app.conn
        self.settings = app.settings
        self.project_path = app.project_path
        self.code_or_cat = code_or_cat
        self.font_size = font_size
        # categories are bold by default to stand out from codes;
        # an explicit bold argument (e.g. from a saved graph) is always respected.
        if bold is None:
            bold = code_or_cat['cid'] is None
        self.bold = bold
        self.is_ellipse = False
        self.is_collapsed = False
        self.setPos(self.code_or_cat['x'], self.code_or_cat['y'])
        self.text = displayed_text
        if self.text == "":
            self.text = self.code_or_cat['name']
        self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setDefaultTextColor(QtGui.QColor(TextColor(self.code_or_cat['color']).recommendation))
        fontweight = QtGui.QFont.Weight.Normal
        if self.bold:
            fontweight = QtGui.QFont.Weight.Bold
        self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        self.setPlainText(self.code_or_cat['name'])
        if not isvisible:
            self.hide()
        self.code_or_cat['memo'] = ""
        self.get_memo()

    def __repr__(self):
        txt = f"TextGraphicsItem CodeOrCat:{self.code_or_cat} Font:{self.font_size} Bold:{self.bold}\n"
        txt += f"Ellipse:{self.is_ellipse} Collapse:{self.is_collapsed}\n"
        txt += f"Text:{self.text}"
        return txt

    # trigger handle sync when selection changes (deferred for multi-selection)
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._sync_handles_with_selection)
        return super().itemChange(change, value)

    # delegates to module-level helper (single source of truth)
    def _sync_handles_with_selection(self):
        sync_handles_with_selection(self)

    def get_memo(self):
        cur = self.app.conn.cursor()
        if self.code_or_cat['cid'] is not None:
            cur.execute("select ifnull(memo,'') from code_name where name=?", [self.code_or_cat['name']])
            res = cur.fetchone()
            if res:
                self.code_or_cat['memo'] = res[0]
                self.setToolTip(_("Code") + ": " + res[0])
            else:
                self.setToolTip(_("Code"))
        else:
            cur.execute("select ifnull(memo,'') from code_cat where name=?", [self.code_or_cat['name']])
            res = cur.fetchone()
            if res:
                self.code_or_cat['memo'] = res[0]
                self.setToolTip(_("Category") + ": " + res[0])
            else:
                self.setToolTip(_("Category"))

    def paint(self, painter, option, widget):
        painter.save()
        color = QtGui.QColor(self.code_or_cat['color'])
        painter.setBrush(QtGui.QBrush(color, style=QtCore.Qt.BrushStyle.SolidPattern))
        # ellipse or rectangle, per the is_ellipse visual flag
        if getattr(self, 'is_ellipse', False):
            painter.drawEllipse(self.boundingRect())
        else:
            painter.drawRect(self.boundingRect())
        painter.restore()
        super().paint(painter, option, widget)

    # find a code/category node in the scene by ids; returns the item or None
    def _find_node_in_scene(self, cid=None, catid=None):
        scene = self.scene()
        if scene is None:
            return None
        for item in scene.items():
            if type(item).__name__ == "TextGraphicsItem" and item is not self:
                if cid is not None and item.code_or_cat.get('cid') == cid:
                    return item
                if cid is None and catid is not None and item.code_or_cat.get('cid') is None \
                        and item.code_or_cat.get('catid') == catid:
                    return item
        return None

    # show a hidden node again, plus any lines whose endpoints are both visible
    def _recover_hidden_node(self, node):
        node.show()
        scene = self.scene()
        for item in scene.items():
            if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                    if item.from_widget.isVisible() and item.to_widget.isVisible():
                        item.show()
        scene.update()

    def contextMenuEvent(self, event):
        """ https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        # context menu reorganized into themed submenus
        # (Add to graph / Memo / Coding / Appearance) instead of one long flat list.
        # Add to graph: bring related items into the scene
        add_menu = menu.addMenu(_('Add'))
        add_segments_action = None
        add_cooc_action = None
        add_parent_cat_action = None
        add_parent_code_action = None
        add_child_codes_action = None
        import_memo_action = None
        if self.code_or_cat['cid'] is not None:
            add_segments_action = add_menu.addAction(_('Coded segments'))
            add_cooc_action = add_menu.addAction(_('Co-occurrences'))
            # bring the parent category of this code into the scene
            if self.code_or_cat.get('catid') is not None:
                parent_cat_node = self._find_node_in_scene(catid=self.code_or_cat['catid'])
                if parent_cat_node is None or not parent_cat_node.isVisible():
                    add_parent_cat_action = add_menu.addAction(_('Category'))
            # (sub-codes): bring the parent CODE of this sub-code into the scene
            if self.code_or_cat.get('supercid') is not None:
                parent_code_node = self._find_node_in_scene(cid=self.code_or_cat['supercid'])
                if parent_code_node is None or not parent_code_node.isVisible():
                    add_parent_code_action = add_menu.addAction(_('Add parent code'))
        else:
            # category node, offer its child codes and its parent category
            add_child_codes_action = add_menu.addAction(_('Add child codes'))
            if self.code_or_cat.get('supercatid') is not None:
                parent_cat_node = self._find_node_in_scene(catid=self.code_or_cat['supercatid'])
                if parent_cat_node is None or not parent_cat_node.isVisible():
                    add_parent_cat_action = add_menu.addAction(_('Add category'))
        # import and link the memo of this code/category (if non-empty)
        if self.code_or_cat.get('memo'):
            import_memo_action = add_menu.addAction(_("Memo"))
        # Memo submenu
        memo_menu = menu.addMenu(_('Memo'))
        memo_action = memo_menu.addAction(_('View Memo'))
        show_memo_action = None
        hide_memo_action = None
        if self.code_or_cat['memo'] != "":
            if "\nMEMO:" in self.text:
                hide_memo_action = memo_menu.addAction(_("Hide memo"))
            else:
                show_memo_action = memo_menu.addAction(_("Display memo"))
        # Coding submenu (codes only): inspect coded media
        coded_action = None
        case_action = None
        if self.code_or_cat['cid'] is not None:
            coding_menu = menu.addMenu(_('Coding'))
            coded_action = coding_menu.addAction(_('View text and media'))
            case_action = coding_menu.addAction(_('Case text and media'))
        # Appearance submenu
        appearance_menu = menu.addMenu(_('Appearance'))
        bold_action = appearance_menu.addAction(_("Bold toggle"))
        shape_action = appearance_menu.addAction(_('Toggle: Ellipse/Rectangle'))
        # Sub-menú para el tamaño de fuente. Submenu for font size
        font_size_menu = appearance_menu.addMenu(_("Font size"))
        font_size_actions = {}
        for size in [8, 10, 12, 14, 16, 18, 20]:
            act = font_size_menu.addAction(str(size))
            font_size_actions[act] = size
        menu.addSeparator()
        collapse_action = None
        if self.code_or_cat.get('child_names'):
            if getattr(self, 'is_collapsed', False):
                collapse_action = menu.addAction(_('Expand'))
            else:
                collapse_action = menu.addAction(_('Collapse'))
        hide_action = menu.addAction(_('Hide'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # unified undo snapshot. Actions in _self_snapshot_actions manage
        # their own snapshot (after user confirmation) or are read-only dialogs.
        _self_snapshot_actions = {memo_action, coded_action, case_action, hide_action,
                                  add_segments_action, add_cooc_action, add_child_codes_action,
                                  add_parent_cat_action, add_parent_code_action, import_memo_action}
        if action not in _self_snapshot_actions:
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
        # import-and-link memo (delegates to module-level helper)
        if import_memo_action and action == import_memo_action:
            if self.code_or_cat['cid'] is not None:
                link_memo_to_segment(self.app, self, 'code', self.code_or_cat['cid'],
                                     self.code_or_cat.get('memo', ''))
            else:
                link_memo_to_segment(self.app, self, 'category', self.code_or_cat['catid'],
                                     self.code_or_cat.get('memo', ''))
            return
        # parent category / parent code / child codes
        if add_parent_cat_action and action == add_parent_cat_action:
            self.add_parent_category_to_scene()
            return
        if add_parent_code_action and action == add_parent_code_action:
            self.add_parent_code_to_scene()
            return
        if add_child_codes_action and action == add_child_codes_action:
            self.add_child_codes_to_scene()
            return
        if action == shape_action:
            self.is_ellipse = not self.is_ellipse
            self.update()
        if collapse_action and action == collapse_action:
            self.toggle_collapse()
        if action == add_segments_action:
            self.add_coded_segments()
        if action == add_cooc_action:
            self.add_cooccurring_codes()
        if action == show_memo_action:
            self.text = f"{self.code_or_cat['name']}\nMEMO: {self.code_or_cat['memo']}"
            self.setPlainText(self.text)
        if action == hide_memo_action:
            self.text = self.code_or_cat['name']
            self.setPlainText(self.text)
        if action == bold_action:
            self.bold = not self.bold
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action in font_size_actions:
            self.font_size = font_size_actions[action]
            fontweight = QtGui.QFont.Weight.Normal
            if self.bold:
                fontweight = QtGui.QFont.Weight.Bold
            self.setFont(QtGui.QFont(self.settings['font'], self.font_size, fontweight))
        if action == memo_action:
            self.add_edit_memo()
            self.get_memo()
        if action == coded_action:
            self.coded_media()
        if action == case_action:
            self.case_media()
        if action == hide_action:
            ui_confirm = DialogConfirmDelete(self.app, _("Hide this item?"))
            if not ui_confirm.exec():
                return
            # snapshot AFTER confirmation
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.hide()
            for item in self.scene().items():
                if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                    if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                        if not item.from_widget.isVisible() or not item.to_widget.isVisible():
                            item.hide()
            self.scene().update()

    # bring the parent category of this node into the scene (or recover it
    # if it is present but hidden). Works for a code (catid) and a category (supercatid).
    def add_parent_category_to_scene(self):
        if self.code_or_cat['cid'] is not None:
            parent_catid = self.code_or_cat.get('catid')
        else:
            parent_catid = self.code_or_cat.get('supercatid')
        if parent_catid is None:
            return
        existing = self._find_node_in_scene(catid=parent_catid)
        if existing is not None:
            if not existing.isVisible():
                self._recover_hidden_node(existing)
            return
        cur = self.app.conn.cursor()
        cur.execute("select name, ifnull(memo,''), supercatid from code_cat where catid=?", [parent_catid])
        res = cur.fetchone()
        if res is None:
            return
        scene = self.scene()
        if scene is not None and getattr(scene, 'parent', None) is not None:
            if hasattr(scene.parent, '_save_undo_state'):
                scene.parent._save_undo_state()
        cat_data = {'name': res[0], 'supercatid': res[2], 'catid': parent_catid, 'cid': None,
                    'x': self.pos().x() - 180, 'y': self.pos().y(),
                    'color': '#FFFFFF', 'memo': res[1], 'child_names': []}
        new_node = TextGraphicsItem(self.app, cat_data)
        scene.addItem(new_node)
        # Hierarchy convention: child -> parent (same as the reactive synchronizer)
        line_item = LinkGraphicsItem(self, new_node, 2, "solid", "gray", True)
        scene.addItem(line_item)
        scene.update()

    # (sub-codes): mirror of add_parent_category_to_scene for a sub-code,
    # bringing its parent CODE (supercid) into the scene, or recovering it if hidden.
    def add_parent_code_to_scene(self):
        parent_cid = self.code_or_cat.get('supercid')
        if parent_cid is None:
            return
        existing = self._find_node_in_scene(cid=parent_cid)
        if existing is not None:
            if not existing.isVisible():
                self._recover_hidden_node(existing)
            return
        cur = self.app.conn.cursor()
        cur.execute("select cid, name, color, ifnull(memo,''), catid, supercid from code_name where cid=?",
                    [parent_cid])
        res = cur.fetchone()
        if res is None:
            return
        scene = self.scene()
        if scene is not None and getattr(scene, 'parent', None) is not None:
            if hasattr(scene.parent, '_save_undo_state'):
                scene.parent._save_undo_state()
        code_data = {'name': res[1], 'supercatid': None, 'catid': res[4], 'cid': res[0],
                     'supercid': res[5],
                     'x': self.pos().x() - 180, 'y': self.pos().y(),
                     'color': res[2], 'memo': res[3], 'child_names': []}
        new_node = TextGraphicsItem(self.app, code_data)
        scene.addItem(new_node)
        # Hierarchy convention: child -> parent (sub-code -> parent code)
        line_item = LinkGraphicsItem(self, new_node, 2, "solid", "gray", True)
        scene.addItem(line_item)
        scene.update()

    # import the child codes of this category that are not yet in the scene
    def add_child_codes_to_scene(self):
        catid = self.code_or_cat.get('catid')
        if catid is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select cid, name, color, ifnull(memo,'') from code_name where catid=?", [catid])
        res = cur.fetchall()
        candidates = []
        for r in res:
            if self._find_node_in_scene(cid=r[0]) is None:
                candidates.append({'cid': r[0], 'name': r[1], 'color': r[2], 'memo': r[3]})
        if not candidates:
            Message(self.app, _("No codes"),
                    _("All child codes of this category are already in the graph.")).exec()
            return
        ui = DialogSelectItems(self.app, candidates, _("Select codes to add"), "multi")
        if not ui.exec():
            return
        selected = ui.get_selected()
        if not selected:
            return
        scene = self.scene()
        if scene is not None and getattr(scene, 'parent', None) is not None:
            if hasattr(scene.parent, '_save_undo_state'):
                scene.parent._save_undo_state()
        radius = 200
        angle_step = (2 * math.pi) / max(1, len(selected))
        for i, s in enumerate(selected):
            if self._find_node_in_scene(cid=s['cid']) is not None:
                continue
            angle = i * angle_step
            cx = self.pos().x() + radius * math.cos(angle)
            cy = self.pos().y() + radius * math.sin(angle)
            # 'supercid': None for dict uniformity; the next reactive sync fills the
            # real value from the database (sub-codes).
            code_data = {'name': s['name'], 'supercatid': None, 'catid': catid, 'cid': s['cid'],
                         'supercid': None,
                         'x': cx, 'y': cy, 'color': s['color'], 'memo': s['memo'], 'child_names': []}
            new_node = TextGraphicsItem(self.app, code_data)
            scene.addItem(new_node)
            # Hierarchy convention: child -> parent
            line_item = LinkGraphicsItem(new_node, self, 2, "solid", "gray", True)
            scene.addItem(line_item)
        scene.update()

    def add_coded_segments(self):
        """ Window to import coded segments from text, image, and A/V associated with this code.
        Generates automatic dotted links using the FreeLineGraphicsItem.
        """

        cur = self.app.conn.cursor()
        cid = self.code_or_cat['cid']
        code_name = self.code_or_cat['name']

        # Collect TEXT segments
        sql_text = ("select code_text.cid, code_text.fid, code_text.seltext, "
                    "ifnull(code_text.memo,''), code_text.ctid, source.name "
                    "from code_text join source on source.id = code_text.fid "
                    "where code_text.cid=?")
        cur.execute(sql_text, [cid])
        res_text = cur.fetchall()
        text_codings = []
        for r in res_text:
            already_present = any(isinstance(item, FreeTextGraphicsItem) and item.ctid == r[4]
                          for item in self.scene().items())
            if not already_present:
                # To fix error in save graph: 2034, in save_graph
                # i.to_widget.code_or_cat['catid'], i.to_widget.code_or_cat['cid'],
                code_or_cat = {'cid':r[0], 'catid': None}
                text_codings.append({
                    'cid': r[0], 'fid': r[1], 'name': r[2], 'memo': r[3],
                    'ctid': r[4], 'filename': r[5], 'codename': code_name,
                    'code_or_cat': code_or_cat
                })

        # Collect IMAGE segments
        sql_img = ("select code_image.cid, code_image.id, x1, y1, width, height, "
                   "ifnull(code_image.memo,''), code_image.imid, code_image.pdf_page, "
                   "source.name, source.mediapath "
                   "from code_image join source on source.id = code_image.id "
                   "where code_image.cid=?")
        cur.execute(sql_img, [cid])
        res_img = cur.fetchall()
        image_codings = []
        for r in res_img:
            already_present = any(isinstance(item, PixmapGraphicsItem) and item.imid == r[7]
                          for item in self.scene().items())
            if not already_present:
                # To fix error in save graph: 2034, in save_graph
                # i.to_widget.code_or_cat['catid'], i.to_widget.code_or_cat['cid'],
                code_or_cat = {'cid': r[0], 'catid': None}
                image_codings.append({
                    'cid': r[0], 'fid': r[1], 'x': int(r[2]), 'y': int(r[3]),
                    'width': int(r[4]), 'height': int(r[5]), 'memo': r[6],
                    'imid': r[7], 'pdf_page': r[8], 'filename': r[9],
                    'path': r[10] if r[10] else '', 'codename': code_name,
                    'name': f"{r[9]} x:{int(r[2])} y:{int(r[3])} w:{int(r[4])} h:{int(r[5])}",
                    'code_or_cat': code_or_cat
                })

        # Collect A/V segments
        sql_av = ("select code_av.cid, code_av.id, code_av.pos0, code_av.pos1, "
                  "ifnull(code_av.memo,''), code_av.avid, source.name, source.mediapath "
                  "from code_av join source on source.id = code_av.id "
                  "where code_av.cid=?")
        cur.execute(sql_av, [cid])
        res_av = cur.fetchall()
        av_codings = []
        for r in res_av:
            already_present = any(isinstance(item, AVGraphicsItem) and item.avid == r[5]
                          for item in self.scene().items())
            if not already_present:
                # To fix error in save graph: 2034, in save_graph
                # i.to_widget.code_or_cat['catid'], i.to_widget.code_or_cat['cid'],
                code_or_cat = {'cid': r[0], 'catid': None}
                av_codings.append({
                    'cid': r[0], 'fid': r[1], 'pos0': int(r[2]), 'pos1': int(r[3]),
                    'memo': r[4], 'avid': r[5], 'filename': r[6],
                    'path': r[7] if r[7] else '', 'codename': code_name,
                    'name': f"{r[6]}: {int(r[2])} to {int(r[3])} msecs",
                    'code_or_cat': code_or_cat
                })

        if not text_codings and not image_codings and not av_codings:
            Message(self.app, _("No segments"),
                    _("There are no new coded segments for this code.")).exec()
            return

        # Show unified dialog to select text, image, A/V segments
        ui = DialogSelectCodedSegments(
            self.app, code_name, text_codings, image_codings, av_codings, self.scene().views()[0]
        )
        if not ui.exec():
            return
        # snapshot AFTER confirmation, so Cancel never pollutes the undo stack
        scene = self.scene()
        if scene is not None and getattr(scene, 'parent', None) is not None:
            if hasattr(scene.parent, '_save_undo_state'):
                scene.parent._save_undo_state()

        x = self.pos().x() + 180
        y = self.pos().y()

        # Import selected TEXT segments
        for s in ui.selected_text:
            y += 40
            freetextid = 1
            for item in self.scene().items():
                if isinstance(item, FreeTextGraphicsItem) and item.freetextid >= freetextid:
                    freetextid = item.freetextid + 1
            item = FreeTextGraphicsItem(self.app, freetextid, x, y, s['name'], 9, "black", False, s['ctid'])
            msg = f"File: {s['filename']}\nCode: {s['codename']}"
            if s['memo']:
                msg += f"\nMemo: {s['memo']}"
            item.setToolTip(msg)
            item.code_or_cat['cid'] = cid
            self.scene().addItem(item)
            line_item = FreeLineGraphicsItem(self, item, line_width=2, line_type="dotted", color="gray")
            self.scene().addItem(line_item)

        # Import selected IMAGE segments
        for s in ui.selected_image:
            y += 40
            item = PixmapGraphicsItem(self.app, s['imid'], x, y, s['x'], s['y'], s['width'], s['height'],
                                      s['path'], None, s['pdf_page'])
            msg = f"IMID:{s['imid']} File: {s['filename']}\nCode: {s['codename']}"
            if s['memo']:
                msg += f"\nMemo: {s['memo']}"
            item.setToolTip(msg)
            item.code_or_cat['cid'] = cid
            self.scene().addItem(item)
            line_item = FreeLineGraphicsItem(self, item, line_width=2, line_type="dotted", color="gray")
            self.scene().addItem(line_item)

        # Import selected A/V segments
        for s in ui.selected_av:
            y += 40
            item = AVGraphicsItem(self.app, s['avid'], x, y, s['pos0'], s['pos1'], s['path'])
            msg = f"AVID:{s['avid']} File: {s['filename']}\nCode: {s['codename']}"
            msg += f"\n{s['pos0']} - {s['pos1']} msecs"
            if s['memo']:
                msg += f"\nMemo: {s['memo']}"
            item.setToolTip(msg)
            item.code_or_cat['cid'] = cid
            self.scene().addItem(item)
            line_item = FreeLineGraphicsItem(self, item, line_width=2, line_type="dotted", color="gray")
            self.scene().addItem(line_item)

    def add_cooccurring_codes(self):
        """ Importa códigos co-ocurrentes desde un nodo específico sin duplicados.
         Import co-occurring codes from a specific node without duplicates.
         """

        cur = self.app.conn.cursor()
        sql = """
        SELECT c2.cid, n2.name, n2.color, COUNT(c2.cid) as overlap_count
        FROM code_text c1
        JOIN code_text c2 ON c1.fid = c2.fid AND c1.cid != c2.cid AND c1.pos0 < c2.pos1 AND c1.pos1 > c2.pos0
        JOIN code_name n2 ON c2.cid = n2.cid
        WHERE c1.cid = ?
        GROUP BY c2.cid, n2.name, n2.color
        """
        cur.execute(sql, [self.code_or_cat['cid']])
        res = cur.fetchall()
        if not res:
            Message(self.app, _("No co-ocurrences"), "No overlapping codes for this code in the text.").exec()
            return

        cooc_list = [
            {'cid': r[0], 'name': f"{r[1]} (Co-occ freq: {r[3]})", 'raw_name': r[1], 'color': r[2], 'count': r[3]} for r
            in res]
        ui = DialogSelectItems(self.app, cooc_list, "Select codes", "multi")
        if not ui.exec():
            return
        selected = ui.get_selected()
        # snapshot AFTER confirmation, so Cancel never pollutes the undo stack
        scene = self.scene()
        if scene is not None and getattr(scene, 'parent', None) is not None:
            if hasattr(scene.parent, '_save_undo_state'):
                scene.parent._save_undo_state()
        # redundant "import math" removed (math imported at module level)
        radius = 250
        angle_step = (2 * math.pi) / max(1, len(selected))
        for i, s in enumerate(selected):
            # CORRECCIÓN: Uso estricto de str(). CORRECTION: Strict use of str().
            target_node = next((item for item in self.scene().items() if
                                type(item).__name__ == "TextGraphicsItem" and str(item.code_or_cat.get('cid')) == str(
                                    s['cid'])), None)
            if not target_node:
                angle = i * angle_step
                cx = self.pos().x() + radius * math.cos(angle)
                cy = self.pos().y() + radius * math.sin(angle)
                # 'supercid': None for dict uniformity; the next reactive sync fills the
                # real value from the database (sub-codes).
                code_data = {'name': s['raw_name'], 'supercatid': None, 'catid': None, 'cid': s['cid'],
                             'supercid': None,
                             'x': cx, 'y': cy, 'color': s['color'], 'memo': "", 'child_names': []}
                target_node = TextGraphicsItem(self.app, code_data)
                self.scene().addItem(target_node)

            line_exists = any(type(link).__name__ == "LinkGraphicsItem" and
                              ((link.from_widget == self and link.to_widget == target_node) or
                               (link.from_widget == target_node and link.to_widget == self))
                              for link in self.scene().items())
            if not line_exists:
                line_item = LinkGraphicsItem(self, target_node, line_width=2, line_type="dotted", color="blue",
                                             isvisible=True)
                self.scene().addItem(line_item)

    def add_edit_memo(self):
        """ Add or edit memos for codes and categories. """

        if self.code_or_cat['cid'] is not None:
            ui = DialogMemo(self.app, _("Memo for Code ") + self.code_or_cat['name'], self.code_or_cat['memo'])
            ui.exec()
            self.code_or_cat['memo'] = ui.memo
            cur = self.conn.cursor()
            cur.execute("update code_name set memo=? where cid=?", (self.code_or_cat['memo'], self.code_or_cat['cid']))
            self.conn.commit()
        if self.code_or_cat['catid'] is not None and self.code_or_cat['cid'] is None:
            ui = DialogMemo(self.app, _("Memo for Category ") + self.code_or_cat['name'], self.code_or_cat['memo'])
            ui.exec()
            self.code_or_cat['memo'] = ui.memo
            cur = self.conn.cursor()
            cur.execute("update code_cat set memo=? where catid=?",
                        (self.code_or_cat['memo'], self.code_or_cat['catid']))
            self.conn.commit()

    def toggle_collapse(self):
        """ Oculta o muestra todos los nodos descendientes y actualiza las líneas.
         Hides or shows all descendant nodes and updates the lines"""
        self.is_collapsed = not getattr(self, 'is_collapsed', False)
        # refresh child names first, so sub-codes or codes added after this
        # node was created are also covered and the action propagates to ALL children.
        scene = self.scene()
        if scene is not None and getattr(scene, 'parent', None) is not None \
                and hasattr(scene.parent, 'named_children_of_node'):
            self.code_or_cat['child_names'] = scene.parent.named_children_of_node(self.code_or_cat)

        # 1. Recopilar CIDs del nodo actual (si aplica) para ocultar sus propios segmentos. Collect CIDs from the current node (if applicable) to hide its own segments
        child_cids = []
        if self.code_or_cat.get('cid') is not None:
            child_cids.append(self.code_or_cat['cid'])

        # 2. Ocultar/Mostrar nodos hijos en cascada y recolectar sus CIDs. Hide/Show child nodes in cascade and collect their CIDs
        for item in self.scene().items():
            if type(item).__name__ == "TextGraphicsItem" and item != self:
                if item.code_or_cat['name'] in self.code_or_cat.get('child_names', []):
                    # Guardar el CID de los códigos hijos para ocultar sus segmentos. Save the CID of child codes to hide their segments.
                    if item.code_or_cat.get('cid') is not None:
                        child_cids.append(item.code_or_cat['cid'])

                    if self.is_collapsed:
                        item.hide()
                    else:
                        item.show()
                        item.is_collapsed = False  # Reinicia el estado de los hijos para evitar errores lógicos. Reset the state of the children to prevent logical errors

        # 3. Ocultar/Mostrar los segmentos (texto, imagen, a/v) vinculados a los códigos colapsados. Hide/Show the segments (text, image, A/V) linked to the collapsed codes
        for item in self.scene().items():
            if type(item).__name__ in ("FreeTextGraphicsItem", "PixmapGraphicsItem", "AVGraphicsItem"):
                if hasattr(item, 'code_or_cat') and item.code_or_cat is not None:
                    if item.code_or_cat.get('cid') in child_cids:
                        if self.is_collapsed:
                            item.hide()
                        else:
                            item.show()

        # 4. Refrescar las líneas (Ocultar las que queden sueltas). Refresh lines (Hide any loose ones)
        for item in self.scene().items():
            if type(item).__name__ in ("LinkGraphicsItem", "FreeLineGraphicsItem"):
                if hasattr(item, 'from_widget') and hasattr(item, 'to_widget'):
                    if not item.from_widget.isVisible() or not item.to_widget.isVisible():
                        item.hide()
                    else:
                        item.show()
        self.scene().update()

    def case_media(self, ):
        """ Display all coded text and media for this code.
        Codings come from ALL files and ALL coders. """

        DialogCodeInAllFiles(self.app, self.code_or_cat, "Case")

    def coded_media(self, ):
        """ Display all coded media for this code.
        Coded media comes from ALL files and current coder.
        """

        DialogCodeInAllFiles(self.app, self.code_or_cat)


class LinkGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Takes the coordinate from the two TextGraphicsItems. """

    def __init__(self, from_widget, to_widget, line_width=2, line_type="solid",
                 color="gray", isvisible=True, label=""):
        """ Links codes and categories. Called when codes or categories of categories are inserted.
        Args:
            from_widget  : TextGraphicsItem
            to_widget : TextGraphicsItem
            line_width : Real
            line_type : String
            color : String
            isvisible : boolean
            label : String  allow connections (edges) to show analytical information (e.g., frequencies).
        """

        super(LinkGraphicsItem, self).__init__(None)
        self.app = from_widget.app
        self.from_widget = from_widget
        self.to_widget = to_widget
        self.text = f"{from_widget.text} - {to_widget.text}"
        self.line_width = line_width
        # Cannot select or drag line.
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.RightButton)
        self.color = color
        self.line_type = QtCore.Qt.PenStyle.SolidLine
        if line_type == "dotted":
            self.line_type = QtCore.Qt.PenStyle.DotLine
        # persisted in v17 (gr_cdct_line_item.arrow_mode). Hierarchy links stay
        # arrow-less by default; the loader may assign it after construction.
        self.arrow_mode = "none"
        self._label_bg = None  # white backing rect managed by position_line_label()
        self.calculate_points_and_draw()
        if not isvisible:
            self.hide()
        # relation label (v17): top-level text item managed by _create_label_item
        self.label = str(label)
        self.text_item = None
        if self.label:
            self._create_label_item()
        self.redraw()

    # shared implementation with FreeLineGraphicsItem (build_line_label)
    def _create_label_item(self, label=None):
        return build_line_label(self, label)

    def itemChange(self, change, value):
        sync_line_label_on_item_change(self, change, value)
        return super().itemChange(change, value)

    def __repr__(self):
        txt = f"LinkGraphicsItem From:{self.from_widget} To:{self.to_widget} Txt:{self.text}\n"
        txt += f"Color:{self.color} Width:{self.line_width}"
        return txt

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        # Sub-menú de grosor y estilo de línea. Submenu for line thickness and style
        line_menu = menu.addMenu(_('Line style'))
        width1_action = line_menu.addAction(_('Thin (1px)'))
        width2_action = line_menu.addAction(_('Normal (2px)'))
        width4_action = line_menu.addAction(_('Thick (4px)'))
        width6_action = line_menu.addAction(_('Extra thick (6px)'))
        line_menu.addSeparator()
        dotted_action = line_menu.addAction(_('Dotted'))
        solid_action = line_menu.addAction(_('Solid'))
        # Sub-menú de color. Color submenu
        color_menu = menu.addMenu(_('Line color'))
        red_action = color_menu.addAction(_('Red'))
        yellow_action = color_menu.addAction(_('Yellow'))
        green_action = color_menu.addAction(_('Green'))
        blue_action = color_menu.addAction(_('Blue'))
        cyan_action = color_menu.addAction(_('Cyan'))
        magenta_action = color_menu.addAction(_('Magenta'))
        orange_action = color_menu.addAction(_("Orange"))
        gray_action = color_menu.addAction(_("Gray"))
        menu.addSeparator()
        hide_action = menu.addAction(_('Hide'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        # snapshot before style changes so they are undoable (3-level stack)
        if action != hide_action:
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
        # Grosor. Thickness
        if action == width1_action:
            self.line_width = 1
        if action == width2_action:
            self.line_width = 2
        if action == width4_action:
            self.line_width = 4
        if action == width6_action:
            self.line_width = 6
        # Estilo. Style
        if action == dotted_action:
            self.line_type = QtCore.Qt.PenStyle.DotLine
        if action == solid_action:
            self.line_type = QtCore.Qt.PenStyle.SolidLine
        # Color
        if action == red_action:
            self.color = "red"
        if action == yellow_action:
            self.color = "yellow"
        if action == green_action:
            self.color = "green"
        if action == blue_action:
            self.color = "blue"
        if action == orange_action:
            self.color = "orange"
        if action == cyan_action:
            self.color = "cyan"
        if action == magenta_action:
            self.color = "magenta"
        if action == gray_action:
            self.color = "gray"
        if action == hide_action:
            ui_confirm = DialogConfirmDelete(self.app, _("Hide this line?"))
            if not ui_confirm.exec():
                return
            # snapshot after confirmation so Hide is undoable
            scene = self.scene()
            if scene is not None and getattr(scene, 'parent', None) is not None:
                if hasattr(scene.parent, '_save_undo_state'):
                    scene.parent._save_undo_state()
            self.hide()
        self.redraw()

    def redraw(self):
        """ Called from mouse move and release events. """

        self.calculate_points_and_draw()

    def calculate_points_and_draw(self):
        """ Cálculo fluido de intersección perimetral. Smooth calculation of the perimeter intersection """

        c1 = self.from_widget.sceneBoundingRect().center()
        c2 = self.to_widget.sceneBoundingRect().center()

        # Enviar la línea detrás de los nodos visualmente. Send the line behind the nodes visually
        self.setZValue(-1)

        is_ellipse_from = getattr(self.from_widget, 'is_ellipse', False)
        is_ellipse_to = getattr(self.to_widget, 'is_ellipse', False)

        rect1 = self.from_widget.sceneBoundingRect()
        rect2 = self.to_widget.sceneBoundingRect()

        # the former inner get_edge_point() (and its local "import math")
        # was hoisted to the module-level compute_edge_point helper shared with
        # FreeLineGraphicsItem, so both line classes use one geometry source.
        if rect1.intersects(rect2):
            p1 = c1
            p2 = c2
        else:
            p1 = compute_edge_point(c1, c2, rect1, is_ellipse_from)
            p2 = compute_edge_point(c2, c1, rect2, is_ellipse_to)

        color_obj = safe_color(self.color)  # tolerant color lookup
        self.setPen(QtGui.QPen(color_obj, self.line_width, self.line_type))
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())

        # label centring replaced by the shared anti-collision placer
        # (adds the white backing rect and slides along the line to dodge nodes).
        position_line_label(self, p1, p2)
