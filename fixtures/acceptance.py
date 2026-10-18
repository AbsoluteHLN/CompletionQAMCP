"""Produces an inspectable acceptance artifact; no candidate integrations invoked."""
import json
from pathlib import Path
from completion_qa.core import Engine
from completion_qa.host import simulate_stop
root=Path(__file__).resolve().parent
engine=Engine(root)
report={}
for label, artifact, checks, profile in [
    ('syntax_ok','good.py',['code'],'technical_report'),
    ('syntax_fail','bad.json',['code'],'technical_report'),
    ('missing_browser','good.py',['browser'],'technical_report'),
    ('text_proposal','academic.txt',['text'],'academic')]:
    p=engine.plan([artifact],checks,profile)
    evidence=[engine.run(p['plan_id'],c) for c in checks]
    gate=engine.gate(p['plan_id'])
    report[label]={'plan':p,'evidence':evidence,'gate':gate,'simulated_host_output':simulate_stop(lambda:gate)}
print(json.dumps(report,ensure_ascii=False,indent=2))
