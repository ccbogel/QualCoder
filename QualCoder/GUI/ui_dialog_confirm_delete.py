# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_confirm_delete.ui'
#
# Created: Fri Dec 28 23:53:21 2018
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_confirmDelete(object):
    def setupUi(self, Dialog_confirmDelete):
        Dialog_confirmDelete.setObjectName("Dialog_confirmDelete")
        Dialog_confirmDelete.resize(400, 243)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_confirmDelete)
        self.buttonBox.setGeometry(QtCore.QRect(290, 20, 81, 241))
        self.buttonBox.setOrientation(QtCore.Qt.Vertical)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.label = QtWidgets.QLabel(Dialog_confirmDelete)
        self.label.setGeometry(QtCore.QRect(30, 20, 251, 201))
        self.label.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop)
        self.label.setWordWrap(True)
        self.label.setObjectName("label")

        self.retranslateUi(Dialog_confirmDelete)
        self.buttonBox.accepted.connect(Dialog_confirmDelete.accept)
        self.buttonBox.rejected.connect(Dialog_confirmDelete.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_confirmDelete)

    def retranslateUi(self, Dialog_confirmDelete):
        _translate = QtCore.QCoreApplication.translate
        Dialog_confirmDelete.setWindowTitle(_translate("Dialog_confirmDelete", "Confirm Delete"))
        self.label.setText(_translate("Dialog_confirmDelete", "TextLabel"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_confirmDelete = QtWidgets.QDialog()
    ui = Ui_Dialog_confirmDelete()
    ui.setupUi(Dialog_confirmDelete)
    Dialog_confirmDelete.show()
    sys.exit(app.exec_())

