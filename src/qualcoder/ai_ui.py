"""Lightweight Qt helpers shared by AI views."""

from typing import Any

from PyQt6 import QtCore, QtGui
import qtawesome as qta


class AIChatSignalEmitter(QtCore.QObject):
    """Relay requests from coding views to the AI chat."""

    newTextChatSignal = QtCore.pyqtSignal(int, str, str, int, object)


# Construct the QObject on the GUI thread during normal application imports.
ai_chat_signal_emitter = AIChatSignalEmitter()


def code_analysis_icon(app: Any) -> QtGui.QIcon:
    return qta.icon('mdi6.tag-text-outline', color=app.highlight_color())


def topic_exploration_icon(app: Any) -> QtGui.QIcon:
    return qta.icon('mdi6.star-outline', color=app.highlight_color())


def search_icon(app: Any) -> QtGui.QIcon:
    return qta.icon('mdi6.magnify', color=app.highlight_color())


def text_analysis_icon(app: Any) -> QtGui.QIcon:
    return qta.icon('mdi6.text-box-outline', color=app.highlight_color())


def general_chat_icon(app: Any) -> QtGui.QIcon:
    return qta.icon('mdi6.chat-question-outline', color=app.highlight_color())


def prompt_scope_icon(app: Any) -> QtGui.QIcon:
    return qta.icon('mdi6.folder-open-outline', color=app.highlight_color())


def prompt_icon(app: Any) -> QtGui.QIcon:
    return qta.icon('mdi6.script-text-outline', color=app.highlight_color())
