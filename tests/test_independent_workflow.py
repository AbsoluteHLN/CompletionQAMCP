"""Independent negative-path coverage of the local workflow and evidence APIs."""
import json
import math
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from completion_plugin.evidence import Review, snapshot
from completion_plugin.usage import Ledger
from completion_plugin.workflow import Workflow


class IndependentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def ready(self, scopes=(('src',),), required_checks=('code',)):
        workflow = Workflow(self.root / 'state.json', confirm=lambda shown: shown)
        for stage in ('research', 'direction_review', 'specification'):
            workflow.transition(stage, record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'})
        workflow.revise('Approved specification')
        for index, writes in enumerate(scopes):
            workflow.add_task(str(index), writes=writes, code_mode='syntax',acceptance='run checks', required_checks=required_checks)
        self.review_and_approve(workflow)
        return workflow

    def verified_result(self, workflow, name='0'):
        """Real syntax Review, installed through the trusted application boundary."""
        artifact = self.root / ('task_' + name + '.py')
        artifact.write_text('checked = True\n')
        review = Review(self.root, [artifact.name], workflow.data['revision'])
        review.syntax()
        workflow._verifiers[name] = lambda: review.gate(['code'])['allow_completion']
        return {'review': review.gate(['code']), 'observations': ['pass']}

    @staticmethod
    def review_and_approve(workflow):
        workflow.transition('specification_qa', record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'})
        workflow.transition('awaiting_confirmation', record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'})
        workflow.approve()

    def test_changed_spec_invalidates_pass_results(self):
        workflow = self.ready()
        workflow.start('0')
        workflow.finish('0', status='pass', result=self.verified_result(workflow))
        workflow.revise('Changed specification and acceptance target')
        self.review_and_approve(workflow)
        with self.assertRaises(ValueError):
            workflow.complete()

    def test_required_text_evidence_cannot_be_omitted(self):
        workflow = self.ready(required_checks=('code', 'text'))
        workflow.start('0')
        with self.assertRaises(ValueError):
            workflow.finish('0', status='pass', result=self.verified_result(workflow))

    def test_changed_content_after_finish_blocks_complete(self):
        workflow = self.ready()
        workflow.start('0')
        workflow.finish('0', status='pass', result=self.verified_result(workflow))
        (self.root / 'task_0.py').write_text('checked = False\n')
        with self.assertRaises(ValueError):
            workflow.complete()

    def test_missing_research_sources_rejected(self):
        workflow = Workflow(self.root / 'state.json')
        workflow.transition('research', record={'goals': 'fixture'})
        with self.assertRaises(ValueError):
            workflow.transition('direction_review', record={'status': 'pass'})

    def test_direction_without_user_source_rejected(self):
        workflow = Workflow(self.root / 'state.json')
        workflow.transition('research', record={'goals': 'fixture'})
        workflow.transition('direction_review', record={'sources': ['https://example.org']})
        with self.assertRaises(ValueError):
            workflow.transition('specification', record={'choice': 'model recommendation'})

    def test_untrusted_pass_without_application_verifier_rejected(self):
        workflow = self.ready()
        workflow.start('0')
        forged = {'review': {'revision': workflow.data['revision'],
                            'allow_completion': True, 'checks': {'code': 'pass'}}}
        with self.assertRaises(ValueError):
            workflow.finish('0', status='pass', result=forged)

    def test_restore_requires_verifier_reconnection_before_complete(self):
        workflow = self.ready()
        workflow.start('0')
        workflow.finish('0', status='pass', result=self.verified_result(workflow))
        restored = Workflow(workflow.path)
        with self.assertRaises(ValueError):
            restored.complete()

    def test_scope_dot_alias_cannot_run_concurrently(self):
        workflow = self.ready((('src',), ('./src/file.py',)))
        workflow.start('0')
        with self.assertRaises(ValueError):
            workflow.start('1')

    def test_parent_scope_alias_rejected_or_conflicts(self):
        try:
            workflow = self.ready((('src',), ('other/../src/file.py',)))
        except ValueError:
            return
        workflow.start('0')
        with self.assertRaises(ValueError):
            workflow.start('1')

    def test_normal_nested_scopes_conflict(self):
        workflow = self.ready((('src',), ('src/sub/file.py',)))
        workflow.start('0')
        with self.assertRaises(ValueError):
            workflow.start('1')

    def test_independent_scopes_can_run(self):
        workflow = self.ready((('src/a',), ('src/b',)))
        workflow.start('0')
        workflow.start('1')
        self.assertEqual(workflow.data['tasks']['1']['status'], 'running')

    def test_damaged_restored_state_rejected(self):
        path = self.root / 'broken.json'
        path.write_text(json.dumps({'schema_version': 1, 'events': []}))
        with self.assertRaises(ValueError):
            Workflow(path)

    def test_mismatching_restored_approval_rejected(self):
        workflow = self.ready()
        state = json.loads(workflow.path.read_text())
        state['approval']['spec'] = 'different text'
        workflow.path.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            Workflow(workflow.path)

    def test_damaged_event_sequence_rejected(self):
        workflow = self.ready()
        state = json.loads(workflow.path.read_text())
        state['events'][-1]['sequence'] = 1
        workflow.path.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            Workflow(workflow.path)

    def test_readable_state_cannot_silently_replace_deleted_state(self):
        workflow = self.ready()
        workflow.path.unlink()
        with self.assertRaises(ValueError):
            workflow.start('0')

    def test_generator_dependencies_are_preserved(self):
        workflow = Workflow(self.root / 'state.json', confirm=lambda shown: shown)
        for stage in ('research', 'direction_review', 'specification'):
            workflow.transition(stage, record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'})
        workflow.revise('specification')
        workflow.add_task('parent', code_mode='syntax',acceptance='pass')
        workflow.add_task('child', depends=iter(['parent']), code_mode='syntax',acceptance='pass')
        self.review_and_approve(workflow)
        with self.assertRaises(ValueError):
            workflow.start('child')

    def test_restored_completed_task_needs_result(self):
        workflow = self.ready()
        workflow.start('0')
        workflow.finish('0', status='pass', result=self.verified_result(workflow))
        workflow.complete()
        state = json.loads(workflow.path.read_text())
        state['tasks']['0']['result'] = None
        workflow.path.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            Workflow(workflow.path)

    def test_restored_task_cannot_lose_required_checks(self):
        workflow = self.ready(required_checks=('code', 'text'))
        state = json.loads(workflow.path.read_text())
        state['tasks']['0']['required_checks'] = []
        workflow.path.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            Workflow(workflow.path)

    def test_restored_completed_review_revision_must_match(self):
        workflow = self.ready()
        workflow.start('0')
        workflow.finish('0', status='pass', result=self.verified_result(workflow))
        workflow.complete()
        state = json.loads(workflow.path.read_text())
        state['tasks']['0']['result']['review']['revision'] = 0
        workflow.path.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            Workflow(workflow.path)

    def test_concurrent_writers_do_not_both_commit(self):
        seed = Workflow(self.root / 'state.json')
        seed.revise('initial')
        writers = [Workflow(seed.path), Workflow(seed.path)]
        start = threading.Barrier(2)
        successes, errors = [], []
        real_read = Path.read_text

        def delayed_read(path, *args, **kwargs):
            data = real_read(path, *args, **kwargs)
            if path == seed.path and threading.current_thread() != threading.main_thread():
                time.sleep(0.05)
            return data

        def write(index):
            start.wait(timeout=5)
            try:
                writers[index].revise('revision ' + str(index))
                successes.append(index)
            except ValueError:
                errors.append(index)

        with patch.object(Path, 'read_text', delayed_read):
            threads = [threading.Thread(target=write, args=(i,)) for i in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive(), 'writer did not finish')
        self.assertEqual(len(successes), 1, 'concurrent writers silently overwrote state')
        self.assertEqual(len(errors), 1)

    def test_returned_execution_result_is_isolated(self):
        workflow = self.ready()
        workflow.start('0')
        result = self.verified_result(workflow)
        workflow.finish('0', status='pass', result=result)
        result['observations'].clear()
        self.assertEqual(workflow.data['tasks']['0']['result']['observations'], ['pass'])


class IndependentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'a.py').write_text('x = 1\n')

    def test_same_size_change_invalidates_review(self):
        review = Review(self.root, ['a.py'], 1)
        review.syntax()
        (self.root / 'a.py').write_text('x = 2\n')
        self.assertFalse(review.gate(['code'])['allow_completion'])

    def test_deleted_file_blocks_gate(self):
        review = Review(self.root, ['a.py'], 1)
        review.syntax()
        (self.root / 'a.py').unlink()
        self.assertFalse(review.gate(['code'])['allow_completion'])

    def test_empty_generator_does_not_allow_completion(self):
        review = Review(self.root, ['a.py'], 1)
        self.assertFalse(review.gate(iter(()))['allow_completion'])

    def test_returned_syntax_result_is_deeply_isolated(self):
        (self.root / 'a.py').write_text('x =')
        review = Review(self.root, ['a.py'], 1)
        result = review.syntax()
        result['errors'][0]['reason'] = 'caller changed this'
        self.assertNotEqual(review.results['code']['errors'][0]['reason'], 'caller changed this')

    def test_detected_change_requires_new_review_even_if_restored(self):
        review = Review(self.root, ['a.py'], 1)
        review.syntax()
        (self.root / 'a.py').write_text('x = 2\n')
        self.assertEqual(review.syntax()['status'], 'blocked')
        (self.root / 'a.py').write_text('x = 1\n')
        self.assertFalse(review.gate(['code'])['allow_completion'])

    def test_oversized_file_is_not_read_unbounded(self):
        (self.root / 'a.py').write_bytes(b' ' * 1_000_001)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded read')):
            with self.assertRaises(ValueError):
                Review(self.root, ['a.py'], 1)

    def create_project_test(self, passing=True):
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / 'test_sample.py').write_text(
            'import unittest\nclass Sample(unittest.TestCase):\n'
            '    def test_case(self): self.assertTrue(' + repr(passing) + ')\n')

    def test_project_dependency_changed_after_run_blocks_gate(self):
        self.create_project_test()
        review = Review(self.root, ['a.py'], 1)
        self.assertEqual(review.project_tests(explicitly_trusted=True)['status'], 'pass')
        (self.root / 'tests' / 'test_sample.py').write_text('changed = True\n')
        self.assertFalse(review.gate(['code'])['allow_completion'])

    def test_syntax_cannot_erase_failed_project_execution(self):
        self.create_project_test(passing=False)
        review = Review(self.root, ['a.py'], 1)
        self.assertEqual(review.project_tests(explicitly_trusted=True)['status'], 'fail')
        review.syntax()
        self.assertFalse(review.gate(['code'])['allow_completion'])

    def test_missing_required_check_blocks(self):
        review = Review(self.root, ['a.py'], 1)
        review.syntax()
        self.assertFalse(review.gate(['code', 'native'])['allow_completion'])

    def test_symlink_outside_root_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external) / 'secret.py'
            outside.write_text('secret = 1')
            (self.root / 'link').symlink_to(external, target_is_directory=True)
            with self.assertRaises(ValueError):
                snapshot(self.root, ['link/secret.py'])

    def test_parent_traversal_rejected(self):
        with self.assertRaises(ValueError):
            snapshot(self.root, ['../a.py'])

    def test_oversized_file_blocked(self):
        (self.root / 'a.py').write_bytes(b' ' * 1_000_001)
        with self.assertRaises(ValueError):
            Review(self.root, ['a.py'], 1)


class IndependentUsageTests(unittest.TestCase):
    def test_nonfinite_measurements_rejected(self):
        for field in ('tokens', 'cost'):
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        Ledger().record(task='task', model='model', status='fail',
                                        source='actual', currency='USD', **{field: value})

    def test_unknown_cost_blocks_budget(self):
        ledger = Ledger()
        ledger.record(task='task', model='model', status='fail')
        self.assertFalse(ledger.budget_allows(10, 'USD'))

    def test_estimated_cost_does_not_guarantee_budget(self):
        ledger = Ledger()
        ledger.record(task='task', model='model', status='pass', cost=1,
                      currency='USD', source='estimated')
        self.assertFalse(ledger.budget_allows(10, 'USD'))

    def test_currency_mismatch_blocks_budget(self):
        ledger = Ledger()
        ledger.record(task='task', model='model', status='pass', cost=1,
                      currency='EUR', source='actual')
        self.assertFalse(ledger.budget_allows(10, 'USD'))

    def test_failed_attempt_cost_counts(self):
        ledger = Ledger()
        ledger.record(task='task', model='model', status='fail', cost=10,
                      currency='USD', source='actual')
        self.assertFalse(ledger.budget_allows(10, 'USD'))


if __name__ == '__main__':
    unittest.main()
