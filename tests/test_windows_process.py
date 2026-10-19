"""Native lifecycle checks are skipped on Linux, never counted as Windows evidence."""
import ctypes
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from completion_plugin.windows_process import run_windows, _excerpt, OutputLimitExceeded


class WindowsRunnerContractTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Wrong-platform contract applies off Windows')
    def test_wrong_platform_fails_closed(self):
        with self.assertRaisesRegex(OSError, 'native Windows'):
            run_windows([sys.executable, '-c', 'print(123)'], '.')

    def test_small_excerpt(self):
        self.assertEqual(_excerpt(io.BytesIO(b'hello\xff')), 'hello\ufffd')

    def test_large_excerpt_is_bounded(self):
        result = _excerpt(io.BytesIO(b'A' * 10000 + b'B' * 10000))
        self.assertLess(len(result), 19000)
        self.assertTrue(result.startswith('A' * 9000))
        self.assertTrue(result.endswith('B' * 9000))
        self.assertIn('[output truncated]', result)

    def test_argv_and_timeout_validation_without_native_execution(self):
        with patch('completion_plugin.windows_process.os.name', 'nt'):
            with self.assertRaises(ValueError):
                run_windows('python -c print(1)', '.')
            with self.assertRaises(ValueError):
                run_windows(['relative-python', '-c', 'print(1)'], '.')
            for timeout in (0, -1, 21, float('inf'), float('nan')):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    run_windows([sys.executable], '.', timeout)


@unittest.skipUnless(os.name == 'nt', 'Requires native Windows Job Objects; skipped is not passed')
class NativeWindowsRunnerTests(unittest.TestCase):
    def run_code(self, code, root, timeout=20):
        return run_windows([sys.executable, '-c', code], root, timeout)

    def test_success_and_minimal_environment(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'QA_PRIVATE_SENTINEL': 'secret'}):
            result = self.run_code('import os,sys; print("hello"); print("error",file=sys.stderr); '
                                   'assert "QA_PRIVATE_SENTINEL" not in os.environ', root)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'hello')
        self.assertEqual(result.stderr.strip(), 'error')

    def test_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_code('import sys; print("failed"); sys.exit(7)', root)
        self.assertEqual(result.returncode, 7)
        self.assertIn('failed', result.stdout)

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_code('import time; time.sleep(30)', root, .3)

    def test_watchdog(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(OutputLimitExceeded):
                self.run_code('import os; data=b"x"*65536\nwhile True: os.write(1,data)', root)

    def test_create_failure(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(OSError):
                run_windows([str(Path(root) / 'does-not-exist.exe')], root)

    def assert_child_dead(self, pid):
        from ctypes import wintypes as w
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        k.OpenProcess.restype = w.HANDLE
        k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        k.WaitForSingleObject.restype = w.DWORD
        k.CloseHandle.argtypes = [w.HANDLE]
        k.CloseHandle.restype = w.BOOL
        handle = k.OpenProcess(0x100000, False, pid)
        if not handle:
            self.assertEqual(ctypes.get_last_error(), 87, 'OpenProcess failed for a reason other than nonexistent PID')
            return
        try:
            self.assertEqual(k.WaitForSingleObject(handle, 0), 0, 'descendant still alive')
        finally:
            k.CloseHandle(handle)

    def exercise_child_cleanup(self, mode):
        with tempfile.TemporaryDirectory() as root:
            pid_path = Path(root) / 'child.pid'
            child = 'import os,time,pathlib; pathlib.Path("child.tmp").write_text(str(os.getpid())); pathlib.Path("child.tmp").rename("child.pid"); time.sleep(60)'
            ending = {'success': 'pass', 'timeout': 'time.sleep(30)',
                      'error': 'data=b"x"*65536\nwhile True: os.write(1,data)'}[mode]
            code = ('import subprocess,sys,time,os,pathlib\n'
                    f'subprocess.Popen([sys.executable,"-c",{child!r}])\n'
                    'deadline=time.monotonic()+5\n'
                    'while not pathlib.Path("child.pid").exists():\n'
                    ' if time.monotonic()>deadline: raise RuntimeError("child did not start")\n'
                    ' time.sleep(.01)\n' + ending)
            if mode == 'timeout':
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.run_code(code, root, 3)
            elif mode == 'error':
                with self.assertRaises(OutputLimitExceeded):
                    self.run_code(code, root)
            else:
                self.assertEqual(self.run_code(code, root).returncode, 0)
            self.assert_child_dead(int(pid_path.read_text()))

    def test_child_cleanup_after_success(self):
        self.exercise_child_cleanup('success')

    def test_child_cleanup_after_timeout(self):
        self.exercise_child_cleanup('timeout')

    def test_child_cleanup_after_output_error(self):
        self.exercise_child_cleanup('error')


if __name__ == '__main__':
    unittest.main()
