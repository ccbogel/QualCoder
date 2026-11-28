
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

"""ODT (LibreOffice/OpenOffice text document) rendering helpers for the irastats
reports (no Qt). odfpy is imported lazily inside the functions so that importing
the irastats package does not require it. Strings marked for translation are
wrapped in _() so that rebuild_lang.py extracts them; at runtime _ is installed
in builtins by qualcoder/__init__.py.
"""

import logging

logger = logging.getLogger(__name__)


def _add_table(doc, headers: list, rows: list):
    """Append an ODF table to doc.text: one header row + one row per record. """

    from odf.table import Table, TableRow, TableCell
    from odf.text import P

    table = Table()
    header_row = TableRow()
    for header in headers:
        cell = TableCell()
        cell.addElement(P(text=str(header)))
        header_row.addElement(cell)
    table.addElement(header_row)
    for row in rows:
        table_row = TableRow()
        for value in row:
            cell = TableCell()
            cell.addElement(P(text=str(value)))
            table_row.addElement(cell)
        table.addElement(table_row)
    doc.text.addElement(table)


def descstats_odt(stats: dict, variable: str = None):
    """Build an ODT document of the descending statistics (IRaMuTeQ "rapport
    descendant"): summary measures, frequency table, hapax and the breakdown by
    the partition variable when given. Returns the OpenDocumentText object
    (call .save(filepath) on it). """

    from odf.opendocument import OpenDocumentText
    from odf.text import H, P

    from .descstats import frequency_rows, hapax_rows, variable_rows

    doc = OpenDocumentText()
    doc.text.addElement(H(outlinelevel=1, text=_("Text statistics")))
    doc.text.addElement(H(outlinelevel=2, text=_("Totals")))
    summary = [
        [_("Total occurrences"), stats["total_occurrences"]],
        [_("Distinct forms"), stats["distinct_forms"]],
        [_("Active forms"), stats["active_forms"]],
        [_("Supplementary forms"), stats["supplementary_forms"]],
        [_("Hapax"), len(stats["hapax"])],
    ]
    _add_table(doc, [_("Measure"), _("Value")], summary)
    doc.text.addElement(H(outlinelevel=2, text=_("Frequencies (decreasing)")))
    _add_table(doc, [_("Form"), _("Frequency"), _("%")], frequency_rows(stats))
    if stats["hapax"]:
        doc.text.addElement(H(outlinelevel=2, text=_("Hapax") + f" ({len(stats['hapax'])})"))
        _add_table(doc, [_("Form"), _("Frequency")], hapax_rows(stats))
    if variable and stats["by_variable"]:
        doc.text.addElement(H(outlinelevel=2, text=_("Breakdown by variable") + f": {variable}"))
        _add_table(doc, [_("Modality"), _("Segments"), _("Occurrences"), _("Distinct forms")],
                   variable_rows(stats))
    doc.text.addElement(P(text=""))
    return doc
