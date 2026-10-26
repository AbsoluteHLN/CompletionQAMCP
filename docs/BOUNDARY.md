# Ownership boundary — who owns what

Approved spec-v002 turns this plugin into a **task-package approval, execution-supervision and completion-review** product. That only stays coherent if every neighbouring component keeps one owner. This file is the single place that says which owner is which, so a future change can be checked against it instead of re-argued.

Rule of the road: **one owner per concern, no second scheduler, no second completion authority.** When two layers appear to make the same decision, the more specific contract wins and the other layer must only recommend.

## 1. Ownership table

| Concern | Owner | Explicitly not owned here |
|---|---|---|
| Task-package approval, user-confirmation stage, execution supervision, model routing + usage accounting, completion review | **Completion Review (this repository)** | Cross-client scheduling; deciding which peer runs a task; transport of tasks; storage of project facts |
| Project rules and prompt source (reasoning-depth routing, model allowlist, independent parallel work with exclusive write scopes, self-contained handoff, evidence-based progress, bounded escalation) | **KalciriteThinking** (public MIT source, fixed revision recorded in `docs/PLUGIN-REFACTOR-SPEC.md`) | Any runtime: it ships no meter, no classifier, no scheduler, no two-stage state machine. This repository implements and enforces those rules; it does not re-publish them as a competing runtime |
| Task/message transport, leases, shared-fact transport, roster | **cross-agent-bridge (CABP/1)** | Planning, model selection, deciding that work is semantically finished, waking a model |
| Groups, carrier roster, explicit strategy routing, session projection, delayed acceptance checks | **Agent Workbench / workbench-core** | Model permissions of any agent; a second copy of the task ledger or the completion verdict |
| Cross-session project memory, core blocks, handoff notes, governance audit | **agent-memory** | Dispatching work, adjudicating which fact is true, a second task engine |
| The final decision to dispatch, which strategy, whether to approve | **The human, or the agent that sends the task** | — |

## 2. The MCP surface is a diagnostics surface

The optional stdio MCP server exposes exactly two read-only tools:

| Tool | Purpose |
|---|---|
| `capabilities` | Report what is and is not configured (semantic verification, native stop, user confirmation route) |
| `review_text` | Deterministic text diagnostics and review-only candidate comparison |

Anything that would grant authority — approving a task package, installing a stop hook, executing project commands, reading a host's chat history — is **not** on the MCP surface. Those live in the trusted host integration and the local CLI/Skill path, where the user confirmation stage is explicit and cannot be synthesised by a model.

`capabilities` is the honest boundary report: `semantic_verification: not_configured`, `native: not_configured`, `user_confirmation: trusted_host_only`, `stop_installed: false`. A host that ignores it does not gain the missing capability.

## 3. Cross-component rules

1. **No second scheduler.** If the workbench already routes a task to a peer, this plugin does not also pick a peer. If the workbench asks for a recommendation, the recommendation is advisory and the caller decides.
2. **No second completion authority.** `done` means this plugin's acceptance evidence passed. It never means "the hub says the task is done", and it never means "another agent said so".
3. **Facts are evidence, not authority.** Shared facts (CABP `cab_fact_put`, agent-memory) are claims with sources. This plugin may cite them; it may not treat them as user approval.
4. **Memory is bounded.** Memory is read to reduce repeated work, not to crowd out the agent's own instructions. Read a bounded context, retrieve more on demand, and prefer live evidence over remembered state.
5. **Public sources stay attributable.** KalciriteThinking and the other public projects listed in the spec are referenced by fixed revision and licence; only verified public material is adopted, and private material is excluded.
6. **Unknown stays unknown.** Missing metering, an unconfigured provider, an unverified host capability: report it as unknown/blocked. Never substitute zero, never promote a mock to a real-host result.

## 4. How a change is checked against this file

- Adding an MCP tool: it must stay read-only. If it can approve, execute or install something, it belongs in the trusted host path, not here.
- Adding a scheduling decision: out of scope — route it to the workbench or the dispatching agent instead.
- Touching routing, supervision or accounting: the rules above stay implemented here; only their *source* may be re-read from KalciriteThinking, never forked into a second engine.
- The contract is enforced by `tests/test_boundary_contract.py` (tool surface, capability report, ownership table presence).

## 5. Related documents

- `docs/PLUGIN-REFACTOR-SPEC.md` — the approved design and the task/acceptance matrix.
- `docs/IMPLEMENTATION-STATUS.md` — what is implemented, exercised, blocked or not run.
- `docs/TASK-MATRIX.md` — per-task implementation state.
- `docs/VALIDATION.md` — validation record.
- `skills/completion-review/SKILL.md` — the portable entry point hosts can follow.
