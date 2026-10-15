"""The unique scientific admission path, shared by preflight and recovery.

All functions are pure. Store supplies exact immutable bytes and publishes the
result under its one writer lock only after revalidation against the live view.
"""
from __future__ import annotations
from copy import deepcopy
import secrets
from . import contracts as C, knowledge, relations, assurance
from .util import require, sha, canonical
from .language import authored_english

SCIENCE_MAPS=('records','objects','sources','production_events','inferences','supports','qualifications','withdrawals','result_families')
EFFECT_FIELDS=set('binding_id expected_definition_revision work_disposition resolution_proposal evidence_refs remaining_conditions blocker_proposals'.split())
PROPOSAL_FIELDS=set('local_key type reason_code target_refs criterion_body scope_context_refs dependency_bindings consumer_binding_proposals effect_on_goal reason_refs'.split())


def _query_members(snapshot,guard):
    scope=guard['scope_binding'];scope=scope if isinstance(scope,dict) else {'instance_id':scope}
    iid=scope.get('instance_id');mid=scope.get('mission_id');kind=guard['query_kind']
    if kind=='TARGET_SET':return sorted({i['target_ref'] for key,i in snapshot.get('instances',{}).items() if i.get('target_ref') and (iid is None or key==iid)})
    if kind=='CANDIDATE_FRONTIER':return sorted({c['statement_ref'] for c in snapshot.get('candidates',{}).values() if (iid is None or c.get('instance_id')==iid) and (mid is None or c.get('mission_id')==mid)})
    if kind=='OPEN_OBLIGATION_SET':
        return sorted(key+'@'+str(o['definition']['definition_revision']) for key,o in snapshot.get('obligations',{}).items() if o['projection']['resolution']!='SATISFIED_FOR_CONSUMER' and any((iid is None or c.get('instance_id')==iid) and (mid is None or c.get('mission_id')==mid) for c in o['definition']['consumer_bindings']))
    if kind=='REQUIRED_REVIEW_SET':
        return sorted(key+'@'+str(o['definition']['definition_revision']) for key,o in snapshot.get('obligations',{}).items() if o['definition']['type']=='VERIFY' and any((iid is None or c.get('instance_id')==iid) and (mid is None or c.get('mission_id')==mid) for c in o['definition']['consumer_bindings']))
    raise C.PMRSError('RESPONSE_SCHEMA_INVALID','Unsupported query guard')


def live_check(task,snapshot,blob_get=None):
    require(task.get('schema')==C.TASK_SCHEMA,'RESPONSE_SCHEMA_INVALID','Final task required')
    if task.get('report_context'):
        report=snapshot.get('reports',{}).get(task['report_context']['report_id'],{})
        require(report.get('status')!='ABANDONED','REPORT_ABANDONED','The report was abandoned before this task could proceed.')
    for binding in task.get('read_set',[]):
        C.fields(binding,{'record_ref','body_hash','selection_binding','required_support_refs','scope','qualification_guard'},'ReadBinding')
        ref=binding['record_ref'];record=snapshot.get('records',{}).get(ref)
        require(record is not None and record['body_sha256']==binding['body_hash'],'STALE_READ',ref)
        if blob_get:require(sha(blob_get(binding['body_hash']))==binding['body_hash'],'ORIGINAL_BYTES_MISMATCH',ref)
        require(C.scientific_identity(record)==ref,'ORIGINAL_BYTES_MISMATCH','Record identity changed')
        sel=binding['selection_binding'];C.fields(sel,{'mode','object_id','expected_revision'},'selection binding')
        C.enum(sel['mode'],('PINNED','CURRENT'),'selection mode')
        require(sel['expected_revision']==ref,'STALE_READ','Read binding revision differs')
        if sel['mode']=='CURRENT':require(snapshot.get('objects',{}).get(sel['object_id'],{}).get('selected_revision')==ref,'STALE_READ','Current selection changed')
        for sid in binding['required_support_refs']:
            current=snapshot.get('supports',{}).get(sid)
            require(current is not None,'STALE_READ','Support missing')
            guard=binding['qualification_guard']
            if isinstance(guard,dict) and sid in guard:require(C.digest(current)==guard[sid],'STALE_READ','Support qualification changed')
            require(sid not in relations.affected_supports(snapshot,{w['support_id'] for w in snapshot.get('withdrawals',{}).values() if w.get('active',True)}),'STALE_READ','Selected support withdrawn or needs recheck')
    for item in task.get('input_manifest',[]):
        if item.get('kind')=='source':
            src=snapshot.get('sources',{}).get(item['ref']);require(src and src.get('blob_hash',src.get('sha256'))==item['sha256'],'STALE_READ','Source occurrence changed')
            if blob_get:require(sha(blob_get(item['sha256']))==item['sha256'],'ORIGINAL_BYTES_MISMATCH','Required source bytes changed')
            coverage=item.get('body_coverage') or task.get('source_excerpts',{}).get(item['ref'])
            if coverage:require(C.digest(src)==coverage['source_revision'],'STALE_READ','The exact excerpt source revision changed')
            require(not src.get('withdrawn') and not src.get('version_conflict'),'STALE_READ','Selected original source was withdrawn or has conflicting versions')
    for guard in task.get('query_guards',[]):
        C.fields(guard,{'query_kind','scope_binding','member_refs','member_digest'},'QueryGuard')
        members=_query_members(snapshot,guard)
        require(members==sorted(guard['member_refs']) and C.digest(members)==guard['member_digest'],'STALE_QUERY','Required collection membership changed')
    for guard in task.get('write_guards',[]):
        C.fields(guard,{'object_id','expected_parent'},'WriteGuard')
        require(snapshot.get('objects',{}).get(guard['object_id'],{}).get('selected_revision')==guard['expected_parent'],'WRITE_CAS_CONFLICT',guard['object_id'])
    for binding in task.get('obligation_bindings',[]):
        o=snapshot.get('obligations',{}).get(binding['obligation_id'])
        require(o and o['definition']['definition_revision']==binding['expected_definition_revision'],'STALE_OBLIGATION_DEFINITION',binding['obligation_id'])
    report_authorized=False
    if task.get('report_context'):
        from .reports import dispatch_authorized
        report_authorized=dispatch_authorized(snapshot,task)
    request=snapshot.get('requests',{}).get(task.get('request_id'),{})
    if task.get('instance_id'):
        instance=snapshot.get('instances',{}).get(task['instance_id'])
        # A paused instance may receive an already sealed stage capture. This
        # does not admit a new request, invoke tools, or apply a MAIN strategy.
        paused_stage_capture=(instance is not None and instance.get('status')=='PAUSED'
            and task.get('actor_kind')!='MAIN' and request.get('execution_state')=='CAPTURED'
            and bool(request.get('capture_ref')) and request.get('task_id')==task.get('task_id')
            and request.get('instance_id')==task['instance_id'] and not request.get('fenced'))
        require(instance is not None and (instance.get('status')=='ACTIVE' or report_authorized or paused_stage_capture),
                'TASK_FENCED','Instance is not accepting new work; paused MAIN captures remain sealed')
    if task.get('mission_id'):
        mission=snapshot.get('missions',{}).get(task['mission_id'])
        require(mission is not None and (mission.get('status') not in ('ENDED','CANCELLED','DELIVERED') or report_authorized),'TASK_FENCED','Original mission no longer accepts results')
    require(request.get('execution_state')!='CANCELLED' and not request.get('cancelled') and not request.get('fenced'),'TASK_FENCED','Request cancelled')
    return True


def _raw_duplicate(task,snapshot,raw):
    prior=snapshot.get('accepted_requests',{}).get(task['request_id'])
    if prior:
        require(prior['capture_hash']==sha(raw),'ALREADY_SETTLED_CONTENT_CONFLICT','This request already accepted different raw bytes')
        return C.ValidatedChange(outcome='EXACT_DUPLICATE',receipt=deepcopy(prior.get('receipt',prior)),events=[],blobs={},accepted_request_bindings=[])
    return None


def validate_response(task,snapshot,raw,mode='preflight',blob_get=None):
    require(mode in ('preflight','live'),'RESPONSE_SCHEMA_INVALID','Validation mode')
    raw=raw.encode('utf-8') if isinstance(raw,str) else raw
    try:result=_validate(task,snapshot,raw,mode,blob_get,allocations={})
    except (KeyError,TypeError,AttributeError,IndexError) as exc:
        raise C.PMRSError('RESPONSE_SCHEMA_INVALID','Invalid required nested response structure') from exc
    result._task=deepcopy(task);result._raw=raw;result._mode=mode
    return result


def _validate(task,snapshot,raw,mode,blob_get,allocations):
    envelope=C.bounded_json(raw)
    if task.get('repair_kind')=='FORMAT':_format_science_unchanged(task,snapshot,envelope,blob_get)
    if task.get('response_contract_revision')==C.AUTHORING_REVISION:C.validate_authoring(envelope,task,snapshot)
    C.fields(envelope,C.ENVELOPE_FIELDS,'ResponseEnvelope')
    require(envelope['schema']==C.RESPONSE_SCHEMA and envelope['task_id']==task['task_id'] and envelope['request_id']==task['request_id'],'RESPONSE_SCHEMA_INVALID','Frozen task/request/schema differs')
    duplicate=_raw_duplicate(task,snapshot,raw)
    if duplicate:return duplicate
    require(task.get('schema')==C.TASK_SCHEMA,'RESPONSE_SCHEMA_INVALID','Frozen final task required')
    permissions=task.get('permission_manifest',{})
    require(envelope['payload_kind'] in permissions.get('allowed_payload_kinds',[]),'AUTHORIZATION_REQUIRED','Payload not permitted for this role')
    if task.get('stage_id'):
        from .workflows.registry import spec
        require(spec(task['stage_id'])['digest']==task.get('stage_spec_digest'),'RESPONSE_SCHEMA_INVALID','Unsupported frozen StageSpec contract')
    if mode=='live':
        require(snapshot.get('tasks',{}).get(task['task_id'])==task,'AUTHORIZATION_REQUIRED','Task must equal the host frozen contract')
        live_check(task,snapshot,blob_get)
        request=snapshot.get('requests',{}).get(task['request_id'])
        require(request is not None and request.get('task_id')==task['task_id'],'AUTHORIZATION_REQUIRED','Host request not registered')
        capture=request.get('capture_ref',request.get('capture_hash'))
        require(capture==sha(raw),'ORIGINAL_BYTES_MISMATCH','Admission must use exact sealed capture')
        if blob_get:require(blob_get(capture)==raw,'ORIGINAL_BYTES_MISMATCH','Capture bytes differ')
    else:
        # Structural preflight still verifies every supplied original byte.
        for item in task.get('input_manifest',[]):
            h=item.get('body_sha256') if item.get('kind')=='record' else item.get('sha256')
            if h and blob_get:require(sha(blob_get(h))==h,'ORIGINAL_BYTES_MISMATCH','Frozen material damaged')
    common={'events':[],'blobs':{},'actor':{'kind':'TASK','task_id':task['task_id']},'base_knowledge_commit':task.get('knowledge_commit'),
        'live_checked':mode=='live','pending_live_checks':[] if mode=='live' else ['read/query/write guards','obligation definitions','authorization/cancel fence','sealed capture'],
        'accepted_request_bindings':[{'request_id':task['request_id'],'task_id':task['task_id'],'capture_hash':sha(raw)}]}
    if envelope['payload_kind'] in ('REPORT_OUTPUT','REPORT_REVIEW'):
        from .reports import validate_payload
        p=validate_payload(task,snapshot,envelope['payload'],blob_get=blob_get)
        result=C.ValidatedChange(**common,outcome='ACCEPTED',report_event=p['event'])
        result['blobs'].update(p.get('blobs',{}));result['receipt']={'receipt_id':'AR-'+C.digest([task['request_id'],sha(raw)]),'request_id':task['request_id'],'capture_hash':sha(raw),'outcome':'ACCEPTED','content_added':[]}
        return result
    survey_payload=None
    if envelope['payload_kind']=='SURVEY_RESULT':
        C.fields(envelope['payload'],{'schema','knowledge_change','action','data'},'SurveyResult')
        survey_payload=deepcopy(envelope['payload']);envelope['payload_kind']='KNOWLEDGE_CHANGE';envelope['payload']=survey_payload['knowledge_change']
    require(envelope['payload_kind']=='KNOWLEDGE_CHANGE','AUTHORIZATION_REQUIRED','Control proposals cannot grant human decisions or scientific authority')
    kcs=envelope['payload'];C.optional_fields(kcs,C.KCS_FIELDS,C.KCS_OPTIONAL_FIELDS,'KnowledgeChangeSet')
    require(kcs['schema']==C.CHANGE_SCHEMA and kcs['task_id']==task['task_id'] and kcs['request_id']==task['request_id'],'RESPONSE_SCHEMA_INVALID','KCS binding differs')
    require(kcs['base_knowledge_commit']==task.get('knowledge_commit'),'RESPONSE_SCHEMA_INVALID','KCS base differs from frozen task')
    for name,key in [('read_set_digest','read_set'),('query_guard_digest','query_guards'),('write_guard_digest','write_guards')]:require(kcs[name]==C.digest(task.get(key,[])),'RESPONSE_SCHEMA_INVALID','Frozen '+key+' digest differs')
    C.enum(kcs['work_outcome'],('RESULT','PARTIAL','NO_RESULT','BLOCKED'),'work outcome')
    C.enum(kcs['semantic_novelty'],('NOT_AUTOMATICALLY_CERTIFIED',),'semantic_novelty')
    require(isinstance(kcs['attempt_account'],str) and isinstance(kcs['claimed_change'],str),'RESPONSE_SCHEMA_INVALID','attempt_account and claimed_change must be English strings')
    authored_english(kcs['attempt_account'],'attempt account');authored_english(kcs['claimed_change'],'claimed change')
    ops=C.sequence(kcs['operations'],'operations',640);effects=C.sequence(kcs['obligation_effects'],'obligation_effects',256)
    proposals=C.sequence(kcs['new_obligation_proposals'],'new obligations',32)
    require(sum(x.get('op') in ('NEW','REVISE') for x in ops)<=64 and sum(x.get('op')=='LINK' for x in ops)<=512,'PAYLOAD_LIMIT','KCS operation limit')
    records={};blobs={};local={};pending={};objects={};inferences={};productions={};supports={};qualifications={};withdrawals={};new_relations=[];outcomes=[]
    supplied={b['record_ref'] for b in task.get('read_set',[])}
    manifest_records={i['ref'] for i in task.get('input_manifest',[]) if i.get('kind')=='record'}
    require(supplied<=manifest_records,'INCOMPLETE_CONTEXT','Read set lists material not actually supplied')
    source_refs={i['ref'] for i in task.get('input_manifest',[]) if i.get('kind')=='source'}
    dynamic_source_refs=set()
    if task.get('communication_contract'):
        from .input_delivery import supplied_records,supplied_sources
        supplied.update(supplied_records(snapshot,task,blob_get))
        dynamic_source_refs=supplied_sources(snapshot,task,blob_get)
        source_refs.update(dynamic_source_refs)
    known_records={r:snapshot['records'][r] for r in supplied if r in snapshot.get('records',{})}
    known_sources={r:snapshot['sources'][r] for r in source_refs if r in snapshot.get('sources',{})}
    for op_index,op in enumerate(ops):
        require(isinstance(op,dict) and op.get('op') in C.OP_FIELDS,'RESPONSE_SCHEMA_INVALID','Unknown KCS operation')
        C.fields(op,C.OP_FIELDS[op['op']],op['op'])
        require(op['op'] in permissions.get('allowed_operations',[]),'AUTHORIZATION_REQUIRED','Operation not permitted')
        if op['op'] not in ('NEW','REVISE'):continue
        key=op['local_key'];require(isinstance(key,str) and C.LOCAL_KEY.fullmatch(key) and key not in pending,'RESPONSE_SCHEMA_INVALID','Unique bounded local key required')
        row=op if op['op']=='NEW' else op['new_record']
        if op['op']=='REVISE':C.fields(row,{'kind','context_refs','body','data'},'new_record')
        require(row['kind'] in permissions.get('allowed_record_kinds',[]),'AUTHORIZATION_REQUIRED','Scientific kind not permitted for role')
        require(isinstance(row['body'],str),'RESPONSE_SCHEMA_INVALID','Inline UTF-8 body required')
        b=row['body'].encode('utf-8');require(0<len(b)<=C.MAX_BODY,'PAYLOAD_LIMIT','Body size')
        blobs[sha(b)]=b;pending[key]=(op,row)
    def getblob(h):
        if h in blobs:return blobs[h]
        require(blob_get is not None,'INCOMPLETE_CONTEXT','Body reader required: '+str(h))
        return blob_get(h)
    active=set()
    def resolve(value,allow_ib=False):
        if isinstance(value,str) and value.startswith('local:'):
            key=value[6:];require(key in pending,'INCOMPLETE_CONTEXT','Unknown local reference');return build(key)
        if isinstance(value,list):return [resolve(v,allow_ib) for v in value]
        if isinstance(value,dict):
            if set(value)=={'inference_of'}:
                require(allow_ib,'RESPONSE_SCHEMA_INVALID','Inference alias is only a review target')
                ref=resolve(value['inference_of']);ib=C.inference_identity(ref)
                require(ib in inferences or ib in snapshot.get('inferences',{}),'RELATION_ENDPOINT_INVALID','Alias requires REDUCTION Argument');return ib
            if set(value)==C.LOCATOR_FIELDS and str(value['blob_hash']).startswith('body:'):
                key=value['blob_hash'][5:];require(key in pending,'INCOMPLETE_CONTEXT','Unknown local body locator')
                rawbody=pending[key][1]['body'].encode('utf-8');l=knowledge.locator(rawbody,value['start'],value['end'],value['unit'])
                require(value['quoted_sha256'] is None or value['quoted_sha256']==l['quoted_sha256'],'ORIGINAL_BYTES_MISMATCH','Local body quote differs');return l
            return {k:resolve(v,allow_ib and k in ('target_refs','checked','unchecked','ref')) for k,v in value.items()}
        return value
    def context_set(authored,resolved,label):
        # Local aliases are replaced by content hashes, whose order cannot be
        # preserved by sorting the alias names. Canonicalize only these Context
        # membership sets after resolution; never reorder proofs or locators,
        # and never hide duplicate references (including alias collisions).
        C.refs(resolved,label)
        return sorted(resolved) if any(ref.startswith('local:') for ref in authored) else resolved
    def build(key):
        if key in local:return local[key]
        require(key not in active,'CYCLIC_MATH_SUPPORT','Cyclic local scientific content');active.add(key)
        op,row=pending[key];data=resolve(row['data'],row['kind']=='Assessment');contexts=resolve(row['context_refs'])
        contexts=context_set(row['context_refs'],contexts,'context_refs')
        for field in ('parent_context_refs','scope_context_refs'):
            if field in data:data[field]=context_set(row['data'][field],data[field],field)
        source_quotes=[]
        for link in ops:
            if link['op']=='LINK' and link['type']=='USED_SOURCE' and link['source_ref']=='local:'+key:
                for use in link['evidence_bindings']:
                    knowledge.source_use(use,known_sources,getblob)
                    validate_source_delivery(task,use['source_ref'],use['locators'],dynamic_sources=dynamic_source_refs)
                    require(use['source_ref']==link['target_ref'],'RELATION_ENDPOINT_INVALID','Quotation source differs')
                    source_quotes.extend(knowledge.validate_locator(loc,getblob).decode('utf-8') for loc in use['locators'])
        try:
            ref,record,body=knowledge.make_record(row['kind'],row['body'],data,contexts,records={**known_records,**records},sources=known_sources,blob_get=getblob,inferences={**snapshot.get('inferences',{}),**inferences},source_quotes=source_quotes)
        except C.PMRSError as exc:
            if getattr(exc,'diagnostic',None):
                exc.diagnostic['pointer']='/payload/'+('knowledge_change/' if survey_payload is not None else '')+'operations/'+str(ops.index(op))+('/new_record' if op['op']=='REVISE' else '')+exc.diagnostic['pointer']
            raise
        _validate_record_source_delivery(task,record,dynamic_source_refs)
        if record['kind']=='Argument':
            for premise in data['premise_bindings']:
                if premise['kind']=='SUPPORTED_STATEMENT':
                    support=snapshot.get('supports',{}).get(premise['support_ref'])
                    require(support and support['statement_ref']==premise['premise_ref'],'RESPONSE_SCHEMA_INVALID','Selected support does not support the exact premise')
                    require(any(premise['support_ref'] in b['required_support_refs'] for b in task['read_set']),'INCOMPLETE_CONTEXT','Premise support was not frozen')
                    support_requirement=support.get('consumer_requirement')
                    require(support_requirement and assurance.evaluate_requirement(snapshot,premise['support_ref'],support_requirement,support.get('policy_digest'))['result']=='QUALIFIED','DEPENDENCY_UNQUALIFIED','SUPPORTED_STATEMENT requires exact qualified support; an unreviewed candidate cannot be relabeled')
        if record['kind']=='Assessment' and task.get('independent'):
            req=task.get('required_assurance')
            if req:
                assurance.validate_requirement(req)
                slots=[s for s in req['review_slots'] if task['role'] in s['allowed_roles'] and data['review_kind']==s['review_kind']]
                require(slots,'AUTHORIZATION_REQUIRED','Assessment kind does not match the frozen consumer slot')
                allowed_scope=[x for slot in slots for x in slot['required_scope']]
                require(set(data['target_refs'])<=set(x['target_ref'] for x in allowed_scope),'AUTHORIZATION_REQUIRED','Review target outside frozen scope')
                require(assurance.coverage(assurance.checked_scope(record),allowed_scope)['complete'] if data['checked'] else True,'AUTHORIZATION_REQUIRED','Checked scope exceeds frozen task assignment')
                require(all(any(r['ref']==a['target_ref'] and r['aspect'] in a['aspects'] for a in allowed_scope) for r in data['unchecked']),'AUTHORIZATION_REQUIRED','Unchecked aspect exceeds frozen task assignment')
        if op['op']=='REVISE':
            parent=op['expected_parent'];oid=op['object_id']
            require(parent in supplied,'STALE_READ','Revision parent was not read')
            old=snapshot.get('objects',{}).get(oid)
            require(old and old.get('selected_revision')==parent,'WRITE_CAS_CONFLICT','Revision parent selection changed')
            require(snapshot['records'][parent]['kind']==row['kind'],'RELATION_ENDPOINT_INVALID','Revision changes scientific kind')
            require(any(g['object_id']==oid and g['expected_parent']==parent for g in task.get('write_guards',[])),'AUTHORIZATION_REQUIRED','Revision lacks frozen write guard')
            obj=deepcopy(old);obj['revisions']=list(dict.fromkeys(obj.get('revisions',[parent])+[ref]));obj['selected_revision']=ref
            new_relations.append(relations.relation(ref,parent,'REVISION_OF',created_by_event='PROD-'+C.digest([task['request_id'],key])))
        else:
            existing=[(o,v) for o,v in snapshot.get('objects',{}).items() if v.get('kind')==row['kind'] and ref in v.get('revisions',[])]
            if existing:oid,obj=sorted(existing)[0];obj=deepcopy(obj)
            else:
                oid=allocations.setdefault(key,'KO-'+secrets.token_hex(16));obj={'object_id':oid,'kind':row['kind'],'created_by_event':'PROD-'+C.digest([task['request_id'],key]),'revisions':[ref],'selected_revision':ref}
        objects[oid]=obj;records[ref]=record;local[key]=ref;active.remove(key)
        inference=knowledge.derive_inference(ref,record)
        if inference:inferences[inference[0]]=inference[1]
        eid='PROD-'+C.digest([task['request_id'],key])
        productions[eid]={'event_id':eid,'record_ref':ref,'workflow_instance_id':task.get('instance_id'),'task_id':task['task_id'],'request_id':task['request_id'],'capture_hash':sha(raw),'origin_ref':None,'at':snapshot.get('requests',{}).get(task['request_id'],{}).get('captured_at'),'authorship':'MODEL' if snapshot.get('requests',{}).get(task['request_id'],{}).get('execution_kind') in ('MODEL','MODEL_CAPTURE','SYNTHETIC_TEST_ONLY') else 'HUMAN'}
        outcomes.append({'record_ref':ref,'operation':op['op'],'content':'REUSED' if ref in snapshot.get('records',{}) else 'CONTENT_ADDED'})
        return ref
    for key in sorted(pending):build(key)
    combined={**snapshot,'records':{**snapshot.get('records',{}),**records},'inferences':{**snapshot.get('inferences',{}),**inferences}}
    for op in ops:
        if op['op']=='LINK':
            a=resolve(op['source_ref']);b=resolve(op['target_ref'],op['type']=='REVIEW_TARGET')
            require(a in supplied or a in records,'INCOMPLETE_CONTEXT','Link source was not supplied')
            require(b in supplied or b in records or b in source_refs or b in inferences or b in snapshot.get('obligations',{}),'INCOMPLETE_CONTEXT','Link target was not supplied')
            contexts=context_set(op['scope_context_refs'],resolve(op['scope_context_refs']),'relation scope')
            row=relations.relation(a,b,op['type'],scope_context_refs=contexts,evidence_bindings=resolve(op['evidence_bindings']),assertion_state=op['assertion_state'],created_by_event='CHANGE-'+sha(raw))
            relations.validate_relation(row,combined,getblob)
            if row['type']=='USED_SOURCE':
                for use in row['evidence_bindings']:validate_source_delivery(task,use['source_ref'],use['locators'],dynamic_sources=dynamic_source_refs)
            new_relations.append(row)
        elif op['op']=='WITHDRAW_SUPPORT':
            sid=op['support_id'];support=snapshot.get('supports',{}).get(sid)
            require(support and C.digest(support.get('qualification_refs',[]))==op['expected_qualification_head'],'WRITE_CAS_CONFLICT','Support qualification head changed')
            evidence=resolve(op['evidence_refs']);authorized=permissions.get('human_review_withdrawal',False)
            for r in evidence:
                a=combined['records'].get(r)
                if a and a['kind']=='Assessment' and a['data']['verdict']=='DEFECT_FOUND':
                    targets=set(a['data']['target_refs'])
                    targets.update(snapshot.get('inferences',{}).get(x,{}).get('argument_ref') for x in list(targets) if x.startswith('IB-'))
                    if support['argument_ref'] in targets and assurance.coverage(resolve(op['scope']),assurance.checked_scope(a))['complete']:
                        for q in snapshot.get('qualifications',{}).values():
                            if q.get('assessment_ref')!=r:continue
                            event,error=assurance._credential(snapshot,q,a,None)
                            authorized |= not error and bool(event and event.get('independent') and event.get('task_id')!=support.get('author_task_id') and q.get('review_execution_event')!=support.get('author_execution_event'))
            require(authorized,'AUTHORIZATION_REQUIRED','Withdrawal requires independent defect evidence or explicit human review authority')
            assurance.validate_scope(resolve(op['scope']))
            wid='WD-'+C.digest([task['request_id'],sid]);withdrawals[wid]={'withdrawal_id':wid,'support_id':sid,'reason_code':op['reason_code'],'evidence_refs':evidence,'scope':resolve(op['scope']),'actor_permission':deepcopy(permissions),'expected_qualification_head':op['expected_qualification_head'],'active':True}
    relations.acyclic(relations.edges(snapshot)+new_relations)
    bindings={b['binding_id']:b for b in task.get('obligation_bindings',[])};seen=set();resolved_effects=[]
    for effect in effects:
        C.fields(effect,EFFECT_FIELDS,'ObligationEffect');bid=effect['binding_id']
        require(bid in bindings and bid not in seen,'AUTHORIZATION_REQUIRED','Every assigned binding exactly once');seen.add(bid)
        require(effect['expected_definition_revision']==bindings[bid]['expected_definition_revision'],'STALE_OBLIGATION_DEFINITION',bid)
        C.enum(effect['work_disposition'],('ADDRESSED','PARTIAL','BLOCKED','NO_RESULT'),'work disposition')
        C.enum(effect['resolution_proposal'],('CANDIDATE_RESPONSE','UNRESOLVED','NEEDS_RECHECK'),'resolution proposal')
        resolved=resolve(effect);C.refs(resolved['evidence_refs'],'effect evidence')
        require(all(r in supplied or r in records for r in resolved['evidence_refs']),'INCOMPLETE_CONTEXT','Effect evidence not read')
        require(isinstance(resolved['remaining_conditions'],(list,str)) and isinstance(resolved['blocker_proposals'],list),'RESPONSE_SCHEMA_INVALID','Effect conditions/blockers')
        for blocker in resolved['blocker_proposals']:
            C.fields(blocker,{'code','evidence_refs','scope','hardness','retry_condition'},'BlockerProposal')
            C.enum(blocker['hardness'],('HARD','EXPLORATORY'),'blocker hardness')
            require(isinstance(blocker['code'],str) and blocker['code'],'RESPONSE_SCHEMA_INVALID','Stable blocker code required')
            C.refs(blocker['evidence_refs'],'blocker evidence')
            require(all(r in supplied or r in records or r in source_refs for r in blocker['evidence_refs']),'INCOMPLETE_CONTEXT','Blocker evidence not supplied')
            from .obligations import validate_condition
            validate_condition(blocker['retry_condition'])
        if effect['work_disposition']=='NO_RESULT':require(effect['resolution_proposal']=='UNRESOLVED','AUTHORIZATION_REQUIRED','No result cannot close science')
        resolved_effects.append({**resolved,'obligation_id':bindings[bid]['obligation_id']})
    require(seen==set(bindings),'RESPONSE_SCHEMA_INVALID','Missing assigned obligation effect')
    new_obligations={}
    for prop in proposals:
        C.fields(prop,PROPOSAL_FIELDS,'new obligation');C.enum(prop['type'],C.OBLIGATION_TYPES,'obligation type')
        require(prop['reason_code'] is None or prop['type']=='MATERIAL' and prop['reason_code']=='NORMALIZATION_REQUIRED','RESPONSE_SCHEMA_INVALID','Normalization is a MATERIAL reason')
        value=resolve(prop);authored_english(value['criterion_body'],'criterion');raw_criterion=value.pop('criterion_body').encode();h=sha(raw_criterion);blobs[h]=raw_criterion
        oid='OB-'+C.digest([task['request_id'],prop['local_key']]);require(oid not in new_obligations,'RESPONSE_SCHEMA_INVALID','Duplicate obligation local key')
        require(all(r in supplied or r in records for r in value['target_refs']),'AUTHORIZATION_REQUIRED','New obligation targets outside task inputs')
        require(not value['consumer_binding_proposals'],'AUTHORIZATION_REQUIRED','New consumer authority must be assigned by the host workflow')
        definition={'obligation_id':oid,'definition_revision':1,'type':value['type'],'target_refs':value['target_refs'],'criterion_body_ref':h,'scope_context_refs':value['scope_context_refs'],'dependency_bindings':value['dependency_bindings'],'consumer_bindings':[],'effect_on_goal':value['effect_on_goal'],'created_by':'CHANGE-'+sha(raw),'reason_code':value['reason_code'],'alias_of':None}
        new_obligations[oid]={'definition':definition,'projection':{'work_state':'OPEN','resolution':'UNRESOLVED','attempt_refs':[],'blocker_refs':[],'evidence_refs':[],'consumer_resolutions':{},'retry_gate_ref':None}}
    # Supports and qualifications are derived by host from scientific records and
    # frozen execution evidence; neither is a model operation.
    for ref,record in records.items():
        if record['kind']=='Argument':
            sid='SUP-'+C.digest([ref,task['request_id']]);d=record['data']
            supports[sid]={'support_id':sid,'statement_ref':d['conclusion_ref'],'argument_ref':ref,
                'premise_support_refs':[p['support_ref'] for p in d['premise_bindings'] if p['support_ref']],
                'open_assumption_refs':[p['premise_ref'] for p in d['premise_bindings'] if p['kind'] in ('CONTEXT_ASSUMPTION','CONDITIONAL_CANDIDATE')],
                'scope_context_refs':record['context_refs'],'qualification_refs':[],'created_by_change':'CHANGE-'+sha(raw),
                'condition_evidence':assurance.condition_evidence(ref,record),
                'author_task_id':task['task_id'],'author_execution_event':snapshot.get('requests',{}).get(task['request_id'],{}).get('execution_id'),'integrity_valid':True}
        if record['kind']=='Assessment':
            event_id=snapshot.get('requests',{}).get(task['request_id'],{}).get('execution_id')
            event=snapshot.get('review_executions',{}).get(event_id)
            if event:
                require(event['role']==task['role'] and event.get('task_id')==task['task_id'],'AUTHORIZATION_REQUIRED','Review execution binding')
                qid='QUAL-'+C.digest([ref,event_id]);targets=list(record['data']['target_refs'])
                targets.extend(combined['inferences'][r]['argument_ref'] for r in record['data']['target_refs'] if r in combined['inferences'])
                q={'assessment_ref':ref,'review_execution_event':event_id,'input_manifest_hash':task.get('input_manifest_hash',C.digest(task['input_manifest'])),'target_revision_hashes':sorted(set(targets)),'actual_checked_scope':assurance.checked_scope(record),'evidence_origin':'MODEL_CAPTURE','policy_digest':task.get('policy_digest'),'integrity_valid':True}
                qualifications[qid]=q
                for sid,support in {**snapshot.get('supports',{}),**supports}.items():
                    if support['argument_ref'] in targets:
                        revised=deepcopy(support);revised['qualification_refs']=list(dict.fromkeys(revised['qualification_refs']+[qid]))
                        req=snapshot.get('coverage_plans',{}).get(task.get('coverage_plan_id'),{}).get('requirement',task.get('required_assurance'))
                        if req and not revised.get('consumer_requirement') and req['purpose']!='INTEGRATION' and all(x['target_ref'] in targets for x in req['required_scope']):
                            revised['consumer_requirement']=deepcopy(req);revised['policy_digest']=task.get('policy_digest')
                        supports[sid]=revised
    combined['supports']={**snapshot.get('supports',{}),**supports};relations.validate_support_graph(combined)
    receipt={'receipt_id':'AR-'+C.digest([task['request_id'],sha(raw)]),'request_id':task['request_id'],'capture_hash':sha(raw),'outcome':'ACCEPTED','content_added':sorted(r for r in records if r not in snapshot.get('records',{})),'content_reused':sorted(r for r in records if r in snapshot.get('records',{})),'semantic_novelty':'NOT_AUTOMATICALLY_CERTIFIED'}
    candidates={}
    if snapshot.get('instances',{}).get(task.get('instance_id'),{}).get('kind')=='FDH':
        for ref,r in records.items():
            if r['kind']!='Statement':continue
            cid='CAND-'+C.digest([task['instance_id'],ref])
            if cid in snapshot.get('candidates',{}):continue
            candidates[cid]={'instance_id':task['instance_id'],'mission_id':task.get('mission_id'),'statement_ref':ref,'candidate_state':'CONSIDERED','reason_ref':ref,'evidence_refs':[],'comparison_refs':[],'decision_event':None,
              'origin_statement_refs':sorted({x['ref'] for x in task.get('input_manifest',[]) if x.get('kind')=='record' and snapshot.get('records',{}).get(x.get('ref'),{}).get('kind')=='Statement'}),
              'change_axes':[],'motivation_refs':[],'cost_locators':[],'calibration_refs':[]}
    result=C.ValidatedChange(**common,outcome='ACCEPTED',receipt=receipt,records=records,objects=objects,inferences=inferences,production_events=productions,supports=supports,qualifications=qualifications,withdrawals=withdrawals,relations=new_relations,obligation_effects=resolved_effects,new_obligations=new_obligations,change_items=outcomes,attempt_account=kcs['attempt_account'],work_outcome=kcs['work_outcome'],candidates=candidates,input_fingerprint=task.get('input_fingerprint'))
    if survey_payload is not None:
        from .survey import validate_result
        survey_payload['data']=resolve(survey_payload['data'])
        result['survey_changes']=validate_result(task,snapshot,survey_payload,records,getblob)
    if 'message_dispositions' in kcs or task.get('communication_contract'):
        from .communication import validate_dispositions
        disposition_items=resolve(kcs.get('message_dispositions',[]))
        validate_dispositions(snapshot,task,disposition_items,resolved_refs=set(supplied)|set(records))
        result['message_dispositions']=disposition_items
    if 'strategy_proposal' in kcs:
        require(task.get('actor_kind')=='MAIN','AUTHORIZATION_REQUIRED','Only registered MAIN tasks may propose strategy')
        from .strategy import validate_output_proposal
        result['strategy_change']=validate_output_proposal(task,snapshot,kcs['strategy_proposal'],resolve,records=records,blobs=blobs,blob_get=getblob,science=result)
    elif task.get('actor_kind')=='MAIN':
        raise C.PMRSError('STRATEGY_PROPOSAL_REQUIRED','The assigned main responsibility requires a concrete strategy proposal')
    result['blobs']=blobs;result['events']=[{'kind':'KNOWLEDGE_CHANGE_ACCEPTED','request_id':task['request_id'],'capture_hash':sha(raw),'work_outcome':kcs['work_outcome'],'changes':outcomes}]
    result._allocations=allocations
    return result


def apply_validated(snapshot,proposal):
    state=deepcopy(snapshot)
    if proposal.get('outcome')=='EXACT_DUPLICATE':return state
    for name in SCIENCE_MAPS:
        if name in proposal:state.setdefault(name,{}).update(deepcopy(proposal[name]))
    if proposal.get('relations'):
        current=state.setdefault('relations',[])
        if isinstance(current,dict):current.update({r['relation_id']:deepcopy(r) for r in proposal['relations']})
        else:
            ids={r['relation_id'] for r in current};current.extend(deepcopy(r) for r in proposal['relations'] if r['relation_id'] not in ids)
    for name,rows in proposal.get('survey_changes',{}).items():
        from .survey import MAPS
        require(name in MAPS,'SURVEY_RESULT_INVALID','Unknown Survey metadata collection')
        state.setdefault(name,{}).update(deepcopy(rows))
    state.setdefault('obligations',{}).update(deepcopy(proposal.get('new_obligations',{})))
    state.setdefault('candidates',{}).update(deepcopy(proposal.get('candidates',{})))
    for effect in proposal.get('obligation_effects',[]):
        o=state['obligations'][effect['obligation_id']];p=o['projection']
        p['work_state']='BLOCKED' if effect['work_disposition']=='BLOCKED' else 'ATTEMPTED'
        p['resolution']=effect['resolution_proposal'];p.setdefault('evidence_refs',[])
        p['evidence_refs']=list(dict.fromkeys(p['evidence_refs']+effect['evidence_refs']))
        p.setdefault('attempt_refs',[]).append(proposal['receipt']['request_id'])
        p.setdefault('attempt_accounts',[]).append({'request_id':proposal['receipt']['request_id'],'account':proposal['attempt_account'],'work_disposition':effect['work_disposition'],'remaining_conditions':effect['remaining_conditions'],'blocker_proposals':effect['blocker_proposals']})
        for index,blocker in enumerate(effect['blocker_proposals']):
            blocker_id='BLK-'+C.digest([proposal['receipt']['request_id'],effect['binding_id'],index])
            state.setdefault('blockers',{})[blocker_id]={**deepcopy(blocker),'blocker_id':blocker_id,'obligation_id':effect['obligation_id'],
                'definition_revision':effect['expected_definition_revision'],'observed_input_fingerprint':proposal.get('input_fingerprint'),
                'created_event':proposal['receipt']['receipt_id'],'resolution_events':[]}
            if blocker_id not in p.setdefault('blocker_refs',[]):p['blocker_refs'].append(blocker_id)
        # Only host requirement evaluation may satisfy a mathematical consumer.
        for consumer in o['definition']['consumer_bindings']:
            if consumer.get('binding_id')!=effect['binding_id']:continue
            threshold=consumer.get('threshold',consumer.get('required_threshold','SUPPORT_QUALIFIED'))
            if threshold=='ARTIFACT_AVAILABLE':satisfied=bool(effect['evidence_refs'])
            elif threshold=='WORK_DISPOSITION_RECORDED':satisfied=True
            elif threshold=='SUPPORT_QUALIFIED' and consumer.get('required_assurance'):
                refs=o['definition']['target_refs'];views=[assurance.evaluate(r,consumer,state) for r in refs if state.get('records',{}).get(r,{}).get('kind')=='Statement']
                satisfied=bool(views) and all(v['support_state']=='SUPPORTED_WITHIN_SCOPE' for v in views)
            else:satisfied=False
            p.setdefault('consumer_resolutions',{})[effect['binding_id']]='SATISFIED_FOR_CONSUMER' if satisfied else effect['resolution_proposal']
        if p.get('consumer_resolutions') and all(v=='SATISFIED_FOR_CONSUMER' for v in p['consumer_resolutions'].values()) and len(p['consumer_resolutions'])==len(o['definition']['consumer_bindings']):p['resolution']='SATISFIED_FOR_CONSUMER'
    if proposal.get('withdrawals'):
        roots={w['support_id'] for w in proposal['withdrawals'].values()}
        affected=relations.affected_supports(state,roots)
        for sid in affected:
            if sid not in roots and sid in state.get('supports',{}):state['supports'][sid]['needs_recheck']=True
        for o in state.get('obligations',{}).values():
            if any(any(s in affected for s in c.get('selected_support_refs',[])) or c.get('selected_support') in affected for c in o['definition']['consumer_bindings']):o['projection']['resolution']='NEEDS_RECHECK'
    if 'report_event' in proposal:
        from .reports import apply_event
        state=apply_event(state,proposal['report_event'])
    receipt=proposal.get('receipt',{})
    for binding in proposal.get('accepted_request_bindings',[]):
        state.setdefault('accepted_requests',{})[binding['request_id']]={**deepcopy(binding),'receipt':deepcopy(receipt)}
        if binding['request_id'] in state.get('requests',{}):
            request=state['requests'][binding['request_id']]
            if 'message_dispositions' in proposal:request['message_dispositions']=deepcopy(proposal['message_dispositions'])
            request['acceptance_state']='ACCEPTED';request['execution_state']='SETTLED';request['receipt_ref']=receipt.get('receipt_id')
    state.setdefault('knowledge_changes',[]).append({'base_knowledge_commit':proposal.get('base_knowledge_commit'),'receipt':deepcopy(receipt),'items':deepcopy(proposal.get('change_items',[])),'work_outcome':proposal.get('work_outcome')})
    if proposal.get('strategy_change'):
        from .strategy import apply_validated as apply_strategy
        state=apply_strategy(state,proposal['strategy_change'])
    return state


def revalidate(validated,snapshot,*,blob_get=None):
    require(isinstance(validated,C.ValidatedChange),'AUTHORIZATION_REQUIRED','Store only accepts a validated change')
    if getattr(validated,'_family',None) is not None:return prepare_result_family(snapshot,validated._family)
    if getattr(validated,'_material',None) is not None:
        return prepare_material_input(snapshot,**validated._material,blob_get=blob_get)
    if getattr(validated,'_source',None) is not None:
        value=validated._source
        return prepare_source_input(snapshot,value['raw'],value['title'],value['purpose'],source_id=value['source_id'],blob_get=blob_get)
    result=_validate(validated._task,snapshot,validated._raw,'live',blob_get,getattr(validated,'_allocations',{}))
    result._task=validated._task;result._raw=validated._raw;result._mode='live'
    return result


def _prepare_original_input(snapshot,batch,blob_get=None):
    """Validate native user originals; this host path grants no proof authority."""
    C.fields(batch,{'records','objects','sources','production_events','blobs','relations'},'Original input')
    require(not batch['relations'],'SOURCE_INPUT_INVALID','Original input cannot introduce relations')
    records=batch['records'];blobs=batch['blobs']
    require(len(records)<=1,'PAYLOAD_LIMIT','One exact original statement per input')
    for h,b in blobs.items():require(isinstance(b,bytes) and sha(b)==h,'ORIGINAL_BYTES_MISMATCH','Original blob')
    def getblob(h):
        if h in blobs:return blobs[h]
        require(blob_get is not None,'INCOMPLETE_CONTEXT','Original blob missing');return blob_get(h)
    sources={**snapshot.get('sources',{}),**batch['sources']}
    for ref,source in batch['sources'].items():
        require(ref.startswith('SO-') and source['source_id']==ref,'SOURCE_INPUT_INVALID','Source occurrence ID')
        require(source['origin']['kind'] in {'USER_INPUT','USER_UPLOAD'} and source['access_class']=='SCIENTIFIC_SOURCE'
                and source['provenance_refs']==[],'SOURCE_INPUT_INVALID','Exact user original required')
        raw=getblob(source['blob_hash'])
        require(sha(raw)==source['blob_hash'] and len(raw)==source['bytes'],'ORIGINAL_BYTES_MISMATCH','Source bytes changed')
        require(ref not in snapshot.get('sources',{}) or snapshot['sources'][ref]==source,'WRITE_CAS_CONFLICT','Source occurrence cannot be overwritten')
    combined={**snapshot.get('records',{}),**records}
    for ref,record in records.items():
        require(record['kind']=='Statement' and record['data']['representation']=='SOURCE_BOUND','SOURCE_INPUT_INVALID','Only exact source-bound target input')
        actual=knowledge.validate_record(record,getblob(record['body_sha256']),records=combined,sources=sources,blob_get=getblob,authored=False)
        require(actual==ref,'ORIGINAL_BYTES_MISMATCH','Original scientific identity differs')
    for ref,obj in batch['objects'].items():
        require(ref.startswith('KO-') and obj['object_id']==ref and obj['kind']=='Statement'
                and len(obj['revisions'])==1 and obj['revisions'][0] in records
                and obj['selected_revision']==obj['revisions'][0],'SOURCE_INPUT_INVALID','Exact logical target required')
        require(ref not in snapshot.get('objects',{}) or snapshot['objects'][ref]==obj,'WRITE_CAS_CONFLICT','Original target cannot be overwritten')
    for event in batch['production_events'].values():
        require(event['authorship']=='SOURCE_PRESERVED' and event['origin_ref'] in batch['sources']
                and event['record_ref'] in records and not event.get('task_id') and not event.get('capture_hash'),
                'SOURCE_INPUT_INVALID','Original input cannot invent a model execution')
    return C.ValidatedChange({**deepcopy(batch),'outcome':'ACCEPTED','new_obligations':{},'events':[],
        'actor':{'kind':'HOST_SOURCE_INPUT'},'live_checked':True,'base_knowledge_commit':snapshot.get('knowledge_commit'),
        'accepted_request_bindings':[],'receipt':{'outcome':'ACCEPTED','content_added':sorted(set(records)-set(snapshot.get('records',{}))),
        'authority':'SOURCE_PRESERVATION_ONLY'}})


def prepare_source_input(snapshot,raw,title='Original research input',purpose='PROBLEM',*,source_id=None,blob_get=None):
    """Host receipt of exact user bytes; no model or mathematical promotion."""
    C.enum(purpose,('PROBLEM','PHENOMENON'),'source input purpose')
    raw=raw.encode('utf-8') if isinstance(raw,str) else raw
    require(isinstance(raw,bytes) and raw and len(raw)<=C.MAX_BODY,'PAYLOAD_LIMIT','Original source input limit')
    try:text=raw.decode('utf-8')
    except UnicodeError as exc:raise C.PMRSError('RESPONSE_SCHEMA_INVALID','Initial research input must be UTF-8') from exc
    sid=source_id or 'SO-'+secrets.token_hex(16);h=sha(raw)
    source={'source_id':sid,'blob_hash':h,'bytes':len(raw),'media_type':'text/plain; charset=utf-8','original_filename':title,
       'origin':{'kind':'USER_INPUT','uri':None,'received_at':None,'provided_by':'HUMAN'},'language':'mixed' if any('\u3400'<=c<='\u9fff' for c in text) else 'en',
       'coverage':'FULL_DOCUMENT','provenance_refs':[],'access_class':'SCIENTIFIC_SOURCE'}
    batch={'records':{},'objects':{},'sources':{sid:source},'production_events':{},'blobs':{h:raw},'relations':[]}
    target=None
    if purpose=='PROBLEM':
        loc=knowledge.locator(raw)
        data={'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[],'conclusion_locators':[loc],'quantifier_locators':[],
           'form':'QUESTION','representation':'SOURCE_BOUND','source_binding':{'source_ref':sid,'locators':[loc],'usage_mode':'DECLARED_EXCERPT','trust_boundary':'Exact user-provided target, not independently established.'}}
        target,record,_=knowledge.make_record('Statement',raw,data,[],records=snapshot.get('records',{}),sources={sid:source},blob_get=lambda key:raw if key==h else blob_get(key))
        oid='KO-'+C.digest([sid,target]);eid='PROD-'+C.digest([sid,target])
        batch['records'][target]=record;batch['objects'][oid]={'object_id':oid,'kind':'Statement','created_by_event':eid,'revisions':[target],'selected_revision':target}
        batch['production_events'][eid]={'event_id':eid,'record_ref':target,'workflow_instance_id':None,'task_id':None,'request_id':None,'capture_hash':None,'origin_ref':sid,'at':None,'authorship':'SOURCE_PRESERVED'}
    result=_prepare_original_input(snapshot,batch,blob_get)
    result['actor']={'kind':'HOST_SOURCE_INPUT'};result['events']=[{'kind':'ORIGINAL_SOURCE_RECEIVED','source_ref':sid,'target_ref':target,'purpose':purpose}]
    result['receipt'].update(source_ref=sid,target_ref=target,purpose=purpose)
    result._source={'raw':raw,'title':title,'purpose':purpose,'source_id':sid}
    return result


def prepare_material_input(snapshot,raw,title='Supplemental source',media_type='application/octet-stream',*,source_id=None,blob_get=None):
    """Preserve an uploaded original, including binary PDF, without executing it."""
    require(isinstance(raw,bytes) and raw and len(raw)<=4*1024**3,'PAYLOAD_LIMIT','Source must contain exact bytes within the 4 GiB source limit')
    require(isinstance(title,str) and title and len(title)<=1024 and '\0' not in title,'RESPONSE_SCHEMA_INVALID','Source display filename')
    require(isinstance(media_type,str) and media_type and len(media_type)<=200 and '\0' not in media_type,'RESPONSE_SCHEMA_INVALID','Media type')
    sid=source_id or 'SO-'+secrets.token_hex(16);h=sha(raw)
    source={'source_id':sid,'blob_hash':h,'bytes':len(raw),'media_type':media_type,'original_filename':title,
       'origin':{'kind':'USER_UPLOAD','uri':None,'received_at':None,'provided_by':'HUMAN'},'language':'undetermined',
       'coverage':'FULL_DOCUMENT','provenance_refs':[],'access_class':'SCIENTIFIC_SOURCE'}
    batch={'sources':{sid:source},'blobs':{h:raw},'records':{},'objects':{},'production_events':{},'relations':[]}
    result=_prepare_original_input(snapshot,batch,blob_get);result['actor']={'kind':'HOST_MATERIAL_INPUT'}
    result['events']=[{'kind':'ORIGINAL_MATERIAL_RECEIVED','source_ref':sid,'media_type':media_type}]
    result['receipt'].update(source_ref=sid,target_ref=None,authority='ORIGINAL_MATERIAL_ONLY')
    result._material={'raw':raw,'title':title,'media_type':media_type,'source_id':sid}
    return result


def prepare_result_family(snapshot,family):
    """Host navigation index only: exact existing refs, no record or authority edits."""
    value=knowledge.result_family(family,snapshot.get('records',{}));fid=value['family_id']
    existing=snapshot.get('result_families',{}).get(fid)
    require(existing is None or existing==value,'WRITE_CAS_CONFLICT','Use a new family ID for a different navigation grouping')
    result=C.ValidatedChange(outcome='ACCEPTED',actor={'kind':'HOST_NAVIGATION'},result_families={fid:value},blobs={},
        base_knowledge_commit=snapshot.get('knowledge_commit'),live_checked=True,accepted_request_bindings=[],
        events=[{'kind':'RESULT_FAMILY_INDEXED','family_id':fid}],receipt={'outcome':'ACCEPTED','family_id':fid,'authority':'DISPLAY_ONLY','content_added':[]})
    result._family=deepcopy(value)
    return result


_FORMAT_WIRE_FIELDS=frozenset({'schema','task_id','request_id','base_knowledge_commit','read_set_digest','query_guard_digest','write_guard_digest'})


def _repair_kcs(envelope):
    require(isinstance(envelope,dict) and isinstance(envelope.get('payload'),dict),'REPAIR_SCIENCE_UNVERIFIABLE','An exact object payload is required to preserve science')
    if envelope.get('payload_kind')=='KNOWLEDGE_CHANGE':return envelope['payload']
    if envelope.get('payload_kind')=='SURVEY_RESULT':
        require(isinstance(envelope['payload'].get('knowledge_change'),dict),'REPAIR_SCIENCE_UNVERIFIABLE','Survey must retain its native knowledge change')
        return envelope['payload']['knowledge_change']
    require(envelope.get('payload_kind') in {'REPORT_OUTPUT','REPORT_REVIEW'},'REPAIR_SCIENCE_UNVERIFIABLE','Unknown original payload kind')
    return None


def _resolve_projection_locators(envelope):
    """Only the registered local-body locator representation is normalized."""
    value=deepcopy(envelope);kcs=_repair_kcs(value);bodies={}
    if kcs is not None:
        for field in ('operations','obligation_effects','new_obligation_proposals'):
            require(isinstance(kcs.get(field),list),'REPAIR_SCIENCE_UNVERIFIABLE','Original '+field+' must have a unique list interpretation')
        for op in kcs['operations']:
            require(isinstance(op,dict),'REPAIR_SCIENCE_UNVERIFIABLE','Original operation is not uniquely typed')
            if op.get('op') in {'NEW','REVISE'}:
                row=op if op['op']=='NEW' else op.get('new_record')
                require(isinstance(row,dict) and isinstance(row.get('body'),str) and isinstance(op.get('local_key'),str),'REPAIR_SCIENCE_UNVERIFIABLE','Exact original scientific body required')
                require(op['local_key'] not in bodies,'REPAIR_SCIENCE_UNVERIFIABLE','Duplicate local body identity')
                bodies[op['local_key']]=row['body'].encode('utf-8')
    def walk(v):
        if isinstance(v,list):return [walk(x) for x in v]
        if not isinstance(v,dict):return v
        if set(v)==C.LOCATOR_FIELDS and isinstance(v['blob_hash'],str) and v['blob_hash'].startswith('body:'):
            require(v['blob_hash'][5:] in bodies,'REPAIR_SCIENCE_UNVERIFIABLE','Unbound local body')
            raw=bodies[v['blob_hash'][5:]]
            try:actual=knowledge.locator(raw,v['start'],v['end'],v['unit'])
            except (C.PMRSError,TypeError,IndexError) as exc:raise C.PMRSError('REPAIR_SCIENCE_UNVERIFIABLE','Invalid original local-body locator') from exc
            require(v['quoted_sha256'] is None or v['quoted_sha256']==actual['quoted_sha256'],'REPAIR_SCIENCE_UNVERIFIABLE','Conflicting original quotation digest')
            return actual
        return {k:walk(x) for k,x in v.items()}
    return walk(value)


def science_projection(raw_or_envelope):
    """Versioned, exhaustive science projection; unknown fields stay locked.

    Everything except registered transport identity fields is scientific for
    FORMAT purposes. No premise, account, proposal or nested Survey field is
    selectively omitted. Unparseable JSON and duplicate keys are never proof.
    """
    envelope=C.bounded_json(raw_or_envelope) if isinstance(raw_or_envelope,(str,bytes)) else deepcopy(raw_or_envelope)
    value=_resolve_projection_locators(envelope)
    for key in ('schema','task_id','request_id'):value.pop(key,None)
    kcs=_repair_kcs(value)
    if kcs is not None:
        for key in _FORMAT_WIRE_FIELDS:kcs.pop(key,None)
    return {'schema':C.SCIENCE_PROJECTION_REVISION,'content':value}


def _wire_repair(envelope,task):
    value=_resolve_projection_locators(envelope)
    value.update(schema=C.RESPONSE_SCHEMA,task_id=task['task_id'],request_id=task['request_id'])
    kcs=_repair_kcs(value)
    if kcs is not None:
        kcs.update(schema=C.CHANGE_SCHEMA,task_id=task['task_id'],request_id=task['request_id'],base_knowledge_commit=task.get('knowledge_commit'))
        for name,key in [('read_set_digest','read_set'),('query_guard_digest','query_guards'),('write_guard_digest','write_guards')]:kcs[name]=C.digest(task.get(key,[]))
    return value


def validation_snapshot_digest(snapshot):
    return C.digest({k:v for k,v in snapshot.items() if not k.startswith('_')})


def validator_identity():
    """Content identities bind a proof to implementation, not a mutable label."""
    from pathlib import Path
    root=Path(__file__).parent
    modules=('contracts.py','changes.py','knowledge.py','relations.py','assurance.py','language.py','reports.py','survey.py','strategy.py','communication.py','input_delivery.py','execution.py','store.py')
    fingerprints={name:sha((root/name).read_bytes()) for name in modules if (root/name).is_file()}
    domain=root.parent/'pmrh'/'domain'
    fingerprints.update({'pmrh/domain/'+path.name:sha(path.read_bytes()) for path in sorted(domain.glob('*.py'))})
    return {'revision':'pmrs.admission-validator/3','modules':fingerprints}


def _error_diagnostic(exc):
    if getattr(exc,'diagnostic',None):return deepcopy(exc.diagnostic)
    category='STRUCTURE' if exc.code in {'RESPONSE_SCHEMA_INVALID','UNKNOWN_FIELD','DUPLICATE_JSON_KEY'} else 'AUTHORIZATION' if exc.code=='AUTHORIZATION_REQUIRED' else 'SCIENTIFIC_SEMANTICS'
    return {'code':exc.code,'category':category,'pointer':'/','expected':exc.message,'actual':None,'frozen_binding':None,'format_repair_eligible':False,'reason':'No registered pure representation repair has been proved.'}


def format_repair_evidence(task,snapshot,raw,blob_get=None):
    """Prove a bounded pure representation repair and all other semantics.

    A first structural exception alone is never authorization: normalize only
    the registered wire fields, then execute the complete admission path. Any
    remaining structure, endpoint, permissions or scope error blocks FORMAT.
    """
    raw=raw.encode() if isinstance(raw,str) else raw
    proof={'schema':'pmrs.format-evidence/1','eligible':False,'reason':'Pure representation preservation is unproved.',
        'capture_sha256':sha(raw),'task_id':task['task_id'],'request_id':task['request_id'],
        'snapshot_digest':validation_snapshot_digest(snapshot),'snapshot_commit':snapshot.get('knowledge_commit'),'contract_digest':C.digest(C.authoring_contract(task,snapshot)),
        'contract_revision':C.AUTHORING_REVISION,'projection_revision':C.SCIENCE_PROJECTION_REVISION,
        'validator_revision':validator_identity(),'diagnostics':[],'allowed_transforms':['FROZEN_WIRE_BINDINGS','LOCAL_BODY_LOCATOR_CODEC'],'projection_digest':None}
    try:
        original=C.bounded_json(raw);projection=science_projection(original)
        proof['projection_digest']=C.digest(projection)
        schema_issues=C.schema_diagnostics(original,C.authoring_contract(task,snapshot)['response_schema'])
        proof['diagnostics']=schema_issues
        try:validate_response(task,snapshot,raw,blob_get=blob_get)
        except C.PMRSError as exc:
            first=_error_diagnostic(exc)
            if first not in proof['diagnostics']:proof['diagnostics'].append(first)
        else:
            proof['reason']='The original output already passes admission; no FORMAT is needed.';return proof
        candidate=_wire_repair(original,task)
        require(science_projection(candidate)==projection,'REPAIR_SCIENCE_CHANGED','Registered normalization changed science')
        normalized_task={k:v for k,v in task.items() if k not in {'repair_kind','repair_of','repair_index'}}
        validate_response(normalized_task,snapshot,canonical(candidate),blob_get=blob_get)
        proof['eligible']=True;proof['reason']='Only registered frozen wire bindings differ; the exact science passes all admission checks.'
        proof['normalized_capture_sha256']=sha(canonical(candidate))
    except (C.PMRSError,KeyError,TypeError,AttributeError,IndexError) as exc:
        if not isinstance(exc,C.PMRSError):exc=C.PMRSError('REPAIR_SCIENCE_UNVERIFIABLE','Original payload has no unique supported interpretation')
        d=_error_diagnostic(exc)
        if d not in proof['diagnostics']:proof['diagnostics'].append(d)
        proof['reason']=exc.message
    for d in proof['diagnostics']:
        d['format_repair_eligible']=proof['eligible'];d.setdefault('frozen_binding',task.get('request_id'));d.setdefault('reason',proof['reason'])
    return proof


def response_diagnostics(task,snapshot,raw,blob_get=None):
    """Read-only precheck; diagnostics cannot grant scope, budget or truth."""
    try:
        validated=validate_response(task,snapshot,raw,blob_get=blob_get)
        return {'valid':True,'outcome':validated['outcome'],'diagnostics':[],'format_repair_eligible':False}
    except C.PMRSError as exc:
        evidence=format_repair_evidence(task,snapshot,raw,blob_get)
        return {'valid':False,'code':exc.code,'diagnostics':evidence['diagnostics'],'format_repair_eligible':evidence['eligible'],'format_evidence':evidence}


def _format_science_unchanged(task,snapshot,envelope,blob_get):
    require(blob_get is not None,'REPAIR_SCIENCE_UNVERIFIABLE','FORMAT needs the original sealed capture')
    root=snapshot.get('requests',{}).get(task.get('repair_of'),{})
    capture=root.get('capture_ref',root.get('capture_hash'))
    require(isinstance(capture,str),'REPAIR_SCIENCE_UNVERIFIABLE','Original sealed capture identity is missing')
    raw=blob_get(capture);require(sha(raw)==capture,'ORIGINAL_BYTES_MISMATCH','Original sealed capture changed')
    try:before=science_projection(raw);after=science_projection(envelope)
    except C.PMRSError as exc:raise C.PMRSError('REPAIR_SCIENCE_UNVERIFIABLE','Cannot prove unique original science: '+exc.message) from exc
    require(before==after,'REPAIR_SCIENCE_CHANGED','FORMAT cannot change records, premises, conditions, modes, review scope/verdict, effects, gaps, work accounts, strategy or message use')
    proof=task.get('format_proof') or task.get('format_evidence')
    if proof is None:
        event=next((e for e in snapshot.get('execution_events',{}).values() if e.get('event_type')=='PREPARE_REPAIR' and e.get('payload',{}).get('task',{}).get('task_id')==task.get('task_id')),None)
        proof=(event or {}).get('payload',{}).get('format_proof',{}).get('diagnostic')
    if proof:
        same_lineage=any(r.get('capture_ref')==proof.get('capture_sha256') and (rid==task.get('repair_of') or r.get('repair_of')==task.get('repair_of')) for rid,r in snapshot.get('requests',{}).items())
        require(same_lineage and proof.get('projection_digest')==C.digest(before),'REPAIR_SCIENCE_UNVERIFIABLE','FORMAT evidence is not bound to this capture lineage and scientific projection')


def validate_source_delivery(task,source_ref,locators,*,coverage=None,dynamic_sources=()):
    """A stored full blob is not evidence that a task received every byte."""
    source=next((x for x in task.get('input_manifest',[]) if x.get('kind')=='source' and x.get('ref')==source_ref),None)
    if source is None and source_ref in dynamic_sources:return True
    require(source is not None,'INCOMPLETE_CONTEXT','Source occurrence was not delivered to this task: '+str(source_ref))
    view=source.get('body_coverage') or task.get('source_excerpts',{}).get(source_ref)
    if not view:return True
    require(view.get('source_ref')==source_ref and view.get('source_blob_hash')==source.get('sha256'),'ORIGINAL_BYTES_MISMATCH','Source delivery identity differs')
    require(coverage!='FULL_DOCUMENT','INCOMPLETE_CONTEXT','An excerpt or metadata packet cannot establish full-document reading')
    delivered=[x['locator'] for x in view.get('segments',[])]
    for loc in locators:
        cursor=loc['start']
        for part in sorted((l for l in delivered if l['blob_hash']==loc['blob_hash'] and l['unit']==loc['unit']),key=lambda l:l['start']):
            if part['start']<=cursor<part['end']:cursor=max(cursor,part['end'])
            if cursor>=loc['end']:break
        require(cursor>=loc['end'],'INCOMPLETE_CONTEXT','Quoted source range was not actually delivered')
    return True


def _validate_record_source_delivery(task,record,dynamic_sources=()):
    data=record['data']
    if record['kind']=='Statement' and data['source_binding']:
        use=data['source_binding'];validate_source_delivery(task,use['source_ref'],use['locators'],dynamic_sources=dynamic_sources)
    if record['kind']=='SourceEvidence':
        if data['coverage']=='FULL_DOCUMENT':
            for ref in data['source_occurrence_refs']:validate_source_delivery(task,ref,[],coverage='FULL_DOCUMENT',dynamic_sources=dynamic_sources)
        for loc in data['locators']:
            accepted=False
            for ref in data['source_occurrence_refs']:
                try:validate_source_delivery(task,ref,[loc],coverage=data['coverage'],dynamic_sources=dynamic_sources);accepted=True;break
                except C.PMRSError as exc:
                    if exc.code not in {'INCOMPLETE_CONTEXT'}:raise
            require(accepted,'INCOMPLETE_CONTEXT','SourceEvidence cites original bytes absent from the actual input packet')
