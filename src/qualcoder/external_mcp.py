# -*- coding: utf-8 -*-

"""Local Streamable HTTP transport for QualCoder's shared MCP server."""

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
import re
import sqlite3
import threading
from typing import Any, Callable

from PyQt6 import QtCore
import uvicorn

from .ai_mcp_server import AiMcpExecutionContext, AiMcpServer


logger = logging.getLogger(__name__)


class ExternalMcpController(QtCore.QObject):
    """Run MCP HTTP and project work off the GUI thread, like the internal AI agent does."""

    status_changed = QtCore.pyqtSignal(str)
    start_failed = QtCore.pyqtSignal(str)

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
        # One worker keeps requests in order; a busy database then waits here and not in the GUI
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="QualCoderExternalMCPWork")
        self._traced_conn: sqlite3.Connection | None = None
        self._gui_statements: deque[tuple[str, str]] = deque(maxlen=12)
        self.mcp_server.set_external_executor(self._invoke_off_gui_thread)

    @property
    def endpoint(self) -> str:
        """Return the configured local MCP endpoint."""

        return f"http://{self.HOST}:{self.port}/mcp"

    @staticmethod
    def port_from_settings(settings: Any) -> int:
        """Return a normalized TCP port from application settings."""

        default_port = ExternalMcpController.DEFAULT_PORT
        try:
            port = int(settings.get("mcp_external_port", default_port))
        except (TypeError, ValueError):
            port = default_port
        if not 1024 <= port <= 65535:
            return default_port
        return port

    @property
    def port(self) -> int:
        """Return a normalized configured TCP port."""

        return self.port_from_settings(self.app.settings)

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
        self._trace_gui_connection(enabled)
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

    async def _invoke_off_gui_thread(
            self, operation: Callable[[], Any], execution_context: AiMcpExecutionContext
    ) -> Any:
        """Queue a synchronous project operation on the worker and await its result."""

        if not self._active:
            raise RuntimeError("External MCP is disabled.")
        future = self._worker.submit(self._execute, operation, execution_context)
        return await asyncio.wrap_future(future)

    def _execute(self, operation: Callable[[], Any], execution_context: AiMcpExecutionContext) -> Any:
        """Execute one queued request; the MCP server itself reports a missing project."""

        if not self._active:
            raise RuntimeError("External MCP is disabled.")
        try:
            return self.mcp_server.run_with_execution_context(execution_context, operation)
        except sqlite3.OperationalError as err:
            raise self._explain_database_error(err) from err
        except Exception as err:
            # Visible in the action log, so a failed external request needs no log hunting
            self.status_changed.emit(f"External MCP request failed: {str(err)[:300]}")
            raise

    def _trace_gui_connection(self, enabled: bool) -> None:
        """Keep the last statements of the GUI connection, to name the window that holds the database."""

        conn = self.app.conn if enabled else None
        if conn is self._traced_conn:
            return
        try:
            if self._traced_conn is not None:
                self._traced_conn.set_trace_callback(None)
        except sqlite3.Error:
            pass
        self._traced_conn = None
        self._gui_statements.clear()
        if conn is None:
            return
        try:
            conn.set_trace_callback(self._remember_gui_statement)
            self._traced_conn = conn
        except sqlite3.Error as err:
            logger.debug("GUI connection trace unavailable: %s", err)

    def _remember_gui_statement(self, statement: str) -> None:
        """Trace callback, runs on the GUI thread for every statement, so it only stores."""

        self._gui_statements.append((datetime.now().strftime("%H:%M:%S"), statement[:240]))

    def _gui_statement_trail(self) -> str:
        """Return the remembered statements without their text values, which may be research data."""

        lines = []
        for clock, statement in list(self._gui_statements):
            cleaned = re.sub(r"'(?:[^']|'')*'", "'?'", statement)
            cleaned = cleaned.split("'")[0] + "'?" if cleaned.count("'") % 2 else cleaned
            lines.append(f"  {clock} {' '.join(cleaned.split())}")
        return "\n".join(lines)

    def _explain_database_error(self, err: sqlite3.OperationalError) -> Exception:
        """Turn a database lock into something the external client and the user can act on."""

        if "locked" not in str(err).lower():
            return err
        pending = bool(getattr(self.app.conn, "in_transaction", False))
        if pending:
            reason = ("A QualCoder window has changes that are not saved to the project yet. "
                      "Ask the user to finish or close that window in QualCoder.")
        else:
            reason = ("Another QualCoder window is still reading the project database. "
                      "Ask the user to close open coding, report or graph windows.")
        message = (
            f"External MCP: nothing written, the project database is locked (unsaved changes in QualCoder: {pending})."
        )
        trail = self._gui_statement_trail()
        if trail != "":
            # Stays in the local log, the external client never receives it
            message += "\nLast statements of the QualCoder window connection, newest last:\n" + trail
        self.status_changed.emit(message)
        return RuntimeError(
            f"The project database stayed locked and nothing was written. {reason} "
            "Do not retry until the user confirms."
        )
