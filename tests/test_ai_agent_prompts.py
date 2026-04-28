import os
import tempfile
from types import SimpleNamespace
from unittest import TestCase
import yaml

from qualcoder.ai_agent_prompts import AiAgentPromptsCatalog


class TestAiAgentPromptsCatalog(TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.system_root = os.path.join(self.temp_dir.name, "system_prompts")
        self.user_root = os.path.join(self.temp_dir.name, "user_home", "ai_prompts")
        self.project_root = os.path.join(self.temp_dir.name, "project", "ai_data", "ai_prompts")
        os.makedirs(self.system_root, exist_ok=True)
        os.makedirs(self.user_root, exist_ok=True)
        os.makedirs(self.project_root, exist_ok=True)

        self.app = SimpleNamespace(
            confighome=os.path.join(self.temp_dir.name, "user_home"),
            project_path=os.path.join(self.temp_dir.name, "project"),
        )
        self.catalog = AiAgentPromptsCatalog(self.app)
        self.catalog._system_root = self.system_root

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_prompt(self, scope: str, name: str, content: str) -> None:
        roots = {
            "system": self.system_root,
            "user": self.user_root,
            "project": self.project_root,
        }
        path = os.path.join(roots[scope], name + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def _write_legacy_prompts(self, scope: str, prompts: list[dict]) -> None:
        paths = {
            "user": os.path.join(self.temp_dir.name, "user_home", "ai_prompts.yaml"),
            "project": os.path.join(self.temp_dir.name, "project", "ai_data", "ai_prompts.yaml"),
        }
        path = paths[scope]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(prompts, handle, allow_unicode=True, sort_keys=False)

    def test_resolve_prompt_references_expands_nested_prompts_once(self):
        self._write_prompt("system", "a", "/b\nAlpha")
        self._write_prompt("system", "b", "Notes before /c\n/c\nBeta")
        self._write_prompt("system", "c", "Gamma")

        prompts = self.catalog.resolve_prompt_references("Please use /a and /c and /a again.")

        self.assertEqual(["c", "b", "a"], [prompt.name for prompt in prompts])

    def test_resolve_prompt_references_handles_cycles_without_duplicates(self):
        self._write_prompt("system", "a", "/b\nAlpha")
        self._write_prompt("system", "b", "/a\nBeta")

        prompts = self.catalog.resolve_prompt_references("/a")

        self.assertEqual(["b", "a"], [prompt.name for prompt in prompts])

    def test_resolve_prompt_references_can_include_internal_prompts_when_enabled(self):
        self._write_prompt("system", "_agent", "/_shared\n/base\nAgent")
        self._write_prompt("system", "_shared", "Internal")
        self._write_prompt("system", "base", "Public")

        prompts = self.catalog.resolve_prompt_references("/_agent", include_internal=True)

        self.assertEqual(["_shared", "base", "_agent"], [prompt.name for prompt in prompts])

    def test_resolve_prompt_references_excludes_internal_prompts_by_default(self):
        self._write_prompt("system", "_shared", "Internal")

        prompts = self.catalog.resolve_prompt_references("/_shared")

        self.assertEqual([], prompts)

    def test_list_prompts_discovers_nested_prompt_paths(self):
        self._write_prompt("system", "code-analysis/code-critic", "Critic")
        self._write_prompt("system", "text-analysis/open-coding", "Open coding")

        prompts = self.catalog.list_prompts()

        self.assertEqual(
            ["code-analysis/code-critic", "text-analysis/open-coding"],
            [prompt.name for prompt in prompts],
        )

    def test_scope_override_uses_full_relative_prompt_path(self):
        self._write_prompt("system", "code-analysis/review", "System review")
        self._write_prompt("user", "code-analysis/review", "User review")
        self._write_prompt("system", "topic-exploration/review", "Topic review")

        prompts = self.catalog.list_prompts()

        self.assertEqual(
            {
                "code-analysis/review": ("user", "User review"),
                "topic-exploration/review": ("system", "Topic review"),
            },
            {prompt.name: (prompt.scope, prompt.content) for prompt in prompts},
        )

    def test_resolve_prompt_references_with_nested_names(self):
        self._write_prompt("system", "code-analysis/code-critic", "Critic")
        self._write_prompt("system", "code-analysis/code-comparison", "/code-analysis/code-critic\nCompare")

        prompts = self.catalog.resolve_prompt_references("/code-analysis/code-comparison")

        self.assertEqual(
            ["code-analysis/code-critic", "code-analysis/code-comparison"],
            [prompt.name for prompt in prompts],
        )

    def test_nested_prompt_content_includes_same_folder_init(self):
        self._write_prompt("system", "code-analysis/_init", "Shared context")
        self._write_prompt("system", "code-analysis/code-critic", "Prompt body")

        prompt = self.catalog.get_prompt("code-analysis/code-critic")

        self.assertIsNotNone(prompt)
        self.assertEqual("Shared context\n\nPrompt body", prompt.content)

    def test_nested_prompt_init_references_are_resolved_recursively(self):
        self._write_prompt("system", "shared/base", "Base prompt")
        self._write_prompt("system", "code-analysis/_init", "/shared/base\nShared context")
        self._write_prompt("system", "code-analysis/code-critic", "Prompt body")

        prompts = self.catalog.resolve_prompt_references("/code-analysis/code-critic")

        self.assertEqual(
            ["shared/base", "code-analysis/code-critic"],
            [prompt.name for prompt in prompts],
        )

    def test_user_prompt_uses_system_init_when_local_init_is_missing(self):
        self._write_prompt("system", "code-analysis/_init", "System shared context")
        self._write_prompt("user", "code-analysis/code-critic", "User prompt body")

        prompt = self.catalog.get_prompt("code-analysis/code-critic")

        self.assertIsNotNone(prompt)
        self.assertEqual("user", prompt.scope)
        self.assertEqual("System shared context\n\nUser prompt body", prompt.content)

    def test_project_prompt_prefers_local_init_over_system_init(self):
        self._write_prompt("system", "code-analysis/_init", "System shared context")
        self._write_prompt("project", "code-analysis/_init", "Project shared context")
        self._write_prompt("project", "code-analysis/code-critic", "Project prompt body")

        prompt = self.catalog.get_prompt("code-analysis/code-critic")

        self.assertIsNotNone(prompt)
        self.assertEqual("project", prompt.scope)
        self.assertEqual("Project shared context\n\nProject prompt body", prompt.content)

    def test_prompt_frontmatter_is_not_included_in_loaded_content(self):
        self._write_prompt(
            "system",
            "text-analysis/frontmatter-test",
            "---\nname: frontmatter-test\ndescription: Frontmatter description\n---\nPrompt body",
        )

        prompt = self.catalog.get_prompt("text-analysis/frontmatter-test")

        self.assertIsNotNone(prompt)
        self.assertEqual("Frontmatter description", prompt.description)
        self.assertEqual("Prompt body", prompt.content)

    def test_empty_frontmatter_description_overrides_inferred_description(self):
        self._write_prompt(
            "system",
            "text-analysis/frontmatter-empty-description",
            "---\nname: frontmatter-empty-description\ndescription: \"\"\n---\nPrompt body",
        )

        prompt = self.catalog.get_prompt("text-analysis/frontmatter-empty-description")

        self.assertIsNotNone(prompt)
        self.assertEqual("", prompt.description)
        self.assertEqual("Prompt body", prompt.content)

    def test_list_prompt_variants_can_ignore_init_content(self):
        self._write_prompt("system", "_search/_init", "Search init")
        self._write_prompt("system", "_search/focused-search", "Search body")

        with_init = self.catalog.find_prompt_variant(
            "_search/focused-search",
            "system",
            prompt_type="search",
            include_internal=True,
            apply_init=True,
        )
        without_init = self.catalog.find_prompt_variant(
            "_search/focused-search",
            "system",
            prompt_type="search",
            include_internal=True,
            apply_init=False,
        )

        self.assertIsNotNone(with_init)
        self.assertIsNotNone(without_init)
        self.assertEqual("Search init\n\nSearch body", with_init.content)
        self.assertEqual("Search body", without_init.content)

    def test_find_prompt_variant_filters_by_type_and_scope(self):
        self._write_prompt("system", "_search/focused-search", "System search")
        self._write_prompt("user", "_search/focused-search", "User search")

        prompt = self.catalog.find_prompt_variant("_search/focused-search", "user", prompt_type="search", include_internal=True, apply_init=False)

        self.assertIsNotNone(prompt)
        self.assertEqual("user", prompt.scope)
        self.assertEqual("User search", prompt.content)

    def test_internal_prompt_folder_is_hidden_from_public_prompt_list(self):
        self._write_prompt("system", "_search/focused-search", "Internal search")

        public_prompts = self.catalog.list_prompts()
        internal_prompts = self.catalog.list_prompts(include_internal=True)

        self.assertEqual([], public_prompts)
        self.assertEqual(["_search/focused-search"], [prompt.name for prompt in internal_prompts])

    def test_migrate_legacy_user_prompts_creates_markdown_files(self):
        self._write_legacy_prompts(
            "user",
            [
                {
                    "name": "Custom Code Prompt",
                    "type": "code_analysis",
                    "description": "Custom description",
                    "text": "Custom body",
                },
                {
                    "name": "Migrated Search Prompt",
                    "type": "search",
                    "description": "Search description",
                    "text": "Search body",
                },
            ],
        )

        result = self.catalog.migrate_legacy_prompts_once()

        self.assertEqual({"migrated": 2, "skipped": 0}, result["user"])
        code_path = os.path.join(self.user_root, "code-analysis", "custom-code-prompt.md")
        self.assertTrue(os.path.exists(code_path))
        with open(code_path, "r", encoding="utf-8") as handle:
            migrated_text = handle.read()
        self.assertIn("name: custom-code-prompt", migrated_text)
        self.assertIn("description: Custom description", migrated_text)
        self.assertTrue(migrated_text.rstrip().endswith("Custom body"))
        search_path = os.path.join(self.user_root, "_search", "migrated-search-prompt.md")
        self.assertTrue(os.path.exists(search_path))

    def test_migrate_legacy_search_prompts_creates_search_markdown_files(self):
        self._write_legacy_prompts(
            "user",
            [
                {
                    "name": "Focused Search Custom",
                    "type": "search",
                    "description": "Search description",
                    "text": "Search body",
                },
            ],
        )

        result = self.catalog.migrate_legacy_prompts_once()

        self.assertEqual({"migrated": 1, "skipped": 0}, result["user"])
        migrated_path = os.path.join(self.user_root, "_search", "focused-search-custom.md")
        self.assertTrue(os.path.exists(migrated_path))

    def test_migrate_legacy_project_prompts_skips_existing_target_file(self):
        self._write_prompt("project", "text-analysis/existing-prompt", "Already there")
        self._write_legacy_prompts(
            "project",
            [
                {
                    "name": "Existing Prompt",
                    "type": "text_analysis",
                    "description": "Should skip",
                    "text": "Legacy body",
                }
            ],
        )

        result = self.catalog.migrate_legacy_prompts_once()

        self.assertEqual({"migrated": 0, "skipped": 1}, result["project"])
        migrated_path = os.path.join(self.project_root, "text-analysis", "existing-prompt.md")
        with open(migrated_path, "r", encoding="utf-8") as handle:
            self.assertEqual("Already there", handle.read())

    def test_migrate_legacy_prompts_resolves_slug_collisions_with_suffixes(self):
        self._write_legacy_prompts(
            "user",
            [
                {
                    "name": "Foo Bar",
                    "type": "text_analysis",
                    "description": "First",
                    "text": "Body one",
                },
                {
                    "name": "Foo/Bar",
                    "type": "text_analysis",
                    "description": "Second",
                    "text": "Body two",
                },
            ],
        )

        result = self.catalog.migrate_legacy_prompts_once()

        self.assertEqual({"migrated": 2, "skipped": 0}, result["user"])
        first_path = os.path.join(self.user_root, "text-analysis", "foo-bar.md")
        second_path = os.path.join(self.user_root, "text-analysis", "foo-bar-2.md")
        self.assertTrue(os.path.exists(first_path))
        self.assertTrue(os.path.exists(second_path))

    def test_migrate_legacy_prompts_runs_only_once_per_scope(self):
        self._write_legacy_prompts(
            "user",
            [
                {
                    "name": "One Time Prompt",
                    "type": "text_analysis",
                    "description": "Once",
                    "text": "Only once",
                },
            ],
        )

        first_result = self.catalog.migrate_legacy_prompts_once()
        second_result = self.catalog.migrate_legacy_prompts_once()

        self.assertEqual({"migrated": 1, "skipped": 0}, first_result["user"])
        self.assertEqual({"migrated": 0, "skipped": 1}, second_result["user"])
