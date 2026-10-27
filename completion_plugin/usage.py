"""Local attempt accounting and bounded progress supervision."""
import math
import copy
import json
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone


def _source_of(row):
    """Measurement source key; ledgers written before the rename keep 'source'."""
    return row.get('measurement_source', row.get('source'))


class Ledger:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.attempts = json.loads(self.path.read_text(encoding="utf-8")) if self.path and self.path.exists() else []
        if not isinstance(self.attempts,list) or any(not isinstance(r,dict) or not r.get('attempt_id') or _source_of(r) not in ('actual','estimated','unknown') or r.get('status') not in ('pass','fail','blocked') for r in self.attempts):
            raise ValueError('Damaged usage ledger')
        self._loaded=copy.deepcopy(self.attempts)

    def record(self, *, task, model, status, tokens=None, cost=None, currency=None,
               measurement_source='unknown', unknown_reason=None, provider=None,
               run_id=None, operation=None, started_at=None, attempt_id=None):
        if measurement_source not in ('actual', 'estimated', 'unknown') or status not in ('pass', 'fail', 'blocked'):
            raise ValueError('Invalid measurement')
        if measurement_source == 'unknown' and (tokens is not None or cost is not None):
            raise ValueError('Unknown usage cannot have numeric values')
        if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v < 0) for v in (tokens,cost)):
            raise ValueError('Invalid amount')
        if cost is not None and not currency: raise ValueError('Currency required')
        for field, value in (('provider', provider), ('run_id', run_id), ('operation', operation),
                             ('unknown_reason', unknown_reason)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError('Invalid ' + field)
        started = None
        if started_at is not None:
            if not isinstance(started_at, datetime) or started_at.tzinfo is None or started_at.utcoffset() is None:
                raise ValueError('Started time must be timezone-aware')
            started = started_at.astimezone(timezone.utc).isoformat()
        # Missing billing values stay null with a stated reason; never zero.
        if unknown_reason is None:
            if measurement_source == 'unknown':
                unknown_reason = 'usage_not_reported'
            elif tokens is None or cost is None:
                unknown_reason = 'partial_measurement'
        attempt_id=attempt_id or uuid4().hex
        if any(r['attempt_id']==attempt_id for r in self.attempts): raise ValueError('Duplicate attempt')
        row = dict(attempt_id=attempt_id,task=task, model=model, provider=provider, status=status,
                   operation=operation, run_id=run_id, tokens=tokens, cost=cost,
                   currency=currency, measurement_source=measurement_source,
                   unknown_reason=unknown_reason, started_at=started,
                   ended_at=datetime.now(timezone.utc).isoformat())
        if self.path:
            from .locking import writer_lock
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with writer_lock(self.path.with_name(self.path.name+'.lock')):
                current=json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
                if current != self._loaded: raise ValueError('Usage ledger changed; reload')
                temp=self.path.with_name(self.path.name+'.'+uuid4().hex+'.tmp')
                temp.write_text(json.dumps(self.attempts+[row],ensure_ascii=False), encoding="utf-8")
                os.replace(temp,self.path)
        self.attempts.append(row)
        self._loaded=copy.deepcopy(self.attempts)
        return dict(row)

    def budget_allows(self, ceiling, currency, *, next_max_cost=None):
        if type(ceiling) not in (int,float) or not math.isfinite(ceiling) or ceiling < 0: return False
        if type(next_max_cost) not in (int,float) or not math.isfinite(next_max_cost) or next_max_cost < 0: return False
        if not self.attempts: return False
        if any(_source_of(r) != 'actual' or r['cost'] is None or r['currency'] != currency for r in self.attempts):
            return False
        return sum(r['cost'] for r in self.attempts) + next_max_cost <= ceiling


class Supervisor:
    def __init__(self): self.blockers = {}; self.progress = []; self.noise = {}
    def observe(self, task, *, kind, detail):
        if kind not in ('artifact', 'acceptance', 'research_source', 'active_build', 'blocker', 'noise'):
            raise ValueError('Unknown observation')
        if not detail: raise ValueError('Observation evidence required')
        if kind == 'blocker':
            previous, count = self.blockers.get(task, (None, 0))
            count = count + 1 if detail == previous else 1
            self.blockers[task] = (detail, count)
            return {'action': 'pause' if count >= 2 else 'inspect', 'same_blocker_count': count}
        if kind == 'noise':
            self.noise[task] = self.noise.get(task,0)+1
            if self.noise[task] >= 2:return {'action':'pause','reason':'No useful progress'}
        if kind != 'noise':
            self.noise[task] = 0
            self.progress.append((task, kind, detail))
            self.blockers.pop(task, None)
        return {'action': 'wait' if kind == 'active_build' else 'continue' if kind != 'noise' else 'inspect'}

    def model_check(self, task, *, reviewer=None, authorize=None, ledger=None, model='unknown'):
        """Optional cheap host review at scheduler checkpoints; never self-schedules."""
        if reviewer is None or authorize is None or authorize(task,model) is not True:
            return {'status':'blocked','reason':'Authorized supervisory host unavailable'}
        if getattr(self,'_reviewing',False):return {'status':'blocked','reason':'Recursive supervision rejected'}
        self._reviewing=True
        try:
            response=reviewer({'task':task,'progress':list(self.progress),'blocker':self.blockers.get(task)})
            if not isinstance(response,dict) or response.get('action') not in ('continue','inspect','pause'):
                raise ValueError('Invalid supervisory response')
            if ledger is not None:
                usage=response.get('usage') or {}
                ledger.record(task=task,model=model,status='pass',operation='supervisory_review',
                    tokens=usage.get('tokens'),cost=usage.get('cost'),currency=usage.get('currency'),
                    measurement_source=usage.get('measurement_source',usage.get('source','unknown')))
            # A model opinion cannot turn a repeated blocker into completion.
            if self.blockers.get(task,(None,0))[1]>=2 or self.noise.get(task,0)>=2:
                response=dict(response,action='pause')
            return {'status':'reviewed','action':response['action'],'opinion':response.get('reason'), 'allow_completion':False}
        except Exception as exc:
            if ledger is not None:ledger.record(task=task,model=model,status='fail',operation='supervisory_review')
            return {'status':'blocked','reason':type(exc).__name__}
        finally:self._reviewing=False
