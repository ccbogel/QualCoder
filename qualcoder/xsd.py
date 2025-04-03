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

This file contains hardcoded versions of the REFI-QDA XSD files for:
    Codebook.xsd
    Project-mrt2019.xsd


Hard-coding reduces potential problems when pyinstaller tries to import data files.
"""


xsd_codebook = '<?xml version="1.0" encoding="UTF-8"?>\n\
<xsd:schema xmlns="urn:QDA-XML:codebook:1.0" xmlns:xsd="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:QDA-XML:codebook:1.0" elementFormDefault="qualified" attributeFormDefault="unqualified" version="1.0">\n\
<!-- =====ElementDeclarations===== ‐‐>\n\
<xsd:element name="CodeBook" type="CodeBookType">\n\
<xsd:annotation>\n\
<xsd:documentation>This element MUST be conveyed as the root element in any instance document based on this Schema expression\n\
</xsd:documentation>\n\
</xsd:annotation>\n\
</xsd:element>\n\
<!‐‐ =====TypeDefinitions===== ‐‐>\n\
<xsd:complexType name="CodeBookType">\n\
<xsd:sequence>\n\
<xsd:element name="Codes" type="CodesType"/>\n\
<xsd:element name="Sets" type="SetsType" minOccurs="0"/>\n\
</xsd:sequence>\n\
<xsd:attribute name="origin"type="xsd:string"/>\n\
</xsd:complexType>\n\
<xsd:complexType name="CodesType">\n\
<xsd:sequence>\n\
<xsd:element name="Code" type="CodeType" maxOccurs="unbounded"/>\n\
</xsd:sequence>\n\
</xsd:complexType>\n\
<xsd:complexType name="SetsType">\n\
<xsd:sequence>\n\
<xsd:element name="Set" type="SetType" maxOccurs="unbounded"/>\n\
</xsd:sequence>\n\
</xsd:complexType>\n\
<xsd:complexType name="CodeType">\n\
<xsd:sequence>\n\
<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
<xsd:element name="Code" type="CodeType"minOccurs="0" maxOccurs="unbounded"/>\n\
</xsd:sequence>\n\
<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
<xsd:attribute name="name" type="xsd:string" use="required"/>\n\
<xsd:attribute name="isCodable" type="xsd:boolean" use="required"/>\n\
<xsd:attribute name="color" type="RGBType"/>\n\
</xsd:complexType>\n\
<xsd:complexType name="SetType">\n\
<xsd:sequence>\n\
<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
<xsd:element name="MemberCode" type="MemberCodeType" minOccurs="0" maxOccurs="unbounded"/>\n\
</xsd:sequence>\n\
<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
<xsd:attribute name="name" type="xsd:string" use="required"/>\n\
</xsd:complexType>\n\
<xsd:complexType name="MemberCodeType">\n\
<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
</xsd:complexType>\n\
<xsd:simpleType name="GUIDType">\n\
<xsd:restriction base="xsd:token">\n\
<xsd:pattern value="([0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12})|(\\{[0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12}\})"/>\n\
</xsd:restriction>\n\
</xsd:simpleType>\n\
<xsd:simpleType name="RGBType">\n\
<xsd:restriction base="xsd:token">\n\
<xsd:pattern value="#([A‐Fa‐f0‐9]{6}|[A‐Fa‐f0‐9]{3})"/>\n\
</xsd:restriction>\n\
</xsd:simpleType>\n\
</xsd:schema>'

xsd_project = '<?xml version="1.0" encoding="UTF-8"?>\n\
<!-- edited with XMLSpy v2005 rel. 3 U (http://www.altova.com) by  Fred van Blommestein -->\n\
<!--  Library: QDA-XML version 1.0  Release Date: 18 March 2019 Module: Project.xsd  -->\n\
<!-- ===== Copyright Notice ===== -->\n\
<!--\n\
The Rotterdam Exchange Format Initiative (REFI, www.qdasoftware.org) as the publisher of \
QDA-XML takes no position regarding the validity or scope of any \
intellectual property or other rights that might be claimed to pertain \
to the implementation or use of the technology described in this \
document or the extent to which any license under such rights \
might or might not be available; neither does it represent that it has \
made any effort to identify any such rights. Information on QDA-XMLs \
procedures with respect to rights in QDA-XML specifications can be \
found at the QDA-XML website www.qdasoftware.org..\
\
REFI invites any interested party to bring to its attention any \
copyrights, patents or patent applications, or other proprietary \
rights which may cover technology that may be required to \
implement this specification.\
\
This specification is licensed under the MIT license.  \
\
Copyright 2019 REFI www.qdasoftware.org.\
 \
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\
\
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\
\
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. \
-->\n\
<xsd:schema xmlns="urn:QDA-XML:project:1.0" xmlns:xsd="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:QDA-XML:project:1.0" elementFormDefault="qualified" attributeFormDefault="unqualified" version="1.0">\n\
	<!-- ===== Element Declarations ===== -->\n\
	<xsd:element name="Project" type="ProjectType">\n\
		<xsd:annotation>\n\
			<xsd:documentation>This element MUST be conveyed as the root element in any instance document based on this Schema expression</xsd:documentation>\n\
		</xsd:annotation>\n\
	</xsd:element>\n\
	<!-- ===== Type Definitions ===== -->\n\
	<xsd:complexType name="ProjectType">\n\
		<xsd:sequence>\n\
			<xsd:element name="Users" type="UsersType" minOccurs="0"/>\
			<xsd:element name="CodeBook" type="CodeBookType" minOccurs="0"/>\
			<xsd:element name="Variables" type="VariablesType" minOccurs="0"/>\
			<xsd:element name="Cases" type="CasesType" minOccurs="0"/>\
			<xsd:element name="Sources" type="SourcesType" minOccurs="0"/>\n\
			<xsd:element name="Notes" type="NotesType" minOccurs="0"/>\
			<xsd:element name="Links" type="LinksType" minOccurs="0"/>\
			<xsd:element name="Sets" type="SetsType" minOccurs="0"/>\
			<xsd:element name="Graphs" type="GraphsType" minOccurs="0"/>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<!-- Note(s) that apply to the project as a whole -->\
		</xsd:sequence>\
		<xsd:attribute name="name" type="xsd:string" use="required"/>\
		<xsd:attribute name="origin" type="xsd:string"/>\
		<xsd:attribute name="creatingUserGUID" type="GUIDType"/>\n\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUserGUID" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="basePath" type="xsd:string"/>\
	</xsd:complexType>\
	<xsd:complexType name="UsersType">\n\
		<xsd:sequence>\
			<xsd:element name="User" type="UserType" maxOccurs="unbounded"/>\
		</xsd:sequence>\
	</xsd:complexType>\
	<xsd:complexType name="UserType">\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="id" type="xsd:string"/>\
	</xsd:complexType>\
	<xsd:complexType name="CodeBookType">\n\
		<xsd:sequence>\
			<xsd:element name="Codes" type="CodesType"/>\
		</xsd:sequence>\
	</xsd:complexType>\
	<xsd:complexType name="CodesType">\n\
		<xsd:sequence>\
			<xsd:element name="Code" type="CodeType" maxOccurs="unbounded"/>\
		</xsd:sequence>\
	</xsd:complexType>\
	<xsd:complexType name="CodeType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="Code" type="CodeType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="name" type="xsd:string" use="required"/>\n\
		<xsd:attribute name="isCodable" type="xsd:boolean" use="required"/>\
		<xsd:attribute name="color" type="RGBType"/>\
	</xsd:complexType>\
	<xsd:complexType name="CasesType">\n\
		<xsd:sequence>\
			<xsd:element name="Case" type="CaseType" maxOccurs="unbounded"/>\
		</xsd:sequence>\
	</xsd:complexType>\
	<xsd:complexType name="CaseType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
			<xsd:element name="CodeRef" type="CodeRefType" minOccurs="0" maxOccurs="unbounded"/>\n\
			<xsd:element name="VariableValue" type="VariableValueType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="SourceRef" type="SourceRefType" minOccurs="0" maxOccurs="unbounded"/>\n\
			<xsd:element name="SelectionRef" type="SelectionRefType" minOccurs="0" maxOccurs="unbounded"/>\n\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
	</xsd:complexType>\
	<xsd:complexType name="VariablesType">\n\
		<xsd:sequence>\n\
			<xsd:element name="Variable" type="VariableType" maxOccurs="unbounded"/>\
		</xsd:sequence>\
	</xsd:complexType>\
	<xsd:complexType name="VariableType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string" use="required"/>\
		<xsd:attribute name="typeOfVariable" type="typeOfVariableType" use="required"/>\
	</xsd:complexType>\n\
	<xsd:complexType name="VariableValueType">\n\
		<xsd:sequence>\
			<xsd:element name="VariableRef" type="VariableRefType"/>\n\
			<xsd:choice>\
				<xsd:element name="TextValue" type="xsd:string" minOccurs="0"/>\n\
				<xsd:element name="BooleanValue" type="xsd:boolean" minOccurs="0"/>\
				<xsd:element name="IntegerValue" type="xsd:integer" minOccurs="0"/>\n\
				<xsd:element name="FloatValue" type="xsd:decimal" minOccurs="0"/>\
				<xsd:element name="DateValue" type="xsd:date" minOccurs="0"/>\
				<xsd:element name="DateTimeValue" type="xsd:dateTime" minOccurs="0"/>\
			</xsd:choice>\n\
		</xsd:sequence>\
	</xsd:complexType>\n\
	<xsd:complexType name="SetsType">\n\
		<xsd:sequence>\n\
			<xsd:element name="Set" type="SetType" maxOccurs="unbounded"/>\n\
		</xsd:sequence>\n\
	</xsd:complexType>\n\
	<xsd:complexType name="SetType">\
		<xsd:sequence>\n\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="MemberCode" type="CodeRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="MemberSource" type="SourceRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="MemberNote" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string" use="required"/>\n\
	</xsd:complexType>\n\
	<xsd:complexType name="SourcesType">\n\
		<xsd:choice maxOccurs="unbounded">\
			<xsd:element name="TextSource" type="TextSourceType"/>\
			<xsd:element name="PictureSource" type="PictureSourceType"/>\n\
			<xsd:element name="PDFSource" type="PDFSourceType"/>\
			<xsd:element name="AudioSource" type="AudioSourceType"/>\
			<xsd:element name="VideoSource" type="VideoSourceType"/>\n\
		</xsd:choice>\n\
	</xsd:complexType>\n\
	<xsd:complexType name="TextSourceType">\n\
		<xsd:sequence>\n\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
			<xsd:element name="PlainTextContent" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="PlainTextSelection" type="PlainTextSelectionType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="VariableValue" type="VariableValueType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\n\
		<xsd:attribute name="richTextPath" type="xsd:string"/>\
		<xsd:attribute name="plainTextPath" type="xsd:string"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\n\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
		<!-- Either PlainTextContent or plainTextPath MUST be filled, not both -->\
	</xsd:complexType>\n\
	<xsd:complexType name="PlainTextSelectionType">\n\
		<xsd:sequence>\n\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\n\
		<xsd:attribute name="startPosition" type="xsd:integer" use="required"/>\
		<xsd:attribute name="endPosition" type="xsd:integer" use="required"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\n\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
	</xsd:complexType>\
	<xsd:complexType name="PictureSourceType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
			<xsd:element name="TextDescription" type="TextSourceType" minOccurs="0"/>\
			<xsd:element name="PictureSelection" type="PictureSelectionType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="VariableValue" type="VariableValueType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="path" type="xsd:string"/>\
		<xsd:attribute name="currentPath" type="xsd:string"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\n\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
	</xsd:complexType>\
	<xsd:complexType name="PictureSelectionType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\n\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="firstX" type="xsd:integer" use="required"/>\
		<xsd:attribute name="firstY" type="xsd:integer" use="required"/>\n\
		<xsd:attribute name="secondX" type="xsd:integer" use="required"/>\
		<xsd:attribute name="secondY" type="xsd:integer" use="required"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\n\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\n\
	</xsd:complexType>\n\
	<xsd:complexType name="PDFSourceType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="PDFSelection" type="PDFSelectionType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="Representation" type="TextSourceType" minOccurs="0"/>\n\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="VariableValue" type="VariableValueType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="path" type="xsd:string"/>\
		<xsd:attribute name="currentPath" type="xsd:string"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\n\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\n\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\n\
	</xsd:complexType>\
	<xsd:complexType name="PDFSelectionType">\
		<xsd:sequence>\n\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="Representation" type="TextSourceType" minOccurs="0"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="page" type="xsd:integer" use="required"/>\n\
		<xsd:attribute name="firstX" type="xsd:integer" use="required"/>\
		<xsd:attribute name="firstY" type="xsd:integer" use="required"/>\
		<xsd:attribute name="secondX" type="xsd:integer" use="required"/>\n\
		<xsd:attribute name="secondY" type="xsd:integer" use="required"/>\n\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\n\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\n\
	</xsd:complexType>\
	<xsd:complexType name="AudioSourceType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\n\
			<xsd:element name="Transcript" type="TranscriptType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="AudioSelection" type="AudioSelectionType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="VariableValue" type="VariableValueType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="path" type="xsd:string"/>\
		<xsd:attribute name="currentPath" type="xsd:string"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\n\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
	</xsd:complexType>\n\
	<xsd:complexType name="AudioSelectionType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="begin" type="xsd:integer" use="required"/>\n\
		<xsd:attribute name="end" type="xsd:integer" use="required"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\n\
	</xsd:complexType>\n\
	<xsd:complexType name="VideoSourceType">\n\
		<xsd:sequence>\n\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="Transcript" type="TranscriptType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="VideoSelection" type="VideoSelectionType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="VariableValue" type="VariableValueType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="path" type="xsd:string"/>\
		<xsd:attribute name="currentPath" type="xsd:string"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
	</xsd:complexType>\n\
	<xsd:complexType name="VideoSelectionType">\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="begin" type="xsd:integer" use="required"/>\
		<xsd:attribute name="end" type="xsd:integer" use="required"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
	</xsd:complexType>\
	<xsd:complexType name="TranscriptType">\n\
		<xsd:sequence>\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="PlainTextContent" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="SyncPoint" type="SyncPointType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="TranscriptSelection" type="TranscriptSelectionType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="richTextPath" type="xsd:string"/>\
		<xsd:attribute name="plainTextPath" type="xsd:string"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
		<!-- Either PlainTextContent or plainTextPath MUST be filled, not both -->\
	</xsd:complexType>\n\
	<xsd:complexType name="TranscriptSelectionType">\n\
		<xsd:sequence>\n\
			<xsd:element name="Description" type="xsd:string" minOccurs="0"/>\
			<xsd:element name="Coding" type="CodingType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="fromSyncPoint" type="GUIDType"/>\
		<xsd:attribute name="toSyncPoint" type="GUIDType"/>\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\
		<xsd:attribute name="modifyingUser" type="GUIDType"/>\
		<xsd:attribute name="modifiedDateTime" type="xsd:dateTime"/>\
	</xsd:complexType>\n\
	<xsd:complexType name="SyncPointType">\n\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="timeStamp" type="xsd:integer"/>\
		<xsd:attribute name="position" type="xsd:integer"/>\
	</xsd:complexType>\n\
	<xsd:complexType name="CodingType">\n\
		<xsd:sequence>\
			<xsd:element name="CodeRef" type="CodeRefType"/>\n\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="creatingUser" type="GUIDType"/>\
		<xsd:attribute name="creationDateTime" type="xsd:dateTime"/>\n\
	</xsd:complexType>\
	<xsd:complexType name="GraphsType">\
		<xsd:sequence>\
			<xsd:element name="Graph" type="GraphType" maxOccurs="unbounded"/>\n\
		</xsd:sequence>\
	</xsd:complexType>\n\
	<xsd:complexType name="GraphType">\n\
		<xsd:sequence>\
			<xsd:element name="Vertex" type="VertexType" minOccurs="0" maxOccurs="unbounded"/>\
			<xsd:element name="Edge" type="EdgeType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="name" type="xsd:string"/>\
	</xsd:complexType>\
	<xsd:complexType name="VertexType">\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="representedGUID" type="GUIDType"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="firstX" type="xsd:integer" use="required"/>\
		<xsd:attribute name="firstY" type="xsd:integer" use="required"/>\n\
		<xsd:attribute name="secondX" type="xsd:integer"/>\
		<xsd:attribute name="secondY" type="xsd:integer"/>\n\
		<xsd:attribute name="shape" type="ShapeType"/>\
		<xsd:attribute name="color" type="RGBType"/>\n\
	</xsd:complexType>\
	<xsd:complexType name="EdgeType">\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\n\
		<xsd:attribute name="representedGUID" type="GUIDType"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="sourceVertex" type="GUIDType" use="required"/>\
		<xsd:attribute name="targetVertex" type="GUIDType" use="required"/>\
		<xsd:attribute name="color" type="RGBType"/>\
		<xsd:attribute name="direction" type="directionType"/>\
		<xsd:attribute name="lineStyle" type="LineStyleType"/>\
	</xsd:complexType>\
	<xsd:complexType name="NotesType">\
		<xsd:sequence>\n\
			<xsd:element name="Note" type="TextSourceType" maxOccurs="unbounded"/>\
		</xsd:sequence>\
	</xsd:complexType>\
	<xsd:complexType name="LinksType">\
		<xsd:sequence>\n\
			<xsd:element name="Link" type="LinkType" maxOccurs="unbounded"/>\
		</xsd:sequence>\
	</xsd:complexType>\
	<xsd:complexType name="LinkType">\
		<xsd:sequence>\
			<xsd:element name="NoteRef" type="NoteRefType" minOccurs="0" maxOccurs="unbounded"/>\
		</xsd:sequence>\
		<xsd:attribute name="guid" type="GUIDType" use="required"/>\
		<xsd:attribute name="name" type="xsd:string"/>\
		<xsd:attribute name="direction" type="directionType"/>\n\
		<xsd:attribute name="color" type="RGBType"/>\
		<xsd:attribute name="originGUID" type="GUIDType"/>\n\
		<xsd:attribute name="targetGUID" type="GUIDType"/>\
	</xsd:complexType>\
	<xsd:complexType name="NoteRefType">\n\
		<xsd:attribute name="targetGUID" type="GUIDType" use="required"/>\
	</xsd:complexType>\n\
	<xsd:complexType name="CodeRefType">\n\
		<xsd:attribute name="targetGUID" type="GUIDType" use="required"/>\
	</xsd:complexType>\
	<xsd:complexType name="SourceRefType">\n\
		<xsd:attribute name="targetGUID" type="GUIDType" use="required"/>\
	</xsd:complexType>\
	<xsd:complexType name="SelectionRefType">\n\
		<xsd:attribute name="targetGUID" type="GUIDType" use="required"/>\n\
	</xsd:complexType>\n\
	<xsd:complexType name="VariableRefType">\
		<xsd:attribute name="targetGUID" type="GUIDType" use="required"/>\
	</xsd:complexType>\
	<xsd:simpleType name="GUIDType">\
		<xsd:restriction base="xsd:token">\
			<xsd:pattern value="([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})|(\\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\})"/>\
		</xsd:restriction>\
	</xsd:simpleType>\
	<xsd:simpleType name="RGBType">\
		<xsd:restriction base="xsd:token">\
			<xsd:pattern value="#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})"/>\
		</xsd:restriction>\n\
	</xsd:simpleType>\
	<xsd:simpleType name="directionType">\
		<xsd:restriction base="xsd:token">\
			<xsd:enumeration value="Associative"/>\n\
			<xsd:enumeration value="OneWay"/>\
			<xsd:enumeration value="Bidirectional"/>\
		</xsd:restriction>\n\
	</xsd:simpleType>\n\
	<xsd:simpleType name="typeOfVariableType">\
		<xsd:restriction base="xsd:token">\
			<xsd:enumeration value="Text"/>\
			<xsd:enumeration value="Boolean"/>\
			<xsd:enumeration value="Integer"/>\
			<xsd:enumeration value="Float"/>\
			<xsd:enumeration value="Date"/>\n\
			<xsd:enumeration value="DateTime"/>\
		</xsd:restriction>\
	</xsd:simpleType>\
	<xsd:simpleType name="ShapeType">\
		<xsd:restriction base="xsd:token">\
			<xsd:enumeration value="Person"/>\n\
			<xsd:enumeration value="Oval"/>\
			<xsd:enumeration value="Rectangle"/>\
			<xsd:enumeration value="RoundedRectangle"/>\
			<xsd:enumeration value="Star"/>\
			<xsd:enumeration value="LeftTriangle"/>\n\
			<xsd:enumeration value="RightTriangle"/>\
			<xsd:enumeration value="UpTriangle"/>\
			<xsd:enumeration value="DownTriangle"/>\
			<xsd:enumeration value="Note"/>\
		</xsd:restriction>\n\
	</xsd:simpleType>\
	<xsd:simpleType name="LineStyleType">\
		<xsd:restriction base="xsd:token">\n\
			<xsd:enumeration value="dotted"/>\n\
			<xsd:enumeration value="dashed"/>\
			<xsd:enumeration value="solid"/>\n\
		</xsd:restriction>\
	</xsd:simpleType>\
</xsd:schema>'