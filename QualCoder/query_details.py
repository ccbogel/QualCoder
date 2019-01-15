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

from PyQt5.QtWidgets import QDialog, QMessageBox
from GUI.ui_queryDetails import Ui_Dialog_QueryDetails
import re
import os
import logging

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogQueryDetails(QDialog):

    queryname = None
    settings = None

    def __init__(self, parent, settings, queryname, sql):
        ''' Note, need to comment out the connection accept signal line in
        GUI/ui_Dialog_QueryDetails.py.
         Otherwise get a double-up of accept signals. '''

        super(DialogQueryDetails, self).__init__(parent)
        self.settings = settings
        self.queryname = queryname
        self.sql = sql

        # Set up the user interface from Designer.
        self.ui = Ui_Dialog_QueryDetails()
        self.ui.setupUi(self)
        self.ui.lineEdit_QueryName.setText(self.queryname)
        cur = self.settings['conn'].cursor()
        cur.execute("select notes from zzzz_queries where queryname=?", [self.queryname, ])
        qresults = cur.fetchone()
        description = ""
        if qresults is not None:
            description = qresults[0]
        self.ui.textEdit_description.setText(description)

        self.ui.buttonBox.accepted.connect(self.accept)
        self.ui.buttonBox.rejected.connect(self.reject)

    def accept(self):
        ''' Finalise query details.
        Get dialog text and return query details to RunSQL.
        Requires current group names and user query names '''

        queryDetailsGood = True
        queryname = str(self.ui.lineEdit_QueryName.text())
        # check there is a query name
        if queryname == "":
            QMessageBox.warning(None, "Warning", "No query name entered")
            self.queryDetails = []
            super(DialogQueryDetails, self).reject()
            return
        # check for acceptable query name
        if re.match("^[a-zA-Z_][a-zA-Z0-9_]*$", queryname) is None:
            QMessageBox.warning(None, "Query Name Error",
            "The name must contain only letters and numbers or '_' and must not start with a number.")
            return
        # check if query name is already in use and ask to overwrite
        nameExists = False
        cur = self.settings['conn'].cursor()
        cur.execute("select queryname from zzzz_queries where queryname=?", [queryname, ])
        qresults = cur.fetchone()
        if qresults is not None:
            nameExists = True
        if nameExists:
            overwrite = QMessageBox.question(None, 'Query name exists',
            "Do you want to overwrite this query?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if overwrite == QMessageBox.No:
                queryDetailsGood = False
        notes = str(self.ui.textEdit_description.toPlainText())
        if notes is None:
            notes = ""
        if queryDetailsGood is True:
            queryDetails = [queryname, self.sql, notes]
            cur = self.settings['conn'].cursor()
            sql = "delete from zzzz_queries where queryname=?"
            cur.execute(sql, [queryname, ])
            sql = "insert into zzzz_queries (queryname, query, notes) values(?, ?, ?)"
            cur.execute(sql, queryDetails)
            self.settings['conn'].commit()
        super(DialogQueryDetails, self).accept()

    def reject(self):
        ''' cancel pressed '''

        super(DialogQueryDetails, self).reject()
