# -*- coding: utf-8 -*-

"""
Helpers for AI-visible memo content.

---

This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Kai Dröge (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

PERSONAL_NOTE_MARK = "#####"


def split_public_private_memo(memo: str) -> tuple[str, str]:
    """Split a memo into AI-visible text and a preserved private suffix."""

    memo_text = "" if memo is None else str(memo)
    mark = memo_text.find(PERSONAL_NOTE_MARK)
    if mark < 0:
        return memo_text, ""
    return memo_text[:mark], memo_text[mark:]


def extract_ai_memo(memo: str) -> str:
    """Return only the memo text that may be sent to the AI."""

    public_memo, _private_suffix = split_public_private_memo(memo)
    return public_memo


def merge_public_memo(existing_memo: str, new_public_memo: str) -> str:
    """Replace the public memo text while preserving any private suffix."""

    existing_public, private_suffix = split_public_private_memo(existing_memo)
    public_memo = extract_ai_memo(new_public_memo)
    if private_suffix == "":
        return public_memo
    if public_memo == "":
        return private_suffix
    trimmed_existing_public = existing_public.rstrip(" \t\r\n")
    separator = existing_public[len(trimmed_existing_public):]
    return public_memo + separator + private_suffix
