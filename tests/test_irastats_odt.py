# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.report_odt (no GUI)."""

import os
import tempfile
import unittest
import zipfile

from qualcoder.irastats.descstats import descendant_statistics
from qualcoder.irastats.lexicon import build_lexical_table
from qualcoder.irastats.report_odt import descstats_odt


def make_stats():
    segments = [
        {"text": "pomme pomme poire", "variables": {"code": "a"}},
        {"text": "pomme poire poire", "variables": {"code": "b"}},
        {"text": "poire raisin", "variables": {"code": "b"}},
    ]
    table = build_lexical_table(segments)
    return descendant_statistics(table, variable="code")


class TestDescstatsOdt(unittest.TestCase):

    def test_builds_odt_document(self):
        stats = make_stats()
        doc = descstats_odt(stats, variable="code")
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "stats.odt")
            doc.save(filepath)
            self.assertTrue(os.path.exists(filepath))
            with zipfile.ZipFile(filepath) as archive:
                self.assertIn("content.xml", archive.namelist())
                content = archive.read("content.xml").decode("utf-8")
            # forms and modalities appear in the document text
            self.assertIn("pomme", content)
            self.assertIn("poire", content)
            self.assertIn("raisin", content)

    def test_without_variable(self):
        stats = make_stats()
        stats["by_variable"] = None
        doc = descstats_odt(stats)
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "stats.odt")
            doc.save(filepath)
            self.assertTrue(os.path.getsize(filepath) > 0)


if __name__ == "__main__":
    unittest.main()
