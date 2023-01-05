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
<p>Optional: Install VLC for audio and video coding.<br /> \
Optional: Install ffmpeg for speech to text and waveform images.</p>\
<p>Tested on: Ubuntu 22.04, Windows 10/11, used on macOS and on other Linux distros.</p>\
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
images, audio and video. It also contains the sqlite database, named data.qda, which stores the coding data.</p>\
<p>QualCoder creates a .qualcoder folder inside your home directory. \
This contains QualCoder.log, config.ini (for settings) and \
recent_project.txt. The config file contains the name of the current coder, \
default working directory, selected font and other parameters.</p>\
<p>QualCoder is written in python3 using Qt6 for the graphical interface.</p>\
<p>The REFI-QDA Project import and export seem to work ok, but are still experimental. </p>\
<h2 class="western">Licenses</h2>\
<h3>MIT License</h3>\
<p>Copyright (c) 2023 Colin Curtain</p>\
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
THE USE OR OTHER DEALINGS IN THE SOFTWARE.</p>\
<h3>License for highlighter.py code</h3>\
<p>## Copyright (C) 2013 Riverbank Computing Limited.<br />\
## Copyright (C) 2010 Nokia Corporation and/or its subsidiary(-ies).<br />\
## All rights reserved.<br />\
##<br />\
## This file is part of the examples of PyQt.<br />\
##<br />\
## $QT_BEGIN_LICENSE:BSD<br />\
## You may use this file under the terms of the BSD license as follows:<br />\
##<br />\
## "Redistribution and use in source and binary forms, with or without<br />\
## modification, are permitted provided that the following conditions are<br />\
## met:<br />\
##   * Redistributions of source code must retain the above copyright<br />\
##     notice, this list of conditions and the following disclaimer.<br />\
##   * Redistributions in binary form must reproduce the above copyright<br />\
##     notice, this list of conditions and the following disclaimer in<br />\
##     the documentation and/or other materials provided with the<br />\
##     distribution.<br />\
##   * Neither the name of Nokia Corporation and its Subsidiary(-ies) nor<br />\
##     the names of its contributors may be used to endorse or promote<br />\
##     products derived from this software without specific prior written<br />\
##     permission.<br />\
##<br />\
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS<br />\
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT<br />\
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR<br />\
## A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT<br />\
## OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,<br />\
## SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT<br />\
## LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,<br />\
## DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY<br />\
## THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT<br />\
## (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE<br />\
## OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."<br />\
<h3>License for docx.py code</h3>\
Copyright (c) 2009-2010 Mike MacCana<br />\
<br />\
Permission is hereby granted, free of charge, to any person<br />\
obtaining a copy of this software and associated documentation<br />\
files (the "Software"), to deal in the Software without<br />\
restriction, including without limitation the rights to use,<br />\
copy, modify, merge, publish, distribute, sublicense, and/or sell<br />\
copies of the Software, and to permit persons to whom the<br />\
Software is furnished to do so, subject to the following<br />\
conditions:<br />\
<br />\
The above copyright notice and this permission notice shall be<br />\
included in all copies or substantial portions of the Software.<br />\
<br />\
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,<br />\
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES<br />\
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND<br />\
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT<br />\
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,<br />\
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING<br />\
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR<br />\
OTHER DEALINGS IN THE SOFTWARE.'
