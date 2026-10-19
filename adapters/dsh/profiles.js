// Bounded profile configuration only. Imported validation/authorization is forbidden.
import { isDeepStrictEqual } from 'node:util';
export const EMPTY_PROFILES = '{"schema_version":1,"profiles":[]}';
const fail = message => { throw new Error(message); };
function fields(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || !isDeepStrictEqual(Object.keys(value).sort(), [...keys].sort()))
    fail('Missing or unknown profile field (credentials and validation evidence are forbidden)');
}
function id(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_.:/-]{1,128}$/.test(value)
      || /^(sk-|sk_|gh[pousr]_|github_pat_|AIza|AKIA|Bearer|eyJ)/i.test(value))
    fail('Only bounded identifiers or credential references are allowed, never secrets');
}
function integer(value, min, max) {
  if (!Number.isSafeInteger(value) || value < min || value > max) fail('Integer outside supported range');
}
function list(value, nonempty = false) {
  if (!Array.isArray(value) || value.length > 256 || (nonempty && !value.length)) fail('Bounded list required');
}
function unique(values) {
  if (new Set(values).size !== values.length) fail('Duplicate identifier or cyclic fallback');
}
function strictJSON(text) {
  if (typeof text !== 'string' || Buffer.byteLength(text, 'utf8') > 1048576) fail('Profile text exceeds limit');
  const stack = [];
  // Track object keys before JSON.parse discards duplicate occurrences.
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '{' || c === '[') {
      stack.push(c === '{' ? new Set() : null);
      if (stack.length > 32) fail('JSON nesting exceeds limit');
    } else if (c === '}' || c === ']') stack.pop();
    else if (c === '"') {
      const start = i++;
      for (; i < text.length; i++) {
        if (text[i] === '\\') i++;
        else if (text[i] === '"') break;
      }
      let next = i + 1;
      while (/\s/.test(text[next] || '') && next < text.length) next++;
      if (text[next] === ':' && stack.at(-1) instanceof Set) {
        const key = JSON.parse(text.slice(start, i + 1));
        if (stack.at(-1).has(key)) fail('Duplicate JSON field');
        stack.at(-1).add(key);
      }
    }
  }
  return JSON.parse(text);
}
export function parseProfiles(text) {
  const data = strictJSON(text);
  fields(data, ['schema_version', 'profiles']);
  if (data.schema_version !== 1) fail('Unsupported profile collection version');
  list(data.profiles);
  unique(data.profiles.map(p => p?.profile_id));
  for (const p of data.profiles) {
    fields(p, ['schema_version', 'profile_id', 'profile_revision', 'name', 'created_at',
      'modified_at', 'routes', 'roles', 'allowlist', 'default_role']);
    if (p.schema_version !== 1) fail('Unsupported profile version');
    [p.profile_id, p.name, p.default_role].forEach(id);
    integer(p.profile_revision, 1, Number.MAX_SAFE_INTEGER);
    for (const t of [p.created_at, p.modified_at])
      if (typeof t !== 'string' || !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(t)
          || !Number.isFinite(Date.parse(t))) fail('Timezone-aware timestamps required');
    if (Date.parse(p.modified_at) < Date.parse(p.created_at)) fail('Modification predates creation');
    list(p.routes, true); list(p.roles, true); list(p.allowlist);
    const routes = p.routes.map(r => {
      fields(r, ['route_id', 'provider', 'model', 'effort', 'auth_ref']);
      [r.route_id, r.provider, r.model, r.auth_ref].forEach(id);
      if (!['inherit','low','medium','high','xhigh','max'].includes(r.effort)) fail('Unsupported effort');
      return r.route_id;
    });
    unique(routes); unique(p.roles.map(r => r.name)); unique(p.allowlist); p.allowlist.forEach(id);
    if (!isDeepStrictEqual([...routes].sort(), [...p.allowlist].sort())) fail('Every route must be allowlisted');
    for (const r of p.roles) {
      fields(r, ['name','route_id','concurrency','timeout_seconds','fallbacks']);
      id(r.name); id(r.route_id); integer(r.concurrency,1,256); integer(r.timeout_seconds,1,86400);
      list(r.fallbacks); r.fallbacks.forEach(id); unique([r.route_id,...r.fallbacks]);
      if (![r.route_id,...r.fallbacks].every(x => routes.includes(x))) fail('Unknown route reference');
    }
    if (!p.roles.some(r => r.name === p.default_role)) fail('Unknown default role');
  }
  return data;
}
export function importPreview(currentText, incomingText) {
  const current = parseProfiles(currentText), incoming = parseProfiles(incomingText);
  const currentById = new Map(current.profiles.map(p => [p.profile_id,p]));
  const conflicts = [], changes = [];
  for (const p of incoming.profiles) {
    const previous = currentById.get(p.profile_id);
    if (!previous) changes.push({profile_id:p.profile_id, kind:'add'});
    else if (!isDeepStrictEqual(previous,p)) {
      conflicts.push({profile_id:p.profile_id, current_revision:previous.profile_revision,
        incoming_revision:p.profile_revision, reason:'Existing profile differs; explicit replacement confirmation required'});
      changes.push({profile_id:p.profile_id,kind:'replace'});
    }
  }
  const deleted = current.profiles.filter(p => !incoming.profiles.some(q => q.profile_id === p.profile_id));
  for (const p of deleted) changes.push({profile_id:p.profile_id,kind:'delete'});
  return {changes, conflicts, requires_confirmation:true, mapping:'Exact CompletionQA profile schema v1',
    validation_evidence_imported:false, candidate:incoming};
}
export function profileStatus(text) {
  return parseProfiles(text).profiles.map(p => ({profile_id:p.profile_id,profile_revision:p.profile_revision,
    name:p.name,schema:'validated_schema',capability:'blocked',discovery:'not_run',smoke:'not_run',
    reason:'DSH native model/effort selection unsupported; saved intentions do not establish execution',
    roles:p.roles.map(r=>({name:r.name,route_id:r.route_id,fallbacks:[...r.fallbacks]}))}));
}
