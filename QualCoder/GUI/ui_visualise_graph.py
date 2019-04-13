# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_visualise_graph.ui'
#
# Created by: PyQt5 UI code generator 5.5.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog_visualiseGraph(object):
    def setupUi(self, Dialog_visualiseGraph):
        Dialog_visualiseGraph.setObjectName("Dialog_visualiseGraph")
        Dialog_visualiseGraph.resize(1098, 753)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_visualiseGraph)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter = QtWidgets.QSplitter(Dialog_visualiseGraph)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.graphicsView = QtWidgets.QGraphicsView(self.splitter)
        self.graphicsView.setObjectName("graphicsView")
        self.gridLayout.addWidget(self.splitter, 0, 0, 1, 1)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_visualiseGraph)
        self.groupBox_2.setMinimumSize(QtCore.QSize(0, 40))
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.pushButton_view = QtWidgets.QPushButton(self.groupBox_2)
        self.pushButton_view.setGeometry(QtCore.QRect(0, 0, 161, 27))
        self.pushButton_view.setObjectName("pushButton_view")
        self.checkBox_blackandwhite = QtWidgets.QCheckBox(self.groupBox_2)
        self.checkBox_blackandwhite.setGeometry(QtCore.QRect(170, 0, 191, 22))
        self.checkBox_blackandwhite.setObjectName("checkBox_blackandwhite")
        self.checkBox_fontsize = QtWidgets.QCheckBox(self.groupBox_2)
        self.checkBox_fontsize.setGeometry(QtCore.QRect(370, 0, 281, 22))
        self.checkBox_fontsize.setObjectName("checkBox_fontsize")
        self.comboBox = QtWidgets.QComboBox(self.groupBox_2)
        self.comboBox.setGeometry(QtCore.QRect(660, 0, 421, 30))
        self.comboBox.setObjectName("comboBox")
        self.gridLayout.addWidget(self.groupBox_2, 2, 0, 1, 1)

        self.retranslateUi(Dialog_visualiseGraph)
        QtCore.QMetaObject.connectSlotsByName(Dialog_visualiseGraph)

    def retranslateUi(self, Dialog_visualiseGraph):
        _translate = QtCore.QCoreApplication.translate
        Dialog_visualiseGraph.setWindowTitle(_translate("Dialog_visualiseGraph", "Graph Visualisation"))
        self.pushButton_view.setText(_translate("Dialog_visualiseGraph", "View graph"))
        self.checkBox_blackandwhite.setText(_translate("Dialog_visualiseGraph", "Black and white"))
        self.checkBox_fontsize.setText(_translate("Dialog_visualiseGraph", "Categories larger font"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_visualiseGraph = QtWidgets.QDialog()
    ui = Ui_Dialog_visualiseGraph()
    ui.setupUi(Dialog_visualiseGraph)
    Dialog_visualiseGraph.show()
    sys.exit(app.exec_())

