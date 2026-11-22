# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.descstats and irastats.report_html (no GUI)."""

import unittest

from qualcoder.irastats.descstats import (
    descendant_statistics,
    frequency_rows,
    hapax_rows,
    variable_rows,
)
from qualcoder.irastats.lexicon import build_lexical_table
from qualcoder.irastats.report_html import descstats_html, escape, html_page, table_html


def make_table():
    segments = [
        {"text": "le chat mange le poisson", "variables": {"code": "a", "case": "c1"}},
        {"text": "le chien mange", "variables": {"code": "b", "case": "c1"}},
        {"text": "le chat dort", "variables": {"code": "a", "case": "c2"}},
    ]
    return build_lexical_table(segments, stopwords={"le"})


class TestDescendantStatistics(unittest.TestCase):

    def setUp(self):
        self.table = make_table()
        self.stats = descendant_statistics(self.table, variable="code")

    def test_counts(self):
        self.assertEqual(self.stats["total_occurrences"], 7)
        self.assertEqual(self.stats["distinct_forms"], 5)
        self.assertEqual(self.stats["active_forms"], 5)  # min_freq=1 default
        self.assertEqual(self.stats["supplementary_forms"], 0)
        self.assertEqual(self.stats["hapax"], ["chien", "dort", "poisson"])

    def test_frequencies_sorted(self):
        self.assertEqual(self.stats["frequencies"][0], ("chat", 2))
        self.assertEqual(self.stats["frequencies"][1], ("mange", 2))
        # Ties sorted alphabetically
        self.assertEqual([f for f, _ in self.stats["frequencies"]],
                         ["chat", "mange", "chien", "dort", "poisson"])

    def test_by_variable(self):
        by_code = self.stats["by_variable"]
        self.assertEqual(set(by_code.keys()), {"a", "b"})
        self.assertEqual(by_code["a"], {"segments": 2, "occurrences": 5, "distinct_forms": 4})
        self.assertEqual(by_code["b"], {"segments": 1, "occurrences": 2, "distinct_forms": 2})

    def test_active_filter(self):
        table = build_lexical_table(
            [{"text": "aaa bbb aaa ccc", "variables": {}}], stopwords=set(), min_freq=2)
        stats = descendant_statistics(table)
        self.assertEqual(stats["active_forms"], 1)
        self.assertEqual(stats["active_frequencies"], [("aaa", 2)])
        self.assertEqual(stats["supplementary_forms"], 2)

    def test_no_variable(self):
        stats = descendant_statistics(self.table)
        self.assertIsNone(stats["by_variable"])


class TestRows(unittest.TestCase):

    def setUp(self):
        self.stats = descendant_statistics(make_table(), variable="case")

    def test_frequency_rows(self):
        rows = frequency_rows(self.stats)
        self.assertEqual(rows[0], ["chat", 2, round(100.0 * 2 / 7, 4)])
        self.assertEqual(len(rows), 5)

    def test_hapax_rows(self):
        self.assertEqual(len(hapax_rows(self.stats)), 3)

    def test_variable_rows(self):
        rows = variable_rows(self.stats)
        self.assertIn(["c1", 2, 5, 4], rows)
        self.assertIn(["c2", 1, 2, 2], rows)


class TestHtml(unittest.TestCase):

    def test_escape(self):
        self.assertEqual(escape("<b>&\""), "&lt;b&gt;&amp;&quot;")

    def test_table_html(self):
        out = table_html(["a", "b"], [["<x>", 1]], row_classes=["pos"])
        self.assertIn('<tr class="pos">', out)
        self.assertIn("<td>&lt;x&gt;</td>", out)

    def test_descstats_html(self):
        html = descstats_html(self.stats if hasattr(self, "stats") else descendant_statistics(make_table(), variable="code"),
                              variable="code")
        page = html_page("t", html)
        self.assertIn("<table>", page)
        self.assertIn("chat", page)


if __name__ == "__main__":
    unittest.main()
