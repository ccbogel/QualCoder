# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_assign_attribute.ui'
#
# Created: Wed Dec  6 23:24:24 2017
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_assignAttribute(object):
    def setupUi(self, Dialog_assignAttribute):
        Dialog_assignAttribute.setObjectName("Dialog_assignAttribute")
        Dialog_assignAttribute.resize(487, 148)
        self.radioButton_cases = QtWidgets.QRadioButton(Dialog_assignAttribute)
        self.radioButton_cases.setGeometry(QtCore.QRect(180, 19, 81, 20))
        self.radioButton_cases.setChecked(True)
        self.radioButton_cases.setObjectName("radioButton_cases")
        self.buttonGroup = QtWidgets.QButtonGroup(Dialog_assignAttribute)
        self.buttonGroup.setObjectName("buttonGroup")
        self.buttonGroup.addButton(self.radioButton_cases)
        self.radioButton_files = QtWidgets.QRadioButton(Dialog_assignAttribute)
        self.radioButton_files.setGeometry(QtCore.QRect(280, 19, 81, 20))
        self.radioButton_files.setObjectName("radioButton_files")
        self.buttonGroup.addButton(self.radioButton_files)
        self.label = QtWidgets.QLabel(Dialog_assignAttribute)
        self.label.setGeometry(QtCore.QRect(20, 20, 171, 17))
        self.label.setObjectName("label")
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_assignAttribute)
        self.buttonBox.setGeometry(QtCore.QRect(130, 80, 221, 27))
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")

        self.retranslateUi(Dialog_assignAttribute)
        self.buttonBox.accepted.connect(Dialog_assignAttribute.accept)
        self.buttonBox.rejected.connect(Dialog_assignAttribute.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_assignAttribute)

    def retranslateUi(self, Dialog_assignAttribute):
        _translate = QtCore.QCoreApplication.translate
        Dialog_assignAttribute.setWindowTitle(_translate("Dialog_assignAttribute", "Assign attribute"))
        self.radioButton_cases.setText(_translate("Dialog_assignAttribute", "Cases"))
        self.radioButton_files.setText(_translate("Dialog_assignAttribute", "Files"))
        self.label.setText(_translate("Dialog_assignAttribute", "Assign attribute to:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_assignAttribute = QtWidgets.QDialog()
    ui = Ui_Dialog_assignAttribute()
    ui.setupUi(Dialog_assignAttribute)
    Dialog_assignAttribute.show()
    sys.exit(app.exec_())

