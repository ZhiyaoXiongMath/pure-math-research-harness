"""Native Survey scope, evidence, readiness and publication selection.

The mathematical bodies remain PMRS records. This module stores only versioned
survey metadata in the same journal, admits model results through native frozen
tasks and captures, and never interprets a completed task as proof authority.
"""
from __future__ import annotations
from copy import deepcopy
from collections import OrderedDict
import threading
from .util import canonical, identity, require, sha, now, PMRSError
from . import contracts as C
from .language import authored_english

SCHEMA='pmrs.survey/1'
MAPS=frozenset({'survey_events','survey_search_plans','survey_retrievals','survey_sources',
               'survey_source_status','survey_readings','survey_coverage','survey_reviews','survey_snapshots','survey_output_plans'})
PROFILES=('minimal','thematic','lecture')
_ACTIVE_RETRIEVALS=set()
_RETRIEVAL_LOCK=threading.Lock()
_DERIVED_CACHE=OrderedDict()
_DERIVED_CACHE_BYTES=0
_DERIVED_CACHE_LOCK=threading.RLock()
DERIVED_CACHE_LIMIT=4*1024*1024


def _reuse(key,value,compute):
    """Cache only bounded metadata; equality checks exact relevant inputs."""
    global _DERIVED_CACHE_BYTES
    with _DERIVED_CACHE_LOCK:
        previous=_DERIVED_CACHE.get(key)
        if previous and previous[0]==value:
            _DERIVED_CACHE.move_to_end(key);return deepcopy(previous[1])
        result=compute()
        encoded=canonical([value,result]);size=len(encoded)
        if previous:_DERIVED_CACHE_BYTES-=_DERIVED_CACHE.pop(key)[2]
        if size<=DERIVED_CACHE_LIMIT:
            while _DERIVED_CACHE and (len(_DERIVED_CACHE)>=32 or _DERIVED_CACHE_BYTES+size>DERIVED_CACHE_LIMIT):
                _DERIVED_CACHE_BYTES-=_DERIVED_CACHE.popitem(last=False)[1][2]
            _DERIVED_CACHE[key]=(deepcopy(value),deepcopy(result),size);_DERIVED_CACHE_BYTES+=size
        return result
SCOPE_FIELDS={'topic','questions','objects','conditions','include','exclude','delivery_goal','entry',
              'selected_refs','source_refs','parent_instance_id','scope_version'}
MAPPING={'questions':'Statement or scoped question metadata','definitions':'Context',
         'results':'Statement','mechanisms':'Argument','examples_and_boundaries':'Example or Statement',
         'source_claims':'SourceEvidence with exact SourceOccurrence binding',
         'mathematical_reviews':'independent input-bound Survey review; no proof qualification',
         'search_reading_coverage':'versioned native Survey metadata','output_selection':'frozen output plan'}
ROLES={'S1':('SEARCH_PLAN','MATERIAL'),'S2':('SOURCE_READ','MATERIAL'),
       'S3':('ORGANIZE','FORMULATE'),'S4':('READINESS_REVIEW','VERIFY')}


def _strings(value,label,*,nonempty=False):
    require(isinstance(value,list) and len(value)<=256 and all(isinstance(v,str) and v.strip() and len(v)<=12000 for v in value)
            and len(value)==len(set(value)) and (bool(value) or not nonempty),'SURVEY_SCOPE_INVALID',label+' requires distinct nonempty text entries')
    return deepcopy(value)


def normalize_scope(snapshot,value):
    require(isinstance(value,dict) and not set(value)-SCOPE_FIELDS,'SURVEY_SCOPE_INVALID','A typed Survey scope is required')
    s=deepcopy(value)
    require(isinstance(s.get('topic'),str) and 0<len(s['topic'].strip())<=2000,'SURVEY_SCOPE_INVALID','State a bounded topic')
    for key in ('questions','objects','conditions','include','exclude','selected_refs','source_refs'):
        s[key]=_strings(s.get(key,[]),key,nonempty=key=='questions')
    s.setdefault('delivery_goal','KNOWLEDGE_ONLY');s.setdefault('entry','NEW_TOPIC');s.setdefault('parent_instance_id',None);s.setdefault('scope_version',1)
    require(s['delivery_goal'] in {'KNOWLEDGE_ONLY','SURVEY_MANUSCRIPT'} and s['entry'] in {'NEW_TOPIC','EXISTING_KNOWLEDGE','UPDATE'}
            and type(s['scope_version']) is int and s['scope_version']==1,'SURVEY_SCOPE_INVALID','Unknown delivery goal, entry or scope version')
    require(all(r in snapshot.get('records',{}) and snapshot['records'][r]['kind']!='Assessment' for r in s['selected_refs']),
            'SURVEY_SCOPE_INVALID','Selection must name exact native mathematical records')
    require(all(r in snapshot.get('sources',{}) for r in s['source_refs']),'SURVEY_SCOPE_INVALID','Selected source is unavailable')
    parent=s['parent_instance_id']
    require(parent is None or snapshot.get('instances',{}).get(parent,{}).get('kind')=='SURVEY','SURVEY_SCOPE_INVALID','Update parent must be an existing Survey instance')
    require(s['entry']!='UPDATE' or parent,'SURVEY_SCOPE_INVALID','An update must preserve its parent instance')
    require(s['entry']=='NEW_TOPIC' or s['selected_refs'],'SURVEY_SCOPE_INVALID','Existing knowledge and update entries require an explicit selection')
    return s


def _instance(snapshot,iid):
    instance=snapshot.get('instances',{}).get(iid)
    require(instance is not None and instance['kind']=='SURVEY','SURVEY_INSTANCE_REQUIRED','Select a native Survey instance')
    return instance


def _owned(snapshot,name,iid):
    return [deepcopy(v) for v in snapshot.get(name,{}).values() if v.get('instance_id')==iid]


def _latest(rows):
    return max(rows,key=lambda r:(r.get('sequence',0),r.get('at',''),r.get('id','')),default=None)


def _scope_basis(snapshot,iid):
    # Entry point, parent, selected records and desired output do not change the
    # mathematics of an otherwise identical scoped review reused by an update.
    scope=_instance(snapshot,iid)['survey_scope']
    return {k:scope[k] for k in ('topic','questions','objects','conditions','include','exclude','scope_version')}


def selection(snapshot,iid,selected_refs=None):
    instance=_instance(snapshot,iid)
    if selected_refs is not None:refs=_strings(list(selected_refs),'selected_refs')
    else:
        coverage=_latest(_owned(snapshot,'survey_coverage',iid))
        refs=deepcopy(coverage['selected_refs'] if coverage else instance['survey_scope']['selected_refs'])
    require(all(r in snapshot.get('records',{}) and snapshot['records'][r]['kind']!='Assessment' for r in refs),
            'SURVEY_SELECTION_INVALID','Select exact native knowledge, not review verdicts')
    return sorted(set(refs))


def dependency_closure(snapshot,iid,selected_refs):
    from .relations import edges
    key=('closure',snapshot.get('project_id'),iid,tuple(sorted(selected_refs)))
    with _DERIVED_CACHE_LOCK:previous=_DERIVED_CACHE.get(key)
    # An edge from any old member can add a new member. Checking those edges,
    # native record data and extraction bindings makes membership reuse exact.
    if previous:
        members=previous[1]
        basis=_closure_basis(snapshot,iid,members,edges(snapshot))
        if previous[0]==basis:return _reuse(key,basis,lambda:members)
    result=_dependency_closure(snapshot,iid,selected_refs)
    return _reuse(key,_closure_basis(snapshot,iid,result,edges(snapshot)),lambda:result)


def _closure_basis(snapshot,iid,members,relations):
    refs=set(members);parent=_instance(snapshot,iid)['survey_scope'].get('parent_instance_id')
    return {'records':{r:snapshot.get('records',{}).get(r) for r in members},
            'relations':[e for e in relations if e['source_ref'] in refs],
            'inferences':{r:snapshot.get('inferences',{}).get(r) for r in members},
            'originals':{r:snapshot.get('survey_sources',{}).get(r,{}).get('read_via_source_ref') for r in members},
            'dependencies':[e for row in snapshot.get('survey_coverage',{}).values() if row.get('instance_id') in {iid,parent}
                            for e in row.get('dependencies',[]) if e['source_ref'] in refs]}


def _dependency_closure(snapshot,iid,selected_refs):
    from .relations import premise_closure
    refs=set(selected_refs)
    relevant=[r for r in snapshot.get('survey_coverage',{}).values() if r.get('instance_id')==iid or
              r.get('instance_id')==_instance(snapshot,iid)['survey_scope'].get('parent_instance_id')]
    dependencies=[edge for row in relevant for edge in row.get('dependencies',[])]
    while True:
        before=set(refs);refs=premise_closure(refs,snapshot)
        for edge in dependencies:
            if edge['source_ref'] in refs and edge['relation'] in {'uses_definition','proof_input','explained_by'}:refs.add(edge['target_ref'])
        for ref in list(refs):
            record=snapshot.get('records',{}).get(ref,{})
            if record.get('kind')=='SourceEvidence':refs.update(record['data']['source_occurrence_refs'])
            original=snapshot.get('survey_sources',{}).get(ref,{}).get('read_via_source_ref')
            if original:refs.add(original)
        if refs==before:return sorted(refs)


def _coverage_for(snapshot,iid,refs):
    basis=_scope_basis(snapshot,iid);by_question={}
    for row in sorted(snapshot.get('survey_coverage',{}).values(),key=lambda r:r.get('sequence',0)):
        if row.get('scope_basis')!=basis:continue
        for item in row.get('coverage',[]):
            consumed=set(item['answer_refs']+item['mechanism_refs']+item['boundary_refs'])
            if consumed & set(refs):by_question[item['question']]=deepcopy(item)
    return list(by_question.values())


def source_details(snapshot,ref):
    source=snapshot.get('sources',{}).get(ref)
    require(source is not None,'INCOMPLETE_CONTEXT','Exact source is missing')
    metadata=snapshot.get('survey_sources',{}).get(ref,{})
    source_status=snapshot.get('survey_source_status',{}).get(ref,{})
    return {'source_ref':ref,'version':metadata.get('version','sha256:'+source['blob_hash']),
            'material_sha256':source['blob_hash'],'original_pdf_sha256':metadata.get('original_pdf_sha256',source['blob_hash'] if source.get('media_type')=='application/pdf' else None),
            'text_sha256':metadata.get('text_sha256',source['blob_hash'] if source.get('media_type','').startswith('text/') else None),
            'text_source_ref':metadata.get('text_source_ref'),'read_via_source_ref':metadata.get('read_via_source_ref'),
            'access_status':metadata.get('access_status','FULL_DOCUMENT_AVAILABLE' if source.get('media_type')=='application/pdf' or source.get('media_type','').startswith('text/') else 'MATERIAL_AVAILABLE'),
            'source_status':metadata.get('source_status','SUPPLIED_MATERIAL'),
            'version_conflict':source_status.get('version_conflict',False),'withdrawn':source_status.get('withdrawn',False),'status_revision':source_status.get('revision'),
            'url':metadata.get('url',source.get('origin',{}).get('uri')),'limitations':metadata.get('limitations',[])}


def scope_material(snapshot,iid,selected_refs,*,source_refs=None):
    closure=dependency_closure(snapshot,iid,selected_refs)
    record_refs=[r for r in closure if r in snapshot.get('records',{})]
    sources=set(r for r in closure if r in snapshot.get('sources',{}))
    if source_refs is not None:sources.update(source_refs)
    source_rows={ref:source_details(snapshot,ref) for ref in sorted(sources)}
    readings={r['id']:r for r in snapshot.get('survey_readings',{}).values() if r['source_ref'] in sources
              and r['version']==source_rows[r['source_ref']]['version'] and r['material_sha256']==source_rows[r['source_ref']]['material_sha256']}
    # Only support changes and revisions within the consumed closure invalidate.
    supports={sid:s for sid,s in snapshot.get('supports',{}).items() if s.get('argument_ref') in record_refs or s.get('statement_ref') in record_refs}
    relevant_objects={oid:o.get('selected_revision') for oid,o in snapshot.get('objects',{}).items() if set(o.get('revisions',[]))&set(record_refs)}
    return {'scope_basis':_scope_basis(snapshot,iid),'selected_refs':sorted(selected_refs),'closure':closure,
            'records':{r:snapshot['records'][r] for r in record_refs},'sources':source_rows,
            'readings':readings,'coverage':_coverage_for(snapshot,iid,record_refs),
            'supports':supports,'object_selections':relevant_objects,
            'withdrawals':{wid:w for wid,w in snapshot.get('withdrawals',{}).items() if w.get('support_id') in supports}}


def scope_fingerprint(snapshot,iid,selected_refs,*,source_refs=None):
    return _material_fingerprint(snapshot,iid,scope_material(snapshot,iid,selected_refs,source_refs=source_refs))


def _material_fingerprint(snapshot,iid,material):
    key=('fingerprint',snapshot.get('project_id'),iid,tuple(material['selected_refs']),tuple(material['sources']))
    return _reuse(key,material,lambda:identity(material,'SURVEY-SCOPE-'))


def readiness(snapshot,iid,selected_refs=None,*,question_ids=None,proof_promises=None):
    refs=selection(snapshot,iid,selected_refs);mat=scope_material(snapshot,iid,refs);errors=[]
    def fail(code,ref,message,stage):errors.append({'code':code,'ref':ref,'message':message,'return_stage':stage})
    if not refs:fail('SURVEY_SELECTION_EMPTY',None,'Select actual mathematical knowledge before readiness review.','S3')
    questions=list(question_ids or _instance(snapshot,iid)['survey_scope']['questions'])
    require(set(questions)<=set(_instance(snapshot,iid)['survey_scope']['questions']),'SURVEY_SELECTION_INVALID','Questions exceed the declared scope')
    for ref,source in mat['sources'].items():
        if source['version_conflict'] or source['withdrawn']:fail('SOURCE_VERSION_CONFLICT',ref,'The controlling source version is conflicted or withdrawn.','S1')
        if source['access_status'] in {'METADATA_ONLY','ABSTRACT_ONLY','FULL_TEXT_UNAVAILABLE'}:fail('SOURCE_NOT_READ',ref,'Metadata or an abstract is not original-text evidence.','S2')
        if source.get('read_via_source_ref') in mat['sources']:continue
        readings=[r for r in mat['readings'].values() if r['source_ref']==ref and r.get('locators')]
        if not readings:fail('SOURCE_NOT_READ',ref,'No accepted input-bound original-text reading covers this source.','S2')
    coverage={r['question']:r for r in mat['coverage']}
    for q in questions:
        c=coverage.get(q)
        if c is None or c['assessment']=='PENDING':fail('SURVEY_COVERAGE_PENDING',q,'The selected question needs explicit answer, mechanism and boundary coverage.','S3');continue
        for gap in c['gaps']:
            if gap['disposition'] not in {'RESOLVED','OUTSIDE_SCOPE','DEFERRED_NONESSENTIAL'}:
                if not gap.get('refs') or set(gap['refs'])&set(mat['closure']):fail('SURVEY_COVERAGE_GAP',q,gap['description'],gap['return_stage'])
    fingerprint=_material_fingerprint(snapshot,iid,mat)
    reviews=[r for r in snapshot.get('survey_reviews',{}).values() if r['scope_fingerprint']==fingerprint
             and set(questions)&set(r['coverage_questions'])]
    latest={}
    for r in sorted(reviews,key=lambda row:row.get('sequence',0)):
        for question in set(questions)&set(r['coverage_questions']):latest[(r['role'],question)]=r
    valid=[]
    for r in {r['id']:r for r in latest.values()}.values():
        task=snapshot.get('tasks',{}).get(r['task_id'],{});accepted=snapshot.get('accepted_requests',{}).get(r['request_id'])
        request=snapshot.get('requests',{}).get(r['request_id'],{})
        actual=snapshot.get('review_executions',{}).get(request.get('execution_id'),{})
        bound=(task.get('independent') and actual.get('task_id')==r['task_id'] and actual.get('independent')
               and actual.get('excluded_verdicts') and actual.get('integrity_valid') and actual.get('capture_ref')==request.get('capture_ref')
               and actual.get('input_manifest_hash')==task.get('input_manifest_hash') and accepted)
        if not bound:continue
        for finding in r['findings']:
            if finding['blocking']:fail(finding['code'],finding['ref'],finding['message'],finding['return_stage'])
        if r['role']=='READINESS_REVIEW' and r['verdict']=='READY' and not r['unchecked_refs'] and not any(f['blocking'] for f in r['findings']):valid.append(r)
    valid_ids={r['id'] for r in valid}
    covered_questions={q for (role,q),r in latest.items() if role=='READINESS_REVIEW' and r['id'] in valid_ids}
    if not set(questions)<=covered_questions:fail('SURVEY_REVIEW_REQUIRED',None,'An independent S4 task must review these exact knowledge versions, original readings and coverage.','S4')
    for promise in proof_promises or []:
        if not any(set(promise.get('required_steps',[]))<=set(r.get('proof_steps',{}).get(promise['record_ref'],[])) for r in valid):
            fail('SURVEY_PROOF_PROMISE_UNCHECKED',promise['record_ref'],'Promised proof steps have not been independently checked.','S4')
    unchecked=[g for c in mat['coverage'] for g in c['gaps'] if g['disposition']=='DEFERRED_NONESSENTIAL']
    unchecked.extend({'question':q,'disposition':'OUTSIDE_SELECTED_QUESTIONS','reason':'This explicitly unselected question remains outside the present readiness decision; no completion is asserted.'}
                     for q in _instance(snapshot,iid)['survey_scope']['questions'] if q not in questions)
    return {'status':'NEEDS_WORK' if errors else 'SYNTHETIC_READY' if snapshot.get('synthetic_test_only') else 'READY',
            'selected_refs':refs,'closure':mat['closure'],'scope_fingerprint':fingerprint,'errors':errors,'unchecked':unchecked,
            'review_refs':[r['id'] for r in valid],'mathematical_state':'NOT_CERTIFIED_BY_SURVEY','proof_qualification_granted':False}


def status(snapshot,iid):
    instance=_instance(snapshot,iid);r=readiness(snapshot,iid)
    result={'instance_id':iid,'scope':deepcopy(instance['survey_scope']),'readiness':r,'mapping':MAPPING,
            **{out:_owned(snapshot,name,iid) for out,name in [('search_plans','survey_search_plans'),('retrievals','survey_retrievals'),('readings','survey_readings'),('coverage','survey_coverage'),('reviews','survey_reviews'),('snapshots','survey_snapshots'),('output_plans','survey_output_plans')]},
            'next_activity':r['errors'][0]['return_stage'] if r['selected_refs'] and r['errors'] else 'S1' if instance['survey_scope']['entry']=='NEW_TOPIC' else 'S4',
            'model_calls':sum(1 for req in snapshot.get('requests',{}).values() if req.get('instance_id')==iid and req.get('execution_state')!='CANCELLED_BEFORE_SEND'),
            'network_requests':sum(row.get('network_requests',0) for row in _owned(snapshot,'survey_retrievals',iid)),
            'simulated_network_requests':sum(row.get('simulated_network_requests',0) for row in _owned(snapshot,'survey_retrievals',iid))}
    for retrieval in result['retrievals']:
        if retrieval['status']=='RUNNING' and retrieval['id'] not in _ACTIVE_RETRIEVALS:
            retrieval['status']='UNKNOWN';retrieval['recovery_note']='Registered retrieval has no completion receipt. Inspect the original operation; do not automatically repeat it.'
    return result


def event(snapshot,iid,kind,data):
    row={'schema':SCHEMA,'event_type':kind,'instance_id':iid,'expected_scope_version':snapshot.get('scope_versions',{}).get(iid,0),
         'payload':deepcopy(data),'actor':'HOST','at':now(),'operation_sequence':snapshot.get('_snapshot_sequence',0)+1}
    row['event_id']=identity(row,'SURVEY-EVENT-');return row


def apply_event(snapshot,e):
    require(e.get('schema')==SCHEMA and e.get('actor')=='HOST','SURVEY_EVENT_INVALID','Typed deterministic host event required')
    iid=e['instance_id'];instance=_instance(snapshot,iid);kind=e['event_type'];data=deepcopy(e['payload'])
    old=snapshot.get('survey_events',{}).get(e['event_id'])
    if old:
        require({k:v for k,v in old.items() if k!='accepted_sequence'}==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Survey event identity conflict');return deepcopy(snapshot)
    require(e['expected_scope_version']==snapshot.get('scope_versions',{}).get(iid,0),'WRITE_CAS_CONFLICT','Survey control scope changed')
    s=deepcopy(snapshot)
    if kind in {'RETRIEVAL_STARTED','RETRIEVAL_FINISHED'}:
        rid=data['id'];prior=s.get('survey_retrievals',{}).get(rid)
        require(data['instance_id']==iid and data['plan_ref'] in s.get('survey_search_plans',{}),'SURVEY_EVENT_INVALID','Retrieval must bind an accepted search plan')
        if kind=='RETRIEVAL_STARTED':require(prior is None and data['status']=='RUNNING','SURVEY_RETRIEVAL_EXISTS','Existing retrieval must be inspected; it is never silently repeated')
        else:require(prior and prior['status']=='RUNNING' and data['status']!='RUNNING','SURVEY_EVENT_INVALID','Finish the original registered retrieval')
        s.setdefault('survey_retrievals',{})[rid]=data
    elif kind=='SOURCE_REGISTERED':
        ref=data['source_ref'];source=s.get('sources',{}).get(ref)
        require(source is not None and source['blob_hash']==data['material_sha256'],'ORIGINAL_BYTES_MISMATCH','Source registration binds original native bytes')
        if data.get('original_pdf_sha256'):require(data['original_pdf_sha256']==source['blob_hash'] and source.get('media_type')=='application/pdf','ORIGINAL_BYTES_MISMATCH','A text derivative cannot be the PDF hash')
        if data.get('text_source_ref'):
            text=s.get('sources',{}).get(data['text_source_ref']);require(text and text['blob_hash']==data.get('text_sha256'),'ORIGINAL_BYTES_MISMATCH','Extracted text must bind separate native material')
        previous=s.get('survey_sources',{}).get(ref)
        require(previous is None or previous==data,'SURVEY_SOURCE_IMMUTABLE','Source versions are immutable; register a new occurrence')
        s.setdefault('survey_sources',{})[ref]=data
        if data.get('text_source_ref'):
            # Native SourceUse accepts only derivatives registered by this
            # checked host extraction event, while original PDF bytes stay intact.
            source['extraction_blob_hashes']=sorted(set(source.get('extraction_blob_hashes',[]))|{data['text_sha256']})
            source['extracted_text_source_refs']=sorted(set(source.get('extracted_text_source_refs',[]))|{data['text_source_ref']})
            s['sources'][ref]=source
    elif kind=='SOURCE_STATUS_CHANGED':
        require(data.get('source_ref') in s.get('sources',{}) and type(data.get('withdrawn')) is bool and type(data.get('version_conflict')) is bool and isinstance(data.get('reason'),str) and data['reason'].strip(),'SURVEY_SOURCE_STATUS_INVALID','Exact source, explicit status and substantive reason required')
        data['revision']=e['event_id'];s.setdefault('survey_source_status',{})[data['source_ref']]=data
    elif kind=='SNAPSHOT_FROZEN':
        expected=_snapshot(snapshot,iid,data['selected_refs'],data['question_ids'])
        require(data==expected,'SURVEY_SNAPSHOT_INVALID','Only an exact native selection may be frozen')
        s.setdefault('survey_snapshots',{})[data['id']]=data
    elif kind=='OUTPUT_PLANNED':
        validate_output_plan(snapshot,iid,data)
        s.setdefault('survey_output_plans',{})[data['id']]=data
    else:require(False,'SURVEY_EVENT_INVALID','Unknown Survey host event')
    s.setdefault('survey_events',{})[e['event_id']]={**deepcopy(e),'accepted_sequence':snapshot.get('_snapshot_sequence',0)+1}
    return s


def _snapshot(snapshot,iid,refs,questions):
    refs=selection(snapshot,iid,refs);mat=scope_material(snapshot,iid,refs)
    row={'schema':SCHEMA,'instance_id':iid,'selected_refs':refs,'question_ids':list(questions),
         'scope_fingerprint':_material_fingerprint(snapshot,iid,mat),'material':mat,
         'readiness':readiness(snapshot,iid,refs,question_ids=questions),'synthetic_test_only':bool(snapshot.get('synthetic_test_only'))}
    row['id']=identity(row,'SURVEY-SNAPSHOT-');return row


def freeze_knowledge(store,iid,selected_refs=None,*,question_ids=None):
    snapshot=store.read_snapshot();refs=selection(snapshot,iid,selected_refs)
    questions=list(question_ids or _instance(snapshot,iid)['survey_scope']['questions'])
    row=_snapshot(snapshot,iid,refs,questions)
    receipt=store.commit_survey(event(snapshot,iid,'SNAPSHOT_FROZEN',row))
    return {**receipt,'snapshot_ref':row['id'],'snapshot':row,'model_calls':0}


def validate_output_plan(snapshot,iid,plan):
    frozen=snapshot.get('survey_snapshots',{}).get(plan.get('snapshot_ref'))
    require(frozen is not None and frozen['instance_id']==iid,'SURVEY_SNAPSHOT_INVALID','Plan must bind this instance\'s exact frozen knowledge')
    require(plan['profile'] in PROFILES and plan['language']=='en','SURVEY_PLAN_INVALID','Select one English minimal, thematic or lecture manuscript')
    require(plan['selected_refs']==frozen['selected_refs'] and plan['scope_fingerprint']==frozen['scope_fingerprint'],
            'SURVEY_PLAN_INVALID','Plan cannot modify its frozen selection')
    for field in ('prerequisites','limitations'):
        for text in plan[field]:authored_english(text,field)
    for field in ('audience','view'):
        require(isinstance(plan.get(field),str) and plan[field].strip(),'SURVEY_PLAN_INVALID','Explicit '+field+' required');authored_english(plan[field],field)
    for item in plan['omissions']:
        require(set(item)=={'record_ref','reason'} and item['record_ref'] in snapshot['records'] and item['record_ref'] not in plan['selected_refs'],'SURVEY_PLAN_INVALID','An omission must name unselected native knowledge')
        authored_english(item['reason'],'omission reason')
    for item in plan['proof_promises']:
        require(set(item)=={'record_ref','treatment','required_steps'} and item['record_ref'] in frozen['material']['closure']
                and item['treatment'] in {'complete','sketch','mechanism','citation','none'},'SURVEY_PLAN_INVALID','Proof promise must bind consumed knowledge')
        _strings(item['required_steps'],'proof steps',nonempty=item['treatment'] in {'complete','sketch','mechanism'})
    current=readiness(snapshot,iid,plan['selected_refs'],question_ids=frozen['question_ids'],proof_promises=plan['proof_promises'])
    require(current['status'] in {'READY','SYNTHETIC_READY'} and current['scope_fingerprint']==frozen['scope_fingerprint'],
            'SURVEY_NOT_READY','Selected evidence and proof promises need a current independent readiness review')
    require(plan['id']==identity({k:v for k,v in plan.items() if k!='id'},'SURVEY-PLAN-'),'SURVEY_PLAN_INVALID','Output plan identity differs')
    if plan.get('comparison_group'):
        for other in snapshot.get('survey_output_plans',{}).values():
            if other.get('comparison_group')==plan['comparison_group']:
                require(other['snapshot_ref']==plan['snapshot_ref'] and other['selected_refs']==plan['selected_refs'],'SURVEY_COMPARISON_MISMATCH','Explicit comparison group requires the same frozen mathematical scope')
    return plan


def create_output_plan(store,iid,snapshot_ref,profile='minimal',*,audience='Readers of the selected mathematical question',
                       view='integrated',prerequisites=None,omissions=None,proof_promises=None,limitations=None,comparison_group=None):
    s=store.read_snapshot();f=s.get('survey_snapshots',{}).get(snapshot_ref)
    require(f is not None and f['instance_id']==iid,'SURVEY_SNAPSHOT_INVALID','Choose this instance\'s frozen snapshot')
    row={'schema':SCHEMA,'instance_id':iid,'snapshot_ref':snapshot_ref,'profile':profile,'language':'en',
         'audience':audience,'view':view,'prerequisites':_strings(prerequisites or [],'prerequisites'),
         'question_ids':f['question_ids'],'unselected_questions':[q for q in _instance(s,iid)['survey_scope']['questions'] if q not in f['question_ids']],
         'selected_refs':f['selected_refs'],'omissions':deepcopy(omissions or []),'proof_promises':deepcopy(proof_promises or []),
         'limitations':_strings(limitations or [],'limitations'),'comparison_group':comparison_group,'scope_fingerprint':f['scope_fingerprint']}
    row['id']=identity(row,'SURVEY-PLAN-');validate_output_plan(s,iid,row)
    receipt=store.commit_survey(event(s,iid,'OUTPUT_PLANNED',row))
    return {**receipt,'plan_ref':row['id'],'plan':row,'model_calls':0}


def report_scope(snapshot,iid,plan_ref=None):
    instance=_instance(snapshot,iid)
    if plan_ref is None:
        plans=_owned(snapshot,'survey_output_plans',iid);require(plans,'SURVEY_PLAN_REQUIRED','Explicitly create an output plan before requesting a manuscript')
        # Dict insertion order is not a reliable clock after journal replay.
        events=[e for e in snapshot.get('survey_events',{}).values() if e['instance_id']==iid and e['event_type']=='OUTPUT_PLANNED']
        chosen=max(events,key=lambda e:e.get('accepted_sequence',0))['payload'] if events else plans[-1];plan_ref=chosen['id']
    p=snapshot.get('survey_output_plans',{}).get(plan_ref);require(p and p['instance_id']==iid,'SURVEY_PLAN_REQUIRED','Choose an output plan belonging to this instance')
    f=snapshot['survey_snapshots'][p['snapshot_ref']];records=f['material']['records'];refs=f['material']['closure']
    scope={'instance_ids':[iid],'mission_ids':[instance['current_mission_id']] if instance['current_mission_id'] else [],
           'target_refs':[r for r in refs if records.get(r,{}).get('kind')=='Statement'],'candidate_refs':[],
           'context_refs':[r for r in refs if records.get(r,{}).get('kind')=='Context'],
           'argument_refs':[r for r in refs if records.get(r,{}).get('kind')=='Argument'],
           'example_refs':[r for r in refs if records.get(r,{}).get('kind')=='Example'],
           'source_refs':sorted(f['material']['sources']),'record_refs':sorted(records),
           'survey_plan_ref':p['id'],'survey_snapshot_ref':f['id'],'workflow_kind':'SURVEY','profiles':[p['profile']],
           'policy_digest':identity({'schema':SCHEMA,'language':'en','selected_profile':p['profile']})}
    scope['scope_id']=identity(scope,'REPORT-SCOPE-');return scope


def freeze_for_report(snapshot,selected_scope,*,copy_values=True):
    p=snapshot.get('survey_output_plans',{}).get(selected_scope.get('survey_plan_ref'))
    require(p is not None,'SURVEY_PLAN_REQUIRED','Exact Survey output plan is missing')
    f=snapshot['survey_snapshots'][p['snapshot_ref']]
    clone=deepcopy if copy_values else lambda value:value
    return {'survey_plan_ref':p['id'],'survey_snapshot_ref':f['id'],'survey_scope_fingerprint':f['scope_fingerprint'],
            'survey_output_plan':clone(p),'survey_evidence':clone(f['material']),'survey_readiness':clone(f['readiness']),
            'source_texts':{ref:row['text_sha256'] for ref,row in f['material']['sources'].items() if row.get('text_sha256')}}


def report_current(snapshot,report_or_scope):
    scope=report_or_scope.get('scope',report_or_scope);p=snapshot.get('survey_output_plans',{}).get(scope.get('survey_plan_ref'))
    if not p:return False
    try:validate_output_plan(snapshot,p['instance_id'],p)
    except (PMRSError,KeyError,TypeError):return False
    return True


def task_context(snapshot,iid,refs,source_refs,stage):
    material=scope_material(snapshot,iid,refs,source_refs=source_refs)
    return {'schema':SCHEMA,'scope':deepcopy(_instance(snapshot,iid)['survey_scope']),
            'selected_refs':sorted(refs),'source_refs':sorted(source_refs),
            'source_details':{ref:source_details(snapshot,ref) for ref in source_refs},
            'readings':deepcopy(material['readings']),'coverage':deepcopy(material['coverage']),
            'scope_fingerprint':scope_fingerprint(snapshot,iid,refs),
            'synthetic_test_only':bool(snapshot.get('synthetic_test_only')),
            'mapping':MAPPING,'stage':stage,'prior_review_verdicts_included':False}


def start_activity(store,iid,stage=None,intent=None,*,max_calls=8,max_workers=1,policy=None,
                   selected_refs=None,source_refs=None,role=None,allow_reports=None,
                   model_overrides=None,max_research_attempts=1,report_first_actions=None):
    from . import obligations as O,workflow_instances as W,changes
    require(isinstance(intent,str) and intent.strip(),'AUTHORIZATION_REQUIRED','State the exact bounded Survey activity')
    require(type(max_calls) is int and max_calls>=0 and type(max_workers) is int and 1<=max_workers<=4,
            'AUTHORIZATION_REQUIRED','Finite model allowance and bounded concurrency required')
    require(type(max_research_attempts) is int and 1<=max_research_attempts<=max(1,max_calls),'AUTHORIZATION_REQUIRED','Bounded responsibility attempts required')
    s=store.read_snapshot();instance=_instance(s,iid);require(instance['status']!='ENDED','AUTHORIZATION_REQUIRED','Create a linked paused Survey to update an ended instance')
    stage=stage or ('S1' if instance['survey_scope']['entry']=='NEW_TOPIC' else 'S4')
    require(stage in {'S1','S2','S3','S4','S5'},'SURVEY_ACTIVITY_INVALID','Choose S1–S4 research or deterministic S5 report authorization')
    refs=selection(s,iid,selected_refs);sources=_strings(list(source_refs if source_refs is not None else instance['survey_scope']['source_refs']),'source_refs')
    sources=sorted(set(sources)|{ref for ref in dependency_closure(s,iid,refs) if ref in s['sources']})
    require(all(ref in s['sources'] for ref in sources),'SURVEY_SELECTION_INVALID','Chosen reading sources are missing')
    if stage in {'S2','S3','S4'}:
        prepare_reading_sources(store,iid,sources);s=store.read_snapshot()
    if stage=='S2':require(bool(sources),'SURVEY_SOURCE_REQUIRED','Select actual original materials for reading')
    if stage=='S4':require(bool(refs),'SURVEY_SELECTION_EMPTY','Select organized knowledge for independent readiness review')
    if stage=='S5':require(report_current(s,report_scope(s,iid)),'SURVEY_NOT_READY','Create a current output plan before authorizing writing')
    selected_role,obligation_type=ROLES.get(stage,('HOST','CONTROL'));role=role or selected_role
    require((stage,role) in {('S1','SEARCH_PLAN'),('S2','SOURCE_READ'),('S3','ORGANIZE'),('S3','RECONSTRUCT'),('S4','READINESS_REVIEW'),('S4','COVERAGE_REVIEW'),('S5','HOST')},
            'STAGE_ROLE_FORBIDDEN','Survey role must have an explicit stage contract')
    if role=='RECONSTRUCT':obligation_type='ESTABLISH'
    if role=='COVERAGE_REVIEW':obligation_type='ACCOUNT'
    intent_ref=store.blob(intent.encode());mid=identity({'instance':iid,'intent':intent_ref,'stage':stage,'ordinal':len(instance['mission_ids'])+1},'MISSION-')
    # The original user intent is separately preserved and fully supplied; it is
    # not confused with a paper or granted evidence for readiness.
    receipt=store.commit(changes.prepare_source_input(s,intent.encode(),title='Survey activity intent',purpose='PHENOMENON',blob_get=store.read_blob))
    intent_source=receipt['source_ref'];s=store.read_snapshot()
    context=task_context(s,iid,refs,sources,stage)
    criterion=('Carry out only '+stage+' / '+role+' for the frozen Survey scope. Preserve exact source versions, hypotheses, quantifiers, material limits and unchecked work. '
               'Return a pmrs.survey-result/1 with a native knowledge_change and the role-specific metadata. '
               'Do not browse from the model task. A source abstract is not original-text reading. '
               'Only claim readiness for the exact consumed knowledge and evidence; no proof certification is granted. '+intent)
    criterion_ref=store.blob(criterion.encode())
    oid=identity({'instance':iid,'stage':stage,'role':role,'intent':intent_ref,'input':context['scope_fingerprint'],'sources':sources},'OB-')
    require(oid not in s['obligations'],'SURVEY_RETRY_REQUIRES_NEW_BASIS','This exact responsibility already exists. Continue its original authorized request or provide changed inputs or a specific new retry question.')
    gid='RETRY-'+oid;consumer={'binding_id':'BINDING-'+oid,'instance_id':iid,'mission_id':mid,'stage_id':stage,'role':role,
         'retry_grant_id':gid,'method_ref':'SURVEY_'+role,'scope':{'target_refs':refs,'survey_scope':instance['survey_scope'],'intent_ref':intent_ref},
         'entry_basis':{'survey_scope_fingerprint':context['scope_fingerprint'],'survey_stage':stage},
         'input_refs':refs,'source_refs':sorted(set(sources+[intent_source])),'threshold':'WORK_DISPOSITION_RECORDED',
         'success_criterion':criterion_ref,'survey_context':context,'ready_since':s.get('_snapshot_sequence',0)}
    if stage=='S3':
        consumer['write_guards']=[{'object_id':oid,'expected_parent':obj['selected_revision']}
            for oid,obj in sorted(s['objects'].items()) if obj.get('selected_revision') in refs]
    if role=='RECONSTRUCT':consumer['scope']['declared_purpose']='SUBSTANTIVE_MATHEMATICAL_RECONSTRUCTION'
    obligation=O.make(oid,obligation_type,refs,criterion_ref,consumer_bindings=[consumer],created_by='HUMAN_SURVEY_SCOPE',effect='SURVEY_SCOPED_WORK')
    mission={'mission_id':mid,'instance_id':iid,'intent_ref':intent_ref,'authorized_scope':{'target_refs':refs,'source_refs':sources,
        'survey_scope':deepcopy(instance['survey_scope']),'survey_stage':stage,'allow_derived_work':False,
        'max_research_attempts':max_research_attempts,'reports':bool(allow_reports if allow_reports is not None else stage=='S5' or instance['survey_scope']['delivery_goal']=='SURVEY_MANUSCRIPT')},
        'budget_grant_id':'BUDGET-'+mid,'obligations':[obligation] if stage!='S5' else [],
        'retry_grants':[{'grant_id':gid,'obligation_id':oid,'method_ref':'SURVEY_'+role,'max_research_attempts':max_research_attempts,
                         'max_responsibility_attempts':max_research_attempts,'reason_ref':intent_ref}] if stage!='S5' else []}
    if report_first_actions is not None:mission['report_first_actions']=W.validate_report_first_actions(report_first_actions)
    policy=deepcopy(policy or {})
    if model_overrides is not None:
        from .model_policy import merge_overrides
        policy['model_overrides']=merge_overrides(policy.get('model_overrides',[]),model_overrides,workflow_kind='SURVEY',capabilities=policy.get('model_capabilities'))
    budget={'budget_grant_id':mission['budget_grant_id'],'max_calls':max_calls,'max_workers':max_workers,'execution_policy':{**policy,'max_workers':max_workers}}
    result=store.commit_control(W.authorize_event(s,iid,mission,budget))
    return {**result,'instance_id':iid,'mission_id':mid,'stage':stage,'role':role,'obligation_id':oid if stage!='S5' else None,
            'model_calls':0,'status':'AUTHORIZED','reports_authorized':mission['authorized_scope']['reports']}


def response_contract(role):
    common={'schema':'pmrs.survey-result/1','knowledge_change':'Exact pmrs.knowledge-change/1 for this frozen task, including every obligation effect',
            'action':{'SEARCH_PLAN':'SEARCH_PLAN','SOURCE_READ':'READING','ORGANIZE':'ORGANIZE','RECONSTRUCT':'ORGANIZE','READINESS_REVIEW':'REVIEW','COVERAGE_REVIEW':'REVIEW'}[role]}
    examples={
      'SEARCH_PLAN':{'queries':[{'provider':'arxiv or crossref','query':'actual provider query','reason':'English selection rationale','max_results':5}], 'stop_reason':'Bounded stopping condition; not a claim of exhaustive literature coverage'},
      'READING':{'readings':[{'source_ref':'exact source ref','version':'version from frozen source_details','locators':[], 'read_scope':'English supporting sections actually read','unread_scope':['Unrelated sections not read'], 'limitations':[], 'claim_refs':[]}]},
      'ORGANIZE':{'selected_refs':['native or local: record refs'],'dependencies':[{'source_ref':'native ref','target_ref':'native ref','relation':'uses_definition|proof_input|explained_by|compares_with'}],
        'coverage':[{'question':'exact question from scope','answer_refs':[],'mechanism_refs':[],'boundary_refs':[], 'assessment':'ADEQUATE|LIMITED|PENDING','rationale':'English coverage and boundary reasoning',
          'gaps':[{'description':'Precise gap','refs':[],'disposition':'OPEN|RESOLVED|OUTSIDE_SCOPE|DEFERRED_NONESSENTIAL','reason':'Reasoned disposition','return_stage':'S1|S2|S3'}]}]},
      'REVIEW':{'selected_refs':['exact frozen selection'],'checked_refs':['all consumed native records actually reviewed'],'unchecked_refs':[],
        'coverage_questions':['exact questions reviewed'],'verdict':'READY|NEEDS_WORK','proof_steps':{},
        'findings':[{'code':'stable_code','ref':None,'message':'English substantive finding','blocking':True,'return_stage':'S1|S2|S3|S4'}],
        'limitations':['English scope limitation']}}
    return {**common,'data':examples[common['action']]}


def validate_result(task,snapshot,payload,records,blob_get):
    """Validate metadata after the wrapped native KCS, using its resolved refs."""
    from .knowledge import validate_locator
    require(payload.get('schema')=='pmrs.survey-result/1','SURVEY_RESULT_INVALID','Native Survey result schema required')
    role=task['role'];expected=response_contract(role)['action'];data=deepcopy(payload['data'])
    require(payload['action']==expected,'SURVEY_RESULT_INVALID','Role cannot author another activity\'s metadata')
    ctx=task.get('survey_context');require(ctx is not None,'SURVEY_RESULT_INVALID','Frozen Survey input context is missing')
    allowed={r['ref'] for r in task['input_manifest'] if r['kind']=='record'}|set(records)
    actual_sources={r['ref'] for r in task['input_manifest'] if r['kind']=='source'}
    iid=task['instance_id'];base={'schema':SCHEMA,'instance_id':iid,'task_id':task['task_id'],'request_id':task['request_id'],
         'sequence':snapshot.get('_snapshot_sequence',0)+1,'synthetic_test_only':bool(snapshot.get('synthetic_test_only'))}
    def known(refs):
        _strings(refs,'exact native references');require(set(refs)<=allowed,'INCOMPLETE_CONTEXT','Survey metadata exceeds frozen or newly admitted records')
    def prose(value,label):
        require(isinstance(value,str) and value.strip(),'SURVEY_RESULT_INVALID',label+' is required');authored_english(value,label)
    if expected=='SEARCH_PLAN':
        C.fields(data,{'queries','stop_reason'},'Survey search plan');require(isinstance(data['queries'],list) and 1<=len(data['queries'])<=4,'SURVEY_QUERY_INVALID','One to four bounded queries required')
        for q in data['queries']:
            C.fields(q,{'provider','query','reason','max_results'},'Survey query')
            require(q['provider'] in {'arxiv','crossref'} and isinstance(q['query'],str) and 0<len(q['query'].strip())<=1500 and type(q['max_results']) is int and 1<=q['max_results']<=10,'SURVEY_QUERY_INVALID','Unsupported or unbounded provider query')
            prose(q['reason'],'query reason')
        prose(data['stop_reason'],'search stop reason');row={**base,**data};row['id']=identity(row,'SURVEY-SEARCH-')
        return {'survey_search_plans':{row['id']:row}}
    if expected=='READING':
        C.fields(data,{'readings'},'Survey reading result');require(isinstance(data['readings'],list) and len(data['readings'])<=64,'SURVEY_READING_INVALID','Bounded readings required')
        rows={}
        for item in data['readings']:
            C.fields(item,{'source_ref','version','locators','read_scope','unread_scope','limitations','claim_refs'},'Survey source reading')
            ref=item['source_ref'];require(ref in ctx['source_refs'] and ref in actual_sources,'INCOMPLETE_CONTEXT','Read only supplied, selected original sources')
            src=ctx['source_details'][ref];require(item['version']==src['version'],'SOURCE_VERSION_CONFLICT','Reading version differs from frozen material')
            require(src['access_status'] not in {'METADATA_ONLY','ABSTRACT_ONLY','FULL_TEXT_UNAVAILABLE'},'SURVEY_READING_INVALID','Metadata cannot be marked as original-text reading')
            require(isinstance(item['locators'],list) and bool(item['locators']),'SURVEY_READING_INVALID','Actual read portions need exact text locators')
            hashes={src['text_sha256']} if src.get('text_sha256') else set()
            for loc in item['locators']:
                require(loc.get('blob_hash') in hashes,'SURVEY_READING_INVALID','Reading locator must bind the original text or registered PDF extraction')
                validate_locator(loc,blob_get)
            prose(item['read_scope'],'actual read scope');_strings(item['unread_scope'],'unread scope');_strings(item['limitations'],'reading limitations');known(item['claim_refs'])
            for text in item['unread_scope']+item['limitations']:authored_english(text,'reading scope and limitations')
            row={**base,**item,'material_sha256':src['material_sha256'],'access_status':'SUPPORTING_SECTIONS_READ'};row['id']=identity(row,'SURVEY-READING-');rows[row['id']]=row
        return {'survey_readings':rows}
    if expected=='ORGANIZE':
        C.fields(data,{'selected_refs','dependencies','coverage'},'Survey organization');known(data['selected_refs'])
        require(isinstance(data['dependencies'],list) and len(data['dependencies'])<=512,'SURVEY_DEPENDENCY_INVALID','Bounded dependency list required')
        for edge in data['dependencies']:
            C.fields(edge,{'source_ref','target_ref','relation'},'Survey dependency');known([edge['source_ref'],edge['target_ref']])
            require(edge['relation'] in {'uses_definition','proof_input','explained_by','compares_with'},'SURVEY_DEPENDENCY_INVALID','Unknown relation')
        from .relations import _acyclic
        graph={}
        for e in data['dependencies']:
            if e['relation']!='compares_with':graph.setdefault(e['source_ref'],set()).add(e['target_ref'])
        _acyclic(graph)
        require(isinstance(data['coverage'],list) and len(data['coverage'])<=256,'SURVEY_COVERAGE_INVALID','Bounded question coverage required')
        seen=set()
        for coverage in data['coverage']:
            C.fields(coverage,{'question','answer_refs','mechanism_refs','boundary_refs','gaps','assessment','rationale'},'Question coverage')
            require(coverage['question'] in ctx['scope']['questions'] and coverage['question'] not in seen,'SURVEY_COVERAGE_INVALID','Coverage must identify a unique declared question');seen.add(coverage['question'])
            for key in ('answer_refs','mechanism_refs','boundary_refs'):known(coverage[key])
            require(coverage['assessment'] in {'PENDING','ADEQUATE','LIMITED'},'SURVEY_COVERAGE_INVALID','Coverage assessment is not mathematical certification')
            prose(coverage['rationale'],'coverage rationale')
            if coverage['assessment']!='PENDING':require(bool(coverage['answer_refs']),'SURVEY_COVERAGE_INVALID','Adequate or limited coverage needs an actual answer record')
            require(isinstance(coverage['gaps'],list) and len(coverage['gaps'])<=256,'SURVEY_COVERAGE_INVALID','Bounded gaps required')
            for gap in coverage['gaps']:
                C.fields(gap,{'description','refs','disposition','reason','return_stage'},'Coverage gap');known(gap['refs'])
                require(gap['disposition'] in {'OPEN','RESOLVED','OUTSIDE_SCOPE','DEFERRED_NONESSENTIAL'} and gap['return_stage'] in {'S1','S2','S3'},'SURVEY_COVERAGE_INVALID','Each gap needs its actual return activity')
                prose(gap['description'],'gap description');prose(gap['reason'],'gap disposition reason')
        row={**base,**data,'scope_basis':_scope_basis(snapshot,iid)};row['id']=identity(row,'SURVEY-COVERAGE-');return {'survey_coverage':{row['id']:row}}
    C.fields(data,{'selected_refs','checked_refs','unchecked_refs','coverage_questions','verdict','proof_steps','findings','limitations'},'Survey readiness review')
    require(task.get('independent') is True and task.get('excluded_verdicts') is True,'INDEPENDENT_REVIEW_REQUIRED','Readiness requires its own actual isolated review task')
    require(data['selected_refs']==ctx['selected_refs'],'SURVEY_REVIEW_INVALID','Review must bind the exact frozen selection')
    known(data['checked_refs']);known(data['unchecked_refs']);require(not set(data['checked_refs'])&set(data['unchecked_refs']),'SURVEY_REVIEW_INVALID','Checked and unchecked scope overlap')
    frozen_records={r['ref'] for r in task['input_manifest'] if r['kind']=='record'}
    require(set(data['checked_refs'])|set(data['unchecked_refs'])==frozen_records,'SURVEY_REVIEW_INVALID','Account for every actual consumed record')
    _strings(data['coverage_questions'],'reviewed questions');require(set(data['coverage_questions'])<=set(ctx['scope']['questions']),'SURVEY_REVIEW_INVALID','Review questions exceed the scope')
    require(data['verdict'] in {'READY','NEEDS_WORK'} and isinstance(data['proof_steps'],dict),'SURVEY_REVIEW_INVALID','A bounded readiness verdict and checked proof steps are required')
    for ref,steps in data['proof_steps'].items():
        known([ref]);_strings(steps,'checked proof steps')
        record=snapshot.get('records',{}).get(ref,{})
        require(ref in data['checked_refs'] and record.get('kind')=='Argument' and set(steps)<={step['step_id'] for step in record['data']['steps']},'SURVEY_REVIEW_INVALID','Checked proof steps must identify actual steps of a consumed native Argument')
    require(isinstance(data['findings'],list) and len(data['findings'])<=256,'SURVEY_REVIEW_INVALID','Bounded findings required')
    for finding in data['findings']:
        C.fields(finding,{'code','ref','message','blocking','return_stage'},'Readiness finding')
        require(isinstance(finding['code'],str) and finding['code'] and type(finding['blocking']) is bool and finding['return_stage'] in {'S1','S2','S3','S4'},'SURVEY_REVIEW_INVALID','Finding needs a code, impact and precise return activity')
        if finding['ref'] is not None:require(finding['ref'] in allowed|actual_sources,'SURVEY_REVIEW_INVALID','Finding refers outside frozen scope')
        prose(finding['message'],'readiness finding')
    _strings(data['limitations'],'review limitations')
    for text in data['limitations']:authored_english(text,'review limitations')
    if data['verdict']=='READY':require(not data['unchecked_refs'] and not any(f['blocking'] for f in data['findings']),'SURVEY_REVIEW_INVALID','Unreviewed essential work cannot be ready')
    # Admission fails on a relevant evidence change, but unrelated task counters,
    # additions, UI preferences and independent branches do not affect the guard.
    require(ctx['scope_fingerprint']==scope_fingerprint(snapshot,iid,ctx['selected_refs']),'STALE_READ','Consumed Survey knowledge or evidence changed during review')
    row={**base,**data,'scope_fingerprint':ctx['scope_fingerprint'],'role':role};row['id']=identity(row,'SURVEY-REVIEW-')
    return {'survey_reviews':{row['id']:row}}


def mark_source(store,iid,source_ref,*,withdrawn=False,version_conflict=False,reason):
    s=store.read_snapshot();_instance(s,iid)
    data={'source_ref':source_ref,'withdrawn':withdrawn,'version_conflict':version_conflict,'reason':reason,'at':now()}
    receipt=store.commit_survey(event(s,iid,'SOURCE_STATUS_CHANGED',data))
    return {**receipt,'source_ref':source_ref,'model_calls':0}


def _register_material(store,iid,raw,title,media_type,details,*,source_id):
    from .changes import prepare_material_input
    result=store.commit(prepare_material_input(store.read_snapshot(),raw,title,media_type,source_id=source_id,blob_get=store.read_blob))
    row={**details,'source_ref':result['source_ref'],'material_sha256':sha(raw),'instance_id':iid}
    store.commit_survey(event(store.read_snapshot(),iid,'SOURCE_REGISTERED',row))
    return result['source_ref']


def _retrieve(store,iid,plan_ref,*,provider=None,selected_candidate_ids=None,max_downloads=2,retrieval_key=None):
    """Execute one accepted S1 plan; persist intent before any network access.

    A process lost during retrieval leaves a conservative UNKNOWN projection.
    Its original registration is recoverable and never automatically reissued.
    """
    from . import survey_retrieval as R
    s=store.read_snapshot();_instance(s,iid);plan=s.get('survey_search_plans',{}).get(plan_ref)
    require(plan and plan['instance_id']==iid and plan['request_id'] in s.get('accepted_requests',{}),'SURVEY_SEARCH_PLAN_REQUIRED','Select an accepted S1 query plan')
    require(type(max_downloads) is int and 0<=max_downloads<=3,'SURVEY_RETRIEVAL_LIMIT','At most three explicit downloads per retrieval')
    if selected_candidate_ids is not None:_strings(selected_candidate_ids,'selected candidate IDs')
    if provider is not None:require(s.get('synthetic_test_only') and isinstance(provider,R.MockProvider),'SYNTHETIC_ISOLATION','Injected providers are restricted to synthetic test projects')
    key=retrieval_key or plan_ref
    rid=identity({'instance':iid,'plan':plan_ref,'key':key},'SURVEY-RETRIEVAL-')
    existing=s.get('survey_retrievals',{}).get(rid)
    if existing:
        return {'outcome':'EXACT_DUPLICATE','retrieval_ref':rid,'retrieval':{**deepcopy(existing),'status':'UNKNOWN' if existing['status']=='RUNNING' else existing['status']},'model_calls':0}
    simulated=isinstance(provider,R.MockProvider)
    request_counter='simulated_network_requests' if simulated else 'network_requests'
    reservations=(len(plan['queries'])+max_downloads)*(R.MAX_RETRIES+1)
    row={'id':rid,'instance_id':iid,'plan_ref':plan_ref,'status':'RUNNING','started_at':now(),'finished_at':None,
         'queries':[],'candidates':[],'stop_reason':plan['stop_reason'],'network_requests':0,
         'simulated_network_requests':0,'network_request_reservations':0 if simulated else reservations,
         'simulated_network_request_reservations':reservations if simulated else 0,
         'max_downloads':max_downloads,'max_total_download_bytes':32*1024*1024,'downloaded_bytes':0,
         'synthetic_test_only':bool(s.get('synthetic_test_only'))}
    store.commit_survey(event(s,iid,'RETRIEVAL_STARTED',row))
    used=0;failed=False
    for qi,query in enumerate(plan['queries']):
        impl=provider or R.provider(query['provider']);result=impl.search(query['query'],query['max_results'])
        raw=result.get('raw');response_hash=store.blob(raw) if isinstance(raw,bytes) else None
        record={'provider':impl.name,'query':query['query'],'reason':query['reason'],'at':now(),'status':result['status'],
                'url':result.get('url'),'response_sha256':response_hash,'attempts':result.get('attempts',[]),'failure_reason':result.get('reason')}
        row['queries'].append(record);row[request_counter]+=len(record['attempts'])
        failed|=result['status']!='SUCCESS'
        for ci,candidate in enumerate(result.get('candidates',[])[:query['max_results']]):
            require(isinstance(candidate,dict) and isinstance(candidate.get('candidate_id'),str),'SURVEY_PROVIDER_INVALID','Provider candidate identity is missing')
            chosen=(selected_candidate_ids is None or candidate['candidate_id'] in selected_candidate_ids) and used<max_downloads and row['downloaded_bytes']+R.MAX_BYTES<=row['max_total_download_bytes']
            candidate=deepcopy(candidate);candidate['query_index']=qi;candidate['selected']=chosen
            candidate['selection_reason']=query['reason'] if chosen else ('Outside the explicitly selected candidates.' if selected_candidate_ids is not None and candidate['candidate_id'] not in selected_candidate_ids else 'Not acquired within the declared download and total-byte bound; metadata remains a discovery candidate.')
            details={'version':candidate.get('version') or 'metadata:'+sha(canonical(candidate)),
                'url':candidate.get('url'),'source_status':candidate.get('publication_status','UNVERIFIED'),
                'original_pdf_sha256':None,'text_sha256':None,'text_source_ref':None,'access_status':'METADATA_ONLY',
                'limitations':['Bibliographic metadata and abstracts do not establish full-text reading.']}
            prefix=identity({'retrieval':rid,'query':qi,'candidate':ci},'SO-')
            metadata_raw=canonical(candidate)
            metadata_ref=_register_material(store,iid,metadata_raw,candidate.get('title') or candidate['candidate_id'],'application/json',details,source_id=prefix+'-metadata')
            candidate['metadata_source_ref']=metadata_ref;candidate['source_ref']=metadata_ref;candidate['access_status']='METADATA_ONLY'
            if chosen:
                used+=1;acquired=impl.acquire(candidate);row[request_counter]+=len(acquired.get('attempts',[]))
                candidate['acquisition_status']=acquired['status'];candidate['acquisition_attempts']=acquired.get('attempts',[])
                candidate['acquisition_limitation']=acquired.get('reason')
                original=acquired.get('raw')
                if acquired['status']=='SUCCESS' and isinstance(original,bytes):
                    require(len(original)<=R.MAX_BYTES and row['downloaded_bytes']+len(original)<=row['max_total_download_bytes'],'SURVEY_SIZE_LIMIT','Provider exceeded acquisition limits')
                    is_pdf=original.startswith(b'%PDF-');extraction=acquired.get('extraction') or (R.extract_pdf(original) if is_pdf else {})
                    require(is_pdf or provider is not None,'SURVEY_MEDIA_REJECTED','Only validated PDF originals are acquired from real providers')
                    text=extraction.get('text');text_ref=None
                    if text:
                        text_ref=_register_material(store,iid,text,'Extracted text: '+candidate.get('title',candidate['candidate_id']),'text/plain',
                            {**details,'access_status':'EXTRACTED_TEXT_AVAILABLE','text_sha256':sha(text),'read_via_source_ref':prefix+'-original','limitations':['Text derivative of the separately preserved original PDF.']},source_id=prefix+'-text')
                    original_details={**details,'access_status':'FULL_DOCUMENT_AVAILABLE','original_pdf_sha256':sha(original) if is_pdf else None,
                        'text_source_ref':text_ref,'text_sha256':sha(text) if text else sha(original) if not is_pdf else None,
                        'limitations':[extraction.get('limitation','Original PDF acquired; textual extraction is unavailable or incomplete.')] if is_pdf else ['Explicit synthetic teaching material.']}
                    original_ref=_register_material(store,iid,original,candidate.get('title',candidate['candidate_id']),
                        'application/pdf' if is_pdf else 'text/plain',original_details,source_id=prefix+'-original')
                    candidate.update(source_ref=original_ref,text_source_ref=text_ref,access_status='FULL_DOCUMENT_AVAILABLE',original_sha256=sha(original))
                    row['downloaded_bytes']+=len(original)
                elif acquired['status'] not in {'FULL_TEXT_UNAVAILABLE'}:failed=True
            row['candidates'].append(candidate)
    row.update(status='PARTIAL' if failed else 'COMPLETE',finished_at=now())
    receipt=store.commit_survey(event(store.read_snapshot(),iid,'RETRIEVAL_FINISHED',row))
    return {**receipt,'retrieval_ref':rid,'retrieval':row,'model_calls':0}


TEACHING_TEXT=('SYNTHETIC TEACHING MATERIAL; no real literature citation.\n'
    'For a complex number q and an integer n >= 1, define G_n(q) = sum_{k=0}^{n-1} q^k.\n'
    'If q != 1 then G_n(q) = (1-q^n)/(1-q); if q = 1 then G_n(1) = n.\n'
    'Multiply the finite sum by q and subtract: (1-q)G_n(q) = 1-q^n.\n'
    'Division is permitted only when q != 1. At q = 1, count the n unit summands.\n')


def demo_scope():
    return {'topic':'Finite geometric sums','questions':['What is the finite geometric sum, including the boundary q = 1?'],
            'objects':['A complex number q and an integer n >= 1'],'conditions':['Only finite sums are considered.'],
            'include':['Definition, closed formula, q = 1, and subtraction proof'],
            'exclude':['Infinite series and convergence'],'delivery_goal':'KNOWLEDGE_ONLY','entry':'NEW_TOPIC',
            'selected_refs':[],'source_refs':[]}


def demo_response(task,snapshot):
    """Synthetic-only software fixture, never a mathematical review credential."""
    from .knowledge import locator
    require(snapshot.get('synthetic_test_only') is True,'SYNTHETIC_ISOLATION','Survey fixtures are only for isolated software tests')
    role=task['role'];ctx=task['survey_context'];ops=[];evidence=[]
    if role=='SEARCH_PLAN':
        action='SEARCH_PLAN';data={'queries':[{'provider':'crossref','query':'finite geometric series','reason':'Find candidates within the declared finite-sum scope.','max_results':2}],
            'stop_reason':'Stop after the bounded query; record missing original text and do not claim exhaustive coverage.'}
    elif role=='SOURCE_READ':
        action='READING';data={'readings':[]}
        for ref in ctx['source_refs']:
            src=ctx['source_details'][ref]
            if src['text_sha256']!=sha(TEACHING_TEXT.encode()):continue
            data['readings'].append({'source_ref':ref,'version':src['version'],'locators':[locator(TEACHING_TEXT)],
                'read_scope':'All explicitly synthetic teaching paragraphs about the finite sum and q = 1.',
                'unread_scope':[],'limitations':['Synthetic fixture: no actual model reading or external literature review.'],'claim_refs':[]})
    elif role in {'ORGANIZE','RECONSTRUCT'}:
        action='ORGANIZE'
        source=next((ref for ref,row in ctx['source_details'].items() if row['text_sha256']==sha(TEACHING_TEXT.encode())),None)
        require(source is not None,'SYNTHETIC_FIXTURE_SCOPE','The geometric fixture requires its explicitly labeled teaching material')
        context='Let q be a complex number and n an integer with n >= 1. Define G_n(q) as the sum of q^k over integers k from 0 through n-1. Only finite sums are considered.'
        formula='For every complex number q != 1 and every integer n >= 1, G_n(q) = (1-q^n)/(1-q).'
        boundary='For every integer n >= 1, G_n(1) = n.'
        argument='Multiplying the finite sum by q shifts its powers from 0 through n-1 to 1 through n. Subtraction cancels the intermediate terms, giving (1-q)G_n(q) = 1-q^n. For q != 1 division yields the displayed formula. For q = 1 the n summands are all one. Synthetic fixture only; no real mathematical review was performed.'
        ops=[{'op':'NEW','local_key':'context','kind':'Context','context_refs':[],'body':context,
              'data':{'definitions':[{'key':'finite_sum','locator':locator(context)}],'objects':[],'assumptions':[],'quantifiers':[],'conventions':[],'parent_context_refs':[]}}]
        for key,body in [('formula',formula),('boundary',boundary)]:
            ops.append({'op':'NEW','local_key':key,'kind':'Statement','context_refs':['local:context'],'body':body,
                'data':{'statement_locator':locator(body),'scope_context_refs':['local:context'],'hypothesis_locators':[locator(body)],'conclusion_locators':[locator(body)],
                        'quantifier_locators':[locator(body)],'form':'PROPOSITION','representation':'AUTHORED','source_binding':None}})
        ops.append({'op':'NEW','local_key':'mechanism','kind':'Argument','context_refs':['local:context'],'body':argument,
            'data':{'conclusion_ref':'local:formula','premise_bindings':[],'steps':[{'step_id':'multiply_subtract','locator':locator(argument),'premise_refs':[]}],
                'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'DERIVATION','mode_payload':{}}})
        use={'source_ref':source,'locators':[locator(TEACHING_TEXT)],'usage_mode':'DECLARED_EXCERPT','trust_boundary':'SOURCE_CONTENT_NOT_EXECUTABLE'}
        # Match the native SourceUse trust-boundary enum rather than minting a
        # special testing loophole in admission.
        use['trust_boundary']='UNTRUSTED_SOURCE_CONTENT'
        ops.append({'op':'LINK','type':'USED_SOURCE','source_ref':'local:mechanism','target_ref':source,'scope_context_refs':['local:context'],
                    'evidence_bindings':[use],'assertion_state':'PROPOSED'})
        evidence=['local:context','local:formula','local:boundary','local:mechanism']
        data={'selected_refs':evidence,'dependencies':[], 'coverage':[{'question':ctx['scope']['questions'][0],'answer_refs':['local:formula'],
            'mechanism_refs':['local:mechanism'],'boundary_refs':['local:boundary'],'gaps':[],'assessment':'ADEQUATE',
            'rationale':'The synthetic finite-sum example includes the full hypotheses, subtraction mechanism and q = 1 boundary; infinite series are outside scope.'}]}
    else:
        action='REVIEW';refs=sorted(r['ref'] for r in task['input_manifest'] if r['kind']=='record')
        data={'selected_refs':ctx['selected_refs'],'checked_refs':refs,'unchecked_refs':[],
            'coverage_questions':ctx['scope']['questions'],'verdict':'READY','proof_steps':{},'findings':[],
            'limitations':['Synthetic software fixture only: no real independent mathematical review occurred and no proof qualification is granted.']}
    effects=[{'binding_id':b['binding_id'],'expected_definition_revision':b['expected_definition_revision'],'work_disposition':'ADDRESSED',
        'resolution_proposal':'CANDIDATE_RESPONSE','evidence_refs':evidence,'remaining_conditions':['Synthetic fixture only; actual research remains unverified.'],'blocker_proposals':[]} for b in task['obligation_bindings']]
    kcs={'schema':C.CHANGE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'base_knowledge_commit':task['knowledge_commit'],
         'read_set_digest':C.digest(task['read_set']),'query_guard_digest':C.digest(task['query_guards']),'write_guard_digest':C.digest(task['write_guards']),
         'operations':ops,'obligation_effects':effects,'new_obligation_proposals':[],'work_outcome':'RESULT',
         'attempt_account':'Deterministic synthetic Survey fixture through the ordinary freeze, capture and admission path. No paid model or real mathematical review occurred.',
         'claimed_change':'Synthetic Survey software evidence; no mathematical certification.','semantic_novelty':'NOT_AUTOMATICALLY_CERTIFIED'}
    return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'payload_kind':'SURVEY_RESULT',
                      'payload':{'schema':'pmrs.survey-result/1','knowledge_change':kcs,'action':action,'data':data}})


def handoff_scope(snapshot,iid,target_ref):
    _instance(snapshot,iid)
    require(snapshot.get('records',{}).get(target_ref,{}).get('kind')=='Statement','TARGET_REQUIRED','Choose an exact native statement for handoff')
    from .views import scope_refs
    require(target_ref in scope_refs(snapshot,iid),'HANDOFF_INVALID','Selected statement must belong to this Survey scope')
    refs=dependency_closure(snapshot,iid,[target_ref])
    for record_ref in selection(snapshot,iid):
        record=snapshot['records'][record_ref]
        if record['kind']=='Argument' and record['data']['conclusion_ref']==target_ref:refs=sorted(set(refs)|set(dependency_closure(snapshot,iid,[record_ref])))
    return {'candidate_refs':[target_ref],'target_refs':[target_ref],
            'context_refs':[r for r in refs if snapshot.get('records',{}).get(r,{}).get('kind')=='Context'],
            'argument_refs':[r for r in refs if snapshot.get('records',{}).get(r,{}).get('kind')=='Argument'],
            'example_refs':[r for r in refs if snapshot.get('records',{}).get(r,{}).get('kind')=='Example'],
            'source_refs':[r for r in refs if r in snapshot.get('sources',{})]}


def retrieve(store,iid,plan_ref,*,provider=None,selected_candidate_ids=None,max_downloads=2,retrieval_key=None):
    rid=identity({'instance':iid,'plan':plan_ref,'key':retrieval_key or plan_ref},'SURVEY-RETRIEVAL-')
    with _RETRIEVAL_LOCK:
        existing=store.read_snapshot().get('survey_retrievals',{}).get(rid)
        if existing:
            row=deepcopy(existing)
            if row['status']=='RUNNING' and rid not in _ACTIVE_RETRIEVALS:row['status']='UNKNOWN'
            return {'outcome':'EXACT_DUPLICATE','retrieval_ref':rid,'retrieval':row,'model_calls':0}
        require(rid not in _ACTIVE_RETRIEVALS,'SURVEY_RETRIEVAL_ACTIVE','The same retrieval registration is being prepared')
        _ACTIVE_RETRIEVALS.add(rid)
    try:
        return _retrieve(store,iid,plan_ref,provider=provider,selected_candidate_ids=selected_candidate_ids,max_downloads=max_downloads,retrieval_key=retrieval_key)
    finally:
        with _RETRIEVAL_LOCK:_ACTIVE_RETRIEVALS.discard(rid)


def prepare_reading_sources(store,iid,source_refs):
    """Extract selected uploaded PDFs deterministically, preserving original bytes."""
    from .survey_retrieval import extract_pdf,MAX_BYTES
    for ref in source_refs:
        s=store.read_snapshot();source=s.get('sources',{}).get(ref)
        require(source is not None,'INCOMPLETE_CONTEXT','Selected source is unavailable')
        if source.get('media_type')!='application/pdf' or ref in s.get('survey_sources',{}):continue
        require(source.get('bytes',0)<=MAX_BYTES,'SURVEY_SIZE_LIMIT','Selected PDF exceeds the bounded extraction size; supply a relevant original excerpt')
        original=store.read_blob(source['blob_hash']);extracted=extract_pdf(original);text=extracted.get('text');text_ref=None
        details={'version':'sha256:'+source['blob_hash'],'url':source.get('origin',{}).get('uri'),'source_status':'SUPPLIED_MATERIAL',
                 'original_pdf_sha256':source['blob_hash'],'text_sha256':None,'text_source_ref':None,'access_status':'FULL_DOCUMENT_AVAILABLE',
                 'limitations':[extracted.get('limitation') or 'PDF text extraction unavailable: '+str(extracted.get('reason','unknown'))]}
        if text:
            text_ref=_register_material(store,iid,text,'Extracted text: '+source.get('original_filename','Supplied PDF'),'text/plain',
                {**details,'original_pdf_sha256':None,'access_status':'EXTRACTED_TEXT_AVAILABLE','text_sha256':sha(text),'read_via_source_ref':ref,
                 'limitations':['Extracted text is a derivative of the separately preserved supplied PDF.']},
                 source_id=identity({'source':ref,'text_sha256':sha(text)},'SO-'))
        details.update(source_ref=ref,material_sha256=source['blob_hash'],instance_id=iid,text_sha256=sha(text) if text else None,text_source_ref=text_ref)
        store.commit_survey(event(store.read_snapshot(),iid,'SOURCE_REGISTERED',details))
    return {'source_refs':list(source_refs),'model_calls':0}
