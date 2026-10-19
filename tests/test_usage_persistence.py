import unittest,tempfile
from pathlib import Path
from completion_plugin.usage import Ledger
class LedgerTests(unittest.TestCase):
 def test_recover_unknown_and_duplicate(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'usage';l=Ledger(p);l.record(task='a',model='unknown',status='fail',attempt_id='once')
   restored=Ledger(p);self.assertIsNone(restored.attempts[0]['cost']);self.assertFalse(restored.budget_allows(1,'USD'))
   with self.assertRaises(ValueError):restored.record(task='a',model='unknown',status='fail',attempt_id='once')
 def test_stale_writer(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'usage';a,b=Ledger(p),Ledger(p);a.record(task='a',model='unknown',status='fail')
   with self.assertRaises(ValueError):b.record(task='b',model='unknown',status='fail')
