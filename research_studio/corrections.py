"""Explicit human correction contracts; no scope, budget or request reset."""
from copy import deepcopy
from .util import identity, require, sha
from . import obligations as O


def contract(snapshot,iid,bid,instruction,success):
    instance=snapshot['instances'][iid];mid=instance.get('current_mission_id')
    require(instance['status']!='ENDED' and mid in snapshot['missions'],'AUTHORIZATION_REQUIRED','A current authorized round is required')
    require(all(isinstance(t,str) and 0<len(t.strip())<=12000 for t in (instruction,success)),
            'CORRECTION_INVALID','Describe the concrete correction and its success criterion')
    matches=[(o,c) for o in snapshot['obligations'].values() for c in o['definition']['consumer_bindings']
             if c['binding_id']==bid and c['instance_id']==iid and c['mission_id']==mid]
    require(len(matches)==1,'CORRECTION_INVALID','Select a responsibility from the current round')
    original,c=matches[0];d=original['definition']
    require(d['type'] not in {'REPORT','CONTROL'} and not c['role'].startswith('REPORT_'),
            'CORRECTION_INVALID','Use the report revision operation for manuscript corrections')
    text='Human-requested correction (an instruction to investigate, not a mathematical verdict):\n'+instruction+'\nSuccess criterion:\n'+success
    criterion=sha(text.encode());oid=identity({'original_duty':d['obligation_id'],'criterion':criterion,'targets':d['target_refs']},'OB-')
    correction_id=identity({'instance':iid,'mission':mid,'obligation':oid},'CORRECTION-')
    binding=deepcopy(c)
    for key in ('visit_id','report_context','ready_since'):binding.pop(key,None)
    binding.update(binding_id='BINDING-'+correction_id,retry_grant_id='RETRY-'+correction_id,
                   method_ref='EXPLICIT_HUMAN_CORRECTION',unlocks=True)
    binding.setdefault('entry_basis',{})['human_correction']={'correction_id':correction_id,'affected_binding_id':bid}
    proposed=O.make(oid,d['type'],d['target_refs'],criterion,consumer_bindings=[binding],
                    dependencies=deepcopy(d.get('dependency_bindings',[])),
                    scope_context_refs=d.get('scope_context_refs',[]),created_by=correction_id,effect='CORRECT_EXACT_DUTY')
    return {'correction_id':correction_id,'instance_id':iid,'mission_id':mid,'affected_binding_id':bid,
            'instruction':instruction,'success_criterion':success,'criterion_body':text,'obligation':proposed,
            'retry_grant':{'grant_id':binding['retry_grant_id'],'obligation_id':oid,'method_ref':binding['method_ref'],
                           'max_research_attempts':1,'max_responsibility_attempts':1}}


def request(store,iid,bid,instruction,success):
    from . import workflow_instances as W
    snapshot=store.read_snapshot();p=contract(snapshot,iid,bid,instruction,success)
    if p['correction_id'] in snapshot.get('corrections',{}):
        return {'correction_id':p['correction_id'],'status':'ALREADY_RECORDED','model_calls':0}
    store.blob(p['criterion_body'].encode())
    receipt=store.commit_control(W.event(snapshot,'REQUEST_CORRECTION',p,instance_id=iid,mission_id=p['mission_id']))
    return {**receipt,'correction_id':p['correction_id'],'binding_id':p['obligation']['definition']['consumer_bindings'][0]['binding_id'],
            'status':'PAUSED_CORRECTION_RECORDED','model_calls':0}


def apply(snapshot,event):
    p=event['payload'];iid=event['instance_id']
    require(p==contract(snapshot,iid,p['affected_binding_id'],p['instruction'],p['success_criterion']),
            'CORRECTION_INVALID','Correction must retain the selected exact scientific scope')
    require(p['mission_id']==event['mission_id'],'AUTHORIZATION_REQUIRED','Correction cannot create a mission')
    require(p['correction_id'] not in snapshot.get('corrections',{}),'CORRECTION_INVALID','Correction already recorded')
    snapshot.setdefault('corrections',{})[p['correction_id']]={**deepcopy(p),'event_id':event['event_id']}
    snapshot['instances'][iid]['status']='PAUSED'
    bid=p['affected_binding_id']
    snapshot.setdefault('retired_consumers',{})[bid]={'instance_id':iid,'event_id':event['event_id'],'reason':p['instruction']}
    for r in snapshot['requests'].values():
        if any(b['binding_id']==bid for b in snapshot['tasks'][r['task_id']].get('obligation_bindings',[])) and r['execution_state']=='PREPARED':
            r.update(execution_state='CANCELLED_BEFORE_SEND',fenced=True)


def pending(snapshot,iid):
    rows=[]
    mid=snapshot['instances'][iid].get('current_mission_id')
    for cid,c in snapshot.get('corrections',{}).items():
        if c['instance_id']!=iid or c['mission_id']!=mid:continue
        d=c['obligation']['definition'];bid=d['consumer_bindings'][0]['binding_id']
        o=snapshot['obligations'].get(d['obligation_id'])
        complete=bool(o and o['projection'].get('consumer_resolutions',{}).get(bid)=='SATISFIED_FOR_CONSUMER')
        rows.append({'correction_id':cid,'affected_binding_id':c['affected_binding_id'],'binding_id':bid,
                     'stage_id':d['consumer_bindings'][0]['stage_id'],'instruction':c['instruction'],
                     'success_criterion':c['success_criterion'],'assigned':o is not None,'complete':complete})
    return rows


def advance(store,iid):
    from . import execution
    snapshot=store.read_snapshot()
    if snapshot['instances'][iid]['status']!='ACTIVE':return []
    created=[]
    for row in pending(snapshot,iid):
        if row['assigned']:continue
        c=snapshot['corrections'][row['correction_id']];bid=c['affected_binding_id']
        original=[r for r in snapshot['requests'].values() if any(b['binding_id']==bid for b in snapshot['tasks'][r['task_id']].get('obligation_bindings',[]))]
        if any(r['execution_state'] in O.PENDING for r in original):continue
        proposed=deepcopy(c['obligation'])
        # Material inputs retain the original exact selection. The original
        # capture can be recovered before this new, explicitly authorized call.
        created.append(store.commit_execution(execution.event('ASSIGN_OBLIGATION',{
            'instance_id':iid,'mission_id':c['mission_id'],'obligation':proposed,'retry_grant':c['retry_grant'],
            'authorization_basis_ref':c['event_id']})))
        snapshot=store.read_snapshot()
    return created


def is_exact_authorization(snapshot,p):
    event=snapshot.get('control_events',{}).get(p.get('authorization_basis_ref'),{})
    if event.get('event_type')!='REQUEST_CORRECTION':return False
    c=event['payload']
    return (p['instance_id']==c['instance_id'] and p['mission_id']==c['mission_id']
            and p['obligation']==c['obligation'] and p['retry_grant']==c['retry_grant'])


def resolve_dependency(snapshot,dependency):
    """Resolve only an explicit human correction of an exact work binding.

    The original duty and request are untouched. Its replacement must still
    produce an accepted native account; this function never declares either
    duty satisfied and never substitutes for a qualified-support dependency.
    Ambiguous replacement branches or cycles remain blocked.
    """
    if dependency.get('threshold')!='WORK_DISPOSITION_RECORDED' or not dependency.get('binding_id'):
        return dependency
    resolved=deepcopy(dependency);seen=set();chain=[]
    while True:
        bid=resolved['binding_id']
        if bid in seen:return None
        seen.add(bid)
        old=snapshot.get('obligations',{}).get(resolved.get('binding_ref'),{})
        bindings=[c for c in old.get('definition',{}).get('consumer_bindings',[]) if c['binding_id']==bid]
        if len(bindings)!=1:return resolved if not chain else None
        original=bindings[0]
        matches=[row for row in snapshot.get('corrections',{}).values()
                 if row['affected_binding_id']==bid and row['instance_id']==original['instance_id']
                 and row['mission_id']==original['mission_id']]
        if not matches:return resolved
        if len(matches)!=1:return None
        correction=matches[0];event=snapshot.get('control_events',{}).get(correction.get('event_id'),{})
        if event.get('event_type')!='REQUEST_CORRECTION' or event.get('payload',{}).get('correction_id')!=correction['correction_id']:
            return None
        definition=correction['obligation']['definition'];replacement=definition['consumer_bindings'][0]
        if replacement['instance_id']!=original['instance_id'] or replacement['mission_id']!=original['mission_id']:
            return None
        chain.append(correction['correction_id'])
        resolved.update(binding_ref=definition['obligation_id'],binding_id=replacement['binding_id'],
                        correction_chain=list(chain),original_binding_id=dependency['binding_id'])
        if definition['obligation_id'] not in snapshot.get('obligations',{}):return resolved
