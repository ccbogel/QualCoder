# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_visualise_graph_original.ui'
#
# Created by: PyQt5 UI code generator 5.12.3
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog_visualiseGraph_original(object):
    def setupUi(self, Dialog_visualiseGraph_original):
        Dialog_visualiseGraph_original.setObjectName("Dialog_visualiseGraph_original")
        Dialog_visualiseGraph_original.resize(1098, 744)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_visualiseGraph_original)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog_visualiseGraph_original)
        self.groupBox_2.setMinimumSize(QtCore.QSize(0, 60))
        self.groupBox_2.setTitle("")
        self.groupBox_2.setObjectName("groupBox_2")
        self.pushButton_view = QtWidgets.QPushButton(self.groupBox_2)
        self.pushButton_view.setGeometry(QtCore.QRect(0, 0, 161, 27))
        self.pushButton_view.setObjectName("pushButton_view")
        self.checkBox_blackandwhite = QtWidgets.QCheckBox(self.groupBox_2)
        self.checkBox_blackandwhite.setGeometry(QtCore.QRect(170, 0, 191, 22))
        self.checkBox_blackandwhite.setObjectName("checkBox_blackandwhite")
        self.comboBox = QtWidgets.QComboBox(self.groupBox_2)
        self.comboBox.setGeometry(QtCore.QRect(650, 0, 421, 30))
        self.comboBox.setObjectName("comboBox")
        self.checkBox_listview = QtWidgets.QCheckBox(self.groupBox_2)
        self.checkBox_listview.setGeometry(QtCore.QRect(170, 30, 141, 22))
        self.checkBox_listview.setObjectName("checkBox_listview")
        self.comboBox_fontsize = QtWidgets.QComboBox(self.groupBox_2)
        self.comboBox_fontsize.setGeometry(QtCore.QRect(550, 0, 71, 31))
        self.comboBox_fontsize.setObjectName("comboBox_fontsize")
        self.label = QtWidgets.QLabel(self.groupBox_2)
        self.label.setGeometry(QtCore.QRect(430, 6, 111, 17))
        self.label.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.groupBox_2, 1, 0, 1, 1)
        self.graphicsView = QtWidgets.QGraphicsView(Dialog_visualiseGraph_original)
        self.graphicsView.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.graphicsView.setObjectName("graphicsView")
        self.gridLayout.addWidget(self.graphicsView, 0, 0, 1, 1)

        self.retranslateUi(Dialog_visualiseGraph_original)
        QtCore.QMetaObject.connectSlotsByName(Dialog_visualiseGraph_original)
        Dialog_visualiseGraph_original.setTabOrder(self.graphicsView, self.pushButton_view)
        Dialog_visualiseGraph_original.setTabOrder(self.pushButton_view, self.checkBox_blackandwhite)
        Dialog_visualiseGraph_original.setTabOrder(self.checkBox_blackandwhite, self.checkBox_listview)
        Dialog_visualiseGraph_original.setTabOrder(self.checkBox_listview, self.comboBox_fontsize)
        Dialog_visualiseGraph_original.setTabOrder(self.comboBox_fontsize, self.comboBox)

    def retranslateUi(self, Dialog_visualiseGraph_original):
        _translate = QtCore.QCoreApplication.translate
        Dialog_visualiseGraph_original.setWindowTitle(_translate("Dialog_visualiseGraph_original", "Graph Visualisation"))
        self.pushButton_view.setText(_translate("Dialog_visualiseGraph_original", "View graph"))
        self.checkBox_blackandwhite.setText(_translate("Dialog_visualiseGraph_original", "Black and white"))
        self.checkBox_listview.setText(_translate("Dialog_visualiseGraph_original", "List view"))
        self.label.setText(_translate("Dialog_visualiseGraph_original", "Font size"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_visualiseGraph_original = QtWidgets.QDialog()
    ui = Ui_Dialog_visualiseGraph_original()
    ui.setupUi(Dialog_visualiseGraph_original)
    Dialog_visualiseGraph_original.show()
    sys.exit(app.exec_())
