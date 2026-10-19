# Completion Review Plugin 0.1.2

中文快速入口：[Codex / Windows 安装与手动测试](docs/INSTALL-CODEX-WINDOWS.md)。旧 MCP 迁移：[说明](docs/MIGRATION-v0.4-to-plugin.md)。

Independent private plugin under implementation against approved spec-v002. No cryptographic content identifiers are used. Explicit revisions and direct byte comparisons do not provide tamper protection.

Run without installation:

    python -m completion_plugin.cli check --root ./project --artifact main.py --revision 1
    python -m completion_plugin.cli text ./draft.txt --profile academic
    python -m unittest discover -s tests -v

The Skill in skills/completion-review guides the two-stage planning flow. The Python modules supply state, bounded local checks, configurable profile validation and accounting contracts. Host adapters report their own capability limits. A Skill alone cannot enforce host completion.

Trusted host confirmation is injected by application code; no command accepts a model-supplied approval boolean. Real providers, actual host Stop installation, browser and native-device checks are not connected by default. Configuration and synthetic tests do not establish real backend availability.

No secrets are stored in profiles. Local state and host callbacks are trusted. Review directories must be trusted and preferably exclusive/read-only while checked. Direct comparisons are observations, not adversarial security protection.

This private repository publishes the independent plugin source. Persistent host installation and native Windows acceptance have not been verified.

## Interactive terminal path

    python -m completion_plugin.cli wizard --root /project --state /private/task-state.json --artifact main.py

This asks for key goals, official research sources or an explicit research waiver, direction choice, and approval of the complete versioned task package. It only runs syntax validation. Piped approval is rejected; cancellation executes no project check. Terminal access is a trusted operator boundary, not a way to authenticate a human against malicious local software. The Skill uses host research and richer task planning; the wizard does not claim to browse supplied URLs.

## Model-assisted polishing

completion_plugin.polishing exposes the authorized host-model workflow for all three writing profiles. Missing host means blocked. Generated candidates and exact edit comparisons are returned; optional independent semantic review is separately labeled. Adoption is bound to document revision and current content. No external provider was contacted in validation; mock results are explicitly identified.

## Operational limits

Local state/usage locks now use native POSIX or Windows byte-range locking. Windows project checks now use suspended process creation and a Job Object for bounded process-tree cleanup; native Windows validation is pending. See docs/WINDOWS-RUNNER.md. Restored successful task results cannot authorize a new completion without reconnecting current verifiers. DSH has a packable adapter but its trusted completionQAHost integration and official Schemastery runtime are not present here, so actual DSH loading, native-team calls and Stop behavior are unverified. Do not interpret mock tests or package creation as real-host installation.

To resume a cancelled final proposal without deleting state:

    python -m completion_plugin.cli resume --state /private/task-state.json

The exact saved package is shown again. Interrupted running tasks are not blindly replayed. The wizard identifies source links as user-supplied/unverified and asks for explicit acknowledgement of that research limitation.

Save or inspect validated profile configuration without writing application code:

    python -m completion_plugin.cli profiles --store /private/profiles.json --import-file ./profiles.json
    python -m completion_plugin.cli profiles --store /private/profiles.json

This establishes schema validity only. Actual host capability, model discovery, authorized smoke and current recheck still require a configured trusted host. No API secret is requested or stored. Use a state/usage location outside the reviewed repository for project-test checks so bookkeeping does not invalidate the reviewed content.
