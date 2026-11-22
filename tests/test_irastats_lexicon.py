# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.lexicon (pure Python, no GUI)."""

import unittest

import numpy as np

from qualcoder.irastats.lexicon import build_lexical_table


def make_segments():
    return [
        {"text": "le chat mange le poisson", "variables": {"code": "a"}},
        {"text": "le chien mange", "variables": {"code": "b"}},
    ]


class TestBuildLexicalTable(unittest.TestCase):

    def test_matrix_and_frequencies(self):
        table = build_lexical_table(make_segments(), stopwords={"le"})
        self.assertEqual(table.matrix.shape, (4, 2))
        frequencies = dict(table.frequencies())
        self.assertEqual(frequencies, {"mange": 2, "chat": 1, "poisson": 1, "chien": 1})
        # Sorted by decreasing frequency, then alphabetically
        self.assertEqual(table.frequencies()[0], ("mange", 2))
        self.assertEqual([form for form, _ in table.frequencies()],
                         ["mange", "chat", "chien", "poisson"])
        index = {form: i for i, form in enumerate(table.forms)}
        self.assertEqual(table.matrix[index["mange"], 0], 1)
        self.assertEqual(table.matrix[index["mange"], 1], 1)
        self.assertEqual(table.matrix[index["chat"], 1], 0)

    def test_active_and_supplementary(self):
        table = build_lexical_table(make_segments(), stopwords={"le"}, min_freq=2)
        self.assertEqual(table.active_forms, ["mange"])
        self.assertEqual(sorted(table.supplementary_forms), ["chat", "chien", "poisson"])
        self.assertEqual(table.active_matrix.shape, (1, 2))

    def test_active_supplementary_lists(self):
        table = build_lexical_table(make_segments(), stopwords={"le"}, min_freq=1,
                                    supplementary_forms=["mange"])
        self.assertNotIn("mange", table.active_forms)
        self.assertIn("mange", table.supplementary_forms)
        table2 = build_lexical_table(make_segments(), stopwords={"le"}, min_freq=5,
                                     active_forms=["chat"])
        self.assertEqual(table2.active_forms, ["chat"])

    def test_hapax(self):
        table = build_lexical_table(make_segments(), stopwords={"le"})
        self.assertEqual(table.hapax(), ["chat", "chien", "poisson"])

    def test_stemming_merges_forms(self):
        segments = [{"text": "manger mangé", "variables": {}}]
        table = build_lexical_table(segments, stem=True, language="fr")
        self.assertEqual(table.frequencies(), [("mang", 2)])

    def test_matrix_values_are_numpy_counts(self):
        table = build_lexical_table(make_segments(), stopwords={"le"})
        total = int(np.asarray(table.matrix.sum()).item())
        self.assertEqual(total, 5)


if __name__ == "__main__":
    unittest.main()
