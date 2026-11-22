# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.similarity (no GUI; matplotlib Agg-free Figure)."""

import unittest

import networkx as nx
import numpy as np

from qualcoder.irastats.lexicon import build_lexical_table
from qualcoder.irastats.similarity import (
    build_graph,
    cooccurrence,
    detect_communities,
    draw_similarity_graph,
    halo_neighbors,
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


class TestCommunitiesAndHalos(unittest.TestCase):

    def make_two_cluster_graph(self):
        # two strong pairs, no cross edges
        labels = ["chat", "chien", "poisson", "requin"]
        sim = np.array([
            [0.0, 0.9, 0.0, 0.0],
            [0.9, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.8],
            [0.0, 0.0, 0.8, 0.0],
        ])
        freq = np.array([5, 4, 3, 2])
        return build_graph(labels, sim, freq, threshold=0.5)

    def test_detect_communities(self):
        graph = self.make_two_cluster_graph()
        communities = detect_communities(graph, seed=42)
        self.assertEqual(len(communities), 2)
        self.assertEqual({frozenset(c) for c in communities},
                         {frozenset({"chat", "chien"}), frozenset({"poisson", "requin"})})
        self.assertEqual(graph.nodes["chat"]["community"], graph.nodes["chien"]["community"])
        self.assertNotEqual(graph.nodes["chat"]["community"], graph.nodes["poisson"]["community"])

    def test_detect_communities_empty(self):
        import networkx as nx
        self.assertEqual(detect_communities(nx.Graph()), [])

    def test_halo_neighbors(self):
        graph = self.make_two_cluster_graph()
        self.assertEqual(halo_neighbors(graph, "chat", radius=1), {"chat", "chien"})
        self.assertEqual(halo_neighbors(graph, "unknown", radius=1), set())
        # path graph for radius 2
        path = nx.path_graph(["a", "b", "c", "d"])
        self.assertEqual(halo_neighbors(path, "a", radius=1), {"a", "b"})
        self.assertEqual(halo_neighbors(path, "a", radius=2), {"a", "b", "c"})

    def test_draw_with_communities_and_halo(self):
        graph = self.make_two_cluster_graph()
        detect_communities(graph, seed=42)
        fig = draw_similarity_graph(graph, seed=1, halo="chat")
        ax = fig.axes[0]
        # one halo circle
        self.assertEqual(len(ax.patches), 1)
        # two distinct node colors (two communities): the nodes are the PathCollection
        from matplotlib.collections import PathCollection
        scatters = [c for c in ax.collections if isinstance(c, PathCollection)]
        self.assertEqual(len(scatters), 1)
        colors = {tuple(c) for c in scatters[0].get_facecolor()}
        self.assertGreaterEqual(len(colors), 2)


if __name__ == "__main__":
    unittest.main()
