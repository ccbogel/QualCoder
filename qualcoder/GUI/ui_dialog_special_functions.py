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
        Dialog_special_functions.resize(627, 246)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_special_functions)
        self.buttonBox.setGeometry(QtCore.QRect(330, 190, 261, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.radioButton_text_coding_start_positions = QtWidgets.QRadioButton(Dialog_special_functions)
        self.radioButton_text_coding_start_positions.setGeometry(QtCore.QRect(10, 50, 491, 23))
        self.radioButton_text_coding_start_positions.setObjectName("radioButton_text_coding_start_positions")
        self.spinBox_text_starts = QtWidgets.QSpinBox(Dialog_special_functions)
        self.spinBox_text_starts.setGeometry(QtCore.QRect(537, 48, 61, 26))
        self.spinBox_text_starts.setMinimum(-100)
        self.spinBox_text_starts.setMaximum(100)
        self.spinBox_text_starts.setObjectName("spinBox_text_starts")
        self.label = QtWidgets.QLabel(Dialog_special_functions)
        self.label.setGeometry(QtCore.QRect(20, 10, 511, 17))
        self.label.setObjectName("label")
        self.spinBox_text_ends = QtWidgets.QSpinBox(Dialog_special_functions)
        self.spinBox_text_ends.setGeometry(QtCore.QRect(537, 78, 61, 26))
        self.spinBox_text_ends.setMinimum(-100)
        self.spinBox_text_ends.setMaximum(100)
        self.spinBox_text_ends.setObjectName("spinBox_text_ends")
        self.radioButton_text_coding_end_positions = QtWidgets.QRadioButton(Dialog_special_functions)
        self.radioButton_text_coding_end_positions.setGeometry(QtCore.QRect(10, 80, 491, 23))
        self.radioButton_text_coding_end_positions.setObjectName("radioButton_text_coding_end_positions")

        self.retranslateUi(Dialog_special_functions)
        self.buttonBox.accepted.connect(Dialog_special_functions.accept)
        self.buttonBox.rejected.connect(Dialog_special_functions.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_special_functions)

    def retranslateUi(self, Dialog_special_functions):
        _translate = QtCore.QCoreApplication.translate
        Dialog_special_functions.setWindowTitle(_translate("Dialog_special_functions", "Special Functions"))
        self.radioButton_text_coding_start_positions.setText(_translate("Dialog_special_functions", "Change text coding start positions for ALL codes in ALL files"))
        self.label.setText(_translate("Dialog_special_functions", "Special user function requests"))
        self.radioButton_text_coding_end_positions.setText(_translate("Dialog_special_functions", "Change text coding end positions for ALL codes in ALL files"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_special_functions = QtWidgets.QDialog()
    ui = Ui_Dialog_special_functions()
    ui.setupUi(Dialog_special_functions)
    Dialog_special_functions.show()
    sys.exit(app.exec_())
