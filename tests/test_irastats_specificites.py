# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.specificites (no GUI)."""

import unittest

from qualcoder.irastats.lexicon import build_lexical_table
from qualcoder.irastats.report_html import specificites_html
from qualcoder.irastats.specificites import (
    chi2_statistic,
    format_p,
    modalities_of,
    specificities,
    specificity_rows,
)


def make_table():
    segments = [
        {"text": "pomme pomme", "variables": {"code": "a"}},
        {"text": "pomme", "variables": {"code": "a"}},
        {"text": "poire poire poire", "variables": {"code": "b"}},
    ]
    return build_lexical_table(segments)


class TestChi2Statistic(unittest.TestCase):

    def test_perfect_association(self):
        # [[3, 0], [0, 3]] -> chi2 = 6
        self.assertAlmostEqual(chi2_statistic(3, 0, 0, 3), 6.0)

    def test_independence(self):
        self.assertAlmostEqual(chi2_statistic(1, 1, 1, 1), 0.0)

    def test_known_value(self):
        # [[10, 5], [5, 10]]: N=30, chi2 = 30*(100-25)^2/(15*15*15*15) = 30*5625/50625 = 3.333...
        self.assertAlmostEqual(chi2_statistic(10, 5, 5, 10), 30 * 5625 / 50625)

    def test_degenerate(self):
        self.assertEqual(chi2_statistic(0, 0, 0, 0), 0.0)
        self.assertEqual(chi2_statistic(5, 0, 0, 0), 0.0)


class TestSpecificities(unittest.TestCase):

    def setUp(self):
        self.table = make_table()

    def test_modalities(self):
        self.assertEqual(modalities_of(self.table, "code"), ["a", "b"])

    def test_results(self):
        results = specificities(self.table, "code", p_threshold=None)
        self.assertEqual(len(results), 4)  # 2 forms x 2 modalities
        for row in results:
            self.assertAlmostEqual(row["chi2"], 6.0)
            self.assertAlmostEqual(row["effectif_attendu"], 1.5)
        by_key = {(r["forme"], r["modalite"]): r for r in results}
        self.assertEqual(by_key[("pomme", "a")]["signe"], 1)
        self.assertEqual(by_key[("pomme", "a")]["valeur"], 6.0)
        self.assertEqual(by_key[("pomme", "b")]["signe"], -1)
        self.assertEqual(by_key[("poire", "b")]["signe"], 1)
        self.assertEqual(by_key[("poire", "a")]["signe"], -1)
        # p-value of chi2=6 with df=1 is about 0.0143
        self.assertAlmostEqual(by_key[("pomme", "a")]["p"], 0.0143, places=3)

    def test_sorted_most_specific_first(self):
        results = specificities(self.table, "code", p_threshold=None)
        chi2_values = [r["chi2"] for r in results]
        self.assertEqual(chi2_values, sorted(chi2_values, reverse=True))

    def test_p_threshold_filter(self):
        # chi2=6 -> p ~ 0.0143 > 0.01, so everything is filtered out
        self.assertEqual(specificities(self.table, "code", p_threshold=0.01), [])
        # default 0.05 keeps all four rows
        self.assertEqual(len(specificities(self.table, "code")), 4)

    def test_min_freq_filter(self):
        self.assertEqual(specificities(self.table, "code", min_freq=4, p_threshold=None), [])

    def test_forms_filter(self):
        results = specificities(self.table, "code", forms=["pomme"], p_threshold=None)
        self.assertEqual({r["forme"] for r in results}, {"pomme"})

    def test_rows(self):
        rows = specificity_rows(specificities(self.table, "code", p_threshold=None))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][:2], ["poire", "a"])  # alphabetical tie-break
        # p formatted by convention: 3 decimals (chi2=6 -> p ~ 0.0143 -> "0.014")
        self.assertEqual(rows[0][6], "0.014")

    def test_format_p(self):
        self.assertEqual(format_p(0.0143), "0.014")
        self.assertEqual(format_p(0.05), "0.050")
        self.assertEqual(format_p(0.001), "0.001")
        self.assertEqual(format_p(0.0009), "<0.001")
        self.assertEqual(format_p(0.0), "<0.001")
        self.assertEqual(format_p(1.0), "1.000")

    def test_html_highlights_signs(self):
        html = specificites_html(specificities(self.table, "code", p_threshold=None), variable="code")
        self.assertIn('class="pos"', html)
        self.assertIn('class="neg"', html)


if __name__ == "__main__":
    unittest.main()
