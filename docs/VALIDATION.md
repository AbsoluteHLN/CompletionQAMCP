# Current validation

2026-10-19 UTC; independent plugin 0.1.0, approved design spec-v002.

Current aggregate: 147 Python unittest methods passed; 13 JavaScript tests passed. These counts cover this new code, not legacy v0.8 tests. Independent workflow audit contributes 38 methods within that aggregate, not an extra additive count.

## 2026-10-20 Windows console output encoding

Redirected CLI output is now written as UTF-8 bytes instead of depending on the active console code page. On a zh-CN Windows host (ANSI code page 936) the previous `print(json.dumps(..., ensure_ascii=False))` path raised `UnicodeEncodeError` on any character outside GBK, including emoji and a UTF-8 BOM, and aborted the command with no output. Four new methods in `tests/test_output.py` cover this, including a real subprocess that forces a GBK stdout encoding.

Windows run on 2026-10-20: 166 Python tests collected, 163 passed, 3 skipped, 3 failed. The three failures are environment limits, not new regressions: two symlink tests need the Windows symlink privilege (`WinError 1314`) and `test_child_cleanup_after_success` still fails in the native Job Object runner. The same three failures occur on the unmodified baseline revision 0ac9b88 (162 tests collected, same skips, same failures), so this change adds no failing test.


Actual local processes tested: Python syntax checks, temporary trusted unittest subprocesses, real MCP stdio initialize/list/call, real PTY wizard acceptance and cancellation. PTY input is a synthetic operator fixture, not an actual user's approval record.

Simulated backends: host model generation/independent prose review, profile model discovery/smoke, DSH Config/native-team contracts. They do not prove actual provider access, billing, native agent availability, DSH loading or real Stop behavior.

Important regression fixes include stale successful task results after revision, write-scope aliases, malformed restored state, generator dependency/check omissions, mutable result leakage, undetected concurrent writer overwrite, deleted-state recreation, nonfinite usage, stale evidence resurrection, changed project dependencies after test execution, syntax overwriting failed real tests, omitted required text checks and completion after file changes.

Publication/install not performed. Source package excludes transfer helpers and earlier product archives. Source scan found no retained content-fingerprint algorithm or legacy receipt fields in runtime code.

Final user-workflow review additionally verified approval-mode matching, non-boolean opt-in rejection, explicit unverified-source acknowledgement, and cancel/resume over real local PTY fixtures. No remaining blocking issue was reported in that review.

DSH integration example syntax and local action-store restart/writer exclusion/return isolation passed. npm pack with a temporary cache succeeded after its default cache path was unavailable; six package files were included. No runtime dependency was installed.

## 2026-10-22 spec-v002 alignment increment

Independent spec-gap audit against spec-v002; see ../../verify-evidence/2026-10-22-completionqa-spec-audit.md for the full item-by-item record. Timeline events now carry event_sequence (legacy 'sequence' files stay readable), UTC RFC3339 stamps, revision_before/revision_after, reason, actor and task; state gains a random document_id and tasks gain random task_id; the reviewing stage joins the state machine between executing and complete. The usage ledger records provider, run_id, operation, started_at/ended_at and unknown_reason, renames source to measurement_source (old ledgers remain readable), and keeps failed or blocked attempts with null billing values plus a stated reason.

Windows run on 2026-10-22 (Python 3.13.14): 191 tests collected, 184 passed, 2 failed, 2 errors, 3 skipped. The four non-passing cases are the same environment limits as the baseline 166-test run (two symlink-privilege tests, the Job Object child-cleanup test, and the offline mcp import missing anyio); the 25 new tests all pass and no previously passing test regressed. Changed files were backed up as *.bak-2026-10-22 before editing.

