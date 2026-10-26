"""spec-v002 timeline acceptance: monotonic event_sequence, UTC RFC3339 stamps,
before/after document revision, reasons, no-op revisions and clock rollback."""
import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from completion_plugin.workflow import Workflow

RFC3339_UTC = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$')
RECORD = {'sources': ['https://example.org'], 'source': 'user', 'choice': 'fixture', 'status': 'pass'}


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def approved(self):
        workflow = Workflow(self.root / 'state.json', confirm=lambda shown: shown)
        for stage in ('research', 'direction_review', 'specification'):
            workflow.transition(stage, record=RECORD)
        workflow.revise('specification text')
        workflow.add_task('review', code_mode='syntax', acceptance='syntax')
        for stage in ('specification_qa', 'awaiting_confirmation'):
            workflow.transition(stage, record=RECORD)
        return workflow

    def test_event_sequence_is_monotonic(self):
        workflow = self.approved()
        workflow.approve()
        workflow.start('review')
        sequences = [event['event_sequence'] for event in workflow.data['events']]
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))

    def test_event_timestamps_are_utc_rfc3339(self):
        workflow = self.approved()
        for event in workflow.data['events']:
            self.assertRegex(event['at'], RFC3339_UTC)
            self.assertEqual(datetime.fromisoformat(event['at']).utcoffset(), timedelta(0))

    def test_revision_carries_before_and_after(self):
        workflow = self.approved()
        workflow.approve()
        before = workflow.data['revision']
        workflow.revise('changed specification')
        event = workflow.data['events'][-1]
        self.assertEqual(event['kind'], 'specification_revised')
        self.assertEqual(event['revision_before'], before)
        self.assertEqual(event['revision_after'], before + 1)
        transition = [e for e in workflow.data['events']
                      if isinstance(e['kind'], dict) and 'transition' in e['kind']][-1]
        self.assertEqual(transition['revision_before'], transition['revision_after'])

    def test_unchanged_text_creates_no_revision_or_event(self):
        workflow = self.approved()
        events = len(workflow.data['events'])
        revision = workflow.data['revision']
        self.assertEqual(workflow.revise('specification text'), revision)
        self.assertEqual(workflow.data['revision'], revision)
        self.assertEqual(len(workflow.data['events']), events)
        restored = Workflow(workflow.path)
        self.assertEqual(restored.data['revision'], revision)
        self.assertEqual(len(restored.data['events']), events)

    def test_events_record_reason_task_and_actor(self):
        workflow = self.approved()
        workflow.approve()
        confirmation = workflow.data['events'][-1]
        self.assertEqual(confirmation['kind'], 'user_confirmed')
        self.assertEqual(confirmation['actor'], 'confirmed_user')
        self.assertTrue(confirmation['reason'])
        workflow.start('review')
        started = workflow.data['events'][-1]
        self.assertEqual(started['kind'], 'task_started')
        self.assertEqual(started['task'], 'review')
        self.assertTrue(started['reason'])

    def test_clock_rollback_cannot_reorder_causality(self):
        workflow = self.approved()
        workflow.approve()
        with patch('completion_plugin.workflow.now', return_value='2020-01-01T00:00:00+00:00'):
            workflow.revise('later edit observed with an earlier clock')
        last = workflow.data['events'][-1]
        self.assertEqual(last['event_sequence'], len(workflow.data['events']))
        self.assertLess(last['at'], '2026-01-01T00:00:00+00:00')
        restored = Workflow(workflow.path)
        self.assertEqual([e['event_sequence'] for e in restored.data['events']],
                         list(range(1, len(restored.data['events']) + 1)))
        self.assertEqual(restored.data['events'][-1]['revision_after'], restored.data['revision'])

    def test_document_id_is_random_not_content_derived(self):
        first = self.approved()
        second = Workflow(self.root / 'other.json', confirm=lambda shown: shown)
        self.assertRegex(first.data['document_id'], r'^[0-9a-f]{32}$')
        self.assertNotEqual(first.data['document_id'], second.data['document_id'])
        self.assertNotIn(first.data['document_id'], first.data['spec'])

    def test_tasks_have_random_ids_in_proposal(self):
        workflow = self.approved()
        task = workflow.data['tasks']['review']
        self.assertRegex(task['task_id'], r'^[0-9a-f]{32}$')
        self.assertIn('task_id', workflow._proposal()['tasks']['review'])

    def test_reviewing_stage_sits_between_executing_and_complete(self):
        workflow = self.approved()
        workflow.approve()
        workflow.start('review')
        workflow.transition('reviewing', record=RECORD)
        self.assertEqual(workflow.data['state'], 'reviewing')
        with self.assertRaises(ValueError):
            workflow.complete()
        workflow._verifiers['review'] = lambda: True
        workflow.finish('review', status='pass', result={
            'review': {'revision': workflow.data['revision'], 'allow_completion': True,
                       'code_mode': 'syntax', 'checks': {'code': 'pass'}}})
        workflow.complete()
        self.assertEqual(Workflow(workflow.path).data['state'], 'complete')

    def test_legacy_sequence_events_remain_readable(self):
        workflow = self.approved()
        state = json.loads(workflow.path.read_text(encoding='utf-8'))
        for event in state['events']:
            event['sequence'] = event.pop('event_sequence')
        workflow.path.write_text(json.dumps(state), encoding='utf-8')
        restored = Workflow(workflow.path)
        self.assertEqual(len(restored.data['events']), len(state['events']))

    def test_damaged_timestamp_rejected(self):
        workflow = self.approved()
        state = json.loads(workflow.path.read_text(encoding='utf-8'))
        state['events'][-1]['at'] = '2026-10-22 12:00:00'
        workflow.path.write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaises(ValueError):
            Workflow(workflow.path)

    def test_damaged_document_id_rejected(self):
        workflow = self.approved()
        state = json.loads(workflow.path.read_text(encoding='utf-8'))
        state['document_id'] = ''
        workflow.path.write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaises(ValueError):
            Workflow(workflow.path)


if __name__ == '__main__':
    unittest.main()
