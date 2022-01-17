# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_dialog_graph.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DialogGraph(object):
    def setupUi(self, DialogGraph):
        DialogGraph.setObjectName("DialogGraph")
        DialogGraph.resize(1024, 600)
        self.gridLayout = QtWidgets.QGridLayout(DialogGraph)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox_2 = QtWidgets.QGroupBox(DialogGraph)
        self.groupBox_2.setMinimumSize(QtCore.QSize(0, 60))
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.checkBox_blackandwhite = QtWidgets.QCheckBox(self.groupBox_2)
        self.checkBox_blackandwhite.setGeometry(QtCore.QRect(20, 0, 191, 22))
        self.checkBox_blackandwhite.setObjectName("checkBox_blackandwhite")
        self.comboBox = QtWidgets.QComboBox(self.groupBox_2)
        self.comboBox.setGeometry(QtCore.QRect(420, 0, 421, 30))
        self.comboBox.setObjectName("comboBox")
        self.checkBox_listview = QtWidgets.QCheckBox(self.groupBox_2)
        self.checkBox_listview.setGeometry(QtCore.QRect(20, 30, 141, 22))
        self.checkBox_listview.setChecked(True)
        self.checkBox_listview.setObjectName("checkBox_listview")
        self.comboBox_fontsize = QtWidgets.QComboBox(self.groupBox_2)
        self.comboBox_fontsize.setGeometry(QtCore.QRect(310, 0, 71, 31))
        self.comboBox_fontsize.setObjectName("comboBox_fontsize")
        self.label = QtWidgets.QLabel(self.groupBox_2)
        self.label.setGeometry(QtCore.QRect(205, 4, 101, 17))
        self.label.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.label.setObjectName("label")
        self.graphicsView = QtWidgets.QGraphicsView(self.groupBox_2)
        self.graphicsView.setGeometry(QtCore.QRect(0, 60, 1000, 520))
        self.graphicsView.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.graphicsView.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.graphicsView.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.graphicsView.setObjectName("graphicsView")
        self.pushButton_export = QtWidgets.QPushButton(self.groupBox_2)
        self.pushButton_export.setGeometry(QtCore.QRect(860, 0, 28, 28))
        self.pushButton_export.setText("")
        self.pushButton_export.setObjectName("pushButton_export")
        self.gridLayout.addWidget(self.groupBox_2, 0, 0, 1, 1)

        self.retranslateUi(DialogGraph)
        QtCore.QMetaObject.connectSlotsByName(DialogGraph)
        DialogGraph.setTabOrder(self.checkBox_blackandwhite, self.checkBox_listview)
        DialogGraph.setTabOrder(self.checkBox_listview, self.comboBox_fontsize)
        DialogGraph.setTabOrder(self.comboBox_fontsize, self.comboBox)

    def retranslateUi(self, DialogGraph):
        _translate = QtCore.QCoreApplication.translate
        DialogGraph.setWindowTitle(_translate("DialogGraph", "Graph Visualisation"))
        self.checkBox_blackandwhite.setText(_translate("DialogGraph", "Black and white"))
        self.checkBox_listview.setText(_translate("DialogGraph", "List view"))
        self.label.setText(_translate("DialogGraph", "Font size"))
        self.pushButton_export.setToolTip(_translate("DialogGraph", "Export image"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    DialogGraph = QtWidgets.QDialog()
    ui = Ui_DialogGraph()
    ui.setupUi(DialogGraph)
    DialogGraph.show()
    sys.exit(app.exec_())
