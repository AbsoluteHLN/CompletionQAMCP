import unittest,tempfile
from pathlib import Path
from completion_plugin.workflow import Workflow
from completion_plugin.runtime import execute_review
from completion_plugin.usage import Ledger
class ModeTests(unittest.TestCase):
 def test_project_tests_cannot_downgrade(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a.py').write_text('x=1');w=Workflow(p/'state',confirm=lambda shown:shown)
   record={'sources':['https://example.org'],'source':'user','choice':'x','status':'pass'}
   for target in ('research','direction_review','specification'):w.transition(target,record=record)
   w.revise('Test project');w.add_task('a',acceptance='run tests',code_mode='project_tests')
   for target in ('specification_qa','awaiting_confirmation'):w.transition(target,record=record)
   w.approve()
   with self.assertRaises(ValueError):execute_review(w,'a',root=p,artifacts=['a.py'],ledger=Ledger(),trusted_tests=False)
   self.assertEqual(w.data['tasks']['a']['status'],'not_run')
 def test_mode_must_be_explicit(self):
  with tempfile.TemporaryDirectory() as d:
   w=Workflow(Path(d)/'state');w.data['state']='specification'
   with self.assertRaises(ValueError):w.add_task('a',acceptance='must test')

 def test_non_boolean_execution_optin_rejected(self):
  for value in ('false',1,[],None):
   with self.assertRaises(ValueError):execute_review(None,'a',root='.',artifacts=[],ledger=Ledger(),trusted_tests=value)
