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
"""

# Shared PDF helpers: word-map text extraction, markup detection, colour matching
# and import coding, so manage_files and manage_references do not need code_pdf.

import datetime
import logging
import os
import sqlite3

import pymupdf
from PyQt6 import QtCore, QtWidgets

from .color_selector import color_matcher, colors, colour_ranges

logger = logging.getLogger(__name__)

# Word tuple indices: (x0, y0, x1, y1, pos0, pos1, line_id)
W_X0, W_Y0, W_X1, W_Y1, W_POS0, W_POS1, W_LINE = 0, 1, 2, 3, 4, 5, 6

# Category and code naming per markup subtype.
MARKUP_KINDS = {
    'highlight': {'category': "PDF Highlights", 'code_prefix': "Highlight"},
    'underline': {'category': "PDF Underlines", 'code_prefix': "Underline"},
}

# Known highlighter colours pinned to (palette hex, family): plain RGB distance
# sends Zotero purple to a blue shade and Acrobat pale yellow to the orange ramp.
KNOWN_MARKUP_COLORS = {
    # Zotero annotation palette
    '#FFD400': ('#DDE600', 'yellow'),
    '#FF6666': ('#FA5858', 'red'),
    '#5FB236': ('#487E4B', 'green'),
    '#2EA8E5': ('#3498DB', 'blue'),
    '#A28AE5': ('#B07CE1', 'purple'),
    '#E56EEE': ('#F781F3', 'pink'),
    '#F19837': ('#FF8B33', 'orange'),
    '#AAAAAA': ('#A8A8A8', 'gray'),
    # Adobe Acrobat default highlight yellow
    '#FCF485': ('#F2F5A9', 'yellow'),
}


def _word_flags():
    """
    Extraction flags: expand ligatures (fi -> f i) so that the text matches.
    """

    try:
        return pymupdf.TEXTFLAGS_WORDS & ~pymupdf.TEXT_PRESERVE_LIGATURES
    except AttributeError:
        return None


def _page_words_raw(page):
    """ Reads the raw word tuples of ONE page once, so both text variants
    (lines and joined paragraphs) can be built from a single extraction.
    Returns:
        (raw word tuples, rotation matrix)
    """

    flags = _word_flags()
    if flags is not None:
        raw = page.get_text("words", flags=flags)
    else:
        raw = page.get_text("words")
    return raw, page.rotation_matrix


def _build_page_text(raw, rot, offset, join_lines=False):
    """
    Deterministic text reconstruction from raw word tuples:
        "" before the first word, "\n\n" between blocks,
        "\n" between lines of the same block (or " " when join_lines is True,
        so each block reads as one whole paragraph),
        " " between words on the same line, and ALWAYS "\n" at the end of the page.
    Word rects are transformed with rotation_matrix so that they match
    the page exactly as it is rendered (get_pixmap applies the rotation).
    line_id keeps incrementing on every visual line change regardless of
    join_lines: highlight rectangles are still drawn per visual line.
    Args:
        raw: word tuples from _page_words_raw
        rot: rotation matrix
        offset: Integer, starting character position of this page in the fulltext
        join_lines: Boolean, True joins the lines of a block into one paragraph
    Returns:
        (page_text: str, words: list[tuple], final_offset: int)
    """

    parts = []
    words = []
    pos = offset
    prev_block = None
    prev_line = None
    line_id = -1
    for x0, y0, x1, y1, wtext, bno, lno, _wno in raw:
        wtext = wtext.replace("\x00", "")
        if wtext == "":
            continue
        if prev_block is None:
            sep = ""
        elif bno != prev_block:
            sep = "\n\n"
        elif lno != prev_line:
            sep = " " if join_lines else "\n"
        else:
            sep = " "
        if sep:
            parts.append(sep)
            pos += len(sep)
        if prev_block != bno or prev_line != lno:
            line_id += 1
        parts.append(wtext)
        rect = pymupdf.Rect(x0, y0, x1, y1) * rot
        rect.normalize()
        words.append((float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1),
                      pos, pos + len(wtext), line_id))
        pos += len(wtext)
        prev_block, prev_line = bno, lno
    parts.append("\n")  # Page limit, always present even if the page is empty
    pos += 1
    return "".join(parts), words, pos


def _extract_page(page, offset, join_lines=False):
    """ Extracts the words from ONE page in natural reading order (PDF content flow
    order, which preserves columns in digital documents). See _build_page_text. """

    raw, rot = _page_words_raw(page)
    return _build_page_text(raw, rot, offset, join_lines)


def extract_pdf_fulltext(filepath, progress_callback=None, join_lines=False):
    """
    Extracts ONLY the fulltext of a PDF, for importing in manage_files.
    It MUST produce exactly the same text that the viewer reconstructs, otherwise
    the coding positions cannot be mapped to the page.
    Args:
        filepath: PDF path
        progress_callback: callable(current_page: int, total: int) or None
        join_lines: Boolean, True joins the lines of each block into one paragraph
    Returns:
        String fulltext
    """

    doc = pymupdf.open(filepath)
    try:
        if doc.needs_pass:
            raise ValueError(_("PDF is password protected"))
        total = len(doc)
        parts = []
        offset = 0
        for i, page in enumerate(doc):
            page_text, _words, offset = _extract_page(page, offset, join_lines)
            parts.append(page_text)
            if progress_callback is not None:
                progress_callback(i + 1, total)
        return "".join(parts)
    finally:
        doc.close()


def extract_pdf_highlights(filepath):
    """
    Detects highlight and underline annotations in a PDF.
    Returns a list of {'page', 'quads' (rects in rotated page coordinates),
    'color', 'kind': 'highlight'|'underline', 'memo'}; empty on unreadable PDFs.
    """

    kinds_by_type = {pymupdf.PDF_ANNOT_HIGHLIGHT: 'highlight',
                     pymupdf.PDF_ANNOT_UNDERLINE: 'underline'}
    out = []
    try:
        doc = pymupdf.open(filepath)
    except Exception as err:
        logger.warning(f"extract_pdf_highlights: {filepath} {err}")
        return out
    try:
        for i, page in enumerate(doc):
            rot = page.rotation_matrix
            annot = page.first_annot
            while annot is not None:
                try:
                    kind = kinds_by_type.get(annot.type[0])
                    if kind is not None:
                        stroke = (annot.colors or {}).get('stroke')
                        if stroke and len(stroke) >= 3:
                            color = "#{:02X}{:02X}{:02X}".format(
                                int(round(stroke[0] * 255)), int(round(stroke[1] * 255)),
                                int(round(stroke[2] * 255)))
                        else:
                            color = "#F7FE2E"  # PDF default highlight yellow
                        quads = []
                        vertices = annot.vertices
                        if vertices:
                            for k in range(0, len(vertices) - 3, 4):
                                pts = vertices[k:k + 4]
                                rect = pymupdf.Rect(min(p[0] for p in pts), min(p[1] for p in pts),
                                                 max(p[0] for p in pts), max(p[1] for p in pts)) * rot
                                rect.normalize()
                                quads.append(rect)
                        else:
                            rect = pymupdf.Rect(annot.rect) * rot
                            rect.normalize()
                            quads.append(rect)
                        if quads:
                            content = (annot.info or {}).get('content', '') or ''
                            out.append({'page': i, 'quads': quads, 'color': color,
                                        'kind': kind, 'memo': content.strip()})
                except Exception as err:
                    logger.debug(f"extract_pdf_highlights annot: {err}")
                annot = annot.next
    except Exception as err:
        # Encrypted or damaged: page iteration fails after open.
        logger.warning(f"extract_pdf_highlights: {filepath} {err}")
    finally:
        doc.close()
    return out


def extract_pdf_annotations(filepath):
    """
    Non-markup annotations with text (sticky notes, etc.) for the file memo.
    Highlight and underline comments go to their coded segment memo instead.
    Returns a list of {'page' (1-based), 'type', 'content'} in document order.
    """

    markup_types = (pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE)
    out = []
    try:
        doc = pymupdf.open(filepath)
    except Exception as err:
        logger.warning(f"extract_pdf_annotations: {filepath} {err}")
        return out
    try:
        for i, page in enumerate(doc):
            annot = page.first_annot
            while annot is not None:
                try:
                    if annot.type[0] not in markup_types:
                        content = ((annot.info or {}).get('content', '') or '').strip()
                        if content:
                            out.append({'page': i + 1,
                                        'type': annot.type[1] if len(annot.type) > 1 else '',
                                        'content': content})
                except Exception as err:
                    logger.debug(f"extract_pdf_annotations annot: {err}")
                annot = annot.next
    except Exception as err:
        # Encrypted or damaged: page iteration fails after open.
        logger.warning(f"extract_pdf_annotations: {filepath} {err}")
    finally:
        doc.close()
    return out


def pdf_highlights_to_positions(filepath, highlights, progress_callback=None):
    """
    Maps markup quads to character positions of the stored fulltext, using the
    SAME word map as the paragraph extractor (join_lines=True), so pos0/pos1 land
    exactly on the imported text.
    Args:
        filepath: PDF path
        highlights: output of extract_pdf_highlights
        progress_callback: callable(step, total) or None; called per page while
            building the word map and per markup while matching.
    Returns:
        List of {'pos0': int, 'pos1': int, 'color': '#RRGGBB', 'kind': str,
        'memo': str}, ordered by pos0.
    """

    if not highlights:
        return []
    try:
        doc = pymupdf.open(filepath)
    except Exception as err:
        logger.warning(f"pdf_highlights_to_positions: {filepath} {err}")
        return []
    page_words = []
    try:
        total_steps = len(doc) + len(highlights)
        step = 0
        offset = 0
        for page in doc:
            raw, rot = _page_words_raw(page)
            _text, words, offset = _build_page_text(raw, rot, offset, join_lines=True)
            page_words.append(words)
            step += 1
            if progress_callback is not None:
                progress_callback(step, total_steps)
    except Exception as err:
        # Encrypted or damaged: page iteration fails after open.
        logger.warning(f"pdf_highlights_to_positions: {filepath} {err}")
        return []
    finally:
        doc.close()
    results = []
    for hl in highlights:
        step += 1
        if progress_callback is not None:
            progress_callback(step, total_steps)
        words = page_words[hl['page']] if hl['page'] < len(page_words) else []
        pos0 = None
        pos1 = None
        for w in words:
            w_rect = pymupdf.Rect(w[0], w[1], w[2], w[3])
            w_area = max(1e-6, w_rect.get_area())
            for quad in hl['quads']:
                inter = pymupdf.Rect(w_rect)
                inter.intersect(quad)
                if inter.is_empty:
                    continue
                # The word counts as marked when at least half of it is covered.
                if inter.get_area() / w_area >= 0.5:
                    pos0 = w[4] if pos0 is None else min(pos0, w[4])
                    pos1 = w[5] if pos1 is None else max(pos1, w[5])
                    break
        if pos0 is not None and pos1 is not None and pos1 > pos0:
            results.append({'pos0': int(pos0), 'pos1': int(pos1), 'color': hl['color'],
                            'kind': hl.get('kind', 'highlight'), 'memo': hl.get('memo', '')})
    results.sort(key=lambda r: r['pos0'])
    return results


def closest_qualcoder_color(hex_color):
    """
    Matches a markup colour to the QualCoder palette: KNOWN_MARKUP_COLORS for
    known highlighters, the gray range for achromatics (plain distance lands them
    on odd hues), color_selector.color_matcher() for the rest.
    Returns (palette hex, family name from colour_ranges).
    """

    try:
        hex_norm = hex_color.strip().upper()
        r = int(hex_norm[1:3], 16)
        g = int(hex_norm[3:5], 16)
        b = int(hex_norm[5:7], 16)
        if len(hex_norm) != 7:
            raise ValueError
    except (AttributeError, ValueError, IndexError):
        hex_norm = "#F7FE2E"  # default highlight yellow
        r, g, b = 247, 254, 46
    known = KNOWN_MARKUP_COLORS.get(hex_norm)
    if known is not None:
        return known
    if max(r, g, b) - min(r, g, b) < 32:
        # Nearest gray shade, same metric as color_matcher.
        gray = next(rng for rng in colour_ranges if rng['name'] == 'gray')
        best_idx = gray['min']
        best_diff = None
        for idx in range(gray['min'], min(gray['max'] + 1, len(colors))):
            c = colors[idx]
            diff = (abs(int(c[1:3], 16) - r) + abs(int(c[3:5], 16) - g)
                    + abs(int(c[5:7], 16) - b)) / 3
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_idx = idx
    else:
        best_idx = colors.index(color_matcher(hex_norm))
    family = "colour"
    for rng in colour_ranges:
        if rng['name'] != 'all' and rng['min'] <= best_idx <= rng['max']:
            family = rng['name']
            break
    return colors[best_idx], family


def pdf_annotations_to_file_memo(app, parent_text_edit, fid, filepath, existing_memo=""):
    """
    Appends the PDF's non-markup text annotations to the file memo.
    Shared by manage_files and the reference attachment import.
    Args:
        fid: source id, Integer
        filepath: PDF path
        existing_memo: current memo of the source row, String
    Returns:
        String, the memo of the source row after the call (unchanged if no annotations)
    """

    try:
        notes = extract_pdf_annotations(filepath)
    except Exception as err:
        logger.warning(f"Annotation detection: {filepath} {err}")
        return existing_memo
    if not notes:
        return existing_memo
    memo_lines = [_("PDF annotations:")]
    for n in notes:
        memo_lines.append(f"[p. {n['page']}] {n['content']}")
    memo_text = "\n".join(memo_lines)
    if existing_memo:
        memo_text = existing_memo + "\n\n" + memo_text
    cur = app.conn.cursor()
    cur.execute("update source set memo=? where id=?", [memo_text, fid])
    app.conn.commit()
    if getattr(app, "project_events", None) is not None:
        app.project_events.emit_table_changes(['source'], source=None)
    if parent_text_edit is not None:
        parent_text_edit.append(_("PDF annotations added to file memo: ") + f"{len(notes)}")
    return memo_text


def pdf_markups_question_text(highlights):
    """
    Once-per-batch question before coding imported markups, naming only the
    categories in use. Shared by both import dialogs.
    Args:
        highlights: output of extract_pdf_highlights
    Returns:
        String
    """

    kinds = {hl.get('kind', 'highlight') for hl in highlights}
    if kinds == {'underline'}:
        msg = _("Underlined segments were detected in the imported PDF(s).") + "\n\n"
        msg += _("Code those segments? A 'PDF Underlines' category will be created, "
                 "with one code per colour (named and coloured after the closest "
                 "QualCoder colour).")
    elif kinds == {'highlight'}:
        msg = _("Highlighted segments were detected in the imported PDF(s).") + "\n\n"
        msg += _("Code those segments? A 'PDF Highlights' category will be created, "
                 "with one code per highlight colour (named and coloured after the "
                 "closest QualCoder colour).")
    else:
        msg = _("Highlighted and underlined segments were detected in the imported PDF(s).") + "\n\n"
        msg += _("Code those segments? 'PDF Highlights' and 'PDF Underlines' categories "
                 "will be created, with one code per colour (named and coloured after "
                 "the closest QualCoder colour).")
    return msg


def _markup_category_id(app, kind, owner, now_):
    """ Catid for the markup kind, creating the category once. """

    labels = MARKUP_KINDS[kind]
    memo_by_kind = {'highlight': _("Codes created from PDF highlight annotations"),
                    'underline': _("Codes created from PDF underline annotations")}
    cur = app.conn.cursor()
    cur.execute("select catid from code_cat where name=?", [labels['category']])
    res = cur.fetchone()
    if res is not None:
        return res[0]
    cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                (labels['category'], memo_by_kind[kind], owner, now_, None))
    app.conn.commit()
    cur.execute("select last_insert_rowid()")
    return cur.fetchone()[0]


def code_pdf_highlights(app, parent_text_edit, fid, filepath, fulltext, highlights,
                        progress_=None, parent_widget=None):
    """
    Codes the marked segments under 'PDF Highlights' / 'PDF Underlines', one code
    per colour and kind named after the closest palette colour ("Highlight yellow",
    "_2" suffix for further shades), inserting code_text rows over the positions.
    Progress reuses the batch dialog when passed; headless-safe without one.
    Args:
        fid: source id, Integer
        filepath: PDF path
        fulltext: the imported fulltext (paragraph layout)
        highlights: output of extract_pdf_highlights
        progress_: the batch QProgressDialog from import_files, or None
        parent_widget: parent for a standalone progress dialog, or None
    """

    filename_ = os.path.basename(filepath)
    external = progress_ is not None
    progress = progress_
    if progress is None and QtWidgets.QApplication.instance() is not None:
        progress = QtWidgets.QProgressDialog("", "", 0, 100, parent_widget)
        progress.setCancelButton(None)  # Partial runs are safe, but avoid them
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)  # Only appears if it takes a while
        progress.setAutoReset(False)
        progress.setAutoClose(False)

    def _show_phase(phase_label, pct):
        if progress is None:
            return
        progress.setLabelText(f"{filename_}\n{phase_label} {pct}%")
        if not external:
            progress.setValue(pct)
        QtWidgets.QApplication.processEvents()

    def _map_progress(step, total):
        if total > 0:
            _show_phase(_("Mapping marked segments"), int(step * 60 / total))

    positions = pdf_highlights_to_positions(filepath, highlights, _map_progress)
    if not positions:
        if progress is not None and not external:
            progress.close()
        elif external and progress is not None:
            progress.setLabelText(filename_)
        return
    now_ = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    owner = app.settings['codername']
    cur = app.conn.cursor()
    # One category per kind, reused across batches.
    catids_by_kind = {}
    for kind in sorted({p['kind'] for p in positions}):
        catids_by_kind[kind] = _markup_category_id(app, kind, owner, now_)
    # One code per colour and kind, family-named; reused when its palette colour
    # already exists under the name pattern.
    cids_by_key = {}
    for kind, hl_color in sorted({(p['kind'], p['color']) for p in positions}):
        qc_hex, family = closest_qualcoder_color(hl_color)
        base_name = f"{MARKUP_KINDS[kind]['code_prefix']} {family}"
        cur.execute("select cid, name, color from code_name where name=? or name like ?",
                    [base_name, base_name + "_%"])
        existing = [row for row in cur.fetchall()
                    if row[1] == base_name or
                    (row[1].startswith(base_name + "_") and row[1][len(base_name) + 1:].isdigit())]
        reuse = next((row for row in existing if row[2] == qc_hex), None)
        if reuse is not None:
            cids_by_key[(kind, hl_color)] = reuse[0]
            continue
        taken = {row[1] for row in existing}
        code_name = base_name
        n = 2
        while code_name in taken:
            code_name = f"{base_name}_{n}"
            n += 1
        try:
            cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                        (code_name, "", owner, now_, catids_by_kind[kind], qc_hex))
            app.conn.commit()
            cur.execute("select last_insert_rowid()")
            cids_by_key[(kind, hl_color)] = cur.fetchone()[0]
            if parent_text_edit is not None:
                parent_text_edit.append(_("New code: ") + code_name)
        except sqlite3.IntegrityError:
            # Roll back: no implicit transaction may stay open.
            app.conn.rollback()
            cur.execute("select cid from code_name where name=?", [code_name])
            res2 = cur.fetchone()
            if res2 is not None:
                cids_by_key[(kind, hl_color)] = res2[0]
    # Codings over the marked positions. Insertion: 60-100 % of the bar.
    counts = {kind: 0 for kind in catids_by_kind}
    for seq, pos in enumerate(positions, start=1):
        cid = cids_by_key.get((pos['kind'], pos['color']))
        if cid is None:
            continue
        seltext = fulltext[pos['pos0']:pos['pos1']]
        if seltext.strip() == "":
            continue
        try:
            # The markup comment becomes the segment memo.
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,memo,date,important) "
                        "values(?,?,?,?,?,?,?,?,?)",
                        (cid, fid, seltext, pos['pos0'], pos['pos1'], owner,
                         pos.get('memo', ''), now_, None))
            app.conn.commit()
            counts[pos['kind']] += 1
        except sqlite3.IntegrityError:
            # Re-import duplicate: roll back, no implicit transaction may stay open.
            app.conn.rollback()
        _show_phase(_("Coding marked segments"), 60 + int(seq * 40 / len(positions)))
    if progress is not None:
        if external:
            progress.setLabelText(filename_)  # Back to the batch label
        else:
            progress.setValue(100)
            progress.close()
    if sum(counts.values()) > 0:
        if parent_text_edit is not None:
            if counts.get('highlight', 0) > 0:
                parent_text_edit.append(
                    _("PDF highlights coded: ") + f"{counts['highlight']}"
                    + _(" segments in ") + filename_)
            if counts.get('underline', 0) > 0:
                parent_text_edit.append(
                    _("PDF underlines coded: ") + f"{counts['underline']}"
                    + _(" segments in ") + filename_)
        if getattr(app, "project_events", None) is not None:
            app.project_events.emit_table_changes(
                ['code_cat', 'code_name', 'code_text'], source=parent_widget)
