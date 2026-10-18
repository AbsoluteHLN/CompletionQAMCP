import json, sys, tempfile, unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from completion_qa.core import Engine
from completion_qa.manifest import repository_manifest

SOURCE=Path(__file__).resolve().parents[1]
class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'a.py').write_text('x=1\n');self.e=Engine(self.root)
    def start(self):
        p=self.e.plan(['a.py'],['code'],scope='repository')['plan_id']
        self.assertEqual(self.e.run(p,'code')['status'],'pass');return p
    def test_nested_untracked(self):
        p=self.start();(self.root/'nested').mkdir();(self.root/'nested'/'x').write_text('new')
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_delete_untracked(self):
        (self.root/'other').write_text('x');p=self.start();(self.root/'other').unlink()
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_same_size_changed_untracked(self):
        (self.root/'other').write_text('x');p=self.start();(self.root/'other').write_text('y')
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_outside_file_symlink(self):
        (self.root/'link').symlink_to('/etc/hosts')
        with self.assertRaises(ValueError): self.start()
    def test_inside_file_symlink(self):
        (self.root/'link').symlink_to(self.root/'a.py')
        with self.assertRaises(ValueError): self.start()
    def test_directory_symlink(self):
        (self.root/'link').symlink_to('/tmp',target_is_directory=True)
        with self.assertRaises(ValueError): self.start()
    def test_symlink_added_after_pass(self):
        p=self.start();(self.root/'link').symlink_to('/etc/hosts')
        self.assertFalse(self.e.gate(p)['allow_completion'])
        self.assertEqual(self.e.run(p,'code')['status'],'blocked')
    def test_unicode_path_included(self):
        (self.root/'中文').write_text('a');p=self.start();(self.root/'中文').write_text('b')
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_exclusions_are_reported(self):
        p=self.e.plan(['a.py'],['code'],scope='repository')
        self.assertEqual(p['repository_manifest']['excluded_directory_names'],['.git','.pytest_cache','__pycache__'])
    def test_excluded_name_as_file_not_ignored(self):
        (self.root/'.git').write_text('gitdir pointer');p=self.start();(self.root/'.git').write_text('changed')
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_gate_not_run(self):
        p=self.e.plan(['a.py'],['code'],scope='repository')['plan_id']
        self.assertFalse(self.e.gate(p)['allow_completion'])

class StdioNegativeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_transport_negative_cases(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'a.py').write_text('x=1')
            params=StdioServerParameters(command=sys.executable,args=['-m','completion_qa.server','--root',d],cwd=str(SOURCE))
            async with stdio_client(params) as (r,w):
                async with ClientSession(r,w) as client:
                    await client.initialize()
                    async def ok(name,args):
                        x=await client.call_tool(name,args);self.assertFalse(x.isError);return x.structuredContent or json.loads(x.content[0].text)
                    async def error(name,args):
                        x=await client.call_tool(name,args);self.assertTrue(x.isError)
                    for path in ['../x','/etc/hosts']:
                        await error('review_plan',{'artifacts':[path],'required':['code'],'scope':'repository'})
                    await error('review_plan',{'artifacts':['a.py'],'required':['code'],'scope':'invalid'})
                    p=await ok('review_plan',{'artifacts':['a.py'],'required':['code'],'scope':'repository'});pid=p['plan_id']
                    await error('completion_gate',{'plan_id':'forged'})
                    await error('run_check',{'plan_id':pid,'check':'code','command_id':'echo injected'})
                    await error('run_check',{'plan_id':pid,'check':'model'})
                    await ok('run_check',{'plan_id':pid,'check':'code'})
                    self.assertTrue((await ok('completion_gate',{'plan_id':pid}))['allow_completion'])
                    self.assertFalse((await ok('completion_gate',{'plan_id':pid,'origin':'recursive'}))['allow_completion'])
                    (root/'untracked.py').write_text('invalid syntax?')
                    self.assertFalse((await ok('completion_gate',{'plan_id':pid}))['allow_completion'])
                    self.assertEqual((await ok('run_check',{'plan_id':pid,'check':'code'}))['status'],'blocked')
                    for check in ['model','native','browser']:
                        p=await ok('review_plan',{'artifacts':['a.py'],'required':[check],'scope':'repository'})
                        self.assertEqual((await ok('run_check',{'plan_id':p['plan_id'],'check':check}))['status'],'blocked')
                        self.assertFalse((await ok('completion_gate',{'plan_id':p['plan_id']}))['allow_completion'])
                    (root/'link').symlink_to('/etc/hosts')
                    await error('review_plan',{'artifacts':['a.py'],'required':['code'],'scope':'repository'})

if __name__=='__main__': unittest.main()
