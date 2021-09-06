# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_save_query.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DialogSaveQuery(object):
    def setupUi(self, DialogSaveQuery):
        DialogSaveQuery.setObjectName("DialogSaveQuery")
        DialogSaveQuery.resize(379, 227)
        self.verticalLayout = QtWidgets.QVBoxLayout(DialogSaveQuery)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label_name = QtWidgets.QLabel(DialogSaveQuery)
        self.label_name.setObjectName("label_name")
        self.verticalLayout.addWidget(self.label_name)
        self.lineEdit_name = QtWidgets.QLineEdit(DialogSaveQuery)
        self.lineEdit_name.setObjectName("lineEdit_name")
        self.verticalLayout.addWidget(self.lineEdit_name)
        self.label = QtWidgets.QLabel(DialogSaveQuery)
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.lineEdit_group = QtWidgets.QLineEdit(DialogSaveQuery)
        self.lineEdit_group.setObjectName("lineEdit_group")
        self.verticalLayout.addWidget(self.lineEdit_group)
        self.textEdit = QtWidgets.QTextEdit(DialogSaveQuery)
        self.textEdit.setReadOnly(True)
        self.textEdit.setObjectName("textEdit")
        self.verticalLayout.addWidget(self.textEdit)
        self.buttonBox = QtWidgets.QDialogButtonBox(DialogSaveQuery)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(DialogSaveQuery)
        self.buttonBox.accepted.connect(DialogSaveQuery.accept)
        self.buttonBox.rejected.connect(DialogSaveQuery.reject)
        QtCore.QMetaObject.connectSlotsByName(DialogSaveQuery)

    def retranslateUi(self, DialogSaveQuery):
        _translate = QtCore.QCoreApplication.translate
        DialogSaveQuery.setWindowTitle(_translate("DialogSaveQuery", "Save Query"))
        self.label_name.setText(_translate("DialogSaveQuery", "Query name:"))
        self.label.setText(_translate("DialogSaveQuery", "Query Group"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    DialogSaveQuery = QtWidgets.QDialog()
    ui = Ui_DialogSaveQuery()
    ui.setupUi(DialogSaveQuery)
    DialogSaveQuery.show()
    sys.exit(app.exec_())
