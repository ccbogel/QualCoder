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

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

from PyQt6 import QtWidgets, QtCore
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
    information = ""

    def __init__(self, app_, title, html=""):
        """Display information text in dialog.
        If no html is given, fill with About html. """

        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_information()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app_.settings['fontsize']) + 'pt '
        font += '"' + app_.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowTitle(title)
        if html == "":
            self.setHtml(about.replace("QualCoderVersion", app_.version))
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
<p>Depends on python minimum version 3.6 (I recommend 3.10). \
<p>Modules required: pyqt6 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl pandas plotly pydub \
SpeechRecognition</p>\
<p>A recent version of VLC (64 bit) needs to be installed. \
ffmpeg is optional, but recommended to be installed for speech to text and waveform images.</p>\
<p>Tested on: Ubuntu 20.04, mostly tested on Windows 10, used on Mac OS and on other Linux distros.</p>\
<p></p>\
<h2 class="western">Acknowledgements</h2>\
<p>Ronggui Huang and Zhang Gehao for creating RQDA, which inspired this software. \
Mike MacCana for the source code for the docx module. \
User: bit4 on stackoverflow who presented the source code to convert html to text. \
ebooklib: Aleksandar Erkalović https://github.com/aerkalov. \
The VideoLAN team for the bindings to VLC. https://github.com/oaubert/python-vlc. \
The ffmpeg team. https://ffmpeg.org/ used with speech to text and waveform/spectrograph images. \
Julius Reich for creating the cool QualCoder logo. \
 To various members on github for supporting this project.</p>\
<h2 class="western">Other details</h2\
<p>The qda data folder contains folders for imported documents, \
images, audio and video. It also contains the sqlite database, named data.qda, to store coding data.</p>\
<p>QualCoder creates a .qualcoder folder inside your home directory. \
This contains QualCoder.log, config.ini (for settings) and \
recent_project.txt. The config file contains the name of the current coder, \
default working directory, selected font and other parameters.</p>\
<p>QualCoder is written in python using Qt6 for the graphical interface.</p>\
<p>The REFI-QDA Project import and export seem to work ok, but should not be fully relied upon. </p>\
<h2 class="western">License</h2>\
<p>MIT License</p>\
<p>Copyright (c) 2022 Colin Curtain</p>\
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
