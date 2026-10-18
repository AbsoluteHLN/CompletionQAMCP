import asyncio
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from mcp import types
from mcp.server.session import ServerSession
from completion_qa.sampling import (
    FixtureSamplingProvider, MCPSamplingProvider, SamplingApproval,
    SamplingPolicy, SamplingRequest, SamplingReviewService,
    classify_protections, rewrite_is_constrained,
)

PASS = json.dumps({'verdict': 'pass', 'summary': 'No issue found in this limited fixture.', 'findings': []})

async def approve(request):
    return SamplingApproval(request.digest)

class SamplingTests(unittest.IsolatedAsyncioTestCase):
    def service(self, response=PASS, **kwargs):
        provider = FixtureSamplingProvider(response)
        return provider, SamplingReviewService(provider, policy=kwargs.pop('policy', SamplingPolicy(enabled=True)),
                                              approve_request=kwargs.pop('approve_request', approve), **kwargs)

    async def test_default_disabled_no_approval_or_request(self):
        provider = FixtureSamplingProvider(PASS)
        callback = AsyncMock(side_effect=AssertionError('must not approve'))
        result = await SamplingReviewService(provider, approve_request=callback).review_code('x = 1')
        self.assertEqual(result['reason'], 'sampling_disabled')
        self.assertFalse(provider.requests)
        callback.assert_not_called()

    async def test_capability_before_approval_and_missing_callback(self):
        provider, service = self.service()
        provider.capable = False
        self.assertEqual((await service.review_code('x'))['reason'], 'sampling_capability_missing')
        provider, service = self.service(approve_request=None)
        self.assertEqual((await service.review_code('x'))['reason'], 'host_approval_unavailable')
        self.assertFalse(provider.requests)

    async def test_boolean_denial_and_stale_approval_cannot_sample(self):
        for answer in (True, False, None, SamplingApproval('wrong')):
            provider, service = self.service(approve_request=AsyncMock(return_value=answer))
            self.assertEqual((await service.review_code('x'))['reason'], 'host_approval_denied')
            self.assertFalse(provider.requests)

    async def test_exact_immutable_request_approved_before_sample(self):
        observed = []
        provider = FixtureSamplingProvider(PASS)
        async def inspect(request):
            self.assertFalse(provider.requests)
            self.assertIn('input_sha256', request.prompt)
            self.assertIn('"findings"', request.system_prompt)
            with self.assertRaises(FrozenInstanceError):
                request.prompt = 'changed'
            observed.append(request)
            return SamplingApproval(request.digest)
        service = SamplingReviewService(provider, policy=SamplingPolicy(enabled=True), approve_request=inspect)
        result = await service.review_code('x = 1')
        self.assertEqual(provider.requests, observed)
        self.assertEqual(result['status'], 'fixture')
        self.assertFalse(result['llm_pass'])

    async def test_synthetic_semantic_bug_is_fixture(self):
        response = json.dumps({'verdict':'fail', 'summary':'Zero denominator is unguarded.',
                               'findings':[{'severity':'error','message':'Calling ratio(1, 0) raises ZeroDivisionError.'}]})
        _, service = self.service(response)
        result = await service.review_code('def ratio(a, b):\n    return a / b\n')
        self.assertEqual(result['verdict'], 'fail')
        self.assertEqual(result['status'], 'fixture')
        self.assertFalse(result['llm_pass'])

    async def test_strict_response_and_limits(self):
        responses = ['```json\n'+PASS+'\n```', '{}', '[]',
                     '{"verdict":"pass","verdict":"fail","summary":"s","findings":[]}',
                     json.dumps({'verdict':'pass','summary':12,'findings':[]}),
                     json.dumps({'verdict':'pass','summary':'s','findings':[], 'extra':True})]
        for response in responses:
            _, service = self.service(response)
            self.assertEqual((await service.review_code('x'))['status'], 'blocked')
        provider, service = self.service(policy=SamplingPolicy(enabled=True, max_input_chars=2))
        self.assertEqual((await service.review_code('abc'))['reason'], 'invalid_or_oversize_input')
        self.assertFalse(provider.requests)
        _, service = self.service(policy=SamplingPolicy(enabled=True, max_output_chars=2))
        self.assertEqual((await service.review_code('x'))['reason'], 'invalid_or_oversize_response')

    async def test_timeout_and_approval_exception_fail_closed(self):
        async def slow(request):
            await asyncio.sleep(1)
        provider, service = self.service(approve_request=slow, policy=SamplingPolicy(enabled=True, approval_timeout_seconds=.001))
        self.assertEqual((await service.review_code('x'))['reason'], 'host_approval_timeout')
        self.assertFalse(provider.requests)
        provider, service = self.service(policy=SamplingPolicy(enabled=True, timeout_seconds=.001))
        provider.sample = slow
        self.assertEqual((await service.review_code('x'))['reason'], 'sampling_timeout')
        provider, service = self.service(approve_request=AsyncMock(side_effect=RuntimeError('private detail')))
        result = await service.review_code('x')
        self.assertEqual(result['reason'], 'host_approval_error')
        self.assertNotIn('private detail', str(result))

    async def test_rewrite_preserves_stage_facts(self):
        source = '值得注意的是，原13项测试通过；独立15项和wrapper5项通过。browser未运行，model未运行；相关不代表因果。'
        proposed = source.removeprefix('值得注意的是，')
        _, service = self.service(json.dumps({'proposed_text':proposed, 'findings':[]}))
        result = await service.rewrite_text(source)
        self.assertEqual(result['proposed_text'], proposed)
        self.assertFalse(result['llm_pass'])
        self.assertFalse(result['applied'])
        self.assertEqual(set(result['protections']), {'numeric','negation','causality','status'})
        for changed in (proposed.replace('13','14'), proposed.replace('未运行','通过'),
                        proposed.replace('不代表','代表'), proposed.replace('相关','实验'),
                        proposed+' 全部通过。'):
            _, service = self.service(json.dumps({'proposed_text':changed,'findings':[]}))
            result = await service.rewrite_text(source)
            self.assertEqual(result['reason'], 'claim_preservation_rejected')
            self.assertEqual(result['proposed_text'],source)

    async def test_quotes_and_code_diagnostic_only(self):
        for source in ('“值得注意的是，13项通过。”', '```\n值得注意的是，代码\n```', '> 值得注意的是，引用', "It isn't proven."):
            _, service = self.service(json.dumps({'proposed_text':source,'findings':[]}))
            result = await service.rewrite_text(source)
            self.assertTrue(result['diagnostic_only'])
            self.assertFalse(rewrite_is_constrained(source, source+' changed'))

    async def test_official_sdk_serialization_with_in_memory_transport(self):
        # Calls the real installed SDK method, but substitutes only send_request:
        # no network/model is used, and this is not LLM quality evidence.
        session = object.__new__(ServerSession)
        session._client_params = SimpleNamespace(capabilities=types.ClientCapabilities(sampling=types.SamplingCapability()))
        session.send_request = AsyncMock(return_value=types.CreateMessageResult(
            role='assistant', content=types.TextContent(type='text',text=PASS), model='local-transport-fixture', stopReason='endTurn'))
        self.assertFalse(MCPSamplingProvider(session).supports_sampling())
        provider = MCPSamplingProvider(session, allow_legacy_compatibility=True)
        self.assertTrue(provider.supports_sampling())
        request = SamplingRequest('code_review','system','synthetic source',128)
        result = await provider.sample(request)
        self.assertEqual(result.text, PASS)
        params = session.send_request.call_args.kwargs['request'].root.params
        self.assertEqual(params.includeContext, 'none')
        self.assertIsNone(params.tools)
        self.assertIsNone(params.toolChoice)
        self.assertEqual(params.maxTokens,128)
        self.assertEqual(params.messages[0].content.text,'synthetic source')
        for stop in ('maxTokens','toolUse',None):
            session.send_request.return_value.stopReason = stop
            with self.assertRaises(ValueError):
                await provider.sample(request)

    def test_policy_and_conservative_boundaries(self):
        for args in ({'max_tokens':True}, {'timeout_seconds':float('nan')}, {'max_input_chars':999999}):
            with self.assertRaises(ValueError): SamplingPolicy(**args)
        self.assertFalse(rewrite_is_constrained('Therefore, x passed.', 'x passed.'))
        self.assertFalse(rewrite_is_constrained('值得注意的是，事实。\n', '事实。'))
        self.assertFalse(rewrite_is_constrained('值得注意的是，\n', '\n'))
        self.assertIn('status', classify_protections('not_run'))

if __name__ == '__main__':
    unittest.main()
