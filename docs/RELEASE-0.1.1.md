# 0.1.1 Windows storage compatibility patch

2026-10-19. Replaces unconditional fcntl imports in workflow and usage with native Windows msvcrt byte-range locks or POSIX flock. Waiting is bounded, lock release is exception-safe. Existing 0.1.0 artifact is unchanged.

149 Python tests pass on the current Linux cloud, including two new lock tests. Windows API contract is simulated here, not native validation. The Windows installation task must verify wizard save, cancellation/resume, ledger persistence and concurrent writers on the actual machine.

Project unittest execution still requires POSIX in 0.1.1. A separate Windows process-tree-safe runner is the next patch; this version never pretends a blocked runner passed.
