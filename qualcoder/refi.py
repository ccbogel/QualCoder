# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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

from copy import copy
import datetime
import logging
from lxml import etree
from operator import itemgetter
import os
import re
import shutil
import sqlite3
import sys
import traceback
import uuid
try:
    import vlc
except:
    pass
from xsd import codebook, project
import zipfile

from PyQt5 import QtWidgets

from helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    #QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class Refi_import():
    """     Import Rotterdam Exchange Format Initiative (refi) xml documents for codebook.xml
    and project.xml
    Validate using REFI-QDA Codebook.xsd or Project-mrt2019.xsd
    """

    #TODO parse_sources PDF - WORKS BUT FULLY WORKS ?
    #TODO load_audio_source - check it works, load transcript, transcript synchpoints, transcript codings
    #TODO load_video_source - check it works, load transcript, transcript synchpoints, transcript codings
    #TODO check imports from different vendors
    #TODO reference external sources - relative or absolute paths

    file_path = None
    codes = []
    users = []
    cases = []
    sources = []
    variables = []  # Dictionary of Variable guid, name, variable application (cases or files/sources), last_insert_id, text or other
    parent_textEdit = None
    app = None
    tree = None
    import_type = None
    xml = None
    base_path = ""

    def __init__(self, app, parent_textEdit, import_type):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.import_type = import_type
        self.tree = None
        self.codes = []
        self.users = []
        self.cases = []
        self.sources = []
        self.variables = []
        self.base_path = ""
        self.file_path, ok = QtWidgets.QFileDialog.getOpenFileName(None,
            _('Select REFI_QDA file'), self.app.settings['directory'], "(*." + import_type + ")")
        if not ok or self.file_path == "":
            return

        if import_type == "qdc":
            self.import_codebook()
        else:
            self.import_project()

    def import_codebook(self):
        """ Import REFI-QDA standard codebook into opened project.
        Codebooks do not validate using the qdasoftware.org Codebook.xsd generated on 2017-10-05 16:17z"""

        """
        with open(self.file_path, "r") as xml_file:
            self.xml = xml_file.read()
        result = self.xml_validation("codebook")
        print("PARSING: ", result)
        # Typical error with codebook XSD validation:
        # PARSING ERROR: StartTag: invalid element name, line 3, column 2 (Codebook.xsd, line 3)
        """

        tree = etree.parse(self.file_path)  # get element tree object
        root = tree.getroot()
        # look for the Codes tag, which contains each Code element
        children = root.getchildren()
        for cb in children:
            #print("CB:", cb, "tag:", cb.tag)  # 1 only , Codes
            if cb.tag in ("{urn:QDA-XML:codebook:1:0}Codes", "{urn:QDA-XML:project:1.0}Codes"):
                counter = 0
                code_elements = cb.getchildren()
                for c in code_elements:
                    # recursive search through each Code element
                    counter += self.sub_codes(cb, None)
                Message(self.app, _("Codebook imported"),
                    str(counter) + _(" categories and codes imported from ") + self.file_path).exec_()
                return
        Message(self.app, _("Codebook importation"), self.file_path + _(" NOT imported"), "warning").exec_()

    def sub_codes(self, parent, cat_id):
        """ Get subcode elements, if any.
        Determines whether the Code is a Category item or a Code item.
        Uses the parent entered cat_id ot give a Code a category alignment,
        or if a category, gives the category alignment to a super_category.
        Called from: import_project, import_codebook

        Some software e.g. MAXQDA categories are also codes
        in this case QualCoder will create a category, and also a code with the same name underneath that category

        Recursive, until no more child Codes found.
        Enters this category or code into database and obtains a cat_id (last_insert_id) for next call of method.
        Note: urn difference between codebook.qdc and project.qdpx

        :param parent element, cat_id

        :returns counter of inserted codes and categories
        """

        counter = 0
        elements = parent.getchildren()
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        description = ""
        for e in elements:
            if e.tag in("{urn:QDA-XML:codebook:1:0}Description", "{urn:QDA-XML:project:1.0}Description"):
                description = e.text

        # Determine if the parent is a code or a category
        # if it has Code element children, so must be a category, insert into code_cat table
        is_category = False
        for e in elements:
            if e.tag in ("{urn:QDA-XML:codebook:1:0}Code", "{urn:QDA-XML:project:1.0}Code"):
                is_category = True
        if is_category:
            last_insert_id = None
            name = parent.get("name")
            if name is not None:
                cur = self.app.conn.cursor()
                # insert this category into code_cat table
                try:
                    cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,'',?,?)"
                        , [name, description, now_date, cat_id])
                    self.app.conn.commit()
                    cur.execute("select last_insert_rowid()")
                    last_insert_id = cur.fetchone()[0]
                    counter += 1
                except sqlite3.IntegrityError as e:
                    QtWidgets.QMessageBox.warning(None, _("Import error"), _("Category name already exists: ") + name)

                # This category may ALSO be a code (e.g. MAXQDA has categories as codes also)
                # So create a code for this codable category
                isCodable = parent.get("isCodable")
                if isCodable == "true":
                    color = parent.get("color")
                    if color is None:
                        color = "#999999"
                    try:
                        #print(isCodable, name, "inserting into code name")
                        cur = self.app.conn.cursor()
                        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)"
                            , [name, description, now_date, last_insert_id, color])
                        self.app.conn.commit()
                        cur.execute("select last_insert_rowid()")
                        code_last_insert_id = cur.fetchone()[0]
                        self.codes.append({'guid': parent.get('guid'), 'cid': code_last_insert_id})
                        counter += 1
                    except sqlite3.IntegrityError as e:
                        QtWidgets.QMessageBox.warning(None, _("Import error"), _("Code name already exists: ") + name)

            for e in elements:
                if e.tag not in ("{urn:QDA-XML:codebook:1:0}Description", "{urn:QDA-XML:project:1.0}Description"):
                    counter += self.sub_codes(e, last_insert_id)
                    #print("tag:", e.tag, e.text, e.get("name"), e.get("color"), e.get("isCodable"))
            return counter

        # No children and no Description child element so, insert this code into code_name table
        if is_category is False and elements == []:
            name = parent.get("name")
            #print("No children or description ", name)
            color = parent.get("color")
            if color == None:
                color = "#999999"
            try:
                cur = self.app.conn.cursor()
                cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)"
                    , [name, description, now_date, cat_id, color])
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                last_insert_id = cur.fetchone()[0]
                self.codes.append({'guid': parent.get('guid'), 'cid': last_insert_id})
                counter += 1
            except sqlite3.IntegrityError as e:
                QtWidgets.QMessageBox.warning(None, _("Import error"), _("Code name already exists: ") + name)
            return counter

        # One child, a description so, insert this code into code_name table
        if is_category is False and len(elements) == 1 and elements[0].tag in ("{urn:QDA-XML:codebook:1:0}Description", "{urn:QDA-XML:project:1.0}Description"):
            name = parent.get("name")
            #print("Only a description child: ", name)
            color = parent.get("color")
            if color == None:
                color = "#999999"
            try:
                cur = self.app.conn.cursor()
                cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)"
                    , [name, description, now_date, cat_id, color])
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                last_insert_id = cur.fetchone()[0]
                self.codes.append({'guid': parent.get('guid'), 'cid': last_insert_id})
                counter += 1
            except sqlite3.IntegrityError as e:
                QtWidgets.QMessageBox.warning(None, _("Import error"), _("Code name already exists: ") + name)
            return counter

        # SHOULD NOT GET HERE
        print("SHOULD NOT GET HERE")
        print("tag:", e.tag, e.text, e.get("name"), e.get("color"), e.get("isCodable"))
        logger.debug("REFI sub_codes import: SHOULD NOT GET HERE:")
        logger.debug("tag:" + str(e.tag) + " " + str(e.text) + " name:" + str(e.get("name")) + " color:" + str(e.get("isCodable")))
        QtWidgets.QMessageBox.warning(None, "tag: " + e.tag +"  " + e.text + " " + e.get("name") + " " + e.get("color") +" " + e.get("isCodable"))
        return counter

    def import_project(self):
        """ Import REFI-QDA standard project into a new project space.
        Unzip project folder and parse xml.
        Key project tags:
        {urn: QDA - XML: project:1.0}Users
        {urn: QDA - XML: project:1.0}CodeBook
        {urn: QDA - XML: project:1.0}Variables
        {urn: QDA - XML: project:1.0}Cases
        {urn: QDA - XML: project:1.0}Sources
        {urn: QDA - XML: project:1.0}Links  not implemented
        {urn: QDA - XML: project:1.0}Sets  not implemented
        {urn: QDA - XML: project:1.0}Graphs  not implemented
        {urn: QDA - XML: project:1.0}Notes
        {urn: QDA - XML: project:1.0}Description

        Source files:
        Internal files are identified in the path attribute of the source element by the
        URL naming scheme internal:// /Sources folder
        plainTextPath="internal://8e7fddfe‐db36‐48dc‐b464‐80c3a4decd90.txt"
        richTextPath="internal://6f35c6f2‐bd8f‐4f08‐ad49‐6d62cb8442a5.docx" >

        path="internal://361bcdb8‐7d11‐4343‐a4cd‐4130693eff76.png"

        External files are identified in the path attribute of the source element by the URL
        They can be relative to the basePath of the project
        path="relative:///DF370983‐F009‐4D47‐8615‐711633FA9DE6.m4a"
        basePath='//PROJECT/Sources'

        Or they can be Absolute paths
        path="absolute:///hiome/username/Documents/DF370983‐F009‐4D47‐8615‐711633FA9DE6.m4a"
        """

        # Create extract folder
        self.folder_name = self.file_path[:-4] + "_temporary"
        self.parent_textEdit.append(_("Reading from: ") + self.file_path)
        self.parent_textEdit.append(_("Creating temporary directory: ") + self.folder_name)

        # Unzip folder
        project_zip = zipfile.ZipFile(self.file_path)
        project_zip.extractall(self.folder_name)
        project_zip.close()
        # Parse xml
        with open(self.folder_name + "/project.qde", "r") as xml_file:
            self.xml = xml_file.read()
        result = self.xml_validation("project")
        self.parent_textEdit.append("Project XML parsing successful: " + str(result))

        tree = etree.parse(self.folder_name + "/project.qde")  # get element tree object
        root = tree.getroot()
        children = root.getchildren()
        for c in children:
            #print(c.tag)
            if c.tag == "{urn:QDA-XML:project:1.0}Project":
                self.parse_project_tag(c)
            if c.tag == "{urn:QDA-XML:project:1.0}Users":
                count = self.parse_users(c)
                self.parent_textEdit.append(_("Parse users. Loaded: " + str(count)))
            if c.tag == "{urn:QDA-XML:project:1.0}CodeBook":
                codes = c.getchildren()[0]  # <Codes> tag is only element
                count = 0
                for code in codes:
                    # recursive search through each Code in Codes
                    count += self.sub_codes(code, None)
                self.parent_textEdit.append(_("Parse codes and categories. Loaded: " + str(count)))
            if c.tag == "{urn:QDA-XML:project:1.0}Variables":
                count = self.parse_variables(c)
                self.parent_textEdit.append(_("Parse file variables. Loaded: ") + str(count[0]))
                self.parent_textEdit.append(_("Parse case variables. Loaded: ") + str(count[1]))
            if c.tag == "{urn:QDA-XML:project:1.0}Notes":
                count = self.parse_notes(c)
                self.parent_textEdit.append(_("Parsing journal notes. Loaded: " + str(count)))
            if c.tag == "{urn:QDA-XML:project:1.0}Description":
                self.parent_textEdit.append(_("Parsing and loading project memo"))
                self.parse_project_description(c)
            QtWidgets.QApplication.processEvents()

        # Parse cases and sources after the variables components parsed
        # Need to fill placeholders and values for variables for sources and cases
        children = root.getchildren()
        for c in children:
            # print(c.tag)
            if c.tag == "{urn:QDA-XML:project:1.0}Cases":
                count = self.parse_cases(c)
                self.parent_textEdit.append(_("Parsing cases. Loaded: " + str(count)))
            if c.tag == "{urn:QDA-XML:project:1.0}Sources":
                count = self.parse_sources(c)
                self.parent_textEdit.append(_("Parsing sources. Loaded: " + str(count)))
        self.clean_up_case_codes_and_case_text()
        self.parent_textEdit.append(self.file_path + _(" loaded."))

        # Remove temporary extract folder
        try:
            shutil.rmtree(self.folder_name)
        except OSError as e:
            logger.debug(str(e) + " " + self.folder_name)

        # Change the user name to an owner name from the import
        if len(self.users) > 0:
            self.app.settings['codername'] = self.users[0]['name']
            self.app.write_config_ini(self.app.settings)

        msg = "EXPERIMENTAL - NOT FULLY TESTED\n"
        msg += "Audio/video transcripts: transcript codings and synchpoints not tested.\n"
        msg += "Sets and Graphs not imported as QualCoder does not have this functionality.\n"
        msg += "Boolean variables treated as character (text). Integer variables treated as floating point. \n"
        msg += "All variables are stored as text, but cast as text or float during operations.\n"
        msg += "Relative paths to external files are untested.\n"
        msg += "\n\nSelect a coder name in Settings dropbox, otherwise coded text and media may appear uncoded."
        Message(self.app, _('REFI-QDA Project import'), msg, "warning").exec_()

    def parse_variables(self, element):
        """ Parse the Variables element.
        Example format:
        <Variable guid="51dc3bcd-5454-47ff-a4d6-ea699144410d" name="Cases:Age group" typeOfVariable="Text">
        <Description />
        </Variable>

        typeOfVariable: Text, Boolean, Integer, Float, Date, Datetime

        :param element

        :return count of variables
        """

        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        casevarcount = 0
        filevarcount = 0
        for e in element.getchildren():
            #print(e.tag, e.get("name"), e.get("guid"), e.get("typeOfVariable"))
            # <Variable name="Cases:something"> or ?
            name = ""
            caseOrFile = "file"
            try:
                name = e.get("name").split(':')[1]
                caseOrFile = e.get("name").split(':')[0]
                if caseOrFile == "Cases":
                    caseOrFile = "case"
                else:
                    caseOrFile = "file"
            except IndexError:
                name = e.get("name")

            valuetype = e.get("typeOfVariable")  # may need to tweak Text
            if valuetype in("Text", "Boolean", "Date", "DateTime"):
                valuetype = "character"
            if valuetype in ("Integer", "Float"):
                valuetype = "numeric"
            variable = {"name": name, "caseOrFile": caseOrFile, "guid": e.get("guid"), "id": None, "memo": "", "valuetype": valuetype}
            # Get the description text
            d_elements = e.getchildren()
            for d in d_elements:
                memo = ""
                #print("Memo ", d.tag)
                if e.tag != "{urn:QDA-XML:codebook:1:0}Description":
                    memo = d.text
                variable["memo"] = memo

            # insert variable type into database
            try:
                cur.execute(
                    "insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)"
                    , (name, now_date, self.app.settings['codername'], variable["memo"], caseOrFile, valuetype))
                self.app.conn.commit()
                if caseOrFile == "case":
                    casevarcount += 1
                else:
                    filevarcount += 1

            except sqlite3.IntegrityError as e:
                QtWidgets.QMessageBox.warning(None, _("Variable import error"), _("Variable name already exists: ") + name)

            # refer to the variables later
            self.variables.append(variable)
        return [filevarcount, casevarcount]

    def parse_cases(self, element):
        """ Parse the Cases element.
        Need to parse the element twice.
        First parse: enter Cases into database to generate caseids after insert.
        Enter empty values for Variables for each Case.
        Second parse: read variable values and update in attributes table.

        Note: some Codes in CodeBook are Cases - they use the same guid

        Example xml format:
        <Case guid="4a463c0d-9263-494a-81d6-e9d5a229f227" name="Anna">
            <Description />
            <VariableValue>
                <VariableRef targetGUID="51dc3bcd-5454-47ff-a4d6-ea699144410d" />
                <TextValue>20-29</TextValue>
                </VariableValue>
            <VariableValue>
                <VariableRef targetGUID="d5ef65d5-bf84-425b-a1d6-ea69914df5ca" />
                <TextValue>Female</TextValue>
            </VariableValue>
        </Case>

        :param element - the Cases element:
        """

        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        count = 0
        for e in element.getchildren():
            #print(e.tag, e.get("name"), e.get("guid"))

            item = {"name": e.get("name"), "guid": e.get("guid"), "owner": self.app.settings['codername'], "memo": "", "caseid": None}
            # Get the description text
            d_elements = e.getchildren()
            for d in d_elements:
                memo = ""
                #print("Memo ", d.tag)
                if e.tag != "{urn:QDA-XML:codebook:1:0}Description":
                    memo = d.text
                item["memo"] = memo

            # Enter Case into sqlite and keep a copy in  a list
            try:
                cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)"
                    ,(item['name'], item['memo'], item['owner'], now_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                item['caseid'] = cur.fetchone()[0]
                self.cases.append(item)
                count += 1
            except Exception as e:
                self.parent_textEdit.append(_('Error entering Case into database') + '\n' + str(e))
                logger.error("item:" + str(item) + ", " + str(e))

            # Create an empty attribute entry for each Case and variable in the attributes table
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            for v in self.variables:
                if v['caseOrFile'] == 'case':
                    cur.execute(sql, (v['name'], "", item['caseid'], 'case', now_date, self.app.settings['codername']))
                    self.app.conn.commit()

            # look for VariableValue tag, extract and enter into
            for vv in d_elements:
                guid = None
                value = None
                if vv.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                    for v_element in vv.getchildren():
                        if v_element.tag == "{urn:QDA-XML:project:1.0}VariableRef":
                            guid = v_element.get("targetGUID")
                        if v_element.tag in ("{urn:QDA-XML:project:1.0}TextValue", "{urn:QDA-XML:project:1.0}BooleanValue",
                        "{urn:QDA-XML:project:1.0}IntegerValue", "{urn:QDA-XML:project:1.0}FloatValue",
                        "{urn:QDA-XML:project:1.0}DateValue", "{urn:QDA-XML:project:1.0}DateTimeValue"):
                            value = v_element.text
                    #print(guid, value)
                    # Get attribute name by linking guids
                    attr_name = ""
                    for attr in self.variables:
                        if attr['guid'] == guid:
                            attr_name = attr['name']

                    # Update the attribute table
                    sql = "update attribute set value=? where name=? and attr_type='case'and id=?"
                    cur.execute(sql, (value, attr_name, item['caseid']))
                    self.app.conn.commit()
        return count

    def clean_up_case_codes_and_case_text(self):
        """ Some Code guids match the Case guids. So remove these Codes.
        For text selectino:
        Some Coding selections match the Case guid. So re-align to Case selections.
        """

        cur = self.app.conn.cursor()

        # Remove Code and code_text
        case_texts = []
        for case in self.cases:
            for code in self.codes:
                if case['guid'] == code['guid']:
                    cur.execute("delete from code_name where cid=?", (code['cid'],))
                    cur.execute("select ? as 'caseid', fid, pos0,pos1, owner, date, memo from code_text where cid=?",
                        (case['caseid'], code['cid']))
                    results = cur.fetchall()
                    for c in results:
                        case_texts.append(c)
                    cur.execute("delete from code_text where cid=?", (code['cid'],))
                    self.app.conn.commit()

        # Insert case text details into case_text
        for c in case_texts:
            sql = "insert into case_text (caseid,fid,pos0,pos1,owner, date, memo) values(?,?,?,?,?,?,?)"
            cur.execute(sql, c)
            self.app.conn.commit()

    def parse_sources(self, element):
        """ Parse the Sources element.
        This contains text and media sources as well as variables describing the source and coding information.
        Example format:
        <TextSource guid="a2b94468-80a5-412f-92d6-e900d97b55a6" name="Anna" richTextPath="internal://a2b94468-80a5-412f-92d6-e900d97b55a6.docx" plainTextPath="internal://a2b94468-80a5-412f-92d6-e900d97b55a6.txt" creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime="2019-06-04T05:25:16Z" modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime="2019-06-04T05:25:16Z">

        If during import it detects that the external file is not found, it should
        check file location and if not found ask user for the new file location.
        This check occurs in qualcoder.py

        :param element: Sources element object

        :return count of sources
        """

        count = 0
        for e in element.getchildren():
            #print(e.tag, e.get("name"))
            if e.tag == "{urn:QDA-XML:project:1.0}TextSource":
                self.load_text_source(e)  # TESTING
            if e.tag == "{urn:QDA-XML:project:1.0}PictureSource":
                self.load_picture_source(e)  # TESTING
            if e.tag == "{urn:QDA-XML:project:1.0}AudioSource":
                self.load_audio_source(e)  # TESTING
            if e.tag == "{urn:QDA-XML:project:1.0}VideoSource":
                self.load_video_source(e)  # TESTING
            if e.tag == "{urn:QDA-XML:project:1.0}PDFSource":
                self.load_pdf_source(e)  # TESTING
            count += 1
        return count

    def name_creating_user_create_date_source_path_helper(self, element):
        """ Helper method to obtain name, guid, creating user, create date, path type from each source.
         The sources folder can be named: sources or Sources
         MAXQDA uses sources, NVIVO uses Sources
         """

        name = element.get("name")
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        # path starts with internal:// or relative:// (with<Project basePath or absolute
        path = element.get("path")
        # Sources folder name can be capital or lower case, check and get the correct one
        contents = os.listdir(self.folder_name)
        sources_name = "/Sources"
        for i in contents:
            if i == "sources":
                sources_name = "/sources"
        # Determine internal or external path
        source_path = ""
        path_type = ""
        if path is None:
            source_path = element.get("plainTextPath").split('internal:/')[1]
            source_path = self.folder_name + sources_name + source_path
            path_type = "internal"
        if path is not None and path.find("internal://") == 0:
            path = element.get("path").split('internal:/')[1]
            source_path = self.folder_name + sources_name + path
            path_type = "internal"
        if path is not None and path.find("relative://") == 0:
            source_path = self.base_path + path.split('relative://')[1]
            path_type = "relative"
        if path is not None and path.find("absolute://") == 0:
            source_path = path.split('absolute://')[1]
            path_type = "absolute"
        return name, creating_user, create_date, source_path, path_type

    def load_picture_source(self, element):
        """ Load this picture source.
         Load the description and codings into sqlite.
         Can manage internal and absolute source paths.
         TODO relative import path

        Params:
            element: PictureSource element object
         """

        name, creating_user, create_date, source_path, path_type = self.name_creating_user_create_date_source_path_helper(element)
        if path_type == "internal":
            # Copy file into .qda images folder and rename into original name
            destination = self.app.project_path + "/images/" + name
            media_path = "/images/" + name
            try:
                shutil.copyfile(source_path, destination)
            except Exception as e:
                self.parent_textEdit.append(_('Cannot copy Image file from: ') + source_path + "\nto: " + destination + '\n' + str(e))
        if path_type == "absolute":
            media_path = "images:" + source_path
        if path_type == "relative":
            #TODO check this works
            media_path = "images:" + self.base_path + source_path
            print(source_path, media_path)
        memo = ""
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = e.text
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (name, memo, creating_user, create_date, media_path, None))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]

        # Parse PictureSelection and VariableValue elements to load codings and variables
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}PictureSelection":
                self._load_codings_for_picture(id_, e)
            if e.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(e, id_, creating_user)

    def _load_codings_for_picture(self, id_, element):
        """ Load coded rectangles for pictures
        Example format:
        <PictureSelection guid="04980e59-b290-4481-8cb6-e732824440a1"
        firstX="783" firstY="1238" secondX="1172" secondY="1788"
        name="some wording."
        creatingUser="70daf61c-b6f0-4b5e-8c2f-548fde3ad3d4" creationDateTime="2019-03-09T23:19:07Z">
        <Coding guid="7a7e80ca-ed8c-4006-86b3-731e36baca19" creatingUser="70daf61c-b6f0-4b5e-8c2f-548fde3ad3d4" >
        <CodeRef targetGUID="1b594544-2954-4b67-86ff-fb552f090ba8"/>
        </Coding></PictureSelection>
        """

        firstX = int(element.get("firstX"))
        firstY = int(element.get("firstY"))
        secondX = int(element.get("secondX"))
        secondY = int(element.get("secondY"))
        width = secondX - firstX
        height = secondY - firstY
        memo = element.get("name")
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        cur = self.app.conn.cursor()
        for e in element:
            if e.tag == "{urn:QDA-XML:project:1.0}Coding":
                # Get the code id from the CodeRef guid
                cid = None
                codeRef = e.getchildren()[0]
                for c in self.codes:
                    if c['guid'] == codeRef.get("targetGUID"):
                        cid = c['cid']
                cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,\
                    date, owner) values(?,?,?,?,?,?,?,?,?)", (id_, firstX, firstY,
                    width, height, cid, memo, create_date, creating_user))
                self.app.conn.commit()

    def load_audio_source(self, element):
        """ Load audio source into .
        Load the description and codings into sqlite.
        Can manage internal and absolute source paths.
        TODO relative path

        Params:
            element: AudioSource element object
        """

        name, creating_user, create_date, source_path, path_type = self.name_creating_user_create_date_source_path_helper(element)
        if path_type == "internal":
            # Copy file into .qda audio folder and rename into original name
            destination = self.app.project_path + "/audio/" + name
            media_path = "/audio/" + name
            try:
                shutil.copyfile(source_path, destination)
            except Exception as e:
                self.parent_textEdit.append(_('Cannot copy Audio file from: ') + source_path + "\nto: " + destination + '\n' + str(e))
        if path_type == "absolute":
            media_path = "audio:" + source_path
        if path_type == "relative":
            #TODO check relative import works
            media_path = "audio:" + self.base_path + source_path
            #print(source_path, media_path)

        memo = ""
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = e.text
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (name, memo, creating_user, create_date, media_path, None))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]

        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Transcript":
                self.parse_transcript_with_codings_and_syncpoints(name, id_, creating_user, e)

        # Parse AudioSelection and VariableValue elements to load codings and variables
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}AudioSelection":
                self.load_codings_for_audio_video(id_, e)
            if e.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(e, id_, creating_user)

    def load_video_source(self, element):
        """ Load this video source into .
        Load the description and codings into sqlite.
        Can manage internal and absolute source paths.
        TODO relative paths to be tested

        Params:
            element: VideoSource element object
        """

        name, creating_user, create_date, source_path, path_type = self.name_creating_user_create_date_source_path_helper(element)
        if path_type == "internal":
            # Copy file into .qda video folder and rename into original name
            destination = self.app.project_path + "/video/" + name
            media_path = "/video/" + name
            try:
                shutil.copyfile(source_path, destination)
            except Exception as e:
                self.parent_textEdit.append(_('Cannot copy Video file from: ') + source_path + "\nto: " + destination + '\n' + str(e))
        if path_type == "absolute":
            media_path = "video:" + source_path
        if path_type == "relative":
            #TODO check relative import works
            media_path = "video:" + self.base_path + source_path
            #print(source_path, media_path)
        memo = ""
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = e.text
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (name, memo, creating_user, create_date, media_path, None))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        av_id = cur.fetchone()[0]

        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Transcript":
                self.parse_transcript_with_codings_and_syncpoints(name, av_id, creating_user, e)

        # Parse VideoSelection and VariableValue elements to load codings and variables
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}VideoSelection":
                self.load_codings_for_audio_video(av_id, e)
            if e.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(e, av_id, creating_user)

    def parse_transcript_with_codings_and_syncpoints(self, av_name, av_id, creating_user, element):
        """ Load the transcript plain text file into source table.
        For now - this file MUST be internal to the project.
        Change transcript filename to match the audio/video name, unless .srt
        Add ".transcribed" suffix so QualCoder can interpret as a transcription for this a/v file.

        Transcription file is stored in documents folder or if an .srt then it is stored in audio or video folder.

        Load the transcript codings.

        Called by: load_audio_source, load_video_source

         Param:
            av_id     : source id in sqlite, Integer
            creating_user    : user who created source, String
            element     : the Transcript element object
         """

        # Change transcript filename to match the audio/video name, unless .srt
        # Add ".transcribed" suffix so qualcoder can interpret as a transcription for this a/v file.
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        guid = element.get("guid")
        #print("guid", element.get("guid"))

        # Load the plain text transcript file into project.
        # Presumes the plain text file is internal
        #TODO rich text path import - UNSURE - IMPORT OR NOT?
        #rich_text_path = element.get("richTextPath")
        #print("rtpath", element.get("richTextPath"))
        plain_text_path = element.get("plainTextPath")
        path_type = "internal"
        if plain_text_path[0:11] == "internal://":
            plain_text_path = plain_text_path[11:]
        else:
            logger.debug("Cannot import plain text transcription file - not internal")
            return

        # Copy plain text file into documents folder, or if .srt into audio or video folder.
        name = element.get("name")
        destination = self.app.project_path + "/documents/" + name
        if name[-4:] == ".srt" and av_name[-4] in ("mp4", "ogg", "mov"):
            destination = self.app.project_path + "/video/" + name
        elif name[-4:] == ".srt" and av_name[-4] in ("mp3", "m4a", "wav"):
            destination = self.app.project_path + "/audio/" + name
        else:
            destination = self.app.project_path + "/documents/" + name
        # Sources folder name can be capital or lower case, check and get the correct one
        contents = os.listdir(self.folder_name)
        sources_name = "/Sources/"
        for i in contents:
            if i == "sources":
                sources_name = "/sources/"
        source_path = self.folder_name + sources_name + plain_text_path
        #print("Source path: ", source_path)
        #print("Destination: ", destination)
        try:
            shutil.copyfile(source_path, destination)
        except Exception as e:
            self.parent_textEdit.append(
                _('Cannot copy transcript file from: ') + source_path + "\nto: " + destination + '\n' + str(e))

        # Load transcription text into database with filename matching and suffixed with .transcribed
        text = ""
        try:
            # can get UnicodeDecode Error on Windows so using error handler
            with open(destination, "r", encoding="utf-8", errors="backslashreplace") as sourcefile:
                while 1:
                    line = sourcefile.readline()
                    if not line:
                        break
                    try:
                        text += line
                    except Exception as e:
                        # logger.debug("Importing plain text file, line ignored: " + str(e))
                        pass
                if text[0:6] == "\ufeff":  # associated with notepad files
                    text = text[6:]
        except Exception as e:
            Message(self.app, _("Warning"), _("Cannot import") + str(destination) + "\n" + str(e), "warning").exec_()

        memo = ""
        if name is not None:
            memo = "Name: " + name + "\n"
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Description":
                if(e.text) is not None:
                    memo += e.text
        if av_name[-12:] != '.transcribed':
            av_filename = av_name + ".transcribed"

        cur = self.app.conn.cursor()
        sql = "insert into source (name, fulltext, mediapath, memo, owner, date) values (?,?,?,?,?,?)"
        cur.execute(sql, [av_filename, text, None, memo, creating_user, create_date])
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        fid = cur.fetchone()[0]

        # Syncpoints
        #TODO syncpoints are not stored in QualCoder - unsure how to make use of the timestamps
        # Perhaps add syncpoint timestamps from and to into the code_text table ?
        syncpoints = []
        """ Format:
        <SyncPoint guid="58716919-f62e-4f2a-b386-6ceb1ebbd859" position="3044" timeStamp="155000" />
        """
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}SyncPoint":
                syncpoints.append({"guid": e.get("guid"), "pos": e.get("position"), "timestamp": e.get("timeStamp")})

        """
        Transcript selections.
        Get a lot of details, av_id, fid (from text into source above), cid, memo, pos0,pos1, seltext, owner, date
        
        <TranscriptSelection guid="fea90668-ed71-4cd9-a47e-23d588f4207e" name="Brighton_Storm.mp4.transcribed" 
        fromSyncPoint="28b27114-5284-4481-837d-dc0d98a5a9a8" 
        toSyncPoint="a687db0f-d12d-401d-b9e3-405dcb2b7879">
        <Description>a note</Description>
        <Coding guid="7f0fa382-05fe-4c93-b0f7-182a4c2eb7b1" >
        <CodeRef targetGUID="a3825924-8bf7-47c1-a51b-be9196147a56" />
        </Coding>
        </TranscriptSelection>
        """

        value_list = []
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}TranscriptSelection":
                pos0 = 0
                pos1 = 0
                guid_pos0 = e.get("fromSyncPoint")
                guid_pos1 = e.get("toSyncPoint")
                for s in syncpoints:
                    if guid_pos0 == s['guid']:
                        #TODO test pos0 and 1 are correct, added 1 for python as String starts from 0
                        pos0 = int(s['pos']) + 1
                    if guid_pos1 == s['guid']:
                        pos1 = int(s['pos']) + 1
                memo = ""
                for ee in e.getchildren():
                    if ee.tag == "{urn:QDA-XML:project:1.0}Description":
                        memo = str(ee.text)
                for ee in e.getchildren():
                    if ee.tag == "{urn:QDA-XML:project:1.0}Coding":
                        cid = None
                        code_ref = ee.getchildren()[0]
                        for c in self.codes:
                            if c['guid'] == code_ref.get("targetGUID"):
                                cid = c['cid']  # String ?
                                value_list.append([cid, fid, text[pos0:pos1], pos0 , pos1, creating_user, create_date, memo, av_id])
        sql = "insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo, avid) "
        sql += " values (?,?,?,?,?,?,?,?,?)"
        cur = self.app.conn.cursor()
        for v in value_list:
            cur.execute(sql, v)
        self.app.conn.commit()

    def load_codings_for_audio_video(self, id_, element):
        """ Load coded segments for audio and video
        Example format:
        <VideoSelection begin="115" modifyingUser="5D2B49D0-9562-4DD3-9EE3-CE2B965E413C" end="1100" guid="BB652E1B-5CCC-4AA3-9C7F-E5D9BD99F6BF"
        creatingUser="5D2B49D0-9562-4DD3-9EE3-CE2B965E413C" creationDateTime="2020-11-10T18:01:23Z" name="(115,0),(1100,0)" modifiedDateTime="2020-11-10T18:01:23Z">
        <Coding guid="2E0A7A4D-453B-4A1B-9784-4FC5B8432816" creatingUser="5D2B49D0-9562-4DD3-9EE3-CE2B965E413C" creationDateTime="2020-11-10T18:01:23Z">
        <CodeRef targetGUID="86392BC1-A364-4904-A406-87A7E025EBF7"/>
        </Coding>
        </VideoSelection>
        """

        seg_start = int(element.get("begin"))
        seg_end = int(element.get("end"))
        memo = element.get("name")
        create_date = element.get("creationDateTime")
        try:
            create_date = create_date.replace('T', ' ')
            create_date = create_date.replace('Z', '')
        except AttributeError as e:
            # None type object ??
            print("load_codings_for_audio_video", e)
            create_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d_%H:%M:%S")

        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']

        cur = self.app.conn.cursor()
        for e in element:
            if e.tag == "{urn:QDA-XML:project:1.0}Coding":
                # Get the code id from the CodeRef guid
                cid = None
                codeRef = e.getchildren()[0]
                for c in self.codes:
                    if c['guid'] == codeRef.get("targetGUID"):
                        cid = c['cid']
                cur.execute("insert into code_av (id,pos0,pos1,cid,memo,\
                    date, owner) values(?,?,?,?,?,?,?)", (id_, seg_start, seg_end,
                    cid, memo, create_date, creating_user))
                self.app.conn.commit()

    def load_pdf_source(self, element):
        """ Load the pdf and text representation into sqlite.
        Can manage internal and absolute source paths.

        Params:
            element: PDFSource element object
        """

        #TODO relative

        name, creating_user, create_date, source_path, path_type = self.name_creating_user_create_date_source_path_helper(element)
        if path_type == "internal":
            # Copy file into .qda documents folder and rename into original name
            destination = self.app.project_path + "/documents/" + name
            try:
                shutil.copyfile(source_path, destination)
                print("PDF IMPORT", source_path, destination)
            except Exception as e:
                self.parent_textEdit.append(_('Cannot copy PDF file from: ') + source_path + "\nto: " + destination + '\n' + str(e))
        if path_type == "absolute":
            media_path = "docs:" + source_path
        if path_type == "relative":
            #TODO check this works
            media_path = "docs:" + self.base_path + source_path
            #print(source_path, media_path)

        """ The PDF source contains a text representation:
        <Representation plainTextPath="internal://142EB46D‐612E‐4593‐A385‐D0E5D04D1288.txt"
        modifyingUser="AD68FBE7‐E1EE‐4A82‐A279‐23CC698C89EB" modifiedDateTime="2018‐03‐27T18:01:07Z"
        creatingUser="AD68FBE7‐E1EE‐4A82‐A279‐23CC698C89EB" creationDateTime="2018‐03‐27T18:01:07Z"
        guid="142EB46D‐612E‐4593‐A385‐D0E5D04D1288" name="Representation_for_Pay de Limónpdf">

        The representation contains text codings:
        <PlainTextSelection startPosition="297" modifyingUser="AD68FBE7‐E1EE‐4A82‐A279‐
        23CC698C89EB" modifiedDateTime="2018‐03‐27T19:11:47Z" creatingUser="AD68FBE7‐E1EE‐4A82‐A279‐
        23CC698C89EB" creationDateTime="2018‐03‐27T19:11:47Z" endPosition="498" guid="95916796‐D0A0‐4B49‐
        80B0‐5A5C8B94AE13" name="favoritos. 2 horas 30 minuto Para la bas...">
        <Coding creatingUser="AD68FBE7‐E1EE‐4A82‐A279‐23CC698C89EB"
        creationDateTime="2018‐03‐27T19:11:47Z" guid="5C931701‐6CD4‐4A2B‐A553‐F1DDE2EAC46D">
        <CodeRef targetGUID="AE6D04CE‐D987‐4FC8‐AF97‐D72CA6FFD08F"/></Coding></PlainTextSelection>
        </Representation>
        """
        for e in element:
            if e.tag == "{urn:QDA-XML:project:1.0}Represenation":
                self.load_text_source(e)

    def load_text_source(self, element):
        """ Load this text source into sqlite.
         Add the description and the text codings.
         When testing with Windows Nvivo export: import from docx or txt
         The text may need an additional line-ending character for Windows \r\n
        Can manage internal and absolute source paths.

        Params:
            element: TextSource element object
         """

        #TODO absolute and relative
        name, creating_user, create_date, source_path, path_type = self.name_creating_user_create_date_source_path_helper(element)

        cur = self.app.conn.cursor()
        # find Description to complete memo
        memo = ""
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = e.text
        source = {'name': name, 'id': -1, 'fulltext': "", 'mediapath': None, 'memo': memo,
                 'owner': self.app.settings['codername'], 'date': create_date}

        # Check plain text file line endings for Windows 2 character \r\n
        add_ending = False
        with open(source_path,"rb") as f:
            while True:
                c = f.read(1)
                if not c or c == b'\n':
                    break
                if c == b'\r':
                    if f.read(1) == b'\n':
                        #print('rn')
                        add_ending = True
                    #print('r')
                    pass
            #print('n')

        # Read the text and enter into sqlite source table
        try:
            with open(source_path, encoding='utf-8', errors='replace') as f:
                fulltext = f.read()
                # Replace fixes mismatched coding with line endings on import from Windows text files.
                # Due to 2 character line endings
                #TODO TEST if importing Windows endings on Windows OS that it requires the 2 char line-ending replacement
                if fulltext is not None and add_ending:
                    fulltext = fulltext.replace('\n', '\n ')
                source['fulltext'] = fulltext
                # logger.debug("type fulltext: " + str(type(entry['fulltext'])))
                cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                    (name, fulltext, source['mediapath'], memo, creating_user, create_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                id_ = cur.fetchone()[0]
                source['id'] = id_
                self.sources.append(source)
        except Exception as e:
            self.parent_textEdit.append(_("Cannot read from TextSource: ") + source_path + "\n" + str(e))

        if path_type == "internal":
            # Copy file into .qda documents folder and rename into original name
            destination = self.app.project_path + "/documents/" + name + '.' + source_path.split('.')[-1]
            try:
                shutil.copyfile(source_path, destination)
            except Exception as e:
                self.parent_textEdit.append(_('Cannot copy TextSource file from: ') + source_path + "\nto: " + destination + '\n' + str(e))

        # Parse forPlainTextSelection elements for Coding elements and VariableValues
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}PlainTextSelection":
                self._load_codings_for_text(source, e)
            if e.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(e, id_, creating_user)

    def parse_variable_value(self, element, id_, creating_user):
        """ Parse VariableValue element.
        Needs two parses - one to get the variable name and one to get the value.
        Enter details into attributes table.
        Called from load_picture_source, load_text_source, load_audio_source, load_video_source

        Params:
            element : VariableValue xml element object
            id_ : File id of source, Integer
            creating_user : The user who created this source, String
        """

        value_types = ["{urn:QDA-XML:project:1.0}IntegerValue", "{urn:QDA-XML:project:1.0}TextValue",
                "{urn:QDA-XML:project:1.0}DateValue", "{urn:QDA-XML:project:1.0}FloatValue",
                "{urn:QDA-XML:project:1.0}DateTimeValue", "{urn:QDA-XML:project:1.0}BooleanValue"]

        var_name = ""
        value = ""
        for var_el in element.getchildren():
            if var_el.tag == "{urn:QDA-XML:project:1.0}VariableRef":
                guid = var_el.get("targetGUID")
                for v in self.variables:
                    if v['guid'] == guid:
                        var_name = v['name']
                        break
        # Need to parse the element children twice, otherwise may miss the needed element
        for var_el in element.getchildren():
            if var_el.tag in value_types and var_el.text is not None:
                value = var_el.text
                value = value.strip()
        # print("varname:", var_name, " value:",value)
        cur = self.app.conn.cursor()
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file',?,?,?,?)"
        placeholders = [var_name, value, id_, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), creating_user]
        cur.execute(insert_sql, placeholders)
        self.app.conn.commit()

    def _load_codings_for_text(self, source, element):
        """ These are PlainTextSelection elements.
        These elements contain a Coding element and a Description element.
        The Description element is treated as an Annotation.

        Some Coding guids withh match a Case guid. This is Case text.

        Example format:
        < PlainTextSelection guid = "08cbced0-d736-44c8-8fd6-eb4d29fe46c5" name = "" startPosition = "1967"
        endPosition = "2207" creatingUser = "5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime = "2019-06-07T03:36:36Z"
        modifyingUser = "5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime = "2019-06-07T03:36:36Z" >
        < Description / >
        < Coding guid = "76414714-63c4-4a25-a47e-66fef80bd52e" creatingUser = "5c94bc9e-db8c-4f1d-9cd6-e900c7440860"
        creationDateTime = "2019-06-06T06:27:01Z" >
        < CodeRef targetGUID = "2dfba8c9-59f5-4424-99d6-ea9bce18134b" / >
        < / Coding >
        < / PlainTextSelection >

        :param entry - the source text dictionary
        :param element - the PlainTextSelection element
        """

        cur = self.app.conn.cursor()
        pos0 = int(element.get("startPosition"))
        pos1 = int(element.get("endPosition"))
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        seltext = source['fulltext'][pos0:pos1]
        for e in element:
            # Treat description text as an annotation
            if e.tag == "{urn:QDA-XML:project:1.0}Description" and e.text is not None:
                cur.execute("insert into annotation (fid,pos0, pos1,memo,owner,date) \
                values(?,?,?,?,?,?)" ,(source['id'], pos0, pos1,
                e.text, creating_user, create_date))
                self.app.conn.commit()
            if e.tag == "{urn:QDA-XML:project:1.0}Coding":
                memo = ""
                #TODO can coded text be memoed?
                # Get the code id from the CodeRef guid
                cid = None
                codeRef = e.getchildren()[0]
                for c in self.codes:
                    if c['guid'] == codeRef.get("targetGUID"):
                        cid = c['cid']
                cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                    memo,date) values(?,?,?,?,?,?,?,?)", (cid, source['id'],
                    seltext, pos0, pos1, creating_user, memo, create_date))
                self.app.conn.commit()

    def parse_notes(self, element):
        """ Parse the Notes element.
        Notes are possibly journal entries.
        Example format:
        <Note guid="4691a8a0-d67c-4dcc-91d6-e9075dc230cc" name="Assignment Progress Memo" richTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.docx" plainTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.txt" creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime="2019-06-04T06:11:56Z" modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime="2019-06-17T08:00:58Z">
        <Description>Steps towards completing the assignment</Description>
        </Note>

        :param element Notes

        : return count of Notes
        """

        cur = self.app.conn.cursor()
        count = 0
        for e in element.getchildren():
            #print(e.tag, e.get("name"), e.get("plainTextPath"))
            name = e.get("name")
            create_date = e.get("creationDateTime")
            create_date = create_date.replace('T', ' ')
            create_date = create_date.replace('Z', '')
            creating_user_guid = e.get("creatingUser")
            creating_user = "default"
            for u in self.users:
                if u['guid'] == creating_user_guid:
                    creating_user = u['name']
            # paths starts with internal://
            path = e.get("plainTextPath").split('internal:/')[1]
            path = self.folder_name + '/Sources' + path
            #print(path)
            jentry = ""
            try:
                with open(path) as f:
                    jentry = f.read()
            except Exception as e:
                self.parent_textEdit.append(_('Trying to read Note element: ') + path + '\n'+ str(e))
            cur.execute("insert into journal(name,jentry,owner,date) values(?,?,?,?)",
            (name, jentry, creating_user, create_date))
            self.app.conn.commit()
            count += 1
        return count

    def parse_project_description(self, element):
        """ Parse the Description element
        This might be an overall project description, at the end of the xml.
        Example format:
        <Description guid="4691a8a0-d67c-4dcc-91d6-e9075dc230cc" >
        </Description>

        :param element Description
        """

        memo = element.text
        if memo is None:
            memo = ""
        cur = self.app.conn.cursor()
        cur.execute("update project set memo = ?", (memo, ))
        self.app.conn.commit()

    def parse_project_tag(self, element):
        """ Parse the Project tag.
        Interested in basePath for relative linked sources. """

        self.base_path = element.get("basePath")
        print("BASEPATH ", self.base_path, type(self.base_path))  # tmp

    def parse_users(self, element):
        """ Parse Users element children, fill list with guid and name.
        There is no user table in QualCoder sqlite.
        Store each user in dictionary with name and guid.
        :param Users element

        :return count of users
        """

        count = 0
        for e in element.getchildren():
            #print(e.tag, e.get("name"), e.get("guid"))
            self.users.append({"name": e.get("name"), "guid": e.get("guid")})
            count += 1
        return count

    def xml_validation(self, xsd_type="codebook"):
        """ Verify that the XML complies with XSD
        Arguments:
            1. file_xml: Input xml file
            2. file_xsd: xsd file which needs to be validated against xml

        :param xsd_type codebook or project

        :return true or false passing validation
        """

        file_xsd = codebook
        if xsd_type != "codebook":
            file_xsd = project
        try:
            xml_doc = etree.fromstring(bytes(self.xml, "utf-8"))
            xsd_doc = etree.fromstring(bytes(file_xsd, "utf-8"))
            xmlschema = etree.XMLSchema(xsd_doc)
            xmlschema.assert_(xml_doc)
            return True
        except etree.XMLSyntaxError as err:
            print("PARSING ERROR:{0}".format(err))
            return False

        except AssertionError as err:
            print("Incorrect XML schema: {0}".format(err))
            return False


class Refi_export(QtWidgets.QDialog):
    """ Create Rotterdam Exchange Format Initiative (refi) xml documents for
    codebook.xml and project.xml
    NOTES:
    https://stackoverflow.com/questions/299588/validating-with-an-xml-schema-in-python
    http://infohost.nmt.edu/tcc/help/pubs/pylxml/web/index.html
    """

    categories = []
    codes = []
    users = []
    sources = []
    guids = []
    note_files = []  # contains guid.txt name and note text
    variables = []  # contains dictionary of variable xml, guid, name
    xml = ""
    parent_textEdit = None
    app = None
    tree = None
    export_type = ""

    def __init__(self, app, parent_textEdit, export_type):
        """  """

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.export_type = export_type
        self.xml = ""
        self.get_categories()
        self.get_codes()
        self.get_users()
        self.get_sources()
        if self.export_type == "codebook":
            self.codebook_exchange_xml()
            self.xml_validation("codebook")
            self.export_codebook()
        if self.export_type == "project":
            self.project_xml()
            self.xml_validation("project")
            self.export_project()

    def export_project(self):
        """ Create a REFI-QDA project folder project.qdpx zipfile
        This contains the .qde project xml and a Sources folder.

        Source types:
        Plain text, PDF,md, odt, docx, md, epub
        Images must be jpeg or png
        mp3, ogg, mp4, mov, wav

        Create an unzipped folder with a /Sources folder and project.qde xml document
        Then create zip wih suffix .qdpx
        """

        project_name = self.app.project_name[:-4]
        prep_path = os.path.expanduser('~') + '/.qualcoder/' + project_name
        try:
            shutil.rmtree(prep_path)
        except FileNotFoundError as e:
            pass
        try:
            os.mkdir(prep_path)
            os.mkdir(prep_path + "/Sources")
        except Exception as e:
            logger.error(_("Project export error ") + str(e))
            Message(self.app, _("Project"), _("Project not exported. Exiting. ") + str(e), "warning").exec_()
            return
        try:
            with open(prep_path +'/project.qde', 'w', encoding="utf-8-sig") as f:
                f.write(self.xml)
        except Exception as e:
            Message(self.app,_("Project"), _("Project not exported. Exiting. ") + str(e), "warning").exec_()
            logger.debug(str(e))
            return
        txt_errors = ""
        for s in self.sources:
            #print(s['id'], s['name'], s['mediapath'], s['filename'], s['plaintext_filename'], s['external'])
            destination = '/Sources/' + s['filename']
            if s['mediapath'] is not None and s['external'] is None:
                    try:
                        if s['external'] is None:
                            shutil.copyfile(self.app.project_path + s['mediapath'],
                                prep_path + destination)
                        else:
                            shutil.copyfile(self.app.project_path + s['mediapath'],
                                self.app.settings['directory'] + '/' + s['filename'])
                    except FileNotFoundError as e:
                        txt_errors += "Error in media export: " + s['filename'] + "\n" + str(e)
                        print("ERROR in refi.export_project. media export: " + s['filename'])
                        print(e)
            if s['mediapath'] is None:  # an internal document
                try:
                    shutil.copyfile(self.app.project_path + '/documents/' + s['name'],
                        prep_path + destination)
                except FileNotFoundError as e:
                    with open(prep_path + destination, 'w', encoding="utf-8-sig") as f:
                        f.write(s['fulltext'])
            # Also need to export a plain text file as a source
            # plaintext has different guid from richtext, and also might be associated with media - eg transcripts
            if s['plaintext_filename'] is not None:
                with open(prep_path + '/Sources/' + s['plaintext_filename'], "w", encoding="utf-8-sig") as f:
                    try:
                        f.write(s['fulltext'])
                    except Exception as e:
                        txt_errors += '\nIn plaintext file export: ' + s['plaintext_filename'] + "\n" + str(e)
                        logger.error(str(e) + '\nIn plaintext file export: ' + s['plaintext_filename'])
                        print(e)

        for notefile in self.note_files:
            with open(prep_path + '/Sources/' + notefile[0], "w", encoding="utf-8-sig") as f:
                f.write(notefile[1])

        export_path = self.app.project_path[:-4]
        shutil.make_archive(prep_path, 'zip', prep_path)
        os.rename(prep_path + ".zip", prep_path + ".qdpx")
        shutil.copyfile(prep_path + ".qdpx", export_path + ".qdpx")
        try:
            shutil.rmtree(prep_path)
            os.remove(prep_path + ".qdpx")
        except FileNotFoundError as e:
            logger.debug(str(e))
        msg = export_path + ".qpdx\n"
        msg += "This project exchange is not guaranteed compliant with the exchange standard.\n"
        msg += "REFI-QDA EXPERIMENTAL FUNCTION."
        if txt_errors != "":
            msg += "\nErrors: "
            msg += txt_errors
        Message(self.app, _("Project exported"), _(msg)).exec_()
        self.parent_textEdit.append(_("Project exported") + "\n" + _(msg))

    def export_codebook(self):
        """ Export REFI format codebook. """

        filename = "Codebook-" + self.app.project_name[:-4] + ".qdc"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.settings['directory'], options)
        if directory == "":
            return
        filename = directory + "/" + filename
        try:
            f = open(filename, 'w')
            f.write(self.xml)
            f.close()
            msg = "Codebook has been exported to "
            msg += filename
            Message(self.app, _("Codebook exported"), _(msg)).exec_()
            self.parent_textEdit.append(_("Codebook exported") +"\n" + _(msg))
        except Exception as e:
            logger.debug(str(e))
            Message(self.app, _("Codebook NOT exported"), str(e)).exec_()
            self.parent_textEdit.append(_("Codebook NOTexported") + "\n" + _(msg))

    def user_guid(self, username):
        """ Requires a username. returns matching guid """
        for u in self.users:
            if u['name'] == username:
                return u['guid']
        return ""

    def code_guid(self, code_id):
        """ Requires a code id. returns matching guid """
        for c in self.codes:
            if c['cid'] == code_id:
                return c['guid']
        return ""

    def project_xml(self):
        """ Creates the xml for the .qde file.
        External files will be exported using absolute path
        So base path for external sources is not required.
        ? PDFSources ?
        No sets, No graphs.
        """

        self.xml = '<?xml version="1.0" encoding="utf-8"?>\n'
        self.xml += '<Project '
        self.xml += 'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        self.xml += 'name="' + self.app.project_name + '" '
        self.xml += 'origin="' + self.app.version + '" '
        # There is no creating user in QualCoder
        guid = self.create_guid()
        self.xml += 'creatingUserGUID="' + guid + '" '
        cur = self.app.conn.cursor()
        cur.execute("select date from project")
        result = cur.fetchone()
        self.xml += 'creationDateTime="' + self.convert_timestamp(result[0]) + '" '
        #self.xml += 'basePath="' + self.app.settings['directory'] + '" '
        self.xml += 'xmlns="urn:QDA-XML:project:1.0"'
        self.xml += '>\n'
        # add users
        self.xml += "<Users>\n"
        for row in self.users:
            self.xml += '<User guid="' + row['guid'] + '" name="' + row['name'] + '" />\n'
        self.xml += "</Users>\n"
        self.xml += self.codebook_xml()
        self.xml += self.variables_xml()
        self.xml += self.cases_xml()
        self.xml += self.sources_xml()
        self.xml += self.notes_xml()
        self.xml += self.project_description_xml()
        self.xml += '</Project>'

    def variables_xml(self):
        """ Variables are associated with Sources and Cases.
        Stores a list of the variables with guids for later use.
        Called by project_xml

        :returns xml string
        """

        self.variables = []
        xml = ""
        cur = self.app.conn.cursor()
        cur.execute("select name, memo, caseOrFile,valuetype from attribute_type")
        results = cur.fetchall()
        if results == []:
            return xml
        xml = '<Variables>\n'
        for r in results:
            guid = self.create_guid()
            xml += '<Variable guid="' + guid + '" '
            xml += 'name="' + r[0] + '" '
            xml += 'typeOfVariable="'
            # Only two variable options in QualCoder
            if r[3] == 'numeric':
                xml += 'Float" '
            else:
                xml += 'Text" '
            xml += '>\n'
            # Add variable memo in description
            if r[1] == "" or r[1] is None:
                xml += '<Description />\n'
            else:
                xml += '<Description>' + r[1] + '</Description>\n'
            xml += '</Variable>\n'
            self.variables.append({'guid': guid, 'name': r[0], 'caseOrFile': r[2], 'type': r[3]})
        xml += '</Variables>\n'
        return xml

    def project_description_xml(self):
        """
        :returns xml string of project description
        """

        cur = self.app.conn.cursor()
        cur.execute("select memo from project")
        results = cur.fetchall()
        if results == []:  # this should not happen
            return '<Description />\n'
        memo = str(results[0][0])  # could be None
        xml = '<Description>' + memo + '</Description>\n'
        return xml

    def create_note_xml(self, journal):  #guid, text, user, datetime, name=""):
        """ Create a Note xml for journal entries
        Appends xml in notes list.
        Appends file name and journal text in notes_files list. This is exported to Sources folder.
        Called by: notes_xml
        Format:
        <Note guid="4691a8a0-d67c-4dcc-91d6-e9075dc230cc" name="Assignment Progress Memo" richTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.docx" plainTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.txt" creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime="2019-06-04T06:11:56Z" modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime="2019-06-17T08:00:58Z">
       <Description></Description>
       </Note>

        :param guid
        :param the text of the journal entry
        :param user is the user who created the entry
        :param datetime is the creation datetime of the entry
        :param name is the name of the journal entry

        :returns a guid for a NoteRef
        """

        guid = self.create_guid()
        xml = '<Note guid="' + guid + '" '
        xml += 'creatingUser="' + self.user_guid(journal[3]) + '" '
        xml += 'creationDateTime="' + self.convert_timestamp(journal[2]) + '" '
        xml += 'name="' + journal[0] + '" '
        xml += ' plainTextPath="internal://' + guid + '.txt" '
        xml += '>\n'
        #xml += '<PlainTextContent>' + text + '</PlainTextContent>\n'
        # Add blank Description tag for the journal entry, as these are not memoed
        xml += '<Description />'
        xml += '</Note>\n'
        self.note_files.append([guid + '.txt', journal[1]])
        return xml

    def notes_xml(self):
        """ Get journal entries and store them as Notes.
        Collate note_xml list into final xml
        <Notes><Note></Note></Notes>
        Note xml requires a NoteRef in the source or case.
        Called by: project_xml

        :returns xml
        """

        self.note_files = []
        # Get journal entries
        cur = self.app.conn.cursor()
        sql = "select name, jentry, date, owner from journal where jentry is not null"
        cur.execute(sql)
        j_results = cur.fetchall()
        if j_results == []:
            return ''
        xml = '<Notes>\n'
        for j in j_results:
            xml += self.create_note_xml(j)
        xml += '</Notes>\n'
        return xml

    def cases_xml(self):
        """ Create xml for cases.
        Put case memo into description tag.
        Called by: project_xml
        returns xml """

        xml = ''
        cur = self.app.conn.cursor()
        cur.execute("select caseid, name, memo, owner, date from cases")
        result = cur.fetchall()
        if result == []:
            return xml
        xml = '<Cases>\n'
        for r in result:
            xml += '<Case guid="' + self.create_guid() + '" '
            xml += 'name="' + r[1] + '">\n'
            if r[2] != "":
                xml += '<Description>' + r[2] + '</Description>\n'
            if r[2] == "":
                xml += '<Description />\n'
            xml += self.case_variables_xml(r[0])
            xml += self.case_source_ref_xml(r[0])
            xml += '</Case>\n'
        xml += '</Cases>\n'
        return xml

    def case_variables_xml(self, caseid):
        """ Get the variables, name, type and value for this case and create xml.
        Case variables are stored like this:
        <VariableValue>
        <VariableRef targetGUID="51dc3bcd-5454-47ff-a4d6-ea699144410d" />
        <TextValue>20-29</TextValue>
        </VariableValue>

        :param caseid integer

        :returns xml string for case variables
        """

        xml = ""
        cur = self.app.conn.cursor()
        sql = "select attribute.name, value from attribute where attr_type='case' and id=?"
        cur.execute(sql, (caseid, ))
        attributes = cur.fetchall()
        for a in attributes:
            xml += '<VariableValue>\n'
            guid = ''
            var_type = 'character'
            for v in self.variables:
                if v['name'] == a[0]:
                    guid = v['guid']
                    var_type == v['type']
            xml += '<VariableRef targetGUID="' + guid + '" />\n'
            if var_type == 'numeric':
                xml += '<FloatValue>' + a[1] + '</FloatValue>\n'
            if var_type == 'character':
                xml += '<TextValue>' + a[1] + '</TextValue>\n'
            xml += '</VariableValue>\n'
        return xml

    def case_source_ref_xml(self, caseid):
        """ Find sources linked to this case, pos0 and pos1 must equal zero.
        Called by: cases_xml

        :param caseid integer

        :returns xml string
        """

        xml = ''
        cur = self.app.conn.cursor()
        cur.execute("select fid, owner, date from case_text where caseid=? and pos0=0 and pos1=0", [caseid,])
        result = cur.fetchall()
        if result == []:
            return xml
        for row in result:
            for s in self.sources:
                if s['id'] == row[0]:
                    # put xml creation here, in case a source id does not match up
                    xml += '<SourceRef targetGUID="'
                    xml += s['guid']
                    xml += '"/>\n'
        return xml

    def source_variables_xml(self, sourceid):
        """ Get the variables, name, type and value for this source and create xml.
        Source variables are stored like this:
        <VariableValue>
        <VariableRef targetGUID="51dc3bcd-5454-47ff-a4d6-ea699144410d" />
        <TextValue>20-29</TextValue>
        </VariableValue>

        :param caseid integer

        :returns xml string for case variables
        """

        xml = ""
        cur = self.app.conn.cursor()
        sql = "select attribute.name, value from attribute where attr_type='file' and id=?"
        cur.execute(sql, (sourceid, ))
        attributes = cur.fetchall()
        for a in attributes:
            xml += '<VariableValue>\n'
            guid = ''
            var_type = 'character'
            for v in self.variables:
                if v['name'] == a[0]:
                    guid = v['guid']
                    var_type == v['type']
            xml += '<VariableRef targetGUID="' + guid + '" />\n'
            if var_type == 'numeric':
                xml += '<FloatValue>' + a[1] + '</FloatValue>\n'
            if var_type == 'character':
                xml += '<TextValue>' + a[1] + '</TextValue>\n'
            xml += '</VariableValue>\n'
        return xml

    def sources_xml(self):
        """ Create xml for sources: text, pictures, pdf, audio, video.
         Also add selections to each source.

        Audio and video source file size:
        The maximum size in bytes allowed for an internal file is 2,147,483,647 bytes (2^31−1 bytes, or 2 GiB
        minus 1 byte). An exporting application must detect file size limit during export and inform the
        user.

        Internal files are identified in the path attribute of the source element by the
        URL naming scheme internal:// /Sources folder
        plainTextPath="internal://8e7fddfe‐db36‐48dc‐b464‐80c3a4decd90.txt"
        richTextPath="internal://6f35c6f2‐bd8f‐4f08‐ad49‐6d62cb8442a5.docx" >

        path="internal://361bcdb8‐7d11‐4343‐a4cd‐4130693eff76.png"

        currentPath="absolute://E:/Data/David/Video/Transana/Images/ch130214.gif" >

        External files are identified in the path attribute of the source element by the URL
        They can be relative to the basePath of the project
        path="relative:///DF370983‐F009‐4D47‐8615‐711633FA9DE6.m4a"
        basePath='//PROJECT/Sources'

        Or they can be Absolute paths - USE THIS APPROACH AS EASIER TO MANAGE
        path="absolute:///hiome/username/Documents/DF370983‐F009‐4D47‐8615‐711633FA9DE6.m4a"

        Audio and video source file size:
        The maximum size in bytes allowed for an internal file is 2,147,483,647 bytes (2^31−1 bytes, or 2 GiB
        minus 1 byte). An exporting application must detect file size limit during export and inform the
        user.

        Need to replace xml special characters in filenames
        e.g. & to &#038;

        Source types:
        Plain text, PDF
        Images must be jpeg or png

        Create an unzipped folder with a /Sources folder and project.qde xml document
        Then create zip wih suffix .qdpx

        Called by: project_xml

        :returns xml String
        """

        xml = "<Sources>\n"
        for s in self.sources:
            guid = self.create_guid()
            # Text document
            if (s['mediapath'] is None and (s['name'][-4:].lower() != '.pdf' and s['name'][-12:] != '.transcribed')) or \
                (s['mediapath'] is not None and s['mediapath'][0:5] == 'docs:' and (s['name'][-4:].lower() != '.pdf' or s['name'][-12:] != '.transcribed')):
                xml += '<TextSource '
                if s['external'] is None:
                    xml += 'richTextPath="internal://' + s['filename'].replace('&', '&#038;') + '" '
                else:
                    xml += 'richTextPath="absolute://' + s['external'].replace('&', '&#038;') + '" '
                xml += 'plainTextPath="internal://' + s['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'].replace('&', '&#038;') + '">\n'
                if s['memo'] != '' and s['memo'] is not None:
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.text_selection_xml(s['id'])
                xml += self.source_variables_xml(s['id'])
                xml += '</TextSource>\n'
            # PDF document
            if (s['mediapath'] is None and s['name'][-4:].lower() == '.pdf') or \
                (s['mediapath'] is not None and s['mediapath'][0:5] == 'docs:' and s['name'][-4:].lower() == '.pdf') :
                xml += '<PDFSource '
                if s['external'] is None:
                    xml += 'path="internal://' + s['filename'] + '" '
                else:
                    xml += 'path="absolute://' + s['external'].replace('&', '&#038;') + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'].replace('&', '&#038;') + '">\n'
                if s['memo'] != '' and s['memo'] is not None:
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += '<Representation guid="' + self.create_guid() + '" '
                xml += 'plainTextPath="internal://' + s['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'name="' + s['name'] + '">\n'
                xml += self.text_selection_xml(s['id'])
                xml += '</Representation>'
                xml += self.source_variables_xml(s['id'])
                xml += '</PDFSource>\n'
            # Images
            if s['mediapath'] is not None and s['mediapath'][0:7] in ('/images', 'images:'):
                xml += '<PictureSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                if s['external'] is None:
                    xml += 'path="internal://' + s['filename'] + '" '
                else:
                    xml += 'path="absolute://' + s['external'].replace('&', '&#038;') + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'].replace('&', '&#038;') + '" >\n'
                if s['memo'] != '' and s['memo'] is not None:
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.picture_selection_xml(s['id'])
                xml += self.source_variables_xml(s['id'])
                xml += '</PictureSource>\n'
            # Audio
            if s['mediapath'] is not None and s['mediapath'][0:6] in ('/audio', 'audio:'):
                xml += '<AudioSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                if s['external'] is None:
                    xml += 'path="internal://' + s['filename'] + '" '
                else:
                    xml += 'path="absolute://' + s['external'].replace('&', '&#038;') + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'].replace('&', '&#038;') + '" >\n'
                if s['memo'] != '' and s['memo'] is not None:
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.transcript_xml(s)
                xml += self.av_selection_xml(s['id'], 'Audio')
                xml += self.source_variables_xml(s['id'])
                xml += '</AudioSource>\n'
            # Video
            if s['mediapath'] is not None and s['mediapath'][0:6] in ('/video', 'video:'):
                xml += '<VideoSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                if s['external'] is None:
                    xml += 'path="internal://' + s['filename'] + '" '
                else:
                    xml +='path="absolute://' + s['external'].replace('&', '&#038;') + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'].replace('&', '&#038;') + '" >\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.transcript_xml(s)
                xml += self.av_selection_xml(s['id'], 'Video')
                xml += self.source_variables_xml(s['id'])
                xml += '</VideoSource>\n'
        xml += "</Sources>\n"
        return xml

    def text_selection_xml(self, id_):
        """ Get and complete text selection xml.
        xml is in form:
        <PlainTextSelection><Coding><CodeRef/></Coding></PlainTextSelection>
        Called by: sources_xml

        :param id_ file id integer

        :returns xml string
        """

        xml = ""
        sql = "select cid, seltext, pos0, pos1, owner, date from code_text "
        sql += "where fid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [id_, ])
        results = cur.fetchall()
        for r in results:
            xml += '<PlainTextSelection guid="' + self.create_guid() + '" '
            xml += 'startPosition="' + str(r[2]) + '" '
            xml += 'endPosition="' + str(r[3]) + '" '
            # Ampersands may cause parsing problems
            xml += 'name="' + str(r[1]).replace('&', '&#038;') + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" '
            xml += 'creationDateTime="' + self.convert_timestamp(r[5]) + '">\n'
            xml += '<Coding guid="' + self.create_guid() + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" >'
            xml += '<CodeRef targetGUID="' + self.code_guid(r[0]) + '" />\n'
            xml += '</Coding>\n'
            xml += '</PlainTextSelection>\n'
        return xml

    def picture_selection_xml(self, id_):
        """ Get and complete picture selection xml.
        Called by: sources_xml

        :param id_ is the source id

        :returns xml string
        """

        xml = ""
        sql = "select imid, cid, x1,y1, width, height, owner, date, memo from code_image "
        sql += "where id=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [id_, ])
        results = cur.fetchall()
        for r in results:
            xml += '<PictureSelection guid="' + self.create_guid() + '" '
            xml += 'firstX="' + str(int(r[2])) + '" '
            xml += 'firstY="' + str(int(r[3])) + '" '
            xml += 'secondX="' + str(int(r[2] + r[4])) + '" '
            xml += 'secondY="' + str(int(r[3] + r[5])) + '" '
            xml += 'name="' + str(r[8]) + '" '
            xml += 'creatingUser="' + self.user_guid(r[6]) + '" '
            xml += 'creationDateTime="' + self.convert_timestamp(r[7]) + '">\n'
            xml += '<Coding guid="' + self.create_guid() + '" '
            xml += 'creatingUser="' + self.user_guid(r[6]) + '" >'
            xml += '<CodeRef targetGUID="' + self.code_guid(r[1]) + '"/>\n'
            xml += '</Coding>\n'
            xml += '</PictureSelection>\n'
        return xml

    def av_selection_xml(self, id_, mediatype):
        """ Get codings and complete av selection xml.
        Called by: sources_xml.
        Video Format:
        <VideoSelection end="17706" modifyingUser="AD68FBE7‐E1EE‐4A82‐A279‐23CC698C89EB"
        begin="14706" creatingUser="AD68FBE7‐E1EE‐4A82‐A279‐23CC698C89EB" creationDateTime="2018‐03‐
        27T19:34:32Z" modifiedDateTime="2018‐03‐27T19:34:55Z" guid="0EF270BA‐47AD‐4107‐B78F‐7697362BCA44"
        name="00:14.70 – 00:17.70">
        <Coding creatingUser="AD68FBE7‐E1EE‐4A82‐A279‐23CC698C89EB"
        creationDateTime="2018‐03‐27T19:36:01Z" guid="04EBEC7D‐EAB4‐43FC‐8167‐ADB14F921143">
        <CodeRef targetGUID="9F43FE32‐C2CB‐4BA8‐B766‐A0734C826E49"/>
        </Coding>
        </VideoSelection>

        :param id_ is the source id

        :returns xml string
        """

        xml = ""
        sql = "select avid, cid, pos0, pos1, owner, date, memo from code_av "
        sql += "where id=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [id_, ])
        results = cur.fetchall()
        for r in results:
            xml += '<' + mediatype + 'Selection guid="' + self.create_guid() + '" '
            xml += 'begin="' + str(int(r[2])) + '" '
            xml += 'end="' + str(int(r[3])) + '" '
            xml += 'name="' + str(r[6]) + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" >'
            xml += '<Coding guid="' + self.create_guid() + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" '
            xml += 'creationDateTime="' + self.convert_timestamp(r[5]) + '">\n'
            xml += '<CodeRef targetGUID="' + self.code_guid(r[1]) + '"/>\n'
            xml += '</Coding>\n'
            xml += '</' + mediatype + 'Selection>\n'
        return xml

    def transcript_xml(self, source):
        """ Find any transcript of media source.
        Need to add timestamp synchpoints.
        Replace & xml char with &#038;

        Called by: sources_xml

        :param source  is this media source dictionary.

        :returns xml string
        """

        xml = ""
        for t in self.sources:
            if t['name'] == source['name'] + '.transcribed':
                xml = '<Transcript plainTextPath="internal://' + t['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(t['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(t['date']) + '" '
                xml += 'guid="' + self.create_guid() + '" '
                xml += 'name="' + t['name'].replace('&', '&#038;') + '" >\n'
                # Get and add xml for syncpoints
                sync_list = self.get_transcript_syncpoints(t)
                for s in sync_list:
                    xml += s[1]
                xml += self.get_transcript_selections(t, sync_list)
                xml += '</Transcript>\n'
                break
        return xml

    def get_transcript_selections(self, media, sync_list):
        """ Add transcript selections with syncpoints.
        Cannot accurately match the millisecond transcript selections used here as the
        syncpoint msecs are calculated from transcript textual timestamps.
        Start end character text positions are accurate.

        Format:
        <TranscriptSelection guid="ecdbd559‐e5d2‐45b4‐bb60‐54e2530de054" name="English Clip 1"
        fromSyncPoint="d7c91d8c‐77f6‐4058‐b21e‐010a157ba027" toSyncPoint="01809d1d‐40a9‐4941‐8685‐c5eafa9de319">
        <Description>English Clip Comment 1</Description>
        <Coding guid="f1d221e5‐fa3a‐4b9a‐865c‐7712cd428c62">
        <CodeRef targetGUID="d342cd5e‐52d1‐4894‐a342‐7d42ed947797" />
        </Coding>
        <Coding
        guid="ee856ef0‐6296‐4fd3‐8e5a‐5e3d202a145c">
        <CodeRef targetGUID="0bd904ef‐7dff‐47d6‐a94e‐f47e9134a596" />
        </Coding>
        </TranscriptSelection>

        :param media dictionary containing id, name, owner, date, fulltext, memo, mediapath

        :param sync_list  list of guid, xml and char positions

        :return: xml for transcript selections
        """

        xml = ''
        sql = "select pos0,pos1,cid,owner, date, memo from code_text where fid=? order by pos0"
        cur = self.app.conn.cursor()
        cur.execute(sql, [media['id'], ])
        results = cur.fetchall()
        for coded in results:
            #print(coded)
            xml += '<TranscriptSelection guid="' + self.create_guid() + '" '
            xml += 'name="' + media['name'] + '" '
            xml += 'fromSyncPoint="'
            for sp in sync_list:
                if sp[2] == coded[0]:
                    xml += sp[0]
            xml += '" toSyncPoint="'
            doubleup = False
            for sp in sync_list:
                if sp[2] == coded[1] and doubleup is False:
                    xml += sp[0]
                    doubleup = True
            xml += '">\n'
            xml += '<Coding guid="' + self.create_guid() + '" >\n'
            xml += '<CodeRef targetGUID="' + self.code_guid(coded[2]) + '" />\n'
            xml += '</Coding>\n'
            xml += '</TranscriptSelection>\n'
        return xml

    def get_transcript_syncpoints(self, media):
        """
        Need to get all the transcription codings, start, end positions, code, coder.
        For each of these and create a syncpoint.
        Look through sll the textual timepoints to find the closest needed to create the syncpoints.
        The milliseconds syncs will be approximate only, based on the start and end media milliseconds and any
        in-text detected timestamps.

        :param media dictionary containing id, name, owner, date, fulltext, memo, mediapath

        :return: list containing guid, syncpoint xml, character position
        """

        tps = self.get_transcript_timepoints(media)  # ordered list of charpos, msecs
        #print("TIME POINTS", len(tps))
        #print(tps)

        sql = "select pos0,pos1,cid,owner, date, memo from code_text where fid=? order by pos0"
        cur = self.app.conn.cursor()
        cur.execute(sql, [media['id'], ])
        results = cur.fetchall()
        sync_list = []
        # starting syncpoint
        guid = self.create_guid()
        xml = '<SyncPoint guid="' + guid + '" position="0" timeStamp="0" />\n'
        sync_list.append([guid, xml, 0])

        for r in results:
            # text start position
            guid = self.create_guid()
            msecs = 0
            for t in tps:
                if t[0] <= r[0]:
                    msecs = t[1]
            xml = '<SyncPoint guid="' + guid + '" position="' + str(r[0]) + '" '
            xml += 'timeStamp="' + str(msecs) + '" />\n'
            sync_list.append([guid, xml, r[0]])
            # text end position
            msecs = 0
            for t in tps:
                if t[0] <= r[1]:
                    msecs = t[1]
            if msecs == 0:
                msecs = tps[-1][1]  # the media end
            guid = self.create_guid()
            xml = '<SyncPoint guid="' + guid + '" position="' + str(r[1]) + '" '
            xml += 'timeStamp="' + str(msecs) + '" />\n'
            sync_list.append([guid, xml, r[1]])

        #TODO might have multiples of the same char position and msecs, trim back?
        #print("SYNC_LIST", len(sync_list))
        #print(sync_list)  # tmp
        return sync_list

    def get_transcript_timepoints(self, media):
        """ Get a list of starting/ending character positions and time in milliseconds
        from transcribed text file.

        Example formats:  [00:34:12] [45:33] [01.23.45] [02.34] #00:12:34.567#
        09:33:04,100 --> 09:33:09,600

        Converts hh mm ss to milliseconds with text positions for xml SyncPoint
        Format:
        <SyncPoint guid="c32d0ae1‐7f16‐4bbe‐93a1‐537e2dc0fb66"
        position="94" timeStamp="45000" />

        :param text string

        :return list of time points as [character position, milliseconds]
        """

        text = media['fulltext']

        if len(text) == 0 or text is None:
            return []

        mmss1 = "\[[0-9]?[0-9]:[0-9][0-9]\]"
        hhmmss1 = "\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = "\[[0-9]?[0-9]\.[0-9][0-9]\]"
        hhmmss2 = "\[[0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\]"
        hhmmss_sss = "#[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]{1,3}#"  # allow for 1 to 3 msecs digits
        srt = "[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]\s-->\s[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]"

        time_pos = [[0, 0]]
        for match in re.finditer(mmss1, text):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000

                time_pos.append([match.span()[0], msecs])
            except:
                pass
        for match in re.finditer(hhmmss1, text):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                time_pos.append([match.span()[0], msecs])
            except:
                pass
        for match in re.finditer(mmss2, text):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                time_pos.append([match.span()[0], msecs])
            except:
                pass
        for match in re.finditer(hhmmss2, text):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                time_pos.append([match.span()[0], msecs])
            except:
                pass
        for match in re.finditer(hhmmss_sss, text):
            # Format #00:12:34.567#
            stamp = match.group()[1:-1]
            text_hms = stamp.split(':')
            text_secs = text_hms[2].split('.')[0]
            text_msecs = text_hms[2].split('.')[1]
            # adjust msecs to 1000's for 1 or 2 digit strings
            if len(text_msecs) == 1:
                text_msecs += "00"
            if len(text_msecs) == 2:
                text_msecs += "0"
            try:
                msecs = (int(text_hms[0]) * 3600 + int(text_hms[1]) * 60 + int(text_secs)) * 1000 + int(text_msecs)
                time_pos.append([match.span()[0], msecs])
            except:
                pass
        for match in re.finditer(srt, text):
            # Format 09:33:04,100 --> 09:33:09,600  skip the arrow and second time position
            stamp = match.group()[0:12]
            s = stamp.split(':')
            s2 = s[2].split(',')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                time_pos.append([match.span()[0], msecs])
            except:
                pass

        media_length = 0
        cur = self.app.conn.cursor()
        media_name = media['name'][0:-12]
        cur.execute("select mediapath from source where name=?", (media_name, ))
        media_path_list = cur.fetchone()
        try:
            instance = vlc.Instance()
            vlc_media = instance.media_new(self.app.project_path + media_path_list[0])
            vlc_media.parse()
            media_length = vlc_media.get_duration() - 1
            if media_length == -1:
                media_length = 0
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, _("Media not found"),
                str(e) + "\n" + media_name)
        time_pos.append([len(text) - 1, media_length])

        # order the list by character positions
        time_pos = sorted(time_pos, key=itemgetter(0))
        return time_pos

    def convert_timestamp(self, time_in):
        """ Convert yyyy-mm-dd hh:mm:ss to REFI-QDA yyyy-mm-ddThh:mm:ssZ """

        time_out = time_in.split(' ')[0] + 'T' + time_in.split(' ')[1] + 'Z'
        return time_out

    def get_sources(self):
        """ Add text sources, picture sources, pdf sources, audio sources, video sources.
        Add a .txt suffix to unsuffixed text sources.

        The filename below is also used for the richTextPath for INTERNAL text documents.
        Each text source also needs a plain text file with a separate unique guid..
        plainTextPath = guid + .txt and consists of fulltext

        Files over the 2GiB-1 size must be stored externally, these will be located in the
        qualcoder settings directory. They are not imported into QualCoder but must be linked as an external resource.
        Other files that are linked externally will hav ethe external key replaced with the absolute path.
        """

        self.sources = []
        cur = self.app.conn.cursor()
        cur.execute("SELECT id, name, fulltext, mediapath, memo, owner, date FROM source")
        results = cur.fetchall()
        for r in results:
            guid = self.create_guid()
            suffix = "txt"
            if r[3] is not None:
                suffix = r[3].split('.')[-1]
            else:
                if '.' in r[1]:
                    suffix = r[1].split('.')[-1]
            if suffix == 'transcribed':
                suffix = 'txt'
            filename = guid + '.' + suffix

            plaintext_filename = None
            if r[2] is not None:
                plaintext_filename = self.create_guid() + ".txt"
            source = {'id': r[0], 'name': r[1], 'fulltext': r[2], 'mediapath': r[3],
            'memo': r[4], 'owner': r[5], 'date': r[6], 'guid': guid,
            'filename': filename, 'plaintext_filename': plaintext_filename,
            'external': None}
            # external is an absolute path
            # Make it so that no media > 2Gb is able to be imported internally into the project
            if source['mediapath'] is not None:
                #fileinfo = os.stat(self.app.project_path + source['mediapath'])
                #f fileinfo.st_size >= 2147483647:
                if source['mediapath'][0:5] == 'docs:':
                    source['external'] = source['mediapath'][5:]
                if source['mediapath'][0:7] == 'images:':
                    source['external'] = source['mediapath'][7:]
                if source['mediapath'][0:6] in ('audio:', 'video:'):
                    source['external'] = source['mediapath'][6:]
            self.sources.append(source)

    def get_users(self):
        """ Get all users and assign guid.
        QualCoder sqlite does not actually keep a separate list of users.
        Usernames are drawn from coded text, images and a/v."""

        self. users = []
        sql = "select distinct owner from code_image union select owner from code_text union \
        select owner from source union select owner from code_av"
        cur = self.app.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        for row in result:
            self.users.append({'name': row[0], 'guid': self.create_guid()})

    def get_codes(self):
        """ get all codes and assign guid """

        self.codes = []
        cur = self.app.conn.cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        for row in result:
            c = {'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3].replace(' ', 'T'),
                'cid': row[4], 'catid': row[5], 'color': row[6], 'guid': self.create_guid()}
            xml = '<Code guid="' + c['guid']
            xml += '" name="' + c['name']
            xml += '" isCodable="true'
            xml += '" color="' + c['color'] + '"'
            if c['memo'] != "" and c['memo'] is not None:
                xml += '>\n'
                xml += '<Description>' + c['memo'] + '</Description>\n'
                xml += '</Code>\n'
            else:  # no description element, so wrap up code as <code />
                xml += ' />\n'
            c['xml'] = xml
            self.codes.append(c)

    def get_categories(self):
        """ get categories and assign guid.
        examine is set to true and then to false when creating the xml """

        self.categories = []
        cur = self.app.conn.cursor()
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat")
        result = cur.fetchall()
        for row in result:
            self.categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
            'date': row[3].replace(' ', 'T'), 'memo': row[4], 'supercatid': row[5],
            'guid': self.create_guid(),'examine': True})

    def codebook_xml(self):
        """ Top level items are main categories and unlinked codes
        Create xml for codes and categories.
        codes within categories are does like this: <code><code></code></code>

        :returns xml string
        """

        xml = '<CodeBook>\n'
        xml += '<Codes>\n'
        cats = copy(self.categories)

        # add unlinked codes as top level items
        for c in self.codes:
            if c['catid'] is None:
                xml += c['xml']
        # add top level categories
        for c in cats:
            if c['supercatid'] is None and c['examine']:
                c['examine'] = False
                xml += '<Code guid="' + c['guid']
                xml += '" name="' + c['name']
                xml += '" isCodable="true'
                xml += '">\n'
                if c['memo'] != "":
                    xml += '<Description>' + c['memo'] + '</Description>\n'
                # add codes in this category
                for co in self.codes:
                    if co['catid'] == c['catid']:
                        xml += co['xml']
                xml += self.add_sub_categories(c['catid'], cats)
                xml += '</Code>\n'
        xml += '</Codes>\n'
        xml += '</CodeBook>\n'
        return xml

    def add_sub_categories(self, cid, cats):
        """ Returns recursive xml of category.
        Categories have isCodable=true in exports from other software.

        :param cid  is this cid
        :param cats  a list of categories

        :returns xml string
        """

        xml = ""
        counter = 0
        unfinished = True
        while unfinished and counter < 5000:
            for c in cats:
                if c['examine'] and cid == c['supercatid']:
                    c['examine'] = False
                    xml += '<Code guid="' + c['guid']
                    xml += '" name="' + c['name']
                    xml += '" isCodable="true'
                    xml += '">\n'
                    if c['memo'] != "":
                        xml += '<Description>' + c['memo'] + '</Description>\n'
                    xml += self.add_sub_categories(c['catid'], cats)
                    # add codes
                    for co in self.codes:
                        if co['catid'] == c['catid']:
                            xml += co['xml']
                    xml += '</Code>\n'

            # Are there any categories remaining to examine
            unfinished = False
            for c in cats:
                if c['examine']:
                    unfinished = True
            counter += 1
        return xml

    def create_guid(self):
        """ Create globally unique guid for each component. 128 bit integer, 32 chars
        Format:
        ([0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12})|(\{[0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12}\})

        :returns guid string
        """

        v = uuid.uuid4().hex
        guid = "-".join([v[0:8], v[8:12], v[12:16], v[16:20], v[20:33]])
        duplicated = True
        while duplicated:
            duplicated = False
            if guid in self.guids:
                duplicated = True
            if duplicated:
                v = uuid.uuid4().hex
                guid = "-".join([v[0:8], v[8:12], v[12:16], v[16:20], v[20:33]])
        self.guids.append(guid)
        return guid

    def codebook_exchange_xml(self):
        """ See: https://www.qdasoftware.org/wp-content/uploads/2019/03/QDAS-XML-1-0.pdf
        GUID: 128 bit integer used to identify resources, globally unique
        lxml parser: error occurs when defining UTF-8 encoding in first line
        ValueError:
        Unicode strings with encoding declaration are not supported.
        Please use bytes input or XML fragments without declaration.
        This does not validate DONT USE"""

        self.xml = '<?xml version="1.0" encoding="utf-8"?>\n'
        self.xml += '<CodeBook xmlns="urn:QDA-XML:codebook:1:0" '
        self.xml += 'xsi:schemaLocation="urn:QDA-XML:codebook:1:0 Codebook.xsd" '
        self.xml += 'origin="QualCoder" '
        self.xml += 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        self.xml += self.codebook_xml()[10:]

    def xml_validation(self, xsd_type="codebook"):
        """ Verify that the XML complies with XSD.
        I believe the codebook XSD might be incorrect.
        Arguments:
            1. file_xml: Input xml file
            2. file_xsd: xsd file which needs to be validated against xml
        Return:
            No return value
        """

        file_xsd = codebook
        if xsd_type != "codebook":
            file_xsd = project
        try:
            xml_doc = etree.fromstring(bytes(self.xml, "utf-8"))
            xsd_doc = etree.fromstring(bytes(file_xsd, "utf-8"))
            xmlschema = etree.XMLSchema(xsd_doc)
            xmlschema.assert_(xml_doc)
            return True
        except etree.XMLSyntaxError as err:
            print("PARSING ERROR:{0}".format(err))
            # May have problems with special characters e.g. &
            return False

        except AssertionError as err:
            print("Incorrect XML schema: {0}".format(err))
            return False



