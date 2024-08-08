# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

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

Author: Kai Dröge (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import sys
import traceback
import logging
from PyQt6 import QtCore, QtGui, QtWidgets
from .GUI.ui_error_dlg import Ui_ErrorDlg

logger = logging.getLogger(__name__)

class ErrorDlg(QtWidgets.QDialog):
    """Shows error dialog with traceback."""

    def __init__(self, msg, tb):
        super(ErrorDlg, self).__init__(parent=None)
        self.ui = Ui_ErrorDlg()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("* {font-size: 12pt}")
        self.setWindowIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical))
        self.ui.label_icon.setPixmap(self.windowIcon().pixmap(64, 64))
        # Add a copy button
        self.copyButton = QtWidgets.QPushButton(_('Copy'))
        self.copyButton.setToolTip(_('Copy error message and traceback to the clipboard.'))
        self.copyButton.clicked.connect(self.on_copy_clicked)
        self.ui.buttonBox.addButton(self.copyButton, QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        
        self.ui.label_error_message.setText(msg)
        self.ui.plainTextEdit.setPlainText(f'{tb}\n{msg}')
        
    def on_copy_clicked(self):
        err_msg = self.ui.plainTextEdit.toPlainText()
        clipboard = QtGui.QGuiApplication.clipboard()
        clipboard.setText(err_msg)
def show_error_dlg(msg, tb):
    try:
        error_dlg = ErrorDlg(msg, tb)
        error_dlg.exec()
    except Exception as e:
        print(f"Failed to show error dialog: {e}")
        mb = QtWidgets.QMessageBox()
        mb.setStyleSheet("* {font-size: 12pt}")
        mb.setWindowTitle(_('Exception handler'))
        mb.setText(f"Failed to show error dialog: \n{e}")
        mb.exec()
        
class UncaughtHook(QtCore.QObject):
    """Inspired by Tim Lehr:
    https://timlehr.com/2018/01/python-exception-hooks-with-qt-message-box/index.html
    """
    _exception_caught = QtCore.pyqtSignal(object, object)

    def __init__(self, *args, **kwargs):
        super(UncaughtHook, self).__init__(*args, **kwargs)

        # this registers the exception_hook() function as hook with the Python interpreter
        sys.excepthook = self.exception_hook

        # connect signal to execute the message box function always on main thread
        self._exception_caught.connect(show_error_dlg)

    def exception_hook(self, exception_type, value, tb_obj):
        """Function handling uncaught exceptions.
        It is triggered each time an uncaught exception occurs. 
        """
        if issubclass(exception_type, KeyboardInterrupt):
            # ignore keyboard interrupt to support console applications
            sys.__excepthook__(exception_type, value, tb_obj)
        else:
            msg = exception_type.__name__ + ': ' + str(value)
            tb = '\n'.join(traceback.format_tb(tb_obj))
            logger.error(_("Uncaught exception: ") + msg + '\n' + tb)

            # trigger message box show
            self._exception_caught.emit(msg, tb)