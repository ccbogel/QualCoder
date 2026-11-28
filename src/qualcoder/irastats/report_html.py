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

"""HTML rendering helpers for the irastats reports (no Qt). Strings marked for
translation are wrapped in _() so that rebuild_lang.py extracts them; at runtime
_ is installed in builtins by qualcoder/__init__.py.
"""

import html
import logging

logger = logging.getLogger(__name__)


def escape(text) -> str:
    """HTML-escape a value. """
    return html.escape(str(text), quote=True)


def html_page(title: str, body: str) -> str:
    """Wrap a body fragment in a minimal HTML page. """

    return ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{escape(title)}</title>"
            "<style>body{font-family:sans-serif;margin:1em;}"
            "table{border-collapse:collapse;margin:1em 0;}"
            "th,td{border:1px solid #999;padding:2px 8px;text-align:right;}"
            "th{background:#ddd;}td:first-child,th:first-child{text-align:left;}"
            ".pos{color:#0a7d00;font-weight:bold;}.neg{color:#b00000;font-weight:bold;}"
            "h1{font-size:1.4em;}h2{font-size:1.15em;}</style>"
            "</head><body>\n" + body + "\n</body></html>\n")


def table_html(headers: list, rows: list, row_classes: list = None) -> str:
    """Render a list of rows as an HTML table.

    Args:
        headers: column headers
        rows: list of row values (lists/tuples)
        row_classes: optional list of CSS classes, one per row
    """

    out = ["<table><thead><tr>"]
    out.extend(f"<th>{escape(h)}</th>" for h in headers)
    out.append("</tr></thead><tbody>")
    for i, row in enumerate(rows):
        cls = f' class="{escape(row_classes[i])}"' if row_classes and i < len(row_classes) else ""
        out.append(f"<tr{cls}>")
        out.extend(f"<td>{escape(cell)}</td>" for cell in row)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def descstats_body(stats: dict, variable: str = None) -> str:
    """Body fragment of the Totals report (IRaMuTeQ "rapport descendant"). """

    from .descstats import frequency_rows, hapax_rows, variable_rows

    parts = [f"<h1>{escape(_('Text statistics'))}</h1>", f"<h2>{escape(_('Totals'))}</h2>"]
    summary = [
        [_("Total occurrences"), stats["total_occurrences"]],
        [_("Distinct forms"), stats["distinct_forms"]],
        [_("Active forms"), stats["active_forms"]],
        [_("Supplementary forms"), stats["supplementary_forms"]],
        [_("Hapax"), len(stats["hapax"])],
    ]
    parts.append(table_html([_("Measure"), _("Value")], summary))
    parts.append("<p><i>" + escape(_("Definitions")) + ": "
                 + escape(_("Segments = the analysed text units (coded texts of the selected codes, or whole documents); "
                            "Occurrences = total number of words; Forms = distinct word forms after normalisation; "
                            "Active forms = forms occurring at least the minimum frequency (rarer forms are supplementary); "
                            "Hapax = forms occurring only once.")) + "</i></p>")
    parts.append(f"<h2>{escape(_('Frequencies (decreasing)'))}</h2>")
    parts.append(table_html([_("Form"), _("Frequency"), _("%")],
                            frequency_rows(stats)))
    if stats["hapax"]:
        parts.append(f"<h2>{escape(_('Hapax'))} ({len(stats['hapax'])})</h2>")
        parts.append(table_html([_("Form"), _("Frequency")], hapax_rows(stats)))
    if variable and stats["by_variable"]:
        parts.append(f"<h2>{escape(_('Breakdown by variable'))}: {escape(variable)}</h2>")
        parts.append(table_html([_("Category"), _("Segments"), _("Occurrences"), _("Distinct forms")],
                                variable_rows(stats)))
    return "\n".join(parts)


def descstats_html(stats: dict, variable: str = None) -> str:
    """HTML report of the descending statistics (IRaMuTeQ "rapport descendant"). """

    return html_page(_("Text statistics"), descstats_body(stats, variable))


def specificites_body(results: list, variable: str = None, p_threshold: float = 0.05) -> str:
    """Body fragment of the chi-square specificities report, highlighting over-represented
    (positive, .pos) and under-represented (negative, .neg) forms. """

    from .specificites import specificity_rows

    parts = [f"<h1>{escape(_('Text statistics'))}</h1>",
             f"<h2>{escape(_('Specificities (chi-square)'))}</h2>"]
    if variable:
        parts.append(f"<p>{escape(_('Partition variable'))}: {escape(variable)} - "
                     f"{escape(_('probability threshold'))}: {p_threshold}</p>")
    rows = specificity_rows(results)
    classes = ["pos" if r["signe"] > 0 else ("neg" if r["signe"] < 0 else "") for r in results]
    parts.append(table_html([_("Form"), _("Category"), _("Count"), _("Expected count"),
                             "chi2", _("Signed value"), "p"], rows, row_classes=classes))
    return "\n".join(parts)


def specificites_html(results: list, variable: str = None, p_threshold: float = 0.05) -> str:
    """HTML report of the chi-square specificities. """

    return html_page(_("Specificities"), specificites_body(results, variable, p_threshold))


def statistics_html(stats: dict, results: list = None, variable: str = None,
                    p_threshold: float = 0.05) -> str:
    """Single-page report with all the statistics: descending statistics plus the
    chi-square specificities (when a partition variable is selected). """

    body = descstats_body(stats, variable)
    if results:
        body += "\n" + specificites_body(results, variable, p_threshold)
    else:
        body += ("\n<p><i>" + escape(_("Select a partition variable to also compute "
                                      "the chi-square specificities.")) + "</i></p>")
    return html_page(_("Text statistics"), body)
