# Form implementation generated from reading ui file 'ui_dialog_assign_attribute.ui'
#
# Created by: PyQt6 UI code generator 6.4.2
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog_assignAttribute(object):
    def setupUi(self, Dialog_assignAttribute):
        Dialog_assignAttribute.setObjectName("Dialog_assignAttribute")
        Dialog_assignAttribute.resize(472, 162)
        self.radioButton_cases = QtWidgets.QRadioButton(parent=Dialog_assignAttribute)
        self.radioButton_cases.setGeometry(QtCore.QRect(20, 42, 111, 20))
        self.radioButton_cases.setChecked(True)
        self.radioButton_cases.setObjectName("radioButton_cases")
        self.buttonGroup = QtWidgets.QButtonGroup(Dialog_assignAttribute)
        self.buttonGroup.setObjectName("buttonGroup")
        self.buttonGroup.addButton(self.radioButton_cases)
        self.radioButton_files = QtWidgets.QRadioButton(parent=Dialog_assignAttribute)
        self.radioButton_files.setGeometry(QtCore.QRect(160, 42, 81, 20))
        self.radioButton_files.setObjectName("radioButton_files")
        self.buttonGroup.addButton(self.radioButton_files)
        self.label = QtWidgets.QLabel(parent=Dialog_assignAttribute)
        self.label.setGeometry(QtCore.QRect(20, 20, 171, 17))
        self.label.setObjectName("label")
        self.buttonBox = QtWidgets.QDialogButtonBox(parent=Dialog_assignAttribute)
        self.buttonBox.setGeometry(QtCore.QRect(90, 90, 171, 27))
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.radioButton_journals = QtWidgets.QRadioButton(parent=Dialog_assignAttribute)
        self.radioButton_journals.setGeometry(QtCore.QRect(270, 42, 121, 20))
        self.radioButton_journals.setObjectName("radioButton_journals")

        self.retranslateUi(Dialog_assignAttribute)
        self.buttonBox.accepted.connect(Dialog_assignAttribute.accept) # type: ignore
        self.buttonBox.rejected.connect(Dialog_assignAttribute.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog_assignAttribute)

    def retranslateUi(self, Dialog_assignAttribute):
        _translate = QtCore.QCoreApplication.translate
        Dialog_assignAttribute.setWindowTitle(_translate("Dialog_assignAttribute", "Assign attribute"))
        self.radioButton_cases.setText(_translate("Dialog_assignAttribute", "Cases"))
        self.radioButton_files.setText(_translate("Dialog_assignAttribute", "Files"))
        self.label.setText(_translate("Dialog_assignAttribute", "Assign attribute to:"))
        self.radioButton_journals.setText(_translate("Dialog_assignAttribute", "Journals"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_assignAttribute = QtWidgets.QDialog()
    ui = Ui_Dialog_assignAttribute()
    ui.setupUi(Dialog_assignAttribute)
    Dialog_assignAttribute.show()
    sys.exit(app.exec())
