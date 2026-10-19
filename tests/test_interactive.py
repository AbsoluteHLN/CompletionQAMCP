import unittest
import tempfile
from pathlib import Path
from completion_plugin.interactive import run,resume
class InteractiveTests(unittest.TestCase):
 def test_operator_fixture_accept(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a.py').write_text('x=1');answers=iter(['Check syntax','yes','https://docs.python.org','acknowledge','local','APPROVE 2'])
   result=run(state=p/'state',root=p,artifacts=['a.py'],read=lambda _:next(answers),write=lambda _:None,terminal=True)
   self.assertEqual(result['status'],'pass')
 def test_operator_fixture_reject(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);answers=iter(['Check syntax','yes','https://docs.python.org','acknowledge','local','NO'])
   result=run(state=p/'state',root=p,artifacts=['missing.py'],read=lambda _:next(answers),write=lambda _:None,terminal=True)
   self.assertEqual(result['status'],'cancelled')
 def test_no_pipe_approval(self):
  with self.assertRaises(ValueError):run(state='x',root='.',artifacts=['x'],terminal=False)

 def test_cancel_and_resume(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a.py').write_text('x=1');answers=iter(['Check syntax','yes','https://docs.python.org','acknowledge','local','NO'])
   self.assertEqual(run(state=p/'state',root=p,artifacts=['a.py'],read=lambda _:next(answers),write=lambda _:None,terminal=True)['status'],'cancelled')
   self.assertEqual(resume(p/'state',read=lambda _:'APPROVE 2',write=lambda _:None,terminal=True)['status'],'pass')
