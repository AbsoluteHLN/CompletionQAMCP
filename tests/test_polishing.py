"""Synthetic host contract tests; no real model is called."""
import json
import unittest
from dataclasses import replace

from completion_plugin.polishing import HostBindings, PolishingSession


class PolishingTests(unittest.TestCase):
    original = '研究方法：对32例样本进行分析。结果：未发现显著改善[1]。局限：样本量较小。'
    candidate = '研究方法：分析32例样本。结果：未发现显著改善[1]。局限：样本量较小。'

    def binding(self, **kwargs):
        values = dict(authorize=lambda request: request,
                      generate=lambda request: {'candidate': self.candidate},
                      execution_kind='mock', generator_identity='generation-context')
        values.update(kwargs)
        return HostBindings(**values)

    def run_session(self, host):
        session = PolishingSession(host)
        return session, session.run(self.original, 'academic', document_id='paper-a', revision=2)

    def test_missing_host_is_blocked_without_model(self):
        _, result = self.run_session(None)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['generation'], 'not_run')
        self.assertEqual(result['attempts'], [])

    def test_no_permission_means_no_calls(self):
        calls = []
        _, result = self.run_session(self.binding(authorize=lambda request: None, generate=lambda request: calls.append(request)))
        self.assertEqual(calls, [])
        self.assertEqual(result['reason'], 'generation_not_authorized')

    def test_bare_boolean_cannot_authorize(self):
        _, result = self.run_session(self.binding(authorize=lambda request: True))
        self.assertEqual(result['generation'], 'not_run')

    def test_different_request_cannot_authorize(self):
        _, result = self.run_session(self.binding(authorize=lambda request: replace(request, original='不同正文')))
        self.assertEqual(result['generation'], 'not_run')

    def test_three_profile_prompts_are_distinct(self):
        requests = []
        host = self.binding(generate=lambda request: (requests.append(request) or {'candidate': request.original}))
        session = PolishingSession(host)
        for profile in ('academic', 'technical_document', 'conversation_summary'):
            session.run(self.original, profile, document_id='document', revision=1)
        self.assertEqual(len({r.instructions for r in requests}), 3)
        self.assertTrue(all('待编辑数据' in r.instructions for r in requests))

    def test_candidate_generated_and_audited_without_reviewer(self):
        _, result = self.run_session(self.binding())
        self.assertEqual(result['generation'], 'completed')
        self.assertEqual(result['semantic_review'], 'not_run')
        self.assertEqual(result['status'], 'review_required')
        self.assertTrue(result['audit']['changed_spans'])
        self.assertFalse(result['allow_completion'])
        self.assertIsNone(result['attempts'][0]['cost'])

    def test_mock_end_to_end_review_and_adoption(self):
        approvals = []
        host = self.binding(semantic_review=lambda request: {'verdict': 'no_issues_found', 'notes': '合成测试：未发现语义变化。'},
                            reviewer_identity='independent-review-context',
                            accept=lambda request: (approvals.append(request) or request))
        session, result = self.run_session(host)
        adopted = session.adopt(result['result_id'], current_text=self.original, current_revision=2)
        self.assertEqual(adopted['status'], 'accepted_for_use')
        self.assertEqual(adopted['semantic_review'], 'mock_completed')
        self.assertEqual(adopted['factual_verification'], 'not_run')
        self.assertFalse(adopted['allow_completion'])
        self.assertEqual(json.loads(approvals[0].review_report)['audit']['candidate'], self.candidate)
        session.adopt(result['result_id'], current_text=self.original, current_revision=2)
        self.assertEqual(len(approvals), 1)

    def test_reviewer_not_authorized_does_not_call(self):
        calls = []
        host = self.binding(authorize=lambda request: request if request.phase == 'generate' else None,
                            semantic_review=lambda request: calls.append(request), reviewer_identity='review-context')
        _, result = self.run_session(host)
        self.assertEqual(calls, [])
        self.assertEqual(result['semantic_review'], 'not_run')
        self.assertEqual(result['reason'], 'semantic_review_not_authorized')

    def test_protected_changes_not_overruled_by_opinion(self):
        host = self.binding(generate=lambda request: {'candidate': '研究结果：64例均改善[2]。'},
                            semantic_review=lambda request: {'verdict': 'no_issues_found', 'notes': '模拟评审漏检。'},
                            reviewer_identity='review-context')
        _, result = self.run_session(host)
        self.assertTrue(result['audit']['rewrite_risks'])
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['factual_verification'], 'not_run')

    def test_same_context_is_not_independent(self):
        with self.assertRaises(ValueError):
            self.binding(semantic_review=lambda request: {}, reviewer_identity='generation-context')

    def test_generation_failure_is_preserved(self):
        def fail(request):
            raise RuntimeError('synthetic failure')
        _, result = self.run_session(self.binding(generate=fail))
        self.assertEqual(result['generation'], 'failed')
        self.assertEqual(result['attempts'][0]['status'], 'failed')
        self.assertIsNone(result['attempts'][0]['tokens'])

    def test_malformed_generation_blocked(self):
        _, result = self.run_session(self.binding(generate=lambda request: {'candidate': 123}))
        self.assertEqual(result['generation'], 'failed')

    def test_malformed_review_is_not_pass(self):
        _, result = self.run_session(self.binding(semantic_review=lambda request: {'verdict': 'verified', 'notes': '虚构验证'}, reviewer_identity='review'))
        self.assertEqual(result['semantic_review'], 'failed')
        self.assertFalse(result['allow_completion'])

    def test_stale_document_prevents_adoption(self):
        calls = []
        session, result = self.run_session(self.binding(accept=lambda request: calls.append(request)))
        for text, revision in ((self.original + '追加。', 2), (self.original, 3)):
            self.assertEqual(session.adopt(result['result_id'], current_text=text, current_revision=revision)['reason'], 'stale_document')
        self.assertEqual(calls, [])

    def test_return_mutation_cannot_change_stored_candidate(self):
        session, result = self.run_session(self.binding(accept=lambda request: request))
        result['audit']['candidate'] = '恶意替换'
        adopted = session.adopt(result['result_id'], current_text=self.original, current_revision=2)
        self.assertEqual(adopted['audit']['candidate'], self.candidate)

    def test_accept_requires_matching_trusted_callback(self):
        session, result = self.run_session(self.binding())
        self.assertEqual(session.adopt(result['result_id'], current_text=self.original, current_revision=2)['reason'], 'trusted_acceptance_unavailable')
        session, result = self.run_session(self.binding(accept=lambda request: True))
        self.assertEqual(session.adopt(result['result_id'], current_text=self.original, current_revision=2)['reason'], 'candidate_not_accepted')

    def test_usage_kept_even_if_response_candidate_is_invalid(self):
        host = self.binding(generate=lambda request: {'candidate': 3, 'usage': {'tokens': 21, 'cost': 0.01, 'currency': 'USD', 'measurement_source': 'actual'}})
        _, result = self.run_session(host)
        self.assertEqual(result['generation'], 'failed')
        self.assertEqual(result['attempts'][0]['tokens'], 21)
        self.assertEqual(result['attempts'][0]['cost'], 0.01)

    def test_invalid_usage_does_not_become_zero(self):
        host = self.binding(generate=lambda request: {'candidate': self.candidate, 'usage': {'tokens': -1, 'measurement_source': 'actual'}})
        _, result = self.run_session(host)
        self.assertEqual(result['generation'], 'completed')
        self.assertIsNone(result['attempts'][0]['tokens'])
        self.assertEqual(result['attempts'][0]['unknown_reason'], 'invalid_host_usage')

    def test_invalid_document_binding(self):
        with self.assertRaises(ValueError):
            PolishingSession().run(self.original, 'academic', document_id='', revision=1)
        with self.assertRaises(ValueError):
            PolishingSession().run(self.original, 'academic', document_id='doc', revision=True)


if __name__ == '__main__':
    unittest.main()
