"""Bounded repository content manifest; independent of Git tracking state."""
import hashlib
import os
from pathlib import Path

EXCLUDED_DIRS = frozenset({'.git', '__pycache__', '.pytest_cache'})
MAX_FILES = 2000
MAX_BYTES = 20_000_000


def repository_manifest(root: Path):
    files = {}
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
        base = Path(directory)
        for name in list(dirs):
            path = base / name
            if name in EXCLUDED_DIRS:
                dirs.remove(name)
            elif path.is_symlink():
                raise ValueError('Repository scope rejects symlink directories')
        for name in sorted(names):
            path = base / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('Repository scope requires regular files')
            size = path.stat().st_size
            if len(files) >= MAX_FILES or total + size > MAX_BYTES:
                raise ValueError('Repository manifest limit exceeded')
            with path.open("rb") as handle:
                data = handle.read(MAX_BYTES - total + 1)
            total += len(data)
            if total > MAX_BYTES:
                raise ValueError('Repository manifest limit exceeded')
            files[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return {'files': files, 'excluded_directory_names': sorted(EXCLUDED_DIRS), 'scope': 'repository-content'}
