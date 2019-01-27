# -*- coding: utf-8 -*-

'''
Copyright (c) 2019 Colin Curtain

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

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
'''

from PyQt5 import QtWidgets
import os
import sys
from GUI.ui_dialog_information import Ui_Dialog_information
import logging
import traceback

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error("Uncaught exception:\n" + text)
    QtWidgets.QMessageBox.critical(None, 'Uncaught Exception ', text)


class DialogInformation(QtWidgets.QDialog):
    """
    Dialog to display details information PyQDA development, version and license.
    """

    title = ""
    text = ""
    #Dialog_information = None

    def __init__(self, title, filename="", parent=None):
        ''' Display information text in dialog.
        If no filename is given, open a blank dialog to be populated later '''

        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_information()
        self.ui.setupUi(self)
        self.setWindowTitle(title)
        if filename != "":
            scriptdir = os.path.dirname(os.path.abspath(__file__))
            htmlFile = os.path.join(scriptdir, filename)
            try:
                with open(htmlFile, 'r') as f:
                    self.text = f.read()
                self.ui.textEdit.setHtml(self.text)
            except Exception as e:
                print(e)
                self.text = "Cannot open file."

    def setHtml(self, html):
        ''' This menthod is used to populate the textEdit.
        Usually called from a View_graph TextGraphicsItem via a context menu '''

        self.text = html
        self.ui.textEdit.setHtml(self.text)

    def accepted(self):
        ''' Accepted button overridden method '''
        self.information = self.ui.textEdit.toPlainText()
        self.ui.Dialog_information.accept()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogInformation("a title", "a filename")
    ui.show()
    sys.exit(app.exec_())

