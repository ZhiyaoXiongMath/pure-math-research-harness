"""Thin application facade for the shared kernel and three independent workflows."""
from copy import deepcopy
from .store import Store
from .util import read, loads, canonical, identity, require, PMRSError
from . import changes, workflow_instances as W, scheduler, execution, tasks, handoff


class Engine:
    def create(self,root,problem,*,title='Mathematical research',phenomenon=False,synthetic=False):
        store=Store.create(root,title,synthetic=synthetic)
        store.commit(changes.prepare_source_input(store.read_snapshot(),problem,title=title,
                     purpose='PHENOMENON' if phenomenon else 'PROBLEM',blob_get=store.read_blob))
        return store

    def create_survey(self,root,scope,*,title='Mathematical survey',synthetic=False,name=None):
        from .survey import normalize_scope
        scope=normalize_scope({'records':{},'sources':{},'instances':{}},scope)
        store=Store.create(root,title,synthetic=synthetic)
        self.new_workflow(store,'SURVEY',name=name or title,survey_scope=scope)
        return store

    def prepare_discovery_scope(self,store,scope,*,brief=None):
        """Preserve supplied text verbatim, or reuse explicit original-source refs."""
        require(isinstance(scope,dict),'DISCOVERY_SCOPE_INVALID','Discovery scope must be a form object')
        allowed={'phenomenon','immutable_background','allowed_axes'}
        require(not set(scope)-allowed-{key+'_ref' for key in allowed},'DISCOVERY_SCOPE_INVALID','Unknown discovery scope field')
        supplied=deepcopy(scope)
        if brief is not None and 'phenomenon' not in supplied and 'phenomenon_ref' not in supplied:supplied['phenomenon']=brief
        # Validate the entire form before preserving any new source.
        for key in allowed:
            require(not (key in supplied and key+'_ref' in supplied),'DISCOVERY_SCOPE_INVALID','Choose original text or an existing source for '+key)
            if supplied.get(key) is not None:
                raw=supplied[key].encode('utf-8') if isinstance(supplied[key],str) else supplied[key]
                require(isinstance(raw,bytes),'DISCOVERY_SCOPE_INVALID','Discovery text must be UTF-8 text')
                raw.decode('utf-8');supplied[key]=raw
            if supplied.get(key+'_ref'):
                ref=supplied[key+'_ref'];source=store.read_snapshot().get('sources',{}).get(ref)
                require(source is not None and source.get('bytes',0)>0,'DISCOVERY_SCOPE_INVALID','Selected discovery source is unavailable')
                require(store.read_blob(source['blob_hash']).strip(),'DISCOVERY_SCOPE_INVALID','Selected discovery source is empty')
        result={}
        for key in ('phenomenon','immutable_background','allowed_axes'):
            raw=supplied.get(key)
            if isinstance(raw,bytes) and raw.strip():
                receipt=store.commit(changes.prepare_source_input(store.read_snapshot(),raw,title=W.DISCOVERY_FIELDS[key+'_ref'],purpose='PHENOMENON',blob_get=store.read_blob))
                result[key+'_ref']=receipt['source_ref']
            elif supplied.get(key+'_ref'):result[key+'_ref']=supplied[key+'_ref']
        return result

    def update_discovery_scope(self,store,instance_id,scope):
        s=store.read_snapshot();instance=W.select_instance(s,instance_id)
        require(instance['kind']=='FDH','DISCOVERY_SCOPE_INVALID','Only FDH has discovery scope')
        require(not instance.get('mission_ids') and not any(t['instance_id']==instance_id for t in s['tasks'].values()),
                'DISCOVERY_SCOPE_IMMUTABLE','只能补齐尚未授权或派发的发现草稿；请为新的范围另建流程。')
        # Existing fields remain immutable once a mission was authorized; callers
        # can explicitly complete a paused native discovery draft.
        merged=deepcopy(instance.get('discovery_scope') or {})
        if not merged.get('phenomenon_ref') and instance.get('discovery_brief_ref'):
            merged['phenomenon_ref']=instance['discovery_brief_ref']
        for key in ('phenomenon','immutable_background','allowed_axes'):
            if key in scope:merged.pop(key+'_ref',None)
        merged.update(scope)
        prepared=self.prepare_discovery_scope(store,merged)
        current=store.read_snapshot()
        return store.commit_control(W.event(current,'DISCOVERY_SCOPE_DEFINED',{'discovery_scope':prepared},instance_id=instance_id))

    def configure_discovery(self,store,instance_id,discovery_scope):
        return self.update_discovery_scope(store,instance_id,discovery_scope)

    def new_workflow(self,store,kind,*,name=None,target_ref=None,target=None,brief=None,discovery_scope=None,survey_scope=None):
        require(kind in {'TRH','FDH','SURVEY'},'WORKFLOW_KIND_INVALID',str(kind))
        if name is not None:require(isinstance(name,str) and 0<len(name.strip())<=200,'INSTANCE_NAME_INVALID','研究流程名称须为 1–200 字符。')
        require(kind!='TRH' or not discovery_scope and brief is None,'DISCOVERY_SCOPE_INVALID','TRH uses a fixed target, not a discovery scope')
        require(not (target_ref and target is not None),'TARGET_REQUIRED','Choose an exact existing target or provide new original text')
        require(kind=='TRH' or target is None,'TARGET_REQUIRED','FDH does not have a fixed target')
        source_ref=None;scope=None
        if target is not None:
            result=store.commit(changes.prepare_source_input(store.read_snapshot(),target,title=name or '研究题目',purpose='PROBLEM',blob_get=store.read_blob));target_ref=result['target_ref']
        if kind=='FDH':
            scope=self.prepare_discovery_scope(store,discovery_scope or {},brief=brief)
            source_ref=scope.get('phenomenon_ref')
        snapshot=store.read_snapshot();instance=W.new_instance(snapshot,kind,target_ref=target_ref,discovery_brief_ref=source_ref,
                name=name,discovery_scope=scope,survey_scope=survey_scope)
        receipt=store.commit_control(W.event(snapshot,'CREATE_INSTANCE',{'instance':instance}))
        return {**receipt,'instance_id':instance['instance_id'],'name':instance.get('name'),'status':'PAUSED','target_ref':target_ref,
                'discovery_scope':deepcopy(scope),'survey_scope':deepcopy(instance.get('survey_scope')),'model_calls':0}

    def authorize(self,store,instance_id,mission,budget):
        mission=deepcopy(mission);budget=deepcopy(budget);snapshot=store.read_snapshot()
        W.validate_discovery_scope(snapshot,W.select_instance(snapshot,instance_id))
        mission['instance_id']=instance_id
        if 'intent' in mission:mission['intent_ref']=store.blob(mission.pop('intent').encode('utf-8'))
        if 'mission_id' not in mission:mission['mission_id']=identity({'instance_id':instance_id,'mission':mission,'ordinal':len(snapshot['missions'])+1},'MISSION-')
        budget.setdefault('budget_grant_id',identity({'mission_id':mission['mission_id'],'budget':budget},'BUDGET-'))
        mission['budget_grant_id']=budget['budget_grant_id']
        for obligation in mission.get('obligations',[]):
            definition=obligation['definition']
            if 'criterion_body' in definition:definition['criterion_body_ref']=store.blob(definition.pop('criterion_body').encode('utf-8'))
            for binding in definition['consumer_bindings']:
                binding['instance_id']=instance_id;binding['mission_id']=mission['mission_id']
        event=W.authorize_event(snapshot,instance_id,mission,budget)
        return {**store.commit_control(event),'instance_id':instance_id,'mission_id':mission['mission_id'],
                'budget_grant_id':budget['budget_grant_id'],'model_calls':0}

    def start_round(self,store,instance_id,intent,**options):
        return start_round(store,instance_id,intent,**options)

    def plan_work(self,store,instance_id,intent,items,**options):
        require(store.read_snapshot()['instances'][instance_id]['kind']=='SURVEY','MAIN_DECISION_REQUIRED','Harness stages are selected by product MAIN; submit a research direction instead')
        from .research_plans import plan_work
        return plan_work(store,instance_id,intent,items,**options)

    def extend_budget(self,store,instance_id,added_calls,reason):
        s=store.read_snapshot();instance=W.select_instance(s,instance_id);mid=instance.get('current_mission_id')
        mission=s.get('missions',{}).get(mid,{})
        before=s.get('budget_grants',{}).get(mission.get('budget_grant_id'),{}).get('max_calls')
        result=store.commit_control(W.event(s,'EXTEND_MISSION_BUDGET',{'added_calls':added_calls,'reason':reason},instance_id=instance_id,mission_id=mid))
        return {**result,'mission_id':mid,'budget_before':before,'budget_after':before+added_calls,'model_calls':0}

    def request_correction(self,store,instance_id,binding_id,instruction,success_criterion):
        from .corrections import request
        return request(store,instance_id,binding_id,instruction,success_criterion)

    def defer_work(self,store,instance_id,binding_id,reason):
        from .obligations import PENDING
        s=store.read_snapshot();W.select_instance(s,instance_id)
        matches=[c for o in s['obligations'].values() for c in o['definition']['consumer_bindings']
                 if c['binding_id']==binding_id and c['instance_id']==instance_id]
        require(len(matches)==1 and isinstance(reason,str) and reason.strip(),'OBLIGATION_INVALID','Select an exact responsibility and preserve its reasoned deferral')
        require(not any(r['execution_state'] in PENDING and
                    any(b['binding_id']==binding_id for b in s['tasks'][r['task_id']].get('obligation_bindings',[]))
                    for r in s['requests'].values()),'EXISTING_REQUEST','Recover or explicitly resolve the original pending request before deferring its responsibility')
        receipt=store.commit_control(W.event(s,'RETIRE_CONSUMER',{'binding_id':binding_id,'reason':reason},
            instance_id=instance_id,mission_id=matches[0]['mission_id']))
        return {**receipt,'binding_id':binding_id,'model_calls':0,'status':'DEFERRED_WITH_REASON'}

    def add_unsent_sources(self,store,instance_id,binding_id,source_refs,reason):
        return execution.add_unsent_sources(store,instance_id,binding_id,source_refs,reason)

    def add_unsent_inputs(self,store,instance_id,binding_id,input_refs,reason):
        return execution.add_unsent_inputs(store,instance_id,binding_id,input_refs,reason)

    def apply_strategy_proposal(self,store,request_id):
        # The original capture owns both science and the atomic native plan.
        return execution.recover(store,request_id)

    def run_round(self,store,instance_id,*,executor=None,max_tasks=1000):
        return run_round(store,instance_id,executor=executor,max_tasks=max_tasks)

    def update_configuration(self,store,instance_id,model_overrides,reason='Explicit future task configuration',*,reset_scopes=None):
        s=store.read_snapshot();instance=W.select_instance(s,instance_id)
        require(instance['current_mission_id'] in s['missions'],'AUTHORIZATION_REQUIRED','An existing authorized mission is required')
        config={'mission_id':instance['current_mission_id'],'model_overrides':deepcopy(model_overrides),'reset_scopes':deepcopy(reset_scopes or []),'reason_ref':store.blob(reason.encode())}
        return store.commit_control(W.event(s,'AUTHORIZE_MISSION',{'future_configuration':config},instance_id=instance_id,mission_id=instance['current_mission_id']))

    def policy(self,store,instance_id):
        s=store.read_snapshot();instance=W.select_instance(s,instance_id)
        mission=s['missions'].get(instance['current_mission_id'],{})
        grant=s['budget_grants'].get(mission.get('budget_grant_id'),{})
        return deepcopy(grant.get('execution_policy',{}))

    def schedule(self,store,instance_id,policy=None):
        return scheduler.plan(store.read_snapshot(),[instance_id],policy or self.policy(store,instance_id))

    def prepare(self,store,instance_id,policy=None):
        policy=policy or self.policy(store,instance_id)
        return scheduler.commit_dispatch(store,self.schedule(store,instance_id,policy),policy=policy)

    def pause(self,store,instance_id,reason):
        s=store.read_snapshot();return store.commit_control(W.event(s,'PAUSE',{'reason':reason},instance_id=instance_id))

    def decide(self,store,instance_id,action,note,*,snapshot_commit,candidate_ref=None,report_ref=None):
        frozen=store.read_snapshot(snapshot_commit)
        decision=W.decide_event(frozen,instance_id,action,note,candidate_ref=candidate_ref,report_ref=report_ref)
        return {**store.commit_control(decision),'decision_id':decision['event_id'],'decision_basis':decision['payload']['decision_basis'],
                'instance_id':instance_id,'model_calls':0}

    def resume(self,store,instance_id,decision):
        s=store.read_snapshot()
        if isinstance(decision,dict) and decision.get('event_type')=='HUMAN_DECISION':
            store.commit_control(decision);s=store.read_snapshot();ref=decision['event_id']
        else:ref=decision.get('decision_id',decision.get('decision_ref')) if isinstance(decision,dict) else decision
        return store.commit_control(W.event(s,'RESUME',{'decision_ref':ref},instance_id=instance_id))

    def preflight(self,store,task_id,raw):
        task=tasks.load(store,task_id);s=store.read_snapshot()
        proposal=changes.validate_response(task,s,raw,'preflight',store.read_blob)
        return {'valid':True,'live_checked':False,'task_id':task_id,'request_id':task['request_id'],
                'content_added':proposal.get('receipt',{}).get('content_added',[]),'model_calls':0,
                'remaining_live_checks':['related inputs','scope membership','authorization and cancellation','write guards']}

    def recover(self,store,request_id,*,check_only=False,recheck=False,reason=None):
        return execution.recover(store,request_id,check_only=check_only,recheck=recheck,reason=reason)

    def reconcile_unknown(self,store,instance_id,request_id,disposition,note,*,not_sent_evidence_ref=None):
        s=store.read_snapshot();W.select_instance(s,instance_id);request=s['requests'].get(request_id)
        require(request and request['instance_id']==instance_id,'REQUEST_UNKNOWN','请选择本研究流程的原始请求。')
        payload={'request_id':request_id,'execution_id':request['execution_id'],'disposition':disposition,'note':note}
        if not_sent_evidence_ref:
            source=s.get('sources',{}).get(not_sent_evidence_ref)
            require(source is not None and source.get('bytes',0)>0,'UNKNOWN_REQUIRES_EVIDENCE','请选择已保存的实际传输证据原件。')
            require(len(store.read_blob(source['blob_hash']))==source['bytes'],'UNKNOWN_REQUIRES_EVIDENCE','证据原件不可用。')
            payload['not_sent_evidence_ref']=not_sent_evidence_ref
        previous=s.get('control_events',{}).get(request.get('reconciliation_event'))
        if previous and previous['payload']==payload:
            return {'outcome':'EXACT_DUPLICATE','event_id':previous['event_id'],'request_id':request_id,'execution_state':request['execution_state'],'model_calls':0}
        result=store.commit_control(W.event(s,'RECONCILE_UNKNOWN',payload,instance_id=instance_id,mission_id=request['mission_id']))
        return {**result,'request_id':request_id,'execution_state':store.read_snapshot()['requests'][request_id]['execution_state'],'model_calls':0}

    def prepare_handoff(self,store,instance_id,direction,scope):
        s=store.read_snapshot();manifest=handoff.prepare(s,scope,direction,from_instance_id=instance_id,
            selection_rationale_ref=scope.get('selection_rationale_ref'))
        result=store.commit_control(W.event(s,'HANDOFF_PREPARED',{'manifest':manifest},instance_id=instance_id))
        return {**result,'handoff_id':manifest['handoff_id'],'manifest':manifest,'model_calls':0}

    def adopt_handoff(self,store,handoff_id,decision):
        s=store.read_snapshot();ref=decision.get('decision_id',decision.get('decision_ref'))
        event=handoff.adopt_event(s,handoff_id,ref,discovery_brief_ref=decision.get('discovery_brief_ref'),
                discovery_scope=decision.get('discovery_scope'),name=decision.get('name'))
        result=store.commit_control(event);state=store.read_snapshot()
        return {**result,'instance_id':state['handoff_adoptions'][ref]['instance_id'],'status':'PAUSED','model_calls':0}


def start_round(store,instance_id,intent,*,max_calls=8,max_workers=None,policy=None,model_overrides=None,max_research_attempts=1,allow_reports=True,report_first_actions=None,stage=None,selected_refs=None,source_refs=None,role=None,items=None,entry_basis=None,p14_mode="AUTO_P14"):
    """Translate one human round form into an exact, finite native authorization.

    No model is used to translate or normalize the supplied intent. Later English
    research output is produced only by the explicitly authorized research work.
    """
    from . import obligations as O
    require(isinstance(intent,str) and intent.strip(),'AUTHORIZATION_REQUIRED','A concrete research intent is required')
    require(type(max_calls) is int and max_calls>=0,'AUTHORIZATION_REQUIRED','Finite model-call allowance required')
    require(type(max_research_attempts) is int and 1<=max_research_attempts<=max(1,max_calls),
            'AUTHORIZATION_REQUIRED','Finite per-responsibility sampling allowance required')
    if report_first_actions is not None:W.validate_report_first_actions(report_first_actions)
    s=store.read_snapshot();instance=W.select_instance(s,instance_id)
    max_workers=s.get('max_workers',1) if max_workers is None else max_workers
    require(instance['kind']=='SURVEY' or items is None and stage is None,
            'MAIN_DECISION_REQUIRED','TRH and FDH research stages are selected by product MAIN; submit a research direction instead')
    if stage is None and items is None:
        from .autoflow import start_round as automatic_round
        return automatic_round(store,instance_id,intent,max_calls=max_calls,max_workers=max_workers,policy=policy,
            model_overrides=model_overrides,max_research_attempts=max_research_attempts,allow_reports=allow_reports,
            report_first_actions=report_first_actions,selected_refs=selected_refs,source_refs=source_refs,p14_mode=p14_mode)
    if instance['kind']=='SURVEY':
        from .survey import start_activity
        return start_activity(store,instance_id,stage,intent,max_calls=max_calls,max_workers=max_workers,policy=policy,
            model_overrides=model_overrides,max_research_attempts=max_research_attempts,allow_reports=allow_reports,report_first_actions=report_first_actions,selected_refs=selected_refs,source_refs=source_refs,role=role)
    raise PMRSError('MAIN_DECISION_REQUIRED','Use the product MAIN research entry point')


def _assign_followup(store,instance,mission,obligation,consumer,*,basis_ref):
    proposed=deepcopy(obligation)
    if proposed['definition']['obligation_id'] in store.read_snapshot()['obligations']:
        proposed['definition']['consumer_bindings'].append(consumer);proposed['definition']['definition_revision']+=1
    else:proposed['definition']['consumer_bindings']=[consumer]
    from .input_plans import enrich_consumer
    consumer=enrich_consumer(store.read_snapshot(),proposed,consumer,blob_get=store.read_blob)
    proposed['definition']['consumer_bindings']=[consumer if c['binding_id']==consumer['binding_id'] else c for c in proposed['definition']['consumer_bindings']]
    oid=proposed['definition']['obligation_id'];grant={'grant_id':consumer['retry_grant_id'],'obligation_id':oid,
        'method_ref':consumer.get('method_ref'),'max_research_attempts':mission['authorized_scope'].get('max_research_attempts',1)}
    if consumer.get('max_responsibility_attempts'):grant['max_responsibility_attempts']=consumer['max_responsibility_attempts']
    return store.commit_execution(execution.event('ASSIGN_OBLIGATION',{'instance_id':instance['instance_id'],
        'mission_id':mission['mission_id'],'obligation':proposed,'retry_grant':grant,'authorization_basis_ref':basis_ref}))


def derive_followups(store,instance_id):
    """Only relay scientific events to MAIN; Survey retains linear advancement."""
    from .autoflow import advance
    return advance(store,instance_id)


def _close_accounted_visits(store,instance_id):
    from .workflows.registry import validate_exit
    s=store.read_snapshot()
    for vid,v in list(s.get('visits',{}).items()):
        if v['instance_id']!=instance_id or v['outcome'] is not None:continue
        requests=[r for r in s['requests'].values() if s['tasks'][r['task_id']].get('visit_id')==vid]
        if not requests or any(r['execution_state'] not in {'SETTLED','CANCELLED_BEFORE_SEND'} for r in requests):continue
        bindings=v['assigned_obligation_bindings'];open_bindings=[]
        for b in bindings:
            o=s['obligations'][b['obligation_id']]
            if o['projection'].get('consumer_resolutions',{}).get(b['binding_id'])!='SATISFIED_FOR_CONSUMER':open_bindings.append(b)
        reason=store.blob(b'The actual frozen requests are settled. Any unresolved mathematical responsibility remains open; unperformed stages are not backfilled.')
        disposition={'visit_id':vid,'outcome':'INVESTIGATED_OPEN' if open_bindings else 'FULFILLED_FOR_SCOPE',
            'completed_work_bindings':bindings,'open_mathematical_bindings':open_bindings,'unperformed_bindings':[],
            'next_activity_proposal':None,'reason_ref':reason}
        store.commit_execution(execution.event('VISIT_DISPOSED',{'disposition':disposition}));s=store.read_snapshot()


def run_round(store,instance_id,*,executor=None,max_tasks=1000):
    from .runner import run
    require(type(max_tasks) is int and 1<=max_tasks<=1000,'BATCH_INVALID','Bounded task batch required')
    s=store.read_snapshot();instance=W.select_instance(s,instance_id);mission=s['missions'].get(instance['current_mission_id'])
    require(mission is not None,'AUTHORIZATION_REQUIRED','Start an explicitly authorized research round first')
    if instance['status']!='ACTIVE':return {'state':'PAUSED','tasks':[],'model_calls':0}
    authorized=[iid for iid,row in s['instances'].items() if row['status']=='ACTIVE' and row.get('current_mission_id') in s['missions']]
    report_waits={}
    def refresh_work(current_store,*_):
        current=current_store.read_snapshot();before=current['knowledge_commit']
        for request in current['requests'].values():
            if request['execution_state']=='PREPARED' and current['tasks'][request['task_id']].get('purpose')=='PROJECT_ASSISTANT':
                current_store.commit_execution(execution.event('LEGACY_ASSISTANT_RETIRED_UNSENT',{
                    'request_id':request['request_id'],'reason':'4.2.2 removed new assistant dispatch. This unsent original task and its history remain readable.'}))
        authorized[:]=[iid for iid,row in current['instances'].items() if row['status']=='ACTIVE' and row.get('current_mission_id') in current['missions']]
        for selected_instance in authorized:
            now=current_store.read_snapshot()['instances'][selected_instance]
            if now['status']!='ACTIVE':continue
            from . import corrections
            if now['kind']=='SURVEY':corrections.advance(current_store,selected_instance)
            if now['kind'] in {'TRH','FDH'} or not any(not c['complete'] for c in corrections.pending(current_store.read_snapshot(),selected_instance)):
                derive_followups(current_store,selected_instance)
            if now['kind']=='SURVEY':scheduler.derive_coverage_integration(current_store,selected_instance)
            _close_accounted_visits(current_store,selected_instance)
        from . import communication
        snapshot=current_store.read_snapshot();groups={}
        for task in snapshot.get('tasks',{}).values():
            gid=task.get('communication_contract',{}).get('group_ref')
            if gid and task['instance_id'] in authorized:
                groups.setdefault(gid,[]).append(task['request_id'])
        for gid,requests in groups.items():
            if len(requests)<2:continue
            old=snapshot.get('collaboration_groups',{}).get(gid)
            if old and set(old['request_ids'])==set(requests):continue
            communication.bind_group(current_store,requests,'Accepted main scientific collaboration',
                'The accepted native plan binds these exact frozen responsibilities to one cooperative interface.',group_id=gid)
        # Explicitly requested reports join the same live project queue, including
        # requests made while another workflow has slow model calls in flight.
        from . import reports
        from .render import Renderer
        snapshot=current_store.read_snapshot()
        for iid,rid in snapshot.get('active_reports',{}).items():
            if iid not in authorized or snapshot['instances'][iid]['status']!='ACTIVE':continue
            try:
                step=reports.advance(current_store,iid,rid,renderer=Renderer())
                if step.get('state') in {'RESOURCE_WAIT','REPORT_BLOCKED'}:report_waits[rid]=step
                else:report_waits.pop(rid,None)
            except PMRSError as exc:
                if exc.code.startswith(('REPORT_','SURVEY_')) or exc.code in {'RESOURCE_WAIT','RESOURCE_DISK_LOW','DAMAGED_ACTIVE_ARTIFACT'}:
                    report_waits[rid]={'code':exc.code,'message':exc.message,'report_id':rid,'model_calls':0}
                else:raise
        return current_store.read_snapshot()['knowledge_commit']!=before
    try:
        # One live queue refills on each result; independent slow requests stay active.
        result=run(store,instance_ids=authorized,executor=executor,max_tasks=max_tasks,
                   policy={'max_workers':s.get('max_workers',1),'mission_policies':True},
                   on_result=refresh_work,on_idle=refresh_work,on_tick=refresh_work)
        result={**result,'report_waits':list(report_waits.values())}
        from .rounds import record
        result['round_result']=record(store,instance_id,result)
        return result
    except PMRSError as exc:
        if exc.code=='COORDINATOR_BUSY':return {'state':'COORDINATOR_ACTIVE','tasks':[],'model_calls':0}
        from .rounds import record
        from . import incidents
        incidents.detect(store,instance_id,exc,location='Engine.run_round')
        record(store,instance_id,{'state':'FAULT','error':{'code':exc.code,'message':str(exc)}})
        raise
