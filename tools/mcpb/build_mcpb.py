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

Build QualCoder.mcpb, the Claude Desktop extension, as a release artifact.

    python tools/mcpb/build_mcpb.py [--version 4.0.0] [--port 47363] [--output dist/QualCoder.mcpb]

Needs Node and npm (the bridge is bundled with esbuild) and QualCoder's Python dependencies
(the tool catalog is read from the MCP server). The result is a versioned, generic file to publish
on GitHub Releases; the port stays editable in the extension's settings.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(REPO, "src")
ICON = os.path.join(SRC, "qualcoder", "GUI", "qualcoder128.png")
DEFAULT_PORT = 47363


def qualcoder_version() -> str:
    """Return a three part semver derived from app.py's version string."""

    text = open(os.path.join(SRC, "qualcoder", "app.py"), encoding="utf-8").read()
    match = re.search(r'self\.version = "QualCoder ([0-9][0-9.]*)', text)
    parts = (match.group(1) if match else "0").strip(".").split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def catalog_snapshot() -> dict:
    """Read tools, resources and instructions from the MCP server of this source tree."""

    sys.path.insert(0, SRC)
    from qualcoder.ai_mcp_server import AiMcpExecutionContext, AiMcpServer

    class NoProjectApp:
        conn = None
        project_path = ""
        project_name = ""
        settings = {"ai_permissions": 2, "codername": "default"}
        delete_backup = True

    server = AiMcpServer(NoProjectApp())
    context = AiMcpExecutionContext(source="external_mcp", owner="External MCP")

    def collect() -> dict:
        out = {}
        for method, key in (("tools/list", "tools"), ("resources/list", "resources"),
                            ("resources/templates/list", "resourceTemplates")):
            response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}})
            if "error" in response:
                raise RuntimeError(f"{method}: {response['error'].get('message', '')}")
            out[key] = response["result"].get(key, [])
        return out

    return {"instructions": server._server_instructions(), "snapshot": server.run_with_execution_context(context, collect)}


def manifest(version: str, port: int) -> dict:
    return {
        "manifest_version": "0.3",
        "name": "qualcoder",
        "display_name": "QualCoder",
        "version": version,
        "description": "Work with the project that is open in QualCoder: read documents, cases and codes, "
                       "search the texts, and code with the permissions chosen in QualCoder.",
        "long_description": "Connects Claude Desktop to the External MCP access of a running QualCoder. "
                            "QualCoder must be open with 'allow external MCP access' ticked in Settings. "
                            "Data read by the tools is sent to the AI provider.",
        "author": {"name": "QualCoder", "url": "https://qualcoder.org"},
        "homepage": "https://qualcoder.org",
        "repository": {"type": "git", "url": "https://github.com/ccbogel/QualCoder"},
        "license": "LGPL-3.0-or-later",
        "icon": "icon.png",
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


def bundle_bridge(work: str) -> str:
    """Install the SDK and bundle server/bridge.js into one self-contained file."""

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("npm was not found; Node and npm are required to build the bridge.")
    shutil.copy(os.path.join(HERE, "package.json"), work)
    subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=work, check=True)
    # The bridge resolves the SDK from where it sits, so it is bundled from inside the work dir
    source = os.path.join(work, "bridge.js")
    shutil.copy(os.path.join(HERE, "server", "bridge.js"), source)
    out_file = os.path.join(work, "index.js")
    esbuild = os.path.join(work, "node_modules", ".bin", "esbuild" + (".cmd" if os.name == "nt" else ""))
    subprocess.run([esbuild, source, "--bundle", "--platform=node",
                    "--target=node18", "--format=cjs", f"--outfile={out_file}", "--log-level=warning"],
                   check=True, shell=os.name == "nt")
    return out_file


def build(output: str, version: str, port: int) -> None:
    catalog = catalog_snapshot()
    work = tempfile.mkdtemp(prefix="qualcoder-mcpb-")
    try:
        bridge = bundle_bridge(work)
        os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest(version, port), indent=2))
            bundle.write(bridge, "server/index.js")
            bundle.writestr("server/config.json", json.dumps({"version": version, "port": port, **catalog}, ensure_ascii=False))
            bundle.write(ICON, "icon.png")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Built {output} ({os.path.getsize(output) // 1024} KB), version {version}, port {port}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--version", default=None, help="three part semver (default: from app.py)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--output", default=os.path.join(REPO, "dist", "QualCoder.mcpb"))
    args = parser.parse_args()
    version = args.version or qualcoder_version()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Claude Desktop needs a three part version such as 4.0.0")
    build(args.output, version, args.port)


if __name__ == "__main__":
    main()
