# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_manage_files.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_manage_files(object):
    def setupUi(self, Dialog_manage_files):
        Dialog_manage_files.setObjectName("Dialog_manage_files")
        Dialog_manage_files.resize(794, 560)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_manage_files)
        self.gridLayout.setObjectName("gridLayout")
        self.tableWidget = QtWidgets.QTableWidget(Dialog_manage_files)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(0)
        self.gridLayout.addWidget(self.tableWidget, 3, 0, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(Dialog_manage_files)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 60))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.pushButton_view = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_view.setGeometry(QtCore.QRect(10, 10, 91, 36))
        self.pushButton_view.setObjectName("pushButton_view")
        self.pushButton_create = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_create.setGeometry(QtCore.QRect(230, 10, 101, 36))
        self.pushButton_create.setObjectName("pushButton_create")
        self.pushButton_export = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_export.setGeometry(QtCore.QRect(550, 10, 101, 36))
        self.pushButton_export.setObjectName("pushButton_export")
        self.pushButton_delete = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_delete.setGeometry(QtCore.QRect(660, 10, 111, 36))
        self.pushButton_delete.setObjectName("pushButton_delete")
        self.pushButton_import = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_import.setGeometry(QtCore.QRect(110, 10, 111, 36))
        self.pushButton_import.setObjectName("pushButton_import")
        self.pushButton_add_attribute = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_add_attribute.setGeometry(QtCore.QRect(340, 10, 201, 36))
        self.pushButton_add_attribute.setObjectName("pushButton_add_attribute")
        self.gridLayout.addWidget(self.groupBox, 1, 0, 1, 1)
        self.label_fcount = QtWidgets.QLabel(Dialog_manage_files)
        self.label_fcount.setObjectName("label_fcount")
        self.gridLayout.addWidget(self.label_fcount, 2, 0, 1, 1)

        self.retranslateUi(Dialog_manage_files)
        QtCore.QMetaObject.connectSlotsByName(Dialog_manage_files)

    def retranslateUi(self, Dialog_manage_files):
        _translate = QtCore.QCoreApplication.translate
        Dialog_manage_files.setWindowTitle(_translate("Dialog_manage_files", "Files"))
        self.pushButton_view.setText(_translate("Dialog_manage_files", "View"))
        self.pushButton_create.setText(_translate("Dialog_manage_files", "Create"))
        self.pushButton_export.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Make sure the file name does not contain unusual characters such as \': ; &quot; \' otherwise it will raise an error when trying to save this file. Rename the file if needed.</p></body></html>"))
        self.pushButton_export.setText(_translate("Dialog_manage_files", "Export"))
        self.pushButton_delete.setText(_translate("Dialog_manage_files", "Delete"))
        self.pushButton_import.setText(_translate("Dialog_manage_files", "Import"))
        self.pushButton_add_attribute.setText(_translate("Dialog_manage_files", "Add Attribute"))
        self.label_fcount.setText(_translate("Dialog_manage_files", "Files:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_manage_files = QtWidgets.QDialog()
    ui = Ui_Dialog_manage_files()
    ui.setupUi(Dialog_manage_files)
    Dialog_manage_files.show()
    sys.exit(app.exec_())
