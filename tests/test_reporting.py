import json
import tempfile
import unittest
from pathlib import Path
from completion_qa.core import Engine
from completion_qa.reporting import receipt_digest
from completion_qa.editorial import diagnose
from completion_qa.sampling import rewrite_is_constrained

class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); (self.root/'a.py').write_text('a=1')
        self.engine=Engine(self.root)
    def plan(self, checks=['code'], scope='artifacts'):
        return self.engine.plan(['a.py'],checks,scope=scope)['plan_id']
    def test_not_run_not_pass(self):
        r=self.engine.report(self.plan())
        self.assertFalse(r['allow_completion']); self.assertEqual(r['checks'][0]['status'],'not_run')
    def test_syntax_only_summary(self):
        p=self.plan(); e=self.engine.run(p,'code'); r=self.engine.report(p)
        self.assertTrue(r['allow_completion']); self.assertFalse(r['llm_pass'])
        self.assertEqual(r['checks'][0]['evidence_id'],e['id']); self.assertIn('不含运行',r['summary'])
        self.assertEqual(r['receipt_sha256'],receipt_digest(r))
        self.assertNotIn(str(self.root),json.dumps(r)); self.assertNotIn('stdout',r)
    def test_model_blocks_and_unrequested_stays_unverified(self):
        p=self.plan(['code','model']); self.engine.run(p,'code'); self.engine.run(p,'model'); r=self.engine.report(p)
        self.assertFalse(r['allow_completion']); self.assertIn('未配置模型',r['summary'])
        self.assertEqual(r['checks'][3]['status'],'not_required')
    def test_changed_invalidates_observed_pass(self):
        p=self.plan(); self.engine.run(p,'code'); (self.root/'a.py').write_text('a=2');r=self.engine.report(p)
        self.assertFalse(r['source_valid']); self.assertEqual(r['checks'][0]['observed_status'],'pass')
        self.assertEqual(r['checks'][0]['status'],'blocked'); self.assertNotIn('代码语法：通过',r['summary'])
    def test_deleted_artifact_blocks(self):
        p=self.plan(); self.engine.run(p,'code'); (self.root/'a.py').unlink();r=self.engine.report(p)
        self.assertFalse(r['source_valid']);self.assertFalse(r['allow_completion'])
    def test_added_repository_file_blocks(self):
        p=self.plan(scope='repository');self.engine.run(p,'code');(self.root/'new.txt').write_text('new')
        self.assertFalse(self.engine.report(p)['source_valid'])
    def test_failure_preserved(self):
        (self.root/'a.py').write_text('=');p=self.plan();self.engine.run(p,'code');r=self.engine.report(p)
        self.assertEqual(r['checks'][0]['status'],'fail');self.assertIn('代码语法：失败',r['summary'])
    def test_unknown_plan_error(self):
        with self.assertRaises(KeyError):self.engine.report('unknown')
    def test_receipt_not_mutable_gate(self):
        p=self.plan();self.engine.run(p,'code');r=self.engine.report(p)
        r['planned_artifact_hashes']['a.py']='fake';r['checks'][0]['status']='fail'
        self.assertTrue(self.engine.report(p)['allow_completion'])
        self.assertNotEqual(r['receipt_sha256'],receipt_digest(r))
    def test_snapshot_prose_protected(self):
        source=(Path(__file__).parents[1]/'fixtures'/'synthetic_stage.txt').read_text()
        proposed=diagnose(source,'technical_report')['proposed_text']
        self.assertTrue(rewrite_is_constrained(source,proposed))
        for token in ['120/120','1500','1200','300','4000','30','90','900','18/24','75.00%','不构成','未验证','无 PDF 编译']:
            self.assertEqual(source.count(token),proposed.count(token))
        for a,b in [('未验证','已验证'),('120/120','121/121'),('无 PDF 编译','PDF 编译通过'),('不构成','构成')]:
            self.assertFalse(rewrite_is_constrained(source,source.replace(a,b)))

    def test_repository_receipt_binding(self):
        p=self.plan(scope='repository');r=self.engine.report(p)
        self.assertEqual(r['repository_binding']['file_count'],1)
        self.assertEqual(r['repository_binding']['excluded_directory_names'],['.git','.pytest_cache','__pycache__'])
        self.assertEqual(len(r['repository_binding']['manifest_sha256']),64)
        self.assertIsNone(self.engine.report(self.plan())['repository_binding'])
