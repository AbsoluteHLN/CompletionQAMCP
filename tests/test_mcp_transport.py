import sys
import unittest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
class TransportTests(unittest.IsolatedAsyncioTestCase):
 async def test_real_local_stdio(self):
  async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','completion_plugin.server'])) as (read,write):
   async with ClientSession(read,write) as session:
    await session.initialize()
    listing=await session.list_tools();self.assertEqual({t.name for t in listing.tools},{'capabilities','review_text'})
    result=await session.call_tool('review_text',{'text':'结果已经完成。结果已经完成。','profile':'conversation_summary'})
    self.assertFalse(result.isError)
