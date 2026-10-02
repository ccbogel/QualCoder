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

Generic stdio to HTTP bridge for QualCoder's external MCP access.

Lets MCP clients that only speak stdio use the HTTP endpoint of a running QualCoder:

    qualcoder-mcp-stdio --url http://127.0.0.1:47363/mcp
    python -m qualcoder.mcp_stdio --port 47363

Built on the official MCP SDK. It only adapts the transport; tool names, permissions,
locks and error classification stay in QualCoder.
"""

import argparse
import asyncio
import sys
from typing import Any, Awaitable, Callable, Optional

from mcp import ClientSession, types
from mcp.shared.exceptions import MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.server import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

DEFAULT_URL = "http://127.0.0.1:47363/mcp"
BRIDGE_VERSION = "1.0.0"


class QualCoderStdioBridge:
    """One stdio server whose handlers forward to QualCoder over Streamable HTTP."""

    def __init__(self, url: str):
        self.url = url
        self.instructions = "QualCoder qualitative data analysis."
        self.unreachable = (
            f"QualCoder is not reachable at {url}. Ask the user to check that QualCoder is running, "
            "that 'allow external MCP access' is ticked in Settings under AI Integration, "
            "and that the port matches. Then try again."
        )
        self.server = Server(
            "qualcoder",
            version=BRIDGE_VERSION,
            title="QualCoder",
            instructions=self.instructions,
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
            on_list_resources=self._list_resources,
            on_list_resource_templates=self._list_resource_templates,
            on_read_resource=self._read_resource,
            on_list_prompts=self._list_prompts,
        )

    async def _with_session(self, operation: Callable[[ClientSession], Awaitable[Any]]) -> Any:
        """Open a fresh session per request; QualCoder's endpoint is stateless and may restart."""

        try:
            async with streamable_http_client(self.url) as streams:
                async with ClientSession(
                    streams[0], streams[1],
                    client_info=types.Implementation(name="qualcoder-mcp-stdio", version=BRIDGE_VERSION),
                ) as session:
                    init = await session.initialize()
                    if init.instructions:
                        self.instructions = init.instructions
                    return await operation(session)
        except MCPError:
            raise  # A protocol error from QualCoder is forwarded as is
        except Exception as err:
            # Anything else here is transport trouble, QualCoder is not listening
            raise ConnectionError(self.unreachable) from err

    async def _list_tools(self, _ctx: ServerRequestContext[Any], params: Optional[types.PaginatedRequestParams]):
        try:
            return await self._with_session(lambda s: s.list_tools(params=params))
        except ConnectionError:
            return types.ListToolsResult(tools=[])

    async def _call_tool(self, _ctx: ServerRequestContext[Any], params: types.CallToolRequestParams):
        try:
            return await self._with_session(lambda s: s.call_tool(params.name, params.arguments or {}))
        except ConnectionError as err:
            return types.CallToolResult(content=[types.TextContent(type="text", text=str(err))], isError=True)

    async def _list_resources(self, _ctx: ServerRequestContext[Any], params: Optional[types.PaginatedRequestParams]):
        try:
            return await self._with_session(lambda s: s.list_resources(params=params))
        except ConnectionError:
            return types.ListResourcesResult(resources=[])

    async def _list_resource_templates(
            self, _ctx: ServerRequestContext[Any], params: Optional[types.PaginatedRequestParams]
    ):
        try:
            return await self._with_session(
                lambda s: s.list_resource_templates(params=params)
            )
        except ConnectionError:
            return types.ListResourceTemplatesResult(resourceTemplates=[])

    async def _read_resource(self, _ctx: ServerRequestContext[Any], params: types.ReadResourceRequestParams):
        return await self._with_session(lambda s: s.read_resource(params.uri))

    async def _list_prompts(self, _ctx: ServerRequestContext[Any], _params: Optional[types.PaginatedRequestParams]):
        return types.ListPromptsResult(prompts=[])

    async def serve(self) -> None:
        options = self.server.create_initialization_options()
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, options)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="stdio bridge to a running QualCoder's MCP endpoint")
    parser.add_argument("--url", default=None, help=f"MCP endpoint (default {DEFAULT_URL})")
    parser.add_argument("--port", type=int, default=None, help="shortcut for http://127.0.0.1:PORT/mcp")
    args = parser.parse_args(argv)
    url = args.url or (f"http://127.0.0.1:{args.port}/mcp" if args.port else DEFAULT_URL)
    print(f"[qualcoder-mcp-stdio] bridging stdio to {url}", file=sys.stderr, flush=True)
    try:
        asyncio.run(QualCoderStdioBridge(url).serve())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
