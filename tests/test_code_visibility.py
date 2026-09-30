from types import SimpleNamespace

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

import qualcoder.code_text as code_text_module
from qualcoder.code_tree import CodeTreeController
from qualcoder.code_text import DialogCodeText


_qt_app = None


def _controller(visibility_enabled=True):
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
    tree = QtWidgets.QTreeWidget()
    controller = CodeTreeController(
        app, tree, host, visibility_enabled=visibility_enabled)
    controller.fill_tree()
    return app, tree, controller


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


def test_alt_click_solos_code_and_second_click_restores_exact_visibility(monkeypatch):
    app, tree, controller = _controller()
    code_item = tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    monkeypatch.setattr(
        QtWidgets.QApplication,
        "keyboardModifiers",
        staticmethod(lambda: Qt.KeyboardModifier.AltModifier),
    )

    controller.handle_item_clicked(code_item, controller.COL_VIS)
    assert app.hidden_cids == {2}
    assert app.pre_solo_hidden_cids == set()

    controller.handle_item_clicked(code_item, controller.COL_VIS)
    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids is None


def test_solo_restore_survives_controller_recreation(monkeypatch):
    app, _tree, controller = _controller()
    alpha_item = controller.tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    monkeypatch.setattr(
        QtWidgets.QApplication,
        "keyboardModifiers",
        staticmethod(lambda: Qt.KeyboardModifier.AltModifier),
    )

    controller.handle_item_clicked(alpha_item, controller.COL_VIS)
    assert app.hidden_cids == {2}

    reopened_tree = QtWidgets.QTreeWidget()
    reopened_controller = CodeTreeController(
        app, reopened_tree, controller.host, visibility_enabled=True)
    reopened_controller.fill_tree()
    reopened_alpha = reopened_tree.findItems(
        "Alpha", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    reopened_controller.handle_item_clicked(reopened_alpha, reopened_controller.COL_VIS)

    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids is None
    assert app.solo_visibility_target is None


def test_alt_click_solos_category_and_switches_target(monkeypatch):
    app, tree, controller = _controller()
    category_item = tree.findItems(
        "Group", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    beta_item = tree.findItems(
        "Beta", QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive, 1)[0]
    monkeypatch.setattr(
        QtWidgets.QApplication,
        "keyboardModifiers",
        staticmethod(lambda: Qt.KeyboardModifier.ControlModifier),
    )

    controller.handle_item_clicked(category_item, controller.COL_VIS)
    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids == set()

    controller.handle_item_clicked(beta_item, controller.COL_VIS)
    assert app.hidden_cids == {1}
    assert app.pre_solo_hidden_cids == set()

    controller.handle_item_clicked(beta_item, controller.COL_VIS)
    assert app.hidden_cids == set()
    assert app.pre_solo_hidden_cids is None


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