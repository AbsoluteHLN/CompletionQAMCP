"""Explicit revisions and trusted local approval. No content fingerprints.

Trust boundary: caller and storage are trusted; this is not tamper protection.
"""
import copy
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Workflow:
    def __init__(self, path, *, confirm=None):
        self.path = Path(path)
        self.confirm = confirm
        self._verifiers = {}
        self._existed = self.path.exists()
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if self.data.get('schema_version') != 1 or not isinstance(self.data.get('events'), list):
                raise ValueError('Unsupported or damaged state')
        else:
            self.data = {'schema_version': 1, 'revision': 0, 'state': 'intake', 'spec': '',
                         'events': [], 'approval': None, 'tasks': {}}
        self._validate()
        self._loaded = copy.deepcopy(self.data)

    def _proposal(self):
        tasks = {name:{k:copy.deepcopy(v) for k,v in task.items() if k not in ('status','result')} for name,task in self.data['tasks'].items()}
        return {'revision':self.data['revision'], 'spec':self.data['spec'], 'tasks':tasks}

    def _validate(self):
        d = self.data
        if type(d.get('revision')) is not int or d['revision'] < 0 or not isinstance(d.get('spec'), str) or not isinstance(d.get('tasks'), dict):
            raise ValueError('Damaged state')
        states = {'intake','research','direction_review','specification','specification_qa','awaiting_confirmation','approved','executing','complete'}
        if d.get('state') not in states or any(e.get('sequence') != i+1 for i,e in enumerate(d['events'])):
            raise ValueError('Damaged timeline')
        if d.get('approval') is not None and d['approval'] != self._proposal():
            raise ValueError('Damaged approval')
        if d['state'] in {'approved','executing','complete'} and d.get('approval') is None:
            raise ValueError('Approval missing')
        for t in d['tasks'].values():
            if t.get('status') not in {'not_run','running','pass','fail','blocked'} or not isinstance(t.get('depends'),list) or not isinstance(t.get('writes'),list) or not t.get('acceptance'):
                raise ValueError('Damaged task')
            if t['status'] in ('pass','fail') and not t.get('result'): raise ValueError('Missing result')
            if t['status'] == 'pass':
                evidence=t['result'].get('review',{})
                if evidence.get('revision') != d['revision'] or evidence.get('allow_completion') is not True or any(evidence.get('checks',{}).get(c) != 'pass' for c in t['required_checks']):
                    raise ValueError('Restored acceptance evidence invalid')
            if any(dep not in d['tasks'] for dep in t['depends']): raise ValueError('Missing dependency')
        if d['state'] == 'complete' and (not d['tasks'] or any(t['status'] != 'pass' for t in d['tasks'].values())):
            raise ValueError('Incomplete completed state')

    def _save(self, event):
        from .locking import writer_lock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with writer_lock(self.path.with_name(self.path.name + '.lock')):
            if self._existed and not self.path.exists():
                raise ValueError("State removed; reload required")
            if self.path.exists() and json.loads(self.path.read_text(encoding="utf-8")) != self._loaded:
                raise ValueError('State conflict; reload before modifying')
            self.data['events'].append({'sequence': len(self.data['events']) + 1,
                                        'at': now(), 'kind': event, 'revision': self.data['revision']})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_name(self.path.name + '.' + uuid4().hex + '.tmp')
            temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.path)
            self._existed = True
            self._loaded = copy.deepcopy(self.data)
    

    def transition(self, target, *, record):
        edges = {'intake': 'research', 'research': 'direction_review',
                 'direction_review': 'specification', 'specification': 'specification_qa',
                 'specification_qa': 'awaiting_confirmation'}
        if edges.get(self.data['state']) != target or not record:
            raise ValueError('Invalid stage or missing record')
        if target == 'direction_review' and not (isinstance(record,dict) and (any(isinstance(u,str) and u.startswith('https://') for u in record.get('sources',[])) or record.get('research_waiver') == 'user_confirmed')):
            raise ValueError('Research source records or explicit waiver required')
        if target == 'specification' and not (isinstance(record,dict) and record.get('source') == 'user' and record.get('choice')):
            raise ValueError('User direction record required')
        if target == 'awaiting_confirmation' and not (isinstance(record,dict) and record.get('status') == 'pass'):
            raise ValueError('Specification QA did not pass')
        if target == 'awaiting_confirmation' and not self.data['spec']:
            raise ValueError('Specification missing')
        self.data['state'] = target
        self._save({'transition': target, 'record': copy.deepcopy(record)})

    def revise(self, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Empty specification')
        if text != self.data['spec']:
            self.data['spec'] = text
            self.data['revision'] += 1
            self.data['approval'] = None
            for task in self.data['tasks'].values():
                task.update(status='not_run', result=None)
            if self.data['state'] not in ('intake', 'research', 'direction_review'):
                self.data['state'] = 'specification'
            self._save('specification_revised')
        return self.data['revision']

    def approve(self):
        if self.data['state'] != 'awaiting_confirmation' or self.confirm is None:
            raise ValueError('Trusted confirmation unavailable')
        shown = self._proposal()
        answer = self.confirm(copy.deepcopy(shown))
        if answer != shown or self._proposal() != shown:
            raise ValueError('Explicit confirmation did not match shown version')
        self.data['approval'] = copy.deepcopy(shown)
        self.data['state'] = 'approved'
        self._save('user_confirmed')

    def add_task(self, name, *, depends=(), writes=(), acceptance='', required_checks=('code',), profile_binding=None, complexity='standard', inputs=None, code_mode=None):
        depends, writes, required_checks = list(depends), list(writes), list(required_checks)
        if 'code' in required_checks and code_mode not in ('syntax','project_tests'): raise ValueError('Explicit code checker mode required')
        if not required_checks or set(required_checks) - {'code','text','model','browser','native'}: raise ValueError('Required checks invalid')
        if name in self.data['tasks'] or not acceptance or any(d not in self.data['tasks'] for d in depends):
            raise ValueError('Invalid task or dependencies')
        if self.data['state'] not in ('specification', 'specification_qa'):
            raise ValueError('Task edits require specification stage')
        normalized = []
        for scope in writes:
            path = Path(scope)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Unsafe write scope')
            normalized.append(path.as_posix())
        self.data['tasks'][name] = {'depends': list(depends), 'writes': normalized,
                                    'acceptance': acceptance, 'code_mode':code_mode, 'inputs':copy.deepcopy(inputs), 'profile_binding':copy.deepcopy(profile_binding), 'complexity':complexity, 'required_checks': required_checks, 'status': 'not_run', 'result': None}
        self.data['revision'] += 1
        self.data['approval'] = None
        self._save('task_added')

    def start(self, name):
        approval = self.data['approval']
        if self.data['state'] not in ('approved', 'executing') or not approval or approval != self._proposal():
            raise ValueError('Current specification approval required')
        task = self.data['tasks'][name]
        if task['status'] not in ('not_run', 'fail', 'blocked') or any(self.data['tasks'][d]['status'] != 'pass' for d in task['depends']):
            raise ValueError('Task unavailable')
        def overlap(a,b):
            return a == b or a.startswith(b.rstrip('/') + '/') or b.startswith(a.rstrip('/') + '/')
        for other in self.data['tasks'].values():
            if other['status'] == 'running' and any(overlap(a,b) for a in task['writes'] for b in other['writes']):
                raise ValueError('Write scopes overlap')
        task['status'] = 'running'
        self.data['state'] = 'executing'
        self._save('task_started')

    def finish(self, name, *, status, result):
        task = self.data['tasks'][name]
        if task['status'] != 'running' or status not in ('pass', 'fail', 'blocked') or not result:
            raise ValueError('Invalid execution result')
        if status == 'pass':
            if name not in self._verifiers or self._verifiers[name]() is not True:
                raise ValueError('Trusted current verifier required')
            evidence = result.get('review',{}) if isinstance(result,dict) else {}
            if ('code' in task['required_checks'] and evidence.get('code_mode') != task['code_mode']) or evidence.get('revision') != self.data['revision'] or evidence.get('allow_completion') is not True or any(evidence.get('checks',{}).get(c) != 'pass' for c in task.get('required_checks',[])):
                raise ValueError('Required acceptance evidence missing')
        task.update(status=status, result=copy.deepcopy(result))
        self._save('task_result')

    def complete(self):
        if self.data['state'] != 'executing':
            raise ValueError('No current execution')
        if not self.data['tasks'] or any(t['status'] != 'pass' for t in self.data['tasks'].values()):
            raise ValueError('Required task results incomplete')
        if self.data['approval'] != self._proposal():
            raise ValueError('Approval stale')
        if any(name not in self._verifiers or self._verifiers[name]() is not True for name in self.data['tasks']):
            raise ValueError('Current acceptance recheck required')
        self.data['state'] = 'complete'
        self._save('completed')
