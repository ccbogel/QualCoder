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

Author: Kai Droege (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder.org/

Async worker for lengthy AI functions that would otherwise block the UI.
Adopted from https://www.pythonguis.com/tutorials/multithreading-pyqt-applications-qthreadpool/ 
"""

import logging
import sys
from typing import Callable, Optional

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, QThread, Qt, pyqtSignal, pyqtSlot


logger = logging.getLogger(__name__)


class AIException(Exception):
    """Exception raised for AI-related errors"""
    def __init__(self, message='Unspecified AI Exception'):
        self.message = message
        super().__init__(self.message)


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    progress
        int indicating % progress

    confirmation
        object containing a request that must be answered by the GUI thread
        
    streaming
        str containing the current streaming response particle coming from the LLM
    """

    finished = pyqtSignal()
    error = pyqtSignal(object, object, object)
    result = pyqtSignal(object)
    progress = pyqtSignal(str)
    streaming = pyqtSignal(str)
    confirmation = pyqtSignal(object)


class GuiThreadRelay(QObject):
    """Deliver worker messages and errors safely in the Qt application thread."""

    message = pyqtSignal(str)
    error = pyqtSignal(object, object, object)

    def __init__(self, message_handler: Callable[[str], None],
                 error_handler: Optional[Callable[[object, object, object], None]] = None,
                 parent: Optional[QObject] = None):
        """Create a queued relay for callbacks that may touch GUI objects.

        Args:
            message_handler: Callback that displays a message in the GUI.
            error_handler: Optional callback that displays a worker error.
            parent: Optional QObject owner.
        """

        super().__init__(parent)
        self._message_handler = message_handler
        self._error_handler = error_handler
        self.message.connect(
            self._deliver_message,
            type=Qt.ConnectionType.QueuedConnection,
        )
        self.error.connect(
            self._deliver_error,
            type=Qt.ConnectionType.QueuedConnection,
        )

    @staticmethod
    def _in_application_thread() -> bool:
        app = QCoreApplication.instance()
        return app is None or QThread.currentThread() == app.thread()

    @pyqtSlot(str)
    def _deliver_message(self, message: str) -> None:
        if not self._in_application_thread():
            logger.critical("Blocked a GUI message callback outside the Qt application thread")
            return
        self._message_handler(message)

    @pyqtSlot(object, object, object)
    def _deliver_error(self, exception_type: object, value: object,
                       traceback_obj: object) -> None:
        if self._error_handler is None:
            return
        if not self._in_application_thread():
            logger.critical("Blocked a GUI error callback outside the Qt application thread")
            return
        self._error_handler(exception_type, value, traceback_obj)

    @pyqtSlot(str)
    def post_message(self, message: str) -> None:
        """Queue a GUI message from any thread."""

        self.message.emit(message)

    @pyqtSlot(object, object, object)
    def post_error(self, exception_type: object, value: object,
                   traceback_obj: object) -> None:
        """Queue a GUI error callback from any thread."""

        self.error.emit(exception_type, value, traceback_obj)


class Worker(QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function
    """

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
        # Pass the signals to the function
        self.kwargs['signals'] = self.signals

    @pyqtSlot()
    def run(self):
        """ Initialise the runner function with passed args, kwargs. """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as err:
            exctype, value = sys.exc_info()[:2]
            if not sip.isdeleted(self.signals):
                self.signals.error.emit(exctype, value, err.__traceback__)
            return
        finally:
            if not sip.isdeleted(self.signals):
                self.signals.finished.emit()  # Done
        
        if not sip.isdeleted(self.signals):
            self.signals.result.emit(result)  # Return the result of the processing
