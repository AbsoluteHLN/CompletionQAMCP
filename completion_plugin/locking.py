"""Local advisory writer lock for POSIX and Windows, with bounded waiting."""
from contextlib import contextmanager
import os
from pathlib import Path
import time


@contextmanager
def writer_lock(path, timeout=10):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        acquired=False
        if os.name=='nt':
            import msvcrt
            # Windows locking locks a byte range from the current position.
            handle.seek(0,2)
            if handle.tell()==0:handle.write(b'\0');handle.flush()
            deadline=time.monotonic()+timeout
            while True:
                try:
                    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                    acquired=True;break
                except OSError:
                    if time.monotonic()>=deadline:raise TimeoutError('State writer lock unavailable')
                    time.sleep(.05)
            try:yield
            finally:
                if acquired:
                    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        elif os.name=='posix':
            import fcntl
            deadline=time.monotonic()+timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired=True;break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise TimeoutError('State writer lock unavailable')
                    time.sleep(.05)
            try:yield
            finally:
                if acquired:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        else:raise OSError('Unsupported local writer-lock platform')
