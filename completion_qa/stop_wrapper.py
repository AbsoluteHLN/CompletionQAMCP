"""Opt-in local command hook adapter. Never registers itself with a host."""
import argparse
import json
import sys
from pathlib import Path
from .core import Engine
from .host import simulate_stop

def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--root', required=True)
        parser.add_argument('--artifact', action='append', required=True)
        parser.add_argument('--check', action='append', required=True)
        parser.add_argument('--profile', default='short_reply')
        parser.add_argument('--scope', choices=['artifacts', 'repository'], default='artifacts')
        args = parser.parse_args()
        payload = json.loads(sys.stdin.read(65537))
        if not isinstance(payload, dict) or payload.get('hook_event_name') != 'Stop' or type(payload.get('stop_hook_active')) is not bool:
            raise ValueError('Expected official Stop input with boolean stop_hook_active')
        def run():
            engine = Engine(Path(args.root))
            plan = engine.plan(args.artifact, args.check, args.profile, args.scope)
            for check in args.check:
                engine.run(plan['plan_id'], check)
            return engine.gate(plan['plan_id'])
        result = simulate_stop(run, stop_hook_active=payload['stop_hook_active'])
        print(json.dumps(result))
    except (Exception, SystemExit):
        print(json.dumps({'decision':'block','reason':'Completion review input/configuration/runtime error; manual review required'}))
    # JSON block is the command-hook protocol. This program must not use a
    # generic error exit that a host may ignore.
    return 0

if __name__ == '__main__':
    main()
