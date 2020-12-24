# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_report_comparisons.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_reportComparisons(object):
    def setupUi(self, Dialog_reportComparisons):
        Dialog_reportComparisons.setObjectName("Dialog_reportComparisons")
        Dialog_reportComparisons.setWindowModality(QtCore.Qt.NonModal)
        Dialog_reportComparisons.resize(750, 606)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog_reportComparisons)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtWidgets.QGroupBox(Dialog_reportComparisons)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 110))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 110))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.pushButton_exporttext = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_exporttext.setGeometry(QtCore.QRect(370, 70, 231, 36))
        self.pushButton_exporttext.setObjectName("pushButton_exporttext")
        self.pushButton_run = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_run.setGeometry(QtCore.QRect(370, 27, 231, 36))
        self.pushButton_run.setObjectName("pushButton_run")
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setGeometry(QtCore.QRect(10, 30, 71, 22))
        self.label_2.setObjectName("label_2")
        self.comboBox_coders = QtWidgets.QComboBox(self.groupBox)
        self.comboBox_coders.setGeometry(QtCore.QRect(90, 27, 221, 36))
        self.comboBox_coders.setObjectName("comboBox_coders")
        self.pushButton_clear = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_clear.setGeometry(QtCore.QRect(90, 70, 221, 36))
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.label_title = QtWidgets.QLabel(self.groupBox)
        self.label_title.setGeometry(QtCore.QRect(10, 0, 301, 22))
        self.label_title.setObjectName("label_title")
        self.verticalLayout.addWidget(self.groupBox)
        self.label_selections = QtWidgets.QLabel(Dialog_reportComparisons)
        self.label_selections.setMinimumSize(QtCore.QSize(0, 36))
        self.label_selections.setMaximumSize(QtCore.QSize(16777213, 36))
        self.label_selections.setWordWrap(True)
        self.label_selections.setObjectName("label_selections")
        self.verticalLayout.addWidget(self.label_selections)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_reportComparisons)
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout.setObjectName("gridLayout")
        self.treeWidget = QtWidgets.QTreeWidget(self.groupBox_2)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.treeWidget, 0, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox_2)

        self.retranslateUi(Dialog_reportComparisons)
        QtCore.QMetaObject.connectSlotsByName(Dialog_reportComparisons)
        Dialog_reportComparisons.setTabOrder(self.comboBox_coders, self.pushButton_run)
        Dialog_reportComparisons.setTabOrder(self.pushButton_run, self.pushButton_exporttext)

    def retranslateUi(self, Dialog_reportComparisons):
        _translate = QtCore.QCoreApplication.translate
        Dialog_reportComparisons.setWindowTitle(_translate("Dialog_reportComparisons", "Coder Comparisons"))
        self.pushButton_exporttext.setText(_translate("Dialog_reportComparisons", "Export text file"))
        self.pushButton_run.setText(_translate("Dialog_reportComparisons", "Run Comparisons"))
        self.label_2.setText(_translate("Dialog_reportComparisons", "Coders:"))
        self.pushButton_clear.setText(_translate("Dialog_reportComparisons", "Clear selection"))
        self.label_title.setText(_translate("Dialog_reportComparisons", "Coder comparisons"))
        self.label_selections.setText(_translate("Dialog_reportComparisons", "Coders selected:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_reportComparisons = QtWidgets.QDialog()
    ui = Ui_Dialog_reportComparisons()
    ui.setupUi(Dialog_reportComparisons)
    Dialog_reportComparisons.show()
    sys.exit(app.exec_())
