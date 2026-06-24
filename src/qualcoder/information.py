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

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

import html
from markdown_it import MarkdownIt
from PyQt6 import QtWidgets, QtCore, QtGui
import os
import logging
import qtawesome as qta
import re

from .GUI.ui_dialog_information import Ui_Dialog_information

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)
tab_info_markdown_renderer = MarkdownIt("commonmark")
help_link_pattern = re.compile(r'(<a href="qualcoder://help/[^"]*">)', re.IGNORECASE)
menu_link_pattern = re.compile(r'(<a href="qualcoder://menu/[^"]*">)', re.IGNORECASE)
action_link_pattern = re.compile(r'(<a href="qualcoder://action/[^"]*">)', re.IGNORECASE)
first_h1_pattern = re.compile(r"<h1>(.*?)</h1>", re.IGNORECASE | re.DOTALL)


def _qtawesome_icon_data_uri(icon_name, color, size=16, y_offset=0):
    """Render a qtawesome icon as a PNG data URI for rich text."""

    icon = qta.icon(icon_name, color=color)
    source_pixmap = icon.pixmap(size, size)
    canvas_width = size
    canvas_height = size + (y_offset // 2)
    pixmap = QtGui.QPixmap(canvas_width, canvas_height)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(0, y_offset, source_pixmap)
    painter.end()
    byte_array = QtCore.QByteArray()
    buffer = QtCore.QBuffer(byte_array)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    encoded = bytes(byte_array.toBase64()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_tab_info_markdown(markdown_text, highlight_color, text_color, doc_font_size, doc_font_family, heading_icon_name=None):
    """Render placeholder tab Markdown to HTML, including link decoration, etc.
    """

    icon_size = round(doc_font_size * 2)
    rendered_html = tab_info_markdown_renderer.render(markdown_text)
    help_icon_uri = _qtawesome_icon_data_uri("mdi.help-circle-outline", highlight_color, size=icon_size)
    menu_icon_uri = _qtawesome_icon_data_uri("mdi.cursor-default-outline", highlight_color, size=icon_size)
    action_icon_uri = _qtawesome_icon_data_uri("mdi.cursor-default-click-outline", highlight_color, size=icon_size)
    help_icon_html = (
        f'<img src="{help_icon_uri}" width="{icon_size}" height="{icon_size}" '
        'style="vertical-align: middle; margin-right: 0.3em;" />'
    )
    menu_icon_html = (
        f'<img src="{menu_icon_uri}" width="{icon_size}" height="{icon_size}" '
        'style="vertical-align: middle; margin-right: 0.3em;" />'
    )
    action_icon_html = (
        f'<img src="{action_icon_uri}" width="{icon_size}" height="{icon_size}" '
        'style="vertical-align: middle; margin-right: 0.3em;" />'
    )
    rendered_html = help_link_pattern.sub(rf"\1{help_icon_html}", rendered_html)
    rendered_html = menu_link_pattern.sub(rf"\1{menu_icon_html}", rendered_html)
    rendered_html = action_link_pattern.sub(rf"\1{action_icon_html}", rendered_html)
    if heading_icon_name:
        heading_size = max(64, icon_size * 4)
        heading_offset = max(4, round(heading_size * 0.28))
        heading_width_em = heading_size / (heading_size + heading_offset)
        heading_icon_uri = _qtawesome_icon_data_uri(
            heading_icon_name,
            highlight_color,
            size=heading_size,
            y_offset=heading_offset,
        )
        heading_icon_html = (
            f'<img src="{heading_icon_uri}" '
            f'style="width: {heading_width_em:.3f}em; height: 1em; margin-right: 0.25em;" />'
        )
        rendered_html = first_h1_pattern.sub(rf"<h1>{heading_icon_html}\1</h1>", rendered_html, count=1)
    safe_font_family = html.escape(doc_font_family, quote=True)
    return (
        "<style>"
        f"body {{ font-family: \"{safe_font_family}\"; font-size: {doc_font_size}pt; line-height: 1.35; margin: 0; color: {text_color}; }}"
        f"p, li {{ font-size: {doc_font_size}pt; margin: 0 0 0.1em 0; }}"
        f"h1 {{ font-size: {doc_font_size + 6}pt; margin: 2em -0.5em 0.5em 0; }}"
        f"h2 {{ font-size: {doc_font_size + 4}pt; font-weight: normal; margin: 1.5em 0 0.5em 0; }}"
        f"h3 {{ font-size: {doc_font_size + 2}pt; font-weight: normal; font-style: italic; margin: 0.8em 0 0.3em 0; }}"
        "</style>"
        + f'<div style="margin-left: 20px; margin-right: 20px;">{rendered_html}</div>'
    )


class DialogInformation(QtWidgets.QDialog):
    """
    Dialog to display about information about development, version and license.
    The html is coded below because it avoids potential data file import errors with pyinstaller.
    Called from:
         qualcoder.MainWindow.about
         view_graph_original.ViewGraphOriginal.list_graph.TextGraphicsItem
         view_graph_original.ViewGraphOriginal.circular_graph.TextGraphicsItem
    """

    def __init__(self, app, title, html_string=""):
        """Display information text in dialog.
        If no html is given, fill with About html.
        Args:
            app: App object
            title: String
            html_string: html string for contents
        """

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_information()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {app.settings["fontsize"]}pt "{app.settings["font"]}";'
        self.setStyleSheet(font)
        self.text = ""
        self.information = ""
        self.setWindowTitle(title)
        if html_string == "":
            qualcoder_tag = app.version.split("QualCoder ")[1]
            about_modifed = about.replace("QualCoderVersion", app.version)
            about_modifed = about_modifed.replace("QualCoderTag", qualcoder_tag)
            self.setHtml(about_modifed)
        else:
            self.setHtml(html_string)

    def setHtml(self, html_string):
        """This method is used to populate the textEdit.
        Usually called from a View_graph TextGraphicsItem via a context menu.
        Args:
            html_string: string of html
        """

        self.text = html_string
        self.ui.textEdit.setHtml(self.text)

    def accept(self):
        """ Accepted button overridden method """
        self.information = self.ui.textEdit.toPlainText()
        super().accept()


about = f'<h1 class="western">{_("About")} QualCoder</h1>\
<h2 class="western">Version:</h2>\
<p>QualCoderVersion</p>\
<p>{_("Optional: Install VLC for audio and video coding.")}<br /> \
{_("Optional: Install ffmpeg for waveform images.")}</p>\
<p>Tested on: Windows 11.</p>\
<p></p>\
<h2 class="western">{_("Acknowledgements")}</h2>\
<p>Ronggui Huang, Zhang Gehao - {_("Created RQDA - inspiration for QualCoder.")}<br /> \
Mike MacCana -  {_("Source code for the docx module.")}<br /> \
Julius Reich - {_("Created the QualCoder logo.")}<br /> \
Kai Dröge -  {_("Programming, artificial intelligence and much more.")}<br /> \
Justin Missaghieh-Poncet - {_("French translations, programming, setting up the new website and more.")}<br />\
<a href="https://qualcoder.org" target="_blank">https://qualcoder.org</a><br /> \
Lorenzo Salomón - {_("Programming and Spanish translations.")}<br /> \
Jofen Kihlstrom for past Swedish translations.<br /> \
{_("To the many members on Github for supporting this project.")}</p>\
<h2>Citation</h2>\
<p>Curtain C, Dröge K, Missaghieh--Poncet J, Salomón L. (2026) QualCoder Version [Computer software]. \
Retrieved from https://github.com/ccbogel/QualCoder/releases/tag/QualCoderTag</p>\
<h2 class="western">Other details</h2> \
<p>The qda data folder contains folders for imported documents, \
images, audio and video. It also contains the sqlite database, named data.qda, which stores the coding data.<br /> \
QualCoder is written in python3 using Qt6 for the graphical interface.</p>\
<p>Created by Colin Curtain BPharm GradDipComp PhD, programmer, Lecturer University of Tasmania.</p>\
<h2 class="western">Licenses</h2>\
<h3>LGPL-3.0 License</h3>\
<p>This file is part of QualCoder.</p>\
<p>QualCoder is free software: you can redistribute it and/or modify it under the \
terms of the GNU Lesser General Public License as published by the Free Software \
Foundation, either version 3 of the License, or (at your option) any later version. </p\
<p>QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; \
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. \
See the GNU General Public License for more details.</p>\
<p>You should have received a copy of the GNU Lesser General Public License along with QualCoder. \
If not, see <a href="https://www.gnu.org/licenses">https://www.gnu.org/licenses</a>  </p>\
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

menu_shortcuts = f'<h1>{_("Menu key shortcuts")}</h1>\n\
<table><tr><td><b>{_("Menu shortcuts")}</b></td><td><b>{_("Project menu shortcuts")}</b></td>\n\
<td><b>{_("Files and Cases menu shortcuts")}</b></td></tr>\n\
<tr><td>Alt 1 {_("Open Project menu")}</td>\n\
<td>Ctrl N (macOS Cmd N) {_("New project")}</td><td>\n\
Alt F (macOS Option F) {_("Manage files")}</td></tr>\n\
<tr><td>Alt 2 {_("Open Files and Cases menu")}</td><td>Ctrl O {_("Open project")}</td><td>Alt C {_("Manage cases")}</td></tr>\n\
<tr><td>Alt 3 {_("Open Coding menu")}</td><td>Alt X {_("Close project")}</td><td>Alt J {_("Manage journals")}</td></tr>\n\
<tr><td>Alt 4 {_("Open Reports menu")}</td><td>Ctrl M {_("Project memo")}</td><td>Alt A {_("Manage attributes")}</td></tr>\n\
<tr><td>Alt 5 {_("Open Help menu")}</td><td>Alt S {_("Settings")}</td><td>Alt R {_("Manage references")}</td></tr>\n\
<tr><td><br/></td><td>Ctrl Q (macOS Cmd Q) {_("Exit")}</td><td></td></tr>\n\
</table><br/><table>\n\
<tr><td><b>{_("Coding menu shortcuts")}</b></td><td><b>{_("Reports menu shortcuts")}</b></td><td><b>{_("Help menu shortcuts")}</b></td></tr>\n\
<tr><td>Alt T {_("Code text")}</td><td>Alt K {_("Code retrieval")}</td><td>Alt H {_("Help contents")}</td></tr>\n\
<tr><td>Alt I {_("Code image")}</td><td>Alt L {_("Code comparison")}</td><td>Alt Y {_("About")}</td></tr>\n\
<tr><td>Alt V {_("Code audio/video")}</td><td>Alt M {_("Code comparison by file")}</td><td>Alt Z {_("Special functions")}</td></tr>\n\
<tr><td>Alt E {_("Colour scheme")}</td><td>Alt N {_("Code frequencies")}</td><td></td></tr>\n\
<tr><td></td><td>Alt O {_("File summary")}</td><td></td></tr>\n\
<tr><td></td><td>Alt P {_("Code summary")}</td><td></td></tr>\n\
<tr><td></td><td>Alt Q {_("Code relations")}</td><td></td></tr>\n\
<tr><td></td><td>Alt G {_("Open Graph")}</td><td></td></tr>\n\
<tr><td></td><td>Alt U {_("Charts")}</td><td></td></tr>\n\
<tr><td></td><td>Alt D {_("Database queries")}</td><td></td></tr></table>'

manage_section_shortcuts = f'<h1>{_("Manage menu key shortcuts")}</h1><table>\n\
<tr><td><b>Key&nbsp;&nbsp;&nbsp;</b></td><td><b>{_("Files")}</b></td><td><b>{_("Cases")}</b></td>\n\
<td><b>{_("Journals")}</b></td><td><b>{_("References")}</b></td></tr>\n\
<tr><td>Ctrl 0</td><td>{_("Help")}</td><td>{_("Help")}</td><td>{_("Help")}</td><td></td></tr>\n\
<tr><td>Ctrl 1</td><td>{_("View file")}</td><td>{_("Create case")}</td><td>{_("Create journal")}</td><td></td></tr>\n\
<tr><td>Ctrl 2</td><td>{_("Import file")}</td><td>{_("Import cases")}</td><td>{_("Export")}</td><td>{_("Unlink file")}</td></tr>\n\
<tr><td>Ctrl 3</td><td>{_("Link to file")}</td><td>{_("Case file manager")}</td><td>{_("Export all")}</td><td>{_("Edit reference")}</td></tr>\n\
<tr><td>Ctrl 4</td><td>{_("Create text file")}</td><td>{_("Add attribute")}</td><td>{_("Delete journal")}</td><td>{_("Import references")}</td></tr>\n\
<tr><td>Ctrl 5</td><td>{_("Import linked file")}</td><td>{_("Export attributes")}</td><td></td><td>{_("Delete reference")}</td></tr>\n\
<tr><td>Ctrl 6</td><td>{_("Export to linked file")}</td><td>{_("Delete case")}</td><td></td><td></td></tr>\n\
<tr><td>Ctrl 7</td><td>{_("Add attribute")}</td><td></td><td></td><td></td></tr>\n\
<tr><td>Ctrl 8</td><td>{_("Export attributes")}</td><td></td><td></td><td></td></tr>\n\
<tr><td>Ctrl 9</td><td>{_("Export file")}</td><td></td><td></td><td></td></tr>\n\
<tr><td>Ctrl A</td><td>{_("Show all rows")}</td><td>{_("Show all rows")}</td><td></td><td>L {_("Link selected")}</td></tr>\n\
<tr><td></td><td></td><td></td><td></td><td>U {_("Unlink file")}</td></tr>\n\
</table>'

view_av_shortcuts = f'<br /><h2>{_("Manage files - view A/V shortcuts")}</h2>\n\
Alt - {_("Rewind 30 seconds.")}<br />\n\
Ctrl R (macOS Cmd R) {_("Rewind 5 seconds")}<br />\n\
Alt + {_("Forward 30 seconds")}<br />\n\
Ctrl S OR Ctrl P (macOS Cmd S Cmd P) {_("Start / pause.On start rewind slightly")}<br />\n\
Ctrl T {_("Insert timestamp in format")}[hh.mm.ss]<br />\n\
Ctrl N (macOS use Button) {_("Enter a new speakers name into shortcuts")}<br />\n\
Ctrl D {_("Delete speaker names from shortcuts")}<br />\n\
Ctrl 1 .. 8 {_("Insert speaker in format[speaker name]")}<br />\n\
Ctrl Shift &gt; (macOS Cmd Shift &gt;) {_("Increase play rate")}<br />\n\
Ctrl Shift &lt; (macOS Cmd Shift &lt;) {_("Decrease play rate")}<br />\n\
F2 {_("When tree item selected - Rename code or category")}<br /><br />'

menu_shortcuts_display = menu_shortcuts + manage_section_shortcuts + view_av_shortcuts

coding_text_shortcuts = f'<h2>{_("Code text key shortcuts")}</h2>\
Ctrl 1 {_("Next file")}<br />\
Ctrl 2 {_("File with latest coding")}<br />\
Ctrl 3 {_("Go to bookmark")}<br />\
Ctrl 4 {_("Open file memo")}<br />\
Ctrl 5 {_("Filter files by attributes")}<br />\
Ctrl 6 {_("Show selected code previous")}<br />\
Ctrl 7 {_("Show selected code next")}<br />\
Ctrl 8 {_("Show all codes in text ( if selected code previous or next has been used)")}<br />\
Ctrl 9 {_("Show codes marked important")}<br />\
Ctrl 0 {_("Help - opens in browser")}<br />\
Ctrl F {_("Jump to search box")}<br />\
Ctrl Z {_("The last code that was unmarked, restore that coding")}<br />\
Ctrl E {_("Enter and Exit Edit mode")}<br />\
A {_("Annotate - Current text selection")}<br />\
B {_("Create bookmark - at clicked position")}<br />\
Shift B {_("Go to bookmark")}<br />\
C {_("Create new category. If a category is already selected, the new category will be underneath")}<br />\
H {_("Hide / Unhide top groupbox")}<br />\
I {_("Tag coded text at clicked position as important")}<br />\
L {_("Show codes like (when text coding area is in focus)")}<br />\
M {_("Memo code - at clicked position")}<br />\
N {_("New code - for selected text")}<br />\
O {_("Shortcut to cycle through overlapping codes - at clicked position")}<br />\
Q {_("Quick Mark with code - for current selection")}<br />\
S {_("Search text - may include current selection")}<br />\
R {_("Opens a context menu for recently used codes for marking text")}<br />\
Ctrl R {_("Reverse text direction: Left to Right | Right to Left")}<br />\
U {_("Unmark At clicked position in the text")}<br />\
V {_("assign in vivo code to selected text")}<br />\
{_("Alt Left arrow.Shrink coding to the left")}<br />\
{_("Alt Right arrow.Shrink coding to the right")}<br />\
{_("Shift Left arrow.Extend coding to the left")}<br />\
{_("Shift Right arrow.Extend coding to the right")}<br />\
! {_("Describes clicked text character position")}<br />\
$ {_("Shift all coding positions after a clicked position by X characters (negative numbers shift left)")}<br />\
F2 {_("When tree item selected - Rename code or category")}'

coding_pdf_shortcuts = f'<h2>{_("Code PDF key shortcuts")}</h2>\
Ctrl 0 {_("Help - opens in browser")}<br />\
Ctrl 1 {_("Next file")}<br />\
Ctrl 2 {_("File with latest coding")}<br />\
Ctrl 3 {_("Open file memo")}<br />\
Ctrl 4 {_("Filter files by attributes")}<br />\
Ctrl 5 {_("Show codes marked important")}<br />\
Ctrl 9 {_("Show codes marked important")}<br />\
A {_("Annotate - Current text selection")}<br />\
B {_("Create bookmark - at clicked position")}<br />\
C {_("Create new category. If a category is already selected, the new category will be underneath")}<br />\
H {_("Hide / Unhide top groupbox")}<br />\
I {_("Tag coded text at clicked position as important")}<br />\
L {_("Show codes like (when coding area is in focus)")}<br />\
M {_("Memo code - at clicked position")}<br />\
Q {_("Quick Mark with code - for current selection")}<br />\
R {_("Opens a context menu for recently used codes for marking text")}<br />\
U {_("Unmark At clicked position in the text")}<br />\
V {_("assign in vivo code to selected text")}<br />\
Ctrl Z {_("The last code is unmarked, undo and restore that coding")}<br />\
Minus {_("Zoom out")}<br />\
Plus {_("Zoom in")}<br />\
! {_("Describes clicked text character position")}<br />\
F2 {_("When tree item selected - Rename code or category")}'

coding_image_shortcuts = f'<h2>{_("Code image key shortcuts")}</h2>\
Ctrl 1 {_("Next file")}<br />\
Ctrl 2 {_("File with latest coding")}<br />\
Ctrl 3 {_("Open file memo")}<br />\
Ctrl 4 {_("Filter files by attributes")}<br />\
Ctrl 5 {_("Show codes marked important")}<br />\
Ctrl 0 {_("Help - opens in browser")}<br />\
C {_("Create new category. If a category is already selected, the new category will be underneath")}<br />\
L {_("Show codes like (when coding area is in focus)")}<br />\
Ctrl Z {_("The last code is unmarked, undo and restore that coding")}<br />\
Ctrl G {_("Create a grayed-out image with coloured coded highlights (Wait a few seconds)")}<br />\
Minus or Q {_("Zoom out")}<br />\
Plus or W {_("Zoom in")}<br />\
{_("Right - click on image for menu to rotate image")}<br />\
F2 {_("When tree item selected - Rename code or category")}'

coding_av_shortcuts = f'<h2>{_("Code audio/video key shortcuts")}</h2>\
Ctrl 1 {_("Next file")}<br />\
Ctrl 2 {_("File with latest coding")}<br />\
Ctrl 3 {_("Open file memo")}<br />\
Ctrl 4 {_("Filter files by attributes")}<br />\
Ctrl 9 {_("Show codes marked important")}<br />\
Ctrl 0 {_("Help - opens in browser")}<br />\
A {_("Annotate - for current selection")}<br />\
B <br />\
Shift B <br />\
C {_("Create new category. If a category is already selected, the new category will be underneath")}<br />\
G {_("Assign segment to currently selected code, and open memo for segment.")}<br />\
I {_("Tag important")}<br />\
L {_("Show codes like (when text coding area is in focus)")}<br />\
M {_("Memo code - at clicked position")}<br />\
O {_("Cycle through overlapping codes at clicked position")}<br />\
Q {_("Quick Mark with code - for current selection")}<br />\
S {_("Search text - may include current selection")}<br />\
R {_("Opens a context menu for recently used codes for marking text")}<br />\
! {_("Shows cursor position in text area")}<br />\
5 {_("Go forward 5 seconds.")}<br />\
Ctrl Z {_("Restore last unmarked code(s) - text code(s) or segment code")}<br />\
Alt - {_("Rewind 30 seconds")}<br />\
Ctrl R {_("Rewind 5 seconds")}<br />\
Alt + {_("Forward 30 seconds")}<br />\
Ctrl P {_("Play / pause.On start rewind slightly")}<br />\
Ctrl D {_("Play / pause.On start rewind slightly")}<br />\
Ctrl S {_("Start and stop av segment creation")}<br />\
Ctrl Shift &gt; {_("Increase play rate")}<br />\
Ctrl Shift &lt; {_("Decrease play rate")}<br />\n\
F2 {_("When tree item selected - Rename code or category")}'

database_queries_shortcuts = f'<h2>{_("Database Queries key shortcuts")}</h2>\
Ctrl + Enter {_("Run SQL query")}<br />'

coding_shortcuts_display = coding_text_shortcuts + coding_pdf_shortcuts + coding_image_shortcuts + coding_av_shortcuts
coding_shortcuts_display += database_queries_shortcuts

def manage_tab_info():
    """Return translated Markdown for the Manage tab placeholder."""

    return _("""# Manage

The Manage tab displays workspaces for organising cases, files, attributes, journals, and references.
Use the [Manage menu](qualcoder://menu/files_and_cases) to choose among them.


## [Manage Files](qualcoder://menu/files_and_cases/manage_files)

- This menu lets you add and remove empirical data in your project.
- You can import plain text and many other document types,
including PDFs, images, audio, and video.
- You may also import survey data.
- Before importing text files, you may want to create pseudonyms to protect the privacy of people or organisations.
- [Help: Import files](qualcoder://help/3.2.-Files/)


## [Manage Cases](qualcoder://menu/files_and_cases/manage_cases)

- You can use cases to group files together that are related to a topic, person, organisation, or any other empirical entity in your study. 
- This can be useful for organising your data and for running reports on specific groups of files.
- [Help: Cases](qualcoder://help/3.3.-Cases/)


## [Manage Journals](qualcoder://menu/files_and_cases/manage_journals)

- Journals are used to record your thoughts when coding and analysing data. 
- The journal window opens separately from the main window so you can move between them easily.
- [Help: Journals](qualcoder://help/5.2.-Journals/)


## [Manage Attributes](qualcoder://menu/files_and_cases/manage_attributes)

- Files, cases, and journals can have attributes (variables) that describe their characteristics. 
- They can be used to filter and organise data, and to run reports based on specific criteria. 
- Use this menu to create and manage such attributes. They can be attached to files, cases, and journals directly in the respective workspaces. 
- [Help: Attributes](qualcoder://help/3.4.-Attributes/)


## [Manage References](qualcoder://menu/files_and_cases/manage_references)

- Bibliographic references can be imported from NBIB and RIS files.
- After that, references can be linked to files in the project.
- [Help: Import References](qualcoder://help/6.1.-Imports-and-Exports/)
""")


def coding_tab_info():
    """Return translated Markdown for the Coding tab placeholder."""

    return _("""# Coding

The Coding tab displays workspaces for coding text, PDFs, images, audio, and video.
Use the [Coding menu](qualcoder://menu/coding) to select an option to begin. 
Note that you can only open a particular coding workspace if that type of data is actually present in the current project. 


## [Code Text](qualcoder://menu/coding/codes)

- Use this workspace to read textual data closely and assign codes to selected passages.
- You can organise codes in a tree, add memos and annotations, create bookmarks, and mark especially useful segments as important.
- [Help: Coding text](qualcoder://help/4.1.-Coding-Text/)


## [Code Images](qualcoder://menu/coding/code_image)

- In this workspace, you can select regions in photographs, diagrams, screenshots, or other visual material and assign codes to them.
- Coded areas are displayed as coloured rectangles linked to your code system.
- [Help: Coding images](qualcoder://help/4.4.-Coding-Images/)


## [Code Audio and Video](qualcoder://menu/coding/code_audio_video)

- Use this workspace to transcribe and/or code time-based media such as interviews, focus groups, and field recordings.
- [Help: Coding audio and video](qualcoder://help/4.5.-Coding-Audio-and-Video/)


## [Code PDFs](qualcoder://menu/coding/code_pdf)

- This workspace allows you to code text directly in PDF documents when you want to keep the original page layout in view.
- This is useful for articles, reports, and other source material where page position and formatting matter.
- [Help: Coding PDFs](qualcoder://help/4.3.-Coding-Text-on-PDFs/)


## [AI Assisted Coding](qualcoder://menu/coding/ai_assisted_coding)

- This loads a variant of the text coding workspace that uses AI to explore your data and suggest segments for a selected code.
- [Help: AI assisted coding](qualcoder://help/4.2.-AI-Assisted-Coding/)


## [Code Organiser](qualcoder://menu/coding/code_organiser)

- Use this workspace to reorganise your code system using a graphical, mind-map style interface.
- You can move, merge, and rename codes and categories as your analytic structure becomes clearer.
- [Help: Code Organiser](qualcoder://help/4.6-Code-Organiser/)


## [Colour Scheme](qualcoder://menu/coding/colour_scheme)

- This allows you to change the colour scheme of your codes and categories. 
- Special schemes for colour-blind users are available. 
""")


def reports_tab_info():
    """Return translated Markdown for the Reports tab placeholder."""

    return _("""# Reports tab

This tab displays tools from both the [Analysis](qualcoder://menu/analysis) and [Reports](qualcoder://menu/reports) menus.


## [Analysis](qualcoder://menu/analysis)

Use these tools when you want to explore coded segments and relationships in detail.

[Help: Analysis and Reports menu options](qualcoder://help/5.3.-Reports/)


### Retrieval and segment-based analysis

These tools help you inspect the actual coded material in your project.

- [Code retrieval](qualcoder://menu/analysis/coding_reports) is a flexible analysis tool. It gathers all segments for selected codes or categories and lets you narrow the results by file, case, attributes, or search text.
- [Codes by text segments](qualcoder://menu/analysis/text_segments_by_codes) generates a table with text segments and all associated codes.


### Code relationships and overlaps

Use these tools to examine how codes relate to one another. They only work with text files.

- [Code relations](qualcoder://menu/analysis/code_relations) shows proximity, overlap, inclusion, and exact matches between selected codes.
- [Code co-occurrence](qualcoder://menu/analysis/code_co_occurrence) focuses on where two codes overlap or directly touch.
- [Code text exact matches](qualcoder://menu/analysis/code_text_exact_matches) lists passages where different codes were applied to exactly the same text.
- [Graph](qualcoder://menu/analysis/view_graph) provides a visual, mind-map style view of linked project elements like codes, cases, files, etc. [Help: Graph](qualcoder://help/5.4.-Graph/)


## Reports

Use these tools when you want summaries, comparisons, counts, charts, or exports for reporting purposes.

[Help: Analysis and Reports menu options](qualcoder://help/5.3.-Reports/)


### Inter-Coder Comparisons

- [Coding comparison](qualcoder://menu/reports/coding_comparison) and [Coding comparison by file](qualcoder://menu/reports/coding_comparison_by_file) are especially useful for collaborative work and inter-coder checking.


### Summaries, frequencies, and charts

These reports summarise patterns across the project rather than showing every coded segment in detail.

- [Code frequencies](qualcoder://menu/reports/code_frequencies) counts how often codes and categories have been used.
- [Code counts by file/case](qualcoder://menu/reports/code_comparison_table) gives a compact overview of where selected codes appear most often.
- [File summary](qualcoder://menu/reports/file_summary) and [Code summary](qualcoder://menu/reports/code_summary) give focused overviews of one file or one code at a time.
- [Charts](qualcoder://menu/reports/charts) visualises distributions and comparisons with diagrams such as bar charts, treemaps, and heatmaps.


### Advanced reporting

- [Database queries](qualcoder://menu/reports/sql_statements) gives direct access to the project database for custom analyses. This is most useful when the standard reports do not answer a specific research question in the exact form you need.
""")

