# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_select_items.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_selectitems(object):
    def setupUi(self, Dialog_selectitems):
        Dialog_selectitems.setObjectName("Dialog_selectitems")
        Dialog_selectitems.resize(400, 303)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_selectitems)
        self.gridLayout.setObjectName("gridLayout")
        self.listView = QtWidgets.QListView(Dialog_selectitems)
        self.listView.setObjectName("listView")
        self.gridLayout.addWidget(self.listView, 0, 0, 1, 1)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog_selectitems)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.gridLayout.addWidget(self.buttonBox, 1, 0, 1, 1)

        self.retranslateUi(Dialog_selectitems)
        self.buttonBox.accepted.connect(Dialog_selectitems.accept)
        self.buttonBox.rejected.connect(Dialog_selectitems.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog_selectitems)

    def retranslateUi(self, Dialog_selectitems):
        _translate = QtCore.QCoreApplication.translate
        Dialog_selectitems.setWindowTitle(_translate("Dialog_selectitems", "Select Items"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_selectitems = QtWidgets.QDialog()
    ui = Ui_Dialog_selectitems()
    ui.setupUi(Dialog_selectitems)
    Dialog_selectitems.show()
    sys.exit(app.exec_())
