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

"""Tokenisation, normalisation, stopwords and light stemming.

The stemming is deliberately light (suffix stripping, no heavy dependency such
as spaCy): the "stem" option of the analyses uses light_stem, the "none" option
keeps the surface forms.
"""

import logging
import re
from pathlib import Path
from typing import Iterable, Optional

from .. import stopwords as qc_stopwords

logger = logging.getLogger(__name__)

# A token is a run of letters/digits, keeping intra-word apostrophes and hyphens
# (l'homme, porte-monnaie), as IRaMuTeQ does.
TOKEN_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)

# Light suffix lists, longest first. Only stripped when the remaining stem is
# at least 4 characters long.
FR_SUFFIXES = (
    "ements", "ement", "ations", "ation", "atrices", "atrice", "ateurs", "ateur",
    "tions", "tion", "ences", "ence", "ments", "ment", "ités", "ité",
    "ives", "ive", "ifs", "if", "euses", "euse", "eux", "ants", "ant",
    "ées", "ée", "és", "é", "ers", "er", "ir", "re", "s",
)
EN_SUFFIXES = ("ing", "ed", "es", "s")


def tokenize(text: str, lowercase: bool = True) -> list:
    """Split a text into tokens (formes).

    Args:
        text: raw text
        lowercase: lowercase the tokens
    Returns:
        List of tokens; punctuation is removed, intra-word apostrophes and
        hyphens are kept.
    """

    tokens = TOKEN_RE.findall(text if text else "")
    if lowercase:
        tokens = [token.lower() for token in tokens]
    return tokens


def load_stopwords(language: str = "fr", extra_words: Optional[Iterable[str]] = None,
                   custom_path: Optional[str] = None) -> set:
    """Stopwords for a language: built-in ISO list (qualcoder.stopwords) plus
    extra words and an optional editable custom file (one word per line,
    '#' starts a comment).

    Args:
        language: 2-letter ISO code ("fr", "en", "de", "es", ...)
        extra_words: additional words to remove
        custom_path: path of an editable stopword file, or None
    Returns:
        Set of stopwords.
    """

    words = set()
    builtin = getattr(qc_stopwords, language, "") or ""
    words.update(word for word in builtin.split() if word)
    if extra_words:
        words.update(str(word).strip().lower() for word in extra_words if str(word).strip())
    if custom_path:
        path = Path(custom_path)
        if path.is_file():
            with open(path, encoding="utf-8") as file_:
                for line in file_:
                    line = line.split("#", 1)[0].strip().lower()
                    if line:
                        words.add(line)
        else:
            logger.warning("Custom stopwords file not found: %s", custom_path)
    return words


def light_stem(token: str, language: str = "fr") -> str:
    """Light stemming by suffix stripping (no heavy NLP dependency).

    Only one suffix is stripped, and only when the remaining stem is at least
    4 characters long. Unknown languages are returned unchanged.
    """

    if language == "fr":
        suffixes = FR_SUFFIXES
    elif language == "en":
        suffixes = EN_SUFFIXES
    else:
        return token
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def normalize_tokens(tokens: list, stopwords: Optional[set] = None, stem: bool = False,
                     language: str = "fr") -> list:
    """Apply stopword removal and optional light stemming to tokens. """

    stopwords = stopwords or set()
    normalized = []
    for token in tokens:
        if token in stopwords:
            continue
        if stem:
            token = light_stem(token, language)
        normalized.append(token)
    return normalized


def segment_tokens(text: str, language: str = "fr", lowercase: bool = True,
                   stopwords: Optional[set] = None, stem: bool = False) -> list:
    """Full normalisation pipeline for one segment text: tokenize then normalize. """

    return normalize_tokens(tokenize(text, lowercase=lowercase), stopwords=stopwords,
                            stem=stem, language=language)
