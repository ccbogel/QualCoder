# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_report_file_summary.ui'
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
        self.label_files = QtWidgets.QLabel(self.groupBox_2)
        self.label_files.setMinimumSize(QtCore.QSize(0, 22))
        self.label_files.setMaximumSize(QtCore.QSize(16777215, 22))
        self.label_files.setObjectName("label_files")
        self.gridLayout_2.addWidget(self.label_files, 0, 0, 1, 1)
        self.splitter = QtWidgets.QSplitter(self.groupBox_2)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.listWidget = QtWidgets.QListWidget(self.splitter)
        self.listWidget.setObjectName("listWidget")
        self.textEdit = QtWidgets.QTextEdit(self.splitter)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout_2.addWidget(self.splitter, 1, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox_2, 1, 1, 1, 1)

        self.retranslateUi(Dialog_file_summary)
        QtCore.QMetaObject.connectSlotsByName(Dialog_file_summary)
        Dialog_file_summary.setTabOrder(self.listWidget, self.textEdit)

    def retranslateUi(self, Dialog_file_summary):
        _translate = QtCore.QCoreApplication.translate
        Dialog_file_summary.setWindowTitle(_translate("Dialog_file_summary", "File summary"))
        self.label_files.setText(_translate("Dialog_file_summary", "File summary report"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_file_summary = QtWidgets.QDialog()
    ui = Ui_Dialog_file_summary()
    ui.setupUi(Dialog_file_summary)
    Dialog_file_summary.show()
    sys.exit(app.exec_())
