"""Deterministic, evidence-bound round accounting; never a scientific verdict."""
from copy import deepcopy
from .util import identity, require, PMRSError
from . import scheduler, obligations


def rejection_history(snapshot, requests, tasks):
    """Keep rejected captures visible while identifying native accepted repairs."""
    failures=[]
    accepted_repairs={}
    for request in requests:
        if request.get('repair_of') and request.get('acceptance_state') in {'ACCEPTED','EXACT_DUPLICATE'}:
            accepted_repairs.setdefault(request['repair_of'],[]).append(request['request_id'])
    retired=snapshot.get('retired_consumers',{})
    for request in requests:
        if not request.get('acceptance_state','').startswith('REJECTED'):continue
        bindings=tasks[request['task_id']].get('obligation_bindings',[])
        root=request.get('repair_of',request['request_id'])
        recovered=sorted(accepted_repairs.get(root,[]))
        deferred=bool(bindings) and all(binding['binding_id'] in retired for binding in bindings)
        from .main_recovery import disposition
        maintenance=disposition(snapshot,request['request_id'])
        failures.append({'request_id':request['request_id'],'state':request['acceptance_state'],
                         'error':request.get('admission_error'),'recovered_by':recovered,
                         'capture_ref':request.get('capture_ref'),'consumer_retired':deferred,**maintenance,
                         'blocking':not recovered and not deferred and not maintenance.get('historical_execution_failure',False)})
    return failures


def describe(snapshot, instance_id, runtime=None):
    instance=snapshot['instances'][instance_id]
    mission=snapshot.get('missions',{}).get(instance.get('current_mission_id'))
    if not mission:return {'state':'NOT_STARTED','instance_id':instance_id,'model_calls':0}
    mid=mission['mission_id'];runtime=runtime or {}
    requests=[r for r in snapshot['requests'].values() if r['mission_id']==mid]
    tasks={r['task_id']:snapshot['tasks'][r['task_id']] for r in requests}
    duties=[];evidence=set();unfinished=[];unperformed=[];historical_unfinished=[];current_unfinished=[];maintenance_bindings={}
    for oid,o in sorted(snapshot['obligations'].items()):
        for c in o['definition']['consumer_bindings']:
            if c['mission_id']!=mid:continue
            bid=c['binding_id'];resolution=o['projection'].get('consumer_resolutions',{}).get(bid)
            retired=snapshot.get('retired_consumers',{}).get(bid)
            runs=[r for r in requests if any(b['binding_id']==bid for b in tasks[r['task_id']].get('obligation_bindings',[]))]
            refs=sorted(o['projection'].get('evidence_refs',[]));evidence.update(refs)
            from .main_recovery import binding_disposition
            maintenance=binding_disposition(snapshot,bid)
            if maintenance:maintenance_bindings[bid]=maintenance
            row={'obligation_id':oid,'binding_id':bid,'stage_id':c['stage_id'],'role':c['role'],
                 'criterion_ref':o['definition']['criterion_body_ref'],'resolution':resolution or 'OPEN',
                 'requests':[r['request_id'] for r in runs],'evidence_refs':refs,'deferred':bool(retired),**maintenance,
                 'current_blocking':resolution!='SATISFIED_FOR_CONSUMER' and not retired and not maintenance.get('historical_execution_failure',False)}
            duties.append(row)
            if resolution!='SATISFIED_FOR_CONSUMER':
                unfinished.append(bid)
                (historical_unfinished if maintenance.get('historical_execution_failure') else current_unfinished).append(bid)
            if not runs:unperformed.append(bid)
    remaining=min(scheduler.budget_remaining(snapshot,mission['budget_grant_id']),scheduler.project_remaining(snapshot))
    plan=scheduler.plan(snapshot,[instance_id],{'max_workers':snapshot.get('max_workers',1),'mission_policies':True})
    ignored={'CONSUMER_SATISFIED','CONSUMER_RETIRED'}
    reasons=[]
    for wait in plan['waits']:
        if wait.get('code') in ignored:continue
        maintenance=maintenance_bindings.get(wait.get('binding_id'),{})
        if not maintenance and wait.get('request_id'):
            from .main_recovery import disposition
            maintenance=disposition(snapshot,wait['request_id'])
        reasons.append({**deepcopy(wait),**maintenance,'current_blocking':not maintenance.get('historical_execution_failure',False)})
    current_reasons=[reason for reason in reasons if reason['current_blocking']]
    auto={}
    if mission['authorized_scope'].get('autoflow'):
        from . import autoflow
        auto=autoflow.status(snapshot,instance_id)
    failures=rejection_history(snapshot,requests,tasks)
    from .incidents import current_fault
    fault=current_fault(snapshot,instance_id)
    pending={r['execution_state'] for r in requests if not r.get('fenced')}
    control=instance.get('run_control',{})
    if control.get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5'}:state=control['state']
    elif control.get('state')=='COMPLETE':state='COMPLETE'
    elif instance['status']!='ACTIVE':state='PAUSED' if instance['status']=='PAUSED' else 'ENDED'
    elif 'UNKNOWN' in pending:state='UNKNOWN'
    elif pending & {'SENT','RESERVED'}:state='RUNNING'
    elif runtime.get('state')=='RESOURCE_WAIT':state='WAITING_RESOURCE'
    elif 'CAPTURED' in pending:state='CAPTURED'
    elif runtime.get('state')=='FAULT':state='FAULT'
    elif fault:state='FAULT'
    elif plan['selected'] or plan['actions']:state='READY'
    elif auto.get('waiting_human'):state='HUMAN_INPUT_REQUIRED'
    elif remaining<=0 and (current_unfinished or auto.get('missing')):state='BUDGET_EXHAUSTED'
    elif any('DEPEND' in r.get('code','') or r.get('code') in {'P7_BRANCH_DISPOSITION_REQUIRED'} for r in current_reasons):state='WAITING_DEPENDENCY'
    elif any(r.get('state')=='REJECT' for r in current_reasons):state='FAULT'
    elif any(failure['blocking'] for failure in failures):state='FAULT'
    elif runtime.get('report_waits'):state='WAITING_REPORT'
    elif auto.get('enabled') and not auto.get('complete'):state='HUMAN_INPUT_REQUIRED'
    else:state='READY_FOR_DECISION'
    produced=sorted({p['record_ref'] for p in snapshot.get('production_events',{}).values()
                     if p.get('task_id') in tasks})
    frontier=sorted(c['statement_ref'] for c in snapshot.get('candidates',{}).values() if c['instance_id']==instance_id)
    return {'schema':'pmrs.round-account/1','instance_id':instance_id,'mission_id':mid,
            'stage_id':{'TRH':'P13','FDH':'D5','SURVEY':'S7'}[instance['kind']],
            'state':state,'workflow_kind':instance['kind'],'remaining_calls':None if remaining==float('inf') else remaining,
            'actual_requests':[{'request_id':r['request_id'],'task_id':r['task_id'],'execution_state':r['execution_state'],
                               'acceptance_state':r['acceptance_state'],'capture_ref':r.get('capture_ref')} for r in sorted(requests,key=lambda r:r['request_id'])],
            'duties':duties,'unfinished_bindings':unfinished,'unperformed_bindings':unperformed,
            'current_unfinished_bindings':current_unfinished,'historical_unfinished_bindings':historical_unfinished,
            'produced_refs':produced,'evidence_refs':sorted(evidence),'candidate_frontier':frontier,
            'failures':failures,'waiting_reasons':reasons,'autoflow':auto,
            'resource_waits':deepcopy(runtime.get('waiting_requests',[])) if state=='WAITING_RESOURCE' else [],
            'fault':runtime.get('error') or fault if state=='FAULT' else None,
            'formal_report_requested':bool(snapshot.get('active_reports',{}).get(instance_id)),
            'scientific_completion':control.get('state')=='COMPLETE','round_work_complete':bool(auto.get('complete')),
            'round_number':control.get('round_number',1),'target_ref':instance.get('target_ref'),
            'run_control':deepcopy(control),
            'next_decision':'HUMAN' if state in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','PAUSED','ENDED'} else
                'MAIN' if instance['kind'] in {'TRH','FDH'} else 'HOST',
            'model_calls':0}


def record(store, instance_id, runtime=None):
    """Persist one stable progress account, without inventing a human decision."""
    from . import execution
    snapshot=store.read_snapshot();summary=describe(snapshot,instance_id,runtime)
    if summary['state'] in {'NOT_STARTED','RUNNING','READY','PAUSED','WAITING_RESOURCE','CAPTURED'}:
        return summary
    did=identity(summary,'DELIVERY-')
    if did not in snapshot.get('round_deliveries',{}):
        store.commit_execution(execution.event('ROUND_ACCOUNTED',{'instance_id':instance_id,
            'mission_id':summary['mission_id'],'basis_commit':snapshot['knowledge_commit'],
            'runtime':{k:deepcopy(v) for k,v in (runtime or {}).items() if k in {'state','report_waits','error'}},
            'delivery_id':did,'summary':summary}))
    return {**summary,'delivery_id':did}


def apply(snapshot,payload):
    expected=describe(snapshot,payload['instance_id'],payload.get('runtime'))
    require(payload['basis_commit']==snapshot['knowledge_commit'] and payload['summary']==expected
            and payload['mission_id']==expected['mission_id'] and payload['delivery_id']==identity(expected,'DELIVERY-'),
            'STALE_READ','Round account must describe the exact current native evidence')
    require(expected['state'] not in {'NOT_STARTED','RUNNING','READY','PAUSED','WAITING_RESOURCE','CAPTURED'},
            'EXECUTION_EVENT_INVALID','Pending execution is not a delivered round')
    row=deepcopy(payload)
    previous=next((r for r in reversed(list(snapshot.get('round_deliveries',{}).values())) if r.get('instance_id')==payload['instance_id'] and r.get('summary',{}).get('main_capture_ref')), {})
    previous_body=previous.get('report_body') or previous.get('summary',{}).get('report_body','')
    row['report_body']=(f"# Research status: {expected['state']}\n\n"
        f"Original target: {expected.get('target_ref')}\nRound: {expected.get('round_number')}\n"
        f"Remaining PMRS top-level calls: {expected['remaining_calls']}\n\n"
        f"Scientific completion: {expected['scientific_completion']}\n"
        f"Open responsibilities: {len(expected['unfinished_bindings'])} total; {len(expected['current_unfinished_bindings'])} current; "
        f"{len(expected['historical_unfinished_bindings'])} preserved after maintenance successor admission; unperformed: {len(expected['unperformed_bindings'])}.\n\n"
        f"Runtime reason: {expected.get('fault') or [r for r in expected.get('waiting_reasons',[]) if r.get('current_blocking',True)] or expected['state']}\n\n"
        "This is a deterministic status account, not a new mathematical judgment.\n\n"+
        ("## Last preserved MAIN account\n\n"+previous_body if previous_body else "No MAIN round account has been delivered yet.\n"))
    snapshot.setdefault('round_deliveries',{})[payload['delivery_id']]=row
    snapshot['missions'][payload['mission_id']]['delivery_ref']=payload['delivery_id']
