"""Probe-result regressions; fake processes test logic, not game compatibility."""
import array
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('clonehero_probe', Path(__file__).with_name('clonehero.py'))
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class ProbeResults(unittest.TestCase):
    def run_probe(self, dismiss=True, crash_at=None, exit_code=1, audible=True):
        clock = [0.0]
        class Process:
            def __init__(self, game=False):
                self.game = game
                self.stopped = False
            def poll(self):
                if self.stopped:
                    return 0
                if self.game and crash_at is not None and clock[0] >= crash_at:
                    return exit_code
                return None
            def terminate(self):
                self.stopped = True
            kill = terminate
            def wait(self, timeout=None):
                return 0
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'pulse.sock').touch()
            def spawn(argv, **kwargs):
                if argv[0] == 'parec':
                    kwargs['stdout'].write(array.array('h', [1000 if audible else 0] * 6000).tobytes())
                return Process(game=argv[0].endswith('/clonehero'))
            def sleep(seconds):
                clock[0] += seconds
            image = types.SimpleNamespace(save=lambda path: None)
            pil = types.ModuleType('PIL')
            pil.ImageGrab = types.SimpleNamespace(grab=lambda: image)
            response = types.SimpleNamespace(returncode=0, stdout='mock external command', stderr='')
            with patch.object(PROBE.subprocess, 'Popen', side_effect=spawn), \
                 patch.object(PROBE.subprocess, 'run', return_value=response), \
                 patch.object(PROBE.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(PROBE.time, 'sleep', side_effect=sleep), \
                 patch.dict('sys.modules', {'PIL': pil}), contextlib.redirect_stdout(io.StringIO()):
                status = PROBE.client(root, root, dismiss)
            return status, json.loads((root / 'clonehero.json').read_text())

    def test_post_consent_exit_is_failure_even_after_initial_survival(self):
        for exit_code in (0, 1, -11):
            with self.subTest(exit_code=exit_code):
                status, report = self.run_probe(crash_at=45, exit_code=exit_code)
                self.assertTrue(report['alive_after_40s'])
                self.assertFalse(report['alive_after_opt_out_20s'])
                self.assertEqual(report['game_exit_before_cleanup'], exit_code)
                self.assertNotEqual(status, 0)

    def test_crash_during_audio_capture_is_failure(self):
        status, report = self.run_probe(crash_at=62)
        self.assertTrue(report['alive_after_opt_out_20s'])
        self.assertTrue(report['menu_audio_captured'])
        self.assertNotEqual(status, 0)

    def test_silent_capture_is_failure(self):
        status, report = self.run_probe(audible=False)
        self.assertIsNone(report['game_exit_before_cleanup'])
        self.assertFalse(report['menu_audio_captured'])
        self.assertNotEqual(status, 0)

    def test_survival_with_audio_passes(self):
        status, report = self.run_probe()
        self.assertTrue(report['alive_after_opt_out_20s'])
        self.assertTrue(report['menu_audio_captured'])
        self.assertEqual(status, 0)

    def test_initial_crash_is_failure(self):
        status, report = self.run_probe(crash_at=10)
        self.assertFalse(report['alive_after_40s'])
        self.assertNotEqual(status, 0)

    def test_plain_startup_does_not_require_consent_or_audio(self):
        status, report = self.run_probe(dismiss=False)
        self.assertTrue(report['alive_after_40s'])
        self.assertNotIn('alive_after_opt_out_20s', report)
        self.assertEqual(status, 0)


if __name__ == '__main__':
    unittest.main()
