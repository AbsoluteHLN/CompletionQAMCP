import tempfile,unittest
from pathlib import Path
from completion_plugin.workflow import Workflow
from completion_plugin.usage import Ledger
class UnicodeTests(unittest.TestCase):
 def test_utf8_state_and_usage(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);w=Workflow(p/'状态.json');w.revise('论文修改 🏛️');self.assertIn('论文', (p/'状态.json').read_bytes().decode('utf-8'));self.assertEqual(Workflow(p/'状态.json').data['spec'],'论文修改 🏛️')
   l=Ledger(p/'消耗.json');l.record(task='文字润色',model='未知',status='blocked');self.assertEqual(Ledger(p/'消耗.json').attempts[0]['task'],'文字润色')
