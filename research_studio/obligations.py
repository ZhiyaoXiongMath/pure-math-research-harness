"""Persistent responsibilities, explicit consumer thresholds and bounded retry gates."""
from copy import deepcopy
from .util import identity, require

TYPES = {'ESTABLISH','REFUTE','APPLICABILITY','REDUCE','COMPATIBILITY','VERIFY','MATERIAL',
         'DISCRIMINATE','CALIBRATE','FORMULATE','COMPARE','INTEGRATE','ACCOUNT','REPORT','CONTROL'}
THRESHOLDS = {'ARTIFACT_AVAILABLE','WORK_DISPOSITION_RECORDED','SUPPORT_QUALIFIED',
              'HUMAN_DECISION_RECORDED','MATERIAL_VERIFIED'}
PENDING = {'PREPARED','RESERVED','SENT','UNKNOWN','CAPTURED'}
RETRY_LEAVES = {'MATERIAL_VERIFIED','INPUT_REVISION_CHANGED','SUPPORT_CHANGED',
                'DEPENDENCY_SATISFIED','METHOD_GRANTED','OPERATOR_RELEASED'}

def make(oid, kind, target_refs, criterion_body_ref, *, consumer_bindings=(), dependencies=(),
         scope_context_refs=(), effect='OPEN_SCOPE', created_by=None, reason_code=None, alias_of=None):
    require(kind in TYPES and oid and criterion_body_ref, 'OBLIGATION_INVALID', 'Exact criterion and valid responsibility required')
    require(reason_code is None or reason_code == 'NORMALIZATION_REQUIRED' and kind == 'MATERIAL',
            'OBLIGATION_INVALID', 'Normalization is a material reason, not a scientific qualification')
    return {'definition': {'obligation_id': oid, 'definition_revision': 1, 'type': kind,
        'target_refs': list(target_refs), 'criterion_body_ref': criterion_body_ref,
        'scope_context_refs': list(scope_context_refs), 'dependency_bindings': list(dependencies),
        'consumer_bindings': list(consumer_bindings), 'effect_on_goal': effect,
        'created_by': created_by, 'reason_code': reason_code, 'alias_of': alias_of},
        'projection': {'work_state':'OPEN','resolution':'UNRESOLVED','attempt_refs':[],
            'blocker_refs':[], 'evidence_refs':[], 'consumer_resolutions':{}, 'retry_gate_ref':None}}

def definition(o): return o['definition']
def projection(o): return o['projection']

def canonical_definition(snapshot, obligation):
    seen=set(); current=obligation
    while current['definition'].get('alias_of'):
        oid=current['definition']['alias_of']
        require(oid not in seen and oid in snapshot['obligations'], 'OBLIGATION_INVALID', 'Broken or cyclic alias')
        seen.add(oid); current=snapshot['obligations'][oid]
    return current['definition']

def responsibility_key(snapshot, obligation, consumer):
    d=canonical_definition(snapshot, obligation)
    # Neither the alias name, mission, task, route mode nor full KB HEAD participates.
    return identity({'criterion':d['criterion_body_ref'],'targets':sorted(d['target_refs']),
                     'scope':consumer.get('scope', {}),'success':consumer.get('success_criterion', d['criterion_body_ref'])}, 'RESPONSIBILITY-')

def purpose(snapshot, obligation, consumer, role):
    return identity({'responsibility':responsibility_key(snapshot,obligation,consumer),'role':role}, 'PURPOSE-')

def dependency_inputs(snapshot,definition):
    refs=set()
    for dep in definition.get('dependency_bindings',[]):
        ref=dep.get('binding_ref')
        if ref in snapshot.get('records',{}):refs.add(ref)
        if ref in snapshot.get('obligations',{}):
            upstream=snapshot['obligations'][ref]
            refs.update(upstream['definition']['target_refs']);refs.update(upstream['projection'].get('evidence_refs',[]))
        if ref in snapshot.get('supports',{}):
            upstream=snapshot['supports'][ref];refs.update([upstream['statement_ref'],upstream['argument_ref']])
    return sorted(refs)

def fingerprint(snapshot, obligation, consumer, *, method_ref=None):
    d=canonical_definition(snapshot,obligation)
    refs=set(d['target_refs']+d.get('scope_context_refs', [])+consumer.get('input_refs', [])+dependency_inputs(snapshot,d))
    sources=set(consumer.get('source_refs', []))
    selected_supports=consumer.get('selected_support_refs') or consumer.get('selected_supports', []) or ([consumer['selected_support']] if consumer.get('selected_support') else [])
    return identity({'records':{r:identity(snapshot.get('records',{}).get(r)) for r in sorted(refs)},
                     'sources':{r:identity(snapshot.get('sources',{}).get(r)) for r in sorted(sources)},
                     'supports':{r:identity(snapshot.get('supports',{}).get(r)) for r in sorted(selected_supports)},
                     'dependencies':d['dependency_bindings'], 'method':method_ref,
                     'report_context':consumer.get('report_context')}, 'INPUT-')

def keys(snapshot, obligation, consumer, role, method_ref=None):
    p=purpose(snapshot,obligation,consumer,role)
    f=fingerprint(snapshot,obligation,consumer,method_ref=method_ref)
    return {'responsibility_key':responsibility_key(snapshot,obligation,consumer), 'purpose_key':p,
            'input_fingerprint':f,'attempt_group_key':identity({'purpose':p,'method':method_ref,'input':f},'GROUP-')}

def validate_condition(condition):
    leaves=0
    def walk(c,depth):
        nonlocal leaves
        require(isinstance(c,dict) and depth<=4,'RETRY_CONDITION_INVALID','Bounded declarative retry condition required')
        kind=c.get('kind')
        if kind in {'ALL','ANY'}:
            require(set(c)=={'kind','conditions'} and isinstance(c['conditions'],list) and c['conditions'],
                    'RETRY_CONDITION_INVALID','Nonempty logical condition required')
            for child in c['conditions']:walk(child,depth+1)
        else:
            require(kind in RETRY_LEAVES,'RETRY_CONDITION_INVALID','Unknown predicate')
            leaves+=1; require(leaves<=16,'RETRY_CONDITION_INVALID','Too many leaves')
    walk(condition,1); return condition

def dependency_met(snapshot, dep):
    threshold=dep.get('threshold')
    require(threshold in THRESHOLDS, 'DEPENDENCY_THRESHOLD_INVALID', str(threshold))
    ref=dep.get('binding_ref'); scope=dep.get('scope',{})
    if threshold=='ARTIFACT_AVAILABLE':
        return ref in snapshot.get('records',{}) or ref in snapshot.get('artifacts',{}) or bool(snapshot.get('obligations',{}).get(ref,{}).get('projection',{}).get('evidence_refs'))
    if threshold=='WORK_DISPOSITION_RECORDED':
        p=snapshot.get('obligations',{}).get(ref,{}).get('projection',{})
        return bool(p.get('attempt_refs')) or p.get('work_state')=='DEFERRED'
    if threshold=='HUMAN_DECISION_RECORDED':
        e=snapshot.get('control_events',{}).get(ref,{})
        return e.get('event_type')=='HUMAN_DECISION'
    if threshold=='MATERIAL_VERIFIED':
        s=snapshot.get('sources',{}).get(ref,{})
        return bool(material_verified(s) and (not scope or scope==s.get('coverage')))
    from .assurance import evaluate_requirement
    requirement=dep.get('required_assurance')
    require(requirement is not None,'DEPENDENCY_UNQUALIFIED','Support dependency needs an exact requirement')
    result=evaluate_requirement(snapshot,ref,requirement,dep.get('policy_digest'))
    return result.get('result') in {'QUALIFIED','SATISFIED','SUPPORT_QUALIFIED',True}

def material_verified(source):
    return source.get('verified') is True or (isinstance(source.get('blob_hash'),str) and len(source['blob_hash'])==64
        and type(source.get('bytes')) is int and source['bytes']>0 and source.get('coverage')=='FULL_DOCUMENT')

def condition_met(c,snapshot,*,blocker=None):
    validate_condition(c); kind=c['kind']
    if kind in {'ALL','ANY'}:
        values=[condition_met(x,snapshot,blocker=blocker) for x in c['conditions']]
        return all(values) if kind=='ALL' else any(values)
    if kind=='MATERIAL_VERIFIED':
        row=snapshot.get('sources',{}).get(c.get('source_id'),{})
        return bool(material_verified(row) and (not c.get('coverage') or row.get('coverage')==c['coverage'])
                and (not c.get('sha256') or row.get('blob_hash',row.get('sha256'))==c['sha256']))
    if kind=='INPUT_REVISION_CHANGED':
        new=snapshot.get('objects',{}).get(c.get('logical_object'),{}).get('selected_revision')
        return bool(c.get('scope') and new and new!=c.get('old_ref') and new in snapshot.get('records',{}))
    if kind=='SUPPORT_CHANGED':
        row=snapshot.get('supports',{}).get(c.get('support_id'),{})
        return bool(c.get('scope') and row and row.get('projection_version')!=c.get('previous_version'))
    if kind=='DEPENDENCY_SATISFIED':return dependency_met(snapshot,c['dependency'])
    if kind=='METHOD_GRANTED':
        grant=snapshot.get('retry_grants',{}).get(c.get('grant_id'),{})
        return grant.get('method_ref')==c.get('method_ref') and grant.get('remaining_uses',0)>0 and not grant.get('expired',False)
    if kind=='OPERATOR_RELEASED':
        event=snapshot.get('control_events',{}).get(c.get('decision_event'),{})
        forbidden={'ORIGINAL_BYTES_MISMATCH','INCOMPLETE_CONTEXT','NON_SELF_CONTAINED','DEPENDENCY_UNQUALIFIED'}
        return bool(blocker and blocker['code'] not in forbidden and c.get('blocker_id')==blocker['blocker_id']
                    and event.get('actor')=='human' and c.get('blocker_id') in event.get('payload',{}).get('released_blocker_ids',[]))
    return False

def eligible(snapshot, obligation, consumer, role, *, method_ref=None):
    d=definition(obligation); p=projection(obligation)
    result=keys(snapshot,obligation,consumer,role,method_ref)
    def wait(code, **extra):return {**result,'state':'WAIT','code':code,**extra}
    iid=consumer['instance_id']; instance=snapshot.get('instances',{}).get(iid,{})
    if instance.get('status')!='ACTIVE':return wait('INSTANCE_PAUSED')
    mission=snapshot.get('missions',{}).get(consumer.get('mission_id'),{})
    if mission.get('status')!='ACTIVE':return wait('AUTHORIZATION_REQUIRED')
    if consumer.get('retired') or p['work_state'] in {'DEFERRED','RETIRED_WITH_REASON'}:return wait('CONSUMER_INACTIVE')
    if p.get('consumer_resolutions',{}).get(consumer['binding_id'])=='SATISFIED_FOR_CONSUMER':return wait('CONSUMER_SATISFIED')
    for request in snapshot.get('requests',{}).values():
        if request.get('purpose_key')==result['purpose_key'] and request.get('execution_state') in PENDING:
            return wait('EXISTING_REQUEST', request_id=request['request_id'],action='RECOVER' if request['execution_state']=='CAPTURED' else 'REUSE' if request['execution_state']=='PREPARED' else 'WAIT')
    for bid in p.get('blocker_refs',[]):
        b=snapshot.get('blockers',{}).get(bid)
        require(b is not None,'OBLIGATION_INVALID','Missing blocker definition')
        # Appending a consumer or renaming a grant cannot erase a persistent
        # hard blocker. Only its declared relevant condition/resolution clears it.
        if not b.get('resolution_events') and not condition_met(b['retry_condition'],snapshot,blocker=b):
            return wait('BLOCKER_UNCHANGED',blocker_id=bid,hardness=b.get('hardness','HARD'))
    for dep in d['dependency_bindings']:
        if not dependency_met(snapshot,dep):return wait('DEPENDENCY_UNQUALIFIED' if dep['threshold']=='SUPPORT_QUALIFIED' else 'DEPENDENCY_PENDING',dependency_id=dep['dependency_id'])
    grant=snapshot.get('retry_grants',{}).get(consumer.get('retry_grant_id'),{})
    if not grant or grant.get('method_ref')!=method_ref or grant.get('expired') or grant.get('obligation_id')!=canonical_definition(snapshot,obligation)['obligation_id']:return wait('AUTHORIZATION_REQUIRED')
    require(type(grant.get('max_research_attempts')) is int and grant['max_research_attempts']>=1,'AUTHORIZATION_REQUIRED','Finite cumulative attempt allowance required')
    limit=grant['max_research_attempts']
    # The responsibility ceiling also spans P7 role and route changes. Separate
    # role grants may specify an explicit responsibility ceiling for comparative work.
    cap=grant.get('max_responsibility_attempts',limit)
    used=[r for r in snapshot.get('requests',{}).values() if r.get('execution_state')!='CANCELLED_BEFORE_SEND' and not r.get('repair_of')]
    group_used=sum(r.get('attempt_group_key')==result['attempt_group_key'] for r in used)
    duty_used=sum(r.get('responsibility_key')==result['responsibility_key'] for r in used)
    if group_used>=limit or duty_used>=cap:return wait('RETRY_GRANT_EXHAUSTED')
    if grant.get('expires_on_scope_change') and grant.get('scope_version')!=snapshot.get('scope_versions',{}).get(iid,0):
        return wait('AUTHORIZATION_REQUIRED')
    return {**result,'state':'READY','code':'AUTHORIZED_RELEVANT_WORK','retry_grant':deepcopy(grant),
            'remaining_uses':min(limit-group_used,cap-duty_used)}

def validate_graph(items):
    visiting=set(); done=set()
    def walk(oid):
        require(oid not in visiting,'OBLIGATION_CYCLE',oid)
        if oid in done:return
        visiting.add(oid); d=definition(items[oid])
        require(d['obligation_id']==oid and d['type'] in TYPES,'OBLIGATION_INVALID',oid)
        for dep in d['dependency_bindings']:
            require(dep.get('threshold') in THRESHOLDS,'DEPENDENCY_THRESHOLD_INVALID',oid)
            if dep.get('binding_ref') in items:walk(dep['binding_ref'])
        visiting.remove(oid); done.add(oid)
    for oid in items:walk(oid)
