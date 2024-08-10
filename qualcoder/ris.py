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
"""

import collections
import datetime
import logging
import os
import rispy
import sys
import traceback
from PyQt6 import QtWidgets

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class Ris:
    """ Load ris list of dictionaries.
        Format RIS to Vancouver or APA for display.
        References in RIS can be poorly created often due to how the researcher created them. """

    app = None
    refs = []

    def __init__(self, app):
        self.app = app

    def get_references(self, selected_ris=None):
        """ As list of dictionaries with risid and summary.

        """

        self.refs = []
        cur = self.app.conn.cursor()
        if not selected_ris:
            cur.execute("select distinct risid from ris order by risid")
        else:
            cur.execute("select distinct risid from ris where risid=?", [selected_ris])
        ris_ids_res = cur.fetchall()
        if not ris_ids_res:  # May be empty if selected_ris is incorrect or no references present
            return
        for ris_id in ris_ids_res:
            ref = {'risid': ris_id[0]}
            details = str(ris_id[0]) + " "
            cur.execute("select tag, longtag, value from ris where risid=?", [ris_id[0]])
            ris_result = cur.fetchall()
            jnl_or_secondary_title = ""
            for tpl in ris_result:
                ref[tpl[0]] = tpl[2]
                ref[tpl[1]] = tpl[2]
                details += f"{tpl[0]} - {tpl[1]} - {tpl[2]}\n"
                if tpl[0] == 'JO':
                    jnl_or_secondary_title = tpl[2]
                if jnl_or_secondary_title == "" and tpl[0] == 'JF':
                    jnl_or_secondary_title = tpl[2]
                if jnl_or_secondary_title == "" and tpl[0] == 'T2':
                    jnl_or_secondary_title = tpl[2]
            ref['details'] = details
            ref['journal_or_secondary'] = jnl_or_secondary_title
            # This is use in Manage files display
            ref['journal_vol_issue'] = jnl_or_secondary_title + " "
            # Volume and issue
            volume = None
            issue = None
            ref['volume'] = ""
            ref['issue'] = ""
            for tpl in ris_result:
                if 'VL' in tpl:
                    volume = tpl[2]
                    ref['volume'] = tpl[2]
                if volume is None and 'VO' in tpl:
                    volume = tpl[2]
                    ref['volume'] = tpl[2]
                if 'IS' in tpl:
                    issue = tpl[2]
                    ref['issue'] = tpl[2]
            if volume and issue:
                ref['journal_vol_issue'] += f"{volume} ({issue})"
            if 'PY' not in ref:
                ref['PY'] = ""
            if 'authors' not in ref:
                ref['authors'] = ""
            if 'keywords' not in ref:
                ref['keywords'] = ""
            ref['vancouver'], ref['apa'] = self.format_vancouver_and_apa(ref)
            self.refs.append(ref)

    def format_vancouver_and_apa(self, ref):
        """ Format items in list for display as Vancouver style and APA style.
            Vancouver:
            Title.  authors (or editor)
            journal name, year, date, volume, issue, pages
            publisher (and place) issn, url

            APA:
            authors (year). title, journal volume issue (page numbers) URL
         """

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
        vancouver = ""  # Vancouver reference style, approximately
        apa = "" # American Psychological Association reference style

        # Get the first title based on this order
        for tag in ("TI", "T1", "ST", "TT"):
            try:
                title = f"{ref[tag]}.\n"
                break
            except KeyError:
                pass
        # Authors
        for tag in ("AU", "A1", "A2", "A3", "A4"):
            try:
                authors += " " + ref[tag]
            except KeyError:
                pass
        if authors != "":
            authors = authors[1:] + "\n"
        # Editor
        if 'ED' in ref:
            editor = f"Editor: {ref['ED']} \n"
        # Publication year
        if 'PY' in ref:
            published_year = ref['PY']
        if published_year == "" and 'Y1' in ref:
            published_year = ref['Y1']
        # Publisher
        if 'PB' in ref:
            publisher = ref['PB']
            if 'PP' in ref:
                publisher += f" {ref['PP']}"
        # ISSN
        if 'SN' in ref:
            issn = f"ISSN: {ref['SN']}"
        # Journal name, T2 tag is often used for this
        for tag in ("JO", "JF", "T2", "JA", "J1", "J2"):
            try:
                if periodical_name == "":
                    periodical_name = f"{ref[tag]} "
                    continue
            except KeyError:
                pass
        # Edition
        if 'ET' in ref:
            edition = ref['ET']
        # Volume and issue
        if 'VL' in ref:
            volume = f" Vol.{ref['VL']}"
        if volume is None and 'VO' in ref:
            volume = " Vol." + ref['VO']
        if 'IS' in ref:
            issue = ref['IS']
        volume_and_or_issue = ""
        if volume and issue:
            volume_and_or_issue = volume + f"({issue}) "
        if volume is None and issue:
            volume_and_or_issue += " " + issue + " "
        if volume_and_or_issue == "" and edition:
            volume_and_or_issue = "Edn. " + edition
        # Pages
        if 'SP' in ref:
            pages = ref['SP']
        if 'EP' in ref:
            end_page = ref['EP']
        if pages and end_page is not None:
            pages += "-" + end_page
        if pages:
            pages = " pp." + pages
            pages = pages.strip()
        # URL
        if 'UR' in ref:
            url = ref['UR']
            if 'Y2' in ref:
                url += f" Accessed: {ref['Y2']}"
        if 'DO' in ref:
            doi = f"doi: {ref['DO']}"

        # Wrap up Vancouver style reference
        vancouver = title + authors
        if editor:
            vancouver += editor
        # Periodicals
        vancouver += periodical_name + published_year + " " + volume_and_or_issue
        if pages:
            vancouver += pages
        vancouver += "\n"
        # Other published
        if publisher:
            vancouver += publisher + " "
        # Extra information
        if issn:
            vancouver += issn + "\n"
        # Links
        if url:
            vancouver += url + "\n"
        if doi:
            vancouver += doi
        # Clean up
        vancouver = vancouver.replace("  ", " ")
        vancouver = vancouver.strip()

        # Wrap up APA style
        # authors(year).title, journal volume issue(page numbers) URL
        apa = authors.replace(";", ",")
        if editor:
            apa += editor
        apa += " "
        if published_year != "":
            apa += f"({published_year}). "
        if title != "":
            apa += f"{title}"
        if periodical_name != "":
            apa += f"{periodical_name}, "
        if volume_and_or_issue != "":
            apa += f"{volume_and_or_issue}. "
        if pages:
            apa += f"({pages})"
        if url is not None:
            apa += url
        if doi is not None:
            apa += f" {doi}"
        # Clean up
        apa = apa.replace(" ,", ",")
        apa = apa.replace(" .", ".")
        apa = apa.replace("  ", " ")
        apa = apa.strip()

        return vancouver, apa


class RisImport:
    """ Import an RIS format bibliography and store in database.
    References in RIS can be poorly created often due to how the researcher created them.

    Create these variables for the sources
    Ref_Type (Type of Reference) – character variable
    Ref_Author (authors list) – character
    Ref_Title – character
    Ref_Year (of publication) – numeric
    Ref_journal
    """

    app = None
    parent_text_edit = None

    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_text_edit = parent_text_edit
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select RIS references file'),
                                                          self.app.settings['directory'],
                                                          "(*.txt *.ris *.RIS)")
        # options=QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        imports = response[0]
        if imports:
            self.create_file_attributes()
            self.create_file_placeholder_attributes()
            self.import_ris_file(imports[0])

    def create_file_attributes(self):
        """ Creates the attributes for Ref_Authors, Ref_Title, Ref_Type, Ref_Year, Ref_Journal """

        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        ref_vars = {'Ref_Authors': 'character', 'Ref_Title': 'character', 'Ref_Type': 'character',
                    'Ref_Year': 'numeric', 'Ref_Journal': 'character'}
        for key in ref_vars:
            cur.execute("select name from attribute type where name=?", [key])
            res = cur.fetchone()
            if not res:
                cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                        (key, now_date, self.app.settings['codername'], "", 'file', ref_vars[key]))
                self.app.conn.commit()
        self.app.delete_backup = False

    def create_file_placeholder_attributes(self):
        """ Creates empty placeholder attributes for each file.
         Duplicated the methods manage_files.check_attribute_placeholders """

        cur = self.app.conn.cursor()
        sql = "select id from source "
        cur.execute(sql)
        sources = cur.fetchall()
        sql = 'select name from attribute_type where caseOrFile ="file"'
        cur.execute(sql)
        attr_types = cur.fetchall()
        attr_types = ["Ref_Authors", "Ref_Title", "Ref_Type", "Ref_Year", "Ref_Journal"]
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)"
        for source in sources:
            for att in attr_types:
                sql = "select value from attribute where id=? and name=?"
                cur.execute(sql, [source[0], att])
                res = cur.fetchone()
                if res is None:
                    placeholders = [att, source[0], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    self.app.settings['codername']]
                    cur.execute(insert_sql, placeholders)
                    self.app.conn.commit()

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
                    if not isinstance(data, str):
                        continue
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
            if not isinstance(data, str):
                continue
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


