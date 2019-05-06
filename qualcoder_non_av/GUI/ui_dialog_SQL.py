# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_SQL.ui'
#
# Created: Sun Feb 11 09:50:03 2018
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_sql(object):
    def setupUi(self, Dialog_sql):
        Dialog_sql.setObjectName("Dialog_sql")
        Dialog_sql.resize(947, 606)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_sql)
        self.gridLayout.setObjectName("gridLayout")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.splitter_2 = QtWidgets.QSplitter(Dialog_sql)
        self.splitter_2.setOrientation(QtCore.Qt.Horizontal)
        self.splitter_2.setObjectName("splitter_2")
        self.treeWidget = QtWidgets.QTreeWidget(self.splitter_2)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "Tables")
        self.splitter = QtWidgets.QSplitter(self.splitter_2)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.textEdit_sql = QtWidgets.QTextEdit(self.splitter)
        self.textEdit_sql.setObjectName("textEdit_sql")
        self.tableWidget_results = QtWidgets.QTableWidget(self.splitter)
        self.tableWidget_results.setObjectName("tableWidget_results")
        self.tableWidget_results.setColumnCount(0)
        self.tableWidget_results.setRowCount(0)
        self.verticalLayout.addWidget(self.splitter_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(Dialog_sql)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.pushButton_runSQL = QtWidgets.QPushButton(Dialog_sql)
        self.pushButton_runSQL.setMaximumSize(QtCore.QSize(100, 16777215))
        self.pushButton_runSQL.setObjectName("pushButton_runSQL")
        self.horizontalLayout.addWidget(self.pushButton_runSQL)
        self.pushButton_export = QtWidgets.QPushButton(Dialog_sql)
        self.pushButton_export.setMaximumSize(QtCore.QSize(150, 16777215))
        self.pushButton_export.setObjectName("pushButton_export")
        self.horizontalLayout.addWidget(self.pushButton_export)
        self.comboBox_delimiter = QtWidgets.QComboBox(Dialog_sql)
        self.comboBox_delimiter.setMaximumSize(QtCore.QSize(80, 16777215))
        self.comboBox_delimiter.setObjectName("comboBox_delimiter")
        self.comboBox_delimiter.addItem("")
        self.comboBox_delimiter.addItem("")
        self.comboBox_delimiter.addItem("")
        self.comboBox_delimiter.addItem("")
        self.horizontalLayout.addWidget(self.comboBox_delimiter)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)

        self.retranslateUi(Dialog_sql)
        QtCore.QMetaObject.connectSlotsByName(Dialog_sql)

    def retranslateUi(self, Dialog_sql):
        _translate = QtCore.QCoreApplication.translate
        Dialog_sql.setWindowTitle(_translate("Dialog_sql", "SQL_statements"))
        self.label.setText(_translate("Dialog_sql", "."))
        self.pushButton_runSQL.setText(_translate("Dialog_sql", "Run"))
        self.pushButton_export.setText(_translate("Dialog_sql", "Export to file"))
        self.comboBox_delimiter.setItemText(0, _translate("Dialog_sql", "tab"))
        self.comboBox_delimiter.setItemText(1, _translate("Dialog_sql", ","))
        self.comboBox_delimiter.setItemText(2, _translate("Dialog_sql", ";"))
        self.comboBox_delimiter.setItemText(3, _translate("Dialog_sql", "|"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_sql = QtWidgets.QDialog()
    ui = Ui_Dialog_sql()
    ui.setupUi(Dialog_sql)
    Dialog_sql.show()
    sys.exit(app.exec_())

