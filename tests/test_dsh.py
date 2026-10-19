"""Synthetic host contract tests; these do not load or exercise real DSH."""
import unittest
from completion_plugin.dsh import DSHAdapter, DSHBlocked


class SyntheticHost:
    def __init__(self):
        self.config = {'revision': 1, 'value': {'route': 'inherit'}}
        self.members = []
        self.calls = []
        self.fail_spawn = False
        self.fail_send = False

    def probe(self):
        return {'host_version': 'synthetic-v1', 'native_team': True}

    def get_config(self, namespace):
        return self.config

    def mutate_config(self, namespace, ops, *, expectedRevision):
        if expectedRevision != self.config['revision']:
            raise ValueError('CAS conflict')
        self.calls.append(('mutate', expectedRevision, ops))
        self.config['revision'] += 1
        return self.config

    def list_members(self, root):
        self.calls.append(('list', root))
        return self.members

    def spawn_teammate(self, root, name, **kwargs):
        self.calls.append(('spawn', root, name, kwargs))
        if self.fail_spawn:
            raise TimeoutError('Outcome unknown')
        member = {'name': name, 'id': 'member-' + name}
        self.members.append(member)
        return member

    def send_message(self, root, member, text):
        self.calls.append(('send', root, member, text))
        if self.fail_send:
            raise TimeoutError('Outcome unknown')
        return {'accepted': True}

    def interrupt(self, root, member):
        self.calls.append(('interrupt', root, member))
        return {'status': 'requested'}

    def update_task(self, root, task, patch, *, expectedRevision):
        self.calls.append(('update', root, task, patch, expectedRevision))
        return {'revision': expectedRevision + 1}


class DSHContractTests(unittest.TestCase):
    def setUp(self):
        self.host = SyntheticHost()
        self.adapter = DSHAdapter(self.host, namespace='unique-loader-id',
                                  root_session_id='root-session',
                                  supported_versions=['synthetic-v1'], authorize=lambda op: True)

    def member(self, name='worker', **kwargs):
        return self.adapter.ensure_member(name, provider='resumable-backend',
                                          context={'prompt': 'fixture'}, allow_inherited=True, **kwargs)

    def test_missing_and_unrecognized_host_block(self):
        bare = DSHAdapter(namespace='ns', root_session_id='root')
        self.assertFalse(bare.capabilities()['native_team'])
        with self.assertRaises(DSHBlocked):
            bare.snapshot()
        self.adapter.supported_versions = frozenset()
        with self.assertRaises(DSHBlocked):
            self.adapter.snapshot()

    def test_capabilities_do_not_claim_real_loading_or_model_control(self):
        result = self.adapter.capabilities()
        self.assertEqual(result['integration_status'], 'not_verified')
        self.assertFalse(result['model_selection'])
        self.assertIsNone(result['effective_model'])
        self.assertFalse(result['write_scopes_are_locks'])

    def test_authoritative_snapshot_is_isolated_and_live(self):
        snapshot = self.adapter.snapshot()
        snapshot['value']['route'] = 'changed'
        self.assertEqual(self.adapter.snapshot()['value']['route'], 'inherit')
        self.host.config['revision'] = 5
        self.assertEqual(self.adapter.snapshot()['revision'], 5)

    def test_config_cas_and_unknown_import(self):
        self.adapter.mutate_config([{'op': 'replace'}], expected_revision=1)
        with self.assertRaises(DSHBlocked):
            self.adapter.mutate_config([], expected_revision=1)
        self.assertEqual(len(self.host.calls), 1)
        preview = self.adapter.import_preview({'model': 'x', 'extra': 1}, {'model': 'route.model'})
        self.assertEqual(preview['unknown_fields'], ['extra'])
        self.assertTrue(preview['requires_confirmation'])

    def test_model_request_blocked_before_spawn(self):
        with self.assertRaises(DSHBlocked):
            self.member(requested_model='specific-model')
        self.assertEqual(self.host.calls, [])

    def test_root_team_member_reused_before_spawn(self):
        self.member()
        result = self.member()
        self.assertEqual(result['status'], 'reused')
        self.assertEqual(sum(c[0] == 'spawn' for c in self.host.calls), 1)
        self.assertEqual(self.host.calls[0], ('list', 'root-session'))
        self.assertNotIn('model', self.host.calls[1][3])

    def test_failed_creation_never_blindly_retried(self):
        self.host.fail_spawn = True
        with self.assertRaises(TimeoutError):
            self.member()
        with self.assertRaises(DSHBlocked):
            self.member()
        self.assertEqual(sum(c[0] == 'spawn' for c in self.host.calls), 1)
        self.host.members.append({'name': 'worker', 'id': 'reserved-name'})
        self.assertEqual(self.member()['status'], 'reused')

    def test_scopes_exclusive_and_interrupt_does_not_release(self):
        self.member(write_scopes=['src'])
        self.adapter.interrupt('worker')
        with self.assertRaises(DSHBlocked):
            self.member('second', write_scopes=['src/file.py'])
        with self.assertRaises(ValueError):
            self.member('second', write_scopes=['../escape'])
        self.member('second', write_scopes=['tests'])

    def test_uncertain_message_is_not_retried_even_with_fresh_id(self):
        self.host.fail_send = True
        result = self.adapter.send_message('worker', 'hello', action_id='action-1')
        self.assertEqual(result['status'], 'uncertain')
        self.adapter.send_message('worker', 'hello', action_id='action-1')
        with self.assertRaises(DSHBlocked):
            self.adapter.send_message('worker', 'hello', action_id='action-2')
        with self.assertRaises(DSHBlocked):
            self.adapter.send_message('worker', 'different', action_id='action-1')
        self.assertEqual(sum(c[0] == 'send' for c in self.host.calls), 1)

    def test_send_acceptance_not_completion_and_result_isolation(self):
        result = self.adapter.send_message('worker', 'hello', action_id='one')
        self.assertEqual(result['status'], 'inbox_accepted')
        result['status'] = 'complete'
        self.assertEqual(self.adapter.send_message('worker', 'hello', action_id='one')['status'], 'inbox_accepted')

    def test_guard_preserves_host_deny_ask_and_requires_trusted_approval(self):
        for decision in ('allow', 'deny', 'ask'):
            self.assertEqual(self.adapter.guard({}, decision), decision)
        self.adapter._authorize = None
        self.assertEqual(self.adapter.guard({'approved': True}, 'allow'), 'deny')
        with self.assertRaises(DSHBlocked):
            self.member()

    def test_update_task_forwards_cas(self):
        self.adapter.update_task('task', {'status': 'running'}, expected_revision=3)
        self.assertEqual(self.host.calls[-1][-1], 3)

    def test_failed_attempts_and_unknown_usage(self):
        first = self.adapter.usage_attempt(status='failed')
        second = self.adapter.usage_attempt(status='failed', usage={'tokens': 5})
        self.assertIsNone(first['cost'])
        self.assertIsNone(first['tokens'])
        self.assertEqual(first['measurement_source'], 'unknown')
        self.assertEqual(second['tokens'], 5)
        self.assertIsNone(second['cost'])
        self.assertNotEqual(first['attempt_id'], second['attempt_id'])
        with self.assertRaises(ValueError):
            self.adapter.usage_attempt(status='success', usage={'cost': 1})


if __name__ == '__main__':
    unittest.main()
