"""Independent in-process alias/freshness regression; no host/provider setup."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from completion_qa.core import Engine
from completion_qa.host import simulate_stop
from completion_qa.reporting import receipt_digest

def containers(obj):
    found = set()
    def visit(v):
        if isinstance(v, (dict, list, set)):
            if id(v) in found: return
            found.add(id(v))
            for item in (v.values() if isinstance(v, dict) else v): visit(item)
        elif isinstance(v, tuple):
            for item in v: visit(item)
    visit(obj)
    return found

def corrupt(obj):
    if isinstance(obj, dict):
        for v in list(obj.values()): corrupt(v)
        obj.clear(); obj['allow_completion'] = True; obj['status'] = 'pass'
    elif isinstance(obj, list):
        for v in obj: corrupt(v)
        obj.clear(); obj.append('tampered')

class Review(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'a.py').write_text('x=1')
        (self.root/'note.txt').write_text('值得注意的是，全部通过。')
        self.e = Engine(self.root)
    def plan(self, checks=('code',), scope='artifacts', files=('a.py',)):
        return self.e.plan(files, checks, profile='technical_report', scope=scope)['plan_id']
    def detached(self, returned):
        self.assertFalse(containers(returned) & containers(self.e.plans))
        before = copy.deepcopy(self.e.plans)
        corrupt(returned)
        self.assertEqual(self.e.plans, before)
    def test_plan_all_containers_and_caller_inputs(self):
        files=['a.py']; required=['code','model']
        out=self.e.plan(files,required,scope='repository'); pid=out['plan_id']
        self.detached(out)
        files[:]=['note.txt']; required[:]=['text']
        self.assertEqual(self.e.plans[pid]['artifacts'], ['a.py'])
        self.assertEqual(self.e.plans[pid]['required'], ['code','model'])
        self.e.run(pid,'code'); self.assertFalse(self.e.gate(pid)['allow_completion'])
    def test_code_success_nested_command_environment(self):
        p=self.plan(); self.detached(self.e.run(p,'code'))
        self.assertTrue(self.e.gate(p)['allow_completion'])
    def test_code_failure_stays_fail(self):
        (self.root/'a.py').write_text('x=('); p=self.plan()
        self.detached(self.e.run(p,'code')); self.assertFalse(self.e.gate(p)['allow_completion'])
        self.assertEqual(self.e.report(p)['checks'][0]['status'],'fail')
    def test_text_nested_findings(self):
        p=self.plan(('text',),files=('note.txt',)); out=self.e.run(p,'text')
        self.assertTrue(out['results']['note.txt']['findings']); self.detached(out)
        self.assertTrue(self.e.gate(p)['allow_completion'])
    def test_unavailable_early_return(self):
        p=self.plan(); (self.root/'a.py').unlink(); self.detached(self.e.run(p,'code'))
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_stale_run_return(self):
        p=self.plan(); (self.root/'a.py').write_text('x=2'); self.detached(self.e.run(p,'code'))
        self.assertFalse(self.e.gate(p)['allow_completion'])
    def test_all_unconfigured_checks(self):
        for c in ('model','native','browser'):
            with self.subTest(c=c):
                p=self.plan((c,)); out=self.e.run(p,c)
                self.assertEqual(out['source'],'capability_declaration'); self.detached(out)
                self.assertFalse(self.e.gate(p)['allow_completion']); self.assertFalse(self.e.report(p)['llm_pass'])
    def test_gate_first_hit_and_separate_results(self):
        p=self.plan(); self.e.run(p,'code'); first=self.e.gate(p); second=self.e.gate(p)
        self.assertEqual(first, second); self.assertFalse(containers(first)&containers(second))
        self.detached(first); self.detached(second); self.assertTrue(self.e.gate(p)['allow_completion'])
    def test_blocked_cache_forgery_cannot_reach_stop(self):
        p=self.plan(('model',)); self.e.run(p,'model')
        for _ in range(3): self.detached(self.e.gate(p))
        self.assertEqual(simulate_stop(lambda:self.e.gate(p))['decision'],'block')
    def test_report_repository_all_containers(self):
        p=self.plan(scope='repository'); self.e.run(p,'code')
        r=self.e.report(p); self.assertEqual(r['receipt_sha256'],receipt_digest(r)); self.detached(r)
        self.assertTrue(self.e.report(p)['allow_completion'])
    def test_report_ignores_forged_returns(self):
        p=self.plan(('model',)); self.detached(self.e.run(p,'model')); self.detached(self.e.gate(p)); self.detached(self.e.report(p))
        r=self.e.report(p); self.assertFalse(r['allow_completion']); self.assertEqual(r['checks'][2]['status'],'blocked')
    def test_cache_rechecks_changed_and_deleted_files(self):
        p=self.plan(); self.e.run(p,'code'); self.assertTrue(self.e.gate(p)['allow_completion'])
        (self.root/'a.py').write_text('x=2'); r=self.e.report(p)
        self.assertFalse(r['source_valid']); self.assertFalse(r['allow_completion']); self.assertEqual(r['checks'][0]['observed_status'],'pass')
        (self.root/'a.py').unlink(); self.assertFalse(self.e.report(p)['source_valid'])
    def test_repository_other_file_change_rechecks(self):
        p=self.plan(scope='repository'); self.e.run(p,'code'); self.assertTrue(self.e.gate(p)['allow_completion'])
        (self.root/'new.txt').write_text('new'); self.assertFalse(self.e.report(p)['allow_completion'])
    def test_stop_recursion_never_calls_gate(self):
        def forbidden(): self.fail('Recursive stop called gate')
        self.assertEqual(simulate_stop(forbidden,stop_hook_active=True)['decision'],'block')
        self.assertEqual(simulate_stop(forbidden,attempt=2)['decision'],'block')
        p=self.plan(); self.e.run(p,'code')
        self.assertFalse(self.e.gate(p,origin='reviewer')['allow_completion'])
        self.assertEqual(simulate_stop(lambda:self.e.gate(p)),{})
    def test_capability_returns_independent(self):
        r=self.e.capabilities(); corrupt(r)
        self.assertFalse(self.e.capabilities()['model']['configured'])

if __name__=='__main__': unittest.main(verbosity=2)
