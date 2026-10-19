import { isDeepStrictEqual } from 'node:util';
import { posix } from 'node:path';
import { parseProfiles, importPreview, profileStatus } from './profiles.js';

const clone = value => structuredClone(value);
const blocked = message => { throw new Error(message); };

// Trusted host seam supplies current approval, version probe, synchronous
// durable action records, live Agent resolution, and bridge registration.
export function install(ctx, config) {
  const host = ctx.completionQAHost;
  if (!host || typeof host.probe !== 'function') blocked('Trusted host integration absent');
  const probe = host.probe();
  if (!probe || host.supportsVersion(probe.version) !== true) blocked('Unsupported host version');
  const snapshot = () => Object.freeze({
    inheritModel: config.inheritModel.get(), maxConcurrent: config.maxConcurrent.get(),
    revision: host.configRevision(),
    profiles: parseProfiles(config.profilesJson.get()),
  });
  const approved = operation => {
    if (host.authorize(clone(operation)) !== true) blocked('Current trusted approval required');
  };
  const reservations = new Map();
  let disposed = false;
  const caller = root => {
    if (disposed) blocked('Plugin disposed');
    const agent = host.resolveRootAgent(root);
    if (!agent || ctx.agentTeams.membership(agent).root !== agent || agent.id !== root)
      blocked('Exact live root Agent required');
    return agent;
  };
  const scopeList = list => list.map(raw => {
    if (typeof raw !== 'string' || !raw || raw.includes('\\') || posix.isAbsolute(raw)
        || raw.split('/').includes('..')) blocked('Invalid write scope');
    return posix.normalize(raw).replace(/\/$/, '') || '.';
  });
  const overlap = (a, b) => a === '.' || b === '.' || a === b || a.startsWith(b + '/') || b.startsWith(a + '/');
  const bridge = {
    capabilities: () => ({version: probe.version, modelSelection: false, effectiveModel: null,
      usage: 'unknown', realHostValidation: 'not_run', writeScopesAreLocks: false}),
    snapshot,
    profileStatus: () => profileStatus(config.profilesJson.get()),
    previewProfiles: text => importPreview(config.profilesJson.get(), text),
    importProfiles(form, text, expectedRevision) {
      const current = config.profilesJson.get();
      const preview = importPreview(current, text);
      const frozen = snapshot();
      if (frozen.revision !== expectedRevision) blocked('Config revision conflict');
      for (const p of preview.candidate.profiles) {
        const old = frozen.profiles.profiles.find(x => x.profile_id === p.profile_id);
        if (old && !isDeepStrictEqual(old, p) && p.profile_revision <= old.profile_revision)
          blocked('Changed profiles require a newer revision');
      }
      approved({kind:'importProfiles', preview, expectedRevision, config:frozen});
      if (config.profilesJson.get() !== current || host.configRevision() !== expectedRevision)
        blocked('Config changed during approval');
      return form.mutate([{op:'replace', path:'/profilesJson', value:JSON.stringify(preview.candidate)}], expectedRevision);
    },
    // form is supplied by the trusted Plugins page owner. No sidecar settings.
    mutateConfig(form, operations, expectedRevision) {
      const ops = clone(operations);
      approved({kind: 'config', operations: ops, expectedRevision, config: snapshot()});
      return form.mutate(ops, expectedRevision);
    },
    async ensureMember(root, request, {writeScopes = [], requestedModel = null} = {}) {
      const agent = caller(root);
      const frozen = snapshot();
      if (requestedModel !== null || frozen.inheritModel !== true)
        blocked('Native specific-model routing unsupported; approved inheritance required');
      const {signal, ...body} = request;
      const data = clone(body);
      if (Object.keys(data).some(k => !['name', 'description', 'prompt', 'context', 'provider'].includes(k)))
        blocked('Unknown native spawn field');
      approved({kind: 'spawn', root, request: data, writeScopes, config: frozen});
      const scopes = scopeList(writeScopes);
      const key = JSON.stringify([root, data.name]);
      if (reservations.has(key) && !isDeepStrictEqual(reservations.get(key), scopes))
        blocked('Reserved member scopes differ');
      for (const [owner, held] of reservations)
        if (owner !== key && scopes.some(a => held.some(b => overlap(a, b)))) blocked('Write scope conflict');
      const matches = ctx.agentTeams.listMembers(agent).filter(m => m.name === data.name);
      if (matches.length > 1) blocked('Ambiguous member');
      if (matches.length === 1) {
        if (matches[0].status === 'failed' || matches[0].status === 'provisioning')
          blocked('Member requires lifecycle reconciliation');
        reservations.set(key, scopes);
        return {status: 'reused', member: clone(matches[0]), effectiveModel: null};
      }
      if (reservations.size >= frozen.maxConcurrent) blocked('Plugin concurrency limit');
      const actionKey = 'spawn:' + key;
      if (host.actions.get(actionKey)) blocked('Previous spawn needs reconciliation');
      reservations.set(key, scopes);
      host.actions.put(actionKey, {status: 'pending', request: data});
      try {
        const result = await ctx.agentTeams.spawnTeammate(agent, {...data, signal});
        host.actions.put(actionKey, {status: 'accepted', request: data});
        return {status: 'accepted', result: clone(result), effectiveModel: null};
      } catch (error) {
        host.actions.put(actionKey, {status: 'uncertain', request: data});
        throw error;
      }
    },
    async sendMessage(root, request, actionId) {
      const agent = caller(root);
      if (typeof actionId !== 'string' || !actionId) blocked('Stable action ID required');
      const {signal, ...body} = request;
      const payload = {root, ...clone(body)};
      const key = 'send:' + actionId;
      const old = host.actions.get(key);
      if (old) {
        if (!isDeepStrictEqual(old.payload, payload)) blocked('Action ID conflict');
        return clone(old);
      }
      for (const old of host.actions.values())
        if (['pending', 'uncertain'].includes(old.status) && isDeepStrictEqual(old.payload, payload))
          blocked('Message delivery unresolved');
      approved({kind: 'send', payload, config: snapshot()});
      host.actions.put(key, {status: 'pending', payload});
      let result;
      try {
        result = {status: 'inbox_accepted', payload,
          result: clone(await ctx.agentTeams.sendMessage(agent, {...clone(body), signal}))};
      } catch (error) { result = {status: 'uncertain', payload, error: String(error)}; }
      host.actions.put(key, result);
      return clone(result);
    },
    updateTask(root, request) {
      const agent = caller(root), frozen = clone(request);
      if (!Number.isSafeInteger(frozen.expectedRevision) || frozen.expectedRevision < 1)
        blocked('Task expectedRevision required');
      approved({kind: 'updateTask', root, request: frozen, config: snapshot()});
      return ctx.agentTeams.updateTask(agent, frozen);
    },
    interrupt(root, name) {
      const agent = caller(root);
      approved({kind: 'interrupt', root, name, config: snapshot()});
      return ctx.agentTeams.interrupt(agent, name); // Reservations deliberately retained.
    },
    createTask(root, request) {
      const agent = caller(root), frozen = clone(request);
      approved({kind: 'createTask', root, request: frozen, config: snapshot()});
      return ctx.agentTeams.createTask(agent, frozen);
    },
    waitForChange(root, timeoutMs, signal) {
      if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 10000 || timeoutMs > 3600000)
        blocked('Wait duration outside host bounds');
      return ctx.agentTeams.waitForChange(caller(root), timeoutMs, signal);
    },
    listMembers: root => clone(ctx.agentTeams.listMembers(caller(root))),
    listTasks: root => clone(ctx.agentTeams.listTasks(caller(root))),
    getTask: (root, id) => clone(ctx.agentTeams.getTask(caller(root), id)),
  };
  ctx.tools.guard(exec => {
    if (!host.manages(exec.agent)) return undefined;
    try {
      approved({kind: 'tool', agentId: exec.agent?.id, name: exec.name,
        args: exec.args, config: snapshot()});
      return undefined; // Never force allow, preserving host deny/ask.
    } catch { return 'CompletionQA approval required'; }
  });
  ctx.on('loader/volatile-update', () => host.invalidateValidation('config_changed'));
  ctx.on('dispose', () => { disposed = true; });
  host.registerBridge(bridge);
  return bridge;
}
