"""Deterministic, evidence-bound round accounting; never a scientific verdict."""
from copy import deepcopy
from .util import identity, require, PMRSError
from . import scheduler, obligations


def describe(snapshot, instance_id, runtime=None):
    instance=snapshot['instances'][instance_id]
    mission=snapshot.get('missions',{}).get(instance.get('current_mission_id'))
    if not mission:return {'state':'NOT_STARTED','instance_id':instance_id,'model_calls':0}
    mid=mission['mission_id'];runtime=runtime or {}
    requests=[r for r in snapshot['requests'].values() if r['mission_id']==mid]
    tasks={r['task_id']:snapshot['tasks'][r['task_id']] for r in requests}
    duties=[];evidence=set();unfinished=[];unperformed=[]
    for oid,o in sorted(snapshot['obligations'].items()):
        for c in o['definition']['consumer_bindings']:
            if c['mission_id']!=mid:continue
            bid=c['binding_id'];resolution=o['projection'].get('consumer_resolutions',{}).get(bid)
            retired=snapshot.get('retired_consumers',{}).get(bid)
            runs=[r for r in requests if any(b['binding_id']==bid for b in tasks[r['task_id']].get('obligation_bindings',[]))]
            refs=sorted(o['projection'].get('evidence_refs',[]));evidence.update(refs)
            row={'obligation_id':oid,'binding_id':bid,'stage_id':c['stage_id'],'role':c['role'],
                 'criterion_ref':o['definition']['criterion_body_ref'],'resolution':resolution or 'OPEN',
                 'requests':[r['request_id'] for r in runs],'evidence_refs':refs,'deferred':bool(retired)}
            duties.append(row)
            if resolution!='SATISFIED_FOR_CONSUMER':unfinished.append(bid)
            if not runs:unperformed.append(bid)
    remaining=min(scheduler.budget_remaining(snapshot,mission['budget_grant_id']),scheduler.project_remaining(snapshot))
    plan=scheduler.plan(snapshot,[instance_id],{'max_workers':snapshot.get('max_workers',1),'mission_policies':True})
    ignored={'CONSUMER_SATISFIED','CONSUMER_RETIRED'}
    reasons=[w for w in plan['waits'] if w.get('code') not in ignored]
    auto={}
    if mission['authorized_scope'].get('autoflow'):
        from . import autoflow
        auto=autoflow.status(snapshot,instance_id)
    failures=[{'request_id':r['request_id'],'state':r['acceptance_state'],'error':r.get('admission_error')}
              for r in requests if r.get('acceptance_state','').startswith('REJECTED')]
    pending={r['execution_state'] for r in requests if not r.get('fenced')}
    if instance['status']!='ACTIVE':state='PAUSED' if instance['status']=='PAUSED' else 'ENDED'
    elif 'UNKNOWN' in pending:state='UNKNOWN'
    elif pending & {'SENT','RESERVED'}:state='RUNNING'
    elif runtime.get('state')=='RESOURCE_WAIT':state='WAITING_RESOURCE'
    elif 'CAPTURED' in pending:state='CAPTURED'
    elif runtime.get('state')=='FAULT':state='FAULT'
    elif plan['selected'] or plan['actions']:state='READY'
    elif auto.get('waiting_human'):state='HUMAN_INPUT_REQUIRED'
    elif remaining<=0 and (unfinished or auto.get('missing')):state='BUDGET_EXHAUSTED'
    elif any('DEPEND' in r.get('code','') or r.get('code') in {'P7_BRANCH_DISPOSITION_REQUIRED'} for r in reasons):state='WAITING_DEPENDENCY'
    elif any(r.get('state')=='REJECT' for r in reasons):state='FAULT'
    elif failures:state='FAULT'
    elif runtime.get('report_waits'):state='WAITING_REPORT'
    elif auto.get('enabled') and not auto.get('complete'):state='HUMAN_INPUT_REQUIRED'
    else:state='READY_FOR_DECISION'
    produced=sorted({p['record_ref'] for p in snapshot.get('production_events',{}).values()
                     if p.get('task_id') in tasks})
    frontier=sorted(c['statement_ref'] for c in snapshot.get('candidates',{}).values() if c['instance_id']==instance_id)
    return {'schema':'pmrs.round-account/1','instance_id':instance_id,'mission_id':mid,
            'stage_id':{'TRW':'P13','TFDW':'D5','SURVEY':'S7'}[instance['kind']],
            'state':state,'workflow_kind':instance['kind'],'remaining_calls':None if remaining==float('inf') else remaining,
            'actual_requests':[{'request_id':r['request_id'],'task_id':r['task_id'],'execution_state':r['execution_state'],
                               'acceptance_state':r['acceptance_state'],'capture_ref':r.get('capture_ref')} for r in sorted(requests,key=lambda r:r['request_id'])],
            'duties':duties,'unfinished_bindings':unfinished,'unperformed_bindings':unperformed,
            'produced_refs':produced,'evidence_refs':sorted(evidence),'candidate_frontier':frontier,
            'failures':failures,'waiting_reasons':reasons,'autoflow':auto,
            'resource_waits':deepcopy(runtime.get('waiting_requests',[])) if state=='WAITING_RESOURCE' else [],
            'fault':runtime.get('error') if state=='FAULT' else None,
            'formal_report_requested':bool(snapshot.get('active_reports',{}).get(instance_id)),
            'scientific_completion':False,'next_decision':'HUMAN_ONLY','model_calls':0}


def record(store, instance_id, runtime=None):
    """Persist one stable progress account, without inventing a human decision."""
    from . import execution
    snapshot=store.read_snapshot();summary=describe(snapshot,instance_id,runtime)
    if summary['state'] in {'NOT_STARTED','RUNNING','READY','PAUSED','ENDED','WAITING_RESOURCE','CAPTURED','UNKNOWN'}:
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
    require(expected['state'] not in {'NOT_STARTED','RUNNING','READY','PAUSED','ENDED','WAITING_RESOURCE','CAPTURED','UNKNOWN'},
            'EXECUTION_EVENT_INVALID','Pending execution is not a delivered round')
    snapshot.setdefault('round_deliveries',{})[payload['delivery_id']]=deepcopy(payload)
    snapshot['missions'][payload['mission_id']]['delivery_ref']=payload['delivery_id']
