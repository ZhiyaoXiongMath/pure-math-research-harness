"""Scope-local report snapshots and six catalog classes, independent of decisions."""
from copy import deepcopy
from .util import identity, require, canonical, read, safe_path, sha, PMRSError
from .relations import premise_closure, edges

SCHEMA='pmrs.report/final-1'
CLASSES=('UNKNOWN_FORMAT','DAMAGED_ACTIVE_ARTIFACT','STALE_CANDIDATE',
         'RECOVERABLE_ACTIVE_CANDIDATE','COMPLETED_CURRENT_REPORT')


def scope(snapshot, instance_id, mission_id=None):
    require(instance_id in snapshot.get('instances',{}),'INSTANCE_SELECTOR_REQUIRED','Select an exact report workflow')
    instance=snapshot['instances'][instance_id]
    mission_id=mission_id or instance.get('current_mission_id')
    if mission_id is not None:
        require(snapshot.get('missions',{}).get(mission_id,{}).get('instance_id')==instance_id,'REPORT_SCOPE_INVALID','Mission belongs to another workflow')
    targets=[instance['target_ref']] if instance.get('target_ref') else []
    candidates=sorted(c['statement_ref'] for c in snapshot.get('candidates',{}).values()
                      if c['instance_id']==instance_id and c.get('candidate_state') not in {'NOT_SELECTED','REJECTED_FOR_STATED_REASON'})
    content={'kind':'INSTANCE_MISSION','instance_ids':[instance_id], 'mission_ids':[mission_id] if mission_id else [],
             'target_refs':targets,'candidate_refs':candidates,
             'membership_query':{'query_kind':'CANDIDATE_FRONTIER','instance_id':instance_id},
             'policy_digest':identity(snapshot.get('language_policy',{}))}
    return {'scope_id':identity(content,'REPORT-SCOPE-'),**content}


def freeze(snapshot, selected_scope):
    """Include exact relevant material and scope membership, not runtime counters."""
    current=scope(snapshot,selected_scope['instance_ids'][0],next(iter(selected_scope['mission_ids']),None))
    current['mission_ids']=list(selected_scope['mission_ids'])
    current['scope_id']=identity({k:v for k,v in current.items() if k!='scope_id'},'REPORT-SCOPE-')
    roots=set(current['target_refs']+current['candidate_refs'])
    brief=snapshot['instances'][current['instance_ids'][0]].get('discovery_brief_ref')
    if brief in snapshot.get('sources',{}):roots.add(brief)
    obligations={}
    for oid,o in snapshot.get('obligations',{}).items():
        d=o.get('definition',o)
        if d.get('type')=='REPORT': continue
        if any(c.get('instance_id') in current['instance_ids'] and
               (not current['mission_ids'] or c.get('mission_id') in current['mission_ids'])
               for c in d.get('consumer_bindings',[])):
            obligations[oid]=deepcopy(o)
            roots.update(d.get('target_refs',[]));roots.update(o.get('projection',{}).get('evidence_refs',[]))
    # All explicit alternative arguments for selected statements are relevant;
    # they retain separate support paths and are not substituted for one another.
    for ref,record in snapshot.get('records',{}).items():
        if record['kind']=='Argument' and record['data']['conclusion_ref'] in roots: roots.add(ref)
        if record['kind']=='Example' and set(record['data']['target_refs'])&roots: roots.add(ref)
    members=premise_closure(roots,snapshot,include_method_sources=True)
    support={sid:deepcopy(value) for sid,value in snapshot.get('supports',{}).items()
             if value.get('statement_ref') in members or value.get('argument_ref') in members}
    qualifications={qid:deepcopy(q) for qid,q in snapshot.get('qualifications',{}).items()
                    if q.get('support_id') in support or q.get('support_ref') in support
                    or qid in {r for p in support.values() for r in p.get('qualification_refs',[])}}
    assessments={ref:record for ref,record in snapshot.get('records',{}).items()
                 if record['kind']=='Assessment' and any(r in members for r in record['data'].get('target_refs',[]))}
    members.update(assessments)
    members.update(q['assessment_ref'] for q in qualifications.values() if q.get('assessment_ref') in snapshot['records'])
    records={r:deepcopy(snapshot['records'][r]) for r in sorted(members) if r in snapshot.get('records',{})}
    sources={r:deepcopy(snapshot['sources'][r]) for r in sorted(members) if r in snapshot.get('sources',{})}
    related=[deepcopy(e) for e in edges(snapshot) if e['source_ref'] in members and e['target_ref'] in members]
    visited={k:deepcopy(v) for k,v in snapshot.get('visits',{}).items()
             if v.get('instance_id') in current['instance_ids'] and
             (not current['mission_ids'] or v.get('mission_id') in current['mission_ids']) and
             not all(snapshot.get('obligations',{}).get(b['obligation_id'],{}).get('definition',{}).get('type')=='REPORT'
                     for b in v.get('assigned_obligation_bindings',[]))}
    value={'schema':'pmrs.report-snapshot/final-1','project_id':snapshot['project_id'],
           'scope':current,'workflow_kind':snapshot['instances'][current['instance_ids'][0]]['kind'],
           'language_policy':deepcopy(snapshot['language_policy']),'records':records,'sources':sources,
           'relations':related,'supports':support,'qualifications':qualifications,'obligations':obligations,
           'inferences':{k:deepcopy(v) for k,v in snapshot.get('inferences',{}).items() if v.get('argument_ref') in members},
           'review_executions':{q['review_execution_event']:deepcopy(snapshot.get('review_executions',{}).get(q['review_execution_event'])) for q in qualifications.values() if q.get('review_execution_event')},
           'withdrawals':{k:v for k,v in snapshot.get('withdrawals',{}).items() if v.get('support_id') in support},
           'performed_stages':visited,
           'authority':'RESEARCH_EVIDENCE_AND_OPEN_BOUNDARIES_NOT_FORMAL_PROOF'}
    return value


def fingerprint(snapshot, selected_scope):
    return identity(freeze(snapshot, selected_scope))


def check_files(store, entry):
    for path,digest in entry.get('files',{}).items():
        require(sha(read(safe_path(store.root,path),256*1024**2))==digest,'REPORT_ARTIFACT_CHANGED',path)
    for digest in entry.get('blobs',[]):store.read_blob(digest)
    for ref in entry.get('record_refs',[]):
        # The actual record file, not just a snapshot copy, is authoritative.
        store.read_record(ref)


def classify(store,snapshot,entry):
    if entry.get('schema')!=SCHEMA: return 'UNKNOWN_FORMAT'
    required={'report_id','scope','scope_fingerprint','snapshot_ref','profiles','files','blobs','status'}
    if not required<=set(entry): return 'UNKNOWN_FORMAT'
    try: check_files(store,entry)
    except (PMRSError,OSError,KeyError,ValueError): return 'DAMAGED_ACTIVE_ARTIFACT'
    if entry['scope_fingerprint']!=fingerprint(snapshot,entry['scope']):return 'STALE_CANDIDATE'
    from .reports import pair_complete
    return 'COMPLETED_CURRENT_REPORT' if entry['status']=='COMPLETE' and pair_complete(entry) else 'RECOVERABLE_ACTIVE_CANDIDATE'


def catalog(store,snapshot=None,instance_id=None):
    snapshot=store.read_snapshot() if snapshot is None else snapshot
    result=[{'report_id':rid,'classification':classify(store,snapshot,entry),
             'active':rid in snapshot.get('active_reports',{}).values(),
             'instance_ids':entry.get('scope',{}).get('instance_ids',[]),
             'state':entry.get('status'),'missing_checks':missing_checks(entry)}
            for rid,entry in snapshot.get('reports',{}).items()
            if instance_id is None or instance_id in entry.get('scope',{}).get('instance_ids',[])]
    return result


def missing_checks(entry):
    missing=[]
    for name,p in entry.get('profiles',{}).items():
        if not p.get('body_sha256'):missing.append(name+': author')
        if not p.get('render'):missing.append(name+': PDF and all page images')
        if not p.get('semantic') or p['semantic']['verdict']!='PASS':missing.append(name+': semantic review')
        for page in (p.get('render') or {}).get('pages',[]):
            if p.get('visual',{}).get(page['id'],{}).get('verdict')!='PASS': missing.append(name+': '+page['id'])
    return missing
