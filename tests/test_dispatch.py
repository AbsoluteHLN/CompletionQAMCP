"""Synthetic host dispatcher integration; no external model invocation."""
import unittest,tempfile
from pathlib import Path
from completion_plugin.profiles import Profile,Route,Role,ProfileValidator,ProbeResult,HostContext,STAGES
from completion_plugin.workflow import Workflow
from completion_plugin.runtime import dispatch_profile
from completion_plugin.usage import Ledger,Supervisor
class DispatchTests(unittest.TestCase):
 def test_approved_route_to_pending_qa(self):
  with tempfile.TemporaryDirectory() as d:
   p=Profile.create('p',(Route('r','provider','model','low','host/account'),),(Role('worker','r'),),('r',),'worker')
   c=HostContext('host','adapter','account','permission','alias')
   v=ProfileValidator(lambda stage,route,context,scope:ProbeResult(True,True,provider=route.provider,model=route.model,effort=route.effort,concurrency=1),lambda *_:True)
   for stage in STAGES:v.validate(p,'r',stage,c)
   w=Workflow(Path(d)/'state',confirm=lambda shown:shown);record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'}
   for state in ('research','direction_review','specification'):w.transition(state,record=record)
   w.revise('Generate then review');w.add_task('x',code_mode='syntax',acceptance='code QA',profile_binding={'profile_id':p.profile_id,'revision':p.profile_revision,'role':'worker','approved_routes':['r']})
   for state in ('specification_qa','awaiting_confirmation'):w.transition(state,record=record)
   w.approve();l=Ledger();s=Supervisor()
   r=dispatch_profile(w,'x',profile=p,validator=v,context=c,ledger=l,supervisor=s,host_concurrency=1,execute=lambda *args:{'output':'synthetic'})
   self.assertEqual(r['status'],'review_required');self.assertIsNone(r['usage']['cost'])
   with self.assertRaises(ValueError):w.complete()
