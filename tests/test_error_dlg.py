import os
from pathlib import Path
import subprocess
import sys
from unittest import TestCase


class TestExceptionHook(TestCase):
    """Check exception reporting in isolated Qt processes."""

    def run_script(self, script: str) -> subprocess.CompletedProcess[str]:
        source = Path(__file__).resolve().parents[1] / 'src'
        environment = dict(os.environ, PYTHONPATH=str(source), QT_QPA_PLATFORM='offscreen')
        return subprocess.run(
            [sys.executable, '-c', script], env=environment,
            capture_output=True, text=True, timeout=30,
        )

    def test_startup_failure_preserves_traceback_and_exit_status(self):
        result = self.run_script("""
from qualcoder import error_dlg

def fail_during_startup():
    raise RuntimeError('startup failure sentinel')

fail_during_startup()
""")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Traceback (most recent call last):', result.stderr)
        self.assertIn('fail_during_startup', result.stderr)
        self.assertIn('RuntimeError: startup failure sentinel', result.stderr)
        self.assertNotIn('Must construct a QApplication', result.stderr)
        self.assertNotIn('Error in sys.excepthook', result.stderr)

    def test_gui_failure_still_reaches_dialog(self):
        result = self.run_script("""
from unittest.mock import patch
from PyQt6 import QtWidgets
from qualcoder import error_dlg

app = QtWidgets.QApplication([])
with patch.object(error_dlg, 'show_error_dlg') as show_dialog:
    hook = error_dlg.UncaughtHook()
    with patch('sys.__excepthook__') as default_hook:
        hook.exception_hook(RuntimeError, RuntimeError('GUI failure sentinel'), None)
        show_dialog.assert_called_once()
        assert show_dialog.call_args.args[0] == 'RuntimeError: GUI failure sentinel'
        default_hook.assert_not_called()
""")
        self.assertEqual(result.returncode, 0, result.stderr)
