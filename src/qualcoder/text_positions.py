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

Authors: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/

Text positions stored in the database count Unicode code points, as Python and SQLite do.
Qt text documents count UTF-16 units, where characters above U+FFFF (most emoji) take two.
Convert only where a database position meets a Qt cursor.
"""

import bisect
from functools import lru_cache
import re

_ASTRAL = re.compile('[\U00010000-\U0010FFFF]')


@lru_cache(maxsize=8)
def _astral_indexes(text):
    """Code point indexes of characters above U+FFFF."""
    return tuple(match.start() for match in _ASTRAL.finditer(text))


@lru_cache(maxsize=8)
def _astral_qt_indexes(text):
    """Qt positions of characters above U+FFFF."""
    return tuple(index + count for count, index in enumerate(_astral_indexes(text)))


def has_astral(text):
    """True if text holds characters that Qt counts as two units."""
    return bool(text) and bool(_astral_indexes(text))


def to_qt(text, pos):
    """Qt position for a code point index into text."""
    if not text:
        return pos
    astral = _astral_indexes(text)
    if not astral:
        return pos
    return pos + bisect.bisect_left(astral, pos)


def to_py(text, qt_pos):
    """Code point index into text for a Qt position; a position inside a surrogate pair snaps to its start."""
    if not text:
        return qt_pos
    astral_qt = _astral_qt_indexes(text)
    if not astral_qt:
        return qt_pos
    return qt_pos - bisect.bisect_left(astral_qt, qt_pos)


def qt_length(text):
    """Length of text in Qt units."""
    if not text:
        return 0
    return len(text) + len(_astral_indexes(text))


# --- one-off migration of positions saved in Qt units (database v18) ---

def same_text(a, b):
    """Compare texts ignoring the paragraph separator Qt puts in selectedText."""
    return (a or "").replace("\u2029", "\n").replace("\r", "") == (b or "").replace("\u2029", "\n").replace("\r", "")


def _nearest(text, target, pos):
    """Start of the occurrence of target closest to pos, or None."""
    best = None
    start = text.find(target)
    while start != -1:
        if best is None or abs(start - pos) < abs(best - pos):
            best = start
        elif start > pos:
            break
        start = text.find(target, start + 1)
    return best


def locate_coding(text, pos0, pos1, seltext):
    """New (pos0, pos1, status) for a stored text coding, using its seltext to tell the unit apart.
    status: unchanged, converted (was Qt units), relocated (found by its text) or unresolved."""
    astral = _astral_indexes(text) if text else ()
    if not astral or pos1 <= astral[0]:
        return pos0, pos1, "unchanged"
    if same_text(text[pos0:pos1], seltext):
        return pos0, pos1, "unchanged"
    qt0, qt1 = to_py(text, pos0), to_py(text, pos1)
    if same_text(text[qt0:qt1], seltext):
        return qt0, qt1, "converted"
    target = (seltext or "").replace("\u2029", "\n")
    if target:
        start = _nearest(text, target, pos0)
        if start is not None:
            return start, start + len(target), "relocated"
    return pos0, pos1, "unresolved"


def positions_may_change(conn):
    """True if any text source with characters above U+FFFF has codings, annotations or case links."""

    cur = conn.cursor()
    cur.execute("select id, fulltext from source where fulltext is not null and fulltext != ''")
    for fid, text in cur.fetchall():
        if not has_astral(text):
            continue
        for table in ("code_text", "annotation", "case_text"):
            cur.execute(f"select 1 from {table} where fid=? limit 1", [fid])
            if cur.fetchone():
                return True
    return False


def migrate_positions_to_code_points(conn):
    """Convert text positions saved in Qt units to code points; caller commits.
    Codings are checked against their seltext. Annotations and case links have no text, so they
    are taken as Qt units (made by selecting text), except in PDFs and whole file case links.
    Returns counts per status and the ctids left unresolved."""

    counts = {"unchanged": 0, "converted": 0, "relocated": 0, "unresolved": 0, "annotations": 0, "case_text": 0}
    unresolved = []
    cur = conn.cursor()
    cur.execute("select id, fulltext, mediapath from source where fulltext is not null and fulltext != ''")
    sources = [(fid, text, mediapath) for fid, text, mediapath in cur.fetchall() if has_astral(text)]
    for fid, text, mediapath in sources:
        is_pdf = (mediapath or "").lower().endswith(".pdf")
        cur.execute("select ctid, pos0, pos1, seltext from code_text where fid=?", [fid])
        for ctid, pos0, pos1, seltext in cur.fetchall():
            new0, new1, status = locate_coding(text, pos0, pos1, seltext)
            counts[status] += 1
            if status == "unresolved":
                unresolved.append(ctid)
            if (new0, new1) != (pos0, pos1):
                cur.execute("update code_text set pos0=?, pos1=? where ctid=?", [new0, new1, ctid])
        first_astral = _astral_indexes(text)[0]
        if not is_pdf:
            cur.execute("select anid, pos0, pos1 from annotation where fid=? and pos1>?", [fid, first_astral])
            for anid, pos0, pos1 in cur.fetchall():
                cur.execute("update annotation set pos0=?, pos1=? where anid=?",
                            [to_py(text, pos0), to_py(text, pos1), anid])
                counts["annotations"] += 1
        cur.execute("select id, pos0, pos1 from case_text where fid=? and pos1>?", [fid, first_astral])
        for row_id, pos0, pos1 in cur.fetchall():
            if is_pdf or (pos0 == 0 and pos1 >= len(text)):
                continue
            cur.execute("update case_text set pos0=?, pos1=? where id=?", [to_py(text, pos0), to_py(text, pos1), row_id])
            counts["case_text"] += 1
    texts = {fid: (text, mediapath) for fid, text, mediapath in sources}
    cur.execute("select bookmarkfile, bookmarkpos, avbookmarkfile, avbookmarktextpos from project")
    row = cur.fetchone()
    if row is not None:
        bookmarkfile, bookmarkpos, avbookmarkfile, avbookmarktextpos = row
        if bookmarkfile in texts and bookmarkpos and not (texts[bookmarkfile][1] or "").lower().endswith(".pdf"):
            cur.execute("update project set bookmarkpos=?", [to_py(texts[bookmarkfile][0], bookmarkpos)])
        if avbookmarktextpos:
            cur.execute("select av_text_id from source where id=?", [avbookmarkfile])
            av_text = cur.fetchone()
            if av_text and av_text[0] in texts:
                cur.execute("update project set avbookmarktextpos=?",
                            [to_py(texts[av_text[0]][0], avbookmarktextpos)])
    return counts, unresolved
