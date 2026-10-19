import tempfile
import unittest
from pathlib import Path
from completion_plugin.evidence import Review
class ExecutionTests(unittest.TestCase):
 def test_trusted_true_execution(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'main.py').write_text('x=1');(p/'tests').mkdir();(p/'tests/test_one.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self):self.assertEqual(1,1)\n')
   r=Review(p,['main.py'],1);self.assertEqual(r.project_tests()['status'],'blocked');self.assertEqual(r.project_tests(explicitly_trusted=True)['status'],'pass')
 def test_empty_fails(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'main.py').write_text('x=1');(p/'tests').mkdir();r=Review(p,['main.py'],1);self.assertEqual(r.project_tests(explicitly_trusted=True)['status'],'fail')
