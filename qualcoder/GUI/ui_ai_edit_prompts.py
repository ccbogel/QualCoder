# Form implementation generated from reading ui file 'c:\Users\kai\Documents\Programmierung\2023QualCoder\GUI_UIs\ui_ai_edit_prompts.ui'
#
# Created by: PyQt6 UI code generator 6.7.1
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog_AiPrompts(object):
    def setupUi(self, Dialog_AiPrompts):
        Dialog_AiPrompts.setObjectName("Dialog_AiPrompts")
        Dialog_AiPrompts.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        Dialog_AiPrompts.resize(879, 556)
        self.gridLayout_2 = QtWidgets.QGridLayout(Dialog_AiPrompts)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.widget = QtWidgets.QWidget(parent=Dialog_AiPrompts)
        self.widget.setObjectName("widget")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.widget)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.splitter = QtWidgets.QSplitter(parent=self.widget)
        self.splitter.setMinimumSize(QtCore.QSize(6, 0))
        self.splitter.setLineWidth(1)
        self.splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.splitter.setOpaqueResize(True)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName("splitter")
        self.widget_3 = QtWidgets.QWidget(parent=self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget_3.sizePolicy().hasHeightForWidth())
        self.widget_3.setSizePolicy(sizePolicy)
        self.widget_3.setMinimumSize(QtCore.QSize(100, 0))
        self.widget_3.setObjectName("widget_3")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.widget_3)
        self.verticalLayout_3.setContentsMargins(0, 0, 3, 0)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.label = QtWidgets.QLabel(parent=self.widget_3)
        self.label.setObjectName("label")
        self.verticalLayout_3.addWidget(self.label)
        self.treeWidget_prompts = QtWidgets.QTreeWidget(parent=self.widget_3)
        self.treeWidget_prompts.setProperty("showDropIndicator", False)
        self.treeWidget_prompts.setRootIsDecorated(False)
        self.treeWidget_prompts.setItemsExpandable(False)
        self.treeWidget_prompts.setExpandsOnDoubleClick(False)
        self.treeWidget_prompts.setObjectName("treeWidget_prompts")
        self.treeWidget_prompts.headerItem().setText(0, "1")
        self.treeWidget_prompts.header().setVisible(False)
        self.verticalLayout_3.addWidget(self.treeWidget_prompts)
        self.widget_7 = QtWidgets.QWidget(parent=self.widget_3)
        self.widget_7.setObjectName("widget_7")
        self.horizontalLayout_5 = QtWidgets.QHBoxLayout(self.widget_7)
        self.horizontalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.pushButton_new_prompt = QtWidgets.QPushButton(parent=self.widget_7)
        self.pushButton_new_prompt.setObjectName("pushButton_new_prompt")
        self.horizontalLayout_5.addWidget(self.pushButton_new_prompt)
        self.pushButton_duplicate_prompt = QtWidgets.QPushButton(parent=self.widget_7)
        self.pushButton_duplicate_prompt.setObjectName("pushButton_duplicate_prompt")
        self.horizontalLayout_5.addWidget(self.pushButton_duplicate_prompt)
        self.pushButton_delete_prompt = QtWidgets.QPushButton(parent=self.widget_7)
        self.pushButton_delete_prompt.setObjectName("pushButton_delete_prompt")
        self.horizontalLayout_5.addWidget(self.pushButton_delete_prompt)
        self.verticalLayout_3.addWidget(self.widget_7)
        self.widget_prompt_details = QtWidgets.QWidget(parent=self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget_prompt_details.sizePolicy().hasHeightForWidth())
        self.widget_prompt_details.setSizePolicy(sizePolicy)
        self.widget_prompt_details.setObjectName("widget_prompt_details")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.widget_prompt_details)
        self.verticalLayout.setContentsMargins(3, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.widget_4 = QtWidgets.QWidget(parent=self.widget_prompt_details)
        self.widget_4.setObjectName("widget_4")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.widget_4)
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_2 = QtWidgets.QLabel(parent=self.widget_4)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_2.addWidget(self.label_2)
        self.lineEdit_name = QtWidgets.QLineEdit(parent=self.widget_4)
        self.lineEdit_name.setObjectName("lineEdit_name")
        self.horizontalLayout_2.addWidget(self.lineEdit_name)
        self.label_uneditable = QtWidgets.QLabel(parent=self.widget_4)
        self.label_uneditable.setObjectName("label_uneditable")
        self.horizontalLayout_2.addWidget(self.label_uneditable)
        self.verticalLayout.addWidget(self.widget_4)
        self.widget_5 = QtWidgets.QWidget(parent=self.widget_prompt_details)
        self.widget_5.setObjectName("widget_5")
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout(self.widget_5)
        self.horizontalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.groupBox = QtWidgets.QGroupBox(parent=self.widget_5)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 50))
        self.groupBox.setObjectName("groupBox")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout(self.groupBox)
        self.horizontalLayout_3.setContentsMargins(9, 6, -1, 6)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.radioButton_system = QtWidgets.QRadioButton(parent=self.groupBox)
        self.radioButton_system.setEnabled(False)
        self.radioButton_system.setCheckable(True)
        self.radioButton_system.setChecked(True)
        self.radioButton_system.setObjectName("radioButton_system")
        self.horizontalLayout_3.addWidget(self.radioButton_system)
        self.radioButton_user = QtWidgets.QRadioButton(parent=self.groupBox)
        self.radioButton_user.setObjectName("radioButton_user")
        self.horizontalLayout_3.addWidget(self.radioButton_user)
        self.radioButton_project = QtWidgets.QRadioButton(parent=self.groupBox)
        self.radioButton_project.setObjectName("radioButton_project")
        self.horizontalLayout_3.addWidget(self.radioButton_project)
        self.horizontalLayout_4.addWidget(self.groupBox)
        self.groupBox_2 = QtWidgets.QGroupBox(parent=self.widget_5)
        self.groupBox_2.setObjectName("groupBox_2")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.groupBox_2)
        self.verticalLayout_4.setContentsMargins(-1, 6, -1, 6)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.comboBox_type = QtWidgets.QComboBox(parent=self.groupBox_2)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comboBox_type.sizePolicy().hasHeightForWidth())
        self.comboBox_type.setSizePolicy(sizePolicy)
        self.comboBox_type.setObjectName("comboBox_type")
        self.verticalLayout_4.addWidget(self.comboBox_type)
        self.horizontalLayout_4.addWidget(self.groupBox_2)
        self.verticalLayout.addWidget(self.widget_5)
        self.widget_6 = QtWidgets.QWidget(parent=self.widget_prompt_details)
        self.widget_6.setObjectName("widget_6")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.widget_6)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.label_3 = QtWidgets.QLabel(parent=self.widget_6)
        self.label_3.setObjectName("label_3")
        self.verticalLayout_2.addWidget(self.label_3)
        self.plainTextEdit_description = QtWidgets.QPlainTextEdit(parent=self.widget_6)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.plainTextEdit_description.sizePolicy().hasHeightForWidth())
        self.plainTextEdit_description.setSizePolicy(sizePolicy)
        self.plainTextEdit_description.setMinimumSize(QtCore.QSize(0, 30))
        self.plainTextEdit_description.setMaximumSize(QtCore.QSize(16777215, 130))
        self.plainTextEdit_description.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.plainTextEdit_description.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        self.plainTextEdit_description.setObjectName("plainTextEdit_description")
        self.verticalLayout_2.addWidget(self.plainTextEdit_description)
        self.label_4 = QtWidgets.QLabel(parent=self.widget_6)
        self.label_4.setObjectName("label_4")
        self.verticalLayout_2.addWidget(self.label_4)
        self.plainTextEdit_prompt_text = QtWidgets.QPlainTextEdit(parent=self.widget_6)
        self.plainTextEdit_prompt_text.setMinimumSize(QtCore.QSize(100, 0))
        self.plainTextEdit_prompt_text.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.plainTextEdit_prompt_text.setObjectName("plainTextEdit_prompt_text")
        self.verticalLayout_2.addWidget(self.plainTextEdit_prompt_text)
        self.verticalLayout.addWidget(self.widget_6)
        self.horizontalLayout.addWidget(self.splitter)
        self.gridLayout_2.addWidget(self.widget, 0, 0, 1, 1)
        self.buttonBox = QtWidgets.QDialogButtonBox(parent=Dialog_AiPrompts)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.gridLayout_2.addWidget(self.buttonBox, 2, 0, 1, 1)
        self.line = QtWidgets.QFrame(parent=Dialog_AiPrompts)
        self.line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        self.line.setObjectName("line")
        self.gridLayout_2.addWidget(self.line, 1, 0, 1, 1)

        self.retranslateUi(Dialog_AiPrompts)
        QtCore.QMetaObject.connectSlotsByName(Dialog_AiPrompts)

    def retranslateUi(self, Dialog_AiPrompts):
        _translate = QtCore.QCoreApplication.translate
        Dialog_AiPrompts.setWindowTitle(_translate("Dialog_AiPrompts", "AI Edit Prompts"))
        self.label.setText(_translate("Dialog_AiPrompts", "Prompts library:"))
        self.pushButton_new_prompt.setText(_translate("Dialog_AiPrompts", "New"))
        self.pushButton_duplicate_prompt.setText(_translate("Dialog_AiPrompts", "Duplicate"))
        self.pushButton_delete_prompt.setText(_translate("Dialog_AiPrompts", "Delete"))
        self.label_2.setText(_translate("Dialog_AiPrompts", "Name:"))
        self.label_uneditable.setText(_translate("Dialog_AiPrompts", "(Uneditable system prompt)"))
        self.groupBox.setTitle(_translate("Dialog_AiPrompts", "Scope:"))
        self.radioButton_system.setText(_translate("Dialog_AiPrompts", "system"))
        self.radioButton_user.setText(_translate("Dialog_AiPrompts", "user"))
        self.radioButton_project.setText(_translate("Dialog_AiPrompts", "project"))
        self.groupBox_2.setTitle(_translate("Dialog_AiPrompts", "Type:"))
        self.label_3.setText(_translate("Dialog_AiPrompts", "Prompt description:"))
        self.label_4.setText(_translate("Dialog_AiPrompts", "Prompt text (this will be send to the AI):"))