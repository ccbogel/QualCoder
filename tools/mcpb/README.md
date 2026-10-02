# QualCoder.mcpb (Claude Desktop extension)

`QualCoder.mcpb` lets Claude Desktop use the External MCP access of a running QualCoder.
It is a release artifact, not something QualCoder generates at runtime. Build it with:

    python tools/mcpb/build_mcpb.py            # writes dist/QualCoder.mcpb, version from app.py
    python tools/mcpb/build_mcpb.py --version 4.0.1 --port 47363 --output dist/QualCoder.mcpb

Requirements: Node 18+ with npm, and QualCoder's Python dependencies (the tool catalog is read
from `qualcoder.ai_mcp_server`). The bridge in `server/bridge.js` is built on the official MCP
SDK and bundled into one file with esbuild, so the extension needs nothing but the Node runtime
that Claude Desktop ships.

The builder uses `npm ci` and the committed `package-lock.json`. To update dependencies,
run `npm install --package-lock-only` in this directory and commit the updated lockfile.
Generated `.mcpb` files belong in GitHub Releases, rather than source control.
Run the bridge regression tests with `npm test` in this directory.

What the bridge does: stdio to Streamable HTTP transport, a clear message while QualCoder is
closed, and a catalog refresh (`tools/list_changed`) when QualCoder comes up. Tool names,
resource tools, permissions, database locks and error classification all live in QualCoder.
The catalog stored in `server/config.json` is only shown while QualCoder is closed and matches
the QualCoder version the file was built for.

Installing: open the `.mcpb` with Claude Desktop, or drag it into Settings > Extensions. The port
can be changed in the extension's settings if `mcp_external_port` was changed in QualCoder.

Other clients do not need this file. HTTP clients (Claude Code, Codex, IDEs) connect to
`http://127.0.0.1:47363/mcp` directly; stdio-only clients can use
`python -m qualcoder.mcp_stdio --port 47363` or
`python -m qualcoder --mcp-stdio --port 47363`. Both require a running QualCoder with
external MCP access enabled; they do not launch the GUI. Start QualCoder normally first.
The current Windows windowed executable does not provide stdin/stdout, so use a
console-enabled Python interpreter for stdio clients. Packaged executable support
and automatic GUI startup are deferred.
