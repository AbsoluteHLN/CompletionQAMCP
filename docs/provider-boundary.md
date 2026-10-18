# Independent review provider boundary and constrained rewrite

## Compatibility and rollout status

The provider abstraction and local fixtures are the primary deliverable. Everything is disabled by default. No API key, external provider, hosted model, server sampling hook, or production acceptance gate is configured here. No private project content was sent to a model during implementation/testing.

The optional `LegacyMCPSamplingProvider` (compatibility alias `MCPSamplingProvider`) is **legacy compatibility only**, pinned to the installed Python `mcp==1.29.0` API and the 2025-11-25 sampling protocol. It requires `allow_legacy_compatibility=True` as well as the service policy and approval checks below. It is not recommended for a new deployment: the official [2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) deprecates Sampling and recommends direct provider API integration for new implementations. No direct provider integration or credentials are authorized/configured in this stage.

Reference verification on 2026-10-17:

- [2025-11-25 sampling specification](https://modelcontextprotocol.io/specification/2025-11-25/client/sampling): capability negotiation, host/client control, request and response contract.
- [Official Python SDK v1.29.0 session source](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.0/src/mcp/server/session.py): installed `ServerSession.create_message(messages, *, max_tokens, system_prompt, include_context, temperature, ..., tools, tool_choice, ...)` and `check_client_capability(ClientCapabilities(...))` signatures inspected directly.
- The test transport invokes that real SDK serializer locally with a mocked `send_request`. This establishes the SDK wire shape, not a live-host handshake or LLM quality.

## Trust boundary

A trusted host constructs `SamplingReviewService`. It supplies the provider, `SamplingPolicy(enabled=True)`, and an asynchronous `approve_request` callback. These must never be accepted as tool-call arguments. Public operations accept only the review input and, for rewriting, a supported profile.

Before every provider request:

1. Reject disabled policy, empty/oversize input, or missing sampling capability.
2. Build a frozen exact request with the full source, an input SHA-256, review instructions, complete strict output schema, token limit, host-configured `provider_destination`, and `include_context="none"`. Input SHA-256 and destination also appear in the result evidence.
3. Present this request to the trusted host callback. It must perform the actual permission/UI decision for the exact content and return `SamplingApproval(request.digest)` or `None`. A bare caller boolean, missing callback, mismatched digest, callback error, or timeout blocks the request. There is no tool argument that grants approval.
4. Recheck capability, then send one request. No automatic retries, added server context, tool definitions, tool execution, file execution, or automatic application of edits.

A permissive callback is appropriate only for synthetic local fixtures. Shipping a callback that automatically approves real/private content would defeat the intended host boundary. The host must set `provider_destination` to the actual relevant destination/provider and show that destination and content to the user under its own permissions. The legacy default describes only the connected MCP client, whose host retains control over actual model/provider selection; it is not independent proof of the final recipient. Request hashes bind bytes; they do not prove confidentiality, identity, or informed consent.

Defaults: 32,000 input characters, 24,000 output characters, 2,048 generation tokens, 20-second generation timeout, 60-second approval timeout. Constructor limits cap inputs/outputs at 64,000 characters and generation at 4,096 tokens. Timeout cancels the local await; a remote provider may already have received the request, so it is not a rollback guarantee.

## Result semantics

Code review JSON must contain exactly `verdict` (`pass`/`fail`), `summary`, and `findings`. Findings contain exactly `severity` (`advisory`/`warning`/`error`) and `message`. Unknown fields, duplicate JSON keys, wrong types, markdown wrappers, malformed JSON, excessive size, contradictory passing/error findings, and incomplete/non-text SDK results fail closed.

Rewrite JSON must contain exactly `proposed_text` and `findings`. A response never edits a file. All results have `applied: false` and a scope statement. Real code-review `llm_pass` is a bounded review opinion only, not execution evidence or proof of correctness. Do not substitute it for build/test/browser/native evidence. Fixture results have `status: "fixture"` and `llm_pass: false`, even if the simulated reviewer says `verdict: "pass"`. The model controls neither provenance nor gate status.

## Rewrite constraints

This implementation intentionally does not promise general semantic rewriting. Every factual clause, line order, punctuation, and line ending remains byte-for-byte unchanged. The only candidate edits are deletion of one of three line-start lead-ins (`值得注意的是，`, `值得一提的是，`, `It is worth noting that `), at most one per line, while retaining a nonempty remainder. All other substitutions, deletions, additions, and reorderings are rejected.

Numbers, negation, causality, and validation/status language receive diagnostic classifications. Those regexes are not a semantic parser and are not the basis for claim preservation. The exact unchanged-clause constraint rejects changes even if their terms are unrecognized by the classifiers. Causal and contrastive transitions such as therefore, because, however, 因此, and 但是 are not editable. Removing emphasis can still change pragmatics, so a human must review even accepted proposals.

Any quote/code marker or blockquote makes the entire input diagnostic-only, including mixed code/prose. This deliberately overprotects apostrophes and contractions. Classification cannot identify every possible quotation or programming language; acceptance nevertheless permits only the narrow lead-in deletion operation and never executes input. This is a conservative text boundary, not a semantic guarantee.

## Runnable local fixture

Run from the project root. The callback below approves **only this in-memory fixture**, with no network or model access:

```python
import asyncio
import json
from completion_qa.sampling import (
    FixtureSamplingProvider, SamplingApproval, SamplingPolicy,
    SamplingReviewService,
)

SOURCE = '值得注意的是，原13项测试通过；独立15项和wrapper5项通过。browser未运行，model未运行；相关不代表因果。'
PROPOSED = SOURCE.removeprefix('值得注意的是，')

async def fixture_only_approval(request):
    return SamplingApproval(request.digest)

async def main():
    provider = FixtureSamplingProvider(json.dumps({
        'proposed_text': PROPOSED, 'findings': []
    }, ensure_ascii=False))
    service = SamplingReviewService(
        provider, policy=SamplingPolicy(enabled=True),
        approve_request=fixture_only_approval,
    )
    print(json.dumps(await service.rewrite_text(SOURCE), ensure_ascii=False, indent=2))

asyncio.run(main())
```

Before: 值得注意的是，原13项测试通过；独立15项和wrapper5项通过。browser未运行，model未运行；相关不代表因果。

After: 原13项测试通过；独立15项和wrapper5项通过。browser未运行，model未运行；相关不代表因果。

The unchanged test counts/statuses are supplied example facts, not rerun by this fixture. The necessary limitations occur once in the output. This is a simulated contract exercise, not an LLM editorial review.

`test_synthetic_semantic_bug_is_fixture` similarly uses invented source `def ratio(a, b): return a / b` and a canned zero-denominator finding. It exercises finding structure and provenance; no model discovered the bug.

## Local verification

```sh
python -m unittest discover -s tests -p test_sampling.py -v
```

The focused suite checks disabled defaults, capability/approval order, boolean and stale approval rejection, immutable exact request binding, fixture provenance, strict JSON, bounds, timeouts, protected fact changes, quotes/code, policy validation, and real SDK serialization through an in-memory mock transport. Live client consent UI, an external model, semantic-review quality, and real-world multi-provider behavior remain untested.
