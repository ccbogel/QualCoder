# -*- coding: utf-8 -*-

"""
Local help index for QualCoder AI assistance.

The English Markdown manual from the QualCoder website repository is treated as
the canonical source. Pages are synced into a local SQLite FTS5 index under
``~/.qualcoder/help`` and can then be queried quickly by the internal MCP
server.

---

This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Kai Dröge (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

logger = logging.getLogger(__name__)

GITHUB_TREE_API_URL = (
    "https://api.github.com/repos/QualCoder-Org/qualcoder-org.github.io/git/trees/main?recursive=1"
)
GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com/QualCoder-Org/qualcoder-org.github.io/main/"
HELP_DOCS_ROOT_CANDIDATES = (
    "docs/doc/en/",
    "docs/en/",
)
DEFAULT_SYNC_INTERVAL_HOURS = 12
DEFAULT_SEARCH_PAGE_SIZE = 5
MAX_SEARCH_PAGE_SIZE = 20
PAGE_READ_DEFAULT_CHARS = 5000

FRONTMATTER_PATTERN = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.MULTILINE)


class AiHelpIndex:
    """Synchronize and query a local chunk index of the English help pages."""

    def __init__(self) -> None:
        self.help_dir = os.path.join(os.path.expanduser("~"), ".qualcoder", "help")
        self.db_path = os.path.join(self.help_dir, "help_index.sqlite")
        self._lock = threading.Lock()

    def search(self, queries: List[str], page_size: int = DEFAULT_SEARCH_PAGE_SIZE,
               cursor: Optional[str] = None) -> Dict[str, Any]:
        """Search the indexed help chunks with one or more English queries."""

        normalized_queries = [q.strip() for q in queries if str(q).strip() != ""]
        if len(normalized_queries) == 0:
            raise ValueError("Help search requires at least one non-empty q parameter.")

        self._ensure_index_ready()
        page_size = max(1, min(int(page_size), MAX_SEARCH_PAGE_SIZE))
        offset = self._cursor_to_offset(cursor)
        match_query = self._build_fts_query(normalized_queries)

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    slug,
                    title,
                    heading,
                    snippet(help_chunks_fts, 4, '[', ']', ' ... ', 18) AS snippet_text,
                    bm25(help_chunks_fts) AS score
                FROM help_chunks_fts
                WHERE help_chunks_fts MATCH ?
                ORDER BY score, title, slug
                LIMIT ? OFFSET ?
                """,
                (match_query, page_size + 1, offset),
            ).fetchall()
            sync_info = self._read_sync_info(conn)

        has_more = len(rows) > page_size
        result_rows = rows[:page_size]
        results: List[Dict[str, Any]] = []
        for row in result_rows:
            slug = str(row["slug"])
            title = str(row["title"])
            heading = str(row["heading"])
            snippet_text = str(row["snippet_text"] if row["snippet_text"] is not None else "")
            results.append(
                {
                    "page_path": slug,
                    "title": title,
                    "heading": heading,
                    "snippet": snippet_text,
                    "help_href": f"qualcoder://help/page/{slug}",
                    "score": float(row["score"]) if row["score"] is not None else 0.0,
                }
            )

        return {
            "queries": normalized_queries,
            "results": results,
            "page_size": page_size,
            "cursor": str(offset),
            "next_cursor": str(offset + page_size) if has_more else None,
            "index_info": sync_info,
        }

    def read_page(self, slug: str, start: int = 0, length: int = PAGE_READ_DEFAULT_CHARS) -> Dict[str, Any]:
        """Read one cached help page by slug."""

        normalized_slug = self._normalize_slug(slug)
        if normalized_slug == "":
            raise ValueError("Help page slug is missing.")

        self._ensure_index_ready()
        start = max(0, int(start))
        length = max(1, int(length))

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT slug, title, source_path, source_url, markdown, plain_text, updated_at
                FROM help_pages
                WHERE slug = ?
                """,
                (normalized_slug,),
            ).fetchone()
            sync_info = self._read_sync_info(conn)

        if row is None:
            raise ValueError(f'Unknown help page: "{normalized_slug}".')

        plain_text = str(row["plain_text"] if row["plain_text"] is not None else "")
        excerpt = plain_text[start:start + length]
        return {
            "page_path": str(row["slug"]),
            "title": str(row["title"]),
            "source_path": str(row["source_path"]),
            "source_url": str(row["source_url"]),
            "help_href": f'qualcoder://help/page/{row["slug"]}',
            "text": excerpt,
            "start": start,
            "length": len(excerpt),
            "char_length_total": len(plain_text),
            "truncated": start + len(excerpt) < len(plain_text),
            "updated_at": str(row["updated_at"]),
            "index_info": sync_info,
        }

    def list_pages(self) -> Dict[str, Any]:
        """Return indexed help pages for overview/debugging purposes."""

        self._ensure_index_ready()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT slug, title, source_path, updated_at
                FROM help_pages
                ORDER BY title, slug
                """
            ).fetchall()
            sync_info = self._read_sync_info(conn)
        pages = [
            {
                "page_path": str(row["slug"]),
                "title": str(row["title"]),
                "source_path": str(row["source_path"]),
                "updated_at": str(row["updated_at"]),
                "help_href": f'qualcoder://help/page/{row["slug"]}',
            }
            for row in rows
        ]
        return {"pages": pages, "index_info": sync_info}

    def _ensure_index_ready(self) -> None:
        """Create schema if needed and refresh the local index when it is stale."""

        with self._lock:
            self._ensure_storage()
            with self._connect() as conn:
                self._ensure_schema(conn)
                meta = self._read_meta(conn)
                local_page_count = int(meta.get("page_count", "0") or "0")
                if self._sync_required(meta):
                    try:
                        self._sync_from_remote(conn)
                    except Exception as err:
                        logger.warning("Help index sync failed: %s", err)
                        self._write_meta(
                            conn,
                            {
                                "last_sync_attempt_at": self._utc_now_iso(),
                                "last_sync_error": str(err),
                            },
                        )
                        conn.commit()
                        if local_page_count <= 0:
                            raise
                elif local_page_count <= 0:
                    self._sync_from_remote(conn)

    def _sync_required(self, meta: Dict[str, str]) -> bool:
        """Return True when the cached help index should be refreshed."""

        last_successful_sync = meta.get("last_successful_sync_at", "").strip()
        if last_successful_sync == "":
            return True
        try:
            last_sync_dt = datetime.fromisoformat(last_successful_sync)
        except ValueError:
            return True
        if last_sync_dt.tzinfo is None:
            last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
        sync_interval = timedelta(hours=DEFAULT_SYNC_INTERVAL_HOURS)
        return datetime.now(timezone.utc) - last_sync_dt >= sync_interval

    def _sync_from_remote(self, conn: sqlite3.Connection) -> None:
        """Fetch the current English docs tree and refresh changed pages."""

        remote_pages = self._fetch_remote_page_listing()
        remote_slugs = {page["slug"] for page in remote_pages}
        local_rows = conn.execute("SELECT slug, sha FROM help_pages").fetchall()
        local_sha_by_slug = {str(row["slug"]): str(row["sha"]) for row in local_rows}

        changed_pages = [page for page in remote_pages if local_sha_by_slug.get(page["slug"]) != page["sha"]]
        deleted_slugs = [slug for slug in local_sha_by_slug if slug not in remote_slugs]

        for page in changed_pages:
            markdown = self._download_text(page["source_url"])
            title, plain_text, chunks = self._parse_markdown_page(page["slug"], markdown)
            self._replace_page(conn, page, title, markdown, plain_text, chunks)

        for slug in deleted_slugs:
            self._delete_page(conn, slug)

        now = self._utc_now_iso()
        page_count = conn.execute("SELECT COUNT(*) FROM help_pages").fetchone()[0]
        self._write_meta(
            conn,
            {
                "last_sync_attempt_at": now,
                "last_successful_sync_at": now,
                "last_sync_error": "",
                "page_count": str(page_count),
            },
        )
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _fetch_remote_page_listing(self) -> List[Dict[str, str]]:
        """Return current English help pages from the GitHub repo tree."""

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "QualCoder-Help-Index",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        response = requests.get(GITHUB_TREE_API_URL, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        tree = payload.get("tree", [])
        if not isinstance(tree, list):
            raise ValueError("Unexpected GitHub tree response for help docs.")

        pages: List[Dict[str, str]] = []
        active_root = self._detect_help_docs_root(tree)
        for item in tree:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", ""))
            if not path.startswith(active_root) or not path.endswith(".md"):
                continue
            if str(item.get("type", "")) != "blob":
                continue
            slug = os.path.splitext(os.path.basename(path))[0]
            if slug.strip() == "":
                continue
            pages.append(
                {
                    "slug": slug,
                    "sha": str(item.get("sha", "")),
                    "source_path": path,
                    "source_url": GITHUB_RAW_BASE_URL + path,
                }
            )
        if len(pages) == 0:
            raise ValueError("No English help pages were found in the remote docs tree.")
        pages.sort(key=lambda item: item["slug"].lower())
        return pages

    def _detect_help_docs_root(self, tree: List[Dict[str, Any]]) -> str:
        """Return the active English docs root used by the remote repository."""

        for root in HELP_DOCS_ROOT_CANDIDATES:
            for item in tree:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path", ""))
                if str(item.get("type", "")) == "blob" and path.startswith(root) and path.endswith(".md"):
                    return root
        tried = ", ".join(HELP_DOCS_ROOT_CANDIDATES)
        raise ValueError(f"No English help pages were found in the remote docs tree. Tried: {tried}")

    def _download_text(self, url: str) -> str:
        """Download one UTF-8 text file."""

        response = requests.get(
            url,
            headers={"User-Agent": "QualCoder-Help-Index"},
            timeout=30,
        )
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    def _parse_markdown_page(self, slug: str, markdown: str) -> Tuple[str, str, List[Dict[str, Any]]]:
        """Extract title, plain text, and indexed chunks from one Markdown page."""

        _, body = self._split_frontmatter(markdown)
        title = self._extract_title(slug, body)
        plain_text = self._markdown_to_text(body)
        sections = self._split_sections(body, fallback_heading=title)

        chunks: List[Dict[str, Any]] = []
        chunk_index = 0
        for heading, section_text in sections:
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section_text) if p.strip() != ""]
            if len(paragraphs) == 0:
                paragraphs = [section_text.strip()]
            current_parts: List[str] = []
            current_length = 0
            for paragraph in paragraphs:
                paragraph_text = self._markdown_to_text(paragraph).strip()
                if paragraph_text == "":
                    continue
                projected = current_length + len(paragraph_text) + (1 if current_parts else 0)
                if current_parts and projected > 1200:
                    chunk_body = "\n\n".join(current_parts).strip()
                    if chunk_body != "":
                        chunks.append(
                            {
                                "chunk_index": chunk_index,
                                "heading": heading,
                                "body": chunk_body,
                            }
                        )
                        chunk_index += 1
                    current_parts = [paragraph_text]
                    current_length = len(paragraph_text)
                else:
                    current_parts.append(paragraph_text)
                    current_length = projected
            if current_parts:
                chunk_body = "\n\n".join(current_parts).strip()
                if chunk_body != "":
                    chunks.append(
                        {
                            "chunk_index": chunk_index,
                            "heading": heading,
                            "body": chunk_body,
                        }
                    )
                    chunk_index += 1

        if len(chunks) == 0 and plain_text.strip() != "":
            chunks.append({"chunk_index": 0, "heading": title, "body": plain_text.strip()})
        return title, plain_text, chunks

    def _replace_page(self, conn: sqlite3.Connection, page: Dict[str, str], title: str,
                      markdown: str, plain_text: str, chunks: List[Dict[str, Any]]) -> None:
        """Replace one cached page and all indexed chunks."""

        conn.execute("DELETE FROM help_chunks_fts WHERE slug = ?", (page["slug"],))
        conn.execute("DELETE FROM help_pages WHERE slug = ?", (page["slug"],))
        now = self._utc_now_iso()
        conn.execute(
            """
            INSERT INTO help_pages (slug, title, sha, source_path, source_url, markdown, plain_text, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page["slug"],
                title,
                page["sha"],
                page["source_path"],
                page["source_url"],
                markdown,
                plain_text,
                now,
            ),
        )
        for chunk in chunks:
            conn.execute(
                """
                INSERT INTO help_chunks_fts (slug, chunk_index, title, heading, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    page["slug"],
                    int(chunk["chunk_index"]),
                    title,
                    str(chunk["heading"]),
                    str(chunk["body"]),
                ),
            )

    def _delete_page(self, conn: sqlite3.Connection, slug: str) -> None:
        """Delete one cached page and all related index rows."""

        conn.execute("DELETE FROM help_chunks_fts WHERE slug = ?", (slug,))
        conn.execute("DELETE FROM help_pages WHERE slug = ?", (slug,))

    def _split_frontmatter(self, text: str) -> Tuple[Dict[str, Any], str]:
        """Return YAML frontmatter metadata and body without the frontmatter block."""

        raw_text = str(text if text is not None else "")
        match = FRONTMATTER_PATTERN.match(raw_text)
        if match is None:
            return {}, raw_text
        metadata_text = match.group(1)
        try:
            metadata = yaml.safe_load(metadata_text)
        except yaml.YAMLError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return metadata, raw_text[match.end():]

    def _extract_title(self, slug: str, body: str) -> str:
        """Return a usable page title."""

        match = HEADING_PATTERN.search(body)
        if match is not None:
            title = self._markdown_inline_to_text(match.group(2))
            if title.strip() != "":
                return title.strip()
        title_from_slug = slug.replace("-", " ").replace(".", ". ").strip()
        return title_from_slug if title_from_slug != "" else slug

    def _split_sections(self, body: str, fallback_heading: str) -> List[Tuple[str, str]]:
        """Split one page into heading-based sections."""

        matches = list(HEADING_PATTERN.finditer(body))
        if len(matches) == 0:
            cleaned = body.strip()
            return [(fallback_heading, cleaned)] if cleaned != "" else []

        sections: List[Tuple[str, str]] = []
        intro_text = body[:matches[0].start()].strip()
        if intro_text != "":
            sections.append((fallback_heading, intro_text))
        for idx, match in enumerate(matches):
            heading = self._markdown_inline_to_text(match.group(2)).strip() or fallback_heading
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
            section_text = body[start:end].strip()
            if section_text != "":
                sections.append((heading, section_text))
        return sections

    def _markdown_to_text(self, text: str) -> str:
        """Convert Markdown to compact plain text for indexing and page reads."""

        raw = str(text if text is not None else "")
        raw = re.sub(r"```.*?```", " ", raw, flags=re.DOTALL)
        raw = re.sub(r"`([^`]*)`", r"\1", raw)
        raw = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", raw)
        raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
        raw = re.sub(r"^>\s?", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^#{1,6}\s+", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^\s*[-*+]\s+", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^\s*\d+\.\s+", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\|", " ", raw)
        raw = re.sub(r"\*\*([^*]+)\*\*", r"\1", raw)
        raw = re.sub(r"\*([^*]+)\*", r"\1", raw)
        raw = re.sub(r"_([^_]+)_", r"\1", raw)
        raw = raw.replace("\r", "")
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        return raw.strip()

    def _markdown_inline_to_text(self, text: str) -> str:
        """Convert one inline Markdown string to text."""

        return self._markdown_to_text(text).replace("\n", " ").strip()

    def _build_fts_query(self, queries: List[str]) -> str:
        """Build one conservative FTS5 MATCH query from natural-language search prompts."""

        clauses: List[str] = []
        for query in queries:
            tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9._:/+-]*", query)
            if len(tokens) == 0:
                continue
            token_clause = " AND ".join(f'"{token.replace("\"", "\"\"")}"' for token in tokens[:10])
            if token_clause != "":
                clauses.append("(" + token_clause + ")")
        if len(clauses) == 0:
            raise ValueError("The help search query does not contain searchable terms.")
        return " OR ".join(clauses)

    def _normalize_slug(self, slug: str) -> str:
        """Normalize help page references."""

        value = str(slug if slug is not None else "").strip()
        if value.endswith(".md"):
            value = value[:-3]
        value = value.strip().strip("/")
        return value

    def _cursor_to_offset(self, cursor: Optional[str]) -> int:
        """Parse one numeric cursor into an offset."""

        if cursor is None or str(cursor).strip() == "":
            return 0
        try:
            return max(0, int(str(cursor).strip()))
        except ValueError:
            raise ValueError("Invalid help search cursor.")

    def _ensure_storage(self) -> None:
        """Create the persistent help cache directory if needed."""

        os.makedirs(self.help_dir, exist_ok=True)
        if not os.path.exists(self.db_path):
            for suffix in ("-wal", "-shm"):
                sidecar_path = self.db_path + suffix
                if os.path.exists(sidecar_path):
                    try:
                        os.remove(sidecar_path)
                    except OSError:
                        logger.warning("Could not remove stale help index sidecar: %s", sidecar_path)

    def _connect(self) -> sqlite3.Connection:
        """Open the local help index database."""

        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create the required tables and FTS index."""

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS help_pages (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                sha TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_url TEXT NOT NULL,
                markdown TEXT NOT NULL,
                plain_text TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS help_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS help_chunks_fts USING fts5(
                slug UNINDEXED,
                chunk_index UNINDEXED,
                title,
                heading,
                body,
                tokenize = 'porter unicode61 remove_diacritics 2'
            )
            """
        )
        conn.commit()

    def _read_meta(self, conn: sqlite3.Connection) -> Dict[str, str]:
        """Return all sync metadata as a simple dict."""

        rows = conn.execute("SELECT key, value FROM help_meta").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def _write_meta(self, conn: sqlite3.Connection, values: Dict[str, str]) -> None:
        """Upsert sync metadata values."""

        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO help_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(key), str(value)),
            )

    def _read_sync_info(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Build one small sync status payload for MCP responses."""

        meta = self._read_meta(conn)
        page_count = int(meta.get("page_count", "0") or "0")
        return {
            "page_count": page_count,
            "last_successful_sync_at": meta.get("last_successful_sync_at", ""),
            "last_sync_attempt_at": meta.get("last_sync_attempt_at", ""),
            "last_sync_error": meta.get("last_sync_error", ""),
            "source": "QualCoder-Org/qualcoder-org.github.io English docs on main",
            "cache_path": self.db_path,
        }

    def _utc_now_iso(self) -> str:
        """Return the current UTC timestamp in ISO format."""

        return datetime.now(timezone.utc).isoformat()
