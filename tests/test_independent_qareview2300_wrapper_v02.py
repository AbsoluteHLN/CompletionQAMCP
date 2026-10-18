import json, subprocess, sys, tempfile, unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]
class WrapperNegative(unittest.TestCase):
    def call(self,root,payload,extra=()):
        r=subprocess.run([sys.executable,'-m','completion_qa.stop_wrapper','--root',str(root),'--artifact','a.py','--check','code',*extra],input=payload,text=True,capture_output=True,cwd=SOURCE,timeout=15)
        self.assertEqual(r.returncode,0);return json.loads(r.stdout)
    def test_real_cli_recursive_always_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'a.py').write_text('x=1')
            self.assertEqual(self.call(t,json.dumps({'hook_event_name':'Stop','stop_hook_active':True}))['decision'],'block')
    def test_real_cli_malformed_inputs_block(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'a.py').write_text('x=1')
            for payload in ['','[]','null','{','{"hook_event_name":"Stop","stop_hook_active":1}','{"hook_event_name":"Start","stop_hook_active":false}']:
                with self.subTest(payload=payload):self.assertEqual(self.call(t,payload)['decision'],'block')
    def test_real_cli_model_missing_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'a.py').write_text('x=1')
            self.assertEqual(self.call(t,'{"hook_event_name":"Stop","stop_hook_active":false}',('--check','model'))['decision'],'block')
    def test_real_cli_invalid_scope_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'a.py').write_text('x=1')
            self.assertEqual(self.call(t,'{"hook_event_name":"Stop","stop_hook_active":false}',('--scope','bad'))['decision'],'block')
    def test_real_cli_repo_symlink_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'a.py').write_text('x=1');Path(t,'link').symlink_to('/etc/hosts')
            self.assertEqual(self.call(t,'{"hook_event_name":"Stop","stop_hook_active":false}',('--scope','repository'))['decision'],'block')
