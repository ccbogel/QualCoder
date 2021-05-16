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


from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QBrush, QFont, QColor
from PyQt5.QtCore import *


class Highlighter(QSyntaxHighlighter):
    """ SQL code highlighter """

    highlighting_rules = []

    def __init__(self, parent):
        QSyntaxHighlighter.__init__(self, parent)
        self.parent = parent
        self.highlighting_rules = []
        self.create_rules()

    def create_rules(self, dark=False):
        """ Sets stling rules for SQL text.
         param: dark = True - changes some text coloring """

        # Keywords
        keywords = ["ABORT", "ACTION", "ADD", "AFTER", "ALL", "ALTER", "ANALYZE", "AND", "AS",
                    "ASC", "ATTACH", "AUTOINCREMENT", "BEFORE", "BEGIN", "BETWEEN", "BY", "CASCADE", "CASE", "CAST",
                    "CHECK", "COLLATE", "COLUMN",
                    "COMMIT", "CONFLICT", "CONSTRAINT", "CREATE", "CROSS", "CURRENT_DATE", "CURRENT_TIME",
                    "CURRENT_TIMESTAMP", "DATABASE", "DEFAULT",
                    "DEFERRABLE", "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DROP", "EACH", "ELSE", "END",
                    "ESCAPE", "EXCEPT", "EXCLUSIVE",
                    "EXISTS", "EXPLAIN", "FAIL", "FOR", "FOREIGN", "FROM", "FULL", "GLOB", "GROUP", "HAVING", "IF",
                    "IGNORE", "IMMEDIATE", "IN", "INDEX",
                    "INDEXED", "INITIALLY", "INNER", "INSERT", "INSTEAD", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN",
                    "KEY", "LEFT", "LIKE", "LIMIT", "LOWER"
                                                    "MATCH", "NATURAL", "NO", "NOT", "NOTNULL", "NULL", "OF", "OFFSET",
                    "ON", "OR", "ORDER", "OUTER", "PLAN", "PRAGMA", "PRIMARY", "QUERY",
                    "RAISE", "RECURSIVE", "REFERENCES", "REGEXP", "REINDEX", "RELEASE", "RENAME", "REPLACE", "RESTRICT",
                    "RIGHT", "ROLLBACK", "ROW",
                    "SAVEPOINT", "SELECT", "SET", "TABLE", "TEMP", "TEMPORARY", "THEN", "TO", "TRANSACTION", "TRIGGER",
                    "UNION", "UNIQUE", "UPDATE",
                    "USING", "VACUUM", "VALUES", "VIEW", "VIRTUAL", "WHEN", "WHERE", "WITH", "WITHOUT"]
        tmp = []
        for k in keywords:
            tmp.append(k + " ")
            tmp.append(k.lower() + " ")
        keywords = tmp
        keyword_format = QTextCharFormat()
        brush = QBrush(Qt.darkRed, Qt.SolidPattern)
        if dark:
            brush = QBrush(QColor("#FFAF0A"), Qt.SolidPattern)
        keyword_format.setForeground(brush)
        keyword_format.setFontWeight(QFont.Bold)
        self.highlighting_rules = [(QRegExp(word), keyword_format)
                                   for word in keywords]

        # Data types
        data_types = ["TEXT", "NUMERIC", "INTEGER", "REAL", "INT", "TINYINT", "SMALLINT",
                      "MEDIUMINT", "BIGINT", "CHARACTER", "VARCHAR", "NCHAR", "NVARCHAR", "CLOB", "DOUBLE",
                      "FLOAT", "DECIMAL", "BOOLEAN", "DATE", "DATETIME", "NONE", "text", "numeric", "integer",
                      "real", "int", "tinyint", "smallint", "mediumint", "bigint", "character", "varchar", "nchar",
                      "nvarchar", "clob", "double", "float", "decimal", "boolean", "date", "datetime", "none"]
        data_types_format = QTextCharFormat()
        brush = QBrush(Qt.darkGreen, Qt.SolidPattern)
        data_types_format.setForeground(brush)
        data_types_format.setFontWeight(QFont.Bold)
        self.highlighting_rules += [(QRegExp(word), data_types_format)
                                    for word in data_types]

        # Functions
        function_words = ["count", "max", "min", "avg", "sum", "random", "abs", "upper",
                          "lower", "length", "sqlite_version", "COUNT", "MAX", "MIN", "AVG", "SUM", "RANDOM", "ABS",
                          "UPPER", "LOWER", "LENGTH", "SQLITE_VERSION", ]
        functions_format = QTextCharFormat()
        brush = QBrush(Qt.darkBlue, Qt.SolidPattern)
        if dark:
            brush = QBrush(QColor("#00BFFF"), Qt.SolidPattern)
        functions_format.setForeground(brush)
        functions_format.setFontWeight(QFont.Bold)
        self.highlighting_rules += [(QRegExp(word), functions_format)
                                    for word in function_words]

        # In-line comment
        comment_format = QTextCharFormat()
        brush = QBrush(QColor("#00BFFF"), Qt.SolidPattern)
        if dark:
            brush = QBrush(Qt.yellow, Qt.SolidPattern)
        comment_format.setForeground(brush)
        self.highlighting_rules += [(QRegExp("--[^\n]*"), comment_format)]

        # Multi-line comment
        multi_comment_format = QTextCharFormat()
        brush = QBrush(Qt.blue, Qt.SolidPattern)
        if dark:
            brush = QBrush(Qt.yellow, Qt.SolidPattern)
        multi_comment_format.setForeground(brush)
        self.highlighting_rules += [(QRegExp("/*.*/"), multi_comment_format)]

        # Double quoted string
        string_format = QTextCharFormat()
        brush = QBrush(Qt.magenta, Qt.SolidPattern)
        string_format.setForeground(brush)
        self.highlighting_rules += [(QRegExp("\".*\""), string_format)]

        # Single quoted String
        string2_format = QTextCharFormat()
        brush = QBrush(Qt.magenta, Qt.SolidPattern)
        string2_format.setForeground(brush)
        self.highlighting_rules += [(QRegExp("\'.*\'"), string2_format)]

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)
        self.setCurrentBlockState(0)


