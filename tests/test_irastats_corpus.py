# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.corpus (pure Python, no GUI)."""

import sqlite3
import unittest

from qualcoder.irastats.corpus import (
    available_variables,
    build_coded_segments,
    build_document_segments,
    build_segments,
    variable_values,
)


SCHEMA = """
CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text);
CREATE TABLE code_name (cid integer primary key, name text);
CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer, seltext text,
                        pos0 integer, pos1 integer, owner text);
CREATE TABLE cases (caseid integer primary key, name text);
CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer);
CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer);
"""


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.executescript("""
        INSERT INTO source VALUES (1, 'doc1.txt', 'le chat mange. le chien dort.', NULL);
        INSERT INTO source VALUES (2, 'doc2.txt', 'le poisson nage.', 'docs:pdf');
        INSERT INTO code_name VALUES (1, 'alpha'), (2, 'beta');
        INSERT INTO code_text VALUES (1, 1, 1, 'le chat mange', 0, 14, 'bob'),
                                (2, 2, 1, 'le chat mange', 0, 14, 'bob'),
                                (3, 1, 2, 'le poisson', 0, 10, 'bob');
        INSERT INTO cases VALUES (1, 'caseA'), (2, 'caseB');
        INSERT INTO case_text VALUES (1, 1, 1, 0, 20), (2, 2, 1, 0, 20);
        INSERT INTO attribute VALUES (1, 'lang', 'file', 'fr', 1);
        INSERT INTO attribute VALUES (2, 'sexe', 'case', 'F', 1);
        INSERT INTO attribute VALUES (3, 'sexe', 'case', 'M', 2);
    """)
    return conn


class TestBuildCodedSegments(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def test_segments_grouped_by_location(self):
        segments = build_coded_segments(self.conn)
        self.assertEqual(len(segments), 2)
        first = segments[0]
        self.assertEqual(first["kind"], "coded")
        self.assertEqual(first["document"], "doc1.txt")
        self.assertEqual(first["text"], "le chat mange")
        self.assertEqual(sorted(first["codes"]), ["alpha", "beta"])
        self.assertEqual(first["variables"]["code"], "alpha + beta")

    def test_case_and_attributes_attached(self):
        segments = build_coded_segments(self.conn)
        first = segments[0]
        self.assertEqual(first["case"], "caseA")
        self.assertEqual(first["variables"]["case"], "caseA")
        self.assertEqual(first["variables"]["file:lang"], "fr")
        self.assertEqual(first["variables"]["case:sexe"], "F")
        # Segment of doc2 is not in any case
        second = segments[1]
        self.assertEqual(second["case"], "")
        self.assertNotIn("case:sexe", second["variables"])

    def test_file_filter(self):
        segments = build_coded_segments(self.conn, file_ids=[2])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["document"], "doc2.txt")

    def test_code_filter(self):
        segments = build_coded_segments(self.conn, code_ids=[2])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["codes"], ["beta"])

    def test_case_filter(self):
        # caseA covers doc1 only, so the doc2 segment is excluded
        segments = build_coded_segments(self.conn, case_ids=[1])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["document"], "doc1.txt")

    def test_case_filter_picks_the_selected_case_attributes(self):
        # doc1 belongs to both caseA and caseB: selecting only caseB must attach
        # caseB and its attributes, not caseA's
        segments = build_coded_segments(self.conn, case_ids=[2])
        self.assertEqual(segments[0]["case"], "caseB")
        self.assertEqual(segments[0]["variables"]["case:sexe"], "M")
        self.assertNotIn("caseA", str(segments[0]["variables"]))
        # without a filter, the first case by caseid wins (caseA)
        segments = build_coded_segments(self.conn)
        self.assertEqual(segments[0]["case"], "caseA")
        self.assertEqual(segments[0]["variables"]["case:sexe"], "F")

    def test_owner_filter(self):
        segments = build_coded_segments(self.conn, owner="nobody")
        self.assertEqual(segments, [])


class TestBuildDocumentSegments(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def test_documents(self):
        segments = build_document_segments(self.conn)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["kind"], "document")
        self.assertEqual(segments[0]["text"], "le chat mange. le chien dort.")
        self.assertEqual(segments[0]["variables"]["file:lang"], "fr")

    def test_documents_file_filter(self):
        segments = build_document_segments(self.conn, file_ids=[2])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["document"], "doc2.txt")

    def test_build_segments_include_documents(self):
        coded = build_segments(self.conn)
        self.assertEqual(len(coded), 2)
        all_segments = build_segments(self.conn, include_documents=True)
        self.assertEqual(len(all_segments), 4)
        self.assertEqual({s["kind"] for s in all_segments}, {"coded", "document"})


class TestVariables(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def test_variable_values(self):
        segments = build_coded_segments(self.conn)
        self.assertEqual(variable_values(segments, "document"), ["doc1.txt", "doc2.txt"])
        self.assertEqual(variable_values(segments, "code"), ["alpha + beta", "alpha"])
        self.assertEqual(variable_values(segments, "missing"), ["", ""])

    def test_available_variables(self):
        segments = build_coded_segments(self.conn)
        self.assertEqual(available_variables(segments), ["case", "case:sexe", "code", "document", "file:lang"])


if __name__ == "__main__":
    unittest.main()
