"""Independent workflow controls; human decisions never assert mathematical truth."""
from pmrh.domain.protocols import (
    DISCOVERY_FIELDS,
    completion_evidence,
    validate_discovery_scope,
)
from copy import deepcopy
from .util import identity, require, canonical, now
from .workflows.registry import REGISTRY, spec, validate_exit

EVENT_FIELDS={'event_id','actor','capability_ref','project_id','instance_id','mission_id',
              'event_type','expected_scope_version','payload','related_change_ref','issued_at'}
EVENT_TYPES={'CREATE_INSTANCE','AUTHORIZE_MISSION','EXTEND_MISSION_BUDGET','PAUSE','RESUME','CANCEL_REQUEST','RETIRE_CONSUMER',
             'REQUEST_CORRECTION','HANDOFF_PREPARED','HANDOFF_ADOPTED','REPORT_SELECTED','HUMAN_DECISION','RECONCILE_UNKNOWN','DISCOVERY_SCOPE_DEFINED',
             'SET_P14_MODE','REQUEST_STOP_AT_P14','CANCEL_STOP_AT_P14','SET_RESEARCH_AUDIT_POLICY'}

def validate_report_first_actions(actions):
    require(type(actions) is list and all(type(action) is str and action in {'CONTINUE','END','ADOPT','ADOPT_HANDOFF'} for action in actions)
            and len(actions)==len(set(actions)), 'AUTHORIZATION_REQUIRED',
            'Report-first actions must explicitly select CONTINUE, END, ADOPT or ADOPT_HANDOFF without duplicates')
    return list(actions)

def event(snapshot,event_type,payload,*,instance_id=None,mission_id=None,actor='human',capability_ref='CAP-HUMAN',event_id=None):
    row={'actor':actor,'capability_ref':capability_ref,'project_id':snapshot['project_id'],
         'instance_id':instance_id,'mission_id':mission_id,'event_type':event_type,
         'expected_scope_version':snapshot.get('scope_versions',{}).get(instance_id or 'project',0),
         'payload':deepcopy(payload),'related_change_ref':None,'issued_at':now()}
    row['event_id']=event_id or identity(row,'CONTROL-');return row

def select_instance(snapshot,instance_id):
    require(instance_id is not None,'INSTANCE_SELECTOR_REQUIRED','Specify the workflow instance for every write')
    require(instance_id in snapshot.get('instances',{}),'INSTANCE_UNKNOWN',str(instance_id))
    return snapshot['instances'][instance_id]


def new_instance(snapshot,kind,*,target_ref=None,discovery_brief_ref=None,created_by_decision=None,instance_id=None,name=None,discovery_scope=None,survey_scope=None):
    require(kind in {'TRH','FDH','SURVEY'},'WORKFLOW_KIND_INVALID',str(kind))
    if kind=='TRH':
        require(target_ref in snapshot.get('records',{}) and snapshot['records'][target_ref]['kind']=='Statement'
                and discovery_brief_ref is None,'TARGET_REQUIRED','TRH requires an exact Statement revision')
    elif kind=='FDH':
        require(target_ref is None and (discovery_brief_ref is not None or discovery_scope is not None),'DISCOVERY_BRIEF_REQUIRED','FDH has a discovery brief or an explicit incomplete draft and no fixed target')
    else:
        from .survey import normalize_scope
        require(target_ref is None and discovery_brief_ref is None,'SURVEY_SCOPE_INVALID','Survey has its own scope and no fabricated research target')
        survey_scope=normalize_scope(snapshot,survey_scope)
    iid=instance_id or identity({'kind':kind,'target':target_ref,'brief':discovery_brief_ref,
        'decision':created_by_decision,'ordinal':len(snapshot.get('instances',{}))+1},'INSTANCE-')
    if name is not None:require(isinstance(name,str) and 0<len(name.strip())<=200,'INSTANCE_NAME_INVALID','研究流程名称须为 1–200 字符。')
    row={'instance_id':iid,'kind':kind,'definition_version':{'TRH':'pmrs.trh/1','FDH':'pmrs.fdh/1','SURVEY':'pmrs.survey/1'}[kind],
            'definition_digest':REGISTRY['digest'],'created_by_decision':created_by_decision,'status':'PAUSED',
            'target_ref':target_ref,'discovery_brief_ref':discovery_brief_ref,'mission_ids':[],
            'current_mission_id':None,'input_knowledge_commit':snapshot.get('knowledge_commit'),'policy_refs':[]}
    if survey_scope is not None:row['survey_scope']=deepcopy(survey_scope)
    if kind in {'TRH','FDH'}:
        row['run_control']={'mode':'AUTO_P14' if kind=='TRH' else 'HUMAN_D5','round_number':1,'state':'PAUSED',
                            'stop_request':None,'control_version':0,'last_delivery_ref':None,
                            'automatic_authorization_ref':None}
    if name is not None:row['name']=name
    if discovery_scope is not None:
        require(kind=='FDH','DISCOVERY_SCOPE_INVALID','Only FDH has discovery scope')
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
    elif kind=='SET_RESEARCH_AUDIT_POLICY':
        instance=select_instance(s,iid)
        require(instance['kind'] in {'TRH','FDH'} and set(p)=={'light_check_seconds','full_audit_seconds'}
                and all(type(v) is int and v>0 for v in p.values()),
                'AUDIT_POLICY_INVALID','Specify positive light-check and full-audit intervals in seconds')
        instance['research_audit_policy']=deepcopy(p)
        instance['run_control'].update(control_version=instance['run_control']['control_version']+1,
            last_instruction_ref=e['event_id'],last_instruction_at=e['issued_at'])
    elif kind in {'SET_P14_MODE','REQUEST_STOP_AT_P14','CANCEL_STOP_AT_P14'}:
        instance=select_instance(s,iid)
        require(instance['kind']=='TRH','CONTROL_EVENT_INVALID','P14 controls apply to TRH only')
        control=instance['run_control']
        require(instance['status'] not in {'ENDED','COMPLETE'},'CONTROL_EVENT_INVALID','This research has ended')
        if kind=='SET_P14_MODE':
            require(set(p)=={'mode'} and p['mode'] in {'AUTO_P14','HUMAN_P14'},'CONTROL_EVENT_INVALID','Choose AUTO_P14 or HUMAN_P14')
            control['mode']=p['mode'];control['automatic_authorization_ref']=e['event_id'] if p['mode']=='AUTO_P14' else None
        elif kind=='REQUEST_STOP_AT_P14':
            require(set(p)=={'requested_at'} and isinstance(p['requested_at'],str),'CONTROL_EVENT_INVALID','Persist the actual stop request time')
            old=control.get('stop_request')
            if not old or old['status'] not in {'PENDING','REACHED'}:
                control['stop_request']={'requested_at':p['requested_at'],'requested_round':control['round_number'],
                                        'status':'REACHED' if control['state']=='WAITING_HUMAN_AT_P14' else 'PENDING','event_ref':e['event_id']}
        else:
            require(not p,'CONTROL_EVENT_INVALID','Cancellation takes no replacement policy')
            if control.get('stop_request'):control['stop_request']={**control['stop_request'],'status':'CANCELLED','cancel_event_ref':e['event_id']}
        control['control_version']+=1
        control.update(last_instruction_ref=e['event_id'],last_instruction_at=e['issued_at'])
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
    elif kind=='EXTEND_MISSION_BUDGET':
        instance=select_instance(s,iid);mid=instance.get('current_mission_id')
        mission=s.get('missions',{}).get(mid)
        require(set(p)=={'added_calls','reason'} and type(p['added_calls']) is int and 1<=p['added_calls']<=1000
                and isinstance(p['reason'],str) and 0<len(p['reason'].strip())<=12000,
                'AUTHORIZATION_REQUIRED','Authorize one to 1000 additional calls with a concrete reason.')
        require(instance['status']!='ENDED' and mission and mission['status']=='ACTIVE' and e['mission_id']==mid,
                'AUTHORIZATION_REQUIRED','Additional calls must belong to the current existing active mission.')
        grant=s['budget_grants'][mission['budget_grant_id']];project=s['project_budget']
        require(grant.get('explicit_unlimited') is not True and project.get('explicit_unlimited') is not True
                and type(grant.get('max_calls')) is int and grant['max_calls']>=0
                and type(project.get('max_calls')) is int and project['max_calls']>=0,
                'AUTHORIZATION_REQUIRED','This operation extends existing finite mission and project budgets only.')
        grant['max_calls']+=p['added_calls'];project['max_calls']+=p['added_calls']
        # Exact frozen tasks, uncertainty, responsibility allowances and the
        # human pause state are intentionally outside this budget operation.
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
            require(type(b['max_workers']) is int and 1<=b['max_workers']<=8,'AUTHORIZATION_REQUIRED','Project concurrency must be explicitly bounded at one to eight')
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
        if instance['kind'] in {'TRH','FDH'}:
            control=instance['run_control']
            control['automatic_authorization_ref']=e['event_id'] if control['mode']=='AUTO_P14' else None
            control.update(state='RUNNING',control_version=control['control_version']+1,
                           last_instruction_ref=e['event_id'],last_instruction_at=e['issued_at'])
    elif kind in {'PAUSE','RESUME'}:
        instance=select_instance(s,iid)
        require(p.get('reason') or p.get('decision_ref'),'AUTHORIZATION_REQUIRED','Control reason or recorded decision required')
        if kind=='RESUME':
            ref=p.get('decision_ref');decision=s.get('control_events',{}).get(ref,{})
            require(decision.get('event_type')=='HUMAN_DECISION' and decision.get('instance_id')==iid
                    and decision.get('mission_id')==instance.get('current_mission_id')
                    and decision['payload']['action']==('CONTINUE_DISCOVERY' if instance['kind']=='FDH' else 'CONTINUE'),
                    'AUTHORIZATION_REQUIRED','Resume requires the exact current mission continuation decision')
            require(instance['current_mission_id'] in s.get('missions',{}),'AUTHORIZATION_REQUIRED','No authorized mission')
            if instance['kind'] in {'TRH','FDH'}:
                control=instance['run_control']
                require(control.get('human_continue_ref')==ref and control.get('last_instruction_ref')==ref,
                        'STALE_CONTROL_INSTRUCTION','A prior continuation cannot override a later pause, end or control instruction')
        instance['status']='PAUSED' if kind=='PAUSE' else 'ACTIVE'
        if instance['kind'] in {'TRH','FDH'}:
            control=instance['run_control']
            if kind=='RESUME':control['state']='RUNNING'
            elif control['state'] not in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5'}:
                control['state']='PAUSED'
            control.update(control_version=control['control_version']+1,last_instruction_ref=e['event_id'],
                           last_instruction_at=e['issued_at'],pause_reason=p.get('reason') if kind=='PAUSE' else None)
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
            require((action=='CONTINUE_DISCOVERY')==(instance['kind']=='FDH'),
                    'CONTROL_EVENT_INVALID','FDH uses explicit CONTINUE_DISCOVERY; TRH and SURVEY use CONTINUE')
            require(mission.get('status')=='ACTIVE' and mission.get('budget_grant_id') in s.get('budget_grants',{}),'AUTHORIZATION_REQUIRED','Continuation does not create scope or budget')
            instance['status']='ACTIVE'
            if instance['kind'] in {'TRH','FDH'}:
                control=instance['run_control']
                if control['state'] in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5'}:control['round_number']+=1
                control['state']='RUNNING';control['stop_request']=None;control['control_version']+=1
                control['human_continue_ref']=e['event_id']
                control['pause_reason']=None
        elif action=='PAUSE':
            instance['status']='PAUSED'
            if instance['kind'] in {'TRH','FDH'}:
                control=instance['run_control']
                if control['state'] not in {'WAITING_HUMAN_AT_P14','WAITING_HUMAN_AT_D5'}:control['state']='PAUSED'
                control['control_version']+=1;control['pause_reason']=p['note']
        elif action in {'END','END_WITHOUT_ADOPTION'}:
            instance['status']='ENDED'
            if instance['kind'] in {'TRH','FDH'}:
                instance['run_control'].update(state='OPEN_ENDED',control_version=instance['run_control']['control_version']+1)
        if instance['kind'] in {'TRH','FDH'}:
            instance['run_control'].update(last_instruction_ref=e['event_id'],last_instruction_at=e['issued_at'])
    elif kind=='CANCEL_REQUEST':
        r=s.get('requests',{}).get(p.get('request_id'))
        require(r and r['instance_id']==iid,'TASK_FENCED','Exact workflow request required')
        require(p.get('reason'),'AUTHORIZATION_REQUIRED','Cancellation reason required')
        r['fenced']=True
        if r['execution_state']=='PREPARED':r['execution_state']='CANCELLED_BEFORE_SEND'
    elif kind=='DISCOVERY_SCOPE_DEFINED':
        instance=select_instance(s,iid)
        require(instance['kind']=='FDH' and set(p)=={'discovery_scope'},'DISCOVERY_SCOPE_INVALID','Exact discovery scope update required')
        require(not instance.get('mission_ids') and not any(t['instance_id']==iid for t in s['tasks'].values()),
                'DISCOVERY_SCOPE_IMMUTABLE','Only an unassigned discovery draft can be completed')
        old=instance.get('discovery_scope') or {};new=deepcopy(p['discovery_scope'])
        require(not instance.get('mission_ids') or all(new.get(k)==v for k,v in old.items()),
                'DISCOVERY_SCOPE_IMMUTABLE','已授权的研究范围不能更改；请另建研究流程。')
        instance['discovery_scope']=new
        if new.get('phenomenon_ref'):instance['discovery_brief_ref']=new['phenomenon_ref']
        validate_discovery_scope(s,instance,required=False)
    elif kind=='REQUEST_CORRECTION':
        from .corrections import apply
        apply(s,e)
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
    if iid and iid in s.get('instances',{}) and s['instances'][iid]['kind'] in {'TRH','FDH'}:
        from .research_audit import transition
        transition(s,iid,at=e['issued_at'])
    return s


def configure_p14(store, instance_id, *, mode=None, stop_next=None):
    """Persist user controls through the same lock/version used by MAIN decisions."""
    require(mode is not None or stop_next is not None,'CONTROL_EVENT_INVALID','Specify a P14 control')
    if mode is not None:
        mode={'AUTO':'AUTO_P14','MANUAL':'HUMAN_P14'}.get(mode,mode)
        s=store.read_snapshot()
        store.commit_control(event(s,'SET_P14_MODE',{'mode':mode},instance_id=instance_id))
    if stop_next is not None:
        require(type(stop_next) is bool,'CONTROL_EVENT_INVALID','Stop request must be boolean')
        s=store.read_snapshot()
        store.commit_control(event(s,'REQUEST_STOP_AT_P14' if stop_next else 'CANCEL_STOP_AT_P14',
                                   {'requested_at':now()} if stop_next else {},instance_id=instance_id))
    return {'instance_id':instance_id,'run_control':deepcopy(store.read_snapshot()['instances'][instance_id]['run_control']),'model_calls':0}


def preserve_main_report(snapshot, task, request, proposal, proposal_id, *, report_body=None):
    """Freeze actual MAIN prose in its acceptance transaction, without a new call.

    An explicit P13 account may accompany continued work in the same round. It
    changes neither the round nor its P14 stop state; only apply_p14_decision
    below has that responsibility.
    """
    iid=task['instance_id'];instance=snapshot['instances'][iid]
    require(task.get('actor_kind')=='MAIN' and instance['kind'] in {'TRH','FDH'},
            'AUTHORIZATION_REQUIRED','Only the owning product MAIN may account a harness round')
    require(task['request_id']==request['request_id'] and request.get('capture_ref'),
            'MAIN_DECISION_REQUIRED','A captured native MAIN decision is required')
    decision=proposal.get('p14_decision') or {}
    account=deepcopy(proposal['progress_account'])
    report=report_body if report_body is not None else decision.get('report_body') or account.get('summary')
    require(isinstance(report,str) and report.strip(),'ROUND_REPORT_REQUIRED','Save an actual readable MAIN progress account')
    control=instance.get('run_control',{})
    round_number=control.get('round_number',1)
    did=identity([iid,task['request_id'],proposal_id,round_number],'DELIVERY-')
    summary={'schema':'pmrs.round-account/4.2.2','instance_id':iid,'mission_id':task['mission_id'],
        'stage_id':'P13' if instance['kind']=='TRH' else 'D5','workflow_kind':instance['kind'],
        'delivery_kind':'PROGRESS_ACCOUNT',
        'round_number':round_number,'target_ref':instance.get('target_ref'),
        'scientific_completion':False,'state':'OPEN','progress_account':account,
        'report_body':report,'main_request_id':request['request_id'],'main_capture_ref':request['capture_ref'],
        'proposal_id':proposal_id,'model_calls':0}
    delivery={'delivery_id':did,'instance_id':iid,'mission_id':task['mission_id'],
        'basis_commit':snapshot.get('knowledge_commit'),'summary':summary,'report_body':report,
        'round_number':round_number,'at':now(),'timestamp_basis':'DELIVERY_ACCEPTANCE',
        'target_ref':instance.get('target_ref')}
    snapshot.setdefault('round_deliveries',{})[did]=delivery
    snapshot['missions'][task['mission_id']]['delivery_ref']=did
    return delivery


def apply_p14_decision(snapshot, task, request, proposal, proposal_id):
    """Apply captured MAIN P14 choice after freezing the round report atomically.

    The current user stop state wins over a previously frozen MAIN proposal.
    Neither this reducer nor a P14 transition grants budget or changes the goal.
    """
    delivery=preserve_main_report(snapshot,task,request,proposal,proposal_id)
    iid=task['instance_id'];instance=snapshot['instances'][iid]
    did=delivery['delivery_id'];summary=delivery['summary'];round_number=delivery['round_number']
    decision=proposal.get('p14_decision') or {};control=instance.get('run_control',{})
    if instance['kind']=='FDH':
        instance['status']='PAUSED'
        control.update(state='WAITING_HUMAN_AT_D5',last_delivery_ref=did,
                       control_version=control['control_version']+1,
                       pause_reason='Formal D5 delivery awaits the researcher’s explicit choice.')
        summary.update(state='WAITING_HUMAN_AT_D5',next_decision='HUMAN',delivery_kind='FORMAL_D5')
        return {'allow_dispatch':False,'delivery_id':did,'state':'WAITING_HUMAN_AT_D5'}
    control['last_delivery_ref']=did
    summary['delivery_kind']='P13_P14'
    stop=control.get('stop_request')
    if control['mode']=='HUMAN_P14' or stop and stop['status'] in {'PENDING','REACHED'}:
        if stop and stop['status']=='PENDING':control['stop_request']={**stop,'status':'REACHED','reached_round':round_number,'delivery_ref':did}
        control['state']='WAITING_HUMAN_AT_P14';instance['status']='PAUSED';control['control_version']+=1
        summary.update(state='WAITING_HUMAN_AT_P14',next_decision='HUMAN')
        return {'allow_dispatch':False,'delivery_id':did,'state':control['state']}
    action=decision.get('action')
    require(action in {'CONTINUE','COMPLETE','WAIT'},'MAIN_DECISION_REQUIRED','Automatic P14 needs an explicit MAIN decision')
    require(decision.get('rationale'),'MAIN_DECISION_REQUIRED','MAIN must explain the P14 decision')
    require(control.get('automatic_authorization_ref'),'AUTHORIZATION_REQUIRED','Automatic mode must reference the actual user authorization')
    qualified=completion_evidence(snapshot,iid,decision.get('completion_evidence',[])) if action=='COMPLETE' else []
    require(action!='COMPLETE' or qualified,'SCIENTIFIC_COMPLETION_UNQUALIFIED',
            'Original-target completion requires exact independent positive/adversarial scope and unconditional support')
    event_id=identity([proposal_id,control['control_version'],did],'MAIN-P14-')
    row={'event_id':event_id,'event_type':'MAIN_P14_DECISION','actor':'MAIN','instance_id':iid,
         'mission_id':task['mission_id'],'request_id':request['request_id'],'capture_ref':request['capture_ref'],
         'proposal_id':proposal_id,'automatic_authorization_ref':control['automatic_authorization_ref'],
         'control_version':control['control_version'],'round_number':round_number,'delivery_ref':did,
         'action':action,'rationale':decision['rationale'],'qualified_evidence':qualified}
    snapshot.setdefault('main_decisions',{})[event_id]=row
    control['last_decision_ref']=event_id;control['control_version']+=1
    if action=='COMPLETE':
        instance['status']='COMPLETE';control['state']='COMPLETE'
        summary.update(state='COMPLETE',scientific_completion=True,next_decision='NONE')
    elif action=='CONTINUE':
        control['round_number']+=1;control['state']='RUNNING'
        summary.update(state='OPEN_CONTINUING',next_decision='MAIN',next_round=control['round_number'])
    else:
        require(proposal.get('waiting_condition') or proposal.get('wait_condition'),'WAIT_CONDITION_REQUIRED','WAIT must name an observable condition')
        control['state']='WAITING_CONDITION';summary.update(state='WAITING_CONDITION',next_decision='MAIN_ON_EVENT')
    return {'allow_dispatch':action=='CONTINUE','delivery_id':did,'state':control['state'],'decision_ref':event_id}
