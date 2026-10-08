"""Scope-local report snapshots and six catalog classes, independent of decisions."""
from copy import deepcopy
from collections import OrderedDict
import threading
from .util import identity, require, canonical, read, safe_path, sha, loads, PMRSError
from .relations import premise_closure, edges

SCHEMA='pmrs.report/final-1'
CLASSES=('UNKNOWN_FORMAT','DAMAGED_ACTIVE_ARTIFACT','STALE_CANDIDATE',
         'RECOVERABLE_ACTIVE_CANDIDATE','COMPLETED_CURRENT_REPORT')
_CACHE=OrderedDict()
_CACHE_BYTES=0
_CACHE_LOCK=threading.RLock()
CACHE_LIMIT=4*1024*1024


def _remember(key,value):
    global _CACHE_BYTES
    size=len(canonical(value))
    with _CACHE_LOCK:
        if key in _CACHE:_CACHE_BYTES-=_CACHE.pop(key)[1]
        if size>CACHE_LIMIT:return
        while _CACHE and (len(_CACHE)>=64 or _CACHE_BYTES+size>CACHE_LIMIT):
            _CACHE_BYTES-=_CACHE.popitem(last=False)[1][1]
        _CACHE[key]=(deepcopy(value),size);_CACHE_BYTES+=size


def _cached(key):
    with _CACHE_LOCK:
        row=_CACHE.get(key)
        if row:_CACHE.move_to_end(key)
        return row[0] if row else None


def scope(snapshot, instance_id, mission_id=None, *, plan_ref=None):
    require(instance_id in snapshot.get('instances',{}),'INSTANCE_SELECTOR_REQUIRED','Select an exact report workflow')
    instance=snapshot['instances'][instance_id]
    if instance['kind']=='SURVEY':
        from . import survey
        selected=survey.report_scope(snapshot,instance_id,plan_ref=plan_ref)
        require(mission_id is None or selected['mission_ids']==[mission_id],
                'REPORT_SCOPE_INVALID','Survey plan must bind the selected mission.')
        return selected
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
    if snapshot['instances'][selected_scope['instance_ids'][0]]['kind']=='SURVEY':
        return _freeze_survey(snapshot,selected_scope)
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


def _freeze_survey(snapshot, selected_scope, *, copy_values=True):
    """Survey plans select a dependency closure, independent of runtime activity."""
    from . import survey
    clone=deepcopy if copy_values else lambda value:value
    metadata=survey.freeze_for_report(snapshot,selected_scope,copy_values=copy_values)
    roots=set()
    for key in ('target_refs','candidate_refs','context_refs','argument_refs','example_refs','source_refs','selected_refs','record_refs'):
        roots.update(selected_scope.get(key,[]))
    members=premise_closure(roots,snapshot,include_method_sources=True)
    records={r:clone(snapshot['records'][r]) for r in sorted(members) if r in snapshot['records']}
    sources={r:clone(snapshot['sources'][r]) for r in sorted(members) if r in snapshot['sources']}
    support={sid:clone(v) for sid,v in snapshot.get('supports',{}).items()
             if v.get('statement_ref') in members or v.get('argument_ref') in members}
    qualifications={qid:clone(q) for qid,q in snapshot.get('qualifications',{}).items()
                    if q.get('support_id') in support or q.get('support_ref') in support
                    or qid in {r for v in support.values() for r in v.get('qualification_refs',[])}}
    return {'schema':'pmrs.survey-report-snapshot/1','project_id':snapshot['project_id'],
            'scope':clone(selected_scope),'workflow_kind':'SURVEY',
            'language_policy':clone(snapshot['language_policy']),'records':records,'sources':sources,
            'relations':[clone(e) for e in edges(snapshot) if e['source_ref'] in members and e['target_ref'] in members],
            'supports':support,'qualifications':qualifications,
            'withdrawals':{k:v for k,v in snapshot.get('withdrawals',{}).items() if v.get('support_id') in support},
            'authority':'RESEARCH_EVIDENCE_AND_OPEN_BOUNDARIES_NOT_FORMAL_PROOF',**metadata}


def fingerprint(snapshot, selected_scope):
    if snapshot['instances'][selected_scope['instance_ids'][0]]['kind']=='SURVEY':
        key=('fingerprint',snapshot['project_id'],selected_scope['scope_id'])
        material=_freeze_survey(snapshot,selected_scope,copy_values=False)
        previous=_cached(key)
        if previous and previous['material']==material:return previous['digest']
        digest=identity(material);_remember(key,{'material':material,'digest':digest});return digest
    return identity(freeze(snapshot, selected_scope))


def _file_signature(store,paths):
    result={}
    for path in paths:
        info=safe_path(store.root,path).stat()
        result[path]=[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]
    return result


def check_files(store, entry, *, read_only=False):
    from .resources import hash_file
    key=('files',str(store.root),identity({name:entry.get(name) for name in ('files','blobs','record_refs','snapshot_ref')}))
    previous=_cached(key) if read_only else None
    if previous and _file_signature(store,previous)==previous:return
    paths=set(entry.get('files',{}))|{'blobs/'+digest for digest in entry.get('blobs',[])}
    before=_file_signature(store,sorted(paths))
    for path,digest in entry.get('files',{}).items():
        require(hash_file(safe_path(store.root,path),256*1024**2)==digest,'REPORT_ARTIFACT_CHANGED',path)
    for digest in entry.get('blobs',[]):
        require(hash_file(safe_path(store.root,'blobs/'+digest),256*1024**2)==digest,'BLOB_CHANGED',digest)
    for ref in entry.get('record_refs',[]):
        # The actual record file, not just a snapshot copy, is authoritative.
        record_path='records/'+ref+'.json'
        before.update(_file_signature(store,[record_path]))
        metadata=loads(read(safe_path(store.root,record_path)))
        before.update(_file_signature(store,['blobs/'+metadata['body_sha256']]))
        store.read_record(ref);paths.update((record_path,'blobs/'+metadata['body_sha256']))
    # Original sources are independently checked at use/delivery boundaries.
    # Catalog refreshes reuse this check only while every file stat is identical.
    if entry.get('snapshot_ref'):
        before.update(_file_signature(store,['blobs/'+entry['snapshot_ref']]))
        frozen=loads(store.read_blob(entry['snapshot_ref']));paths.add('blobs/'+entry['snapshot_ref'])
        digests={source['blob_hash'] for source in frozen.get('sources',{}).values()}|set(frozen.get('source_texts',{}).values())
        from .resources import hash_file
        for digest in digests:
            path='blobs/'+digest
            before.update(_file_signature(store,[path]))
            require(hash_file(safe_path(store.root,path),256*1024**2)==digest,'BLOB_CHANGED',digest);paths.add(path)
    after=_file_signature(store,sorted(paths))
    require(before==after,'REPORT_ARTIFACT_CHANGED','A report input changed during integrity verification')
    _remember(key,after)


def classify(store,snapshot,entry, *, read_only=False):
    if entry.get('schema')!=SCHEMA: return 'UNKNOWN_FORMAT'
    required={'report_id','scope','scope_fingerprint','snapshot_ref','profiles','files','blobs','status'}
    if not required<=set(entry): return 'UNKNOWN_FORMAT'
    try: check_files(store,entry,read_only=read_only)
    except (PMRSError,OSError,KeyError,ValueError): return 'DAMAGED_ACTIVE_ARTIFACT'
    if entry['status']=='ABANDONED':return 'REPORT_ABANDONED'
    if entry.get('workflow_kind')=='SURVEY':
        from . import survey
        if not survey.report_current(snapshot,entry['scope']):return 'STALE_CANDIDATE'
    if entry['scope_fingerprint']!=fingerprint(snapshot,entry['scope']):return 'STALE_CANDIDATE'
    from .reports import pair_complete
    return 'COMPLETED_CURRENT_REPORT' if entry['status']=='COMPLETE' and pair_complete(entry) else 'RECOVERABLE_ACTIVE_CANDIDATE'


def catalog(store,snapshot=None,instance_id=None):
    snapshot=store.read_snapshot() if snapshot is None else snapshot
    result=[{'report_id':rid,'classification':classify(store,snapshot,entry,read_only=True),
             'active':rid in snapshot.get('active_reports',{}).values(),
             'instance_ids':entry.get('scope',{}).get('instance_ids',[]),
             'state':entry.get('status'),'selected_profiles':list(entry['profiles']),'missing_checks':missing_checks(entry)}
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
