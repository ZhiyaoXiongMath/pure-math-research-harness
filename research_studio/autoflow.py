"""Evidence-driven ordinary rounds; no stage counter or management model.

Every assignment is a native responsibility in the original finite mission.
A disposition records work, not mathematical qualification. Human decisions and
manuscript requests remain outside this deterministic advancement service.
"""
from copy import deepcopy
from .util import identity, require, PMRSError
from . import obligations as O, workflow_instances as W, changes
from .workflows.registry import validate_assignment, INDEPENDENT
from .research_prompts import DUTIES

PREREQUISITES = ('P1', 'P2', 'P3')
ROLES = {'P1':'PLAN','P2':'PLAN','P3':'PLAN','P4':'RESEARCH','P5':'SYNTHESIS',
         'P6':'PLAN','P7':'LEARN','P8':'RESEARCH','P10':'SYNTHESIS','P11':'SYNTHESIS',
         'P12':'INDEPENDENT','D1':'LEARN','D2':'PLAN','D3':'DIRECT','D4':'FORMULATION_REVIEW','D5':'SYNTHESIS',
         'S1':'SEARCH_PLAN','S2':'SOURCE_READ','S3':'ORGANIZE','S4':'READINESS_REVIEW'}
KINDS = {'P1':'MATERIAL','P2':'REDUCE','P3':'ESTABLISH','P4':'ESTABLISH','P5':'COMPARE',
         'P6':'REDUCE','P7':'APPLICABILITY','P8':'ESTABLISH','P10':'INTEGRATE','P11':'ACCOUNT',
         'P12':'VERIFY','D1':'APPLICABILITY','D2':'FORMULATE','D3':'DISCRIMINATE',
         'D4':'VERIFY','D5':'ACCOUNT','S1':'MATERIAL','S2':'MATERIAL','S3':'INTEGRATE','S4':'VERIFY'}


def _bindings(snapshot, iid, mid=None):
    return [(o,c) for o in snapshot['obligations'].values() for c in o['definition']['consumer_bindings']
            if c['instance_id']==iid and (mid is None or c['mission_id']==mid)]


def _accounts(snapshot, o, c):
    requests={r['request_id'] for r in snapshot['requests'].values() if r.get('acceptance_state')=='ACCEPTED'
              and any(b['binding_id']==c['binding_id'] for b in snapshot['tasks'][r['task_id']].get('obligation_bindings',[]))}
    return [a for a in o['projection'].get('attempt_accounts',[]) if a['request_id'] in requests]


def _finished(snapshot, o, c):
    return bool(_accounts(snapshot,o,c)) or c['binding_id'] in snapshot.get('retired_consumers',{})


def _branch(o,c):
    return {'key':c['binding_id'],'obligation_id':o['definition']['obligation_id'],'binding_id':c['binding_id'],
            'stage_id':c['stage_id'],'role':c['role'],'required':True}


def _current_record(snapshot, ref):
    record=snapshot.get('records',{}).get(ref)
    if not record:return False
    obj=snapshot.get('objects',{}).get(record.get('object_id'),{})
    return not obj or obj.get('selected_revision')==ref


def _reusable(snapshot,o,c,refs,sources):
    """Require an actual addressed prerequisite and unchanged controlling input.

    Merely settling a task or mentioning a stage never supplies its mathematics.
    Evidence must still be selected and the original exact source set available.
    """
    if c['stage_id'] not in PREREQUISITES:return None
    if c['binding_id'] in snapshot.get('retired_consumers',{}):return None
    supplied=set(c.get('input_refs',[]))|set(o['definition']['target_refs'])
    if not set(refs)<=supplied:return None
    # Human intent sources are deliberately not prerequisites for reuse.
    if not set(sources)<=set(c.get('source_refs',[])):return None
    if any(not _current_record(snapshot,r) for r in supplied):return None
    evidence=o['projection'].get('evidence_refs',[])
    if not evidence or any(not _current_record(snapshot,r) for r in evidence):return None
    expected={'Context'} if c['stage_id']=='P1' else {'Statement','Argument'}
    if not any(snapshot['records'][r]['kind'] in expected for r in evidence):return None
    if o['projection'].get('blocker_refs') or o['projection'].get('resolution')=='NEEDS_RECHECK':return None
    # A later failed or partial recheck supersedes the former completion account.
    for account in _accounts(snapshot,o,c)[-1:]:
        if account['work_disposition']!='ADDRESSED' or account['remaining_conditions'] or account['blocker_proposals']:continue
        task=snapshot['tasks'][snapshot['requests'][account['request_id']]['task_id']]
        manifest={row['ref']:row for row in task.get('input_manifest',[])}
        if any(ref not in manifest for ref in refs+sources):continue
        # Reuse obeys the scientific read bindings but deliberately ignores old
        # mission status and unrelated task/queue counters. Integrity is checked
        # again by ordinary freezing/admission before consuming these artifacts.
        stale=False
        from .contracts import digest
        from .relations import affected_supports
        for binding in task.get('read_set',[]):
            record=snapshot['records'].get(binding['record_ref'])
            selection=binding['selection_binding']
            if not record or record['body_sha256']!=binding['body_hash'] or (
                selection['mode']=='CURRENT' and snapshot['objects'].get(selection['object_id'],{}).get('selected_revision')!=selection['expected_revision']):
                stale=True;break
            required=binding['required_support_refs'];guard=binding['qualification_guard']
            withdrawn=affected_supports(snapshot,{w['support_id'] for w in snapshot.get('withdrawals',{}).values() if w.get('active',True)}) if required else set()
            if any(ref not in snapshot['supports'] or ref in withdrawn or
                   isinstance(guard,dict) and ref in guard and digest(snapshot['supports'][ref])!=guard[ref] for ref in required):
                stale=True;break
        if stale:continue
        if any(snapshot['sources'].get(ref,{}).get('blob_hash')!=manifest[ref].get('sha256') for ref in sources):continue
        if any(snapshot.get('survey_source_status',{}).get(ref,{}).get('withdrawn') or
               snapshot.get('survey_source_status',{}).get(ref,{}).get('version_conflict') for ref in sources):continue
        if any(not snapshot.get('sources',{}).get(ref) for ref in sources):continue
        return {'stage_id':c['stage_id'],'task_id':task['task_id'],'request_id':account['request_id'],
                'binding_id':c['binding_id'],'evidence_refs':list(evidence),'account':deepcopy(account)}
    return None


def prerequisites(snapshot,iid,scope):
    reuse={}
    for o,c in _bindings(snapshot,iid):
        result=_reusable(snapshot,o,c,scope['selected_refs'],scope['source_refs'])
        if result:reuse[c['stage_id']]=result
    return {'required':list(PREREQUISITES),'reused':reuse,'missing':[sid for sid in PREREQUISITES if sid not in reuse]}


def _prerequisite_bindings(rows,current):
    selected={row['binding_id'] for row in current['reused'].values()}
    return [(o,c) for o,c in rows if c['binding_id'] in selected]


def start_round(store,iid,intent,*,max_calls=8,max_workers=None,policy=None,model_overrides=None,
                max_research_attempts=1,allow_reports=True,report_first_actions=None,
                selected_refs=None,source_refs=None,p14_mode="AUTO_P14"):
    s=store.read_snapshot();instance=W.select_instance(s,iid)
    require(instance['status']!='ENDED','AUTHORIZATION_REQUIRED','An ended instance needs an explicit new instance')
    discovery=W.validate_discovery_scope(s,instance)
    refs=list(selected_refs or [])
    if instance.get('target_ref'):refs.append(instance['target_ref'])
    if instance['kind']=='SURVEY':
        from . import survey
        refs=survey.selection(s,iid,selected_refs)
        sources=list(source_refs if source_refs is not None else instance['survey_scope']['source_refs'])
    else:sources=list(source_refs or [])
    refs=sorted(set(refs));sources=sorted(set(sources))
    require(all(ref in s['records'] for ref in refs) and all(ref in s['sources'] for ref in sources),
            'INCOMPLETE_CONTEXT','Select exact available knowledge and source materials')
    from .input_plans import _source_version
    for ref in sources:_source_version(s,ref)
    if instance['kind'] in {'TRH','FDH'} and (policy or {}).get('executor_contract',{}).get('executor')=='codex':
        from .model_policy import resolve
        main_stage,main_role='MAIN_'+instance['kind'],'MAIN_DECIDE'
        resolve(instance['kind'],main_stage,main_role,'MAIN_STRATEGY',actor_kind='MAIN',capabilities=policy.get('model_capabilities'))
    max_workers=1 if instance['kind']=='SURVEY' else 8
    require(type(max_workers) is int and 1<=max_workers<=8,'AUTHORIZATION_REQUIRED','One to eight project workers required')
    intent_ref=store.blob(intent.encode())
    receipt=store.commit(changes.prepare_source_input(s,intent.encode(),title='Human research intent',purpose='PHENOMENON',blob_get=store.read_blob))
    s=store.read_snapshot();mid=identity({'instance':iid,'intent':intent_ref,'ordinal':len(instance['mission_ids'])+1},'MISSION-')
    config={'schema':'pmrs.harness-runtime/4.2.2','main_enabled':instance['kind'] in {'TRH','FDH'},'selected_refs':refs,'source_refs':sources,'intent_source_ref':receipt['source_ref'],
            'method_version':'pmrs.harness-methods/4.2.2'}
    scope={'target_refs':refs,'source_refs':sources,'allow_derived_work':True,
           'max_research_attempts':max_research_attempts,'formal_target_review':instance['kind']=='TRH',
           'formulation_review':instance['kind']=='FDH','reports':bool(allow_reports),'autoflow':config}
    if discovery:scope['discovery_scope']=deepcopy(discovery)
    if instance['kind']=='SURVEY':
        scope['survey_scope']=deepcopy(instance['survey_scope'])
        # A knowledge objective never implicitly starts or authorizes a manuscript.
        scope['reports']=False
    mission={'mission_id':mid,'instance_id':iid,'intent_ref':intent_ref,'authorized_scope':scope,
             'budget_grant_id':'BUDGET-'+mid,'obligations':[],'retry_grants':[]}
    if report_first_actions:mission['report_first_actions']=list(report_first_actions)
    policy=deepcopy(policy or {})
    if model_overrides is not None:
        from .model_policy import merge_overrides
        policy['model_overrides']=merge_overrides(policy.get('model_overrides',[]),model_overrides,
            workflow_kind=instance['kind'],capabilities=policy.get('model_capabilities'))
    budget={'budget_grant_id':mission['budget_grant_id'],'max_calls':max_calls,'max_workers':max_workers,
            'execution_policy':{**policy,'max_workers':max_workers}}
    if instance['kind']=='TRH':
        W.configure_p14(store,iid,mode=p14_mode)
        s=store.read_snapshot()
    result=store.commit_control(W.authorize_event(s,iid,mission,budget))
    from . import strategy
    if instance['kind'] in {'TRH','FDH'}:strategy.initialize(store,iid)
    advance(store,iid)
    now=store.read_snapshot()
    return {**result,'instance_id':iid,'mission_id':mid,'status':'ACTIVE','model_calls':0,
            'autoflow':status(now,iid),'bindings':[_branch(o,c) for o,c in _bindings(now,iid,mid)]}


def _assign(store,instance,mission,sid,*,role=None,kind=None,criterion=None,refs=None,sources=None,
            dependencies=(),basis=None,key=None):
    from .engine import _assign_followup
    s=store.read_snapshot();cfg=mission['authorized_scope']['autoflow'];iid=instance['instance_id'];mid=mission['mission_id']
    role=role or ROLES[sid];kind=kind or KINDS[sid]
    refs=sorted(set(cfg['selected_refs'] if refs is None else refs))
    sources=sorted(set(cfg['source_refs'] if sources is None else sources))
    criterion=criterion or ('Carry out the actual '+sid+' scientific responsibility for this exact authorized objective. '+DUTIES[sid][1]+' '+DUTIES[sid][2])
    criterion_ref=store.blob(criterion.encode())
    oid=identity({'instance':iid,'criterion':criterion_ref,'targets':refs},'OB-')
    bid=identity({'mission':mid,'obligation':oid,'role':role},'BINDING-')
    existing=s['obligations'].get(oid)
    if existing and any(c['binding_id']==bid for c in existing['definition']['consumer_bindings']):return None
    # The criterion/targets stay stable across mission labels and input revisions.
    # The ordinary responsibility gate therefore retains its cumulative ceiling.
    deps=[{'dependency_id':identity([oid,o['definition']['obligation_id'],c['binding_id']],'DEP-'),
           'binding_ref':o['definition']['obligation_id'],'binding_id':c['binding_id'],'threshold':'WORK_DISPOSITION_RECORDED'}
          for o,c in dependencies if c['mission_id']==mid]
    b=deepcopy(basis or {});b['autoflow']={'mission_id':mid,'key':key or sid,
        'accounted_bindings':b.pop('autoflow_accounted_bindings',[]),
        'reused_work':deepcopy(cfg.get('prerequisites',{}).get('reused',{}))}
    branches=[_branch(o,c) for o,c in _bindings(s,iid,mid)]
    b['research_plan']={'plan_id':'AUTOFLOW-'+mid,'branch_key':key or sid,'selected_branches':branches,
        'common_input_refs':cfg['selected_refs'],'common_source_refs':cfg['source_refs'],'plan_intent':'Actual result-driven bounded round'}
    if sid=='P7':b.setdefault('analysis_route','SOURCE_APPLICATION' if role=='LEARN' else 'DIRECT_ANALYSIS' if role=='DIRECT' else 'COMPARATIVE')
    validate_assignment(sid,kind,role,b)
    inputs=sorted(set(refs))
    # Every predecessor's exact evidence is supplied through native dependencies.
    c={'binding_id':bid,'instance_id':iid,'mission_id':mid,'stage_id':sid,'role':role,'retry_grant_id':'RETRY-'+bid,
       'method_ref':'AUTOFLOW_SCIENTIFIC_DUTY','scope':{'target_refs':refs},'entry_basis':b,'input_refs':inputs,
       'source_refs':sorted(set(sources+[cfg['intent_source_ref']]+list(mission['authorized_scope'].get('discovery_scope',{}).values()))),
       'threshold':'WORK_DISPOSITION_RECORDED','success_criterion':criterion_ref,'ready_since':s.get('_snapshot_sequence',0)}
    require(instance['kind']=='SURVEY','MAIN_DECISION_REQUIRED','Only Survey permits host-created stage tasks')
    if instance['kind']=='SURVEY':
        from .survey import plan_consumer
        c=plan_consumer(store,s,instance,{'item':{},'scope':{'target_refs':refs},'stage':sid,'role':role},c,deps)
    o=O.make(oid,kind,refs,criterion_ref,consumer_bindings=[c],dependencies=deps,
             created_by='AUTHORIZED_AUTOFLOW',effect='BOUNDED_SCIENTIFIC_DUTY')
    if existing:
        # Keep original dependencies and definition on repeat rather than create
        # another duty or erase previous failed attempts.
        o=existing
    return _assign_followup(store,instance,mission,o,c,basis_ref=mission['intent_ref'])


def proposal_activity(definition,origin_stage,workflow_kind):
    """Optional declarative activity hint; it grants no consumer authority."""
    effect=definition.get('effect_on_goal','')
    if not isinstance(effect,str) or not effect.startswith('ACTIVITY:'):return None
    parts=effect.split(':')
    if len(parts)!=3:return None
    sid,role=parts[1:]
    permitted={'TRH':set(ROLES)&{'P1','P2','P3','P4','P5','P6','P7','P8','P10','P11','P12'},
               'FDH':{'D1','D2','D3'},'SURVEY':{'S1','S2','S3'}}[workflow_kind]
    if sid not in permitted:return None
    basis={}
    if sid=='P7':basis['analysis_route']='SOURCE_APPLICATION' if role=='LEARN' else 'DIRECT_ANALYSIS'
    try:validate_assignment(sid,definition['type'],role,basis)
    except PMRSError:return None
    return sid,role,basis


def _survey_advance(store,s,instance,mission):
    from . import survey
    iid=instance['instance_id'];mid=mission['mission_id'];cfg=mission['authorized_scope']['autoflow'];rows=_bindings(s,iid,mid)
    if any(not _finished(s,o,c) for o,c in rows):return []
    refs=survey.selection(s,iid) or cfg['selected_refs'];sources=cfg['source_refs']
    if not sources and not refs:
        if not rows:return [_assign(store,instance,mission,'S1',refs=[],sources=[])]
        return []
    # Reading is required for each selected actual source version; the model may
    # honestly fail to read it, in which case work waits instead of claiming done.
    read_sources=set()
    for row in s.get('survey_readings',{}).values():
        if row['instance_id']!=iid or not row.get('locators'):continue
        actual=survey.source_details(s,row['source_ref'])
        if row['version']==actual['version'] and row['material_sha256']==actual['material_sha256'] and not actual['withdrawn'] and not actual['version_conflict']:
            read_sources.add(row['source_ref'])
    missing=[r for r in sources if r not in read_sources]
    if missing:
        if not any(c['stage_id']=='S2' and missing[0] in c['source_refs'] for o,c in rows):
            return [_assign(store,instance,mission,'S2',refs=refs,sources=missing[:1],dependencies=rows)]
        return []
    coverage=[r for r in s.get('survey_coverage',{}).values() if r['instance_id']==iid]
    if not coverage or not refs:
        if not any(c['stage_id']=='S3' for o,c in rows):return [_assign(store,instance,mission,'S3',refs=refs,sources=sources,dependencies=rows)]
        return []
    ready=survey.readiness(s,iid,refs)
    if ready['status'] in {'READY','SYNTHETIC_READY'}:
        if not any(row['instance_id']==iid and row['scope_fingerprint']==ready['scope_fingerprint'] for row in s.get('survey_snapshots',{}).values()):
            return [survey.freeze_knowledge(store,iid,refs)]
        return []
    problems=[e for e in ready['errors'] if e['code']!='SURVEY_REVIEW_REQUIRED']
    if not problems:
        if not any(c['stage_id']=='S4' and c.get('survey_context',{}).get('scope_fingerprint')==ready['scope_fingerprint'] for o,c in rows):
            return [_assign(store,instance,mission,'S4',refs=refs,sources=sources,dependencies=rows)]
        return []
    # Insufficient science stops the linear workflow. A user revision can
    # authorize a necessary suffix; no hidden autonomous return loop.
    return []


def advance(store,iid):
    s=store.read_snapshot();instance=W.select_instance(s,iid);mission=s['missions'].get(instance.get('current_mission_id'),{})
    if instance['status']!='ACTIVE' or not mission.get('authorized_scope',{}).get('autoflow'):return []
    if instance['kind'] in {'TRH','FDH'}:
        from .harness_runtime import advance as wake_main
        return wake_main(store,s,instance,mission)
    return _survey_advance(store,s,instance,mission)


def status(snapshot,iid):
    instance=W.select_instance(snapshot,iid);mission=snapshot['missions'].get(instance.get('current_mission_id'),{})
    cfg=mission.get('authorized_scope',{}).get('autoflow')
    if not cfg:return {'enabled':False,'complete':False,'missing':[],'waiting_human':[]}
    rows=_bindings(snapshot,iid,mission['mission_id']);missing=[];human=[]
    if instance['kind']=='TRH':missing=[]
    if instance['kind']=='FDH' and rows and __import__('research_studio.strategy',fromlist=['completed_global']).completed_global(snapshot,iid):
        candidates=any(c['instance_id']==iid for c in snapshot.get('candidates',{}).values())
        human=['CANDIDATE_FRONTIER_SELECTION' if candidates else 'NO_CANDIDATES_DECISION']
    if instance['kind']=='SURVEY':
        from . import survey
        refs=survey.selection(snapshot,iid) or cfg['selected_refs']
        r=survey.readiness(snapshot,iid,refs)
        missing=[e['code'] for e in r['errors']]
        if not cfg['source_refs'] and not refs:human=['SOURCE_SELECTION']
        if r['status'] in {'READY','SYNTHETIC_READY'}:missing=[]
    from .main_recovery import binding_disposition
    outstanding=[]
    for o,c in rows:
        if _finished(snapshot,o,c):continue
        maintenance=binding_disposition(snapshot,c['binding_id'])
        outstanding.append({'obligation_id':o['definition']['obligation_id'],'binding_id':c['binding_id'],'stage_id':c['stage_id'],
            **maintenance,'current_blocking':not maintenance.get('historical_execution_failure',False)})
    current_outstanding=[row for row in outstanding if row['current_blocking']]
    origins={'CHANGE-'+str(r.get('capture_ref')) for r in snapshot['requests'].values() if r['mission_id']==mission['mission_id']}
    unassigned=[{'obligation_id':o['definition']['obligation_id'],'criterion_ref':o['definition']['criterion_body_ref'],
                 'type':o['definition']['type'],'code':'UNASSIGNED_SCIENTIFIC_GAP'} for o in snapshot['obligations'].values()
                if not o['definition']['consumer_bindings'] and o['definition'].get('created_by') in origins]
    if unassigned:missing.append('MAIN_GAP_DISPOSITION_REQUIRED')
    if cfg.get('main_enabled') and instance['kind'] in {'TRH','FDH'}:
        from . import strategy
        if not strategy.completed_global(snapshot,iid):missing.append('MAIN_GLOBAL_ACCOUNT_REQUIRED')
    return {'enabled':True,'complete':not missing and not current_outstanding,'missing':missing,'waiting_human':human,
            'outstanding':outstanding,'current_outstanding':current_outstanding,'unassigned':unassigned,'prerequisites':{},
            'automatic_manuscript':False,'mission_id':mission['mission_id']}
