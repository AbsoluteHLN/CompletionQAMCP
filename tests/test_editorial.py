import unittest

from completion_plugin.editorial import MAX_TEXT_LENGTH, PROFILES, review


class EditorialTests(unittest.TestCase):
    def test_profiles_are_distinct(self):
        codes = [{d['code'] for d in review('正文。', p)['structure_diagnostics']} for p in PROFILES]
        self.assertEqual(len(PROFILES), 3)
        self.assertNotEqual(codes[0], codes[1])
        self.assertNotEqual(codes[1], codes[2])

    def test_original_retained_no_candidate(self):
        text = '我们对32例样本进行分析。结果可能与选择偏倚有关[1]。'
        result = review(text, 'academic')
        self.assertEqual(result['original'], text)
        self.assertEqual(result['candidate'], text)
        self.assertFalse(result['changed'])
        self.assertFalse(result['applied'])
        self.assertFalse(result['candidate_supplied'])
        self.assertEqual(result['semantic_review'], 'not_run')
        self.assertEqual(result['factual_verification'], 'not_run')

    def test_suggestions_are_precise_and_review_only(self):
        text = '🙂我们进行分析，但未发现显著差异。'
        result = review(text, 'academic')
        item = result['suggestions'][0]
        self.assertEqual(item['replacement'], '分析')
        self.assertEqual(text[item['span']['start']:item['span']['end']], '进行分析')
        self.assertFalse(item['safe_to_apply'])

    def test_uncertainty_not_deleted(self):
        result = review('在一定程度上可能改善结果。', 'academic')
        item = result['suggestions'][0]
        self.assertIsNone(item['replacement'])
        self.assertIn('保留', item['message'])

    def test_numbers_units_citations_change(self):
        old = '结果：32例中改善12.5%，随访6个月[1]。'
        new = '结果：33例中改善21.5%，随访6个月[2]。'
        codes = {r['code'] for r in review(old, 'academic', new)['rewrite_risks']}
        self.assertIn('numbers_changed', codes)
        self.assertIn('citations_changed', codes)

    def test_limitations_negations_causality_conclusions(self):
        old = '结论：仅观察到相关性，未发现因果证据；样本量有限，可能存在偏倚。'
        new = '结论：证明干预导致改善。'
        result = review(old, 'academic', new)
        codes = {r['code'] for r in result['rewrite_risks']}
        for name in ('negation', 'limitations', 'causality', 'conclusions'):
            self.assertIn(name + '_changed', codes)
        self.assertFalse(result['candidate_within_permitted_edits'])

    def test_same_numbers_different_subject_still_review(self):
        result = review('甲组改善20%，乙组改善10%。', 'academic', '乙组改善20%，甲组改善10%。')
        self.assertTrue(result['protected_content']['numbers']['sequence_unchanged'])
        self.assertEqual(result['status'], 'review_required')
        self.assertTrue(result['changed_protected_sentences'])

    def test_same_conclusion_word_different_content_still_review(self):
        result = review('结论：方案可采用。', 'technical_document', '结论：方案应废弃。')
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['semantic_review'], 'not_run')

    def test_code_and_citation_not_polished(self):
        result = review('`进行分析`\n```python\nprint("进行研究")\n```\n【众所周知】', 'technical_document')
        self.assertEqual(result['suggestions'], [])

    def test_unterminated_code_block_not_polished(self):
        result = review('```text\n进行分析', 'technical_document')
        self.assertEqual(result['suggestions'], [])

    def test_repeated_sentence_diagnostic(self):
        result = review('结果只适用于本次小规模测试。结果只适用于本次小规模测试。', 'academic')
        self.assertIn('repeated_sentence', {d['code'] for d in result['structure_diagnostics']})

    def test_long_sentence(self):
        result = review('范围和条件需要逐项说明，' * 20 + '结束。', 'technical_document')
        self.assertIn('long_sentence', {d['code'] for d in result['structure_diagnostics']})

    def test_complete_summary_has_no_missing_structure(self):
        text = '决定：使用方案甲。下一步：李工周三负责验收。待确认：预算上限。'
        result = review(text, 'conversation_summary')
        self.assertEqual(result['structure_diagnostics'], [])
        self.assertEqual(result['status'], 'no_rule_findings')
        self.assertEqual(result['factual_verification'], 'not_run')

    def test_changes_reconstruct_candidate(self):
        old, new = '实验🙂显示3例改善[1]。', '实验🙂观察到3例改善[1]，尚需验证。'
        result = review(old, 'academic', new)
        parts, cursor = [], 0
        for change in result['changed_spans']:
            a, b = change['original'], change['candidate']
            self.assertEqual(old[a['start']:a['end']], a['text'])
            self.assertEqual(new[b['start']:b['end']], b['text'])
            parts.extend([old[cursor:a['start']], b['text']])
            cursor = a['end']
        parts.append(old[cursor:])
        self.assertEqual(''.join(parts), new)

    def test_only_exact_line_normalization_is_permitted(self):
        old = '结果：32例。\r\n局限：样本量不足。\r\n'
        self.assertTrue(review(old, 'academic', old.replace('\r\n', '\n'))['candidate_within_permitted_edits'])
        self.assertFalse(review('有结果。  \n', 'academic', '有结果。\n')['candidate_within_permitted_edits'])
        self.assertFalse(review(old, 'academic', old.replace('32', '33').replace('\r\n', '\n'))['candidate_within_permitted_edits'])

    def test_empty_candidate_is_actual_deletion(self):
        result = review('未发现改善[1]。', 'academic', '')
        self.assertTrue(result['candidate_supplied'])
        self.assertTrue(result['changed'])
        self.assertFalse(result['candidate_within_permitted_edits'])

    def test_english_qualifiers_and_author_year(self):
        result = review('This may suggest correlation (Li, 2024), not causality.', 'academic', 'This proves causality (Li, 2025).')
        self.assertIn('citations_changed', {r['code'] for r in result['rewrite_risks']})
        self.assertIn('negation_changed', {r['code'] for r in result['rewrite_risks']})

    def test_results_do_not_share_mutable_state(self):
        one = review('进行分析。', 'academic')
        one['suggestions'].clear()
        one['capability_limits'].clear()
        two = review('进行分析。', 'academic')
        self.assertTrue(two['suggestions'])
        self.assertTrue(two['capability_limits'])

    def test_units_are_not_interchangeable(self):
        result = review('剂量为5 mg，体积10 mL。', 'academic', '剂量为5 kg，体积10 ml。')
        self.assertIn('quantities_changed', {r['code'] for r in result['rewrite_risks']})
        self.assertFalse(result['candidate_within_permitted_edits'])

    def test_latex_formula_changes_flagged_and_never_polished(self):
        old = r'模型为 $y = 2x$；说明 \(p < 0.05\)。$进行分析$'
        new = r'模型为 $y = 3x$；说明 \(p > 0.05\)。$进行分析$'
        result = review(old, 'academic', new)
        self.assertIn('formulas_changed', {r['code'] for r in result['rewrite_risks']})
        self.assertEqual(result['suggestions'], [])

    def test_term_variants_are_review_only(self):
        result = review('训练数据集与验证资料集应分别说明。', 'academic')
        diagnostic = next(d for d in result['structure_diagnostics'] if d['code'] == 'terminology_consistency')
        self.assertTrue(diagnostic['requires_human_review'])
        self.assertEqual(result['original'], result['candidate'])

    def test_dense_paragraph(self):
        result = review('这是背景说明。' * 80, 'technical_document')
        self.assertIn('dense_paragraph', {d['code'] for d in result['structure_diagnostics']})

    def test_input_validation(self):
        for args, exception in [((None, 'academic'), TypeError), (('a', 'other'), ValueError), (('a', [], None), ValueError), (('a', 'academic', 1), TypeError), (('a' * (MAX_TEXT_LENGTH + 1), 'academic'), ValueError)]:
            with self.assertRaises(exception):
                review(*args)

    def test_large_repetitive_diff_bounded_and_exact(self):
        old = '甲' * 12000 + '乙' + '甲' * 12000
        new = '甲' * 12000 + '丙' + '甲' * 12000
        change = review(old, 'academic', new)['changed_spans'][0]
        self.assertEqual(change['original']['text'], '乙')
        self.assertEqual(change['candidate']['text'], '丙')


if __name__ == '__main__':
    unittest.main()
