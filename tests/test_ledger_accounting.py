"""spec-v002 U01 acceptance: every attempt is accounted, unknown billing stays
null with a stated reason, and zero recorded calls never claim zero cost."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from completion_plugin.runtime import execute_review
from completion_plugin.usage import Ledger
from completion_plugin.workflow import Workflow

RECORD = {'sources': ['https://example.org'], 'source': 'user', 'choice': 'fixture', 'status': 'pass'}


class LedgerAccountingTests(unittest.TestCase):
    def test_failed_request_is_accounted_with_unknown_billing(self):
        row = Ledger().record(task='task', model='model', status='fail')
        self.assertIsNone(row['tokens'])
        self.assertIsNone(row['cost'])
        self.assertEqual(row['measurement_source'], 'unknown')
        self.assertEqual(row['unknown_reason'], 'usage_not_reported')
        self.assertIsNotNone(row['ended_at'])

    def test_partial_measurement_keeps_null_and_reason(self):
        row = Ledger().record(task='task', model='model', status='pass', tokens=120,
                              measurement_source='actual')
        self.assertIsNone(row['cost'])
        self.assertEqual(row['unknown_reason'], 'partial_measurement')

    def test_routing_fields_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.json'
            started = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
            Ledger(path).record(task='task', model='model', provider='provider', status='pass',
                                run_id='run-1', operation='host_generation', started_at=started,
                                tokens=10, cost=0.5, currency='USD', measurement_source='actual')
            row = Ledger(path).attempts[0]
            self.assertEqual(row['provider'], 'provider')
            self.assertEqual(row['run_id'], 'run-1')
            self.assertEqual(row['operation'], 'host_generation')
            self.assertEqual(row['started_at'], started.astimezone(timezone.utc).isoformat())
            self.assertGreaterEqual(row['ended_at'], row['started_at'])
            self.assertIsNone(row['unknown_reason'])

    def test_zero_calls_do_not_claim_zero_cost(self):
        ledger = Ledger()
        self.assertEqual(ledger.attempts, [])
        self.assertFalse(ledger.budget_allows(10, 'USD', next_max_cost=0))

    def test_legacy_source_rows_remain_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.json'
            path.write_text(json.dumps([{'attempt_id': 'old', 'task': 't', 'model': 'm',
                                         'status': 'fail', 'tokens': None, 'cost': None,
                                         'currency': None, 'source': 'unknown',
                                         'at': '2026-10-22T00:00:00+00:00'}]), encoding='utf-8')
            ledger = Ledger(path)
            self.assertEqual(ledger.attempts[0]['attempt_id'], 'old')
            self.assertFalse(ledger.budget_allows(1, 'USD', next_max_cost=0))
            ledger.record(task='t2', model='m', status='fail')
            self.assertEqual(len(Ledger(path).attempts), 2)

    def test_damaged_row_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.json'
            path.write_text(json.dumps([{'attempt_id': 'x', 'task': 't', 'model': 'm',
                                         'status': 'weird', 'measurement_source': 'unknown'}]),
                            encoding='utf-8')
            with self.assertRaises(ValueError):
                Ledger(path)

    def test_failed_local_review_attempt_is_accounted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = Workflow(root / 'state.json', confirm=lambda shown: shown)
            for stage in ('research', 'direction_review', 'specification'):
                workflow.transition(stage, record=RECORD)
            workflow.revise('review missing artifact')
            workflow.add_task('review', code_mode='syntax', acceptance='syntax')
            for stage in ('specification_qa', 'awaiting_confirmation'):
                workflow.transition(stage, record=RECORD)
            workflow.approve()
            ledger = Ledger()
            result = execute_review(workflow, 'review', root=root, artifacts=['missing.py'],
                                    ledger=ledger)
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(len(ledger.attempts), 1)
            row = ledger.attempts[0]
            self.assertEqual(row['status'], 'blocked')
            self.assertEqual(row['operation'], 'syntax_check')
            self.assertEqual(row['provider'], 'local')
            self.assertIsNone(row['cost'])
            self.assertEqual(row['measurement_source'], 'unknown')


if __name__ == '__main__':
    unittest.main()
