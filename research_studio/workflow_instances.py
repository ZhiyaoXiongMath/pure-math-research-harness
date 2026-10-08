"""Independent workflow controls; human decisions never assert mathematical truth."""
from copy import deepcopy
from .util import identity, require, canonical
from .workflows.registry import REGISTRY, spec, validate_exit

EVENT_FIELDS={'event_id','actor','capability_ref','project_id','instance_id','mission_id',
              'event_type','expected_scope_version','payload','related_change_ref'}
EVENT_TYPES={'CREATE_INSTANCE','AUTHORIZE_MISSION','PAUSE','RESUME','CANCEL_REQUEST','RETIRE_CONSUMER',
             'HANDOFF_PREPARED','HANDOFF_ADOPTED','REPORT_SELECTED','HUMAN_DECISION','RECONCILE_UNKNOWN','DISCOVERY_SCOPE_DEFINED'}

def validate_report_first_actions(actions):
    require(type(actions) is list and all(type(action) is str and action in {'CONTINUE','END','ADOPT','ADOPT_HANDOFF'} for action in actions)
            and len(actions)==len(set(actions)), 'AUTHORIZATION_REQUIRED',
            'Report-first actions must explicitly select CONTINUE, END, ADOPT or ADOPT_HANDOFF without duplicates')
    return list(actions)

def event(snapshot,event_type,payload,*,instance_id=None,mission_id=None,actor='human',capability_ref='CAP-HUMAN',event_id=None):
    row={'actor':actor,'capability_ref':capability_ref,'project_id':snapshot['project_id'],
         'instance_id':instance_id,'mission_id':mission_id,'event_type':event_type,
         'expected_scope_version':snapshot.get('scope_versions',{}).get(instance_id or 'project',0),
         'payload':deepcopy(payload),'related_change_ref':None}
    row['event_id']=event_id or identity(row,'CONTROL-');return row

def select_instance(snapshot,instance_id):
    require(instance_id is not None,'INSTANCE_SELECTOR_REQUIRED','Specify the workflow instance for every write')
    require(instance_id in snapshot.get('instances',{}),'INSTANCE_UNKNOWN',str(instance_id))
    return snapshot['instances'][instance_id]

DISCOVERY_FIELDS={'phenomenon_ref':'现象','immutable_background_ref':'不可改变的背景','allowed_axes_ref':'允许探索的范围'}

def validate_discovery_scope(snapshot,instance,*,required=True):
    if instance['kind']!='TFDW':return {}
    scope=instance.get('discovery_scope') or {}
    require(isinstance(scope,dict) and not set(scope)-set(DISCOVERY_FIELDS),'DISCOVERY_SCOPE_INVALID','Unknown discovery scope field')
    for key,label in DISCOVERY_FIELDS.items():
        ref=scope.get(key)
        require(not required or ref,'DISCOVERY_SCOPE_REQUIRED','请补齐'+label+'；若无附加限制，请由用户明确说明。')
        if ref:
            source=snapshot.get('sources',{}).get(ref)
            require(source is not None and source.get('access_class','SCIENTIFIC_SOURCE')=='SCIENTIFIC_SOURCE'
                    and source.get('bytes',0)>0,'DISCOVERY_SCOPE_INVALID',label+'必须引用完整保存的用户原文。')
    if scope.get('phenomenon_ref'):
        require(scope['phenomenon_ref']==instance.get('discovery_brief_ref'),'DISCOVERY_SCOPE_INVALID','Phenomenon and discovery brief must bind the same original source')
    return deepcopy(scope)

def new_instance(snapshot,kind,*,target_ref=None,discovery_brief_ref=None,created_by_decision=None,instance_id=None,name=None,discovery_scope=None,survey_scope=None):
    require(kind in {'TRW','TFDW','SURVEY'},'WORKFLOW_KIND_INVALID',str(kind))
    if kind=='TRW':
        require(target_ref in snapshot.get('records',{}) and snapshot['records'][target_ref]['kind']=='Statement'
                and discovery_brief_ref is None,'TARGET_REQUIRED','TRW requires an exact Statement revision')
    elif kind=='TFDW':
        require(target_ref is None and (discovery_brief_ref is not None or discovery_scope is not None),'DISCOVERY_BRIEF_REQUIRED','TFDW has a discovery brief or an explicit incomplete draft and no fixed target')
    else:
        from .survey import normalize_scope
        require(target_ref is None and discovery_brief_ref is None,'SURVEY_SCOPE_INVALID','Survey has its own scope and no fabricated research target')
        survey_scope=normalize_scope(snapshot,survey_scope)
    iid=instance_id or identity({'kind':kind,'target':target_ref,'brief':discovery_brief_ref,
        'decision':created_by_decision,'ordinal':len(snapshot.get('instances',{}))+1},'INSTANCE-')
    if name is not None:require(isinstance(name,str) and 0<len(name.strip())<=200,'INSTANCE_NAME_INVALID','研究流程名称须为 1–200 字符。')
    row={'instance_id':iid,'kind':kind,'definition_version':{'TRW':'pmrs.trw/1','TFDW':'pmrs.tfdw/1','SURVEY':'pmrs.survey/1'}[kind],
            'definition_digest':REGISTRY['digest'],'created_by_decision':created_by_decision,'status':'PAUSED',
            'target_ref':target_ref,'discovery_brief_ref':discovery_brief_ref,'mission_ids':[],
            'current_mission_id':None,'input_knowledge_commit':snapshot.get('knowledge_commit'),'policy_refs':[]}
    if survey_scope is not None:row['survey_scope']=deepcopy(survey_scope)
    if name is not None:row['name']=name
    if discovery_scope is not None:
        require(kind=='TFDW','DISCOVERY_SCOPE_INVALID','Only TFDW has discovery scope')
        row['discovery_scope']=deepcopy(discovery_scope);validate_discovery_scope(snapshot,row,required=False)
    return row

def report_obligation_ids(snapshot,instance_id):
    """Link report-discovered duties to their exact originating instance.

    Visibility and decision accounting do not create a consumer or a grant.
    Both the report link and duty provenance must agree, including the request.
    """
    result=set()
    for rid,report in snapshot.get('reports',{}).items():
        if instance_id not in report.get('scope',{}).get('instance_ids',[]):continue
        for item in report.get('open_research_requests',[]):
            oid=item.get('obligation_id');d=snapshot.get('obligations',{}).get(oid,{}).get('definition',{})
            origin=d.get('created_by')
            if (isinstance(origin,dict) and origin.get('report_id')==rid and
                origin.get('review_request_id')==item.get('request_id') and item.get('request_id')):
                result.add(oid)
    return result


def decision_basis(snapshot,instance_id,*,candidate_ref=None,report_ref=None):
    instance=select_instance(snapshot,instance_id)
    if report_ref is not None:
        report=snapshot.get('reports',{}).get(report_ref)
        require(report is not None and instance_id in report.get('scope',{}).get('instance_ids',[]),'REPORT_UNKNOWN','Decision attachment must name a real scoped report; completion remains optional')
    candidates=[c['statement_ref'] for c in snapshot.get('candidates',{}).values()
                if c['instance_id']==instance_id and c.get('candidate_state') not in {'NOT_SELECTED','REJECTED_FOR_STATED_REASON'}]
    if candidate_ref is not None:
        require(candidate_ref in candidates,'CANDIDATE_UNKNOWN','Select an exact candidate in this workflow')
    targets=[instance['target_ref']] if instance['target_ref'] else []
    chosen=[candidate_ref] if candidate_ref else []
    open_refs=[];checked=[];unchecked=[];report_duties=report_obligation_ids(snapshot,instance_id)
    for oid,o in snapshot.get('obligations',{}).items():
        d=o['definition'];p=o['projection'];bindings=[c for c in d['consumer_bindings'] if c['instance_id']==instance_id and not c.get('retired')]
        if not bindings and oid not in report_duties:continue
        if p['resolution']!='SATISFIED_FOR_CONSUMER':open_refs.append({'obligation_id':oid,'definition_revision':d['definition_revision']})
        for binding in bindings:
            if binding.get('required_assurance') and (binding.get('selected_support') or binding.get('selected_supports')):
                from .assurance import evaluate
                view=evaluate(d['target_refs'][0],binding,snapshot)
                checked.extend(view.get('checked_scope',[])); unchecked.extend(view.get('not_checked',[]))
    for ref in targets+chosen:
        if not any(x.get('target_ref')==ref for x in checked+unchecked):
            unchecked.append({'target_ref':ref,'aspects':['ALL_REQUIRED_SCOPE'],'reason':'No qualified check is recorded for this selected scope.'})
    return {'knowledge_commit':snapshot.get('knowledge_commit'),'target_refs':targets,'candidate_refs':chosen,
            'open_obligation_refs':sorted(open_refs,key=lambda x:x['obligation_id']),
            'checked_scope':checked,'unchecked_scope':unchecked,'report_ref':report_ref}

def decision_guard(snapshot,basis):
    return identity({'records':{r:identity(snapshot.get('records',{}).get(r)) for r in basis['target_refs']+basis['candidate_refs']},
                     'obligations':{b['obligation_id']:snapshot.get('obligations',{}).get(b['obligation_id']) for b in basis['open_obligation_refs']},
                     'boundaries':{'checked':basis['checked_scope'],'unchecked':basis['unchecked_scope']}},'DECISION-SCOPE-')

def decide_event(snapshot,instance_id,action,note,*,candidate_ref=None,report_ref=None,actor='human',capability_ref='CAP-HUMAN'):
    require(isinstance(note,str) and note.strip(),'AUTHORIZATION_REQUIRED','Record the actual human decision')
    basis=decision_basis(snapshot,instance_id,candidate_ref=candidate_ref,report_ref=report_ref)
    return event(snapshot,'HUMAN_DECISION',{'action':action,'note':note,'decision_basis':basis,
        'decision_guard':decision_guard(snapshot,basis)},instance_id=instance_id,
        mission_id=select_instance(snapshot,instance_id)['current_mission_id'],actor=actor,capability_ref=capability_ref)

def authorize_event(snapshot,instance_id,mission,budget,*,actor='human',capability_ref='CAP-HUMAN'):
    return event(snapshot,'AUTHORIZE_MISSION',{'mission':mission,'budget':budget},instance_id=instance_id,
                 mission_id=mission['mission_id'],actor=actor,capability_ref=capability_ref)

def _authority(snapshot,e):
    require(set(e)==EVENT_FIELDS and e['event_type'] in EVENT_TYPES,'CONTROL_EVENT_INVALID','Typed control event required')
    require(e['project_id']==snapshot['project_id'],'AUTHORIZATION_REQUIRED','Wrong project')
    cap=snapshot.get('capabilities',{}).get(e['capability_ref'],{})
    require(cap.get('actor')==e['actor'] and (e['event_type'] in cap.get('actions',[]) or '*' in cap.get('actions',[])),
            'AUTHORIZATION_REQUIRED','Actor lacks this capability')
    require('*' in cap.get('instance_ids',[]) or e['instance_id'] in cap.get('instance_ids',[]),'AUTHORIZATION_REQUIRED','Capability is outside this workflow scope')
    require(e['expected_scope_version']==snapshot.get('scope_versions',{}).get(e['instance_id'] or 'project',0),
            'WRITE_CAS_CONFLICT','Relevant control scope changed')
    require(e['actor']=='human','AUTHORIZATION_REQUIRED','Models may propose controls but may not grant or perform human actions')

def apply_control(snapshot,e):
    previous=snapshot.get('control_events',{}).get(e.get('event_id'))
    if previous:
        require(previous==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Control event identity reused with different content')
        return deepcopy(snapshot)
    _authority(snapshot,e);s=deepcopy(snapshot);p=e['payload'];kind=e['event_type'];iid=e['instance_id']
    if kind=='CREATE_INSTANCE':
        row=p['instance'];expected=new_instance(s,row['kind'],target_ref=row['target_ref'],discovery_brief_ref=row['discovery_brief_ref'],
                                              created_by_decision=row['created_by_decision'],instance_id=row['instance_id'],
                                              name=row.get('name'),discovery_scope=row.get('discovery_scope'),survey_scope=row.get('survey_scope'))
        require(row==expected and row['instance_id'] not in s.get('instances',{}),'CONTROL_EVENT_INVALID','Invalid or existing workflow instance')
        s.setdefault('instances',{})[row['instance_id']]=deepcopy(row)
    elif kind=='AUTHORIZE_MISSION' and set(p)=={'future_configuration'}:
        from . import model_policy
        config=p['future_configuration'];instance=select_instance(s,iid)
        require({'mission_id','model_overrides','reason_ref'}<=set(config)<= {'mission_id','model_overrides','reset_scopes','reason_ref'} and config['mission_id']==e['mission_id']==instance['current_mission_id'],
                'AUTHORIZATION_REQUIRED','Future configuration must name the existing current mission')
        require(config['reason_ref'],'AUTHORIZATION_REQUIRED','Explicit configuration reason required')
        mission=s['missions'][config['mission_id']];grant=s['budget_grants'][mission['budget_grant_id']]
        policy=grant.setdefault('execution_policy',{})
        existing=deepcopy(policy.get('model_overrides',[]))
        if policy.get('model_override'):existing.append(policy['model_override'])
        policy['model_overrides']=model_policy.merge_overrides(existing,config['model_overrides'],reset_scopes=config.get('reset_scopes',[]),
                workflow_kind=instance['kind'],capabilities=policy.get('model_capabilities'));policy.pop('model_override',None)
        policy['configuration_authorized']=True;policy['configuration_event_ref']=e['event_id']
    elif kind=='AUTHORIZE_MISSION':
        instance=select_instance(s,iid);m=deepcopy(p['mission']);b=deepcopy(p['budget'])
        require(instance['kind']!='SURVEY' or instance['status']!='ENDED','AUTHORIZATION_REQUIRED','An ended Survey requires a linked new instance')
        validate_discovery_scope(s,instance)
        from . import model_policy
        policy=b.setdefault('execution_policy',{})
        overrides=deepcopy(policy.get('model_overrides',[]))
        if policy.get('model_override'):overrides.append(policy.pop('model_override'))
        if overrides:
            policy['model_overrides']=model_policy.merge_overrides([],overrides,workflow_kind=instance['kind'],capabilities=policy.get('model_capabilities'))
            policy['configuration_authorized']=True;policy['configuration_event_ref']=e['event_id']
        if 'report_first_actions' in m:validate_report_first_actions(m['report_first_actions'])
        require(m['instance_id']==iid and m['mission_id']==e['mission_id'] and m['mission_id'] not in s.get('missions',{}),
                'AUTHORIZATION_REQUIRED','New exact mission required')
        require(m.get('intent_ref') and m.get('authorized_scope'),'AUTHORIZATION_REQUIRED','Research intent and bounded scope required')
        from . import obligations as duties
        from .contracts import HASH
        from .workflows.registry import validate_assignment
        for proposed in m.pop('obligations',[]):
            require(set(proposed)=={'definition','projection'},'OBLIGATION_INVALID','Typed new responsibility required')
            d=proposed['definition'];oid=d['obligation_id']
            require(oid not in s.get('obligations',{}) and d['definition_revision']==1 and HASH.fullmatch(str(d['criterion_body_ref'])),
                    'OBLIGATION_INVALID','New responsibility must bind an immutable criterion blob')
            allowed_refs=set(m['authorized_scope'].get('target_refs',[]))|({instance['target_ref']} if instance['target_ref'] else set())
            allowed_refs.update(c['statement_ref'] for c in s.get('candidates',{}).values() if c['instance_id']==iid)
            require(all(r in allowed_refs and r in s.get('records',{}) for r in d['target_refs']),
                    'AUTHORIZATION_REQUIRED','New responsibility targets exceed the exact authorized scope')
            expected=duties.make(oid,d['type'],d['target_refs'],d['criterion_body_ref'],consumer_bindings=d['consumer_bindings'],
                dependencies=d['dependency_bindings'],scope_context_refs=d['scope_context_refs'],effect=d['effect_on_goal'],
                created_by=d['created_by'],reason_code=d['reason_code'],alias_of=d['alias_of'])
            require(proposed==expected,'OBLIGATION_INVALID','A new grant cannot import lifecycle, attempts or scientific support')
            for consumer in d['consumer_bindings']:
                require(consumer['instance_id']==iid and consumer['mission_id']==m['mission_id'],
                        'AUTHORIZATION_REQUIRED','Consumer must bind this exact authorized mission')
                validate_assignment(consumer['stage_id'],d['type'],consumer['role'],consumer.get('entry_basis',{}))
            s.setdefault('obligations',{})[oid]=deepcopy(proposed)
        duties.validate_graph(s.get('obligations',{}))
        require(type(b.get('max_calls')) is int and b['max_calls']>=0 or b.get('explicit_unlimited') is True,
                'AUTHORIZATION_REQUIRED','Finite budget or explicit unlimited authorization required')
        require(b.get('budget_grant_id')==m.get('budget_grant_id'),'AUTHORIZATION_REQUIRED','Mission budget binding differs')
        if 'max_workers' in b:
            require(type(b['max_workers']) is int and 1<=b['max_workers']<=4,'AUTHORIZATION_REQUIRED','Project concurrency must be explicitly bounded at one to four')
            s['max_workers']=b['max_workers']
        used=sum(r.get('reserved_calls',1) for r in s.get('requests',{}).values() if r['execution_state']!='CANCELLED_BEFORE_SEND')
        project_budget=s.setdefault('project_budget',{'max_calls':0})
        if 'project_limit' in b:
            require(type(b['project_limit']) is int and b['project_limit']>=used,'AUTHORIZATION_REQUIRED','Project limit cannot discard prior usage or uncertain reservations')
            project_budget['max_calls']=b.pop('project_limit')
        elif b.get('explicit_unlimited') is True:project_budget['explicit_unlimited']=True
        elif not project_budget.get('explicit_unlimited'):project_budget['max_calls']+=b['max_calls']
        b.update(instance_id=iid,mission_id=m['mission_id'],authorized_by=e['event_id'])
        s.setdefault('budget_grants',{})[b['budget_grant_id']]=b
        m.update(status='ACTIVE',stage_visit_ids=[],delivery_ref=None,input_knowledge_commit=s.get('knowledge_commit'))
        for grant in m.pop('retry_grants',[]):
            require(type(grant.get('max_research_attempts',1)) is int and grant.get('max_research_attempts',1)>=1,
                    'AUTHORIZATION_REQUIRED','Bounded sampling grant required')
            require(grant['obligation_id'] in s.get('obligations',{}),'OBLIGATION_INVALID','Retry grant must name an existing responsibility')
            grant=deepcopy(grant);grant.setdefault('max_research_attempts',1)
            grant['authorized_by']=e['event_id'];grant['source_decision_or_mission_grant']=m['mission_id']
            grant['stop_conditions']=grant.get('stop_conditions',['CONSUMER_SATISFIED','BUDGET_EXHAUSTED','HARD_BLOCKER','PAUSED','CANCELLED'])
            grant['remaining_uses']=grant['max_research_attempts'];grant['scope_version']=e['expected_scope_version']+1
            old=s.setdefault('retry_grants',{}).get(grant['grant_id'])
            require(old is None or old==grant,'AUTHORIZATION_REQUIRED','Existing grants are immutable; an explicit allowance amendment is required')
            s['retry_grants'][grant['grant_id']]=grant
        s.setdefault('missions',{})[m['mission_id']]=m;instance['mission_ids'].append(m['mission_id']);instance['current_mission_id']=m['mission_id'];instance['status']='ACTIVE'
    elif kind in {'PAUSE','RESUME'}:
        instance=select_instance(s,iid)
        require(p.get('reason') or p.get('decision_ref'),'AUTHORIZATION_REQUIRED','Control reason or recorded decision required')
        if kind=='RESUME':
            decision=s.get('control_events',{}).get(p.get('decision_ref'),{})
            require(decision.get('event_type')=='HUMAN_DECISION' and decision.get('instance_id')==iid
                    and decision['payload']['action'] in {'CONTINUE','CONTINUE_DISCOVERY'},'AUTHORIZATION_REQUIRED','Resume requires the exact knowledge-based human decision')
            require(instance['current_mission_id'] in s.get('missions',{}),'AUTHORIZATION_REQUIRED','No authorized mission')
        instance['status']='PAUSED' if kind=='PAUSE' else 'ACTIVE'
    elif kind=='HUMAN_DECISION':
        instance=select_instance(s,iid);basis=p.get('decision_basis',{});action=p.get('action')
        require(action in {'CONTINUE','CONTINUE_DISCOVERY','ADOPT','PAUSE','END','END_WITHOUT_ADOPTION','PREPARE_HANDOFF','ADOPT_HANDOFF','REVISE_REPORT'},'CONTROL_EVENT_INVALID','Unknown human decision')
        require(set(basis)=={'knowledge_commit','target_refs','candidate_refs','open_obligation_refs','checked_scope','unchecked_scope','report_ref'}
                and basis['knowledge_commit'],'CONTROL_EVENT_INVALID','Host frozen knowledge basis required')
        expected=decision_basis(s,iid,candidate_ref=basis['candidate_refs'][0] if len(basis['candidate_refs'])==1 else None,report_ref=basis['report_ref'])
        require(len(basis['candidate_refs'])<=1 and {k:v for k,v in expected.items() if k!='knowledge_commit'}=={k:v for k,v in basis.items() if k!='knowledge_commit'},
                'STALE_READ','Selected decision scope or knowledge boundary changed')
        require(p.get('decision_guard')==decision_guard(s,basis),'STALE_READ','Relevant decision inputs changed')
        if action=='ADOPT':require(len(basis['candidate_refs'])==1,'CANDIDATE_SELECTOR_REQUIRED','Choose one exact candidate')
        mission=s.get('missions',{}).get(instance['current_mission_id'],{})
        gated_action={'CONTINUE_DISCOVERY':'CONTINUE','END_WITHOUT_ADOPTION':'END'}.get(action,action)
        if gated_action in mission.get('report_first_actions',[]):
            report=s.get('reports',{}).get(basis['report_ref'],{})
            require(report.get('status')=='COMPLETE','REPORT_BLOCKED','The researcher explicitly required a completed report first')
        if action in {'CONTINUE','CONTINUE_DISCOVERY'}:
            require(mission.get('status')=='ACTIVE' and mission.get('budget_grant_id') in s.get('budget_grants',{}),'AUTHORIZATION_REQUIRED','Continuation does not create scope or budget')
            instance['status']='ACTIVE'
        elif action=='PAUSE':instance['status']='PAUSED'
        elif action in {'END','END_WITHOUT_ADOPTION'}:instance['status']='ENDED'
    elif kind=='CANCEL_REQUEST':
        r=s.get('requests',{}).get(p.get('request_id'))
        require(r and r['instance_id']==iid,'TASK_FENCED','Exact workflow request required')
        require(p.get('reason'),'AUTHORIZATION_REQUIRED','Cancellation reason required')
        r['fenced']=True
        if r['execution_state']=='PREPARED':r['execution_state']='CANCELLED_BEFORE_SEND'
    elif kind=='DISCOVERY_SCOPE_DEFINED':
        instance=select_instance(s,iid)
        require(instance['kind']=='TFDW' and set(p)=={'discovery_scope'},'DISCOVERY_SCOPE_INVALID','Exact discovery scope update required')
        require(not instance.get('mission_ids') and not any(t['instance_id']==iid for t in s['tasks'].values()),
                'DISCOVERY_SCOPE_IMMUTABLE','Only an unassigned discovery draft can be completed')
        old=instance.get('discovery_scope') or {};new=deepcopy(p['discovery_scope'])
        require(not instance.get('mission_ids') or all(new.get(k)==v for k,v in old.items()),
                'DISCOVERY_SCOPE_IMMUTABLE','已授权的研究范围不能更改；请另建研究流程。')
        instance['discovery_scope']=new
        if new.get('phenomenon_ref'):instance['discovery_brief_ref']=new['phenomenon_ref']
        validate_discovery_scope(s,instance,required=False)
    elif kind=='RETIRE_CONSUMER':
        require(p.get('binding_id') and p.get('reason'),'CONTROL_EVENT_INVALID','Exact consumer and reason required')
        s.setdefault('retired_consumers',{})[p['binding_id']]={'instance_id':iid,'event_id':e['event_id'],'reason':p['reason']}
    elif kind=='HANDOFF_PREPARED':
        from .handoff import validate_manifest
        validate_manifest(s,p['manifest']);s.setdefault('handoffs',{})[p['manifest']['handoff_id']]=deepcopy(p['manifest'])
    elif kind=='HANDOFF_ADOPTED':
        from .handoff import apply_adoption
        s=apply_adoption(s,p,e)
    elif kind=='RECONCILE_UNKNOWN':
        r=s.get('requests',{}).get(p.get('request_id'))
        require(r and r['instance_id']==iid and r['execution_state']=='UNKNOWN' and not r.get('capture_ref'),
                'UNKNOWN_REQUIRES_EVIDENCE','处置必须对应本流程中仍无捕获的原始 UNKNOWN 请求。')
        require(p.get('execution_id')==r['execution_id'],'EXECUTION_IDENTITY','Unknown disposition must bind the original execution')
        disposition=p.get('disposition');require(disposition in {'ABANDON_UNKNOWN','CONFIRMED_NOT_SENT'},'CONTROL_EVENT_INVALID','请选择明确的未知请求处置方式。')
        require(e['actor']=='human' and isinstance(p.get('note'),str) and p['note'].strip(),
                'AUTHORIZATION_REQUIRED','请记录此次人类决定的具体说明。')
        if disposition=='CONFIRMED_NOT_SENT':
            source=s.get('sources',{}).get(p.get('not_sent_evidence_ref'))
            require(source is not None and source.get('bytes',0)>0 and source.get('blob_hash'),
                    'UNKNOWN_REQUIRES_EVIDENCE','确认未发送必须选择已保存的实际传输证据原件；说明文字不能代替证据。')
            r['execution_state']='CANCELLED_BEFORE_SEND';r['not_sent_evidence_ref']=p['not_sent_evidence_ref']
        else:
            require(not p.get('not_sent_evidence_ref'),'CONTROL_EVENT_INVALID','放弃等待保留未知消耗，不声明已确认未发送。')
        r['unknown_disposition']=disposition;r['fenced']=True;r['reconciliation_event']=e['event_id']
    elif kind=='REPORT_SELECTED':
        select_instance(s,iid);s.setdefault('selected_reports',{})[iid]=p.get('report_ref')
    s.setdefault('control_events',{})[e['event_id']]=deepcopy(e)
    scope=iid or 'project';s.setdefault('scope_versions',{})[scope]=e['expected_scope_version']+1
    return s
