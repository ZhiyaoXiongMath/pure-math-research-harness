"""Persistent research choices, never mathematical authority or a second scheduler.

The same captured KCS atomically admits scientific candidates, the strategy
revision and bounded native assignments. Reads and repeated triggers are free.
"""
from copy import deepcopy
from .util import canonical, identity, require, sha, now, PMRSError
from .research_audit import MAPS as AUDIT_MAPS

SCHEMA='pmrs.strategy/1'
PROPOSAL_SCHEMA='pmrs.strategy-proposal/1'
MAPS=frozenset({'strategies','research_routes','strategy_triggers','strategy_proposals',
                'human_directions','main_replies','strategy_events','consumer_controls','live_main_dispatches','main_execution_recoveries',
                'obligations','retry_grants','execution_events','instances','missions','visits','requests','round_accounts','round_deliveries','main_decisions','retired_consumers'}) | AUDIT_MAPS
ROUTE_STATES={'PROPOSED','ACTIVE','PARKED','EXHAUSTED','REFUTED_ON_SCOPE','SUPERSEDED'}
MAIN_STAGES={'MAIN_TRH','MAIN_FDH'}

def event(kind,payload):
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':kind,'payload':deepcopy(payload)}
    return {**e,'event_id':identity(e,'STRATEGY-EVENT-')}

from pmrh.application.read_projections import strategy_id as strategy_id

from pmrh.application.read_projections import strategy_current as current

def frontier(s,iid,mid):
    """Only actual scientific/version changes; no HEAD, timestamps or counters."""
    rows=[]
    for request in s.get('requests',{}).values():
        if request.get('instance_id')!=iid or request.get('mission_id')!=mid:continue
        task=s.get('tasks',{}).get(request['task_id'],{})
        if task.get('actor_kind')=='MAIN' or task.get('budget_domain','SCIENCE')!='SCIENCE':continue
        if request.get('execution_state')=='SETTLED':
            rows.append({'request_id':request['request_id'],'capture_ref':request.get('capture_ref'),
                         'acceptance_state':request['acceptance_state'],'bindings':[b['binding_id'] for b in task.get('obligation_bindings',[])]})
    return sorted(rows,key=lambda r:r['request_id'])

def frontier_digest(s,iid,mid):
    """Semantic MAIN read set: no global HEAD, timestamps or self-created work."""
    instance=s['instances'][iid];mission=s.get('missions',{}).get(mid,{})
    cfg=mission.get('authorized_scope',{}).get('autoflow',{})
    sources=sorted(set(cfg.get('source_refs',[])+list(mission.get('authorized_scope',{}).get('discovery_scope',{}).values())))
    gaps=[]
    for oid,o in s.get('obligations',{}).items():
        bindings=o['definition']['consumer_bindings']
        if any(c.get('actor_kind')=='MAIN' for c in bindings):continue
        if any(c.get('instance_id')==iid and c.get('mission_id')==mid for c in bindings) or not bindings and str(o['definition'].get('created_by','')).startswith('CHANGE-'):
            projection=o.get('projection',{})
            if projection.get('attempt_accounts') or not bindings:
                gaps.append([oid,projection.get('attempt_accounts'),projection.get('blocker_refs'),projection.get('resolution')])
    failures=[{'request_id':r['request_id'],'execution_state':r.get('execution_state'),'acceptance_state':r.get('acceptance_state'),
              'failure':r.get('error') or r.get('failure_reason')} for r in s.get('requests',{}).values()
              if r.get('instance_id')==iid and r.get('mission_id')==mid and s['tasks'][r['task_id']].get('actor_kind')!='MAIN'
              and r.get('execution_state') in {'UNKNOWN','FAILED','CAPTURED','CANCELLED_BEFORE_SEND'}]
    messages=[{'message_id':m.get('message_id'),'body_ref':m.get('body_ref'),'status':m.get('status'),'withdrawn':m.get('withdrawn')}
        for m in s.get('research_messages',{}).values() if m.get('instance_id')==iid and
        (m.get('recipient_actor_id')=='MAIN-'+iid or m.get('recipient',{}).get('kind')=='MAIN')]
    control=instance.get('run_control',{})
    return identity({'target':instance.get('target_ref'),'work':frontier(s,iid,mid),'gaps':sorted(gaps,key=lambda r:r[0]),
        'source_versions':[[r,s.get('sources',{}).get(r),s.get('survey_source_status',{}).get(r)] for r in sources],
        'selected_revisions':[[r,s.get('objects',{}).get(s.get('records',{}).get(r,{}).get('object_id'),{}).get('selected_revision')] for r in cfg.get('selected_refs',[])],
        'failures':sorted(failures,key=lambda r:r['request_id']),'messages':sorted(messages,key=lambda r:str(r['message_id'])),
        'round_number':control.get('round_number',1),
        'withdrawals':sorted(w['withdrawal_id'] for w in s.get('withdrawals',{}).values() if w.get('active',True)
            and (not w.get('instance_id') or w.get('instance_id')==iid))})

def resource_state(s,iid):
    from .host_pool import status
    from .scheduler import budget_remaining,project_remaining
    pool=status();instance=s['instances'][iid];mission=s['missions'][instance['current_mission_id']]
    remaining=min(budget_remaining(s,mission['budget_grant_id']),project_remaining(s))
    return {'global_inflight':pool.get('active',len(pool.get('slots',[]))),
        'instance_inflight':sum(r.get('instance_id')==iid and r.get('execution_state') in {'RESERVED','SENT','UNKNOWN'} and s['tasks'][r['task_id']].get('actor_kind')!='MAIN' for r in s['requests'].values()),
        'remaining_calls':None if remaining==float('inf') else remaining}

def wait_ready(s,iid,st,*,pending=()):
    if pending:return True
    wait=st.get('wait_condition') or {};kind=wait.get('kind');refs=wait.get('refs',[])
    changed=st.get('frontier_digest')!=frontier_digest(s,iid,st['mission_id'])
    if kind=='WAIT_FOR_TASKS':return changed
    if kind=='WAIT_FOR_RESOURCE':
        previous=st.get('wait_resource_state',{});current=resource_state(s,iid)
        improved=(current['global_inflight']<previous.get('global_inflight',0) and current['global_inflight']<20 or
                  current['instance_inflight']<previous.get('instance_inflight',0) and current['instance_inflight']<8 or
                  current['remaining_calls'] is not None and current['remaining_calls']>previous.get('remaining_calls',current['remaining_calls']))
        return changed or improved
    return changed if kind=='WAIT_FOR_INPUT' else False

def initialize(store,iid):
    s=store.read_snapshot();instance=s['instances'][iid];mid=instance.get('current_mission_id')
    require(mid in s['missions'],'AUTHORIZATION_REQUIRED','A native authorized mission is required')
    require(instance['kind'] in {'TRH','FDH'},'MAIN_NOT_APPLICABLE','SURVEY has no MAIN session')
    old=current(s,iid)
    if old and old['mission_id']==mid:
        if store.history()[-1][1]['schema'] == 'pmrh.commit/2':
            original = [e for e in s['strategy_events'].values() if e['event_type']=='STRATEGY_INITIALIZED' and e['payload']['instance_id']==iid and e['payload']['mission_id']==mid]
            require(bool(original),'STALE_STRATEGY','Original initialization required')
            store.commit_strategy(max(original,key=lambda e: -1 if e['payload']['previous_revision'] is None else e['payload']['previous_revision']))
        return old
    store.commit_strategy(event('STRATEGY_INITIALIZED',{'instance_id':iid,'mission_id':mid,
                         'target_or_scope_ref':instance.get('target_ref') or instance.get('discovery_brief_ref') or identity(instance.get('survey_scope',{})),
                         'previous_revision':old['revision'] if old else None}))
    return current(store.read_snapshot(),iid)

def apply_event(snapshot,e,blob_get=None):
    require(set(e)=={'event_id','actor','capability_ref','event_type','payload'} and e['actor']=='host'
            and snapshot.get('capabilities',{}).get(e['capability_ref'],{}).get('actor')=='host',
            'AUTHORIZATION_REQUIRED','Host-bound strategy event required')
    old=snapshot.get('strategy_events',{}).get(e['event_id'])
    if old:require(old==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Strategy event conflict');return deepcopy(snapshot)
    s=deepcopy(snapshot);p=e['payload'];kind=e['event_type'];iid=p['instance_id'];mid=p.get('mission_id')
    require(iid in s['instances'],'INSTANCE_UNKNOWN',iid)
    if mid:require(s['missions'].get(mid,{}).get('instance_id')==iid,'AUTHORIZATION_REQUIRED','Mission belongs to another instance')
    sid=strategy_id(iid);st=s.setdefault('strategies',{}).get(sid)
    if kind=='AUDIT_CLOCK_OBSERVED':
        from .research_audit import apply_event as apply_audit
        s=apply_audit(s,e)
    elif kind=='MAIN_EXECUTION_RECOVERY_AUTHORIZED':
        from .main_recovery import apply_authorization
        apply_authorization(s,p,blob_get)
    elif kind=='STRATEGY_INITIALIZED':
        require(s['instances'][iid].get('current_mission_id')==mid and (st['revision'] if st else None)==p['previous_revision'],
                'STALE_STRATEGY','Strategy initialization changed')
        s['strategies'][sid]={'schema':SCHEMA,'strategy_id':sid,'instance_id':iid,'mission_id':mid,
            'revision':(st['revision']+1) if st else 0,'target_or_scope_ref':p['target_or_scope_ref'],
            'route_refs':list(st['route_refs']) if st else [],'frontier_digest':frontier_digest(s,iid,mid),
            'pending_trigger_refs':[],'last_accounted_frontier':None,'active_main_request_id':None,
            'last_accepted_proposal_ref':None,'waiting_reason':None,'wait_condition':None,'next_action':'CONTINUE'}
    elif kind=='STRATEGY_TRIGGERED':
        require(st and st['mission_id']==mid,'STALE_STRATEGY','Initialize this mission strategy first')
        trigger=p['trigger'];tid=trigger['trigger_id']
        require(trigger['frontier_digest']==frontier_digest(s,iid,mid),'STALE_STRATEGY','Relevant work frontier changed')
        s.setdefault('strategy_triggers',{})[tid]=deepcopy(trigger)
        if tid not in st['pending_trigger_refs']:st['pending_trigger_refs'].append(tid)
    elif kind=='STRATEGY_LIVE_PROPOSAL':
        rid=p['request_id'];request=s['requests'].get(rid,{})
        require(request.get('execution_state') in {'SENT','UNKNOWN'},'REQUEST_NOT_ACTIVE','Live dispatch requires the running MAIN request')
        task=deepcopy(s['tasks'][request['task_id']]);key=identity([rid,p['idempotency_key']],'LIVE-DISPATCH-')
        old=s.setdefault('live_main_dispatches',{}).get(key)
        if old:
            require(old['proposal']==p['proposal'],'ALREADY_SETTLED_CONTENT_CONFLICT','Live dispatch idempotency key changed')
            return s
        task['strategy_context']['revision']=st['revision']
        task['strategy_context']['pending_trigger_refs']=list(st['pending_trigger_refs'])
        task['strategy_context']['direction_ids']=[d for d in task['strategy_context'].get('direction_ids',[]) if s.get('human_directions',{}).get(d,{}).get('status') in {'QUEUED','DELIVERED'}]
        blobs={}
        prepared=validate_output_proposal(task,s,p['proposal'],lambda value:value,records={},blobs=blobs,blob_get=blob_get,live=True)
        require(all(blob_get(ref)==data for ref,data in blobs.items()),'ORIGINAL_BYTES_MISMATCH','Live dispatch criterion blobs differ')
        s=apply_validated(s,prepared)
        current(s,iid)['active_main_request_id']=rid
        s['live_main_dispatches'][key]={'dispatch_id':key,'request_id':rid,'proposal':deepcopy(p['proposal']),
            'proposal_id':prepared['proposal_id'],'work_bindings':deepcopy(prepared['work_bindings'])}
    elif kind=='HUMAN_DIRECTION_SUBMITTED':
        d=p['direction'];require(d['instance_id']==iid and d['direction_id']==identity([iid,d['client_action_id']],'DIRECTION-'),
            'DIRECTION_INVALID','Exact user action identity required')
        require(d['text'].strip() and len(d['text'].encode())<=16000,'DIRECTION_INVALID','A bounded research direction is required')
        allowed=set(s.get('records',{}))|set(s.get('sources',{}))|set(s.get('tasks',{}))|set(s.get('research_routes',{}))
        require(set(d['refs'])<=allowed,'DIRECTION_INVALID','Direction references must exist in this project')
        old=s.setdefault('human_directions',{}).get(d['direction_id'])
        if old:
            require(all(old[k]==d[k] for k in ('text','refs','client_action_id','instance_id')),'ALREADY_SETTLED_CONTENT_CONFLICT','Direction action changed')
            return deepcopy(snapshot)
        s['human_directions'][d['direction_id']]=deepcopy(d)
        for relation,status in (('supersedes','SUPERSEDED'),('revokes','REVOKED')):
            for old_id in d.get(relation,[]):
                old=s['human_directions'].get(old_id)
                require(old and old['instance_id']==iid,'DIRECTION_INVALID','Guidance replacement must remain within this MAIN instance')
                old.update(status=status,replaced_by=d['direction_id'])
    else:raise PMRSError('STRATEGY_EVENT_INVALID','Unknown strategy event '+kind)
    s.setdefault('strategy_events',{})[e['event_id']]=deepcopy(e)
    return s

def pending_directions(s,iid):
    return [d for d in s.get('human_directions',{}).values() if d['instance_id']==iid and d['status'] in {'QUEUED','DELIVERED'}]

def task_context(store,snapshot,consumer):
    if consumer.get('actor_kind')!='MAIN':return {}
    st=current(snapshot,consumer['instance_id'])
    require(st and st['mission_id']==consumer['mission_id'],'STRATEGY_MISSING','Initialize main native strategy before freezing')
    directions=[{k:d[k] for k in ('direction_id','text','refs','status')} for d in pending_directions(snapshot,consumer['instance_id'])
                if not d.get('request_id')]
    relevant=frontier(snapshot,consumer['instance_id'],consumer['mission_id'])
    from .scheduler import budget_remaining,project_remaining
    mission=snapshot['missions'][consumer['mission_id']]
    remaining=min(budget_remaining(snapshot,mission['budget_grant_id']),project_remaining(snapshot))
    from .harness_methods import manual
    from .research_audit import context as memory_context
    methods=manual(snapshot['instances'][consumer['instance_id']]['kind'])
    context={'schema':SCHEMA,'strategy_id':st['strategy_id'],'revision':st['revision'],
            'main_inbox':[deepcopy(m) for m in snapshot.get('research_messages',{}).values() if m.get('instance_id')==consumer['instance_id'] and m.get('recipient',{}).get('kind')=='MAIN'],
            'method_manual':methods,'run_control':deepcopy(snapshot['instances'][consumer['instance_id']].get('run_control',{})),
            'research_memory':memory_context(snapshot,consumer['instance_id'],store.read_blob),
            'execution_recoveries':[deepcopy(r) for r in snapshot.get('main_execution_recoveries',{}).values() if r['instance_id']==consumer['instance_id']],
            'stage_handoffs':[{'obligation_id':o['definition']['obligation_id'],
                'accounts':deepcopy(o.get('projection',{}).get('attempt_accounts',[])),
                'evidence_refs':o.get('projection',{}).get('evidence_refs',[])}
                for o in snapshot['obligations'].values() if o.get('projection',{}).get('attempt_accounts')
                and any(c.get('instance_id')==consumer['instance_id'] and c.get('actor_kind')!='MAIN' for c in o['definition']['consumer_bindings'])],
            'open_obligations':[{'obligation_id':o['definition']['obligation_id'],'definition':o['definition'],'projection':o.get('projection',{})} for o in snapshot['obligations'].values() if not any(c.get('actor_kind')=='MAIN' for c in o['definition']['consumer_bindings']) and (not o['definition']['consumer_bindings'] or any(c['instance_id']==consumer['instance_id'] for c in o['definition']['consumer_bindings']))],
            'tasks':[{'task_id':t['task_id'],'request_id':t['request_id'],'stage_id':t['stage_id'],'role':t['role'],'actor_kind':t.get('actor_kind'),'entry_basis':t.get('entry_basis',{}),'state':snapshot['requests'][t['request_id']]} for t in snapshot['tasks'].values() if t['instance_id']==consumer['instance_id']],
            'frontier_digest':frontier_digest(snapshot,consumer['instance_id'],consumer['mission_id']),
            'pending_trigger_refs':list(st['pending_trigger_refs']),'routes':[snapshot['research_routes'][r] for r in st['route_refs']],
            'queued_directions':directions,'direction_ids':[d['direction_id'] for d in directions],
            'work_frontier':relevant,'covered_binding_ids':sorted({b for r in relevant for b in r['bindings']}),
            'last_accounted_frontier':st['last_accounted_frontier'],'main_request_purpose':consumer.get('work_purpose'),
            'remaining_calls':None if remaining==float('inf') else remaining,'budget_grant_id':mission['budget_grant_id'],
            'last_proposal':snapshot.get('strategy_proposals',{}).get(st.get('last_accepted_proposal_ref')),
            'tool_reads_required':'Navigation is not evidence. Read exact Statement/Argument/source before relying on it.'}
    return _checkpoint_input_navigation(snapshot,consumer,context)


def _checkpoint_input_navigation(snapshot,consumer,context):
    """Keep complete current science; reference redundant historical control data.

    The input plan already derives original materials plus checkpoint evidence,
    changed/uncovered requests and their premise closure. This representation
    changes no scientific root, body, read guard or independent qualification.
    """
    from .main_history import reference,owns_obligation
    iid=consumer['instance_id'];memory=context['research_memory']
    ref=lambda collection,key:reference(snapshot,collection,key,iid)
    incremental={r['request_id'] for r in memory['incremental_requests']}
    outstanding={r['request_id'] for r in snapshot['requests'].values() if r.get('instance_id')==iid and r['execution_state'] not in {'SETTLED','CANCELLED_BEFORE_SEND'}}
    current_ids=incremental|outstanding
    all_tasks=context['tasks']
    context['tasks']=[{'task_id':r['task_id'],'request_id':r['request_id'],'stage_id':r['stage_id'],'role':r['role'],'actor_kind':r['actor_kind'],
        'state':{k:r['state'].get(k) for k in ('execution_state','acceptance_state','capture_ref','fenced','admission_error')},
        'decision_ref':snapshot['tasks'][r['task_id']].get('strategy_proposal_ref'),
        'exact_task_history':ref('tasks',r['task_id']),'exact_request_history':ref('requests',r['request_id'])}
        for r in all_tasks if r['request_id'] in current_ids]
    context['task_history']={'count':len(all_tasks),'current_request_ids':sorted(current_ids),
        'selection':'EXACT_CHECKPOINT_UNCOVERED_OR_CHANGED_REQUEST_VERSION_PLUS_UNFINISHED',
        'exact_history':ref('instance_tasks',iid)}
    obligations=context['open_obligations'];context['open_obligations']=[]
    for o in obligations:
        if not owns_obligation(snapshot,snapshot['obligations'][o['obligation_id']],iid):continue
        projection=o['projection'];resolutions=projection.get('consumer_resolutions',{})
        # Retain every obligation's status/identity, not another copy of each
        # criterion, consumer input manifest, attempt body and usage ledger.
        definition=o['definition']
        context['open_obligations'].append({'obligation_id':o['obligation_id'],'type':definition.get('type'),
            'target_refs':definition.get('target_refs',[]),'definition_revision':definition.get('definition_revision'),
            'dependency_bindings':deepcopy(definition.get('dependency_bindings',[])),
            'work_state':projection.get('work_state'),'resolution':projection.get('resolution'),
            'consumer_resolutions':deepcopy(resolutions),'blocker_refs':deepcopy(projection.get('blocker_refs',[])),
            'exact_history':ref('obligations',o['obligation_id'])})
    context['stage_handoffs']=[{**row,'accounts':[a for a in row['accounts'] if a.get('request_id') in current_ids],
        'exact_history':ref('obligations',row['obligation_id'])} for row in context['stage_handoffs']
        if any(a.get('request_id') in current_ids for a in row['accounts'])]
    context['stage_handoff_history']={'selection':'Only exact changed/uncovered or unfinished request handoffs repeat in the current packet.',
        'exact_history':ref('instance_obligations',iid)}
    previous=context.get('last_proposal')
    if previous:
        authored=previous.get('proposal',{})
        context['last_proposal']={k:deepcopy(previous.get(k)) for k in ('proposal_id','request_id','task_id','revision','status','delivery_disposition','frontier_digest')}
        context['last_proposal']['last_control_decision']={k:deepcopy(authored.get(k)) for k in ('next_action','main_followup','wait_condition','no_change_reason')}
        decision=authored.get('p14_decision')
        if decision:context['last_proposal']['last_control_decision']['p14_decision']={k:deepcopy(decision.get(k)) for k in ('action','rationale','completion_evidence')}
        context['last_proposal']['exact_history']=ref('strategy_proposals',previous['proposal_id'])
    clock=memory.get('clock')
    if clock:
        for key in ('intervals','uncertainty_intervals'):clock.pop(key,None)
        clock['exact_interval_history']=ref('research_clocks',iid)
    guidance=memory['effective_guidance']
    guidance['prior_task_delivery_count']=len(guidance.get('task_deliveries',[]))
    guidance['exact_delivery_history']=ref('effective_guidance',iid)
    guidance['task_deliveries']=[x for x in guidance.get('task_deliveries',[]) if x['request_id'] in current_ids]
    # Current route facts stay complete. Repeating every previous revision in
    # every MAIN input grows even after a research checkpoint was published.
    # Preserve the exact immutable revision history behind an owned, versioned
    # paginated reference; this is control history, never a scientific premise.
    context['routes']=deepcopy(context['routes'])
    for route in context['routes']:
        history=route.pop('history',[])
        route['prior_revision_count']=len(history)
        route['exact_revision_history']=ref('research_routes',route['route_id'])
    context['history_access']={'schema':'pmrs.main-history-navigation/1','as_of_commit':snapshot['knowledge_commit'],
        'instruction':'Use knowledge_history(ref=<exact MAIN_HISTORY reference>+"?start=0&length=4096") and follow next_ref to read exact historical metadata pages. This is navigation, not scientific-body or qualification evidence. Use knowledge_get(ref=<KR/SO ref>) for exact scientific bodies and current guards. The complete original objective, original materials, current method handbook, latest published checkpoint body, current guidance and mechanically selected subsequent science remain in this frozen packet.',
        'scientific_materials_omitted_by_this_navigation_projection':False}
    return context

def request_prepared(s,task):
    if task.get('actor_kind')!='MAIN':return
    st=current(s,task['instance_id']);require(st,'STRATEGY_MISSING','Missing native main state')
    active=st.get('active_main_request_id')
    if active:
        from pmrh.application.read_projections import control_lane_closed
        previous=s['requests'][active]
        require(control_lane_closed(previous) if 'admission' in previous else
                previous['execution_state'] in {'SETTLED','CANCELLED_BEFORE_SEND'},'MAIN_BUSY','One active main request per instance')
    require(task.get('strategy_revision',task.get('strategy_context',{}).get('revision'))==st['revision'],'STALE_STRATEGY','Strategy revision changed')
    st['active_main_request_id']=task['request_id']
    for did in task.get('strategy_context',{}).get('direction_ids',[]):
        d=s.get('human_directions',{}).get(did)
        require(d and d['instance_id']==task['instance_id'] and not d.get('request_id'),'DIRECTION_INVALID','Direction already bound')
        d['request_id']=task['request_id']

def request_sent(s,task):
    if task.get('actor_kind')!='MAIN':return
    for did in task.get('strategy_context',{}).get('direction_ids',[]):
        d=s['human_directions'][did];d['status']='DELIVERED';d['delivery_basis']='FROZEN_INPUT_SENT';d['task_id']=task['task_id']

def _schema_obj(properties,required=None):
    return {'type':'object','additionalProperties':False,'properties':properties,'required':list(properties) if required is None else required}

def authoring_schema(task=None):
    text={'type':'string'};refs={'type':'array','items':text}
    route=_schema_obj({'route_key':text,'status':{'enum':sorted(ROUTE_STATES)},'origin':text,'mechanism':text,
        'target_relation':text,'sufficient_chain':text,'unproved_arrows':refs,'extra_assumptions':refs,
        'decisive_probe':text,'failure_evidence_refs':refs,'reactivation_condition':text,'allocation_rationale':text,
        'reason':text,'evidence_refs':refs,'previous_pending_statement':text,'next_pending_statement':text,
        'key_premise_refs':refs,'counterevidence_refs':refs,'decision_outcome':text,'progress_state':{'enum':['SIGNIFICANT','LIMITED_REAL','NO_REAL_PROGRESS','NOT_EVALUATED','INSUFFICIENT_EVIDENCE','IN_PROGRESS']},
        'mechanism_difference':text,'unknown_comparisons':refs,'candidate_refs':refs},
        ['route_key','status','origin','mechanism','target_relation','sufficient_chain','unproved_arrows','extra_assumptions','decisive_probe','failure_evidence_refs','reactivation_condition','allocation_rationale','reason','evidence_refs'])
    work=_schema_obj({'key':text,'stage_id':text,'role':text,'purpose':text,'obligation_type':text,
        'question':text,'success_criterion':text,'target_refs':refs,'input_refs':refs,'source_refs':refs,
        'depends_on':refs,'route_key':text,'communication_group':{'type':['string','null']},
        'argument_ref':{'type':['string','null']},'entry_basis':{'type':'object'},'priority':{'type':'integer'},'selection_reason':text,'allow_independence_loss':{'type':'boolean'}},
        ['key','stage_id','role','purpose','obligation_type','question','success_criterion','target_refs','input_refs','source_refs','depends_on','route_key','communication_group'])
    account=_schema_obj({'summary':text,'record_refs':refs,'remaining_difficulties':refs,'scope_limitations':refs,
        'failed_or_unperformed':refs,'covered_binding_ids':refs,'frontier_complete':{'type':'boolean'}})
    answer=_schema_obj({'direction_id':text,'answer':text,'record_refs':refs,'work_keys':refs,'needs_human':{'type':'boolean'}})
    inp=_schema_obj({'work_key':text,'source_ref':text,'ranges':{'type':'array','items':_schema_obj({'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':1}})},'reason':text})
    from .research_audit import authoring_schema as audit_schema
    return _schema_obj({'schema':{'const':PROPOSAL_SCHEMA},'base_strategy_revision':{'type':'integer','minimum':0},
        'trigger_refs':refs,'route_updates':{'type':'array','maxItems':16,'items':route},
        'work_items':{'type':'array','maxItems':8,'items':work},'input_plan_proposals':{'type':'array','items':inp},
        'progress_account':account,'direction_answers':{'type':'array','items':answer},
        'next_action':{'enum':['CONTINUE','WAIT','DELIVER','P14','COMPLETE']},'human_decision_needed':refs,'no_change_reason':{'type':['string','null']},
        'wait_condition':{'anyOf':[{'type':'null'},_schema_obj({'kind':{'enum':['WAIT_FOR_TASKS','WAIT_FOR_INPUT','WAIT_FOR_RESOURCE','WAIT_FOR_USER']},'refs':refs,'reason':text})]},
        'task_controls':{'type':'array','items':_schema_obj({'binding_id':text,'action':{'enum':['KEEP','PRIORITIZE','PARK','RESUME','CANCEL_UNSENT']},'priority':{'type':'integer'},'reason':text})},
        'main_followup':{'type':'boolean'},
        'research_audit':{'anyOf':[{'type':'null'},audit_schema()]},
        'guidance_summary':{'anyOf':[{'type':'null'},_schema_obj({'guidance_version':text,'direction_ids':refs,'body':text})]},
        'p13_report':{'anyOf':[{'type':'null'},_schema_obj({'report_body':text})]},
        'p14_decision':{'anyOf':[{'type':'null'},_schema_obj({'action':{'enum':['CONTINUE','COMPLETE','WAIT']},'rationale':text,'report_body':text,'completion_evidence':refs})]}},
        ['schema','base_strategy_revision','trigger_refs','route_updates','work_items','input_plan_proposals','progress_account','direction_answers','next_action','human_decision_needed','no_change_reason'])

def prompt_sections(task):
    if task.get('actor_kind')!='MAIN':return {}
    return {'MAIN_RESEARCH_RESPONSIBILITY':
        'You are the product MAIN. The complete method manual and current problem state are in packet.json strategy_context. '
        'Decide every stage from the first research action. You may directly research, freely use native internal delegation, '
        'dispatch stage CLI tasks through the actual main_stage_dispatch tool, revise communication and read/reply to tasks. '
        'Never fabricate a MAIN decision after host-selected work. No minimum phase/route/worker count. '
        'Use registered stage/role/purpose work items (at most eight per command); the role matrix controls stage workers only. '
        'Every work item names exact scientific inputs, completion dependencies and a substantive selection reason. '
        'progress_account.covered_binding_ids may name the supplied settled stage frontier and this MAIN task\'s own frozen bindings; '
        'claiming a complete frontier requires accounting for every supplied stage binding, including failed and unfinished work. '
        'P/D duties are capabilities; there is no required numbered progression or all-task barrier. '
        'The final strategy_proposal uses the latest strategy revision returned by live dispatch, and must not repeat already applied tasks. '
        'After live dispatch, your trigger_refs are the current pending_trigger_refs returned by the tool, not the old frozen array. Only pending_direction_ids still need final direction_answers; do not repeat already applied answers. '
        'If doing more MAIN research without a new external event is scientifically needed, set main_followup=true explicitly. '
        'Use WAIT with a concrete wait_condition; no paid periodic polling. Use P14 with a full progress account and p14_decision '
        'to save the P13 report and continue the original TRH goal in the existing allowance. Persisted user stop has priority. '
        'When making a P13 account while continuing within the same round, include p13_report={report_body: your full readable account}; '
        'it is saved atomically with your captured response without opening a new round or starting a separate writing task. '
        'FDH DELIVER preserves the human candidate-adoption decision. COMPLETE requires qualified exact original-goal evidence. '
        'New mathematical deductions require native scientific records; strategy prose and messages are not proof. '
        'History references MAIN_HISTORY/<commit>/<collection>/<native_id> are exact native metadata navigation: read with knowledge_history(ref=reference+"?start=0&length=4096"), then follow next_ref. They do not qualify scientific reads; use knowledge_get for the original scientific record/source. '
        'Read research_memory in your actual packet: current effective human guidance, latest published research checkpoint, later changes and live tasks. '
        'On a same-turn event navigation, use main_runtime_context to actually read new guidance/audit/control/frontier; only that confirmed response extends your observed basis and direction-answer set. Read exact scientific bodies separately. '
        'Pending FULL_STRATEGIC_AUDIT_DUE is substantive MAIN work; complete a research_audit with its full authored body and every known route/candidate assessment, or preserve a concrete deferral reason in your account. '
        'A 30-minute host status check is not a paid research review. Four-hour audit time is accumulated instance research wall time; no automatic route change is required. '
        'Do not launch other PMRS processes or modify native state through the shell. Native Codex internal delegation is unrestricted. '
        'Answer every queued direction. Work not performed and independence contamination remain visible. All MAIN calls are Astra Ultra.'}

def _bounded_text(value,label,minimum=1):
    require(isinstance(value,str) and minimum<=len(value.strip()) and len(value.encode())<=24000,'STRATEGY_INVALID',label+' requires concrete bounded text')
    return value

def validate_output_proposal(task,snapshot,proposal,resolve,*,records,blobs,blob_get=None,science=None,live=False):
    """Pure validation/preparation; no writes, processes or grants are created."""
    from . import execution,obligations as O,assurance
    from .workflows.registry import validate_assignment,INDEPENDENT
    require(task.get('actor_kind')=='MAIN','AUTHORIZATION_REQUIRED','Workers cannot author main strategy')
    require(isinstance(proposal,dict) and proposal.get('schema')==PROPOSAL_SCHEMA,'STRATEGY_INVALID','A versioned strategy proposal is required')
    p=resolve(deepcopy(proposal));context=deepcopy(task.get('strategy_context',{}));st=current(snapshot,task['instance_id'])
    from .research_audit import verified_runtime_contexts
    runtime_contexts=verified_runtime_contexts(snapshot,task,blob_get,live=live)
    if runtime_contexts:
        received=runtime_contexts[-1]
        context['frontier_digest']=received['frontier_digest']
        context['covered_binding_ids']=received.get('covered_binding_ids',[])
    live_receipts=[v for v in snapshot.get('live_main_dispatches',{}).values() if v['request_id']==task['request_id']]
    expected_revision=st['revision'] if live_receipts or live else context.get('revision')
    require(st and st['mission_id']==task['mission_id'] and p['base_strategy_revision']==expected_revision==st['revision'],
            'STALE_STRATEGY','Proposal must preserve its exact main request strategy version')
    require(set(p['trigger_refs'])==set(st['pending_trigger_refs'] if live_receipts or live else context.get('pending_trigger_refs',[])),'STRATEGY_INVALID','Proposal triggers differ from frozen task')
    require(p['next_action'] in {'CONTINUE','WAIT','DELIVER','P14','COMPLETE'},'STRATEGY_INVALID','Explicit next action required')
    s=deepcopy(snapshot)
    for name in ('records','objects','production_events','supports','qualifications','inferences','candidates'):
        s.setdefault(name,{}).update(deepcopy((science or {}).get(name,records if name=='records' else {})))
    s.setdefault('obligations',{}).update(deepcopy((science or {}).get('new_obligations',{})))
    known=set(s['records']);supplied={r['ref'] for r in task.get('input_manifest',[]) if r['kind']=='record'}|set(records)
    if task.get('communication_contract'):
        from .input_delivery import supplied_records
        supplied.update(supplied_records(snapshot,task,blob_get,live=live))
    pid=identity([task['request_id'],p],'PROPOSAL-');iid=task['instance_id'];mid=task['mission_id'];mission=s['missions'][mid]
    require(mission['status']=='ACTIVE' and s['instances'][iid]['status']=='ACTIVE','TASK_FENCED','Paused research cannot apply a new plan')
    require(mission['authorized_scope'].get('allow_derived_work'),'AUTHORIZATION_REQUIRED','Derived work is outside the mission')
    def checked_refs(refs):
        require(isinstance(refs,list) and set(refs)<=supplied,'INCOMPLETE_CONTEXT','Strategy mathematical references must be actual supplied or newly authored records')
        return sorted(set(refs))
    supplied_sources={r['ref'] for r in task.get('input_manifest',[]) if r['kind']=='source'}
    if task.get('communication_contract'):
        from .input_delivery import supplied_sources as dynamic_sources
        supplied_sources.update(dynamic_sources(snapshot,task,blob_get,live=live))
    def checked_evidence(refs):
        require(isinstance(refs,list) and set(refs)<=supplied|supplied_sources,'INCOMPLETE_CONTEXT','Route evidence must be an actually supplied record or exact original source')
        return sorted(set(refs))
    account=p['progress_account'];_bounded_text(account['summary'],'Progress account')
    checked_refs(account['record_refs'])
    require(account['record_refs'] or not records,'STAGE_PRODUCT_MISSING','New scientific work must be cited in the progress account')
    frontier_bindings=set(context.get('covered_binding_ids',[]))
    # MAIN may research and author native records during this very request. Its
    # own frozen responsibility is observable work even before settlement; it is
    # deliberately absent from the historical stage-task frontier above. This
    # account does not satisfy that responsibility or certify its mathematics:
    # native effects, evidence and assurance are validated independently.
    own_bindings={b['binding_id'] for b in task.get('obligation_bindings',[])}
    # A live dispatch can return new duties after the last runtime frontier.
    # Its sealed, confirmed receipt allows an honest unfinished-work account;
    # it does not refresh the frontier digest or certify any stage result.
    from .input_delivery import observed_main_dispatch_bindings
    dispatched_bindings=observed_main_dispatch_bindings(snapshot,task,blob_get,live=live)
    require(set(account['covered_binding_ids'])<=frontier_bindings|own_bindings|dispatched_bindings,'STRATEGY_INVALID','Account claims unobserved work')
    report=p.get('p13_report')
    if report is not None:
        require(isinstance(report,dict) and set(report)=={'report_body'} and snapshot['instances'][iid]['kind']=='TRH',
            'STRATEGY_INVALID','P13 report must be a TRH MAIN readable round account')
        _bounded_text(report['report_body'],'P13 report body')
    if p['next_action'] in {'DELIVER','P14','COMPLETE'} or report is not None:
        require(not live,'STRATEGY_INVALID','Global delivery is finalized with the captured scientific response')
        # A continuing P14 or ordinary progress report is not an all-worker
        # barrier. Preserve its older observed frontier and explicit gaps; new
        # results remain increments for the same MAIN. A claimed full account,
        # final delivery or scientific completion still requires fresh coverage.
        full_account=(p['next_action'] in {'DELIVER','COMPLETE'} or
                      (p.get('p14_decision') or {}).get('action')=='COMPLETE' or account['frontier_complete'] is True)
        if full_account:
            require(context.get('frontier_digest')==frontier_digest(snapshot,task['instance_id'],task['mission_id']),
                'GLOBAL_ACCOUNT_INCOMPLETE','Relevant scientific work changed during the global account; incorporate it in a new MAIN decision')
            require(account['frontier_complete'] is True and frontier_bindings<=set(account['covered_binding_ids']),
                'GLOBAL_ACCOUNT_INCOMPLETE','Delivery must account for the full supplied scientific frontier')
        else:
            require(account['failed_or_unperformed'] or account['scope_limitations'],
                'GLOBAL_ACCOUNT_INCOMPLETE','An incomplete progress account must preserve unread or unperformed work explicitly')
        require(snapshot['instances'][task['instance_id']]['kind']=='TRH' or p['next_action']=='DELIVER',
            'STRATEGY_INVALID','FDH delivers its candidate account for human decisions')
    if p['next_action']=='WAIT':
        wait=p.get('wait_condition') or {}
        require(wait.get('kind') in {'WAIT_FOR_TASKS','WAIT_FOR_INPUT','WAIT_FOR_RESOURCE','WAIT_FOR_USER'} and wait.get('reason'),
            'WAIT_CONDITION_REQUIRED','WAIT needs a concrete kind, references and reason')
        if wait['kind']=='WAIT_FOR_TASKS':
            require(wait.get('refs') and all(r in snapshot['tasks'] or r in snapshot['requests'] for r in wait['refs']),
                'WAIT_CONDITION_REQUIRED','Task wait references actual tasks or requests')
    routes=[];keys=set();route_keys={s['research_routes'][r]['route_key']:r for r in st['route_refs']}
    for r in p['route_updates']:
        _bounded_text(r['route_key'],'Route key');require(r['route_key'] not in keys and r['status'] in ROUTE_STATES,'STRATEGY_INVALID','Unique route and legal status required');keys.add(r['route_key'])
        for name in ('mechanism','reason','allocation_rationale'):_bounded_text(r[name],name)
        checked_evidence(r['evidence_refs']);checked_evidence(r['failure_evidence_refs'])
        for field in ('key_premise_refs','counterevidence_refs','candidate_refs'):
            if field in r:checked_evidence(r[field])
        rid=route_keys.get(r['route_key']) or identity([iid,r['route_key']],'ROUTE-');old=s.get('research_routes',{}).get(rid)
        row={**r,'schema':'pmrs.research-route/1','route_id':rid,'instance_id':iid,'mission_id':mid,
             'revision':old['revision']+1 if old else 1,'proposal_ref':pid,
             'mechanism_fingerprint':identity([r['mechanism'],r['extra_assumptions']]),
             'history':([*old.get('history',[]),{k:v for k,v in old.items() if k!='history'}] if old else [])}
        routes.append(row);route_keys[r['route_key']]=rid
    items=p['work_items'];require(isinstance(items,list) and len(items)<=8,'STRATEGY_INVALID','One MAIN dispatch may create at most eight stage CLI tasks')
    require(p['next_action'] not in {'DELIVER','COMPLETE','WAIT'} or not items,'STRATEGY_INVALID','Work and delivery/wait decision conflict')
    if not items and not routes:require(p.get('no_change_reason') or p['next_action'] in {'P14','COMPLETE','DELIVER','WAIT'},'STRATEGY_INVALID','No-change needs a reason')
    prepared=[];by_key={};events=[]
    for item in items:
        key=item['key'];require(key not in by_key,'STRATEGY_INVALID','Duplicate work key')
        stage=item['stage_id'];role=item['role'];kind=item['obligation_type'];basis=deepcopy(item.get('entry_basis',{}))
        require(stage not in MAIN_STAGES and not role.startswith('REPORT_') and role not in {'HOST','HUMAN'},'AUTHORIZATION_REQUIRED','Main proposes research work; main turns and explicit reports use native triggers')
        from .model_policy import resolve as resolve_model
        resolve_model(s['instances'][iid]['kind'],stage,role,item['purpose'],require_capability=False)
        if stage=='P7':basis.setdefault('analysis_route','SOURCE_APPLICATION' if role=='LEARN' else 'DIRECT_ANALYSIS')
        targets=checked_refs(item['target_refs']);inputs=checked_refs(item['input_refs'])
        require(targets or s['instances'][iid]['kind'] in {'SURVEY','FDH'},'STRATEGY_INVALID','Exact work target required')
        _bounded_text(item['question'],'Scientific question');_bounded_text(item['success_criterion'],'Success criterion')
        require(not item['route_key'] or item['route_key'] in route_keys,'STRATEGY_INVALID','Unknown route key')
        sources=item['source_refs'];allowed_sources=set(mission['authorized_scope'].get('source_refs',[]))|{r['ref'] for r in task['input_manifest'] if r['kind']=='source'}
        require(set(sources)<=allowed_sources,'AUTHORIZATION_REQUIRED','Plan cannot add unauthorized source scope')
        group=item.get('communication_group')
        require(not group or role not in INDEPENDENT and not (stage=='P7' and role in {'LEARN','DIRECT'}) or item.get('allow_independence_loss') is True, 'INDEPENDENCE_EXPOSURE_REQUIRED','MAIN must explicitly acknowledge loss of independent evidence eligibility when opening scientific cooperation')
        criterion=('Concrete scientific responsibility ['+stage+'/'+role+']: '+item['question']+'\nSuccess and honest stopping criterion: '+item['success_criterion']).encode()
        cref=sha(criterion);blobs[cref]=criterion
        oid=identity({'instance':iid,'criterion':cref,'targets':targets},'OB-');bid=identity({'mission':mid,'obligation':oid,'role':role},'BINDING-')
        require(not any(c['binding_id']==bid for c in s.get('obligations',{}).get(oid,{}).get('definition',{}).get('consumer_bindings',[])),
                'STRATEGY_DUPLICATE_DUTY','Use the existing exact responsibility; relabelling does not buy another sample')
        c={'binding_id':bid,'instance_id':iid,'mission_id':mid,'stage_id':stage,'role':role,'retry_grant_id':'RETRY-'+bid,
           'method_ref':'MAIN_ACCEPTED_PLAN','scope':{'target_refs':targets},'entry_basis':basis,'input_refs':inputs,
           'source_refs':sources,'threshold':'WORK_DISPOSITION_RECORDED','success_criterion':cref,
           'strategy_ref':st['strategy_id'],'strategy_revision':st['revision']+1,'strategy_proposal_ref':pid,
           'route_ref':route_keys.get(item['route_key']),'ready_since':s.get('_snapshot_sequence',0),
           'work_purpose':item['purpose'],'priority':item.get('priority',0),
           'round_number':s['instances'][iid].get('run_control',{}).get('round_number',1)}
        c['entry_basis']['strategy']={'proposal_ref':pid,'work_key':key,'route_ref':c['route_ref'],
            'main_request_id':task['request_id'],'main_input_ref':task.get('input_packet_ref'),
            'selection_reason':item.get('selection_reason') or item['question'],'goal_gap':account['remaining_difficulties']}
        if group:
            c['communication_group']=identity([iid,mid,pid,group],'COLLAB-');c['communication_mode']='COOPERATIVE'
            c['allow_independence_loss']=item.get('allow_independence_loss',False)
        if role in INDEPENDENT and stage=='D4':
            scope=[{'target_ref':r,'locators':[],'aspects':['formulation_precision','counterevidence','inter_candidate_comparisons','hypothesis_cost','explanation_boundary']} for r in targets]
            req=assurance.requirement('FORMULATION',scope)
            if blob_get:req=assurance.normalize_requirement(req,s,blob_get)
            c.update(required_assurance=req,policy_digest=identity(req))
        elif role in INDEPENDENT:
            arg=item.get('argument_ref') or next((r for r in inputs if s['records'][r]['kind']=='Argument'),None)
            require(arg in inputs and s['records'][arg]['kind']=='Argument','INCOMPLETE_CONTEXT','Independent check requires an exact argument input')
            stmt=s['records'][arg]['data']['conclusion_ref'];require(stmt in targets,'AUTHORIZATION_REQUIRED','Review must bind its exact conclusion')
            scope=[{'target_ref':r,'locators':[],'aspects':['original_target' if r==stmt and stage=='P9' else 'full_argument' if stage=='P9' else 'complete_statement' if r==stmt else 'complete_argument']} for r in (stmt,arg)]
            purpose='REFUTATION_SUPPORT' if s['records'][arg]['data']['mode']=='REFUTATION' else 'PROOF_SUPPORT'
            req=assurance.requirement(purpose,scope,review_mode='TARGET_DUAL' if stage=='P9' else 'SCOPED_SINGLE',
                assumption_policy=assurance.declared_assumption_policy(s,stmt,arg))
            if role=='INDEPENDENT':req=assurance.requirement('INTEGRATION',scope)
            require(role!='SPECIALIST','AUTHORIZATION_REQUIRED','Specialist escalation requires a separately authorized exact optional scope')
            if blob_get:req=assurance.normalize_requirement(req,s,blob_get)
            support=next((v for v in s['supports'].values() if v['argument_ref']==arg),None)
            require(support,'INCOMPLETE_CONTEXT','Review argument has no native support identity')
            c.update(required_assurance=req,selected_support=support['support_id'],policy_digest=identity(req),
                author_execution_event=support.get('author_execution_event'))
            c['entry_basis']['consumer_requirement']=req
            if stage in {'P4','P7','P8'}:c['entry_basis']['dependency_threshold']='SUPPORT_QUALIFIED'
        validate_assignment(stage,kind,role,c['entry_basis'])
        by_key[key]={'oid':oid,'bid':bid};prepared.append((item,c,oid,cref,targets,kind))
    existing_dependencies={c['binding_id']:{'oid':o['definition']['obligation_id'],'bid':c['binding_id']} for o in snapshot['obligations'].values() for c in o['definition']['consumer_bindings'] if c['instance_id']==iid and c['mission_id']==mid}
    dependency_keys={**existing_dependencies,**by_key}
    for item,c,oid,cref,targets,kind in prepared:
        require(set(item['depends_on'])<=set(dependency_keys) and item['key'] not in item['depends_on'],'STRATEGY_INVALID','Dependencies must name other proposed work')
        deps=[{'dependency_id':identity([oid,dependency_keys[k]['oid']],'DEP-'),'binding_ref':dependency_keys[k]['oid'],'binding_id':dependency_keys[k]['bid'],'threshold':'WORK_DISPOSITION_RECORDED'} for k in item['depends_on']]
        c['entry_basis']['research_plan']={'plan_id':pid,'branch_key':item['key'],'common_input_refs':[],
             'common_source_refs':[],'selected_branches':[{'key':i['key'],'obligation_id':o,'binding_id':b['binding_id'],'stage_id':b['stage_id'],'role':b['role'],'required':True} for i,b,o,_,_,_ in prepared],
             'plan_intent':account['summary']}
        ob=O.make(oid,kind,targets,cref,consumer_bindings=[c],dependencies=deps,created_by=pid,effect='BOUNDED_MAIN_PLAN')
        selections={}
        for plan in p['input_plan_proposals']:
            require(plan['work_key'] in by_key,'INPUT_PLAN_INVALID','Material plan refers to unknown work')
            if plan['work_key']!=item['key']:continue
            source_ref=plan['source_ref'];require(source_ref in c['source_refs'],'INPUT_PLAN_INVALID','Excerpt must be a selected scientific source')
            require(blob_get is not None,'INPUT_PLAN_INVALID','Exact source bytes are required for excerpts')
            from .knowledge import locator
            raw=blob_get(s['sources'][source_ref]['blob_hash'])
            selections[source_ref]={'coverage':'DECLARED_RANGE','reason':_bounded_text(plan['reason'],'Excerpt scientific justification'),
                'locators':[locator(raw,r['start'],r['end'],'UTF8_BYTE') for r in plan['ranges']]}
        if selections:c['source_selections']=selections
        if oid in s['obligations']:
            prior=deepcopy(s['obligations'][oid]);prior['definition']['consumer_bindings'].append(c);prior['definition']['definition_revision']+=1;ob=prior
        from .input_plans import enrich_consumer
        c=enrich_consumer(s,ob,c,blob_get=blob_get)
        ob['definition']['consumer_bindings']=[c if row['binding_id']==c['binding_id'] else row for row in ob['definition']['consumer_bindings']]
        grant={'grant_id':c['retry_grant_id'],'obligation_id':oid,'method_ref':c['method_ref'],
               'max_research_attempts':mission['authorized_scope'].get('max_research_attempts',1),
               'max_responsibility_attempts':mission['authorized_scope'].get('max_research_attempts',1)}
        events.append(execution.event('ASSIGN_OBLIGATION',{'instance_id':iid,'mission_id':mid,'obligation':ob,
            'retry_grant':grant,'authorization_basis_ref':pid}))
    # Ensure DAG before mutation; roles and stage contracts have already been checked.
    active=set();done=set()
    def visit(k):
        require(k not in active,'STRATEGY_INVALID','Cyclic work dependencies')
        if k in done:return
        active.add(k)
        for other in next(i['depends_on'] for i in items if i['key']==k):
            if other in by_key:visit(other)
        active.remove(k);done.add(k)
    for k in by_key:visit(k)
    # Assignment admission validates the real MAIN proposal provenance even in this pure preparation snapshot.
    s.setdefault('strategy_proposals',{})[pid]={'proposal_id':pid,'instance_id':iid,'mission_id':mid,'request_id':task['request_id'],'status':'VALIDATED'}
    for ev in events:s=execution.apply_event(s,ev)
    controls=p.get('task_controls',[])
    for control in controls:
        require(any(c['binding_id']==control['binding_id'] and c['instance_id']==iid and c['mission_id']==mid for o in snapshot['obligations'].values() for c in o['definition']['consumer_bindings']), 'STRATEGY_INVALID','Task control must belong to this MAIN instance and mission')
        require(control['action'] in {'KEEP','PRIORITIZE','PARK','RESUME','CANCEL_UNSENT'},'STRATEGY_INVALID','Unknown task disposition')
        _bounded_text(control['reason'],'Task disposition reason')
    answers=p['direction_answers'];delivered=set(context.get('direction_ids',[]))
    for received in runtime_contexts:
        delivered.update(d['direction_id'] for d in received.get('effective_guidance',{}).get('original_directions',[])
            if d.get('status') in {'QUEUED','DELIVERED'} and d.get('request_id') in {None,task['request_id']})
    expected={d for d in delivered if snapshot.get('human_directions',{}).get(d,{}).get('status') in {'QUEUED','DELIVERED'}}
    replaced={d for d in delivered if snapshot.get('human_directions',{}).get(d,{}).get('status') in {'REVOKED','SUPERSEDED'}}
    if live:
        require({a['direction_id'] for a in answers}<=expected,'DIRECTION_INVALID','Live response may answer only still-pending frozen directions')
        expected={a['direction_id'] for a in answers}
    actual_answers={a['direction_id'] for a in answers}
    require(expected<=actual_answers<=expected|replaced and len(answers)==len(actual_answers),'DIRECTION_UNANSWERED','Every actually delivered current direction needs an exact answer; unseen directions cannot be answered')
    for answer in answers:
        _bounded_text(answer['answer'],'Direction answer');checked_refs(answer['record_refs'])
        require(set(answer['work_keys'])<=set(by_key),'DIRECTION_INVALID','Applied direction must name actual proposed work')
    from .research_audit import prepare as prepare_audit,effective_guidance
    audit=prepare_audit(s,task,p.get('research_audit'),supplied=supplied,known_sources=supplied_sources,
        blobs=blobs,live=live,route_keys=set(route_keys),runtime_contexts=runtime_contexts)
    guidance=p.get('guidance_summary')
    if guidance is not None:
        _bounded_text(guidance['body'],'Effective guidance summary')
        actual=effective_guidance(snapshot,iid)
        observed_guidance={task.get('research_memory_context',{}).get('guidance_version')}|{r.get('effective_guidance',{}).get('version') for r in runtime_contexts}
        require(guidance['guidance_version']==actual['version'] and set(guidance['direction_ids'])=={d['direction_id'] for d in actual['original_directions']},
            'STALE_GUIDANCE','Guidance summary must cover the exact current original directions')
        require(guidance['guidance_version'] in observed_guidance,'INCOMPLETE_CONTEXT','Guidance summary must come from frozen or actually delivered original wording')
        require(not live,'GUIDANCE_CAPTURE_REQUIRED','Publish guidance summary with the actual captured MAIN output')
    return {'schema':PROPOSAL_SCHEMA,'proposal_id':pid,'request_id':task['request_id'],'task_id':task['task_id'],
        'instance_id':iid,'mission_id':mid,'base_revision':st['revision'],'frontier_digest':context['frontier_digest'],
        'frontier_was_current':context['frontier_digest']==frontier_digest(snapshot,iid,mid),
        'routes':routes,'assignment_events':events,'work_bindings':by_key,'proposal':p,'stage_id':task['stage_id'],'live':live,
        'main_input_ref':task.get('input_packet_ref'),'main_prompt_ref':task.get('prompt_ref'),'research_audit':audit,
        'runtime_context_deliveries':[{'delivery_id':r['delivery_id'],'response_ref':r['response_ref'],'as_of_commit':r['as_of_commit']} for r in runtime_contexts],
        'runtime_direction_deliveries':{d['direction_id']:{'delivery_id':r['delivery_id'],'response_ref':r['response_ref']}
            for r in runtime_contexts for d in r.get('effective_guidance',{}).get('original_directions',[])}}

def apply_validated(s,prepared):
    from . import execution,workflow_instances as W
    st=current(s,prepared['instance_id']);pid=prepared['proposal_id']
    if pid in s.get('strategy_proposals',{}):return s
    require(st['revision']==prepared['base_revision'],'STALE_STRATEGY','Plan compare-and-swap failed')
    for row in prepared['routes']:
        s.setdefault('research_routes',{})[row['route_id']]=deepcopy(row)
        if row['route_id'] not in st['route_refs']:st['route_refs'].append(row['route_id'])
        for o in s['obligations'].values():
            for c in o['definition']['consumer_bindings']:
                if c.get('route_ref')!=row['route_id']:continue
                status='ACTIVE' if row['status']=='ACTIVE' else 'PARKED' if row['status']=='PARKED' else 'CANCELLED' if row['status'] in {'SUPERSEDED','EXHAUSTED','REFUTED_ON_SCOPE'} else None
                if status:s.setdefault('consumer_controls',{})[c['binding_id']]={'status':status,'proposal_ref':pid,'reason':row['reason'],'priority':c.get('priority',0)}
    p=prepared['proposal'];st['revision']+=1
    st.update(frontier_digest=prepared['frontier_digest'],last_accepted_proposal_ref=pid,
        active_main_request_id=prepared['request_id'] if prepared.get('live') else None,
        pending_trigger_refs=[r for r in st['pending_trigger_refs'] if r not in p['trigger_refs']],
        next_action=p['next_action'],waiting_reason=(p.get('wait_condition') or {}).get('reason') if p['next_action']=='WAIT' else None,
        wait_condition=deepcopy(p.get('wait_condition')))
    if p['next_action']=='WAIT' and (p.get('wait_condition') or {}).get('kind')=='WAIT_FOR_RESOURCE':
        st['wait_resource_state']=resource_state(s,prepared['instance_id'])
    if p['progress_account']['frontier_complete']:st['last_accounted_frontier']=prepared['frontier_digest']
    row={k:deepcopy(v) for k,v in prepared.items() if k!='assignment_events'}
    row.update(status='APPLIED',revision=st['revision']);s.setdefault('strategy_proposals',{})[pid]=row
    for control in p.get('task_controls',[]):
        previous=s.setdefault('consumer_controls',{}).get(control['binding_id'],{})
        state={'PARK':'PARKED','RESUME':'ACTIVE','CANCEL_UNSENT':'CANCELLED'}.get(control['action'],previous.get('status','ACTIVE'))
        s['consumer_controls'][control['binding_id']]={**previous,'status':state,'priority':control['priority'],'proposal_ref':pid,'reason':control['reason']}
    allow=True
    if p['next_action'] in {'P14','COMPLETE','DELIVER'}:
        task=s['tasks'][prepared['task_id']];request=s['requests'][prepared['request_id']]
        decision=W.apply_p14_decision(s,task,request,p,pid)
        allow=decision.get('allow_dispatch',False)
        row['delivery_disposition']=decision
    elif p.get('p13_report') is not None:
        task=s['tasks'][prepared['task_id']];request=s['requests'][prepared['request_id']]
        delivery=W.preserve_main_report(s,task,request,p,pid,report_body=p['p13_report']['report_body'])
        row['delivery_disposition']={'delivery_id':delivery['delivery_id'],'state':'OPEN','allow_dispatch':True,
            'p14_reached':False}
    if allow:
        for ev in prepared['assignment_events']:
            actual=deepcopy(ev)
            if p['next_action']=='P14':
                for c in actual['payload']['obligation']['definition']['consumer_bindings']:
                    c['round_number']=s['instances'][prepared['instance_id']].get('run_control',{}).get('round_number',1)
                actual=execution.event('ASSIGN_OBLIGATION',actual['payload'])
            s=execution.apply_event(s,actual)
    else:row['withheld_work_bindings']=deepcopy(prepared['work_bindings'])
    for answer in p['direction_answers']:
        d=s['human_directions'][answer['direction_id']]
        status='WAITING_HUMAN' if answer['needs_human'] else 'APPLIED' if answer['work_keys'] and allow else 'ANSWERED'
        if d.get('status') in {'REVOKED','SUPERSEDED'}:status=d['status']
        d.update(status=status,reply_ref=pid,answer=answer['answer'],record_refs=answer['record_refs'],work_keys=answer['work_keys'])
        observed=prepared.get('runtime_direction_deliveries',{}).get(answer['direction_id'])
        if observed:
            d.setdefault('dynamic_read_receipts',[]).append({**observed,'request_id':prepared['request_id'],
                'basis':'CONFIRMED_RUNTIME_CONTEXT','reply_ref':pid})
    task=s['tasks'][prepared['task_id']]
    from .research_audit import apply_validated as apply_audit
    apply_audit(s,task,prepared.get('research_audit'),pid)
    if p.get('guidance_summary'):
        guidance=p['guidance_summary'];gid=identity([pid,guidance],'GUIDANCE-SUMMARY-')
        s.setdefault('research_guidance',{})[gid]={'guidance_id':gid,'instance_id':prepared['instance_id'],
            **deepcopy(guidance),'author_request_id':prepared['request_id'],'author_capture_ref':s['requests'][prepared['request_id']].get('capture_ref'),
            'published_at':now(),'status':'PUBLISHED'}
    if prepared.get('frontier_was_current'):
        # Own newly admitted gaps/records were already part of this decision.
        # Absorb only these self-effects. A genuinely newer external frontier
        # observed at validation remains pending and wakes the same MAIN later.
        acknowledged=frontier_digest(s,prepared['instance_id'],prepared['mission_id'])
        stored=s['strategy_proposals'][pid]
        stored['input_frontier_digest']=prepared['frontier_digest']
        stored['frontier_digest']=acknowledged
        current(s,prepared['instance_id'])['frontier_digest']=acknowledged
    return s

def dispatch_from_main(store,request_id,proposal,idempotency_key):
    """Real request-scoped MAIN tool call; raw decision and inputs stay native."""
    require(isinstance(idempotency_key,str) and idempotency_key,'IDEMPOTENCY_REQUIRED','Live dispatch needs an idempotency key')
    s=store.read_snapshot();request=s.get('requests',{}).get(request_id,{})
    task=deepcopy(s.get('tasks',{}).get(request.get('task_id'),{}))
    require(task.get('actor_kind')=='MAIN','AUTHORIZATION_REQUIRED','Only a product MAIN can dispatch stage tasks')
    key=identity([request_id,idempotency_key],'LIVE-DISPATCH-');old=s.get('live_main_dispatches',{}).get(key)
    if old and store.history()[-1][1]['schema'] != 'pmrh.commit/2':
        require(old['proposal']==proposal,'ALREADY_SETTLED_CONTENT_CONFLICT','Idempotency content differs')
        return {**old,'strategy_revision':current(s,task['instance_id'])['revision'],'pending_trigger_refs':current(s,task['instance_id'])['pending_trigger_refs'],'pending_direction_ids':[d for d in task.get('strategy_context',{}).get('direction_ids',[]) if s.get('human_directions',{}).get(d,{}).get('status') in {'QUEUED','DELIVERED'}]}
    if old:
        # The /2 duplicate still enters commit_strategy's current gate. Its
        # original already-applied proposal is not a new plan at today's CAS.
        require(old['proposal']==proposal,'ALREADY_SETTLED_CONTENT_CONFLICT','Idempotency content differs')
    else:
        st=current(s,task['instance_id']);task['strategy_context']['revision']=st['revision'];task['strategy_context']['pending_trigger_refs']=st['pending_trigger_refs'];task['strategy_context']['direction_ids']=[d for d in task['strategy_context'].get('direction_ids',[]) if s.get('human_directions',{}).get(d,{}).get('status') in {'QUEUED','DELIVERED'}]
        blobs={};validate_output_proposal(task,s,proposal,lambda value:value,records={},blobs=blobs,blob_get=store.read_blob,live=True)
        for ref,body in blobs.items():require(store.blob(body)==ref,'BLOB_CHANGED','Live decision body changed')
    result=store.commit_strategy(event('STRATEGY_LIVE_PROPOSAL',{'instance_id':task['instance_id'],'mission_id':task['mission_id'],
        'request_id':request_id,'idempotency_key':idempotency_key,'proposal':proposal}))
    now=store.read_snapshot();receipt=now['live_main_dispatches'][key]
    return {**result,**receipt,'strategy_revision':current(now,task['instance_id'])['revision'],
        'pending_trigger_refs':current(now,task['instance_id'])['pending_trigger_refs'],
        'pending_direction_ids':[d for d in task.get('strategy_context',{}).get('direction_ids',[]) if now.get('human_directions',{}).get(d,{}).get('status') in {'QUEUED','DELIVERED'}],'model_calls':0}

def trigger(store,iid,reason,stage):
    if store.history()[-1][1]['schema'] == 'pmrh.commit/2':
        st=current(store.read_snapshot(),iid)
        require(st is not None,'STALE_STRATEGY','Initialize explicitly before the trigger command')
    else:st=initialize(store,iid)
    s=store.read_snapshot();digest=frontier_digest(s,iid,st['mission_id'])
    directions=sorted(d['direction_id'] for d in pending_directions(s,iid) if not d.get('request_id'))
    tid=identity([iid,st['mission_id'],reason,stage,digest,directions],'TRIGGER-')
    if tid in s.get('strategy_triggers',{}) and store.history()[-1][1]['schema'] != 'pmrh.commit/2':return tid
    store.commit_strategy(event('STRATEGY_TRIGGERED',{'instance_id':iid,'mission_id':st['mission_id'],
        'trigger':{'schema':'pmrs.strategy-trigger/1','trigger_id':tid,'instance_id':iid,'mission_id':st['mission_id'],
                   'reason':reason,'stage_id':stage,'frontier_digest':digest,'direction_ids':directions}}))
    return tid

def completed_global(s,iid):
    st=current(s,iid)
    if not st:return False
    proposal=s.get('strategy_proposals',{}).get(st.get('last_accepted_proposal_ref'),{})
    return (st.get('next_action') in {'DELIVER','P14','COMPLETE'} and
        proposal.get('proposal',{}).get('progress_account',{}).get('frontier_complete') is True and
        proposal.get('delivery_disposition',{}).get('allow_dispatch') is False)
