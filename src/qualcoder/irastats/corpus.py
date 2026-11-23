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

"""Build the analysable corpus from a QualCoder project database.

A segment is a dictionary:
    {
        "kind": "coded" or "document",
        "text": the segment text,
        "document": file name (source.name),
        "codes": list of code names applied to the segment,
        "case": case name or "" if the segment is not in a case,
        "fid", "pos0", "pos1": location in the source document,
        "variables": dict of analysis variables, e.g.
            "code": code names joined with " + ",
            "case": case name,
            "document": file name,
            "file:<attribute name>": file attribute value,
            "case:<attribute name>": case attribute value,
    }

All database access goes through the sqlite connection of the App object
(self.app.conn); no hard-coded database path is used.
"""

import logging
import re
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _in_clause(values: Iterable[int]) -> str:
    """SQL placeholders for an IN clause. """
    return ",".join("?" * len(list(values)))


def _attributes_for(conn, attr_type: str, id_: int) -> dict:
    """Attributes of a file or case as {name: value}. attr_type is 'file' or 'case'. """

    cur = conn.cursor()
    cur.execute("select name, value from attribute where attr_type=? and id=?", [attr_type, id_])
    return {row[0]: row[1] for row in cur.fetchall()}


def _case_for_segment(conn, fid: int, pos0: int, pos1: int, case_ids: Optional[list] = None) -> tuple:
    """Case (caseid, name) containing the segment [pos0, pos1] of file fid, or (None, "").
    When case_ids is given, only those cases are considered (a segment can belong to
    several cases; without a filter the first case by caseid wins). """

    cur = conn.cursor()
    sql = ("select case_text.caseid, cases.name from case_text join cases on cases.caseid = case_text.caseid "
           "where case_text.fid=? and ? >= case_text.pos0 and ? <= case_text.pos1 ")
    params = [fid, pos0, pos1]
    if case_ids:
        sql += f" and case_text.caseid in ({_in_clause(case_ids)}) "
        params += list(case_ids)
    sql += " order by case_text.caseid limit 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return None, ""
    return row[0], row[1]


def _make_variables(document: str, case: str, codes: list, file_attributes: dict, case_attributes: dict) -> dict:
    """Variables dict of a segment: code, case, document and attributes. """

    variables = {
        "document": document,
        "case": case,
        "code": " + ".join(sorted(set(codes))),
    }
    for name, value in file_attributes.items():
        variables[f"file:{name}"] = value
    for name, value in case_attributes.items():
        variables[f"case:{name}"] = value
    return variables


def build_coded_segments(conn, file_ids: Optional[list] = None, case_ids: Optional[list] = None,
                         code_ids: Optional[list] = None, owner: Optional[str] = None) -> list:
    """Coded text segments of the project as a list of segment dicts.

    Args:
        conn: sqlite connection of the App object (self.app.conn)
        file_ids: restrict to these source ids (None = all files)
        case_ids: restrict to segments inside these cases (None = all)
        code_ids: restrict to these code ids (None = all codes)
        owner: restrict to this coder name (None = all coders)
    Returns:
        List of segment dicts, ordered by file and position. Segments coded with
        several codes appear once, with all code names in "codes".
    """

    cur = conn.cursor()
    sql = ("select code_text.ctid, code_text.fid, source.name as filename, code_name.name as codename, "
           "code_text.pos0, code_text.pos1, code_text.seltext "
           "from code_text join code_name on code_name.cid = code_text.cid "
           "join source on source.id = code_text.fid where 1=1 ")
    params = []
    if owner:
        sql += " and code_text.owner like ? "
        params.append(owner)
    if file_ids:
        sql += f" and code_text.fid in ({_in_clause(file_ids)}) "
        params += list(file_ids)
    if code_ids:
        sql += f" and code_text.cid in ({_in_clause(code_ids)}) "
        params += list(code_ids)
    if case_ids:
        sql += (f" and exists (select 1 from case_text where case_text.fid = code_text.fid "
                f"and case_text.caseid in ({_in_clause(case_ids)}) "
                f"and code_text.pos0 >= case_text.pos0 and code_text.pos1 <= case_text.pos1) ")
        params += list(case_ids)
    sql += " order by code_text.fid, code_text.pos0, code_text.pos1, lower(code_name.name)"
    cur.execute(sql, params)
    rows = cur.fetchall()

    segments = []
    by_location = {}
    for ctid, fid, filename, codename, pos0, pos1, seltext in rows:
        key = (fid, pos0, pos1)
        if key not in by_location:
            segment = {
                "kind": "coded",
                "ctid": ctid,
                "fid": fid,
                "document": filename,
                "codes": [],
                "case": "",
                "caseid": None,
                "pos0": pos0,
                "pos1": pos1,
                "text": seltext if seltext is not None else "",
                "variables": {},
            }
            by_location[key] = segment
            segments.append(segment)
        by_location[key]["codes"].append(codename)

    for segment in segments:
        caseid, casename = _case_for_segment(conn, segment["fid"], segment["pos0"], segment["pos1"],
                                             case_ids=case_ids)
        segment["caseid"] = caseid
        segment["case"] = casename
        file_attributes = _attributes_for(conn, "file", segment["fid"])
        case_attributes = _attributes_for(conn, "case", caseid) if caseid is not None else {}
        segment["variables"] = _make_variables(segment["document"], casename, segment["codes"],
                                               file_attributes, case_attributes)
    return segments


def build_document_segments(conn, file_ids: Optional[list] = None) -> list:
    """Whole text documents as segments (one segment per document).

    Args:
        conn: sqlite connection of the App object (self.app.conn)
        file_ids: restrict to these source ids (None = all text files)
    Returns:
        List of segment dicts with kind "document" and the full text.
    """

    cur = conn.cursor()
    sql = ("select id, name, fulltext from source "
           "where fulltext is not null and (mediapath is null or mediapath like '/docs/%' or mediapath like 'docs:%') ")
    params = []
    if file_ids:
        sql += f" and id in ({_in_clause(file_ids)}) "
        params += list(file_ids)
    sql += " order by lower(name)"
    cur.execute(sql, params)
    segments = []
    for fid, name, fulltext in cur.fetchall():
        file_attributes = _attributes_for(conn, "file", fid)
        segments.append({
            "kind": "document",
            "ctid": None,
            "fid": fid,
            "document": name,
            "codes": [],
            "case": "",
            "caseid": None,
            "pos0": 0,
            "pos1": len(fulltext) if fulltext else 0,
            "text": fulltext if fulltext else "",
            "variables": _make_variables(name, "", [], file_attributes, {}),
        })
    return segments


def build_segments(conn, file_ids: Optional[list] = None, case_ids: Optional[list] = None,
                   code_ids: Optional[list] = None, owner: Optional[str] = None,
                   include_documents: bool = False) -> list:
    """Constitute the analysable corpus (equivalent of an IRaMuTeQ corpus).

    Args:
        conn: sqlite connection of the App object (self.app.conn)
        file_ids, case_ids, code_ids, owner: selection filters, None = no filter
        include_documents: also include the whole documents as segments
    Returns:
        List of segment dicts (coded segments, plus whole documents if requested).
    """

    segments = build_coded_segments(conn, file_ids=file_ids, case_ids=case_ids, code_ids=code_ids, owner=owner)
    if include_documents:
        segments += build_document_segments(conn, file_ids=file_ids)
    return segments


def variable_values(segments: list, variable: str) -> list:
    """Value of an analysis variable for each segment, in segment order.

    Args:
        segments: list of segment dicts from build_segments
        variable: key of the segment "variables" dict, e.g. "code", "case",
            "document", "file:<name>", "case:<name>"
    Returns:
        List of strings, "" when the variable is not set for a segment.
    """

    return [str(segment["variables"].get(variable, "")) for segment in segments]


def available_variables(segments: list) -> list:
    """Sorted list of the variable keys present in the corpus. """

    keys = set()
    for segment in segments:
        keys.update(segment["variables"].keys())
    return sorted(keys)


def iramuteq_token(text) -> str:
    """ IRaMuTeQ separates starred variables by spaces, so none can contain whitespace. """

    return re.sub(r"\s+", "_", str(text).strip())


IRAMUTEQ_VAR_RE = re.compile(r"[^0-9A-Za-z_\-]+")


def _iramuteq_var_token(text) -> str:
    """ Token for the IRaMuTeQ native variable format (*variable_modality):
    no whitespace and no special characters (official documentation restricts
    the charset of variable names and values). """

    return IRAMUTEQ_VAR_RE.sub("_", iramuteq_token(text))


def segment_to_iramuteq(segment: dict) -> str:
    """One corpus segment in the IRaMuTeQ native text format: a "****" line
    followed by the starred variables (*code_<modality>, *cas_<modality>,
    *doc_<modality>, and one *<attribute>_<modality> per file/case attribute),
    then the segment text.
    """

    parts = [f"*code_{_iramuteq_var_token(code)}" for code in sorted(set(segment.get("codes") or []))]
    if segment.get("case"):
        parts.append(f"*cas_{_iramuteq_var_token(segment['case'])}")
    if segment.get("document"):
        parts.append(f"*doc_{_iramuteq_var_token(segment['document'])}")
    for key, value in sorted(segment.get("variables", {}).items()):
        if key in ("code", "case", "document"):
            continue
        parts.append(f"*{_iramuteq_var_token(key)}_{_iramuteq_var_token(value)}")
    header = "**** " + " ".join(parts) if parts else "****"
    return header + "\n" + segment.get("text", "") + "\n"


def format_iramuteq(segments: list) -> str:
    """Whole corpus as IRaMuTeQ-formatted text (one "****" block per segment). """

    return "\n".join(segment_to_iramuteq(segment) for segment in segments)


def export_iramuteq(segments: list, filepath: str) -> int:
    """Write the corpus to filepath in the IRaMuTeQ text format.

    Returns:
        The number of segments written.
    """

    with open(filepath, "w", encoding="utf-8") as file_:
        file_.write(format_iramuteq(segments))
    return len(segments)


def parse_iramuteq(text: str) -> list:
    """Parse a corpus in the IRaMuTeQ native text format into segment dicts.

    Each text starts with a "****" line followed by starred variables
    (*variable_modality, name and modality separated on the first "_"), then
    the text body up to the next "****" line. The reserved variables *doc_<name>
    and *cas_<name> give the document and case names; every other variable
    becomes an entry of the segment "variables" dict (a repeated variable name
    is joined with " + ", as for the codes of segment_to_iramuteq).

    Returns:
        List of {"text", "document", "case", "variables"} dicts, in file order.
        Empty list when the text has no "****" header line (not an IRaMuTeQ file).
    """

    text = text.lstrip("\ufeff")
    segments = []
    current = None
    for line in text.splitlines():
        if line.startswith("****"):
            if current is not None:
                segments.append(current)
            variables = {}
            document = ""
            case = ""
            for token in line[4:].split():
                if not token.startswith("*"):
                    continue
                name, sep, value = token[1:].partition("_")
                if not sep:
                    value = ""
                if name == "doc":
                    document = value
                elif name == "cas":
                    case = value
                elif name in variables:
                    variables[name] = variables[name] + " + " + value
                else:
                    variables[name] = value
            current = {"text_lines": [], "document": document, "case": case, "variables": variables}
        elif current is not None:
            current["text_lines"].append(line)
    if current is not None:
        segments.append(current)
    for segment in segments:
        segment["text"] = "\n".join(segment.pop("text_lines")).strip()
    return segments


def iramuteq_to_rows(segments: list) -> tuple:
    """Convert parsed IRaMuTeQ segments to (columns, rows) for a table-like import
    (e.g. the survey import of Manage Files): one row per text, a "doc" column with
    the document name (*doc_, else *cas_, else Text_N), a "text" column with the
    segment text, and one column per variable (the IRaMuTeQ variables become
    attributes).
    """

    var_names = set()
    has_case = False
    for segment in segments:
        var_names.update(segment["variables"])
        if segment["case"]:
            has_case = True
    var_names.discard("doc")
    var_names.discard("text")
    columns = ["doc", "text"]
    if has_case:
        columns.append("cas")
    columns += sorted(var_names)
    rows = []
    for i, segment in enumerate(segments):
        row = dict(segment["variables"])
        if segment["case"]:
            row["cas"] = segment["case"]
        row["doc"] = segment["document"] or segment["case"] or f"Text_{i + 1}"
        row["text"] = segment["text"]
        rows.append({col: row.get(col, "") for col in columns})
    return columns, rows
