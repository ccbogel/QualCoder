"""Regression tests for #1727: importing a QualCoder-origin REFI-QDA text source.

A QualCoder export stores coding positions against ``\\n`` text (one character
per line break), even when the exported ``.txt`` file itself uses ``\\r\\n``
(old Windows exports, or the MaxQDA line-endings export option) and carries a
BOM. ``RefiImport.load_text_source`` used to read the file with ``utf-8`` (so a
BOM became an extra character at position 0) and insert a space after every
line break for CRLF files, shifting every coding after the first line. The fix
reads with ``utf-8-sig`` and skips the space insertion for QualCoder-origin
files; other software keeps the old behaviour.

Runs headless: the real import is tried first (CI has PyQt6 installed); when
that fails the GUI-adjacent modules are stubbed, since ``load_text_source``
itself is pure Python plus sqlite.
"""

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
import xml.etree.ElementTree as etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from qualcoder.refi import RefiImport
except ImportError:
    # Headless environment without PyQt6: stub the GUI-adjacent modules that
    # refi.py imports at module level, then import the real refi.py.
    _pyqt6 = ModuleType("PyQt6")
    _pyqt6.QtWidgets = MagicMock()
    _pyqt6.QtCore = MagicMock()
    sys.modules["PyQt6"] = _pyqt6
    sys.modules["vlc"] = ModuleType("vlc")
    _gui = ModuleType("qualcoder.GUI")
    _gui.__path__ = []
    sys.modules["qualcoder.GUI"] = _gui
    _endings = ModuleType("qualcoder.GUI.ui_dialog_refi_export_endings")
    _endings.Ui_Dialog_refi_export_line_endings = MagicMock()
    sys.modules["qualcoder.GUI.ui_dialog_refi_export_endings"] = _endings
    _color_selector = ModuleType("qualcoder.color_selector")
    _color_selector.colors = {}
    _color_selector.color_matcher = MagicMock()
    sys.modules["qualcoder.color_selector"] = _color_selector
    _helpers = ModuleType("qualcoder.helpers")
    _helpers.Message = MagicMock()
    sys.modules["qualcoder.helpers"] = _helpers
    from qualcoder.refi import RefiImport

NS = "{urn:QDA-XML:project:1.0}"
TEXT = "line one\nline two\nline three\n"
# A Windows QualCoder 4.0 export: UTF-8 BOM plus CRLF line endings.
WINDOWS_BYTES = b"\xef\xbb\xbfline one\r\nline two\r\nline three\r\n"


class TestRefiQualcoderLineEndings(unittest.TestCase):
    """load_text_source keeps QualCoder coding positions; other software unchanged."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        (self.tmp_path / "sources").mkdir()
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE source (name, fulltext, mediapath, memo, owner, date)"
        )
        self.conn.execute(
            "CREATE TABLE code_text (cid, fid, seltext, pos0, pos1, owner, memo, date)"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _importer(self, software_name):
        """A RefiImport with a fake app, bypassing __init__ (it opens file dialogs)."""
        importer = object.__new__(RefiImport)
        importer.app = SimpleNamespace(
            conn=self.conn,
            settings={"codername": "tester"},
            project_path=str(self.tmp_path),
        )
        importer.parent_textedit = []
        importer.sources = []
        importer.source_name_prefix = 0
        importer.users = [{"guid": "u1", "name": "tester"}]
        importer.codes = [{"guid": "code-guid-1", "cid": 1}]
        importer.links = []
        importer.folder_name = str(self.tmp_path)
        importer.sources_name = "/sources"
        importer.software_name = software_name
        importer.xmlns_version = "1.0"
        importer.base_path = ""
        return importer

    def _text_source_element(self, file_path):
        """A TextSource element coding the word 'two' (positions 14-17 in \\n text)."""
        el = etree.Element("TextSource")
        el.set("name", "doc.txt")
        el.set("guid", "src-guid-1")
        el.set("creatingUser", "u1")
        el.set("creationDateTime", "2026-01-01T00:00:00Z")
        el.set("path", f"absolute://{file_path}")
        etree.SubElement(el, f"{NS}Description")
        selection = etree.SubElement(el, f"{NS}PlainTextSelection")
        selection.set("guid", "sel-guid-1")
        selection.set("startPosition", "14")
        selection.set("endPosition", "17")
        selection.set("creatingUser", "u1")
        selection.set("creationDateTime", "2026-01-01T00:00:00Z")
        coding = etree.SubElement(selection, f"{NS}Coding")
        coding.set("guid", "coding-guid-1")
        code_ref = etree.SubElement(coding, f"{NS}CodeRef")
        code_ref.set("targetGUID", "code-guid-1")
        return el

    def _import_file(self, data, software_name):
        file_path = self.tmp_path / "doc.txt"
        file_path.write_bytes(data)
        importer = self._importer(software_name)
        importer.load_text_source(self._text_source_element(file_path))
        fulltext = self.conn.execute("SELECT fulltext FROM source").fetchone()[0]
        row = self.conn.execute(
            "SELECT seltext, pos0, pos1 FROM code_text"
        ).fetchone()
        return fulltext, row

    def test_qualcoder_crlf_bom_file_keeps_positions(self):
        """#1727: BOM dropped, no spaces inserted, the coding still selects 'two'."""
        fulltext, row = self._import_file(WINDOWS_BYTES, "QualCoder 4.0")
        self.assertEqual(TEXT, fulltext)
        self.assertEqual(("two", 14, 17), row)
        self.assertEqual("two", fulltext[14:17])

    def test_other_software_keeps_old_space_insertion(self):
        """Other origins are unaffected: the space-per-line behaviour stays."""
        fulltext, row = self._import_file(WINDOWS_BYTES, "NVivo 14")
        self.assertEqual("line one\n line two\n line three\n ", fulltext)
        # Positions are stored as given; the stored text keeps the old padding,
        # so the slice is " tw" here, exactly as before this change.
        self.assertEqual((" tw", 14, 17), row)

    def test_plain_lf_file_is_unchanged(self):
        """A plain LF file without a BOM imports identically."""
        fulltext, row = self._import_file(TEXT.encode("utf-8"), "QualCoder 4.0")
        self.assertEqual(TEXT, fulltext)
        self.assertEqual(("two", 14, 17), row)


if __name__ == "__main__":
    unittest.main()
