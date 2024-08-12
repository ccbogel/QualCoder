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
<p>QualCoder creates a .qualcoder_ai folder inside your home directory. \
This contains QualCoder.log, config.ini (for settings) and \
recent_project.txt. The config file contains the name of the current coder, \
default working directory, selected font and other parameters.</p>\
<p>QualCoder is written in python3 using Qt6 for the graphical interface.</p>\
<p>The REFI-QDA Project import and export seem to work ok, but are still experimental. </p>\
<p>Created by Colin Curtain BPharm GradDipComp PhD, python programmer, lecturer University of Tasmania.</p>\
<h2>Citation</h2>\
Curtain, C. (2023) QualCoder VERSION [Computer software]. Retrieved from https://github.com/ccbogel/QualCoder/releases/tag/VERSION\
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

menu_shortcuts = '<h1>Menu key shortcuts</h1>\n\
<table><tr><td><b>Menu shortcuts</b></td><td><b>Project menu shortcuts</b></td>\n\
<td><b>Files and Cases menu shortcuts</b></td></tr>\n\
<tr><td>Alt 1 Open Project menu</td><td>Ctrl N New project</td><td>Alt F Manage files</td></tr>\n\
<tr><td>Alt 2 Open Files and Cases menu</td><td>Ctrl O Open project</td><td>Alt C Manage cases</td></tr>\n\
<tr><td>Alt 3 Open Coding menu</td><td>Alt X Close project</td><td>Alt J Manage journals</td></tr>\n\
<tr><td>Alt 4 Open Reports menu</td><td>Ctrl M Project memo</td><td>Alt A Manage attributes</td></tr>\n\
<tr><td>Alt 5 Open Help menu</td><td>Alt S Settings</td><td>Alt R Manage references</td></tr>\n\
<tr><td><br/></td><td>Ctrl Q Exit</td><td>Ctrl I Import survey</td></tr>\n\
</table><br/><table>\n\
<tr><td><b>Coding menu shortcuts</b></td><td><b>Reports menu shortcuts</b></td><td><b>Help menu shortcuts</b></td></tr>\n\
<tr><td>Alt T Code text</td><td>Alt K Coding reports</td><td>Alt H Contents - in web browser</td></tr>\n\
<tr><td>Alt I Code image</td><td>Alt L Coding comparison</td><td>Alt Y About</td></tr>\n\
<tr><td>Alt V Code audio/video</td><td>Alt M Coding comparison by file</td><td>Alt Z Special functions</td></tr>\n\
<tr><td>Alt E Colour scheme</td><td>Alt N Code frequencies</td><td></td></tr>\n\
<tr><td></td><td>Alt O File summary</td><td></td></tr>\n\
<tr><td></td><td>Alt P Code summary</td><td></td></tr>\n\
<tr><td></td><td>Alt Q Code relations</td><td></td></tr>\n\
<tr><td></td><td>Alt G Open Graph</td><td></td></tr>\n\
<tr><td></td><td>Alt U Charts</td><td></td></tr>\n\
<tr><td></td><td>Alt D Database queries</td><td></td></tr></table>'

manage_section_shortcuts = '<h1>Manage menu section key shortcuts</h1><table>\n\
<tr><td><b>Key&nbsp;&nbsp;&nbsp;</b></td><td><b>Manage files</b></td><td><b>Cases</b></td>\n\
<td><b>Journals</b></td><td><b>References</b></td></tr>\n\
<tr><td>Ctrl 0</td><td>Help</td><td>Help</td><td>Help</td><td></td></tr>\n\
<tr><td>Ctrl 1</td><td>View file</td><td>Create case</td><td>Create journal</td><td></td></tr>\n\
<tr><td>Ctrl 2</td><td>Import file</td><td>Import cases</td><td>Export</td><td>Unlink file</td></tr>\n\
<tr><td>Ctrl 3</td><td>Link to file</td><td>Case file manager</td><td>Export all</td><td>Edit reference</td></tr>\n\
<tr><td>Ctrl 4</td><td>Create text file</td><td>Add attribute</td><td>Delete journal</td><td>Import references</td></tr>\n\
<tr><td>Ctrl 5</td><td>Import linked file</td><td>Export attributes</td><td></td><td>Delete reference<</td></tr>\n\
<tr><td>Ctrl 6</td><td>Export to linked file</td><td>Delete case</td><td></td><td></td></tr>\n\
<tr><td>Ctrl 7</td><td>Add attribute</td><td></td><td></td><td></td></tr>\n\
<tr><td>Ctrl 8</td><td>Export attributes</td><td></td><td></td><td></td></tr>\n\
<tr><td>Ctrl 9</td><td>Export file</td><td></td><td></td><td></td></tr>\n\
<tr><td></td><td>Ctrl A Show all rows</td><td>Ctrl A Show all rows</td><td></td><td>L Link selected</td></tr>\n\
<tr><td></td><td></td><td></td><td></td><td>U Unlink file</td></tr>\n\
</table>'

view_av_shortcuts = '<br /><h2>Manage files - view A/V shortcuts</h2>\n\
Alt minus Rewind 30 seconds.<br />Ctrl R Rewind 5 seconds<br />Alt plus Forward 30 seconds<br />\n\
Ctrl S OR Ctrl P Start/pause. On start rewind 1 second<br />\n\
Ctrl T Insert timestamp in format [hh.mm.ss]<br />\n\
Ctrl N Enter a new speakers name into shortcuts<br />\n\
Ctrl D Delete speaker names from shortcuts<br />\n\
Ctrl 1 .. 8 Insert speaker in format [speaker name]<br />\n\
Ctrl Shift &gt; Increase play rate<br />\n\
Ctrl Shift &lt; Decrease play rate<br /><br />'

menu_shortcuts_display = menu_shortcuts + manage_section_shortcuts + view_av_shortcuts

coding_text_shortcuts = '<h2>Code text key shortcuts</h2>\
Ctrl 1 Next file<br />\
Ctrl 2 File with latest coding<br />\
Ctrl 3 Go to bookmark<br />\
Ctrl 4 Open file memo<br />\
Ctrl 5 Filter files by attributes<br />\
Ctrl 6 Show selected code previous<br />\
Ctrl 7 Show selected code next<br />\
Ctrl 8 Show all codes in text (if selected code previous or next has been used)<br />\
Ctrl 9 Show codes marked important<br />\
Ctrl 0 Help - opens in browser<br />\
Ctrl F Jump to search box<br />\
Ctrl Z The last code that was unmarked, restore that coding<br />\
Ctrl E Enter and Exit Edit mode<br />\
A Annotate - Current text selection<br />\
Q Quick Mark with code - for current selection<br />\
B Create bookmark - at clicked position<br />\
H Hide / Unhide top groupbox<br />\
I Tag code at clicked position as important<br />\
M Memo code - at clicked position<br />\
O Shortcut to cycle through overlapping codes - at clicked position<br />\
S Search text - may include current selection<br />\
R Opens a context menu for recently used codes for marking text<br />\
U Umark at clicked position in the text<br />\
V assign in vivo code to selected text<br />\
Alt + Left arrow  Shrink coding to the left <br />\
Alt + Right arrow Shrink coding to the right<br />\
Shift + Left arrow Extend coding to the left<br />\
Shift + Right arrow Extend coding to the right<br />\
! Exclamation mark key - describes clicked text character position<br />\
$ Dollar key - Shift all coding postiions after a clicked position by X characters (negative numbers shift left)'

coding_image_shortcuts = '<h2>Code image key shortcuts</h2>\
Ctrl 1 Next file<br />\
Ctrl 2 File with latest coding<br />\
Ctrl 3 Open file memo<br />\
Ctrl 4 Filter files by attributes<br />\
Ctrl 5 Show codes marked important<br />\
Ctrl 0 Help - opens in browser<br />\
Ctrl Z The last code is unmarked, undo and restore that coding<br />\
Minus or Q Zoom out<br />\
Plus or W Zoom in'

coding_av_shortcuts = '<h2>Code audio/video key shortcuts</h2>\
Ctrl 1 Next file<br />\
Ctrl 2 File with latest coding<br />\
Ctrl 3 Open file memo<br />\
Ctrl 4 Filter files by attributes<br />\
Ctrl 9 Show codes marked important<br />\
Ctrl 0 Help - opens in browser<br />\
A annotate - for current selection<br />\
Q Quick Mark with code - for current selection<br />\
I Tag important<br />\
M memo code - at clicked position<br />\
O Shortcut to cycle through overlapping codes - at clicked position<br />\
S search text - may include current selection<br />\
R opens a context menu for recently used codes for marking text<br />\
Ctrl Z Restore last unmarked code(s) - text code(s) or segment code<br />\
Alt minus Rewind 30 seconds<br />\
Ctrl R Rewind 5 seconds<br />\
Alt + plus Forward 30 seconds<br />\
Ctrl P Play/pause. On start rewind 1 second<br />\
Ctrl D Play/pause. On start rewind 1 second<br />\
Ctrl S Start and stop av segment creation<br />\
Ctrl Shift > Increase play rate<br />\
Ctrl Shift < Decrease play rate<br />'

coding_shortcuts_display = coding_text_shortcuts + coding_image_shortcuts + coding_av_shortcuts