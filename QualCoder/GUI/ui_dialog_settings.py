# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_settings.ui'
#
# Created: Mon Dec 18 08:25:32 2017
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_settings(object):
    def setupUi(self, Dialog_settings):
        Dialog_settings.setObjectName("Dialog_settings")
        Dialog_settings.resize(737, 401)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_settings)
        self.buttonBox.setGeometry(QtCore.QRect(390, 350, 261, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.lineEdit_coderName = QtWidgets.QLineEdit(Dialog_settings)
        self.lineEdit_coderName.setGeometry(QtCore.QRect(200, 24, 241, 31))
        self.lineEdit_coderName.setObjectName("lineEdit_coderName")
        self.label_coderName = QtWidgets.QLabel(Dialog_settings)
        self.label_coderName.setGeometry(QtCore.QRect(40, 30, 141, 21))
        self.label_coderName.setObjectName("label_coderName")
        self.fontComboBox = QtWidgets.QFontComboBox(Dialog_settings)
        self.fontComboBox.setGeometry(QtCore.QRect(30, 180, 229, 38))
        self.fontComboBox.setObjectName("fontComboBox")
        self.spinBox = QtWidgets.QSpinBox(Dialog_settings)
        self.spinBox.setGeometry(QtCore.QRect(270, 180, 71, 38))
        self.spinBox.setMinimum(8)
        self.spinBox.setMaximum(32)
        self.spinBox.setSingleStep(2)
        self.spinBox.setObjectName("spinBox")
        self.label = QtWidgets.QLabel(Dialog_settings)
        self.label.setGeometry(QtCore.QRect(30, 150, 211, 21))
        self.label.setObjectName("label")
        self.checkBox = QtWidgets.QCheckBox(Dialog_settings)
        self.checkBox.setGeometry(QtCore.QRect(30, 120, 151, 22))
        self.checkBox.setObjectName("checkBox")
        self.label_directory = QtWidgets.QLabel(Dialog_settings)
        self.label_directory.setGeometry(QtCore.QRect(30, 310, 671, 21))
        self.label_directory.setObjectName("label_directory")
        self.pushButton_choose_directory = QtWidgets.QPushButton(Dialog_settings)
        self.pushButton_choose_directory.setGeometry(QtCore.QRect(30, 270, 391, 31))
        self.pushButton_choose_directory.setObjectName("pushButton_choose_directory")
        self.label_2 = QtWidgets.QLabel(Dialog_settings)
        self.label_2.setGeometry(QtCore.QRect(35, 80, 141, 20))
        self.label_2.setObjectName("label_2")
        self.comboBox_coders = QtWidgets.QComboBox(Dialog_settings)
        self.comboBox_coders.setGeometry(QtCore.QRect(200, 70, 241, 33))
        self.comboBox_coders.setObjectName("comboBox_coders")
        self.label_3 = QtWidgets.QLabel(Dialog_settings)
        self.label_3.setGeometry(QtCore.QRect(30, 220, 241, 41))
        self.label_3.setWordWrap(True)
        self.label_3.setObjectName("label_3")
        self.spinBox_treefontsize = QtWidgets.QSpinBox(Dialog_settings)
        self.spinBox_treefontsize.setGeometry(QtCore.QRect(270, 220, 71, 38))
        self.spinBox_treefontsize.setMinimum(8)
        self.spinBox_treefontsize.setMaximum(32)
        self.spinBox_treefontsize.setSingleStep(2)
        self.spinBox_treefontsize.setObjectName("spinBox_treefontsize")

        self.retranslateUi(Dialog_settings)
        self.buttonBox.accepted.connect(Dialog_settings.accept)
        self.buttonBox.rejected.connect(Dialog_settings.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_settings)

    def retranslateUi(self, Dialog_settings):
        _translate = QtCore.QCoreApplication.translate
        Dialog_settings.setWindowTitle(_translate("Dialog_settings", "Settings"))
        self.label_coderName.setText(_translate("Dialog_settings", "This Coder Name"))
        self.label.setText(_translate("Dialog_settings", "General font and size"))
        self.checkBox.setText(_translate("Dialog_settings", "Show IDs"))
        self.label_directory.setText(_translate("Dialog_settings", "/"))
        self.pushButton_choose_directory.setText(_translate("Dialog_settings", "Default project directory"))
        self.label_2.setText(_translate("Dialog_settings", "Coders"))
        self.label_3.setText(_translate("Dialog_settings", "Font size for categories and codes tree"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_settings = QtWidgets.QDialog()
    ui = Ui_Dialog_settings()
    ui.setupUi(Dialog_settings)
    Dialog_settings.show()
    sys.exit(app.exec_())

