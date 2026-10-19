"""Bounded direct-content checks; trusted local runner, not tamper protection."""
import os
import copy
import ast
import json
from pathlib import Path
from uuid import uuid4


def snapshot(root, names):
    root = Path(root).resolve(strict=True)
    result = {}
    total = 0
    for name in names:
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():
            raise ValueError('Unsafe file')
        path = path.resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Not an in-scope file')
        with path.open("rb") as handle:
            content = handle.read(1_000_001)
        total += len(content)
        if len(content) > 1_000_000 or total > 20_000_000 or len(result) >= 2000:
            raise ValueError('Snapshot limits exceeded')
        result[name] = content
    return result


def repository_snapshot(root):
    root = Path(root)
    names = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ('.git','__pycache__','.pytest_cache')]
        if any((Path(directory)/d).is_symlink() for d in dirs): raise ValueError('Symlink directory')
        names.extend(str((Path(directory)/f).relative_to(root)) for f in files)
        if len(names) > 2000: raise ValueError('Repository file limit exceeded')
    return snapshot(root, names)


class Review:
    def __init__(self, root, artifacts, revision):
        self.root, self.artifacts, self.revision = root, list(artifacts), revision
        if not self.artifacts or len(set(self.artifacts)) != len(self.artifacts):
            raise ValueError('Unique nonempty artifacts required')
        self.original = snapshot(root, self.artifacts)
        self.id = uuid4().hex
        self.results = {}
        self.invalidated = False
        self.project_snapshot = None
        self.project_requested = False

    def current(self):
        if self.invalidated: return False
        try:
            same = snapshot(self.root, self.artifacts) == self.original
            if self.project_snapshot is not None: same = same and repository_snapshot(self.root) == self.project_snapshot
        except (ValueError, OSError):
            same = False
        if not same: self.invalidated = True
        return same

    def syntax(self):
        if self.project_requested: return {"status":"blocked", "reason":"Cannot downgrade project test requirement"}
        if not self.current():
            return {'status': 'blocked', 'reason': 'Content changed'}
        errors = []
        for name, data in self.original.items():
            try:
                if name.endswith('.py'): ast.parse(data, filename=name)
                elif name.endswith('.json'): json.loads(data)
                else: raise ValueError('Unsupported syntax type')
            except (SyntaxError, ValueError, UnicodeError) as exc:
                errors.append({'file': name, 'reason': type(exc).__name__})
        self.results['code'] = {'status': 'fail' if errors else 'pass', 'errors': errors,
                                'scope': 'Syntax only; no project execution'}
        if not self.current(): self.results['code']['status'] = 'blocked'
        return copy.deepcopy(self.results['code'])

    def gate(self, required):
        required = list(required)
        fresh = self.current()
        statuses = {name: self.results.get(name, {}).get('status', 'not_run') for name in required}
        return {'review_id': self.id, 'revision': self.revision, 'code_mode':'project_tests' if self.project_requested else 'syntax', 'content_current': fresh,
                'checks': statuses, 'allow_completion': bool(required) and fresh and all(s == 'pass' for s in statuses.values()),
                'limit': 'Direct comparison at observed times; not tamper protection or semantic verification'}

    def project_tests(self, *, explicitly_trusted=False):
        """Trusted unittest runner; never use on unknown project code."""
        if explicitly_trusted is not True:
            return {'status': 'blocked', 'reason': 'Explicit trusted-code permission required'}
        import sys
        import os
        import subprocess
        from .process import run_project
        from .windows_process import OutputLimitExceeded
        if not self.current(): return {'status':'blocked', 'reason':'Content changed'}
        self.project_requested = True
        before = repository_snapshot(self.root)
        self.project_snapshot = before
        try:
            result = run_project([sys.executable, '-I', str(Path(__file__).with_name('test_runner.py'))], Path(self.root))
            try:
                counts = json.loads(result.stdout.strip().splitlines()[-1])
                valid = all(type(counts.get(k)) is int for k in ('discovered','ran','failures','errors','skipped')) and counts['discovered'] == counts['ran'] and counts['ran'] > counts['skipped'] >= 0 and counts['failures'] == counts['errors'] == 0
            except (ValueError, IndexError, AttributeError): counts, valid = {}, False
            self.results['code'] = {'status':'pass' if result.returncode == 0 and valid else 'fail',
                                    'test_counts':counts, 'exit_code':result.returncode,
                                    'stdout':result.stdout, 'stderr':result.stderr,
                                    'scope':'Trusted unittest execution, not sandbox or security certification'}
        except (OSError, subprocess.TimeoutExpired, OutputLimitExceeded) as exc:
            self.results['code'] = {'status':'blocked','reason':type(exc).__name__}
        if not self.current() or repository_snapshot(self.root) != before:self.results['code']['status']='blocked'
        return copy.deepcopy(self.results['code'])
