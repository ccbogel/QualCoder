# -*- coding: utf-8 -*-

'''
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

This file contains hardcoded versions of the REFI-QDA XSD files for:
    codebook

Hard-coding reduces potential problems when pyinstaller tries to import data files.
'''


codebook = '<?xml version="1.0" encoding="UTF-8"?>\
<xsd:schema xmlns="urn:QDA-XML:codebook:1.0" xmlns:xsd="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:QDA-XML:codebook:1.0" elementFormDefault="qualified" attributeFormDefault="unqualified" version="1.0">\
<!‐‐ =====ElementDeclarations===== ‐‐>\
<xsd:elementname="CodeBook" type="CodeBookType">\
<xsd:annotation>\
<xsd:documentation>This element MUST be conveyed as the root element in any instance document based on this Schema expression\
</xsd:documentation>\
</xsd:annotation>\
</xsd:element>\
<!‐‐ =====TypeDefinitions===== ‐‐>\
<xsd:complexTypename="CodeBookType">\
<xsd:sequence>\
<xsd:elementname="Codes" type="CodesType"/>\
<xsd:elementname="Sets" type="SetsType" minOccurs="0"/>\
</xsd:sequence>\
<xsd:attributename="origin"type="xsd:string"/>\
</xsd:complexType>\
<xsd:complexTypename="CodesType">\
<xsd:sequence>\
<xsd:elementname="Code"type="CodeType" maxOccurs="unbounded"/>\
</xsd:sequence></xsd:complexType>\
<xsd:complexTypename="SetsType">\
<xsd:sequence>\
<xsd:elementname="Set"type="SetType" maxOccurs="unbounded"/>\
</xsd:sequence>\
</xsd:complexType>\
<xsd:complexTypename="CodeType">\
<xsd:sequence>\
<xsd:elementname="Description" type="xsd:string" minOccurs="0"/>\
<xsd:elementname="Code" type="CodeType"minOccurs="0" maxOccurs="unbounded"/>\
</xsd:sequence>\
<xsd:attributename="guid" type="GUIDType" use="required"/>\
<xsd:attributename="name" type="xsd:string" use="required"/>\
<xsd:attributename="isCodable" type="xsd:boolean" use="required"/>\
<xsd:attributename="color" type="RGBType"/>\
</xsd:complexType>\
<xsd:complexTypename="SetType">\
<xsd:sequence>\
<xsd:elementname="Description" type="xsd:string" minOccurs="0"/>\
<xsd:elementname="MemberCode" type="MemberCodeType" minOccurs="0" maxOccurs="unbounded"/>\
</xsd:sequence>\
<xsd:attributename="guid" type="GUIDType" use="required"/>\
<xsd:attributename="name" type="xsd:string" use="required"/>\
</xsd:complexType>\
<xsd:complexTypename="MemberCodeType">\
<xsd:attributename="guid" type="GUIDType" use="required"/>\
</xsd:complexType>\
<xsd:simpleTypename="GUIDType">\
<xsd:restrictionbase="xsd:token">\
<xsd:patternvalue="([0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12})|(\{[0‐9a‐fA‐F]{8}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{4}‐[0‐9a‐fA‐F]{12}\})"/>\
</xsd:restriction>\
</xsd:simpleType>\
<xsd:simpleTypename="RGBType">\
<xsd:restrictionbase="xsd:token">\
<xsd:patternvalue="#([A‐Fa‐f0‐9]{6}|[A‐Fa‐f0‐9]{3})"/>\
</xsd:restriction>\
</xsd:simpleType>\
</xsd:schema>'