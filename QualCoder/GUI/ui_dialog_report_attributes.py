# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_report_attributes.ui'
#
# Created: Sun Jan 20 22:12:38 2019
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_report_attributes(object):
    def setupUi(self, Dialog_report_attributes):
        Dialog_report_attributes.setObjectName("Dialog_report_attributes")
        Dialog_report_attributes.resize(758, 527)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_report_attributes)
        self.gridLayout.setObjectName("gridLayout")
        self.tableWidget = QtWidgets.QTableWidget(Dialog_report_attributes)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(4)
        self.tableWidget.setRowCount(0)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(0, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(1, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(2, item)
        item = QtWidgets.QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(3, item)
        self.gridLayout.addWidget(self.tableWidget, 1, 0, 1, 2)
        self.label = QtWidgets.QLabel(Dialog_report_attributes)
        self.label.setMinimumSize(QtCore.QSize(0, 80))
        self.label.setMaximumSize(QtCore.QSize(16777215, 80))
        self.label.setWordWrap(True)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 2)

        self.retranslateUi(Dialog_report_attributes)
        QtCore.QMetaObject.connectSlotsByName(Dialog_report_attributes)

    def retranslateUi(self, Dialog_report_attributes):
        _translate = QtCore.QCoreApplication.translate
        Dialog_report_attributes.setWindowTitle(_translate("Dialog_report_attributes", "Attributes"))
        item = self.tableWidget.horizontalHeaderItem(0)
        item.setText(_translate("Dialog_report_attributes", "Attribute"))
        item = self.tableWidget.horizontalHeaderItem(1)
        item.setText(_translate("Dialog_report_attributes", "Type"))
        item = self.tableWidget.horizontalHeaderItem(2)
        item.setText(_translate("Dialog_report_attributes", "Operator"))
        item = self.tableWidget.horizontalHeaderItem(3)
        item.setText(_translate("Dialog_report_attributes", "Value list"))
        self.label.setText(_translate("Dialog_report_attributes", "Select parameters to restrict reports for the attributes below. \n"
"Operators include <, >, =, between.\n"
"The value list can be a single value  or a list where each list item is separated by a comma."))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_report_attributes = QtWidgets.QDialog()
    ui = Ui_Dialog_report_attributes()
    ui.setupUi(Dialog_report_attributes)
    Dialog_report_attributes.show()
    sys.exit(app.exec_())

