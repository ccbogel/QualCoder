import sys
sys.path.insert(0, 'src')
import pytest
from PyQt6 import QtCore, QtGui, QtWidgets
from qualcoder.helpers import setup_search_shortcuts


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    yield app


def test_enter_calls_next_callback(qapp):
    line_edit = QtWidgets.QLineEdit()
    called = []

    def on_next():
        called.append("next")

    def on_prev():
        called.append("prev")

    setup_search_shortcuts(line_edit, next_callback=on_next, prev_callback=on_prev)

    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(line_edit, ev)

    assert called == ["next"]


def test_shift_enter_calls_prev_callback(qapp):
    line_edit = QtWidgets.QLineEdit()
    called = []

    def on_next():
        called.append("next")

    def on_prev():
        called.append("prev")

    setup_search_shortcuts(line_edit, next_callback=on_next, prev_callback=on_prev)

    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
    QtWidgets.QApplication.sendEvent(line_edit, ev)

    assert called == ["prev"]


def test_shift_enter_without_prev_callback_is_noop(qapp):
    line_edit = QtWidgets.QLineEdit()
    called = []

    def on_next():
        called.append("next")

    setup_search_shortcuts(line_edit, next_callback=on_next, prev_callback=None)

    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
    handled = QtWidgets.QApplication.sendEvent(line_edit, ev)

    assert handled is True
    assert called == []


def test_ctrl_f_in_line_edit_selects_all(qapp):
    line_edit = QtWidgets.QLineEdit()
    line_edit.setText("existing search query")
    setup_search_shortcuts(line_edit)

    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_F, QtCore.Qt.KeyboardModifier.ControlModifier)
    QtWidgets.QApplication.sendEvent(line_edit, ev)

    assert line_edit.selectedText() == "existing search query"


def test_parent_window_find_shortcut_focuses_and_selects_all(qapp):
    window = QtWidgets.QWidget()
    other_widget = QtWidgets.QLineEdit(parent=window)
    line_edit = QtWidgets.QLineEdit(parent=window)
    line_edit.setText("test query")
    window.show()
    QtWidgets.QApplication.setActiveWindow(window)
    qapp.processEvents()

    setup_search_shortcuts(line_edit, parent_widget=window)

    other_widget.setFocus()
    qapp.processEvents()
    assert line_edit.hasFocus() is False

    # Trigger Ctrl+F shortcut
    shortcut = getattr(line_edit, "_find_shortcut", None)
    assert shortcut is not None
    shortcut.activated.emit()
    qapp.processEvents()

    assert line_edit.hasFocus() is True
    assert line_edit.selectedText() == "test query"
    window.close()


def test_other_keys_pass_through(qapp):
    line_edit = QtWidgets.QLineEdit()
    setup_search_shortcuts(line_edit)

    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.NoModifier, "a")
    QtWidgets.QApplication.sendEvent(line_edit, ev)

    assert line_edit.text() == "a"


def test_return_pressed_signal_not_fired_when_handled(qapp):
    line_edit = QtWidgets.QLineEdit()
    signal_fired = []
    line_edit.returnPressed.connect(lambda: signal_fired.append(True))

    called = []
    setup_search_shortcuts(line_edit, next_callback=lambda: called.append("next"))

    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(line_edit, ev)

    assert called == ["next"]
    assert signal_fired == []
