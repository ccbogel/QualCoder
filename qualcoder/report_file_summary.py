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
"""

import logging
import os
from PIL import Image
from PIL.ExifTags import TAGS
import re

from PyQt6 import QtCore, QtWidgets, QtGui

from .GUI.base64_helper import *
from .GUI.ui_dialog_report_file_summary import Ui_Dialog_file_summary
from .helpers import msecs_to_hours_mins_secs

# If VLC not installed, it will not crash
vlc = None
meta_keys = []
try:
    import vlc
    meta_keys = [vlc.Meta.Actors, vlc.Meta.Album, vlc.Meta.AlbumArtist, vlc.Meta.Artist,
                 vlc.Meta.ArtworkURL, vlc.Meta.Copyright, vlc.Meta.Date, vlc.Meta.Description,
                 vlc.Meta.Director, vlc.Meta.DiscTotal, vlc.Meta.EncodedBy,
                 vlc.Meta.Episode, vlc.Meta.Genre, vlc.Meta.Language, vlc.Meta.NowPlaying, vlc.Meta.Publisher,
                 vlc.Meta.Rating, vlc.Meta.Season, vlc.Meta.Setting, vlc.Meta.ShowName, vlc.Meta.Title,
                 vlc.Meta.TrackID, vlc.Meta.TrackNumber, vlc.Meta.TrackTotal, vlc.Meta.URL]
except Exception as e:
    print(e)

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogReportFileSummary(QtWidgets.QDialog):
    """ Provide a summary report for selected file.
    """

    app = None
    parent_tetEdit = None
    files = []

    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_textEdit = parent_text_edit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_file_summary()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        docfont = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.textEdit.setStyleSheet(docfont)
        treefont = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        try:
            s0 = int(self.app.settings['dialogreport_file_summary_splitter0'])
            s1 = int(self.app.settings['dialogreport_file_summary_splitter1'])
            self.ui.splitter.setSizes([s0, s1])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.splitter_sizes)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
        self.ui.pushButton_search_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_search_next.pressed.connect(self.search_results_next)
        self.ui.listWidget.setStyleSheet(treefont)
        self.ui.listWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.get_files()
        self.ui.listWidget.itemClicked.connect(self.fill_text_edit)
        self.ui.textEdit.setTabChangesFocus(True)

    def splitter_sizes(self):
        """ Detect size changes in splitter and store in app.settings variable. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogreport_file_summary_splitter0'] = sizes[0]
        self.app.settings['dialogreport_file_summary_splitter1'] = sizes[1]

    def get_files(self):
        """ Get source files with additional details and fill list widget.
        """

        self.ui.listWidget.clear()
        self.files = self.app.get_filenames()
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), mediapath from source where id=?"
        sql_text_codings = "select count(cid) from code_text where fid=?"
        sql_av_codings = "select count(cid) from code_av where id=?"
        sql_image_codings = "select count(cid) from code_image where id=?"
        for f in self.files:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # safety catch
                res = [0]
            tt = ""
            if res[1] is None or res[1][0:5] == "docs:":
                tt += _("Text file\n")
                tt += _("Characters: ") + str(res[0])
            if res[1] is not None and (res[1][0:7] == "images:" or res[1][0:7] == "/images"):
                tt += _("Image")
            if res[1] is not None and (res[1][0:6] == "audio:" or res[1][0:6] == "/audio"):
                tt += _("Audio")
            if res[1] is not None and (res[1][0:6] == "video:" or res[1][0:6] == "/video"):
                tt += _("Video")
            cur.execute(sql_text_codings, [f['id']])
            txt_res = cur.fetchone()
            cur.execute(sql_av_codings, [f['id']])
            av_res = cur.fetchone()
            cur.execute(sql_image_codings, [f['id']])
            img_res = cur.fetchone()
            tt += _("\nCodings: ")
            if txt_res[0] > 0:
                tt += str(txt_res[0])
            if av_res[0] > 0:
                tt += str(av_res[0])
            if img_res[0] > 0:
                tt += str(img_res[0])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] != "":
                tt += _("\nMemo: ") + f['memo']
            item.setToolTip(tt)
            self.ui.listWidget.addItem(item)

    def fill_text_edit(self):
        """ Get data about file and fill text edit. """

        file_ = {}
        file_name = self.ui.listWidget.currentItem().text()
        for f in self.files:
            if f['name'] == file_name:
                file_ = f
                break
        if file_ == "":
            return
        cur = self.app.conn.cursor()
        text_ = f"{file_name}\n\n"
        if file_['memo'] != "":
            text_ += _("MEMO: ") + f"\n{file_['memo']}\n"
        text_ += self.get_attributes(file_['id'])
        text_ += self.get_case_assignment(file_['id'])
        cur.execute("select date, owner, fulltext, mediapath from source where id=?", [file_['id']])
        res = cur.fetchone()
        text_ += f"ID: {file_['id']}  " + _("Date: ") + f"{res[0]}  " + _("Owner: ") + f"{res[1]}\n"
        media_path = ""
        file_type = ""
        if res[3] is None or res[3] == "":
            media_path = _("Internal text document")
            file_type = "text"
        elif res[3][0:5] == "docs:":
            media_path = _("External text document: ") + res[3][5:]
            file_type = "text"
        elif res[3][0:6] == "audio:":
            media_path = _("External audio file: ") + res[3][6:]
            file_type = "audio"
        elif res[3][0:7] == "/audio/":
            media_path = _("Internal audio file")
            file_type = "audio"
        elif res[3][0:6] == "video:":
            media_path = _("External video file: ") + res[3][6:]
            file_type = "video"
        elif res[3][0:7] == "/video/":
            media_path = _("Internal video file")
            file_type = "video"
        elif res[3][0:7] == "images:":
            media_path = _("External image file: ") + res[3][7:]
            file_type = "image"
        elif res[3][0:8] == "/images/":
            media_path = _("Internal image file")
            file_type = "image"
        text_ += _("Media path: ") + f"{media_path}\n"
        if file_type == "text":
            text_ += self.text_statistics(file_['id'])
        if file_type == "image":
            text_ += self.image_statistics(file_['id'])
        if file_type == "audio":
            text_ += self.audio_statistics(file_['id'])
        if file_type == "video":
            text_ += self.video_statistics(file_['id'])
        self.ui.textEdit.setText(text_)

    def get_case_assignment(self, id_):
        """ Get case or cases associated with this file.
        Show text positions if a text file.
        param: id : Integer """

        text_ = "\n" + _("CASE:") + "\n"
        cur = self.app.conn.cursor()
        sql = "select cases.name, pos0, pos1 from case_text \
              join cases on cases.caseid=case_text.caseid \
              where case_text.fid=?"
        cur.execute(sql, [id_])
        result = cur.fetchall()
        for row in result:
            if row[1] == 0 and row[2] == 0:
                text_ += f"{row[0]}\n"
            else:
                text_ += f"{row[0]} [{row[1]} - {row[2]}]\n"
        if not result:
            text_ += _("No case assignment") + "\n"
        text_ += "\n"
        return text_

    def get_attributes(self, id_):
        """ Get attributes and return text representation.
        param: id : Integer """

        text_ = _("ATTRIBUTES:") + "\n"
        cur = self.app.conn.cursor()
        sql = "select attribute.name, value from attribute join attribute_type on \
            attribute_type.name=attribute.name where attribute_type.caseOrFile='file' and \
            id=? order by attribute.name"
        cur.execute(sql, [id_])
        result = cur.fetchall()
        if not result:
            return ""
        for row in result:
            text_ += f"{row[0]}: {row[1]} | "
        text_ += "\n"
        return text_

    def video_statistics(self, id_):
        """ Get video statistics for image file
        param: id : Integer """

        text_ = _("METADATA:") + "\n"
        cur = self.app.conn.cursor()
        cur.execute("select mediapath from source where id=?", [id_])
        mediapath = cur.fetchone()[0]
        abs_path = ""
        if 'video:' == mediapath[0:6]:
            abs_path = mediapath[6:]
        else:
            abs_path = self.app.project_path + mediapath
        msecs = None
        if vlc:
            try:
                instance = vlc.Instance()
            except NameError as name_err:
                logger.error(f"vlc.Instance: {name_err}")
                text_ += f"Duration cannot obtain. vlc.Instance: {name_err}\n"
                instance = None
            if instance:
                mediaplayer = instance.media_player_new()
                media = instance.media_new(abs_path)
                media.parse()
                mediaplayer.play()
                mediaplayer.pause()
                msecs = media.get_duration()
                text_ += _("Duration: ") + msecs_to_hours_mins_secs(msecs) + "\n"
                for meta_key in meta_keys:
                    meta = media.get_meta(meta_key)
                    if meta is not None:
                        text_ += f"{meta_key}:  {meta}\n"
        else:
            text_ += _("Duration: Cannot obtain. VLC not installed.")

        # Codes
        sql = "select code_name.name, code_av.cid, count(code_av.cid), round(avg(pos1 - pos0)), sum(pos1-pos0) "
        sql += " from code_av join code_name "
        sql += "on code_name.cid=code_av.cid where id=? "
        sql += "group by code_name.name, code_av.cid order by count(code_av.cid) desc"
        cur.execute(sql, [id_])
        res = cur.fetchall()
        text_ += "\n\n" + _("CODE COUNTS:") + "\n"
        for r in res:
            text_ += f"{r[0]}  " + _("Count: ") + f"{r[2]}  "
            if msecs:
                text_ += _("Percent: ") + f"{round(r[4] / msecs * 100, 2)}%  "
            text_ += _("Average segment: ") + f"{int(r[3]):,d}" + _(" msecs") + "\n"

        # Transcript
        cur.execute("select name from source where id=?", [id_])
        filename = cur.fetchone()[0]
        cur.execute("select id from source where name=?", [filename + ".transcribed"])
        res = cur.fetchone()
        if res is not None:
            text_ += "\n" + _("TRANSCRIPT:") + f"{filename}.transcribed\n"
            text_ += self.text_statistics(res[0])
            text_ += _("END OF TRANSCRIPT") + "\n"
        return text_

    def audio_statistics(self, id_):
        """ Get audio statistics for image file
        param: file_ Dictionary of {name, id, memo} """

        text_ = _("METADATA:") + "\n"
        cur = self.app.conn.cursor()
        cur.execute("select mediapath from source where id=?", [id_])
        mediapath = cur.fetchone()[0]
        abs_path = ""
        if 'audio:' == mediapath[0:6]:
            abs_path = mediapath[6:]
        else:
            abs_path = self.app.project_path + mediapath
        msecs = None
        if vlc:
            instance = vlc.Instance()
            mediaplayer = instance.media_player_new()
            media = instance.media_new(abs_path)
            media.parse()
            msecs = media.get_duration()
            text_ += _("Duration: ") + msecs_to_hours_mins_secs(msecs) + "\n"
            for meta_key in meta_keys:
                meta = media.get_meta(meta_key)
                if meta is not None:
                    text_ += f"{meta_key}:  {meta}\n"
        else:
            text_ = _("Duration: Cannot obtain. VLC not installed.")

        # Codes
        sql = "select code_name.name, code_av.cid, count(code_av.cid), round(avg(pos1 - pos0)), sum(pos1 - pos0) "
        sql += " from code_av join code_name "
        sql += "on code_name.cid=code_av.cid where id=? "
        sql += "group by code_name.name, code_av.cid order by count(code_av.cid) desc"
        cur.execute(sql, [id_])
        res = cur.fetchall()
        text_ += "\n\n" + _("CODE COUNTS:") + "\n"
        for r in res:
            text_ += f"{r[0]}  " + _("Count: ") + f"{r[2]}  "
            text_ += _("Percent: ") + f"{round(r[4] / msecs * 100, 2)}%  "
            text_ += _("Average segment: ") + f"{int(r[3]):,d}" + _(" msecs") + "\n"
        # Transcript
        cur.execute("select name from source where id=?", [id_])
        filename = cur.fetchone()[0]
        cur.execute("select id from source where name=?", [filename + ".transcribed"])
        res = cur.fetchone()
        if res is not None:
            text_ += "\n" + _("TRANSCRIPT: ") + f"{filename}.transcribed\n"
            text_ += self.text_statistics(res[0])
            text_ += _("END OF TRANSCRIPT") + "\n"
        return text_

    def image_statistics(self, id_):
        """ Get image statistics for image file
        param: id: Integer """

        text_ = _("METADATA:") + "\n"
        cur = self.app.conn.cursor()
        cur.execute("select mediapath from source where id=?", [id_])
        mediapath = cur.fetchone()[0]
        abs_path = ""
        if 'images:' == mediapath[0:7]:
            abs_path = mediapath[7:]
        else:
            abs_path = self.app.project_path + mediapath
        # Image size and metadata
        image = Image.open(abs_path)
        w, h = image.size
        text_ += _("Width: ") + f"{w:,d}" + "  " + _("Height: ") + f"{h:,d}  " + _("Area: ") + f"{w * h:,d}" + \
                _(" pixels") + "\n"
        image_type = abs_path[-3:].lower()
        # From: www.thepythoncode.com/article/extracting-image-metadata-in-python
        if image_type in ("jpg", "peg"):
            exifdata = image.getexif()
            # iterating over the EXIF data fields
            for tag_id in exifdata:
                # get the tag name, instead of human unreadable tag id
                tag = TAGS.get(tag_id, tag_id)
                data = exifdata.get(tag_id)
                # Decode bytes
                if isinstance(data, bytes):
                    try:
                        data = data.decode()
                        text_ += f"{tag:25}: {data}\n"
                    except UnicodeDecodeError as e_:
                        logger.debug(e_)
        # From: www.vice.com/en/article/aekn58/hack-this-extra-image-metadata-using-python
        if image_type == "png":
            for tag, value in image.info.items():
                key = TAGS.get(tag, tag)
                text_ += f"{key} {value}\n"
        # Codes
        sql = "select code_name.name, code_image.cid, count(code_image.cid), round(avg(width)), round(avg(height)), "
        sql += "sum(width*height) "
        sql += " from code_image join code_name "
        sql += "on code_name.cid=code_image.cid where id=? "
        sql += "group by code_name.name, code_image.cid order by count(code_image.cid) desc"
        cur.execute(sql, [id_])
        res = cur.fetchall()
        text_ += "\n\n" + _("CODE COUNTS:") + "\n"
        # Calculate statistics
        for r in res:
            area = int(r[3] * r[4])
            text_ += r[0] + "  " + _("Count: ") + f"{r[2]}  "
            text_ += _("Percent: ") + f"{round(r[5] / (w * h) * 100, 2)}%  "
            text_ += _("Average area: ") + f"{area:,d}" + _(" pixels") + "\n"
        return text_

    def text_statistics(self, id_):
        """ Get details of text file statistics
        param: id Integer
        """

        text_ = _("STATISTICS:") + "\n"
        cur = self.app.conn.cursor()
        cur.execute("select fulltext from source where id=?", [id_])
        fulltext = cur.fetchone()[0]
        if fulltext is None:
            fulltext = ""
        text_ += _("Characters: ") + f"{len(fulltext):,d}\n"
        # Remove punctuation. Convert to lower case
        chars = ""
        for c in range(0, len(fulltext)):
            if fulltext[c].isalpha() or fulltext[c] == "'":
                chars += fulltext[c]
            else:
                chars += " "
        chars = chars.lower()
        word_list = chars.split()
        msg = _("Word calculations: Words use alphabet characters and include the apostrophe. All other characters are word separators")
        text_ += f"\n{msg}\n"
        text_ += "\n" + _("Words: ") + f"{len(word_list):,d}\n"
        # Word frequency
        d = {}
        for word in word_list:
            d[word] = d.get(word, 0) + 1  # get(key, value if not present)
        # https://codeburst.io/python-basics-11-word-count-filter-out-punctuation-dictionary-manipulation-and-sorting-lists-3f6c55420855
        word_freq = []
        for key, value in d.items():
            word_freq.append((value, key))
        word_freq.sort(reverse=True)
        text_ += _("Unique words: ") + f"{len(word_freq)}\n"
        # Top 100 or maximum of less than 100
        max_count = len(word_freq)
        if max_count > 100:
            max_count = 100
        text_ += _("Top 100 words") + "\n"
        for i in range(0, max_count):
            text_ += f"{word_freq[i][1]}   {word_freq[i][0]} | "
        # Codes
        sql = "select code_name.name, code_text.cid, count(code_text.cid), sum(length(code_text.seltext)), "
        sql += "round(avg(length(code_text.seltext))) from code_text join code_name "
        sql += "on code_name.cid=code_text.cid where fid=? "
        sql += "group by code_name.name, code_text.cid order by count(code_text.cid) desc"
        cur.execute(sql, [id_])
        res = cur.fetchall()
        text_ += "\n\n" + _("CODE COUNTS:") + "\n"
        # Calculate code statistics
        for r in res:
            text_ += r[0] + "  " + _("Count: ") + str(r[2]) + "  " + _("Total characters: ") + f"{r[3]:,d}"
            text_ += "  " + _("Percent: ") + f"{round((r[3] / len(fulltext)) * 100, 2)}%"
            text_ += "  " + _("Average characters: ") + f"{int(r[4])}\n"
        return text_

    def search_results_next(self):
        """ Search textedit for text """

        search_text = self.ui.lineEdit_search_results.text()
        if search_text == "":
            return
        if self.ui.textEdit.toPlainText() == "":
            return
        if self.ui.textEdit.textCursor().position() >= len(self.ui.textEdit.toPlainText()):
            cursor = self.ui.textEdit.textCursor()
            cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
            self.ui.textEdit.setTextCursor(cursor)
        te_text = self.ui.textEdit.toPlainText()
        pattern = None
        flags = 0
        try:
            pattern = re.compile(search_text, flags)
        except re.error as e_:
            logger.warning('re error Bad escape ' + str(e_))
        if pattern is None:
            return
        for match in pattern.finditer(te_text):
            if match.start() > self.ui.textEdit.textCursor().position():
                cursor = self.ui.textEdit.textCursor()
                cursor.setPosition(match.start(), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(match.start() + len(search_text), QtGui.QTextCursor.MoveMode.KeepAnchor)
                self.ui.textEdit.setTextCursor(cursor)
                break
