# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_memo.ui'
#
# Created: Fri Dec 28 09:00:41 2018
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_memo(object):
    def setupUi(self, Dialog_memo):
        Dialog_memo.setObjectName("Dialog_memo")
        Dialog_memo.resize(740, 533)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_memo)
        self.gridLayout.setObjectName("gridLayout")
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_memo)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.gridLayout.addWidget(self.buttonBox, 1, 0, 1, 1)
        self.textEdit = QtWidgets.QTextEdit(Dialog_memo)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout.addWidget(self.textEdit, 0, 0, 1, 1)

        self.retranslateUi(Dialog_memo)
        self.buttonBox.accepted.connect(Dialog_memo.accept)
        self.buttonBox.rejected.connect(Dialog_memo.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_memo)

    def retranslateUi(self, Dialog_memo):
        _translate = QtCore.QCoreApplication.translate
        Dialog_memo.setWindowTitle(_translate("Dialog_memo", "Memo"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_memo = QtWidgets.QDialog()
    ui = Ui_Dialog_memo()
    ui.setupUi(Dialog_memo)
    Dialog_memo.show()
    sys.exit(app.exec_())

