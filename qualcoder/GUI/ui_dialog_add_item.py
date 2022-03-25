# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_add_item.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_add_item(object):
    def setupUi(self, Dialog_add_item):
        Dialog_add_item.setObjectName("Dialog_add_item")
        Dialog_add_item.resize(400, 142)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog_add_item)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QtWidgets.QLabel(Dialog_add_item)
        self.label.setMaximumSize(QtCore.QSize(16777215, 40))
        self.label.setWordWrap(True)
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.lineEdit = QtWidgets.QLineEdit(Dialog_add_item)
        self.lineEdit.setObjectName("lineEdit")
        self.verticalLayout.addWidget(self.lineEdit)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_add_item)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

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
