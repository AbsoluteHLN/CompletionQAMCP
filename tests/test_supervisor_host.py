import unittest
from completion_plugin.usage import Supervisor,Ledger
class SupervisorHostTests(unittest.TestCase):
 def test_absent(self):self.assertEqual(Supervisor().model_check('x')['status'],'blocked')
 def test_cannot_override_pause(self):
  s=Supervisor();s.observe('x',kind='blocker',detail='a');s.observe('x',kind='blocker',detail='a');l=Ledger()
  r=s.model_check('x',authorize=lambda *a:True,reviewer=lambda x:{'action':'continue'},ledger=l)
  self.assertEqual(r['action'],'pause');self.assertIsNone(l.attempts[0]['cost'])
 def test_recursive(self):
  s=Supervisor();s._reviewing=True
  self.assertEqual(s.model_check('x',authorize=lambda *a:True,reviewer=lambda x:{'action':'continue'})['status'],'blocked')
