# 0.1.2 Windows runner and Unicode patch

2026-10-19. Adds Windows Job Object execution to approved project tests. Suspended creation precedes assignment and resume; failures do not fall back to unmanaged execution. Normal exit, error and timeout all clean up contained descendants. Output has a sampled 8 MiB watchdog, not a hard quota. See WINDOWS-RUNNER.md for boundaries and official references.

State, usage, profile, CLI and test-runner text reads/writes use explicit UTF-8. Windows Python child processes enable UTF-8 and avoid project bytecode writes. Existing v0.1.0 and v0.1.1 release files are unchanged.

Current Linux validation: 162 discovered Python tests, 154 passed, 8 native Windows cases skipped. The skips are not Windows validation. Thirteen JavaScript adapter tests passed. Native Windows trial results must be recorded separately; actual DSH loading and model-provider calls remain unverified here.

## Native trial

From the unpacked product root on Windows with Python 3.11 or later:

    python -m unittest discover -s tests -p test_windows_process.py -v
    python -m unittest discover -s tests -p test_project_execution.py -v
    python -m unittest discover -s tests -p test_unicode_storage.py -v
    python -m unittest discover -s tests -p test_locking.py -v
    python -m unittest discover -s tests -v

Expect 11 Windows-runner tests to pass and the one wrong-platform-only check to skip, including child PID disappearance after normal exit, timeout and output limit. POSIX-only PTY tests may be skipped on Windows and do not establish interactive terminal acceptance there. Also exercise wizard cancellation and resume in a real terminal with a temporary source file and a state path outside the reviewed project; test Chinese goals and paths. Record exact Python/Windows versions, output and failures. Do not turn a skip or environment blockage into a pass.
