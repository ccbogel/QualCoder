# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Authors: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

import json
import os
import tempfile
from typing import Any, Dict
import zipfile

from .ai_mcp_server import AiMcpExecutionContext
from .external_mcp import ExternalMcpController


BUNDLE_VERSION = "1.0.2"  # Must stay a three part semver, Claude Desktop rejects anything else
ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GUI", "qualcoder128.png")
CATALOG_METHODS = (
    ("tools/list", "tools"),
    ("resources/list", "resources"),
    ("resources/templates/list", "resourceTemplates"),
)


def catalog_snapshot(mcp_server: Any) -> Dict[str, Any]:
    """Return the tools and resources an external client sees, for offline listing."""

    def collect() -> Dict[str, Any]:
        snapshot = {}
        for method, key in CATALOG_METHODS:
            response = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}})
            if "error" in response:
                raise RuntimeError(f"{method}: {response['error'].get('message', '')}")
            snapshot[key] = response["result"].get(key, [])
        return snapshot

    context = AiMcpExecutionContext(source="external_mcp", owner="External MCP")
    return mcp_server.run_with_execution_context(context, collect)


def bundle_manifest(port: int, with_icon: bool) -> Dict[str, Any]:
    """Return the MCPB manifest for the bridge."""

    manifest = {
        "manifest_version": "0.3",
        "name": "qualcoder",
        "display_name": "QualCoder",
        "version": BUNDLE_VERSION,
        "description": "Work with the project that is open in QualCoder: read documents, cases and codes, "
                       "search the texts, and code with the permissions chosen in QualCoder.",
        "long_description": "Connects Claude Desktop to the External MCP access of a running QualCoder. "
                            "QualCoder must be open with a project loaded and 'allow external MCP access' "
                            "ticked in Settings. Data read by the tools is sent to the AI provider.",
        "author": {"name": "QualCoder", "url": "https://qualcoder.org"},
        "homepage": "https://qualcoder.org",
        "repository": {"type": "git", "url": "https://github.com/ccbogel/QualCoder"},
        "license": "LGPL-3.0-or-later",
        "keywords": ["qualcoder", "qualitative research", "caqdas", "coding"],
        "server": {
            "type": "node",
            "entry_point": "server/index.js",
            "mcp_config": {
                "command": "node",
                "args": ["${__dirname}/server/index.js"],
                "env": {"QUALCODER_MCP_PORT": "${user_config.port}"},
            },
        },
        "user_config": {
            "port": {
                "type": "number",
                "title": "QualCoder MCP port",
                "description": "Change it only if mcp_external_port was changed in QualCoder's config.ini.",
                "default": port,
                "min": 1024,
                "max": 65535,
                "required": False,
            }
        },
        "tools_generated": True,
        "compatibility": {"platforms": ["darwin", "win32", "linux"], "runtimes": {"node": ">=18.0.0"}},
    }
    if with_icon:
        manifest["icon"] = "icon.png"
    return manifest


def build_claude_desktop_bundle(app: Any, target_path: str) -> None:
    """Write the extension file for the running QualCoder to target_path."""

    port = ExternalMcpController.port_from_settings(app.settings)
    mcp_server = app.ai_mcp_server
    bridge_config = {
        "version": BUNDLE_VERSION,
        "port": port,
        "instructions": mcp_server._server_instructions(),
        "snapshot": catalog_snapshot(mcp_server),
    }
    with_icon = os.path.isfile(ICON_FILE)
    directory = os.path.dirname(os.path.abspath(target_path))
    handle, temp_path = tempfile.mkstemp(suffix=".mcpb.tmp", dir=directory)
    os.close(handle)
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps(bundle_manifest(port, with_icon), indent=2))
            bundle.writestr("server/index.js", BRIDGE_JS)
            bundle.writestr("server/config.json", json.dumps(bridge_config, ensure_ascii=False))
            if with_icon:
                bundle.write(ICON_FILE, "icon.png")
        os.replace(temp_path, target_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# Node script packed as server/index.js. Claude Desktop ships Node, so nothing else is installed.
BRIDGE_JS = r'''#!/usr/bin/env node
// QualCoder bridge for Claude Desktop: stdio MCP <-> QualCoder's local HTTP MCP endpoint.
// No dependencies, Node core modules only.
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const readline = require("readline");

const HOST = "127.0.0.1";
const DEFAULT_PORT = 47363;
const FALLBACK_PROTOCOL = "2025-06-18";
const KNOWN_PROTOCOLS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];
const REQUEST_TIMEOUT_MS = 10 * 60 * 1000;
const LIST_TOOL = "qualcoder_list_resources";
const READ_TOOL = "qualcoder_read_resource";

function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, "config.json"), "utf8"));
  } catch (err) {
    return {};
  }
}

const config = loadConfig();
const snapshot = config.snapshot || {};
const BRIDGE_VERSION = String(config.version || "1.0.0");

function validPort(value) {
  const port = Number.parseInt(String(value), 10);
  return Number.isInteger(port) && port >= 1024 && port <= 65535 ? port : null;
}

// An unset user option can arrive empty or as the literal placeholder, so fall back
const PORT = validPort(process.env.QUALCODER_MCP_PORT) || validPort(config.port) || DEFAULT_PORT;
const ENDPOINT = `http://${HOST}:${PORT}/mcp`;

const UNREACHABLE =
  `QualCoder is not reachable at ${ENDPOINT}. Ask the user to check that: ` +
  "(1) QualCoder is running; " +
  "(2) 'allow external MCP access' is ticked in QualCoder Settings, under AI Integration; " +
  "(3) the port in this extension's settings matches QualCoder's (default 47363). Then try again.";

function log(text) {
  process.stderr.write(`[qualcoder-bridge] ${text}\n`);
}

function send(message) {
  process.stdout.write(JSON.stringify(message) + "\n");
}

class UnreachableError extends Error {}

const inFlight = new Map();
let internalSeq = 0;

// POST one JSON-RPC message, resolve with the response that carries the same id
function postRpc(message, trackId) {
  return new Promise((resolve, reject) => {
    const body = Buffer.from(JSON.stringify(message), "utf8");
    let settled = false;
    let answer = null;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      if (trackId !== undefined) inFlight.delete(trackId);
      fn(value);
    };
    const onMessage = (payload) => {
      if (payload && payload.id === message.id && ("result" in payload || "error" in payload)) {
        answer = payload;
      } else if (payload && typeof payload.method === "string" && payload.id === undefined) {
        send(payload);  // Server notification, e.g. progress
      }
    };
    const req = http.request(
      {
        host: HOST,
        port: PORT,
        path: "/mcp",
        method: "POST",
        agent: false,  // Fresh connection each time, QualCoder may have restarted
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json, text/event-stream",
          "Content-Length": body.length,
        },
      },
      (res) => {
        const isStream = String(res.headers["content-type"] || "").includes("text/event-stream");
        let buffer = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          buffer += chunk;
          if (!isStream) return;
          buffer = buffer.replace(/\r\n/g, "\n");
          let cut = buffer.indexOf("\n\n");
          while (cut !== -1) {
            parseEvent(buffer.slice(0, cut), onMessage);
            buffer = buffer.slice(cut + 2);
            cut = buffer.indexOf("\n\n");
          }
        });
        res.on("end", () => {
          if (isStream) {
            parseEvent(buffer.replace(/\r\n?/g, "\n"), onMessage);
          } else if (buffer.trim() !== "") {
            try {
              onMessage(JSON.parse(buffer));
            } catch (err) {
              log(`Unreadable response body (HTTP ${res.statusCode})`);
            }
          }
          if (answer !== null) return finish(resolve, answer);
          finish(reject, new Error(`QualCoder returned HTTP ${res.statusCode} without a result.`));
        });
        res.on("error", (err) => finish(reject, err));
      }
    );
    req.setTimeout(REQUEST_TIMEOUT_MS, () => req.destroy(new Error("QualCoder did not answer in time.")));
    req.on("error", (err) => {
      const refused = ["ECONNREFUSED", "ECONNRESET", "EHOSTUNREACH", "ENOTFOUND", "ETIMEDOUT"];
      finish(reject, refused.includes(err.code) ? new UnreachableError(UNREACHABLE) : err);
    });
    if (trackId !== undefined) inFlight.set(trackId, req);
    req.end(body);
  });
}

function parseEvent(block, onMessage) {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");
  if (data.trim() === "") return;
  try {
    onMessage(JSON.parse(data));
  } catch (err) {
    log("Skipped an unreadable server event");
  }
}

function rpc(method, params, id, trackId) {
  const message = { jsonrpc: "2.0", id: id === undefined ? `bridge-${++internalSeq}` : id, method };
  if (params !== undefined) message.params = params;
  return postRpc(message, trackId);
}

// Claude only accepts tool names made of letters, digits, "_" and "-"
const toServerName = new Map();

function exposeTools(serverTools) {
  const used = new Set([LIST_TOOL, READ_TOOL]);
  const renamed = [];
  toServerName.clear();
  for (const tool of serverTools) {
    const base = String(tool.name).replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 60) || "tool";
    let safe = base;
    for (let n = 2; used.has(safe); n++) safe = `${base}_${n}`;
    used.add(safe);
    toServerName.set(safe, tool.name);
    renamed.push([tool.name, safe]);
  }
  const mentioned = renamed.filter(([name, safe]) => name !== safe).sort((a, b) => b[0].length - a[0].length);
  return serverTools.map((tool, index) => {
    let description = String(tool.description || "");
    for (const [name, safe] of mentioned) description = description.split(name).join(safe);
    return { ...tool, name: renamed[index][1], description };
  });
}

function resourceCatalogText() {
  const lines = [];
  for (const item of snapshot.resources || []) lines.push(`${item.uri} : ${item.description || item.name || ""}`);
  for (const item of snapshot.resourceTemplates || []) {
    lines.push(`${item.uriTemplate} : ${item.description || item.name || ""}`);
  }
  return lines.join("\n");
}

function bridgeTools() {
  return [
    {
      name: LIST_TOOL,
      title: "List QualCoder resources",
      description:
        "List the qualcoder:// URIs that expose the open project's data (documents, cases, codes, " +
        "coded segments, annotations, searches, help pages). Read them with " + READ_TOOL + ".",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true },
    },
    {
      name: READ_TOOL,
      title: "Read a QualCoder resource",
      description:
        "Read project data from QualCoder by URI. This is the way to read documents, cases, coded " +
        "segments and annotations, and to search the texts. Filters and paging go in the query " +
        "string, for example qualcoder://search/regex?pattern=migra&file_ids=1. Available URIs:\n" +
        resourceCatalogText(),
      inputSchema: {
        type: "object",
        properties: { uri: { type: "string", description: "A qualcoder:// URI, with optional query parameters." } },
        required: ["uri"],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true },
    },
  ];
}

function toolError(text) {
  return { content: [{ type: "text", text }], isError: true };
}

function errorText(error) {
  if (!error) return "Unknown error.";
  const extra = typeof error.data === "string" && error.data !== "" ? ` (${error.data})` : "";
  return `${error.message || "Error"}${extra}`;
}

async function liveOrSnapshot(method, key, params) {
  try {
    const response = await rpc(method, params);
    if (response.result && Array.isArray(response.result[key])) return response.result;
  } catch (err) {
    if (!(err instanceof UnreachableError)) log(`${method}: ${err.message}`);
  }
  return { [key]: snapshot[key] || [] };
}

async function listTools(params) {
  const result = await liveOrSnapshot("tools/list", "tools", params);
  const tools = exposeTools(result.tools);
  const firstPage = !params || params.cursor === undefined || params.cursor === null;
  return { ...result, tools: firstPage ? tools.concat(bridgeTools()) : tools };
}

async function callTool(params, trackId) {
  const name = String((params && params.name) || "");
  const args = (params && params.arguments) || {};
  try {
    if (name === LIST_TOOL) {
      const resources = await liveOrSnapshot("resources/list", "resources");
      const templates = await liveOrSnapshot("resources/templates/list", "resourceTemplates");
      const listing = { resources: resources.resources, resourceTemplates: templates.resourceTemplates };
      return { content: [{ type: "text", text: JSON.stringify(listing, null, 1) }] };
    }
    if (name === READ_TOOL) {
      if (typeof args.uri !== "string" || args.uri.trim() === "") return toolError("Missing uri.");
      const response = await rpc("resources/read", { uri: args.uri.trim() }, undefined, trackId);
      if (response.error) return toolError(errorText(response.error));
      const contents = (response.result && response.result.contents) || [];
      const content = contents.map((item) => ({
        type: "text",
        text: typeof item.text === "string" ? item.text : `[binary content, ${item.mimeType || "unknown type"}]`,
      }));
      return { content: content.length ? content : [{ type: "text", text: "(empty)" }] };
    }
    if (toServerName.size === 0) exposeTools(snapshot.tools || []);
    const forwarded = { ...params, name: toServerName.get(name) || name };
    const response = await rpc("tools/call", forwarded, undefined, trackId);
    return response.error ? toolError(errorText(response.error)) : response.result;
  } catch (err) {
    return toolError(err.message);
  }
}

function initializeResult(params) {
  const requested = params && params.protocolVersion;
  const guide =
    " Start with project_get_status. Project data is read with " + READ_TOOL + " using qualcoder:// " +
    "URIs (" + LIST_TOOL + " shows them). Tools that change the project follow the AI permission " +
    "level chosen in QualCoder (Read-only, Sandboxed or Full access). QualCoder must be running " +
    "with a project open and external MCP access enabled.";
  return {
    protocolVersion: KNOWN_PROTOCOLS.includes(requested) ? requested : FALLBACK_PROTOCOL,
    capabilities: { tools: { listChanged: false }, resources: { subscribe: false, listChanged: false } },
    serverInfo: { name: "qualcoder", title: "QualCoder", version: BRIDGE_VERSION },
    instructions: String(config.instructions || "QualCoder qualitative data analysis.") + guide,
  };
}

let pending = 0;
let closing = false;

async function handleRequest(message) {
  const { id, method, params } = message;
  const reply = (result) => send({ jsonrpc: "2.0", id, result });
  pending += 1;
  try {
    switch (method) {
      case "initialize":
        return reply(initializeResult(params));
      case "ping":
        return reply({});
      case "tools/list":
        return reply(await listTools(params));
      case "tools/call": {
        const started = Date.now();
        const toolName = String((params && params.name) || "");
        log(`call ${toolName} received`);
        const result = await callTool(params, id);
        log(`call ${toolName} ${result && result.isError ? "failed" : "done"} in ${Date.now() - started} ms`);
        return reply(result);
      }
      case "resources/list":
        return reply(await liveOrSnapshot(method, "resources", params));
      case "resources/templates/list":
        return reply(await liveOrSnapshot(method, "resourceTemplates", params));
      case "prompts/list":
        return reply({ prompts: [] });
      default:
        return send(await rpc(method, params, id, id));
    }
  } catch (err) {
    return send({ jsonrpc: "2.0", id, error: { code: -32000, message: err.message } });
  } finally {
    pending -= 1;
    if (closing && pending === 0) process.exit(0);
  }
}

function handleMessage(message) {
  if (Array.isArray(message)) return message.forEach(handleMessage);
  if (!message || typeof message !== "object" || typeof message.method !== "string") return;
  if (message.id === undefined || message.id === null) {
    if (message.method === "notifications/cancelled" && message.params) {
      const req = inFlight.get(message.params.requestId);
      if (req) req.destroy(new Error("Cancelled by the client."));
    }
    return;
  }
  handleRequest(message);
}

process.stdin.setEncoding("utf8");
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
  if (line.trim() === "") return;
  try {
    handleMessage(JSON.parse(line));
  } catch (err) {
    send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } });
  }
});
input.on("close", () => {
  closing = true;
  if (pending === 0) process.exit(0);
  setTimeout(() => process.exit(0), 5000);
});
process.stdout.on("error", () => process.exit(0));
log(`Bridge ${BRIDGE_VERSION} ready, QualCoder endpoint ${ENDPOINT}`);
'''
