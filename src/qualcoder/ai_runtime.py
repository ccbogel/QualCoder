"""Background loading support for the optional AI runtime."""

import logging
import traceback
from typing import Any

from PyQt6 import QtCore

from .helpers import Message

logger = logging.getLogger(__name__)

AI_UNLOADED = "unloaded"
AI_DISABLED = "disabled"
AI_LOADING = "loading"
AI_INITIALIZING = "initializing"
AI_READY = "ready"
AI_FAILED = "failed"


class AiImportThread(QtCore.QThread):
    """Import expensive AI modules without blocking the GUI event loop."""

    loaded = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal(str)

    def run(self) -> None:
        """Load expensive AI dependencies in this worker thread."""

        try:
            from . import ai_llm

            ai_llm.load_ai_runtime_dependencies()
        except Exception:
            error_text = traceback.format_exc()
            logger.exception("Could not load the AI runtime")
            self.failed.emit(error_text)
            return
        self.loaded.emit()


def ai_runtime_ready(app: Any) -> bool:
    """Return whether the application's AI runtime can be used."""

    return getattr(app, "ai_runtime_state", AI_UNLOADED) == AI_READY


def show_ai_not_ready(app: Any, title: str = "AI") -> None:
    """Explain why the AI cannot handle the requested action yet."""

    get_ai_status = getattr(app, "get_ai_status", None)
    status = (
        get_ai_status()
        if callable(get_ai_status)
        else getattr(app, "ai_runtime_state", AI_UNLOADED)
    )
    if status == AI_FAILED:
        text = _("The AI components could not be loaded. Please restart QualCoder or check the log for details.")
    elif status == AI_DISABLED:
        text = _("The AI is disabled. Enable it in the AI Setup Wizard or AI Settings.")
    elif status == "busy":
        text = _("The AI is busy. Please wait a moment and retry.")
    elif status in ("no data", "reading data"):
        text = _("The AI is still preparing the project data. Please retry in a moment.")
    else:
        text = _("The AI components are still loading in the background. Please retry in a moment.")
    Message(app, title, text, "Information").exec()


def show_ai_runtime_not_ready(app: Any, title: str = "AI") -> None:
    """Compatibility wrapper for callers that manage runtime loading."""

    show_ai_not_ready(app, title)


def ensure_ai_loaded(app: Any, title: str = "AI") -> bool:
    """Return whether AI-dependent UI may be used, otherwise explain why."""

    status = app.get_ai_status()
    if status not in (AI_UNLOADED, AI_LOADING, AI_INITIALIZING, AI_FAILED, AI_DISABLED):
        return True
    show_ai_not_ready(app, title)
    return False


def ensure_ai_ready(app: Any, title: str = "AI") -> bool:
    """Return whether the AI can accept a request, otherwise explain why."""

    if app.get_ai_status() == AI_READY:
        return True
    show_ai_not_ready(app, title)
    return False
