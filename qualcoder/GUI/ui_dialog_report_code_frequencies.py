# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_report_code_frequencies.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_reportCodeFrequencies(object):
    def setupUi(self, Dialog_reportCodeFrequencies):
        Dialog_reportCodeFrequencies.setObjectName("Dialog_reportCodeFrequencies")
        Dialog_reportCodeFrequencies.setWindowModality(QtCore.Qt.NonModal)
        Dialog_reportCodeFrequencies.resize(694, 543)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog_reportCodeFrequencies)
        self.verticalLayout.setObjectName("verticalLayout")
        self.groupBox = QtWidgets.QGroupBox(Dialog_reportCodeFrequencies)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 90))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 90))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.label_selections = QtWidgets.QLabel(self.groupBox)
        self.label_selections.setGeometry(QtCore.QRect(10, 0, 481, 22))
        self.label_selections.setMinimumSize(QtCore.QSize(0, 22))
        self.label_selections.setMaximumSize(QtCore.QSize(16777213, 22))
        self.label_selections.setWordWrap(True)
        self.label_selections.setObjectName("label_selections")
        self.pushButton_exporttext = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_exporttext.setGeometry(QtCore.QRect(300, 30, 36, 36))
        self.pushButton_exporttext.setMinimumSize(QtCore.QSize(36, 36))
        self.pushButton_exporttext.setMaximumSize(QtCore.QSize(36, 36))
        self.pushButton_exporttext.setText("")
        self.pushButton_exporttext.setObjectName("pushButton_exporttext")
        self.pushButton_exportcsv = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_exportcsv.setGeometry(QtCore.QRect(350, 30, 36, 36))
        self.pushButton_exportcsv.setMinimumSize(QtCore.QSize(36, 36))
        self.pushButton_exportcsv.setMaximumSize(QtCore.QSize(36, 36))
        self.pushButton_exportcsv.setText("")
        self.pushButton_exportcsv.setObjectName("pushButton_exportcsv")
        self.pushButton_select_files = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_select_files.setGeometry(QtCore.QRect(10, 30, 271, 36))
        self.pushButton_select_files.setObjectName("pushButton_select_files")
        self.verticalLayout.addWidget(self.groupBox)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_reportCodeFrequencies)
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout.setObjectName("gridLayout")
        self.treeWidget = QtWidgets.QTreeWidget(self.groupBox_2)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "1")
        self.gridLayout.addWidget(self.treeWidget, 0, 0, 1, 1)
        self.verticalLayout.addWidget(self.groupBox_2)

        self.retranslateUi(Dialog_reportCodeFrequencies)
        QtCore.QMetaObject.connectSlotsByName(Dialog_reportCodeFrequencies)

    def retranslateUi(self, Dialog_reportCodeFrequencies):
        _translate = QtCore.QCoreApplication.translate
        Dialog_reportCodeFrequencies.setWindowTitle(_translate("Dialog_reportCodeFrequencies", "Code frequencies"))
        self.label_selections.setText(_translate("Dialog_reportCodeFrequencies", "Code and category frequencies: overall and by coder"))
        self.pushButton_exporttext.setToolTip(_translate("Dialog_reportCodeFrequencies", "<html><head/><body><p>Export text file</p></body></html>"))
        self.pushButton_exportcsv.setToolTip(_translate("Dialog_reportCodeFrequencies", "<html><head/><body><p>Export csv file</p></body></html>"))
        self.pushButton_select_files.setText(_translate("Dialog_reportCodeFrequencies", "Select files"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_reportCodeFrequencies = QtWidgets.QDialog()
    ui = Ui_Dialog_reportCodeFrequencies()
    ui.setupUi(Dialog_reportCodeFrequencies)
    Dialog_reportCodeFrequencies.show()
    sys.exit(app.exec_())
