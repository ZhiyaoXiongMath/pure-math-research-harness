"""Native SETTLE and audit-clock effects with explicit persisted time only."""
from copy import deepcopy
from datetime import datetime
from .primitives import require, identity

def _cost(snapshot,request):
    # Unknown usage retains the full authorization reservation, never zero.
    if 'admission' in request:
        return 0 if request['admission']['charge']=='RELEASED' else 1
    if request['execution_state']=='CANCELLED_BEFORE_SEND':return 0
    return request.get('reserved_calls',1)

def budget_remaining(snapshot,grant_id):
    grant=snapshot.get('budget_grants',{}).get(grant_id,{})
    if grant.get('explicit_unlimited') is True:return float('inf')
    maximum=grant.get('max_calls',0)
    used=sum(_cost(snapshot,r) for r in snapshot.get('requests',{}).values() if r.get('budget_grant_id')==grant_id)
    return maximum-used if any('ownership' in i for i in snapshot.get('instances',{}).values()) else max(0,maximum-used)

def project_remaining(snapshot):
    budget=snapshot.get('project_budget',{'max_calls':0})
    if budget.get('explicit_unlimited') is True:return aggregate_project_remaining(snapshot)
    remaining=budget.get('max_calls',0)-sum(_cost(snapshot,r) for r in snapshot.get('requests',{}).values() if r.get('budget_domain','SCIENCE')=='SCIENCE')
    return min(aggregate_project_remaining(snapshot),remaining if any('ownership' in i for i in snapshot.get('instances',{}).values()) else max(0,remaining))

def aggregate_project_remaining(snapshot):
    """An optional explicitly configured total includes every request domain."""
    budget=snapshot.get('project_total_budget')
    if not budget or budget.get('explicit_unlimited') is True:return float('inf')
    remaining=budget.get('max_calls',0)-sum(_cost(snapshot,r) for r in snapshot.get('requests',{}).values())
    return remaining if any('ownership' in i for i in snapshot.get('instances',{}).values()) else max(0,remaining)

def strategy_id(iid):return identity(iid,'STRATEGY-')

def strategy_current(s,iid):return s.get('strategies',{}).get(strategy_id(iid))

DEFAULT_POLICY={'light_check_seconds':1800,'full_audit_seconds':14400,'observation_seconds':60}

def seconds(at):
    return int(datetime.fromisoformat(at.replace('Z','+00:00')).timestamp())

def policy(s,iid):
    value={**DEFAULT_POLICY,**s['instances'][iid].get('research_audit_policy',{})}
    require(all(type(v) is int and v>0 for v in value.values()),'AUDIT_POLICY_INVALID','Audit intervals must be positive integer seconds')
    return value

def phase(s,iid):
    instance=s['instances'][iid];control=instance.get('run_control',{})
    mission=s.get('missions',{}).get(instance.get('current_mission_id'),{})
    if instance.get('status')!='ACTIVE':
        reason=control.get('state') if control.get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','COMPLETE','OPEN_ENDED'} else instance.get('status')
        return {'effective':False,'reason':reason,'active_request_ids':[]}
    if control.get('state') in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5','COMPLETE','OPEN_ENDED'}:
        return {'effective':False,'reason':control['state'],'active_request_ids':[]}
    if not mission or mission.get('status')!='ACTIVE':
        return {'effective':False,'reason':'NO_ACTIVE_AUTHORIZATION','active_request_ids':[]}
    requests=[r for r in s.get('requests',{}).values() if r.get('instance_id')==iid and r.get('mission_id')==mission['mission_id']]
    active=sorted(r['request_id'] for r in requests if r.get('execution_state')=='SENT')
    # The instance clock runs once, including MAIN/internal work and live stages.
    if active:return {'effective':True,'reason':'ACTUAL_RESEARCH_IN_FLIGHT','active_request_ids':active}
    if any(r.get('execution_state')=='UNKNOWN' for r in requests):
        return {'effective':False,'reason':'TRANSPORT_UNCERTAIN','active_request_ids':[],'evidence_incomplete':True}
    if min(budget_remaining(s,mission['budget_grant_id']),project_remaining(s))<=0:
        return {'effective':False,'reason':'BUDGET_EXHAUSTED','active_request_ids':[]}
    st=strategy_current(s,iid) or {};wait=st.get('wait_condition') or {}
    if st.get('next_action')=='WAIT' or control.get('state')=='WAITING_CONDITION':
        return {'effective':False,'reason':wait.get('kind') or 'EXPLICIT_WAIT','active_request_ids':[]}
    if any(r.get('execution_state') in {'PREPARED','RESERVED'} for r in requests):
        return {'effective':False,'reason':'RESOURCE_ADMISSION_WAIT','active_request_ids':[]}
    return {'effective':False,'reason':'NO_OBSERVED_ACTIVE_RESEARCH','active_request_ids':[]}

def _append_interval(clock,start,end,previous):
    delta=max(0,seconds(end)-seconds(start))
    if not delta:return
    if previous.get('effective'):clock['effective_seconds']+=delta
    row={'from':start,'to':end,'seconds':delta,'effective':previous.get('effective',False),
        'reason':previous.get('reason'),'evidence_request_ids':previous.get('active_request_ids',[])}
    if previous.get('evidence_incomplete'):
        row['evidence_incomplete']=True
        clock.setdefault('uncertainty_intervals',[]).append(deepcopy(row))
    intervals=clock.setdefault('intervals',[])
    if intervals and all(intervals[-1].get(k)==row.get(k) for k in ('effective','reason','evidence_request_ids','evidence_incomplete')) and intervals[-1]['to']==start:
        intervals[-1]['to']=end;intervals[-1]['seconds']+=delta
    else:intervals.append(row)

def transition(s,iid,*,at):
    """Pure reducer hook after an actual control or execution state change."""
    if s['instances'][iid]['kind'] not in {'TRH','FDH'}:return None
    clock=s.setdefault('research_clocks',{}).get(iid)
    if not clock:return None  # First maintenance reconstructs the immutable journal.
    if seconds(at)<seconds(clock['last_observed_at']):return clock
    elapsed=seconds(at)-seconds(clock['last_observed_at'])
    if elapsed>2*clock['policy']['observation_seconds']:
        clock.setdefault('uncertainty_intervals',[]).append({'from':clock['last_observed_at'],'to':at,'seconds':elapsed,
            'reason':'BACKEND_OBSERVATION_GAP','accounting':'Persisted research phase used; continuous process activity was not observed here.'})
    _append_interval(clock,clock['last_observed_at'],at,clock['phase'])
    clock['last_observed_at']=at;clock['phase']=phase(s,iid);clock['policy']=policy(s,iid)
    clock['deadline_effective_seconds']=clock['last_full_audit_effective_seconds']+clock['policy']['full_audit_seconds']
    return clock

def _request(s,rid):
    require(rid in s.get('requests',{}),'REQUEST_UNKNOWN',rid);return s['requests'][rid]

def event(payload,*,event_id=None):
    """Construct original SETTLE identity; caller supplies persisted time."""
    payload=deepcopy(payload)
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':'SETTLE','payload':payload}
    e['event_id']=event_id or identity(e,'EXEC-EVENT-');return e


def apply_event(snapshot,e):
    old=snapshot.get('execution_events',{}).get(e.get('event_id'))
    if old:
        require(old==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Execution event identity conflict');return deepcopy(snapshot)
    require(set(e)=={'event_id','actor','capability_ref','event_type','payload'} and e['event_type']=='SETTLE',
            'EXECUTION_EVENT_INVALID','Typed execution event required')
    cap=snapshot.get('capabilities',{}).get(e['capability_ref'],{})
    require(e['actor']=='host' and cap.get('actor')=='host','AUTHORIZATION_REQUIRED','Execution requires host capability')
    s=deepcopy(snapshot);p=e['payload']
    r=_request(s,p['request_id'])
    require(r['execution_state'] in {'CAPTURED','SETTLED'},'EXECUTION_TRANSITION_INVALID','Capture must precede settlement')
    require(p.get('acceptance_state') in {'ACCEPTED','REJECTED_STALE','REJECTED_CONTRACT','EXACT_DUPLICATE'},'EXECUTION_EVENT_INVALID','Exact admission disposition required')
    if r['execution_state']=='SETTLED':require(r['receipt_ref']==p.get('receipt_ref'),'ALREADY_SETTLED_CONTENT_CONFLICT','Original settlement required')
    else:
        r.update(execution_state='SETTLED',acceptance_state=p['acceptance_state'],receipt_ref=p.get('receipt_ref'),admission_error=p.get('error'))
        if p.get('diagnostic'):r['admission_diagnostic']=deepcopy(p['diagnostic'])
    if p.get('issued_at'):
        request=s.get('requests',{}).get(p.get('request_id'))
        iid=(request or {}).get('instance_id') or p.get('instance_id') or p.get('task',{}).get('instance_id')
        if iid in s.get('instances',{}):transition(s,iid,at=p['issued_at'])
    s.setdefault('execution_events',{})[e['event_id']]=deepcopy(e);return s
