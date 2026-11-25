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

"""Correspondence analysis (AFC) of a lexical table, by SVD of the standardized
residuals (numpy only, no prince). Typical use: forms x modalities of a
partition variable, or forms x segments.
"""

import logging

import numpy as np
from matplotlib.figure import Figure
from scipy import sparse

from .lexicon import LexicalTable

logger = logging.getLogger(__name__)


def lexical_table_by_variable(table: LexicalTable, variable: str, active_only: bool = True):
    """Aggregate the lexical table into a forms x modalities contingency matrix.

    Args:
        table: a LexicalTable
        variable: partition variable key ("code", "case", "document", ...)
        active_only: keep only the active forms as rows
    Returns:
        (row_labels, col_labels, matrix) with matrix a sparse csr of counts.
    """

    matrix = table.active_matrix if active_only else table.matrix
    row_labels = list(table.active_forms) if active_only else list(table.forms)
    values = [str(v.get(variable, "")) for v in table.segment_variables]
    col_labels = sorted(set(values))
    col_index = {label: j for j, label in enumerate(col_labels)}
    dense = matrix.toarray()
    agg = np.zeros((dense.shape[0], len(col_labels)), dtype=np.int64)
    for col, value in enumerate(values):
        agg[:, col_index[value]] += dense[:, col]
    return row_labels, col_labels, sparse.csr_matrix(agg)


def correspondence_analysis(matrix, row_labels: list = None, col_labels: list = None) -> dict:
    """Correspondence analysis of a contingency matrix of counts, by SVD.

    Args:
        matrix: 2D array-like of counts (scipy sparse or numpy)
        row_labels, col_labels: optional labels
    Returns:
        dict with: eigenvalues, inertia, percent (percent of inertia per axis),
        cumulative, row_coords / col_coords (principal coordinates),
        row_masses / col_masses, row_freq / col_freq, row_contrib / col_contrib
        (contribution to each axis), row_cos2 / col_cos2 (squared cosines),
        row_labels, col_labels. Rows/columns with zero total are dropped.
    """

    M = matrix.toarray() if sparse.issparse(matrix) else np.asarray(matrix, dtype=float)
    M = np.asarray(M, dtype=float)
    row_keep = M.sum(axis=1) > 0
    col_keep = M.sum(axis=0) > 0
    M = M[np.ix_(row_keep, col_keep)]
    if row_labels is not None:
        row_labels = [label for label, keep in zip(row_labels, row_keep) if keep]
    if col_labels is not None:
        col_labels = [label for label, keep in zip(col_labels, col_keep) if keep]
    if M.size == 0 or M.sum() == 0:
        raise ValueError("Empty contingency matrix")

    total = M.sum()
    P = M / total
    r = P.sum(axis=1)
    c = P.sum(axis=0)
    S = (P - np.outer(r, c)) / np.sqrt(np.outer(r, c))
    U, s, Vt = np.linalg.svd(S, full_matrices=False)
    eigenvalues = s ** 2
    inertia = float(eigenvalues.sum())
    F = U * s / np.sqrt(r)[:, None]          # row principal coordinates
    G = Vt.T * s / np.sqrt(c)[:, None]        # column principal coordinates
    n_axes = len(eigenvalues)
    row_contrib = np.zeros_like(F)
    col_contrib = np.zeros_like(G)
    for k in range(n_axes):
        if eigenvalues[k] > 0:
            row_contrib[:, k] = r * F[:, k] ** 2 / eigenvalues[k]
            col_contrib[:, k] = c * G[:, k] ** 2 / eigenvalues[k]
    row_dist2 = (F ** 2).sum(axis=1)
    col_dist2 = (G ** 2).sum(axis=1)
    row_cos2 = np.divide(F ** 2, row_dist2[:, None], out=np.zeros_like(F), where=row_dist2[:, None] > 0)
    col_cos2 = np.divide(G ** 2, col_dist2[:, None], out=np.zeros_like(G), where=col_dist2[:, None] > 0)
    percent = eigenvalues / inertia * 100 if inertia > 0 else np.zeros(n_axes)
    return {
        "eigenvalues": eigenvalues,
        "inertia": inertia,
        "percent": percent,
        "cumulative": np.cumsum(percent),
        "row_coords": F,
        "col_coords": G,
        "row_masses": r,
        "col_masses": c,
        "row_freq": M.sum(axis=1),
        "col_freq": M.sum(axis=0),
        "row_contrib": row_contrib,
        "col_contrib": col_contrib,
        "row_cos2": row_cos2,
        "col_cos2": col_cos2,
        "row_labels": row_labels if row_labels is not None else [str(i) for i in range(M.shape[0])],
        "col_labels": col_labels if col_labels is not None else [str(j) for j in range(M.shape[1])],
    }


def plot_ca(result: dict, axes=(0, 1), top_forms: int = 40, figsize=(10, 8)) -> Figure:
    """Factor map of a correspondence analysis: row points (forms, blue) sized by
    frequency and column points (modalities, red); the forms with the highest
    contribution to the two displayed axes are annotated. """

    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    # clamp the requested axes to the available ones (a 1-column or 1-class
    # table has a single axis)
    n_axes = result["row_coords"].shape[1]
    i = min(axes[0], n_axes - 1)
    j = min(axes[1], n_axes - 1)
    F = result["row_coords"]
    G = result["col_coords"]
    row_freq = result["row_freq"]
    sizes = 20 + 8 * row_freq / max(row_freq.max(), 1) * 10
    ax.scatter(F[:, i], F[:, j], s=sizes, c="#22a7f0", edgecolors="#115f9a", linewidths=0.8,
               label="forms", zorder=3)
    ax.scatter(G[:, i], G[:, j], s=120, c="#e14b31", marker="s", label="modalities", zorder=3)
    contrib = result["row_contrib"][:, i] + result["row_contrib"][:, j]
    order = np.argsort(-contrib)[:top_forms]
    for k in order:
        ax.annotate(str(result["row_labels"][k])[:30], (F[k, i], F[k, j]), fontsize=7, zorder=4)
    for k in range(G.shape[0]):
        ax.annotate(str(result["col_labels"][k])[:30], (G[k, i], G[k, j]), fontsize=9, color="#e14b31", zorder=4)
    ax.axhline(0, color="#cccccc", linewidth=0.8)
    ax.axvline(0, color="#cccccc", linewidth=0.8)
    ax.set_xlabel(f"axis {i + 1} ({result['percent'][i]:.1f}%)")
    ax.set_ylabel(f"axis {j + 1} ({result['percent'][j]:.1f}%)")
    ax.set_title("Correspondence analysis")
    ax.legend(loc="best")
    fig.tight_layout()
    return fig


def ca_coordinate_rows(result: dict, n_axes: int = None) -> list:
    """CSV rows of the form coordinates: [form, freq, coord per axis, contrib per
    axis, cos2 per axis] for the first n_axes axes (default: all). """

    n_axes = n_axes or len(result["eigenvalues"])
    n_axes = min(n_axes, len(result["eigenvalues"]))
    rows = []
    for k, label in enumerate(result["row_labels"]):
        row = [label, int(result["row_freq"][k])]
        row += [round(float(result["row_coords"][k, a]), 6) for a in range(n_axes)]
        row += [round(float(result["row_contrib"][k, a]), 6) for a in range(n_axes)]
        row += [round(float(result["row_cos2"][k, a]), 6) for a in range(n_axes)]
        rows.append(row)
    return rows
