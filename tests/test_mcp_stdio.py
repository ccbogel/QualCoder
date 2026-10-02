import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
import uvicorn

from qualcoder.mcp_stdio import QualCoderStdioBridge, QualCoderUnreachableError, launch_gui


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

    def test_source_gui_launch_uses_current_environment_on_all_platforms(self):
        source_path = Path(__file__).resolve().parents[1] / "src"
        for platform_name in ("win32", "darwin", "linux"):
            with self.subTest(platform=platform_name), \
                    patch("qualcoder.mcp_stdio.sys.platform", platform_name), \
                    patch("qualcoder.mcp_stdio.sys.frozen", False, create=True), \
                    patch.dict(os.environ, {"PYTHONPATH": "existing-path"}), \
                    patch("qualcoder.mcp_stdio.subprocess.Popen") as popen:
                launch_gui()
            self.assertEqual([sys.executable, "-m", "qualcoder"], popen.call_args.args[0])
            options = popen.call_args.kwargs
            self.assertEqual(str(source_path), options["cwd"])
            self.assertEqual(
                str(source_path) + os.pathsep + "existing-path", options["env"]["PYTHONPATH"],
            )
            for stream in ("stdin", "stdout", "stderr"):
                self.assertEqual(subprocess.DEVNULL, options[stream])
            if platform_name == "win32":
                self.assertTrue(options["creationflags"] & subprocess.CREATE_NO_WINDOW)
                self.assertNotIn("start_new_session", options)
            else:
                self.assertTrue(options["start_new_session"])
                self.assertNotIn("creationflags", options)

    def test_frozen_gui_launch_resets_pyinstaller_environment(self):
        with patch("qualcoder.mcp_stdio.sys.frozen", True, create=True), \
                patch("qualcoder.mcp_stdio.subprocess.Popen") as popen:
            launch_gui()
        self.assertEqual([sys.executable], popen.call_args.args[0])
        self.assertEqual("1", popen.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"])


class TestMcpStdioStartup(IsolatedAsyncioTestCase):
    """Exercise attach, startup, failure and cancellation without launching a real GUI."""

    async def test_existing_server_does_not_start_gui(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        with patch.object(bridge, "_probe", AsyncMock(return_value=True)), \
                patch("qualcoder.mcp_stdio.launch_gui") as launch:
            await bridge.ensure_server(1)
        launch.assert_not_called()

    async def test_waits_for_launched_gui_before_serving(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        with patch.object(bridge, "_probe", AsyncMock(side_effect=[False, False, True])), \
                patch.object(bridge, "serve", AsyncMock()) as serve, \
                patch("qualcoder.mcp_stdio.launch_gui", return_value=MagicMock(poll=lambda: None)) as launch, \
                patch("qualcoder.mcp_stdio.asyncio.sleep", AsyncMock()), \
                patch("sys.stderr"):
            await bridge.run(5)
        launch.assert_called_once()
        serve.assert_awaited_once()

    async def test_startup_timeout_does_not_stop_gui(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        process = MagicMock(poll=lambda: None)
        with patch.object(bridge, "_probe", AsyncMock(return_value=False)), \
                patch("qualcoder.mcp_stdio.launch_gui", return_value=process), patch("sys.stderr"):
            with self.assertRaisesRegex(QualCoderUnreachableError, "within"):
                await bridge.ensure_server(0.01)
        process.terminate.assert_not_called()

    async def test_failed_launcher_reports_exit_code(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        with patch.object(bridge, "_probe", AsyncMock(return_value=False)), \
                patch("qualcoder.mcp_stdio.launch_gui", return_value=MagicMock(poll=lambda: 3)), \
                patch("sys.stderr"):
            with self.assertRaisesRegex(QualCoderUnreachableError, "code 3"):
                await bridge.ensure_server(1)

    async def test_no_start_and_remote_endpoint_never_launch_gui(self):
        for url, auto_start in (("http://127.0.0.1:47363/mcp", False), ("https://example.com/mcp", True)):
            bridge = QualCoderStdioBridge(url)
            with patch.object(bridge, "_probe", AsyncMock(return_value=False)), \
                    patch("qualcoder.mcp_stdio.launch_gui") as launch:
                with self.assertRaises(QualCoderUnreachableError):
                    await bridge.ensure_server(1, auto_start)
            launch.assert_not_called()

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
            with patch("qualcoder.mcp_stdio.launch_gui") as launch:
                await bridge.ensure_server(1)
            launch.assert_not_called()
            source = Path(__file__).resolve().parents[1] / "src"
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "qualcoder", "--mcp-stdio", "--port", str(port), "--no-start"],
                env=dict(os.environ, PYTHONPATH=str(source)),
            )
            async with asyncio.timeout(20):
                async with stdio_client(parameters) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        initialized = await session.initialize()
                        self.assertEqual("qualcoder", initialized.server_info.name)
                        tools_result = await session.list_tools()
                        self.assertEqual(["test_tool"], [tool.name for tool in tools_result.tools])

    async def test_other_mcp_server_does_not_trigger_gui_startup(self):
        async with self.http_server("another-application") as port:
            bridge = QualCoderStdioBridge(f"http://127.0.0.1:{port}/mcp")
            with patch("qualcoder.mcp_stdio.launch_gui") as launch:
                # The HTTP SDK's task groups may wrap the identity error.
                with self.assertRaises((ValueError, ExceptionGroup)) as caught:
                    await bridge.ensure_server(1)
            self.assertIn("another-application", str(caught.exception) + repr(caught.exception))
            launch.assert_not_called()

    async def test_protocol_error_or_cancellation_never_launch_gui(self):
        bridge = QualCoderStdioBridge("http://127.0.0.1:47363/mcp")
        for failure in (ValueError("wrong server"), asyncio.CancelledError()):
            with patch.object(bridge, "_probe", AsyncMock(side_effect=failure)), \
                    patch("qualcoder.mcp_stdio.launch_gui") as launch:
                with self.assertRaises(type(failure)):
                    await bridge.ensure_server(1)
            launch.assert_not_called()
