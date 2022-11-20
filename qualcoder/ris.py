# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

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
"""

import collections
import logging
import os
import rispy
import sys
import traceback
from PyQt6 import QtWidgets

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


class Ris:
    """ Load ris list of dictionaries.
        Format RIS to short display.
        References in RIS can be poorly created often due to how the researcher created them. """

    app = None
    refs = []

    def __init__(self, app):
        sys.excepthook = exception_handler
        self.app = app

    def get_references(self):
        """ As list if dictionaries with risid and summary
        """
        cur = self.app.conn.cursor()
        self.refs = []
        cur.execute("select distinct risid from ris order by risid")
        ris_ids_res = cur.fetchall()
        for ris_id in ris_ids_res:
            ref = {'risid': ris_id[0]}
            details = str(ris_id[0]) + " "
            cur.execute("select tag, longtag, value from ris where risid=?", [ris_id[0]])
            res = cur.fetchall()
            for r in res:
                ref[r[0]] = r[2]
                ref[r[1]] = r[2]
                details += r[0] + ' - ' + r[1] + ' - ' + r[2] + "\n"
            ref['details'] = details
            ref['formatted'] = self.format_ris(ref)
            self.refs.append(ref)

    def format_ris(self, ref):
        """ Format items in list for display.
            ref type
            title
            authors (or editor)
            journal name, year, date, volume, issue
            pages
            publisher (and place)
            issn
            url, doi?
         """

        ref_type = ""
        try:
            ref_type = ref_types[ref['TY']] + "\n"
        except KeyError:
            pass
        title = ""
        authors = ""
        published_year = ""
        periodical_name = ""
        volume = None
        issue = None
        editor = None
        edition = None
        pages = None
        end_page = None
        publisher = None
        issn = None
        url = None
        doi = None
        txt = ""

        for tag in ("TI", "ST", "T2", "T3", "TT"):
            try:
                # Get the first title based on the above order
                if title == "":
                    title = ref[tag] + "\n"
            except KeyError:
                pass
        for tag in ("AU", "A1", "A2", "A3", "A4"):
            try:
                authors += " " + ref[tag]
            except KeyError:
                pass
        if authors != "":
            authors = authors[1:] + "\n"
        try:
            editor = "Editor: " + ref['ED'] + "\n"
        except KeyError:
            pass

        for tag in ("PY", "Y1"):
            try:
                if published_year == "":
                    published_year = ref[tag] + " "
            except KeyError:
                pass
        try:
            publisher = ref['PB']
            try:
                publisher += " " + ref['PP']
            except KeyError:
                pass
        except KeyError:
            pass
        try:
            issn = "ISSN: " + ref['SN']
        except KeyError:
            pass
        # Journal name, T2 tag is often used for this
        for tag in ("JO", "JF", "T2", "JA", "J1", "J2"):
            try:
                if periodical_name == "":
                    periodical_name = ref[tag] + ". "
            except KeyError:
                pass
        # Edition
        try:
            edition = ref['ET']
        except KeyError:
            pass
        # Volume and issue
        for tag in ("VL", "VO"):
            try:
                if volume is None:
                    volume = " Vol." + ref[tag]
            except KeyError:
                pass
        try:
            issue = ref['IS']
        except KeyError:
            pass
        volume_and_or_issue = ""
        if volume and issue:
            volume_and_or_issue = volume + "(" + issue + ") "
        if volume is None and issue:
            volume_and_or_issue += " " + issue + " "
        if volume_and_or_issue == "" and edition:
            volume_and_or_issue = "Edn. " + edition
        # Pages
        try:
            pages = ref['SP']
        except KeyError:
            pass
        try:
            end_page = ref['EP']
        except KeyError:
            pass
        if pages and end_page is not None:
            pages += "-" + end_page
        if pages:
            pages = " pp." + pages
        # URL and DOI
        try:
            url = ref['UR']
            try:
                url += " Accessed: " + ref['Y2']
            except KeyError:
                pass
        except KeyError:
            pass
        try:
            doi = "DOI: " + ref['DO']
        except KeyError:
            pass

        # Wrap up reference
        txt += ref_type + title + authors
        if editor:
            txt += editor
        # Periodicals
        txt += periodical_name + published_year + volume_and_or_issue
        if pages:
            txt += pages
        txt += "\n"
        # Other published
        if publisher:
            txt += publisher + " "
        # Extra information
        if issn:
            txt += issn + "\n"
        # Links
        if url:
            txt += url + "\n"
        '''if doi:
            txt += doi'''
        # Clean up
        txt = txt.replace("  ", " ")
        txt = txt.strip()
        #print(txt)
        return txt


class RisImport:
    """ Import an RIS format bibliography and store in database.
    References in RIS can be poorly created often due to how the researcher created them. """

    app = None
    parent_text_edit = None

    def __init__(self, app, parent_text_edit):
        sys.excepthook = exception_handler
        self.app = app
        self.parent_text_edit = parent_text_edit
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select RIS references file'),
                                                          self.app.settings['directory'],
                                                          "(*.txt *.ris *.RIS)",
                                                          options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                          )
        # print("Response ", response)
        imports = response[0]
        if imports:
            self.import_ris_file(imports[0])

    def import_ris_file(self, filepath):
        """ Open file and extract RIS information.
        List tags: 'A1', 'A2', 'A3', 'A4', 'AU', 'KW', 'N1'  # authors, KW keywords, N1 Notes
        longtag is the extended wording of a tag
        tag_keys is the dictionary of 2 char short tag keys (e.g. AU) and the longtag wording
        """

        #list_tags = rispy.LIST_TYPE_TAGS
        #print("List tags ", list_tags)
        tag_keys = rispy.TAG_KEY_MAPPING
        #for tk in tag_keys:
        #    print(tk, tag_keys[tk])
        longtag_to_tag = dict((v, k) for k, v in tag_keys.items())
        cur = self.app.conn.cursor()
        cur.execute("select max(risid) from ris")
        res = cur.fetchone()
        new_entries = 0
        duplicates = 0
        max_risid = 0
        if res is not None:
            max_risid = res[0]
            if max_risid is None:
                max_risid = 0
        with open(filepath, 'r', encoding="utf-8", errors="surrogateescape") as ris_file:
            entries = rispy.load(ris_file)
        for entry in entries:
            try:
                del entry['id']
            except KeyError:
                pass
            if self.entry_exists(entry):
                duplicates += 1
            else:
                new_entries += 1
                max_risid += 1
                #print(entry.keys())
                for longtag in entry:
                    if isinstance(entry[longtag], list):
                        data = "; ".join(entry[longtag])
                    else:
                        data = entry[longtag]
                    #print("risid", max_risid, longtag_to_tag[longtag], longtag, data)
                    sql = "insert into ris (risid,tag,longtag,value) values (?,?,?,?)"
                    cur.execute(sql, [max_risid, longtag_to_tag[longtag], longtag, data])
            self.app.conn.commit()

        if new_entries > 0:
            msg = _("Bibliography loaded from: ") + filepath + "\n"
            msg += _("New Entries: ") + str(new_entries) + "\n"
            if duplicates > 0:
                msg += _("Duplicates not inserted: ") + str(duplicates)
            self.parent_text_edit.append(msg + "\n========")
        else:
            msg = _("No new references loaded from: ") + filepath + "\n"
            if duplicates > 0:
                msg += _("References already exist")
            self.parent_text_edit.append(msg + "\n========")

    def entry_exists(self, entry):
        """ Check if this entry exists.
        Criteria for exists: each entry matches for tag and value. Identical number of data points.
        param: entry - dictionary of longtag and value
        return: exists - boolean
        """

        exists = False
        #print(entry)
        res_list = []
        cur = self.app.conn.cursor()
        sql = "select risid from ris where longtag=? and value=?"
        for longtag in entry:
            if isinstance(entry[longtag], list):
                data = "; ".join(entry[longtag])
            else:
                data = entry[longtag]
            #print("Parameters ", longtag, data)
            cur.execute(sql, [longtag, data])
            res = cur.fetchall()
            #print("res for",longtag,data,res)
            for r in res:
                res_list.append(r[0])
        #print("len entry ", len(entry), "res_list", res_list)
        # Check number of db matching data points equals the number of data points in entry
        frequencies = collections.Counter(res_list)
        freq_dict = dict(frequencies)
        for k in freq_dict:
            if freq_dict[k] == len(entry):
                exists = True
        return exists


ref_types = {
'ABST': 'Abstract',
'ADVS': 'Audiovisual material',
'AGGR': 'Aggregated Database',
'ANCIENT': 'Ancient Text',
'ART': 'Art Work',
'BILL': 'Bill',
'BLOG': 'Blog',
'BOOK': 'Whole book',
'CASE': 'Case',
'CHAP': 'Book chapter',
'CHART': 'Chart',
'CLSWK': 'Classical Work',
'COMP': 'Computer program',
'CONF': 'Conference proceeding',
'CPAPER': 'Conference paper',
'CTLG': 'Catalog',
'DATA': 'Data file',
'DBASE': 'Online Database',
'DICT': 'Dictionary',
'EBOOK': 'Electronic Book',
'ECHAP': 'Electronic Book Section',
'EDBOOK': 'Edited Book',
'EJOUR': 'Electronic Article',
'WEB': 'Web Page',
'ENCYC': 'Encyclopedia',
'EQUA': 'Equation',
'FIGURE': 'Figure',
'GEN': 'Generic',
'GOVDOC': 'Government Document',
'GRANT': 'Grant',
'HEAR': 'Hearing',
'ICOMM': 'Internet Communication',
'INPR': 'In Press',
'JFULL': 'Journal (full)',
'JOUR': 'Journal',
'LEGAL': 'Legal Rule or Regulation',
'MANSCPT': 'Manuscript',
'MAP': 'Map',
'MGZN': 'Magazine article',
'MPCT': 'Motion picture',
'MULTI': 'Online Multimedia',
'MUSIC': 'Music score',
'NEWS': 'Newspaper',
'PAMP': 'Pamphlet',
'PAT': 'Patent',
'PCOMM': 'Personal communication',
'RPRT': 'Report',
'SER': 'Serial publication',
'SLIDE': 'Slide',
'SOUND': 'Sound recording',
'STAND': 'Standard',
'STAT': 'Statute',
'THES': 'Thesis/Dissertation',
'UNBILL': 'Unenacted Bill',
'UNPB': 'Unpublished work',
'VIDEO': 'Video recording'
}


