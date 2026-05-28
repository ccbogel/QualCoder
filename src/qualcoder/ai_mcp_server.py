# -*- coding: utf-8 -*-

"""
Internal MCP server for QualCoder.

This module uses the official MCP Python SDK (low-level server) and exposes
an in-process JSON-RPC bridge (`handle_request`) so the current chat flow can
call it without transport setup.
"""

import asyncio
import hashlib
import json
import os
import random
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.server import ReadResourceContents


class AiMcpServer:
    """Internal MCP server for QualCoder project data."""

    protocol_version = "2025-06-18"
    server_name = "qualcoder-internal-mcp"
    server_version = "0.1.0"
    max_read_length = 12000
    default_read_length = 4000
    default_segments_max_segments = 40
    max_segments_limit = 200
    default_segments_max_chars = 8000
    max_segments_chars_limit = 50000
    default_vector_page_size = 20
    default_vector_k_per_query = 50
    default_vector_score_threshold = 0.5
    default_bm25_page_size = 20
    max_bm25_page_size = 100
    default_regex_page_size = 20
    max_regex_page_size = 100
    default_regex_context_chars = 120
    max_regex_context_chars = 1000
    max_regex_hits = 20000
    AI_AGENT_OWNER = "AI Agent"
    AI_PERMISSION_READ_ONLY = 0
    AI_PERMISSION_SANDBOXED = 1
    AI_PERMISSION_FULL_ACCESS = 2
    SANDBOX_WRITE_TOOL_NAMES = (
        "codes/create_category",
        "codes/create_code",
        "codes/create_text_coding",
    )
    FULL_ACCESS_WRITE_TOOL_NAMES = (
        "codes/rename_category",
        "codes/rename_code",
        "codes/move_category",
        "codes/move_code",
        "codes/delete_category",
        "codes/delete_code",
        "codes/move_text_coding",
        "codes/delete_text_coding",
    )
    PREVIEW_TOOL_NAMES = (
        "codes/preview_delete_category",
        "codes/preview_delete_code",
    )
    WRITE_TOOL_NAMES = SANDBOX_WRITE_TOOL_NAMES + FULL_ACCESS_WRITE_TOOL_NAMES
    PREVIEW_REQUIRED_EXECUTE_TOOLS = (
        "codes/delete_category",
        "codes/delete_code",
    )

    def __init__(self, app):
        self.app = app
        self._request_seq = 1
        self._preview_tokens: Dict[str, Dict[str, Any]] = {}
        self._sdk_server = Server(
            self.server_name,
            version=self.server_version,
            instructions=self._server_instructions(),
        )
        self._register_sdk_handlers()

    def _server_instructions(self) -> str:
        return (
            "QualCoder internal MCP server. "
            "Use resources/list, resources/read, tools/list, and tools/call. "
            "Available resources: text documents list (qualcoder://documents), document text by id "
            "(qualcoder://documents/text/{id}, with optional start/length or line_start/line_end), "
            "cases list (qualcoder://cases), case details by id (qualcoder://cases/{id}), "
            "and case text segments by case id (qualcoder://cases/text/{id}), "
            "code tree (qualcoder://codes/tree), and coded text segments by code id "
            "(qualcoder://codes/segments/{cid}), semantic vector search "
            "(qualcoder://vector/search?q=...) with optional filters file_ids and exclude_cids, "
            "BM25 chunk search "
            "(qualcoder://search/bm25?q=...) with optional filters file_ids and exclude_cids, "
            "and regular-expression search "
            "(qualcoder://search/regex?pattern=...) with optional filters file_ids and exclude_cids. "
            "Available tools include preview and write operations for categories, codes, and text codings. "
            "Delete actions on categories or codes should be previewed before execution."
        )

    def _current_ai_permissions(self) -> int:
        """Return the normalized AI permissions level."""

        ai_permissions = self.app.settings.get("ai_permissions", self.AI_PERMISSION_SANDBOXED)
        if ai_permissions not in (
            self.AI_PERMISSION_READ_ONLY,
            self.AI_PERMISSION_SANDBOXED,
            self.AI_PERMISSION_FULL_ACCESS,
        ):
            return self.AI_PERMISSION_SANDBOXED
        return ai_permissions

    def _current_ai_permissions_label(self) -> str:
        """Return the current AI permissions label."""

        labels = {
            self.AI_PERMISSION_READ_ONLY: "Read-only",
            self.AI_PERMISSION_SANDBOXED: "Sandboxed",
            self.AI_PERMISSION_FULL_ACCESS: "Full access",
        }
        return labels.get(self._current_ai_permissions(), "Sandboxed")

    def _tool_result_payload(self, payload: Dict[str, Any], is_error: bool = False) -> Dict[str, Any]:
        """Wrap structured tool content in an MCP tool result."""

        return {
            "isError": is_error,
            "structuredContent": payload,
            "content": [
                {
                    "type": "text",
                    "text": self._tool_result_summary_text(payload, is_error),
                }
            ],
        }

    def _tool_result_summary_text(self, payload: Dict[str, Any], is_error: bool = False) -> str:
        """Return one short human-readable summary for MCP tool results."""

        if not isinstance(payload, dict):
            return "Tool call failed." if is_error else "Tool call completed."

        tool_name = str(payload.get("tool", "")).strip()
        if tool_name == "":
            return "Tool call failed." if is_error else "Tool call completed."

        if is_error:
            return f"{tool_name} failed."

        if "created" in payload:
            return f"{tool_name} {'created' if bool(payload.get('created', False)) else 'did not create'} a result."
        if "deleted" in payload:
            return f"{tool_name} {'deleted' if bool(payload.get('deleted', False)) else 'did not delete'} a result."
        if "moved" in payload:
            return f"{tool_name} {'moved' if bool(payload.get('moved', False)) else 'did not move'} a result."
        if "renamed" in payload:
            return f"{tool_name} {'renamed' if bool(payload.get('renamed', False)) else 'did not rename'} a result."
        if "preview_token" in payload:
            return f"{tool_name} prepared a preview."
        return f"{tool_name} completed."

    def _emit_project_table_changes(self, tables: List[str], source: str = "ai_agent") -> None:
        """Emit one app-level project data change event if the event bus exists."""

        project_events = getattr(self.app, "project_events", None)
        if project_events is None or not hasattr(project_events, "emit_table_changes") or not isinstance(tables, list):
            return
        project_events.emit_table_changes(tables, source=source)

    def _snapshot_changed_table_names(self, snapshot: Dict[str, Any]) -> List[str]:
        """Return non-empty table names from one snapshot payload."""

        tables = snapshot.get("tables", {}) if isinstance(snapshot, dict) else {}
        if not isinstance(tables, dict):
            return []
        changed_tables: List[str] = []
        for table_name, rows in tables.items():
            name = str(table_name if table_name is not None else "").strip()
            if name == "" or not isinstance(rows, list) or len(rows) == 0:
                continue
            changed_tables.append(name)
        return changed_tables

    def _tool_required_permission(self, tool_name: str) -> int:
        """Return the required AI permissions level for one tool."""

        if tool_name in self.SANDBOX_WRITE_TOOL_NAMES:
            return self.AI_PERMISSION_SANDBOXED
        if tool_name in self.FULL_ACCESS_WRITE_TOOL_NAMES:
            return self.AI_PERMISSION_FULL_ACCESS
        return self.AI_PERMISSION_READ_ONLY

    def _tool_permission_error(self, tool_name: str, required_permission: int) -> Dict[str, Any]:
        """Return a standardized permission error for tools with insufficient access."""

        if required_permission == self.AI_PERMISSION_FULL_ACCESS:
            required_label = '"Full access"'
        else:
            required_label = '"Sandboxed" or "Full access"'
        message = (
            f'Tool "{tool_name}" requires AI Permissions set to {required_label}. '
            f'Current level: "{self._current_ai_permissions_label()}".'
        )
        return self._tool_result_payload(
            {
                "tool": tool_name,
                "error": {
                    "code": "ai_permissions_denied",
                    "message": message,
                },
            },
            is_error=True,
        )

    def _issue_preview_token(self, execute_tool: str, signature_payload: Dict[str, Any]) -> str:
        """Create one transient preview token for a later execute call."""

        signature_text = json.dumps(signature_payload, sort_keys=True, ensure_ascii=False)
        now = datetime.now().astimezone().isoformat()
        token = hashlib.sha1(f"{execute_tool}|{signature_text}|{now}|{random.random()}".encode("utf-8")).hexdigest()
        self._preview_tokens[token] = {
            "execute_tool": execute_tool,
            "signature": signature_text,
            "created_at": now,
        }
        return token

    def _consume_preview_token(self, execute_tool: str, signature_payload: Dict[str, Any], token: str) -> None:
        """Validate and consume one preview token."""

        preview_token = str(token if token is not None else "").strip()
        if preview_token == "":
            raise ValueError(f'{execute_tool} requires a preview_token from the corresponding preview tool.')
        token_data = self._preview_tokens.get(preview_token)
        if not isinstance(token_data, dict):
            raise ValueError("preview_token is invalid or expired.")
        expected_signature = json.dumps(signature_payload, sort_keys=True, ensure_ascii=False)
        if str(token_data.get("execute_tool", "")) != execute_tool:
            raise ValueError("preview_token does not match this tool.")
        if str(token_data.get("signature", "")) != expected_signature:
            raise ValueError("preview_token does not match the requested object or target.")
        del self._preview_tokens[preview_token]

    def new_request_id(self) -> int:
        req_id = self._request_seq
        self._request_seq += 1
        return req_id

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC request and return a JSON-RPC response."""

        request_id = request.get("id")
        jsonrpc = request.get("jsonrpc", "2.0")
        method = request.get("method")
        params = request.get("params", {})

        if jsonrpc != "2.0":
            return self._error_response(request_id, -32600, "Invalid Request", "jsonrpc must be '2.0'.")
        if not isinstance(method, str) or method.strip() == "":
            return self._error_response(request_id, -32600, "Invalid Request", "Missing method.")
        if not isinstance(params, dict):
            return self._error_response(request_id, -32602, "Invalid params", "params must be an object.")

        try:
            if method == "initialize":
                result = self._initialize_result()
            elif method == "resources/list":
                req = types.ListResourcesRequest(params=self._pagination_params(params))
                result = self._dispatch_sdk(types.ListResourcesRequest, req)
            elif method == "resources/templates/list":
                req = types.ListResourceTemplatesRequest(params=self._pagination_params(params))
                result = self._dispatch_sdk(types.ListResourceTemplatesRequest, req)
            elif method == "resources/read":
                uri = params.get("uri")
                if not isinstance(uri, str) or uri.strip() == "":
                    raise ValueError("Missing resource uri.")
                uri_with_window = self._with_read_window(
                    uri,
                    params.get("start"),
                    params.get("length"),
                    params.get("line_start"),
                    params.get("line_end"),
                )
                req = types.ReadResourceRequest(params=types.ReadResourceRequestParams(uri=uri_with_window))
                result = self._dispatch_sdk(types.ReadResourceRequest, req)
            elif method == "tools/list":
                result = self._list_tools_payload()
            elif method == "tools/call":
                name = str(params.get("name", "")).strip()
                if name == "":
                    raise ValueError("Missing tool name.")
                args = params.get("arguments")
                if args is not None and not isinstance(args, dict):
                    raise ValueError("Tool arguments must be an object.")
                change_set_id = str(params.get("_ai_change_set_id", "")).strip()
                result = self._call_tool_payload(name, args, change_set_id)
            else:
                return self._error_response(request_id, -32601, "Method not found", method)
            return self._result_response(request_id, result)
        except ValueError as err:
            return self._error_response(request_id, -32602, "Invalid params", str(err))
        except RuntimeError as err:
            return self._error_response(request_id, -32000, "Runtime error", str(err))
        except Exception as err:
            return self._error_response(request_id, -32603, "Internal error", str(err))

    def describe_status_event(self, method: str, params: Dict[str, Any]) -> str:
        """Describe one user-facing status line for a request, if applicable."""

        if method == "initialize":
            return ""
        if method == "resources/templates/list":
            return ""
        if method == "resources/list":
            return ""
        if method == "tools/list":
            return ""
        if method == "tools/call":
            tool_name = str(params.get("name", "")).strip()
            if tool_name == "":
                return ""
            tool_args = params.get("arguments", {})
            if not isinstance(tool_args, dict):
                tool_args = {}
            if tool_name == "codes/create_category":
                cat_name = " ".join(str(tool_args.get("name", "")).split()).strip()
                if cat_name == "":
                    cat_name = _("(unnamed category)")
                return _('Creating category "{name}"...').format(name=cat_name)
            if tool_name == "codes/create_code":
                code_name = " ".join(str(tool_args.get("name", "")).split()).strip()
                if code_name == "":
                    code_name = _("(unnamed code)")
                return _('Creating code "{name}"...').format(name=code_name)
            if tool_name == "codes/create_text_coding":
                cid = self._to_int(tool_args.get("cid"), -1)
                fid = self._to_int(tool_args.get("fid"), -1)
                code_name = self._fetch_code_name(cid) if cid > 0 else None
                if code_name is None or str(code_name).strip() == "":
                    code_name = _("Code") + (f" #{cid}" if cid > 0 else "")
                doc_name = self._fetch_source_name(fid) if fid > 0 else None
                if doc_name is None or str(doc_name).strip() == "":
                    doc_name = _("Document") + (f" #{fid}" if fid > 0 else "")
                return _('Creating text coding for code "{code}" in document "{document}"...').format(
                    code=str(code_name),
                    document=str(doc_name),
                )
            if tool_name in ("codes/delete_category", "codes/move_category", "codes/preview_delete_category"):
                catid = self._to_int(tool_args.get("catid"), -1)
                category_name = self._fetch_category_name(catid) if catid > 0 else None
                if category_name is None or str(category_name).strip() == "":
                    category_name = _("Category") + (f" #{catid}" if catid > 0 else "")
                if tool_name == "codes/preview_delete_category":
                    return _('Reviewing impact of deleting category "{name}"...').format(name=str(category_name))
                if tool_name == "codes/move_category":
                    return _('Moving category "{name}"...').format(name=str(category_name))
                return _('Deleting category "{name}"...').format(name=str(category_name))
            if tool_name in ("codes/delete_code", "codes/move_code", "codes/preview_delete_code"):
                cid = self._to_int(tool_args.get("cid"), -1)
                code_name = self._fetch_code_name(cid) if cid > 0 else None
                if code_name is None or str(code_name).strip() == "":
                    code_name = _("Code") + (f" #{cid}" if cid > 0 else "")
                if tool_name == "codes/preview_delete_code":
                    return _('Reviewing impact of deleting code "{name}"...').format(name=str(code_name))
                if tool_name == "codes/move_code":
                    return _('Moving code "{name}"...').format(name=str(code_name))
                return _('Deleting code "{name}"...').format(name=str(code_name))
            if tool_name == "codes/rename_category":
                catid = self._to_int(tool_args.get("catid"), -1)
                if catid <= 0:
                    return _('Renaming category "error: missing category id"...')
                category_name = self._fetch_category_name(catid)
                if category_name is None or str(category_name).strip() == "":
                    category_name = _("Category") + f" #{catid}"
                return _('Renaming category "{name}"...').format(name=str(category_name))
            if tool_name == "codes/rename_code":
                cid = self._to_int(tool_args.get("cid"), -1)
                if cid <= 0:
                    return _('Renaming code "error: missing code id"...')
                code_name = self._fetch_code_name(cid)
                if code_name is None or str(code_name).strip() == "":
                    code_name = _("Code") + f" #{cid}"
                return _('Renaming code "{name}"...').format(name=str(code_name))
            if tool_name == "codes/move_text_coding":
                ctid = self._to_int(tool_args.get("ctid"), -1)
                return _('Moving text coding #{ctid}...').format(ctid=ctid if ctid > 0 else "?")
            if tool_name == "codes/delete_text_coding":
                ctid = self._to_int(tool_args.get("ctid"), -1)
                return _('Deleting text coding #{ctid}...').format(ctid=ctid if ctid > 0 else "?")
            return _('Executing tool "{name}"...').format(name=tool_name)
        if method != "resources/read":
            return ""

        uri = str(params.get("uri", ""))
        uri_base = uri.split("?", 1)[0]

        if uri_base == "qualcoder://documents":
            return _('Reviewing the list of text documents...')
        if uri_base == "qualcoder://cases":
            return _('Reviewing the list of cases...')
        if uri_base == "qualcoder://codes/tree":
            return _('Reviewing the current code structure...')
        if uri_base == "qualcoder://vector/search":
            return _('Running semantic search in the project data...')
        if uri_base == "qualcoder://search/bm25":
            return _('Running keyword search in empirical data (BM25)...')
        if uri_base == "qualcoder://search/regex":
            return _('Running keyword search in empirical data (Regex)...')
        case_text_match = re.fullmatch(r"qualcoder://cases/text/(\d+)", uri_base)
        if case_text_match is not None:
            case_id = int(case_text_match.group(1))
            case_name = self._fetch_case_name(case_id)
            if case_name is None or case_name == "":
                case_name = f"Case {case_id}"
            return _('Reviewing text segments for case "{name}"...').format(name=case_name)
        case_match = re.fullmatch(r"qualcoder://cases/(\d+)", uri_base)
        if case_match is not None:
            case_id = int(case_match.group(1))
            case_name = self._fetch_case_name(case_id)
            if case_name is None or case_name == "":
                case_name = f"Case {case_id}"
            return _('Reviewing case details for "{name}"...').format(name=case_name)
        code_segments_match = re.fullmatch(r"qualcoder://codes/segments/(\d+)", uri_base)
        if code_segments_match is not None:
            cid = int(code_segments_match.group(1))
            code_name = self._fetch_code_name(cid)
            if code_name is None or code_name == "":
                code_name = f"Code {cid}"
            return _('Reviewing coded text segments for "{name}"...').format(name=code_name)
        doc_match = re.fullmatch(r"qualcoder://documents/text/(\d+)", uri_base)
        if doc_match is not None:
            doc_id = int(doc_match.group(1))
            doc_name = self._fetch_source_name(doc_id)
            if doc_name is None or doc_name == "":
                doc_name = f"Document {doc_id}"
            return _('Reviewing passages from "{name}"...').format(name=doc_name)

        return _('Reviewing project material...')

    def _initialize_result(self) -> Dict[str, Any]:
        result = types.InitializeResult(
            protocolVersion=self.protocol_version,
            capabilities=types.ServerCapabilities(
                resources=types.ResourcesCapability(subscribe=False, listChanged=False),
                tools=types.ToolsCapability(listChanged=False),
                prompts=types.PromptsCapability(listChanged=False),
            ),
            serverInfo=types.Implementation(name=self.server_name, version=self.server_version),
            instructions=self._server_instructions(),
        )
        return result.model_dump(mode="json", exclude_none=True)

    def _dispatch_sdk(self, req_type: type, req_obj: Any) -> Dict[str, Any]:
        handler = self._sdk_server.request_handlers.get(req_type)
        if handler is None:
            raise RuntimeError(f"MCP handler not registered for {req_type.__name__}.")
        server_result = asyncio.run(handler(req_obj))
        if hasattr(server_result, "model_dump"):
            return server_result.model_dump(mode="json", exclude_none=True)
        return dict(server_result)

    def _pagination_params(self, params: Dict[str, Any]) -> Optional[types.PaginatedRequestParams]:
        cursor = params.get("cursor")
        if cursor is None:
            return None
        return types.PaginatedRequestParams(cursor=str(cursor))

    def _with_read_window(self, uri: str, start: Any, length: Any,
                          line_start: Any = None, line_end: Any = None) -> str:
        has_char_window = start is not None or length is not None
        has_line_window = line_start is not None or line_end is not None
        if has_char_window and has_line_window:
            raise ValueError("Use either start/length or line_start/line_end, not both.")
        if not has_char_window and not has_line_window:
            return uri
        parts = urlsplit(uri)
        query = parse_qs(parts.query, keep_blank_values=True)
        if has_char_window:
            if start is not None:
                start_i = max(0, self._to_int(start, 0))
                query["start"] = [str(start_i)]
            if length is not None:
                length_i = max(1, min(self._to_int(length, self.default_read_length), self.max_read_length))
                query["length"] = [str(length_i)]
            query.pop("line_start", None)
            query.pop("line_end", None)
        else:
            if line_start is not None:
                line_start_i = max(1, self._to_int(line_start, 1))
                query["line_start"] = [str(line_start_i)]
            if line_end is not None:
                line_end_i = max(1, self._to_int(line_end, 1))
                query["line_end"] = [str(line_end_i)]
            query.pop("start", None)
            query.pop("length", None)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))

    def _parse_read_window(self, uri: str) -> Tuple[str, Dict[str, Any]]:
        parts = urlsplit(uri)
        query = parse_qs(parts.query, keep_blank_values=True)
        has_char_window = "start" in query or "length" in query
        has_line_window = "line_start" in query or "line_end" in query
        if has_char_window and has_line_window:
            raise ValueError("Use either start/length or line_start/line_end, not both.")
        if has_line_window:
            line_start = max(1, self._to_int(query.get("line_start", [1])[0], 1))
            line_end = self._to_int(query.get("line_end", [line_start])[0], line_start)
            if line_end < line_start:
                raise ValueError("line_end must be greater than or equal to line_start.")
            window = {
                "mode": "line",
                "line_start": line_start,
                "line_end": line_end,
            }
        else:
            start = max(0, self._to_int(query.get("start", [0])[0], 0))
            length = max(
                1,
                min(
                    self._to_int(query.get("length", [self.default_read_length])[0], self.default_read_length),
                    self.max_read_length,
                ),
            )
            window = {
                "mode": "char",
                "start": start,
                "length": length,
            }
        query.pop("start", None)
        query.pop("length", None)
        query.pop("line_start", None)
        query.pop("line_end", None)
        base_uri = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))
        return base_uri, window

    def _register_sdk_handlers(self) -> None:
        @self._sdk_server.list_resources()
        async def _list_resources(_: types.ListResourcesRequest) -> types.ListResourcesResult:
            return types.ListResourcesResult(resources=self._base_resources())

        @self._sdk_server.list_resource_templates()
        async def _list_resource_templates() -> List[types.ResourceTemplate]:
            return [
                types.ResourceTemplate(
                    uriTemplate="qualcoder://documents/text/{id}",
                    name="Document by id",
                    description=(
                        "Read a text document by source id. Optional window params: start and length, "
                        "or line_start and line_end."
                    ),
                    mimeType="application/json",
                ),
                types.ResourceTemplate(
                    uriTemplate="qualcoder://cases/{id}",
                    name="Case by id",
                    description=(
                        "Read one case by case id, including memo, attributes, and linked files."
                    ),
                    mimeType="application/json",
                ),
                types.ResourceTemplate(
                    uriTemplate="qualcoder://cases/text/{id}{?cursor,max_segments,max_chars,file_ids}",
                    name="Case text segments by case id",
                    description=(
                        "Read text-backed case segments for a case id. Optional query params: "
                        "cursor, max_segments, max_chars, file_ids."
                    ),
                    mimeType="application/json",
                ),
                types.ResourceTemplate(
                    uriTemplate="qualcoder://codes/segments/{cid}",
                    name="Coded text segments by code id",
                    description=(
                        "Read coded text segments for a code id. Optional query params: strategy "
                        "(diverse_by_document|recent_first|sequential), max_segments, max_chars, cursor, file_ids, owner. "
                        "If owner is set, the server reads from code_text instead of code_text_visible."
                    ),
                    mimeType="application/json",
                ),
                types.ResourceTemplate(
                    uriTemplate="qualcoder://vector/search{?q,cursor,file_ids,exclude_cids,score_threshold}",
                    name="Semantic vector search",
                    description=(
                        "Search semantically similar text chunks. Pass one or more q parameters "
                        "(for example ?q=work&q=employment). Optional params: cursor, "
                        "file_ids, exclude_cids, score_threshold."
                    ),
                    mimeType="application/json",
                ),
                types.ResourceTemplate(
                    uriTemplate="qualcoder://search/bm25{?q,cursor,page_size,file_ids,exclude_cids}",
                    name="BM25 search",
                    description=(
                        "Search chunked text lexically using SQLite FTS5 BM25 ranking. "
                        "Pass one or more q parameters. Optional params: cursor, page_size, "
                        "file_ids and exclude_cids."
                    ),
                    mimeType="application/json",
                ),
                types.ResourceTemplate(
                    uriTemplate="qualcoder://search/regex{?pattern,flags,cursor,page_size,file_ids,exclude_cids,context_chars}",
                    name="Regular-expression search",
                    description=(
                        "Search text documents using a regular expression pattern. "
                        "Optional params: flags (imsx), cursor, page_size, file_ids, "
                        "exclude_cids, context_chars."
                    ),
                    mimeType="application/json",
                ),
            ]

        @self._sdk_server.read_resource()
        async def _read_resource(uri: str) -> List[ReadResourceContents]:
            uri_str = str(uri)
            base_uri, window = self._parse_read_window(uri_str)
            payload = self._read_resource_payload(base_uri, window)
            return [ReadResourceContents(content=json.dumps(payload, ensure_ascii=False), mime_type="application/json")]

        @self._sdk_server.list_tools()
        async def _list_tools(_: types.ListToolsRequest) -> types.ListToolsResult:
            return types.ListToolsResult.model_validate(self._list_tools_payload())

        @self._sdk_server.call_tool()
        async def _call_tool(_name: str, _arguments: Dict[str, Any]) -> Dict[str, Any]:
            return self._call_tool_payload(_name, _arguments, "")

        @self._sdk_server.list_prompts()
        async def _list_prompts(_: types.ListPromptsRequest) -> types.ListPromptsResult:
            return types.ListPromptsResult.model_validate(self._list_prompts_payload())

        @self._sdk_server.get_prompt()
        async def _get_prompt(_name: str, _arguments: Optional[Dict[str, str]]) -> types.GetPromptResult:
            return types.GetPromptResult.model_validate(self._get_prompt_payload(_name, _arguments))

    def _read_resource_payload(self, uri: str, window: Dict[str, Any]) -> Dict[str, Any]:
        parts = urlsplit(uri)
        uri_no_query = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
        query = parse_qs(parts.query, keep_blank_values=True)

        if uri_no_query == "qualcoder://codes/tree":
            return self._codes_tree()
        if uri_no_query == "qualcoder://documents":
            return {"documents": self._fetch_text_documents()}
        if uri_no_query == "qualcoder://cases":
            return {"cases": self._fetch_cases()}
        if uri_no_query == "qualcoder://vector/search":
            options = self._parse_vector_search_options(query)
            return self._read_vector_search(options)
        if uri_no_query == "qualcoder://search/bm25":
            options = self._parse_bm25_search_options(query)
            return self._read_bm25_search(options)
        if uri_no_query == "qualcoder://search/regex":
            options = self._parse_regex_search_options(query)
            return self._read_regex_search(options)

        case_text_match = re.fullmatch(r"qualcoder://cases/text/(\d+)", uri_no_query)
        if case_text_match is not None:
            case_id = int(case_text_match.group(1))
            options = self._parse_case_text_options(query)
            return self._read_case_text(case_id, options)

        case_match = re.fullmatch(r"qualcoder://cases/(\d+)", uri_no_query)
        if case_match is not None:
            case_id = int(case_match.group(1))
            return self._read_case(case_id)

        code_segments_match = re.fullmatch(r"qualcoder://codes/segments/(\d+)", uri_no_query)
        if code_segments_match is not None:
            cid = int(code_segments_match.group(1))
            options = self._parse_code_segments_options(query)
            return self._read_code_segments(cid, options)

        doc_match = re.fullmatch(r"qualcoder://documents/text/(\d+)", uri_no_query)
        if doc_match is not None:
            doc_id = int(doc_match.group(1))
            return self._read_document(doc_id, window)

        if str(window.get("mode", "char")) == "line":
            raise ValueError("line_start/line_end are only supported for text document reads.")

        raise ValueError(f"Unknown resource uri: {uri}")

    def _result_response(self, request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error_response(self, request_id: Any, code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    def _base_resources(self) -> List[types.Resource]:
        return [
            types.Resource(
                uri="qualcoder://codes/tree",
                name="Codes and categories",
                description="Code tree with categories and code metadata.",
                mimeType="application/json",
            ),
            types.Resource(
                uri="qualcoder://documents",
                name="Text documents",
                description="List text documents in the project.",
                mimeType="application/json",
            ),
            types.Resource(
                uri="qualcoder://cases",
                name="Cases",
                description="List cases in the project with memo, attributes, and linked-file counts.",
                mimeType="application/json",
            ),
            types.Resource(
                uri="qualcoder://vector/search",
                name="Semantic vector search",
                description="Semantic retrieval over embedded text chunks. Requires query param q. "
                            "Optional filters: file_ids and exclude_cids.",
                mimeType="application/json",
            ),
            types.Resource(
                uri="qualcoder://search/bm25",
                name="BM25 search",
                description="FTS5/BM25 lexical retrieval over text chunks. Requires query param q. "
                            "Optional filters: file_ids and exclude_cids.",
                mimeType="application/json",
            ),
            types.Resource(
                uri="qualcoder://search/regex",
                name="Regular-expression search",
                description="Regex keyword search over text documents. Requires query param pattern. "
                            "Optional filters: file_ids and exclude_cids.",
                mimeType="application/json",
            ),
        ]

    def _list_tools_payload(self) -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": "codes/create_category",
                    "description": (
                        "Create a new code category. Use this only when explicitly needed by the user request."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "memo": {"type": "string"},
                            "supercatid": {"type": ["integer", "null"]},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/create_code",
                    "description": (
                        "Create a new code. Use catid to assign the code to a category, or null for top-level."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "memo": {"type": "string"},
                            "catid": {"type": ["integer", "null"]},
                            "color": {"type": "string"},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/create_text_coding",
                    "description": (
                        "Create one text coding by code id and quoted text in a text document."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "cid": {"type": "integer"},
                            "fid": {"type": "integer"},
                            "quote": {"type": "string"},
                            "memo": {"type": "string"},
                        },
                        "required": ["cid", "fid", "quote"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/preview_delete_category",
                    "description": (
                        "Preview the impact of deleting a category tree recursively. "
                        "Returns affected subtree counts, warnings, and a preview_token for execution."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "catid": {"type": "integer"},
                        },
                        "required": ["catid"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/preview_delete_code",
                    "description": (
                        "Preview the impact of deleting a code and all its codings. "
                        "Returns affected coding counts, warnings, and a preview_token for execution."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "cid": {"type": "integer"},
                        },
                        "required": ["cid"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/rename_category",
                    "description": "Rename an existing category. Requires Full access.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "catid": {"type": "integer"},
                            "new_name": {"type": "string"},
                        },
                        "required": ["catid", "new_name"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/rename_code",
                    "description": "Rename an existing code. Requires Full access.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "cid": {"type": "integer"},
                            "new_name": {"type": "string"},
                        },
                        "required": ["cid", "new_name"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/move_category",
                    "description": (
                        "Move a category tree under another category or to top-level. "
                        "Requires Full access."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "catid": {"type": "integer"},
                            "new_supercatid": {"type": ["integer", "null"]},
                        },
                        "required": ["catid"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/move_code",
                    "description": (
                        "Move a code to another category or to top-level. "
                        "Requires Full access."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "cid": {"type": "integer"},
                            "new_catid": {"type": ["integer", "null"]},
                        },
                        "required": ["cid"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/delete_category",
                    "description": (
                        "Delete a category tree recursively, including descendant categories, codes, and codings. "
                        "Requires Full access and a preview_token from codes/preview_delete_category."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "catid": {"type": "integer"},
                            "preview_token": {"type": "string"},
                        },
                        "required": ["catid", "preview_token"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/delete_code",
                    "description": (
                        "Delete a code and all related codings. "
                        "Requires Full access and a preview_token from codes/preview_delete_code."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "cid": {"type": "integer"},
                            "preview_token": {"type": "string"},
                        },
                        "required": ["cid", "preview_token"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/move_text_coding",
                    "description": "Move one text coding to a different code. Requires Full access.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ctid": {"type": "integer"},
                            "new_cid": {"type": "integer"},
                        },
                        "required": ["ctid", "new_cid"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "codes/delete_text_coding",
                    "description": "Delete one text coding. Requires Full access.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ctid": {"type": "integer"},
                        },
                        "required": ["ctid"],
                        "additionalProperties": False,
                    },
                },
            ]
        }

    def _call_tool_payload(self, name: str, arguments: Optional[Dict[str, Any]], change_set_id: str) -> Dict[str, Any]:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object.")
        tool_name = str(name).strip()
        if tool_name == "":
            raise ValueError("Missing tool name.")
        required_permission = self._tool_required_permission(tool_name)
        if self._current_ai_permissions() < required_permission:
            return self._tool_permission_error(tool_name, required_permission)

        if tool_name == "codes/create_category":
            payload = self._tool_create_category(arguments, change_set_id)
        elif tool_name == "codes/create_code":
            payload = self._tool_create_code(arguments, change_set_id)
        elif tool_name == "codes/create_text_coding":
            payload = self._tool_create_text_coding(arguments, change_set_id)
        elif tool_name == "codes/preview_delete_category":
            payload = self._tool_preview_delete_category(arguments)
        elif tool_name == "codes/preview_delete_code":
            payload = self._tool_preview_delete_code(arguments)
        elif tool_name == "codes/rename_category":
            payload = self._tool_rename_category(arguments, change_set_id)
        elif tool_name == "codes/rename_code":
            payload = self._tool_rename_code(arguments, change_set_id)
        elif tool_name == "codes/move_category":
            payload = self._tool_move_category(arguments, change_set_id)
        elif tool_name == "codes/move_code":
            payload = self._tool_move_code(arguments, change_set_id)
        elif tool_name == "codes/delete_category":
            payload = self._tool_delete_category(arguments, change_set_id)
        elif tool_name == "codes/delete_code":
            payload = self._tool_delete_code(arguments, change_set_id)
        elif tool_name == "codes/move_text_coding":
            payload = self._tool_move_text_coding(arguments, change_set_id)
        elif tool_name == "codes/delete_text_coding":
            payload = self._tool_delete_text_coding(arguments, change_set_id)
        else:
            raise ValueError(f"Unknown tool name: {tool_name}")

        return self._tool_result_payload(payload)

    def _tool_create_category(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        name = " ".join(str(arguments.get("name", "")).split()).strip()
        if name == "":
            raise ValueError("Category name must not be empty.")
        memo = str(arguments.get("memo", "") if arguments.get("memo", "") is not None else "")
        supercatid_raw = arguments.get("supercatid", None)
        supercatid = None
        if supercatid_raw is not None:
            supercatid = self._to_int(supercatid_raw, -1)
            if supercatid <= 0:
                raise ValueError("supercatid must be a positive integer or null.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if supercatid is not None:
                row = cur.execute("SELECT catid FROM code_cat WHERE catid=?", (supercatid,)).fetchone()
                if row is None:
                    raise ValueError(f"Parent category id {supercatid} not found.")

            existing = cur.execute(
                "SELECT catid, owner, ifnull(memo,''), supercatid FROM code_cat WHERE lower(name)=lower(?)",
                (name,),
            ).fetchone()
            if existing is not None:
                return {
                    "tool": "codes/create_category",
                    "created": False,
                    "reason": "already_exists",
                    "category": {
                        "catid": int(existing[0]),
                        "name": name,
                        "owner": existing[1],
                        "memo": existing[2],
                        "supercatid": existing[3],
                    },
                }

            cur.execute(
                "INSERT INTO code_cat (name, memo, owner, date, supercatid) VALUES (?, ?, ?, ?, ?)",
                (name, memo, self.AI_AGENT_OWNER, now, supercatid),
            )
            catid = int(cur.lastrowid)
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False

            self._record_ai_change(
                change_set_id,
                {
                    "type": "create_category",
                    "catid": catid,
                    "name": name,
                    "memo": memo,
                    "supercatid": supercatid,
                    "owner": self.AI_AGENT_OWNER,
                    "created_at": now,
                },
            )
            self._emit_project_table_changes(["code_cat"])
            return {
                "tool": "codes/create_category",
                "created": True,
                "category": {
                    "catid": catid,
                    "name": name,
                    "memo": memo,
                    "owner": self.AI_AGENT_OWNER,
                    "date": now,
                    "supercatid": supercatid,
                },
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_create_code(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        name = " ".join(str(arguments.get("name", "")).split()).strip()
        if name == "":
            raise ValueError("Code name must not be empty.")
        memo = str(arguments.get("memo", "") if arguments.get("memo", "") is not None else "")
        catid_raw = arguments.get("catid", None)
        catid = None
        if catid_raw is not None:
            catid = self._to_int(catid_raw, -1)
            if catid <= 0:
                raise ValueError("catid must be a positive integer or null.")
        color = self._normalize_hex_color(arguments.get("color"))
        if color == "":
            color = "#8A8A8A"

        conn = self._connect()
        try:
            cur = conn.cursor()
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if catid is not None:
                row = cur.execute("SELECT catid FROM code_cat WHERE catid=?", (catid,)).fetchone()
                if row is None:
                    raise ValueError(f"Category id {catid} not found.")

            existing = cur.execute(
                "SELECT cid, owner, ifnull(memo,''), catid, color FROM code_name WHERE lower(name)=lower(?)",
                (name,),
            ).fetchone()
            if existing is not None:
                return {
                    "tool": "codes/create_code",
                    "created": False,
                    "reason": "already_exists",
                    "code": {
                        "cid": int(existing[0]),
                        "name": name,
                        "owner": existing[1],
                        "memo": existing[2],
                        "catid": existing[3],
                        "color": existing[4],
                    },
                }

            cur.execute(
                "INSERT INTO code_name (name, memo, catid, owner, date, color) VALUES (?, ?, ?, ?, ?, ?)",
                (name, memo, catid, self.AI_AGENT_OWNER, now, color),
            )
            cid = int(cur.lastrowid)
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False

            self._record_ai_change(
                change_set_id,
                {
                    "type": "create_code",
                    "cid": cid,
                    "name": name,
                    "memo": memo,
                    "catid": catid,
                    "color": color,
                    "owner": self.AI_AGENT_OWNER,
                    "created_at": now,
                },
            )
            self._emit_project_table_changes(["code_name"])
            return {
                "tool": "codes/create_code",
                "created": True,
                "code": {
                    "cid": cid,
                    "name": name,
                    "memo": memo,
                    "catid": catid,
                    "color": color,
                    "owner": self.AI_AGENT_OWNER,
                    "date": now,
                },
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_create_text_coding(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        cid = self._to_int(arguments.get("cid"), -1)
        fid = self._to_int(arguments.get("fid"), -1)
        quote = str(arguments.get("quote", "") if arguments.get("quote", "") is not None else "").strip()
        memo = str(arguments.get("memo", "") if arguments.get("memo", "") is not None else "")

        if cid <= 0:
            raise ValueError("cid must be a positive integer.")
        if fid <= 0:
            raise ValueError("fid must be a positive integer.")
        if quote == "":
            raise ValueError("quote must not be empty.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

            code_row = cur.execute("SELECT cid, name FROM code_name WHERE cid=?", (cid,)).fetchone()
            if code_row is None:
                raise ValueError(f"Code id {cid} not found.")

            source_row = cur.execute(
                "SELECT id, name, ifnull(fulltext,'') FROM source WHERE id=? AND fulltext IS NOT NULL",
                (fid,),
            ).fetchone()
            if source_row is None:
                raise ValueError(f"Text document id {fid} not found.")
            fulltext = str(source_row[2])

            pos0, pos1 = self._quote_search(quote, fulltext)
            if pos0 < 0 or pos1 <= pos0:
                raise ValueError("quote could not be matched in the document text.")
            seltext = fulltext[pos0:pos1]

            existing = cur.execute(
                "SELECT ctid FROM code_text WHERE cid=? AND fid=? AND pos0=? AND pos1=? AND owner=?",
                (cid, fid, pos0, pos1, self.AI_AGENT_OWNER),
            ).fetchone()
            if existing is not None:
                return {
                    "tool": "codes/create_text_coding",
                    "created": False,
                    "reason": "already_exists",
                    "coding": {
                        "ctid": int(existing[0]),
                        "cid": cid,
                        "fid": fid,
                        "pos0": pos0,
                        "pos1": pos1,
                        "owner": self.AI_AGENT_OWNER,
                    },
                }

            cur.execute(
                "INSERT INTO code_text (cid, fid, seltext, pos0, pos1, owner, date, memo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, fid, seltext, pos0, pos1, self.AI_AGENT_OWNER, now, memo),
            )
            ctid = int(cur.lastrowid)
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False

            self._record_ai_change(
                change_set_id,
                {
                    "type": "create_coding_text",
                    "ctid": ctid,
                    "cid": cid,
                    "fid": fid,
                    "code_name": str(code_row[1] if code_row[1] is not None else ""),
                    "source_name": str(source_row[1] if source_row[1] is not None else ""),
                    "pos0": pos0,
                    "pos1": pos1,
                    "seltext": seltext,
                    "owner": self.AI_AGENT_OWNER,
                    "memo": memo,
                    "created_at": now,
                },
            )
            self._emit_project_table_changes(["code_text"])
            return {
                "tool": "codes/create_text_coding",
                "created": True,
                "coding": {
                    "ctid": ctid,
                    "cid": cid,
                    "fid": fid,
                    "pos0": pos0,
                    "pos1": pos1,
                    "quote": seltext,
                    "owner": self.AI_AGENT_OWNER,
                    "date": now,
                },
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_preview_delete_category(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        catid = self._to_int(arguments.get("catid"), -1)
        conn = self._connect()
        try:
            cur = conn.cursor()
            category = self._fetch_category_row_cur(cur, catid)
            if category is None:
                raise ValueError(f"Category id {catid} not found.")
            subtree = self._collect_category_subtree(cur, catid)
            impact = self._build_category_tree_impact(cur, subtree)
            signature = {"tool": "codes/delete_category", "catid": catid}
            preview_token = self._issue_preview_token("codes/delete_category", signature)
            warnings = [
                _("Deleting this category removes the full subtree, including descendant categories, codes, and codings.")
            ]
            non_ai = int(impact["counts"].get("non_ai_codings", 0))
            if non_ai > 0:
                warnings.append(
                    _("Warning: {count} affected coding(s) are not owned by 'AI Agent'.").format(count=non_ai)
                )
            return {
                "tool": "codes/preview_delete_category",
                "execute_tool": "codes/delete_category",
                "preview_token": preview_token,
                "requires_confirmation": True,
                "risk_level": "high",
                "category": self._category_ref(category),
                "impact": impact,
                "warnings": warnings,
            }
        finally:
            conn.close()

    def _tool_preview_delete_code(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = self._to_int(arguments.get("cid"), -1)
        conn = self._connect()
        try:
            cur = conn.cursor()
            code = self._fetch_code_row_cur(cur, cid)
            if code is None:
                raise ValueError(f"Code id {cid} not found.")
            impact = self._build_code_impact(cur, code)
            signature = {"tool": "codes/delete_code", "cid": cid}
            preview_token = self._issue_preview_token("codes/delete_code", signature)
            warnings = [_("Deleting this code also removes all codings that use it.")]
            non_ai = int(impact["counts"].get("non_ai_codings", 0))
            if non_ai > 0:
                warnings.append(
                    _("Warning: {count} affected coding(s) are not owned by 'AI Agent'.").format(count=non_ai)
                )
            return {
                "tool": "codes/preview_delete_code",
                "execute_tool": "codes/delete_code",
                "preview_token": preview_token,
                "requires_confirmation": True,
                "risk_level": "high",
                "code": self._code_ref(code),
                "category": self._category_ref(
                    self._fetch_category_row_cur(cur, code.get("catid", None))
                ),
                "impact": impact,
                "warnings": warnings,
            }
        finally:
            conn.close()

    def _tool_rename_category(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        catid = self._to_int(arguments.get("catid"), -1)
        new_name = " ".join(str(arguments.get("new_name", "")).split()).strip()
        if catid <= 0:
            raise ValueError("catid must be a positive integer.")
        if new_name == "":
            raise ValueError("new_name must not be empty.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            category = self._fetch_category_row_cur(cur, catid)
            if category is None:
                raise ValueError(f"Category id {catid} not found.")
            old_name = str(category.get("name", ""))
            if old_name == new_name:
                return {
                    "tool": "codes/rename_category",
                    "renamed": False,
                    "reason": "unchanged",
                    "category": self._category_ref(category),
                }
            existing = cur.execute(
                "SELECT catid FROM code_cat WHERE lower(name)=lower(?) AND catid != ?",
                (new_name, catid),
            ).fetchone()
            if existing is not None:
                raise ValueError(f'Another category already uses the name "{new_name}".')

            cur.execute("UPDATE code_cat SET name=? WHERE catid=?", (new_name, catid))
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            self._record_ai_change(
                change_set_id,
                {
                    "type": "rename_category",
                    "catid": catid,
                    "old_name": old_name,
                    "new_name": new_name,
                },
            )
            self._emit_project_table_changes(["code_cat"])
            return {
                "tool": "codes/rename_category",
                "renamed": True,
                "category": {"catid": catid, "old_name": old_name, "new_name": new_name},
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_rename_code(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        cid = self._to_int(arguments.get("cid"), -1)
        new_name = " ".join(str(arguments.get("new_name", "")).split()).strip()
        if cid <= 0:
            raise ValueError("cid must be a positive integer.")
        if new_name == "":
            raise ValueError("new_name must not be empty.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            code = self._fetch_code_row_cur(cur, cid)
            if code is None:
                raise ValueError(f"Code id {cid} not found.")
            old_name = str(code.get("name", ""))
            if old_name == new_name:
                return {
                    "tool": "codes/rename_code",
                    "renamed": False,
                    "reason": "unchanged",
                    "code": self._code_ref(code),
                }
            existing = cur.execute(
                "SELECT cid FROM code_name WHERE lower(name)=lower(?) AND cid != ?",
                (new_name, cid),
            ).fetchone()
            if existing is not None:
                raise ValueError(f'Another code already uses the name "{new_name}".')

            cur.execute("UPDATE code_name SET name=? WHERE cid=?", (new_name, cid))
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            self._record_ai_change(
                change_set_id,
                {
                    "type": "rename_code",
                    "cid": cid,
                    "old_name": old_name,
                    "new_name": new_name,
                },
            )
            self._emit_project_table_changes(["code_name"])
            return {
                "tool": "codes/rename_code",
                "renamed": True,
                "code": {"cid": cid, "old_name": old_name, "new_name": new_name},
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_move_category(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        catid = self._to_int(arguments.get("catid"), -1)
        new_supercatid_raw = arguments.get("new_supercatid", None)
        new_supercatid = None
        if new_supercatid_raw is not None:
            new_supercatid = self._to_int(new_supercatid_raw, -1)
            if new_supercatid <= 0:
                raise ValueError("new_supercatid must be a positive integer or null.")
        conn = self._connect()
        try:
            cur = conn.cursor()
            category = self._fetch_category_row_cur(cur, catid)
            if category is None:
                raise ValueError(f"Category id {catid} not found.")
            if new_supercatid is not None and self._fetch_category_row_cur(cur, new_supercatid) is None:
                raise ValueError(f"Target category id {new_supercatid} not found.")
            subtree = self._collect_category_subtree(cur, catid)
            subtree_ids = [int(item["catid"]) for item in subtree["categories"]]
            if new_supercatid is not None and new_supercatid in subtree_ids:
                raise ValueError("A category cannot be moved into its own subtree.")
            old_supercatid = category.get("supercatid", None)
            if old_supercatid == new_supercatid:
                return {
                    "tool": "codes/move_category",
                    "moved": False,
                    "reason": "unchanged",
                    "category": self._category_ref(category),
                }
            cur.execute("UPDATE code_cat SET supercatid=? WHERE catid=?", (new_supercatid, catid))
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            impact = self._build_category_tree_impact(cur, subtree)
            self._record_ai_change(
                change_set_id,
                {
                    "type": "move_category_tree",
                    "root_catid": catid,
                    "name": str(category.get("name", "")),
                    "before": {"supercatid": old_supercatid},
                    "after": {"supercatid": new_supercatid},
                    "impact": impact,
                },
            )
            self._emit_project_table_changes(["code_cat"])
            return {
                "tool": "codes/move_category",
                "moved": True,
                "category": self._category_ref(category),
                "old_supercatid": old_supercatid,
                "new_supercatid": new_supercatid,
                "impact": impact,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_move_code(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        cid = self._to_int(arguments.get("cid"), -1)
        new_catid_raw = arguments.get("new_catid", None)
        new_catid = None
        if new_catid_raw is not None:
            new_catid = self._to_int(new_catid_raw, -1)
            if new_catid <= 0:
                raise ValueError("new_catid must be a positive integer or null.")
        conn = self._connect()
        try:
            cur = conn.cursor()
            code = self._fetch_code_row_cur(cur, cid)
            if code is None:
                raise ValueError(f"Code id {cid} not found.")
            if new_catid is not None and self._fetch_category_row_cur(cur, new_catid) is None:
                raise ValueError(f"Target category id {new_catid} not found.")
            old_catid = code.get("catid", None)
            if old_catid == new_catid:
                return {
                    "tool": "codes/move_code",
                    "moved": False,
                    "reason": "unchanged",
                    "code": self._code_ref(code),
                }
            cur.execute("UPDATE code_name SET catid=? WHERE cid=?", (new_catid, cid))
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            impact = self._build_code_impact(cur, code)
            self._record_ai_change(
                change_set_id,
                {
                    "type": "move_code",
                    "cid": cid,
                    "name": str(code.get("name", "")),
                    "before": {"catid": old_catid},
                    "after": {"catid": new_catid},
                    "impact": impact,
                },
            )
            self._emit_project_table_changes(["code_name"])
            return {
                "tool": "codes/move_code",
                "moved": True,
                "code": self._code_ref(code),
                "old_catid": old_catid,
                "new_catid": new_catid,
                "impact": impact,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_delete_category(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        catid = self._to_int(arguments.get("catid"), -1)
        signature = {"tool": "codes/delete_category", "catid": catid}
        self._consume_preview_token("codes/delete_category", signature, arguments.get("preview_token", ""))

        conn = self._connect()
        try:
            cur = conn.cursor()
            category = self._fetch_category_row_cur(cur, catid)
            if category is None:
                raise ValueError(f"Category id {catid} not found.")
            subtree = self._collect_category_subtree(cur, catid)
            impact = self._build_category_tree_impact(cur, subtree)
            snapshot = self._build_category_tree_snapshot(cur, subtree)
            code_ids = [int(item["cid"]) for item in subtree["codes"]]
            category_ids = [int(item["catid"]) for item in subtree["categories"]]
            self._delete_codings_for_code_ids(cur, code_ids)
            if len(code_ids) > 0:
                cur.execute(
                    "DELETE FROM code_name WHERE cid IN (" + ",".join(["?"] * len(code_ids)) + ")",
                    tuple(code_ids),
                )
            if len(category_ids) > 0:
                cur.execute(
                    "DELETE FROM code_cat WHERE catid IN (" + ",".join(["?"] * len(category_ids)) + ")",
                    tuple(category_ids),
                )
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            self._record_ai_change(
                change_set_id,
                {
                    "type": "delete_category_tree",
                    "root_catid": catid,
                    "name": str(category.get("name", "")),
                    "snapshot": snapshot,
                    "impact": impact,
                },
            )
            self._emit_project_table_changes(self._snapshot_changed_table_names(snapshot))
            return {
                "tool": "codes/delete_category",
                "deleted": True,
                "category": self._category_ref(category),
                "impact": impact,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_delete_code(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        cid = self._to_int(arguments.get("cid"), -1)
        signature = {"tool": "codes/delete_code", "cid": cid}
        self._consume_preview_token("codes/delete_code", signature, arguments.get("preview_token", ""))

        conn = self._connect()
        try:
            cur = conn.cursor()
            code = self._fetch_code_row_cur(cur, cid)
            if code is None:
                raise ValueError(f"Code id {cid} not found.")
            impact = self._build_code_impact(cur, code)
            snapshot = self._build_code_snapshot(cur, cid)
            self._delete_codings_for_code_ids(cur, [cid])
            cur.execute("DELETE FROM code_name WHERE cid=?", (cid,))
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            self._record_ai_change(
                change_set_id,
                {
                    "type": "delete_code",
                    "cid": cid,
                    "name": str(code.get("name", "")),
                    "snapshot": snapshot,
                    "impact": impact,
                },
            )
            self._emit_project_table_changes(self._snapshot_changed_table_names(snapshot))
            return {
                "tool": "codes/delete_code",
                "deleted": True,
                "code": self._code_ref(code),
                "impact": impact,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_move_text_coding(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        ctid = self._to_int(arguments.get("ctid"), -1)
        new_cid = self._to_int(arguments.get("new_cid"), -1)
        if ctid <= 0:
            raise ValueError("ctid must be a positive integer.")
        if new_cid <= 0:
            raise ValueError("new_cid must be a positive integer.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            coding = self._fetch_text_coding_row_cur(cur, ctid)
            if coding is None:
                raise ValueError(f"Text coding id {ctid} not found.")
            old_cid = int(coding.get("cid", -1))
            if self._fetch_code_row_cur(cur, new_cid) is None:
                raise ValueError(f"Target code id {new_cid} not found.")
            if old_cid == new_cid:
                return {
                    "tool": "codes/move_text_coding",
                    "moved": False,
                    "reason": "unchanged",
                    "coding": {"ctid": ctid, "cid": old_cid},
                }
            cur.execute("UPDATE code_text SET cid=? WHERE ctid=?", (new_cid, ctid))
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            self._record_ai_change(
                change_set_id,
                {
                    "type": "move_coding_text",
                    "ctid": ctid,
                    "fid": int(coding.get("fid", -1)),
                    "before": {"cid": old_cid},
                    "after": {"cid": new_cid},
                },
            )
            self._emit_project_table_changes(["code_text"])
            return {
                "tool": "codes/move_text_coding",
                "moved": True,
                "coding": {"ctid": ctid, "old_cid": old_cid, "new_cid": new_cid},
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _tool_delete_text_coding(self, arguments: Dict[str, Any], change_set_id: str) -> Dict[str, Any]:
        ctid = self._to_int(arguments.get("ctid"), -1)
        if ctid <= 0:
            raise ValueError("ctid must be a positive integer.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            coding = self._fetch_text_coding_row_cur(cur, ctid)
            if coding is None:
                raise ValueError(f"Text coding id {ctid} not found.")
            snapshot = {"tables": {"code_text": [dict(coding)]}}
            cur.execute("DELETE FROM code_text WHERE ctid=?", (ctid,))
            conn.commit()
            if hasattr(self.app, "delete_backup"):
                self.app.delete_backup = False
            self._record_ai_change(
                change_set_id,
                {
                    "type": "delete_coding_text",
                    "ctid": ctid,
                    "snapshot": snapshot,
                },
            )
            self._emit_project_table_changes(["code_text"])
            return {
                "tool": "codes/delete_text_coding",
                "deleted": True,
                "coding": {
                    "ctid": ctid,
                    "cid": int(coding.get("cid", -1)),
                    "fid": int(coding.get("fid", -1)),
                },
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _category_ref(self, category: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(category, dict):
            return None
        return {
            "catid": category.get("catid", None),
            "name": str(category.get("name", "")),
            "owner": str(category.get("owner", "")),
        }

    def _code_ref(self, code: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(code, dict):
            return None
        return {
            "cid": code.get("cid", None),
            "name": str(code.get("name", "")),
            "owner": str(code.get("owner", "")),
        }

    def _table_exists_cur(self, cur: sqlite3.Cursor, table_name: str) -> bool:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cur.fetchone() is not None

    def _fetchone_dict_cur(self, cur: sqlite3.Cursor, sql: str,
                           params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        columns = [str(item[0]) for item in (cur.description or [])]
        return {columns[i]: row[i] for i in range(min(len(columns), len(row)))}

    def _fetchall_dict_cur(self, cur: sqlite3.Cursor, sql: str,
                           params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        cur.execute(sql, params)
        rows = cur.fetchall()
        columns = [str(item[0]) for item in (cur.description or [])]
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append({columns[i]: row[i] for i in range(min(len(columns), len(row)))})
        return result

    def _fetch_category_row_cur(self, cur: sqlite3.Cursor, catid: Any) -> Optional[Dict[str, Any]]:
        catid_i = self._to_int(catid, -1)
        if catid_i <= 0:
            return None
        return self._fetchone_dict_cur(
            cur,
            "SELECT catid, name, ifnull(memo,'') as memo, owner, date, supercatid FROM code_cat WHERE catid=?",
            (catid_i,),
        )

    def _fetch_code_row_cur(self, cur: sqlite3.Cursor, cid: Any) -> Optional[Dict[str, Any]]:
        cid_i = self._to_int(cid, -1)
        if cid_i <= 0:
            return None
        return self._fetchone_dict_cur(
            cur,
            "SELECT cid, name, ifnull(memo,'') as memo, catid, color, owner, date FROM code_name WHERE cid=?",
            (cid_i,),
        )

    def _fetch_text_coding_row_cur(self, cur: sqlite3.Cursor, ctid: Any) -> Optional[Dict[str, Any]]:
        ctid_i = self._to_int(ctid, -1)
        if ctid_i <= 0:
            return None
        return self._fetchone_dict_cur(
            cur,
            "SELECT ctid, cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important "
            "FROM code_text WHERE ctid=?",
            (ctid_i,),
        )

    def _collect_category_subtree(self, cur: sqlite3.Cursor, root_catid: int) -> Dict[str, Any]:
        categories = self._fetchall_dict_cur(
            cur,
            "SELECT catid, name, ifnull(memo,'') as memo, owner, date, supercatid FROM code_cat ORDER BY catid",
        )
        by_parent: Dict[Any, List[Dict[str, Any]]] = {}
        root_category = None
        for category in categories:
            if int(category.get("catid", -1)) == root_catid:
                root_category = category
            by_parent.setdefault(category.get("supercatid", None), []).append(category)
        if root_category is None:
            raise ValueError(f"Category id {root_catid} not found.")

        subtree_categories: List[Dict[str, Any]] = []
        queue: List[Dict[str, Any]] = [root_category]
        seen = set()
        while len(queue) > 0:
            category = queue.pop(0)
            catid = int(category.get("catid", -1))
            if catid in seen or catid <= 0:
                continue
            seen.add(catid)
            subtree_categories.append(category)
            for child in by_parent.get(catid, []):
                queue.append(child)

        category_ids = [int(item["catid"]) for item in subtree_categories]
        codes: List[Dict[str, Any]] = []
        if len(category_ids) > 0:
            placeholders = ",".join(["?"] * len(category_ids))
            codes = self._fetchall_dict_cur(
                cur,
                "SELECT cid, name, ifnull(memo,'') as memo, catid, color, owner, date "
                f"FROM code_name WHERE catid IN ({placeholders}) ORDER BY cid",
                tuple(category_ids),
            )
        return {
            "root_category": root_category,
            "categories": subtree_categories,
            "codes": codes,
        }

    def _collect_table_rows_by_cids(self, cur: sqlite3.Cursor, table_name: str,
                                    cid_values: List[int]) -> List[Dict[str, Any]]:
        if len(cid_values) == 0 or not self._table_exists_cur(cur, table_name):
            return []
        placeholders = ",".join(["?"] * len(cid_values))
        return self._fetchall_dict_cur(
            cur,
            f"SELECT * FROM {table_name} WHERE cid IN ({placeholders}) ORDER BY 1",
            tuple(cid_values),
        )

    def _count_codings_for_code_ids(self, cur: sqlite3.Cursor, cid_values: List[int]) -> Dict[str, int]:
        counts = {"code_text": 0, "code_av": 0, "code_image": 0, "total": 0, "non_ai_codings": 0}
        if len(cid_values) == 0:
            return counts
        placeholders = ",".join(["?"] * len(cid_values))
        params = tuple(cid_values)
        for table_name in ("code_text", "code_av", "code_image"):
            if not self._table_exists_cur(cur, table_name):
                continue
            cur.execute(
                f"SELECT count(*), sum(case when owner != ? then 1 else 0 end) "
                f"FROM {table_name} WHERE cid IN ({placeholders})",
                tuple([self.AI_AGENT_OWNER, *params]),
            )
            row = cur.fetchone()
            table_count = int((row or [0])[0] or 0)
            table_non_ai = int((row or [0, 0])[1] or 0)
            counts[table_name] = table_count
            counts["total"] += table_count
            counts["non_ai_codings"] += table_non_ai
        return counts

    def _build_category_tree_impact(self, cur: sqlite3.Cursor, subtree: Dict[str, Any]) -> Dict[str, Any]:
        categories = subtree.get("categories", [])
        codes = subtree.get("codes", [])
        code_ids = [int(item.get("cid", -1)) for item in codes if int(item.get("cid", -1)) > 0]
        coding_counts = self._count_codings_for_code_ids(cur, code_ids)
        return {
            "counts": {
                "categories": len(categories),
                "codes": len(codes),
                "text_codings": int(coding_counts.get("code_text", 0)),
                "av_codings": int(coding_counts.get("code_av", 0)),
                "image_codings": int(coding_counts.get("code_image", 0)),
                "total_codings": int(coding_counts.get("total", 0)),
                "non_ai_codings": int(coding_counts.get("non_ai_codings", 0)),
            },
            "examples": {
                "categories": [str(item.get("name", "")) for item in categories[:5]],
                "codes": [str(item.get("name", "")) for item in codes[:5]],
            },
        }

    def _build_code_impact(self, cur: sqlite3.Cursor, code: Dict[str, Any]) -> Dict[str, Any]:
        cid = int(code.get("cid", -1))
        coding_counts = self._count_codings_for_code_ids(cur, [cid] if cid > 0 else [])
        return {
            "counts": {
                "codes": 1,
                "text_codings": int(coding_counts.get("code_text", 0)),
                "av_codings": int(coding_counts.get("code_av", 0)),
                "image_codings": int(coding_counts.get("code_image", 0)),
                "total_codings": int(coding_counts.get("total", 0)),
                "non_ai_codings": int(coding_counts.get("non_ai_codings", 0)),
            },
            "examples": {
                "codes": [str(code.get("name", ""))],
            },
        }

    def _build_code_snapshot(self, cur: sqlite3.Cursor, cid: int) -> Dict[str, Any]:
        code = self._fetch_code_row_cur(cur, cid)
        if code is None:
            raise ValueError(f"Code id {cid} not found.")
        return {
            "tables": {
                "code_name": [dict(code)],
                "code_text": self._collect_table_rows_by_cids(cur, "code_text", [cid]),
                "code_av": self._collect_table_rows_by_cids(cur, "code_av", [cid]),
                "code_image": self._collect_table_rows_by_cids(cur, "code_image", [cid]),
            }
        }

    def _build_category_tree_snapshot(self, cur: sqlite3.Cursor, subtree: Dict[str, Any]) -> Dict[str, Any]:
        categories = [dict(item) for item in subtree.get("categories", [])]
        codes = [dict(item) for item in subtree.get("codes", [])]
        code_ids = [int(item.get("cid", -1)) for item in codes if int(item.get("cid", -1)) > 0]
        return {
            "tables": {
                "code_cat": categories,
                "code_name": codes,
                "code_text": self._collect_table_rows_by_cids(cur, "code_text", code_ids),
                "code_av": self._collect_table_rows_by_cids(cur, "code_av", code_ids),
                "code_image": self._collect_table_rows_by_cids(cur, "code_image", code_ids),
            }
        }

    def _delete_codings_for_code_ids(self, cur: sqlite3.Cursor, code_ids: List[int]) -> None:
        if len(code_ids) == 0:
            return
        placeholders = ",".join(["?"] * len(code_ids))
        params = tuple(code_ids)
        for table_name in ("code_text", "code_av", "code_image"):
            if not self._table_exists_cur(cur, table_name):
                continue
            cur.execute(f"DELETE FROM {table_name} WHERE cid IN ({placeholders})", params)

    def _normalize_hex_color(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", text) is None:
            return ""
        return text.upper()

    def _quote_search(self, quote: str, fulltext: str) -> Tuple[int, int]:
        """Find quote boundaries, preferring ai_llm.ai_quote_search with graceful fallback."""

        try:
            from .ai_llm import ai_quote_search as _ai_quote_search
            return _ai_quote_search(quote, fulltext)
        except Exception:
            quote_text = str(quote).strip()
            if quote_text == "":
                return -1, -1
            start = fulltext.find(quote_text)
            if start < 0:
                return -1, -1
            return start, start + len(quote_text)

    def _record_ai_change(self, change_set_id: str, operation: Dict[str, Any]) -> None:
        ai = getattr(self.app, "ai", None)
        if ai is not None and hasattr(ai, "record_ai_change"):
            ai.record_ai_change(change_set_id, operation)

    def _codes_tree(self) -> Dict[str, Any]:
        categories = []
        for row in self._fetchall(
            "SELECT catid, name, ifnull(memo,''), owner, supercatid "
            "FROM code_cat ORDER BY lower(name)"
        ):
            categories.append(
                {
                    "catid": row[0],
                    "name": row[1],
                    "memo": row[2],
                    "owner": row[3],
                    "supercatid": row[4],
                }
            )

        codes = []
        for row in self._fetchall(
            "SELECT cid, name, ifnull(memo,''), catid, color, owner "
            "FROM code_name ORDER BY lower(name)"
        ):
            codes.append(
                {
                    "cid": row[0],
                    "name": row[1],
                    "memo": row[2],
                    "catid": row[3],
                    "color": row[4],
                    "owner": row[5],
                }
            )
        speaker_prefix = "ðŸ“Œ "
        speaker_categories = []
        for cat in categories:
            cat_name = str(cat.get("name", ""))
            if cat_name.startswith(speaker_prefix):
                speaker_categories.append({"catid": cat["catid"], "name": cat_name})

        structure_rules = {
            "codes_are_leaves": True,
            "codes_can_have_subcodes": False,
            "categories_can_contain_codes": True,
            "categories_can_have_subcategories": True,
        }
        special_conventions = {
            "speaker_category_prefix": speaker_prefix,
            "speaker_category_name_is_localized": True,
            "speaker_category_optional": True,
            "speaker_category_present": len(speaker_categories) > 0,
            "speaker_categories": speaker_categories,
            "speaker_category_ids": [item["catid"] for item in speaker_categories],
        }
        return {
            "categories": categories,
            "codes": codes,
            "structure_rules": structure_rules,
            "special_conventions": special_conventions,
        }

    def _fetch_text_documents(self) -> List[Dict[str, Any]]:
        docs = []
        for row in self._fetchall(
            "SELECT id, name, ifnull(memo,''), owner, date, ifnull(length(fulltext),0) "
            "FROM source WHERE fulltext is not null ORDER BY lower(name)"
        ):
            docs.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "memo": row[2],
                    "owner": row[3],
                    "date": row[4],
                    "length": row[5],
                }
            )
        return docs

    def _fetch_case_name(self, case_id: int) -> Optional[str]:
        row = self._fetchone("SELECT name FROM cases WHERE caseid=?", (case_id,))
        if row is None:
            return None
        return row[0]

    def _fetch_case_attributes(self, case_ids: List[int]) -> Dict[int, Dict[str, str]]:
        normalized_ids: List[int] = []
        for case_id in case_ids:
            case_id_i = self._to_int(case_id, -1)
            if case_id_i > 0:
                normalized_ids.append(case_id_i)
        normalized_ids = sorted(set(normalized_ids))
        if len(normalized_ids) == 0:
            return {}
        placeholders = ",".join(["?"] * len(normalized_ids))
        rows = self._fetchall(
            "SELECT id, name, ifnull(value,'') FROM attribute "
            f"WHERE attr_type='case' AND id IN ({placeholders}) "
            "ORDER BY id, lower(name)",
            tuple(normalized_ids),
        )
        result: Dict[int, Dict[str, str]] = {}
        for row in rows:
            case_id = self._to_int(row[0], -1)
            if case_id <= 0:
                continue
            if case_id not in result:
                result[case_id] = {}
            attr_name = "" if row[1] is None else str(row[1])
            result[case_id][attr_name] = "" if row[2] is None else str(row[2])
        return result

    def _fetch_case_link_counts(self, case_ids: List[int]) -> Dict[int, Dict[str, int]]:
        normalized_ids: List[int] = []
        for case_id in case_ids:
            case_id_i = self._to_int(case_id, -1)
            if case_id_i > 0:
                normalized_ids.append(case_id_i)
        normalized_ids = sorted(set(normalized_ids))
        if len(normalized_ids) == 0:
            return {}
        placeholders = ",".join(["?"] * len(normalized_ids))
        rows = self._fetchall(
            "SELECT caseid, count(*), count(distinct fid) "
            f"FROM case_text WHERE caseid IN ({placeholders}) GROUP BY caseid",
            tuple(normalized_ids),
        )
        result: Dict[int, Dict[str, int]] = {}
        for row in rows:
            case_id = self._to_int(row[0], -1)
            if case_id <= 0:
                continue
            result[case_id] = {
                "text_segment_count": self._to_int(row[1], 0),
                "file_count": self._to_int(row[2], 0),
            }
        return result

    def _fetch_cases(self) -> List[Dict[str, Any]]:
        rows = self._fetchall(
            "SELECT caseid, name, ifnull(memo,''), owner, date FROM cases ORDER BY lower(name)"
        )
        case_ids = [self._to_int(row[0], -1) for row in rows]
        attributes_by_case = self._fetch_case_attributes(case_ids)
        counts_by_case = self._fetch_case_link_counts(case_ids)
        result: List[Dict[str, Any]] = []
        for row in rows:
            case_id = self._to_int(row[0], -1)
            counts = counts_by_case.get(case_id, {})
            result.append(
                {
                    "id": case_id,
                    "name": row[1],
                    "memo": row[2],
                    "owner": row[3],
                    "date": row[4],
                    "file_count": self._to_int(counts.get("file_count", 0), 0),
                    "text_segment_count": self._to_int(counts.get("text_segment_count", 0), 0),
                    "attributes": attributes_by_case.get(case_id, {}),
                }
            )
        return result

    def _fetch_source_name(self, doc_id: int) -> Optional[str]:
        row = self._fetchone("SELECT name FROM source WHERE id=?", (doc_id,))
        if row is None:
            return None
        return row[0]

    def _fetch_category_name(self, catid: int) -> Optional[str]:
        row = self._fetchone("SELECT name FROM code_cat WHERE catid=?", (catid,))
        if row is None:
            return None
        return row[0]

    def _fetch_code_name(self, cid: int) -> Optional[str]:
        row = self._fetchone("SELECT name FROM code_name WHERE cid=?", (cid,))
        if row is None:
            return None
        return row[0]

    def _view_exists(self, view_name: str) -> bool:
        row = self._fetchone(
            "SELECT name FROM sqlite_master WHERE type='view' AND name=?",
            (view_name,),
        )
        return row is not None

    def _parse_code_segments_options(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        strategy = str(query.get("strategy", ["diverse_by_document"])[0]).strip()
        allowed = {"diverse_by_document", "recent_first", "sequential"}
        if strategy not in allowed:
            raise ValueError(
                "Invalid strategy. Allowed values are: diverse_by_document, recent_first, sequential."
            )

        max_segments = self._to_int(
            query.get("max_segments", [self.default_segments_max_segments])[0],
            self.default_segments_max_segments,
        )
        max_segments = max(1, min(max_segments, self.max_segments_limit))

        max_chars = self._to_int(
            query.get("max_chars", [self.default_segments_max_chars])[0],
            self.default_segments_max_chars,
        )
        max_chars = max(1, min(max_chars, self.max_segments_chars_limit))

        cursor = self._to_int(query.get("cursor", [0])[0], 0)
        cursor = max(0, cursor)

        file_ids: List[int] = []
        for raw in query.get("file_ids", []):
            parts = [p.strip() for p in str(raw).split(",")]
            for part in parts:
                if part == "":
                    continue
                file_ids.append(max(0, self._to_int(part, -1)))
        file_ids = [fid for fid in file_ids if fid > 0]
        owners = self._parse_string_list_options(query, ("owner", "owners"))

        return {
            "strategy": strategy,
            "max_segments": max_segments,
            "max_chars": max_chars,
            "cursor": cursor,
            "file_ids": file_ids,
            "owners": owners,
        }

    def _parse_case_text_options(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        max_segments = self._to_int(
            query.get("max_segments", [self.default_segments_max_segments])[0],
            self.default_segments_max_segments,
        )
        max_segments = max(1, min(max_segments, self.max_segments_limit))

        max_chars = self._to_int(
            query.get("max_chars", [self.default_segments_max_chars])[0],
            self.default_segments_max_chars,
        )
        max_chars = max(1, min(max_chars, self.max_segments_chars_limit))

        cursor = self._to_int(query.get("cursor", [0])[0], 0)
        cursor = max(0, cursor)

        file_ids = self._parse_positive_int_list_options(query, ("file_ids",))
        return {
            "max_segments": max_segments,
            "max_chars": max_chars,
            "cursor": cursor,
            "file_ids": file_ids,
        }

    def _parse_string_list_options(self, query: Dict[str, List[str]], keys: Tuple[str, ...]) -> List[str]:
        values: List[str] = []
        for key in keys:
            for raw in query.get(key, []):
                parts = [p.strip() for p in str(raw).split(",")]
                for part in parts:
                    if part != "":
                        values.append(part)
        unique_values: List[str] = []
        seen: set[str] = set()
        for value in values:
            norm = value.casefold()
            if norm in seen:
                continue
            seen.add(norm)
            unique_values.append(value)
        return unique_values

    def _parse_positive_int_list_options(self, query: Dict[str, List[str]], keys: Tuple[str, ...]) -> List[int]:
        values: List[int] = []
        for key in keys:
            for raw in query.get(key, []):
                parts = [p.strip() for p in str(raw).split(",")]
                for part in parts:
                    if part == "":
                        continue
                    val = self._to_int(part, -1)
                    if val > 0:
                        values.append(val)
        # Keep input order while removing duplicates.
        unique_values: List[int] = []
        seen = set()
        for val in values:
            if val in seen:
                continue
            seen.add(val)
            unique_values.append(val)
        return unique_values

    def _parse_vector_search_options(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        query_strings: List[str] = []
        for key in ("q", "query", "queries"):
            values = query.get(key, [])
            for raw in values:
                raw_text = str(raw).strip()
                if raw_text == "":
                    continue
                for line in raw_text.splitlines():
                    line_clean = " ".join(line.split()).strip()
                    if line_clean != "":
                        query_strings.append(line_clean)

        # Keep order, remove duplicates case-insensitively.
        deduped_queries: List[str] = []
        seen_queries: set[str] = set()
        for q in query_strings:
            q_key = q.lower()
            if q_key in seen_queries:
                continue
            seen_queries.add(q_key)
            deduped_queries.append(q)

        if len(deduped_queries) == 0:
            raise ValueError("Missing vector search query. Use at least one ?q=... parameter.")

        cursor = self._to_int(query.get("cursor", [0])[0], 0)
        cursor = max(0, cursor)

        score_threshold = self._to_float(
            query.get("score_threshold", [self.default_vector_score_threshold])[0],
            self.default_vector_score_threshold,
        )
        score_threshold = max(0.0, min(score_threshold, 1.0))

        file_ids = self._parse_positive_int_list_options(query, ("file_ids",))
        exclude_cids = self._parse_positive_int_list_options(query, ("exclude_cids", "exclude_code_ids", "cids"))

        return {
            "queries": deduped_queries,
            "cursor": cursor,
            "file_ids": file_ids,
            "exclude_cids": exclude_cids,
            "score_threshold": score_threshold,
        }

    def _parse_bm25_search_options(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        query_strings: List[str] = []
        for key in ("q", "query", "queries"):
            values = query.get(key, [])
            for raw in values:
                raw_text = str(raw).strip()
                if raw_text == "":
                    continue
                for line in raw_text.splitlines():
                    line_clean = " ".join(line.split()).strip()
                    if line_clean != "":
                        query_strings.append(line_clean)

        deduped_queries: List[str] = []
        seen_queries: set[str] = set()
        for q in query_strings:
            q_key = q.lower()
            if q_key in seen_queries:
                continue
            seen_queries.add(q_key)
            deduped_queries.append(q)

        if len(deduped_queries) == 0:
            raise ValueError("Missing BM25 search query. Use at least one ?q=... parameter.")

        cursor = self._to_int(query.get("cursor", [0])[0], 0)
        cursor = max(0, cursor)

        page_size = self._to_int(query.get("page_size", [self.default_bm25_page_size])[0], self.default_bm25_page_size)
        page_size = max(1, min(page_size, self.max_bm25_page_size))

        file_ids = self._parse_positive_int_list_options(query, ("file_ids",))
        exclude_cids = self._parse_positive_int_list_options(query, ("exclude_cids", "exclude_code_ids", "cids"))

        return {
            "queries": deduped_queries,
            "cursor": cursor,
            "page_size": page_size,
            "file_ids": file_ids,
            "exclude_cids": exclude_cids,
        }

    def _parse_regex_search_options(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        pattern = ""
        for key in ("pattern", "q", "query"):
            values = query.get(key, [])
            if len(values) == 0:
                continue
            pattern = str(values[0]).strip()
            if pattern != "":
                break
        if pattern == "":
            raise ValueError("Missing regex pattern. Use ?pattern=...")

        flags = str(query.get("flags", [""])[0]).strip().lower()
        flags = "".join(ch for ch in flags if ch in ("i", "m", "s", "x"))

        cursor = self._to_int(query.get("cursor", [0])[0], 0)
        cursor = max(0, cursor)

        page_size = self._to_int(query.get("page_size", [self.default_regex_page_size])[0], self.default_regex_page_size)
        page_size = max(1, min(page_size, self.max_regex_page_size))

        context_chars = self._to_int(
            query.get("context_chars", [self.default_regex_context_chars])[0],
            self.default_regex_context_chars,
        )
        context_chars = max(0, min(context_chars, self.max_regex_context_chars))

        file_ids = self._parse_positive_int_list_options(query, ("file_ids",))
        exclude_cids = self._parse_positive_int_list_options(query, ("exclude_cids", "exclude_code_ids", "cids"))

        return {
            "pattern": pattern,
            "flags": flags,
            "cursor": cursor,
            "page_size": page_size,
            "context_chars": context_chars,
            "file_ids": file_ids,
            "exclude_cids": exclude_cids,
        }

    def _read_vector_search(self, options: Dict[str, Any]) -> Dict[str, Any]:
        ai = getattr(self.app, "ai", None)
        if ai is None:
            raise RuntimeError("AI integration is not initialized.")
        vectorstore = getattr(ai, "sources_vectorstore", None)
        if vectorstore is None or getattr(vectorstore, "faiss_db", None) is None:
            raise RuntimeError("Vectorstore is not initialized.")
        is_ready_fn = getattr(vectorstore, "is_ready", None)
        if callable(is_ready_fn) and not is_ready_fn():
            raise RuntimeError("Vectorstore is currently updating. Please try again shortly.")

        queries = options.get("queries", [])
        if not isinstance(queries, list) or len(queries) == 0:
            raise ValueError("Missing vector search query.")
        cursor = max(0, self._to_int(options.get("cursor", 0), 0))
        page_size = self.default_vector_page_size
        file_ids = options.get("file_ids", [])
        if not isinstance(file_ids, list):
            file_ids = []
        exclude_cids = options.get("exclude_cids", [])
        if not isinstance(exclude_cids, list):
            exclude_cids = []
        score_threshold = max(0.0, min(self._to_float(options.get("score_threshold", self.default_vector_score_threshold),
                                                      self.default_vector_score_threshold), 1.0))
        k_per_query = self.default_vector_k_per_query

        cache_key = self._vector_search_cache_key(queries, file_ids, exclude_cids, score_threshold, k_per_query)

        conn = self._connect_chat_history()
        try:
            self._ensure_vector_search_cache_tables(conn)
            cache_meta = self._get_vector_search_cache(conn, cache_key)
            if cache_meta is None:
                vectorstore_sig = self._vectorstore_signature()
                cache_id, total_hits = self._build_vector_search_cache(
                    conn,
                    cache_key,
                    vectorstore_sig,
                    queries,
                    file_ids,
                    exclude_cids,
                    score_threshold,
                    k_per_query,
                )
            else:
                cache_id, total_hits = cache_meta

            if cursor > total_hits:
                cursor = total_hits

            cur = conn.cursor()

            hits: List[Dict[str, Any]] = []
            next_cursor = cursor
            fetch_batch_size = max(page_size * 3, 50)
            while len(hits) < page_size and next_cursor < total_hits:
                cur.execute(
                    "SELECT position, docstore_id, source_id, start_index, text_length, score "
                    "FROM mcp_vector_search_hits "
                    "WHERE cache_id=? AND position>=? "
                    "ORDER BY position ASC LIMIT ?",
                    (cache_id, next_cursor, fetch_batch_size),
                )
                rows = cur.fetchall()
                if len(rows) == 0:
                    next_cursor = total_hits
                    break

                docstore_ids = [str(row[1]).strip() for row in rows if row[1] is not None and str(row[1]).strip() != ""]
                docs_map = self._fetch_cached_documents_by_docstore_id(docstore_ids)
                source_texts = self._fetch_sources_texts([self._to_int(row[2], -1) for row in rows])

                for row in rows:
                    position = self._to_int(row[0], 0)
                    docstore_id = "" if row[1] is None else str(row[1]).strip()
                    source_id = self._to_int(row[2], -1)
                    start_index = self._to_int(row[3], -1)
                    next_cursor = max(next_cursor, position + 1)

                    if docstore_id == "":
                        continue
                    doc_obj = docs_map.get(docstore_id)
                    if doc_obj is None:
                        # stale cache entry: silently skip
                        continue

                    text = str(getattr(doc_obj, "page_content", ""))
                    if text.strip() == "":
                        continue
                    metadata = getattr(doc_obj, "metadata", {})
                    if not isinstance(metadata, dict):
                        metadata = {}
                    meta_source_id = self._to_int(metadata.get("id"), -1)
                    if meta_source_id > 0:
                        source_id = meta_source_id
                    meta_start_index = self._to_int(metadata.get("start_index"), -1)
                    if meta_start_index >= 0:
                        start_index = meta_start_index
                    source_name = str(metadata.get("name", "")).strip()
                    if source_name == "" and source_id > 0:
                        fetched_name = self._fetch_source_name(source_id)
                        source_name = "" if fetched_name is None else str(fetched_name)
                    source_fulltext = ""
                    source_row = source_texts.get(source_id)
                    if source_row is None and source_id > 0:
                        source_row = self._fetch_sources_texts([source_id]).get(source_id)
                    if source_row is not None:
                        if source_name == "":
                            source_name = str(source_row[0] if source_row[0] is not None else "")
                        source_fulltext = str(source_row[1] if source_row[1] is not None else "")

                    hit_payload = {
                        "source_id": (source_id if source_id > 0 else None),
                        "source_name": source_name,
                        "start": (start_index if start_index >= 0 else None),
                        "length": len(text),
                        "text": text,
                    }
                    self._append_line_range_fields(hit_payload, source_fulltext, start_index, len(text))
                    hits.append(hit_payload)
                    if len(hits) >= page_size:
                        break

            if next_cursor > total_hits:
                next_cursor = total_hits
            truncated = next_cursor < total_hits

            return {
                "selection": {
                    "queries": queries,
                    "cursor": cursor,
                    "file_ids": file_ids,
                    "exclude_cids": exclude_cids,
                    "score_threshold": score_threshold,
                    "total_hits": total_hits,
                    "next_cursor": next_cursor,
                    "truncated": truncated,
                },
                "hits": hits,
            }
        finally:
            conn.close()

    def _read_bm25_search(self, options: Dict[str, Any]) -> Dict[str, Any]:
        ai = getattr(self.app, "ai", None)
        if ai is None:
            raise RuntimeError("AI integration is not initialized.")
        vectorstore = getattr(ai, "sources_vectorstore", None)
        if vectorstore is None or not getattr(vectorstore, "is_open", lambda: False)():
            raise RuntimeError("Vectorstore is not initialized.")
        is_ready_fn = getattr(vectorstore, "is_ready", None)
        if callable(is_ready_fn) and not is_ready_fn():
            raise RuntimeError("Vectorstore is currently updating. Please try again shortly.")

        queries = options.get("queries", [])
        if not isinstance(queries, list) or len(queries) == 0:
            raise ValueError("Missing BM25 search query.")
        cursor = max(0, self._to_int(options.get("cursor", 0), 0))
        page_size = max(1, min(self._to_int(options.get("page_size", self.default_bm25_page_size),
                                            self.default_bm25_page_size),
                               self.max_bm25_page_size))
        file_ids = options.get("file_ids", [])
        if not isinstance(file_ids, list):
            file_ids = []
        exclude_cids = options.get("exclude_cids", [])
        if not isinstance(exclude_cids, list):
            exclude_cids = []

        search_db_path = getattr(vectorstore, "faiss_db_path", None)
        if search_db_path is None or str(search_db_path).strip() == "" or not os.path.exists(search_db_path):
            raise RuntimeError("Search index is not initialized.")

        excluded_ranges = self._fetch_excluded_coding_ranges(exclude_cids, file_ids) if len(exclude_cids) > 0 else {}
        fused_hits: Dict[int, Dict[str, Any]] = {}

        search_conn = sqlite3.connect(search_db_path, timeout=30)
        try:
            for query_text in queries:
                params: List[Any] = [str(query_text)]
                where_sql = " WHERE search_chunk_fts MATCH ?"
                normalized_file_ids = []
                for fid in file_ids:
                    fid_i = self._to_int(fid, -1)
                    if fid_i > 0:
                        normalized_file_ids.append(fid_i)
                normalized_file_ids = sorted(set(normalized_file_ids))
                if len(normalized_file_ids) > 0:
                    placeholders = ",".join(["?"] * len(normalized_file_ids))
                    where_sql += f" AND source_id IN ({placeholders})"
                    params.extend(normalized_file_ids)

                try:
                    rows = search_conn.execute(
                        "SELECT chunk_id, source_id, source_name, start_index, length, text, bm25(search_chunk_fts) AS raw_score "
                        "FROM search_chunk_fts"
                        + where_sql
                        + " ORDER BY raw_score ASC, CAST(chunk_id AS INTEGER) ASC",
                        tuple(params),
                    ).fetchall()
                except sqlite3.OperationalError as err:
                    raise ValueError(f"Invalid BM25 query: {err}")

                for row in rows:
                    chunk_id = self._to_int(row[0], -1)
                    source_id = self._to_int(row[1], -1)
                    start_index = self._to_int(row[3], -1)
                    length = self._to_int(row[4], 0)
                    if chunk_id <= 0 or source_id <= 0 or start_index < 0 or length <= 0:
                        continue
                    if len(excluded_ranges) > 0:
                        if self._range_overlaps_any(start_index, start_index + length, excluded_ranges.get(source_id, [])):
                            continue
                    raw_score = self._to_float(row[6], 0.0)
                    lexical_score = 1.0 / (1.0 + max(0.0, raw_score))
                    hit = fused_hits.get(chunk_id)
                    if hit is None:
                        fused_hits[chunk_id] = {
                            "chunk_id": chunk_id,
                            "source_id": source_id,
                            "source_name": "" if row[2] is None else str(row[2]),
                            "start": start_index,
                            "length": length,
                            "text": "" if row[5] is None else str(row[5]),
                            "score": 1.0 + lexical_score,
                            "query_matches": 1,
                        }
                    else:
                        hit["score"] = self._to_float(hit.get("score", 0.0), 0.0) + 1.0 + lexical_score
                        hit["query_matches"] = self._to_int(hit.get("query_matches", 0), 0) + 1
        finally:
            search_conn.close()

        ordered_hits = sorted(
            fused_hits.values(),
            key=lambda item: (
                -self._to_float(item.get("score", 0.0), 0.0),
                str(item.get("source_name", "")).lower(),
                self._to_int(item.get("start", 0), 0),
                self._to_int(item.get("chunk_id", 0), 0),
            ),
        )
        total_hits = len(ordered_hits)
        if cursor > total_hits:
            cursor = total_hits
        sliced_hits = ordered_hits[cursor:cursor + page_size]
        source_texts = self._fetch_sources_texts([self._to_int(hit.get("source_id"), -1) for hit in sliced_hits])
        returned_hits: List[Dict[str, Any]] = []
        for hit in sliced_hits:
            source_id = self._to_int(hit.get("source_id"), -1)
            source_fulltext = ""
            source_row = source_texts.get(source_id)
            if source_row is not None:
                source_fulltext = str(source_row[1] if source_row[1] is not None else "")
            hit_payload = {
                "source_id": hit["source_id"],
                "source_name": hit["source_name"],
                "start": hit["start"],
                "length": hit["length"],
                "text": hit["text"],
            }
            self._append_line_range_fields(hit_payload, source_fulltext, hit.get("start"), hit.get("length"))
            returned_hits.append(hit_payload)

        next_cursor = min(total_hits, cursor + len(returned_hits))
        truncated = next_cursor < total_hits
        return {
            "selection": {
                    "queries": queries,
                    "cursor": cursor,
                    "file_ids": file_ids,
                    "exclude_cids": exclude_cids,
                    "total_hits": total_hits,
                    "next_cursor": next_cursor,
                    "truncated": truncated,
                },
                "hits": returned_hits,
            }

    def _read_regex_search(self, options: Dict[str, Any]) -> Dict[str, Any]:
        pattern_text = str(options.get("pattern", "")).strip()
        if pattern_text == "":
            raise ValueError("Missing regex pattern.")
        flags_text = str(options.get("flags", "")).strip().lower()
        cursor = max(0, self._to_int(options.get("cursor", 0), 0))
        page_size = max(1, min(self._to_int(options.get("page_size", self.default_regex_page_size),
                                            self.default_regex_page_size),
                               self.max_regex_page_size))
        context_chars = max(0, min(self._to_int(options.get("context_chars", self.default_regex_context_chars),
                                                self.default_regex_context_chars),
                                   self.max_regex_context_chars))
        file_ids = options.get("file_ids", [])
        if not isinstance(file_ids, list):
            file_ids = []
        exclude_cids = options.get("exclude_cids", [])
        if not isinstance(exclude_cids, list):
            exclude_cids = []

        re_flags = self._regex_flags_to_re_flags(flags_text)
        try:
            regex = re.compile(pattern_text, re_flags)
        except re.error as err:
            raise ValueError(f"Invalid regex pattern: {err}")

        cache_key = self._regex_search_cache_key(pattern_text, flags_text, file_ids, exclude_cids, context_chars)

        conn = self._connect_chat_history()
        try:
            self._ensure_vector_search_cache_tables(conn)
            cache_meta = self._get_regex_search_cache(conn, cache_key)
            if cache_meta is None:
                cache_id, total_hits = self._build_regex_search_cache(
                    conn,
                    cache_key,
                    pattern_text,
                    flags_text,
                    file_ids,
                    exclude_cids,
                    context_chars,
                )
            else:
                cache_id, total_hits = cache_meta

            if cursor > total_hits:
                cursor = total_hits

            cur = conn.cursor()
            hits: List[Dict[str, Any]] = []
            next_cursor = cursor
            fetch_batch_size = max(page_size * 3, 50)

            while len(hits) < page_size and next_cursor < total_hits:
                cur.execute(
                    "SELECT position, source_id, context_start, context_length, match_start, match_length "
                    "FROM mcp_regex_search_hits "
                    "WHERE cache_id=? AND position>=? "
                    "ORDER BY position ASC LIMIT ?",
                    (cache_id, next_cursor, fetch_batch_size),
                )
                rows = cur.fetchall()
                if len(rows) == 0:
                    next_cursor = total_hits
                    break

                source_ids = [self._to_int(row[1], -1) for row in rows]
                source_texts = self._fetch_sources_texts(source_ids)

                for row in rows:
                    position = self._to_int(row[0], 0)
                    source_id = self._to_int(row[1], -1)
                    context_start = self._to_int(row[2], -1)
                    context_length = self._to_int(row[3], 0)
                    match_start = self._to_int(row[4], -1)
                    match_length = self._to_int(row[5], 0)
                    next_cursor = max(next_cursor, position + 1)
                    if source_id <= 0 or context_start < 0 or context_length <= 0:
                        continue

                    source_row = source_texts.get(source_id)
                    if source_row is None:
                        # source vanished or changed unexpectedly; silently skip
                        continue
                    source_name, fulltext = source_row
                    if fulltext == "":
                        continue
                    if context_start >= len(fulltext):
                        continue
                    context_end = min(len(fulltext), context_start + context_length)
                    if context_end <= context_start:
                        continue

                    # Entry may be stale if document text changed since cache build.
                    if match_start < 0 or match_length <= 0:
                        continue
                    if (match_start + match_length) > len(fulltext):
                        continue
                    current_match = regex.match(fulltext, match_start)
                    if current_match is None:
                        continue
                    if current_match.start() != match_start or current_match.end() != (match_start + match_length):
                        continue

                    context_text = fulltext[context_start:context_end]
                    if context_text.strip() == "":
                        continue

                    hit_payload = {
                        "source_id": source_id,
                        "source_name": source_name,
                        "start": context_start,
                        "length": len(context_text),
                        "match_start": match_start,
                        "match_length": match_length,
                        "text": context_text,
                    }
                    self._append_line_range_fields(hit_payload, fulltext, context_start, len(context_text))
                    hits.append(hit_payload)
                    if len(hits) >= page_size:
                        break

            if next_cursor > total_hits:
                next_cursor = total_hits
            truncated = next_cursor < total_hits

            return {
                "selection": {
                    "pattern": pattern_text,
                    "flags": flags_text,
                    "cursor": cursor,
                    "page_size": page_size,
                    "context_chars": context_chars,
                    "file_ids": file_ids,
                    "exclude_cids": exclude_cids,
                    "total_hits": total_hits,
                    "next_cursor": next_cursor,
                    "truncated": truncated,
                },
                "hits": hits,
            }
        finally:
            conn.close()

    def _chat_history_db_path(self) -> str:
        project_path = getattr(self.app, "project_path", "")
        if project_path is None or project_path == "":
            raise RuntimeError("No project open.")
        ai_data_dir = os.path.join(project_path, "ai_data")
        if not os.path.exists(ai_data_dir):
            os.makedirs(ai_data_dir, exist_ok=True)
        return os.path.join(ai_data_dir, "chat_history.sqlite")

    def _connect_chat_history(self) -> sqlite3.Connection:
        return sqlite3.connect(self._chat_history_db_path(), timeout=30)

    def _ensure_vector_search_cache_tables(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS mcp_vector_search_cache ("
            "id INTEGER PRIMARY KEY, "
            "cache_key TEXT NOT NULL, "
            "vectorstore_sig TEXT NOT NULL, "
            "query_json TEXT NOT NULL, "
            "file_ids_json TEXT NOT NULL, "
            "score_threshold REAL NOT NULL, "
            "k_per_query INTEGER NOT NULL, "
            "total_hits INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL, "
            "last_used_at TEXT NOT NULL)"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_vector_search_cache_key "
            "ON mcp_vector_search_cache(cache_key, vectorstore_sig)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS mcp_vector_search_hits ("
            "id INTEGER PRIMARY KEY, "
            "cache_id INTEGER NOT NULL, "
            "position INTEGER NOT NULL, "
            "docstore_id TEXT, "
            "source_id INTEGER, "
            "start_index INTEGER, "
            "text_length INTEGER, "
            "score REAL, "
            "FOREIGN KEY (cache_id) REFERENCES mcp_vector_search_cache(id))"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_vector_search_hits_cache_pos "
            "ON mcp_vector_search_hits(cache_id, position)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_vector_search_cache_key_lookup "
            "ON mcp_vector_search_cache(cache_key)"
        )

        cur.execute(
            "CREATE TABLE IF NOT EXISTS mcp_regex_search_cache ("
            "id INTEGER PRIMARY KEY, "
            "cache_key TEXT NOT NULL, "
            "pattern TEXT NOT NULL, "
            "flags TEXT NOT NULL, "
            "file_ids_json TEXT NOT NULL, "
            "context_chars INTEGER NOT NULL, "
            "total_hits INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL, "
            "last_used_at TEXT NOT NULL)"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_regex_search_cache_key "
            "ON mcp_regex_search_cache(cache_key)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS mcp_regex_search_hits ("
            "id INTEGER PRIMARY KEY, "
            "cache_id INTEGER NOT NULL, "
            "position INTEGER NOT NULL, "
            "source_id INTEGER NOT NULL, "
            "context_start INTEGER NOT NULL, "
            "context_length INTEGER NOT NULL, "
            "match_start INTEGER NOT NULL, "
            "match_length INTEGER NOT NULL, "
            "FOREIGN KEY (cache_id) REFERENCES mcp_regex_search_cache(id))"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_regex_search_hits_cache_pos "
            "ON mcp_regex_search_hits(cache_id, position)"
        )
        conn.commit()

    def _get_vector_search_cache(self, conn: sqlite3.Connection, cache_key: str) -> Optional[Tuple[int, int]]:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, total_hits FROM mcp_vector_search_cache "
            "WHERE cache_key=? ORDER BY id DESC LIMIT 1",
            (cache_key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cache_id = self._to_int(row[0], -1)
        total_hits = max(0, self._to_int(row[1], 0))
        if cache_id <= 0:
            return None
        now = datetime.utcnow().isoformat(timespec="seconds")
        cur.execute(
            "UPDATE mcp_vector_search_cache SET last_used_at=? WHERE id=?",
            (now, cache_id),
        )
        conn.commit()
        return cache_id, total_hits

    def _build_vector_search_cache(self, conn: sqlite3.Connection, cache_key: str,
                                   vectorstore_sig: str, queries: List[str], file_ids: List[int],
                                   exclude_cids: List[int], score_threshold: float,
                                   k_per_query: int) -> Tuple[int, int]:
        ai = getattr(self.app, "ai", None)
        if ai is None:
            raise RuntimeError("AI integration is not initialized.")
        doc_filter = file_ids if len(file_ids) > 0 else None
        chunks = ai._retrieve_from_vectorstore(
            queries,
            doc_ids=doc_filter,
            score_threshold=score_threshold,
            k=k_per_query,
        )
        if not isinstance(chunks, list):
            chunks = []

        if len(exclude_cids) > 0 and len(chunks) > 0:
            excluded_ranges = self._fetch_excluded_coding_ranges(exclude_cids, file_ids)
            filtered_chunks = []
            for chunk_doc in chunks:
                metadata = getattr(chunk_doc, "metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                source_id = self._to_int(metadata.get("id"), -1)
                start_index = self._to_int(metadata.get("start_index"), -1)
                page_content = str(getattr(chunk_doc, "page_content", ""))
                text_length = len(page_content)
                if source_id <= 0 or start_index < 0 or text_length <= 0:
                    # Strict mode for exclude_cids: only keep verifiable "new" passages.
                    continue
                if self._range_overlaps_any(
                    start_index,
                    start_index + text_length,
                    excluded_ranges.get(source_id, []),
                ):
                    continue
                filtered_chunks.append(chunk_doc)
            chunks = filtered_chunks

        total_hits = len(chunks)
        now = datetime.utcnow().isoformat(timespec="seconds")

        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO mcp_vector_search_cache "
                "(cache_key, vectorstore_sig, query_json, file_ids_json, score_threshold, "
                "k_per_query, total_hits, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cache_key,
                    vectorstore_sig,
                    json.dumps(queries, ensure_ascii=False),
                    json.dumps(file_ids),
                    float(score_threshold),
                    int(k_per_query),
                    int(total_hits),
                    now,
                    now,
                ),
            )
            cache_id = int(cur.lastrowid)
        except sqlite3.IntegrityError:
            # If another writer inserted the same key first, reuse it.
            conn.rollback()
            existing = self._get_vector_search_cache(conn, cache_key)
            if existing is None:
                raise
            return existing

        rows_to_insert: List[Tuple[Any, ...]] = []
        for pos, chunk_doc in enumerate(chunks):
            docstore_id = getattr(chunk_doc, "id", None)
            if docstore_id is None:
                docstore_id = ""
            else:
                docstore_id = str(docstore_id)

            metadata = getattr(chunk_doc, "metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            source_id = self._to_int(metadata.get("id"), -1)
            if source_id <= 0:
                source_id = None
            start_index = self._to_int(metadata.get("start_index"), -1)
            if start_index < 0:
                start_index = None
            page_content = str(getattr(chunk_doc, "page_content", ""))
            text_length = len(page_content)
            score = self._to_float(metadata.get("score", 0.0), 0.0)

            rows_to_insert.append(
                (
                    cache_id,
                    pos,
                    docstore_id,
                    source_id,
                    start_index,
                    text_length,
                    score,
                )
            )
        if len(rows_to_insert) > 0:
            cur.executemany(
                "INSERT INTO mcp_vector_search_hits "
                "(cache_id, position, docstore_id, source_id, start_index, text_length, score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows_to_insert,
            )
        conn.commit()
        return cache_id, total_hits

    def _get_regex_search_cache(self, conn: sqlite3.Connection, cache_key: str) -> Optional[Tuple[int, int]]:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, total_hits FROM mcp_regex_search_cache WHERE cache_key=? LIMIT 1",
            (cache_key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cache_id = self._to_int(row[0], -1)
        total_hits = max(0, self._to_int(row[1], 0))
        if cache_id <= 0:
            return None
        now = datetime.utcnow().isoformat(timespec="seconds")
        cur.execute(
            "UPDATE mcp_regex_search_cache SET last_used_at=? WHERE id=?",
            (now, cache_id),
        )
        conn.commit()
        return cache_id, total_hits

    def _build_regex_search_cache(self, conn: sqlite3.Connection, cache_key: str, pattern_text: str,
                                  flags_text: str, file_ids: List[int], exclude_cids: List[int],
                                  context_chars: int) -> Tuple[int, int]:
        re_flags = self._regex_flags_to_re_flags(flags_text)
        try:
            regex = re.compile(pattern_text, re_flags)
        except re.error as err:
            raise ValueError(f"Invalid regex pattern: {err}")

        where_sql = " WHERE fulltext is not null"
        params: List[Any] = []
        norm_file_ids: List[int] = []
        for fid in file_ids:
            try:
                fid_i = int(fid)
            except (TypeError, ValueError):
                continue
            if fid_i > 0:
                norm_file_ids.append(fid_i)
        norm_file_ids = sorted(set(norm_file_ids))
        if len(norm_file_ids) > 0:
            placeholders = ",".join(["?"] * len(norm_file_ids))
            where_sql += f" AND id IN ({placeholders})"
            params.extend(norm_file_ids)

        rows = self._fetchall(
            "SELECT id, ifnull(name,''), ifnull(fulltext,'') FROM source"
            + where_sql
            + " ORDER BY lower(name)",
            tuple(params),
        )

        now = datetime.utcnow().isoformat(timespec="seconds")
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO mcp_regex_search_cache "
                "(cache_key, pattern, flags, file_ids_json, context_chars, total_hits, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cache_key,
                    pattern_text,
                    flags_text,
                    json.dumps(norm_file_ids),
                    int(context_chars),
                    0,
                    now,
                    now,
                ),
            )
            cache_id = int(cur.lastrowid)
        except sqlite3.IntegrityError:
            conn.rollback()
            existing = self._get_regex_search_cache(conn, cache_key)
            if existing is None:
                raise
            return existing

        excluded_ranges = self._fetch_excluded_coding_ranges(exclude_cids, norm_file_ids) if len(exclude_cids) > 0 else {}
        match_rows: List[Tuple[Any, ...]] = []
        for row in rows:
            source_id = self._to_int(row[0], -1)
            fulltext = "" if row[2] is None else str(row[2])
            if source_id <= 0 or fulltext == "":
                continue
            for match in regex.finditer(fulltext):
                match_start = int(match.start())
                match_end = int(match.end())
                if match_end <= match_start:
                    continue
                if len(excluded_ranges) > 0:
                    if self._range_overlaps_any(match_start, match_end, excluded_ranges.get(source_id, [])):
                        continue
                context_start = max(0, match_start - context_chars)
                context_end = min(len(fulltext), match_end + context_chars)
                context_length = max(0, context_end - context_start)
                if context_length <= 0:
                    continue
                match_rows.append(
                    (
                        source_id,
                        context_start,
                        context_length,
                        match_start,
                        match_end - match_start,
                    )
                )
                if len(match_rows) >= self.max_regex_hits:
                    break
            if len(match_rows) >= self.max_regex_hits:
                break

        # Regex has no relevance score. Mix matches deterministically to avoid over-weighting early documents.
        rng = random.Random(cache_key)
        rng.shuffle(match_rows)

        insert_rows: List[Tuple[Any, ...]] = []
        for pos, row_data in enumerate(match_rows):
            insert_rows.append((cache_id, pos, *row_data))

        if len(insert_rows) > 0:
            cur.executemany(
                "INSERT INTO mcp_regex_search_hits "
                "(cache_id, position, source_id, context_start, context_length, match_start, match_length) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                insert_rows,
            )
        cur.execute(
            "UPDATE mcp_regex_search_cache SET total_hits=? WHERE id=?",
            (len(insert_rows), cache_id),
        )
        conn.commit()
        return cache_id, len(insert_rows)

    def _vector_search_cache_key(self, queries: List[str], file_ids: List[int],
                                 exclude_cids: List[int], score_threshold: float,
                                 k_per_query: int) -> str:
        norm_file_ids: List[int] = []
        for fid in file_ids:
            try:
                fid_i = int(fid)
            except (TypeError, ValueError):
                continue
            if fid_i > 0:
                norm_file_ids.append(fid_i)
        norm_exclude_cids: List[int] = []
        for cid in exclude_cids:
            try:
                cid_i = int(cid)
            except (TypeError, ValueError):
                continue
            if cid_i > 0:
                norm_exclude_cids.append(cid_i)
        payload = {
            "queries": queries,
            "file_ids": sorted(set(norm_file_ids)),
            "exclude_cids": sorted(set(norm_exclude_cids)),
            "score_threshold": round(float(score_threshold), 4),
            "k_per_query": int(k_per_query),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _regex_search_cache_key(self, pattern_text: str, flags_text: str, file_ids: List[int],
                                exclude_cids: List[int], context_chars: int) -> str:
        norm_file_ids: List[int] = []
        for fid in file_ids:
            try:
                fid_i = int(fid)
            except (TypeError, ValueError):
                continue
            if fid_i > 0:
                norm_file_ids.append(fid_i)
        norm_exclude_cids: List[int] = []
        for cid in exclude_cids:
            try:
                cid_i = int(cid)
            except (TypeError, ValueError):
                continue
            if cid_i > 0:
                norm_exclude_cids.append(cid_i)
        payload = {
            "version": "regex_order_shuffle_v2",
            "pattern": pattern_text,
            "flags": flags_text,
            "file_ids": sorted(set(norm_file_ids)),
            "exclude_cids": sorted(set(norm_exclude_cids)),
            "context_chars": int(context_chars),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _regex_flags_to_re_flags(self, flags_text: str) -> int:
        flags = 0
        text = str(flags_text).lower()
        if "i" in text:
            flags |= re.IGNORECASE
        if "m" in text:
            flags |= re.MULTILINE
        if "s" in text:
            flags |= re.DOTALL
        if "x" in text:
            flags |= re.VERBOSE
        return flags

    def _vectorstore_signature(self) -> str:
        ai = getattr(self.app, "ai", None)
        vectorstore = getattr(ai, "sources_vectorstore", None) if ai is not None else None
        faiss_path = getattr(vectorstore, "faiss_db_path", None) if vectorstore is not None else None
        if faiss_path is None or str(faiss_path).strip() == "":
            project_path = getattr(self.app, "project_path", "")
            if project_path is None or project_path == "":
                return "missing"
            faiss_path = os.path.join(project_path, "ai_data", "vectorstore", "faiss_store.bin")
        if not os.path.exists(faiss_path):
            return "missing"
        try:
            stat = os.stat(faiss_path)
            return f"{int(stat.st_mtime)}:{int(stat.st_size)}"
        except OSError:
            return "unknown"

    def _fetch_cached_documents_by_docstore_id(self, docstore_ids: List[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        ai = getattr(self.app, "ai", None)
        vectorstore = getattr(ai, "sources_vectorstore", None) if ai is not None else None
        if vectorstore is None:
            return result
        try:
            docs = vectorstore.faiss_db_retrieve_documents(docstore_ids)
        except Exception:
            docs = []
        for doc in docs:
            key = str(getattr(doc, "id", "")).strip()
            if key == "" or key in result:
                continue
            if not hasattr(doc, "page_content"):
                continue
            result[key] = doc
        return result

    def _fetch_sources_texts(self, source_ids: List[int]) -> Dict[int, Tuple[str, str]]:
        normalized_ids: List[int] = []
        for source_id in source_ids:
            try:
                source_id_i = int(source_id)
            except (TypeError, ValueError):
                continue
            if source_id_i > 0:
                normalized_ids.append(source_id_i)
        normalized_ids = sorted(set(normalized_ids))
        if len(normalized_ids) == 0:
            return {}
        placeholders = ",".join(["?"] * len(normalized_ids))
        rows = self._fetchall(
            "SELECT id, ifnull(name,''), ifnull(fulltext,'') FROM source "
            f"WHERE id IN ({placeholders})",
            tuple(normalized_ids),
        )
        result: Dict[int, Tuple[str, str]] = {}
        for row in rows:
            source_id = self._to_int(row[0], -1)
            if source_id <= 0:
                continue
            source_name = "" if row[1] is None else str(row[1])
            fulltext = "" if row[2] is None else str(row[2])
            result[source_id] = (source_name, fulltext)
        return result

    def _line_ranges(self, fulltext: str) -> List[Tuple[int, int]]:
        """Return 0-based [start, end) character ranges for each logical line."""

        text = "" if fulltext is None else str(fulltext)
        if text == "":
            return []
        ranges: List[Tuple[int, int]] = []
        pos = 0
        for line_text in text.splitlines(keepends=True):
            next_pos = pos + len(line_text)
            ranges.append((pos, next_pos))
            pos = next_pos
        if len(ranges) == 0:
            ranges.append((0, len(text)))
        return ranges

    def _char_position_to_line_number(self, fulltext: str, char_pos: int) -> int:
        """Return the 1-based logical line number for one character position."""

        line_ranges = self._line_ranges(fulltext)
        if len(line_ranges) == 0:
            return 0
        text_len = len("" if fulltext is None else str(fulltext))
        if text_len <= 0:
            return 0
        pos = max(0, min(self._to_int(char_pos, 0), text_len - 1))
        for idx, (_, end_pos) in enumerate(line_ranges, start=1):
            if pos < end_pos:
                return idx
        return len(line_ranges)

    def _char_range_to_line_range(self, fulltext: str, start: int, length: int) -> Tuple[int, int]:
        """Return 1-based logical line numbers touched by one character range."""

        text = "" if fulltext is None else str(fulltext)
        if text == "":
            return 0, 0
        text_len = len(text)
        start_i = max(0, min(self._to_int(start, 0), text_len - 1))
        length_i = max(0, self._to_int(length, 0))
        end_exclusive = min(text_len, start_i + length_i)
        start_line = self._char_position_to_line_number(text, start_i)
        if end_exclusive <= start_i:
            return start_line, start_line
        end_line = self._char_position_to_line_number(text, end_exclusive - 1)
        return start_line, end_line

    def _line_range_to_char_window(self, fulltext: str, line_start: int, line_end: int) -> Tuple[int, int, int, int]:
        """Convert one 1-based logical line window to a character start/length pair."""

        line_ranges = self._line_ranges(fulltext)
        if len(line_ranges) == 0:
            return 0, 0, 0, 0
        start_line = max(1, self._to_int(line_start, 1))
        end_line = max(start_line, self._to_int(line_end, start_line))
        if start_line > len(line_ranges):
            raise ValueError(f"line_start exceeds the document line count ({len(line_ranges)}).")
        end_line = min(end_line, len(line_ranges))
        start_pos = line_ranges[start_line - 1][0]
        end_pos = line_ranges[end_line - 1][1]
        return start_pos, max(0, end_pos - start_pos), start_line, end_line

    def _append_line_range_fields(self, payload: Dict[str, Any], fulltext: str,
                                  start: Any, length: Any) -> Dict[str, Any]:
        """Attach line_start and line_end to one payload using its character window."""

        start_i = self._to_int(start, -1)
        length_i = self._to_int(length, -1)
        if start_i < 0 or length_i < 0:
            payload["line_start"] = 0
            payload["line_end"] = 0
            return payload
        line_start, line_end = self._char_range_to_line_range(fulltext, start_i, length_i)
        payload["line_start"] = line_start
        payload["line_end"] = line_end
        return payload

    def _fetch_excluded_coding_ranges(self, exclude_cids: List[int], file_ids: List[int]) -> Dict[int, List[Tuple[int, int]]]:
        """Fetch coded text ranges grouped by source id for exclusion filtering."""

        normalized_cids: List[int] = []
        for cid in exclude_cids:
            cid_i = self._to_int(cid, -1)
            if cid_i > 0:
                normalized_cids.append(cid_i)
        normalized_cids = sorted(set(normalized_cids))
        if len(normalized_cids) == 0:
            return {}

        where_parts = []
        params: List[Any] = []

        cid_placeholders = ",".join(["?"] * len(normalized_cids))
        where_parts.append(f"cid IN ({cid_placeholders})")
        params.extend(normalized_cids)
        where_parts.append("pos1 > pos0")

        normalized_fids: List[int] = []
        for fid in file_ids:
            fid_i = self._to_int(fid, -1)
            if fid_i > 0:
                normalized_fids.append(fid_i)
        normalized_fids = sorted(set(normalized_fids))
        if len(normalized_fids) > 0:
            fid_placeholders = ",".join(["?"] * len(normalized_fids))
            where_parts.append(f"fid IN ({fid_placeholders})")
            params.extend(normalized_fids)

        where_sql = " AND ".join(where_parts)
        try:
            rows = self._fetchall(
                "SELECT fid, pos0, pos1 FROM code_text WHERE " + where_sql + " ORDER BY fid, pos0",
                tuple(params),
            )
        except sqlite3.OperationalError:
            return {}
        ranges_by_fid: Dict[int, List[Tuple[int, int]]] = {}
        for row in rows:
            fid = self._to_int(row[0], -1)
            pos0 = self._to_int(row[1], -1)
            pos1 = self._to_int(row[2], -1)
            if fid <= 0 or pos0 < 0 or pos1 <= pos0:
                continue
            if fid not in ranges_by_fid:
                ranges_by_fid[fid] = []
            ranges_by_fid[fid].append((pos0, pos1))
        return ranges_by_fid

    def _range_overlaps_any(self, start: int, end: int, ranges: List[Tuple[int, int]]) -> bool:
        """Return True if [start, end) intersects any range in ranges."""

        if end <= start:
            return False
        if not isinstance(ranges, list) or len(ranges) == 0:
            return False
        for r_start, r_end in ranges:
            if start < r_end and end > r_start:
                return True
            if r_start > end:
                break
        return False

    def _read_code_segments(self, cid: int, options: Dict[str, Any]) -> Dict[str, Any]:
        code_name = self._fetch_code_name(cid)
        if code_name is None:
            raise ValueError(f"Code id {cid} not found.")

        strategy = str(options.get("strategy", "diverse_by_document"))
        max_segments = int(options.get("max_segments", self.default_segments_max_segments))
        max_chars = int(options.get("max_chars", self.default_segments_max_chars))
        cursor = int(options.get("cursor", 0))
        file_ids = options.get("file_ids", [])
        if not isinstance(file_ids, list):
            file_ids = []
        owners = options.get("owners", [])
        if not isinstance(owners, list):
            owners = []

        if len(owners) > 0:
            table_name = "code_text"
        else:
            if not self._view_exists("code_text_visible"):
                raise RuntimeError("Required view 'code_text_visible' not found.")
            table_name = "code_text_visible"

        where_parts = ["ct.cid=?"]
        where_params: List[Any] = [cid]
        if len(file_ids) > 0:
            placeholders = ",".join(["?"] * len(file_ids))
            where_parts.append(f"ct.fid IN ({placeholders})")
            where_params.extend(file_ids)
        if len(owners) > 0:
            placeholders = ",".join(["?"] * len(owners))
            where_parts.append(f"ct.owner IN ({placeholders})")
            where_params.extend(owners)
        where_sql = " WHERE " + " AND ".join(where_parts)

        count_sql = f"SELECT count(*) FROM {table_name} AS ct" + where_sql
        count_row = self._fetchone(count_sql, tuple(where_params))
        total_segments = 0 if count_row is None else int(count_row[0])

        order_sql = "ORDER BY ct.ctid"
        select_sql = (
            "SELECT ct.ctid, ct.cid, ct.fid, ifnull(ct.seltext,''), ct.pos0, "
            "ct.pos1, ct.owner, source.name, code_name.name "
            f"FROM {table_name} AS ct "
            "JOIN source ON source.id = ct.fid "
            "JOIN code_name ON code_name.cid = ct.cid "
            + where_sql
            + " "
        )

        if strategy == "recent_first":
            order_sql = "ORDER BY ct.date DESC, ct.ctid DESC"
            segment_rows = self._fetchall(
                select_sql + order_sql + " LIMIT ? OFFSET ?",
                tuple(where_params + [max_segments, cursor]),
            )
        elif strategy == "sequential":
            order_sql = "ORDER BY ct.ctid"
            segment_rows = self._fetchall(
                select_sql + order_sql + " LIMIT ? OFFSET ?",
                tuple(where_params + [max_segments, cursor]),
            )
        else:
            diverse_sql = (
                "SELECT ordered.ctid, ordered.cid, ordered.fid, ifnull(ordered.seltext,''), ordered.pos0, "
                "ordered.pos1, ordered.owner, source.name, code_name.name "
                "FROM ("
                "SELECT ct.ctid, ct.cid, ct.fid, ct.seltext, ct.pos0, ct.pos1, "
                "ct.owner, ROW_NUMBER() OVER (PARTITION BY ct.fid ORDER BY ifnull(ct.pos0, ct.ctid), ct.ctid) AS rn "
                f"FROM {table_name} AS ct "
                + where_sql
                + ") AS ordered "
                "JOIN source ON source.id = ordered.fid "
                "JOIN code_name ON code_name.cid = ordered.cid "
                "ORDER BY ordered.rn, ordered.fid, ifnull(ordered.pos0, ordered.ctid), ordered.ctid LIMIT ? OFFSET ?"
            )
            segment_rows = self._fetchall(diverse_sql, tuple(where_params + [max_segments, cursor]))
            segment_rows.sort(
                key=lambda row: (
                    int(row[2]) if row[2] is not None else 0,
                    int(row[4]) if row[4] is not None else int(row[0]),
                    int(row[0]) if row[0] is not None else 0,
                )
            )

        segments: List[Dict[str, Any]] = []
        used_chars = 0
        hit_max_char_limit = False
        source_texts = self._fetch_sources_texts([self._to_int(row[2], -1) for row in segment_rows])
        for row in segment_rows:
            if len(segments) >= max_segments:
                break

            quote = "" if row[3] is None else str(row[3])
            quote_length = len(quote)
            if used_chars >= max_chars:
                hit_max_char_limit = True
                break
            if used_chars + quote_length > max_chars:
                hit_max_char_limit = True
                break

            fid = self._to_int(row[2], -1)
            source_fulltext = ""
            source_row = source_texts.get(fid)
            if source_row is not None:
                source_fulltext = str(source_row[1] if source_row[1] is not None else "")
            segment_payload = {
                "ctid": row[0],
                "cid": row[1],
                "fid": row[2],
                "quote": quote,
                "pos0": row[4],
                "pos1": row[5],
                "owner": row[6],
                "source_name": row[7],
                "code_name": row[8],
            }
            self._append_line_range_fields(
                segment_payload,
                source_fulltext,
                row[4],
                self._to_int(row[5], 0) - self._to_int(row[4], 0),
            )
            segments.append(segment_payload)
            used_chars += quote_length

        next_cursor = cursor + len(segments)
        if next_cursor > total_segments:
            next_cursor = total_segments
        truncated = next_cursor < total_segments

        return {
            "cid": cid,
            "code_name": code_name,
            "selection": {
                "strategy": strategy,
                "max_segments": max_segments,
                "max_chars": max_chars,
                "cursor": cursor,
                "file_ids": file_ids,
                "total_segments": total_segments,
                "next_cursor": next_cursor,
                "truncated": truncated,
                "hit_max_char_limit": hit_max_char_limit,
            },
            "segments": segments,
        }

    def _read_case(self, case_id: int) -> Dict[str, Any]:
        row = self._fetchone(
            "SELECT caseid, name, ifnull(memo,''), owner, date FROM cases WHERE caseid=?",
            (case_id,),
        )
        if row is None:
            raise ValueError(f"Case id {case_id} not found.")
        attributes = self._fetch_case_attributes([case_id]).get(case_id, {})
        counts = self._fetch_case_link_counts([case_id]).get(case_id, {})
        file_rows = self._fetchall(
            "SELECT ct.fid, ifnull(source.name,''), ifnull(source.mediapath,''), "
            "count(*), max(case when source.fulltext is not null then 1 else 0 end), "
            "max(case when source.fulltext is not null and ct.pos0=0 and ct.pos1=length(source.fulltext) "
            "then 1 else 0 end) "
            "FROM case_text AS ct "
            "JOIN source ON source.id = ct.fid "
            "WHERE ct.caseid=? "
            "GROUP BY ct.fid, source.name, source.mediapath "
            "ORDER BY lower(source.name), ct.fid",
            (case_id,),
        )
        files: List[Dict[str, Any]] = []
        for file_row in file_rows:
            files.append(
                {
                    "fid": self._to_int(file_row[0], -1),
                    "name": "" if file_row[1] is None else str(file_row[1]),
                    "mediapath": "" if file_row[2] is None else str(file_row[2]),
                    "segment_count": self._to_int(file_row[3], 0),
                    "has_text": bool(self._to_int(file_row[4], 0)),
                    "fully_linked_text": bool(self._to_int(file_row[5], 0)),
                }
            )
        return {
            "case": {
                "id": self._to_int(row[0], -1),
                "name": row[1],
                "memo": row[2],
                "owner": row[3],
                "date": row[4],
                "file_count": self._to_int(counts.get("file_count", 0), 0),
                "text_segment_count": self._to_int(counts.get("text_segment_count", 0), 0),
                "attributes": attributes,
                "files": files,
            }
        }

    def _read_case_text(self, case_id: int, options: Dict[str, Any]) -> Dict[str, Any]:
        case_name = self._fetch_case_name(case_id)
        if case_name is None:
            raise ValueError(f"Case id {case_id} not found.")

        max_segments = int(options.get("max_segments", self.default_segments_max_segments))
        max_chars = int(options.get("max_chars", self.default_segments_max_chars))
        cursor = max(0, self._to_int(options.get("cursor", 0), 0))
        file_ids = options.get("file_ids", [])
        if not isinstance(file_ids, list):
            file_ids = []

        where_parts = ["ct.caseid=?", "source.fulltext is not null"]
        where_params: List[Any] = [case_id]
        if len(file_ids) > 0:
            placeholders = ",".join(["?"] * len(file_ids))
            where_parts.append(f"ct.fid IN ({placeholders})")
            where_params.extend(file_ids)
        where_sql = " WHERE " + " AND ".join(where_parts)

        count_row = self._fetchone(
            "SELECT count(*) FROM case_text AS ct "
            "JOIN source ON source.id = ct.fid "
            + where_sql,
            tuple(where_params),
        )
        total_segments = 0 if count_row is None else self._to_int(count_row[0], 0)

        all_link_count_row = self._fetchone(
            "SELECT count(*) FROM case_text AS ct WHERE ct.caseid=?"
            + (
                ""
                if len(file_ids) == 0
                else " AND ct.fid IN (" + ",".join(["?"] * len(file_ids)) + ")"
            ),
            tuple([case_id] + list(file_ids)),
        )
        total_links = 0 if all_link_count_row is None else self._to_int(all_link_count_row[0], 0)
        skipped_nontext_segments = max(0, total_links - total_segments)

        if cursor > total_segments:
            cursor = total_segments

        rows = self._fetchall(
            "SELECT ct.id, ct.caseid, ct.fid, ct.pos0, ct.pos1, ct.owner, ct.date, ifnull(ct.memo,''), "
            "ifnull(source.name,''), ifnull(source.fulltext,'') "
            "FROM case_text AS ct "
            "JOIN source ON source.id = ct.fid "
            + where_sql
            + " ORDER BY ct.fid, ct.pos0, ct.id LIMIT ? OFFSET ?",
            tuple(where_params + [max_segments, cursor]),
        )

        segments: List[Dict[str, Any]] = []
        used_chars = 0
        hit_max_char_limit = False
        for row in rows:
            if len(segments) >= max_segments:
                break
            fulltext = "" if row[9] is None else str(row[9])
            pos0 = max(0, self._to_int(row[3], 0))
            pos1 = max(pos0, self._to_int(row[4], pos0))
            excerpt = fulltext[pos0:min(pos1, len(fulltext))]
            excerpt_length = len(excerpt)
            if used_chars >= max_chars:
                hit_max_char_limit = True
                break
            if used_chars + excerpt_length > max_chars:
                hit_max_char_limit = True
                break
            segment_payload = {
                "id": self._to_int(row[0], -1),
                "caseid": self._to_int(row[1], -1),
                "case_name": case_name,
                "fid": self._to_int(row[2], -1),
                "source_name": "" if row[8] is None else str(row[8]),
                "pos0": pos0,
                "pos1": pos1,
                "length": excerpt_length,
                "text": excerpt,
                "owner": "" if row[5] is None else str(row[5]),
                "date": row[6],
                "memo": "" if row[7] is None else str(row[7]),
            }
            self._append_line_range_fields(segment_payload, fulltext, pos0, excerpt_length)
            segments.append(segment_payload)
            used_chars += excerpt_length

        next_cursor = cursor + len(segments)
        if next_cursor > total_segments:
            next_cursor = total_segments
        truncated = next_cursor < total_segments

        return {
            "caseid": case_id,
            "case_name": case_name,
            "selection": {
                "cursor": cursor,
                "max_segments": max_segments,
                "max_chars": max_chars,
                "file_ids": file_ids,
                "total_segments": total_segments,
                "next_cursor": next_cursor,
                "truncated": truncated,
                "hit_max_char_limit": hit_max_char_limit,
                "skipped_nontext_segments": skipped_nontext_segments,
            },
            "segments": segments,
        }

    def _read_document(self, doc_id: int, window: Dict[str, Any]) -> Dict[str, Any]:
        row = self._fetchone(
            "SELECT id, name, ifnull(memo,''), owner, ifnull(fulltext,'') "
            "FROM source WHERE id=? AND fulltext is not null",
            (doc_id,),
        )
        if row is None:
            raise ValueError(f"Document id {doc_id} not found.")
        fulltext = "" if row[4] is None else str(row[4])
        window_mode = str(window.get("mode", "char"))
        if window_mode == "line":
            start, length, _, _ = self._line_range_to_char_window(
                fulltext,
                window.get("line_start", 1),
                window.get("line_end", window.get("line_start", 1)),
            )
        else:
            start = max(0, self._to_int(window.get("start", 0), 0))
            length = max(
                1,
                min(
                    self._to_int(window.get("length", self.default_read_length), self.default_read_length),
                    self.max_read_length,
                ),
            )
        end_pos = min(start + length, len(fulltext))
        excerpt = fulltext[start:end_pos]
        line_start, line_end = self._char_range_to_line_range(fulltext, start, len(excerpt))
        return {
            "id": row[0],
            "name": row[1],
            "memo": row[2],
            "owner": row[3],
            "total_length": len(fulltext),
            "start": start,
            "length": len(excerpt),
            "line_start": line_start,
            "line_end": line_end,
            "text": excerpt,
        }

    def _to_int(self, value: Any, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _to_float(self, value: Any, default: float) -> float:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _project_db_path(self) -> str:
        project_path = getattr(self.app, "project_path", "")
        if project_path is None or project_path == "":
            raise RuntimeError("No project open.")
        db_path = os.path.join(project_path, "data.qda")
        if not os.path.exists(db_path):
            raise RuntimeError("Project database not found.")
        return db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._project_db_path())

    def _fetchall(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Tuple[Any, ...]]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()

    def _fetchone(self, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Tuple[Any, ...]]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchone()
        finally:
            conn.close()
