# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_code_crossovers.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_CodeCrossovers(object):
    def setupUi(self, Dialog_CodeCrossovers):
        Dialog_CodeCrossovers.setObjectName("Dialog_CodeCrossovers")
        Dialog_CodeCrossovers.setWindowModality(QtCore.Qt.NonModal)
        Dialog_CodeCrossovers.resize(694, 543)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog_CodeCrossovers)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtWidgets.QGroupBox(Dialog_CodeCrossovers)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 100))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 90))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.label_1 = QtWidgets.QLabel(self.groupBox)
        self.label_1.setGeometry(QtCore.QRect(10, 0, 651, 32))
        self.label_1.setMinimumSize(QtCore.QSize(0, 32))
        self.label_1.setMaximumSize(QtCore.QSize(16777213, 26))
        self.label_1.setWordWrap(True)
        self.label_1.setObjectName("label_1")
        self.pushButton_exportcsv = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_exportcsv.setGeometry(QtCore.QRect(360, 40, 291, 31))
        self.pushButton_exportcsv.setObjectName("pushButton_exportcsv")
        self.pushButton_calculate = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_calculate.setGeometry(QtCore.QRect(20, 40, 171, 31))
        self.pushButton_calculate.setObjectName("pushButton_calculate")
        self.verticalLayout.addWidget(self.groupBox)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_CodeCrossovers)
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout.setObjectName("gridLayout")
        self.treeWidget = QtWidgets.QTreeWidget(self.groupBox_2)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.treeWidget, 0, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox_2)

        self.retranslateUi(Dialog_CodeCrossovers)
        QtCore.QMetaObject.connectSlotsByName(Dialog_CodeCrossovers)

    def retranslateUi(self, Dialog_CodeCrossovers):
        _translate = QtCore.QCoreApplication.translate
        Dialog_CodeCrossovers.setWindowTitle(_translate("Dialog_CodeCrossovers", "Code crossovers"))
        self.label_1.setText(_translate("Dialog_CodeCrossovers", "Code crossovers"))
        self.pushButton_exportcsv.setText(_translate("Dialog_CodeCrossovers", "Export csv file"))
        self.pushButton_calculate.setText(_translate("Dialog_CodeCrossovers", "Calculate"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_CodeCrossovers = QtWidgets.QDialog()
    ui = Ui_Dialog_CodeCrossovers()
    ui.setupUi(Dialog_CodeCrossovers)
    Dialog_CodeCrossovers.show()
    sys.exit(app.exec_())
