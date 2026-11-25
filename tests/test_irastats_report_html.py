# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.report_html (no GUI)."""

import unittest

from qualcoder.irastats.descstats import descendant_statistics
from qualcoder.irastats.lexicon import build_lexical_table
from qualcoder.irastats.report_html import (
    descstats_html,
    specificites_html,
    statistics_html,
)
from qualcoder.irastats.specificites import specificities


def make_stats():
    segments = [
        {"text": "pomme pomme", "variables": {"code": "a"}},
        {"text": "pomme", "variables": {"code": "a"}},
        {"text": "poire poire poire", "variables": {"code": "b"}},
    ]
    table = build_lexical_table(segments)
    stats = descendant_statistics(table, variable="code")
    results = specificities(table, "code")
    return table, stats, results


class TestReportHtml(unittest.TestCase):

    def test_descstats_html_has_definitions_and_category(self):
        _, stats, _ = make_stats()
        html = descstats_html(stats, variable="code")
        self.assertIn("Definitions", html)
        self.assertIn("Category", html)
        self.assertNotIn("Modality", html)

    def test_specificites_html_uses_category(self):
        table, _, results = make_stats()
        html = specificites_html(results, variable="code")
        self.assertIn("Category", html)
        self.assertNotIn("Modality", html)

    def test_statistics_html_combines_both_reports(self):
        _, stats, results = make_stats()
        html = statistics_html(stats, results, variable="code", p_threshold=0.05)
        # one single page containing both sections
        self.assertEqual(html.count("<html>"), 1)
        self.assertIn("Descending statistics", html)
        self.assertIn("Specificities", html)

    def test_statistics_html_without_variable(self):
        _, stats, _ = make_stats()
        html = statistics_html(stats, None, variable=None)
        self.assertIn("Descending statistics", html)
        self.assertIn("Select a partition variable", html)
        self.assertNotIn("Specificities (chi-square)", html)


if __name__ == "__main__":
    unittest.main()
