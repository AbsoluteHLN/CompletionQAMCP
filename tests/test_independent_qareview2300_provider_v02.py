import asyncio,json,unittest
from completion_qa.sampling import (FixtureSamplingProvider,SamplingReviewService,SamplingPolicy,SamplingApproval,SampledText,rewrite_is_constrained)
async def approve(r):return SamplingApproval(r.digest)
class ProviderNegative(unittest.IsolatedAsyncioTestCase):
    def service(self,obj,approval=approve):
        p=FixtureSamplingProvider(json.dumps(obj,ensure_ascii=False));return p,SamplingReviewService(p,policy=SamplingPolicy(enabled=True),approve_request=approval)
    async def test_fixture_never_llm_pass(self):
        p,s=self.service({'verdict':'pass','summary':'ok','findings':[]});r=await s.review_code('x=1')
        self.assertEqual(r['status'],'fixture');self.assertFalse(r['llm_pass']);self.assertFalse(r['applied'])
    async def test_disabled_never_calls_provider(self):
        p=FixtureSamplingProvider('{}');r=await SamplingReviewService(p,approve_request=approve).review_code('x=1')
        self.assertEqual(r['status'],'blocked');self.assertEqual(p.requests,[])
    async def test_bare_bool_approval_never_calls_provider(self):
        async def bad(r):return True
        p,s=self.service({'verdict':'pass','summary':'ok','findings':[]},bad)
        self.assertEqual((await s.review_code('x=1'))['status'],'blocked');self.assertEqual(p.requests,[])
    async def test_stale_approval_never_calls_provider(self):
        async def bad(r):return SamplingApproval('stale')
        p,s=self.service({'verdict':'pass','summary':'ok','findings':[]},bad)
        self.assertEqual((await s.review_code('x=1'))['status'],'blocked');self.assertEqual(p.requests,[])
    async def test_inconsistent_verdict_blocked(self):
        p,s=self.service({'verdict':'pass','summary':'ok','findings':[{'severity':'error','message':'bad'}]})
        self.assertEqual((await s.review_code('x=1'))['status'],'blocked')
    async def test_extra_field_blocked(self):
        p,s=self.service({'verdict':'pass','summary':'ok','findings':[],'llm_pass':True})
        self.assertEqual((await s.review_code('x=1'))['status'],'blocked')
    async def test_duplicate_fields_blocked(self):
        p=FixtureSamplingProvider('{"verdict":"fail","verdict":"pass","summary":"ok","findings":[]}')
        s=SamplingReviewService(p,policy=SamplingPolicy(enabled=True),approve_request=approve)
        self.assertEqual((await s.review_code('x=1'))['status'],'blocked')
    async def test_numeric_negation_causal_status_mutations(self):
        source='值得注意的是，10%不意味着A导致B；未执行，不能判定通过。'
        for changed in [source.replace('10%','11%'),source.replace('不意味着','意味着'),source.replace('导致','相关'),source.replace('未执行','已执行')]:
            p,s=self.service({'proposed_text':changed,'findings':[]});r=await s.rewrite_text(source)
            self.assertEqual(r['status'],'blocked');self.assertEqual(r['proposed_text'],source)
    async def test_approved_leadin_deletion_stays_fixture(self):
        source='值得注意的是，10%不意味着A导致B；未执行。';target=source.removeprefix('值得注意的是，')
        p,s=self.service({'proposed_text':target,'findings':[]});r=await s.rewrite_text(source)
        self.assertEqual(r['status'],'fixture');self.assertFalse(r['llm_pass']);self.assertEqual(r['proposed_text'],target)
    async def test_quotes_codes_and_line_ending_changes_rejected(self):
        for source in ['“\n值得注意的是，10%未通过。\n”','> worth quoting\n值得注意的是，未通过。','```\n值得注意的是，未通过。\n```','值得注意的是，未通过。\r\n']:
            target=source.replace('值得注意的是，','').replace('\r\n','\n')
            self.assertFalse(rewrite_is_constrained(source,target))
    async def test_provider_timeout_blocked(self):
        class Slow(FixtureSamplingProvider):
            async def sample(self,r):await asyncio.sleep(1)
        s=SamplingReviewService(Slow('{}'),policy=SamplingPolicy(enabled=True,timeout_seconds=.01),approve_request=approve)
        self.assertEqual((await s.review_code('x=1'))['status'],'blocked')
    async def test_unknown_provider_provenance_rejected(self):
        class Unknown(FixtureSamplingProvider):provenance='invented'
        with self.assertRaises(ValueError):SamplingReviewService(Unknown('{}'))
    async def test_legacy_provider_default_disabled(self):
        from completion_qa.sampling import MCPSamplingProvider,SamplingRequest
        class Session:
            def check_client_capability(self,*args):raise AssertionError('must not access capability')
            async def create_message(self,*args,**kwargs):raise AssertionError('must not transmit')
        p=MCPSamplingProvider(Session());self.assertFalse(p.supports_sampling())
        with self.assertRaises(ValueError):await p.sample(SamplingRequest('code_review','s','p',1))
