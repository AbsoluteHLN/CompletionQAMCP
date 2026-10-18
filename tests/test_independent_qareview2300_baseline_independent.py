import asyncio, json, os, sys, tempfile, unittest
from pathlib import Path
from completion_qa.core import Engine
from completion_qa.editorial import diagnose
from completion_qa.host import simulate_stop
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class NegativeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.file=self.root/'safe.py';self.file.write_text('x = 1\n');self.e=Engine(self.root)
 def tearDown(self): self.tmp.cleanup()
 def p(self, checks=['code'], files=['safe.py']):return self.e.plan(files,checks)['plan_id']
 def test_unrun_is_blocked(self): self.assertFalse(self.e.gate(self.p())['allow_completion'])
 def test_unknown_plan_never_passes(self):
  with self.assertRaises(KeyError): self.e.gate('invented')
 def test_modified_deleted_artifact(self):
  p=self.p();self.e.run(p,'code');self.file.write_text('x = 2');self.assertTrue(self.e.gate(p)['stale']);self.assertFalse(self.e.gate(p)['allow_completion']);self.file.unlink();self.assertFalse(self.e.gate(p)['allow_completion'])
 def test_symlink_outside_root(self):
  (self.root/'external.py').symlink_to('/etc/passwd')
  with self.assertRaises(ValueError):self.p(files=['external.py'])
 def test_symlink_swap_before_gate(self):
  p=self.p();self.e.run(p,'code');self.file.unlink();self.file.symlink_to('/etc/passwd');self.assertFalse(self.e.gate(p)['allow_completion'])
 def test_shell_filename_is_literal_and_source_is_not_executed(self):
  name='source;touch INJECTED.py'; (self.root/name).write_text('from pathlib import Path\nPath("EXECUTED").touch()\n')
  p=self.p(files=[name]);self.assertEqual(self.e.run(p,'code')['status'],'pass');self.assertFalse((self.root/'INJECTED.py').exists());self.assertFalse((self.root/'EXECUTED').exists())
 def test_command_injection_rejected(self):
  p=self.p()
  for command in ['sh','parse_sources;touch INJECTED','parse_sources &','$(touch INJECTED)','parse_sources\nsh']:
   with self.assertRaises(ValueError):self.e.run(p,'code',command)
 def test_syntax_fail_and_unsupported_extension(self):
  self.file.write_text('def f(:');p=self.p();self.assertEqual(self.e.run(p,'code')['status'],'fail');self.assertFalse(self.e.gate(p)['allow_completion']);(self.root/'a.js').write_text('const x=1;');p=self.p(files=['a.js']);self.assertEqual(self.e.run(p,'code')['status'],'blocked')
 def test_missing_adapter_not_run_then_blocked(self):
  p=self.p(['browser','native','model']);self.assertEqual(set(self.e.gate(p)['checks'].values()),{'not_run'})
  for c in ['browser','native','model']:self.assertEqual(self.e.run(p,c)['status'],'blocked')
  self.assertFalse(self.e.gate(p)['allow_completion'])
 def test_untracked_not_in_manifest_outside_claim(self):
  p=self.p();self.e.run(p,'code');(self.root/'new.py').write_text('syntax = (');gate=self.e.gate(p);self.assertTrue(gate['allow_completion']);self.assertIn('never whole-project',gate['scope'])
 def test_required_untracked_file_included(self):
  (self.root/'new.py').write_text('syntax = (');p=self.p(files=['safe.py','new.py']);self.assertEqual(self.e.run(p,'code')['status'],'fail')
 def test_recursion_offline_invalid(self):
  p=self.p();self.e.run(p,'code');self.assertFalse(self.e.gate(p,'worker')['allow_completion'])
  for result in [None,{}, {'allow_completion':True,'status':'pass'}, {'allow_completion':1,'status':'pass','evidence_refs':['x']}]:self.assertEqual(simulate_stop(lambda:result)['decision'],'block')
  self.assertEqual(simulate_stop(lambda:1/0)['decision'],'block');self.assertEqual(simulate_stop(lambda:self.e.gate(p),stop_hook_active=True)['decision'],'block');self.assertEqual(simulate_stop(lambda:self.e.gate(p),attempt=2)['decision'],'block')
 def test_numeric_negation_causality_and_references_preserved(self):
  text='值得注意的是，10%不意味着不存在；A与B相关，不能据此认定A导致B。[1] https://example.org/x?a=12'
  r=diagnose(text,'academic');self.assertEqual(r['proposed_text'],text.removeprefix('值得注意的是，'));self.assertFalse(r['applied'])
 def test_quote_protection_observation(self):
  text='原文引语：“值得注意的是，结果不显著（p=0.12）。”\n代码：s = "值得注意的是，"'
  r=diagnose(text,'academic');self.assertEqual(r['proposed_text'],text);self.assertEqual(r['patch'],'')
  samples = ['作者原话：“\n值得注意的是，结果无统计学意义。\n”', 's = """\n值得注意的是，\n"""', '~~~~\n```\n值得注意的是，\n~~~~']
  for sample in samples: self.assertEqual(diagnose(sample,'academic')['proposed_text'],sample)

class StdioNegative(unittest.IsolatedAsyncioTestCase):
 async def test_real_stdio_failure_contract(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'x.py').write_text('x=(')
   params=StdioServerParameters(command=sys.executable,args=['-m','completion_qa.server','--root',temp],cwd=str(Path(__file__).resolve().parents[1]))
   async with stdio_client(params) as (r,w):
    async with ClientSession(r,w) as c:
     await c.initialize()
     async def call(name,args):
      r=await c.call_tool(name,args);self.assertFalse(r.isError);return r.structuredContent or json.loads(r.content[0].text)
     p=await call('review_plan',{'artifacts':['x.py'],'required':['code','native','model']});pid=p['plan_id']
     ev=await call('run_check',{'plan_id':pid,'check':'code'});self.assertEqual(ev['status'],'fail')
     for check in ['native','model']:self.assertEqual((await call('run_check',{'plan_id':pid,'check':check}))['status'],'blocked')
     self.assertFalse((await call('completion_gate',{'plan_id':pid}))['allow_completion'])
     for name,args in [('completion_gate',{'plan_id':'invented'}),('run_check',{'plan_id':pid,'check':'code','command_id':'sh -c true'}),('review_plan',{'artifacts':['/etc/passwd'],'required':['code']}),('review_plan',{'artifacts':['x.py'],'required':[]})]:self.assertTrue((await c.call_tool(name,args)).isError)
     self.assertFalse((await call('capabilities',{}))['model']['configured'])
if __name__=='__main__':unittest.main(verbosity=2)
