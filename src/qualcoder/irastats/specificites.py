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

"""Chi-square specificities, as in IRaMuTeQ.

For each form and each modality of a partition variable (a code, a case, a
document, a case/file attribute), the chi-square of the 2x2 contingency table
(form present / absent  x  inside the modality / outside) is computed with the
classic formula chi2 = sum((obs - exp)^2 / exp) over the cells, taking the
marginal totals into account (no continuity correction). The signed value is
positive when the form is over-represented in the modality, negative when
under-represented. The two-sided p-value uses the chi2 distribution with
1 degree of freedom (scipy.stats.chi2).
"""

import logging

import numpy as np
from scipy.stats import chi2 as chi2_dist

from .lexicon import LexicalTable

logger = logging.getLogger(__name__)


def chi2_statistic(a: int, b: int, c: int, d: int) -> float:
    """Classic chi-square of the 2x2 table [[a, b], [c, d]]:
    chi2 = N * (a*d - b*c)^2 / ((a+b)(c+d)(a+c)(b+d)),
    equivalent to sum((obs - exp)^2 / exp) with the marginal totals.
    Returns 0.0 for degenerate tables.
    """

    n = a + b + c + d
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    if n == 0 or denom == 0:
        return 0.0
    return n * (a * d - b * c) ** 2 / denom


def modalities_of(table: LexicalTable, variable: str) -> list:
    """Sorted modalities (non-empty values) of a partition variable. """

    values = [str(v.get(variable, "")) for v in table.segment_variables]
    return sorted({v for v in values if v != ""})


def format_p(p: float) -> str:
    """Format a p-value by convention: 3 decimal places, "<0.001" when smaller. """

    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def specificities(table: LexicalTable, variable: str, min_freq: int = 1,
                  p_threshold: float = 0.05, forms: list = None, active_only: bool = True) -> list:
    """Chi-square specificities of each form for each modality of a variable.

    Args:
        table: a LexicalTable
        variable: partition variable key ("code", "case", "document", "file:<name>",
            "case:<name>")
        min_freq: minimum total frequency of a form to be tested
        p_threshold: keep only rows with two-sided p-value <= threshold
            (None keeps all rows)
        forms: restrict the tested forms to this list
        active_only: test only the active forms of the table (IRaMuTeQ default)
    Returns:
        List of dicts {forme, modalite, effectif, total_forme, effectif_attendu,
        chi2, signe, valeur, p}, sorted from the most specific (highest chi2) to
        the least specific. "signe" is +1 (over-represented), -1
        (under-represented) or 0; "valeur" is the signed chi2.
    """

    if active_only:
        matrix = table.active_matrix
        form_labels = table.active_forms
    else:
        matrix = table.matrix
        form_labels = table.forms
    values = [str(v.get(variable, "")) for v in table.segment_variables]
    modalities = [m for m in sorted(set(values)) if m != ""]
    col_totals = np.asarray(matrix.sum(axis=0)).ravel()
    grand_total = int(col_totals.sum())

    results = []
    for row, form in enumerate(form_labels):
        counts = np.asarray(matrix[row].todense()).ravel()
        total_form = int(counts.sum())
        if total_form < min_freq:
            continue
        if forms is not None and form not in forms:
            continue
        for modality in modalities:
            mask = np.array([value == modality for value in values], dtype=bool)
            a = int(counts[mask].sum())          # form inside modality
            b = total_form - a                    # form outside modality
            c = int(col_totals[mask].sum()) - a   # other forms inside modality
            d = grand_total - a - b - c           # other forms outside modality
            chi2 = chi2_statistic(a, b, c, d)
            expected_a = (a + b) * (a + c) / grand_total if grand_total else 0.0
            if a > expected_a:
                signe = 1
            elif a < expected_a:
                signe = -1
            else:
                signe = 0
            p_value = float(chi2_dist.sf(chi2, df=1))
            results.append({
                "forme": form,
                "modalite": modality,
                "effectif": a,
                "total_forme": total_form,
                "effectif_attendu": round(expected_a, 4),
                "chi2": chi2,
                "signe": signe,
                "valeur": signe * chi2,
                "p": p_value,
            })
    results.sort(key=lambda r: (-r["chi2"], r["forme"], r["modalite"]))
    if p_threshold is not None:
        results = [r for r in results if r["p"] <= p_threshold]
    return results


def specificity_rows(results: list) -> list:
    """CSV/HTML rows: [form, modality, count, expected count, chi2, signed value, p].
    The p-value is formatted by convention (3 decimals, "<0.001" when smaller). """

    return [[r["forme"], r["modalite"], r["effectif"], r["effectif_attendu"],
             round(r["chi2"], 6), round(r["valeur"], 6), format_p(r["p"])] for r in results]
