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

Async worker for lengthy AI functions that would otherwise block the UI.
Adopted from https://www.pythonguis.com/tutorials/multithreading-pyqt-applications-qthreadpool/ 
"""

import sys
import traceback  # TODO unused
try:
    import pydevd  # for debugging
except ModuleNotFoundError:
    pass
from typing import Any  # TODO unused
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot  # TODO QThreadPool not used
from PyQt6 import sip


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
        
    streaming
        str containing the current streaming response particle coming from the LLM
    """

    finished = pyqtSignal()
    error = pyqtSignal(object, object, object)
    result = pyqtSignal(object)
    progress = pyqtSignal(str)
    streaming = pyqtSignal(str)


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

        try:
            pydevd.settrace(suspend=False)  # enable debugger
        except NameError:
            pass 

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
