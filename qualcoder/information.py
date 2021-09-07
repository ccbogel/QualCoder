# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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
"""

from PyQt5 import QtWidgets, QtCore
import os
import sys
import logging
import traceback

from .GUI.ui_dialog_information import Ui_Dialog_information

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogInformation(QtWidgets.QDialog):
    """
    Dialog to display about information about development, version and license.
    The html is coded below because it avoids potential data file import errors with pyinstaller.
    Called from:
         qualcoder.MainWindow.about
         view_graph_original.ViewGraphOriginal.list_graph.TextGraphicsItem
         view_graph_original.ViewGraphOriginal.circular_graph.TextGraphicsItem
    """

    title = ""
    text = ""

    def __init__(self, app, title, html="", parent=None):
        """Display information text in dialog.
        If no html is given, fill with About html. """

        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_information()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowTitle(title)
        if html == "":
            self.setHtml(about.replace("QualCoderVersion", app.version))
        else:
            self.setHtml(html)

    def setHtml(self, html):
        """This method is used to populate the textEdit.
        Usually called from a View_graph TextGraphicsItem via a context menu. """

        self.text = html
        self.ui.textEdit.setHtml(self.text)

    def accept(self):
        """ Accepted button overridden method """
        self.information = self.ui.textEdit.toPlainText()
        super().accept()

about = '<h1 class="western">About QualCoder</h1>\
<h2 class="western">Version:</h2>\
<p>QualCoderVersion</p>\
<p>Depends on python at least 3.6, pyqt5 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl</p>\
<p>VLC should also be installed.</p>\
<p>Tested on: Ubuntu 20.04, mostly tested on Windows 10, used on Mac OS. Used on other Linux platforms (Lubuntu, Raspberry Pi, Fedora)</p>\
<p></p>\
<h2 class="western">Acknowledgements</h2>\
<p>Ronggui Huang and Zhang Gehao for creating RQDA, which inspired this software.</p>\
<p>Mike MacCana for the source code for the docx module.</p>\
<p>User: bit4 on stackoverflow who presented the source code to convert html to text.</p>\
<p>ebooklib: Aleksandar Erkalović https://github.com/aerkalov</p>\
<p>The VideoLAN team for the bindings to VLC. https://github.com/oaubert/python-vlc</p>\
<p>To various members on github for supporting this project. Greek translations from staff and students of the University of Macedonia.</p>\
<h2 class="western">Other details</h2\
<p>The qda data folder contains folders for imported documents, \
images, audio and video. It also contains the sqlite database, named data.qda, to store coding data.</p>\
<p>QualCoder creates a .qualcoder folder inside your home directory. \
This contains QualCoder.log, config.ini (for settings) and \
recent_project.txt. The config file contains the name of the current coder, \
default working directory, selected font and other parameters.</p>\
<p>QualCoder is written in python 3 using Qt5 for the graphical interface.</p>\
<p>The REFI-QDA Project import and export are experimental and should not be relied upon. </p>\
<h2 class="western">License</h2>\
<p>MIT License</p>\
<p>Copyright (c) 2021 Colin Curtain</p>\
<p>Permission is hereby granted, free of charge, to any person<br />\
obtaining a copy of this software and associated documentation files<br />\
(the &quot;Software&quot;), to deal in the Software without<br />\
restriction, including without limitation the rights to use, copy,<br />\
modify, merge, publish, distribute, sublicense, and/or sell copies of<br />\
the Software, and to permit persons to whom the Software is furnished<br />\
to do so, subject to the following conditions:</p>\
<p>The above copyright notice and this permission notice shall be <br />\
included in all copies or substantial portions of the Software.</p>\
<p>THE SOFTWARE IS PROVIDED &quot;AS IS&quot;, WITHOUT WARRANTY OF<br />\
ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE<br />\
WARRANTIES OF MERCHANTABILITY,</p>\
<p>FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT<br />\
SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,<br />\
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR<br />\
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR<br />\
THE USE OR OTHER DEALINGS IN THE SOFTWARE.</p>'

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogInformation(None, "a title", "")
    ui.show()
    sys.exit(app.exec_())