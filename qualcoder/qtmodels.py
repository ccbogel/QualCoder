
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal

class ListObjectModel(QtCore.QAbstractListModel):
    checkstate_changed = pyqtSignal(str,bool)
    def __init__(self,data,key,checkable=False,*args,**kwargs):
        super(ListObjectModel,self).__init__(*args,**kwargs)
        self.checkable = checkable
        self.nativedata = data
        self.key = key
        self._checkstate = {}

    def rowCount(self,index):
        return len(self.nativedata) 

    def data(self,index,role):
        idx = index.row()
        if role == Qt.DisplayRole:
            return self.nativedata[idx][self.key]
        elif role == Qt.ForegroundRole:
            return QtGui.QBrush(Qt.black)
        elif role == Qt.BackgroundRole:
            return QtGui.QBrush(QtGui.QColor(self.nativedata[idx].get('color',Qt.white)))
        elif role == Qt.CheckStateRole:
            return self._checkstate.get(key,Qt.CheckState.Unchecked)

    def flags(self,index):
        if self.checkable:
            return  Qt.ItemIsUserCheckable | Qt.ItemIsEnabled 
        else:
            return  Qt.ItemIsEnabled | Qt.ItemIsSelectable 

    def reset_data(self,data):
        """ completly reset data """
        self.nativedata = data
        self._checkstate.clear()
        self.modelReset.emit()

    def make_row_to_key(self,data):
        return {i:val[self.key] for i,val in enumerate(data)}

    def setData(self,index, value, role):
        key = self._row_to_key[index.row()]
        if role == Qt.CheckStateRole:
            self._checkstate[key] = value
            self.checkstate_changed.emit(key,bool(value))
        return True

class DictListModel(QtCore.QAbstractListModel):
    checkstate_changed = pyqtSignal(str,bool)
    def __init__(self,data,key=None,checkable=False,*args,**kwargs):
        super(DictListModel,self).__init__(*args,**kwargs)
        self.key = key
        self.checkable = checkable
        self.nativedata = data
        self._checkstate = {}
        self._row_to_key = self.make_row_to_key(data) 

    def rowCount(self,index):
        return len(self.nativedata) 

    def makeProxy(self,key):
        return DictListModel(self.nativedata,key=key)

    def data(self,index,role):
        if index.isValid():
            key = self._row_to_key[index.row()]
            if role == Qt.DisplayRole:
                if self.key is None:
                    return key
                else:
                    return self.nativedata[key][self.key]
            elif role == Qt.ForegroundRole:
                return QtGui.QBrush(Qt.black)
            elif role == Qt.BackgroundRole:
                return QtGui.QBrush(QtGui.QColor(self.nativedata[key].get('color',Qt.white)))
            elif role == Qt.CheckStateRole:
                return self._checkstate.get(key,Qt.CheckState.Unchecked)

    def flags(self,index):
        if self.checkable:
            return  Qt.ItemIsUserCheckable | Qt.ItemIsEnabled 
        else:
            return  Qt.ItemIsEnabled | Qt.ItemIsSelectable 

    def reset_data(self,data):
        """ completly reset data """
        self.nativedata = data
        self._checkstate.clear()
        self._row_to_key = self.make_row_to_key(data) 
        self.modelReset.emit()

    def make_row_to_key(self,data):
        return {i:key for i,key in enumerate(data)}

    def setData(self,index, value, role):
        key = self._row_to_key[index.row()]
        if role == Qt.CheckStateRole:
            self._checkstate[key] = value
            self.checkstate_changed.emit(key,bool(value))
        return True
