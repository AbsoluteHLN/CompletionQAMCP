// SYNTHETIC services only: this does not load the DSH runtime.
import test from 'node:test';
import assert from 'node:assert/strict';
import { install } from './bridge.js';
import { EMPTY_PROFILES, parseProfiles, importPreview, profileStatus } from './profiles.js';
function fixture() {
 const root={id:'root'}, members=[], calls=[], events={}, actions=new Map(); let guard, allow=true;
 const host={probe:()=>({version:'fixture'}),supportsVersion:v=>v==='fixture',configRevision:()=>1,
 authorize:()=>allow, resolveRootAgent:()=>root, manages:a=>a===root,registerBridge:()=>{},
 invalidateValidation:r=>calls.push(r),actions:{get:k=>structuredClone(actions.get(k)),
 put:(k,v)=>actions.set(k,structuredClone(v)), values:()=>[...actions.values()]}};
 const ctx={completionQAHost:host,on:(e,f)=>events[e]=f,tools:{guard:f=>guard=f},agentTeams:{
 membership:a=>({root:a}),listMembers:()=>members,
 spawnTeammate:async(a,r)=>{assert.equal(a,root);calls.push(r);const member={name:r.name,status:'running'};members.push(member);return {member};},
 sendMessage:async()=>({messageId:'m'}),interrupt:()=>({previousStatus:'running'}),
 updateTask:(a,r)=>r}};
 const config={profilesJson:{get:()=>EMPTY_PROFILES},inheritModel:{get:()=>true},maxConcurrent:{get:()=>4}};
 const bridge=install(ctx,config);
 return {bridge,ctx,host,root,calls,events,config,guard:e=>guard(e),deny:()=>allow=false};
}
const request=name=>({name,description:'fixture',prompt:[],provider:'backend',context:'fresh',signal:new AbortController().signal});
test('root Agent identity and member reuse; unsupported model blocked',async()=>{
 const f=fixture();await f.bridge.ensureMember('root',request('w'));
 assert.equal((await f.bridge.ensureMember('root',request('w'))).status,'reused');assert.equal(f.calls.length,1);
 assert.equal('model' in f.calls[0],false);
 await assert.rejects(f.bridge.ensureMember('root',request('x'),{requestedModel:'x'}));
});
test('monotonic managed-agent guard',()=>{
 const f=fixture();assert.equal(f.guard({agent:f.root}),undefined);f.deny();
 assert.equal(f.guard({agent:f.root}),'CompletionQA approval required');assert.equal(f.guard({agent:{}}),undefined);
});
test('uncertain messages never retry including fresh IDs',async()=>{
 const f=fixture();let count=0;f.ctx.agentTeams.sendMessage=async()=>{count++;throw Error('timeout');};
 const request={target:'w',content:[]};
 assert.equal((await f.bridge.sendMessage('root',request,'a')).status,'uncertain');
 await f.bridge.sendMessage('root',request,'a');await assert.rejects(f.bridge.sendMessage('root',request,'b'));
 assert.equal(count,1);
});
test('uncertain spawns do not retry and retain scope reservations',async()=>{
 const f=fixture();let count=0;f.ctx.agentTeams.spawnTeammate=async()=>{count++;throw Error('timeout');};
 await assert.rejects(f.bridge.ensureMember('root',request('w'),{writeScopes:['src']}));
 await assert.rejects(f.bridge.ensureMember('root',request('w'),{writeScopes:['src']}));
 await assert.rejects(f.bridge.ensureMember('root',request('x'),{writeScopes:['src/a']}));assert.equal(count,1);
});
test('form CAS and volatile invalidation',()=>{
 const f=fixture();let rev;f.bridge.mutateConfig({mutate:(ops,r)=>rev=r},[],7);assert.equal(rev,7);
 f.events['loader/volatile-update']();assert.equal(f.calls.at(-1),'config_changed');
});
test('interrupt retains scope and task CAS is forwarded',async()=>{
 const f=fixture();await f.bridge.ensureMember('root',request('w'),{writeScopes:['src']});f.bridge.interrupt('root','w');
 await assert.rejects(f.bridge.ensureMember('root',request('x'),{writeScopes:['src/a']}));
 assert.equal(f.bridge.updateTask('root',{taskId:'t',expectedRevision:2,action:'complete'}).expectedRevision,2);
});
test('missing or unsupported integration fails closed; no real-host claim',()=>{
 assert.throws(()=>install({},{}));const f=fixture();f.host.supportsVersion=()=>false;assert.throws(()=>install(f.ctx,{}));
 assert.equal(f.bridge.capabilities().realHostValidation,'not_run');
});
test('actual entry exports Config/apply with a clearly synthetic schema dependency', async () => {
 const {registerHooks}=await import('node:module');
 const fake='data:text/javascript,'+encodeURIComponent(`const field=()=>({default(){return this},volatile(){return this},step(){return this},min(){return this},description(){return this}});export default {transform:()=>field(),string:field,object:fields=>({fixture:true,fields}),boolean:field,number:field};`);
 const hooks=registerHooks({resolve(specifier,context,next){return specifier==='@deepseek-ai/schemastery'?{url:fake,shortCircuit:true}:next(specifier,context);}});
 try {
  const entry=await import('./index.js');assert.equal(entry.Config.fixture,true);
  assert.deepEqual(Object.keys(entry.Config.fields),['profilesJson','inheritModel','maxConcurrent']);
  assert.equal(typeof entry.apply,'function');assert.ok(entry.inject.includes('completionQAHost'));
 } finally {hooks.deregister();}
});
function sampleProfile(name='first') {
 return {schema_version:1,profile_id:name,profile_revision:1,name,
 created_at:'2026-10-19T00:00:00Z',modified_at:'2026-10-19T00:00:00Z',
 routes:[{route_id:'main',provider:'host',model:'intended-model',effort:'high',auth_ref:'host/default'},
 {route_id:'backup',provider:'host',model:'backup-model',effort:'low',auth_ref:'host/default'}],
 roles:[{name:'worker',route_id:'main',concurrency:1,timeout_seconds:120,fallbacks:['backup']}],
 allowlist:['main','backup'],default_role:'worker'};
}
const collection=(...profiles)=>JSON.stringify({schema_version:1,profiles});
test('multiple profiles roundtrip model effort and fallback intentions',()=>{
 const text=collection(sampleProfile(),sampleProfile('second'));
 assert.equal(parseProfiles(text).profiles.length,2);
 assert.equal(parseProfiles(text).profiles[0].routes[0].effort,'high');
 const states=profileStatus(text);assert.equal(states[0].schema,'validated_schema');
 assert.equal(states[0].capability,'blocked');assert.equal(states[0].smoke,'not_run');
});
test('reject unknown fields, secrets, bad effort, cycles and duplicate JSON keys',()=>{
 for(const mutate of [p=>p.api_key='secret',p=>p.routes[0].auth_ref='sk-secret',
 p=>p.routes[0].effort='ultra-unsupported',p=>p.roles[0].fallbacks=['main'],
 p=>p.allowlist=[],p=>p.roles[0].concurrency=0,p=>p.validation='smoke_pass']) {
  const p=sampleProfile();mutate(p);assert.throws(()=>parseProfiles(collection(p)));
 }
 assert.throws(()=>parseProfiles('{"schema_version":1,"schema_version":1,"profiles":[]}'));
 assert.throws(()=>parseProfiles('{"schema_version":1,"profiles":[],"\\u0070rofiles":[]}'));
});
test('import preview exposes replacements and deletions',()=>{
 const old=sampleProfile(),changed=sampleProfile();changed.routes[0].model='different';changed.profile_revision=2;
 const preview=importPreview(collection(old,sampleProfile('removed')),collection(changed));
 assert.equal(preview.conflicts.length,1);assert.ok(preview.changes.some(x=>x.kind==='delete'));
 assert.equal(preview.requires_confirmation,true);assert.equal(preview.validation_evidence_imported,false);
});
test('import uses owner CAS and rejects stale revision or missing authorization',()=>{
 const f=fixture();let received;const form={mutate:(...args)=>received=args};
 f.bridge.importProfiles(form,collection(sampleProfile()),1);
 assert.equal(received[1],1);assert.equal(received[0][0].path,'/profilesJson');
 assert.throws(()=>f.bridge.importProfiles(form,collection(sampleProfile()),0));
 f.deny();assert.throws(()=>f.bridge.importProfiles(form,collection(sampleProfile()),1));
});

test('saved multi-profile Config is authoritative and stale per-profile replacement blocks',()=>{
 const f=fixture();let stored=EMPTY_PROFILES;f.config.profilesJson.get=()=>stored;
 const form={mutate:(ops,rev)=>{assert.equal(rev,1);stored=ops[0].value;}};
 f.bridge.importProfiles(form,collection(sampleProfile(),sampleProfile('second')),1);
 assert.equal(f.bridge.snapshot().profiles.profiles.length,2);
 assert.equal(f.bridge.profileStatus()[1].profile_id,'second');
 const changed=sampleProfile();changed.routes[0].model='other';
 assert.throws(()=>f.bridge.importProfiles(form,collection(changed),1));
 changed.profile_revision=2;f.bridge.importProfiles(form,collection(changed),1);
 assert.equal(f.bridge.snapshot().profiles.profiles[0].profile_revision,2);
});
