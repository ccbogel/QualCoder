#############################################################################
##
## Copyright (C) 2013 Riverbank Computing Limited.
## Copyright (C) 2010 Nokia Corporation and/or its subsidiary(-ies).
## All rights reserved.
##
## This file is part of the examples of PyQt.
##
## $QT_BEGIN_LICENSE:BSD$
## You may use this file under the terms of the BSD license as follows:
##
## "Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions are
## met:
##   * Redistributions of source code must retain the above copyright
##     notice, this list of conditions and the following disclaimer.
##   * Redistributions in binary form must reproduce the above copyright
##     notice, this list of conditions and the following disclaimer in
##     the documentation and/or other materials provided with the
##     distribution.
##   * Neither the name of Nokia Corporation and its Subsidiary(-ies) nor
##     the names of its contributors may be used to endorse or promote
##     products derived from this software without specific prior written
##     permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
## A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
## OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
## SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
## LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
## DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
## THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
## (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
## OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
## $QT_END_LICENSE$
##
#############################################################################
## Highlighter code was extracted and modified by Colin Curtain from:
## https://github.com/baoboa/pyqt5/blob/master/examples/richtext/syntaxhighlighter.py


from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QBrush, QFont
from PyQt5.QtCore import *

class Highlighter(QSyntaxHighlighter):
    ''' SQL code highlighter '''

    highlightingRules = []

    def __init__(self, parent):
        QSyntaxHighlighter.__init__(self, parent)
        self.parent = parent
        self.highlightingRules = []

        # keywords
        keywords = ["ABORT", "ACTION", "ADD", "AFTER", "ALL", "ALTER", "ANALYZE", "AND", "AS",
        "ASC", "ATTACH", "AUTOINCREMENT", "BEFORE", "BEGIN", "BETWEEN", "BY", "CASCADE", "CASE", "CAST", "CHECK", "COLLATE", "COLUMN",
        "COMMIT", "CONFLICT", "CONSTRAINT", "CREATE", "CROSS", "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP", "DATABASE", "DEFAULT",
        "DEFERRABLE", "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DROP", "EACH", "ELSE", "END", "ESCAPE", "EXCEPT", "EXCLUSIVE",
        "EXISTS", "EXPLAIN", "FAIL", "FOR", "FOREIGN", "FROM", "FULL", "GLOB", "GROUP", "HAVING", "IF", "IGNORE", "IMMEDIATE", "IN", "INDEX",
        "INDEXED", "INITIALLY", "INNER", "INSERT", "INSTEAD", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "KEY", "LEFT", "LIKE", "LIMIT","LOWER"
        "MATCH", "NATURAL", "NO", "NOT", "NOTNULL", "NULL", "OF", "OFFSET", "ON", "OR", "ORDER", "OUTER", "PLAN", "PRAGMA", "PRIMARY", "QUERY",
        "RAISE", "RECURSIVE", "REFERENCES", "REGEXP", "REINDEX", "RELEASE", "RENAME", "REPLACE", "RESTRICT", "RIGHT", "ROLLBACK", "ROW",
        "SAVEPOINT", "SELECT", "SET", "TABLE", "TEMP", "TEMPORARY", "THEN", "TO", "TRANSACTION", "TRIGGER", "UNION", "UNIQUE", "UPDATE",
        "USING", "VACUUM", "VALUES", "VIEW", "VIRTUAL", "WHEN", "WHERE", "WITH", "WITHOUT"]
        tmp = []
        for k in keywords:
            tmp.append(k + " ")
            tmp.append(k.lower() + " ")
        keywords = tmp

        keywordFormat = QTextCharFormat()
        brush = QBrush( Qt.darkRed, Qt.SolidPattern )
        keywordFormat.setForeground(brush)
        keywordFormat.setFontWeight(QFont.Bold)
        self.highlightingRules = [(QRegExp(word), keywordFormat)
        for word in keywords]

        # data types
        dataTypes = ["TEXT", "NUMERIC", "INTEGER", "REAL", "INT", "TINYINT", "SMALLINT",
        "MEDIUMINT", "BIGINT", "CHARACTER", "VARCHAR", "NCHAR", "NVARCHAR", "CLOB", "DOUBLE",
        "FLOAT", "DECIMAL", "BOOLEAN", "DATE", "DATETIME", "NONE", "text", "numeric", "integer",
        "real", "int", "tinyint", "smallint", "mediumint", "bigint", "character", "varchar", "nchar",
         "nvarchar", "clob", "double", "float", "decimal", "boolean", "date", "datetime", "none"]

        dataTypesFormat = QTextCharFormat()
        brush = QBrush(Qt.darkGreen, Qt.SolidPattern)
        dataTypesFormat.setForeground(brush)
        dataTypesFormat.setFontWeight(QFont.Bold)
        self.highlightingRules += [(QRegExp(word), dataTypesFormat)
        for word in dataTypes]

        # functions
        functionWords = ["count", "max", "min", "avg", "sum","random" ,"abs", "upper",
        "lower", "length", "sqlite_version", "COUNT", "MAX", "MIN", "AVG", "SUM", "RANDOM", "ABS",
        "UPPER", "LOWER", "LENGTH", "SQLITE_VERSION",]
        functionsFormat = QTextCharFormat()
        brush = QBrush(Qt.darkBlue, Qt.SolidPattern)
        functionsFormat.setForeground(brush)
        functionsFormat.setFontWeight(QFont.Bold)
        self.highlightingRules += [(QRegExp(word), functionsFormat)
        for word in functionWords]

        # in-line comment
        commentFormat = QTextCharFormat()
        brush = QBrush(Qt.blue, Qt.SolidPattern)
        commentFormat.setForeground(brush)
        self.highlightingRules += [(QRegExp("--[^\n]*"), commentFormat)]

        # multi-line comment
        multiCommentFormat = QTextCharFormat()
        brush = QBrush(Qt.blue, Qt.SolidPattern)
        multiCommentFormat.setForeground(brush)
        self.highlightingRules += [(QRegExp("/*.*/"), multiCommentFormat)]

        # double quoted string
        stringFormat = QTextCharFormat()
        brush = QBrush(Qt.magenta, Qt.SolidPattern)
        stringFormat.setForeground( brush)
        self.highlightingRules += [(QRegExp("\".*\""), stringFormat)]

        # single quoted String
        string2Format = QTextCharFormat()
        brush = QBrush(Qt.magenta, Qt.SolidPattern)
        string2Format.setForeground(brush)
        self.highlightingRules += [(QRegExp("\'.*\'"), string2Format)]

    def highlightBlock(self, text):
        for pattern, format in self.highlightingRules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)
        self.setCurrentBlockState(0)


