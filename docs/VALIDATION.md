# Private source release validation

Date: 2026-10-18 UTC. Version: 0.4.0.

- `python -m unittest discover -s tests -v`: **134 test methods passed**, including author tests and independent negative/regression suites, in the cleaned release directory.
- The first packaging test run found six test-loader subprocess path errors after consolidating formerly separate review folders. Relative project paths were corrected; the entire 134-test suite was rerun successfully. No production code changed.
- Ten `completion_qa/*.py` production files match the prior v0.4 SHA-256 manifest exactly; see `source-sha256.json`.
- Real SDK stdio subprocess tests, command-wrapper tests, stale-source checks, evidence mutation/alias isolation and synthetic provider protection tests are included. They do not establish real host Stop triggering, LLM quality or device operation.
- Real model/provider, browser/native device and real automatic host Stop end-to-end acceptance: **not run / not integrated**.
- Historical project reports, raw environment logs, Library identifiers and personal addresses are excluded. The prose fixture contains invented numbers and generic names; corresponding assertions were updated without weakening preservation/negative tests.
- No dependencies are vendored. Installed test dependency: official `mcp==1.29.0`; Python 3.12. Original code is proprietary; dependency licenses remain separate.

## Safety scan scope

A text scan checked all released files for personal mail addresses, internal Library/file IDs, execution workspace/home paths, private project names, common credential formats and private-key headers. No matches remained. Generic adversarial `/etc/passwd` and `/tmp` fixture literals are intentionally retained as negative path tests, not environment disclosures.

This scan is a bounded release hygiene check, not a security audit or proof that no secrets can exist. The package performs no automatic network calls or hook installation on import. Keep deployment configuration and future credentials outside source control.
