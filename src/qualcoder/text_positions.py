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

Author: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
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


def _python_origin(owner):
    """Owners whose records were always written with code point positions (MCP tools)."""
    owner = owner or ""
    return owner in ("AI Agent", "External MCP") or owner.startswith("MCP: ")


def _edge(text, pos):
    """True if pos does not split a word."""
    if pos <= 0 or pos >= len(text):
        return True
    return not (text[pos - 1].isalnum() and text[pos].isalnum())


def locate_span(text, pos0, pos1, owner="", coding_map=None):
    """New (pos0, pos1, status) for an annotation or case link, which have no stored text.
    status: unchanged, converted (was Qt units) or ambiguous (kept, needs a check)."""
    astral = _astral_indexes(text) if text else ()
    if not astral or pos1 <= astral[0] or _python_origin(owner):
        return pos0, pos1, "unchanged"
    if coding_map and (pos0, pos1) in coding_map:
        new0, new1 = coding_map[(pos0, pos1)]
        return new0, new1, "unchanged" if (new0, new1) == (pos0, pos1) else "converted"
    qt0, qt1 = to_py(text, pos0), to_py(text, pos1)
    if (qt0, qt1) == (pos0, pos1):
        return pos0, pos1, "unchanged"
    if pos1 > len(text):
        return qt0, qt1, "converted"
    py_score = _edge(text, pos0) + _edge(text, pos1)
    qt_score = _edge(text, qt0) + _edge(text, qt1)
    if qt_score > py_score:
        return qt0, qt1, "converted"
    if py_score > qt_score:
        return pos0, pos1, "unchanged"
    return pos0, pos1, "ambiguous"


def _merge_memos(memos):
    """Distinct non-empty memos, in order."""
    seen = []
    for memo in memos:
        if memo and memo not in seen:
            seen.append(memo)
    return "\n\n".join(seen)


def _table_exists(cur, name):
    cur.execute("select 1 from sqlite_master where type='table' and name=?", [name])
    return cur.fetchone() is not None


def _migrate_codings(cur, fid, text, counts, review):
    """Fix codings of one file, merging codings that end up identical. Returns old to new range map."""
    cur.execute("select ctid, cid, owner, pos0, pos1, seltext, memo, important, avid from code_text where fid=?",
                [fid])
    rows = []
    for ctid, cid, owner, pos0, pos1, seltext, memo, important, avid in cur.fetchall():
        new0, new1, status = locate_coding(text, pos0, pos1, seltext)
        counts[status] += 1
        if status == "unresolved":
            review['codings'].append(ctid)
        rows.append({'ctid': ctid, 'cid': cid, 'owner': owner, 'old': (pos0, pos1), 'new': (new0, new1),
                     'memo': memo, 'important': important, 'avid': avid})
    ranges = {}
    for row in rows:
        ranges.setdefault(row['old'], set()).add(row['new'])
    coding_map = {old: next(iter(new)) for old, new in ranges.items() if len(new) == 1}
    groups = {}
    for row in rows:
        groups.setdefault((row['cid'], row['owner'], row['new']), []).append(row)
    graph = _table_exists(cur, "gr_free_text_item")
    graph_memo = _table_exists(cur, "gr_memo_item")
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r['old'] != r['new'], r['ctid']))
        keeper, others = group[0], group[1:]
        memo = _merge_memos([r['memo'] for r in group])
        important = 1 if any(r['important'] == 1 for r in group) else keeper['important']
        avid = keeper['avid'] if keeper['avid'] is not None else next(
            (r['avid'] for r in others if r['avid'] is not None), None)
        cur.execute("update code_text set memo=?, important=?, avid=? where ctid=?",
                    [memo, important, avid, keeper['ctid']])
        for other in others:
            if graph:
                cur.execute("update gr_free_text_item set ctid=? where ctid=?", [keeper['ctid'], other['ctid']])
                cur.execute("update gr_free_text_item set memo_ctid=? where memo_ctid=?",
                            [keeper['ctid'], other['ctid']])
            if graph_memo:
                cur.execute("update gr_memo_item set memo_source_id=? where memo_source_type='code_text' "
                            "and memo_source_id=?", [keeper['ctid'], other['ctid']])
            cur.execute("delete from code_text where ctid=?", [other['ctid']])
            rows.remove(other)
            counts['merged'] += 1
    movers = [r for r in rows if r['old'] != r['new']]
    # Two steps so a move never collides with a row that is moving away
    for row in movers:
        cur.execute("update code_text set pos0=?, pos1=? where ctid=?", [-row['ctid'], -row['ctid'], row['ctid']])
    for row in movers:
        cur.execute("update code_text set pos0=?, pos1=? where ctid=?", [row['new'][0], row['new'][1], row['ctid']])
    return coding_map


def _migrate_annotations(cur, fid, text, coding_map, counts, review):
    """Fix annotations of one file, merging annotations that end up identical."""
    cur.execute("select anid, owner, pos0, pos1, memo from annotation where fid=?", [fid])
    rows = []
    for anid, owner, pos0, pos1, memo in cur.fetchall():
        new0, new1, status = locate_span(text, pos0, pos1, owner, coding_map)
        if status == "converted":
            counts['annotations'] += 1
        if status == "ambiguous":
            review['annotations'].append(anid)
        rows.append({'id': anid, 'owner': owner, 'old': (pos0, pos1), 'new': (new0, new1), 'memo': memo})
    groups = {}
    for row in rows:
        groups.setdefault((row['owner'], row['new']), []).append(row)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r['old'] != r['new'], r['id']))
        cur.execute("update annotation set memo=? where anid=?", [_merge_memos([r['memo'] for r in group]),
                                                                    group[0]['id']])
        for other in group[1:]:
            cur.execute("delete from annotation where anid=?", [other['id']])
            rows.remove(other)
            counts['merged'] += 1
    movers = [r for r in rows if r['old'] != r['new']]
    for row in movers:
        cur.execute("update annotation set pos0=?, pos1=? where anid=?", [-row['id'], -row['id'], row['id']])
    for row in movers:
        cur.execute("update annotation set pos0=?, pos1=? where anid=?", [row['new'][0], row['new'][1], row['id']])


def _migrate_case_links(cur, fid, text, coding_map, counts, review):
    """Fix case links of one file, merging links that end up identical."""
    cur.execute("select id, caseid, owner, pos0, pos1, memo from case_text where fid=?", [fid])
    rows = []
    for row_id, caseid, owner, pos0, pos1, memo in cur.fetchall():
        if pos0 == 0 and pos1 in (len(text), qt_length(text)):
            new0, new1, status = 0, len(text), "unchanged"
        else:
            new0, new1, status = locate_span(text, pos0, pos1, owner, coding_map)
        if (new0, new1) != (pos0, pos1):
            counts['case_text'] += 1
        if status == "ambiguous":
            review['case_text'].append(row_id)
        rows.append({'id': row_id, 'caseid': caseid, 'old': (pos0, pos1), 'new': (new0, new1), 'memo': memo})
    groups = {}
    for row in rows:
        groups.setdefault((row['caseid'], row['new']), []).append(row)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r['old'] != r['new'], r['id']))
        cur.execute("update case_text set memo=? where id=?", [_merge_memos([r['memo'] for r in group]),
                                                                 group[0]['id']])
        for other in group[1:]:
            cur.execute("delete from case_text where id=?", [other['id']])
            rows.remove(other)
            counts['merged'] += 1
    for row in rows:
        if row['old'] != row['new']:
            cur.execute("update case_text set pos0=?, pos1=? where id=?", [row['new'][0], row['new'][1], row['id']])


def migrate_positions_to_code_points(conn):
    """Convert text positions saved in Qt units to code points; caller handles the transaction.
    Codings are checked against their seltext. Annotations and case links have no text: MCP records
    are kept, ranges equal to a coding follow it, others are judged by which reading keeps whole words.
    Returns counts and the ids to review (codings not found, annotations and case links left as they were)."""

    counts = {"unchanged": 0, "converted": 0, "relocated": 0, "unresolved": 0, "merged": 0,
              "annotations": 0, "case_text": 0}
    review = {'codings': [], 'annotations': [], 'case_text': []}
    cur = conn.cursor()
    cur.execute("select id, fulltext, mediapath from source where fulltext is not null and fulltext != ''")
    sources = [(fid, text, mediapath) for fid, text, mediapath in cur.fetchall() if has_astral(text)]
    for fid, text, mediapath in sources:
        coding_map = _migrate_codings(cur, fid, text, counts, review)
        # PDF text is coded on page text with code point positions
        if (mediapath or "").lower().endswith(".pdf"):
            continue
        _migrate_annotations(cur, fid, text, coding_map, counts, review)
        _migrate_case_links(cur, fid, text, coding_map, counts, review)
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
    return counts, review


def upgrade_positions_v18(conn):
    """Run the position migration and mark the project as v18 in one transaction; rolls back on error."""

    if conn.in_transaction:
        conn.commit()
    cur = conn.cursor()
    cur.execute("begin")
    try:
        result = migrate_positions_to_code_points(conn)
        cur.execute("alter table project add position_units text")
        cur.execute('update project set databaseversion="v18", position_units="codepoint"')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return result
