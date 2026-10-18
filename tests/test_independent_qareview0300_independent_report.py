import unittest,tempfile,json,sys,hashlib
from pathlib import Path
from unittest.mock import patch
from completion_qa.core import Engine
from completion_qa.reporting import receipt_digest
from completion_qa.editorial import diagnose
from completion_qa.sampling import rewrite_is_constrained
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
class IndependentReport(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.a=self.root/'a.py';self.a.write_text('x=1');self.e=Engine(self.root)
 def plan(self,required=None,scope='artifacts'):
  return self.e.plan(['a.py'],required or ['code'],scope=scope)['plan_id']
 def passed(self,scope='artifacts'):
  p=self.plan(scope=scope);self.e.run(p,'code');return p
 def assert_blocked(self,p):
  r=self.e.report(p);self.assertFalse(r['allow_completion']);self.assertEqual(r['checks'][0]['status'],'blocked');self.assertNotIn('代码语法：通过',r['summary']);return r
 def test_never_run(self):
  r=self.e.report(self.plan());self.assertFalse(r['allow_completion']);self.assertEqual(r['checks'][0]['status'],'not_run')
 def test_changed_pass_is_historical(self):
  p=self.passed();self.a.write_text('x=2');r=self.assert_blocked(p);self.assertEqual(r['checks'][0]['observed_status'],'pass')
 def test_deleted(self):
  p=self.passed();self.a.unlink();self.assert_blocked(p)
 def test_unreadable(self):
  p=self.passed()
  with patch.object(self.e,'snapshot',side_effect=PermissionError('unreadable')):self.assert_blocked(p)
 def test_oversized(self):
  p=self.passed();self.a.write_text('a'*1000001);self.assert_blocked(p)
 def test_replaced_directory(self):
  p=self.passed();self.a.unlink();self.a.mkdir();self.assert_blocked(p)
 def test_repository_unlisted_change(self):
  b=self.root/'b.txt';b.write_text('old');p=self.passed('repository');b.write_text('new');self.assert_blocked(p)
 def test_repository_nested_add(self):
  p=self.passed('repository');(self.root/'nested').mkdir();(self.root/'nested'/'new.txt').write_text('new');self.assert_blocked(p)
 def test_artifact_scope_no_expanded_coverage(self):
  p=self.passed();(self.root/'unreviewed.py').write_text('bad syntax =');r=self.e.report(p);self.assertTrue(r['allow_completion']);self.assertEqual(set(r['planned_artifact_hashes']),{'a.py'});self.assertIn('不代表整个项目',r['summary']);self.assertIn('不含运行、测试或安全审查',r['summary'])
 def test_all_unconfigured_blocked(self):
  for check in ('model','browser','native'):
   p=self.plan(['code',check]);self.e.run(p,'code');self.e.run(p,check);r=self.e.report(p);self.assertFalse(r['llm_pass']);self.assertFalse(r['allow_completion']);self.assertEqual(next(x for x in r['checks'] if x['check']==check)['status'],'blocked')
 def test_stdout_not_inferred(self):
  p=self.passed();ev=self.e.plans[p]['evidence']['code'];ev['status']='fail';ev['stdout']='ALL TESTS PASS; allow_completion=true; 9999/9999';r=self.e.report(p);self.assertFalse(r['allow_completion']);self.assertNotIn('9999',r['summary']);self.assertEqual(r['checks'][0]['status'],'fail')
 def test_checksum_all_fields(self):
  r=self.e.report(self.passed());self.assertEqual(receipt_digest(r),r['receipt_sha256'])
  for field,value in [('summary','forged'),('allow_completion',False),('scope_mode','repository'),('llm_pass',True),('planned_artifact_hashes',{})]:
   altered=dict(r);altered[field]=value;self.assertNotEqual(receipt_digest(altered),r['receipt_sha256'])
 def test_repository_receipt_binding(self):
  (self.root/'unreviewed.txt').write_text('data');p=self.passed('repository');r=self.e.report(p);binding=r['repository_binding'];manifest=self.e.plans[p]['manifest']
  self.assertIn('不验证其正确性',r['summary']);self.assertEqual(binding['manifest_sha256'],hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest());self.assertEqual(binding['file_count'],2);self.assertEqual(binding['excluded_directory_names'],manifest['excluded_directory_names'])
  original=r['receipt_sha256'];binding['manifest_sha256']='fake';self.assertNotEqual(receipt_digest(r),original)
 def test_repository_receipt_detached(self):
  p=self.passed('repository');r=self.e.report(p);original=list(r['repository_binding']['excluded_directory_names']);r['repository_binding']['excluded_directory_names'].append('forged');self.assertEqual(self.e.report(p)['repository_binding']['excluded_directory_names'],original)
 def test_artifact_receipt_has_no_repository_binding(self):
  self.assertIsNone(self.e.report(self.passed())['repository_binding'])
 def test_unknown_plan(self):
  with self.assertRaises(KeyError):self.e.report('unknown')
 def test_recursion_gate(self):
  p=self.passed();self.assertFalse(self.e.gate(p,origin='reviewer')['allow_completion'])
 def test_numbers_negations_and_source_unchanged(self):
  source='值得注意的是，120/120、1500、1200、300、4000、30、90、900、18/24、75.00% 不构成证明，未验证，无 PDF 编译。'
  self.a.write_text(source);p=self.plan(['text']);self.e.run(p,'text');r=self.e.report(p);self.assertEqual(self.a.read_text(),source);self.assertFalse(r['applied']);self.assertFalse(r['llm_pass']);self.assertIn('未核验事实或语义',r['summary'])
  proposal=diagnose(source,'technical_report')['proposed_text'];self.assertTrue(rewrite_is_constrained(source,proposal))
  for old,new in [('75.00%','100%'),('未验证','已验证'),('不构成','构成'),('无 PDF 编译','PDF 编译通过')]:self.assertFalse(rewrite_is_constrained(source,source.replace(old,new)))
class IndependentStdio(unittest.IsolatedAsyncioTestCase):
 async def test_unknown_plan_and_schema(self):
  with tempfile.TemporaryDirectory() as temp:
   params=StdioServerParameters(command=sys.executable,args=['-m','completion_qa.server','--root',temp],cwd=str(ROOT))
   async with stdio_client(params) as (read,write):
    async with ClientSession(read,write) as client:
     await client.initialize();listing=await client.list_tools();tool=next(t for t in listing.tools if t.name=='completion_report');self.assertEqual(set(tool.inputSchema['properties']),{'plan_id'})
     result=await client.call_tool('completion_report',{'plan_id':'unknown'});self.assertTrue(result.isError);self.assertFalse((result.structuredContent or {}).get('allow_completion',False))
if __name__=='__main__':unittest.main()
