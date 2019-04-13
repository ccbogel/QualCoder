# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_attribute_type.ui'
#
# Created by: PyQt5 UI code generator 5.5.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_attribute_type(object):
    def setupUi(self, Dialog_attribute_type):
        Dialog_attribute_type.setObjectName("Dialog_attribute_type")
        Dialog_attribute_type.resize(400, 188)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_attribute_type)
        self.buttonBox.setGeometry(QtCore.QRect(160, 130, 211, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.radioButton_char = QtWidgets.QRadioButton(Dialog_attribute_type)
        self.radioButton_char.setGeometry(QtCore.QRect(30, 60, 161, 22))
        self.radioButton_char.setChecked(True)
        self.radioButton_char.setObjectName("radioButton_char")
        self.buttonGroup = QtWidgets.QButtonGroup(Dialog_attribute_type)
        self.buttonGroup.setObjectName("buttonGroup")
        self.buttonGroup.addButton(self.radioButton_char)
        self.radioButton_numeric = QtWidgets.QRadioButton(Dialog_attribute_type)
        self.radioButton_numeric.setGeometry(QtCore.QRect(30, 90, 171, 22))
        self.radioButton_numeric.setObjectName("radioButton_numeric")
        self.buttonGroup.addButton(self.radioButton_numeric)
        self.label = QtWidgets.QLabel(Dialog_attribute_type)
        self.label.setGeometry(QtCore.QRect(20, 20, 241, 17))
        self.label.setObjectName("label")

        self.retranslateUi(Dialog_attribute_type)
        self.buttonBox.accepted.connect(Dialog_attribute_type.accept)
        self.buttonBox.rejected.connect(Dialog_attribute_type.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_attribute_type)

    def retranslateUi(self, Dialog_attribute_type):
        _translate = QtCore.QCoreApplication.translate
        Dialog_attribute_type.setWindowTitle(_translate("Dialog_attribute_type", "Attribute Type"))
        self.radioButton_char.setText(_translate("Dialog_attribute_type", "Character - ABC"))
        self.radioButton_numeric.setText(_translate("Dialog_attribute_type", "Numeric - 123"))
        self.label.setText(_translate("Dialog_attribute_type", "Choose attribute type:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_attribute_type = QtWidgets.QDialog()
    ui = Ui_Dialog_attribute_type()
    ui.setupUi(Dialog_attribute_type)
    Dialog_attribute_type.show()
    sys.exit(app.exec_())

