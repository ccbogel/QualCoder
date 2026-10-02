import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import httpx2
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
import uvicorn

from qualcoder.mcp_stdio import QualCoderStdioBridge, QualCoderUnreachableError


class TestMcpStdio(TestCase):
    """Check headless startup and preservation of non-transport failures."""

    def test_main_detects_stdio_before_gui_imports(self):
        source = Path(__file__).resolve().parents[1] / "src"
        script = """
import importlib.abc
import runpy
import sys

class BlockGui(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('PyQt6', 'qualcoder.app', 'qualcoder.ai_runtime')):
            raise AssertionError('GUI imported: ' + fullname)

sys.meta_path.insert(0, BlockGui())
sys.argv = ['qualcoder', '--mcp-stdio', '--help']
runpy.run_module('qualcoder', run_name='__main__')
"""
        environment = dict(os.environ, PYTHONPATH=str(source))
        result = subprocess.run(
            [sys.executable, "-c", script], env=environment,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("stdio bridge", result.stdout)

    def test_session_only_classifies_transport_errors(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")

        @asynccontextmanager
        async def transport(url: str):
            yield (None, None)

        class Session:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def initialize(self):
                return SimpleNamespace(instructions="", server_info=SimpleNamespace(name="qualcoder-mcp"))

        failures = [
            (httpx2.ConnectError("connection refused"), QualCoderUnreachableError),
            (ExceptionGroup("transport", [httpx2.ConnectError("refused")]), QualCoderUnreachableError),
            (ValueError("implementation bug"), ValueError),
            (ExceptionGroup("mixed", [httpx2.ConnectError("refused"), KeyError("bug")]), ExceptionGroup),
            (asyncio.CancelledError(), asyncio.CancelledError),
        ]
        with patch("qualcoder.mcp_stdio.streamable_http_client", transport), \
                patch("qualcoder.mcp_stdio.ClientSession", Session):
            for failure, expected in failures:
                with self.subTest(failure=failure):
                    async def operation(session: Session):
                        raise failure

                    with self.assertRaises(expected) as caught:
                        asyncio.run(bridge._with_session(operation))
                    if expected is not QualCoderUnreachableError:
                        self.assertIs(failure, caught.exception)

    def test_stdio_requires_available_streams(self):
        from qualcoder.mcp_stdio import main

        with patch("sys.stdin", None), patch("sys.stderr"):
            with self.assertRaises(SystemExit) as caught:
                main([])
        self.assertEqual(2, caught.exception.code)

    def test_unavailable_server_exits_cleanly_without_gui_imports(self):
        source = Path(__file__).resolve().parents[1] / "src"
        script = """
import importlib.abc
import runpy
import sys
from unittest.mock import patch

class BlockGui(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('PyQt6', 'qualcoder.app', 'qualcoder.ai_runtime')):
            raise AssertionError('GUI imported: ' + fullname)

sys.meta_path.insert(0, BlockGui())
sys.argv = ['qualcoder', '--mcp-stdio', '--port', sys.argv[1]]
with patch('subprocess.Popen', side_effect=AssertionError('GUI launched')):
    runpy.run_module('qualcoder', run_name='__main__')
"""
        # Keep the port reserved without listening, so no server can answer the probe.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            result = subprocess.run(
                [sys.executable, "-c", script, str(port)],
                env=dict(os.environ, PYTHONPATH=str(source)),
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        self.assertIn("Start QualCoder first", result.stderr)
        self.assertIn("Settings > AI Integration", result.stderr)
        self.assertIn("Then reconnect the MCP client", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class TestMcpStdioStartup(IsolatedAsyncioTestCase):
    """Exercise attachment, failure and cancellation without launching a GUI."""

    async def test_existing_server_is_ready_before_serving(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        with patch.object(bridge, "_probe", AsyncMock(return_value=True)), \
                patch.object(bridge, "serve", AsyncMock()) as serve:
            await bridge.run()
        serve.assert_awaited_once()

    async def test_unavailable_server_reports_error_without_serving(self):
        for url in ("http://127.0.0.1:47363/mcp", "https://example.com/mcp"):
            bridge = QualCoderStdioBridge(url)
            with patch.object(bridge, "_probe", AsyncMock(return_value=False)), \
                    patch.object(bridge, "serve", AsyncMock()) as serve:
                with self.assertRaisesRegex(QualCoderUnreachableError, "Start QualCoder first"):
                    await bridge.run()
            serve.assert_not_awaited()

    async def test_probe_timeout_is_reported_as_unavailable(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        with patch.object(bridge, "_with_session", AsyncMock(side_effect=TimeoutError)):
            with self.assertRaisesRegex(QualCoderUnreachableError, "Start QualCoder first"):
                await bridge.ensure_server()

    @asynccontextmanager
    async def http_server(self, name: str = "qualcoder-mcp"):
        async def list_tools(context, params):
            return types.ListToolsResult(tools=[types.Tool(
                name="test_tool", inputSchema={"type": "object"},
            )])

        mcp_server = Server(name, version="test", on_list_tools=list_tools)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        http_server = uvicorn.Server(uvicorn.Config(
            mcp_server.streamable_http_app(stateless_http=True, host="127.0.0.1"),
            log_level="error", lifespan="on",
        ))
        task = asyncio.create_task(http_server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not http_server.started:
                    if task.done():
                        await task
                        self.fail("HTTP server exited before startup")
                    await asyncio.sleep(0.01)
            yield port
        finally:
            http_server.should_exit = True
            await asyncio.wait_for(task, 10)
            listener.close()

    async def test_real_mcp_initialization_and_stdio_round_trip(self):
        async with self.http_server() as port:
            bridge = QualCoderStdioBridge(f"http://127.0.0.1:{port}/mcp")
            await bridge.ensure_server()
            source = Path(__file__).resolve().parents[1] / "src"
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "qualcoder", "--mcp-stdio", "--port", str(port)],
                env=dict(os.environ, PYTHONPATH=str(source)),
            )
            async with asyncio.timeout(20):
                async with stdio_client(parameters) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        initialized = await session.initialize()
                        self.assertEqual("qualcoder", initialized.server_info.name)
                        tools_result = await session.list_tools()
                        self.assertEqual(["test_tool"], [tool.name for tool in tools_result.tools])

    async def test_other_mcp_server_is_rejected(self):
        async with self.http_server("another-application") as port:
            bridge = QualCoderStdioBridge(f"http://127.0.0.1:{port}/mcp")
            # The HTTP SDK's task groups may wrap the identity error.
            with self.assertRaises((ValueError, ExceptionGroup)) as caught:
                await bridge.ensure_server()
            self.assertIn("another-application", str(caught.exception) + repr(caught.exception))

    async def test_protocol_error_or_cancellation_never_serves(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        for failure in (ValueError("wrong server"), asyncio.CancelledError()):
            with patch.object(bridge, "_probe", AsyncMock(side_effect=failure)), \
                    patch.object(bridge, "serve", AsyncMock()) as serve:
                with self.assertRaises(type(failure)):
                    await bridge.run()
            serve.assert_not_awaited()
