import threading
import time
from typing import Callable
from unittest import TestCase

from PyQt6 import QtCore

from qualcoder.ai_async_worker import GuiThreadRelay


class TestGuiThreadRelay(TestCase):
    """Verify that worker callbacks are delivered in the Qt application thread."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QtCore.QCoreApplication.instance()
        if cls.qt_app is None:
            cls.qt_app = QtCore.QCoreApplication([])

    def _process_events_until(self, condition: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 2.0
        while not condition() and time.monotonic() < deadline:
            self.qt_app.processEvents()
            time.sleep(0.005)

    def test_message_from_python_thread_is_delivered_in_application_thread(self):
        main_thread_id = threading.get_ident()
        received = []
        relay = GuiThreadRelay(
            lambda message: received.append((message, threading.get_ident()))
        )

        worker = threading.Thread(target=relay.post_message, args=("ready",))
        worker.start()
        worker.join()
        self._process_events_until(lambda: len(received) == 1)

        self.assertEqual([("ready", main_thread_id)], received)

    def test_error_from_python_thread_is_delivered_in_application_thread(self):
        main_thread_id = threading.get_ident()
        received = []
        relay = GuiThreadRelay(
            lambda _message: None,
            lambda exception_type, value, traceback_obj: received.append(
                (exception_type, value, traceback_obj, threading.get_ident())
            ),
        )

        worker = threading.Thread(
            target=relay.post_error,
            args=(RuntimeError, "failed", None),
        )
        worker.start()
        worker.join()
        self._process_events_until(lambda: len(received) == 1)

        self.assertEqual(
            [(RuntimeError, "failed", None, main_thread_id)],
            received,
        )
