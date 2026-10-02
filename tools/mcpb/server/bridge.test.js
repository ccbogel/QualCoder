"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

async function fixture() {
  const state = { online: false, calls: 0, connects: 0, toolChanges: 0, resourceChanges: 0 };
  const handlers = new Map();
  const schemas = Object.fromEntries([
    "CallToolRequestSchema", "ListToolsRequestSchema", "ListResourcesRequestSchema",
    "ListResourceTemplatesRequestSchema", "ReadResourceRequestSchema", "ListPromptsRequestSchema",
  ].map((name) => [name, name]));
  class Server {
    setRequestHandler(schema, handler) { handlers.set(schema, handler); }
    async connect() {}
    async sendToolListChanged() { state.toolChanges++; }
    async sendResourceListChanged() { state.resourceChanges++; }
  }
  class Client {
    async connect() {
      state.connects++;
      if (!state.online) throw new Error("ECONNREFUSED");
    }
    async close() {}
    getServerVersion() { return { name: "QualCoder", version: "4.0" }; }
    async listTools() { return { tools: [{ name: "live" }] }; }
    async callTool() {
      state.calls++;
      throw new Error("ECONNRESET after commit");
    }
  }
  const context = vm.createContext({
    URL,
    process: { env: {}, stderr: { write() {} }, exit() { assert.fail("bridge exited"); } },
    setInterval() { return { unref() {} }; },
    __dirname,
    require(name) {
      if (name === "fs") return { readFileSync: () => JSON.stringify({ snapshot: { tools: [{ name: "offline" }] } }) };
      if (name === "path") return path;
      if (name.endsWith("types.js")) return schemas;
      if (name.endsWith("server/index.js")) return { Server };
      if (name.endsWith("client/index.js")) return { Client };
      if (name.endsWith("server/stdio.js")) return { StdioServerTransport: class {} };
      if (name.endsWith("client/streamableHttp.js")) return { StreamableHTTPClientTransport: class {} };
      throw new Error(name);
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "bridge.js"), "utf8"), context);
  await new Promise(setImmediate);
  return { state, handlers };
}

test("first offline-to-online connection refreshes the catalog", async () => {
  const { state, handlers } = await fixture();
  const list = handlers.get("ListToolsRequestSchema");
  assert.equal((await list({}, {})).tools[0].name, "offline");
  state.online = true;
  assert.equal((await list({}, {})).tools[0].name, "live");
  assert.equal(state.toolChanges, 1);
  assert.equal(state.resourceChanges, 1);
});

test("a lost tool response never replays a potentially committed write", async () => {
  const { state, handlers } = await fixture();
  state.online = true;
  const call = handlers.get("CallToolRequestSchema");
  const result = await call({ params: { name: "codes_create_code", arguments: {} } }, {});
  assert.equal(result.isError, true);
  assert.equal(state.calls, 1);
  const connects = state.connects;
  await handlers.get("ListToolsRequestSchema")({}, {});
  assert.equal(state.connects, connects + 1);
});
