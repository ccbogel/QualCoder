# Form implementation generated from reading ui file 'ui_dialog_organiser.ui'
#
# Created by: PyQt6 UI code generator 6.5.2
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_DialogOrganiser(object):
    def setupUi(self, DialogOrganiser):
        DialogOrganiser.setObjectName("DialogOrganiser")
        DialogOrganiser.resize(1024, 600)
        self.gridLayout = QtWidgets.QGridLayout(DialogOrganiser)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox_header = QtWidgets.QGroupBox(parent=DialogOrganiser)
        self.groupBox_header.setMinimumSize(QtCore.QSize(0, 44))
        self.groupBox_header.setMaximumSize(QtCore.QSize(16777215, 70))
        self.groupBox_header.setTitle("")
        self.groupBox_header.setObjectName("groupBox_header")
        self.pushButton_export = QtWidgets.QPushButton(parent=self.groupBox_header)
        self.pushButton_export.setGeometry(QtCore.QRect(110, 3, 28, 28))
        self.pushButton_export.setText("")
        self.pushButton_export.setObjectName("pushButton_export")
        self.label_zoom = QtWidgets.QLabel(parent=self.groupBox_header)
        self.label_zoom.setGeometry(QtCore.QRect(41, 3, 28, 28))
        self.label_zoom.setText("")
        self.label_zoom.setObjectName("label_zoom")
        self.pushButton_create_category = QtWidgets.QPushButton(parent=self.groupBox_header)
        self.pushButton_create_category.setGeometry(QtCore.QRect(70, 3, 28, 28))
        self.pushButton_create_category.setText("")
        self.pushButton_create_category.setObjectName("pushButton_create_category")
        self.pushButton_selectbranch = QtWidgets.QPushButton(parent=self.groupBox_header)
        self.pushButton_selectbranch.setGeometry(QtCore.QRect(10, 3, 28, 28))
        self.pushButton_selectbranch.setText("")
        self.pushButton_selectbranch.setObjectName("pushButton_selectbranch")
        self.label_loaded_graph = QtWidgets.QLabel(parent=self.groupBox_header)
        self.label_loaded_graph.setGeometry(QtCore.QRect(260, 2, 721, 41))
        self.label_loaded_graph.setWordWrap(True)
        self.label_loaded_graph.setObjectName("label_loaded_graph")
        self.pushButton_apply = QtWidgets.QPushButton(parent=self.groupBox_header)
        self.pushButton_apply.setGeometry(QtCore.QRect(150, 3, 91, 28))
        self.pushButton_apply.setObjectName("pushButton_apply")
        self.gridLayout.addWidget(self.groupBox_header, 0, 0, 1, 1)
        self.graphicsView = QtWidgets.QGraphicsView(parent=DialogOrganiser)
        self.graphicsView.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft)
        self.graphicsView.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.graphicsView.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.graphicsView.setObjectName("graphicsView")
        self.gridLayout.addWidget(self.graphicsView, 1, 0, 1, 1)

        self.retranslateUi(DialogOrganiser)
        QtCore.QMetaObject.connectSlotsByName(DialogOrganiser)
        DialogOrganiser.setTabOrder(self.pushButton_selectbranch, self.pushButton_create_category)
        DialogOrganiser.setTabOrder(self.pushButton_create_category, self.pushButton_export)
        DialogOrganiser.setTabOrder(self.pushButton_export, self.graphicsView)

    def retranslateUi(self, DialogOrganiser):
        _translate = QtCore.QCoreApplication.translate
        DialogOrganiser.setWindowTitle(_translate("DialogOrganiser", "Graph Visualisation"))
        self.pushButton_export.setToolTip(_translate("DialogOrganiser", "Export image"))
        self.label_zoom.setToolTip(_translate("DialogOrganiser", "Click on the graph area and press + or W to zoom in. Press - or Q to zoom in or zoom out."))
        self.pushButton_create_category.setToolTip(_translate("DialogOrganiser", "<html><head/><body><p>Create category</p></body></html>"))
        self.pushButton_selectbranch.setToolTip(_translate("DialogOrganiser", "Select code branch"))
        self.label_loaded_graph.setText(_translate("DialogOrganiser", "Code organiser. Right click on codes and categories to link and merge. Add new categories. Re-structure codes tree."))
        self.pushButton_apply.setToolTip(_translate("DialogOrganiser", "<html><head/><body><p>Apply changed structure.</p><p>Warning. No Undo option.</p></body></html>"))
        self.pushButton_apply.setText(_translate("DialogOrganiser", "Apply"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    DialogOrganiser = QtWidgets.QDialog()
    ui = Ui_DialogOrganiser()
    ui.setupUi(DialogOrganiser)
    DialogOrganiser.show()
    sys.exit(app.exec())
