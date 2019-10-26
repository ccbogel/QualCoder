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

from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, pyqtSignal
import os
import sys
import logging
import traceback

try:
    from GUI.ui_dialog_add_item import Ui_Dialog_add_item
except:
    from .GUI.ui_dialog_add_item import Ui_Dialog_add_item

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception") + ":\n" + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogAddItemName(QtWidgets.QDialog):
    """
    Dialog to get a new code or code category from user.
    Also used for Case and File adding attributes.
    Requires a name for Dialog title (and label in setupUI)
    Requires a list of dictionary 'name' items.
    Dialog returns ok if the item is not a duplicate of a name in the list.
    Returns one item through getnewItem method.
    """

    newItem = None
    existingItems = []
    Dialog_addItem = None
    typeOfItem = ""  # for dialog title and label: Code or Category

    def __init__(self, items, title, parent=None):
        super(DialogAddItemName, self).__init__(parent)  # overrride accept method

        sys.excepthook = exception_handler
        for i in items:
            self.existingItems.append(i['name'])

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_add_item()
        self.ui.setupUi(self)
        self.setWindowTitle(title)
        self.ui.lineEdit.setFocus(True)

    def accept(self):
        """ On pressing accept button, check there is no duplicate.
        If no duplicate then accept end close the dialog """

        thisItem = str(self.ui.lineEdit.text())
        duplicate = False
        if thisItem in self.existingItems:
            duplicate = True
            QtWidgets.QMessageBox.warning(None, _("Duplicated"), _("This already exists"))
            return
        if duplicate is False:
            self.newItem = thisItem
        self.close()

    def get_new_name(self):
        ''' Get the new name '''

        return self.newItem

class DialogLinkTo(QtWidgets.QDialog):
    """
    Dialog to get a new code or code category from user.
    Also used for Case and File adding attributes.
    Requires a name for Dialog title (and label in setupUI)
    Requires a list of dictionary 'name' items.
    Dialog returns ok if the item is not a duplicate of a name in the list.
    Returns one item through getnewItem method.
    """

    def __init__(self, model, linktypes, fromname, parent=None):
        super(DialogLinkTo, self).__init__(parent)  # overrride accept method
        self.linktype = None
        self.linkitem = None
        self.linktypes = linktypes
        self.model = model

        self.setupUi()
        completer = QtWidgets.QCompleter()#[x['name'] for x in model.nativedata])
        completer.setCompletionMode(QtWidgets.QCompleter.InlineCompletion)
        completer.setCompletionColumn(0)
        completer.setCompletionRole(Qt.DisplayRole)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setModel(model)
        self.lineEdit.setCompleter(completer)

        self.combo.setModel(linktypes)
        self.setWindowTitle('Create link to %s'%fromname)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed);

    def setupUi(self):
        self.setObjectName("CreateLinkTo")
        self.resize(400, 142)
        self.setFixedSize(400, 142)
        self.buttonBox = QtWidgets.QDialogButtonBox(self)
        self.buttonBox.setGeometry(QtCore.QRect(170, 90, 201, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.lineEdit = QtWidgets.QLineEdit(self)
        self.lineEdit.setGeometry(QtCore.QRect(20, 40, 351, 27))
        self.lineEdit.setObjectName("lineEdit")
        self.label = QtWidgets.QLabel("Link to:",self)
        self.label.setGeometry(QtCore.QRect(20, 20, 141, 17))
        self.label.setObjectName("label")
        self.labelc = QtWidgets.QLabel("Linktype:",self)
        self.labelc.setGeometry(QtCore.QRect(20, 70, 141, 17))
        self.labelc.setObjectName("linktype_label")
        self.combo = QtWidgets.QComboBox(self)
        self.combo.setGeometry(QtCore.QRect(20, 90, 141, 27))
        self.lineEdit.setObjectName("linktype")
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # QtCore.QMetaObject.connectSlotsByName(self)
        # self.setTabOrder(self.combo,self.lineEdit, self.buttonBox)
        self.lineEdit.setFocus(True)

    def accept(self):
        """ On pressing accept button, check there is no duplicate.
        If no duplicate then accept end close the dialog """

        thisItem = str(self.lineEdit.text())
        if thisItem in {v['name'] for v in self.model.nativedata.values()}:
            self.linkitem = thisItem
            self.linktype = self.linktypes.nativedata[self.combo.currentIndex()]
            self.close()
        else:
            QtWidgets.QMessageBox.warning(None, _("Not existing"), _("This does not exists"))


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogAddItemName([{"name":"aaa"}, {"name":"bbb"}], "title")
    ui.show()
    sys.exit(app.exec_())

