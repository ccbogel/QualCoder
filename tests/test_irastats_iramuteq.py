# -*- coding: utf-8 -*-

"""Unit tests for the IRaMuTeQ export of qualcoder.irastats.corpus (no GUI)."""

import tempfile
import unittest
from pathlib import Path

from qualcoder.irastats.corpus import (
    build_coded_segments,
    build_segments,
    export_iramuteq,
    format_iramuteq,
    iramuteq_token,
    segment_to_iramuteq,
)
from tests.test_irastats_corpus import make_conn


class TestToken(unittest.TestCase):

    def test_whitespace_replaced(self):
        self.assertEqual(iramuteq_token("mon code 1"), "mon_code_1")
        self.assertEqual(iramuteq_token("  a\tb "), "a_b")
        self.assertEqual(iramuteq_token(12), "12")


class TestSegmentFormat(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def tearDown(self):
        self.conn.close()

    def test_coded_segment_lines(self):
        segments = build_coded_segments(self.conn)
        text = segment_to_iramuteq(segments[0])
        lines = text.split("\n")
        self.assertTrue(lines[0].startswith("**** "))
        self.assertIn("*code=alpha", lines[0])
        self.assertIn("*code=beta", lines[0])
        self.assertIn("*cas=caseA", lines[0])
        self.assertIn("*doc=doc1.txt", lines[0])
        self.assertIn("*file:lang=fr", lines[0])
        self.assertIn("*case:sexe=F", lines[0])
        self.assertEqual(lines[1], "le chat mange")

    def test_document_segment(self):
        segments = build_segments(self.conn, include_documents=True)
        doc = [s for s in segments if s["kind"] == "document"][0]
        text = segment_to_iramuteq(doc)
        self.assertIn("**** *doc=doc1.txt", text.split("\n")[0])
        self.assertNotIn("*code=", text.split("\n")[0])
        self.assertIn("le chat mange. le chien dort.", text)

    def test_format_and_export(self):
        segments = build_segments(self.conn, include_documents=True)
        text = format_iramuteq(segments)
        self.assertEqual(text.count("****"), 4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corpus.txt"
            count = export_iramuteq(segments, str(path))
            self.assertEqual(count, 4)
            self.assertEqual(path.read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
