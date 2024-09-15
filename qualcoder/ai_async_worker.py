# -*- coding: utf-8 -*-

"""
Copyright (c) 2023 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Kai Droege (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/

Async worker for lengthy AI functions that would otherwise block the UI.
Adopted from https://www.pythonguis.com/tutorials/multithreading-pyqt-applications-qthreadpool/ 
"""

import sys
import traceback
try:
    import pydevd # for debugging
except:
    pass
from typing import Any
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6 import sip

class AIException(Exception):
    """Exception raised for AI-related errors"""
    def __init__(self, message='Unspecified AI Exception'):
        self.message = message
        super().__init__(self.message)

class WorkerSignals(QObject):
    '''
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

    '''
    finished = pyqtSignal()
    error = pyqtSignal(object, object, object)
    result = pyqtSignal(object)
    progress = pyqtSignal(str)
    streaming = pyqtSignal(str)


class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

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
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        try:
            pydevd.settrace(suspend=False) # enable debugger
        except:
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
