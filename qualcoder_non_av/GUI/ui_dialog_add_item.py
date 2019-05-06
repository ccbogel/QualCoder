# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_add_item.ui'
#
# Created: Thu Jan  3 08:54:05 2019
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_add_item(object):
    def setupUi(self, Dialog_add_item):
        Dialog_add_item.setObjectName("Dialog_add_item")
        Dialog_add_item.resize(400, 142)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_add_item)
        self.buttonBox.setGeometry(QtCore.QRect(170, 90, 201, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.lineEdit = QtWidgets.QLineEdit(Dialog_add_item)
        self.lineEdit.setGeometry(QtCore.QRect(20, 40, 351, 27))
        self.lineEdit.setObjectName("lineEdit")
        self.label = QtWidgets.QLabel(Dialog_add_item)
        self.label.setGeometry(QtCore.QRect(20, 20, 141, 17))
        self.label.setObjectName("label")

        self.retranslateUi(Dialog_add_item)
        self.buttonBox.accepted.connect(Dialog_add_item.accept)
        self.buttonBox.rejected.connect(Dialog_add_item.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_add_item)
        Dialog_add_item.setTabOrder(self.lineEdit, self.buttonBox)

    def retranslateUi(self, Dialog_add_item):
        _translate = QtCore.QCoreApplication.translate
        Dialog_add_item.setWindowTitle(_translate("Dialog_add_item", "Add Code"))
        self.label.setText(_translate("Dialog_add_item", "Enter text below:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_add_item = QtWidgets.QDialog()
    ui = Ui_Dialog_add_item()
    ui.setupUi(Dialog_add_item)
    Dialog_add_item.show()
    sys.exit(app.exec_())

