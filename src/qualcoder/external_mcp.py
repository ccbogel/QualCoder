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
    start_failed = QtCore.pyqtSignal(str)
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
        self._startup_pending = False
        self._startup_error = ""
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
        """Start or stop the listener from the current MCP setting."""

        enabled = str(self.app.settings.get("mcp_external_enabled", "False")).lower() == "true"
        if enabled:
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

        self._startup_pending = True
        self._startup_error = ""
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
            self._startup_error = f"{type(err).__name__}: {err}"
            self._report_start_failure()

    @QtCore.pyqtSlot()
    def _retry_start_after_stop(self) -> None:
        """Restart automatically after a project switch finishes listener shutdown."""

        if not self._restart_requested:
            return
        if self._thread is not None and self._thread.is_alive():
            QtCore.QTimer.singleShot(100, self._retry_start_after_stop)
            return
        enabled = str(self.app.settings.get("mcp_external_enabled", "False")).lower() == "true"
        if enabled:
            self.start()
        else:
            self._restart_requested = False

    def _serve(self) -> None:
        """Run uvicorn in this worker thread's asyncio event loop."""

        try:
            asyncio.run(self._serve_async())
        except (Exception, SystemExit) as err:
            # Uvicorn exits on startup failure, including an occupied port.
            cause = err.__cause__ or err.__context__ or err
            self._startup_error = f"{type(cause).__name__}: {cause}"
            logger.exception("External MCP listener failed")
            self.status_changed.emit(f"External MCP failed: {self._startup_error}")
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

        if not self._startup_pending:
            return
        if self.is_running:
            self._startup_pending = False
            self.status_changed.emit(f"External MCP available at {self.endpoint}")
            return
        if self._thread is not None and self._thread.is_alive() and self._active:
            QtCore.QTimer.singleShot(100, self._report_start_status)
            return
        self._report_start_failure()

    def _report_start_failure(self) -> None:
        """Report each failed activation once, on the Qt thread."""

        if not self._startup_pending:
            return
        self._startup_pending = False
        message = _("The external MCP server could not be started at {endpoint}.").format(
            endpoint=self.endpoint
        )
        message += "\n\n" + _(
            "The port may already be in use by another QualCoder instance, or server initialization failed."
        )
        if self._startup_error:
            message += "\n\n" + self._startup_error
        message += "\n\n" + _(
            "MCP access to this QualCoder instance is unavailable. "
            "You can continue using QualCoder. See the log for details."
        )
        self.status_changed.emit(message)
        self.start_failed.emit(message)

    def stop(self) -> None:
        """Promptly reject work and ask the HTTP listener to shut down."""

        self._startup_pending = False
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
        try:
            result = self.mcp_server.run_with_execution_context(execution_context, operation)
        except Exception as err:
            if not future.done():
                future.set_exception(err)
        else:
            if not future.done():
                future.set_result(result)
