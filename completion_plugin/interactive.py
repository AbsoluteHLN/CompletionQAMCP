"""Operator-facing terminal workflow. Agent/host users should use trusted adapters."""
import json
import sys
from .workflow import Workflow
from .runtime import execute_review
from .usage import Ledger


def run(*, state, root, artifacts, read=input, write=print, terminal=None):
    if terminal is None: terminal=sys.stdin.isatty()
    if terminal is not True:
        raise ValueError('Interactive approval requires an operator terminal; piped approval is rejected')
    from pathlib import Path
    if Path(state).exists():
        raise ValueError('Existing task state; inspect it instead of overwriting')
    goal=read('Goal and acceptance (syntax checks only in this entry): ').strip()
    if not goal: raise ValueError('Goal required')
    write('Confirming goal: '+goal)
    if read('Confirm key goal? Type yes: ').strip()!='yes': return {'status':'cancelled'}
    w=Workflow(state)
    w.transition('research',record={'goal':goal,'confirmed_by':'operator'})
    urls=read('Official research source URLs, comma separated (or explicit waiver): ').strip()
    if urls=='waiver':
        if read('Skip online research for this task? Type waive: ').strip()!='waive':return {'status':'cancelled'}
        record={'research_waiver':'user_confirmed'}
    else:
        write('These are user-supplied sources; this CLI has not fetched or verified them.')
        if read('Accept unverified-source limitation for this local check? Type acknowledge: ').strip()!='acknowledge':return {'status':'cancelled'}
        record={'sources':[u.strip() for u in urls.split(',') if u.strip()], 'verification':'user_supplied_not_verified','research_waiver':'user_confirmed'}
    w.transition('direction_review',record=record)
    write('Available direction: local syntax review; no project-code execution or model claims.')
    if read('Choose local syntax review? Type local: ').strip()!='local':return {'status':'cancelled'}
    w.transition('specification',record={'source':'user','choice':'local syntax'})
    w.revise(goal)
    w.add_task('review',code_mode='syntax',acceptance='All declared files pass Python/JSON syntax; no semantic certification',writes=(),required_checks=['code'],inputs={'root':str(Path(root).resolve()),'artifacts':list(artifacts)})
    w.transition('specification_qa',record={'scope':'syntax only'})
    w.transition('awaiting_confirmation',record={'status':'pass','method':'bounded entry schema review'})
    proposal=w._proposal()
    write(json.dumps(proposal,ensure_ascii=False,indent=2))
    def confirm(shown):
        if read('Approve this exact specification? Type APPROVE '+str(shown['revision'])+': ').strip() == 'APPROVE '+str(shown['revision']):return shown
        return None
    w.confirm=confirm
    try:w.approve()
    except ValueError:return {'status':'cancelled','reason':'Specification not approved'}
    result=execute_review(w,'review',root=root,artifacts=artifacts,ledger=Ledger(str(state)+'.usage.json'))
    if result['status']=='pass':w.complete()
    return result


def resume(state, *, read=input, write=print, terminal=None):
    if terminal is None:terminal=sys.stdin.isatty()
    if terminal is not True:raise ValueError('Operator terminal required')
    w=Workflow(state)
    if w.data['state'] not in ('awaiting_confirmation','approved'):
        raise ValueError('Only a saved, unexecuted final proposal can resume safely')
    task=w.data['tasks'].get('review')
    if not task or task['status']!='not_run' or task.get('code_mode')!='syntax':
        raise ValueError('Saved task needs host recovery; not automatically replayed')
    shown=w._proposal();write(json.dumps(shown,ensure_ascii=False,indent=2))
    if read('Resume exact proposal? Type APPROVE '+str(shown['revision'])+': ').strip()!='APPROVE '+str(shown['revision']):return {'status':'cancelled'}
    if w.data['state']=='awaiting_confirmation':
        w.confirm=lambda proposal:shown if proposal==shown else None
        w.approve()
    inputs=task['inputs']
    result=execute_review(w,'review',root=inputs['root'],artifacts=inputs['artifacts'],ledger=Ledger(str(state)+'.usage.json'))
    if result['status']=='pass':w.complete()
    return result
