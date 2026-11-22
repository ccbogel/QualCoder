# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.topic_model (pure Python, no GUI, no sentence-transformers needed)."""

import unittest

import numpy as np

from qualcoder.topic_model import (
    _kmeans_numpy,
    bertopic_analysis,
    cluster_embeddings,
    ctfidf_topics,
    plot_topic_sizes,
    topics_summary,
)


def two_cluster_embeddings():
    rng = np.random.default_rng(0)
    a = rng.normal(loc=[1.0, 0.0], scale=0.05, size=(10, 2))
    b = rng.normal(loc=[0.0, 1.0], scale=0.05, size=(10, 2))
    return np.vstack([a, b])


class TestKMeansFallback(unittest.TestCase):

    def test_two_clusters(self):
        X = two_cluster_embeddings()
        labels = _kmeans_numpy(X, k=2, seed=42)
        self.assertEqual(len(labels), 20)
        self.assertEqual(len(set(labels.tolist())), 2)
        # the two groups must be separated
        self.assertEqual(len(set(labels[:10].tolist())), 1)
        self.assertEqual(len(set(labels[10:].tolist())), 1)
        self.assertNotEqual(labels[0], labels[10])

    def test_deterministic(self):
        X = two_cluster_embeddings()
        self.assertTrue(np.array_equal(_kmeans_numpy(X, 2, seed=1), _kmeans_numpy(X, 2, seed=1)))


class TestClusterEmbeddings(unittest.TestCase):

    def test_sklearn_or_fallback(self):
        X = two_cluster_embeddings()
        labels = cluster_embeddings(X, n_clusters=2, seed=42)
        self.assertEqual(len(labels), 20)
        self.assertEqual(len(set(labels.tolist())), 2)

    def test_empty(self):
        self.assertEqual(len(cluster_embeddings(np.zeros((0, 3)))), 0)

    def test_n_clusters_heuristic(self):
        X = two_cluster_embeddings()
        labels = cluster_embeddings(X, n_clusters=None, min_cluster_size=5, seed=42)
        self.assertGreaterEqual(len(set(labels.tolist())), 2)


class TestCtfidf(unittest.TestCase):

    def test_top_words_per_topic(self):
        texts = (["chat chien chat"] * 5 + ["voiture route moteur"] * 5)
        labels = np.array([0] * 5 + [1] * 5)
        result = ctfidf_topics(texts, labels, top_n=3, stopwords=set())
        top0 = [w for w, _ in result[0]]
        top1 = [w for w, _ in result[1]]
        self.assertIn("chat", top0)
        self.assertIn("voiture", top1)
        self.assertNotIn("voiture", top0)
        # scores are positive
        self.assertTrue(all(s > 0 for _, s in result[0]))

    def test_noise_label(self):
        texts = ["a b", "c d", "e f"]
        labels = np.array([0, 0, -1])
        result = ctfidf_topics(texts, labels, top_n=2, stopwords=set())
        self.assertIn(-1, result)
        self.assertIn(0, result)


class TestTopicsSummary(unittest.TestCase):

    def test_summary(self):
        texts = (["chat chien os patte"] * 5 + ["voiture route moteur roue"] * 5)
        labels = np.array([0] * 5 + [1] * 5)
        topics = topics_summary(texts, labels, top_n=4, stopwords=set())
        self.assertEqual(len(topics), 2)
        self.assertTrue(all(t["size"] == 5 for t in topics))
        words = {w for t in topics for w, _ in t["top_words"]}
        self.assertIn("chat", words)
        self.assertIn("voiture", words)
        self.assertTrue(all(len(t["representative_texts"]) <= 3 for t in topics))

    def test_plot_topic_sizes(self):
        result = {"topics": [{"topic": 0, "size": 5, "top_words": [], "representative_texts": []}],
                  "n_topics": 1}
        fig = plot_topic_sizes(result)
        self.assertEqual(len(fig.axes), 1)


class TestBertopicAnalysis(unittest.TestCase):

    def test_requires_sentence_transformers(self):
        # in this test environment sentence-transformers is not installed: a clear
        # ImportError must be raised (the GUI catches it and shows a message)
        try:
            import sentence_transformers  # noqa: F401
            self.skipTest("sentence-transformers installed")
        except ImportError:
            pass
        with self.assertRaises(ImportError):
            bertopic_analysis([{"text": "un texte", "variables": {}}])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            bertopic_analysis([])


if __name__ == "__main__":
    unittest.main()
