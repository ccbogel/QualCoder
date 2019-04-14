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

from PyQt5 import QtWidgets
from GUI.ui_dialog_add_item import Ui_Dialog_add_item
import os
import sys
import logging
import traceback

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


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogAddItemName([{"name":"aaa"}, {"name":"bbb"}], "title")
    ui.show()
    sys.exit(app.exec_())

