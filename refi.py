# -*- coding: utf-8 -*-

'''
Copyright (c) 2019 Colin Curtain

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
'''

from copy import copy
import datetime
import logging
from lxml import etree
import os
import shutil
import sqlite3
import sys
import traceback
import uuid
import zipfile

from PyQt5 import QtWidgets

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

    """
    Import Rotterdam Exchange Format Initiative (refi) xml documents for codebook.xml and project.xml
    """

    file_path = None
    codes = []
    users = []
    cases = []
    sources = []
    variables = []  # contains dictionary of Variable guid, name, varaible application (cases or files/sources), last_insert_id, text or other
    parent_textEdit = None
    settings = None
    tree = None
    import_type = None
    xml = None

    def __init__(self, settings, parent_textEdit, import_type):

        sys.excepthook = exception_handler
        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.import_type = import_type
        self.tree = None
        self.codes = []
        self.users = []
        self.cases = []
        self.sources = []
        self.variables = []
        self.file_path, ok = QtWidgets.QFileDialog.getOpenFileName(None,
            _('Select REFI_QDA file'), self.settings['directory'], "(*." + import_type + ")")
        if not ok or self.file_path == "":
            return

        if import_type == "qdc":
            self.import_codebook()
        else:
            self.import_project()

    def import_codebook(self):
        """ Import REFI-QDA standard codebook into opened project.
        Codebooks do not validate using the qdasoftware.org Codebook.xsd generated on 2017-10-05 16:17z"""

        #with open(self.file_path, "r") as xml_file:
        #    self.xml = xml_file.read()
        #result = self.xml_validation("codebook")
        #print(result)
        # Typical error with codebook XSD validation:
        # PARSING ERROR: StartTag: invalid element name, line 3, column 2 (Codebook.xsd, line 3)

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
                QtWidgets.QMessageBox.information(None, _("Codebook imported"),
                    str(counter) + _(" categories and codes imported from ") + self.file_path)
                return
        QtWidgets.QMessageBox.warning(None, _("Codebook importation"), self.file_path + _(" NOT imported"))

    def sub_codes(self, parent, cat_id):
        """ Get subcode elements, if any.
        Determines whether the Code is a Category item or a Code item.
        Uses the parent entered cat_id ot give a Code a category alignment,
        or if a category, gives the category alignment to a super_category.

        Recursive, until no more child Codes found.
        Enters this category or code into database and obtains a cat_id (last_insert_id) for next call of method.
        Note: urn difference between codebook.qdc and project.qdpx

        :param parent element, cat_id

        :returns counter of inserted codes and categories
        """

        counter = 0
        elements = parent.getchildren()
        now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        description = ""
        for e in elements:
            if e.tag in("{urn:QDA-XML:codebook:1:0}Description", "{urn:QDA-XML:project:1.0}Description"):
                description = e.text

        # Determine if the parent is a code or a category
        # Has Code element children, so must be a category, insert into code_cat table
        is_category = False
        for e in elements:
            if e.tag in ("{urn:QDA-XML:codebook:1:0}Code", "{urn:QDA-XML:project:1.0}Code"):
                is_category = True
        if is_category:
            last_insert_id = None
            name = parent.get("name")
            if name is not None:
                cur = self.settings['conn'].cursor()
                # insert this category into code_cat table
                try:
                    cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,'',?,?)"
                        , [name, description, now_date, cat_id])
                    self.settings['conn'].commit()
                    cur.execute("select last_insert_rowid()")
                    last_insert_id = cur.fetchone()[0]
                    counter += 1
                except sqlite3.IntegrityError as e:
                    QtWidgets.QMessageBox.warning(None, _("Import error"), _("Category name already exists: ") + name)

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
                cur = self.settings['conn'].cursor()
                cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)"
                    , [name, description, now_date, cat_id, color])
                self.settings['conn'].commit()
                cur.execute("select last_insert_rowid()")
                last_insert_id = cur.fetchone()[0]
                self.codes.append({'guid': parent.get('guid'),'cid': last_insert_id})
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
                cur = self.settings['conn'].cursor()
                cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)"
                    , [name, description, now_date, cat_id, color])
                self.settings['conn'].commit()
                cur.execute("select last_insert_rowid()")
                last_insert_id = cur.fetchone()[0]
                self.codes.append({'guid': parent.get('guid'),'cid': last_insert_id})
                counter += 1
            except sqlite3.IntegrityError as e:
                QtWidgets.QMessageBox.warning(None, _("Import error"), _("Code name already exists: ") + name)
            return counter

        #SHOULD NOT GET HERE
        print("SHOULD NOT BE HERE")
        '''print("tag:", e.tag, e.text, e.get("name"), e.get("color"), e.get("isCodable"))
        return counter'''

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
        """

        #print("IMPORT PROJECT" ,self.file_path)
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
        # look for the Codes tag, which contains each Code element
        children = root.getchildren()
        for c in children:
            #print(c.tag)
            if c.tag == "{urn:QDA-XML:project:1.0}Users":
                self.parent_textEdit.append(_("Parse users"))
                self.parse_users(c)
            if c.tag == "{urn:QDA-XML:project:1.0}CodeBook":
                codes = c.getchildren()[0]  # <Codes> tag is only element
                counter = 0
                for code in codes:
                    # recursive search through each Code in Codes
                    counter += self.sub_codes(code, None)
                self.parent_textEdit.append(_("Parse codes and categories. Loaded: " + str(counter)))
            if c.tag == "{urn:QDA-XML:project:1.0}Variables":
                self.parent_textEdit.append(_("Parse and loading variables"))
                self.parse_variables(c)
            if c.tag == "{urn:QDA-XML:project:1.0}Cases":
                self.parent_textEdit.append(_("Parsing and loading cases"))
                self.parse_cases(c)
            if c.tag == "{urn:QDA-XML:project:1.0}Sources":
                self.parent_textEdit.append(_("Parsing and loading sources"))
                self.parse_sources(c)
            if c.tag == "{urn:QDA-XML:project:1.0}Notes":
                self.parent_textEdit.append(_("Parsing and loading journal notes"))
                self.parse_notes(c)
            if c.tag == "{urn:QDA-XML:project:1.0}Description":
                self.parent_textEdit.append(_("Parsing and loading project memo"))
                self.parse_project_description(c)
            QtWidgets.QApplication.processEvents()
        self.clean_up_case_codes_and_case_text()

    def parse_variables(self, element):
        """ Parse the Variables element.
        Example format:
        <Variable guid="51dc3bcd-5454-47ff-a4d6-ea699144410d" name="Cases:Age group" typeOfVariable="Text">
        <Description />
        </Variable>

        TODO variables assigned to files

        typeOfVariable: Text, Boolean, Integer, Float, Date, Datetime

        :param element
        """

        now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.settings['conn'].cursor()

        for e in element.getchildren():
            #print(e.tag, e.get("name"), e.get("guid"), e.get("typeOfVariable"))
            name = e.get("name").split(':')[1]
            caseOrFile = e.get("name").split(':')[0]
            if caseOrFile == "Cases":
                caseOrFile = "case"
            else:
                caseOrFile = "file"  # is this always true, need to test?
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
                    , (name, now_date, self.settings['codername'], memo, caseOrFile, valuetype))
                self.settings['conn'].commit()
                #cur.execute("select last_insert_rowid()")
                #last_insert_id = cur.fetchone()[0]
            except sqlite3.IntegrityError as e:
                QtWidgets.QMessageBox.warning(None, _("Variable import error"), _("Variable name already exists: ") + name)

            # refer to the variables later
            self.variables.append(variable)

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

        now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.settings['conn'].cursor()

        for e in element.getchildren():
            #print(e.tag, e.get("name"), e.get("guid"))

            item = {"name": e.get("name"), "guid": e.get("guid"), "owner": self.settings['codername'], "memo": "", "caseid": None}
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
                self.settings['conn'].commit()
                cur.execute("select last_insert_rowid()")
                item['caseid'] = cur.fetchone()[0]
                self.cases.append(item)
            except Exception as e:
                self.parent_textEdit.append(_('Error entering Case into database') + '\n' + str(e))
                logger.error("item:" + str(item) + ", " + str(e))

            # Create an empty attribute entry for each Case and variable in the attributes table
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            for v in self.variables:
                if v['caseOrFile'] == 'case':
                    cur.execute(sql, (v['name'], "", item['caseid'], 'case', now_date, self.settings['codername']))
                    self.settings['conn'].commit()

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
                    self.settings['conn'].commit()

    def clean_up_case_codes_and_case_text(self):
        """ Some Code guids match the Case guids. So remove these Codes.
        For text selectino:
        Some Coding selections match the Case guid. So re-align to Case selections.
        """

        cur = self.settings['conn'].cursor()

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
                    self.settings['conn'].commit()

        # Insert case text details into case_text
        for c in case_texts:
            sql = "insert into case_text (caseid,fid,pos0,pos1,owner, date, memo) values(?,?,?,?,?,?,?)"
            cur.execute(sql, c)
            self.settings['conn'].commit()

    def parse_sources(self, element):
        """ Parse the Sources element.
        This contains text and media sources as well as variables describing the source and coding information.
        Example format:
        <TextSource guid="a2b94468-80a5-412f-92d6-e900d97b55a6" name="Anna" richTextPath="internal://a2b94468-80a5-412f-92d6-e900d97b55a6.docx" plainTextPath="internal://a2b94468-80a5-412f-92d6-e900d97b55a6.txt" creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime="2019-06-04T05:25:16Z" modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime="2019-06-04T05:25:16Z">


        :param element:
        """

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
            #TODOif e.tag == "{urn:QDA-XML:project:1.0}PDFSource":
            #    self.load_pdf_source(e)

    def load_picture_source(self, element):
        """ Load this picture source.
         Load the description and codings into sqlite.
         """

        print("Load picture source todo")
        name = element.get("name")
        guid = element.get("guid")
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')

        # paths starts with internal://
        path = element.get("path").split('internal:/')[1]
        source_path = self.folder_name + '/Sources' + path

        # Copy file into .qda images folder and rename into original name
        #print(source_path)
        destination = self.settings['path'] + "/images/" + name
        media_path = "/images/" + name
        #print(destination)
        try:
            shutil.copyfile(source_path, destination)
        except Exception as e:
            self.parent_textEdit.append(_('Cannot copy Image file from: ') + source_path + "\nto: " + destination + '\n' + str(e))

        cur = self.settings['conn'].cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (name, '', creating_user, create_date, media_path, None))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]

        #TODO load codings


    def load_audio_source(self, element):
        """ Load audio source into .
        Load the description and codings into sqlite.

        path to file can be internal or relative.
        e.g. path="relative:///DF370983‐F009‐4D47‐8615‐711633FA9DE6.m4a"
        """
        #TODO check this works
        print("Load audio source todo")
        name = element.get("name")
        guid = element.get("guid")
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')

        # path starts with internal:// or relative:///
        path = element.get("path")
        if path.find("internal://") == 0:
            path = element.get("path").split('internal:/')[1]
            source_path = self.folder_name + '/Sources' + path
        if path.find("relative:///") == 0:
            source_path = self.settings['path'] + "../" + path.split('relative:///')[1]
            print("RELATIVE AUDIO PATH: " + source_path)  # tmp

        # Copy file into .qda audio folder and rename into original name
        #print(source_path)
        destination = self.settings['path'] + "/audio/" + name
        media_path = "/audio/" + name
        #print(destination)
        try:
            shutil.copyfile(source_path, destination)
        except Exception as e:
            self.parent_textEdit.append(_('Cannot copy Audio file from: ') + source_path + "\nto: " + destination + '\n' + str(e))

        cur = self.settings['conn'].cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (name, '', creating_user, create_date, media_path, None))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]

        #TODO load transcript
        #TODO transcript contains SynchPoints AKA timestamps
        #TODO load codings

    def load_video_source(self, element):
        """ Load this video source into .
        Load the description and codings into sqlite.
        """
        #TODO check this works
        print("Load video source todo")
        name = element.get("name")
        guid = element.get("guid")
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')

        # paths starts with internal:// or relative:///
        path = element.get("path")
        if path.find("internal://") == 0:
            path = element.get("path").split('internal:/')[1]
            source_path = self.folder_name + '/Sources' + path
        if path.find("relative:///") == 0:
            source_path = self.settings['path'] + "../" + path.split('relative:///')[1]
            print("RELATIVE AUDIO PATH: " + source_path)  # tmp

        # Copy file into .qda video folder and rename into original name
        #print(source_path)
        destination = self.settings['path'] + "/video/" + name
        media_path = "/video/" + name
        #print(destination)
        try:
            shutil.copyfile(source_path, destination)
        except Exception as e:
            self.parent_textEdit.append(_('Cannot copy Video file from: ') + source_path + "\nto: " + destination + '\n' + str(e))

        cur = self.settings['conn'].cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (name, '', creating_user, create_date, media_path, None))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]

        #TODO load transcript
        #TODO transcript contains SynchPoints AKA timestamps
        #TODO load codings

    def load_text_source(self, element):
        """ Load this text source into sqlite.
         Add the description and the text codings.
         """

        cur = self.settings['conn'].cursor()

        name = element.get("name")
        guid = element.get("guid")
        creating_user_guid = element.get("creatingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        # paths starts with internal://
        plain_path = element.get("plainTextPath").split('internal:/')[1]
        plain_path = self.folder_name + '/Sources' + plain_path

        # find Description to complete memo
        memo = ""
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = e.text
        source = {'name': name, 'id': -1, 'fulltext': "", 'mediapath': None, 'memo': memo,
                 'owner': self.settings['codername'], 'date': create_date, 'guid': guid}
        # Read the text and enter into sqlite source table
        try:
            with open(plain_path) as f:
                fulltext = f.read()
                #if fulltext[0:6] == "\ufeff":  # associated with notepad files
                #    fulltext = fulltext[6:]
                source['fulltext'] = fulltext
                cur = self.settings['conn'].cursor()
                # logger.debug("type fulltext: " + str(type(entry['fulltext'])))
                cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                    (name, fulltext, source['mediapath'], memo, creating_user, create_date))
                self.settings['conn'].commit()
                cur.execute("select last_insert_rowid()")
                id_ = cur.fetchone()[0]
                source['id'] = id_
                self.sources.append(source)
        except Exception as e:
            self.parent_textEdit.append(_("Cannot read from TextSource: ") + plain_path + "\n" + str(e))

        # Copy file into .qda documents folder and rename into original name
        rich_path = element.get("richTextPath").split('internal:/')[1]
        rich_path_full = self.folder_name + '/Sources' + rich_path
        #print(rich_path_full)
        destination = self.settings['path'] + "/documents/" + name + '.' + rich_path.split('.')[-1]
        #print(destination)
        try:
            shutil.copyfile(rich_path_full, destination)
        except Exception as e:
            self.parent_textEdit.append(_('Cannot copy TextSource file from: ') + rich_path_full + "\nto: " + destination + '\n' + str(e))

        # ParsePlainTextSelection elements for Coding elements and load these
        for e in element.getchildren():
            if e.tag == "{urn:QDA-XML:project:1.0}PlainTextSelection":
                self._load_codings_for_text(source, e)

    def _load_codings_for_text(self, source, element):
        ''' These are PlainTextSelection elements.
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

         Inconsistent positioning of pos0 and pos1 from import of plain text from Nvivo.

        :param entry - the source text dictionary
        :param element - the PlainTextSelection element
        '''

        cur = self.settings['conn'].cursor()
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
                self.settings['conn'].commit()
            if e.tag == "{urn:QDA-XML:project:1.0}Coding":
                memo = ""
                #TODO? can coded text be memoed?
                # Get the code id from the CodeRef guid
                cid = None
                codeRef = e.getchildren()[0]
                for c in self.codes:
                    if c['guid'] == codeRef.get("targetGUID"):
                        cid = c['cid']
                cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                    memo,date) values(?,?,?,?,?,?,?,?)", (cid, source['id'],
                    seltext, pos0, pos1, creating_user, memo, create_date))
                self.settings['conn'].commit()

    def parse_notes(self, element):
        """ Parse the Notes element.
        Notes are possibly journal entries.
        Example format:
        <Note guid="4691a8a0-d67c-4dcc-91d6-e9075dc230cc" name="Assignment Progress Memo" richTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.docx" plainTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.txt" creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime="2019-06-04T06:11:56Z" modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime="2019-06-17T08:00:58Z">
        <Description>Steps towards completing the assignment</Description>
        </Note>

        :param element Notes
        """

        cur = self.settings['conn'].cursor()

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
            self.settings['conn'].commit()

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
        cur = self.settings['conn'].cursor()
        cur.execute("update project set memo = ?", (memo, ))
        self.settings['conn'].commit()

    def parse_users(self, element):
        """ Parse Users element children, fill list with guid and name.
        There is no user table in QualCoder sqlite.
        Store each user in dictionary with name and guid.
        :param Users element
        """

        for e in element.getchildren():
            #print(e.tag, e.get("name"), e.get("guid"))
            self.users.append({"name": e.get("name"), "guid": e.get("guid")})

    def xml_validation(self, xsd_type="codebook"):
        """ Verify that the XML complies with XSD
        Arguments:
            1. file_xml: Input xml file
            2. file_xsd: xsd file which needs to be validated against xml

        :param xsd_type codebook or project

        :return true or false passing validation
        """

        file_xsd = path + "/Codebook.xsd"
        if xsd_type != "codebook":
            file_xsd = path + "/Project-mrt2019.xsd"
        #print(file_xsd)
        try:
            #print("Validating:{0}".format(self.xml))
            #print("xsd_file:{0}".format(file_xsd))
            #xml_doc = etree.tostring(self.xml)
            xml_doc = etree.fromstring(bytes(self.xml, "utf-8"))  #  self.xml)
            xsd_doc = etree.parse(file_xsd)
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

    """
    Create Rotterdam Exchange Format Initiative (refi) xml documents for codebook.xml and project.xml
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
    settings = None
    tree = None
    export_type = ""

    def __init__(self, settings, parent_textEdit, export_type):
        """  """

        sys.excepthook = exception_handler
        self.settings = settings
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
        '''
        .qde zipfile
        Internal files are identified in the path attribute of the source element by the URL naming scheme internal://
        /sources folder
        Audio and video source file size:
        The maximum size in bytes allowed for an internal file is 2,147,483,647 bytes (2^31−1 bytes, or 2 GiB
        minus 1 byte). An exporting application must detect file size limit during export and inform the
        user.

        Source types:
        Plain text, PDF
        Images must be jpeg or png

        Create an unzipped folder with a /sources folder and project.qde xml document
        Then create zip wih suffix .qdpx
        '''

        project_name = self.settings['projectName'][:-4]
        prep_path = os.path.expanduser('~') + '/.qualcoder/' + project_name
        #print("REFI-QDA EXPORT prep_path: ", prep_path)  # tmp
        try:
            shutil.rmtree(prep_path)
        except FileNotFoundError :
            logger.error(_("Project export error ") + _(" .qualcoder preperatory path not found"))
        try:
            os.mkdir(prep_path)
            os.mkdir(prep_path + "/sources")
        except Exception as e:
            logger.error(_("Project export error ") + str(e))
            QtWidgets.QMessageBox.warning(None, _("Project"), _("Project not exported. Exiting. ") + str(e))
            exit(0)
        try:
            with open(prep_path +'/project.qde', 'w') as f:
                f.write(self.xml)
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, _("Project"), _("Project not exported. Exiting. ") + str(e))
            print(e)
            exit(0)
        for s in self.sources:
            #print(s['id'], s['name'], s['mediapath'], s['filename'], s['plaintext_filename'], s['external'])  # tmp
            destination = '/sources/' + s['filename']
            if s['mediapath'] is not None:
                    try:
                        if s['external'] is None:
                            shutil.copyfile(self.settings['path'] + s['mediapath'],
                                prep_path + destination)
                        else:
                            shutil.copyfile(self.settings['path'] + s['mediapath'],
                                self.settings['directory'] + '/' + s['filename'])
                    except FileNotFoundError as e:
                        print(e)
            if s['mediapath'] is None:  # a document
                try:
                    shutil.copyfile(self.settings['path'] + '/documents/' + s['name'],
                        prep_path + destination)
                except FileNotFoundError as e:
                    with open(prep_path + destination, 'w') as f:
                        f.write(s['fulltext'])
                # Also need to add the plain text file as a source
                # plaintext has different guid from richtext
                with open(prep_path + '/sources/' + s['plaintext_filename'], 'w') as f:
                    f.write(s['fulltext'])
        for notefile in self.note_files:
            with open(prep_path + '/sources/' + notefile[0], 'w') as f:
                f.write(notefile[1])

        export_path = self.settings['path'][:-4]
        shutil.make_archive(export_path, 'zip', prep_path)
        os.rename(export_path + ".zip", export_path + ".qpdx")
        try:
            shutil.rmtree(prep_path)
        except FileNotFoundError:
            pass
        msg = export_path + ".qpdx\n"
        msg += "Coding for a/v transcripts is not correct yet. \n"
        msg += "Transcript coding exported as a <TextSource> rather than within "
        msg += " the <VideoSource><Transcript> tags.\n"
        msg += "Large > 2GBfiles are not stored externally."
        msg += "This project exchange is not compliant with the exchange standard."
        QtWidgets.QMessageBox.information(None, _("Project exported"), _(msg))

    def export_codebook(self):
        """ Export REFI format codebook. """

        filename = "Codebook-" + self.settings['projectName'][:-4] + ".qdc"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.settings['directory'], options)
        if directory == "":
            return
        filename = directory + "/" + filename
        try:
            f = open(filename, 'w')
            f.write(self.xml)
            f.close()
            msg = "Codebook has been exported to "
            msg += filename
            QtWidgets.QMessageBox.information(None, _("Codebook exported"), _(msg))
        except Exception as e:
            logger.debug(str(e))
            QtWidgets.QMessageBox.information(None, _("Codebook NOT exported"), str(e))

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
        base path for external sources is set to the settings directory. """

        self.xml = '<?xml version="1.0" encoding="utf-8"?>\n'
        self.xml += '<Project '
        self.xml += 'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        self.xml += 'name="' + self.settings['projectName'] + '" '
        self.xml += 'origin="Qualcoder-1.4" '
        guid = self.create_guid()
        self.xml += 'creatingUserGUID="' + guid + '" '  # there is no creating user in QualCoder
        cur = self.settings['conn'].cursor()
        cur.execute("select date from project")
        result = cur.fetchone()
        self.xml += 'creationDateTime="' + self.convert_timestamp(result[0]) + '" '
        #self.xml += 'basePath="' + self.settings['directory'] + '" '
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
        #self.sets_xml()
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
        cur = self.settings['conn'].cursor()
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

        cur = self.settings['conn'].cursor()
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
        Appends file name and journal text in notes_files list. This is exported to sources folder.
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
        cur = self.settings['conn'].cursor()
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
        cur = self.settings['conn'].cursor()
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
        cur = self.settings['conn'].cursor()
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
        cur = self.settings['conn'].cursor()
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
        cur = self.settings['conn'].cursor()
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
        Called by: project_xml

        :returns xml string
        """

        xml = "<Sources>\n"
        for s in self.sources:
            guid = self.create_guid()
            # text document
            if s['mediapath'] is None and (s['name'][-4:].lower() != '.pdf' or s['name'][-12:] != '.transcribed'):
                xml += '<TextSource '
                xml += 'richTextPath="internal://' + s['filename'] + '" '
                xml += 'plainTextPath="internal://' + s['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '">\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.text_selection_xml(s['id'])
                xml += self.source_variables_xml(s['id'])
                xml += '</TextSource>\n'
            # pdf document
            if s['mediapath'] is None and s['name'][-4:].lower() == '.pdf':
                xml += '<PDFSource '
                xml += 'path="internal://' + s['filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '">\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += '<Representation guid="' + self.create_guid() + '" '
                xml += 'plainTextPath="internal://' + s['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'name="' + s['name'] + '">\n'
                xml += self.text_selection_xml(s['id'])
                xml += '</Representation>'
                xml += self.source_variables_xml(s['id'])
                xml += '</PDFSource>\n'
            if s['mediapath'] is not None and s['mediapath'][0:7] == '/images':
                xml += '<PictureSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                xml += 'path="internal://' + s['filename'] + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '" >\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.picture_selection_xml(s['id'])
                xml += self.source_variables_xml(s['id'])
                xml += '</PictureSource>\n'
            if s['mediapath'] is not None and s['mediapath'][0:6] == '/audio':
                xml += '<AudioSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                if s['external'] is None:
                    xml += 'path="internal://' + s['filename'] + '" '
                else:
                    xml += 'path="absolute:///'+ self.settings['directory'] + '/' + s['filename'] + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '" >\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.transcript_xml(s)
                xml += self.av_selection_xml(s['id'])
                xml += self.source_variables_xml(s['id'])
                xml += '</AudioSource>\n'
            if s['mediapath'] is not None and s['mediapath'][0:6] == '/video':
                xml += '<VideoSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + self.convert_timestamp(s['date']) + '" '
                if s['external'] is None:
                    xml += 'path="internal://' + s['filename'] + '" '
                else:
                    xml +='path="absolute:///' + self.settings['directory'] + '/'+ s['filename'] + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '" >\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.transcript_xml(s)
                xml += self.av_selection_xml(s['id'])
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
        cur = self.settings['conn'].cursor()
        cur.execute(sql, [id_, ])
        results = cur.fetchall()
        for r in results:
            xml += '<PlainTextSelection guid="' + self.create_guid() + '" '
            xml += 'startPosition="' + str(r[2]) + '" '
            xml += 'endPosition="' + str(r[3]) + '" '
            xml += 'name="' + str(r[1]) + '" '
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
        cur = self.settings['conn'].cursor()
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

    def av_selection_xml(self, id_):
        """ Get and complete av selection xml.
        Called by: sources_xml

        :param id_ is the source id

        :returns xml string
        """

        xml = ""
        sql = "select avid, cid, pos0, pos1, owner, date, memo from code_av "
        sql += "where id=?"
        cur = self.settings['conn'].cursor()
        cur.execute(sql, [id_, ])
        results = cur.fetchall()
        for r in results:
            xml += '<VideoSelection guid="' + self.create_guid() + '" '
            xml += 'begin="' + str(int(r[2])) + '" '
            xml += 'end="' + str(int(r[3])) + '" '
            xml += 'name="' + str(r[6]) + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" >'
            xml += '<Coding guid="' + self.create_guid() + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" '
            xml += 'creationDateTime="' + self.convert_timestamp(r[5]) + '">\n'
            xml += '<CodeRef targetGUID="' + self.code_guid(r[1]) + '"/>\n'
            xml += '</Coding>\n'
            xml += '</VideoSelection>\n'
        return xml

    def transcript_xml(self, source):
        """ Find any transcript of media source.
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
                xml += 'name="' + t['name'] + '" >\n'
                xml += '<SyncPoint guid="' + self.create_guid() + '" '
                xml += 'position="0" timeStamp="0" />\n'
                # Element not expected
                #if t['memo'] != '':
                #    xml += self.create_note_xml(guid, t['memo'], self.user_guid(t['owner']), t['date'])
                xml += '</Transcript>\n'
                break
        return xml

    def convert_timestamp(self, time_in):
        ''' Convert yyyy-mm-dd hh:mm:ss to REFI-QDA yyyy-mm-ddThh:mm:ssZ '''

        time_out = time_in.split(' ')[0] + 'T' + time_in.split(' ')[1] + 'Z'
        return time_out

    def get_sources(self):
        """ Add text sources, picture sources, pdf sources, audio sources, video sources.
        Add a .txt suffix to unsuffixed text sources.

        The filename below is also used for the richTextPath for text documents.
        Each text source also needs a plain text file with a separate unique guid..
        plainTextPath = guid + .txt and consists of fulltext

        Files over the 2GiB-1 size must be stored externally, these will be located in the
        qualcoder settings directory.
        """

        self.sources = []
        cur = self.settings['conn'].cursor()
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
            if source['mediapath'] is not None:
                fileinfo = os.stat(self.settings['path'] + source['mediapath'])
                if fileinfo.st_size >= 2147483647:
                    source['external'] = self.settings['directory']
            self.sources.append(source)

    def get_users(self):
        """ Get all users and assign guid.
        QualCoder sqlite does not actually keep a separate list of users.
        Usernames are drawn from coded text, images and a/v."""

        self. users = []
        sql = "select distinct owner from  code_image union select owner from code_text union select owner from code_av"
        cur = self.settings['conn'].cursor()
        cur.execute(sql)
        result = cur.fetchall()
        for row in result:
            self.users.append({'name': row[0], 'guid': self.create_guid()})

    def get_codes(self):
        """ get all codes and assign guid """

        self.codes = []
        cur = self.settings['conn'].cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        for row in result:
            c = {'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3].replace(' ', 'T'),
                'cid': row[4], 'catid': row[5], 'color': row[6], 'guid': self.create_guid()}
            xml = '<Code guid="' + c['guid']
            xml += '" name="' + c['name']
            xml += '" isCodable="true'
            xml += '" color="' + c['color'] + '"'
            if c['memo'] != "":
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
        cur = self.settings['conn'].cursor()
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

        file_xsd = path + "/Codebook.xsd"
        if xsd_type != "codebook":
            file_xsd = path + "/Project-mrt2019.xsd"
        print(file_xsd)
        try:
            print("Validating:{0}".format(self.xml))
            print("xsd_file:{0}".format(file_xsd))
            #xml_doc = etree.tostring(self.xml)
            xml_doc = etree.fromstring(bytes(self.xml, "utf-8"))  #  self.xml)
            xsd_doc = etree.parse(file_xsd)
            xmlschema = etree.XMLSchema(xsd_doc)
            xmlschema.assert_(xml_doc)
            return True
        except etree.XMLSyntaxError as err:
            print("PARSING ERROR:{0}".format(err))
            return False

        except AssertionError as err:
            print("Incorrect XML schema: {0}".format(err))
            return False



