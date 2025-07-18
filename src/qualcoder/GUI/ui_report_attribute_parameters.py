# Form implementation generated from reading ui file 'ui_report_attribute_parameters.ui'
#
# Created by: PyQt6 UI code generator 6.5.2
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog_report_attribute_parameters(object):
    def setupUi(self, Dialog_report_attribute_parameters):
        Dialog_report_attribute_parameters.setObjectName("Dialog_report_attribute_parameters")
        Dialog_report_attribute_parameters.resize(758, 509)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog_report_attribute_parameters)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtWidgets.QGroupBox(parent=Dialog_report_attribute_parameters)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 100))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 100))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.pushButton_load_filter = QtWidgets.QPushButton(parent=self.groupBox)
        self.pushButton_load_filter.setGeometry(QtCore.QRect(510, 10, 30, 30))
        self.pushButton_load_filter.setText("")
        self.pushButton_load_filter.setObjectName("pushButton_load_filter")
        self.label = QtWidgets.QLabel(parent=self.groupBox)
        self.label.setGeometry(QtCore.QRect(10, 0, 361, 85))
        self.label.setMinimumSize(QtCore.QSize(0, 85))
        self.label.setMaximumSize(QtCore.QSize(16777215, 80))
        self.label.setWordWrap(True)
        self.label.setObjectName("label")
        self.pushButton_save_filter = QtWidgets.QPushButton(parent=self.groupBox)
        self.pushButton_save_filter.setGeometry(QtCore.QRect(550, 10, 30, 30))
        self.pushButton_save_filter.setText("")
        self.pushButton_save_filter.setObjectName("pushButton_save_filter")
        self.pushButton_clear = QtWidgets.QPushButton(parent=self.groupBox)
        self.pushButton_clear.setGeometry(QtCore.QRect(510, 43, 131, 28))
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.radioButton_and = QtWidgets.QRadioButton(parent=self.groupBox)
        self.radioButton_and.setGeometry(QtCore.QRect(380, 10, 90, 20))
        self.radioButton_and.setMinimumSize(QtCore.QSize(90, 0))
        self.radioButton_and.setObjectName("radioButton_and")
        self.radioButton_or = QtWidgets.QRadioButton(parent=self.groupBox)
        self.radioButton_or.setGeometry(QtCore.QRect(380, 50, 80, 20))
        self.radioButton_or.setMinimumSize(QtCore.QSize(80, 0))
        self.radioButton_or.setChecked(True)
        self.radioButton_or.setObjectName("radioButton_or")
        self.pushButton_delete_filter = QtWidgets.QPushButton(parent=self.groupBox)
        self.pushButton_delete_filter.setGeometry(QtCore.QRect(590, 10, 30, 30))
        self.pushButton_delete_filter.setText("")
        self.pushButton_delete_filter.setObjectName("pushButton_delete_filter")
        self.verticalLayout.addWidget(self.groupBox)
        self.tableWidget = QtWidgets.QTableWidget(parent=Dialog_report_attribute_parameters)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(5)
        self.tableWidget.setRowCount(0)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(0, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(1, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(2, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(3, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(4, item)
        self.verticalLayout.addWidget(self.tableWidget)
        self.buttonBox = QtWidgets.QDialogButtonBox(parent=Dialog_report_attribute_parameters)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(Dialog_report_attribute_parameters)
        self.buttonBox.rejected.connect(Dialog_report_attribute_parameters.reject) # type: ignore
        self.buttonBox.accepted.connect(Dialog_report_attribute_parameters.accept) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog_report_attribute_parameters)

    def retranslateUi(self, Dialog_report_attribute_parameters):
        _translate = QtCore.QCoreApplication.translate
        Dialog_report_attribute_parameters.setWindowTitle(_translate("Dialog_report_attribute_parameters", "Attribute selection parameters"))
        self.pushButton_load_filter.setToolTip(_translate("Dialog_report_attribute_parameters", "<html><head/><body><p>Load filter settings</p></body></html>"))
        self.label.setText(_translate("Dialog_report_attribute_parameters", "Select parameters for the attributes. \n"
"between requires 2 values separated by ; e.g. 1;100\n"
" in and not in require 1 or more values separated by ;\n"
"Wildcards for \'like\' are % and _"))
        self.pushButton_save_filter.setToolTip(_translate("Dialog_report_attribute_parameters", "<html><head/><body><p>Save filter settings.</p><p>Do not use apostrophe or comma in any values.</p></body></html>"))
        self.pushButton_clear.setToolTip(_translate("Dialog_report_attribute_parameters", "Clear attribute selections"))
        self.pushButton_clear.setText(_translate("Dialog_report_attribute_parameters", "Clear"))
        self.radioButton_and.setToolTip(_translate("Dialog_report_attribute_parameters", "<html><head/><body><p>Boolean And</p><p>For all parameter selections</p></body></html>"))
        self.radioButton_and.setText(_translate("Dialog_report_attribute_parameters", "and"))
        self.radioButton_or.setToolTip(_translate("Dialog_report_attribute_parameters", "<html><head/><body><p>Boolean Or</p><p>For all parameter selections</p></body></html>"))
        self.radioButton_or.setText(_translate("Dialog_report_attribute_parameters", "or"))
        self.pushButton_delete_filter.setToolTip(_translate("Dialog_report_attribute_parameters", "Delete saved filter settings"))
        item = self.tableWidget.horizontalHeaderItem(0)
        item.setText(_translate("Dialog_report_attribute_parameters", "Attribute"))
        item = self.tableWidget.horizontalHeaderItem(1)
        item.setText(_translate("Dialog_report_attribute_parameters", "Source"))
        item = self.tableWidget.horizontalHeaderItem(2)
        item.setText(_translate("Dialog_report_attribute_parameters", "Type"))
        item = self.tableWidget.horizontalHeaderItem(3)
        item.setText(_translate("Dialog_report_attribute_parameters", "Operator"))
        item = self.tableWidget.horizontalHeaderItem(4)
        item.setText(_translate("Dialog_report_attribute_parameters", "Value list"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_report_attribute_parameters = QtWidgets.QDialog()
    ui = Ui_Dialog_report_attribute_parameters()
    ui.setupUi(Dialog_report_attribute_parameters)
    Dialog_report_attribute_parameters.show()
    sys.exit(app.exec())
