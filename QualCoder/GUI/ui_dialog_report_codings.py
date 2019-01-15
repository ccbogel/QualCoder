# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_report_codings.ui'
#
# Created: Tue Dec 19 23:05:18 2017
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_reportCodings(object):
    def setupUi(self, Dialog_reportCodings):
        Dialog_reportCodings.setObjectName("Dialog_reportCodings")
        Dialog_reportCodings.setWindowModality(QtCore.Qt.NonModal)
        Dialog_reportCodings.resize(1129, 715)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog_reportCodings)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtWidgets.QGroupBox(Dialog_reportCodings)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 120))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 120))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.pushButton_exporttext = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_exporttext.setGeometry(QtCore.QRect(760, 70, 161, 27))
        self.pushButton_exporttext.setObjectName("pushButton_exporttext")
        self.pushButton_caseselect = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_caseselect.setGeometry(QtCore.QRect(470, 70, 151, 27))
        self.pushButton_caseselect.setObjectName("pushButton_caseselect")
        self.pushButton_exporthtml = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_exporthtml.setGeometry(QtCore.QRect(760, 40, 161, 27))
        self.pushButton_exporthtml.setObjectName("pushButton_exporthtml")
        self.pushButton_fileselect = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_fileselect.setGeometry(QtCore.QRect(470, 40, 151, 27))
        self.pushButton_fileselect.setObjectName("pushButton_fileselect")
        self.lineEdit = QtWidgets.QLineEdit(self.groupBox)
        self.lineEdit.setGeometry(QtCore.QRect(130, 70, 181, 30))
        self.lineEdit.setObjectName("lineEdit")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setGeometry(QtCore.QRect(10, 80, 121, 21))
        self.label.setWordWrap(True)
        self.label.setObjectName("label")
        self.pushButton_search = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_search.setGeometry(QtCore.QRect(630, 40, 71, 61))
        self.pushButton_search.setObjectName("pushButton_search")
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setGeometry(QtCore.QRect(10, 30, 61, 22))
        self.label_2.setObjectName("label_2")
        self.comboBox_coders = QtWidgets.QComboBox(self.groupBox)
        self.comboBox_coders.setGeometry(QtCore.QRect(90, 20, 221, 34))
        self.comboBox_coders.setObjectName("comboBox_coders")
        self.verticalLayout.addWidget(self.groupBox)
        self.label_selections = QtWidgets.QLabel(Dialog_reportCodings)
        self.label_selections.setMinimumSize(QtCore.QSize(0, 50))
        self.label_selections.setMaximumSize(QtCore.QSize(16777213, 50))
        self.label_selections.setWordWrap(True)
        self.label_selections.setObjectName("label_selections")
        self.verticalLayout.addWidget(self.label_selections)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_reportCodings)
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter = QtWidgets.QSplitter(self.groupBox_2)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.textEdit = QtWidgets.QTextEdit(self.splitter)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout.addWidget(self.splitter, 0, 1, 1, 1)
        self.treeWidget = QtWidgets.QTreeWidget(self.groupBox_2)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.treeWidget, 0, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox_2)

        self.retranslateUi(Dialog_reportCodings)
        QtCore.QMetaObject.connectSlotsByName(Dialog_reportCodings)
        Dialog_reportCodings.setTabOrder(self.comboBox_coders, self.lineEdit)
        Dialog_reportCodings.setTabOrder(self.lineEdit, self.pushButton_fileselect)
        Dialog_reportCodings.setTabOrder(self.pushButton_fileselect, self.pushButton_caseselect)
        Dialog_reportCodings.setTabOrder(self.pushButton_caseselect, self.pushButton_search)
        Dialog_reportCodings.setTabOrder(self.pushButton_search, self.pushButton_exporthtml)
        Dialog_reportCodings.setTabOrder(self.pushButton_exporthtml, self.pushButton_exporttext)
        Dialog_reportCodings.setTabOrder(self.pushButton_exporttext, self.treeWidget)
        Dialog_reportCodings.setTabOrder(self.treeWidget, self.textEdit)

    def retranslateUi(self, Dialog_reportCodings):
        _translate = QtCore.QCoreApplication.translate
        Dialog_reportCodings.setWindowTitle(_translate("Dialog_reportCodings", "Reports"))
        self.pushButton_exporttext.setText(_translate("Dialog_reportCodings", "Export text file"))
        self.pushButton_caseselect.setText(_translate("Dialog_reportCodings", "Case selection"))
        self.pushButton_exporthtml.setText(_translate("Dialog_reportCodings", "Export html file"))
        self.pushButton_fileselect.setText(_translate("Dialog_reportCodings", "File selection"))
        self.label.setText(_translate("Dialog_reportCodings", "Search text:"))
        self.pushButton_search.setText(_translate("Dialog_reportCodings", "Search"))
        self.label_2.setText(_translate("Dialog_reportCodings", "Coder:"))
        self.label_selections.setText(_translate("Dialog_reportCodings", "Search selections:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_reportCodings = QtWidgets.QDialog()
    ui = Ui_Dialog_reportCodings()
    ui.setupUi(Dialog_reportCodings)
    Dialog_reportCodings.show()
    sys.exit(app.exec_())

