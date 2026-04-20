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
