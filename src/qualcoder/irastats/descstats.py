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

"""Descending (lexicometric) text statistics, as in the IRaMuTeQ "statistiques
textuelles" report: total counts, frequency table sorted by decreasing frequency,
hapax, and breakdown by a partition variable (code, case, document, attribute).
"""

import logging

import numpy as np

from .lexicon import LexicalTable

logger = logging.getLogger(__name__)


def descendant_statistics(table: LexicalTable, variable: str = None) -> dict:
    """Total of a lexical table.

    Args:
        table: a LexicalTable (irastats.lexicon)
        variable: optional partition variable key ("code", "case", "document",
            "file:<name>", "case:<name>"); when given, the result contains a
            "by_variable" breakdown
    Returns:
        dict with keys:
            total_occurrences, distinct_forms, active_forms, supplementary_forms,
            hapax (list of forms occurring once),
            frequencies ([(form, count)] sorted by decreasing count),
            active_frequencies, by_variable (None or
            {modality: {"segments", "occurrences", "distinct_forms"}})
    """

    frequencies = table.frequencies()
    total_occurrences = int(sum(count for _, count in frequencies))
    active_forms = set(table.active_forms)
    stats = {
        "total_occurrences": total_occurrences,
        "distinct_forms": len(table.forms),
        "active_forms": len(table.active_forms),
        "supplementary_forms": len(table.supplementary_forms),
        "hapax": table.hapax(),
        "frequencies": frequencies,
        "active_frequencies": [(form, count) for form, count in frequencies if form in active_forms],
        "by_variable": None,
    }
    if variable:
        values = variable_values_from_segments(table, variable)
        by_variable = {}
        for modality in sorted(set(values)):
            columns = [i for i, value in enumerate(values) if value == modality]
            if columns:
                sub = table.matrix[:, columns]
                occurrences = int(sub.sum())
                distinct = int((np.asarray(sub.sum(axis=1)).ravel() > 0).sum())
            else:
                occurrences = 0
                distinct = 0
            by_variable[modality] = {"segments": len(columns), "occurrences": occurrences,
                                      "distinct_forms": distinct}
        stats["by_variable"] = by_variable
    return stats


def variable_values_from_segments(table: LexicalTable, variable: str) -> list:
    """Value of a variable for each segment (column) of the table. """

    return [str(variables.get(variable, "")) for variables in table.segment_variables]


def frequency_rows(stats: dict, active_only: bool = False) -> list:
    """CSV rows of the frequency table: [form, frequency, percent]. """

    rows = []
    frequencies = stats["active_frequencies"] if active_only else stats["frequencies"]
    total = stats["total_occurrences"] or 1
    for form, count in frequencies:
        rows.append([form, count, round(100.0 * count / total, 4)])
    return rows


def hapax_rows(stats: dict) -> list:
    """CSV rows of the hapax: [form, 1]. """

    return [[form, 1] for form in stats["hapax"]]


def variable_rows(stats: dict) -> list:
    """CSV rows of the breakdown by variable: [modality, segments, occurrences, distinct_forms]. """

    rows = []
    for modality, values in (stats["by_variable"] or {}).items():
        rows.append([modality, values["segments"], values["occurrences"], values["distinct_forms"]])
    return rows
