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
        # native IRaMuTeQ variable format: *variable_modality, restricted charset
        self.assertIn("*code_alpha", lines[0])
        self.assertIn("*code_beta", lines[0])
        self.assertIn("*cas_caseA", lines[0])
        self.assertIn("*doc_doc1_txt", lines[0])
        self.assertIn("*file_lang_fr", lines[0])
        self.assertIn("*case_sexe_F", lines[0])
        self.assertNotIn("=", lines[0])
        self.assertEqual(lines[1], "le chat mange")

    def test_document_segment(self):
        segments = build_segments(self.conn, include_documents=True)
        doc = [s for s in segments if s["kind"] == "document"][0]
        text = segment_to_iramuteq(doc)
        self.assertIn("**** *doc_doc1_txt", text.split("\n")[0])
        self.assertNotIn("*code_", text.split("\n")[0])
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
