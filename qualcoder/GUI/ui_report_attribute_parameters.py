# Form implementation generated from reading ui file 'ui_report_attribute_parameters.ui'
#
# Created by: PyQt6 UI code generator 6.3.1
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog_report_attribute_parameters(object):
    def setupUi(self, Dialog_report_attribute_parameters):
        Dialog_report_attribute_parameters.setObjectName("Dialog_report_attribute_parameters")
        Dialog_report_attribute_parameters.resize(758, 509)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_report_attribute_parameters)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtWidgets.QLabel(Dialog_report_attribute_parameters)
        self.label.setMinimumSize(QtCore.QSize(0, 85))
        self.label.setMaximumSize(QtCore.QSize(16777215, 80))
        self.label.setWordWrap(True)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 5)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_report_attribute_parameters)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.gridLayout.addWidget(self.buttonBox, 3, 4, 1, 1)
        self.pushButton_clear = QtWidgets.QPushButton(Dialog_report_attribute_parameters)
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.gridLayout.addWidget(self.pushButton_clear, 3, 1, 1, 1)
        self.radioButton_or = QtWidgets.QRadioButton(Dialog_report_attribute_parameters)
        self.radioButton_or.setMinimumSize(QtCore.QSize(80, 0))
        self.radioButton_or.setChecked(True)
        self.radioButton_or.setObjectName("radioButton_or")
        self.gridLayout.addWidget(self.radioButton_or, 3, 2, 1, 1)
        self.tableWidget = QtWidgets.QTableWidget(Dialog_report_attribute_parameters)
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
        self.gridLayout.addWidget(self.tableWidget, 1, 0, 1, 5)
        self.radioButton_and = QtWidgets.QRadioButton(Dialog_report_attribute_parameters)
        self.radioButton_and.setMinimumSize(QtCore.QSize(90, 0))
        self.radioButton_and.setObjectName("radioButton_and")
        self.gridLayout.addWidget(self.radioButton_and, 3, 3, 1, 1)

        self.retranslateUi(Dialog_report_attribute_parameters)
        self.buttonBox.rejected.connect(Dialog_report_attribute_parameters.reject) # type: ignore
        self.buttonBox.accepted.connect(Dialog_report_attribute_parameters.accept) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog_report_attribute_parameters)

    def retranslateUi(self, Dialog_report_attribute_parameters):
        _translate = QtCore.QCoreApplication.translate
        Dialog_report_attribute_parameters.setWindowTitle(_translate("Dialog_report_attribute_parameters", "Attribute selection parameters"))
        self.label.setText(_translate("Dialog_report_attribute_parameters", "Select parameters for the attributes. \n"
"between requires 2 values separated by ; e.g. 1;100\n"
" in and not in require 1 or more values separated by ;\n"
"Wildcards for \'like\' are % and _"))
        self.pushButton_clear.setToolTip(_translate("Dialog_report_attribute_parameters", "Clear attribute selections"))
        self.pushButton_clear.setText(_translate("Dialog_report_attribute_parameters", "Clear"))
        self.radioButton_or.setToolTip(_translate("Dialog_report_attribute_parameters", "<html><head/><body><p>Boolean Or</p><p>For all parameter selections</p></body></html>"))
        self.radioButton_or.setText(_translate("Dialog_report_attribute_parameters", "or"))
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
        self.radioButton_and.setToolTip(_translate("Dialog_report_attribute_parameters", "<html><head/><body><p>Boolean And</p><p>For all parameter selections</p></body></html>"))
        self.radioButton_and.setText(_translate("Dialog_report_attribute_parameters", "and"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_report_attribute_parameters = QtWidgets.QDialog()
    ui = Ui_Dialog_report_attribute_parameters()
    ui.setupUi(Dialog_report_attribute_parameters)
    Dialog_report_attribute_parameters.show()
    sys.exit(app.exec())
