#!/usr/bin/env node
// QualCoder bridge for Claude Desktop: stdio MCP <-> QualCoder's local Streamable HTTP endpoint.
// Built on the official MCP SDK. It only adapts the transport: tool names, resource tools,
// permissions, locks and error classification all live in QualCoder.
"use strict";

const fs = require("fs");
const path = require("path");
const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const { Client } = require("@modelcontextprotocol/sdk/client/index.js");
const { StreamableHTTPClientTransport } = require("@modelcontextprotocol/sdk/client/streamableHttp.js");
const {
  CallToolRequestSchema, ListToolsRequestSchema, ListResourcesRequestSchema,
  ListResourceTemplatesRequestSchema, ReadResourceRequestSchema, ListPromptsRequestSchema,
} = require("@modelcontextprotocol/sdk/types.js");

const DEFAULT_PORT = 47363;
const RECONNECT_MS = 3000;

function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, "config.json"), "utf8"));
  } catch (err) {
    return {};
  }
}

const config = loadConfig();
const snapshot = config.snapshot || {};  // Catalog of the matching QualCoder release, shown while QualCoder is closed
const BRIDGE_VERSION = String(config.version || "0.0.0");

function validPort(value) {
  const port = Number.parseInt(String(value), 10);
  return Number.isInteger(port) && port >= 1024 && port <= 65535 ? port : null;
}

const PORT = validPort(process.env.QUALCODER_MCP_PORT) || validPort(config.port) || DEFAULT_PORT;
const URL_ = new URL(`http://127.0.0.1:${PORT}/mcp`);
const UNREACHABLE =
  `QualCoder is not reachable at ${URL_.href}. Ask the user to check that: ` +
  "(1) QualCoder is running; " +
  "(2) 'allow external MCP access' is ticked in QualCoder Settings, under AI Integration; " +
  "(3) the port in this extension's settings matches QualCoder's (default 47363). Then try again.";

function log(text) {
  process.stderr.write(`[qualcoder-bridge] ${text}\n`);
}

let client = null;
let connecting = null;
let announced = false;

// One client per QualCoder lifetime; a failed call drops it so the next call reconnects
async function connect() {
  if (client) return client;
  if (connecting) return connecting;
  connecting = (async () => {
    const candidate = new Client({ name: "qualcoder-claude-desktop-bridge", version: BRIDGE_VERSION });
    try {
      await candidate.connect(new StreamableHTTPClientTransport(URL_));
    } catch (err) {
      throw new UnreachableError();
    } finally {
      connecting = null;
    }
    candidate.onclose = () => { if (client === candidate) client = null; };
    client = candidate;
    const info = candidate.getServerVersion() || {};
    log(`Connected to ${info.name || "QualCoder"} ${info.version || ""}`.trim());
    if (announced) {
      // QualCoder came back: ask the client to refresh its catalog instead of trusting the snapshot
      server.sendToolListChanged().catch(() => {});
      server.sendResourceListChanged().catch(() => {});
    }
    announced = true;
    return candidate;
  })();
  return connecting;
}

class UnreachableError extends Error {}

async function withClient(call, retry = true) {
  const active = await connect();
  try {
    return await call(active);
  } catch (err) {
    if (err && err.name === "AbortError") throw err;
    if (isTransportFailure(err)) {
      log(`Transport failure: ${err.message}`);
      if (client === active) client = null;
      active.close().catch(() => {});
      if (retry) return withClient(call, false);  // QualCoder may have just restarted
      throw new UnreachableError();
    }
    throw err;  // Protocol errors from QualCoder are forwarded untouched
  }
}

function isTransportFailure(err) {
  const text = String((err && err.message) || "");
  return /ECONNREFUSED|ECONNRESET|EHOSTUNREACH|ETIMEDOUT|fetch failed|socket hang up|Not connected|Connection closed/i.test(text);
}

const server = new Server(
  { name: "qualcoder", title: "QualCoder", version: BRIDGE_VERSION },
  {
    capabilities: { tools: { listChanged: true }, resources: { subscribe: false, listChanged: true }, prompts: {} },
    instructions:
      String(config.instructions || "QualCoder qualitative data analysis.") +
      " QualCoder must be running with external MCP access enabled; open a project before working with its data.",
  }
);

server.setRequestHandler(ListToolsRequestSchema, async (request, extra) => {
  try {
    return await withClient((c) => c.listTools(request.params, { signal: extra.signal }));
  } catch (err) {
    if (err instanceof UnreachableError) return { tools: snapshot.tools || [] };
    throw err;
  }
});

server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
  try {
    return await withClient((c) => c.callTool(request.params, undefined, { signal: extra.signal }));
  } catch (err) {
    if (err instanceof UnreachableError) return { content: [{ type: "text", text: UNREACHABLE }], isError: true };
    throw err;
  }
});

server.setRequestHandler(ListResourcesRequestSchema, async (request, extra) => {
  try {
    return await withClient((c) => c.listResources(request.params, { signal: extra.signal }));
  } catch (err) {
    if (err instanceof UnreachableError) return { resources: snapshot.resources || [] };
    throw err;
  }
});

server.setRequestHandler(ListResourceTemplatesRequestSchema, async (request, extra) => {
  try {
    return await withClient((c) => c.listResourceTemplates(request.params, { signal: extra.signal }));
  } catch (err) {
    if (err instanceof UnreachableError) return { resourceTemplates: snapshot.resourceTemplates || [] };
    throw err;
  }
});

server.setRequestHandler(ReadResourceRequestSchema, async (request, extra) => {
  try {
    return await withClient((c) => c.readResource(request.params, { signal: extra.signal }));
  } catch (err) {
    if (err instanceof UnreachableError) throw new Error(UNREACHABLE);
    throw err;
  }
});

server.setRequestHandler(ListPromptsRequestSchema, async () => ({ prompts: [] }));

// While QualCoder is closed, keep trying so the catalog refreshes as soon as it opens
setInterval(() => { if (!client && !connecting) connect().catch(() => {}); }, RECONNECT_MS).unref();

async function main() {
  await server.connect(new StdioServerTransport());
  log(`Bridge ${BRIDGE_VERSION} ready, QualCoder endpoint ${URL_.href}`);
  connect().catch(() => {});
}

main().catch((err) => {
  log(`Fatal: ${err && err.message}`);
  process.exit(1);
});
