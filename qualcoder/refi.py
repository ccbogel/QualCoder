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
import datetime
import html
import logging
from operator import itemgetter
import os
from random import randint
import re
import shutil
import sqlite3
import sys
import traceback
import uuid
import xml.etree.ElementTree as etree
import zipfile

from PyQt6 import QtWidgets, QtCore

from .color_selector import colors, color_matcher
from .xsd import xsd_codebook, xsd_project
from .GUI.ui_dialog_refi_export_endings import Ui_Dialog_refi_export_line_endings
from .helpers import Message

# If VLC not installed, it will not crash
vlc = None
try:
    import vlc
except Exception as e:
    print(e)

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class RefiImport:
    """ Import Rotterdam Exchange Format Initiative (refi) xml documents for codebook.xml
    and project.xml
    Validate using REFI-QDA Codebook.xsd or Project-mrt2019.xsd

    TODO load_audio_source - check it works: transcript synchpoints, transcript codings
    TODO load_video_source - check it works: transcript synchpoints, transcript codings
    TODO check imports from different vendors, tried Quirkos, Maxqda, Nvivo for text only so far
    TODO reference external sources - relative or absolute paths

    Trying: https://docs.python.org/3/library/xml.etree.elementtree.html
    """

    file_path = None
    folder_name = ""  # Temporary extract folder name
    codes = []
    users = []
    cases = []
    sources = []  # List of Dictionary of mediapath, guid, memo, owner, date, id, fulltext
    sources_name = "/Sources"  # Sources folder can be named Sources or sources
    # List of Dictionaries of Variable guid, name, variable application (cases or files), last_insert_id, text or other
    variables = []
    file_vars = []  # Values for each variable for each file Found within Cases Case tag
    annotations = []  # Text source annotation references
    links = []  # Links - using now for Nvivo to link Note with .txt or .docx to PlainTextSelection annotation
    parent_textedit = None
    app = None
    tree = None
    import_type = None
    xml = None
    base_path = ""
    software_name = ""
    # Progress dialog
    pd = None
    pd_value = 0

    def __init__(self, app, parent_textedit, import_type):

        self.app = app
        self.parent_textedit = parent_textedit
        self.import_type = import_type
        self.tree = None
        self.codes = []
        self.users = []
        self.cases = []
        # Sources: name id fulltext mediapath memo owner date
        self.sources = []
        self.source_name_prefix = 0  # Used to add text prefix to source name. MaxQDA has multile same named text files.
        self.variables = []
        self.base_path = ""
        self.software_name = ""
        if import_type == "qdc":
            self.file_path, ok = QtWidgets.QFileDialog.getOpenFileName(None,
                                                                       _('Select REFI-QDA file'),
                                                                       self.app.settings['directory'],
                                                                       "(*.qdc *.QDC)",
                                                                       options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                                       )
            if not ok or self.file_path == "":
                return
            self.import_codebook()
        else:
            self.file_path, ok = QtWidgets.QFileDialog.getOpenFileName(None,
                                                                       _('Select REFI-QDA qdpx file'),
                                                                       self.app.settings['directory'],
                                                                       "(*.qdpx *.QDPX)",
                                                                       options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                                       )
            if not ok or self.file_path == "":
                return
            self.import_project()

    def import_codebook(self):
        """ Import REFI-QDA standard codebook into opened project.
        """

        # Get element tree object
        tree = etree.parse(self.file_path)
        root = tree.getroot()
        # Look for the Codes tag, which contains each Code element
        for child in root:
            #print("CB:", child, "tag:", child.tag)  # 1 only , Codes
            if child.tag in ("{urn:QDA-XML:codebook:1.0}Codes", "{urn:QDA-XML:project:1.0}Codes"):
                counter = 0
                code_elements = list(child)  # list of children of child element
                for el_ in code_elements:
                    # Recursive search through each Code element
                    counter += self.sub_codes(child, None)
                msg = str(counter) + _(" categories and codes imported from ") + self.file_path
                Message(self.app, _("Codebook imported"), msg).exec()
                self.parent_textedit.append(msg)
                return
        Message(self.app, _("Codebook importation"), self.file_path + _(" NOT imported"), "warning").exec()

    def sub_codes(self, parent, cat_id):
        """ Get subcode elements, if any.
        Determines whether the Code is a Category item or a Code item.
        Uses the parent entered cat_id ot give a Code a category alignment,
        or if a category, gives the category alignment to a super_category.
        Called from: import_project, import_codebook

        Some software e.g. MAXQDA, Nvivo categories are also codes
        in this case QualCoder will create a category, and also a code with the same name underneath that category.

        Recursive, until no more child Codes found.
        Enters this category or code into database and obtains a cat_id (last_insert_id) for next call of method.
        Note: urn difference between codebook.qdc and project.qdpx

        param parent element, cat_id

        returns counter of inserted codes and categories
        """

        counter = 0
        elements = list(parent)
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        description = ""
        for el in elements:
            if el.tag in ("{urn:QDA-XML:codebook:1.0}Description", "{urn:QDA-XML:project:1.0}Description"):
                description = el.text

        # Determine if the parent is a code or a category
        # if parent has Code element children, so must be a category, insert into code_cat table
        is_category = False
        for el in elements:
            if el.tag in ("{urn:QDA-XML:codebook:1.0}Code", "{urn:QDA-XML:project:1.0}Code"):
                is_category = True
        # if parent does not have Code element children and isCodable is false, it must be a category
        if parent.get("isCodable") == "false":
            is_category = True
        if is_category:
            last_insert_id = None
            name = parent.get("name")
            if name is not None:
                cur = self.app.conn.cursor()
                # insert this category into code_cat table
                try:
                    cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,'',?,?)",
                                [name, description, now_date, cat_id])
                    self.app.conn.commit()
                    cur.execute("select last_insert_rowid()")
                    last_insert_id = cur.fetchone()[0]
                    counter += 1
                except sqlite3.IntegrityError:
                    pass
                # This category may ALSO be a code (e.g. MAXQDA has categories as codes also)
                # So create a code for this codable category
                is_codable = parent.get("isCodable")
                if is_codable == "true":
                    color = parent.get("color")
                    if color is None:
                        color = colors[randint(0, 119)]
                    else:
                        # Convert other software hex color to a similar one listed in color_selector.py
                        color = color_matcher(color)
                    try:
                        # print(is_codable, name, "inserting into code name")
                        cur = self.app.conn.cursor()
                        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)",
                                    [name, description, now_date, last_insert_id, color])
                        self.app.conn.commit()
                        cur.execute("select last_insert_rowid()")
                        code_last_insert_id = cur.fetchone()[0]
                        self.codes.append({'guid': parent.get('guid'), 'cid': code_last_insert_id})
                        counter += 1
                    except sqlite3.IntegrityError:
                        pass
            for el in elements:
                if el.tag not in ("{urn:QDA-XML:codebook:1.0}Description", "{urn:QDA-XML:project:1.0}Description"):
                    counter += self.sub_codes(el, last_insert_id)
                    # print("tag:", el.tag, el.text, el.get("name"), el.get("color"), el.get("isCodable"))
            return counter

        # No children and no Description child element so, insert this code into code_name table
        if is_category is False and elements == []:
            name = parent.get("name")
            # print("No children or description ", name)
            color = parent.get("color")
            if color is None:
                color = colors[randint(0, 119)]
            else:
                # Convert other software hex color to a similar one listed in color_selector.py
                color = color_matcher(color)
            try:
                cur = self.app.conn.cursor()
                cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)",
                            [name, description, now_date, cat_id, color])
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                last_insert_id = cur.fetchone()[0]
                self.codes.append({'guid': parent.get('guid'), 'cid': last_insert_id})
                counter += 1
            except sqlite3.IntegrityError:
                pass  # Code name already exists
            return counter

        # One child, a description so, insert this code into code_name table
        if is_category is False and len(elements) == 1 and elements[0].tag in (
                "{urn:QDA-XML:codebook:1.0}Description", "{urn:QDA-XML:project:1.0}Description"):
            name = parent.get("name")
            # print("Only a description child: ", name)
            color = parent.get("color")
            if color is None:
                color = colors[randint(0, 119)]
            else:
                # Convert other software hex color to a similar one listed in color_selector.py
                color = color_matcher(color)
            try:
                cur = self.app.conn.cursor()
                cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,'',?,?,?)",
                            [name, description, now_date, cat_id, color])
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                last_insert_id = cur.fetchone()[0]
                self.codes.append({'guid': parent.get('guid'), 'cid': last_insert_id})
                counter += 1
            except sqlite3.IntegrityError:
                pass
            return counter
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
        {urn: QDA - XML: project:1.0}Links
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

        # Create temporary extract folder
        self.folder_name = self.file_path[:-4] + "_temporary"
        self.parent_textedit.append(_("Reading from: ") + self.file_path)
        self.parent_textedit.append(_("Creating temporary directory: ") + self.folder_name)
        # Unzip qpdx folder
        project_zip = zipfile.ZipFile(self.file_path)
        project_zip.extractall(self.folder_name)
        project_zip.close()

        # Set up progress dialog
        # Source loading can be slow, so use this for the progress dialog
        # Sources folder name can be capital or lower case, check and get the correct one
        contents = os.listdir(self.folder_name)
        self.sources_name = "/Sources"
        for i in contents:
            if i == "sources":
                self.sources_name = "/sources"
        num_sources = len(os.listdir(self.folder_name + self.sources_name))
        self.pd = QtWidgets.QProgressDialog(_("Project Import"), "", 0, num_sources, None)
        self.pd.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.pd_value = 0

        # Parse xml for users, codebook, sources, journals, project description, variable names
        with open(self.folder_name + "/project.qde", "r", encoding="utf8") as xml_file:
            self.xml = xml_file.read()
        result = self.xml_validation("project")
        self.parent_textedit.append("Project XML parsing successful: " + str(result))
        tree = etree.parse(self.folder_name + "/project.qde")  # get element tree object
        root = tree.getroot()
        # Must parse Project tag first to get software_name
        # This is used when importing - especially from ATLAS.ti
        self.parse_project_tag(root)
        children = list(root)
        for c in children:
            # print(c.tag)
            if c.tag == "{urn:QDA-XML:project:1.0}Users":
                count = self.parse_users(c)
                self.parent_textedit.append(_("Parse users. Loaded: " + str(count)))
            if c.tag == "{urn:QDA-XML:project:1.0}CodeBook":
                codes = list(c)[0]  # <Codes> tag is only element
                count = 0
                for code in codes:
                    # Recursive search through each Code in Codes
                    count += self.sub_codes(code, None)
                self.parent_textedit.append(_("Parse codes and categories. Loaded: ") + str(count))
            if c.tag == "{urn:QDA-XML:project:1.0}Variables":
                count = self.parse_variables(c)
                self.parent_textedit.append(_("Parse variables. Loaded: ") + str(count))
            if c.tag == "{urn:QDA-XML:project:1.0}Description":
                self.parent_textedit.append(_("Parsing and loading project memo"))
                self.parse_project_description(c)
            if c.tag == "{urn:QDA-XML:project:1.0}Links":
                self.parse_links(c)

        # Parse Notes to add plaintext to link for links between PlainTextSelection and Note .txt/.docx
        children = list(root)
        for c in children:
            if c.tag == "{urn:QDA-XML:project:1.0}Notes":
                self.parse_notes_for_plaintextselection_link(c)

        # Parse Cases element for any file variable values (No case name and only one sourceref)
        # Fill list of dictionaries of these variable values
        self.parse_cases_for_file_variables(root)
        self.parent_textedit.append(_("Parsed cases for file variables. Loaded: ") + str(len(self.file_vars)))

        # Parse Sources element after the variables components parsed
        # Variables caseOrFile will be 'file' for ALL variables, to change later if needed
        children = list(root)  # root.getchildren()
        for c in children:
            if c.tag == "{urn:QDA-XML:project:1.0}Sources":
                count = self.parse_sources(c)
                self.parent_textedit.append(_("Parsing sources. Loaded: " + str(count)))

        # Parse Notes after sources. Notes contain journals and also text annotations
        for c in children:
            if c.tag == "{urn:QDA-XML:project:1.0}Notes":
                # Parse for journals AND annotations. Multiple ways annotations ca nbe stored
                journal_count = self.parse_notes(c)
                self.parent_textedit.append(_("Parsing Notes. Journals loaded: ") + str(journal_count))

        # Fill attributes table for File variables drawn fom Cases.Case tags
        # After Sources are loaded
        self.fill_file_attribute_values()

        # Parse Cases element and update variables already assigned as 'file' if needed
        children = list(root)
        for c in children:
            # print(c.tag)
            if c.tag == "{urn:QDA-XML:project:1.0}Cases":
                count = self.parse_cases(c)
                self.parent_textedit.append(_("Parsing cases. Loaded: ") + str(count))
        self.clean_up_case_codes_and_case_text()

        # Parse Sets element and update variables
        children = list(root)
        for c in children:
            # print(c.tag)
            if c.tag == "{urn:QDA-XML:project:1.0}Sets":
                self.parse_sets(c)
                self.parent_textedit.append(_("Parsing sets."))
        # Wrap up
        self.parent_textedit.append(self.file_path + _(" loaded."))
        # Remove temporary extract folder
        try:
            shutil.rmtree(self.folder_name)
        except OSError as err:
            logger.debug(f"{err} {self.folder_name}")
        # Change the username to an owner name from the import
        if len(self.users) > 0:
            self.app.settings['codername'] = self.users[0]['name']
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        # Update vectorstore
        if self.app.settings['ai_enable'] == 'True':
            self.app.ai.sources_vectorstore.update_vectorstore()        
        
        self.pd.close()
        msg = _("REFI-QDA PROJECT IMPORT EXPERIMENTAL FUNCTION - NOT FULLY TESTED\n")
        msg += _("Audio/video transcripts: transcript codings and synchpoints not tested.\n")
        msg += _("Set components may be imported as file attributes.\n")
        msg += _("Graphs not imported as QualCoder does not have this functionality.\n")
        msg += _("Boolean variables treated as character (text). Integer variables treated as floating point. \n")
        msg += _("All variables are stored as text. Cast as text or float for SQL operations.\n")
        msg += _("Relative paths to external files are untested.\n")
        msg += _("Select a coder name in Settings dropbox, otherwise coded text and media may appear uncoded.")
        Message(self.app, _('REFI-QDA Project import'), msg, "warning").exec()

    def parse_links(self, element):
        """ Parse Links element for each Link and add to list.
        Nvivo - Links PlainTextSelection to Note. Note contains the plaintext.txt annotation text.
        """

        for el in list(element):
            #print("LINK TAG", el.tag, "GUID", el.get("guid"), "origin", el.get("originGUID"), "target", el.get("targetGUID"))
            link = {"GUID": el.get("guid"), "originGUID": el.get("originGUID"), "targetGUID": el.get("targetGUID")}
            self.links.append(link)

    def parse_notes_for_plaintextselection_link(self, notes_element):
        """ Parse the Notes element to determine if the element is a originGUID
         Nvivo - Links PlainTextSelection to Note. Note contains the plaintext.txt annotation text.
         Add plain text to the link. """

        for el in list(notes_element):
            note_guid = el.get('guid')
            # Presumes these will be internal paths
            source_path = el.get("plainTextPath")
            if source_path is not None:
                try:
                    source_path = source_path.split('internal:/')[1]
                    source_path = self.folder_name + self.sources_name + source_path
                except IndexError:
                    print("IndexError notinternal: source path", source_path)
                    source_path = None
            if source_path:
                try:
                    with open(source_path, encoding='utf-8', errors='replace') as f:
                        fulltext = f.read()
                        for lnk in self.links:
                            #print(lnk['originGUID'], " link --- note", note_guid)
                            if note_guid == lnk['originGUID']:
                                lnk['text'] = fulltext
                except Exception as err:
                    print("Error Note text source", source_path, err)
                    logger.warning(str(err))
                    self.parent_textedit.append(_("Cannot read text source from Note: ") + f"{source_path}\n{err}")

    def parse_cases_for_file_variables(self, root):
        """ Parse Cases element for each Case. Look for any file variables (No case name and only one sourceref).
        Fill out file_vars list """

        self.file_vars = []
        children = list(root)
        for el in children:
            if el.tag == "{urn:QDA-XML:project:1.0}Cases":
                # print(el.tag)
                for c in list(el):
                    self.parse_case_for_file_variables(c)

    def parse_case_for_file_variables(self, e_case):
        """ File variables and their values can be stored in the Case element
        Variables for files stored in Case have one SourceRef and no Case name.
        This approach is used by MAXQDA and Quirkos and ?

        <Case guid="d9001bcb-0803-4b06-b4d4-be0accd558a9">
        <VariableValue>
        <VariableRef targetGUID="3ba84074-e1af-4234-9773-1a71bb5c54de"/>
        <TextValue>0</TextValue>
        </VariableValue>
        <VariableValue>
        <VariableRef targetGUID="96868d37-d832-4d19-bf5e-9bd0792ab8e2"/>
        <TextValue>1</TextValue>
        </VariableValue>
        <SourceRef targetGUID="e92903a3-0fdb-473d-9ae2-58b8d1d68014"/>
        </Case>
        """

        if e_case.get("name") is not None:
            return
        ec = list(e_case)
        count = 0
        file_guid = None
        for el in ec:
            # A variable assigned to a source
            if el.tag == "{urn:QDA-XML:project:1.0}SourceRef":
                # print("el source ref tag ", el.tag, el.get(("targetGUID")))
                count += 1
                file_guid = el.get("targetGUID")
        if file_guid is None or count != 1:
            return
        # Get variable details from tags
        ec = list(e_case)
        for el in ec:
            var_guid = None
            value = None
            if el.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                for v_element in list(el):
                    value = None
                    if v_element.tag == "{urn:QDA-XML:project:1.0}VariableRef":
                        var_guid = v_element.get("targetGUID")
                    if v_element.tag in (
                            "{urn:QDA-XML:project:1.0}TextValue", "{urn:QDA-XML:project:1.0}BooleanValue",
                            "{urn:QDA-XML:project:1.0}IntegerValue", "{urn:QDA-XML:project:1.0}FloatValue",
                            "{urn:QDA-XML:project:1.0}DateValue", "{urn:QDA-XML:project:1.0}DateTimeValue"):
                        value = v_element.text
                attr_val = {'file_guid': file_guid, 'var_guid': var_guid, 'value': value}
                # Get attribute name by linking guids
                for attr in self.variables:
                    if attr['guid'] == var_guid:
                        attr_val['name'] = attr['name']
                        break
                self.file_vars.append(attr_val)

    def fill_file_attribute_values(self):
        """ Fill file attributes from file_vars which were extracted from Cases.Case tag.
         Prepared with: parse_cases_for_file_variables. """

        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        sql = "insert into attribute(name, attr_type, value,id,date,owner) values (?,?,?,?,?,?)"
        for s in self.sources:
            for v in self.file_vars:
                if v['file_guid'] == s['guid']:
                    cur.execute(sql, (v['name'], "file", v['value'], s['id'], now_date, self.app.settings['codername']))
        self.app.conn.commit()

    def parse_variables(self, element):
        """ Parse the Variables element.
        Assign 'file' to the variable caseOrFile as a default position.
        NOTE: This is overwritten when it is later checked to be a case or file variable.
        In Cases Case element the SourceRef may refer to a file
        Example format:
        <Variable guid="51dc3bcd-5454-47ff-a4d6-ea699144410d" name="Cases:Age group" typeOfVariable="Text">
        <Description />
        </Variable>

        typeOfVariable: Text, Boolean, Integer, Float, Date, Datetime

        param: element

        return: count of variables
        """

        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        var_count = 0
        for el in list(element):  # element.getchildren():
            # print(el.tag, el.get("name"), el.get("guid"), el.get("typeOfVariable"))
            # <Variable name="Cases:something"> or ?
            name = el.get("name")
            valuetype = el.get("typeOfVariable")
            if valuetype in ("Text", "Boolean", "Date", "DateTime"):
                valuetype = "character"
            if valuetype in ("Integer", "Float"):
                valuetype = "numeric"
            # Default variable type to "file"
            variable = {"name": name, "caseOrFile": "file", "guid": el.get("guid"), "id": None, "memo": "",
                        "valuetype": valuetype}
            # Get the description text
            d_elements = list(el)
            for d in d_elements:
                memo = ""
                # print("Memo ", d.tag)
                if el.tag != "{urn:QDA-XML:project:1.0}Description":
                    memo = d.text
                variable["memo"] = memo

            # Insert variable type into database
            # CaseOrFile is designated 'file'' - to be updated
            try:
                cur.execute(
                    "insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                    (name, now_date, self.app.settings['codername'], variable["memo"], "file", valuetype))
                self.app.conn.commit()
                var_count += 1
                cur.execute("select last_insert_rowid()")
                variable['id'] = cur.fetchone()[0]
            except sqlite3.IntegrityError:
                Message(self.app, _("Variable import error"), _("Variable name already exists: ") + name,
                        "warning").exec()
            # Refer to the variables later
            # To update caseOrFile and to assign attributes
            self.variables.append(variable)
        return [var_count]

    def parse_cases(self, element):
        """ Parse the Cases element.
        Need to parse the element twice.
        First parse: enter Cases into database to generate caseids after insert.
        Enter empty values for Variables for each Case.
        Second parse: read variable values and update in attributes table.

        Quirkos - Case has no name attribute. Case is used to link variables to files

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
        for el in list(element):
            # print("CASE TAG", el.tag, "CASE NAME", el.get("name"), "GUID", el.get("guid"))
            item = {"name": el.get("name"), "guid": el.get("guid"), "owner": self.app.settings['codername'], "memo": "",
                    "caseid": None}
            # Quirkos, MAXQDA: Cases have no name attribute
            if item['name'] is None:
                pass  # File variable, see parse_cases_for_file_variables
            else:
                # Get the description text
                d_elements = list(el)
                item['memo'] = ""
                for d in d_elements:
                    # print("Memo ", d.tag)
                    if d.tag == "{urn:QDA-XML:project:1.0}Description":
                        # print("case memo")
                        item['memo'] = d.text

                # Enter Case into sqlite and keep a copy in  a list
                try:
                    cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)",
                                (item['name'], item['memo'], item['owner'], now_date))
                    self.app.conn.commit()
                    cur.execute("select last_insert_rowid()")
                    item['caseid'] = cur.fetchone()[0]
                    self.cases.append(item)
                    count += 1
                except Exception as err:
                    self.parent_textedit.append(_('Error entering Case into database') + f'\n{err}')
                    logger.warning(f"item: {item}, {err}")

                # Use case_vars to update attribute-type from 'file' to 'case'
                case_vars = []
                # Look for VariableValue tag, extract and enter into attribute table
                for vv in d_elements:
                    guid = None
                    value = None
                    if vv.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                        for v_element in list(vv):
                            value = None
                            if v_element.tag == "{urn:QDA-XML:project:1.0}VariableRef":
                                guid = v_element.get("targetGUID")
                                case_vars.append(guid)
                            if v_element.tag in (
                                    "{urn:QDA-XML:project:1.0}TextValue", "{urn:QDA-XML:project:1.0}BooleanValue",
                                    "{urn:QDA-XML:project:1.0}IntegerValue", "{urn:QDA-XML:project:1.0}FloatValue",
                                    "{urn:QDA-XML:project:1.0}DateValue", "{urn:QDA-XML:project:1.0}DateTimeValue"):
                                value = v_element.text
                        # print(item, guid, value)
                        # Get attribute name by linking guids
                        attr_name = ""
                        for attr in self.variables:
                            if attr['guid'] == guid:
                                attr_name = attr['name']
                        # Insert into the attribute table
                        sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
                        cur.execute(sql,
                                    (
                                        attr_name, value, item['caseid'], 'case', now_date,
                                        self.app.settings['codername']))
                        self.app.conn.commit()

                # Update attribute_type replace 'file' with 'case'
                case_vars = list(set(case_vars))
                sql = "update attribute_type set caseOrFile='case' where attribute_type.name=?"
                for case_var_guid in case_vars:
                    for attr in self.variables:
                        if attr['guid'] == case_var_guid:
                            cur.execute(sql, [attr['name']])
                self.app.conn.commit()
        return count

    def clean_up_case_codes_and_case_text(self):
        """ Some Code guids match the Case guids. So remove these Codes.
        For text selection:
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
        <TextSource guid="a2b94468-80a5-412f-92d6-e900d97b55a6" name="Anna"
        richTextPath="internal://a2b94468-80a5-412f-92d6-e900d97b55a6.docx"
        plainTextPath="internal://a2b94468-80a5-412f-92d6-e900d97b55a6.txt"
        creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime="2019-06-04T05:25:16Z"
        modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime="2019-06-04T05:25:16Z">

        If during import it detects that the external file is not found, it should
        check file location and if not found ask user for the new file location.
        This check occurs in qualcoder.py

        In MAXQDA qdpx folder - there has been one example of text sources wit hthe same name.
        To work around this: Add a suffix to the text source.

        param element: Sources element object

        return: count of sources
        """

        count = 0
        for el in list(element):
            # print(e.tag, e.get("name"))
            if el.tag == "{urn:QDA-XML:project:1.0}TextSource":
                self.pd_value += 1
                self.pd.setValue(self.pd_value)
                self.load_text_source(el)
            if el.tag == "{urn:QDA-XML:project:1.0}PictureSource":
                self.pd_value += 1
                self.pd.setValue(self.pd_value)
                self.load_picture_source(el)
            if el.tag == "{urn:QDA-XML:project:1.0}AudioSource":
                self.pd_value += 1
                self.pd.setValue(self.pd_value)
                self.load_audio_source(el)
            if el.tag == "{urn:QDA-XML:project:1.0}VideoSource":
                self.pd_value += 1
                self.pd.setValue(self.pd_value)
                self.load_video_source(el)
            if el.tag == "{urn:QDA-XML:project:1.0}PDFSource":
                self.pd_value += 1
                self.pd.setValue(self.pd_value)
                self.load_pdf_source(el)
            count += 1
        return count

    def name_creating_user_create_date_source_path_helper(self, element):
        """ Helper method to obtain name, guid, creating user, create date, path type from each source.
         The sources folder can be named: sources or Sources
         MAXQDA uses sources, NVIVO uses Sources
         param:
            element: xml element
        """

        name = element.get("name")
        creating_user_guid = element.get("creatingUser")
        if creating_user_guid is None:
            creating_user_guid = element.get("modifyingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        if create_date is None:
            create_date = element.get("modifiedDateTime")
        if create_date is None:
            # This occurs with the plain text representation of a PDF source.
            create_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%SZ")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        # path_ starts with internal:// or relative:// (with<Project basePath or absolute
        path_ = element.get("path")
        # Sources folder name can be capital or lower case, check and get the correct one
        contents = os.listdir(self.folder_name)
        self.sources_name = "/Sources"
        for i in contents:
            if i == "sources":
                self.sources_name = "/sources"
        # Determine internal or external path
        source_path = ""
        rich_text_path = ""
        path_type = ""
        if path_ is None:
            source_path = self.folder_name + self.sources_name + element.get("plainTextPath").split('internal:/')[1]
            if element.get("richTextPath") is not None:
                rich_text_path = self.folder_name + self.sources_name + element.get("richTextPath").split('internal:/')[1]
            path_type = "internal"
        if path_ is not None and path_.find("internal://") == 0:
            path_ = element.get("path").split('internal:/')[1]
            source_path = self.folder_name + self.sources_name + path_
            if element.get("richTextPath") is not None:
                rich_text_path = self.folder_name + self.sources_name + element.get("richTextPath").split('internal:/')[1]
            path_type = "internal"
        if path_ is not None and path_.find("relative://") == 0:
            source_path = self.base_path + path_.split('relative://')[1]
            path_type = "relative"
        if path_ is not None and path_.find("absolute://") == 0:
            source_path = path_.split('absolute://')[1]
            path_type = "absolute"
        return name, creating_user, create_date, source_path, path_type, rich_text_path

    def load_picture_source(self, element):
        """ Load this picture source.
         Load the description and codings into sqlite.
         Can manage internal and absolute source paths.
         TODO relative import path

        Params:
            element: PictureSource element object
         """

        name, creating_user, create_date, source_path, path_type, rich_text_path = \
            self.name_creating_user_create_date_source_path_helper(element)
        media_path = "/images/" + name  # Default
        if path_type == "internal":
            # Copy file into .qda images folder and rename into original name
            destination = os.path.join(self.app.project_path, "images", name)
            media_path = "/images/" + name
            try:
                shutil.copyfile(source_path, destination)
            except (FileNotFoundError, PermissionError, shutil.SameFileError) as err:
                self.parent_textedit.append(
                    _('Cannot copy Image file from: ') + f"{source_path}\nto: {destination}\n{err}")
        if path_type == "absolute":
            media_path = "images:" + source_path
        if path_type == "relative":
            # TODO check this works
            media_path = "images:" + self.base_path + source_path
            print("relative path", source_path, media_path)
        memo = ""
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = el.text
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
                    (name, memo, creating_user, create_date, media_path, None))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        source = {'name': name, 'id': id_, 'fulltext': "", 'mediapath': media_path, 'memo': memo,
                  'owner': creating_user, 'date': create_date, 'guid': element.get('guid')}
        self.sources.append(source)
        # Parse PictureSelection and VariableValue elements to load codings and variables
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}PictureSelection":
                self.load_codings_for_picture(id_, el)
            if el.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(el, id_, creating_user)

    def load_codings_for_picture(self, id_, element):
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

        first_x = int(element.get("firstX"))
        first_y = int(element.get("firstY"))
        second_x = int(element.get("secondX"))
        second_y = int(element.get("secondY"))
        width = second_x - first_x
        height = second_y - first_y
        memo = element.get("name")
        create_date = element.get("creationDateTime")
        if create_date is None:
            create_date = element.get("modifiedDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        creating_user_guid = element.get("creatingUser")
        if creating_user_guid is None:
            creating_user_guid = element.get("modifyingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        cur = self.app.conn.cursor()
        for el in element:
            if el.tag == "{urn:QDA-XML:project:1.0}Coding":
                # Get the code id from the CodeRef guid
                cid = None
                code_ref = list(el)[0]
                for c in self.codes:
                    if c['guid'] == code_ref.get("targetGUID"):
                        cid = c['cid']
                try:
                    cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,\
                        date, owner) values(?,?,?,?,?,?,?,?,?)", (id_, first_x, first_y,
                                                                  width, height, cid, memo, create_date, creating_user))
                    self.app.conn.commit()
                except sqlite3.IntegrityError:
                    pass

    def load_audio_source(self, element):
        """ Load audio source into .
        Load the description and codings into sqlite.
        Can manage internal and absolute source paths.
        TODO test relative path

        Params:
            element: AudioSource element object
        """

        name, creating_user, create_date, source_path, path_type, rich_text_path = \
            self.name_creating_user_create_date_source_path_helper(element)
        media_path = "/audio/" + name  # Default
        if path_type == "internal":
            # Copy file into .qda audio folder and rename into original name
            destination = os.path.join(self.app.project_path, "audio", name)
            media_path = "/audio/" + name
            try:
                shutil.copyfile(source_path, destination)
            except Exception as err:
                self.parent_textedit.append(
                    _('Cannot copy Audio file from: ') + f"{source_path}\nto: {destination}\n{err}")
        if path_type == "absolute":
            media_path = "audio:" + source_path
        if path_type == "relative":
            # TODO check relative import works
            media_path = f"audio:{self.base_path}{source_path}"
            # print(source_path, media_path)

        memo = ""
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = el.text
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
                    (name, memo, creating_user, create_date, media_path, None))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        source = {'name': name, 'id': id_, 'fulltext': "", 'mediapath': media_path, 'memo': memo,
                  'owner': creating_user, 'date': create_date, 'guid': element.get('guid')}
        self.sources.append(source)

        no_transcript = True
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Transcript":
                no_transcript = False
                self.parse_transcript_with_codings_and_syncpoints(name, id_, el)
        if no_transcript:
            # Create an empty transcription file
            now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            txt_name = name + ".txt"
            cur.execute('insert into source(name,fulltext,mediapath,memo,owner,date) values(?,"","","",?,?)',
                        (txt_name, creating_user, now_date))
            self.app.conn.commit()
        # Parse AudioSelection and VariableValue elements to load codings and variables
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}AudioSelection":
                self.load_codings_for_audio_video(id_, el)
            if el.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(el, id_, creating_user)

    def load_video_source(self, element):
        """ Load this video source into .
        Load the description and codings into sqlite.
        Can manage internal and absolute source paths.
        TODO relative paths to be tested

        Params:
            element: VideoSource element object
        """

        name, creating_user, create_date, source_path, path_type, rich_text_path = \
            self.name_creating_user_create_date_source_path_helper(element)
        media_path = f"/video/{name}"  # Default
        if path_type == "internal":
            # Copy file into .qda video folder and rename into original name
            destination = os.path.join(self.app.project_path, "video", name)
            media_path = f"/video/{name}"
            try:
                shutil.copyfile(source_path, destination)
            except (FileNotFoundError, PermissionError, shutil.SameFileError) as err:
                self.parent_textedit.append(
                    _('Cannot copy Video file from: ') + f"{source_path}\nto: {destination}\n{err}")
        if path_type == "absolute":
            media_path = f"video:{source_path}"
        if path_type == "relative":
            # TODO check relative import works
            media_path = "video:" + self.base_path + source_path
            # print(source_path, media_path)
        memo = ""
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = el.text
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
                    (name, memo, creating_user, create_date, media_path, None))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        av_id = cur.fetchone()[0]
        source = {'name': name, 'id': av_id, 'fulltext': "", 'mediapath': media_path, 'memo': memo,
                  'owner': creating_user, 'date': create_date, 'guid': element.get('guid')}
        self.sources.append(source)

        no_transcript = True
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Transcript":
                no_transcript = False
                self.parse_transcript_with_codings_and_syncpoints(name, av_id, el)
        if no_transcript:
            # Create an empty transcription file
            now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            txt_name = f"{name}.transcribed"
            cur.execute('insert into source(name,fulltext,mediapath,memo,owner,date) values(?,"","","",?,?)',
                        (txt_name, creating_user, now_date))
            self.app.conn.commit()

        # Parse VideoSelection and VariableValue elements to load codings and variables
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}VideoSelection":
                self.load_codings_for_audio_video(av_id, el)
            if el.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(el, av_id, creating_user)

    def parse_transcript_with_codings_and_syncpoints(self, av_name, av_id, element):
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
        if creating_user_guid is None:
            creating_user_guid = element.get("modifyingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        create_date = element.get("creationDateTime")
        if create_date is None:
            create_date = element.get("modifiedDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        # guid = element.get("guid")  # Testing
        # print("guid", element.get("guid"))

        # Load the plain text transcript file into project.
        # Presumes the plain text file is internal
        # TODO rich text path import - UNSURE - IMPORT OR NOT?
        # rich_text_path = element.get("richTextPath")
        # print("rtpath", element.get("richTextPath"))
        plain_text_path = element.get("plainTextPath")
        if plain_text_path[0:11] == "internal://":
            plain_text_path = plain_text_path[11:]
        else:
            logger.debug("Cannot import plain text transcription file - not internal. " + plain_text_path)
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
        # Not Used: contents = os.listdir(self.folder_name)
        source_path = self.folder_name + self.sources_name
        if source_path[-1] != "/":
            source_path += "/"
        source_path += plain_text_path
        # print("Source path: ", source_path)
        # print("Destination: ", destination)
        try:
            shutil.copyfile(source_path, destination)
        except shutil.Error as err:
            msg = _('Cannot copy transcript file from: ') + f"{source_path}\nto: {destination}\n{err}"
            logger.debug(msg)
            self.parent_textedit.append(msg)
        # Load transcription text into database with filename matching and suffixed with .txt
        text = ""
        try:
            # Can get UnicodeDecode Error on Windows so using error handler
            with open(destination, "r", encoding="utf-8", errors="backslashreplace") as sourcefile:
                while 1:
                    line = sourcefile.readline()
                    if not line:
                        break
                    try:
                        text += line
                    except UnicodeDecodeError:
                        pass
                if text[0:6] == "\ufeff":  # Associated with notepad files
                    text = text[6:]
        except Exception as err:
            print(err)
            logger.debug(str(err))
            Message(self.app, _("Warning"), _("Cannot import") + f"{destination}\n{err}", "warning").exec()

        memo = ""
        if name is not None:
            memo = f"Name: {name}\n"
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Description":
                if el.text is not None:
                    memo += el.text
        transcript_filename = f"{av_name}.txt"
        cur = self.app.conn.cursor()
        sql = "insert into source (name, fulltext, mediapath, memo, owner, date, av_text_id) values (?,?,?,?,?,?,?)"
        cur.execute(sql, [transcript_filename, text, None, memo, creating_user, create_date, av_id])
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        fid = cur.fetchone()[0]

        # Syncpoints
        # TODO syncpoints are not stored in QualCoder - unsure how to make use of the timestamps
        # Perhaps add syncpoint timestamps from and to into the code_text table ?
        syncpoints = []
        """ Format:
        <SyncPoint guid="58716919-f62e-4f2a-b386-6ceb1ebbd859" position="3044" timeStamp="155000" />
        """
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}SyncPoint":
                syncpoints.append({"guid": el.get("guid"), "pos": el.get("position"), "timestamp": el.get("timeStamp")})

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
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}TranscriptSelection":
                pos0 = 0
                pos1 = 0
                guid_pos0 = el.get("fromSyncPoint")
                guid_pos1 = el.get("toSyncPoint")
                for s in syncpoints:
                    if guid_pos0 == s['guid']:
                        # TODO test pos0 and 1 are correct, added 1 for python as String starts from 0
                        pos0 = int(s['pos']) + 1
                    if guid_pos1 == s['guid']:
                        pos1 = int(s['pos']) + 1
                memo = ""
                for el_child in list(el):
                    if el_child.tag == "{urn:QDA-XML:project:1.0}Description":
                        memo = str(el_child.text)
                for el_child in list(el):
                    if el_child.tag == "{urn:QDA-XML:project:1.0}Coding":
                        code_ref = list(el_child)[0]
                        for c in self.codes:
                            if c['guid'] == code_ref.get("targetGUID"):
                                cid = c['cid']
                                value_list.append(
                                    [cid, fid, text[pos0:pos1], pos0, pos1, creating_user, create_date, memo, av_id])
        sql = "insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo, avid) "
        sql += " values (?,?,?,?,?,?,?,?,?)"
        cur = self.app.conn.cursor()
        for v in value_list:
            cur.execute(sql, v)
        self.app.conn.commit()

    def load_codings_for_audio_video(self, id_, element):
        """ Load coded segments for audio and video
        Example format:
        <VideoSelection begin="115" modifyingUser="5D2B49D0-9562-4DD3-9EE3-CE2B965E413C" end="1100"
        guid="BB652E1B-5CCC-4AA3-9C7F-E5D9BD99F6BF"
        creatingUser="5D2B49D0-9562-4DD3-9EE3-CE2B965E413C" creationDateTime="2020-11-10T18:01:23Z"
        name="(115,0),(1100,0)" modifiedDateTime="2020-11-10T18:01:23Z">
        <Description>Memo to video file</Description>
        <Coding guid="2E0A7A4D-453B-4A1B-9784-4FC5B8432816" creatingUser="5D2B49D0-9562-4DD3-9EE3-CE2B965E413C"
        creationDateTime="2020-11-10T18:01:23Z">
        <CodeRef targetGUID="86392BC1-A364-4904-A406-87A7E025EBF7"/>
        </Coding>
        </VideoSelection>
        """

        seg_start = int(element.get("begin"))
        seg_end = int(element.get("end"))
        create_date = element.get("creationDateTime")
        if create_date is None:
            create_date = element.get("modifiedDateTime")
        if create_date is None:
            # Create another date if no element is found
            create_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d_%H:%M:%S")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        creating_user_guid = element.get("creatingUser")
        if creating_user_guid is None:
            creating_user_guid = element.get("modifyingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']

        cur = self.app.conn.cursor()
        memo = ""
        for el in element:
            if el.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = el.text
                if memo is None:
                    memo = ""
        for el in element:
            if el.tag == "{urn:QDA-XML:project:1.0}Coding":
                # Get the code id from the CodeRef guid
                cid = None
                code_ref = list(el)[0]
                for c in self.codes:
                    if c['guid'] == code_ref.get("targetGUID"):
                        cid = c['cid']
                try:
                    cur.execute("insert into code_av (id,pos0,pos1,cid,memo,\
                        date, owner) values(?,?,?,?,?,?,?)", (id_, seg_start, seg_end,
                                                              cid, memo, create_date, creating_user))
                    self.app.conn.commit()
                except sqlite3.IntegrityError:
                    pass

    def load_pdf_source(self, element):
        """ Load the pdf and text representation into sqlite.
        Can manage internal and absolute source paths.
        TODO test relative path

        Params:
            element: PDFSource element object
        """

        name, creating_user, create_date, source_path, path_type, rich_text_path = \
            self.name_creating_user_create_date_source_path_helper(element)
        # pdf suffix may need to be added on
        if name.lower()[-4:] != ".pdf":
            name += ".pdf"
        #print("source path: ", source_path)
        #print("name: ", name)
        media_path = f"/docs/{name}"  # Default
        if path_type == "internal":
            # Copy file into .qda documents folder and rename into original name
            destination = os.path.join(self.app.project_path, "documents", name)
            #print("destination: ", destination)
            try:
                shutil.copyfile(source_path, destination)
                # print("PDF IMPORT", source_path, destination)
            except Exception as err:
                self.parent_textedit.append(
                    _('Cannot copy PDF file from: ') + f"{source_path}\nto: {destination}\n{err}")
        if path_type == "absolute":
            media_path = f"docs:{source_path}"
        if path_type == "relative":
            media_path = f"docs:{self.base_path}{source_path}"
            # print(source_path, media_path)
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
        for el in element:
            if el.tag == "{urn:QDA-XML:project:1.0}Representation":
                # print("PDF Representation element found")
                self.load_text_source(el, name, create_date, media_path)
                break

    def load_text_source(self, element, pdf_rep_name="", pdf_rep_date="", mediapath=None):
        """ Load this text source into sqlite.
         Add the description and the text codings.
         When testing with Windows Nvivo export: import from docx or txt
         The text may need an additional line-ending character for Windows: \r\n
        Can manage internal and absolute source paths.

        Params:
        :name element: TextSource element object
        :type element: etree element
        :name pdf_rep_name: Name of the PDF file
        :type pdf_rep_name: String
        :name pdf_rep_date: Creation date of the PDF file
        :type pdf_rep_date: String
        :name mediapath: Path to media
        :type mediapath: String
         """

        # TODO absolute and relative - not tested relative
        name, creating_user, create_date, source_path, path_type, rich_text_path = \
            self.name_creating_user_create_date_source_path_helper(element)
        for s in self.sources:
            if name == s['name']:
                logger.warning(f"source name duplicated. Adding prefix: {name}")
                self.source_name_prefix += 1
                name = f"{self.source_name_prefix}_{name}"
                self.parent_textedit.append(f"source name duplicated. Adding prefix: {name}")
                break
        if pdf_rep_name != "":
            # contains .pdf
            name = pdf_rep_name
        if pdf_rep_date != "":
            create_date = pdf_rep_date
        cur = self.app.conn.cursor()
        # Find Description to complete memo
        memo = ""
        for el in list(element):  # element.getchildren():
            if el.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = el.text
        source = {'name': name, 'id': -1, 'fulltext': "", 'mediapath': mediapath, 'memo': memo,
                  'owner': self.app.settings['codername'], 'date': create_date, 'guid': element.get('guid')}

        # Check plain text file line endings for Windows 2 character \r\n
        add_ending = False
        with open(source_path, "rb") as f:
            while True:
                c = f.read(1)
                if not c or c == b'\n':
                    break
                if c == b'\r':
                    if f.read(1) == b'\n':
                        # print('rn')
                        add_ending = True
                    # print('r')
                    pass
            # print('n')

        """Atlas stored correct positions in the project.qde xml
        as though it is \n  - one character
        But the source.txt stores \r\n and in ATLAS is treated at one character 
        To test for docx also """
        if "ATLAS" in self.software_name:
            add_ending = False

        # Read the text and enter into sqlite source table
        try:
            with open(source_path, encoding='utf-8', errors='replace') as f:
                fulltext = f.read()
                # Replace fixes mismatched coding with line endings on import from Windows text files.
                # Due to 2 character line endings
                if fulltext is not None and add_ending:
                    fulltext = fulltext.replace('\n', '\n ')
                source['fulltext'] = fulltext
                # Adding split()- DOnt know why ?? - Removed
                # OLD CODE: name + "." + source_path.split('.')[-1]
                # NEW CODE: name
                cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                            (name, fulltext, source['mediapath'], memo,
                             creating_user, create_date))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                id_ = cur.fetchone()[0]
                source['id'] = id_
                self.sources.append(source)
        except Exception as err:
            print("Error text source", err)
            logger.warning(str(err))
            self.parent_textedit.append(_("Cannot read from TextSource: ") + f"{source_path}\n{err}")

        if path_type == "internal":
            # Copy file into .qda documents folder and rename into original name
            destination = f"{self.app.project_path}/documents/{name}.{source_path.split('.')[-1]}"
            #print("source", source_path)
            #print("dest", destination)
            try:
                shutil.copyfile(source_path, destination)
            except Exception as err:
                logger.warning(str(err))
                self.parent_textedit.append(
                    _('Cannot copy TextSource file from: ') + f"{source_path}\nto: {destination}\n{err}")
            # If present, copy rich text file into .qda documents folder and rename into original name
            if rich_text_path != "":
                rtf_destination = f"{self.app.project_path}/documents/{name}.{rich_text_path.split('.')[-1]}"
                #print("rtf source", rich_text_path)
                #print("dest", rtf_destination)
                cur.execute("update source set mediapath=? where id=?", [f"/docs/{name}.{rich_text_path.split('.')[-1]}",
                                                                         source['id']])
                self.app.conn.commit()
                try:
                    shutil.copyfile(rich_text_path, rtf_destination)
                except Exception as err:
                    logger.warning(str(err))
                    self.parent_textedit.append(
                        _('Cannot copy TextSource file from: ') + f"{rich_text_path}\nto: {rtf_destination}\n{err}")

        # Parse PlainTextSelection elements for Coding elements
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}PlainTextSelection":
                self.load_codings_for_text(source, el)
        # Parse PlainTextSelection elements for NoteRef (annotation) elements
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}NoteRef":
                self.annotations.append({"NoteRef": el.get("targetGUID"), "TextSource": source["guid"]})
        # Parse elements for VariableValues
        # This approach used by MAXQDA but not by QUIRKOS
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}VariableValue":
                self.parse_variable_value(el, id_, creating_user)

    def parse_variable_value(self, element, id_, creating_user):
        """ Parse VariableValue element.
        Needs two parses - one to get the variable name and one to get the value.
        Enter details into attributes table.
        This is for when variables are stored within the Source element.

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
        for var_el in list(element):
            if var_el.tag == "{urn:QDA-XML:project:1.0}VariableRef":
                guid = var_el.get("targetGUID")
                for v in self.variables:
                    if v['guid'] == guid:
                        var_name = v['name']
                        break
        # Need to parse the element children twice, otherwise may miss the needed element
        for var_el in list(element):
            if var_el.tag in value_types and var_el.text is not None:
                value = var_el.text
                value = value.strip()
        # print("Text attribute:", var_name, " value:",value)  # tmp
        cur = self.app.conn.cursor()
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file',?,?,?,?)"
        placeholders = [var_name, value, id_, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), creating_user]
        cur.execute(insert_sql, placeholders)
        self.app.conn.commit()

    def load_codings_for_text(self, source, element):
        """ These are PlainTextSelection elements.
        These elements contain a Coding element and a Description element.
        The Description element is treated as a coding memo.

        NOTE: MAXQDA. Some PlainTextSelection elements DO NOT have a Coding element, but DO HAVE a Description element.
        For these, load the Description text as an annotation.

        NOTE: Nvivo some PlainTextSelection elements linkto Link and Note as text annotations

        Some Coding guids match a Case guid. This is Case text.

        Example format:
        < PlainTextSelection guid = "08cbced0-d736-44c8-8fd6-eb4d29fe46c5" name = "" startPosition = "1967"
        endPosition = "2207" creatingUser = "5c94bc9e-db8c-4f1d-9cd6-e900c7440860" creationDateTime = "2019-06-07T03:36:36Z"
        modifyingUser = "5c94bc9e-db8c-4f1d-9cd6-e900c7440860" modifiedDateTime = "2019-06-07T03:36:36Z" >
        < Description / > or <Description>some text</Description>
        < Coding guid = "76414714-63c4-4a25-a47e-66fef80bd52e" creatingUser = "5c94bc9e-db8c-4f1d-9cd6-e900c7440860"
        creationDateTime = "2019-06-06T06:27:01Z" >
        < CodeRef targetGUID = "2dfba8c9-59f5-4424-99d6-ea9bce18134b" / >
        < / Coding >
        < / PlainTextSelection >

        :param source - the source text dictionary
        :param element - the PlainTextSelection element
        """

        cur = self.app.conn.cursor()
        pos0 = int(element.get("startPosition"))
        pos1 = int(element.get("endPosition"))
        create_date = element.get("creationDateTime")
        if create_date is None:
            create_date = element.get("modifiedDateTime")
        create_date = create_date.replace('T', ' ')
        create_date = create_date.replace('Z', '')
        creating_user_guid = element.get("creatingUser")
        if creating_user_guid is None:
            creating_user_guid = element.get("modifyingUser")
        creating_user = "default"
        for u in self.users:
            if u['guid'] == creating_user_guid:
                creating_user = u['name']
        seltext = source['fulltext'][pos0:pos1]

        # The Description element text inside a PlainTextSelection is a coding memo
        memo = ""
        for el in element:
            if el.tag == "{urn:QDA-XML:project:1.0}Description" and el.text is not None:
                memo = el.text
        annotation = True
        for el in element:
            if el.tag == "{urn:QDA-XML:project:1.0}Coding":
                annotation = False
                # Get the code id from the CodeRef guid
                cid = None
                code_ref = list(el)[0]
                for c in self.codes:
                    if c['guid'] == code_ref.get("targetGUID"):
                        cid = c['cid']
                try:
                    cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                        memo,date) values(?,?,?,?,?,?,?,?)", (cid, source['id'],
                                                              seltext, pos0, pos1, creating_user, memo, create_date))
                    self.app.conn.commit()
                except sqlite3.IntegrityError:
                    self.parent_textedit.append(_("Duplicated text coding for code and coder. Only one loaded.") +
                                                " cid:" + str(cid) + " fid: " + str(source['id']) + _(" Positions:") +
                                                str(pos0) + " - " + str(pos1))
        if annotation:
            if memo == "":
                """ Nvivo stores text annotations as txt/docx documents. These are references in a Note.
                PlainTextSelection guid links to the Link targetGUID.
                The Link originGUID links to Note guid.
                The Note should contain the plainTextPath to the annotation text in a .txt file.
                """
                for lnk in self.links:
                    if lnk['targetGUID'] == element.get('guid'):
                        try:
                            memo = lnk['text']
                        except KeyError:
                            pass
            sql = "insert into annotation (fid,pos0,pos1,memo,owner,date) values (?,?,?,?,?,?)"
            cur.execute(sql, [source['id'], int(pos0), int(pos1), memo, creating_user, create_date])
            self.app.conn.commit()

    def parse_notes(self, notes_element):
        """ Parse the Notes element.
        Notes may be journal entries or text annotations.
        Example journal format:
        <Note guid="4691a8a0-d67c-4dcc-91d6-e9075dc230cc" name="Assignment Progress Memo"
        richTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.docx"
        plainTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.txt"
        creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860"
        creationDateTime="2019-06-04T06:11:56Z"
        modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860"
        modifiedDateTime="2019-06-17T08:00:58Z">
        <Description>Steps towards completing the assignment</Description>
        </Note>

        Annotation Note:
        <Note guid="0f758eeb-d61d-4e91-b250-79861c3869a6" modifyingUser="df241da2-bca0-4ad9-83c1-b89c98d83567"
        modifiedDateTime="2021-01-15T23:37:54Z" >
        <PlainTextContent>Memo for only title coding in regulation</PlainTextContent>
        <PlainTextSelection guid="d61907b2-d0d4-48dc-b8b7-5e4f7ae5faa6" startPosition="455" endPosition="596" />
        </Note>

        called by: import_project

        param: element Notes

        return: count of journals, count of annotations
        """

        cur = self.app.conn.cursor()
        journal_count = 0
        for el in list(notes_element):
            #print("Notes xml\n", el.tag, el.get("name"), el.get("plainTextPath"), el.get("guid"))
            name = el.get("name")
            create_date = el.get("creationDateTime")
            if create_date is None:
                create_date = el.get("modifiedDateTime")
            create_date = create_date.replace('T', ' ')
            create_date = create_date.replace('Z', '')
            creating_user_guid = el.get("creatingUser")
            if creating_user_guid is None:
                creating_user_guid = el.get("modifyingUser")
            creating_user = "default"
            for u in self.users:
                if u['guid'] == creating_user_guid:
                    creating_user = u['name']

            # Check if the Note is a TextSource Annotation with Text stored in the Note
            # Text annotation can be as a plainTextPath from the note. This is obtained when getting Links
            annotation = False
            for a in self.annotations:
                if a['NoteRef'] == el.get("guid"):
                    annotation = True
                    self.insert_annotation(a['TextSource'], el)
                    break
            # Check annotations have not already be resolved via parsing PlainTextSelection Link to Notes
            for lnk in self.links:
                if lnk['targetGUID'] == el.get('guid'):
                    if lnk.get('text'):
                        annotation = True

            # Presumes Journal paths starts with internal://
            if el.get("plainTextPath") is not None and not annotation and name != "":
                path_ = el.get("plainTextPath").split('internal:/')[1]
                # Folder can be named: sources or Sources
                path_ = self.folder_name + self.sources_name + path_
                jentry = ""
                try:
                    with open(path_) as f:
                        jentry = f.read()
                except Exception as err:
                    self.parent_textedit.append(_('Trying to read Note element: ') + f"{path_}\n{err}")
                # Check journal name does not exist. If it exists, add 3 random numbers, fix for Integrity Error
                cur.execute("select name from journal where name=?", [name])
                name_exists = cur.fetchone()
                cur.execute("insert into journal(name,jentry,owner,date) values(?,?,?,?)",
                                (name, jentry, creating_user, create_date))
                self.app.conn.commit()
                journal_count += 1
        return journal_count

    def insert_annotation(self, source_guid, element):
        """ Insert annotation into database
        Annotation Note:
        <Note guid="0f758eeb-d61d-4e91-b250-79861c3869a6" modifyingUser="df241da2-bca0-4ad9-83c1-b89c98d83567"
        modifiedDateTime="2021-01-15T23:37:54Z" >
        <PlainTextContent>Memo for only title coding in regulation</PlainTextContent>
        <PlainTextSelection guid="d61907b2-d0d4-48dc-b8b7-5e4f7ae5faa6" startPosition="455" endPosition="596" />
        </Note>

        param: source_guid : guid of the Text source
        param: element The Note element
        """

        user_guid = element.get("modifyingUser")
        owner = None
        for u in self.users:
            if u['guid'] == user_guid:
                owner = u['name']
        if owner is None:
            user_guid = element.get("creatingUser")
            for u in self.users:
                if u['guid'] == user_guid:
                    owner = u['name']
        if owner is None:
            owner = self.app.settings['codername']
        date = element.get("modifiedDateTime")
        if date is not None:
            date = date.replace('T', ' ')
            date = date.replace('Z', '')
        else:
            date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        memo = ""
        pos0 = None
        pos1 = None
        for el in element:
            if el.tag == "{urn:QDA-XML:project:1.0}PlainTextContent":
                memo = el.text
            if el.tag == "{urn:QDA-XML:project:1.0}PlainTextSelection":
                pos0 = el.get("startPosition")
                pos1 = el.get("endPosition")
        if pos0 is None or pos1 is None or memo is None:
            # print("None values ", pos0, pos1, memo)
            return
        fid = None
        for s in self.sources:
            if source_guid == s['guid']:
                fid = s['id']
        if fid is None:
            return
        cur = self.app.conn.cursor()
        sql = "insert into annotation (fid,pos0,pos1,memo,owner,date) values (?,?,?,?,?,?)"
        cur.execute(sql, [fid, int(pos0), int(pos1), memo, owner, date])
        self.app.conn.commit()

    def parse_sets(self, element):
        """ Parse the Sets element

        <Sets>
        <Set name="Document group 1" guid="46467993-B426-49DD-9707-B5958EBA9870">
        <Description>Memo to document group</Description>
        <MemberSource targetGUID="631251CC-9FB4-4131-BEA8-35947084C409"/>
        <MemberSource targetGUID="9DDD19C4-168C-4103-BBAD-08D4BD10A145"/>
        </Set>
        </Sets>
        """

        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Set":
                self.parse_set(el)

    def parse_set(self, element):
        """ Parse the Set element

        <Set name="Document group 1" guid="46467993-B426-49DD-9707-B5958EBA9870">
        <Description>Memo to document group</Description>
        <MemberSource targetGUID="631251CC-9FB4-4131-BEA8-35947084C409"/>
        <MemberSource targetGUID="9DDD19C4-168C-4103-BBAD-08D4BD10A145"/>
        </Set>
        """

        name = element.get("name")
        memo = ""
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}Description":
                memo = el.text
                if memo is None:
                    memo = ""
                break
        set_sources = []  # List of sources associated with this Set
        for el in list(element):
            if el.tag == "{urn:QDA-XML:project:1.0}MemberSource":
                target_guid = el.get("targetGUID")
                for s in self.sources:
                    if target_guid == s['guid']:
                        set_sources.append(s['id'])
        if set_sources:
            self.insert_set_source_variables(name, memo, set_sources)

    def insert_set_source_variables(self, name, memo, set_sources):
        """ Insert the variable name and values for the set source.
        Assume the variable is a character type
        param: name : the variable name
        param: memo : variable memo
        param: set_sources : list of source ids """

        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        try:
            cur.execute(
                "insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                (name, now_date, self.app.settings['codername'], memo, "file", "character"))
            self.app.conn.commit()
            cur.execute("select last_insert_rowid()")
        except sqlite3.IntegrityError:
            Message(self.app, _("Variable import error"), _("Variable name already exists: ") + name, "warning").exec()
            return

        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file',?,?,?,?)"
        for id_ in set_sources:
            placeholders = [name, name, id_, now_date, self.app.settings['codername']]
            cur.execute(insert_sql, placeholders)
            self.app.conn.commit()

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
        cur.execute("update project set memo = ?", (memo,))
        self.app.conn.commit()

    def parse_project_tag(self, element):
        """ Parse the Project tag.
        Interested in basePath for relative linked sources.
         software name for ATLAS.ti for line endings issue where txt source is \r\n but within ATLAS it is just \n """
        self.base_path = element.get("basePath")
        # print("BASEPATH ", self.base_path, type(self.base_path))  # tmp
        self.software_name = element.get("origin")
        # print("SOFTWARE NAME: ", self.software_name)

    def parse_users(self, element):
        """ Parse Users element children, fill list with guid and name.
        There is no user table in QualCoder sqlite.
        Store each user in dictionary with name and guid.

        param element: Users element
        type element: xml tag

        return count of users
        """

        count = 0
        for el in list(element):
            # print(e.tag, el.get("name"), el.get("guid"))
            self.users.append({"name": el.get("name"), "guid": el.get("guid")})
            count += 1
        return count

    def xml_validation(self, xsd_type="codebook"):
        """ Verify that the XML complies with XSD
        NOT USED. Problems geting the original validator to work.
        Arguments:
            1. file_xml: Input xml file
            2. file_xsd: xsd file which needs to be validated against xml

        param: xsd_type codebook or project

        return: true or false passing validation
        """

        file_xsd = xsd_codebook
        if xsd_type != "codebook":
            file_xsd = xsd_project
        return True


class RefiLineEndings(QtWidgets.QDialog):
    """ Refi line endings dialog."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog_refi_export_line_endings()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {app.settings["fontsize"]}pt '
        font += f'"{app.settings["font"]}";'
        self.setStyleSheet(font)


class RefiExport(QtWidgets.QDialog):
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
    note_files = []  # List of Dictionaries of guid.txt name and note text
    annotations = []  # List of Dictionaries of anid, fid, pos0, pos1, memo, owner, date
    variables = []  # List of Dictionaries of variable xml, guid, name
    xml = ""
    parent_textedit = None
    app = None
    tree = None
    export_type = ""

    def __init__(self, app, parent_textedit, export_type):

        super().__init__()
        self.app = app
        self.parent_textedit = parent_textedit
        self.export_type = export_type
        self.xml = ""
        self.get_categories()
        self.get_codes()
        self.get_users()
        self.get_sources()
        self.annotations = self.app.get_annotations()
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

        #TODO put file variables inside Cases.Case elements as with Quirkos
        """

        project_name = self.app.project_name[:-4]
        prep_path = os.path.join(os.path.expanduser('~'), '.qualcoder', project_name)
        try:
            shutil.rmtree(prep_path)
        except FileNotFoundError:
            pass
        try:
            os.mkdir(prep_path)
            os.mkdir(os.path.join(prep_path, "Sources"))
        except Exception as err:
            logger.error(_("Project export error ") + str(err))
            Message(self.app, _("Project"), _("Project not exported. Exiting. ") + str(err), "warning").exec()
            return
        try:
            with open(os.path.join(prep_path, 'project.qde'), 'w', encoding='utf-8-sig') as f:
                f.write(self.xml)
        except Exception as err:
            Message(self.app, _("Project"), _("Project not exported. Exiting. ") + str(err), "warning").exec()
            logger.debug(str(err))
            return

        add_line_ending_for_maxqda = False
        ui = RefiLineEndings(self.app)
        ui.exec()
        if ui.ui.radioButton_maxqda.isChecked():
            add_line_ending_for_maxqda = True
        txt_errors = ""
        for s in self.sources:
            #print(s['id'], s['name'], s['mediapath'], s['filename'], s['plaintext_filename'], s['external'])
            destination = f"/Sources/{s['filename']}"
            if s['mediapath'] is not None and s['mediapath'] != "" and s['external'] is None:
                #print("Source\n", self.app.project_path + s['mediapath'].replace("/docs/", "/documents/"))
                #print("dest\n", prep_path + destination)
                try:
                    shutil.copyfile(self.app.project_path + s['mediapath'].replace("/docs/", "/documents/"),
                                prep_path + destination)
                except FileNotFoundError as err:
                    print(err)
                    logger.warning(err)

            if (s['mediapath'] is None or s['mediapath'] == "") and s['external'] is None:  # an internal document
                try:
                    shutil.copyfile(os.path.join(self.app.project_path, 'documents', s['name']),
                                    prep_path + destination)
                except FileNotFoundError:
                    with open(prep_path + destination, 'w', encoding="utf-8-sig") as f:
                        f.write(s['fulltext'])
            # Also need to export a plain text file as a source
            # plaintext has different guid from richtext, and also might be associated with media - eg transcripts
            if s['plaintext_filename'] is not None:
                with open(os.path.join(prep_path, 'Sources', s['plaintext_filename']), "w", encoding="utf-8-sig") as f:
                    try:
                        if add_line_ending_for_maxqda:
                            f.write(s['fulltext'].replace("\n", "\r\n"))
                        else:
                            f.write(s['fulltext'])
                    except Exception as err:
                        #txt_errors += '\nIn plaintext file export: ' + s['plaintext_filename'] + "\n" + str(err)
                        logger.error(f"{err}\nIn plaintext file export: {s['plaintext_filename']}")
                        print(err)

        for notefile in self.note_files:
            with open(os.path.join(prep_path, 'Sources', notefile[0]), "w", encoding="utf-8-sig") as f:
                f.write(notefile[1])
        options = QtWidgets.QFileDialog.Option.DontResolveSymlinks | QtWidgets.QFileDialog.Option.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                               _("Select directory to save file"),
                                                               self.app.settings['directory'], options)

        export_path = f"{directory}/{self.app.project_name[:-4]}"
        shutil.make_archive(prep_path, 'zip', prep_path)
        os.rename(prep_path + ".zip", prep_path + ".qdpx")

        # Add suffix to project name if it already exists
        counter = 0
        while os.path.exists(f"{export_path}.qdpx"):
            extension = ""
            if counter > 0:
                extension = f"_{counter}"
            export_path = export_path + extension
            counter += 1

        shutil.copyfile(f"{prep_path}.qdpx", f"{export_path}.qdpx")
        try:
            shutil.rmtree(prep_path)
            os.remove(f"{prep_path}.qdpx")
        except FileNotFoundError as err:
            logger.warning(str(err))
        msg = export_path + ".qpdx\n"
        msg += _("REFI-QDA PROJECT EXPORT EXPERIMENTAL FUNCTION.\n")
        msg += _("This project exchange is not guaranteed compliant with the exchange standard.\n")
        if txt_errors != "":
            msg += "\nErrors: "
            msg += txt_errors
        Message(self.app, _("Project exported"), _(msg)).exec()
        self.parent_textedit.append(_("Project exported") + "\n" + msg)

    def export_codebook(self):
        """ Export REFI format codebook. """

        filename = "Codebook-" + self.app.project_name[:-4] + ".qdc"
        options = QtWidgets.QFileDialog.Option.DontResolveSymlinks | QtWidgets.QFileDialog.Option.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                               _("Select directory to save file"),
                                                               self.app.settings['directory'], options)
        if directory == "":
            return
        filename = os.path.join(directory, filename)
        try:
            with open(filename, 'w', encoding='utf-8-sig') as f:
                f.write(self.xml)
            msg = _("Codebook has been exported to ")
            msg += filename
            Message(self.app, _("Codebook exported"), _(msg)).exec()
            self.parent_textedit.append(_("Codebook exported") + "\n" + _(msg))
        except Exception as err:
            logger.warning(str(err))
            Message(self.app, _("Codebook NOT exported"), str(err)).exec()
            self.parent_textedit.append(_("Codebook NOT exported") + f"\n{err}")

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
        self.xml += f'name="{html.escape(self.app.project_name)}" '
        self.xml += f'origin="{self.app.version}" '
        # There is no creating user in QualCoder
        guid = self.create_guid()
        self.xml += f'creatingUserGUID="{guid}" '
        cur = self.app.conn.cursor()
        cur.execute("select date from project")
        result = cur.fetchone()
        self.xml += f'creationDateTime="{self.convert_timestamp(result[0])}" '
        # self.xml += 'basePath="' + self.app.settings['directory'] + '" '
        self.xml += 'xmlns="urn:QDA-XML:project:1.0"'
        self.xml += '>\n'
        # Add users
        self.xml += "<Users>\n"
        for row in self.users:
            self.xml += f'<User guid="{row["guid"]}" name="{html.escape(row["name"])}" />\n'
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
        Called by project_xml.
        TODO not sure how to handle empty (N/A) numeric variables.
        TODO xs:decimal schema does not allow for null values
        TODO I do not inssert the floatvalue tag!
        <VariableRef targetGUID="7d936548-f82a-4819-9315-a7aa81b61bc3" />
        <FloatValue></FloatValue></VariableValue>

        :returns xml string
        """

        self.variables = []
        xml = ""
        cur = self.app.conn.cursor()
        cur.execute("select name, memo, caseOrFile,valuetype from attribute_type")
        results = cur.fetchall()
        if not results:
            return xml
        xml = '<Variables>\n'
        for r in results:
            guid = self.create_guid()
            xml += f'<Variable guid="{guid}" '
            xml += f'name="{html.escape(r[0])}" '
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
                xml += f"<Description>{html.escape(r[1])}</Description>\n"
            xml += '</Variable>\n'
            self.variables.append({'guid': guid, 'name': r[0], 'caseOrFile': r[2], 'type': r[3]})
        xml += '</Variables>\n'
        return xml

    def project_description_xml(self):
        """ Create overall project description memo xml.
        :returns xml string of project description
        """

        cur = self.app.conn.cursor()
        cur.execute("select memo from project")
        results = cur.fetchall()
        if not results:  # this should not happen
            return '<Description />\n'
        memo = str(results[0][0])
        xml = f"<Description>{html.escape(memo)}</Description>\n"
        return xml

    def create_journal_note_xml(self, journal):
        """ Create a Note xml for journal entries
        To be appended to the in notes list. To add to the Notes element
        Appends file name and journal text in notes_files list. This is exported to Sources folder.
        Called by: notes_xml
        Format:
        <Note guid="4691a8a0-d67c-4dcc-91d6-e9075dc230cc" name="Assignment Progress Memo"
        richTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.docx"
        plainTextPath="internal://4691a8a0-d67c-4dcc-91d6-e9075dc230cc.txt"
        creatingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860"
        creationDateTime="2019-06-04T06:11:56Z"
        modifyingUser="5c94bc9e-db8c-4f1d-9cd6-e900c7440860"
        modifiedDateTime="2019-06-17T08:00:58Z">
       <Description></Description>
       </Note>

        :param journal: [0] name is the name of the journal entry
        [1] the text of the journal entry
        [2] the creation datetime of the entry
        [3] user is the user who created the entry
        :type journal: List

        :returns a guid for a NoteRef
        """

        guid = self.create_guid()
        xml = f'<Note guid="{guid}" '
        xml += f'creatingUser="{self.user_guid(journal[3])}" '
        xml += f'creationDateTime="{self.convert_timestamp(journal[2])}" '
        xml += f'name="{html.escape(journal[0])}" '
        xml += f' plainTextPath="internal://{guid}.txt" >\n'
        # xml += '<PlainTextContent>' + text + '</PlainTextContent>\n'
        # Add blank Description tag for the journal entry, as these are not memoed
        xml += '<Description />'
        xml += '</Note>\n'
        self.note_files.append([guid + '.txt', journal[1]])
        return xml

    def create_annotation_note_xml(self, ann):
        """ Create a Note xml for text source annotations
        Appends xml in notes list.
        Appends to the annotations list
        Called by: ??? notes_xml

        Format:
        Annotation Note:
        <Note guid="0f758eeb-d61d-4e91-b250-79861c3869a6" modifyingUser="df241da2-bca0-4ad9-83c1-b89c98d83567"
        modifiedDateTime="2021-01-15T23:37:54Z" >
        <PlainTextContent>Memo for only title coding in regulation</PlainTextContent>
        <PlainTextSelection guid="d61907b2-d0d4-48dc-b8b7-5e4f7ae5faa6" startPosition="455" endPosition="596" />
        </Note>

        Inside <TextSource> is <NoteRef targetGUID="0f758eeb-d61d-4e91-b250-79861c3869a6"/>
        Links to the annotation detail.

        :param ann: Dictionaries of anid, fid, pos0, pos1, memo, owner, date,  NoteRef_guid
        :returns a guid for a NoteRef
        """

        # Temporary hack fix for NoteRef_guid, unsure of the cuase so far, might be ajournal entry
        try:
            ann['NoteRef_guid']
        except KeyError:
            ann['NoteRef_guid'] = self.create_guid()

        xml = f'<Note guid="{ann["NoteRef_guid"]}" '
        user = ""
        for u in self.users:
            if u['name'] == ann['owner']:
                user = u['guid']
                break
        xml += f'creatingUser="{user}" '
        xml += f'creationDateTime="{self.convert_timestamp(ann["date"])}" >\n'
        xml += f"<PlainTextContent>{ann['memo']}</PlainTextContent>\n"
        guid = self.create_guid()
        xml += f'<PlainTextSelection guid="{guid}" startPosition="{ann["pos0"]}" '
        xml += f'endPosition="{ann["pos1"]}" />\n'
        xml += '</Note>\n'
        return xml

    def notes_xml(self):
        """ Get journal entries and store them as Notes.
        Collate note_xml list into final xml
        <Notes><Note></Note></Notes>
        Note xml requires a NoteRef in the source or case.
        Called by: project_xml

        :returns xml
        """

        # Get journal entries
        cur = self.app.conn.cursor()
        sql = "select name, jentry, date, owner from journal where jentry is not null"
        cur.execute(sql)
        j_results = cur.fetchall()
        if j_results == [] and self.annotations == []:
            return ""
        xml = '<Notes>\n'
        for j in j_results:
            xml += self.create_journal_note_xml(j)
        for ann in self.annotations:
            xml += self.create_annotation_note_xml(ann)
        xml += '</Notes>\n'
        return xml

    def cases_xml(self):
        """ Create xml for cases.
        Put case memo into description tag.
        Called by: project_xml
        returns xml """

        xml = ''
        cur = self.app.conn.cursor()
        cur.execute("select caseid, name, ifnull(memo,''), owner, date from cases")
        result = cur.fetchall()
        if not result:
            return xml
        xml = '<Cases>\n'
        for r in result:
            xml += f'<Case guid="{self.create_guid()}" '
            xml += f'name="{html.escape(r[1])}">\n'
            if r[2] != "":
                description = html.escape(r[2])
                xml += f"<Description>{description}</Description>\n"
            else:
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
        sql = "select attribute.name, ifnull(value,'') from attribute where attr_type='case' and id=?"
        cur.execute(sql, (caseid,))
        attributes = cur.fetchall()
        for a in attributes:
            xml += '<VariableValue>\n'
            guid = ''
            var_type = 'character'
            for v in self.variables:
                if v['name'] == a[0]:
                    guid = v['guid']
                    var_type = v['type']
            xml += f'<VariableRef targetGUID="{guid}" />\n'
            if var_type == 'numeric' and a[1] != '':
                xml += f"<FloatValue>{a[1]}</FloatValue>\n"
            if var_type == 'character':
                xml += f"<TextValue>{html.escape(a[1])}</TextValue>\n"
            xml += '</VariableValue>\n'
        return xml

    def case_source_ref_xml(self, caseid):
        """ Find sources linked to this case, pos0 and pos1 must equal zero.
        Called by: cases_xml

        :param caseid Integer

        :returns xml String
        """

        xml = ''
        cur = self.app.conn.cursor()
        cur.execute("select fid, owner, date from case_text where caseid=? and pos0=0 and pos1=0", [caseid, ])
        result = cur.fetchall()
        if not result:
            return xml
        for row in result:
            for s in self.sources:
                if s['id'] == row[0]:
                    # put xml creation here, in case a source id does not match up
                    xml += f'<SourceRef targetGUID="{s["guid"]}"/>\n'
        return xml

    def source_variables_xml(self, sourceid):
        """ Get the variables, name, type and value for this source and create xml.
        Source variables are stored like this:
        <VariableValue>
        <VariableRef targetGUID="51dc3bcd-5454-47ff-a4d6-ea699144410d" />
        <TextValue>20-29</TextValue>
        </VariableValue>

        :param sourceid:
        :type sourceid: Integer

        :returns xml String for case variables
        """

        xml = ""
        cur = self.app.conn.cursor()
        sql = "select attribute.name, value from attribute where attr_type='file' and id=?"
        cur.execute(sql, (sourceid,))
        attributes = cur.fetchall()
        for a in attributes:
            xml += '<VariableValue>\n'
            guid = ''
            var_type = 'character'
            for v in self.variables:
                if v['name'] == a[0]:
                    guid = v['guid']
                    var_type = v['type']
            xml += f'<VariableRef targetGUID="{guid}" />\n'
            if var_type == 'numeric' and a[1] != '':  # test
                xml += f"<FloatValue>{a[1]}</FloatValue>\n"
            if var_type == 'character':
                xml += f"<TextValue>{html.escape(a[1])}</TextValue>\n"
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

        # TODO after Coding: NoteRef and VariableValue for each Source element
        xml = "<Sources>\n"
        for s in self.sources:
            guid = self.create_guid()
            # Text document
            if ((s['mediapath'] is None) and (s['name'][-4:].lower() != '.pdf' and s['name'][-12:] != '.transcribed')) or \
                    (s['mediapath'] is not None and s['mediapath'][0:6] == '/docs/' and (
                            s['name'][-4:].lower() != '.pdf' or s['name'][-12:] != '.transcribed')):
                xml += '<TextSource '
                if s['external'] is None:
                    # Internal filename is a guid identifier
                    xml += f'richTextPath="internal://{s["filename"]}" '
                else:
                    xml += f'richTextPath="absolute://{html.escape(s["external"])}" '
                # Internal filename is a guid identifier
                xml += f'plainTextPath="internal://{s["plaintext_filename"]}" '
                xml += f'creatingUser="{self.user_guid(s["owner"])}" '
                xml += f'creationDateTime="{self.convert_timestamp(s["date"])}" '
                xml += f'guid="{guid}" '
                xml += f'name="{html.escape(s["name"])}">\n'
                memo = html.escape(s['memo'])
                if memo != "":
                    xml += f"<Description>{memo}</Description>\n"
                xml += self.text_selection_xml(s['id'])
                xml += self.source_variables_xml(s['id'])
                for a in self.annotations:
                    if a['fid'] == s['id']:
                        a['NoteRef_guid'] = self.create_guid()
                        xml += f'<NoteRef targetGUID="{a["NoteRef_guid"]}" />\n'
                        break
                xml += '</TextSource>\n'
            # PDF document
            if (s['mediapath'] is None and s['name'][-4:].lower() == '.pdf') or \
                    (s['mediapath'] is not None and s['mediapath'][0:5] == 'docs:' and s['name'][
                                                                                       -4:].lower() == '.pdf'):
                xml += '<PDFSource '
                if s['external'] is None:
                    # Internal filename is a guid identifier
                    xml += f'path="internal://{s["filename"]}" '
                else:
                    xml += f'path="absolute://{html.escape(s["external"])}" '
                xml += f'creatingUser="{self.user_guid(s["owner"])}" '
                xml += f'creationDateTime="{self.convert_timestamp(s["date"])}" '
                xml += f'guid="{guid}" '
                xml += f'name="{html.escape(s["name"])}">\n'
                memo = html.escape(s['memo'])
                if s['memo'] != "":
                    xml += f"<Description>{memo}</Description>\n"
                xml += f'<Representation guid="{self.create_guid()}" '
                # Internal filename is a guid identifier
                xml += f'plainTextPath="internal://{s["plaintext_filename"]}" '
                xml += f'creatingUser="{self.user_guid(s["owner"])}" '
                xml += f'name="{html.escape(s["name"])}">\n'
                xml += self.text_selection_xml(s['id'])
                for a in self.annotations:
                    if a['fid'] == s['id']:
                        a['NoteRef_guid'] = self.create_guid()
                        break
                xml += '</Representation>'
                xml += self.source_variables_xml(s['id'])
                xml += '</PDFSource>\n'
            # Images
            if s['mediapath'] is not None and s['mediapath'][0:7] in ('/images', 'images:'):
                xml += '<PictureSource '
                xml += f'creatingUser="{self.user_guid(s["owner"])}" '
                xml += f'creationDateTime="{self.convert_timestamp(s["date"])}" '
                if s['external'] is None:
                    # Internal filename is a guid identifier
                    xml += f'path="internal://{s["filename"]}" '
                else:
                    xml += f'path="absolute://{html.escape(s["external"])}" '
                xml += f'guid="{guid}" '
                xml += f'name="{html.escape(s["name"])}" >\n'
                memo = html.escape(s['memo'])
                if memo != '':
                    xml += f"<Description>{memo}</Description>\n"
                xml += self.picture_selection_xml(s['id'])
                xml += self.source_variables_xml(s['id'])
                xml += '</PictureSource>\n'
            # Audio
            if s['mediapath'] is not None and s['mediapath'][0:6] in ('/audio', 'audio:'):
                xml += '<AudioSource '
                xml += f'creatingUser="{self.user_guid(s["owner"])}" '
                xml += f'creationDateTime="{self.convert_timestamp(s["date"])}" '
                if s['external'] is None:
                    # Internal filename is a guid identifier
                    xml += f'path="internal://{s["filename"]}" '
                else:
                    xml += f'path="absolute://{html.escape(s["external"])}" '
                xml += f'guid="{guid}" '
                xml += f'name="{html.escape(s["name"])}" >\n'
                memo = html.escape(s['memo'])
                if memo != '':
                    xml += f"<Description>{memo}</Description>\n"
                xml += self.transcript_xml(s)
                xml += self.av_selection_xml(s['id'], 'Audio')
                xml += self.source_variables_xml(s['id'])
                xml += '</AudioSource>\n'
            # Video
            if s['mediapath'] is not None and s['mediapath'][0:6] in ('/video', 'video:'):
                xml += '<VideoSource '
                xml += f'creatingUser="{self.user_guid(s["owner"])}" '
                xml += f'creationDateTime="{self.convert_timestamp(s["date"])}" '
                if s['external'] is None:
                    # Internal - may not need to convert xml entities
                    #print("sources_xml method: plaintext internal", s['plaintext_filename'])
                    xml += f'path="internal://{html.escape(s["filename"])}" '
                else:
                    xml += f'path="absolute://{html.escape(s["external"])}" '
                xml += f'guid="{guid}" '
                xml += f'name="{html.escape(s["name"])}" >\n'
                memo = html.escape(self.code_guid(s['memo']))
                if memo != '':
                    xml += f"<Description>{memo}</Description>\n"
                xml += self.transcript_xml(s)
                xml += self.av_selection_xml(s['id'], 'Video')
                xml += self.source_variables_xml(s['id'])
                xml += '</VideoSource>\n'
        xml += "</Sources>\n"
        return xml

    def text_selection_xml(self, id_):
        """ Get and complete text selection xml.
        xml is in form:
        <PlainTextSelection><Description></Description><Coding><CodeRef/></Coding></PlainTextSelection>
        Called by: sources_xml

        :param id_ file id integer

        :returns xml string
        """

        xml = ""
        sql = "select cid, seltext, pos0, pos1, owner, date, ifnull(memo,'') from code_text "
        sql += "where fid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [id_, ])
        results = cur.fetchall()
        for r in results:
            code_guid = self.code_guid(r[0])
            if code_guid != "":  # Need a coding for this selection
                xml += f'<PlainTextSelection guid="{self.create_guid()}" '
                xml += f'startPosition="{r[2]}" '
                xml += f'endPosition="{r[3]}" '
                xml += f'name="{html.escape(r[1])}" '
                xml += f'creatingUser="{self.user_guid(r[4])}" '
                xml += f'creationDateTime="{self.convert_timestamp(r[5])}">\n'
                if r[6] != "":  # Description element comes before coding element
                    memo = html.escape(r[6])
                    xml += f"<Description>{memo}</Description>\n"
                xml += f'<Coding guid="{self.create_guid()}" '
                xml += f'creatingUser="{self.user_guid(r[4])}" >\n'
                xml += f'<CodeRef targetGUID="{code_guid}" />\n'
                xml += '</Coding>\n'
                xml += '</PlainTextSelection>\n'
        return xml

    def picture_selection_xml(self, id_):
        """ Get and complete picture selection xml.
        Called by: sources_xml
        <PictureSelection><Description></Description><Coding><CodeRef/></Coding></PictureSelection>

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
            xml += f'<PictureSelection guid="{self.create_guid()}" '
            xml += f'firstX="{int(r[2])}" '
            xml += f'firstY="{int(r[3])}" '
            xml += f'secondX="{int(r[2] + r[4])}" '
            xml += f'secondY="{int(r[3] + r[5])}" '
            xml += f'name="{html.escape(r[8])}" '
            xml += f'creatingUser="{self.user_guid(r[6])}" '
            xml += f'creationDateTime="{self.convert_timestamp(r[7])}">\n'
            if r[8] is not None and r[8] != "":
                memo = html.escape(r[8])
                xml += f"<Description>{memo}</Description>\n"
            xml += f'<Coding guid="{self.create_guid()}" '
            xml += f'creatingUser="{self.user_guid(r[6])}" >\n'
            code_guid = self.code_guid(r[1])
            if code_guid != "":
                xml += f'<CodeRef targetGUID="{code_guid}"/>\n'
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
        <Description></Description>
        <Coding creatingUser="AD68FBE7‐E1EE‐4A82‐A279‐23CC698C89EB"
        creationDateTime="2018‐03‐27T19:36:01Z" guid="04EBEC7D‐EAB4‐43FC‐8167‐ADB14F921143">
        <CodeRef targetGUID="9F43FE32‐C2CB‐4BA8‐B766‐A0734C826E49"/>
        </Coding>
        </VideoSelection>

        :param id_ is the source id Integer
        :param mediatype : is the String of Audo or Video
        :returns xml String Audio or Video
        """

        xml = ""
        sql = "select avid, cid, pos0, pos1, owner, date, memo from code_av "
        sql += "where id=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [id_, ])
        results = cur.fetchall()
        for r in results:
            xml += f'<{mediatype}Selection guid="{self.create_guid()}" '
            xml += f'begin="{int(r[2])}" '
            xml += f'end="{int(r[3])}" '
            xml += f'name="{html.escape(r[6])}" '
            xml += f'creatingUser="{self.user_guid(r[4])}" >\n'
            if r[6] != "":
                memo = html.escape(r[6])
                xml += f"<Description>{memo}</Description>\n"
            xml += f'<Coding guid="{self.create_guid()}" '
            xml += f'creatingUser="{self.user_guid(r[4])}" '
            xml += f'creationDateTime="{self.convert_timestamp(r[5])}">\n'
            code_guid = self.code_guid(r[1])
            if code_guid != "":
                xml += f'<CodeRef targetGUID="{code_guid}"/>\n'
            xml += '</Coding>\n'
            xml += f"</{mediatype}'Selection>\n"
        return xml

    def transcript_xml(self, source):
        """ Find any transcript of media source.
        Need to add timestamp synchpoints.

        Either PlainTextContent or plainTextPath MUST be filled, not both

        <Transcript>
        <Description></Description>
            <TranscriptSelection>
            <Description></Description>
            <Coding></Coding>
            <NoteRef></NoteRef>
            </TranscriptSelection>
        </Transcript>

        Called by: sources_xml

        :param source  is this media source dictionary.

        :returns xml String
        """

        xml = ""
        for t in self.sources:
            if t['name'] == source['name'] + '.transcribed':
                # Internal filename is a guid identifier
                xml = '<Transcript plainTextPath="internal://'
                xml += html.escape(t['plaintext_filename']) + '" '
                xml += f'creatingUser="{self.user_guid(t["owner"])}" '
                xml += f'creationDateTime="{self.convert_timestamp(t["date"])}" '
                xml += f'guid="{self.create_guid()}" '
                xml += f'name="{html.escape(t["name"])}" >\n'
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
            # print(coded)
            xml += f'<TranscriptSelection guid="{self.create_guid()}" '
            xml += f'name="{html.escape(media["name"])}" '
            xml += 'fromSyncPoint="'
            for sp in sync_list:
                if sp[2] == coded[0]:
                    xml += sp[0]
                    break  # To avoid a quirky double up of guid
            xml += '" toSyncPoint="'
            doubleup = False
            for sp in sync_list:
                if sp[2] == coded[1] and doubleup is False:
                    xml += sp[0]
                    doubleup = True
            xml += '">\n'
            xml += f'<Coding guid="{self.create_guid()}" >\n'
            code_guid = self.code_guid(coded[2])
            if code_guid != "":
                xml += f'<CodeRef targetGUID="{code_guid}" />\n'
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
        # print("TIME POINTS", len(tps))
        # print(tps)

        sql = "select pos0,pos1,cid,owner, date, memo from code_text where fid=? order by pos0"
        cur = self.app.conn.cursor()
        cur.execute(sql, [media['id'], ])
        results = cur.fetchall()
        sync_list = []
        # Starting syncpoint
        guid = self.create_guid()
        xml = f'<SyncPoint guid="{guid}" position="0" timeStamp="0" />\n'
        sync_list.append([guid, xml, 0])

        for r in results:
            # text start position
            guid = self.create_guid()
            msecs = 0
            for t in tps:
                if t[0] <= r[0]:
                    msecs = t[1]
            xml = f'<SyncPoint guid="{guid}" position="{r[0]}" '
            xml += f'timeStamp="{msecs}" />\n'
            sync_list.append([guid, xml, r[0]])
            # text end position
            msecs = 0
            for t in tps:
                if t[0] <= r[1]:
                    msecs = t[1]
            if msecs == 0:
                msecs = tps[-1][1]  # the media end
            guid = self.create_guid()
            xml = f'<SyncPoint guid="{guid}" position="{r[1]}" '
            xml += f'timeStamp="{msecs}" />\n'
            sync_list.append([guid, xml, r[1]])

        # TODO might have multiples of the same char position and msecs, trim back?
        # print("SYNC_LIST", len(sync_list))
        # print(sync_list)  # tmp
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

        :param media:
        :type media: Dictionary

        :return list of time points as [character position, milliseconds]
        """

        text = media['fulltext']
        if len(text) == 0 or text is None:
            return []

        mmss1 = r"\[[0-9]?[0-9]:[0-9][0-9]\]"
        hhmmss1 = r"\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = r"\[[0-9]?[0-9]\.[0-9][0-9]\]"
        hhmmss2 = r"\[[0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\]"
        hhmmss_sss = r"#[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]{1,3}#"  # allow for 1 to 3 msecs digits
        srt = r"[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]\s-->\s[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]"

        time_pos = [[0, 0]]
        for match in re.finditer(mmss1, text):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                time_pos.append([match.span()[0], msecs])
            except KeyError:
                pass
        for match in re.finditer(hhmmss1, text):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                time_pos.append([match.span()[0], msecs])
            except KeyError:
                pass
        for match in re.finditer(mmss2, text):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                time_pos.append([match.span()[0], msecs])
            except KeyError:
                pass
        for match in re.finditer(hhmmss2, text):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                time_pos.append([match.span()[0], msecs])
            except KeyError:
                pass
        for match in re.finditer(hhmmss_sss, text):
            # Format #00:12:34.567#
            stamp = match.group()[1:-1]
            text_hms = stamp.split(':')
            text_secs = text_hms[2].split('.')[0]
            text_msecs = text_hms[2].split('.')[1]
            # Adjust msecs to 1000's for 1 or 2 digit strings
            if len(text_msecs) == 1:
                text_msecs += "00"
            if len(text_msecs) == 2:
                text_msecs += "0"
            try:
                msecs = (int(text_hms[0]) * 3600 + int(text_hms[1]) * 60 + int(text_secs)) * 1000 + int(text_msecs)
                time_pos.append([match.span()[0], msecs])
            except KeyError:
                pass
        for match in re.finditer(srt, text):
            # Format 09:33:04,100 --> 09:33:09,600  skip the arrow and second time position
            stamp = match.group()[0:12]
            s = stamp.split(':')
            s2 = s[2].split(',')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                time_pos.append([match.span()[0], msecs])
            except KeyError:
                pass

        # Get the end of text postiiton to match to end of media, requires media lenth
        media_length = 0
        cur = self.app.conn.cursor()
        media_name = media['name'][0:-12]
        cur.execute("select mediapath from source where name=?", (media_name,))
        media_path_list = cur.fetchone()
        if vlc:
            try:
                instance = vlc.Instance()
                vlc_media = instance.media_new(self.app.project_path + media_path_list[0])
                vlc_media.parse()
                media_length = vlc_media.get_duration() - 1
                if media_length == -1:
                    media_length = 0
            except Exception as err:
                msg_ = f"{err}\n{media_name}"
                Message(self.app, _("A/V Media not found"), msg_, "warning").exec()
                logger.warning(msg_)
        else:
            msg_ = _("VLC not installed, final end character timepoint will be inaccurate")
            Message(self.app, _("VLC not found"), msg_, "warning").exec()
            logger.warning(msg_)
        time_pos.append([len(text) - 1, media_length])
        # Order the list by character positions
        time_pos = sorted(time_pos, key=itemgetter(0))
        return time_pos

    @staticmethod
    def convert_timestamp(time_in):
        """ Convert yyyy-mm-dd hh:mm:ss to REFI-QDA yyyy-mm-ddThh:mm:ssZ
        I have found one instance of an underscore where the space should be. """

        time_out = f"{time_in[0:10]}T{time_in[11:]}Z"
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
        cur.execute("SELECT id, name, fulltext, mediapath, ifnull(memo,''), owner, date FROM source")
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
            # Make it so that no media > 2Gb to be imported internally into the project
            if source['mediapath'] is not None:
                # fileinfo = os.stat(self.app.project_path + source['mediapath'])
                # f fileinfo.st_size >= 2147483647:
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

        self.users = []
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
        cur.execute("select name, ifnull(memo,''), owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        for row in result:
            c = {'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3].replace(' ', 'T'),
                 'cid': row[4], 'catid': row[5], 'color': row[6], 'guid': self.create_guid()}
            xml = f'<Code guid="{c["guid"]}" '
            xml += f'name="{html.escape(c["name"])}" '
            xml += 'isCodable="true" '
            xml += f'color="{c["color"]}"'
            memo = html.escape(c['memo'])
            if memo != "":
                xml += '>\n'
                xml += f"<Description>{memo}</Description>\n"
                xml += '</Code>\n'
            else:  # no description element, so wrap up code as <code />
                xml += ' />\n'
            c['xml'] = xml
            self.codes.append(c)

    def get_categories(self):
        """ get categories and assign guid.
        examine is set to true and then to false when creating the xml through recursion.
        """

        self.categories = []
        cur = self.app.conn.cursor()
        cur.execute("select name, catid, owner, date, ifnull(memo,''), supercatid from code_cat")
        result = cur.fetchall()
        for row in result:
            self.categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
                                    'date': row[3].replace(' ', 'T'), 'memo': row[4], 'supercatid': row[5],
                                    'guid': self.create_guid(), 'examine': True})

    def codebook_xml(self):
        """ Top level items are main categories and unlinked codes
        Create xml for codes and categories.
        codes within categories are does like this: <code><code></code></code>

        :returns xml string
        """

        if not self.codes:
            return ""
        xml = '<CodeBook>\n'
        xml += '<Codes>\n'
        cats = copy(self.categories)

        # Add unlinked codes as top level items
        for code_ in self.codes:
            if code_['catid'] is None:
                xml += code_['xml']
        # Add top level categories
        for ca in cats:
            if ca['supercatid'] is None and ca['examine']:
                ca['examine'] = False
                xml += '<Code guid="' + ca['guid']
                xml += '" name="' + html.escape(ca['name'])
                xml += '" isCodable="false'
                xml += '">\n'
                memo = html.escape(ca['memo'])
                if memo != "":
                    xml += f"<Description>{memo}</Description>\n"
                # Add codes in this category
                for code_ in self.codes:
                    if code_['catid'] == ca['catid']:
                        xml += code_['xml']
                xml += self.add_sub_categories(ca['catid'], cats)
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
                    xml += f'<Code guid="{c["guid"]}" '
                    xml += f'name="{html.escape(c["name"])}" '
                    xml += 'isCodable="false">\n'
                    memo = html.escape(c['memo'])
                    if memo != "":
                        xml += f"<Description>{memo}</Description>\n"
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
        """ Create globally unique guid for each component. 128-bit integer, 32 chars
        Format:
        ([0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12})|(backslash{[0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12}backslash})

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
        GUID: 128-bit integer used to identify resources, globally unique
        lxml parser: error occurs when defining UTF-8 encoding in first line
        ValueError:
        Unicode strings with encoding declaration are not supported.
        Please use bytes input or XML fragments without declaration.
        """

        self.xml = '<?xml version="1.0" encoding="utf-8"?>\n'
        self.xml += '<CodeBook xmlns="urn:QDA-XML:codebook:1.0" '
        self.xml += 'xsi:schemaLocation="urn:QDA-XML:codebook:1.0 Codebook.xsd" '
        self.xml += 'origin="QualCoder" '
        self.xml += 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        self.xml += self.codebook_xml()[10:]

    def xml_validation(self, xsd_type="codebook"):
        """ Verify that the XML complies with XSD.
        NOT USED could not get implementation of xmlschema to work
        See:
        https://stackoverflow.com/questions/299588/validating-with-an-xml-schema-in-python
        Arguments:
            1. file_xml: Input xml file
            2. file_xsd: xsd file which needs to be validated against xml
        Return:
            No return value
        """

        file_xsd = xsd_codebook
        if xsd_type != "codebook":
            file_xsd = xsd_project
        return True
