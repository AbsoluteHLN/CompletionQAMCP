import tempfile,unittest,types
from pathlib import Path
from unittest.mock import patch
from completion_plugin import locking
class LockTests(unittest.TestCase):
 def test_posix_exclusion(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'lock'
   with locking.writer_lock(p):
    with self.assertRaises(TimeoutError):
     with locking.writer_lock(p,timeout=.01):pass
 def test_windows_api_contract_simulated(self):
  calls=[];fake=types.SimpleNamespace(LK_NBLCK=2,LK_UNLCK=0,locking=lambda fd,mode,count:calls.append((mode,count)))
  with tempfile.TemporaryDirectory() as d,patch.object(locking,'os',types.SimpleNamespace(name='nt')),patch.dict('sys.modules',{'msvcrt':fake}):
   with locking.writer_lock(Path(d)/'lock'):pass
  self.assertEqual(calls,[(2,1),(0,1)])
