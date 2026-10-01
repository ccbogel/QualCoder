from types import SimpleNamespace
import sqlite3
import datetime

import pytest

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

import qualcoder.code_text as code_text_module
import qualcoder.code_tree as code_tree_module
from qualcoder.code_tree import CodeTreeController
from qualcoder.code_text import DialogCodeText
from qualcoder.color_selector import colors, show_codes_of_colour_range


_qt_app = None


@pytest.fixture(autouse=True)
def _qt_widgets():
    global _qt_app
    _qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield
    for widget in _qt_app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)


def _controller(visibility_enabled=True, tree_type=QtWidgets.QTreeWidget):
    global _qt_app
    _qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = SimpleNamespace(
        hidden_cids=set(),
        pre_solo_hidden_cids=None,
        collapsed_categories=set(),
        settings={"showids": True, "fontsize": 10},
    )
    host = SimpleNamespace(
        codes=[
            {"cid": 1, "name": "Alpha", "memo": "", "color": "#ff0000", "catid": 10},
            {"cid": 2, "name": "Beta", "memo": "", "color": "#00ff00", "catid": 10},
        ],
        categories=[
            {"catid": 10, "name": "Group", "memo": "", "supercatid": None},
        ],
        parent_textEdit=None,
    )
    tree = tree_type()
    controller = CodeTreeController(
        app, tree, host, visibility_enabled=visibility_enabled)
    controller.fill_tree()
    return app, tree, controller


def _cell_position(tree, item, column):
    tree.resize(640, 400)
    tree.show()
    QtWidgets.QApplication.processEvents()
    return QtCore.QPoint(
        tree.header().sectionViewportPosition(column) + tree.columnWidth(column) // 2,
        tree.visualItemRect(item).center().y(),
    )


def _click_visibility(controller, item, modifiers=Qt.KeyboardModifier.NoModifier):
    position = _cell_position(controller.tree, item, controller.COL_VIS)
    QTest.mouseClick(controller.tree.viewport(), Qt.MouseButton.LeftButton, modifiers, position)


def test_code_visibility_controller_uses_column_zero_and_cascades():
    app, tree, controller = _controller()

    assert tree.columnCount() == 5
    assert tree.treePosition() == 1
    assert tree.columnWidth(0) == 28
    assert controller.is_code_visible(1)

    code_item = tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    controller.toggle_code_visibility(1)
    assert app.hidden_cids == {1}
    assert not controller.is_code_visible(1)
    assert code_item.icon(0).isNull() is False

    controller.toggle_category_visibility(10)
    assert app.hidden_cids == {1, 2}

    controller.toggle_all_visibility()
    assert app.hidden_cids == set()
    controller.toggle_all_visibility()
    assert app.hidden_cids == {1, 2}


def test_shared_controller_preserves_legacy_columns_without_visibility():
    _app, tree, controller = _controller(visibility_enabled=False)

    assert tree.columnCount() == 4
    assert tree.treePosition() == 0
    code_item = tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 0)[0]
    assert code_item.text(0) == "Alpha"
    assert code_item.text(1) == "cid:1"
    assert controller.COL_VIS is None


@pytest.mark.parametrize("visibility_enabled", [False, True])
@pytest.mark.parametrize("name,item_id,table,key", [
    ("Alpha", "cid:1", "code_name", "cid"),
    ("Group", "catid:10", "code_cat", "catid"),
])
def test_memo_edit_preserves_identifier(monkeypatch, visibility_enabled, name, item_id, table, key):
    app, tree, controller = _controller(visibility_enabled)
    app.conn = sqlite3.connect(":memory:")
    app.conn.execute(f"create table {table} ({key} integer, memo text)")
    app.conn.execute(f"insert into {table} values (?, '')", (int(item_id.split(':')[1]),))
    controller.host.parent_textEdit = QtWidgets.QTextEdit()
    item = tree.findItems(
        name, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, controller.COL_NAME)[0]
    memo_dialog = SimpleNamespace(memo="memo text", exec=lambda: None)
    monkeypatch.setattr(code_tree_module, "DialogMemo", lambda *_args, **_kwargs: memo_dialog)
    try:
        for memo in ("memo text", "memo text", ""):
            memo_dialog.memo = memo
            controller.add_edit_cat_or_code_memo(item)
            assert item.text(controller.COL_ID) == item_id
            assert item.text(controller.COL_MEMO) == ("Memo" if memo else "")
            assert app.conn.execute(f"select memo from {table}").fetchone()[0] == memo
    finally:
        app.conn.close()


@pytest.mark.parametrize("visibility_enabled", [False, True])
def test_colour_filter_uses_identifier_column_and_keeps_matching_ancestors(visibility_enabled):
    app, tree, controller = _controller(visibility_enabled)
    controller.host.codes[0]["color"] = colors[0]
    controller.host.codes[1]["color"] = colors[1]
    controller.host.codes.append({
        "cid": 3, "name": "Child", "memo": "", "color": colors[0],
        "catid": None, "supercid": 2,
    })
    controller.host.codes.append({
        "cid": 4, "name": "Other", "memo": "", "color": colors[1], "catid": 10,
    })
    controller.fill_tree()
    app.hidden_cids = {1}
    column_option = {"id_column": controller.COL_ID} if visibility_enabled else {}
    show_codes_of_colour_range(app, tree, controller.codes, {"min": 0, "max": 1}, **column_option)
    for name, hidden in (("Alpha", False), ("Beta", False), ("Child", False), ("Other", True)):
        item = tree.findItems(
            name, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, controller.COL_NAME)[0]
        assert item.isHidden() is hidden
    assert app.hidden_cids == {1}


def test_category_visibility_cascades_through_nested_categories_and_subcodes():
    global _qt_app
    _qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = SimpleNamespace(
        hidden_cids=set(),
        pre_solo_hidden_cids=None,
        collapsed_categories=set(),
        settings={"showids": True, "fontsize": 10},
    )
    host = SimpleNamespace(
        codes=[
            {"cid": 1, "name": "Parent", "memo": "", "color": "#ff0000", "catid": 10},
            {"cid": 2, "name": "Child", "memo": "", "color": "#00ff00", "catid": None, "supercid": 1},
            {"cid": 3, "name": "Nested", "memo": "", "color": "#0000ff", "catid": 11},
        ],
        categories=[
            {"catid": 10, "name": "Root", "memo": "", "supercatid": None},
            {"catid": 11, "name": "Branch", "memo": "", "supercatid": 10},
        ],
        parent_textEdit=None,
    )
    tree = QtWidgets.QTreeWidget()
    controller = CodeTreeController(app, tree, host, visibility_enabled=True)
    controller.fill_tree()
    root_item = tree.findItems(
        "Root", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    root_icon = root_item.icon(0).cacheKey()
    assert root_item.isExpanded()

    assert controller.category_visibility_state(10) == "visible"
    controller.toggle_category_visibility(10)
    assert app.hidden_cids == {1, 2, 3}
    assert controller.category_visibility_state(10) == "hidden"
    assert controller.category_visibility_state(11) == "hidden"
    hidden_icon = root_item.icon(0).cacheKey()
    assert hidden_icon != root_icon
    assert root_item.isExpanded()

    controller.toggle_category_visibility(10)
    assert app.hidden_cids == set()
    assert controller.category_visibility_state(10) == "visible"
    assert root_item.icon(0).cacheKey() == root_icon

    controller.toggle_code_visibility(1)
    assert controller.category_visibility_state(10) == "partial"
    partial_icon = root_item.icon(0).cacheKey()
    assert partial_icon not in {root_icon, hidden_icon}
    controller.toggle_category_visibility(10)
    assert app.hidden_cids == {1, 2, 3}
    assert controller.category_visibility_state(10) == "hidden"
    assert root_item.icon(0).cacheKey() == hidden_icon
    assert root_item.isExpanded()


def test_ctrl_click_solos_code_and_second_click_restores_exact_visibility():
    app, tree, controller = _controller()
    code_item = tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    _click_visibility(controller, code_item, Qt.KeyboardModifier.ControlModifier)
    assert app.hidden_cids == {2}
    assert app.pre_solo_hidden_cids == set()

    _click_visibility(controller, code_item, Qt.KeyboardModifier.ControlModifier)
    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids is None


def test_solo_restore_survives_controller_recreation():
    app, _tree, controller = _controller()
    alpha_item = controller.tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    _click_visibility(controller, alpha_item, Qt.KeyboardModifier.ControlModifier)
    assert app.hidden_cids == {2}

    reopened_tree = QtWidgets.QTreeWidget()
    reopened_controller = CodeTreeController(
        app, reopened_tree, controller.host, visibility_enabled=True)
    reopened_controller.fill_tree()
    reopened_alpha = reopened_tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    _click_visibility(reopened_controller, reopened_alpha, Qt.KeyboardModifier.ControlModifier)

    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids is None
    assert app.solo_visibility_target is None


def test_ctrl_click_solos_category_and_switches_target():
    app, tree, controller = _controller()
    category_item = tree.findItems(
        "Group", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    beta_item = tree.findItems(
        "Beta", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    _click_visibility(controller, category_item, Qt.KeyboardModifier.ControlModifier)
    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids == set()

    _click_visibility(controller, beta_item, Qt.KeyboardModifier.ControlModifier)
    assert app.hidden_cids == {1}
    assert app.pre_solo_hidden_cids == set()

    _click_visibility(controller, beta_item, Qt.KeyboardModifier.ControlModifier)
    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids is None


@pytest.mark.parametrize("modifiers", [Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier])
@pytest.mark.parametrize("movement", [0, 3, 12])
def test_visibility_gesture_preserves_selection_and_does_not_mark(modifiers, movement):
    app, tree, controller = _controller()
    tree.setDragEnabled(True)
    tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
    tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
    alpha = tree.findItems("Alpha", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    beta = tree.findItems("Beta", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    tree.setCurrentItem(beta)
    pressed = []
    changed = []
    tree.itemPressed.connect(lambda *_args: pressed.append(True))
    controller.code_visibility_changed.connect(lambda: changed.append(True))
    position = _cell_position(tree, alpha, controller.COL_VIS)
    selected = tree.selectedItems()
    position.setX(2)
    QTest.mousePress(tree.viewport(), Qt.MouseButton.LeftButton, modifiers, position)
    destination = position + QtCore.QPoint(movement, 0)
    QTest.mouseMove(tree.viewport(), destination)
    QTest.mouseRelease(tree.viewport(), Qt.MouseButton.LeftButton, modifiers, destination)
    assert pressed == []
    assert tree.currentItem() is beta
    assert tree.selectedItems() == selected
    assert changed == [True]
    assert app.hidden_cids == ({2} if modifiers else {1})


def test_visibility_gesture_cancels_outside_cell_and_on_tree_rebuild():
    app, tree, controller = _controller()
    alpha = tree.findItems("Alpha", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    position = _cell_position(tree, alpha, controller.COL_VIS)
    QTest.mousePress(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    QTest.mouseRelease(tree.viewport(), Qt.MouseButton.LeftButton, pos=position + QtCore.QPoint(60, 0))
    assert app.hidden_cids == set()
    QTest.mousePress(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    controller.fill_tree()
    QTest.mouseRelease(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    assert app.hidden_cids == set()


def test_alt_visibility_click_is_not_solo():
    app, tree, controller = _controller()
    alpha = tree.findItems("Alpha", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    _click_visibility(controller, alpha, Qt.KeyboardModifier.AltModifier)
    assert app.hidden_cids == {1}
    assert app.pre_solo_hidden_cids is None


@pytest.mark.parametrize("column", [0, 1, 2, 3, 4])
def test_only_name_column_marks_selected_text(column):
    app, tree, controller = _controller()
    editor = QtWidgets.QPlainTextEdit()
    editor.setPlainText("selected text")
    editor.selectAll()
    marked = []
    host = SimpleNamespace(
        app=app, code_tree=controller, codes=controller.codes, code_rule=None,
        show_codes_like_filter="", show_codes_colour_filter="",
        ui=SimpleNamespace(
            treeWidget=tree, plainTextEdit=editor, label_code=QtWidgets.QLabel(),
            pushButton_show_codings_prev=QtWidgets.QPushButton(),
            pushButton_show_codings_next=QtWidgets.QPushButton(),
        ),
        mark=lambda: marked.append(True), highlight=lambda: None,
    )
    tree.itemPressed.connect(lambda item, pressed_column:
                            DialogCodeText.fill_code_label_with_selected_code(host, item, pressed_column))
    alpha = tree.findItems("Alpha", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    position = _cell_position(tree, alpha, column)
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    assert marked == ([True] if column == controller.COL_NAME else [])
    assert editor.textCursor().selectedText() == "selected text"


def test_header_and_context_menu_toggle_all_are_clear_first(monkeypatch):
    app, tree, controller = _controller()
    header = tree.headerItem()
    assert header.toolTip(controller.COL_VIS) == "Hide all codes"
    initial_icon = header.icon(controller.COL_VIS).cacheKey()

    controller.handle_header_clicked(controller.COL_VIS)
    assert app.hidden_cids == {1, 2}
    assert header.toolTip(controller.COL_VIS) == "Show all codes"
    assert header.icon(controller.COL_VIS).cacheKey() != initial_icon

    controller.handle_header_clicked(controller.COL_VIS)
    assert app.hidden_cids == set()

    selected_action = {}

    def fake_exec(menu, _position):
        selected_action["label"] = next(
            action.text() for action in menu.actions() if action.text() == "Hide all codes"
        )
        return next(action for action in menu.actions() if action.text() == "Hide all codes")

    monkeypatch.setattr(QtWidgets.QMenu, "exec", fake_exec)
    controller.tree_menu(tree.visualItemRect(tree.topLevelItem(0)).center())
    assert selected_action["label"] == "Hide all codes"
    assert app.hidden_cids == {1, 2}


@pytest.mark.parametrize("name,label", [
    ("Alpha", "Show only this code"), ("Group", "Show only this category"),
])
def test_context_menu_solos_clicked_target_and_restores_original_state(monkeypatch, name, label):
    app, tree, controller = _controller()
    target = tree.findItems(name, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    beta = tree.findItems("Beta", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    tree.setCurrentItem(beta)
    app.hidden_cids = {2}
    position = _cell_position(tree, target, controller.COL_VIS)
    chosen = [label]

    def choose_action(menu, _position):
        return next(action for action in menu.actions() if action.text() == chosen[0])

    monkeypatch.setattr(QtWidgets.QMenu, "exec", choose_action)
    controller.tree_menu(position)
    assert app.hidden_cids == ({2} if name == "Alpha" else set())
    assert app.pre_solo_hidden_cids == {2}
    chosen[0] = "Restore previous visibility"
    controller.tree_menu(_cell_position(tree, beta, controller.COL_VIS))
    assert app.hidden_cids == {2}
    assert app.pre_solo_hidden_cids is None
    assert app.solo_visibility_target is None


def test_legacy_context_menu_has_no_visibility_actions(monkeypatch):
    _app, tree, controller = _controller(False)
    actions = []
    monkeypatch.setattr(QtWidgets.QMenu, "exec", lambda menu, _position:
                        actions.extend(action.text() for action in menu.actions()))
    controller.tree_menu(QtCore.QPoint())
    assert not any("visibility" in action.lower() or "Show only" in action for action in actions)


def test_solo_switch_restores_state_before_first_solo():
    app, _tree, controller = _controller()
    app.hidden_cids = {1}
    controller.solo_visibility({1}, "cid:1")
    controller.solo_visibility({2}, "cid:2")
    controller.solo_visibility({2}, "cid:2")
    assert app.hidden_cids == {1}


def _mark_host(highlight_style, important):
    app, tree, controller = _controller()
    app.hidden_cids = {1}
    app.settings.update({"codername": "tester", "stylesheet": "light"})
    app.conn = sqlite3.connect(":memory:")
    app.conn.execute(
        "create table code_text (ctid integer primary key, cid integer, fid integer, "
        "seltext text, pos0 integer, pos1 integer, owner text, memo text, date text, important integer)")
    app.conn.execute("create table project (recently_used_codes text)")
    app.conn.execute("insert into project values ('')")

    class MarkEditor(QtWidgets.QPlainTextEdit):
        def keyPressEvent(self, event):
            DialogCodeText.keyPressEvent(host, event)

    editor = MarkEditor()
    editor.setPlainText("selected text")
    editor.selectAll()
    updates = []
    host = SimpleNamespace(
        app=app, code_tree=controller, codes=controller.codes, code_text=[], annotations=[],
        file_={"id": 1, "start": 0}, ai_search_message_shown=False, recent_codes=[],
        important=important, highlight_style=highlight_style, code_rule=None, edit_mode=False,
        overlap_timer=datetime.datetime.now(), overlaps_at_pos=[],
        show_codes_like_filter="", show_codes_colour_filter="",
        ui=SimpleNamespace(
            treeWidget=tree, plainTextEdit=editor, label_code=QtWidgets.QLabel(),
            pushButton_show_codings_prev=QtWidgets.QPushButton(),
            pushButton_show_codings_next=QtWidgets.QPushButton(),
            tabWidget=SimpleNamespace(currentIndex=lambda: 0),
        ),
        clear_edit_variables=lambda: None, fill_code_counts_in_tree=lambda: updates.append("count"),
        update_file_tooltip=lambda: None, _emit_project_table_changes=lambda tables: updates.append(tables),
        eventFilterTT=SimpleNamespace(set_codes_and_annotations=lambda *_args: updates.append(_args[1])),
        coding_margin=SimpleNamespace(update=lambda: updates.append("margin")),
        _code_label_contrast_color=lambda color: QtGui.QColor(color),
    )
    host.mark = lambda: DialogCodeText.mark(host)
    host._mark_incremental_refresh = lambda item: DialogCodeText._mark_incremental_refresh(host, item)
    host._apply_format_to_code_item = lambda item, codes: DialogCodeText._apply_format_to_code_item(host, item, codes)
    host._apply_overlap_underlines_for_code = lambda item: DialogCodeText._apply_overlap_underlines_for_code(host, item)
    host.apply_underline_to_overlaps = lambda: DialogCodeText.apply_underline_to_overlaps(host)
    host.highlight = lambda: DialogCodeText.highlight(host)
    return host, updates


@pytest.mark.parametrize("highlight_style", ["marker", "underline"])
@pytest.mark.parametrize("important", [False, True])
def test_hidden_incremental_refresh_preserves_visible_formatting(highlight_style, important):
    host, updates = _mark_host(highlight_style, important)
    try:
        visible = {"cid": 2, "ctid": 2, "pos0": 0, "pos1": 13, "important": 1, "memo": ""}
        hidden = {"cid": 1, "ctid": 1, "pos0": 0, "pos1": 13, "important": 1, "memo": "hidden memo"}
        host.code_text = [visible, hidden]
        host._apply_format_to_code_item(visible, {code["cid"]: code for code in host.codes})
        cursor = host.ui.plainTextEdit.textCursor()
        cursor.setPosition(3)
        before = cursor.charFormat()
        host._mark_incremental_refresh(hidden)
        assert cursor.charFormat() == before
        assert [visible] in updates
        assert "margin" in updates
    finally:
        host.app.conn.close()


@pytest.mark.parametrize("entry_point", ["mouse", "Q"])
@pytest.mark.parametrize("highlight_style", ["marker", "underline"])
@pytest.mark.parametrize("important", [False, True])
def test_hidden_mark_is_saved_without_highlight_then_can_be_revealed(entry_point, highlight_style, important):
    host, updates = _mark_host(highlight_style, important)
    tree = host.ui.treeWidget
    editor = host.ui.plainTextEdit
    alpha = tree.findItems("Alpha", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    tree.setCurrentItem(alpha)
    try:
        if entry_point == "mouse":
            tree.itemPressed.connect(lambda item, column:
                                    DialogCodeText.fill_code_label_with_selected_code(host, item, column))
            position = _cell_position(tree, alpha, host.code_tree.COL_NAME)
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
        else:
            editor.show()
            editor.activateWindow()
            editor.setFocus()
            QtWidgets.QApplication.processEvents()
            assert editor.hasFocus()
            QTest.keyClick(editor, Qt.Key.Key_Q)
        assert host.app.conn.execute("select cid, pos0, pos1 from code_text").fetchall() == [(1, 0, 13)]
        assert "count" in updates
        assert [] in updates
        cursor = editor.textCursor()
        cursor.setPosition(3)
        assert cursor.charFormat().background().style() == Qt.BrushStyle.NoBrush
        assert cursor.charFormat().underlineStyle() == QtGui.QTextCharFormat.UnderlineStyle.NoUnderline
        host.app.hidden_cids.clear()
        host.important = False
        host.highlight()
        if highlight_style == "marker":
            assert cursor.charFormat().background().color().name() == "#ff0000"
        else:
            assert cursor.charFormat().underlineStyle() == QtGui.QTextCharFormat.UnderlineStyle.DashUnderline
    finally:
        editor.close()
        tree.close()
        host.app.conn.close()


@pytest.mark.parametrize("column", [0, 1])
def test_visibility_filter_precedes_text_dialog_filter(column):
    host, updates = _mark_host("marker", False)
    tree = host.ui.treeWidget
    host.show_all_codes_in_text = lambda: updates.append("show all")

    class HostFilter(QtCore.QObject):
        def eventFilter(self, watched, event):
            return DialogCodeText.eventFilter(host, watched, event)

    host_filter = HostFilter(tree)
    tree.viewport().removeEventFilter(host.code_tree)
    tree.viewport().installEventFilter(host_filter)
    tree.viewport().installEventFilter(host.code_tree)
    tree.itemPressed.connect(lambda item, pressed_column:
                            DialogCodeText.fill_code_label_with_selected_code(host, item, pressed_column))
    alpha = tree.findItems("Alpha", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    position = _cell_position(tree, alpha, column)
    try:
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
        assert updates.count("show all") == (1 if column == 1 else 0)
        assert host.app.conn.execute("select count(*) from code_text").fetchone()[0] == (1 if column == 1 else 0)
        assert host.ui.plainTextEdit.textCursor().selectedText() == "selected text"
    finally:
        tree.viewport().removeEventFilter(host_filter)
        host.app.conn.close()


@pytest.mark.parametrize("column", [0, 1])
def test_visibility_gesture_does_not_start_drag_but_name_gesture_does(column):
    class DragTree(QtWidgets.QTreeWidget):
        drag_starts = 0

        def startDrag(self, supported_actions):
            self.drag_starts += 1

    _app, tree, controller = _controller(tree_type=DragTree)
    tree.setDragEnabled(True)
    tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
    alpha = tree.findItems("Alpha", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)[0]
    position = _cell_position(tree, alpha, column)
    QTest.mousePress(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    destination = position + QtCore.QPoint(QtWidgets.QApplication.startDragDistance() + 5, 0)
    event = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseMove, QtCore.QPointF(destination),
        QtCore.QPointF(tree.viewport().mapToGlobal(destination)),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(tree.viewport(), event)
    QTest.mouseRelease(tree.viewport(), Qt.MouseButton.LeftButton, pos=destination)
    assert tree.drag_starts == (1 if column == controller.COL_NAME else 0)


def test_in_text_action_candidates_exclude_hidden_codes():
    dialog = SimpleNamespace()
    dialog.app = SimpleNamespace(hidden_cids={2})
    dialog.file_ = {"start": 100}
    dialog.code_text = [
        {"cid": 1, "ctid": 11, "pos0": 105, "pos1": 120, "important": 1},
        {"cid": 2, "ctid": 12, "pos0": 105, "pos1": 120, "important": 1},
        {"cid": 3, "ctid": 13, "pos0": 105, "pos1": 120, "important": None},
    ]

    visible_code_text_at = DialogCodeText.visible_code_text_at
    assert [item["cid"] for item in visible_code_text_at(dialog, 10)] == [1, 3]
    assert [item["cid"] for item in visible_code_text_at(dialog, 10, important=1)] == [1]

    dialog.app.hidden_cids = {1, 2, 3}
    assert visible_code_text_at(dialog, 10) == []


def test_boundary_nudge_prefers_active_handle_target_without_prompt(monkeypatch):
    editor = QtWidgets.QPlainTextEdit()
    editor.setPlainText("overlapping text")
    cursor = editor.textCursor()
    cursor.setPosition(5)
    editor.setTextCursor(cursor)
    first = {"cid": 1, "ctid": 11, "pos0": 0, "pos1": 10}
    second = {"cid": 2, "ctid": 12, "pos0": 2, "pos1": 12}
    dialog = SimpleNamespace(
        ui=SimpleNamespace(plainTextEdit=editor),
        app=SimpleNamespace(hidden_cids=set()),
        file_={"start": 0},
        code_text=[first, second],
        edit_mode=False,
        code_resize_timer=__import__("datetime").datetime.now()
        - __import__("datetime").timedelta(seconds=1),
        last_resized_ctid=None,
        last_resized_time=__import__("datetime").datetime.min,
        active_handles=[SimpleNamespace(code_item=second)],
    )
    dialog.ui.treeWidget = SimpleNamespace(viewport=lambda: editor)
    nudged = []
    dialog.extend_right = lambda code: nudged.append(code)

    def fail_selection(*_args, **_kwargs):
        raise AssertionError("DialogSelectItems should not be opened")

    monkeypatch.setattr(code_text_module, "DialogSelectItems", fail_selection)
    event = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyPress,
        Qt.Key.Key_Right,
        Qt.KeyboardModifier.ShiftModifier,
    )

    assert DialogCodeText.eventFilter(dialog, editor, event) is True
    assert nudged == [second]


def test_boundary_nudge_refreshes_editor_margin_and_handle_coordinates():
    class FakeHandle:
        def __init__(self, is_start):
            self.is_start = is_start
            self.code_item = {"ctid": 11, "pos0": 0, "pos1": 5}
            self.positions = []

        def move(self, x, y):
            self.positions.append((x, y))

        def width(self):
            return 20

    code = {"ctid": 11, "cid": 1, "fid": 1, "pos0": 0, "pos1": 5}
    dialog = SimpleNamespace(
        app=SimpleNamespace(
            conn=SimpleNamespace(),
            delete_backup=True,
        ),
        ui=SimpleNamespace(plainTextEdit=QtWidgets.QPlainTextEdit()),
        file_={"start": 0},
        code_text=[code],
        active_handles=[FakeHandle(True), FakeHandle(False)],
    )
    dialog.ui.plainTextEdit.setPlainText("abcdef")
    dialog.get_coded_text_update_eventfilter_tooltips = lambda: setattr(
        dialog, "refreshed", True
    )
    dialog._emit_project_table_changes = lambda tables: setattr(dialog, "tables", tables)

    class Cursor:
        def __init__(self, position):
            self.position = position

        def setPosition(self, position):
            self.position = position

    dialog.ui.plainTextEdit.textCursor = lambda: Cursor(0)
    dialog.ui.plainTextEdit.cursorRect = lambda cursor: QtCore.QRect(cursor.position, 7, 1, 1)
    dialog.update_handle_positions = lambda: DialogCodeText.update_handle_positions(dialog)

    class CursorConnection:
        def cursor(self):
            return self

        def execute(self, *_args):
            return None

        def fetchone(self):
            return ("abcde",)

        def commit(self):
            return None

    connection = CursorConnection()
    dialog.app.conn.cursor = connection.cursor
    dialog.app.conn.commit = connection.commit
    DialogCodeText.extend_right(dialog, code)

    assert code["pos1"] == 6
    assert dialog.refreshed is True
    assert dialog.tables == ["code_text"]
    assert all(handle.code_item is code for handle in dialog.active_handles)
    assert all(handle.positions for handle in dialog.active_handles)