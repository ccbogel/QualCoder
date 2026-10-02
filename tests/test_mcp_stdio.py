import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import httpx2

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
                return SimpleNamespace(instructions="")

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
