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
        self.groupBox.setMinimumSize(QtCore.QSize(0, 40))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 40))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.pushButton_view = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_view.setGeometry(QtCore.QRect(10, 3, 36, 36))
        self.pushButton_view.setText("")
        self.pushButton_view.setObjectName("pushButton_view")
        self.pushButton_create = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_create.setGeometry(QtCore.QRect(110, 3, 36, 36))
        self.pushButton_create.setText("")
        self.pushButton_create.setObjectName("pushButton_create")
        self.pushButton_export = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_export.setGeometry(QtCore.QRect(160, 3, 36, 36))
        self.pushButton_export.setText("")
        self.pushButton_export.setObjectName("pushButton_export")
        self.pushButton_delete = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_delete.setGeometry(QtCore.QRect(540, 3, 36, 36))
        self.pushButton_delete.setText("")
        self.pushButton_delete.setObjectName("pushButton_delete")
        self.pushButton_import = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_import.setGeometry(QtCore.QRect(60, 3, 36, 36))
        self.pushButton_import.setText("")
        self.pushButton_import.setObjectName("pushButton_import")
        self.pushButton_add_attribute = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_add_attribute.setGeometry(QtCore.QRect(360, 3, 36, 36))
        self.pushButton_add_attribute.setText("")
        self.pushButton_add_attribute.setObjectName("pushButton_add_attribute")
        self.pushButton_link = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_link.setGeometry(QtCore.QRect(210, 3, 36, 36))
        self.pushButton_link.setText("")
        self.pushButton_link.setObjectName("pushButton_link")
        self.pushButton_import_from_linked = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_import_from_linked.setGeometry(QtCore.QRect(260, 3, 36, 36))
        self.pushButton_import_from_linked.setText("")
        self.pushButton_import_from_linked.setObjectName("pushButton_import_from_linked")
        self.pushButton_export_to_linked = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_export_to_linked.setGeometry(QtCore.QRect(310, 3, 36, 36))
        self.pushButton_export_to_linked.setText("")
        self.pushButton_export_to_linked.setObjectName("pushButton_export_to_linked")
        self.pushButton_export_attributes = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_export_attributes.setGeometry(QtCore.QRect(450, 4, 36, 36))
        self.pushButton_export_attributes.setText("")
        self.pushButton_export_attributes.setObjectName("pushButton_export_attributes")
        self.gridLayout.addWidget(self.groupBox, 1, 0, 1, 1)
        self.label_fcount = QtWidgets.QLabel(Dialog_manage_files)
        self.label_fcount.setObjectName("label_fcount")
        self.gridLayout.addWidget(self.label_fcount, 2, 0, 1, 1)

        self.retranslateUi(Dialog_manage_files)
        QtCore.QMetaObject.connectSlotsByName(Dialog_manage_files)

    def retranslateUi(self, Dialog_manage_files):
        _translate = QtCore.QCoreApplication.translate
        Dialog_manage_files.setWindowTitle(_translate("Dialog_manage_files", "Files"))
        self.pushButton_view.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>View file</p></body></html>"))
        self.pushButton_create.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Create a text file</p></body></html>"))
        self.pushButton_export.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Export selected file</p></body></html>"))
        self.pushButton_delete.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Select files for deletion</p></body></html>"))
        self.pushButton_import.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Import file into project folder</p></body></html>"))
        self.pushButton_add_attribute.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Add attribute</p></body></html>"))
        self.pushButton_link.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Link to a file that is outside the project folder</p></body></html>"))
        self.pushButton_import_from_linked.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Import linked file into project folder</p></body></html>"))
        self.pushButton_export_to_linked.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Export file from project folder as a linked file</p></body></html>"))
        self.pushButton_export_attributes.setToolTip(_translate("Dialog_manage_files", "<html><head/><body><p>Export attributes as csv file</p></body></html>"))
        self.label_fcount.setText(_translate("Dialog_manage_files", "Files:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_manage_files = QtWidgets.QDialog()
    ui = Ui_Dialog_manage_files()
    ui.setupUi(Dialog_manage_files)
    Dialog_manage_files.show()
    sys.exit(app.exec_())
