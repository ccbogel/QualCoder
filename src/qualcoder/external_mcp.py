# -*- coding: utf-8 -*-

"""Local Streamable HTTP transport for QualCoder's shared MCP server."""

import asyncio
from concurrent.futures import Future
import logging
import threading
from typing import Any, Callable

from PyQt6 import QtCore
import uvicorn

from .ai_mcp_server import AiMcpExecutionContext, AiMcpServer


logger = logging.getLogger(__name__)


class ExternalMcpController(QtCore.QObject):
    """Run MCP HTTP off-thread and execute project work on the Qt thread."""

    status_changed = QtCore.pyqtSignal(str)
    _execute_requested = QtCore.pyqtSignal(object, object, object)

    HOST = "127.0.0.1"
    DEFAULT_PORT = 47363

    def __init__(self, app: Any, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.mcp_server: AiMcpServer = app.ai_mcp_server
        self._uvicorn_server: uvicorn.Server | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._active = False
        self._restart_requested = False
        self._execute_requested.connect(self._execute_on_qt_thread)
        self.mcp_server.set_external_executor(self._invoke_on_qt_thread)

    @property
    def endpoint(self) -> str:
        """Return the configured local MCP endpoint."""

        return f"http://{self.HOST}:{self.port}/mcp"

    @property
    def port(self) -> int:
        """Return a normalized configured TCP port."""

        try:
            port = int(self.app.settings.get("mcp_external_port", self.DEFAULT_PORT))
        except (TypeError, ValueError):
            port = self.DEFAULT_PORT
        if not 1024 <= port <= 65535:
            return self.DEFAULT_PORT
        return port

    @property
    def is_running(self) -> bool:
        """Return whether the listener has started and accepts operations."""

        return bool(
            self._active
            and self._uvicorn_server is not None
            and self._uvicorn_server.started
            and self._thread is not None
            and self._thread.is_alive()
        )

    def sync_with_application_state(self) -> None:
        """Start or stop the listener from current setting/project state."""

        enabled = str(self.app.settings.get("mcp_external_enabled", "False")).lower() == "true"
        project_open = self.app.conn is not None and self.app.project_path != ""
        if enabled and project_open:
            self.start()
        else:
            self._restart_requested = False
            self.stop()

    def start(self) -> None:
        """Start the localhost listener if it is not already running."""

        if self.is_running:
            return
        if self._thread is not None and self._thread.is_alive():
            self._restart_requested = True
            QtCore.QTimer.singleShot(100, self._retry_start_after_stop)
            return
        if self.app.conn is None or self.app.project_path == "":
            return

        try:
            asgi_app = self.mcp_server.streamable_http_app()
            config = uvicorn.Config(
                asgi_app,
                host=self.HOST,
                port=self.port,
                log_level="warning",
                access_log=False,
            )
            self._uvicorn_server = uvicorn.Server(config)
            self._active = True
            self._restart_requested = False
            self._thread = threading.Thread(
                target=self._serve,
                name="QualCoderExternalMCP",
                daemon=True,
            )
            self._thread.start()
            QtCore.QTimer.singleShot(100, self._report_start_status)
        except Exception as err:
            self._active = False
            logger.exception("Could not start External MCP")
            self.status_changed.emit(f"External MCP failed to start: {err}")

    @QtCore.pyqtSlot()
    def _retry_start_after_stop(self) -> None:
        """Restart automatically after a project switch finishes listener shutdown."""

        if not self._restart_requested:
            return
        if self._thread is not None and self._thread.is_alive():
            QtCore.QTimer.singleShot(100, self._retry_start_after_stop)
            return
        enabled = str(self.app.settings.get("mcp_external_enabled", "False")).lower() == "true"
        if enabled and self.app.conn is not None and self.app.project_path != "":
            self.start()
        else:
            self._restart_requested = False

    def _serve(self) -> None:
        """Run uvicorn in this worker thread's asyncio event loop."""

        try:
            asyncio.run(self._serve_async())
        except Exception as err:
            logger.exception("External MCP listener failed")
            self.status_changed.emit(f"External MCP failed: {err}")
        finally:
            self._active = False
            self._loop = None

    async def _serve_async(self) -> None:
        """Capture the listener loop and run uvicorn until shutdown."""

        self._loop = asyncio.get_running_loop()
        await self._uvicorn_server.serve()

    @QtCore.pyqtSlot()
    def _report_start_status(self) -> None:
        """Report startup success or wait briefly for uvicorn to settle."""

        if self.is_running:
            self.status_changed.emit(f"External MCP available at {self.endpoint}")
            return
        if self._thread is not None and self._thread.is_alive() and self._active:
            QtCore.QTimer.singleShot(100, self._report_start_status)
            return
        self.status_changed.emit(
            f"External MCP could not bind to {self.HOST}:{self.port}. The port may already be in use."
        )

    def stop(self) -> None:
        """Promptly reject work and ask the HTTP listener to shut down."""

        self._active = False
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_listener_on_server_loop)
            except RuntimeError:
                if self._uvicorn_server is not None:
                    self._uvicorn_server.should_exit = True
        elif self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self.status_changed.emit("External MCP stopped.")

    def _stop_listener_on_server_loop(self) -> None:
        """Close listening sockets and request graceful uvicorn shutdown."""

        if self._uvicorn_server is None:
            return
        for listener in getattr(self._uvicorn_server, "servers", []):
            listener.close()
        self._uvicorn_server.should_exit = True

    async def _invoke_on_qt_thread(
            self, operation: Callable[[], Any], execution_context: AiMcpExecutionContext
    ) -> Any:
        """Queue a synchronous project operation on Qt and await its result."""

        if not self._active:
            raise RuntimeError("External MCP is disabled.")
        future: Future[Any] = Future()
        self._execute_requested.emit(operation, execution_context, future)
        return await asyncio.wrap_future(future)

    @QtCore.pyqtSlot(object, object, object)
    def _execute_on_qt_thread(
            self,
            operation: Callable[[], Any],
            execution_context: AiMcpExecutionContext,
            future: Future[Any],
    ) -> None:
        """Execute one queued request against the currently open project."""

        if future.cancelled():
            return
        if not self._active:
            if not future.done():
                future.set_exception(RuntimeError("External MCP is disabled."))
            return
        if self.app.conn is None or self.app.project_path == "":
            if not future.done():
                future.set_exception(RuntimeError("No QualCoder project is currently open."))
            return
        try:
            result = self.mcp_server.run_with_execution_context(execution_context, operation)
        except Exception as err:
            if not future.done():
                future.set_exception(err)
        else:
            if not future.done():
                future.set_result(result)
