import json
import sys
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class StdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'a.json').write_text('{"ok": true}')
            params=StdioServerParameters(command=sys.executable,args=['-m','completion_qa.server','--root',temp],cwd=str(Path(__file__).resolve().parents[1]))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize()
                    listing = await client.list_tools()
                    self.assertEqual({t.name for t in listing.tools},{'capabilities','review_plan','run_check','review_text','completion_gate','completion_report'})
                    async def call(name,args):
                        result = await client.call_tool(name,args)
                        self.assertFalse(result.isError)
                        return result.structuredContent or json.loads(result.content[0].text)
                    caps=await call('capabilities',{})
                    self.assertFalse(caps['native']['configured'])
                    plan=await call('review_plan',{'artifacts':['a.json'],'required':['code']})
                    args={'plan_id':plan['plan_id']}
                    before=await call('completion_gate',args)
                    self.assertFalse(before['allow_completion'])
                    ev=await call('run_check',{**args,'check':'code'})
                    self.assertEqual(ev['status'],'pass')
                    final=await call('completion_gate',args)
                    self.assertTrue(final['allow_completion'])
                    report=await call('completion_report',args)
                    self.assertTrue(report['allow_completion'])
                    self.assertFalse(report['llm_pass'])
                    self.assertIn('不含运行', report['summary'])
                    invalid=await client.call_tool('review_plan',{'artifacts':['../escape'],'required':['code']})
                    self.assertTrue(invalid.isError)
                    invalid_command=await client.call_tool('run_check',{**args,'check':'code','command_id':'sh -c nope'})
                    self.assertTrue(invalid_command.isError)
                    text=await call('review_text',{'text':'值得注意的是，结果仍可能变化。','profile':'academic'})
                    self.assertFalse(text['applied'])

    async def test_repository_scope_over_stdio(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, 'a.py').write_text('x=1')
            params=StdioServerParameters(command=sys.executable,args=['-m','completion_qa.server','--root',temp],cwd=str(Path(__file__).resolve().parents[1]))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize()
                    async def call(name,args):
                        result=await client.call_tool(name,args)
                        self.assertFalse(result.isError)
                        return result.structuredContent or json.loads(result.content[0].text)
                    plan=await call('review_plan',{'artifacts':['a.py'],'required':['code'],'scope':'repository'})
                    args={'plan_id':plan['plan_id']}
                    await call('run_check',{**args,'check':'code'})
                    self.assertTrue((await call('completion_gate',args))['allow_completion'])
                    Path(temp, 'untracked.txt').write_text('new content')
                    self.assertFalse((await call('completion_gate',args))['allow_completion'])
