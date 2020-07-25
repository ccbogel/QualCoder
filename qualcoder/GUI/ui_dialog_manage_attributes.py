# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_manage_attributes.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_manage_attributes(object):
    def setupUi(self, Dialog_manage_attributes):
        Dialog_manage_attributes.setObjectName("Dialog_manage_attributes")
        Dialog_manage_attributes.resize(546, 569)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_manage_attributes)
        self.gridLayout.setObjectName("gridLayout")
        self.pushButton_add = QtWidgets.QPushButton(Dialog_manage_attributes)
        self.pushButton_add.setObjectName("pushButton_add")
        self.gridLayout.addWidget(self.pushButton_add, 0, 0, 1, 1)
        self.tableWidget = QtWidgets.QTableWidget(Dialog_manage_attributes)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(0)
        self.gridLayout.addWidget(self.tableWidget, 2, 0, 1, 2)
        self.pushButton_delete = QtWidgets.QPushButton(Dialog_manage_attributes)
        self.pushButton_delete.setObjectName("pushButton_delete")
        self.gridLayout.addWidget(self.pushButton_delete, 0, 1, 1, 1)
        self.label = QtWidgets.QLabel(Dialog_manage_attributes)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)

        self.retranslateUi(Dialog_manage_attributes)
        QtCore.QMetaObject.connectSlotsByName(Dialog_manage_attributes)

    def retranslateUi(self, Dialog_manage_attributes):
        _translate = QtCore.QCoreApplication.translate
        Dialog_manage_attributes.setWindowTitle(_translate("Dialog_manage_attributes", "Attributes"))
        self.pushButton_add.setText(_translate("Dialog_manage_attributes", "Add"))
        self.pushButton_delete.setText(_translate("Dialog_manage_attributes", "Delete"))
        self.label.setText(_translate("Dialog_manage_attributes", "Attributes:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_manage_attributes = QtWidgets.QDialog()
    ui = Ui_Dialog_manage_attributes()
    ui.setupUi(Dialog_manage_attributes)
    Dialog_manage_attributes.show()
    sys.exit(app.exec_())
