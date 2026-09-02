from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from qualcoder.ai_agent_prompts import (
    AiAgentPromptsCatalog,
    is_valid_prompt_folder_name,
    is_valid_prompt_name,
    is_windows_reserved_prompt_name,
    normalize_prompt_name_component,
    prompt_folder_name_fits_filesystem,
    prompt_name_fits_filesystem,
    prompt_name_key,
)


class TestPromptNames(TestCase):
    """Regression tests for portable prompt names and prompt resolution."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name)
        self.prompt_root = self.config_dir / "ai_prompts"
        self.prompt_root.mkdir()
        app = SimpleNamespace(confighome=str(self.config_dir), project_path="")
        self.catalog = AiAgentPromptsCatalog(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_prompt(self, relative_path: str, body: str = "Test prompt") -> None:
        """Write one user prompt fixture.

        Args:
            relative_path: Path below the user prompt root.
            body: Markdown prompt body.
        """

        prompt_path = self.prompt_root.joinpath(*relative_path.split("/"))
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(body, encoding="utf-8")

    def test_portable_prompt_name_rules(self):
        valid_names = (
            "Prompt",
            "Mixed_Case",
            "interview-Analysis_2026",
            "Überraschende_Fälle",
            "Résumé_2026",
            "Análisis-cualitativo",
            "Straße",
            "A" * 64,
        )
        invalid_names = (
            "_Prompt",
            "-Prompt",
            "Prompt Name",
            "Prompt!",
            "Prompt🙂",
            "\u0301Accent",
            "A" * 65,
            "\U00010400" * 64,
            "CON",
            "nul",
            "Com1",
            "LPT9",
        )

        for name in valid_names:
            with self.subTest(name=name):
                self.assertTrue(is_valid_prompt_name(name))
        for name in invalid_names:
            with self.subTest(name=name):
                self.assertFalse(is_valid_prompt_name(name))

    def test_windows_reserved_names_are_case_insensitive(self):
        for name in ("CON", "con", "NuL", "COM1", "lpt1"):
            with self.subTest(name=name):
                self.assertTrue(is_windows_reserved_prompt_name(name))
        self.assertFalse(is_windows_reserved_prompt_name("CON_prompt"))

    def test_portable_prompt_folder_name_rules(self):
        valid_names = ("Research", "Überraschende_Fälle", "Résumé-2026", "Straße")
        invalid_names = ("_Research", "Research Notes", "Research!", "CON", "A" * 65)

        for name in valid_names:
            with self.subTest(name=name):
                self.assertTrue(is_valid_prompt_folder_name(name))
        for name in invalid_names:
            with self.subTest(name=name):
                self.assertFalse(is_valid_prompt_folder_name(name))

        self.assertTrue(prompt_folder_name_fits_filesystem("Ü" * 64))
        self.assertFalse(prompt_folder_name_fits_filesystem("\U00010400" * 64))

    def test_unicode_normalization_and_casefold_keys(self):
        decomposed_name = "Re\u0301sume\u0301"

        self.assertEqual("Résumé", normalize_prompt_name_component(decomposed_name))
        self.assertEqual(prompt_name_key("Résumé"), prompt_name_key(decomposed_name))
        self.assertEqual(prompt_name_key("Straße"), prompt_name_key("STRASSE"))
        self.assertEqual(
            "Résumé/Überblick",
            self.catalog.normalize_relative_dir("Re\u0301sume\u0301/U\u0308berblick"),
        )

    def test_utf8_filename_byte_limit_includes_markdown_extension(self):
        self.assertTrue(prompt_name_fits_filesystem("Ü" * 64))
        self.assertFalse(prompt_name_fits_filesystem("\U00010400" * 64))

    def test_prompt_lookup_is_case_insensitive_and_preserves_name(self):
        self._write_prompt("Mixed_Case.md")

        prompt = self.catalog.get_prompt("mixed_case")
        variant = self.catalog.find_prompt_variant("MIXED_CASE", "user")

        self.assertIsNotNone(prompt)
        self.assertIsNotNone(variant)
        self.assertEqual("Mixed_Case", prompt.name)
        self.assertEqual("Mixed_Case", variant.name)

    def test_readiness_prompt_points_to_labelled_project_memo_section(self):
        prompt = self.catalog.get_prompt("Check-project-AI-readiness")

        self.assertIsNotNone(prompt)
        self.assertIn(
            "Review the section explicitly labelled `# Project memo` in your system context.",
            prompt.content,
        )

    def test_slash_reference_resolution_is_case_insensitive(self):
        self._write_prompt("Überblick/Résumé_Analysis.md")

        prompts = self.catalog.resolve_prompt_references(
            "Apply /u\u0308BERBLICK/re\u0301sume\u0301_analysis and "
            "/ÜBERBLICK/RÉSUMÉ_ANALYSIS to this material."
        )

        self.assertEqual(["Überblick/Résumé_Analysis"], [prompt.name for prompt in prompts])

    def test_legacy_slug_preserves_portable_unicode_and_case(self):
        self.assertEqual(
            "Überraschende-Fälle_2026",
            self.catalog._slugify_prompt_filename("Überraschende Fälle_2026"),
        )
        self.assertEqual("My_Prompt", self.catalog._slugify_prompt_filename("My_Prompt"))
        self.assertEqual("CON-prompt", self.catalog._slugify_prompt_filename("CON"))

    def test_case_only_scope_override_uses_higher_priority_prompt(self):
        self._write_prompt("code-analysis/Code-Summary.md", "User override")

        prompt = self.catalog.get_prompt("code-analysis/code-summary")

        self.assertIsNotNone(prompt)
        self.assertEqual("user", prompt.scope)
        self.assertEqual("code-analysis/Code-Summary", prompt.name)
        self.assertTrue(prompt.content.endswith("User override"))
