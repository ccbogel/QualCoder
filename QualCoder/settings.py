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
https://qualcoder.wordpress.com/
'''

from PyQt5 import QtGui, QtWidgets
from GUI.ui_dialog_settings import Ui_Dialog_settings
import os
import sys
import logging
import traceback

home = os.path.expanduser('~')
path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error("Uncaught exception:\n" + text)
    QtWidgets.QMessageBox.critical(None, 'Uncaught Exception ', text)


class DialogSettings(QtWidgets.QDialog):
    ''' Settings for the coder name, coder table and to display ids.
    '''

    settings = {}

    def __init__(self, settings, parent=None):

        sys.excepthook = exception_handler
        self.settings = settings
        super(QtWidgets.QDialog, self).__init__(parent)  # overrride accept method
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_settings()
        self.ui.setupUi(self)
        new_font = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(new_font)
        self.ui.fontComboBox.setCurrentFont(new_font)
        # get coder names from code_text (and from other? may be images?)
        sql = "select distinct owner from code_text"
        coders = [""]
        if settings['conn'] is not None:
            cur = self.settings['conn'].cursor()
            cur.execute(sql)
            results = cur.fetchall()
            for row in results:
                coders.append(row[0])
        self.ui.comboBox_coders.addItems(coders)
        self.ui.spinBox.setValue(self.settings['fontsize'])
        self.ui.spinBox_treefontsize.setValue(self.settings['treefontsize'])
        self.ui.lineEdit_coderName.setText(self.settings['codername'])
        self.ui.comboBox_coders.currentIndexChanged.connect(self.comboBox_coder_changed)
        if self.settings['showIDs'] is True:
            self.ui.checkBox.setChecked(True)
        else:
            self.ui.checkBox.setChecked(False)
        if self.settings['directory'] == "":
            self.settings['directory'] = os.path.expanduser("~")
        self.ui.label_directory.setText(self.settings['directory'])
        self.ui.pushButton_choose_directory.clicked.connect(self.choose_directory)

    def comboBox_coder_changed(self):
        ''' Set the coder name to the current selection. '''

        logger.info("coder changed to: " + self.ui.comboBox_coders.currentText())
        self.ui.lineEdit_coderName.setText(self.ui.comboBox_coders.currentText())

    def choose_directory(self):
        ''' Choose default project directory. '''

        directory = QtWidgets.QFileDialog.getExistingDirectory(self,
            'Choose project directory', self.settings['directory'])
        if directory == "":
            return
        self.ui.label_directory.setText(directory)

    def accept(self):
        self.settings['codername'] = self.ui.lineEdit_coderName.text()
        if self.settings['codername'] == "":
            self.settings['codername'] = "default"
        self.settings['font'] = self.ui.fontComboBox.currentText()
        self.settings['fontsize'] = self.ui.spinBox.value()
        self.settings['treefontsize'] = self.ui.spinBox_treefontsize.value()
        self.settings['directory'] = self.ui.label_directory.text()
        if self.ui.checkBox.isChecked():
            self.settings['showIDs'] = True
        else:
            self.settings['showIDs'] = False
        self.save_settings()
        self.close()

    def save_settings(self):
        ''' Save settings to text file in user's home directory. '''

        txt = self.settings['codername'] + "\n"
        txt += self.settings['font'] + "\n"
        txt += str(self.settings['fontsize']) + "\n"
        txt += str(self.settings['treefontsize']) + "\n"
        txt += self.settings['directory'] + "\n"
        txt += str(self.settings['showIDs'])
        with open(home + '/.qualcoder/QualCoder_settings.txt', 'w') as f:
            f.write(txt)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogSettings()
    ui.show()
    sys.exit(app.exec_())

