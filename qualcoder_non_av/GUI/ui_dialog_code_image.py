# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_code_image2.ui'
#
# Created: Thu Jan 25 08:07:02 2018
#      by: PyQt5 UI code generator 5.2.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_code_image(object):
    def setupUi(self, Dialog_code_image):
        Dialog_code_image.setObjectName("Dialog_code_image")
        Dialog_code_image.resize(1021, 715)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_code_image)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalSlider = QtWidgets.QSlider(Dialog_code_image)
        self.horizontalSlider.setMinimum(9)
        self.horizontalSlider.setSingleStep(3)
        self.horizontalSlider.setProperty("value", 99)
        self.horizontalSlider.setOrientation(QtCore.Qt.Horizontal)
        self.horizontalSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.horizontalSlider.setTickInterval(10)
        self.horizontalSlider.setObjectName("horizontalSlider")
        self.gridLayout.addWidget(self.horizontalSlider, 4, 0, 1, 1)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_code_image)
        self.groupBox_2.setMinimumSize(QtCore.QSize(0, 80))
        self.groupBox_2.setMaximumSize(QtCore.QSize(16777215, 80))
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.pushButton_memo = QtWidgets.QPushButton(self.groupBox_2)
        self.pushButton_memo.setGeometry(QtCore.QRect(20, 40, 141, 32))
        self.pushButton_memo.setObjectName("pushButton_memo")
        self.pushButton_select = QtWidgets.QPushButton(self.groupBox_2)
        self.pushButton_select.setGeometry(QtCore.QRect(10, 0, 201, 32))
        self.pushButton_select.setObjectName("pushButton_select")
        self.label_coder = QtWidgets.QLabel(self.groupBox_2)
        self.label_coder.setGeometry(QtCore.QRect(360, 10, 301, 21))
        self.label_coder.setObjectName("label_coder")
        self.checkBox_show_coders = QtWidgets.QCheckBox(self.groupBox_2)
        self.checkBox_show_coders.setGeometry(QtCore.QRect(690, 10, 221, 22))
        self.checkBox_show_coders.setObjectName("checkBox_show_coders")
        self.label_code = QtWidgets.QLabel(self.groupBox_2)
        self.label_code.setGeometry(QtCore.QRect(360, 40, 521, 26))
        self.label_code.setObjectName("label_code")
        self.gridLayout.addWidget(self.groupBox_2, 0, 0, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(Dialog_code_image)
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout_2.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.splitter = QtWidgets.QSplitter(self.groupBox)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.treeWidget = QtWidgets.QTreeWidget(self.splitter)
        self.treeWidget.setObjectName("treeWidget")
        self.treeWidget.headerItem().setText(0, "1")
        self.scrollArea = QtWidgets.QScrollArea(self.splitter)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.graphicsView = QtWidgets.QGraphicsView()
        self.graphicsView.setGeometry(QtCore.QRect(0, 0, 330, 582))
        self.graphicsView.setObjectName("graphicsView")
        self.scrollArea.setWidget(self.graphicsView)
        self.gridLayout_2.addWidget(self.splitter, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 3, 0, 1, 1)

        self.retranslateUi(Dialog_code_image)
        QtCore.QMetaObject.connectSlotsByName(Dialog_code_image)

    def retranslateUi(self, Dialog_code_image):
        _translate = QtCore.QCoreApplication.translate
        Dialog_code_image.setWindowTitle(_translate("Dialog_code_image", "View Image"))
        self.pushButton_memo.setText(_translate("Dialog_code_image", "Memo"))
        self.pushButton_select.setText(_translate("Dialog_code_image", "Select image"))
        self.label_coder.setText(_translate("Dialog_code_image", "Coder:"))
        self.checkBox_show_coders.setToolTip(_translate("Dialog_code_image", "Mark this to show all coded text by all other coders."))
        self.checkBox_show_coders.setText(_translate("Dialog_code_image", "Show other coders"))
        self.label_code.setText(_translate("Dialog_code_image", "Code:"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_code_image = QtWidgets.QDialog()
    ui = Ui_Dialog_code_image()
    ui.setupUi(Dialog_code_image)
    Dialog_code_image.show()
    sys.exit(app.exec_())

