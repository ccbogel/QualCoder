"""Tests for qualcoder.coding_common (pure logic shared by the coding modules)."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from qualcoder.coding_common import (  # noqa: E402
    build_code_tooltip_html,
    load_recent_codes,
    truncate_memo_text,
    truncate_selection_text,
)


class TestTruncateSelectionText(unittest.TestCase):

    def test_short_text_unchanged(self):
        self.assertEqual(truncate_selection_text("hello world"), "hello world")

    def test_newlines_removed(self):
        self.assertEqual(truncate_selection_text("a\nb\r\nc"), "abc")

    def test_long_text_truncated_with_ellipsis(self):
        text_ = " ".join("word" for _ in range(50))
        result = truncate_selection_text(text_)
        self.assertIn(" ... ", result)
        self.assertLess(len(result), len(text_))

    def test_none_returns_empty(self):
        self.assertEqual(truncate_selection_text(None), "")

    def test_memo_truncation(self):
        self.assertEqual(truncate_memo_text("x" * 200), "x" * 150 + "...")
        self.assertEqual(truncate_memo_text("short"), "short")


class TestBuildCodeTooltipHtml(unittest.TestCase):

    def test_text_coding_tooltip(self):
        code = {
            'name': 'Theme', 'color': '#F5F6CE', 'ctid': 12, 'owner': 'researcher',
            'seltext': 'some coded text', 'memo': '', 'important': 0,
        }
        html = build_code_tooltip_html(code, show_ids=False)
        self.assertIn('Theme', html)
        self.assertIn('some coded text', html)
        self.assertNotIn('ctid', html)
        self.assertIn('researcher', html)

    def test_show_ids_includes_ctid(self):
        code = {'name': 'X', 'color': '#F5F6CE', 'ctid': 5, 'owner': 'a', 'seltext': 's'}
        html = build_code_tooltip_html(code, show_ids=True)
        self.assertIn('ctid:5', html)

    def test_area_coding_tooltip(self):
        code = {'name': 'Area', 'color': '#F5F6CE', 'imid': 3, 'owner': 'a',
                'pdf_page': 2, 'memo': 'm', 'important': 1}
        html = build_code_tooltip_html(code, show_ids=True, is_area=True)
        self.assertIn('imid:3', html)
        self.assertIn('MEMO', html)
        self.assertIn('IMPORTANT', html)

    def test_memo_and_important_flags(self):
        code = {'name': 'N', 'color': '#F5F6CE', 'ctid': 1, 'owner': 'a',
                'seltext': 's', 'memo': 'my memo', 'important': 1}
        html = build_code_tooltip_html(code, show_ids=False)
        self.assertIn('MEMO', html)
        self.assertIn('IMPORTANT', html)


class TestLoadRecentCodes(unittest.TestCase):

    def _conn_with_recent(self, value):
        conn = sqlite3.connect(":memory:")
        conn.execute("create table project (recently_used_codes text)")
        conn.execute("insert into project values (?)", [value])
        return conn

    def test_returns_matching_codes_in_order(self):
        conn = self._conn_with_recent("2 1")
        codes = [{'cid': 1, 'name': 'a'}, {'cid': 2, 'name': 'b'}, {'cid': 3, 'name': 'c'}]
        result = load_recent_codes(conn, codes)
        self.assertEqual([c['cid'] for c in result], [2, 1])

    def test_ignores_unknown_and_invalid_ids(self):
        conn = self._conn_with_recent("9 xx 1")
        codes = [{'cid': 1, 'name': 'a'}]
        result = load_recent_codes(conn, codes)
        self.assertEqual([c['cid'] for c in result], [1])

    def test_empty_value(self):
        conn = self._conn_with_recent("")
        self.assertEqual(load_recent_codes(conn, [{'cid': 1}]), [])

    def test_missing_table_returns_empty(self):
        conn = sqlite3.connect(":memory:")
        self.assertEqual(load_recent_codes(conn, [{'cid': 1}]), [])


if __name__ == "__main__":
    unittest.main()
