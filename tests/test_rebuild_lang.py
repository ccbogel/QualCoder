from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from lxml import etree

import rebuild_lang


class TestQtTranslationUpdate(TestCase):
    """Regression tests for Qt translation source extraction."""

    def test_pylupdate_uses_qt_designer_sources(self):
        with TemporaryDirectory() as temp_dir:
            ui_dir = Path(temp_dir)
            (ui_dir / "ui_second.ui").touch()
            (ui_dir / "ui_first.ui").touch()
            (ui_dir / "ui_generated.py").touch()

            with (
                patch.object(rebuild_lang, "GUI_UI_DIR", str(ui_dir)),
                patch.object(rebuild_lang, "run_subprocess", return_value=True) as run,
            ):
                result = rebuild_lang.run_pylupdate6(["de.ts"])

            self.assertTrue(result)
            run.assert_called_once_with(
                [
                    "pylupdate6",
                    "--ts",
                    "de.ts",
                    "ui_first.ui",
                    "ui_second.ui",
                ],
                cwd=str(ui_dir),
            )

    def test_delete_obsolete_ts_removes_inactive_messages(self):
        with TemporaryDirectory() as temp_dir:
            ts_path = Path(temp_dir) / "de.ts"
            ts_path.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1">
  <context>
    <name>MainWindow</name>
    <message><source>Active</source><translation>Aktiv</translation></message>
    <message><source>Pending</source><translation type="unfinished" /></message>
    <message><source>Old</source><translation type="obsolete">Alt</translation></message>
    <message><source>Gone</source><translation type="vanished">Weg</translation></message>
  </context>
</TS>
""",
                encoding="utf-8",
            )

            rebuild_lang.delete_obsolete_ts(str(ts_path))

            tree = etree.parse(str(ts_path))
            sources = tree.xpath("//message/source/text()")
            self.assertEqual(["Active", "Pending"], sources)
