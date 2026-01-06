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

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io/
"""

import webbrowser
from copy import deepcopy
import datetime
import logging
import os
from PyQt6 import QtWidgets
import sys
import traceback
from wordcloud import WordCloud
from PIL import ImageColor

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


color_ranges = [
    {"name": "blue to yellow",
     "range": ["#115f9a", "#1984c5", "#22a7f0", "#48b5c4", "#76c68f", "#a6d75b", "#c9e52f", "#d0ee11", "#d0f400"]},
    {"name": "grey to red",
     "range": ["#d7e1ee", "#cbd6e4", "#bfcbdb", "#b3bfd1", "#a4a2a8", "#df8879", "#c86558", "#b04238", "#991f17"]},
    {"name": "black to pink",
     "range": ["#2e2b28", "#3b3734", "#474440", "#54504c", "#6b506b", "#ab3da9", "#de25da", "#eb44e8", "#ff80ff"]},
    {"name": "blue to red",
     "range": ["#1984c5", "#22a7f0", "#63bff0", "#a7d5ed", "#e2e2e2", "#e1a692", "#de6e56", "#e14b31", "#c23728"]},
    {"name": "blue to orange",
     "range": ["#003F5C", "#2F4B7C", "#665191", "#A05195", "#D45087", "#F95D6A", "#FF7C43", "#FFA600"]},
    {"name": "orange to purple",
     "range": ["#ffb400", "#d2980d", "#a57c1b", "#786028", "#363445", "#48446e", "#5e569b", "#776bcd", "#9080ff"]},
    {"name": "salmon to aqua",
     "range": ["#e27c7c", "#a86464", "#6d4b4b", "#503f3f", "#333333", "#3c4e4b", "#466964", "#599e94", "#6cd4c5"]},
    {"name": "green to blue", "range": ["#00D40E", "#00BA2D", "#009658", "#007185", "#0053AB", "#003193"]},
    {"name": "yellow to green", "range": ["#FEFB01", "#CEFB02", "#87FA00", "#3AF901", "#00ED01"]},
    {"name": "aqua to pink",
     "range": ["#54bebe", "#76c8c8", "#98d1d1", "#badbdb", "#dedad2", "#e4bcad", "#df979e", "#d7658b", "#c80064"]},
    {"name": "river nights",
     "range": ["#b30000", "#7c1158", "#4421af", "#1a53ff", "#0d88e6", "#00b7c7", "#5ad45a", "#8be04e", "#ebdc78"]},
    {"name": "blue to aqua",
     "range": ["#004C6D", "#006083", "#007599", "#008BAD", "#00A1C1", "#00B8D3", "#00CFE3", "#00E7F2", "#00FFFF"]},
    {"name": "greens",
     "range": ["#198450", "#27A567", "#2EB774", "#38CB82", "#41DC8E", "#64E3A1", "#84EAB3", "#AAF0C9", "#CBF5DD"]},
    {"name": "oranges", "range": ["#FF5500", "#FF6500", "#ff7500", "#FF8500", "#FF9500"]},
    {"name": "blues",
     "range": ["#0000b3", "#0010d9", "#0020ff", "#0040ff", "#0060ff", "#0080ff", "#009fff", "#00bfff", "#00ffff"]},
    {"name": "pinks", "range": ["#A73CA4", "#C353C0", "#D178CF", "#DF9DDD", "#ECC3EB"]},
    {"name": "greys", "range": ["#F2F2F2", "#C2C2C2", "#929292", "#616161", "#414141", "#202020"]},
    {"name": "yellows",
     "range": ["#E47200", "#E69B00", "#E6B400", "#E6CC00", "#E5DE00", "#E8E337", "#ECE75F", "#F1EE8E", "#F7F5BC"]},
    {"name": "reds",
     "range": ["#C61A09", "#DF2C14", "#ED3419", "#FB3B1E", "#FF4122", "#FF6242", "#FF8164", "#FFA590", "#FFC9BB"]}
]

stopwords = ["a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as",
             "at",
             "b", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "c", "can",
             "can't", "could", "couldn't",
             "d", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
             "e", "each", "f", "few", "for", "from", "further", "g", "get", "got",
             "h", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he's", "her", "here",
             "hers", "herself", "him", "himself", "his", "how",
             "i", "i'll", "i'm", "i've", "if", "in", "into", "is", "is'nt", "isn't", "it", "it's", "its", "itself",
             "j", "just", "k", "l", "m", "me", "more", "most", "my", "myself", "n", "no", "nor", "not", "now",
             "o", "of", "off", "oh", "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over",
             "own",
             "p", "pre", "put", "q", "r", "re",
             "s", "same", "she", "she'd", "she's", "should", "shouldn't", "so", "some", "such",
             "t", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's",
             "these",
             "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too",
             "u", "uh", "um", "under", "until", "up", "us", "v", "very",
             "w", "was", "wasn't", "we", "we're", "we've", "were", "weren't", "what",
             "what's", "when", "where", "which", "while",
             "who", "who's", "whom", "why", "will", "with", "would", "wouldn't",
             "x", "y", "you", "you'd", "you'ld", "you're", "you've", "your", "yours", "yourself", "yourselves", "z"]


class Wordcloud:
    """Create a wordcloud using the `wordcloud` package.

    Args are mostly compatible with the original implementation:
        app: kept for compatibility (not used here except for potential future use)
        fulltext: source text
        width, height: image dimensions
        max_words: maximum number of words
        background_color: passed directly to WordCloud
        text_color:
            - "random": use wordcloud's default random coloring
            - a named color ("red", "#ff0000", etc.)
            - a color range name from color_ranges above
        reverse_colors: reverse order of the chosen color range
        ngrams: 1 for single words, >1 for n-grams
        stopwords_filepath2: alternative stopwords file path
    """

    def __init__(
        self,
        app,
        fulltext,
        width=800,
        height=600,
        max_words=200,
        background_color="black",
        text_color="random",
        reverse_colors=False,
        ngrams=1,
        stopwords_filepath2=None
    ):
        self.app = app
        self.width = width
        self.height = height
        self.max_words = max_words
        self.background_color = background_color
        self.text_color = text_color
        self.ngrams = ngrams
        self.reverse_colors = reverse_colors

        # Font in ~/.qualcoder
        self.font_path = os.path.join(os.path.expanduser('~'), ".qualcoder", "DroidSansMono.ttf")

        # Stopwords: file in ~/.qualcoder or provided path, fallback to built-in list
        stopwords_file_path = os.path.join(os.path.expanduser('~'), ".qualcoder", "stopwords.txt")
        if stopwords_filepath2 is not None:
            stopwords_file_path = stopwords_filepath2

        self.stopwords = []
        try:
            with open(stopwords_file_path, "r", encoding="utf-8", errors="backslashreplace") as stopwords_file:
                while True:
                    stopword = stopwords_file.readline()
                    if not stopword:
                        break
                    if stopword[0:6] == "﻿":  # BOM from some editors
                        stopword = stopword[6:]
                    self.stopwords.append(stopword.strip())
        except FileNotFoundError as err:
            print(err)
            self.stopwords = stopwords

        # ---- TEXT PREPROCESSING + NGRAMS ----
        # 1) Clean text (letters + apostrophes, lowercased)
        cleaned = self._clean_text(fulltext)

        # 2) Tokenize
        tokens = cleaned.split()

        # 3) Build n-grams before applying stopwords,
        #    then drop n-grams that are entirely stopwords.
        if self.ngrams > 1:
            units = self.make_ngrams(tokens, self.ngrams)
            # Optional: filter out n-grams where every word is a stopword
            filtered_units = []
            sw_set = set(self.stopwords)
            for phrase in units:
                words = phrase.split()
                if not all(w in sw_set for w in words):
                    filtered_units.append(phrase)
            units = filtered_units
        else:
            units = tokens

        # 4) Remove pure stopword tokens for ngrams=1
        if self.ngrams == 1:
            sw_set = set(self.stopwords)
            units = [t for t in units if t not in sw_set]

        # 5) Build frequency dictionary
        freq = {}
        for u in units:
            freq[u] = freq.get(u, 0) + 1

        if not freq:
            freq = {"NO WORDS": 1}

        # ---- COLOR HANDLING ----
        color_func, colormap = self._build_color_function()

        # ---- WORDCLOUD CONSTRUCTION ----
        wc = WordCloud(
            width=self.width,
            height=self.height,
            max_words=self.max_words,
            background_color=self.background_color,
            stopwords=set(self.stopwords),
            font_path=self.font_path,
            color_func=color_func,
            colormap=colormap,  # used only if color_func is None
            scale=3  # higher-quality PNG
        )

        if self.reverse_colors:
            if wc.colormap is not None and hasattr(wc.colormap, "reversed"):
                wc.colormap = wc.colormap.reversed()

        # Generate image from frequencies
        wc.generate_from_frequencies(freq)

        temp_filepath = os.path.join(os.path.expanduser("~"), ".qualcoder", "wordcloud_temp.png")
        wc.to_file(temp_filepath)
        webbrowser.open(temp_filepath)

    # ---------------- helper methods ----------------

    def _clean_text(self, fulltext: str) -> str:
        """Remove most punctuation except apostrophe; convert to lowercase."""
        chars = []
        for ch in fulltext:
            if ch.isalpha() or ch == "'":
                chars.append(ch)
            else:
                chars.append(" ")
        return "".join(chars).lower()

    def make_ngrams(self, tokens, number_of_words):
        """ Create trigrams from words list. """

        ngrams_list = []
        for i in range(len(tokens) - number_of_words + 1):
            tokens_list = tokens[i: i + number_of_words]
            ngrams_list.append(" ".join(tokens_list))
        return ngrams_list

    def _build_color_function(self):
        """Return (color_func, colormap) suitable for WordCloud based on text_color.

        - If text_color is a named color range: build a color_func cycling through that list.
        - If text_color is 'random': use default WordCloud random coloring (return (None, None)).
        - Otherwise: treat text_color as a fixed color string (#rrggbb or named) and
          build a color_func returning that color.
        """
        # Determine if text_color matches one of the defined color ranges
        color_range_chosen = []
        for color_range in color_ranges:
            if color_range["name"] == self.text_color:
                color_range_chosen = deepcopy(color_range["range"])
                break

        if color_range_chosen:
            def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
                idx = abs(hash(word)) % len(color_range_chosen)
                return color_range_chosen[idx]
            return color_func, None

        if self.text_color == "random":
            return None, None

        fixed_color = self.text_color

        def single_color_func(word, font_size, position, orientation, random_state=None, **kwargs):
            return fixed_color

        return single_color_func, None

if __name__ == "__main__":
    test_text = "qualcoder qualcoder qualcoder qualcoder dogs cats birds qualitative analysis  qualitative analysis qualitative analysis research research"
    Wordcloud(test_text)
