# -*- coding: utf-8 -*-

"""
Agent prompt discovery for QualCoder AI chats.

Prompts are stored as flat Markdown files in three scopes:
- system: src/qualcoder/ai_prompts
- user:   <confighome>/ai_prompts
- project:<project>/ai_data/ai_prompts

Conflicts are resolved by scope priority: project > user > system.
Files beginning with "_" are treated as internal prompts and are not available
through explicit user prompt references.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
from typing import Dict, List, Optional, Tuple


PROMPT_REFERENCE_PATTERN = re.compile(r"(?<!\S)/(\S+)")
logger = logging.getLogger(__name__)


@dataclass
class AgentPromptRecord:
    scope: str
    root_path: str
    name: str
    file_path: str
    content: str
    description: str
    is_internal: bool


class AiAgentPromptsCatalog:
    """Discover and resolve QualCoder agent prompts across scopes."""

    _scope_priority = {
        "system": 0,
        "user": 1,
        "project": 2,
    }

    def __init__(self, app):
        self.app = app
        self._system_root = os.path.join(os.path.dirname(__file__), "ai_prompts")

    def list_prompts(self, include_internal: bool = False) -> List[AgentPromptRecord]:
        """Return resolved prompt files with scope override handling."""

        selected: Dict[str, AgentPromptRecord] = {}
        for scope, root in self._prompt_roots():
            for prompt in self._discover_scope(scope, root):
                conflict_key = self._conflict_key(prompt.name)
                prev = selected.get(conflict_key)
                if prev is None:
                    selected[conflict_key] = prompt
                    continue
                prev_rank = self._scope_priority.get(prev.scope, -1)
                new_rank = self._scope_priority.get(prompt.scope, -1)
                if new_rank > prev_rank:
                    selected[conflict_key] = prompt

        prompts = list(selected.values())
        prompts.sort(key=lambda item: item.name.casefold())
        if include_internal:
            return prompts
        return [item for item in prompts if not item.is_internal]

    def get_prompt(self, name: str) -> Optional[AgentPromptRecord]:
        """Resolve one explicit user-callable prompt by exact filename match."""

        query = str(name if name is not None else "").strip()
        if query == "":
            return None
        for prompt in self.list_prompts(include_internal=False):
            if prompt.name == query:
                return prompt
        return None

    def get_internal_prompt(self, name: str) -> Optional[AgentPromptRecord]:
        """Resolve one internal prompt by exact filename match."""

        query = str(name if name is not None else "").strip()
        if query == "":
            return None
        for prompt in self.list_prompts(include_internal=True):
            if prompt.is_internal and prompt.name == query:
                return prompt
        return None

    def extract_prompt_references(self, text: str) -> List[AgentPromptRecord]:
        """Return prompts referenced via exact `/name` tokens in one chat message."""

        resolved: List[AgentPromptRecord] = []
        for candidate in self._extract_prompt_names(text):
            prompt = self.get_prompt(candidate)
            if prompt is None:
                continue
            resolved.append(prompt)
        return resolved

    def resolve_prompt_references(self, text: str) -> List[AgentPromptRecord]:
        """Return direct and nested prompt references with stable de-duplicated ordering."""

        return self.expand_prompt_references(self.extract_prompt_references(text))

    def expand_prompt_references(self, prompts: List[AgentPromptRecord]) -> List[AgentPromptRecord]:
        """Expand nested prompt references so each resolved prompt appears at most once."""

        ordered: List[AgentPromptRecord] = []
        resolved: set[str] = set()
        visiting: set[str] = set()

        def visit(prompt: AgentPromptRecord) -> None:
            key = self._conflict_key(prompt.name)
            if key == "" or key in resolved:
                return
            if key in visiting:
                logger.warning("Detected cyclic AI prompt reference involving '/%s'", prompt.name)
                return

            visiting.add(key)
            for nested_prompt in self.extract_prompt_references(prompt.content):
                visit(nested_prompt)
            visiting.remove(key)

            resolved.add(key)
            ordered.append(prompt)

        for prompt in prompts:
            visit(prompt)

        return ordered

    def _prompt_roots(self) -> List[Tuple[str, str]]:
        roots: List[Tuple[str, str]] = []
        roots.append(("system", self._system_root))

        confighome = ""
        if hasattr(self.app, "confighome"):
            confighome = str(getattr(self.app, "confighome", "")).strip()
        if confighome != "":
            roots.append(("user", os.path.join(confighome, "ai_prompts")))

        project_path = ""
        if hasattr(self.app, "project_path"):
            project_path = str(getattr(self.app, "project_path", "")).strip()
        if project_path != "":
            roots.append(("project", os.path.join(project_path, "ai_data", "ai_prompts")))
        return roots

    def _discover_scope(self, scope: str, root: str) -> List[AgentPromptRecord]:
        if root is None or str(root).strip() == "" or not os.path.isdir(root):
            return []

        result: List[AgentPromptRecord] = []
        try:
            filenames = sorted(os.listdir(root), key=lambda item: item.casefold())
        except OSError:
            return []

        for filename in filenames:
            if not filename.lower().endswith(".md"):
                continue
            path = os.path.join(root, filename)
            if not os.path.isfile(path):
                continue
            raw = self._read_text(path)
            if raw is None:
                continue
            name = filename[:-3]
            content = raw.strip()
            result.append(
                AgentPromptRecord(
                    scope=scope,
                    root_path=root,
                    name=name,
                    file_path=path,
                    content=content,
                    description=self._infer_description(content),
                    is_internal=name.startswith("_"),
                )
            )
        return result

    def _conflict_key(self, name: str) -> str:
        return str(name if name is not None else "").strip().casefold()

    def _read_text(self, path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                return handle.read()
        except OSError:
            return None

    def _extract_prompt_names(self, text: str) -> List[str]:
        source_text = str(text if text is not None else "")
        if source_text.strip() == "":
            return []

        seen: set[str] = set()
        result: List[str] = []
        for match in PROMPT_REFERENCE_PATTERN.finditer(source_text):
            candidate = str(match.group(1) if match is not None else "").strip()
            if candidate == "" or candidate.startswith("_"):
                continue
            conflict_key = self._conflict_key(candidate)
            if conflict_key == "" or conflict_key in seen:
                continue
            seen.add(conflict_key)
            result.append(candidate)
        return result

    def _infer_description(self, body: str) -> str:
        text = str(body if body is not None else "")
        lines = [line.strip() for line in text.splitlines()]
        paragraph: List[str] = []
        in_paragraph = False
        for line in lines:
            if line == "":
                if in_paragraph:
                    break
                continue
            paragraph.append(line)
            in_paragraph = True
        if len(paragraph) == 0:
            return ""
        desc = " ".join(paragraph).strip()
        if len(desc) > 240:
            desc = desc[:237].rstrip() + "..."
        return desc
