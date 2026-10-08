"""Bounded public research plans using native obligations and one mission ledger.

Display keys and method labels are not scientific duty identities. Explicit
problem, framework scope, criteria and exact materials distinguish real work.
No function in this module dispatches a model or automatically advances stages.
"""
from copy import deepcopy
from .util import canonical, identity, require
from . import obligations as O, workflow_instances as W, execution
from .workflows.registry import spec, role_contract, validate_assignment

MAX_ITEMS = 32
ITEM_FIELDS = {'key','stage','role','intent','success_criterion','target_refs','selected_refs','input_refs','source_refs',
               'depends_on','synthesis_of','analysis_route','framework_scope','entry_basis','method_ref','required',
               'obligation_type','write_scope','question_ids'}


def _refs(value, available, label):
    require(isinstance(value,list) and len(value)<=256 and all(isinstance(r,str) and r in available for r in value)
            and len(value)==len(set(value)), 'RESEARCH_PLAN_INVALID', label+' must contain distinct exact native references')
    return sorted(value)


def _text(value, label):
    require(isinstance(value,str) and 0<len(value.strip())<=12000,'RESEARCH_PLAN_INVALID',label+' requires bounded concrete text')
    return value


def _kind(row, role):
    if role in {'PROOF','COUNTEREXAMPLE','INDEPENDENT','SPECIALIST','FORMULATION_REVIEW','ADVERSARIAL_REVIEW','READINESS_REVIEW'}:return 'VERIFY'
    if role=='COVERAGE_REVIEW':return 'ACCOUNT'
    if role=='RECONSTRUCT':return 'ESTABLISH'
    return row['allowed_obligation_types'][0]


def plan_work(store, instance_id, intent, items, *, mission_id=None, max_calls=8, max_workers=None, policy=None,
              model_overrides=None, max_research_attempts=1, allow_reports=False, report_first_actions=None,
              common_input_refs=None, common_source_refs=None):
    """Authorize a finite DAG, or add work inside an already authorized mission.

    `depends_on` accepts a local key or an exact native dependency object.
    `synthesis_of` fixes selected local keys (including explicitly nonessential
    branches). No new budget is created when mission_id is supplied.
    """
    intent=_text(intent,'Plan intent')
    require(isinstance(items,list) and 1<=len(items)<=MAX_ITEMS,'RESEARCH_PLAN_INVALID','A plan needs one to 32 explicit responsibilities')
    s=store.read_snapshot()
    max_workers=s.get('max_workers',1) if max_workers is None else max_workers
    require(type(max_calls) is int and max_calls>=0 and type(max_workers) is int and 1<=max_workers<=8,
            'AUTHORIZATION_REQUIRED','Finite calls and one to eight project workers required')
    require(type(max_research_attempts) is int and 1<=max_research_attempts<=max(1,max_calls),
            'AUTHORIZATION_REQUIRED','Finite cumulative responsibility allowance required')
    instance=W.select_instance(s,instance_id)
    require(instance['status']!='ENDED','AUTHORIZATION_REQUIRED','An ended instance requires a new authorized instance')
    discovery=W.validate_discovery_scope(s,instance)
    common_inputs=_refs(list(common_input_refs or []),s['records'],'Common inputs')
    common_sources=_refs(list(common_source_refs or []),s['sources'],'Common sources')
    if instance.get('target_ref'):common_inputs=sorted(set(common_inputs+[instance['target_ref']]))
    if discovery:common_sources=sorted(set(common_sources+list(discovery.values())))
    rows=[];seen=set()
    for index, supplied in enumerate(items):
        require(isinstance(supplied,dict) and not set(supplied)-ITEM_FIELDS,'RESEARCH_PLAN_INVALID','Unknown plan item fields')
        item=deepcopy(supplied);key=_text(item.get('key',str(index+1)),'Item key')
        require(key not in seen,'RESEARCH_PLAN_INVALID','Plan keys must be unique');seen.add(key)
        row=spec(item.get('stage'));role=item.get('role') or next((r['role'] for r in row['roles'] if r['role'] not in {'HOST','HUMAN'}),None)
        contract=role_contract(row['stage_id'],role)
        require(row['workflow_kind']==instance['kind'] and role not in {'HOST','HUMAN'} and not role.startswith('REPORT_'),
                'NO_MODEL_OPERATION','Use the native host/human or report operation for this stage')
        question=_text(item.get('intent'),'Item intent');success=_text(item.get('success_criterion',question),'Success criterion')
        targets=item.get('target_refs',item.get('selected_refs',[instance['target_ref']] if instance.get('target_ref') else []))
        targets=_refs(targets,s['records'],'Targets')
        inputs=_refs(item.get('input_refs',[]),s['records'],'Inputs')
        sources=_refs(item.get('source_refs',[]),s['sources'],'Sources')
        framework=deepcopy(item.get('framework_scope',{}))
        require(isinstance(framework,(str,dict)) and len(canonical(framework))<=12000,'RESEARCH_PLAN_INVALID','Framework scope must describe bounded real scientific work')
        basis=deepcopy(item.get('entry_basis',{}));require(isinstance(basis,dict),'RESEARCH_PLAN_INVALID','Entry basis must be an object')
        if item.get('analysis_route'):basis['analysis_route']=item['analysis_route']
        if row['stage_id']=='P7':basis.setdefault('analysis_route','SOURCE_APPLICATION' if role=='LEARN' else 'DIRECT_ANALYSIS' if role=='DIRECT' else 'COMPARATIVE')
        for field in ('depends_on','synthesis_of'):
            require(isinstance(item.get(field,[]),list) and len(item.get(field,[]))<=MAX_ITEMS,'RESEARCH_PLAN_INVALID','Bounded dependencies required')
        require(type(item.get('required',True)) is bool,'RESEARCH_PLAN_INVALID','required must be a boolean')
        kind=item.get('obligation_type') or _kind(row,role)
        scientific={'stage':row['stage_id'],'question':question,'success':success,'framework_scope':framework}
        criterion=('Concrete scientific responsibility: '+question+'\nSuccess and honest stopping criterion: '+success+
                   ('\nFramework and obstacle scope: '+canonical(framework).decode() if framework else ''))
        criterion_ref=store.blob(criterion.encode())
        duty_scope={'target_refs':targets,'framework_scope':framework}
        # No plan title, local key, method label, ordinal, mission or role is
        # included here; cosmetic relabelling cannot create another duty budget.
        duty_id=identity({'instance':instance_id,'criterion':criterion_ref,'targets':targets,'scope':duty_scope},'OB-')
        rows.append({'key':key,'stage':row['stage_id'],'role':role,'kind':kind,'question':question,'success':success,
            'criterion_ref':criterion_ref,'oid':duty_id,'scope':duty_scope,'input_refs':inputs,'source_refs':sources,
            'basis':basis,'item':item,'required':item.get('required',True),
            'method_ref':item.get('method_ref','EXPLICIT_SCIENTIFIC_PLAN')})
    require(len({r['oid'] for r in rows})==len(rows),'RESEARCH_PLAN_DUPLICATE_DUTY','Different keys or method labels do not create independent scientific duties')
    by_key={r['key']:r for r in rows}
    for row in rows:
        if row['stage']=='P7' and row['role']=='SYNTHESIS':
            selected=row['item'].get('synthesis_of',[])
            required={r['key'] for r in rows if r['stage']=='P7' and r['role'] in {'LEARN','DIRECT'}}
            require(set(selected)==required and required,'RESEARCH_PLAN_INVALID',
                    'Comparative synthesis must explicitly account for every selected P7 transfer and direct branch')
    for row in rows:
        for dep in row['item'].get('depends_on',[])+row['item'].get('synthesis_of',[]):
            if isinstance(dep,str):require(dep in by_key and dep!=row['key'],'RESEARCH_PLAN_INVALID','Dependency must name another exact plan item')
            else:require(isinstance(dep,dict) and dep.get('binding_ref') and dep.get('threshold') in O.THRESHOLDS,'RESEARCH_PLAN_INVALID','Exact native dependency required')
    intent_ref=store.blob(intent.encode())
    prior=s.get('missions',{}).get(mission_id) if mission_id else None
    if mission_id:
        require(prior and prior['instance_id']==instance_id and prior['status']=='ACTIVE' and instance['status']=='ACTIVE'
                and prior['authorized_scope'].get('allow_derived_work') is True,
                'AUTHORIZATION_REQUIRED','Adding work consumes an active mission that explicitly allows bounded derived work')
        require(instance['kind']!='SURVEY','AUTHORIZATION_REQUIRED','Declare the complete finite Survey batch in its original authorization')
        require(max_research_attempts<=prior['authorized_scope'].get('max_research_attempts',1),
                'AUTHORIZATION_REQUIRED','An added plan cannot enlarge the responsibility sampling allowance')
    mid=mission_id or identity({'instance':instance_id,'intent':intent_ref,'ordinal':len(instance['mission_ids'])+1},'MISSION-')
    plan_id=identity({'instance':instance_id,'duties':sorted(r['oid'] for r in rows),
                     'dependencies':[{k:r['item'].get(k,[]) for k in ('depends_on','synthesis_of')} for r in rows]},'PLAN-')
    for row in rows:
        row['bid']=identity({'mission':mid,'obligation':row['oid'],'role':row['role']},'BINDING-')
        row['gid']=identity({'mission':mid,'obligation':row['oid'],'role':row['role'],'plan':plan_id},'RETRY-')
    branches=[{'key':r['key'],'obligation_id':r['oid'],'binding_id':r['bid'],'stage_id':r['stage'],'role':r['role'],'required':r['required']} for r in rows]
    obligations=[];grants=[];existing=[]
    for row in rows:
        item=row['item'];deps=[]
        for index,dep in enumerate(item.get('depends_on',[])):
            if isinstance(dep,str):
                parent=by_key[dep];deps.append({'dependency_id':identity([row['oid'],parent['oid']],'DEP-'),'binding_ref':parent['oid'],
                    'binding_id':parent['bid'],'threshold':'WORK_DISPOSITION_RECORDED'})
            else:deps.append(deepcopy(dep))
        selected=[]
        for key in item.get('synthesis_of',[]):
            require(isinstance(key,str),'RESEARCH_PLAN_INVALID','Synthesis selection must name local item keys')
            branch=next(b for b in branches if b['key']==key);selected.append(branch)
            deps.append({'dependency_id':identity([row['oid'],branch['obligation_id'],'synthesis'],'DEP-'),'binding_ref':branch['obligation_id'],
                'binding_id':branch['binding_id'],'threshold':'WORK_DISPOSITION_RECORDED','allow_deferred':not branch['required']})
        basis=row['basis'];basis['research_plan']={'plan_id':plan_id,'branch_key':row['key'],'selected_branches':deepcopy(branches),
            'common_input_refs':common_inputs,'common_source_refs':common_sources,'plan_intent':intent}
        if selected:basis['synthesis_branches']=deepcopy(selected)
        validate_assignment(row['stage'],row['kind'],row['role'],basis)
        c={'binding_id':row['bid'],'instance_id':instance_id,'mission_id':mid,'stage_id':row['stage'],'role':row['role'],
           'retry_grant_id':row['gid'],'method_ref':row['method_ref'],'scope':row['scope'],'entry_basis':basis,
           'input_refs':sorted(set(common_inputs+row['input_refs'])),'source_refs':sorted(set(common_sources+row['source_refs'])),
           'success_criterion':row['criterion_ref'],'threshold':'WORK_DISPOSITION_RECORDED','ready_since':s.get('_snapshot_sequence',0)}
        if item.get('write_scope') is not None:c['write_scope']=deepcopy(item['write_scope'])
        if basis.get('consumer_requirement'):c['required_assurance']=deepcopy(basis['consumer_requirement'])
        if instance['kind']=='SURVEY':
            from .survey import plan_consumer
            c=plan_consumer(store,s,instance,row,c,deps)
        o=O.make(row['oid'],row['kind'],row['scope']['target_refs'],row['criterion_ref'],consumer_bindings=[c],
                 dependencies=deps,created_by='HUMAN_RESEARCH_PLAN',effect='BOUNDED_SCIENTIFIC_PLAN')
        grant={'grant_id':row['gid'],'obligation_id':row['oid'],'method_ref':row['method_ref'],
               'max_research_attempts':max_research_attempts,'max_responsibility_attempts':max_research_attempts,'reason_ref':intent_ref}
        if row['oid'] in s['obligations']:
            old=s['obligations'][row['oid']]
            # Repeating the exact already granted binding is a read-only reuse.
            prior_binding=next((b for b in old['definition']['consumer_bindings'] if b['binding_id']==c['binding_id']),None)
            if prior_binding:existing.append((old,None,None));continue
            # A new wrapper cannot replace the original scientific definition or
            # reset its attempts, dependency conditions or responsibility ceiling.
            require({k:v for k,v in o['definition'].items() if k not in {'consumer_bindings','definition_revision'}}==
                    {k:v for k,v in old['definition'].items() if k not in {'consumer_bindings','definition_revision'}},
                    'RESEARCH_PLAN_DUPLICATE_DUTY','Reuse the original responsibility; changed dependencies need an explicit new scientific criterion')
            existing.append((old,c,grant))
        else:obligations.append(o);grants.append(grant)
    O.validate_graph({**s['obligations'],**{o['definition']['obligation_id']:o for o in obligations}})
    if not mission_id:
        # All validation precedes the single native authorization. Repeating an
        # existing Survey batch cannot buy fresh budget with another click.
        require(instance['kind']!='SURVEY' or not existing,'SURVEY_RETRY_REQUIRES_NEW_BASIS','Continue the original batch; duplicate Survey duties do not create a new allowance')
        authorized={'target_refs':sorted({r for row in rows for r in row['scope']['target_refs']}),
            'source_refs':sorted(set(common_sources)|{ref for row in rows for ref in row['source_refs']}),
            'obligation_ids':[r['oid'] for r in rows],'plan_id':plan_id,'allow_derived_work':instance['kind']!='SURVEY',
            'max_research_attempts':max_research_attempts,'formal_target_review':False,'formulation_review':False,'reports':bool(allow_reports)}
        if instance['kind']=='SURVEY':authorized['survey_scope']=deepcopy(instance['survey_scope'])
        if discovery:authorized['discovery_scope']=deepcopy(discovery)
        mission={'mission_id':mid,'instance_id':instance_id,'intent_ref':intent_ref,'authorized_scope':authorized,
                 'budget_grant_id':'BUDGET-'+mid,'obligations':obligations,'retry_grants':grants}
        if report_first_actions is not None:mission['report_first_actions']=W.validate_report_first_actions(report_first_actions)
        policy=deepcopy(policy or {})
        if model_overrides is not None:
            from .model_policy import merge_overrides
            policy['model_overrides']=merge_overrides(policy.get('model_overrides',[]),model_overrides,workflow_kind=instance['kind'],capabilities=policy.get('model_capabilities'))
        budget={'budget_grant_id':mission['budget_grant_id'],'max_calls':max_calls,'max_workers':max_workers,
                'execution_policy':{**policy,'max_workers':max_workers}}
        receipt=store.commit_control(W.authorize_event(store.read_snapshot(),instance_id,mission,budget))
    else:receipt={'outcome':'EXISTING_MISSION','budget_grant_id':prior['budget_grant_id']}
    from .engine import _assign_followup
    if mission_id:
        for o,g in zip(obligations,grants):
            _assign_followup(store,instance,prior,o,o['definition']['consumer_bindings'][0],basis_ref=intent_ref)
    for old,c,g in existing:
        if c is not None:
            current=store.read_snapshot();_assign_followup(store,current['instances'][instance_id],current['missions'][mid],
                current['obligations'][old['definition']['obligation_id']],c,basis_ref=intent_ref)
    return {**receipt,'schema':'pmrs.research-plan/1','plan_id':plan_id,'instance_id':instance_id,'mission_id':mid,
            'obligation_ids':[r['oid'] for r in rows],'bindings':branches,'status':'AUTHORIZED','model_calls':0,
            'budget_created':mission_id is None,'reports_authorized':bool(allow_reports) if not mission_id else bool(prior['authorized_scope'].get('reports'))}
