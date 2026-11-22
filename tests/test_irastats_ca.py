# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.ca (no GUI; matplotlib Figure without backend)."""

import unittest

import numpy as np

from qualcoder.irastats.ca import ca_coordinate_rows, correspondence_analysis, lexical_table_by_variable, plot_ca
from qualcoder.irastats.lexicon import build_lexical_table


class TestCorrespondenceAnalysis(unittest.TestCase):

    def test_symmetric_2x2(self):
        # [[10, 5], [5, 10]]: chi2 = 10/3, N = 30, inertia = chi2/N = 1/9
        result = correspondence_analysis(np.array([[10, 5], [5, 10]]),
                                         row_labels=["r1", "r2"], col_labels=["c1", "c2"])
        self.assertAlmostEqual(result["inertia"], (10 / 3) / 30)
        self.assertAlmostEqual(result["eigenvalues"][0], (10 / 3) / 30)
        self.assertAlmostEqual(result["percent"][0], 100.0)
        # the two rows are symmetric on opposite sides of axis 1 (SVD sign is arbitrary)
        self.assertAlmostEqual(result["row_coords"][0, 0], -result["row_coords"][1, 0])
        self.assertAlmostEqual(abs(result["row_coords"][0, 0]), 1 / 3)
        # all inertia on axis 1 -> cos2 = 1
        self.assertAlmostEqual(result["row_cos2"][0, 0], 1.0)
        self.assertAlmostEqual(result["row_contrib"][0, 0], 0.5)

    def test_inertia_equals_chi2_over_n(self):
        M = np.array([[4, 1, 0], [1, 3, 2], [0, 2, 5]])
        result = correspondence_analysis(M)
        n = M.sum()
        row = M.sum(axis=1)
        col = M.sum(axis=0)
        expected = 0.0
        for i in range(3):
            for j in range(3):
                exp = row[i] * col[j] / n
                expected += (M[i, j] - exp) ** 2 / exp
        expected /= n
        self.assertAlmostEqual(result["inertia"], expected)
        self.assertAlmostEqual(result["eigenvalues"].sum(), expected)
        # at most min(n,m)-1 = 2 non-zero eigenvalues
        self.assertLessEqual(np.count_nonzero(result["eigenvalues"] > 1e-12), 2)

    def test_zero_rows_dropped(self):
        result = correspondence_analysis(np.array([[0, 0], [3, 4]]), row_labels=["empty", "full"])
        self.assertEqual(result["row_labels"], ["full"])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            correspondence_analysis(np.zeros((2, 2)))

    def test_coordinate_rows(self):
        result = correspondence_analysis(np.array([[10, 5], [5, 10]]), row_labels=["r1", "r2"])
        rows = ca_coordinate_rows(result, n_axes=1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "r1")
        self.assertEqual(rows[0][1], 15)

    def test_plot_single_column_no_indexerror(self):
        # a 1-column table has a single axis; plotting axes (0, 1) must not raise
        result = correspondence_analysis(np.array([[5], [3], [1]]), row_labels=["a", "b", "c"],
                                         col_labels=["only"])
        fig = plot_ca(result, axes=(0, 1))
        self.assertEqual(len(fig.axes), 1)

    def test_plot(self):
        result = correspondence_analysis(np.array([[10, 5], [5, 10]]), row_labels=["r1", "r2"],
                                         col_labels=["c1", "c2"])
        fig = plot_ca(result, axes=(0, 1), top_forms=10)
        self.assertEqual(len(fig.axes), 1)


class TestLexicalTableByVariable(unittest.TestCase):

    def test_aggregation(self):
        segments = [
            {"text": "chat chien", "variables": {"code": "a"}},
            {"text": "chat", "variables": {"code": "a"}},
            {"text": "poisson", "variables": {"code": "b"}},
        ]
        table = build_lexical_table(segments)
        row_labels, col_labels, matrix = lexical_table_by_variable(table, "code")
        self.assertEqual(col_labels, ["a", "b"])
        self.assertEqual(sorted(row_labels), ["chat", "chien", "poisson"])
        dense = matrix.toarray()
        idx = {label: i for i, label in enumerate(row_labels)}
        self.assertEqual(dense[idx["chat"], 0], 2)
        self.assertEqual(dense[idx["chat"], 1], 0)
        self.assertEqual(dense[idx["poisson"], 1], 1)
        # CA runs on the aggregated matrix; inertia = chi2 of the table / N
        result = correspondence_analysis(matrix, row_labels=row_labels, col_labels=col_labels)
        self.assertEqual(result["col_labels"], ["a", "b"])
        n = dense.sum()
        row = dense.sum(axis=1)
        col = dense.sum(axis=0)
        expected = 0.0
        for i in range(dense.shape[0]):
            for j in range(dense.shape[1]):
                exp = row[i] * col[j] / n
                expected += (dense[i, j] - exp) ** 2 / exp
        self.assertAlmostEqual(result["inertia"], expected / n)


if __name__ == "__main__":
    unittest.main()
