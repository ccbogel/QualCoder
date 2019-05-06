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
import logging
from lxml import etree
import os
import shutil
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


class Refi(QtWidgets.QDialog):

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
    notes = []  # contains xml of guid and note (memo) text
    variables = []  # contains dictionary of variable xml, guid, name
    xml = ""
    parent_textEdit = None
    settings = None
    tree = None

    def __init__(self, settings, parent_textEdit):
        """  """

        sys.excepthook = exception_handler
        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.get_categories()
        self.get_codes()
        self.get_users()
        self.get_sources()
        #self.codebook_xml()
        #self.xml_validation("codebook")
        self.project_xml()
        self.xml_validation("project")
        self.export_project()
        print(self.notes)
        exit(0)

    def export_project(self):
        '''
        .qde file
        Internal files are identified in the path attribute of the source element by the URL naming scheme internal://
        /sources folder
        Audio and video source file size:
        The maximum size in bytes allowed for an internal file is 2,147,483,647 bytes (2^31−1 bytes, or 2 GiB
        minus 1 byte). An exporting application must detect file size limit during export and inform the
        user.

        Source types:
        Plain text, PDF
        Images must be jpeg or png - although I will export all types

        Create an unzipped folder with a /sources folder and project.qde xml document
        Then create zip wih suffix .qdpx
        '''

        project_name = self.settings['projectName'][:-4]
        prep_path = os.path.expanduser('~') + '/.qualcoder/' + project_name
        print(prep_path)
        try:
            shutil.rmtree(prep_path)
        except FileNotFoundError:
            pass
        try:
            os.mkdir(prep_path)
            os.mkdir(prep_path + "/sources")
        except Exception as e:
            logger.error(_("Project export error ") + str(e))
            QtWidgets.QMessageBox.warning(None, _("Project"), _("Project not exported. Exiting. ") + str(e))
            exit(0)
        try:
            with open(prep_path +'/' + project_name + '.qde', 'w') as f:
                f.write(self.xml)
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, _("Project"), _("Project not exported. Exiting. ") + str(e))
            print(e)
            exit(0)
        for s in self.sources:
            #print(s)
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

        export_path = self.settings['path'][:-4]
        shutil.make_archive(export_path, 'zip', prep_path)
        os.rename(export_path + ".zip", export_path + ".qpdx")
        try:
            shutil.rmtree(prep_path)
        except FileNotFoundError:
            pass
        msg = export_path + ".qpdx\n"
        msg += "Journals, most memos and variables are not exported. "
        msg += "GIFs (if present) are not converted to jpg on export, which does not meet the exchange standard. "
        msg += "This project exchange is not fully compliant with the exchange standard."
        QtWidgets.QMessageBox.information(None, _("Project exported"), _(msg))

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

        self.xml = '<?xml version="1.0" standalone="yes"?>\n'  #encoding="UTF-8"?>\n'
        self.xml += '<Project '
        self.xml += 'xmlns="urn:QDA-XML:project:1.0" '
        guid = self.create_guid()
        self.xml += 'creatingUserGUID="' + guid + '" '  # there is no creating user in QualCoder
        cur = self.settings['conn'].cursor()
        cur.execute("select date,memo from project")
        result = cur.fetchone()
        dtime = result[0].replace(" ", "T")
        self.xml += 'creationDateTime="' + dtime + '" '
        #self.xml += 'basePath="' + self.settings['directory'] + '" '
        self.xml += 'name="' + self.settings['projectName'] + '" '
        self.xml += 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        self.xml += 'origin="Qualcoder-1.3" '
        self.xml += 'xsi:schemaLocation="urn:QDA-XML:project:1:0 http://schema.qdasoftware.org/versions/Project/v1.0/Project.xsd"'
        self.xml += '>\n'
        # add users
        self.xml += "<Users>\n"
        for row in self.users:
            self.xml += '<User guid="' + row['guid'] + '" name="' + row['name'] + '"/>\n'
        self.xml += "</Users>\n"
        self.xml += self.codebook_xml()
        self.xml += self.variables_xml()
        self.xml += self.cases_xml()
        self.xml += self.sources_xml()
        self.xml += self.notes_xml()
        #self.sets_xml()

        self.xml += '</Project>'

    def variables_xml(self):
        """ Variables are associated with Sources and Cases """

        self.variables = []

        xml = ""
        cur = self.settings['conn'].cursor()
        cur.execute("select name, date ,owner, memo, caseOrFile,valuetype from attribute_type")
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
            if r[5] == 'numeric':
                xml += 'Float" '
            else:
                xml += 'Text" '
            xml += '>\n'
            xml += '</Variable>\n'
            self.variables.append({'guid': guid, 'name': r[0], 'type': r[5], 'caseOrFile': r[4]})
        xml += '</Variables>\n'
        return xml

    def create_note_xml(self, guid, text, user, datetime, name=""):
        """ Create a Note xml for project, sources, cases, codes, etc
        Appends xml in notes list.
        name is used for names of journal entries.
        returns a guid for a NoteRef """

        guid = self.create_guid()
        xml = '<Note guid="' + guid + '" '
        xml += 'creatingUser="' + user + '" '
        xml += 'creationDateTime="' + datetime + '" '
        if name != "":
            xml += 'name="' + name + '" '
        xml += '>\n'
        xml += '<PlainTextContent>' + text + '</PlainTextContent>\n'
        xml += '</Note>\n'
        self.notes.append(xml)
        noteref = '<NoteRef targetGUID="' + guid + '" />\n'
        return noteref

    def notes_xml(self):
        """ Collate note_xml list into final xml
        <Notes><Note></Note></Notes>
        Note xml requires a NoteRef in the source or case
         returns xml """

        if self.notes == []:
            return ''
        xml = '<Notes>\n'
        for note in self.notes:
            xml += note
        xml += '</Notes>\n'
        return xml

    def cases_xml(self):
        """ Create xml for cases.
        Putting memo into description, but should I also create a Note xml too?
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
            xml += self.case_source_ref_xml(r[0])
            #TODO unsure how this works as only has a targetRef
            #xml += self.case_selection_xml(r[0])
            #TODO unsure how this works
            #xml += self.case_variables_xml(r[0])
            xml += '</Case>\n'
        xml += '</Cases>\n'
        return xml

    def case_source_ref_xml(self, caseid):
        """ Find sources linked to this case, pos0 and pos1 must equal zero. """

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

    def sources_xml(self):
        """ Create xml for sources: text, pictures, pdf, audio, video.
         Also add selections to each source.

        returns xml """

        xml = "<Sources>\n"
        for s in self.sources:
            guid = self.create_guid()
            # text document
            if s['mediapath'] is None and (s['name'][-4:].lower() != '.pdf' or s['name'][-12:] != '.transcribed'):
                xml += '<TextSource '
                xml += 'richTextPath="internal://' + s['filename'] + '" '
                xml += 'plainTextPath="internal://' + s['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + s['date'] + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '">\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.text_selection_xml(s['id'])

                """
                #TODO TEST variable value
                #TODO variableRef contains name=targetGUID and type=GUID
                # presume variable [0]
                xml += '<VariableValue>'
                for v in self.variables:
                    print("VARIABLE", v)
                xml += '<VariableRef targetGUID="'  + self.variables[0]['guid'] + '"/>'
                xml += '</VariableValue>\n'
                """

                xml += '</TextSource>\n'
            # pdf document
            if s['mediapath'] is None and s['name'][-4:].lower() == '.pdf':
                xml += '<PDFSource '
                xml += 'path="internal://' + s['filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + s['date'] + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '">\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += '<Representation guid="' + self.create_guid() + '" '
                xml += 'plainTextPath="internal://' + s['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + s['date'] + '" '
                xml += 'name="' + s['name'] + '">\n'
                xml += self.text_selection_xml(s['id'])
                xml += '</Representation>'
                xml += '</PDFSource>\n'
            if s['mediapath'] is not None and s['mediapath'][0:7] == '/images':
                xml += '<PictureSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + s['date'] + '" '
                xml += 'path="internal://' + s['filename'] + '" '
                xml += 'guid="' + guid + '" '
                xml += 'name="' + s['name'] + '" >\n'
                if s['memo'] != '':
                    xml += '<Description>' + s['memo'] + '</Description>\n'
                xml += self.picture_selection_xml(s['id'])
                xml += '</PictureSource>\n'
            if s['mediapath'] is not None and s['mediapath'][0:6] == '/audio':
                xml += '<AudioSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + s['date'] + '" '
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
                xml += '</AudioSource>\n'
            if s['mediapath'] is not None and s['mediapath'][0:6] == '/video':
                xml += '<VideoSource '
                xml += 'creatingUser="' + self.user_guid(s['owner']) + '" '
                xml += 'creationDateTime="' + s['date'] + '" '
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
                xml += '</VideoSource>\n'
        xml += "</Sources>\n"
        return xml

    def text_selection_xml(self, id_):
        """ Get and complete text selection xml.
        xml is in form:
        <PlainTextSelection><Coding><CodeRef/></Coding></PlainTextSelection>
        returns xml
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
            xml += 'creationDateTime="' + str(r[5]).replace(' ', 'T') + '">\n'
            xml += '<Coding guid="' + self.create_guid() + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" '
            xml += 'creationDateTime="' + str(r[5]).replace(' ', 'T') + '">\n'
            xml += '<CodeRef targetGUID="' + self.code_guid(r[0]) + '"/>\n'
            xml += '</Coding>\n'
            xml += '</PlainTextSelection>\n'
        return xml

    def picture_selection_xml(self, id_):
        """ Get and complete picture selection xml.
        returns xml """

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
            xml += 'creationDateTime="' + str(r[7]).replace(' ', 'T') + '">\n'
            xml += '<Coding guid="' + self.create_guid() + '" '
            xml += 'creatingUser="' + self.user_guid(r[6]) + '" '
            xml += 'creationDateTime="' + str(r[7]).replace(' ', 'T') + '">\n'
            xml += '<CodeRef targetGUID="' + self.code_guid(r[1]) + '"/>\n'
            xml += '</Coding>\n'
            xml += '</PictureSelection>\n'
        return xml

    def av_selection_xml(self, id_):
        """ Get and complete av selection xml.
        returns xml """

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
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" '
            xml += 'creationDateTime="' + str(r[5]).replace(' ', 'T') + '">\n'
            xml += '<Coding guid="' + self.create_guid() + '" '
            xml += 'creatingUser="' + self.user_guid(r[4]) + '" '
            xml += 'creationDateTime="' + str(r[5]).replace(' ', 'T') + '">\n'
            xml += '<CodeRef targetGUID="' + self.code_guid(r[1]) + '"/>\n'
            xml += '</Coding>\n'
            xml += '</VideoSelection>\n'
        return xml

    def transcript_xml(self, source):
        """ Find any transcript of media source.
        returns xml """

        xml = ""
        for t in self.sources:
            if t['name'] == source['name'] + '.transcribed':
                xml = '<Transcript plainTextPath="internal://' + t['plaintext_filename'] + '" '
                xml += 'creatingUser="' + self.user_guid(t['owner']) + '" '
                xml += 'creationDateTime="' + t['date'] + '" '
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
            'memo': r[4], 'owner': r[5], 'date': r[6].replace(' ', 'T'), 'guid': guid,
            'filename': filename, 'plaintext_filename': plaintext_filename,
            'external': None}
            if source['mediapath'] is not None:
                fileinfo = os.stat(self.settings['path'] + source['mediapath'])
                if fileinfo.st_size >= 2147483647:
                    source['external'] = self.settings['directory']
            self.sources.append(source)

    def get_users(self):
        """ get all users and assign guid. """

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
            xml += '" color="' + c['color'] + '">\n'
            if c['memo'] != "":
                xml += '<Description>' + c['memo'] + '</Description>\n'
            xml += '</Code>\n'
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
        returns xml """

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
                xml += '" isCodable="false'
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
        """ Returns recursive xml of category """

        xml = ""
        counter = 0
        unfinished = True
        while unfinished and counter < 5000:
            for c in cats:
                if c['examine'] and cid == c['supercatid']:
                    c['examine'] = False
                    xml += '<Code guid="' + c['guid']
                    xml += '" name="' + c['name']
                    xml += '" isCodable="false'
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

    def codebook_exchange_xml_does_not_validate(self):
        """ See: https://www.qdasoftware.org/wp-content/uploads/2019/03/QDAS-XML-1-0.pdf
        GUID: 128 bit integer used to identify resources, globally unique
        lxml parser: error occurs when defining UTF-8 encoding in first line
        ValueError:
        Unicode strings with encoding declaration are not supported.
        Please use bytes input or XML fragments without declaration.
        This does not validate DONT USE"""

        self.xml = '<?xml version="1.0" ?>\n'  #encoding="UTF-8"?>\n'
        self.xml += '<CodeBook \n'
        self.xml += 'xmlns="urn:QDA-XML:codebook:1.0"\n'
        self.xml += 'xmlns:qda="urn:QDA-XML:types"\n'
        self.xml += 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        self.xml += 'xsi:schemaLocation="urn:QDA-XML:codebook:1.0 Codebook.xsd"\n'
        self.xml += 'name="Example" guid="{91ffe013-d122-4acb-a25a-2ec103b9e404}"'
        self.xml += '>\n'
        self.xml += '<Codes>\n'

        for c in self.codes:
            #print(c)
            self.xml += '<Code guid="' + '{00000000-0000-0000-0000-000000000000}' #str(c['cid'])
            self.xml += '" name="' + c['name']
            self.xml += '" isCodable="true'
            self.xml += '" color="' + c['color'] + '">'
            self.xml += '<Description>' + c['memo'] + '</Description>\n'
            #self.xml += '<qda:IsChildOfCode>{5215cc69-b628-4e02-afb9-9beeaee55808}</qda:IsChildOfCode>\n'
            #self.xml += ' creatingUser="{e1fcef53-4718-4698-aac9-a4708d4b982c}"\n'
            self.xml += '</Code>\n'
        for c in self.categories:
            self.xml += '<Code guid="' + '{00000000-0000-0000-0000-000000000000}' #str(c['cid'])
            self.xml += '" name="' + c['name']
            self.xml += '" isCodable="false'
            #self.xml += '" color="' + c['color']
            self.xml += '">'
            self.xml += '<Description>' + c['memo'] + '</Description>\n'
            self.xml += '</Code>\n'
        self.xml += '</Codes>\n'
        self.xml += '<Sets>\n'
        self.xml += '</CodeBook>\n'

    def xml_validation(self, xsd_type="codebook"):
        """ Verify that the XML compliance with XSD
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
            #xml_doc = etree.parse(self.xml)
            xml_doc = etree.fromstring(self.xml)
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



