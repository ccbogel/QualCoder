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
"""

import logging
import os
import rispy
import sys
import traceback
from PyQt6 import QtWidgets

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


class ImportRis:
    """ Import an RIS format bibliography and store in database. """

    app = None
    parent_text_edit = None

    def __init__(self, app, parent_text_edit):
        sys.excepthook = exception_handler
        self.app = app
        self.parent_text_edit = parent_text_edit
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select RIS references file'),
                                                          self.app.settings['directory'],
                                                          "(*.ris *.RIS)",
                                                          options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                          )
        # print("Response ", response)
        imports = response[0]
        if imports:
            self.import_ris_file(imports[0])

    def import_ris_file(self, filepath):
        """ Open file and extract RIS information.
        List tags: 'A1', 'A2', 'A3', 'A4', 'AU', 'KW', 'N1'  # authors, KW keywords, N1 Notes
        """

        #list_tags = rispy.LIST_TYPE_TAGS
        #print("List tags ", list_tags)
        tag_keys = rispy.TAG_KEY_MAPPING
        print("Tag keys ", tag_keys)

        tagmap = ['type_of_reference', 'primary_title', 'first_authors', 'secondary_authors', 'publication_year',
                  'volume', 'number', 'publisher', 'place_published', 'issn', 'doi', 'edition', 'journal_name',
                  'start_page', 'keywords', 'url', 'id']

        print("filepath", filepath)
        with open(filepath, 'r') as ris_file:
            entries = rispy.load(ris_file)
        for entry in entries:
            print(entry)
            # not all keys are used, but like this tagmap order,so doing a for loop on the tagmap items
            for tm in tagmap:
                try:
                    if isinstance(entry[tm], list):
                        data = "; ".join(entry[tm])
                    else:
                        data = entry[tm]
                    print(tm + ": " + data)
                except KeyError:
                    print(" No item  for tag: " + tm)
            print("================")
