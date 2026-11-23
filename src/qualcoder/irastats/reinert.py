# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Authors: Colin Curtain C, Kai Droege, Justin Missaghieh--Poncet, Lorenzo Salomao
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

"""Reinert descending hierarchical classification (CHD), as in IRaMuTeQ.

Method (Reinert 1983, "Une methode de classification descendante des enonces
d'un corpus", and Reinert 1990): the corpus is segmented into intermediate
context units (UCI) of about `size` occurrences, bounded by strong punctuation
when possible; a forms x UCI matrix of the active forms is built; the CHD then
repeatedly splits each class into two sub-classes by finding the binary
partition that maximizes the chi-square between the two classes, initialised
from the first axis of a correspondence analysis of the sub-matrix and
refined by iterative reassignment of the UCI until stabilisation. Splitting
stops when a class has fewer than 2 * min_class_size UCI, or when max_classes
would be exceeded. This is NOT a k-means.

Outputs (IRaMuTeQ-like): class count, sizes, chi-square of the classification
and chi2/df ratio, class profiles (characteristic forms with signed chi-square
specificities), the most representative UCI of each class, and a correspondence
analysis of forms x classes.
"""

import logging
import re

import numpy as np
from scipy import sparse

from .ca import correspondence_analysis
from .lexicon import LexicalTable, build_lexical_table
from .specificites import chi2_statistic
from .text import TOKEN_RE

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;:])\s+|\n+")


def split_sentences(text: str) -> list:
    """Split a text into sentences at strong punctuation and line breaks. """

    return [part for part in SENTENCE_SPLIT_RE.split(text or "") if part.strip()]


def split_uci(text: str, size: int = 40) -> list:
    """Split a text into UCI (intermediate context units) of about `size`
    occurrences, cut at sentence boundaries when possible; a sentence longer
    than `size` is hard-cut every `size` tokens.

    Args:
        text: raw text
        size: target number of occurrences per UCI (IRaMuTeQ default ~40)
    Returns:
        List of UCI texts (normalised: tokens joined by single spaces).
    """

    if size < 1:
        raise ValueError("size must be >= 1")
    ucis = []
    current = []
    for sentence in split_sentences(text):
        tokens = TOKEN_RE.findall(sentence)
        if not tokens:
            continue
        if len(tokens) > size:
            if current:
                ucis.append(current)
                current = []
            for i in range(0, len(tokens), size):
                ucis.append(tokens[i:i + size])
        elif current and len(current) + len(tokens) > size:
            ucis.append(current)
            current = tokens
        else:
            current += tokens
    if current:
        ucis.append(current)
    return [" ".join(tokens) for tokens in ucis]


def build_uci_segments(segments: list, size: int = 40) -> list:
    """Segment every corpus segment into UCI; each UCI inherits the variables of
    its source segment. Returns a list of segment dicts usable with
    build_lexical_table. """

    uci_segments = []
    for segment in segments:
        for uci_text in split_uci(segment["text"], size=size):
            uci_segments.append({"text": uci_text, "variables": dict(segment["variables"])})
    return uci_segments


def chi2_contingency(counts: np.ndarray) -> float:
    """Classic chi-square of a contingency table of counts (marginals included):
    sum((obs - exp)^2 / exp). """

    counts = np.asarray(counts, dtype=float)
    total = counts.sum()
    if total == 0:
        return 0.0
    row = counts.sum(axis=1)
    col = counts.sum(axis=0)
    expected = np.outer(row, col) / total
    mask = expected > 0
    return float(((counts[mask] - expected[mask]) ** 2 / expected[mask]).sum())


def _chi2_two_classes(matrix: sparse.csr_matrix, labels: np.ndarray) -> float:
    """Chi-square between two classes of UCI for a forms x UCI matrix. """

    counts = np.zeros((2, matrix.shape[0]))
    for cls in (0, 1):
        cols = np.where(labels == cls)[0]
        if len(cols):
            counts[cls] = np.asarray(matrix[:, cols].sum(axis=1)).ravel()
    return chi2_contingency(counts)


def best_binary_split(matrix: sparse.csr_matrix, max_iter: int = 100):
    """Binary partition of the columns (UCI) of `matrix` maximizing the
    chi-square between the two classes.

    Deterministic initialisation from the first axis of a correspondence
    analysis of the matrix, then iterative single-UCI reassignment while the
    chi-square increases (Reinert's iterative reaffectation).
    Returns:
        (labels, chi2) with labels a 0/1 array over the columns, or
        (None, 0.0) if fewer than 2 columns.
    """

    n = matrix.shape[1]
    if n < 2:
        return None, 0.0
    labels = np.zeros(n, dtype=int)
    try:
        # CA drops zero-mass columns (UCI whose forms are all supplementary),
        # so realign its first axis on the kept columns before labelling
        kept = np.where(np.asarray(matrix.sum(axis=0)).ravel() > 0)[0]
        if len(kept) >= 2:
            ca = correspondence_analysis(matrix)
            axis = ca["col_coords"][:, 0]
            labels[kept] = (axis >= np.median(axis)).astype(int)
        else:
            labels = np.arange(n) % 2
    except Exception:
        labels = np.arange(n) % 2
    if labels.sum() == 0 or labels.sum() == n:
        labels = np.zeros(n, dtype=int)
        labels[: n // 2] = 1
    current = _chi2_two_classes(matrix, labels)
    for _ in range(max_iter):
        improved = False
        for k in range(n):
            candidate = labels.copy()
            candidate[k] = 1 - candidate[k]
            if candidate.sum() == 0 or candidate.sum() == n:
                continue
            value = _chi2_two_classes(matrix, candidate)
            if value > current + 1e-12:
                labels = candidate
                current = value
                improved = True
        if not improved:
            break
    return labels, current


def reinert_classification(table: LexicalTable, uci_texts: list = None, max_classes: int = 10,
                           min_class_size: int = 3, max_iter: int = 100) -> dict:
    """Reinert CHD on a forms x UCI lexical table.

    Args:
        table: LexicalTable whose columns are UCI (built with
            build_lexical_table(build_uci_segments(segments, size), min_freq=...))
        uci_texts: text of each UCI (defaults to table.segment_texts)
        max_classes: maximum number of classes (IRaMuTeQ default ~10)
        min_class_size: a class is split only if it has at least
            2 * min_class_size UCI
        max_iter: maximum reassignment iterations per split
    Returns:
        dict with n_classes, uci_texts, class_of_uci, chi2, df, chi2_ratio,
        classes (list of dicts: id, uci_indices, size, chi2, profile, representative_ucis),
        tree, ca (correspondence analysis of forms x classes), params.
    """

    matrix = table.active_matrix
    forms = list(table.active_forms)
    if uci_texts is None:
        uci_texts = list(table.segment_texts)
    n = matrix.shape[1]
    if n == 0 or matrix.shape[0] == 0:
        raise ValueError("Empty forms x UCI matrix")

    leaf_count = [0]

    def recurse(indices):
        node = {"indices": list(indices), "children": None, "chi2": 0.0}
        if len(indices) >= 2 * min_class_size and leaf_count[0] + 1 < max_classes:
            sub = matrix[:, indices]
            labels, chi2 = best_binary_split(sub, max_iter=max_iter)
            if labels is not None and chi2 > 0:
                left = [indices[k] for k in range(len(indices)) if labels[k] == 0]
                right = [indices[k] for k in range(len(indices)) if labels[k] == 1]
                # accept the split only if both classes reach min_class_size and
                # the split is a real separation (positive chi-square)
                if min(len(left), len(right)) >= min_class_size:
                    node["chi2"] = chi2
                    leaf_count[0] += 1
                    node["children"] = [recurse(left), recurse(right)]
        return node

    tree = recurse(list(range(n)))

    # collect leaves (classes) in traversal order, keeping the parent split chi2
    leaves = []

    def collect(node, parent_chi2=0.0):
        if node["children"] is None:
            leaves.append((node, parent_chi2))
        else:
            for child in node["children"]:
                collect(child, node["chi2"])

    collect(tree)
    # order classes by decreasing size, then renumber
    leaves.sort(key=lambda item: -len(item[0]["indices"]))
    class_of_uci = [0] * n
    for class_id, (node, _parent_chi2) in enumerate(leaves, start=1):
        for idx in node["indices"]:
            class_of_uci[idx] = class_id
    classes = []
    for class_id, (node, parent_chi2) in enumerate(leaves, start=1):
        # chi2 of the class against the rest of the corpus (2 x n_forms table)
        in_counts = np.asarray(matrix[:, node["indices"]].sum(axis=1)).ravel()
        cls_chi2 = chi2_contingency(np.vstack([in_counts, matrix.sum(axis=1) - in_counts]))
        classes.append({"id": class_id, "uci_indices": list(node["indices"]),
                        "size": len(node["indices"]), "chi2": cls_chi2, "split_chi2": parent_chi2})

    # classification chi-square: k classes x forms table
    counts = np.zeros((len(leaves), matrix.shape[0]))
    for cls, (node, _parent_chi2) in enumerate(leaves):
        counts[cls] = np.asarray(matrix[:, node["indices"]].sum(axis=1)).ravel()
    chi2 = chi2_contingency(counts)
    df = max((len(leaves) - 1) * (matrix.shape[0] - 1), 1)

    # class profiles and representative UCI, via signed chi-square specificities
    # of each form for each class (form x class contingency on presence)
    variables = [{"class": str(class_of_uci[j])} for j in range(n)]
    profile_table = LexicalTable(forms=forms, matrix=matrix, segment_texts=uci_texts,
                                 segment_variables=variables, active_indices=list(range(len(forms))),
                                 supplementary_indices=[])
    for cls in classes:
        cls_id = str(cls["id"])
        profile = []
        for row, form in enumerate(forms):
            counts_row = np.asarray(matrix[row].todense()).ravel()
            total_form = int(counts_row.sum())
            mask = np.array([class_of_uci[j] == cls["id"] for j in range(n)])
            col_totals = np.asarray(matrix.sum(axis=0)).ravel()
            a = int(counts_row[mask].sum())
            b = total_form - a
            c = int(col_totals[mask].sum()) - a
            d = int(col_totals.sum()) - a - b - c
            value = chi2_statistic(a, b, c, d)
            expected_a = (a + b) * (a + c) / col_totals.sum() if col_totals.sum() else 0.0
            signe = 1 if a > expected_a else (-1 if a < expected_a else 0)
            if signe != 0:
                profile.append({"forme": form, "frequence": total_form, "chi2": value,
                                "valeur": signe * value})
        # over-represented forms (valeur > 0) first, then by decreasing chi2
        profile.sort(key=lambda r: (r["valeur"] <= 0, -r["chi2"]))
        cls["profile"] = profile[:50]
        # representative UCI: highest sum of the class's signed specificities of
        # the forms present in the UCI
        scores = []
        form_pos = {form: i for i, form in enumerate(forms)}
        for idx in cls["uci_indices"]:
            uci_counts = np.asarray(matrix[:, idx].todense()).ravel()
            score = sum(p["valeur"] for p in profile if uci_counts[form_pos[p["forme"]]] > 0)
            scores.append((idx, score))
        scores.sort(key=lambda t: -t[1])
        cls["representative_ucis"] = [{"uci_index": idx, "text": uci_texts[idx], "score": score}
                                      for idx, score in scores[:5]]

    # AFC forms x classes
    col_index = {str(i): i - 1 for i in range(1, len(classes) + 1)}
    dense = matrix.toarray()
    agg = np.zeros((dense.shape[0], len(classes)), dtype=np.int64)
    for j, cls_id in enumerate(class_of_uci):
        agg[:, col_index[str(cls_id)]] += dense[:, j]
    ca = correspondence_analysis(sparse.csr_matrix(agg), row_labels=forms,
                                 col_labels=[f"class {c['id']}" for c in classes])

    return {
        "n_classes": len(classes),
        "uci_texts": list(uci_texts),
        "class_of_uci": class_of_uci,
        "chi2": chi2,
        "df": df,
        "chi2_ratio": chi2 / df,
        "classes": classes,
        "tree": tree,
        "ca": ca,
        "params": {"max_classes": max_classes, "min_class_size": min_class_size, "max_iter": max_iter},
    }


CLASS_PALETTE = ["#e14b31", "#22a7f0", "#26CC00", "#ab3da9", "#FFA600", "#009C1A",
                 "#0091ea", "#c2185b", "#5d4037", "#00897b"]


def draw_dendrogram(result: dict, figsize=(10, 7), top_forms: int = 5):
    """Dendrogram of the CHD binary tree (IRaMuTeQ style): leaves are the classes,
    each with its own color and labelled with its id, UCI count and most
    representative forms (top of the class profile); internal nodes are the
    dichotomic splits at height = their chi-square. Returns a matplotlib Figure
    (no backend needed).
    """

    from matplotlib.figure import Figure

    tree = result["tree"]
    class_by_indices = {frozenset(c["uci_indices"]): c for c in result["classes"]}

    def class_of(node):
        return class_by_indices[frozenset(node["indices"])]

    def color_of(node):
        cls = class_of(node)
        return CLASS_PALETTE[(cls["id"] - 1) % len(CLASS_PALETTE)]

    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    positions = {}
    leaves = []
    counter = [0.0]

    def layout(node):
        if node["children"] is None:
            x = counter[0]
            counter[0] += 1.0
            positions[id(node)] = (x, 0.0)
            leaves.append(node)
            return x
        xs = [layout(child) for child in node["children"]]
        x = sum(xs) / len(xs)
        positions[id(node)] = (x, float(node["chi2"]))
        return x

    def draw(node):
        if node["children"] is None:
            return
        x, y = positions[id(node)]
        for child in node["children"]:
            cx, cy = positions[id(child)]
            # leaf branches take the color of their class, internal branches stay gray
            color = color_of(child) if child["children"] is None else "#555555"
            width = 1.8 if child["children"] is None else 1.2
            ax.plot([cx, cx], [cy, y], color=color, linewidth=width)
            ax.plot([cx, x], [y, y], color=color, linewidth=width)
            draw(child)
        ax.annotate(f"{y:.1f}", (x, y), fontsize=7, ha="center", va="bottom")

    layout(tree)
    draw(tree)
    for leaf in leaves:
        cls = class_of(leaf)
        x, _y = positions[id(leaf)]
        # most representative = over-represented forms first (valeur > 0)
        positive = [p for p in cls["profile"] if p["valeur"] > 0]
        shown = positive[:top_forms] if positive else cls["profile"][:top_forms]
        # horizontal block under the class label, as in the IRaMuTeQ dendrogram
        label = f"class {cls['id']} ({cls['size']} initial context units)\n" + "\n".join(str(p["forme"])[:30] for p in shown)
        ax.annotate(label, (x, 0.0), fontsize=8, rotation=0, ha="center", va="top",
                    color=color_of(leaf), annotation_clip=False)
    ax.set_ylabel("chi2")
    ax.set_xticks([])
    # leave room below the axis for the horizontal word blocks
    ymax = max([pos[1] for pos in positions.values()] + [1.0])
    n_lines = top_forms + 1
    ax.set_ylim(-0.09 * n_lines * ymax, ymax * 1.05)
    ax.set_title(_("Reinert classification dendrogram"))
    fig.tight_layout()
    return fig


def reinert_from_segments(segments: list, size: int = 40, min_freq: int = 3, max_classes: int = 10,
                          min_class_size: int = 3, max_iter: int = 100, language: str = "fr",
                          stem: bool = False, stopwords: set = None,
                          custom_stopwords_path: str = None) -> dict:
    """Full Reinert pipeline from corpus segments: UCI segmentation, forms x UCI
    matrix of the active forms (frequency >= min_freq), then the CHD.

    Defaults follow IRaMuTeQ: UCI ~ 40 occurrences, at most ~10 classes, active
    forms with frequency >= 3.
    """

    uci_segments = build_uci_segments(segments, size=size)
    if not uci_segments:
        raise ValueError("No UCI produced from the corpus")
    table = build_lexical_table(uci_segments, language=language, min_freq=min_freq, stem=stem,
                                stopwords=stopwords, custom_stopwords_path=custom_stopwords_path)
    return reinert_classification(table, uci_texts=[s["text"] for s in uci_segments],
                                  max_classes=max_classes, min_class_size=min_class_size,
                                  max_iter=max_iter)
