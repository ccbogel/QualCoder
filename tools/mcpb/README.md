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
`python -m qualcoder --mcp-stdio --port 47363`.
Start QualCoder first and enable external MCP access in Settings > AI Integration.
The Python bridge verifies the running server through MCP initialization before
serving the client. If no QualCoder server responds, it exits with status 1 and prints
a message to stderr explaining how to enable access and reconnect. It never starts
a GUI, so disconnecting the client cannot close QualCoder through a child-process
relationship. The former `--no-start` and `--startup-timeout` options have been removed.

Windows builds from the updated PyInstaller specs support `QualCoder.exe --mcp-stdio`:
they retain stdin/stdout and hide a console window owned by QualCoder. Older windowed
executables still require the Python invocation. The Node extension connects to a
running QualCoder and does not launch it automatically.
