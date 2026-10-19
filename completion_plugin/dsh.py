"""Stdlib-only DSH bridge contract; not an installed DSH plugin.

The injected backend and authorization callback are trusted host code, never
model-supplied configuration. Backend methods below are a Python bridge contract,
not claims that DSH exposes a Python API. An actual loader must implement them
and validate the pinned upstream version. No front-end or hooks are installed.
Local reservations coordinate this adapter instance only, not other host actors.
"""
from copy import deepcopy
from pathlib import PurePosixPath
from threading import RLock
from uuid import uuid4


class DSHBlocked(RuntimeError):
    """Capability, authorization or reconciliation is required."""


class DSHAdapter:
    """Backend contract: probe(), get_config(ns), mutate_config(ns, ops,
    expectedRevision=...), list_members(root), spawn_teammate(root, name,
    provider=..., context=...), send_message(root, member, text), and optional
    interrupt(root, member), get_task(root, task), update_task(root, task,
    patch, expectedRevision=...). All results must be plain data.

    probe returns {host_version, native_team: bool}. Only explicitly supported
    versions are enabled. get_config returns {revision: int, value: dict}.
    authorize receives an isolated operation description and must return True
    from trusted current approval state. It must check revisions and scope.
    """

    def __init__(self, backend=None, *, namespace, root_session_id,
                 supported_versions=(), authorize=None):
        if not namespace or not root_session_id:
            raise ValueError('Namespace and root session are required')
        self.backend = backend
        self.namespace = namespace
        self.team_id = root_session_id
        self.supported_versions = frozenset(supported_versions)
        self._authorize = authorize
        self._lock = RLock()
        self._actions = {}
        self._spawns = {}
        self._reservations = {}

    def capabilities(self):
        result = {'adapter_version': '0.1.0', 'integration_status': 'not_verified',
                  'host_version': None, 'native_team': False,
                  'model_selection': False, 'effective_model': None,
                  'usage_reporting': 'unknown', 'stop_event': 'not_verified',
                  'guard_registration': 'not_verified', 'write_scopes_are_locks': False}
        if self.backend is None:
            result['reason'] = 'Host backend not configured'
            return result
        try:
            probe = deepcopy(self.backend.probe())
            version = probe['host_version']
            if not isinstance(version, str) or version not in self.supported_versions:
                raise DSHBlocked('Unsupported host version')
            result.update(host_version=version, native_team=probe.get('native_team') is True)
        except Exception as exc:
            result['reason'] = str(exc)
        return result

    def _host(self, *, native=False):
        caps = self.capabilities()
        if caps.get('reason') or (native and not caps['native_team']):
            raise DSHBlocked(caps.get('reason', 'Native teams unavailable'))
        return self.backend

    def _approved(self, operation):
        if self._authorize is None or self._authorize(deepcopy(operation)) is not True:
            raise DSHBlocked('Current trusted host approval required')

    def snapshot(self):
        """Read only the authoritative host Config; isolate every operation."""
        value = deepcopy(self._host().get_config(self.namespace))
        if (not isinstance(value, dict) or type(value.get('revision')) is not int
                or value['revision'] < 0 or not isinstance(value.get('value'), dict)):
            raise DSHBlocked('Invalid host configuration snapshot')
        return value

    def mutate_config(self, ops, *, expected_revision):
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Expected revision required')
        operations = deepcopy(ops)
        with self._lock:
            snapshot = self.snapshot()
            if snapshot['revision'] != expected_revision:
                raise DSHBlocked('Configuration revision conflict')
            self._approved({'kind': 'config_mutation', 'namespace': self.namespace,
                            'snapshot': snapshot, 'ops': operations})
            # Host must enforce CAS atomically; never retry on an uncertain write.
            return deepcopy(self._host().mutate_config(
                self.namespace, operations, expectedRevision=expected_revision))

    @staticmethod
    def import_preview(profile, field_mapping):
        """Show unmapped fields and destination collisions before user review."""
        mapped, unknown, conflicts = {}, [], []
        for key, value in profile.items():
            target = field_mapping.get(key)
            if not target:
                unknown.append(key)
            elif target in mapped:
                conflicts.append(target)
            else:
                mapped[target] = deepcopy(value)
        return {'mapped': mapped, 'unknown_fields': unknown, 'conflicts': conflicts,
                'requires_confirmation': True}

    def guard(self, operation, host_decision):
        """Monotonic decision composition; registration is a host responsibility."""
        if host_decision not in ('allow', 'deny', 'ask'):
            return 'deny'
        try:
            self._approved(operation)
        except Exception:
            return 'deny'
        return host_decision

    @staticmethod
    def _scopes(scopes):
        normalized = []
        for raw in scopes:
            if not isinstance(raw, str) or not raw or '\\' in raw:
                raise ValueError('Invalid write scope')
            path = PurePosixPath(raw)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Write scopes must be workspace-relative')
            normalized.append(str(path))
        return tuple(normalized)

    @staticmethod
    def _overlap(a, b):
        return a == '.' or b == '.' or a == b or a.startswith(b + '/') or b.startswith(a + '/')

    def ensure_member(self, name, *, provider, context, write_scopes=(),
                      requested_model=None, allow_inherited=False):
        """Reuse root team and name, then create at most once if outcome unknown.

        provider denotes a DSH resumable backend, not an LLM vendor. Only an
        approved inheritance route is usable; requested model is never forwarded.
        """
        with self._lock:
            host = self._host(native=True)
            snapshot = self.snapshot()
            operation = {'kind': 'native_member', 'name': name, 'provider': provider,
                         'context': deepcopy(context), 'snapshot': snapshot,
                         'write_scopes': list(write_scopes), 'requested_model': requested_model,
                         'allow_inherited': allow_inherited, 'team_id': self.team_id}
            if requested_model is not None or allow_inherited is not True:
                raise DSHBlocked('Native model selection unsupported; approve an inheritance route')
            self._approved(operation)
            scopes = self._scopes(operation['write_scopes'])
            for owner, reserved in self._reservations.items():
                if owner != name and any(self._overlap(a, b) for a in scopes for b in reserved):
                    raise DSHBlocked('Write scopes conflict with an active reservation')
            if name in self._reservations and self._reservations[name] != scopes:
                raise DSHBlocked('Existing member write scope differs')
            members = deepcopy(host.list_members(self.team_id))
            matches = [m for m in members if m.get('name') == name]
            if len(matches) > 1:
                raise DSHBlocked('Ambiguous member identity')
            if matches:
                if matches[0].get('status') in ('failed', 'provisioning'):
                    raise DSHBlocked('Member requires lifecycle reconciliation')
                self._reservations[name] = scopes
                return {'status': 'reused', 'member': matches[0], 'effective_model': None}
            if name in self._spawns:
                raise DSHBlocked('Previous creation unresolved; reconcile host state before reuse')
            self._reservations[name] = scopes
            self._spawns[name] = 'pending'
            try:
                member = host.spawn_teammate(self.team_id, name, provider=provider,
                                            context=deepcopy(context))
            except Exception:
                self._spawns[name] = 'uncertain'
                raise
            self._spawns[name] = 'accepted'
            return {'status': 'accepted', 'member': deepcopy(member), 'effective_model': None}

    def send_message(self, member, text, *, action_id):
        """Same action ID never re-sends, including after timeout/unknown result.

        The caller must persist actions across process restarts before using this
        bridge in production. A new ID must not be used to retry uncertainty.
        """
        if not isinstance(action_id, str) or not action_id:
            raise ValueError('Stable action ID required')
        with self._lock:
            payload = {'member': member, 'text': text}
            if action_id in self._actions:
                old = self._actions[action_id]
                if old['payload'] != payload:
                    raise DSHBlocked('Action ID already belongs to a different message')
                return deepcopy(old)
            # Also block a fresh ID replay of an unresolved identical message.
            if any(a['payload'] == payload and a['status'] == 'uncertain'
                   for a in self._actions.values()):
                raise DSHBlocked('Identical message has an uncertain delivery')
            host = self._host(native=True)
            self._approved({'kind': 'send_message', 'team_id': self.team_id,
                            'snapshot': self.snapshot(), **payload})
            action = {'action_id': action_id, 'payload': deepcopy(payload),
                      'status': 'pending', 'result': None}
            self._actions[action_id] = action
            try:
                action['result'] = deepcopy(host.send_message(self.team_id, member, text))
                action['status'] = 'inbox_accepted'
            except Exception as exc:
                action.update(status='uncertain', error=str(exc))
            return deepcopy(action)

    def interrupt(self, member):
        host = self._host(native=True)
        self._approved({'kind': 'interrupt', 'member': member, 'team_id': self.team_id,
                        'snapshot': self.snapshot()})
        # Interrupt does not release reservations or claim task completion.
        return deepcopy(host.interrupt(self.team_id, member))

    def update_task(self, task_id, patch, *, expected_revision):
        host = self._host(native=True)
        frozen = deepcopy(patch)
        self._approved({'kind': 'update_task', 'task_id': task_id, 'patch': frozen,
                        'expected_revision': expected_revision, 'snapshot': self.snapshot()})
        return deepcopy(host.update_task(self.team_id, task_id, frozen,
                                         expectedRevision=expected_revision))

    @staticmethod
    def usage_attempt(*, status, usage=None, attempt_id=None):
        """One row per attempt, including failures; missing values remain unknown."""
        result = {'attempt_id': attempt_id or str(uuid4()), 'status': status,
                  'tokens': None, 'cost': None, 'currency': None,
                  'measurement_source': 'unknown', 'unknown_reason': 'Host usage missing'}
        if usage is not None:
            data = deepcopy(usage)
            for key in ('tokens', 'cost'):
                value = data.get(key)
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                          or value < 0 or value != value or value == float('inf')):
                    raise ValueError('Invalid usage measurement')
                result[key] = value
            result['currency'] = data.get('currency')
            if result['cost'] is not None and not result['currency']:
                raise ValueError('Cost currency required')
            if result['tokens'] is not None or result['cost'] is not None:
                result['measurement_source'] = 'host_reported'
                result['unknown_reason'] = ('Partial host usage' if None in
                    (result['tokens'], result['cost']) else None)
        return result
