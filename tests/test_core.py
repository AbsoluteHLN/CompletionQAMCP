import json
import tempfile
import unittest
from pathlib import Path
from completion_qa.core import Engine
from completion_qa.editorial import diagnose, DisabledReviewer
from completion_qa.host import simulate_stop

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'ok.py').write_text('x = 1\n')
        self.e = Engine(self.root)
    def tearDown(self): self.tmp.cleanup()
    def plan(self, required=None, files=None):
        return self.e.plan(files or ['ok.py'], required or ['code'])['plan_id']
    def test_actual_command_and_idempotence(self):
        p = self.plan()
        self.assertEqual(self.e.gate(p)['checks']['code'], 'not_run')
        evidence = self.e.run(p, 'code')
        self.assertEqual(evidence['exit_code'], 0)
        self.assertTrue(evidence['command'])
        self.assertEqual(evidence['status'], 'pass')
        self.assertEqual(len(evidence['artifact_hashes']['ok.py']), 64)
        self.assertEqual(self.e.gate(p), self.e.gate(p))
        self.assertTrue(self.e.gate(p)['allow_completion'])
    def test_invalidated_after_edit(self):
        p = self.plan(); self.e.run(p, 'code')
        (self.root/'ok.py').write_text('x = 2\n')
        self.assertTrue(self.e.gate(p)['stale'])
        self.assertFalse(self.e.gate(p)['allow_completion'])
        self.assertEqual(self.e.run(p, 'code')['status'], 'blocked')
    def test_syntax_failure(self):
        (self.root/'ok.py').write_text('x = (')
        p = self.plan()
        self.assertEqual(self.e.run(p, 'code')['status'], 'fail')
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_missing_adapters_are_blocked(self):
        p = self.plan(['browser','native','model'])
        for c in ['browser','native','model']:
            e = self.e.run(p,c)
            self.assertEqual(e['status'],'blocked'); self.assertIsNone(e['exit_code'])
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_path_and_command_injection(self):
        for path in ['/etc/passwd','../oops','ok.py; touch /tmp/qa-injected']:
            with self.assertRaises((ValueError,FileNotFoundError)):
                self.plan(files=[path])
        (self.root/'outside').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): self.plan(files=['outside'])
        p = self.plan()
        with self.assertRaises(ValueError): self.e.run(p,'code','echo injected')
        with self.assertRaises(ValueError): self.e.run(p,'native')
    def test_never_executes_reviewed_code(self):
        marker = self.root/'executed'
        (self.root/'ok.py').write_text(f'open({str(marker)!r}, "w").write("oops")')
        p = self.plan(); self.assertEqual(self.e.run(p,'code')['status'],'pass')
        self.assertFalse(marker.exists())
    def test_recursion_and_fail_closed(self):
        p = self.plan(); self.e.run(p,'code')
        self.assertFalse(self.e.gate(p,'completion_qa')['allow_completion'])
        self.assertEqual(simulate_stop(lambda: self.e.gate(p)), {})
        for kwargs in [{'stop_hook_active': True},{'attempt': 2}]:
            self.assertEqual(simulate_stop(lambda: self.e.gate(p),**kwargs)['decision'],'block')
        self.assertEqual(simulate_stop(lambda: 1/0)['decision'],'block')
        self.assertEqual(simulate_stop(lambda: {'allow_completion':True,'status':'pass'})['decision'],'block')
    def test_text_patch_not_applied(self):
        text = '值得注意的是，结果可能改善10%，见[1]。'
        for profile in ['short_reply','academic','technical_report']:
            r = diagnose(text,profile)
            self.assertFalse(r['applied']); self.assertTrue(r['patch'])
            self.assertIn('10%',r['proposed_text']); self.assertIn('[1]',r['proposed_text'])
        self.assertEqual(DisabledReviewer().review(text,'academic')['status'],'blocked')
        with self.assertRaises(ValueError): diagnose(text,'unknown')
    def test_quoted_and_code_text_preserved(self):
        for text in ['作者原话：“\n值得注意的是，结果无统计学意义。\n”', 's = """\n值得注意的是，\n"""', '~~~~\n```\n值得注意的是，\n~~~~', '“值得注意的是，引用原文。”', '```\n值得注意的是，代码原文\n```', '值为 `值得注意的是，`']:
            self.assertEqual(diagnose(text,"academic")["proposed_text"],text)
    def test_empty_plan_cannot_pass(self):
        with self.assertRaises(ValueError): self.e.plan(['ok.py'],[])
    def test_deleted_artifact(self):
        p = self.plan(); self.e.run(p,'code'); (self.root/'ok.py').unlink()
        self.assertFalse(self.e.gate(p)['allow_completion'])

if __name__ == '__main__': unittest.main()
