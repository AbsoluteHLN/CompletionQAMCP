"""Local explicit actions. No automatic user confirmation through model inputs."""
import argparse
import json
from pathlib import Path
from .evidence import Review
from .workflow import Workflow

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 c=sub.add_parser('check');c.add_argument('--root',required=True);c.add_argument('--artifact',action='append',required=True);c.add_argument('--revision',type=int,required=True)
 s=sub.add_parser('status');s.add_argument('--state',required=True)
 t=sub.add_parser('text');t.add_argument('file');t.add_argument('--profile',default='conversation_summary');t.add_argument('--candidate')
 w=sub.add_parser('wizard');w.add_argument('--root',required=True);w.add_argument('--state',required=True);w.add_argument('--artifact',action='append',required=True)
 f=sub.add_parser('profiles');f.add_argument('--store',required=True);f.add_argument('--import-file')
 r=sub.add_parser('resume');r.add_argument('--state',required=True)
 a=p.parse_args()
 if a.command=='resume':
  from .interactive import resume
  result=resume(a.state)
 elif a.command=='profiles':
  from .profiles import load_profiles,save_profiles,import_profiles
  old=load_profiles(a.store) if Path(a.store).exists() else ()
  if a.import_file:
   profiles=import_profiles(Path(a.import_file).read_text(encoding="utf-8"))
   save_profiles(a.store,profiles,expected_revisions={p.profile_id:p.profile_revision for p in old} if Path(a.store).exists() else None)
  else: profiles=old
  result={'profiles':[p.to_dict() for p in profiles],'validation':'schema_only','host_validation':'not_run'}
 elif a.command=='wizard':
  from .interactive import run
  result=run(state=a.state,root=a.root,artifacts=a.artifact)
 elif a.command=='check':
  r=Review(a.root,a.artifact,a.revision);r.syntax();result=r.gate(['code'])
 elif a.command=='status':
  if not Path(a.state).exists():raise ValueError('State not found')
  w=Workflow(a.state);result={'state':w.data['state'],'revision':w.data['revision'],'events':w.data['events']}
 else:
  from .editorial import review
  result=review(Path(a.file).read_text(encoding="utf-8"),a.profile,candidate=Path(a.candidate).read_text(encoding="utf-8") if a.candidate else None)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
