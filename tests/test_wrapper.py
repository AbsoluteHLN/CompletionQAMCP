import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class WrapperTests(unittest.TestCase):
    def invoke(self, root, payload, check='code', artifact='ok.py'):
        result=subprocess.run([sys.executable,'-m','completion_qa.stop_wrapper','--root',root,'--artifact',artifact,'--check',check],input=payload,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0)
        return json.loads(result.stdout)
    def test_command_protocol_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,'ok.py').write_text('x=1')
            good=json.dumps({'hook_event_name':'Stop','stop_hook_active':False})
            self.assertEqual(self.invoke(root,good),{})
            for bad in ['null','[]','{broken','{}',json.dumps({'hook_event_name':'Stop','stop_hook_active':'false'})]:
                self.assertEqual(self.invoke(root,bad)['decision'],'block')
            self.assertEqual(self.invoke(root,good,'native')['decision'],'block')
            self.assertEqual(self.invoke(root,good,artifact='missing.py')['decision'],'block')
            self.assertEqual(self.invoke(root,good,artifact='../escape')['decision'],'block')
            self.assertEqual(self.invoke(root,json.dumps({'hook_event_name':'Stop','stop_hook_active':True}))['decision'],'block')
            Path(root,'ok.py').write_text('x=(')
            self.assertEqual(self.invoke(root,good)['decision'],'block')
