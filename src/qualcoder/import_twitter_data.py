# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io/
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
    header = []
    data = []

    def __init__(self, app, parent_text_edit):
        """ Need to comment out the connection accept signal line in ui_Dialog_Import.py.
         Otherwise, get a double-up of accept signals. """

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
                                                          self.app.settings['directory'], "(*.csv)")
        # options=QtWidgets.QFileDialog.Option.DontUseNativeDialog)
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
        if self.pre_check_csv_file():
            self.read_csv_file()
            self.create_attribute_types()
            tweets, cases = self.fill_tweets_data()
            msg = _("Tweet file loaded. Please check via Manage files and Manage cases") + "\n"
            msg += _("Tweets: ") + str(tweets) + "\n" + _("Cases: ") + str(cases)
            self.ui.textEdit.setText(msg)
        else:
            self.ui.textEdit.setText(_("Could not import file"))

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
                Message(self.app, _("Cannot use file"), str(err), "warning").exec()
                logger.error(('file %s, line %d: %s' % (self.filepath, reader.line_num, err)))
                self.parent_textEdit.append(_("Row error: ") + str(reader.line_num) + "  " + str(err))
                return False
        if not pre_check_num_cols:
            msg = _("Number of columns is inconsistent. May not be all quoted")
            Message(self.app, _("Cannot use file"), _(msg), "warning").exec()
            return False
        required_header_fields = True
        warn_msg = _("Missing header columns: ")
        for t in ["id", "full_text"]:
            if t not in header:
                warn_msg += "\n" + _("Tweet field: ") + t
                required_header_fields = False
        for u in ["screen_name"]:  # may add to this list, unsure
            if u not in header:
                warn_msg += "\n" + _("User field: ") + t
                required_header_fields = False
        if not required_header_fields:
            Message(self.app, _("Cannot use file"), _(warn_msg), "warning").exec()
            return False
        return True

    def read_csv_file(self):
        """
        First column ignore, if generated from rtweet, as it is an autonumber field
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
            self.header = next(reader)  # first column autogenerated in R.
            try:
                for row in reader:
                    self.data.append(row)
            except csv.Error as err:
                pass

    def create_attribute_types(self):
        """ Set up the attributes types for case and file.
        Try-except as these fields may already exist.
        Also intersect file header fields with the tweetand user fields listed below, as all may not be used.
        """

        tweet_fields = ["created_at", "coordinates", "retweet_count", "favorite_count", "lang"]
        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        sql = "insert into attribute_type (name,date,owner,memo, valueType, caseOrFile) values(?,?,?,?,?,?)"
        intersected_tweet_fields = list(set(tweet_fields).intersection(set(self.header)))
        for field_name in intersected_tweet_fields:
            val_type = "character"
            if "_count" in field_name:
                val_type = "numeric"
            try:
                cur.execute(sql, (field_name, now_date, self.app.settings['codername'], "", val_type, 'file'))
                self.app.conn.commit()
            except sqlite3.IntegrityError:
                pass
        # screen_name is unique and is used as the case name
        # 'name' from tweets user from rtweet data will be ignored
        user_fields = ["location", "url", "description", "followers_count", "friends_count",
                       "listed_count", "favourites_count", "statuses_count"]
        intersected_user_fields = list(set(user_fields).intersection(set(self.header)))
        for field_name in intersected_user_fields:
            val_type = "character"
            if "_count" in field_name:
                val_type = "numeric"
            try:
                cur.execute(sql, (field_name, now_date, self.app.settings['codername'], "", val_type, 'case'))
                self.app.conn.commit()
            except sqlite3.IntegrityError:
                pass

    def fill_tweets_data(self):
        """ Fill tweets data. Each tweet is a text file in source.
         The tweet id is the file name.
         The screen_name is the unique user name - used for cases.
         see: https://developer.twitter.com/en/docs/twitter-api/v1/data-dictionary/object-model/user
         """

        prog_dialog = QtWidgets.QProgressDialog(_("Importing twitter data"), "", 1, len(self.data), None)
        prog_dialog.setWindowTitle(_("Importing twitter data"))
        prog_dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowCloseButtonHint)
        prog_dialog.setAutoClose(True)
        prog_dialog.setValue(1)
        prog_dialog.show()
        QtCore.QCoreApplication.processEvents()
        now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Get field positions for tweet and user data from from the header
        tweet_fields = ["created_at", "id", "full_text", "coordinates", "retweet_count", "favorite_count", "lang"]
        header_pos = {}
        attribute_name_list = []
        for field_name in tweet_fields:
            try:
                # Some header fields may not be present, required: id, full_text
                header_pos[field_name] = self.header.index(field_name)
                if field_name not in ("id", "full_text"):
                    attribute_name_list.append(field_name)
            except ValueError:
                pass

        user_fields = ["name", "screen_name", "location", "url", "description", "followers_count", "friends_count",
                       "listed_count", "favourites_count", "statuses_count"]
        user_header_pos = {}
        user_attribute_name_list = []
        for field_name in user_fields:
            try:
                # Some header fields may not be present, required: screen_name
                user_header_pos[field_name] = self.header.index(field_name)
                if field_name not in ("screen_name"):
                    user_attribute_name_list.append(field_name)
            except ValueError:
                pass

        cur = self.app.conn.cursor()
        cur.execute("select name from attribute_type where caseOrFile='file' and name not in ('created_at', "
                    "'coordinates', 'retweet_count', 'favorite_count', 'lang')")
        existing_file_attributes = cur.fetchall()
        cur.execute("select name from attribute_type where caseOrFile='case' and name not in ('user_name', 'location', "
                    "'url', 'description', 'followers_count', 'friends_count', 'listed_count', 'favourites_count', "
                    "'statuses_count')")
        existing_case_attributes = cur.fetchall()
        tweets = 0
        cases = 0
        for i, d in enumerate(self.data):
            try:
                cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                            (str(d[header_pos['id']]), d[header_pos['full_text']], None, '',
                             self.app.settings['codername'], now_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                id_ = cur.fetchone()[0]
                tweets += 1
                # add to vectorstore
                if self.app.settings['ai_enable'] == 'True':
                    self.app.ai.sources_vectorstore.import_document(id_, str(d[header_pos['id']]), d[header_pos['full_text']])
                # Insert tweet data attributes
                for att_name in attribute_name_list:
                    cur.execute("insert into attribute (name, attr_type, value, id, date, owner) values(?,'file',?,?,?,?)",
                                [att_name, d[header_pos[att_name]], id_, now_date, self.app.settings['codername']])
                    self.app.conn.commit()
                # Create placeholder entries for pre-existing attributes
                for placeholder_attribute in existing_file_attributes:
                    cur.execute("insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)",
                                [placeholder_attribute[0], id_, now_date, self.app.settings['codername']])
                    self.app.conn.commit()

                # Insert cases with unique case name
                try:
                    cur.execute("insert into cases (name, memo , owner,date) values (?,'',?,?)",
                                [d[user_header_pos['screen_name']], now_date, self.app.settings['codername']])
                    self.app.conn.commit()
                    cur.execute("select last_insert_rowid()")
                    case_id = cur.fetchone()[0]
                    cases += 1
                    #  Insert tweet user attributes
                    for att_name in user_attribute_name_list:
                        cur.execute(
                            "insert into attribute (name, attr_type, value, id, date, owner) values(?,'case',?,?,?,?)",
                            [att_name, d[user_header_pos[att_name]], case_id, now_date, self.app.settings['codername']])
                        self.app.conn.commit()
                    # Create placeholder entries for pre-existing attributes
                    for placeholder_attribute in existing_case_attributes:
                        cur.execute(
                            "insert into attribute (name, attr_type, value, id, date, owner) values(?,'case','',?,?,?)",
                            [placeholder_attribute[0], case_id, now_date, self.app.settings['codername']])
                        self.app.conn.commit()
                except sqlite3.IntegrityError:
                    pass  # Unique case names constraint

                # Link file to case now that both have been entered into database
                cur.execute("select caseid from cases where name = ?", [d[user_header_pos['screen_name']]])
                res = cur.fetchone()
                if res:
                    sql = "insert into case_text (caseid, fid, pos0, pos1, owner, date, memo) values (?,?,0,?,?,?,'')"
                    cur.execute(sql, [res[0], id_, len(d[header_pos['full_text']]), self.app.settings['codername'], now_date])
                    self.app.conn.commit()
                QtCore.QCoreApplication.processEvents()
                prog_dialog.setValue(i)
            except sqlite3.IntegrityError:
                # Integrity error if the same file/data is being imported twice
                pass
        return tweets, cases


information = '#  This is an experimental function.\n\
If you have an existing CSV fully quoted file of tweet data that contains at a minimum these exact headings:\n\
id, full_text, screen_name\n\
Then QualCoder should import the tweet data\n\
Additional tweet fields must be: created_at, coordinates, retweet_count, favorite_count, lang\n\
Additional user fields must be:\n\
location, url, description, followers_count, friends_count, listed_count, favourites_count, statuses_count\n\
Each tweet will be a source file in QualCoder. Each user will be a case in QualCoder.\n\
There is an example csv file in the Examples folder called: rtweet_judo_tweets_data.csv\n\
\n\
As of 10th April 2023 these instructions may no longer work. You may need to pay for twitter authentication and rtweet may or may not work.\n\
Instructions for getting twitter data using the R Statistics Package\n\
\n\
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
tweets <- search_tweets("#judo", "lang:en", geocode = lookup_coords("usa"), n = 100)\n\
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
setwd("the path to where you want to save the file")\n\
\n\
# Write to a csv file\n\
write.csv(data_flattened, "testdata.csv", na="", fileEncoding="UTF-8")'




