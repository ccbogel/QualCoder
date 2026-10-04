# -*- coding: utf-8 -*-
"""This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/

Shared pure logic for the coding modules (code_text, code_pdf, code_av).
Contains no Qt or database imports so it can be unit tested in isolation.
"""
from gettext import gettext as _


CODE_NAME = 'name'
CODE_COLOR = 'color'
CODE_MEMO = 'memo'
CODE_IMPORTANT = 'important'
CODE_OWNER = 'owner'
CODE_CID = 'cid'
CODE_CTID = 'ctid'
CODE_IMID = 'imid'

_WHITE_TEXT_CODES = [
    "#EB7333", "#E65100", "#C54949", "#B71C1C", "#CB5E3C", "#BF360C",
    "#FA58F4", "B76E95", "#9F3E72", "#880E4F", "#7D26CD", "#1B5E20",
    "#487E4B", "#1B5E20", "#5E9179", "#AC58FA", "#5E9179", "#9090E3",
    "#6B6BDA", "#4646D1", "#3498DB", "#6D91C6", "#3D6CB3", "#0D47A1",
    "#9090E3", "#5882FA", "#9651D7",
]


def recommended_text_color(color):
    """Light or dark text recommendation depending on the code color.
    Mirrors color_selector.TextColor without the PyQt dependency.
    """
    if color in _WHITE_TEXT_CODES:
        return "#eeeeee"
    return "#000000"


def truncate_selection_text(seltext, max_len=90, head=40, tail=40):
    """Single-line, readable cut-off of a coded text selection.

    Not halfway through a word. Mirrors the historic ToolTipEventFilter
    behaviour shared by code_text and code_pdf.
    """
    seltext = (seltext or "").replace("\n", "").replace("\r", "")
    if len(seltext) > max_len:
        pre = seltext[0:head].split(' ')
        post = seltext[len(seltext) - tail:].split(' ')
        try:
            pre = pre[:-1]
        except IndexError:
            pass
        try:
            post = post[1:]
        except IndexError:
            pass
        seltext = " ".join(pre) + " ... " + " ".join(post)
    return seltext


def truncate_memo_text(memo, max_len=150):
    if len(memo) > max_len:
        memo = memo[:max_len] + "..."
    return memo


def build_code_tooltip_html(code, show_ids, is_area=False):
    """HTML tooltip of a coded segment (text or image area).

    code is a dict with keys: name, color, memo, important, owner and,
    for text codings, ctid and seltext; for areas, imid and pdf_page.
    """
    color = code.get(CODE_COLOR, '#cccccc') or '#cccccc'
    text_ = '<p style="background-color:' + color + "; color:" + \
        recommended_text_color(color) + '"><em>'
    text_ += code.get(CODE_NAME, '') + "</em>"
    if show_ids:
        if is_area:
            text_ += " [imid:" + str(code.get(CODE_IMID, '')) + "]"
        else:
            text_ += " [ctid:" + str(code.get(CODE_CTID, '')) + "]"
    text_ += " (" + str(code.get(CODE_OWNER, '')) + ")"
    if is_area:
        page_no = (code.get('pdf_page', 0) or 0) + 1
        text_ += "<br />" + _("Coded area") + " - " + _("Page") + " " + str(page_no)
    else:
        text_ += "<br />" + truncate_selection_text(code.get('seltext', ''))
    if code.get(CODE_MEMO, '') != "":
        text_ += "<br /><em>" + _("MEMO: ") + truncate_memo_text(code[CODE_MEMO]) + "</em>"
    if code.get(CODE_IMPORTANT) == 1:
        text_ += "<br /><em>" + _("IMPORTANT") + "</em>"
    text_ += "</p>"
    return text_


def load_recent_codes(conn, codes):
    """Get recently used codes, stored as space separated code ids in
    the project table. Requires the full codes list already loaded.

    Args:
        conn : sqlite3 connection
        codes : list of code dicts
    Returns: list of code dicts
    """
    recent_codes = []
    cur = conn.cursor()
    try:
        cur.execute("select recently_used_codes from project")
        res = cur.fetchone()
    except Exception:
        return recent_codes
    if not res or res[0] == "" or res[0] is None:
        return recent_codes
    for code_id in res[0].split():
        try:
            cid = int(code_id)
        except ValueError:
            continue
        for code_ in codes:
            if cid == code_[CODE_CID]:
                recent_codes.append(code_)
    return recent_codes


def select_tree_item_by_code_name(tree_widget, item, text_):
    """Set matching item to be the current selected item.
    Recurse through any child categories.

    Args:
        tree_widget : QTreeWidget
        item : QTreeWidgetItem, usually the invisible root item
        text_ : String code name to match
    """
    child_count = item.childCount()
    for i in range(child_count):
        child = item.child(i)
        if child.text(1)[0:3] == "cid" and (child.text(0) == text_ or child.toolTip(0) == text_):
            tree_widget.setCurrentItem(child)
        select_tree_item_by_code_name(tree_widget, child, text_)
