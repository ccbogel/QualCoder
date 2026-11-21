# -*- coding: utf-8 -*-

"""Unit tests for qualcoder.irastats.text (pure Python, no GUI)."""

import tempfile
import unittest
from pathlib import Path

from qualcoder.irastats.text import light_stem, load_stopwords, normalize_tokens, segment_tokens, tokenize


class TestTokenize(unittest.TestCase):

    def test_lowercase_and_punctuation(self):
        self.assertEqual(tokenize("Le Chat, mange!"), ["le", "chat", "mange"])

    def test_apostrophes_and_hyphens_kept(self):
        self.assertEqual(tokenize("L'homme porte-monnaie."), ["l'homme", "porte-monnaie"])

    def test_no_lowercase(self):
        self.assertEqual(tokenize("Le Chat", lowercase=False), ["Le", "Chat"])

    def test_empty(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])


class TestStopwords(unittest.TestCase):

    def test_builtin_fr_en(self):
        self.assertIn("le", load_stopwords("fr"))
        self.assertIn("the", load_stopwords("en"))

    def test_unknown_language_is_empty(self):
        self.assertEqual(load_stopwords("xx"), set())

    def test_extra_words(self):
        words = load_stopwords("fr", extra_words=["Foo", "bar"])
        self.assertIn("foo", words)
        self.assertIn("bar", words)

    def test_custom_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stopwords.txt"
            path.write_text("# comment\ncustomword\nAutreMot\n\n", encoding="utf-8")
            words = load_stopwords("en", custom_path=str(path))
        self.assertIn("customword", words)
        self.assertIn("autremot", words)

    def test_missing_custom_file_is_ignored(self):
        words = load_stopwords("en", custom_path="/nonexistent/stopwords.txt")
        self.assertIn("the", words)


class TestLightStem(unittest.TestCase):

    def test_french_suffixes(self):
        self.assertEqual(light_stem("manger", "fr"), "mang")
        self.assertEqual(light_stem("chats", "fr"), "chat")
        self.assertEqual(light_stem("nation", "fr"), "nation")  # stem would be too short
        self.assertEqual(light_stem("par", "fr"), "par")  # no stripping below 4 chars of stem

    def test_english_suffixes(self):
        self.assertEqual(light_stem("running", "en"), "runn")
        self.assertEqual(light_stem("houses", "en"), "hous")
        self.assertEqual(light_stem("cats", "en"), "cats")  # stem would be too short

    def test_unknown_language_unchanged(self):
        self.assertEqual(light_stem("manger", "de"), "manger")


class TestNormalize(unittest.TestCase):

    def test_stopwords_removed(self):
        tokens = tokenize("le chat et le chien")
        self.assertEqual(normalize_tokens(tokens, stopwords={"le", "et"}), ["chat", "chien"])

    def test_stem_option(self):
        tokens = tokenize("manger mangé")
        self.assertEqual(normalize_tokens(tokens, stem=True, language="fr"), ["mang", "mang"])
        self.assertEqual(normalize_tokens(tokens, stem=False, language="fr"), ["manger", "mangé"])

    def test_segment_tokens_pipeline(self):
        self.assertEqual(segment_tokens("Le chat!", language="fr", stopwords={"le"}), ["chat"])


if __name__ == "__main__":
    unittest.main()
