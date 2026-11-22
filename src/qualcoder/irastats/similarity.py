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

"""Similarity analysis (graphe de similitude), in the style of IRaMuTeQ.

Forms co-occurring within the same segment are linked in an undirected graph.
The association measure is configurable:
- "jaccard" (default): Jaccard index on the segment-presence sets of the two
  forms, cooc / (df_i + df_j - cooc), in [0, 1];
- "chi2": the phi-squared coefficient, i.e. the classic chi2 of the 2x2
  presence/absence table of the pair divided by the number of segments, also
  in [0, 1].

An edge is kept when the similarity is >= the threshold. The graph is built
with networkx and drawn with matplotlib (force-directed layout, node size
proportional to the form frequency, edge width proportional to the similarity).
"""

import logging

import networkx as nx
import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from networkx.algorithms.community import louvain_communities

from .lexicon import LexicalTable

logger = logging.getLogger(__name__)


def cooccurrence(table: LexicalTable, forms: list = None, min_freq: int = 1, active_only: bool = True):
    """Co-occurrence of forms within segments.

    Args:
        table: a LexicalTable
        forms: restrict to these forms (None = active forms when active_only)
        min_freq: minimum total frequency of a form
        active_only: use only the active forms of the table
    Returns:
        (labels, cooc, doc_freq, freq): labels are the form labels, cooc the
        symmetric n x n co-occurrence count matrix (diagonal = number of
        segments containing the form), doc_freq the same diagonal as a vector,
        freq the total frequency of each form.
    """

    if active_only:
        matrix = table.active_matrix
        labels = list(table.active_forms)
    else:
        matrix = table.matrix
        labels = list(table.forms)
    if forms is not None:
        keep = [i for i, label in enumerate(labels) if label in set(forms)]
        matrix = matrix[keep, :]
        labels = [labels[i] for i in keep]
    freq = np.asarray(matrix.sum(axis=1)).ravel()
    keep = [i for i in range(len(labels)) if freq[i] >= min_freq]
    matrix = matrix[keep, :]
    labels = [labels[i] for i in keep]
    freq = freq[keep]
    presence = (matrix.toarray() > 0).astype(np.int64)
    cooc = presence @ presence.T
    doc_freq = np.diag(cooc).copy()
    np.fill_diagonal(cooc, 0)
    return labels, cooc, doc_freq, freq


def similarity_matrix(labels, cooc, doc_freq, n_segments: int, method: str = "jaccard") -> np.ndarray:
    """Pairwise similarity matrix in [0, 1] (diagonal = 0).

    method "jaccard": cooc / (df_i + df_j - cooc).
    method "chi2": phi-squared = chi2 of the 2x2 presence/absence table / n_segments.
    """

    n = len(labels)
    if method == "chi2":
        # phi-squared: chi2 of the 2x2 presence/absence table / n_segments
        a = cooc.astype(float)
        b = doc_freq[:, None] - a
        c = doc_freq[None, :] - a
        d = n_segments - doc_freq[:, None] - doc_freq[None, :] + a
        denom = (a + b) * (c + d) * (a + c) * (b + d)
        with np.errstate(divide="ignore", invalid="ignore"):
            chi2 = np.where(denom > 0, n_segments * (a * d - b * c) ** 2 / denom, 0.0)
        sim = chi2 / n_segments if n_segments else np.zeros((n, n))
        np.fill_diagonal(sim, 0.0)
        return sim
    # default: Jaccard
    denom = doc_freq[:, None] + doc_freq[None, :] - cooc
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(denom > 0, cooc / denom, 0.0)
    np.fill_diagonal(sim, 0.0)
    return sim


def build_graph(labels, sim, freq, threshold: float = 0.2) -> nx.Graph:
    """Undirected similarity graph: one node per form (attribute "freq"), one
    edge per pair with similarity >= threshold (attribute "weight"). """

    graph = nx.Graph()
    for i, label in enumerate(labels):
        graph.add_node(label, freq=int(freq[i]))
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            weight = float(sim[i, j])
            if weight >= threshold and weight > 0:
                graph.add_edge(labels[i], labels[j], weight=weight)
    return graph


def detect_communities(graph: nx.Graph, seed: int = 42) -> list:
    """Louvain communities on the weighted similarity graph (as in IRaMuTeQ).

    Sets the node attribute "community" (int, communities ordered by decreasing
    size). Returns the list of communities (sets of node labels).
    """

    if graph.number_of_nodes() == 0:
        return []
    communities = louvain_communities(graph, weight="weight", seed=seed)
    communities = sorted(communities, key=lambda comm: (-len(comm), sorted(comm)[0]))
    for i, community in enumerate(communities):
        for node in community:
            graph.nodes[node]["community"] = i
    return communities


def halo_neighbors(graph: nx.Graph, node: str, radius: int = 1) -> set:
    """Halo of a form: the node itself plus its neighbors up to `radius` hops
    in the similarity graph (IRaMuTeQ "halo"). """

    if node not in graph:
        return set()
    return set(nx.bfs_tree(graph, node, depth_limit=radius).nodes)


COMMUNITY_PALETTE = ["#22a7f0", "#e14b31", "#26CC00", "#ab3da9", "#F95D6A", "#FFA600",
                     "#009C1A", "#0091ea", "#c2185b", "#5d4037"]


def draw_similarity_graph(graph: nx.Graph, seed: int = 42, top_labels: int = 40,
                          figsize=(10, 8), halo: str = None) -> Figure:
    """Draw the similarity graph on a matplotlib Figure (force-directed layout,
    node size proportional to the form frequency, edge width proportional to the
    similarity, the most frequent forms annotated). Nodes are colored by Louvain
    community when the "community" node attribute is set (see detect_communities);
    `halo` highlights a form and its neighbors (IRaMuTeQ halo) with a dashed circle.
    """

    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    if graph.number_of_nodes() == 0:
        ax.set_title("Similarity graph (empty)")
        return fig
    pos = nx.spring_layout(graph, seed=seed)
    freqs = nx.get_node_attributes(graph, "freq")
    communities = nx.get_node_attributes(graph, "community")
    sizes = [100 + 40 * freqs.get(node, 1) for node in graph.nodes]
    widths = [0.5 + 4 * data["weight"] for _, _, data in graph.edges(data=True)]
    nx.draw_networkx_edges(graph, pos, ax=ax, width=widths, alpha=0.6, edge_color="#888888")
    if communities:
        node_colors = [COMMUNITY_PALETTE[communities.get(node, 0) % len(COMMUNITY_PALETTE)]
                       for node in graph.nodes]
    else:
        node_colors = "#22a7f0"
    edgecolors = ["#115f9a"] * graph.number_of_nodes()
    if halo and halo in graph:
        halo_set = halo_neighbors(graph, halo, radius=1)
        for i, node in enumerate(graph.nodes):
            if node == halo:
                edgecolors[i] = "#b00000"
            elif node in halo_set:
                edgecolors[i] = "#e14b31"
        hx, hy = pos[halo]
        dists = [((pos[n][0] - hx) ** 2 + (pos[n][1] - hy) ** 2) ** 0.5 for n in halo_set if n != halo]
        radius = max(dists) * 1.15 if dists else 0.15
        ax.add_patch(Circle((hx, hy), radius, fill=False, linestyle="--", linewidth=1.8,
                            edgecolor="#b00000", alpha=0.8))
    nx.draw_networkx_nodes(graph, pos, ax=ax, node_size=sizes, node_color=node_colors,
                           edgecolors=edgecolors, linewidths=1.2)
    labels = {node: str(node)[:30] for node in sorted(graph.nodes, key=lambda n: -freqs.get(n, 0))[:top_labels]}
    nx.draw_networkx_labels(graph, pos, labels=labels, ax=ax, font_size=8)
    ax.set_title("Similarity graph")
    ax.axis("off")
    fig.tight_layout()
    return fig
