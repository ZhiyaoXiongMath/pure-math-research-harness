"""Explicit recovery of an observed MAIN tool-launch failure, never science admission."""
from copy import deepcopy
from pathlib import Path
from .util import canonical,identity,loads,now,read,require,sha

SCHEMA='pmrs.main-execution-recovery/4.2.2'

def _bound(s,iid,rid,capture_ref):
    r=s.get('requests',{}).get(rid,{});t=s.get('tasks',{}).get(r.get('task_id'),{})
    require(r.get('instance_id')==iid and t.get('actor_kind')=='MAIN'
        and r.get('execution_state')=='SETTLED' and r.get('acceptance_state')=='REJECTED_CONTRACT'
        and r.get('capture_ref')==capture_ref and not r.get('fenced'),
        'MAIN_RECOVERY_NOT_ALLOWED','Recovery requires the exact settled, rejected MAIN capture')
    i=s['instances'][iid]
    require(i['status']=='PAUSED' and i.get('current_mission_id')==r['mission_id']
        and s['missions'][r['mission_id']]['status']=='ACTIVE',
        'MAIN_RECOVERY_NOT_ALLOWED','Pause the same authorized mission before explicit maintenance recovery')
    binding=s.get('native_main_bindings',{}).get(iid,{})
    turns=[v for v in s.get('native_main_turns',{}).values() if v.get('request_id')==rid]
    require(len(turns)==1 and turns[0].get('thread_id')==binding.get('thread_id')
        and turns[0].get('execution_id')==r.get('execution_id'),
        'MAIN_RECOVERY_NOT_ALLOWED','The original request must bind one actual persistent native MAIN turn')
    require(not any(v.get('request_id')==rid for name in ('input_deliveries','live_main_dispatches','production_events','strategy_proposals') for v in s.get(name,{}).values()),
        'MAIN_RECOVERY_NOT_ALLOWED','A MAIN that received dynamic material or performed admitted scientific work needs ordinary capture recovery')
    return r,t,binding,turns[0]

def verify_failure(s,iid,rid,capture_ref,raw,blob_get):
    """Verify the original native transcript, not the model's failure claim alone."""
    r,t,binding,turn=_bound(s,iid,rid,capture_ref)
    from .input_delivery import capture_binding
    capture_binding(s,rid)
    captured=blob_get(capture_ref);require(sha(captured)==capture_ref,'ORIGINAL_BYTES_MISMATCH','Original failure capture differs')
    failure=loads(captured)
    require(failure.get('request_id')==rid and failure.get('status')=='execution_failure'
        and failure.get('required_materials_read') is False and failure.get('prescribed_contract_available') is False
        and failure.get('goal_completed') is False and failure.get('stage_tasks_dispatched')==[],
        'MAIN_RECOVERY_NOT_ALLOWED','This maintenance path requires an explicit unread-material execution failure')
    rows=[loads(line) for line in raw.splitlines() if line.strip()]
    meta=[row['payload'] for row in rows if row.get('type')=='session_meta']
    require(len(meta)==1 and meta[0].get('id')==binding['thread_id'],
        'MAIN_RECOVERY_EVIDENCE_INVALID','Original rollout must belong to the persistent MAIN thread')
    starts=[n for n,row in enumerate(rows) if row.get('type')=='event_msg'
        and row.get('payload',{}).get('type')=='task_started' and row['payload'].get('turn_id')==turn['turn_id']]
    ends=[n for n,row in enumerate(rows) if row.get('type')=='event_msg'
        and row.get('payload',{}).get('type')=='task_complete' and row['payload'].get('turn_id')==turn['turn_id']]
    require(len(starts)==len(ends)==1 and starts[0]<ends[0],
        'MAIN_RECOVERY_EVIDENCE_INVALID','A complete exact original native turn is required')
    require(sha(rows[ends[0]]['payload'].get('last_agent_message','').encode())==capture_ref,
        'MAIN_RECOVERY_EVIDENCE_INVALID','Native completion must preserve the exact rejected final bytes')
    calls={};outputs={}
    for row in rows[starts[0]+1:ends[0]]:
        p=row.get('payload',{})
        require(not (row.get('type')=='event_msg' and p.get('type')=='task_started'),
            'MAIN_RECOVERY_EVIDENCE_INVALID','Overlapping native turns cannot establish absence of successful tool execution')
        if row.get('type')!='response_item':continue
        kind=p.get('type')
        if kind in {'message','reasoning'}:continue
        require(kind in {'custom_tool_call','custom_tool_call_output'}
            and p.get('internal_chat_message_metadata_passthrough',{}).get('turn_id')==turn['turn_id'],
            'MAIN_RECOVERY_EVIDENCE_INVALID','Unexpected executable output prevents tool-launch-only recovery')
        call=p.get('call_id');require(isinstance(call,str) and call,'MAIN_RECOVERY_EVIDENCE_INVALID','Exact native tool identity required')
        if kind=='custom_tool_call':
            require(p.get('name')=='exec' and call not in calls,'MAIN_RECOVERY_EVIDENCE_INVALID','Only failed code-mode launcher attempts qualify')
            calls[call]=p
        else:
            output=p.get('output','')
            require(call not in outputs and row.get('metadata',{}).get('client_authored') is False
                and isinstance(output,str) and output.startswith('failed to spawn code-mode host ')
                and '/codex-code-mode-host: No such file or directory (os error 2)' in output,
                'MAIN_RECOVERY_EVIDENCE_INVALID','Every tool output must be a native launcher failure before code execution')
            outputs[call]=p
    require(calls and set(calls)==set(outputs),'MAIN_RECOVERY_EVIDENCE_INVALID','No successful or unaccounted native tool call may be hidden')
    return {'thread_id':binding['thread_id'],'turn_id':turn['turn_id'],'objective_sha256':binding['objective_sha256'],
        'execution_id':r['execution_id'],'mission_id':r['mission_id'],'budget_grant_id':r['budget_grant_id'],
        'failed_tool_call_ids':sorted(calls),'scientific_input_read':False,'failure_kind':'NATIVE_CODE_MODE_HOST_MISSING'}

def authorize(store,iid,rid,capture_ref,repair_reason,authorization_note,*,client_action_id):
    require(all(isinstance(v,str) and v.strip() and len(v.encode())<=16000 for v in (repair_reason,authorization_note,client_action_id)),
        'MAIN_RECOVERY_AUTHORIZATION_REQUIRED','An explicit maintenance operation, repair reason and existing user authorization are required')
    s=store.read_snapshot();recovery_id=identity([rid,capture_ref],'MAIN-RECOVERY-')
    old=s.get('main_execution_recoveries',{}).get(recovery_id)
    if old:
        require(old['instance_id']==iid,'MAIN_RECOVERY_NOT_ALLOWED','Recovery belongs to the original instance')
        return {'state':'EXACT_DUPLICATE','recovery_id':recovery_id,'request_id':rid,'model_calls':0,'original_rejection_preserved':True}
    r,t,binding,turn=_bound(s,iid,rid,capture_ref)
    original=loads(store.read_blob(binding['thread_start_evidence_ref']))['thread']
    require(original.get('id')==binding['thread_id'] and original.get('path'),
        'MAIN_RECOVERY_EVIDENCE_INVALID','Recorded original native thread path is required')
    raw=read(Path(original['path']))
    evidence=verify_failure(s,iid,rid,capture_ref,raw,store.read_blob)
    # This is local executable/hash validation, not a model or synthetic probe.
    from .native_main import native_binary
    _,manifest=native_binary()
    evidence_ref=store.blob(raw);manifest_ref=store.blob(canonical(manifest))
    row={'schema':SCHEMA,'recovery_id':recovery_id,'instance_id':iid,'request_id':rid,'capture_ref':capture_ref,
        **evidence,'native_rollout_ref':evidence_ref,'native_rollout_sha256':sha(raw),
        'thread_start_evidence_ref':binding['thread_start_evidence_ref'],'repaired_runtime_manifest_ref':manifest_ref,
        'repair_reason':repair_reason,'authorization_note':authorization_note,'client_action_id':client_action_id,
        'authorized_at':now(),'disposition':'PRESERVE_REJECTION_ALLOW_ONE_NEW_MAIN','model_calls':0}
    from . import strategy
    receipt=store.commit_strategy(strategy.event('MAIN_EXECUTION_RECOVERY_AUTHORIZED',{'instance_id':iid,'mission_id':r['mission_id'],'recovery':row}))
    return {**receipt,'state':'RECOVERY_AUTHORIZED','recovery_id':recovery_id,'request_id':rid,'model_calls':0,
        'original_rejection_preserved':True,'budget_added':0,'requires_normal_continuation':True}

def apply_authorization(s,p,blob_get):
    row=p['recovery'];iid=p['instance_id'];rid=row['request_id']
    require(row['instance_id']==iid and row['mission_id']==p['mission_id']
        and row['recovery_id']==identity([rid,row['capture_ref']],'MAIN-RECOVERY-')
        and row['disposition']=='PRESERVE_REJECTION_ALLOW_ONE_NEW_MAIN'
        and all(isinstance(row.get(k),str) and row[k].strip() for k in ('repair_reason','authorization_note','client_action_id')),
        'MAIN_RECOVERY_AUTHORIZATION_REQUIRED','Exact explicit recovery authorization is required')
    raw=blob_get(row['native_rollout_ref'])
    require(sha(raw)==row['native_rollout_ref']==row['native_rollout_sha256'],'ORIGINAL_BYTES_MISMATCH','Native failure evidence changed')
    actual=verify_failure(s,iid,rid,row['capture_ref'],raw,blob_get)
    require(all(row.get(k)==v for k,v in actual.items()),'MAIN_RECOVERY_EVIDENCE_INVALID','Recovery must preserve the original failure bindings')
    runtime=blob_get(row['repaired_runtime_manifest_ref']);manifest=loads(runtime)
    require(sha(runtime)==row['repaired_runtime_manifest_ref'] and manifest.get('code_mode_host_sha256'),
        'MAIN_RECOVERY_EVIDENCE_INVALID','The repaired native runtime must include the verified tool launcher')
    old=s.setdefault('main_execution_recoveries',{}).get(row['recovery_id'])
    require(old is None or old==row,'MAIN_RECOVERY_IDENTITY_CONFLICT','A failure receives only one immutable recovery authorization')
    if old:return
    s['main_execution_recoveries'][row['recovery_id']]=deepcopy(row)
    # Preserve the earlier delivery identity while offering genuinely unread
    # original directions to the successor MAIN's freshly frozen input.
    for direction in s.get('human_directions',{}).values():
        if direction.get('request_id')==rid and direction.get('status') in {'QUEUED','DELIVERED'}:
            direction.setdefault('delivery_history',[]).append({k:deepcopy(direction.get(k)) for k in ('request_id','task_id','status','delivery_basis')})
            direction.update(status='QUEUED',request_id=None,task_id=None,delivery_basis=None,requeued_by=row['recovery_id'])

def authorized_for(s,request):
    key=identity([request['request_id'],request.get('capture_ref')],'MAIN-RECOVERY-')
    row=s.get('main_execution_recoveries',{}).get(key)
    return bool(row and row['capture_ref']==request.get('capture_ref') and row['mission_id']==request.get('mission_id'))

def pending(s,iid,mid):
    used={ref for task in s.get('tasks',{}).values() for ref in task.get('entry_basis',{}).get('main_execution_recovery_refs',[])}
    return sorted(row['recovery_id'] for row in s.get('main_execution_recoveries',{}).values()
        if row['instance_id']==iid and row['mission_id']==mid and row['recovery_id'] not in used)

def disposition(s,request_id):
    """Read-only execution lineage; never resolve the original obligation."""
    request=s.get('requests',{}).get(request_id,{})
    key=identity([request_id,request.get('capture_ref')],'MAIN-RECOVERY-')
    recovery=s.get('main_execution_recoveries',{}).get(key)
    if not recovery or not authorized_for(s,request):return {}
    result={'maintenance_recovery_ref':key,'recovery_disposition':'AUTHORIZED_AWAITING_SUCCESSOR',
        'maintenance_successor':None,'historical_execution_failure':False}
    successors=[t for t in s.get('tasks',{}).values() if key in t.get('entry_basis',{}).get('main_execution_recovery_refs',[])
        and t.get('actor_kind')=='MAIN' and t['instance_id']==request['instance_id'] and t['mission_id']==request['mission_id']]
    if len(successors)!=1:return result
    task=successors[0];successor=s.get('requests',{}).get(task['request_id'])
    if not successor:return result
    result['maintenance_successor']={k:deepcopy(successor.get(k)) for k in
        ('request_id','task_id','execution_state','acceptance_state','capture_ref')}
    if successor.get('fenced') or successor['execution_state']=='CANCELLED_BEFORE_SEND':
        result['recovery_disposition']='SUCCESSOR_CANCELLED_REQUIRES_ATTENTION'
    else:
        result.update(recovery_disposition='HISTORICAL_FAILURE_WITH_MAINTENANCE_SUCCESSOR',historical_execution_failure=True)
    return result

def binding_disposition(s,binding_id):
    requests=[r for r in s.get('requests',{}).values() if any(b['binding_id']==binding_id
        for b in s['tasks'][r['task_id']].get('obligation_bindings',[]))]
    if len(requests)!=1:return {}
    return disposition(s,requests[0]['request_id'])
