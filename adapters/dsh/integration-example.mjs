/** Executable integration building blocks, NOT a DSH service registration.
 * Only trusted host code may construct this object or publish confirmation events.
 * The UI event source and Config owner still require version-specific DSH wiring.
 */
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';

export class FileActions {
  constructor(directory) {
    this.directory = directory;
    fs.mkdirSync(directory, {recursive:true, mode:0o700});
    // Hold until clean shutdown. After a crash, an operator must establish that
    // the old writer has stopped before removing writer.lock. Never steal it.
    this.lockPath = path.join(directory, 'writer.lock');
    this.lock = fs.openSync(this.lockPath, 'wx', 0o600);
    this.file = path.join(directory, 'actions.json');
    try {
      const size = fs.statSync(this.file).size;
      if (size > 1048576) throw Error('Action store exceeds bound');
      const data = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      if (data.version !== 1 || !Array.isArray(data.entries)
          || data.entries.some(x=>!Array.isArray(x)||x.length!==2||typeof x[0]!=='string')
          || new Set(data.entries.map(x=>x[0])).size !== data.entries.length)
        throw Error('Invalid action store');
      this.entries = new Map(data.entries);
    } catch (error) {
      if (error.code === 'ENOENT') this.entries = new Map();
      else { this.close(); throw error; }
    }
  }
  get(key) { return structuredClone(this.entries.get(key)); }
  values() { return structuredClone([...this.entries.values()]); }
  put(key, value) {
    if (this.lock === null) throw Error('Store closed');
    const entries = new Map(this.entries); entries.set(key, structuredClone(value));
    const text = JSON.stringify({version:1, entries:[...entries]});
    if (Buffer.byteLength(text) > 1048576) throw Error('Action store exceeds bound');
    const temp = path.join(this.directory, randomUUID() + '.tmp');
    const fd = fs.openSync(temp, 'wx', 0o600);
    try { fs.writeFileSync(fd, text); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temp, this.file);
    const dir = fs.openSync(this.directory, 'r');
    try { fs.fsyncSync(dir); } finally { fs.closeSync(dir); }
    this.entries = entries;
  }
  close() {
    if (this.lock !== null) {
      fs.closeSync(this.lock); this.lock = null; fs.unlinkSync(this.lockPath);
    }
  }
}

export function createCompletionQAHost({ctx, configOwner, confirmations,
  probeHost, acceptedVersions, actionDirectory, onBridge, onValidationInvalidated}) {
  // configOwner is the actual Plugins form owner, with a stable .state.revision
  // and atomic .mutate(operations, expectedRevision). Never emulate its CAS.
  const actions = new FileActions(actionDirectory);
  const grants = [];
  const managedRoots = new Set();
  let bridge;
  const unsubscribe = confirmations.subscribe(event => {
    // verifyReceipt MUST authenticate the actual owner and bind the exact shown
    // operation/revision. This call is supplied by trusted UI transport code,
    // never by model arguments, imported JSON, or an event's claimed source.
    if (confirmations.verifyReceipt(event) !== true) return;
    if (event.configRevision !== configOwner.state.revision) return;
    const operation = structuredClone(event.operation);
    if (operation.config?.revision !== configOwner.state.revision) return;
    grants.push(operation);
    if (operation.root) managedRoots.add(operation.root);
  });
  const host = {
    probe: () => structuredClone(probeHost()),
    supportsVersion: version => acceptedVersions.includes(version),
    configRevision: () => configOwner.state.revision,
    authorize(operation) {
      const index = grants.findIndex(grant => isDeepStrictEqual(grant, operation));
      if (index < 0 || operation.config?.revision !== configOwner.state.revision) return false;
      grants.splice(index, 1); // One exact operation, one trusted confirmation.
      return true;
    },
    resolveRootAgent(root) {
      const agent = ctx.agents.list().find(a => a.id === root);
      if (!agent || ctx.agentTeams.membership(agent).root !== agent) throw Error('Live root missing');
      return agent;
    },
    manages(agent) {
      if (!agent) return false;
      try { return managedRoots.has(ctx.agentTeams.membership(agent).root.id); }
      catch { return false; }
    },
    invalidateValidation(reason) { grants.length = 0; onValidationInvalidated(reason); },
    registerBridge(value) { bridge = value; onBridge(value); },
    actions,
    // Only expose this wrapper in the authenticated Plugins UI. It uses the
    // bridge's exact preview/approval checks, then the real owner's atomic CAS.
    importFromConfirmedUI(text, revision) { return bridge.importProfiles(configOwner, text, revision); },
    close() { unsubscribe(); grants.length = 0; actions.close(); },
  };
  return host;
}
