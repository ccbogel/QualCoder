# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_select_file.ui'
#
# Created by: PyQt5 UI code generator 5.9
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_selectfile(object):
    def setupUi(self, Dialog_selectfile):
        Dialog_selectfile.setObjectName("Dialog_selectfile")
        Dialog_selectfile.resize(400, 433)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_selectfile)
        self.buttonBox.setGeometry(QtCore.QRect(190, 390, 191, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.listView = QtWidgets.QListView(Dialog_selectfile)
        self.listView.setGeometry(QtCore.QRect(10, 10, 371, 361))
        self.listView.setObjectName("listView")

        self.retranslateUi(Dialog_selectfile)
        self.buttonBox.accepted.connect(Dialog_selectfile.accept)
        self.buttonBox.rejected.connect(Dialog_selectfile.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_selectfile)

    def retranslateUi(self, Dialog_selectfile):
        _translate = QtCore.QCoreApplication.translate
        Dialog_selectfile.setWindowTitle(_translate("Dialog_selectfile", "Select File"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_selectfile = QtWidgets.QDialog()
    ui = Ui_Dialog_selectfile()
    ui.setupUi(Dialog_selectfile)
    Dialog_selectfile.show()
    sys.exit(app.exec_())

