# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_code_context_image.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_code_context_image(object):
    def setupUi(self, Dialog_code_context_image):
        Dialog_code_context_image.setObjectName("Dialog_code_context_image")
        Dialog_code_context_image.resize(950, 596)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_code_context_image)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalSlider = QtWidgets.QSlider(Dialog_code_context_image)
        self.horizontalSlider.setMinimum(9)
        self.horizontalSlider.setSingleStep(3)
        self.horizontalSlider.setProperty("value", 99)
        self.horizontalSlider.setOrientation(QtCore.Qt.Horizontal)
        self.horizontalSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.horizontalSlider.setTickInterval(10)
        self.horizontalSlider.setObjectName("horizontalSlider")
        self.gridLayout.addWidget(self.horizontalSlider, 3, 0, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(Dialog_code_context_image)
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.splitter_2 = QtWidgets.QSplitter(self.groupBox)
        self.splitter_2.setOrientation(QtCore.Qt.Horizontal)
        self.splitter_2.setObjectName("splitter_2")
        self.splitter = QtWidgets.QSplitter(self.splitter_2)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.scrollArea = QtWidgets.QScrollArea(self.splitter_2)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollAreaWidgetContents = QtWidgets.QWidget()
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 902, 506))
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.gridLayout_3 = QtWidgets.QGridLayout(self.scrollAreaWidgetContents)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.graphicsView = QtWidgets.QGraphicsView(self.scrollAreaWidgetContents)
        self.graphicsView.setObjectName("graphicsView")
        self.gridLayout_3.addWidget(self.graphicsView, 0, 0, 1, 1)
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.gridLayout_2.addWidget(self.splitter_2, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 1)

        self.retranslateUi(Dialog_code_context_image)
        QtCore.QMetaObject.connectSlotsByName(Dialog_code_context_image)

    def retranslateUi(self, Dialog_code_context_image):
        _translate = QtCore.QCoreApplication.translate
        Dialog_code_context_image.setWindowTitle(_translate("Dialog_code_context_image", "View Image"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_code_context_image = QtWidgets.QDialog()
    ui = Ui_Dialog_code_context_image()
    ui.setupUi(Dialog_code_context_image)
    Dialog_code_context_image.show()
    sys.exit(app.exec_())
