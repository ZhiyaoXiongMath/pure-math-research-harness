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
        require(instance['kind']=='TFDW','DISCOVERY_SCOPE_INVALID','Only TFDW has discovery scope')
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
        require(kind in {'TRW','TFDW','SURVEY'},'WORKFLOW_KIND_INVALID',str(kind))
        if name is not None:require(isinstance(name,str) and 0<len(name.strip())<=200,'INSTANCE_NAME_INVALID','研究流程名称须为 1–200 字符。')
        require(kind!='TRW' or not discovery_scope and brief is None,'DISCOVERY_SCOPE_INVALID','TRW uses a fixed target, not a discovery scope')
        require(not (target_ref and target is not None),'TARGET_REQUIRED','Choose an exact existing target or provide new original text')
        require(kind=='TRW' or target is None,'TARGET_REQUIRED','TFDW does not have a fixed target')
        source_ref=None;scope=None
        if target is not None:
            result=store.commit(changes.prepare_source_input(store.read_snapshot(),target,title=name or '研究题目',purpose='PROBLEM',blob_get=store.read_blob));target_ref=result['target_ref']
        if kind=='TFDW':
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

    def recover(self,store,request_id,*,check_only=False):
        return execution.recover(store,request_id,check_only=check_only)

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


def start_round(store,instance_id,intent,*,max_calls=8,max_workers=1,policy=None,model_overrides=None,max_research_attempts=1,allow_reports=True,report_first_actions=None,stage=None,selected_refs=None,source_refs=None):
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
    if instance['kind']=='SURVEY':
        from .survey import start_activity
        return start_activity(store,instance_id,stage,intent,max_calls=max_calls,max_workers=max_workers,policy=policy,
            model_overrides=model_overrides,max_research_attempts=max_research_attempts,allow_reports=allow_reports,report_first_actions=report_first_actions,selected_refs=selected_refs,source_refs=source_refs)
    discovery_scope=W.validate_discovery_scope(s,instance)
    if model_overrides is not None:
        from .model_policy import merge_overrides
        policy=deepcopy(policy or {});existing=deepcopy(policy.get('model_overrides',[]))
        if policy.get('model_override'):existing.append(policy.pop('model_override'))
        policy['model_overrides']=merge_overrides(existing,model_overrides,workflow_kind=instance['kind'],capabilities=policy.get('model_capabilities'))
    require(instance['status']!='ENDED','AUTHORIZATION_REQUIRED','An ended workflow needs an explicit new research instance')
    intent_ref=store.blob(intent.encode('utf-8'))
    mid=identity({'instance':instance_id,'intent':intent_ref,'ordinal':len(instance['mission_ids'])+1},'MISSION-')
    oid=identity({'instance':instance_id,'intent':intent_ref,'responsibility':'initial-research'},'OB-')
    bid=identity({'mission':mid,'obligation':oid},'BINDING-');gid=identity({'mission':mid,'obligation':oid},'RETRY-')
    # A genuinely new human round may share an existing scientific responsibility.
    # The identity/ledger is not reset by the new mission wrapper.
    targets=[instance['target_ref']] if instance['kind']=='TRW' else []
    if instance['kind']=='TRW':
        stage,role,kind='P4','RESEARCH','ESTABLISH'
        criterion='Investigate the exact fixed target under its original hypotheses and quantifiers, within the attached human research intent. Produce an actual argument, construction or precisely located failure. If a concrete missing step is discovered, propose only that bounded responsibility. Do not replace the original target or claim proof from task completion.'
    else:
        stage,role,kind='D1','LEARN','APPLICABILITY'
        criterion='Investigate the supplied phenomenon and the exact human discovery intent. Preserve the immutable background and permitted variation axes. Account for positive, negative and unknown evidence. Propose a precise candidate or a concrete bounded formulation or discrimination responsibility only when justified; zero candidates is a valid outcome.'
    criterion_ref=store.blob(criterion.encode())
    source_refs=[ref for ref,row in s.get('sources',{}).items() if row.get('access_class','SCIENTIFIC_SOURCE')=='SCIENTIFIC_SOURCE']
    # The intent itself is an immutable user source, so it is present in every
    # actual request and counted in the model context rather than just named.
    intent_receipt=store.commit(changes.prepare_source_input(s,intent.encode(),title='Human research intent',purpose='PHENOMENON',blob_get=store.read_blob))
    source_refs.append(intent_receipt['source_ref']);s=store.read_snapshot()
    inherited=s.get('handoffs',{}).get(instance.get('inherited_handoff_ref'),{})
    inherited_refs=list(dict.fromkeys(inherited.get('context_refs',[])+inherited.get('argument_refs',[])+inherited.get('example_refs',[])+([inherited['target_ref']] if inherited.get('target_ref') else [])))
    consumer={'binding_id':bid,'instance_id':instance_id,'mission_id':mid,'stage_id':stage,'role':role,
              'retry_grant_id':gid,'method_ref':'INITIAL_INVESTIGATION','scope':{'target_refs':targets,'intent_ref':intent_ref},
              'entry_basis':{},'input_refs':inherited_refs,'source_refs':sorted(set(source_refs)),'threshold':'ARTIFACT_AVAILABLE',
              'success_criterion':criterion_ref,'ready_since':s.get('_snapshot_sequence',0)}
    obligation=O.make(oid,kind,targets,criterion_ref,consumer_bindings=[consumer],created_by='HUMAN_SCOPE',effect='FIXED_TARGET_RESEARCH' if targets else 'DISCOVERY_EVIDENCE')
    if oid in s['obligations']:
        # Exact repeated round intent shares the original responsibility. The
        # existing definition and attempts are retained; add the new consumer
        # after authorization through the typed host path.
        obligation=None
    mission={'mission_id':mid,'instance_id':instance_id,'intent_ref':intent_ref,'authorized_scope':{
                'target_refs':targets,'source_refs':sorted(set(source_refs)),'allow_derived_work':True,
                'max_research_attempts':max_research_attempts,'formal_target_review':instance['kind']=='TRW',
                'formulation_review':instance['kind']=='TFDW','reports':bool(allow_reports)},'budget_grant_id':'BUDGET-'+mid,
             'obligations':[obligation] if obligation else [],'retry_grants':[{'grant_id':gid,'obligation_id':oid,
                'method_ref':'INITIAL_INVESTIGATION','max_research_attempts':max_research_attempts,
                'max_responsibility_attempts':max_research_attempts,'reason_ref':intent_ref}] if obligation else []}
    if discovery_scope:
        consumer['scope']['discovery_scope']=deepcopy(discovery_scope)
        mission['authorized_scope']['discovery_scope']=deepcopy(discovery_scope)
    if report_first_actions:mission['report_first_actions']=list(report_first_actions)
    budget={'budget_grant_id':mission['budget_grant_id'],'max_calls':max_calls,'max_workers':max_workers,
            'execution_policy':{**deepcopy(policy or {}),'max_workers':max_workers}}
    receipt=store.commit_control(W.authorize_event(s,instance_id,mission,budget))
    if not obligation:
        current=store.read_snapshot();existing=deepcopy(current['obligations'][oid]);existing['definition']['consumer_bindings'].append(consumer);existing['definition']['definition_revision']+=1
        store.commit_execution(execution.event('ASSIGN_OBLIGATION',{'instance_id':instance_id,'mission_id':mid,'obligation':existing,
            'retry_grant':{'grant_id':gid,'obligation_id':oid,'method_ref':'INITIAL_INVESTIGATION','max_research_attempts':max_research_attempts,
                'max_responsibility_attempts':max_research_attempts},'authorization_basis_ref':intent_ref}))
    return {**receipt,'instance_id':instance_id,'mission_id':mid,'status':'ACTIVE','model_calls':0,
            'message_zh':'已记录本轮研究目的和调用上限；后台按具体义务运行，不逐阶段重复询问。'}


def _assign_followup(store,instance,mission,obligation,consumer,*,basis_ref):
    proposed=deepcopy(obligation)
    if proposed['definition']['obligation_id'] in store.read_snapshot()['obligations']:
        proposed['definition']['consumer_bindings'].append(consumer);proposed['definition']['definition_revision']+=1
    else:proposed['definition']['consumer_bindings']=[consumer]
    oid=proposed['definition']['obligation_id'];grant={'grant_id':consumer['retry_grant_id'],'obligation_id':oid,
        'method_ref':consumer.get('method_ref'),'max_research_attempts':mission['authorized_scope'].get('max_research_attempts',1)}
    if consumer.get('max_responsibility_attempts'):grant['max_responsibility_attempts']=consumer['max_responsibility_attempts']
    return store.commit_execution(execution.event('ASSIGN_OBLIGATION',{'instance_id':instance['instance_id'],
        'mission_id':mission['mission_id'],'obligation':proposed,'retry_grant':grant,'authorization_basis_ref':basis_ref}))


def derive_followups(store,instance_id):
    """Bind only accepted concrete gaps and explicitly required review scopes.

    There is no phase counter and no rule which runs every available role.
    """
    from . import obligations as O,assurance,contracts as C
    s=store.read_snapshot();instance=W.select_instance(s,instance_id);mission=s['missions'].get(instance['current_mission_id'])
    if not mission or instance['status']!='ACTIVE' or instance['kind']=='SURVEY':return []
    mid=mission['mission_id'];created=[]
    from .workflows import trw,tfdw
    workflow=trw if instance['kind']=='TRW' else tfdw
    for oid,o in list(s['obligations'].items()):
        d=o['definition']
        if d['consumer_bindings']:continue
        origin=[r for r in s['requests'].values() if r['mission_id']==mid and 'CHANGE-'+str(r.get('capture_ref'))==d.get('created_by')]
        if not origin:continue
        activity=workflow.activity_for_obligation(d)
        if not activity:continue
        stage,role,basis=activity
        consumer={'binding_id':identity({'mission':mid,'obligation':oid,'role':role},'BINDING-'),
            'instance_id':instance_id,'mission_id':mid,'stage_id':stage,'role':role,'entry_basis':basis,
            'retry_grant_id':identity({'mission':mid,'obligation':oid,'role':role},'RETRY-'),'method_ref':'ACCEPTED_CONCRETE_GAP',
            'scope':{'target_refs':d['target_refs']},'threshold':'ARTIFACT_AVAILABLE','source_refs':mission['authorized_scope'].get('source_refs',[])}
        created.append(_assign_followup(store,instance,mission,o,consumer,basis_ref=d['created_by']))
    s=store.read_snapshot()
    # Only original-target candidate arguments trigger the existing formal dual
    # consumer. Other intermediate artifacts remain usable without extra review.
    if instance['kind']=='TRW' and mission['authorized_scope'].get('formal_target_review'):
        for support_id,support in list(s.get('supports',{}).items()):
            if support['statement_ref']!=instance['target_ref']:continue
            author=s.get('tasks',{}).get(support.get('author_task_id'),{})
            if author.get('mission_id')!=mid:continue
            if any(x['support_id']==support_id for x in s.get('coverage_plans',{}).values()):continue
            argument=support['argument_ref']
            scope=[{'target_ref':ref,'locators':[],'aspects':['full_argument' if ref==argument else 'original_target']} for ref in [instance['target_ref'],argument]]
            req=assurance.requirement('REFUTATION_SUPPORT' if s['records'][argument]['data']['mode']=='REFUTATION' else 'PROOF_SUPPORT',scope,review_mode='TARGET_DUAL')
            evaluation=assurance.evaluate_requirement(s,support_id,req)
            for slot in req['review_slots']:
                if slot['slot_id'] not in evaluation['missing_slots']:continue
                role=slot['allowed_roles'][0];oid=identity({'support':support_id,'review_slot':slot['slot_id'],'scope':scope},'OB-')
                if oid in s['obligations']:continue
                criterion=store.blob(('Independently examine the exact original target and selected candidate argument for '+slot['review_kind']+'. Cover the entire frozen scope, retain all unchecked parts, and state defects or uncertainty honestly.').encode())
                c={'binding_id':'BINDING-'+oid,'instance_id':instance_id,'mission_id':mid,'stage_id':'P9','role':role,
                    'retry_grant_id':'RETRY-'+oid,'method_ref':'INDEPENDENT_TARGET_AUDIT','scope':scope,'input_refs':[argument],
                    'source_refs':mission['authorized_scope'].get('source_refs',[]),'threshold':'WORK_DISPOSITION_RECORDED',
                    'required_assurance':req,'selected_support':support_id,'policy_digest':C.digest(req),
                    'entry_basis':{'consumer_requirement':req},'author_execution_event':support.get('author_execution_event')}
                o=O.make(oid,'VERIFY',[instance['target_ref']],criterion,created_by=argument,effect='FORMAL_ORIGINAL_TARGET_REVIEW')
                created.append(_assign_followup(store,instance,mission,o,c,basis_ref=argument));s=store.read_snapshot()
    if instance['kind']=='TFDW' and mission['authorized_scope'].get('formulation_review'):
        refs=sorted({c['statement_ref'] for c in s.get('candidates',{}).values() if c['instance_id']==instance_id})
        if refs:
            oid=identity({'frontier':refs,'instance':instance_id,'purpose':'FORMULATION'},'OB-')
            if oid not in s['obligations']:
                scope=[{'target_ref':r,'locators':[],'aspects':['formulation_and_counterevidence']} for r in refs]
                req=assurance.requirement('FORMULATION',scope)
                criterion=store.blob(b'Independently examine the exact candidate frontier, quantifiers, hypothesis costs, positive and negative evidence, and unknown comparisons. Preference cannot grant proof support.')
                c={'binding_id':'BINDING-'+oid,'instance_id':instance_id,'mission_id':mid,'stage_id':'D4','role':'FORMULATION_REVIEW',
                    'retry_grant_id':'RETRY-'+oid,'method_ref':'INDEPENDENT_FORMULATION_REVIEW','scope':scope,
                    'input_refs':refs,'source_refs':mission['authorized_scope'].get('source_refs',[]),'threshold':'WORK_DISPOSITION_RECORDED',
                    'required_assurance':req,'entry_basis':{}}
                o=O.make(oid,'VERIFY',refs,criterion,created_by=refs[0],effect='FORMULATION_ONLY')
                created.append(_assign_followup(store,instance,mission,o,c,basis_ref=refs[0]))
    return created


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
    policy=Engine().policy(store,instance_id);performed=[];last=None
    # Every pass either performs a bounded request or stops. No empty management
    # call is dispatched to explain a deterministic waiting condition.
    while True:
        s=store.read_snapshot()
        if s['instances'][instance_id]['status']!='ACTIVE':return {'state':'PAUSED','tasks':performed,'model_calls':len(performed)}
        authorized=[iid for iid,row in s['instances'].items() if row['status']=='ACTIVE' and row.get('current_mission_id') in s['missions']]
        for selected_instance in authorized:
            derive_followups(store,selected_instance)
            scheduler.derive_coverage_integration(store,selected_instance)
        if len(performed)>=max_tasks:return {'state':'BATCH_LIMIT','tasks':performed,'model_calls':len(performed)}
        count=max(1,min(s.get('max_workers',1),4,max_tasks-len(performed)))
        try:last=run(store,instance_ids=authorized,executor=executor,max_tasks=count,policy={'max_workers':s.get('max_workers',1),'mission_policies':True})
        except PMRSError as exc:
            if exc.code=='COORDINATOR_BUSY':return {'state':'COORDINATOR_ACTIVE','tasks':performed,'model_calls':len(performed)}
            raise
        performed.extend(last['tasks'])
        for selected_instance in authorized:_close_accounted_visits(store,selected_instance)
        if not last['tasks']:
            return {**last,'tasks':performed,'model_calls':len(performed)}
