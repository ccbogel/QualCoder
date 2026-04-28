# -*- coding: utf-8 -*-

"""
Agent prompt discovery for QualCoder AI chats.

Prompts are stored as Markdown files in three scopes:
- system: src/qualcoder/ai_prompts
- user:   <confighome>/ai_prompts
- project:<project>/ai_data/ai_prompts

Prompt names are their relative paths without the ``.md`` suffix, normalized to
use forward slashes. For example ``code-analysis/code-critic.md`` becomes the
explicit prompt reference ``/code-analysis/code-critic``.

Conflicts are resolved by scope priority: project > user > system.
Prompt files below path segments beginning with "_" are treated as internal
prompts and are not available through explicit user prompt references.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import unicodedata
import yaml


PROMPT_REFERENCE_PATTERN = re.compile(r"(?<!\S)/(\S+)")
PROMPT_FRONTMATTER_PATTERN = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
LEGACY_PROMPT_TYPE_FOLDERS = {
    "search": "_search",
    "code_analysis": "code-analysis",
    "topic_analysis": "topic-exploration",
    "text_analysis": "text-analysis",
}
WINDOWS_RESERVED_FILENAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}
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


def prompt_name_and_scope(prompt: AgentPromptRecord) -> str:
    """Return one stable display label for a prompt record."""

    name = str(getattr(prompt, "name", "") if prompt is not None else "").strip()
    scope = str(getattr(prompt, "scope", "") if prompt is not None else "").strip()
    if scope == "":
        return name
    return name + f" ({scope})"


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

    def list_prompt_variants(
        self,
        prompt_type: Optional[str] = None,
        include_internal: bool = False,
        apply_init: bool = True,
    ) -> List[AgentPromptRecord]:
        """Return all prompts across scopes without conflict deduplication."""

        prompts: List[AgentPromptRecord] = []
        for scope, root in self._prompt_roots():
            prompts.extend(
                self._discover_scope(
                    scope,
                    root,
                    apply_init=apply_init,
                    prompt_type=prompt_type,
                )
            )
        prompts.sort(key=lambda item: (self._scope_priority.get(item.scope, 99), item.name.casefold()))
        if include_internal:
            return prompts
        return [item for item in prompts if not item.is_internal]

    def find_prompt_variant(
        self,
        name: str,
        scope: str,
        prompt_type: Optional[str] = None,
        include_internal: bool = False,
        apply_init: bool = True,
    ) -> Optional[AgentPromptRecord]:
        """Find one prompt variant by exact name and scope without deduplicating scopes."""

        query_name = self._normalize_prompt_name(name)
        query_scope = str(scope if scope is not None else "").strip()
        if query_name == "" or query_scope == "":
            return None
        for prompt in self.list_prompt_variants(
            prompt_type=prompt_type,
            include_internal=include_internal,
            apply_init=apply_init,
        ):
            if prompt.name == query_name and prompt.scope == query_scope:
                return prompt
        return None

    def get_prompt(self, name: str, include_internal: bool = False) -> Optional[AgentPromptRecord]:
        """Resolve one explicit user-callable prompt by exact filename match."""

        query = self._normalize_prompt_name(name)
        if query == "":
            return None
        for prompt in self.list_prompts(include_internal=include_internal):
            if prompt.name == query:
                return prompt
        return None

    def get_internal_prompt(self, name: str) -> Optional[AgentPromptRecord]:
        """Resolve one internal prompt by exact filename match."""

        query = self._normalize_prompt_name(name)
        if query == "":
            return None
        for prompt in self.list_prompts(include_internal=True):
            if prompt.is_internal and prompt.name == query:
                return prompt
        return None

    def extract_prompt_references(self, text: str, include_internal: bool = False) -> List[AgentPromptRecord]:
        """Return prompts referenced via exact `/name` tokens in one chat message."""

        resolved: List[AgentPromptRecord] = []
        for candidate in self._extract_prompt_names(text, include_internal=include_internal):
            prompt = self.get_prompt(candidate, include_internal=include_internal)
            if prompt is None:
                continue
            resolved.append(prompt)
        return resolved

    def resolve_prompt_references(self, text: str, include_internal: bool = False) -> List[AgentPromptRecord]:
        """Return direct and nested prompt references with stable de-duplicated ordering."""

        return self.expand_prompt_references(
            self.extract_prompt_references(text, include_internal=include_internal),
            include_internal=include_internal,
        )

    def expand_prompt_references(
        self,
        prompts: List[AgentPromptRecord],
        include_internal: bool = False,
    ) -> List[AgentPromptRecord]:
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
            for nested_prompt in self.extract_prompt_references(prompt.content, include_internal=include_internal):
                visit(nested_prompt)
            visiting.remove(key)

            resolved.add(key)
            ordered.append(prompt)

        for prompt in prompts:
            visit(prompt)

        return ordered

    def migrate_legacy_prompts_once(self) -> Dict[str, Dict[str, int]]:
        """Import legacy YAML prompts for user and project scopes into Markdown files."""

        results: Dict[str, Dict[str, int]] = {}

        confighome = str(getattr(self.app, "confighome", "") if hasattr(self.app, "confighome") else "").strip()
        if confighome != "":
            results["user"] = self._migrate_legacy_prompt_scope(
                legacy_yaml_path=os.path.join(confighome, "ai_prompts.yaml"),
                markdown_root=os.path.join(confighome, "ai_prompts"),
            )

        project_path = str(getattr(self.app, "project_path", "") if hasattr(self.app, "project_path") else "").strip()
        if project_path != "":
            results["project"] = self._migrate_legacy_prompt_scope(
                legacy_yaml_path=os.path.join(project_path, "ai_data", "ai_prompts.yaml"),
                markdown_root=os.path.join(project_path, "ai_data", "ai_prompts"),
            )

        return results

    def _migrate_legacy_prompt_scope(self, legacy_yaml_path: str, markdown_root: str) -> Dict[str, int]:
        """One-time import of legacy YAML prompts into the new Markdown folder layout."""

        result = {"migrated": 0, "skipped": 0}
        raw_legacy_yaml = self._read_text(legacy_yaml_path)
        if raw_legacy_yaml is None or raw_legacy_yaml.strip() == "":
            return result

        legacy_prompts = self._load_legacy_prompts_from_yaml(raw_legacy_yaml, legacy_yaml_path)
        if legacy_prompts is None or len(legacy_prompts) == 0:
            return result

        existing_paths = self._collect_existing_markdown_paths(markdown_root)
        planned_targets = self._plan_legacy_prompt_targets(legacy_prompts, markdown_root)

        for prompt, target_path in planned_targets:
            normalized_desired_path = os.path.normcase(os.path.normpath(target_path))
            if normalized_desired_path in existing_paths:
                result["skipped"] += 1
                continue

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            markdown_text = self._build_prompt_markdown_document(
                self._slug_from_prompt_path(target_path),
                str(prompt.get("description", "") if isinstance(prompt, dict) else ""),
                str(prompt.get("text", "") if isinstance(prompt, dict) else ""),
            )
            with open(target_path, "w", encoding="utf-8") as handle:
                handle.write(markdown_text)
            existing_paths.add(normalized_desired_path)
            result["migrated"] += 1

        return result

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

    def _discover_scope(
        self,
        scope: str,
        root: str,
        apply_init: bool = True,
        prompt_type: Optional[str] = None,
    ) -> List[AgentPromptRecord]:
        if root is None or str(root).strip() == "" or not os.path.isdir(root):
            return []

        result: List[AgentPromptRecord] = []
        try:
            entries = list(os.walk(root))
        except OSError:
            return []

        entries.sort(key=lambda item: os.path.relpath(item[0], root).casefold())
        for dirpath, dirnames, filenames in entries:
            dirnames.sort(key=lambda item: item.casefold())
            filenames.sort(key=lambda item: item.casefold())
            init_content = self._read_directory_init_content(scope, root, dirpath) if apply_init else ""
            for filename in filenames:
                if not filename.lower().endswith(".md"):
                    continue
                path = os.path.join(dirpath, filename)
                if not os.path.isfile(path):
                    continue
                raw = self._read_text(path)
                if raw is None:
                    continue
                rel_path = os.path.relpath(path, root)
                name = self._normalize_prompt_name(rel_path[:-3])
                if name == "":
                    continue
                current_prompt_type = self._prompt_type_from_name(name)
                if prompt_type is not None and current_prompt_type != str(prompt_type).strip():
                    continue
                metadata, prompt_body = self._split_frontmatter(raw)
                content = self._compose_prompt_content(name, prompt_body, init_content)
                has_frontmatter_description = isinstance(metadata, dict) and "description" in metadata
                description = str(metadata.get("description", "") if has_frontmatter_description else "").strip()
                if description == "" and not has_frontmatter_description:
                    description = self._infer_description(prompt_body)
                result.append(
                    AgentPromptRecord(
                        scope=scope,
                        root_path=root,
                        name=name,
                        file_path=path,
                        content=content,
                        description=description,
                        is_internal=self._is_internal_prompt_name(name),
                    )
                )
        return result

    def _read_directory_init_content(self, scope: str, root: str, dirpath: str) -> str:
        """Return one subdirectory's `_init.md` content with system fallback for overrides."""

        if root is None or dirpath is None or os.path.normpath(dirpath) == os.path.normpath(root):
            return ""
        rel_dir = os.path.relpath(dirpath, root)
        init_path = os.path.join(dirpath, "_init.md")
        raw = self._read_text(init_path)
        if raw is not None:
            return self._split_frontmatter(raw)[1]
        if scope == "system":
            return ""
        system_init_path = os.path.join(self._system_root, rel_dir, "_init.md")
        system_raw = self._read_text(system_init_path)
        if system_raw is None:
            return ""
        return self._split_frontmatter(system_raw)[1]

    def _compose_prompt_content(self, name: str, body: str, init_content: str) -> str:
        """Prepend one subdirectory `_init.md` body to prompts in that same folder."""

        prompt_body = str(body if body is not None else "").strip()
        if self._normalize_prompt_name(name).rsplit("/", 1)[-1] == "_init":
            return prompt_body
        folder_init = str(init_content if init_content is not None else "").strip()
        if folder_init == "":
            return prompt_body
        if prompt_body == "":
            return folder_init
        return folder_init + "\n\n" + prompt_body

    def _prompt_type_from_name(self, name: str) -> Optional[str]:
        """Infer one prompt type from the top-level prompt directory."""

        normalized_name = self._normalize_prompt_name(name)
        if normalized_name == "" or "/" not in normalized_name:
            return None
        top_level = normalized_name.split("/", 1)[0]
        if top_level == "_search":
            return "search"
        if top_level == "code-analysis":
            return "code_analysis"
        if top_level == "topic-exploration":
            return "topic_analysis"
        if top_level == "text-analysis":
            return "text_analysis"
        return None

    def _conflict_key(self, name: str) -> str:
        return self._normalize_prompt_name(name).casefold()

    def _normalize_prompt_name(self, name: str) -> str:
        text = str(name if name is not None else "").strip()
        if text == "":
            return ""
        parts = re.split(r"[\\/]+", text)
        return "/".join(part for part in parts if part != "")

    def _is_internal_prompt_name(self, name: str) -> bool:
        normalized_name = self._normalize_prompt_name(name)
        if normalized_name == "":
            return False
        return any(part.startswith("_") for part in normalized_name.split("/"))

    def _read_text(self, path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                return handle.read()
        except OSError:
            return None

    def _load_legacy_prompts_from_yaml(self, raw_text: str, source_path: str) -> Optional[List[Dict[str, Any]]]:
        """Parse one legacy ai_prompts.yaml payload and return prompt dictionaries."""

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError:
            logger.warning("Could not parse legacy AI prompts YAML: %s", source_path)
            return None
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _collect_existing_markdown_paths(self, root: str) -> set[str]:
        """Return normalized paths of all existing Markdown files below one prompt root."""

        result: set[str] = set()
        if root is None or str(root).strip() == "" or not os.path.isdir(root):
            return result
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not filename.lower().endswith(".md"):
                    continue
                result.add(os.path.normcase(os.path.normpath(os.path.join(dirpath, filename))))
        return result

    def _slugify_prompt_filename(self, name: str, max_length: int = 64) -> str:
        """Convert one prompt name into a portable lowercase filename slug."""

        text = unicodedata.normalize("NFKD", str(name if name is not None else ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        text = re.sub(r"-{2,}", "-", text).strip("-")
        if text == "":
            text = "prompt"
        text = text[:max_length].rstrip("-")
        if text == "":
            text = "prompt"
        if text in WINDOWS_RESERVED_FILENAMES:
            suffix = "-prompt"
            text = text[:max(1, max_length - len(suffix))].rstrip("-") + suffix
        return text

    def _plan_legacy_prompt_targets(
        self,
        legacy_prompts: List[Dict[str, Any]],
        markdown_root: str,
    ) -> List[Tuple[Dict[str, Any], str]]:
        """Plan deterministic target paths for all migratable legacy prompts in one scope."""

        planned: List[Tuple[Dict[str, Any], str]] = []
        used_paths: set[str] = set()

        for prompt in legacy_prompts:
            prompt_type = str(prompt.get("type", "") if isinstance(prompt, dict) else "").strip()
            target_folder = LEGACY_PROMPT_TYPE_FOLDERS.get(prompt_type, "")
            if target_folder == "":
                continue

            prompt_name = str(prompt.get("name", "") if isinstance(prompt, dict) else "").strip()
            base_slug = self._slugify_prompt_filename(prompt_name)
            target_dir = os.path.join(markdown_root, target_folder)
            candidate_slug = base_slug
            counter = 2

            while True:
                candidate_path = os.path.join(target_dir, candidate_slug + ".md")
                normalized_candidate = os.path.normcase(os.path.normpath(candidate_path))
                if normalized_candidate not in used_paths:
                    used_paths.add(normalized_candidate)
                    planned.append((prompt, candidate_path))
                    break
                suffix = f"-{counter}"
                candidate_slug = self._slugify_prompt_filename(base_slug, max_length=max(8, 64 - len(suffix))) + suffix
                counter += 1

        return planned

    def _slug_from_prompt_path(self, path: str) -> str:
        """Return one prompt slug from a file path."""

        basename = os.path.basename(str(path if path is not None else ""))
        if basename.lower().endswith(".md"):
            basename = basename[:-3]
        return basename

    def _build_prompt_markdown_document(self, slug: str, description: str, text: str) -> str:
        """Build one Markdown prompt file with YAML frontmatter."""

        frontmatter = yaml.safe_dump(
            {
                "name": str(slug if slug is not None else "").strip(),
                "description": str(description if description is not None else "").strip(),
            },
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).strip()
        body = str(text if text is not None else "").strip()
        if body == "":
            return "---\n" + frontmatter + "\n---\n"
        return "---\n" + frontmatter + "\n---\n\n" + body + "\n"

    def _split_frontmatter(self, text: str) -> Tuple[Dict[str, str], str]:
        """Return frontmatter metadata and Markdown body without the frontmatter block."""

        raw_text = str(text if text is not None else "")
        match = PROMPT_FRONTMATTER_PATTERN.match(raw_text)
        if match is None:
            return {}, raw_text.strip()

        metadata_text = str(match.group(1) if match.group(1) is not None else "")
        try:
            metadata = yaml.safe_load(metadata_text)
        except yaml.YAMLError:
            logger.warning("Invalid YAML frontmatter in AI prompt file; using raw body.")
            return {}, raw_text.strip()

        if not isinstance(metadata, dict):
            metadata = {}
        body = raw_text[match.end():].strip()
        return metadata, body

    def _extract_prompt_names(self, text: str, include_internal: bool = False) -> List[str]:
        source_text = str(text if text is not None else "")
        if source_text.strip() == "":
            return []

        seen: set[str] = set()
        result: List[str] = []
        for match in PROMPT_REFERENCE_PATTERN.finditer(source_text):
            candidate = self._normalize_prompt_name(match.group(1) if match is not None else "")
            if candidate == "":
                continue
            if self._is_internal_prompt_name(candidate) and not include_internal:
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
