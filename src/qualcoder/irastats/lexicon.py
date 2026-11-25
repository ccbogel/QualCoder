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

"""Lexical table: sparse matrix of forms x segments.

Forms are split into "active" forms (frequency >= min_freq, or explicitly
listed) and "supplementary" forms (the rest), following the IRaMuTeQ
active/supplementary forms distinction. Supplementary forms are kept in the
table (and re-injected at interpretation time) but excluded from the matrix
used by the factor analyses.
"""

import logging
from collections import Counter
from typing import Optional

import numpy as np
from scipy import sparse

from .text import load_stopwords, segment_tokens

logger = logging.getLogger(__name__)


class LexicalTable:
    """Sparse lexical table: rows are forms, columns are segments.

    Attributes:
        forms: list of all distinct forms, sorted by decreasing frequency
        matrix: scipy.sparse.csr_matrix of shape (len(forms), n_segments)
        segment_texts: text of each segment (columns of the matrix)
        segment_variables: variables dict of each segment
        active_indices: row indices of the active forms
        supplementary_indices: row indices of the supplementary forms
    """

    def __init__(self, forms: list, matrix: sparse.csr_matrix, segment_texts: list,
                 segment_variables: list, active_indices: list, supplementary_indices: list):
        self.forms = forms
        self.matrix = matrix
        self.segment_texts = segment_texts
        self.segment_variables = segment_variables
        self.active_indices = active_indices
        self.supplementary_indices = supplementary_indices

    @property
    def active_forms(self) -> list:
        """Active form labels. """
        return [self.forms[i] for i in self.active_indices]

    @property
    def supplementary_forms(self) -> list:
        """Supplementary form labels. """
        return [self.forms[i] for i in self.supplementary_indices]

    @property
    def active_matrix(self) -> sparse.csr_matrix:
        """Sub-matrix restricted to the active forms. """
        if not self.active_indices:
            return sparse.csr_matrix((0, self.matrix.shape[1]), dtype=self.matrix.dtype)
        return self.matrix[self.active_indices, :]

    def form_frequencies(self) -> dict:
        """Total frequency of each form as {form: count}. """
        counts = np.asarray(self.matrix.sum(axis=1)).ravel()
        return {form: int(count) for form, count in zip(self.forms, counts)}

    def frequencies(self) -> list:
        """(form, frequency) pairs sorted by decreasing frequency, then alphabetically. """
        counts = np.asarray(self.matrix.sum(axis=1)).ravel()
        pairs = sorted(zip(self.forms, (int(c) for c in counts)), key=lambda pair: (-pair[1], pair[0]))
        return pairs

    def hapax(self) -> list:
        """Forms occurring exactly once, sorted alphabetically. """
        counts = np.asarray(self.matrix.sum(axis=1)).ravel()
        return sorted(form for form, count in zip(self.forms, counts) if count == 1)


def build_lexical_table(segments: list, language: str = "fr", min_freq: int = 1,
                        stopwords: Optional[set] = None, stem: bool = False, lowercase: bool = True,
                        active_forms: Optional[list] = None, supplementary_forms: Optional[list] = None,
                        custom_stopwords_path: Optional[str] = None) -> LexicalTable:
    """Build the sparse lexical table (forms x segments) of a corpus.

    Args:
        segments: list of segment dicts from irastats.corpus.build_segments
        language: 2-letter ISO code used for stopwords and stemming
        min_freq: minimum total frequency of an active form
        stopwords: extra stopwords (merged with the built-in list of `language`)
        stem: apply light stemming
        lowercase: lowercase the tokens
        active_forms: forms forced into the active set whatever their frequency
        supplementary_forms: forms forced into the supplementary set
        custom_stopwords_path: path of an editable stopwords file
    Returns:
        A LexicalTable.
    """

    all_stopwords = load_stopwords(language, extra_words=stopwords, custom_path=custom_stopwords_path)
    tokenized = [segment_tokens(segment["text"], language=language, lowercase=lowercase,
                                stopwords=all_stopwords, stem=stem) for segment in segments]

    counts = Counter()
    for tokens in tokenized:
        counts.update(tokens)
    forms = sorted(counts.keys(), key=lambda form: (-counts[form], form))
    form_index = {form: i for i, form in enumerate(forms)}

    active_set = {form for form, count in counts.items() if count >= min_freq}
    if active_forms:
        active_set.update(active_forms)
    if supplementary_forms:
        active_set -= set(supplementary_forms)
    active_set = {form for form in active_set if form in form_index}

    row_indices = []
    col_indices = []
    data = []
    for col, tokens in enumerate(tokenized):
        segment_counts = Counter(tokens)
        for form, count in segment_counts.items():
            row_indices.append(form_index[form])
            col_indices.append(col)
            data.append(count)
    matrix = sparse.coo_matrix(
        (np.array(data, dtype=np.int64), (np.array(row_indices, dtype=np.int64), np.array(col_indices, dtype=np.int64))),
        shape=(len(forms), len(segments)),
    ).tocsr()

    active_indices = [form_index[form] for form in forms if form in active_set]
    supplementary_indices = [form_index[form] for form in forms if form not in active_set]
    return LexicalTable(
        forms=forms,
        matrix=matrix,
        segment_texts=[segment["text"] for segment in segments],
        segment_variables=[segment["variables"] for segment in segments],
        active_indices=active_indices,
        supplementary_indices=supplementary_indices,
    )
