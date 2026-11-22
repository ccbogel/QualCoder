# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.reinert (Reinert CHD) - deterministic, no GUI."""

import unittest

import numpy as np

from qualcoder.irastats.lexicon import build_lexical_table
from qualcoder.irastats.reinert import (
    best_binary_split,
    build_uci_segments,
    chi2_contingency,
    draw_dendrogram,
    reinert_classification,
    reinert_from_segments,
    split_sentences,
    split_uci,
)


class TestSplitUci(unittest.TestCase):

    def test_sentences(self):
        self.assertEqual(split_sentences("Un deux. Trois quatre! Cinq\n six."), ["Un deux.", "Trois quatre!", "Cinq", " six."])

    def test_uci_size_and_punctuation_bound(self):
        text = "alpha beta. gamma delta. epsilon zeta. eta theta."
        ucis = split_uci(text, size=4)
        # sentences of 2 tokens packed by 2 -> UCI of 4 tokens, never crossing a sentence
        self.assertEqual(ucis, ["alpha beta gamma delta", "epsilon zeta eta theta"])

    def test_long_sentence_hard_cut(self):
        text = " ".join(f"w{i}" for i in range(10)) + "."
        ucis = split_uci(text, size=4)
        self.assertEqual([len(u.split()) for u in ucis], [4, 4, 2])

    def test_empty(self):
        self.assertEqual(split_uci("", size=40), [])
        self.assertEqual(split_uci("... !!!", size=40), [])

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            split_uci("alpha beta", size=0)

    def test_build_uci_segments_inherits_variables(self):
        segments = [{"text": "alpha beta. gamma delta.", "variables": {"code": "a"}}]
        uci_segments = build_uci_segments(segments, size=2)
        self.assertEqual(len(uci_segments), 2)
        self.assertTrue(all(s["variables"] == {"code": "a"} for s in uci_segments))


class TestChi2Contingency(unittest.TestCase):

    def test_known_value(self):
        # 2x2 table [[10, 5], [5, 10]] -> chi2 = 10/3
        self.assertAlmostEqual(chi2_contingency(np.array([[10, 5], [5, 10]])), 10 / 3)

    def test_zero(self):
        self.assertEqual(chi2_contingency(np.zeros((2, 3))), 0.0)


class TestBestBinarySplit(unittest.TestCase):

    def test_perfect_separation(self):
        # 2 forms, 4 UCI: forms separate the two pairs perfectly
        # columns 0,1 contain form0 only; columns 2,3 contain form1 only
        from scipy import sparse
        matrix = sparse.csr_matrix(np.array([[2, 3, 0, 0], [0, 0, 4, 1]], dtype=np.int64))
        labels, chi2 = best_binary_split(matrix)
        self.assertIsNotNone(labels)
        # the split must separate {0,1} from {2,3} (up to label swap)
        self.assertEqual(set(labels[:2]), {labels[0]})
        self.assertEqual(labels[0], labels[1])
        self.assertEqual(labels[2], labels[3])
        self.assertNotEqual(labels[0], labels[2])
        self.assertGreater(chi2, 0)

    def test_too_few_columns(self):
        from scipy import sparse
        labels, chi2 = best_binary_split(sparse.csr_matrix(np.array([[1], [2]], dtype=np.int64)))
        self.assertIsNone(labels)
        self.assertEqual(chi2, 0.0)


def make_two_vocabulary_segments():
    segments = []
    for _ in range(5):
        segments.append({"text": "chat chien os patte", "variables": {"code": "animal"}})
        segments.append({"text": "voiture route moteur roue", "variables": {"code": "vehicule"}})
    return segments


class TestReinertClassification(unittest.TestCase):

    def setUp(self):
        self.segments = make_two_vocabulary_segments()
        self.result = reinert_from_segments(self.segments, size=5, min_freq=3,
                                            max_classes=2, min_class_size=1)

    def test_two_pure_classes(self):
        self.assertEqual(self.result["n_classes"], 2)
        class_of_uci = self.result["class_of_uci"]
        # UCI order follows segment order: even indices animal, odd vehicule (size=5 -> 1 UCI each)
        animal_classes = {class_of_uci[i] for i in range(len(class_of_uci)) if i % 2 == 0}
        vehicule_classes = {class_of_uci[i] for i in range(len(class_of_uci)) if i % 2 == 1}
        self.assertEqual(len(animal_classes), 1)
        self.assertEqual(len(vehicule_classes), 1)
        self.assertNotEqual(animal_classes, vehicule_classes)

    def test_chi2_positive_and_ratio(self):
        self.assertGreater(self.result["chi2"], 0)
        self.assertEqual(self.result["df"], (2 - 1) * (8 - 1))
        self.assertAlmostEqual(self.result["chi2_ratio"], self.result["chi2"] / self.result["df"])

    def test_class_profiles(self):
        for cls in self.result["classes"]:
            self.assertGreater(cls["size"], 0)
            self.assertTrue(cls["profile"])
            forms = {p["forme"] for p in cls["profile"]}
            # a class about animals has animal words, a class about vehicles has vehicle words
            self.assertTrue(forms <= {"chat", "chien", "os", "patte", "voiture", "route", "moteur", "roue"})
            for p in cls["profile"]:
                self.assertIn(p["valeur"], (p["chi2"], -p["chi2"]))
        animal_cls = [c for c in self.result["classes"]
                      if any(p["forme"] == "chat" and p["valeur"] > 0 for p in c["profile"])]
        self.assertEqual(len(animal_cls), 1)
        by_form = {p["forme"]: p["valeur"] for p in animal_cls[0]["profile"]}
        for animal_word in ("chat", "chien", "os", "patte"):
            self.assertGreater(by_form[animal_word], 0)

    def test_representative_ucis(self):
        for cls in self.result["classes"]:
            self.assertTrue(cls["representative_ucis"])
            self.assertLessEqual(len(cls["representative_ucis"]), 5)
            for rep in cls["representative_ucis"]:
                self.assertIn(rep["uci_index"], cls["uci_indices"])
                self.assertTrue(rep["text"])

    def test_ca_forms_x_classes(self):
        ca = self.result["ca"]
        self.assertEqual(ca["col_labels"], [f"class {c['id']}" for c in self.result["classes"]])
        self.assertGreater(ca["inertia"], 0)

    def test_deterministic(self):
        again = reinert_from_segments(self.segments, size=5, min_freq=3, max_classes=2, min_class_size=1)
        self.assertEqual(again["n_classes"], self.result["n_classes"])
        self.assertEqual(again["class_of_uci"], self.result["class_of_uci"])
        self.assertAlmostEqual(again["chi2"], self.result["chi2"])

    def test_class_chi2_is_computed(self):
        # per-class chi2 (class vs rest) must be positive, not the zero leaf default
        for cls in self.result["classes"]:
            self.assertGreater(cls["chi2"], 0)
            self.assertGreaterEqual(cls["split_chi2"], 0)

    def test_min_class_size_enforced_on_split(self):
        # 7 animal + 1 vehicle segment: a split would give classes of sizes 7 and 1,
        # below min_class_size=3 -> no split accepted
        segments = [{"text": "chat chien os patte", "variables": {"code": "a"}} for _ in range(7)]
        segments.append({"text": "voiture route moteur roue", "variables": {"code": "v"}})
        result = reinert_from_segments(segments, size=5, min_freq=3, max_classes=10, min_class_size=3)
        self.assertEqual(result["n_classes"], 1)
        for cls in result["classes"]:
            self.assertGreaterEqual(cls["size"], 3)

    def test_identical_segments_single_class(self):
        # identical UCI: chi2 of any split is 0 -> no separation, one class
        segments = [{"text": "chat chien os patte", "variables": {"code": "a"}} for _ in range(10)]
        result = reinert_from_segments(segments, size=5, min_freq=1, max_classes=10, min_class_size=1)
        self.assertEqual(result["n_classes"], 1)
        self.assertEqual(result["chi2"], 0.0)

    def test_max_classes_respected(self):
        result = reinert_from_segments(self.segments, size=5, min_freq=3,
                                       max_classes=3, min_class_size=1)
        self.assertLessEqual(result["n_classes"], 3)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            reinert_from_segments([], size=5)

    def test_zero_count_uci_columns(self):
        # regression: UCI whose forms are all supplementary (zero column in the
        # active matrix) made best_binary_split index out of bounds, because the
        # CA initialisation drops zero-mass columns
        from scipy import sparse
        # 2 active forms in columns 0-1; column 2 is all-zero in the active matrix
        matrix = sparse.csr_matrix(np.array([[3, 2, 0], [0, 4, 0]], dtype=np.int64))
        labels, chi2 = best_binary_split(matrix)
        self.assertIsNotNone(labels)
        self.assertEqual(len(labels), 3)  # no IndexError despite the zero column
        self.assertIn(labels[2], (0, 1))
        self.assertGreater(chi2, 0)
        self.assertTrue(0 < labels.sum() < 3)

    def test_draw_dendrogram(self):
        fig = draw_dendrogram(self.result)
        self.assertEqual(len(fig.axes), 1)
        ax = fig.axes[0]
        k = self.result["n_classes"]
        # binary tree with k leaves: k-1 internal nodes, 2 segments per edge
        self.assertEqual(len(ax.lines), 4 * (k - 1))
        texts = [t.get_text() for t in ax.texts]
        self.assertTrue(any(t.startswith("class 1") for t in texts))
        self.assertTrue(any(t.startswith("class 2") for t in texts))
        self.assertIn("chi2", ax.get_ylabel())
        # each class is labelled horizontally, in a block, with its most
        # representative forms (one per line under the class label)
        self.assertTrue(any("chat" in t for t in texts))
        self.assertTrue(any("voiture" in t for t in texts))
        class_texts = [t for t in ax.texts if t.get_text().startswith("class")]
        self.assertTrue(all(t.get_rotation() == 0 for t in class_texts))
        self.assertTrue(any("\nchat" in t.get_text() for t in class_texts))
        # leaf branches are colored per class (not gray), labels too
        leaf_colors = {ln.get_color() for ln in ax.lines if ln.get_color() != "#555555"}
        self.assertGreaterEqual(len(leaf_colors), 2)
        text_colors = {t.get_color() for t in ax.texts if t.get_text().startswith("class")}
        self.assertGreaterEqual(len(text_colors), 2)


if __name__ == "__main__":
    unittest.main()
