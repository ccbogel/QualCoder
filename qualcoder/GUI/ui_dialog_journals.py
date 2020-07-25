# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_journals.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_journals(object):
    def setupUi(self, Dialog_journals):
        Dialog_journals.setObjectName("Dialog_journals")
        Dialog_journals.resize(1085, 760)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_journals)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox = QtWidgets.QGroupBox(Dialog_journals)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 70))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 70))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.pushButton_create = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_create.setGeometry(QtCore.QRect(10, 10, 111, 27))
        self.pushButton_create.setObjectName("pushButton_create")
        self.pushButton_export = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_export.setGeometry(QtCore.QRect(130, 10, 111, 27))
        self.pushButton_export.setObjectName("pushButton_export")
        self.pushButton_delete = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_delete.setGeometry(QtCore.QRect(250, 10, 111, 27))
        self.pushButton_delete.setObjectName("pushButton_delete")
        self.label_jname = QtWidgets.QLabel(self.groupBox)
        self.label_jname.setGeometry(QtCore.QRect(485, 18, 571, 21))
        self.label_jname.setObjectName("label_jname")
        self.label_jcount = QtWidgets.QLabel(self.groupBox)
        self.label_jcount.setGeometry(QtCore.QRect(20, 50, 221, 20))
        self.label_jcount.setObjectName("label_jcount")
        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 1)
        self.splitter = QtWidgets.QSplitter(Dialog_journals)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.tableWidget = QtWidgets.QTableWidget(self.splitter)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(3)
        self.tableWidget.setRowCount(0)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(0, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(1, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(2, item)
        self.textEdit = QtWidgets.QTextEdit(self.splitter)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout.addWidget(self.splitter, 1, 0, 1, 1)

        self.retranslateUi(Dialog_journals)
        QtCore.QMetaObject.connectSlotsByName(Dialog_journals)

    def retranslateUi(self, Dialog_journals):
        _translate = QtCore.QCoreApplication.translate
        Dialog_journals.setWindowTitle(_translate("Dialog_journals", "Journals"))
        self.pushButton_create.setText(_translate("Dialog_journals", "Create"))
        self.pushButton_export.setText(_translate("Dialog_journals", "Export"))
        self.pushButton_delete.setText(_translate("Dialog_journals", "Delete"))
        self.label_jname.setText(_translate("Dialog_journals", "Journal:"))
        self.label_jcount.setText(_translate("Dialog_journals", "Journals: "))
        item = self.tableWidget.horizontalHeaderItem(0)
        item.setText(_translate("Dialog_journals", "Name"))
        item = self.tableWidget.horizontalHeaderItem(1)
        item.setText(_translate("Dialog_journals", "Date"))
        item = self.tableWidget.horizontalHeaderItem(2)
        item.setText(_translate("Dialog_journals", "Coder"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_journals = QtWidgets.QDialog()
    ui = Ui_Dialog_journals()
    ui.setupUi(Dialog_journals)
    Dialog_journals.show()
    sys.exit(app.exec_())
