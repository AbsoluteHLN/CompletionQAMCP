"""Bounded time/output reads for explicitly trusted POSIX or Windows project commands."""
import os
import signal
import subprocess
import tempfile

def run_project(command, root):
    if os.name == 'nt':
        from .windows_process import run_windows
        with tempfile.TemporaryDirectory(prefix='qa-pycache-') as cache:
            command = [command[0], '-B', '-X', 'utf8', '-X', 'pycache_prefix=' + cache, *command[1:]]
            return run_windows(command, root)
    if os.name != 'posix':
        raise OSError('Process-group cleanup requires POSIX; adapter unavailable here')
    with tempfile.TemporaryDirectory(prefix='qa-pycache-') as cache, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        command = [command[0], '-B', '-X', 'pycache_prefix=' + cache, *command[1:]]
        proc = subprocess.Popen(command, cwd=root, env={'PATH': os.defpath, 'LANG': 'C.UTF-8'},
                                stdout=stdout, stderr=stderr, shell=False, start_new_session=True)
        try:
            proc.wait(timeout=20)
        finally:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait()
        def excerpt(stream):
            stream.seek(0, 2); size = stream.tell(); stream.seek(0)
            if size <= 19000:
                value = stream.read()
            else:
                head = stream.read(9000); stream.seek(-9000, 2)
                value = head + b'\n[output truncated]\n' + stream.read(9000)
            return value.decode('utf-8', errors='replace')
        return subprocess.CompletedProcess(command, proc.returncode, excerpt(stdout), excerpt(stderr))
