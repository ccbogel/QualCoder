# -*- coding: utf-8 -*-

"""
Copyright (c) 2023 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt

import csv
import datetime
import logging
from openpyxl import load_workbook
import os
import re
from shutil import copyfile
import sqlite3
import sys
import traceback

from .GUI.ui_import_twitter import Ui_Dialog_Import_twitter
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec()


class DialogImportTwitterData(QtWidgets.QDialog):
    """ Import twitter from csv file. csv file created with rtweet.  csv.QUOTE_ALL
    Create cases by User name.
    Create qualitative text files for each tweet, each file name will be the tweet id.
    Assign attributes to cases and files.
    """

    app = None
    parent_textEdit = None
    tweet_fields = ["created_at", "id", "full_text", "coordinates", "retweet_count", "favorite_count", "lang"]
    user_fields = ["name", "screen_name", "location", "url", "description","followers_count", "friends_count",
                   "listed_count", "favourites_count", "statuses_count"]
    filepath = ""
    data = []
    #TODO below vars not used yet
    user_data = []  # obtained from file
    tweet_data = []  # obtained from file

    def __init__(self, app, parent_text_edit):
        """ Need to comment out the connection accept signal line in ui_Dialog_Import.py.
         Otherwise, get a double-up of accept signals. """

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_text_edit
        self.filepath = ""
        # Set up the user interface from Designer.
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_Import_twitter()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.textEdit.setText(information)
        self.ui.pushButton_select_file.pressed.connect(self.select_file)

    def select_file(self):
        """ Select csv file containing tweet data.
        File heading row must contain these field names.
        created_at,id,full_text,coordinates, retweet_count, favorite_count,lang,
        name, screen_name, location, url, description, followers_count, friends_count,listed_count,
        favourites_count, statuses_count

         Called by: __init__ """

        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select Twitter csv file'),
                                                          self.app.settings['directory'], "(*.csv)",
                                                          options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                          )
        self.filepath = response[0]
        if not self.filepath:
            #self.parent_textEdit.append(_("File not imported."))
            return
        self.filepath = self.filepath[0]  # A list of one name
        # Copy file into project folder
        name_split = self.filepath.split("/")
        filename = name_split[-1]
        destination = self.app.project_path + "/documents/" + filename
        copyfile(self.filepath, destination)
        self.pre_check_csv_file()
        self.create_attribute_types()
        self.read_csv_file()
        for d in self.data:
            print(d)

    def pre_check_csv_file(self):
        """ Pre-check the csv file for required header columns and for an equal
        number of columns in entire file.

        All fields must be within quotations marks.
        File heading row must contain these field names.
        autonumber as '', created_at*,id*,full_text*, coordinates, retweet_count, favorite_count,lang,
        name*, screen_name, location, url*, description*, followers_count, friends_count,listed_count,
        favourites_count, statuses_count
        This are 18 columns, but be flexible if fewer columns are in file.
        * These are required 6 columns.
        """

        # Pre-check number of columns and correct quotation format
        pre_check_num_cols = True
        header = []
        with open(self.filepath, 'r', newline='') as f:
            reader = csv.reader(f, delimiter=',', quoting=csv.QUOTE_ALL)
            header = next(reader)
            number_columns = len(header)
            try:
                for row in reader:
                    if len(row) != number_columns:
                        pre_check_num_cols = False
            except csv.Error as err:
                print(err)
                logger.error(('file %s, line %d: %s' % (self.filepath, reader.line_num, err)))
                self.parent_textEdit.append(_("Row error: ") + str(reader.line_num) + "  " + str(err))
                return False
        if not pre_check_num_cols:
            msg = _("Number of columns is inconsistent. May not be all quoted")
            Message(self.app, _("Cannot use file"), _(msg), "warning").exec()
            return
        required_header_fields = True
        warn_msg = _("Missing header columns: ")
        for t in ["created_at", "id", "full_text"]:
            if t not in header:
                warn_msg += "\n" + t
                required_header_fields = False
        # ?? User ID ??
        for u in ["name", "url", "description"]:
            if u not in header:
                warn_msg += "\n" + t
                required_header_fields = False
        if not required_header_fields:
            Message(self.app, _("Cannot use file"), _(warn_msg), "warning").exec()
            return

    def create_attribute_types(self):
        """ Set up the attributes types for case and file.
        field 'id' is renames as tweet_id to prevent clash with exisitng id field
        Try-except as these fields may already exist. """

        tweet_fields = ["created_at", "tweet_id", "full_text", "coordinates", "retweet_count", "favorite_count",
                        "lang"]
        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        sql = "insert into attribute_type (name,date,owner,memo, valueType, caseOrFile) values(?,?,?,?,?,?)"
        for field_name in enumerate(tweet_fields):
            val_type = "character"
            if "_count" in field_name:
                val_type = "numeric"
            try:
                cur.execute(sql, (field_name, now_date, self.app.settings['codername'], "", val_type, 'file'))
                self.app.conn.commit()
            except sqlite3.IntegrityError:
                pass
        user_fields = ["name", "screen_name", "location", "url", "description", "followers_count", "friends_count",
                       "listed_count", "favourites_count", "statuses_count"]
        for field_name in enumerate(user_fields):
            val_type = "character"
            if "_count" in field_name:
                val_type = "numeric"
            try:
                cur.execute(sql, (field_name, now_date, self.app.settings['codername'], "", val_type, 'file'))
                self.app.conn.commit()
            except sqlite3.IntegrityError:
                pass

    def read_csv_file(self):
        """
        First column remove, if generated from rtweet, as its an autonumber field
        tweet_fields = ["created_at", "id", "full_text", "coordinates", "retweet_count", "favorite_count",
                        "lang"]
        user_fields = ["name", "screen_name", "location", "url", "description", "followers_count", "friends_count",
                       "listed_count", "favourites_count", "statuses_count"]
        # add id_str  ?
        # https://developer.twitter.com/en/docs/twitter-api/v1/data-dictionary/object-model/user
        """

        self.ui.label_file.setText(self.filepath)
        # Read data
        self.data = []
        with open(self.filepath, 'r', newline='') as f:
            reader = csv.reader(f, delimiter=',', quoting=csv.QUOTE_ALL)
            header = next(reader)  # first column autogenerated in R
            try:
                for row in reader:
                    self.data.append(row)
            except csv.Error as err:
                pass
                #logger.error(('file %s, line %d: %s' % (self.filepath, reader.line_num, err)))
                #self.parent_textEdit.append(_("Row error: ") + str(reader.line_num) + "  " + str(err))
                #return False
        return True


    '''def insert_data(self):
        """ Insert case, attributes, attribute values and qualitative text. """

        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        name_and_caseids = []
        for i, c in enumerate(self.data):
            try:
                self.ui.label_msg.setText(_("Inserting cases: " + str(i)))
                cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)",
                            (c[0], "", self.app.settings['codername'], now_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                name_and_caseids.append([c[0], cur.fetchone()[0]])
                QtWidgets.QApplication.processEvents()
            except sqlite3.IntegrityError as e:
                fail_msg = str(e) + _(
                    " - Duplicate case names, either in the file, or duplicates with existing cases in the project")
                logger.error(_("Survey not loaded: ") + fail_msg)
                Message(self.app, _('Survey not loaded'), fail_msg, "warning").exec()
                self.parent_textEdit.append(_("Survey not loaded: ") + fail_msg)
                return
        # Insert non-qualitative attribute types, except if they are already present
        sql = "select name from attribute_type where caseOrFile='case'"
        cur.execute(sql)
        result = cur.fetchall()
        existing_attr_names = []
        for r in result:
            existing_attr_names.append(r[0])
        sql = "insert into attribute_type (name,date,owner,memo, valueType, caseOrFile) values(?,?,?,?,?,?)"
        for col, name in enumerate(self.fields):
            if self.fields_type[col] != "qualitative" and col > 0:  # col==0 is the case identifier
                if name not in existing_attr_names:
                    logger.debug(name + " is not in case attribute_types. Adding.")
                    cur.execute(sql, (name, now_date, self.app.settings['codername'], "",
                                      self.fields_type[col], 'case'))
        self.app.conn.commit()

        # Look for pre-existing attributes that are not in the survey and insert blank value rows if present
        survey_field_names = []
        for col, fld_name in enumerate(self.fields):
            if self.fields_type[col] != "qualitative" and col > 0:
                survey_field_names.append(fld_name)
        for name in existing_attr_names:
            if name not in survey_field_names:
                for name_id in name_and_caseids:
                    sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,'',?,?,?,?)"
                    cur.execute(sql, (name, name_id[1], 'case', now_date, self.app.settings['codername']))
        self.app.conn.commit()

        # Insert non-qualitative values to each case using caseids
        sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
        for i, name_id in enumerate(name_and_caseids):
            self.ui.label_msg.setText(_("Inserting attributes to cases: ") + str(i))
            for val in self.data:
                if name_id[0] == val[0]:
                    for col in range(1, len(val)):
                        if self.fields_type[col] != "qualitative":
                            cur.execute(sql, (self.fields[col], val[col], name_id[1], 'case',
                                              now_date, self.app.settings['codername']))
            QtWidgets.QApplication.processEvents()
        self.app.conn.commit()

        # insert qualitative data into source table
        self.ui.label_msg.setText(_("Creating qualitative text file"))
        source_sql = "insert into source(name,fulltext,memo,owner,date, mediapath) values(?,?,?,?,?, Null)"
        for field in range(1, len(self.fields)):  # column 0 is for identifiers
            case_text_list = []
            if self.fields_type[field] == "qualitative":
                # Create one text file combining each row, prefix [case identifier] to each row.
                fulltext = ""
                for row in range(0, len(self.data)):
                    if self.data[row][field] != "":
                        fulltext += "[" + str(self.data[row][0]) + "] "
                        pos0 = len(fulltext) - 1
                        fulltext += str(self.data[row][field]) + "\n\n"
                        pos1 = len(fulltext) - 2
                        case_text = [self.app.settings['codername'], now_date, "", pos0, pos1, name_and_caseids[row][1]]
                        case_text_list.append(case_text)
                # add the current time to the file name to ensure uniqueness and to
                # prevent sqlite Integrity Error. Do not use now_date which contains colons
                now = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H-%M-%S"))
                cur.execute(source_sql,
                            (self.fields[field] + "_" + now, fulltext, "", self.app.settings['codername'], now_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                fid = cur.fetchone()[0]
                case_text_sql = "insert into case_text (owner, date, memo, pos0, pos1, caseid, fid) values(?,?,?,?,?,?,?)"
                for case_text in case_text_list:
                    case_text.append(fid)
                    cur.execute(case_text_sql, case_text)
                self.app.conn.commit()
        logger.info(_("Survey imported"))
        self.parent_textEdit.append(_("Survey imported."))
        Message(self.app, _("Survey imported"), _("Survey imported")).exec()
        self.app.delete_backup = False
        '''
information = '# Instructions for geting twitter data using the R Statistics Package\n\
# Install rtweet, only need to do this once\n\
install.packages("rtweet")\n\
# If you get an error using rtweet instill using this command instead (March 2023)\n\
install.packages("rtweet", repos = "https://ropensci.r-universe.dev/")\n\
\n\
# Start using rtweet\n\
library(rtweet)\n\
\n\
# Opens web page to allow authorisation with your account, should only need to do this once\n\
auth_setup_default()\n\
# Future uses this command will be enough:\n\
auth_as("default")\n\
\n\
# This example shows using a language and location to get tweets: English and USA location\n\
tweets <- search_tweets("lang:en", geocode = lookup_coords("usa"), n = 100)\n\
\n\
# The below instructions are what QualCoder will use:\n\
# Find the tweets and combine with users data, using #judo and a 100 tweets limit as an example\n\
tweets <- search_tweets("#judo",n=100,include_rts=FALSE)\n\
data <- cbind(tweets, users_data(tweets))\n\
\n\
# Trim the data frame to a few columns\n\
\n\
# These are the tweet columns:\n\
#  autonumber,  created_at, id,full_text,source,coordinates, retweet_count, favorite_count,lang\n\
# These are the user columns: \n\
#    name, screen_name, location, url,description,followers_count, friends_count,listed_count, favourites_count, statuses_count\n\
keep_cols <- c("created_at","id","full_text","source","coordinates", "retweet_count", "favorite_count","lang",\n\
"name", "screen_name", "location", "url","description","followers_count", "friends_count","listed_count", "favourites_count", "statuses_count")\n\
data_trimmed = data[keep_cols]\n\
\n\
# Make the data.frame all characters (removes list objects)\n\
data_flattened = data.frame(lapply(data_trimmed, as.character), stringsAsFactors=FALSE)\n\
# Check where it is saving:\n\
getwd()\n\
# Change where is it saving:\n\
setwd("the path you your folder")\n\
\n\
# Write to a csv file\n\
write.csv(data_flattened, "testdata.csv", na="", fileEncoding="UTF-8")'




