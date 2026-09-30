from types import SimpleNamespace

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from qualcoder.code_tree import CodeTreeController
from qualcoder.code_text import DialogCodeText


_qt_app = None


def _controller():
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
    controller = CodeTreeController(app, tree, host)
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
    controller = CodeTreeController(app, tree, host)
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