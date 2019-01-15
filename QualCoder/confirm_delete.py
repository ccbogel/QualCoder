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
https://pypi.org/project/QualCoder
'''

from PyQt5 import QtWidgets
from GUI.ui_dialog_confirm_delete import Ui_Dialog_confirmDelete
import os
import logging

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogConfirmDelete(QtWidgets.QDialog):
    ''' A generic confirm delete dialog '''

    labelText = ""

    def __init__(self, text):

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_confirmDelete()
        self.ui.setupUi(self)
        self.ui.label.setText(text)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogConfirmDelete("text")
    ui.show()
    sys.exit(app.exec_())

