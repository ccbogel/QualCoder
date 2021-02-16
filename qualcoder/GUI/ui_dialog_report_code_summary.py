# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_report_code_summary.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_file_summary(object):
    def setupUi(self, Dialog_file_summary):
        Dialog_file_summary.setObjectName("Dialog_file_summary")
        Dialog_file_summary.resize(880, 670)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_file_summary)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_file_summary)
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setContentsMargins(-1, 0, -1, 0)
        self.gridLayout_2.setVerticalSpacing(2)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.label_codes = QtWidgets.QLabel(self.groupBox_2)
        self.label_codes.setMinimumSize(QtCore.QSize(0, 22))
        self.label_codes.setMaximumSize(QtCore.QSize(16777215, 22))
        self.label_codes.setObjectName("label_codes")
        self.gridLayout_2.addWidget(self.label_codes, 0, 0, 1, 1)
        self.splitter = QtWidgets.QSplitter(self.groupBox_2)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.treeWidget = QtWidgets.QTreeWidget(self.splitter)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "1")
        self.textEdit = QtWidgets.QTextEdit(self.splitter)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout_2.addWidget(self.splitter, 1, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox_2, 1, 1, 1, 1)

        self.retranslateUi(Dialog_file_summary)
        QtCore.QMetaObject.connectSlotsByName(Dialog_file_summary)

    def retranslateUi(self, Dialog_file_summary):
        _translate = QtCore.QCoreApplication.translate
        Dialog_file_summary.setWindowTitle(_translate("Dialog_file_summary", "File summary"))
        self.label_codes.setText(_translate("Dialog_file_summary", "Code summary report"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_file_summary = QtWidgets.QDialog()
    ui = Ui_Dialog_file_summary()
    ui.setupUi(Dialog_file_summary)
    Dialog_file_summary.show()
    sys.exit(app.exec_())
