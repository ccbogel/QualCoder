# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_information.ui'
#
# Created: Fri Dec  1 09:42:41 2017
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_information(object):
    def setupUi(self, Dialog_information):
        Dialog_information.setObjectName("Dialog_information")
        Dialog_information.resize(740, 533)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_information)
        self.gridLayout.setObjectName("gridLayout")
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_information)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.gridLayout.addWidget(self.buttonBox, 1, 0, 1, 1)
        self.textEdit = QtWidgets.QTextEdit(Dialog_information)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout.addWidget(self.textEdit, 0, 0, 1, 1)

        self.retranslateUi(Dialog_information)
        self.buttonBox.accepted.connect(Dialog_information.accept)
        self.buttonBox.rejected.connect(Dialog_information.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_information)

    def retranslateUi(self, Dialog_information):
        _translate = QtCore.QCoreApplication.translate
        Dialog_information.setWindowTitle(_translate("Dialog_information", "Information"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_information = QtWidgets.QDialog()
    ui = Ui_Dialog_information()
    ui.setupUi(Dialog_information)
    Dialog_information.show()
    sys.exit(app.exec_())

