from contextlib import asynccontextmanager
import socket
import threading
import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PyQt6 import QtCore
from starlette.applications import Starlette

from qualcoder.external_mcp import ExternalMcpController


class TestExternalMcpStartup(TestCase):
    """Exercise failed activation through the actual HTTP worker and Qt timer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])

    def setUp(self) -> None:
        translation = patch('qualcoder.external_mcp._', lambda text: text, create=True)
        translation.start()
        self.addCleanup(translation.stop)
        self.mcp_server = MagicMock()
        self.mcp_server.streamable_http_app.return_value = Starlette()
        self.controller = ExternalMcpController(SimpleNamespace(
            settings={'mcp_external_enabled': 'True'}, ai_mcp_server=self.mcp_server,
        ))
        self.failures = []
        self.failure_threads = []
        self.controller.start_failed.connect(self._record_failure)
        self.addCleanup(self._stop_controller)

    def _record_failure(self, message: str) -> None:
        self.failures.append(message)
        self.failure_threads.append(threading.get_ident())

    def _stop_controller(self) -> None:
        self.controller.stop()
        if self.controller._thread is not None:
            self.controller._thread.join(timeout=5)
            self.assertFalse(self.controller._thread.is_alive())
        self.qt_app.processEvents()

    def _wait_for_failure(self) -> None:
        deadline = time.monotonic() + 5
        while not self.failures and time.monotonic() < deadline:
            self.qt_app.processEvents()
            time.sleep(0.01)
        self.assertEqual(1, len(self.failures))
        self.assertEqual([threading.get_ident()], self.failure_threads)
        self.assertFalse(self.controller.is_running)
        self.controller._report_start_status()
        self.assertEqual(1, len(self.failures))

    def test_occupied_port_reports_failure_on_gui_thread(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.controller.app.settings['mcp_external_port'] = port
            self.controller.start()
            self._wait_for_failure()
            self.assertIn(f':{port}/mcp', self.failures[0])
            self.assertIn('OSError', self.failures[0])
            self.assertIn('another QualCoder instance', self.failures[0])

    def test_app_creation_failure_reports_original_error(self):
        self.mcp_server.streamable_http_app.side_effect = RuntimeError('Invalid MCP configuration')
        self.controller.start()
        self._wait_for_failure()
        self.assertIn('RuntimeError: Invalid MCP configuration', self.failures[0])

    def test_worker_exception_reports_original_error(self):
        with patch('qualcoder.external_mcp.uvicorn.Server.serve', side_effect=ValueError('Bad transport')):
            self.controller.start()
            self._wait_for_failure()
        self.assertIn('ValueError: Bad transport', self.failures[0])

    def test_lifespan_startup_failure_is_reported(self):
        @asynccontextmanager
        async def failed_lifespan(asgi_app: Starlette):
            raise RuntimeError('Lifespan initialization failed')
            yield

        self.mcp_server.streamable_http_app.return_value = Starlette(lifespan=failed_lifespan)
        self.controller.start()
        self._wait_for_failure()

    def test_listener_returning_without_starting_is_reported(self):
        with patch('qualcoder.external_mcp.uvicorn.Server.serve', return_value=None):
            self.controller.start()
            self._wait_for_failure()

    def test_successful_activation_and_stop_do_not_report_failure(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.controller.app.settings['mcp_external_port'] = probe.getsockname()[1]
        self.controller.start()
        deadline = time.monotonic() + 5
        while self.controller._startup_pending and time.monotonic() < deadline:
            self.qt_app.processEvents()
            time.sleep(0.01)
        self.assertTrue(self.controller.is_running)
        self.assertFalse(self.failures)
        self._stop_controller()
        self.controller._report_start_status()
        self.assertFalse(self.failures)

    def test_cancelled_start_does_not_report_failure(self):
        self.controller._startup_pending = True
        self.controller.stop()
        self.controller._report_start_status()
        self.assertFalse(self.failures)

    def test_main_window_displays_failure_as_plain_text_warning(self):
        from qualcoder.__main__ import MainWindow

        window = SimpleNamespace(app=self.controller.app)
        with patch('qualcoder.__main__.Message') as message_dialog, \
                patch('qualcoder.__main__._', lambda text: text, create=True):
            MainWindow._external_mcp_start_failed(window, 'Invalid <transport>')
        message_dialog.assert_called_once_with(
            window.app, 'External MCP', 'Invalid <transport>', 'warning',
        )
        message_dialog.return_value.setTextFormat.assert_called_once_with(QtCore.Qt.TextFormat.PlainText)
        message_dialog.return_value.exec.assert_called_once_with()
