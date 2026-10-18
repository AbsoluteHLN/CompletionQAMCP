import tempfile
import unittest
from pathlib import Path
from completion_qa.core import Engine


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'main.py').write_text('x=1')
        (self.root/'extra.txt').write_text('baseline')
        self.engine = Engine(self.root)

    def plan(self):
        p = self.engine.plan(['main.py'], ['code'], scope='repository')['plan_id']
        self.assertEqual('pass', self.engine.run(p, 'code')['status'])
        self.assertTrue(self.engine.gate(p)['allow_completion'])
        return p

    def test_add_untracked(self):
        p = self.plan()
        (self.root/'new.py').write_text('broken syntax here')
        self.assertFalse(self.engine.gate(p)['allow_completion'])
        self.assertEqual('blocked', self.engine.run(p,'code')['status'])

    def test_delete_unlisted(self):
        p = self.plan()
        (self.root/'extra.txt').unlink()
        self.assertTrue(self.engine.gate(p)['stale'])

    def test_modify_unlisted(self):
        p = self.plan()
        (self.root/'extra.txt').write_text('new')
        self.assertTrue(self.engine.gate(p)['stale'])

    def test_symlink_rejected(self):
        (self.root/'link').symlink_to('main.py')
        with self.assertRaises(ValueError): self.plan()

    def test_exclusions_declared(self):
        p = self.plan()
        (self.root/'.git').mkdir()
        (self.root/'.git'/'HEAD').write_text('metadata')
        self.assertTrue(self.engine.gate(p)['allow_completion'])

    def test_deleted_artifact_run_blocked(self):
        p = self.plan()
        (self.root/'main.py').unlink()
        self.assertEqual('blocked',self.engine.run(p,'code')['status'])
        self.assertFalse(self.engine.gate(p)['allow_completion'])

    def test_caller_list_not_mutable(self):
        artifacts, required = ['main.py'], ['code']
        p=self.engine.plan(artifacts,required)['plan_id']
        artifacts.clear();required.clear()
        self.assertFalse(self.engine.gate(p)['allow_completion'])
