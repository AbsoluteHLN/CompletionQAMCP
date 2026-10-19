# CompletionQA DSH adapter

Packable ESM plugin source. Real DSH loading, official dependency resolution,
UI rendering and native lifecycle/stop smoke tests are **not run**.
No plugin is installed. `npm run check`, `npm test` and `npm pack --ignore-scripts`
require no downloads. Real entry loading requires official Schemastery.

`index.js` exports Config/inject/apply. Config volatile fields are the single
settings authority; no sidecar exists. The standard host Config form is the
settings surface. A custom client panel is not implemented, and no dsh.client
bundle is advertised. Native specific-model routing is unsupported.

## Trusted integration contract

`completionQAHost` is a new integration seam, NOT a built-in DSH service.
An integrator must supply probe, supportsVersion, configRevision, authorize,
resolveRootAgent, manages, invalidateValidation and registerBridge. It must also
provide synchronous durable actions.get/put/values with isolated return values,
serialized updates, and restart persistence. Missing integration blocks loading.
Never make approval callbacks or live Agent identity model-controlled.

Native calls retain the actual live root Agent credential. Team roster reuse
precedes creation. Provider is a resumable subagent backend, not an LLM vendor.
The config inheritModel route requires current trusted user authorization.
Pending/uncertain messages cannot be retried blindly. Inbox acceptance is not
completion. Interrupt keeps reservations. Reservations coordinate this plugin
instance only; host workspace controls must prevent symlink aliases and other
actors' conflicting writes. Explicit lifecycle reconciliation is still needed
before releasing conservative reservations.

The guard only returns a denial reason or undefined, preserving host deny/ask.
Host Config forms own mutate(ops, expectedRevision). Missing usage is unknown.
No native Stop enforcement claim is made.

## API evidence

Official source inspected 2026-10-19:
- https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/agent-team/src/index.ts
- https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/agent-team/src/types.ts
- https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/src/index.ts
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-settings-card.md

Historical revision c291e7961a515f6d7af9304e7fd1d257929aef26 was also inspected:
its mailbox/lifecycle behavior differs and compatibility is NOT claimed. Current
master remains mutable. No pinned upstream revision has passed real-host
validation. The trusted integrator must allow only a verified installed version;
the peer dependency wildcard is discovery, not a compatibility guarantee.
The package is private. No upstream implementation is copied or vendored.

## Multiple role profiles through host Config

`profilesJson` now stores the portable v1 collection, including multiple named
profiles, their revisions, named routes (provider/model/effort/auth_ref), roles,
ordered fallback routes, concurrency, timeout, allowlist and default role.
The host schema validates this string using Schemastery's documented transform
API; every bridge operation reparses the authoritative volatile Config value.
Unknown fields, imported validation records, duplicate keys/identities, invalid
references, repeated fallback routes and invalid limits are rejected. Credential
fields and recognizable credential prefixes are rejected; opaque strings cannot
be universally classified as secrets. Only credential reference names belong in
this field, never credentials.

`previewProfiles(text)` exposes additions, replacements, removals and conflicts.
`importProfiles(form,text,expectedRevision)` requires trusted confirmation of that
exact preview, rejects stale Config and profile revisions, and forwards a CAS
replacement to the Plugins form owner. It never writes a parallel file. Native
model/effort selection remains blocked even when schema validation succeeds.
`profileStatus()` returns revision-bound schema/capability/discovery/smoke states;
imported smoke success is never accepted. Config changes invalidate host validation.

The profile editing surface is the host's generated Config string field; rendering
and persistence in actual DSH are untested. The status accessor is ready for a
trusted host view but has NOT been wired into or rendered in a real DSH panel.
A custom validation-status panel therefore remains blocked on real integration.
The actual host must implement `completionQAHost`, supply its version and durable
action store, wire the Config form and status view, and validate those paths with
its installed Schemastery/runtime. No such host or connection is available here.

## Reproducible host connection investigation (2026-10-19 UTC)

Read-only checks in this workspace found:

- Node resolves neither `@deepseek-ai/schemastery`,
  `@deepseek-ai/dsh-experimental-agent-team`, nor `@deepseek-ai/dsh`:
  all return `ERR_MODULE_NOT_FOUND`.
- No DSH executable process was visible in the process list. This is a local
  observation, not proof that no DSH exists on another machine.
- The correct package is `@deepseek-ai/dsh-experimental-agent-team`;
  `@deepseek-ai/dsh-agent-team` is not the name in the official manifest.
- Registry metadata was retrieved with `npm view`, not installed or executed.
  Latest tags returned Schemastery `3.18.5`, agent-team `0.1.5-alpha.2`, and CLI
  `0.2.0-rc.2`. The separately inspected mutable master manifests reported
  `3.18.5-alpha.2`, `0.2.1-alpha.4`, and `0.2.1-rc.2`, respectively. These are
  observations of different distribution channels, NOT a tested compatible set.

Reproduce the non-mutating registry checks:

```sh
npm view @deepseek-ai/schemastery version --registry=https://registry.npmjs.org
npm view @deepseek-ai/dsh-experimental-agent-team version --registry=https://registry.npmjs.org
npm view @deepseek-ai/dsh version --registry=https://registry.npmjs.org
```

The following official sources establish the publication and entry paths:

1. [Schemastery manifest](https://github.com/deepseek-ai/deepseek-harness/blob/master/vendor/schemastery/package.json):
   public publication; import entry `lib/index.mjs`, CommonJS entry `lib/index.cjs`.
2. [Team manifest](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/agent-team/package.json):
   public package, host entry `lib/index.js`, with Cordis/agent/session/subagent
   peer services. A standalone schema installation would not provide the team.
3. [CLI manifest](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/package.json):
   executable `dsh` maps to `lib/bin.js` and loads a composed runtime.
4. [Official run instructions](https://github.com/deepseek-ai/deepseek-harness/blob/master/README.md):
   npm entry is `npx @deepseek-ai/dsh web`; source launch requires dependency
   installation, build, then `pnpm dsh web`. Default web endpoint is loopback
   port 3080. These commands were NOT run here.
5. [Team bundle guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/agent-team-profile/README.md):
   teams are opt-in and require the base profile. The documented activation is
   `dsh plugin --profile web add @deepseek-ai/dsh-experimental-agent-team-profile`.
   This changes a profile and was NOT executed. Use an isolated test profile
   after authorization; do not silently alter the user's normal profile.
6. [Official Config cookbook](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-settings-card.md)
   and [schema implementation](https://github.com/deepseek-ai/deepseek-harness/blob/master/vendor/schemastery/src/index.ts)
   establish volatile reads, owner-managed forms and the transform validator API.

### Exact remaining external blockers

A version-pinned DSH installation or built official checkout is required. The
package set must come from that same verified distribution; mixing a mutable
master API with registry latest is not sufficient. The actual installed version,
Loader instance namespace, Config owner/form, owner-authenticated confirmation
transport, durable plugin state directory and live root Agent are unavailable.
No implementation of the new `completionQAHost` service has been registered in
DSH. Consequently entry loading, Config UI rendering/persistence, authenticated
approval receipt verification and native lifecycle tests remain blocked.
The custom status view also needs real Plugins UI wiring. Installing only the
missing schema module would not resolve these integration requirements.

### Minimum isolated real-host test setup

Use one explicitly authorized, disposable DSH profile, a pinned official build,
a private temporary workspace/state directory, and the base + agent-team bundle.
Register this adapter and a trusted `completionQAHost` service under one unique
Loader entry. Connect a genuine owner-confirmation UI and Config owner before
running actions. Avoid private data; a synthetic prompt and stub model backend
are sufficient for initial plumbing checks. A real model smoke separately needs
permission for its provider, transmission and possible cost.

Required observations, saved with installed versions and timestamps:

1. Real entry imports against official schema/runtime; Config form shows profiles.
2. Saving two profiles survives host restart; stale CAS and invalid secret/unknown
   fields leave authoritative Config unchanged.
3. Exact confirmed operations pass, changed/replayed/forged operations fail;
   native host deny/ask remains authoritative.
4. Root roster is reused; failed-name creation does not repeat; interrupted work
   retains ownership; uncertain messages remain blocked after plugin restart.
5. Conflicting writes are rejected; requested native model/effort remains blocked.
6. A status view shows revision-bound validation and never upgrades not-run smoke.
7. Stop-event and teardown behavior have their own bounded real-host tests. The
   present bridge must not be described as enforcing Stop until those pass.

## Concrete trusted integration example

`integration-example.mjs` contains executable local building blocks, not a mock
DSH installer. It provides an exclusive-writer, atomic-replacement `FileActions`
store and `createCompletionQAHost(...)`. The store's restart, writer exclusion and
return-value isolation were exercised with temporary synthetic records. Syntax
was checked. No real host registration or authenticated UI was exercised.

Construct the example only inside trusted host startup code, then register its
returned object as `completionQAHost` using the installed Cordis version's actual
service mechanism. Do not expose its constructor or confirmation subscriber as
model tools. Required arguments and responsibilities are explicit:

- `ctx`: the actual live context. Root resolution searches `ctx.agents.list()`
  and requires `ctx.agentTeams.membership(agent).root === agent`. No session-ID
  string is substituted for the actual Agent authority credential.
- `configOwner`: the real Plugins form owner. `state.revision` is read directly;
  its `mutate(operations, expectedRevision)` must perform atomic host validation
  and CAS. The example does not emulate Config persistence in another file.
- `confirmations.subscribe(callback)`: only an authenticated owner's confirmation
  events. `verifyReceipt(event)` must cryptographically/transport-authenticate
  the owner and bind the complete operation and Config revision to what the
  owner reviewed. Event text or a claimed source field is insufficient. The
  sample captures detached exact operations and consumes each grant once.
- `probeHost()` and `acceptedVersions`: actual installed build identity and an
  explicitly verified allowlist. Never populate from a model's requested version.
- `actionDirectory`: a private, trusted directory without attacker-controlled
  symlinks, shared by only this plugin instance. The example journals pending
  actions before dispatch, uses fsync/atomic replacement, caps state size, and
  blocks a second writer. After a crash, do not steal `writer.lock`: first prove
  the old writer stopped and inspect pending actions before recovery. This file
  is operational action state, not a competing profile/settings authority.
- `onBridge(bridge)` and `onValidationInvalidated(reason)`: register the methods
  with trusted application code and clear validation displays on Config changes.
  UI wiring and invalidation storage remain the host integrator's responsibility.

An authenticated UI prepares the exact `previewProfiles` result and current
Config snapshot, displays the changes/conflicts, and records approval for the
`importProfiles` operation. It then calls `host.importFromConfirmedUI(text,
revision)`. The example forwards through the bridge to the real form's CAS.
If anything shown changes, the equality check or revision checks reject it.
Do not manufacture an approval event just to make this example pass.

Registry dependency ranges retrieved read-only for reproducibility:

- `npm view @deepseek-ai/dsh@0.2.0-rc.2 dependencies --json` reports Schemastery
  `~3.18.4`, Cordis `~4.0.4`, and team-profile `0.2.0-rc.2`.
- `npm view @deepseek-ai/dsh-experimental-agent-team@0.1.5-alpha.2 dependencies peerDependencies --json`
  reports Schemastery `^3.18.2`, Cordis `^4.0.2` and older `^0.1.5-alpha.2`
  agent/session/LLM peers, including Typert. These ranges do not establish
  compatibility with the direct-inbox API used by mutable master.
- Registry metadata sources: `https://registry.npmjs.org/` for the exact scoped
  package names above. The web retrieval tool could not open its metadata URLs;
  read-only npm CLI metadata retrieval succeeded instead. No tarball was fetched
  or executed in these queries.

The companion example is repository documentation. If distributing a package,
include `integration-example.mjs` in its explicit package files allowlist; the
current code package whitelist does not yet include that documentation example.
