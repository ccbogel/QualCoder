# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_special_functions.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_special_functions(object):
    def setupUi(self, Dialog_special_functions):
        Dialog_special_functions.setObjectName("Dialog_special_functions")
        Dialog_special_functions.resize(769, 246)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_special_functions)
        self.buttonBox.setGeometry(QtCore.QRect(490, 190, 261, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Close)
        self.buttonBox.setObjectName("buttonBox")
        self.spinBox_text_starts = QtWidgets.QSpinBox(Dialog_special_functions)
        self.spinBox_text_starts.setGeometry(QtCore.QRect(20, 40, 61, 36))
        self.spinBox_text_starts.setMinimum(-100)
        self.spinBox_text_starts.setMaximum(100)
        self.spinBox_text_starts.setObjectName("spinBox_text_starts")
        self.label = QtWidgets.QLabel(Dialog_special_functions)
        self.label.setGeometry(QtCore.QRect(20, 10, 511, 20))
        self.label.setObjectName("label")
        self.spinBox_text_ends = QtWidgets.QSpinBox(Dialog_special_functions)
        self.spinBox_text_ends.setGeometry(QtCore.QRect(20, 90, 61, 36))
        self.spinBox_text_ends.setMinimum(-100)
        self.spinBox_text_ends.setMaximum(100)
        self.spinBox_text_ends.setObjectName("spinBox_text_ends")
        self.pushButton_text_starts = QtWidgets.QPushButton(Dialog_special_functions)
        self.pushButton_text_starts.setGeometry(QtCore.QRect(90, 40, 36, 36))
        self.pushButton_text_starts.setObjectName("pushButton_text_starts")
        self.pushButton_text_ends = QtWidgets.QPushButton(Dialog_special_functions)
        self.pushButton_text_ends.setGeometry(QtCore.QRect(90, 90, 36, 36))
        self.pushButton_text_ends.setObjectName("pushButton_text_ends")
        self.label_2 = QtWidgets.QLabel(Dialog_special_functions)
        self.label_2.setGeometry(QtCore.QRect(140, 40, 611, 30))
        self.label_2.setObjectName("label_2")
        self.label_3 = QtWidgets.QLabel(Dialog_special_functions)
        self.label_3.setGeometry(QtCore.QRect(140, 90, 611, 30))
        self.label_3.setObjectName("label_3")

        self.retranslateUi(Dialog_special_functions)
        self.buttonBox.accepted.connect(Dialog_special_functions.accept)
        self.buttonBox.rejected.connect(Dialog_special_functions.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_special_functions)

    def retranslateUi(self, Dialog_special_functions):
        _translate = QtCore.QCoreApplication.translate
        Dialog_special_functions.setWindowTitle(_translate("Dialog_special_functions", "Special Functions"))
        self.spinBox_text_starts.setToolTip(_translate("Dialog_special_functions", "<html><head/><body><p>Numer of characters to extend (positive numbers)</p><p>or reduce (negative numbers)</p></body></html>"))
        self.label.setText(_translate("Dialog_special_functions", "Special user function requests"))
        self.spinBox_text_ends.setToolTip(_translate("Dialog_special_functions", "<html><head/><body><p>Numer of characters to extend (positive numbers)</p><p>or reduce (negative numbers)</p></body></html>"))
        self.pushButton_text_starts.setText(_translate("Dialog_special_functions", "Go"))
        self.pushButton_text_ends.setText(_translate("Dialog_special_functions", "Go"))
        self.label_2.setText(_translate("Dialog_special_functions", "Change text code start positions ALL codes ALL files."))
        self.label_3.setText(_translate("Dialog_special_functions", "Change text code end positions ALL codes ALL files."))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_special_functions = QtWidgets.QDialog()
    ui = Ui_Dialog_special_functions()
    ui.setupUi(Dialog_special_functions)
    Dialog_special_functions.show()
    sys.exit(app.exec_())
