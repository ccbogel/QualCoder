import os
import tempfile
from types import SimpleNamespace
from unittest import TestCase

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
