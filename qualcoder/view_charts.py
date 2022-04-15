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

import base64
from collections import Counter
from copy import deepcopy
import logging
import math
import os
import pandas as pd
import plotly.express as px
import sys
import traceback

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QDialog

from .color_selector import TextColor
from .GUI.base64_helper import *
from .GUI.ui_dialog_charts import Ui_DialogCharts
from .helpers import DialogCodeInAllFiles, ExportDirectoryPathDialog, Message
from .memo import DialogMemo


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    txt = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(txt)
    logger.error(_("Uncaught exception: ") + txt)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(txt)
    mb.exec()


class ViewCharts(QDialog):
    """ Dialog to view various charts of codes and categories.
    """

    app = None
    conn = None
    settings = None
    categories = []
    code_names = []
    dialog_list = []

    def __init__(self, app):
        """ Set up the dialog. """

        sys.excepthook = exception_handler
        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogCharts()
        self.ui.setupUi(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        '''pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_export.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export.pressed.connect(self.export_image)'''

        self.code_names, self.categories = app.get_codes_categories()
        self.ui.comboBox_pie_charts.currentIndexChanged.connect(self.show_pie_chart)
        pie_combobox_list = ['', 'Code frequency',
                         'Code by characters',
                         'Code by image area',
                         'Code by audio/video segments'
                         ]
        self.ui.comboBox_pie_charts.addItems(pie_combobox_list)
        self.ui.comboBox_bar_charts.currentIndexChanged.connect(self.show_bar_chart)
        bar_combobox_list = ['', 'Code frequency',
                         'Code by characters',
                         'Code by image area',
                         'Code by audio/video segments'
                         ]
        self.ui.comboBox_bar_charts.addItems(bar_combobox_list)


    def show_bar_chart(self):
        """ https://www.tutorialspoint.com/plotly/plotly_bar_and_pie_chart.htm
        """

        chart_type = self.ui.comboBox_bar_charts.currentText()
        if chart_type == "":
            return
        if chart_type == "Code frequency":
            self.barchart_code_frequency()
        if chart_type == "Code by characters":
            self.barchart_code_volume_by_characters()
        if chart_type == "Code by image area":
            self.barchart_code_volume_by_area()
        if chart_type == "Code by audio/video segments":
            self.barchart_code_volume_by_segments()

    def barchart_code_frequency(self):
        """ Count of codes across text, images and A/V.
        """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select count(cid) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            sql = "select count(cid) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res_image = cur.fetchone()
            sql = "select count(cid) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res_av = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0] + res_image[0] + res_av[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Count': values}
        df = pd.DataFrame(data)
        fig = px.bar(df, x='Code names', y='Count', title='Code count - text, images and Audio/Video')
        fig.show()

    def barchart_code_volume_by_characters(self):
        """ Count of codes in files text by character volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Character count': values}
        df = pd.DataFrame(data)
        fig = px.bar(df, x='Code names', y='Character count', title='Code text by character count')
        fig.show()

    def barchart_code_volume_by_area(self):
        """ Codes by image area volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Pixels': values}
        df = pd.DataFrame(data)
        fig = px.bar(df, x='Code names', y='Pixels', title='Code volume by image area (pixels)')
        fig.show()

    def barchart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Segments': values}
        df = pd.DataFrame(data)
        fig = px.bar(df, x='Code names', y='Segments', title='Code volume by audio/video segments (milliseconds)')
        fig.show()

    def show_pie_chart(self):
        """
        https://plotly.com/python/pie-charts/
        https://www.tutorialspoint.com/plotly/plotly_bar_and_pie_chart.htm
        """

        chart_type = self.ui.comboBox_pie_charts.currentText()
        if chart_type == "":
            return
        '''
        #df = pd.DataFrame(dict(a=[1, 3, 2], b=[3, 2, 1]))
        #fig = px.pie(df, values=values, names=labels, title='test')
        df = px.data.gapminder().query("year == 2007").query("continent == 'Europe'")
        df.loc[df['pop'] < 2.e6, 'country'] = 'Other countries'  # Represent only large countries
        fig = px.pie(df, values='pop', names='country', title='Population of European continent')
        fig.show()'''

        if chart_type == "Code frequency":
            self.piechart_code_frequency()
        if chart_type == "Code by characters":
            self.piechart_code_volume_by_characters()
        if chart_type == "Code by image area":
            self.piechart_code_volume_by_area()
        if chart_type == "Code by audio/video segments":
            self.piechart_code_volume_by_segments()

    def piechart_code_frequency(self):
        """ Count of codes across text, images and A/V.
        can render differntly: fig.show(renderer="svg")
        """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select count(cid) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            sql = "select count(cid) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res_image = cur.fetchone()
            sql = "select count(cid) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res_av = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0] + res_image[0] + res_av[0])
        fig = px.pie(values=values, names=labels, title='Code count - text, images and Audio/Video')
        '''img_bytes = fig.to_image(format="png") # pip install kaledio
        encoding = base64.b64encode(img_bytes).decode()
        img_b64 = "data:image/png;base64," + encoding
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(encoding), "png")
        self.ui.label_bar_chart.setPixmap(pm)'''
        fig.show()

    def piechart_code_volume_by_characters(self):
        """ Count of codes in files text by character volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0])
        fig = px.pie(values=values, names=labels, title='Code text by character count')
        fig.show()

    def piechart_code_volume_by_area(self):
        """ Codes by image area volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0])
        fig = px.pie(values=values, names=labels, title='Code volume by image area (pixels)')
        fig.show()

    def piechart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0])
        #df = pd.DataFrame(dict(a=[1, 3, 2], b=[3, 2, 1]))
        fig = px.pie(values=values, names=labels, title='Code volume by audio/video segments (milliseconds)')
        fig.show()
