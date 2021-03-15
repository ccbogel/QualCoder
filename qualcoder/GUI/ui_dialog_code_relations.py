# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_code_relations.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_CodeRelations(object):
    def setupUi(self, Dialog_CodeRelations):
        Dialog_CodeRelations.setObjectName("Dialog_CodeRelations")
        Dialog_CodeRelations.setWindowModality(QtCore.Qt.NonModal)
        Dialog_CodeRelations.resize(694, 543)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog_CodeRelations)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtWidgets.QGroupBox(Dialog_CodeRelations)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 90))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 90))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.label_1 = QtWidgets.QLabel(self.groupBox)
        self.label_1.setGeometry(QtCore.QRect(10, -4, 651, 26))
        self.label_1.setMinimumSize(QtCore.QSize(0, 26))
        self.label_1.setMaximumSize(QtCore.QSize(16777215, 26))
        self.label_1.setWordWrap(True)
        self.label_1.setObjectName("label_1")
        self.pushButton_exportcsv = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_exportcsv.setGeometry(QtCore.QRect(280, 30, 36, 36))
        self.pushButton_exportcsv.setText("")
        self.pushButton_exportcsv.setObjectName("pushButton_exportcsv")
        self.pushButton_calculate = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_calculate.setGeometry(QtCore.QRect(230, 30, 36, 36))
        self.pushButton_calculate.setText("")
        self.pushButton_calculate.setObjectName("pushButton_calculate")
        self.radioButton_this = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_this.setGeometry(QtCore.QRect(10, 30, 151, 23))
        self.radioButton_this.setChecked(True)
        self.radioButton_this.setObjectName("radioButton_this")
        self.radioButton_all = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_all.setGeometry(QtCore.QRect(10, 60, 171, 23))
        self.radioButton_all.setObjectName("radioButton_all")
        self.verticalLayout.addWidget(self.groupBox)
        self.label_codes = QtWidgets.QLabel(Dialog_CodeRelations)
        self.label_codes.setMinimumSize(QtCore.QSize(0, 30))
        self.label_codes.setMaximumSize(QtCore.QSize(16777215, 40))
        self.label_codes.setScaledContents(True)
        self.label_codes.setWordWrap(True)
        self.label_codes.setObjectName("label_codes")
        self.verticalLayout.addWidget(self.label_codes)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_CodeRelations)
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter = QtWidgets.QSplitter(self.groupBox_2)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.treeWidget = QtWidgets.QTreeWidget(self.splitter)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "1")
        self.tableWidget = QtWidgets.QTableWidget(self.splitter)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(0)
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox_2)

        self.retranslateUi(Dialog_CodeRelations)
        QtCore.QMetaObject.connectSlotsByName(Dialog_CodeRelations)

    def retranslateUi(self, Dialog_CodeRelations):
        _translate = QtCore.QCoreApplication.translate
        Dialog_CodeRelations.setWindowTitle(_translate("Dialog_CodeRelations", "Code relations"))
        self.label_1.setText(_translate("Dialog_CodeRelations", "Relations between codes in text files."))
        self.pushButton_exportcsv.setToolTip(_translate("Dialog_CodeRelations", "<html><head/><body><p>Export csv file</p></body></html>"))
        self.pushButton_calculate.setToolTip(_translate("Dialog_CodeRelations", "<html><head/><body><p>Calculate</p></body></html>"))
        self.radioButton_this.setText(_translate("Dialog_CodeRelations", "This coder"))
        self.radioButton_all.setText(_translate("Dialog_CodeRelations", "All coders"))
        self.label_codes.setText(_translate("Dialog_CodeRelations", "Codes:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_CodeRelations = QtWidgets.QDialog()
    ui = Ui_Dialog_CodeRelations()
    ui.setupUi(Dialog_CodeRelations)
    Dialog_CodeRelations.show()
    sys.exit(app.exec_())
