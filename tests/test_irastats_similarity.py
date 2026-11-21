# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.similarity (no GUI; matplotlib Agg-free Figure)."""

import unittest

import networkx as nx
import numpy as np

from qualcoder.irastats.lexicon import build_lexical_table
from qualcoder.irastats.similarity import (
    build_graph,
    cooccurrence,
    draw_similarity_graph,
    similarity_matrix,
)


def make_table():
    segments = [
        {"text": "chat chien", "variables": {"code": "x"}},
        {"text": "chat chien", "variables": {"code": "x"}},
        {"text": "chat poisson", "variables": {"code": "y"}},
    ]
    return build_lexical_table(segments)


class TestCooccurrence(unittest.TestCase):

    def test_counts(self):
        labels, cooc, doc_freq, freq = cooccurrence(make_table())
        self.assertEqual(sorted(labels), ["chat", "chien", "poisson"])
        idx = {label: i for i, label in enumerate(labels)}
        self.assertEqual(cooc[idx["chat"], idx["chien"]], 2)
        self.assertEqual(cooc[idx["chat"], idx["poisson"]], 1)
        self.assertEqual(cooc[idx["chien"], idx["poisson"]], 0)
        self.assertEqual(list(doc_freq), [3, 2, 1])
        self.assertEqual(dict(zip(labels, freq)), {"chat": 3, "chien": 2, "poisson": 1})

    def test_min_freq(self):
        labels, cooc, doc_freq, freq = cooccurrence(make_table(), min_freq=2)
        self.assertEqual(sorted(labels), ["chat", "chien"])


class TestSimilarity(unittest.TestCase):

    def setUp(self):
        self.labels, self.cooc, self.doc_freq, self.freq = cooccurrence(make_table())

    def test_jaccard(self):
        sim = similarity_matrix(self.labels, self.cooc, self.doc_freq, 3, method="jaccard")
        idx = {label: i for i, label in enumerate(self.labels)}
        self.assertAlmostEqual(sim[idx["chat"], idx["chien"]], 2 / 3)
        self.assertAlmostEqual(sim[idx["chat"], idx["poisson"]], 1 / 3)
        self.assertEqual(sim[idx["chien"], idx["poisson"]], 0.0)
        self.assertEqual(list(np.diagonal(sim)), [0.0, 0.0, 0.0])

    def test_chi2_phi(self):
        sim = similarity_matrix(self.labels, self.cooc, self.doc_freq, 3, method="chi2")
        idx = {label: i for i, label in enumerate(self.labels)}
        # pair (chien,poisson): table [[0,2],[1,0]] -> chi2 = 3*(0-2)^2/(2*1*1*2) = 3; phi2 = chi2/3 = 1
        self.assertAlmostEqual(sim[idx["chien"], idx["poisson"]], 1.0)
        # pair (chat,chien): table [[2,1],[0,0]] -> zero margin -> chi2 = 0
        self.assertEqual(sim[idx["chat"], idx["chien"]], 0.0)
        self.assertGreater(sim[idx["chien"], idx["poisson"]], sim[idx["chat"], idx["poisson"]])


class TestGraph(unittest.TestCase):

    def setUp(self):
        self.labels, self.cooc, self.doc_freq, self.freq = cooccurrence(make_table())

    def test_threshold(self):
        sim = similarity_matrix(self.labels, self.cooc, self.doc_freq, 3, method="jaccard")
        graph = build_graph(self.labels, sim, self.freq, threshold=0.5)
        self.assertEqual(graph.number_of_nodes(), 3)
        self.assertEqual(graph.number_of_edges(), 1)
        self.assertTrue(graph.has_edge("chat", "chien"))
        self.assertAlmostEqual(graph["chat"]["chien"]["weight"], 2 / 3)
        self.assertEqual(graph.nodes["chat"]["freq"], 3)

    def test_empty_graph(self):
        sim = similarity_matrix(self.labels, self.cooc, self.doc_freq, 3, method="jaccard")
        graph = build_graph(self.labels, sim, self.freq, threshold=0.99)
        self.assertIsInstance(graph, nx.Graph)
        self.assertEqual(graph.number_of_edges(), 0)

    def test_draw_figure(self):
        sim = similarity_matrix(self.labels, self.cooc, self.doc_freq, 3, method="jaccard")
        graph = build_graph(self.labels, sim, self.freq, threshold=0.2)
        fig = draw_similarity_graph(graph, seed=1)
        self.assertEqual(len(fig.axes), 1)
        # deterministic layout with a fixed seed
        pos1 = nx.spring_layout(graph, seed=1)
        fig2 = draw_similarity_graph(graph, seed=1)
        self.assertEqual(len(fig2.axes), 1)
        self.assertEqual(pos1.keys(), graph.nodes.keys())


if __name__ == "__main__":
    unittest.main()
