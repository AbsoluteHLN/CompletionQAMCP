import tempfile, unittest
from pathlib import Path
from completion_qa.core import Engine

class IntegrityTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name); (self.root/'a.py').write_text('x=1'); self.e=Engine(self.root)
 def tearDown(self): self.t.cleanup()
 def test_failed_evidence_return_cannot_forge_pass(self):
  (self.root/'a.py').write_text('x=('); p=self.e.plan(['a.py'],['code'])['plan_id']; r=self.e.run(p,'code'); r['status']='pass'; self.assertFalse(self.e.gate(p)['allow_completion'])
 def test_missing_adapter_return_cannot_forge_pass(self):
  p=self.e.plan(['a.py'],['model'])['plan_id']; self.e.run(p,'model')['status']='pass'; self.assertFalse(self.e.gate(p)['allow_completion'])
 def test_gate_cache_return_cannot_forge_pass(self):
  p=self.e.plan(['a.py'],['code'])['plan_id']; r=self.e.gate(p); r['allow_completion']=True; r['status']='pass'; self.assertFalse(self.e.gate(p)['allow_completion'])
 def test_plan_return_required_is_detached(self):
  r=self.e.plan(['a.py'],['code','model']); r['required'].remove('model'); self.e.run(r['plan_id'],'code'); self.assertFalse(self.e.gate(r['plan_id'])['allow_completion'])
 def test_plan_return_snapshot_is_detached(self):
  r=self.e.plan(['a.py'],['code']); old=r['artifact_hashes'].copy(); r['artifact_hashes']['a.py']='tampered'; self.assertEqual(self.e.plans[r['plan_id']]['snapshot'],old)
 def test_evidence_nested_maps_are_detached(self):
  p=self.e.plan(['a.py'],['code'])['plan_id']; r=self.e.run(p,'code'); r['artifact_hashes']['a.py']='bad'; self.assertTrue(self.e.gate(p)['allow_completion'])
 def test_gate_nested_checks_are_detached(self):
  p=self.e.plan(['a.py'],['model'])['plan_id']; r=self.e.gate(p); r['checks']['model']='pass'; self.assertEqual(self.e.gate(p)['checks']['model'],'not_run')
