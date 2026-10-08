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
    from .corrections import resolve_dependency
    refs=set()
    for original in definition.get('dependency_bindings',[]):
        dep=resolve_dependency(snapshot,original)
        if dep is None:continue
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
    from .corrections import resolve_dependency
    dep=resolve_dependency(snapshot,dep)
    if dep is None:return False
    threshold=dep.get('threshold')
    require(threshold in THRESHOLDS, 'DEPENDENCY_THRESHOLD_INVALID', str(threshold))
    ref=dep.get('binding_ref'); scope=dep.get('scope',{})
    if threshold=='ARTIFACT_AVAILABLE':
        return ref in snapshot.get('records',{}) or ref in snapshot.get('artifacts',{}) or bool(snapshot.get('obligations',{}).get(ref,{}).get('projection',{}).get('evidence_refs'))
    if threshold=='WORK_DISPOSITION_RECORDED':
        if dep.get('binding_id'):
            bid=dep['binding_id']
            if dep.get('allow_deferred') and bid in snapshot.get('retired_consumers',{}):return True
            return any(r.get('acceptance_state')=='ACCEPTED'
                and any(b.get('binding_id')==bid for b in snapshot.get('tasks',{}).get(r['task_id'],{}).get('obligation_bindings',[]))
                for r in snapshot.get('requests',{}).values())
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
    from .reports import dispatch_authorized
    report_authorized=bool(consumer.get('report_context')) and dispatch_authorized(snapshot,consumer)
    if instance.get('status')!='ACTIVE' and not report_authorized:return wait('INSTANCE_PAUSED')
    if consumer.get('report_context') and snapshot.get('reports',{}).get(consumer['report_context']['report_id'],{}).get('status')=='ABANDONED':
        return wait('REPORT_ABANDONED')
    mission=snapshot.get('missions',{}).get(consumer.get('mission_id'),{})
    if mission.get('status')!='ACTIVE' and not report_authorized:return wait('AUTHORIZATION_REQUIRED')
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


def branch_context(snapshot, consumer):
    """Actual dispositions for exact selected bindings, never a role-count proxy.

    This small context carries the original attempts, open conditions and source
    identities. Native evidence records still enter the ordinary premise closure.
    It is for mathematical synthesis, not independent review verdict prompting.
    """
    selected = consumer.get('entry_basis', {}).get('synthesis_branches', [])
    result = []
    from .corrections import resolve_dependency
    for declared in selected:
        resolved=resolve_dependency(snapshot,{'binding_ref':declared['obligation_id'],'binding_id':declared['binding_id'],
                                             'threshold':'WORK_DISPOSITION_RECORDED'})
        require(resolved is not None,'DEPENDENCY_PENDING','The selected correction chain is ambiguous or cyclic')
        branch={**declared,'obligation_id':resolved['binding_ref'],'binding_id':resolved['binding_id']}
        if resolved.get('correction_chain'):
            branch.update(original_binding_id=declared['binding_id'],correction_chain=resolved['correction_chain'])
        oid, bid = branch['obligation_id'], branch['binding_id']
        o = snapshot.get('obligations', {}).get(oid, {})
        bindings = [c for c in o.get('definition', {}).get('consumer_bindings', [])
                    if c['binding_id'] == bid and c['mission_id'] == consumer['mission_id']
                    and c['instance_id'] == consumer['instance_id']]
        require(len(bindings) == 1 and bindings[0]['stage_id'] == branch['stage_id']
                and bindings[0]['role'] == branch['role'], 'DEPENDENCY_PENDING', 'Selected branch identity differs from its actual duty')
        requests = [r for r in snapshot.get('requests', {}).values()
                    if r.get('mission_id') == consumer['mission_id'] and r.get('acceptance_state') == 'ACCEPTED'
                    and any(b['binding_id'] == bid for b in snapshot.get('tasks', {}).get(r['task_id'], {}).get('obligation_bindings', []))]
        ids = {r['request_id'] for r in requests}
        accounts = [deepcopy(a) for a in o.get('projection', {}).get('attempt_accounts', []) if a['request_id'] in ids]
        retired = snapshot.get('retired_consumers', {}).get(bid)
        evidence = set()
        for r in requests:
            # Only effects for this exact branch contribute evidence. Older
            # attempts under another mission cannot silently satisfy this one.
            for ref in o.get('projection', {}).get('evidence_refs', []):
                if any(p.get('record_ref') == ref and p.get('task_id') == r['task_id']
                       for p in snapshot.get('production_events', {}).values()):evidence.add(ref)
        result.append({**deepcopy(branch), 'accepted_requests': [{'request_id':r['request_id'], 'task_id':r['task_id'],
                       'capture_ref':r.get('capture_ref')} for r in sorted(requests,key=lambda r:r['request_id'])],
                       'attempt_accounts':accounts, 'evidence_refs':sorted(evidence),
                       'retirement':deepcopy(retired),
                       'disposition':'RECORDED' if requests and accounts else 'DEFERRED' if retired else 'PENDING'})
    return result


def validate_branch_dispositions(snapshot, consumer):
    basis = consumer.get('entry_basis', {})
    if 'synthesis_branches' in basis:
        for branch in branch_context(snapshot, consumer):
            require(branch['disposition'] == 'RECORDED' or
                    branch['disposition'] == 'DEFERRED' and branch.get('required') is False,
                    'DEPENDENCY_PENDING', 'Every selected branch needs its actual accepted attempt or an explicitly permitted reasoned deferral')
        return
    if consumer.get('stage_id') == 'P7' and consumer.get('role') == 'SYNTHESIS' and basis.get('analysis_route') == 'COMPARATIVE':
        for role in ('LEARN', 'DIRECT'):
            bid = basis.get('branch_dispositions', {}).get(role)
            require(isinstance(bid,str) and any(t.get('mission_id') == consumer['mission_id'] and t.get('stage_id') == 'P7'
                    and t.get('role') == role and any(x['binding_id'] == bid for x in t.get('obligation_bindings', []))
                    and snapshot['requests'][t['request_id']].get('acceptance_state') == 'ACCEPTED'
                    for t in snapshot.get('tasks', {}).values()),
                    'DEPENDENCY_PENDING', 'Comparative synthesis needs actual accepted branch work dispositions')


def task_plan_context(snapshot, consumer):
    """Small exact upstream mathematical accounts, excluding review verdicts.

    A gap account is real scientific input even when it produced no new record.
    Independent tasks still never receive an upstream independent review verdict.
    """
    from .workflows.registry import INDEPENDENT
    basis=consumer.get('entry_basis',{})
    if not basis.get('research_plan'):return None
    owner=next((o for o in snapshot.get('obligations',{}).values()
                if any(c['binding_id']==consumer['binding_id'] for c in o['definition']['consumer_bindings'])),None)
    if owner is None:return None
    selected=[]
    from .corrections import resolve_dependency
    for original in owner['definition']['dependency_bindings']:
        dep=resolve_dependency(snapshot,original)
        if dep is None:continue
        upstream=snapshot.get('obligations',{}).get(dep.get('binding_ref'),{})
        for c in upstream.get('definition',{}).get('consumer_bindings',[]):
            if c['binding_id']!=dep.get('binding_id') or c['mission_id']!=consumer['mission_id']:continue
            if consumer['role'] in INDEPENDENT and c['role'] in INDEPENDENT:continue
            selected.append({'key':c.get('entry_basis',{}).get('research_plan',{}).get('branch_key',c['binding_id']),
                'obligation_id':dep['binding_ref'],'binding_id':c['binding_id'],'stage_id':c['stage_id'],'role':c['role'],
                'required':not dep.get('allow_deferred',False)})
    selected=list({b['binding_id']:b for b in selected}.values())
    shadow=deepcopy(consumer);shadow.setdefault('entry_basis',{})['synthesis_branches']=selected
    result={'plan':deepcopy(basis['research_plan']), 'dependency_work':branch_context(snapshot,shadow),
            'synthesis_work':branch_context(snapshot,consumer) if consumer.get('role')=='SYNTHESIS' else [],
            'independent_review_verdicts_excluded':consumer.get('role') in INDEPENDENT}
    if basis.get('autoflow'):
        result['reused_prerequisites']=deepcopy(basis['autoflow'].get('reused_work',{}))
    if consumer.get('stage_id')=='P11':
        # The global account must see actual failures and unperformed duties,
        # including work which was not a dependency of the successful route.
        global_branches=[b for b in basis['research_plan']['selected_branches'] if b['binding_id']!=consumer['binding_id']]
        shadow['entry_basis']['synthesis_branches']=global_branches
        result['global_gap_inventory']=branch_context(snapshot,shadow)
        for branch in result['global_gap_inventory']:
            if branch['role'] in INDEPENDENT:
                branch['attempt_accounts']=[];branch['evidence_refs']=[]
                branch['review_verdict_excluded']=True
    return result


def plan_input_refs(snapshot,consumer):
    """Exact extra mathematical evidence needed by a global P11 account."""
    if consumer.get('stage_id')!='P11':return []
    context=task_plan_context(snapshot,consumer) or {}
    return sorted({ref for b in context.get('global_gap_inventory',[]) for ref in b['evidence_refs']})
