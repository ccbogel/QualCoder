# based on: https://github.com/yjg30737/pyqt-line-number-widget (MIT licence)

from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QTextBrowser
from PyQt6.QtCore import Qt

class LineNumberWidget(QTextBrowser):
    def __init__(self, widget):
        super().__init__()
        self.__initUi(widget)

    def __initUi(self, widget):
        self.__lineCount = widget.document().lineCount()
        self.__size = int(widget.font().pointSizeF())
        self.__styleInit()

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(Qt.NoTextInteraction)

        self.verticalScrollBar().setEnabled(False)

        widget.verticalScrollBar().valueChanged.connect(self.__changeLineWidgetScrollAsTargetedWidgetScrollChanged)

        self.__initLineCount()

    def __changeLineWidgetScrollAsTargetedWidgetScrollChanged(self, v):
        self.verticalScrollBar().setValue(v)

    def __initLineCount(self):
        for n in range(1, self.__lineCount+1):
            self.append(str(n))

    def changeLineCount(self, n):
        max_one = max(self.__lineCount, n)
        diff = n-self.__lineCount
        if max_one == self.__lineCount:
            first_v = self.verticalScrollBar().value()
            for i in range(self.__lineCount, self.__lineCount + diff, -1):
                self.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)
                self.moveCursor(QTextCursor.StartOfLine, QTextCursor.MoveAnchor)
                self.moveCursor(QTextCursor.End, QTextCursor.KeepAnchor)
                self.textCursor().removeSelectedText()
                self.textCursor().deletePreviousChar()
            last_v = self.verticalScrollBar().value()
            if abs(first_v-last_v) != 2:
                self.verticalScrollBar().setValue(first_v)
        else:
            for i in range(self.__lineCount, self.__lineCount + diff, 1):
                self.append(str(i + 1))

        self.__lineCount = n

    def setValue(self, v):
        self.verticalScrollBar().setValue(v)

    def setFontSize(self, s: float):
        self.__size = int(s)
        self.__styleInit()

    def __styleInit(self):
        self.__style = f'''
                       QTextBrowser 
                       {{ 
                       background: transparent; 
                       border: none; 
                       color: #AAA; 
                       font: {self.__size}pt;
                       }}
                       '''
        self.setStyleSheet(self.__style)
        self.setFixedWidth(self.__size*5)