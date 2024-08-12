# -*- coding: utf-8 -*-

"""
Copyright (c) 2023 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
"""
import webbrowser
from copy import deepcopy
import datetime
import logging
import os
from PIL import Image, ImageColor, ImageDraw, ImageFont
from PyQt6 import QtWidgets
from random import randint
import sys
import traceback

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
    """ Create a wordcloud using text separated with spaces. Punctuaiton aparat from apostrophe is removed from the text,
    and the text is converted to lower case. The wordcloud uses the Droid-sans font which is located in the
    /Users/yourname/home/.qualcoder folder.
    A stopwords.txt file stored in the .qualcoder folder will override the stopwords listed below.
    The maximum font siz is the height / 6. The minimum font size is 10. Font sizes are scaled by word frequency.
    Options include:
        maximum number of words to use
        image width and height
        black or white background
        text color(s): a single named colour in Pil, or a named in the named colour ranges above.
        reverse_colors: if true, reverses the order of the colour range
        trigrams: if true, use 3 word phrases in the word cloud
    """

    def __init__(self, app, fulltext, width=800, height=600, max_words=200, background_color="black",
                 text_color="random", reverse_colors=False, ngrams=1):

        self.app = app  # Used for project path
        self.width = width
        self.height = height
        self.max_words = max_words
        self.background_color = background_color
        self.text_color = text_color
        self.color_range_chosen = []
        reverse_colors = reverse_colors
        for color_range in color_ranges:
            if color_range["name"] == text_color:
                # Need to deepcopy otherwise range may be reversed already from previous calls to class
                self.color_range_chosen = deepcopy(color_range["range"])
        if reverse_colors and self.color_range_chosen:
            self.color_range_chosen.reverse()
        self.ngrams = ngrams
        self.max_font_size = int(self.height / 6)  # This factor seems oK
        self.min_font_size = 10
        self.font_path = os.path.join(os.path.expanduser('~'), ".qualcoder", "DroidSansMono.ttf")
        # Get a different stopwords file from the .qualcoder folder
        stopwords_file_path = os.path.join(os.path.expanduser('~'), ".qualcoder", "stopwords.txt")
        self.stopwords = []
        try:
            # Can get UnicodeDecode Error on Windows so using error handler
            with open(stopwords_file_path, "r", encoding="utf-8", errors="backslashreplace") as stopwords_file:
                while 1:
                    stopword = stopwords_file.readline()
                    if stopword[0:6] == "\ufeff":  # Associated with notepad files
                        stopword = stopword[6:]
                    if not stopword:
                        break
                    self.stopwords.append(stopword.strip())  # Remove line ending
        except FileNotFoundError as err:
            self.stopwords = stopwords

        # Remove most punctuation except apostrophe. Convert to lower case
        chars = ""
        for c in range(0, len(fulltext)):
            if fulltext[c].isalpha() or fulltext[c] == "'":
                chars += fulltext[c]
            else:
                chars += " "
        chars = chars.lower()
        word_list = []
        word_list_with_stopwords = chars.split()
        for word in word_list_with_stopwords:
            if word not in self.stopwords:
                word_list.append(word)
        # print("Words: " + f"{len(word_list):,d}")
        #print(word_list)
        if self.ngrams > 1:
            word_list = self.make_ngrams(word_list_with_stopwords, self.ngrams)
            #print(word_list)
            self.max_font_size = int(self.height / 18)  # Needs this bigger divisor. Phrases can be long
            if self.max_font_size < self.min_font_size:
                self.max_font_size = self.min_font_size
        # Word frequency
        d = {}
        for word in word_list:
            d[word] = d.get(word, 0) + 1  # get(key, value if not present)
        self.words = []
        for key, value in d.items():
            self.words.append({"text": key, "frequency": value, "x": 0, "y": -100})
        self.words = sorted(self.words, key=lambda x: x["frequency"], reverse=True)
        if len(self.words) == 0:
            self.words.append({"text": "NO WORDS", "frequency": 1, "x": 0, "y": 0})
        # print("Unique words: " + str(len(self.words)))

        # Limit number of words to display
        max_count = len(self.words)
        if len(self.words) > self.max_words:
            self.words = self.words[:self.max_words]
        # Add frequency count, relative font size and color to each word
        total_frequency = 0
        for word in self.words:
            total_frequency += word["frequency"]
        self.font_scale = self.max_font_size / self.words[0]['frequency']
        for i, word in enumerate(self.words):
            word["color"] = self.word_color(i)
            word['font_size'] = int(self.font_scale * word['frequency'])
            if word['font_size'] < self.min_font_size:
                word['font_size'] = self.min_font_size
            font = ImageFont.truetype(self.font_path, size=word['font_size'])
            left, upper, right, lower = font.getbbox(word['text'])
            word['width'] = right - left
            word['height'] = lower - upper
        # Set x and y with adjustment to minimse overlaps
        for i, word in enumerate(self.words):
            self.position_word_minimise_overlapping(word)
        self.create_image()

    def position_word_minimise_overlapping(self, word):
        """ Try to reduce word overlap by identifying text font bounding boxes.
         While there are overlaps keep creating new x, y coordinates until no overlaps.
         Does not work perfectly, but does reduce overlaps. """

        words2 = deepcopy(self.words)
        words2.remove(word)

        x_upper = self.width - 10 - word['width']
        if x_upper < 0:
            x_upper = 1
        y_upper = self.height - 10 - word['height']
        if y_upper < 0:
            y_upper = 1
        overlap = True
        counter = 0
        while overlap and counter < 1000:
            word["x"] = randint(0, x_upper)
            word["y"] = randint(0, y_upper)
            overlap = False
            counter += 1
            for word2 in words2:
                if word2['x'] <= word['x'] < word2['x'] + word2['width'] and \
                        word2['y'] <= word['y'] < word2['y'] + word2['height'] and \
                        word2['y'] != -100:
                    overlap = True
                    # print("Word ", word, "\nWord2", word2, "\n")
                if word['x'] <= word2['x'] < word['x'] + word['width'] and \
                        word['y'] <= word2['y'] < word['y'] + word['height'] and \
                        word2['y'] != -100:
                    overlap = True
                    # print("Word ", word, "\nWord2", word2, "\n")
                if word2['x'] <= word['x'] < word2['x'] + word2['width'] and \
                        word['y'] <= word2['y'] < word['y'] + word['height'] and \
                        word2['y'] != -100:
                    overlap = True
                if word['x'] <= word2['x'] < word['x'] + word['width'] and \
                        word2['y'] <= word['y'] < word2['y'] + word2['height'] and \
                        word2['y'] != -100:
                    overlap = True
        # If the word shape does not fit, do not use it.
        if counter >= 1000:
            word['y'] = - 100
            word['text'] = ""
        #print(word['text'], counter)
        return

    def word_color(self, list_position):
        """ Use list position and words count to determine colour in color range. """

        if self.color_range_chosen:
            num_colors = len(self.color_range_chosen)
            color_position = int(list_position / len(self.words) * num_colors)
            color = self.color_range_chosen[color_position]
            return color
        if self.text_color == "random":
            colors = []
            for name, code in ImageColor.colormap.items():
                colors.append(code)
            color = colors[randint(0, len(colors) - 1)]
            return color
        return self.text_color

    def make_ngrams(self, tokens, number_of_words):
        """ Create trigrams from words list. """

        ngrams_list = []
        for i in range(len(tokens) - number_of_words + 1):
            tokens_list = tokens[i: i + number_of_words]
            ngrams_list.append(" ".join(tokens_list))
        return ngrams_list

    def create_image(self):
        """ Create image and save to Downloads. Draw lesser frequency words first.
        Image saved to Downloads as png. """

        img = Image.new("RGB", (self.width, self.height), self.background_color)
        draw = ImageDraw.Draw(img)
        for word in reversed(self.words):
            font = ImageFont.truetype(self.font_path, size=word['font_size'])
            draw.text((word['x'], word['y']), word["text"], font=font, fill=word["color"])
        time_now = datetime.datetime.now().astimezone().strftime("%H-%M-%S")
        temp_filepath = os.path.join(os.path.expanduser("~"), ".qualcoder", f"wordcloud_temp.png")
        img.save(temp_filepath)
        webbrowser.open(temp_filepath)
        filepath, ok = QtWidgets.QFileDialog.getSaveFileName(None, _("Save wordcloud"),
                                                             self.app.settings['directory'],
                                                             "PNG Files(*.png)")
        # options=QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        if filepath is None or not ok:
            return
        if filepath[-3:] != ".png":
            filepath += ".png"
        img.save(filepath)


if __name__ == "__main__":
    test_text = "qualcoder qualcoder qualcoder qualcoder dogs cats birds qualitative analysis  qualitative analysis qualitative analysis research research"
    Wordcloud(test_text)
