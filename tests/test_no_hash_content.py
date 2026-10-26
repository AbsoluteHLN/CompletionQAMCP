"""spec-v002 A01/A02 acceptance: no content-fingerprint fields or algorithms in
code or machine output, and direct byte comparison detects equal-size changes,
additions, deletions and renames without any digest."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from completion_plugin import (cli, dsh, editorial, evidence, polishing, profiles,
                               runtime, usage, workflow)
from completion_plugin.evidence import Review, repository_snapshot, snapshot

MODULES = (cli, dsh, editorial, evidence, polishing, profiles, runtime, usage, workflow)
FORBIDDEN_TOKENS = ('hashlib', 'sha256', 'sha1', 'md5', 'digest', 'checksum')
FORBIDDEN_FIELD = re.compile(r'hash|digest|checksum|fingerprint')


class NoFingerprintTests(unittest.TestCase):
    def test_source_has_no_fingerprint_algorithm(self):
        for module in MODULES:
            source = Path(module.__file__).read_text(encoding='utf-8')
            for token in FORBIDDEN_TOKENS:
                self.assertNotIn(token, source, module.__name__ + ' retains ' + token)

    def test_machine_output_has_no_fingerprint_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('x = 1\n')
            review = Review(root, ['a.py'], 1)
            review.syntax()
            gate = review.gate(['code'])
            ledger_row = usage.Ledger().record(task='t', model='m', status='fail')
            dsh_row = dsh.DSHAdapter.usage_attempt(status='fail')
            session = polishing.PolishingSession(polishing.HostBindings(
                authorize=lambda request: request,
                generate=lambda request: {'candidate': 'x = 2\n'},
                execution_kind='mock', generator_identity='generation-context'))
            polished = session.run('x = 1\n', 'technical_document', document_id='doc', revision=1)
            outputs = [gate, ledger_row, dsh_row, polished['attempts'][0],
                       editorial.review('x = 1\n', 'technical_document')]
            for output in outputs:
                for key in output:
                    self.assertFalse(FORBIDDEN_FIELD.search(key), 'output field ' + key)

    def test_gate_reports_versions_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'main.py').write_text('value = 1\n')
            review = Review(root, ['main.py'], 1)
            review.syntax()
            gate = review.gate(['code'])
            self.assertEqual(gate['revision'], 1)
            self.assertTrue(gate['content_current'])
            serialized = json.dumps(gate)
            self.assertNotIn('value = 1', serialized)
            self.assertNotIn('main.py', serialized)


class DirectComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'main.py'
        self.target.write_text('value = 1\n')

    def test_same_size_and_mtime_change_is_detected(self):
        review = Review(self.root, ['main.py'], 1)
        review.syntax()
        original_size = self.target.stat().st_size
        stamp = self.target.stat().st_mtime
        self.target.write_text('value = 2\n')
        os.utime(self.target, (stamp, stamp))
        self.assertEqual(self.target.stat().st_size, original_size)
        self.assertFalse(review.gate(['code'])['allow_completion'])
        self.assertTrue(review.invalidated)

    def test_repeated_snapshots_of_unchanged_content_are_equal(self):
        self.assertEqual(snapshot(self.root, ['main.py']), snapshot(self.root, ['main.py']))

    def test_add_delete_rename_change_repository_snapshot(self):
        before = repository_snapshot(self.root)
        (self.root / 'added.py').write_text('a = 1\n')
        self.assertNotEqual(repository_snapshot(self.root), before)
        (self.root / 'added.py').unlink()
        self.assertEqual(repository_snapshot(self.root), before)
        (self.root / 'renamed.py').write_text('value = 1\n')
        self.target.unlink()
        self.assertNotEqual(repository_snapshot(self.root), before)


if __name__ == '__main__':
    unittest.main()
