# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_refi_export_endings.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_refi_export_line_endings(object):
    def setupUi(self, Dialog_refi_export_line_endings):
        Dialog_refi_export_line_endings.setObjectName("Dialog_refi_export_line_endings")
        Dialog_refi_export_line_endings.resize(582, 252)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_refi_export_line_endings)
        self.buttonBox.setGeometry(QtCore.QRect(280, 210, 261, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.radioButton_no_change = QtWidgets.QRadioButton(Dialog_refi_export_line_endings)
        self.radioButton_no_change.setGeometry(QtCore.QRect(30, 120, 431, 23))
        self.radioButton_no_change.setChecked(True)
        self.radioButton_no_change.setObjectName("radioButton_no_change")
        self.radioButton_maxqda = QtWidgets.QRadioButton(Dialog_refi_export_line_endings)
        self.radioButton_maxqda.setGeometry(QtCore.QRect(30, 150, 481, 23))
        self.radioButton_maxqda.setObjectName("radioButton_maxqda")
        self.radioButton_atlas = QtWidgets.QRadioButton(Dialog_refi_export_line_endings)
        self.radioButton_atlas.setGeometry(QtCore.QRect(30, 180, 481, 23))
        self.radioButton_atlas.setObjectName("radioButton_atlas")
        self.label = QtWidgets.QLabel(Dialog_refi_export_line_endings)
        self.label.setGeometry(QtCore.QRect(20, 20, 541, 81))
        self.label.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop)
        self.label.setWordWrap(True)
        self.label.setObjectName("label")

        self.retranslateUi(Dialog_refi_export_line_endings)
        self.buttonBox.accepted.connect(Dialog_refi_export_line_endings.accept)
        self.buttonBox.rejected.connect(Dialog_refi_export_line_endings.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_refi_export_line_endings)

    def retranslateUi(self, Dialog_refi_export_line_endings):
        _translate = QtCore.QCoreApplication.translate
        Dialog_refi_export_line_endings.setWindowTitle(_translate("Dialog_refi_export_line_endings", "Settings"))
        self.radioButton_no_change.setText(_translate("Dialog_refi_export_line_endings", "No change to line endings"))
        self.radioButton_maxqda.setText(_translate("Dialog_refi_export_line_endings", "Add line ending for MAXQDA importation"))
        self.radioButton_atlas.setText(_translate("Dialog_refi_export_line_endings", "Add line ending for ATLAS.ti importation"))
        self.label.setText(_translate("Dialog_refi_export_line_endings", "REFI-QDA project export. Plain text representation may need adjustment of line endings so that codes do not shift on import into other software."))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_refi_export_line_endings = QtWidgets.QDialog()
    ui = Ui_Dialog_refi_export_line_endings()
    ui.setupUi(Dialog_refi_export_line_endings)
    Dialog_refi_export_line_endings.show()
    sys.exit(app.exec_())
