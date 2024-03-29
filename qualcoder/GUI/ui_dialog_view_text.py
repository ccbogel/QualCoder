# Form implementation generated from reading ui file 'ui_dialog_view_text.ui'
#
# Created by: PyQt6 UI code generator 6.2.3
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog_view_text(object):
    def setupUi(self, Dialog_view_text):
        Dialog_view_text.setObjectName("Dialog_view_text")
        Dialog_view_text.resize(700, 404)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_view_text)
        self.gridLayout.setObjectName("gridLayout")
        self.textEdit = QtWidgets.QTextEdit(Dialog_view_text)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout.addWidget(self.textEdit, 0, 0, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(Dialog_view_text)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 32))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 32))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.buttonBox = QtWidgets.QDialogButtonBox(self.groupBox)
        self.buttonBox.setGeometry(QtCore.QRect(490, 0, 181, 25))
        self.buttonBox.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.pushButton_clear = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_clear.setGeometry(QtCore.QRect(380, 0, 89, 26))
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.pushButton_next = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_next.setGeometry(QtCore.QRect(220, 0, 28, 28))
        self.pushButton_next.setText("")
        self.pushButton_next.setObjectName("pushButton_next")
        self.lineEdit_search = QtWidgets.QLineEdit(self.groupBox)
        self.lineEdit_search.setGeometry(QtCore.QRect(30, 0, 151, 28))
        self.lineEdit_search.setObjectName("lineEdit_search")
        self.label_search_totals = QtWidgets.QLabel(self.groupBox)
        self.label_search_totals.setGeometry(QtCore.QRect(260, 2, 81, 22))
        self.label_search_totals.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label_search_totals.setObjectName("label_search_totals")
        self.label_search_regex = QtWidgets.QLabel(self.groupBox)
        self.label_search_regex.setGeometry(QtCore.QRect(0, 4, 24, 24))
        self.label_search_regex.setAutoFillBackground(False)
        self.label_search_regex.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.label_search_regex.setLineWidth(0)
        self.label_search_regex.setText("")
        self.label_search_regex.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight|QtCore.Qt.AlignmentFlag.AlignTrailing|QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.label_search_regex.setWordWrap(True)
        self.label_search_regex.setObjectName("label_search_regex")
        self.pushButton_previous = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_previous.setGeometry(QtCore.QRect(190, 0, 28, 28))
        self.pushButton_previous.setText("")
        self.pushButton_previous.setObjectName("pushButton_previous")
        self.gridLayout.addWidget(self.groupBox, 1, 0, 1, 1)
        self.label_info = QtWidgets.QLabel(Dialog_view_text)
        self.label_info.setMinimumSize(QtCore.QSize(0, 80))
        self.label_info.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeading|QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignTop)
        self.label_info.setWordWrap(True)
        self.label_info.setObjectName("label_info")
        self.gridLayout.addWidget(self.label_info, 2, 0, 1, 1)

        self.retranslateUi(Dialog_view_text)
        self.buttonBox.accepted.connect(Dialog_view_text.accept) # type: ignore
        self.buttonBox.rejected.connect(Dialog_view_text.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog_view_text)

    def retranslateUi(self, Dialog_view_text):
        _translate = QtCore.QCoreApplication.translate
        Dialog_view_text.setWindowTitle(_translate("Dialog_view_text", "View and Edit Text"))
        self.pushButton_clear.setToolTip(_translate("Dialog_view_text", "Clear all text"))
        self.pushButton_clear.setText(_translate("Dialog_view_text", "Clear"))
        self.pushButton_next.setToolTip(_translate("Dialog_view_text", "<html><head/><body><p>Next</p></body></html>"))
        self.lineEdit_search.setToolTip(_translate("Dialog_view_text", "Search for text."))
        self.label_search_totals.setText(_translate("Dialog_view_text", "0 / 0"))
        self.label_search_regex.setToolTip(_translate("Dialog_view_text", "<html><head/><body><p>Search uses Regex functions. </p><p>A dot ‘.’ is used as a wild card, e.g. ‘.ears’ will match ‘bears’ and ‘years’. </p><p>A ‘?’ after a character will match one or none times that character, e.g. ‘bears?’ will match ‘bear’ and ‘bears’ </p><p><span style=\" background-color:transparent;\">A ‘*’ after a character will match zero or more times. </span></p><p><span style=\" background-color:transparent;\">‘</span>\\. will match the dot symbol, ‘\\?’ will match the question mark. ‘\\n’ will match the line ending symbol. </p><p>Regex cheatsheet: <a href=\"http://www.rexegg.com/regex-quickstart.html\"><span style=\" text-decoration: underline; color:#000080;\">www.rexegg.com/regex-quickstart.html</span></a></p></body></html>"))
        self.pushButton_previous.setToolTip(_translate("Dialog_view_text", "<html><head/><body><p>Previous</p></body></html>"))
        self.label_info.setToolTip(_translate("Dialog_view_text", "Avoid selecting sections of text with a combination of not underlined (not coded / annotated / case-assigned) and underlined (coded, annotated, case-assigned).\n"
"Positions of the underlying codes / annotations / case-assigned may not correctly adjust if text is typed over or deleted.\n"
"Do not code this text until you reload Coding - Code Text from the menu bar."))
        self.label_info.setText(_translate("Dialog_view_text", "Do not select sections of text with a combination of not underlined (not coded / annotated / case-assigned) and underlined (coded, annotated, case-assigned). Positions of the underlying codes / annotations / case-assigned may not correctly adjust if selected text is typed over or deleted.\n"
"Do not code this text until you reload Coding - Code Text from the menu bar."))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_view_text = QtWidgets.QDialog()
    ui = Ui_Dialog_view_text()
    ui.setupUi(Dialog_view_text)
    Dialog_view_text.show()
    sys.exit(app.exec())
