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
'''

from Memo import Ui_Dialog_memo
from PyQt5 import QtGui
import re
import os
import logging

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class CodingSummary_OLD():
    """ Summary of codings """

    settings = None

    def __init__(self, settings):
        self.settings = settings
        text = ""

        cur = self.settings['conn'].cursor()
        sql = "select freecode.id, freecode.name, count (freecode.name) from freecode left join coding"\
        " on  coding.cid = freecode.id left join  coding2 on  coding2.cid =  freecode.id group by freecode.name"
        cur.execute(sql)
        result1 = cur.fetchall()
        text = "CODING SUMMARY\n"
        textrows = []

        # for each code get the average characters and average words
        for row in result1:
            tmp = str(row[1]) + ", id:" + str(row[0]) + ", Count: " + str(row[2])
            sql = "select cid, seltext, length(seltext) from (select cid, seltext from coding union"\
            " select cid, seltext from coding2) where cid =" + str(row[0])
            cur.execute(sql)
            result2 = cur.fetchall()
            charSum = 0
            wordSum = 0
            for row2 in result2:
                charSum += row2[2]
                wordSum += len(re.findall(r'\w+', row2[1])) # approximates word length; doesn't = 2 words

            if len(result2) > 0:
                avgChar = int(charSum / len(result2))
                avgWords = int(wordSum / len(result2))
            else:
                avgChar = 0
                avgWords = 0
            tmp += ", Avg chars: " + str(avgChar) + ", Avg words: " + str(avgWords)
            textrows.append(tmp)

        for row in textrows:
            text += row + "\n"

        Dialog_memo = QtGui.QDialog()
        ui = Ui_Dialog_memo(text)
        ui.setupUi(Dialog_memo, "Coding  summary")
        Dialog_memo.exec_()
