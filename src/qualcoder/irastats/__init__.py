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

"""
irastats: text statistics in the style of the IRaMuTeQ software.

This package is pure Python (no Qt imports) so that every computation engine
can be unit-tested without a GUI:

- corpus: build the analysable corpus (segments with variables) from a
  QualCoder project database, and export it to the IRaMuTeQ text format.
- text: tokenisation, normalisation, stopwords and light stemming.
- lexicon: sparse lexical table (forms x segments), active/supplementary forms.
- descstats: descending (lexicometric) statistics.
- specificites: chi-square specificities per partition variable.
- ca: correspondence analysis (CA) via SVD.
- similarity: similarity graph of co-occurring forms.
- reinert: Reinert descending hierarchical classification (CHD).
- report_html: HTML rendering helpers for the reports.
- report_odt: ODT (word processor document) rendering helpers for the reports.
"""

from .corpus import (
    build_segments,
    build_coded_segments,
    build_document_segments,
    variable_values,
    available_variables,
    iramuteq_token,
    segment_to_iramuteq,
    format_iramuteq,
    export_iramuteq,
    parse_iramuteq,
    iramuteq_to_rows,
)
from .text import tokenize, load_stopwords, light_stem, normalize_tokens, segment_tokens
from .lexicon import LexicalTable, build_lexical_table
from .descstats import descendant_statistics, frequency_rows, hapax_rows, variable_rows
from .specificites import chi2_statistic, modalities_of, specificities, specificity_rows
from .similarity import (
    cooccurrence,
    similarity_matrix,
    build_graph,
    detect_communities,
    halo_neighbors,
    draw_similarity_graph,
)
from .ca import correspondence_analysis, lexical_table_by_variable, plot_ca, ca_coordinate_rows
from .reinert import (
    split_sentences,
    split_uci,
    build_uci_segments,
    chi2_contingency,
    best_binary_split,
    reinert_classification,
    reinert_from_segments,
    draw_dendrogram,
)

__all__ = [
    "build_segments",
    "build_coded_segments",
    "build_document_segments",
    "variable_values",
    "available_variables",
    "iramuteq_token",
    "segment_to_iramuteq",
    "format_iramuteq",
    "export_iramuteq",
    "parse_iramuteq",
    "iramuteq_to_rows",
    "tokenize",
    "load_stopwords",
    "light_stem",
    "normalize_tokens",
    "segment_tokens",
    "LexicalTable",
    "build_lexical_table",
    "descendant_statistics",
    "frequency_rows",
    "hapax_rows",
    "variable_rows",
    "chi2_statistic",
    "modalities_of",
    "specificities",
    "specificity_rows",
    "cooccurrence",
    "similarity_matrix",
    "build_graph",
    "detect_communities",
    "halo_neighbors",
    "draw_similarity_graph",
    "correspondence_analysis",
    "lexical_table_by_variable",
    "plot_ca",
    "ca_coordinate_rows",
    "split_sentences",
    "split_uci",
    "build_uci_segments",
    "chi2_contingency",
    "best_binary_split",
    "reinert_classification",
    "reinert_from_segments",
    "draw_dendrogram",
]
