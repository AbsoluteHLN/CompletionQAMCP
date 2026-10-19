import tempfile
import unittest
from pathlib import Path
from completion_plugin.workflow import Workflow
from completion_plugin.evidence import Review
from completion_plugin.usage import Ledger, Supervisor
class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def ready(self):
  w=Workflow(self.root/'state.json',confirm=lambda shown:shown)
  w.transition('research',record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'});w.transition('direction_review',record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'});w.transition('specification',record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'});w.revise('goal v1');w.add_task('code',writes=['src'],code_mode='syntax',acceptance='syntax');w.transition('specification_qa',record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'});w.transition('awaiting_confirmation',record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'});return w
 def test_unapproved(self):
  w=self.ready()
  with self.assertRaises(ValueError):w.start('code')
 def test_full_restart(self):
  w=self.ready();w.approve();w.start('code');w._verifiers['code']=lambda:True;w.finish('code',status='pass',result={'review':{'revision':w.data['revision'],'allow_completion':True,'code_mode':'syntax','checks':{'code':'pass'}}});w.complete();self.assertEqual(Workflow(w.path).data['state'],'complete')
 def test_revision(self):
  w=self.ready();w.approve();w.revise('v2')
  with self.assertRaises(ValueError):w.start('code')
 def test_boolean(self):
  w=self.ready();w.confirm=lambda s:True
  with self.assertRaises(ValueError):w.approve()
 def test_failed(self):
  w=self.ready();w.approve();w.start('code');w.finish('code',status='fail',result='bad')
  with self.assertRaises(ValueError):w.complete()
 def test_conflict(self):
  w=self.ready();other=Workflow(w.path);w.approve()
  with self.assertRaises(ValueError):other.revise('bad')
 def test_content(self):
  p=self.root/'a.py';p.write_text('x=1');r=Review(self.root,['a.py'],1);r.syntax();self.assertTrue(r.gate(['code'])['allow_completion']);p.write_text('x=2');self.assertFalse(r.gate(['code'])['allow_completion'])
 def test_missing(self):
  (self.root/'a.py').write_text('x=1');r=Review(self.root,['a.py'],1);r.syntax();self.assertFalse(r.gate(['code','native'])['allow_completion'])
 def test_usage(self):
  l=Ledger();r=l.record(task='x',model='unknown',status='fail');self.assertIsNone(r['cost']);self.assertFalse(l.budget_allows(1,'USD'))
 def test_supervision(self):
  s=Supervisor();self.assertEqual(s.observe('x',kind='active_build',detail='PID alive')['action'],'wait');s.observe('x',kind='blocker',detail='missing');self.assertEqual(s.observe('x',kind='blocker',detail='missing')['action'],'pause')
