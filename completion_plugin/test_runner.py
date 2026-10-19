"""Explicitly trusted project tests, not a security sandbox."""
import json
import os
if os.name == "posix":
    import resource
import sys
import unittest
from pathlib import Path

def main():
    # Bound regular-file output (including captured stdout/stderr) to 8 MiB.
    if os.name == "posix":
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    root = Path.cwd()
    sys.path.insert(0, str(root))
    try:
        suite = unittest.defaultTestLoader.discover(str(root / 'tests'))
        count = suite.countTestCases()
        if count == 0:
            print(json.dumps({'discovered': 0, 'reason': 'No tests discovered'}))
            return 4
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print(json.dumps({'discovered': count, 'ran': result.testsRun,
                          'failures': len(result.failures), 'errors': len(result.errors),
                          'skipped': len(result.skipped)}))
        return 0 if result.wasSuccessful() and result.testsRun > len(result.skipped) else 4
    except BaseException as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 3

if __name__ == '__main__':
    sys.exit(main())
