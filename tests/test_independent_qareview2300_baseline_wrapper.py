import json, subprocess, sys, tempfile, unittest
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
class WrapperTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'ok.py').write_text('x=1');self.base=[sys.executable,'-m','completion_qa.stop_wrapper','--root',str(self.root),'--artifact','ok.py']
 def tearDown(self):self.tmp.cleanup()
 def call(self,payload=None,check='code',extra=[]):
  r=subprocess.run(self.base+['--check',check]+extra,input=payload if payload is not None else json.dumps({'hook_event_name':'Stop','stop_hook_active':False}),text=True,capture_output=True,cwd=PROJECT,timeout=15)
  self.assertEqual(r.returncode,0);return json.loads(r.stdout)
 def test_pass_for_valid_syntax_only(self):self.assertEqual(self.call(),{})
 def test_bad_syntax_blocks(self):
  (self.root/'ok.py').write_text('x=(');self.assertEqual(self.call()['decision'],'block')
 def test_adapters_block(self):
  for c in ['native','browser','model']:self.assertEqual(self.call(check=c)['decision'],'block')
 def test_corrupt_or_wrong_event_blocks(self):
  for p in ['garbage','{}','[]','null',json.dumps({'hook_event_name':'Stop','stop_hook_active':'false'}),json.dumps({'hook_event_name':'Stop','stop_hook_active':True}),json.dumps({'hook_event_name':'SubagentStop','stop_hook_active':False})]:self.assertEqual(self.call(p)['decision'],'block')
 def test_missing_root_artifact_invalid_config_blocks(self):
  for extra in [['--root',str(self.root/'missing')],['--artifact','missing.py'],['--artifact','/etc/passwd'],['--profile','unsupported'],['--evil']]:self.assertEqual(self.call(extra=extra)['decision'],'block')
if __name__=='__main__':unittest.main(verbosity=2)
