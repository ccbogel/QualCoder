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
"""

from copy import copy
import logging
import os
import qtawesome as qta

from PyQt6 import QtGui, QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush

from .color_selector import TextColor
from .GUI.ui_dialog_code_context_image import Ui_Dialog_code_context_image
from .GUI.ui_dialog_report_compare_coder_file import Ui_Dialog_reportCompareCoderFile
from .helpers import Message, msecs_to_hours_mins_secs, ExportDirectoryPathDialog
from .information import DialogInformation

# If VLC not installed, it will not crash
vlc = None
try:
    import vlc
except Exception as e:
    print(e)

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCompareCoderByFile(QtWidgets.QDialog):
    """ Compare two coders for:
    Coded text sequences for one code and one text file. Apply Cohen's Kappa for text files.
    Coded image areas for one code and one text file.

    Used to help advise coders / second coder on how to improve accuracy of coding.
    """

    app = None
    parent_textedit = None
    coders = []
    selected_coders = []
    categories = []
    code_ = None  # Selected code
    file_ = None  # Selected file
    pixmap = None
    files = []
    codes = []
    comparisons = ""

    def __init__(self, app, parent_text_edit):

        self.app = app
        self.parent_textedit = parent_text_edit
        self.comparisons = ""
        self.selected_coders = []
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_reportCompareCoderFile()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.get_data()
        self.ui.pushButton_run.setEnabled(False)
        self.ui.pushButton_run.pressed.connect(self.results)
        self.ui.pushButton_run.setIcon(qta.icon('mdi6.play'))
        self.ui.pushButton_clear.pressed.connect(self.clear_selection)
        self.ui.pushButton_clear.setIcon(qta.icon('mdi6.refresh'))
        self.ui.pushButton_export_odt.setIcon(qta.icon('mdi6.export'))
        self.ui.pushButton_export_odt.pressed.connect(self.export_odt_file)
        self.ui.pushButton_help1.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help1.pressed.connect(self.information)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(font)
        self.ui.listWidget_files.setStyleSheet(font)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.SingleSelection)
        self.ui.comboBox_coders.insertItems(0, self.coders)
        self.ui.comboBox_coders.currentTextChanged.connect(self.coder_selected)
        if len(self.coders) == 3:  # Includes empty slot
            self.ui.comboBox_coders.setCurrentIndex(1)
            self.ui.comboBox_coders.setCurrentIndex(2)
        self.fill_tree()
        self.ui.treeWidget.itemSelectionChanged.connect(self.code_selected)
        self.ui.listWidget_files.itemClicked.connect(self.file_selected)
        self.ui.textEdit.setReadOnly(True)

    def information(self):
        """ Provide statistical help information. """

        ui = DialogInformation(self.app, "Statistics information", "")
        ui.setHtml(info)
        ui.exec()

    def get_data(self):
        """ Called from init. gets coders, code_names, categories, files.
        Images are not loaded. """

        self.codes, self.categories = self.app.get_codes_categories()
        cur = self.app.conn.cursor()
        sql = "select owner from  code_image union select owner from code_text union select owner from code_av"
        cur.execute(sql)
        result = cur.fetchall()
        self.coders = [""]
        for row in result:
            self.coders.append(row[0])
        self.get_files()

    def get_files(self):
        """ Get source files with additional details and fill list widget.
        Add file type to dictionary for each file.
        """

        self.ui.listWidget_files.clear()
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
            f['mediapath'] = res[1]
            if res[1] is None or res[1][0:5] == "docs:" or res[1][0:5] == "/docs":
                tt += _("Text file\n")
                tt += _("Characters: ") + str(res[0])
                f['type'] = 'text'
            if res[1] is not None and (res[1][0:7] == "images:" or res[1][0:7] == "/images"):
                tt += _("Image")
                f['type'] = 'image'
            if res[1] is not None and (res[1][0:6] == "audio:" or res[1][0:6] == "/audio"):
                tt += _("Audio")
                f['type'] = 'audio'
            if res[1] is not None and (res[1][0:6] == "video:" or res[1][0:6] == "/video"):
                tt += _("Video")
                f['type'] = 'video'
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
            self.ui.listWidget_files.addItem(item)

    def coder_selected(self):
        """ Select coders for comparison - only two coders can be selected. """

        coder = self.ui.comboBox_coders.currentText()
        if coder == "":
            return
        if len(self.selected_coders) == 0:
            self.selected_coders.append(coder)
            self.ui.label_selections.setText(coder)
        if len(self.selected_coders) == 1 and self.selected_coders[0] != coder:
            self.selected_coders.append(coder)
            coder1 = self.ui.label_selections.text()
            self.ui.label_selections.setText(f"{coder1} , {coder}")
        if len(self.selected_coders) == 2 and self.file_ is not None and self.code_ is not None:
            self.ui.pushButton_run.setEnabled(True)

    def file_selected(self):
        """ May activate run button if file, code and coders selected """

        item_name = self.ui.listWidget_files.currentItem().text()
        for f in self.files:
            if f['name'] == item_name:
                self.file_ = f
        if len(self.selected_coders) == 2 and self.file_ is not None and self.code_ is not None:
            self.ui.pushButton_run.setEnabled(True)

    def code_selected(self):
        """ May activate run button if file, code and coders selected """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] != 'cid':
            return
        self.code_ = None
        for c in self.codes:
            if c['name'] == current.text(0):
                self.code_ = c
        if self.code_ is None:
            return
        if len(self.selected_coders) == 2 and self.file_ is not None and self.code_ is not None:
            self.ui.pushButton_run.setEnabled(True)

    def clear_selection(self):
        """ Clear the coder selection and tree widget statistics. """

        self.selected_coders = []
        self.ui.pushButton_run.setEnabled(False)
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:  # while there is an item in the list
            if item.text(1)[0:4] == 'cid:':
                item.setText(2, "")
                item.setText(3, "")
                item.setText(4, "")
                item.setText(5, "")
                item.setText(6, "")
            it += 1
            item = it.value()
        self.ui.label_selections.setText(_("No coders selected"))

    def export_odt_file(self):
        """ Export coding comparison statistics and text to ODT file. """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        filename = "Coder_comparison_by_file.odt"
        e_ = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(self.ui.textEdit.document())
        msg_ = _("Report exported: ") + filepath
        self.parent_textedit.append(msg_)
        Message(self.app, _('Report exported'), msg_, "information").exec()

    def results(self):
        """ Iterate through tree widget, for all cids
        For each code_name calculate the two-coder comparison statistics.

        {'id': 7, 'name': 'Brighton_Storm.mp4.transcribed', 'memo': 'A transcription of the Optus video'}
        {'name': 'enthusiastic', 'memo': 'very entuistic suggeses', 'owner': 'colin', 'date': '2019-08-05 08:20:48',
        'cid': 12, 'catid': -1, 'color': '#F781F3'}
        ['colin', 'jemima']
        """

        txt = _("CODER COMPARISON FOR FILE") + "\n====\n" + _("CODERS: ")
        c1_pos0 = len(txt)
        txt += f"{self.selected_coders[0]} " + _("(YELLOW CODER 0)")
        c1_pos1 = len(txt)
        txt += f", {self.selected_coders[1]} " + _("(BLUE CODER 1)") + "\n"
        c2_pos1 = len(txt)
        txt += _("FILE: ") + self.file_['name'] + "\n"
        txt += _("CODE: ") + self.code_['name'] + "\n"
        self.ui.textEdit.setText(txt)
        # Format the first coder color, yellow
        cursor = self.ui.textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        cursor.setPosition(c1_pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(c1_pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        color = "#F4FA58"
        brush = QBrush(QtGui.QColor(color))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)
        # Format the second coder color, blue
        cursor.setPosition(c1_pos1, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(c2_pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        color = "#81BEF7"
        brush = QBrush(QtGui.QColor(color))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)
        if self.file_['type'] == 'text':
            self.ui.textEdit.append(self.agreement_text_file())
        if self.file_['type'] == 'image':
            self.ui.textEdit.append(self.agreement_image_file())
        if self.file_['type'] in ('audio', 'video'):
            self.ui.textEdit.append(self.agreement_av_file())

    def agreement_av_file(self):
        """ Calculate the two-coder statistics for this code (cid) and in this A/V file.
        Percentage agreement, disgreement and kappa.
        'Disagree%':'','A not B':'','B not A':'','K':''
        """

        source = self.app.project_path + self.file_['mediapath']
        if self.file_['mediapath'][0:6] in ("audio:", "video:"):
            source = self.file_['mediapath'][7:]
        duration_txt = ""
        msecs = 1  # Default
        if vlc:
            try:
                instance = vlc.Instance()
            except NameError as name_err:
                logger.error(f"vlc.Instance: {name_err}")
                duration_txt += f"Duration unknown. Set at 1 msec. vlc.Instance: {name_err}"
                instance = None
            if instance:
                try:
                    media = instance.media_new(source)
                    media.parse()
                    msecs = media.get_duration()
                    duration_txt = _("A/V Duration: ") + msecs_to_hours_mins_secs(msecs) + " , " + _("msecs: ") + str(msecs)
                except Exception as err:
                    msg_ = _("Cannot open: ") + source + "\n" + str(err)
                    logger.debug(msg_)
                    Message(self.app, _("A/V Error"), msg_, "warning").exec()
                    logger.warning(msg_)
                    return
        else:
            msecs = 1
            duration_txt += _("A/V Duration: Unknown, Set at 1 millisecond") + "\n"
            duration_txt += _("Statistical comparisons will be incorrect. VLC not installed.")

        self.ui.textEdit.append(duration_txt)
        # coded0 and coded1 are the total segment lengths coded by coder 0 and coder 1
        total = {'dual_coded': 0, 'single_coded': 0, 'uncoded': 0, 'duration': msecs, 'coded0': 0, 'coded1': 0}
        # Get res0 and res1 a/v segments
        cur = self.app.conn.cursor()
        sql = "select pos0, pos1, pos1 - pos0, ifnull(memo,''), owner from code_av where id=? and cid=? and owner=?"
        keys = 'pos0', 'pos1', 'seg_len', 'memo', 'owner'
        res0 = []
        res1 = []
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[0]])
        results0 = cur.fetchall()
        for row in results0:
            tmp0 = dict(zip(keys, row))
            tmp0['overlaps'] = []
            res0.append(tmp0)
            total['coded0'] += row[2]
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[1]])
        results1 = cur.fetchall()
        for row in results1:
            tmp1 = dict(zip(keys, row))
            tmp1['overlaps'] = []
            res1.append(tmp1)
            total['coded1'] += row[2]

        # Calculate overlaps and total intersections
        for r0 in res0:
            for r1 in res1:
                total['dual_coded'] += self.segment_overlap(r0, r1)
                overlap = self.segment_overlap(r0, r1)
                if overlap > 0:
                    r1['overlaps'].append(overlap)
                    r0['overlaps'].append(overlap)
        # Summary results
        total['single_coded'] = total['coded1'] + total['coded0'] - total['dual_coded']
        total['uncoded'] = msecs - total['single_coded'] - total['dual_coded']
        total['agreement'] = round(100 * (total['dual_coded'] + total['uncoded']) / msecs, 2)
        total['dual_percent'] = round(100 * total['dual_coded'] / msecs, 2)
        total['uncoded_percent'] = round(100 * total['uncoded'] / msecs, 2)
        total['disagreement'] = round(100 - total['agreement'], 2)
        total['kappa'] = "zerodiv"
        # Calculate kappa
        unique_codings = 0
        try:
            unique_codings = total['coded0'] + total['coded1'] - total['dual_coded']
            Po = total['dual_coded'] / unique_codings
            Pyes = total['coded0'] / unique_codings * total['coded1'] / unique_codings
            Pno = (unique_codings - total['coded0']) / unique_codings * (
                        unique_codings - total['coded1']) / unique_codings
            Pe = Pyes * Pno
            kappa = round((Po - Pe) / (1 - Pe), 4)
            total['kappa'] = kappa
        except ZeroDivisionError:
            msg_ = _("ZeroDivisionError. unique_codings:") + str(unique_codings)
            logger.debug(msg_)
        overall = "\nOVERALL SUMMARY\n"
        overall += _("Total msecs: ") + str(msecs) + ", "
        overall += _("Dual coded: ") + str(total['dual_coded']) + ", "
        overall += _("Single coded: ") + str(total['single_coded']) + ", "
        overall += _("Uncoded: ") + str(total['uncoded']) + ", "
        overall += _("Coder 0: ") + str(total['coded0']) + ", "
        overall += _("Coder 1: ") + str(total['coded1']) + "\n"
        overall += _("Agreement between coders: ") + str(total['agreement']) + "%\n"
        overall += _("Total msecs dual coded: ") + str(total['dual_percent']) + "%, "
        overall += _("Total msecs uncoded: ") + str(total['uncoded_percent']) + "%, "
        overall += _("Total msecs disagreement (single coded): ") + str(total['disagreement']) + "%\n"
        overall += _("Kappa: ") + str(total['kappa']) + "\n"
        self.ui.textEdit.append(overall)
        self.ui.textEdit.append(_("Overlaps Coder: ") + self.selected_coders[0])
        for r in res0:
            txt = "\n" + "pos0: " + str(r['pos0']) + " pos1: " + str(r['pos1'])
            if len(r['overlaps']) == 0:
                txt += " " + _("No overlap")
            else:
                txt += "\n" + _("Count of overlaps: ") + str(len(r['overlaps'])) + "\n"
                txt += str(r['overlaps']) + " " + _("Total: ") + str(sum(r['overlaps'])) + " " + _("msecs") + "\n"
            self.ui.textEdit.append(txt)

        self.ui.textEdit.append(_("Overlaps Coder: ") + self.selected_coders[1])
        for r in res1:
            txt = "\n" + "pos0: " + str(r['pos0']) + " pos1: " + str(r['pos1'])
            if len(r['overlaps']) == 0:
                txt += " " + _("No overlap")
            else:
                txt += "\n" + _("Count of overlaps: ") + str(len(r['overlaps'])) + "\n"
                txt += str(r['overlaps']) + " " + _("Total: ") + str(sum(r['overlaps'])) + " " + _("msecs")
            self.ui.textEdit.append(txt)

    @staticmethod
    def segment_overlap(r0, r1):
        """ Calculate overlap of two A/V segments. """

        result = max(0, min(r0['pos1'], r1['pos1']) - max(r0['pos0'], r1['pos0']))
        return result

    @staticmethod
    def intersect(r0, r1):
        """ Calculation intersection area of two rectangles in image coding. """

        x1 = max(r0['x1'], r1['x1'])
        y1 = max(r0['y1'], r1['y1'])
        x2 = min(r0['x1'] + r0['width'], r1['x1'] + r1['width'])
        y2 = min(r0['y1'] + r0['height'], r1['y1'] + r1['height'])
        return max(0, x2 - x1 + 1) * max(0, y2 - y1 + 1)

    def agreement_image_file(self):
        """ Calculate the two-coder statistics for this code (cid) and in this image file.
        Percentage agreement, disgreement and kappa.
        'Disagree%':'','A not B':'','B not A':'','K':''
        """

        source = self.app.project_path + self.file_['mediapath']
        if self.file_['mediapath'][0:7] == "images:":
            source = self.file_['mediapath'][7:]
        image = QtGui.QImage(source)
        if image.isNull():
            Message(self.app, _("Image Error"), _("Cannot open: ", "warning") + source).exec()
            logger.warning("Cannot open image: " + source)
            return
        self.pixmap = QtGui.QPixmap.fromImage(image)
        width, height = self.pixmap.width(), self.pixmap.height()

        # coded0 and coded1 are the total pixels coded by coder 0 and coder 1
        total = {'dual_coded': 0, 'single_coded': 0, 'uncoded': 0, 'pixels': 0, 'coded0': 0, 'coded1': 0}
        cur = self.app.conn.cursor()
        sql = "select cast(x1 as int), cast(y1 as int), cast(width as int), cast(height as int), " \
              "cast(width as int) * cast(height as int), ifnull(memo,''), owner from code_image where id=? and cid=? " \
              "and owner=?"
        keys = 'x1', 'y1', 'width', 'height', 'area', 'memo', 'owner'
        res0 = []
        res1 = []
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[0]])
        results0 = cur.fetchall()
        total_area_res0 = 0
        for row in results0:
            tmp0 = dict(zip(keys, row))
            tmp0['intersections'] = []
            res0.append(tmp0)
            total_area_res0 += row[4]
            total['coded0'] += row[4]
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[1]])
        results1 = cur.fetchall()
        total_area_res1 = 0
        for row in results1:
            tmp1 = dict(zip(keys, row))
            tmp1['intersections'] = []
            res1.append(tmp1)
            total_area_res1 += row[4]
            total['coded1'] += row[4]
        # Calculate intersection pixels and total intersections
        for r0 in res0:
            for r1 in res1:
                total['dual_coded'] += self.intersect(r0, r1)
                intersecting_pixels = self.intersect(r0, r1)
                if intersecting_pixels > 0:
                    r1['intersections'].append(intersecting_pixels)
                    r0['intersections'].append(intersecting_pixels)
        # Summary results
        total['single_coded'] = total_area_res1 + total_area_res0 - total['dual_coded']
        total['uncoded'] = height * width - total['single_coded'] - total['dual_coded']
        total['pixels'] += width * height
        total['agreement'] = round(100 * (total['dual_coded'] + total['uncoded']) / total['pixels'], 2)
        total['dual_percent'] = round(100 * total['dual_coded'] / total['pixels'], 2)
        total['uncoded_percent'] = round(100 * total['uncoded'] / total['pixels'], 2)
        total['disagreement'] = round(100 - total['agreement'], 2)
        # Cohen's Kappa
        '''
        https://en.wikipedia.org/wiki/Cohen%27s_kappa

        k = Po - Pe     Po is proportionate agreement (both coders coded this text / all coded text))
            -------     Pe is probability of random agreement
            1  - Pe

            Pe = Pyes + Pno
            Pyes = proportion Yes by A multiplied by proportion Yes by B
                 = total['coded0']/total_coded * total['coded1]/total_coded

            Pno = proportion No by A multiplied by proportion No by B
                = (total_coded - total['coded0']) / total_coded * (total_coded - total['coded1]) / total_coded

        IMMEDIATE BELOW IS INCORRECT - RESULTS IN THE TOTAL AGREEMENT SCORE
        Po = total['agreement'] / 100
        Pyes = total['coded0'] / total['pixels'] * total['coded1'] / total['pixels']
        Pno = (total['pixels'] - total['coded0']) / total['pixels'] * (total['pixels'] - total['coded1']) / total['pixels']

        BELOW IS BETTER - ONLY LOOKS AT PROPORTIONS OF CODED CHARACTERS
        NEED TO CONFIRM THIS IS THE CORRECT APPROACH
        '''
        total['kappa'] = "zerodiv"
        unique_codings = 0
        try:
            unique_codings = total['coded0'] + total['coded1'] - total['dual_coded']
            Po = total['dual_coded'] / unique_codings
            Pyes = total['coded0'] / unique_codings * total['coded1'] / unique_codings
            Pno = (unique_codings - total['coded0']) / unique_codings * (
                        unique_codings - total['coded1']) / unique_codings
            Pe = Pyes * Pno
            kappa = round((Po - Pe) / (1 - Pe), 4)
            total['kappa'] = kappa
        except ZeroDivisionError:
            msg_ = _("ZeroDivisionError. unique_codings:") + str(unique_codings)
            logger.debug(msg_)

        overall = "\nOVERALL SUMMARY\n"
        overall += _("Total pixels: ") + str(total['pixels']) + ", "
        overall += _("Dual coded: ") + str(total['dual_coded']) + ", "
        overall += _("Single coded: ") + str(total['single_coded']) + ", "
        overall += _("Uncoded: ") + str(total['uncoded']) + ", "
        overall += _("Coder 0: ") + str(total['coded0']) + ", "
        overall += _("Coder 1: ") + str(total['coded1']) + "\n"
        overall += _("Agreement between coders: ") + str(total['agreement']) + "%\n"
        overall += _("Total pixels dual coded: ") + str(total['dual_percent']) + "%, "
        overall += _("Total pixels uncoded: ") + str(total['uncoded_percent']) + "%, "
        overall += _("Total pixels disagreement (single coded): ") + str(total['disagreement']) + "%\n"
        overall += _("Kappa: ") + str(total['kappa']) + "\n"
        self.ui.textEdit.append(overall)
        self.ui.textEdit.append(_("Intersections Coder: ") + self.selected_coders[0])
        for r in res0:
            txt = "\n" + "x: " + str(r['x1']) + " y: " + str(r['y1']) + " w: " + str(r['width']) + " h: " + str(r['height'])
            if len(r['intersections']) == 0:
                txt += " " + _("No intersections")
            else:
                txt += "\n" + _("Count of intersections: ") + str(len(r['intersections'])) + "\n"
                txt += str(r['intersections']) + " " + _("Total: ") + str(sum(r['intersections'])) + " " + _("pixels")
            self.ui.textEdit.append(txt)

        self.ui.textEdit.append("\n" + _("Intersections Coder: ") + self.selected_coders[1])
        for r in res1:
            txt = "\n" + "x: " + str(r['x1']) + " y: " + str(r['y1']) + " w: " + str(r['width']) + " h: " + str(r['height'])
            if len(r['intersections']) == 0:
                txt += " " + _("No intersections")
            else:
                txt += "\n" + _("Count of intersections: ") + str(len(r['intersections'])) + "\n"
                txt += str(r['intersections']) + " " + _("Total: ") + str(sum(r['intersections'])) + " " + _("pixels")
            self.ui.textEdit.append(txt)
        DialogDualCodedImage(self.app, self.file_, res0, res1).exec()

    def agreement_text_file(self):
        """ Calculate the two-coder statistics for this code_
        Percentage agreement, disgreement and kappa.
        Get the start and end position the text file for this cid
        Each character that is coded by coder 1 or coder 2 is incremented, resulting in a list of 0, 1, 2
        where 0 is no codings at all, 1 is coded by only one coder and 2 is coded by both coders.
        'Disagree%':'','A not B':'','B not A':'','K':''
        """

        # coded0 and coded1 are the total characters coded by coder 0 and coder 1
        total = {'dual_coded': 0, 'single_coded': 0, 'uncoded': 0, 'characters': 0, 'coded0': 0, 'coded1': 0}
        cur = self.app.conn.cursor()
        sql = "select fulltext from source where id=?"
        cur.execute(sql, [self.file_['id']])
        fulltext = cur.fetchone()
        if fulltext[0] is None or fulltext[0] == "":
            return None
        sql = "select pos0,pos1,fid from code_text where fid=? and cid=? and owner=?"
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[0]])
        res0 = cur.fetchall()
        cur.execute(sql, [self.file_['id'], self.code_['cid'], self.selected_coders[1]])
        res1 = cur.fetchall()
        # Determine the same characters coded by both coders, by adding 1 to each coded character
        char_list = [0] * len(fulltext[0])
        # List of which coders coded this char: 1 = coder 1, 2= coder2, 12 = coders 1 and 2
        char_list_coders = [''] * len(fulltext[0])
        for coded in res0:
            for char in range(coded[0], coded[1]):
                char_list[char] += 1
                total['coded0'] += 1
                char_list_coders[char] = 'y'
        for coded in res1:
            for char in range(coded[0], coded[1]):
                char_list[char] += 1
                total['coded1'] += 1
                if char_list_coders[char] == 'y':
                    char_list_coders[char] = 'g'
                else:
                    char_list_coders[char] = 'b'
        uncoded = 0
        single_coded = 0
        dual_coded = 0
        for char in char_list:
            if char == 0:
                uncoded += 1
            if char == 1:
                single_coded += 1
            if char == 2:
                dual_coded += 1
        total['dual_coded'] += dual_coded
        total['single_coded'] += single_coded
        total['uncoded'] += uncoded
        total['characters'] += len(fulltext[0])

        total['agreement'] = round(100 * (total['dual_coded'] + total['uncoded']) / total['characters'], 2)
        total['dual_percent'] = round(100 * total['dual_coded'] / total['characters'], 2)
        total['uncoded_percent'] = round(100 * total['uncoded'] / total['characters'], 2)
        total['disagreement'] = round(100 - total['agreement'], 2)
        # Cohen's Kappa
        '''
        https://en.wikipedia.org/wiki/Cohen%27s_kappa

        k = Po - Pe     Po is proportionate agreement (both coders coded this text / all coded text))
            -------     Pe is probability of random agreement
            1  - Pe

            Pe = Pyes + Pno
            Pyes = proportion Yes by A multiplied by proportion Yes by B
                 = total['coded0']/total_coded * total['coded1]/total_coded

            Pno = proportion No by A multiplied by proportion No by B
                = (total_coded - total['coded0']) / total_coded * (total_coded - total['coded1]) / total_coded

        IMMEDIATE BELOW IS INCORRECT - RESULTS IN THE TOTAL AGREEMENT SCORE
        Po = total['agreement'] / 100
        Pyes = total['coded0'] / total['characters'] * total['coded1'] / total['characters']
        Pno = (total['characters'] - total['coded0']) / total['characters'] * (total['characters'] - total['coded1']) / total['characters']

        BELOW IS BETTER - ONLY LOOKS AT PROPORTIONS OF CODED CHARACTERS
        NEED TO CONFIRM THIS IS THE CORRECT APPROACH
        '''
        total['kappa'] = "zerodiv"
        unique_codings = 0
        try:
            unique_codings = total['coded0'] + total['coded1'] - total['dual_coded']
            Po = total['dual_coded'] / unique_codings
            Pyes = total['coded0'] / unique_codings * total['coded1'] / unique_codings
            Pno = (unique_codings - total['coded0']) / unique_codings * (unique_codings - total['coded1']) / unique_codings
            Pe = Pyes * Pno
            kappa = round((Po - Pe) / (1 - Pe), 4)
            total['kappa'] = kappa
        except ZeroDivisionError:
            msg_ = _("ZeroDivisionError. unique_codings:") + str(unique_codings)
            logger.debug(msg_)
        overall = "\nOVERALL SUMMARY\n"
        overall += _("Total characters: ") + str(total['characters']) + ", "
        overall += _("Dual coded: ") + str(total['dual_coded']) + ", "
        overall += _("Single coded: ") + str(total['single_coded']) + ", "
        overall += _("Uncoded: ") + str(total['uncoded']) + ", "
        overall += _("Coder 0: ") + str(total['coded0']) + ", "
        overall += _("Coder 1: ") + str(total['coded1']) + "\n"
        overall += _("Agreement between coders: ") + str(total['agreement']) + "%\n"
        overall += _("Total text dual coded: ") + str(total['dual_percent']) + "%, "
        overall += _("Total text uncoded: ") + str(total['uncoded_percent']) + "%, "
        overall += _("Total text disagreement (single coded): ") + str(total['disagreement']) + "%\n"
        overall += _("Kappa: ") + str(total['kappa']) + "\n\n"
        overall += "FULLTEXT"
        self.ui.textEdit.append(overall)
        cursor = self.ui.textEdit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        pos = cursor.position()
        self.ui.textEdit.append(fulltext[0])
        # Apply brush, yellow for coder 1, blue for coder 2 and green for dual coded
        cursor = self.ui.textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        # Foreground depends on the defined need_white_text color in color_selector
        for i, c in enumerate(char_list_coders):
            if c == 'b':
                cursor.setPosition(pos + i, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos + i + 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                color = "#81BEF7"
                brush = QBrush(QtGui.QColor(color))
                fmt.setBackground(brush)
                text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                cursor.setCharFormat(fmt)
            if c == 'g':
                cursor.setPosition(pos + i, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos + i + 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                color = "#81F781"
                brush = QBrush(QtGui.QColor(color))
                fmt.setBackground(brush)
                text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                cursor.setCharFormat(fmt)
            if c == 'y':
                cursor.setPosition(pos + i, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos + i + 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                color = "#F4FA58"
                brush = QBrush(QtGui.QColor(color))
                fmt.setBackground(brush)
                text_brush = QBrush(QtGui.QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                cursor.setCharFormat(fmt)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = copy(self.categories)
        codes = copy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(2)
        self.ui.treeWidget.setHeaderLabels([_("Code Tree"), "Id"])
        self.ui.treeWidget.hideColumn(1)
        if self.app.settings['showids']:
            self.ui.treeWidget.showColumn(1)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid'])])
                top_item.setToolTip(0, c['name'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)
        ''' Add child categories. Look at each unmatched category, iterate through tree to
        add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid'])])
                        child.setToolTip(0, c['name'])
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid'])])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                top_item.setToolTip(0, c['name'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                if item.text(1) == 'catid:' + str(c['catid']):
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid'])])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    child.setToolTip(0, c['name'])
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        self.ui.treeWidget.expandAll()


class DialogDualCodedImage(QtWidgets.QDialog):
    """ View two coders coded sections for one code in original image.

    Called by: report_compare_coder_file.DialogCompareCoderByFile.
    """

    app = None
    img = None
    coded0 = None
    coded1 = None
    pixmap = None
    label = None
    scale = None
    scene = None

    def __init__(self, app, img, coded0, coded1, parent=None):
        """ Displays dialog with two coders image codings for selected code.

        param:
            app : class containing app details such as database connection
            img contains {id, name, memo, mediapath, type:image}
            coded0 and coded1 contain: {x1, y1, width, height, area}
            mediapath may be a link as: 'images:path'
        """

        self.app = app
        self.img = img
        self.coded0 = coded0
        self.coded1 = coded1
        self.scale = 1
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_context_image()
        self.ui.setupUi(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        abs_path = ""
        if "images:" in self.img['mediapath']:
            abs_path = self.img['mediapath'].split(':')[1]
        else:
            abs_path = self.app.project_path + self.img['mediapath']
        self.setWindowTitle(abs_path)
        image = QtGui.QImage(abs_path)
        if image.isNull():
            Message(self.app, _('Image error'), _("Cannot open: ") + abs_path, "warning").exec()
            self.close()
            return
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)
        self.ui.scrollArea.setWidget(self.label)
        self.ui.scrollArea.resize(self.pixmap.width(), self.pixmap.height())
        self.ui.horizontalSlider.valueChanged[int].connect(self.change_scale)

        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        # slider and textedit heights
        if self.pixmap.height() > self.height() - 30 - 80:
            self.scale = (self.height() - 30 - 80) / self.pixmap.height()
            slider_value = int(self.scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)
        self.draw_coded_areas()

    def draw_coded_areas(self):
        """ Draw coded areas for both coders """

        for c in self.coded0:
            self.draw_coded_area(c, "#F4FA58")
        for c in self.coded1:
            self.draw_coded_area(c, "#81BEf7")

    def draw_coded_area(self, coded, color):
        """ Draw the coded rectangle in the scene.
         Provide detailed tooltip. """

        tooltip = coded['owner']
        tooltip += "\n x: " + str(coded['x1']) + " y: " + str(coded['y1'])
        tooltip += " w: " + str(coded['width']) + " h: " + str(coded['height']) + " "
        tooltip += _("Area: ") + str(coded['area']) + _(" pixels")
        if len(coded['intersections']) > 0:
            tooltip += "\n " + _("Intersections: ") + str(len(coded['intersections'])) + " "
            tooltip += _("Intersecting: ") + str(sum(coded['intersections'])) + _(" pixels")
            tooltip += " \n" + _("Proportion: ") + str(int(sum(coded['intersections']) / coded['area'] * 100)) + "%"
        if coded['memo'] != "":
            tooltip += "\nMemo: " + coded['memo']
        x = coded['x1'] * self.scale
        y = coded['y1'] * self.scale
        width = coded['width'] * self.scale
        height = coded['height'] * self.scale
        rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
        rect_item.setPen(QtGui.QPen(QtGui.QColor(color), 2, QtCore.Qt.PenStyle.DashLine))
        rect_item.setToolTip(tooltip)
        self.scene.addItem(rect_item)

    def change_scale(self):
        """ Resize image. Triggered by user change in slider.
        Also called by unmark, as all items need to be redrawn. """

        if self.pixmap is None:
            return
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = int(self.scale * self.pixmap.height())
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_areas()
        self.ui.horizontalSlider.setToolTip(_("Scale: ") + str(int(self.scale * 100)) + "%")


info = "<b>Agreement %</b>" \
       "<p>Calculated across the text file as the (total dual coded plus the total uncoded) / total characters</p>" \
       "<p>Calculated in images similarly but by pixel count.</p>" \
       "<b>Disagreement %</b><p>Is 100% minus the total agreement percent.</p>" \
       "<b>Kappa</b><p>Used to measure inter-rater reliability. " \
       "Calculations are based on this site https://en.wikipedia.org/wiki/Cohen%27s_kappa</p>"
