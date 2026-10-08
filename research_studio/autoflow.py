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
         'P12':'INDEPENDENT','D1':'LEARN','D2':'DIRECT','D3':'DIRECT','D4':'FORMULATION_REVIEW',
         'S1':'SEARCH_PLAN','S2':'SOURCE_READ','S3':'ORGANIZE','S4':'READINESS_REVIEW'}
KINDS = {'P1':'MATERIAL','P2':'REDUCE','P3':'ESTABLISH','P4':'ESTABLISH','P5':'COMPARE',
         'P6':'REDUCE','P7':'APPLICABILITY','P8':'ESTABLISH','P10':'INTEGRATE','P11':'ACCOUNT',
         'P12':'VERIFY','D1':'APPLICABILITY','D2':'FORMULATE','D3':'DISCRIMINATE',
         'D4':'VERIFY','S1':'MATERIAL','S2':'MATERIAL','S3':'INTEGRATE','S4':'VERIFY'}


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
                selected_refs=None,source_refs=None):
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
    max_workers=s.get('max_workers',1) if max_workers is None else max_workers
    require(type(max_workers) is int and 1<=max_workers<=8,'AUTHORIZATION_REQUIRED','One to eight project workers required')
    intent_ref=store.blob(intent.encode())
    receipt=store.commit(changes.prepare_source_input(s,intent.encode(),title='Human research intent',purpose='PHENOMENON',blob_get=store.read_blob))
    s=store.read_snapshot();mid=identity({'instance':iid,'intent':intent_ref,'ordinal':len(instance['mission_ids'])+1},'MISSION-')
    config={'schema':'pmrs.autoflow/1','selected_refs':refs,'source_refs':sources,'intent_source_ref':receipt['source_ref'],
            'prerequisites':prerequisites(s,iid,{'selected_refs':refs,'source_refs':sources}) if instance['kind']=='TRW' else {}}
    scope={'target_refs':refs,'source_refs':sources,'allow_derived_work':True,
           'max_research_attempts':max_research_attempts,'formal_target_review':instance['kind']=='TRW',
           'formulation_review':instance['kind']=='TFDW','reports':bool(allow_reports),'autoflow':config}
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
    result=store.commit_control(W.authorize_event(s,iid,mission,budget))
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
    inputs=sorted(set(refs)|{r for row in cfg.get('prerequisites',{}).get('reused',{}).values() for r in row['evidence_refs']})
    # Every predecessor's exact evidence is supplied through native dependencies.
    c={'binding_id':bid,'instance_id':iid,'mission_id':mid,'stage_id':sid,'role':role,'retry_grant_id':'RETRY-'+bid,
       'method_ref':'AUTOFLOW_SCIENTIFIC_DUTY','scope':{'target_refs':refs},'entry_basis':b,'input_refs':inputs,
       'source_refs':sorted(set(sources+[cfg['intent_source_ref']]+list(mission['authorized_scope'].get('discovery_scope',{}).values()))),
       'threshold':'WORK_DISPOSITION_RECORDED','success_criterion':criterion_ref,'ready_since':s.get('_snapshot_sequence',0)}
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
    permitted={'TRW':set(ROLES)&{'P1','P2','P3','P4','P5','P6','P7','P8','P10','P11','P12'},
               'TFDW':{'D1','D2','D3'},'SURVEY':{'S1','S2','S3'}}[workflow_kind]
    if sid not in permitted:return None
    basis={}
    if sid=='P7':basis['analysis_route']='SOURCE_APPLICATION' if role=='LEARN' else 'DIRECT_ANALYSIS'
    try:validate_assignment(sid,definition['type'],role,basis)
    except PMRSError:return None
    return sid,role,basis


def _trw_advance(store,s,instance,mission):
    iid=instance['instance_id'];mid=mission['mission_id'];cfg=mission['authorized_scope']['autoflow']
    rows=_bindings(s,iid,mid);created=[]
    current=prerequisites(s,iid,cfg)
    missing=current['missing']
    if missing:
        sid=missing[0];assigned=[(o,c) for o,c in rows if c['stage_id']==sid]
        if not assigned:
            deps=_prerequisite_bindings(rows,current)
            out=_assign(store,instance,mission,sid,dependencies=deps)
            if out:created.append(out)
        return created
    # All prerequisite work is evidenced, not inferred from three settled tasks.
    scientific=[(o,c) for o,c in rows if c['stage_id'] not in PREREQUISITES and not c['role'].startswith('REPORT_')]
    if not scientific:
        deps=_prerequisite_bindings(rows,current)
        out=_assign(store,instance,mission,'P4',dependencies=deps)
        return [out] if out else []
    # A concrete transfer obstacle has a separately frozen direct baseline.
    # Their common input is the original problem, not one another's output.
    transfers=[(o,c) for o,c in scientific if c['stage_id']=='P7' and c['role']=='LEARN']
    direct=[(o,c) for o,c in scientific if c['stage_id']=='P7' and c['role']=='DIRECT']
    for o,c in transfers:
        if any(x.get('entry_basis',{}).get('direct_for')==c['binding_id'] for _,x in direct):continue
        out=_assign(store,instance,mission,'P7',role='DIRECT',kind='APPLICABILITY',
            criterion='Independently analyze this concrete obstacle directly from the shared original baseline: '+store.read_blob(o['definition']['criterion_body_ref']).decode(),
            basis={'direct_for':c['binding_id'],'analysis_route':'DIRECT_ANALYSIS'})
        if out:created.append(out)
    if created:return created
    branches=transfers+direct
    if branches and all(_finished(s,o,c) for o,c in branches):
        selected=[_branch(o,c) for o,c in branches]
        if not any(c['stage_id']=='P7' and c['role']=='SYNTHESIS' and c['entry_basis'].get('synthesis_branches')==selected for o,c in scientific):
            out=_assign(store,instance,mission,'P7',role='SYNTHESIS',kind='APPLICABILITY',dependencies=branches,
                criterion='Compare every selected transfer and independent direct attempt for this exact obstacle set: '+
                    '; '.join(sorted(store.read_blob(o['definition']['criterion_body_ref']).decode() for o,c in transfers)),
                basis={'analysis_route':'COMPARATIVE','synthesis_branches':selected})
            if out:return [out]
    # Wait only for actual outstanding work; concrete gap proposals are assigned
    # separately by the host before this hook runs again.
    if any(not _finished(s,o,c) for o,c in scientific):return []
    unassigned=[o for o in s['obligations'].values() if not o['definition']['consumer_bindings']
        and any('CHANGE-'+str(r.get('capture_ref'))==o['definition'].get('created_by') and r['mission_id']==mid for r in s['requests'].values())]
    if unassigned:return []
    # A global mathematical account is needed after actual research/review. Its
    # identity includes the exact work frontier, never a task-count iteration.
    frontier=[(o,c) for o,c in scientific if c['stage_id'] not in {'P11','P12'}]
    covered={bid for o,c in scientific if c['stage_id']=='P11'
             for bid in c.get('entry_basis',{}).get('autoflow',{}).get('accounted_bindings',[])}
    if frontier and any(c['binding_id'] not in covered for o,c in frontier):
        bids=sorted(c['binding_id'] for o,c in frontier)
        criterion='Reassess the global mathematical gap for the exact original target using this concrete work frontier: '+', '.join(bids)+'. '+DUTIES['P11'][1]+' Return only concrete missing duties; preserve every failed and unperformed scope.'
        out=_assign(store,instance,mission,'P11',criterion=criterion,dependencies=frontier,
                    basis={'autoflow_accounted_bindings':bids})
        return [out] if out else []
    # A genuinely new global assembly needs a fresh independent check. A mere
    # gap account, an unchanged old argument or a checklist stage does not.
    for o,c in scientific:
        if c['stage_id'] not in {'P10','P11'}:continue
        authors={snapshot_request['task_id'] for account in _accounts(s,o,c)
                 if (snapshot_request:=s['requests'].get(account['request_id']))}
        produced={p['record_ref'] for p in s.get('production_events',{}).values() if p.get('task_id') in authors}
        arguments=[ref for ref in o['projection'].get('evidence_refs',[])
                   if ref in produced and s['records'].get(ref,{}).get('kind')=='Argument']
        if not arguments:continue
        criterion='Independently inspect this exact newly assembled global argument and its unresolved interfaces: '+', '.join(sorted(arguments))
        out=_assign(store,instance,mission,'P12',criterion=criterion,dependencies=[(o,c)],refs=cfg['selected_refs'])
        if out:return [out]
    return []


def _discovery_advance(store,s,instance,mission):
    iid=instance['instance_id'];mid=mission['mission_id'];rows=_bindings(s,iid,mid)
    if not rows:return [_assign(store,instance,mission,'D1')]
    if any(not _finished(s,o,c) for o,c in rows if not c['role'].startswith('REPORT_')):return []
    candidates=sorted({c['statement_ref'] for c in s.get('candidates',{}).values() if c['instance_id']==iid})
    if not candidates:
        learned=[(o,c) for o,c in rows if c['stage_id']=='D1' and o['projection'].get('evidence_refs')
                 and any(a['work_disposition']=='ADDRESSED' for a in _accounts(s,o,c))]
        if learned and not any(c['stage_id']=='D2' for o,c in rows):
            out=_assign(store,instance,mission,'D2',dependencies=learned,
                criterion='Formulate precise candidates only to the extent supported by the actually learned evidence and permitted discovery axes. Zero justified candidates is valid.')
            return [out] if out else []
        return []
    # A precise frontier needs actual discrimination before independent review.
    if not any(c['stage_id']=='D3' and set(candidates)<=set(c['input_refs']) for o,c in rows):
        out=_assign(store,instance,mission,'D3',refs=candidates,dependencies=[(o,c) for o,c in rows if c['stage_id'] in {'D1','D2'}],
            criterion='Compare this exact candidate frontier using distinguishing examples, local deductions, counterevidence and hypothesis costs. Preserve every unknown relation. Frontier: '+', '.join(candidates))
        return [out] if out else []
    return []


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
        if not any(c['stage_id']=='S2' and set(missing)<=set(c['source_refs']) for o,c in rows):
            return [_assign(store,instance,mission,'S2',refs=refs,sources=missing,dependencies=rows)]
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
    # Explicit review findings/coverage gaps are bounded return duties; retain
    # the finding text and exact affected refs. The ordinary cumulative gate is
    # unchanged, and no automatic retrieval or source expansion occurs.
    created=[]
    for error in problems:
        sid=error.get('return_stage')
        if sid not in {'S2','S3'}:continue
        criterion='Resolve only this exact Survey coverage finding: '+error['code']+'; '+error.get('message','')
        out=_assign(store,instance,mission,sid,refs=refs,sources=sources,dependencies=rows,criterion=criterion)
        if out:created.append(out)
    return created


def advance(store,iid):
    s=store.read_snapshot();instance=W.select_instance(s,iid);mission=s['missions'].get(instance.get('current_mission_id'),{})
    if instance['status']!='ACTIVE' or not mission.get('authorized_scope',{}).get('autoflow'):return []
    if instance['kind']=='TRW':return _trw_advance(store,s,instance,mission)
    if instance['kind']=='TFDW':return _discovery_advance(store,s,instance,mission)
    return _survey_advance(store,s,instance,mission)


def status(snapshot,iid):
    instance=W.select_instance(snapshot,iid);mission=snapshot['missions'].get(instance.get('current_mission_id'),{})
    cfg=mission.get('authorized_scope',{}).get('autoflow')
    if not cfg:return {'enabled':False,'complete':False,'missing':[],'waiting_human':[]}
    rows=_bindings(snapshot,iid,mission['mission_id']);missing=[];human=[]
    if instance['kind']=='TRW':missing=prerequisites(snapshot,iid,cfg)['missing']
    if instance['kind']=='TFDW' and rows and all(_finished(snapshot,o,c) for o,c in rows):
        candidates=any(c['instance_id']==iid for c in snapshot.get('candidates',{}).values())
        human=['CANDIDATE_FRONTIER_SELECTION' if candidates else 'NO_CANDIDATES_DECISION']
    if instance['kind']=='SURVEY':
        from . import survey
        refs=survey.selection(snapshot,iid) or cfg['selected_refs']
        r=survey.readiness(snapshot,iid,refs)
        missing=[e['code'] for e in r['errors']]
        if not cfg['source_refs'] and not refs:human=['SOURCE_SELECTION']
        if r['status'] in {'READY','SYNTHETIC_READY'}:missing=[]
    outstanding=[{'obligation_id':o['definition']['obligation_id'],'binding_id':c['binding_id'],'stage_id':c['stage_id']}
                 for o,c in rows if not _finished(snapshot,o,c)]
    origins={'CHANGE-'+str(r.get('capture_ref')) for r in snapshot['requests'].values() if r['mission_id']==mission['mission_id']}
    unassigned=[{'obligation_id':o['definition']['obligation_id'],'criterion_ref':o['definition']['criterion_body_ref'],
                 'type':o['definition']['type'],'code':'UNASSIGNED_SCIENTIFIC_GAP'} for o in snapshot['obligations'].values()
                if not o['definition']['consumer_bindings'] and o['definition'].get('created_by') in origins]
    if unassigned:
        missing.append('UNASSIGNED_SCIENTIFIC_GAP');human.append('SCOPED_GAP_DISPOSITION')
    return {'enabled':True,'complete':not missing and not outstanding,'missing':missing,'waiting_human':human,
            'outstanding':outstanding,'unassigned':unassigned,'prerequisites':prerequisites(snapshot,iid,cfg) if instance['kind']=='TRW' else {},
            'automatic_manuscript':False,'mission_id':mission['mission_id']}
