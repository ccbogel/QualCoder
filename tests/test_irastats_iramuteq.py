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
    iramuteq_to_rows,
    iramuteq_token,
    parse_iramuteq,
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


class TestParseIramuteq(unittest.TestCase):

    SAMPLE = (
        "**** *doc_doc1 *age_25 *sexe_F\n"
        "le chat mange.\n"
        "le chien dort.\n"
        "\n"
        "**** *doc_doc2 *age_30 *sexe_M *ville_Paris\n"
        "un deux trois\n"
    )

    def test_not_iramuteq_returns_empty(self):
        self.assertEqual(parse_iramuteq("just some plain text\nno header lines\n"), [])
        self.assertEqual(parse_iramuteq(""), [])

    def test_parse_blocks_and_variables(self):
        segments = parse_iramuteq(self.SAMPLE)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["document"], "doc1")
        self.assertEqual(segments[0]["case"], "")
        self.assertEqual(segments[0]["variables"], {"age": "25", "sexe": "F"})
        self.assertEqual(segments[0]["text"], "le chat mange.\nle chien dort.")
        self.assertEqual(segments[1]["variables"], {"age": "30", "sexe": "M", "ville": "Paris"})
        self.assertEqual(segments[1]["text"], "un deux trois")

    def test_cas_and_repeated_variables(self):
        segments = parse_iramuteq("**** *cas_caseA *code_alpha *code_beta\ntexte\n")
        self.assertEqual(segments[0]["case"], "caseA")
        self.assertEqual(segments[0]["document"], "")
        self.assertEqual(segments[0]["variables"], {"code": "alpha + beta"})

    def test_token_without_modality_and_bom(self):
        segments = parse_iramuteq("\ufeff**** *flag\ntext\n")
        self.assertEqual(segments[0]["variables"], {"flag": ""})

    def test_roundtrip_of_export(self):
        conn = make_conn()
        try:
            segments = build_segments(conn, include_documents=True)
        finally:
            conn.close()
        parsed = parse_iramuteq(format_iramuteq(segments))
        self.assertEqual(len(parsed), len(segments))
        # doc/cas reserved variables and text are restored (names tokenised: "." -> "_")
        self.assertEqual(parsed[0]["document"], "doc1_txt")
        self.assertEqual(parsed[0]["case"], "caseA")
        self.assertEqual(parsed[0]["text"], segments[0]["text"])
        self.assertIn("alpha + beta", parsed[0]["variables"].get("code", ""))
        self.assertEqual(parsed[0]["variables"].get("file"), "lang_fr")

    def test_iramuteq_to_rows(self):
        columns, rows = iramuteq_to_rows(parse_iramuteq(self.SAMPLE))
        self.assertEqual(columns, ["doc", "text", "age", "sexe", "ville"])
        self.assertEqual(rows[0]["doc"], "doc1")
        self.assertEqual(rows[0]["text"], "le chat mange.\nle chien dort.")
        self.assertEqual(rows[0]["age"], "25")
        self.assertEqual(rows[0]["ville"], "")
        self.assertEqual(rows[1]["ville"], "Paris")

    def test_iramuteq_to_rows_generated_names_and_case(self):
        columns, rows = iramuteq_to_rows(parse_iramuteq("**** *cas_caseA *age_25\nhello\n**** *age_30\nworld\n"))
        self.assertEqual(columns, ["doc", "text", "cas", "age"])
        self.assertEqual(rows[0]["doc"], "caseA")
        self.assertEqual(rows[0]["cas"], "caseA")
        self.assertEqual(rows[1]["doc"], "Text_2")
        self.assertEqual(rows[1]["cas"], "")
        self.assertEqual(rows[1]["age"], "30")


if __name__ == "__main__":
    unittest.main()
