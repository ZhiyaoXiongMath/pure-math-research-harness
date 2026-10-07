"""Complete scoped input packets, independent isolation and token preflight."""
from copy import deepcopy
from .util import require, canonical, sha
from . import contracts as C, relations
from .knowledge import validate_record, validate_locator
from .assurance import validate_scope, coverage, validate_requirement

MAX_CONTEXT_BYTES=32*1024*1024
def _source_tainted(ref,snapshot,seen=None):
    seen=set() if seen is None else seen
    require(isinstance(ref,str),'FORBIDDEN_REVIEW_DERIVATIVE','Source ancestry must reference a native source or record')
    if ref in seen:return False
    seen.add(ref)
    source=snapshot.get('sources',{}).get(ref,{})
    if source.get('access_class') in ('OPERATOR_PREPARATION','HISTORICAL_REVIEW','UNKNOWN'):return True
    if snapshot.get('records',{}).get(ref,{}).get('kind')=='Assessment':return True
    derived=snapshot.get('translations',{}).get(ref,{})
    parents=list(source.get('provenance_refs',[]))+list(derived.get('source_refs',[]))
    parents += [r['target_ref'] for r in relations.edges(snapshot) if r['source_ref']==ref and r['type'] in ('TRANSLATES','SOURCE_PROVENANCE')]
    return any(_source_tainted(r,snapshot,seen) for r in parents)


def build_packet(snapshot,roots,blob_get,*,independent=False,required_source_refs=(),sibling_tasks=(),max_bytes=MAX_CONTEXT_BYTES,include_method_sources=False,selection_modes=None):
    selected=relations.premise_closure(roots,snapshot,include_method_sources=include_method_sources)|set(required_source_refs)
    record_map={};bodies={};sources={};source_bodies={};read_set=[];input_manifest=[]
    allrecords=snapshot.get('records',{});all_sources=snapshot.get('sources',{})
    for ref in sorted(selected):
        if ref in allrecords:
            record=allrecords[ref]
            if independent:
                require(record['kind']!='Assessment','NON_SELF_CONTAINED','A verdict is not an independent proof premise')
                require(not _source_tainted(ref,snapshot),'FORBIDDEN_REVIEW_DERIVATIVE','Prior verdict or preparation derivative in independent input')
                producers=[p for p in snapshot.get('production_events',{}).values() if p.get('record_ref')==ref]
                require(not producers or not all(p.get('task_id') in sibling_tasks for p in producers),'FORBIDDEN_REVIEW_DERIVATIVE','Sibling output not an independent input')
            body=blob_get(record['body_sha256'])
            require(sha(body)==record['body_sha256'],'ORIGINAL_BYTES_MISMATCH',ref)
            if independent:
                # Declared review references inside a purported self-contained
                # proof cannot be silently omitted. Undeclared paraphrases need
                # scoped human/model assessment, not a lexical truth detector.
                for old,old_record in allrecords.items():
                    if old_record['kind']=='Assessment':require(old.encode() not in body,'NON_SELF_CONTAINED','Body depends on an earlier verdict')
            record_map[ref]=deepcopy(record);bodies[record['body_sha256']]=body
            object_ids=[oid for oid,o in snapshot.get('objects',{}).items() if ref in o.get('revisions',[]) or o.get('selected_revision')==ref]
            oid=sorted(object_ids)[0] if object_ids else None
            mode=(selection_modes or {}).get(ref,'PINNED')
            C.enum(mode,('PINNED','CURRENT'),'selection mode')
            supports=[p['support_ref'] for p in record['data'].get('premise_bindings',[]) if p.get('support_ref')]
            read_set.append({'record_ref':ref,'body_hash':record['body_sha256'],
                'selection_binding':{'mode':mode,'object_id':oid,'expected_revision':ref},
                'required_support_refs':supports,'scope':[],
                'qualification_guard':{s:C.digest(snapshot.get('supports',{}).get(s)) for s in supports}})
            input_manifest.append({'kind':'record','ref':ref,'sha256':C.digest(record),'body_sha256':record['body_sha256']})
            # All locator blobs are real supplied material, including exact
            # source fields preserved independently from a statement body.
            def locators(value):
                if isinstance(value,dict):
                    if set(value)==C.LOCATOR_FIELDS:
                        validate_locator(value,blob_get);bodies[value['blob_hash']]=blob_get(value['blob_hash'])
                    else:
                        for v in value.values():locators(v)
                elif isinstance(value,list):
                    for v in value:locators(v)
            locators(record['data'])
        elif ref in all_sources:
            source=all_sources[ref]
            if independent:require(not _source_tainted(ref,snapshot),'FORBIDDEN_REVIEW_DERIVATIVE','Source is review/preparation material or a derivative')
            h=source['blob_hash'];raw=blob_get(h)
            require(sha(raw)==h,'ORIGINAL_BYTES_MISMATCH',ref)
            sources[ref]=deepcopy(source);source_bodies[h]=raw
            input_manifest.append({'kind':'source','ref':ref,'sha256':h})
        elif ref in snapshot.get('inferences',{}):continue
        else:raise C.PMRSError('INCOMPLETE_CONTEXT','Required exact material missing: '+str(ref))
    byte_count=sum(len(b) for b in {**bodies,**source_bodies}.values())+len(canonical(record_map))+len(canonical(sources))
    require(byte_count<=max_bytes,'CONTEXT_LIMIT','Required full material exceeds frozen storage budget; create an explicit CoveragePlan')
    kept=[deepcopy(r) for r in relations.edges(snapshot) if r['source_ref'] in selected and r['target_ref'] in selected and relations.is_premise(r)]
    return {'records':record_map,'bodies':bodies,'sources':sources,'source_bodies':source_bodies,'roots':list(roots),
        'relations':kept,'read_set':read_set,'input_manifest':input_manifest,'input_manifest_hash':C.digest(input_manifest),
        'independent':independent,'excluded_verdicts':independent,'complete':True,'bytes':byte_count}

def token_preflight(serialized_request,capacity,*,reserved_output_tokens,prompt_overhead_tokens=0,safety_margin_tokens=0,token_counter=None):
    require(isinstance(serialized_request,bytes),'CONTEXT_LIMIT','Count the actual serialized request bytes')
    required={'model_id','capacity_source','capacity_revision','context_window_tokens','model_max_output_tokens','tokenizer_revision'}
    require(isinstance(capacity,dict) and required<=set(capacity),'CONTEXT_LIMIT','Missing frozen model capacity source or counter revision')
    require(all(isinstance(capacity[k],str) and capacity[k] for k in ('model_id','capacity_source','capacity_revision','tokenizer_revision')),'CONTEXT_LIMIT','Unknown model capacity/counter provenance')
    if token_counter is not None:
        count=token_counter(serialized_request);method='EXACT'
    else:
        require(capacity.get('tokenizer_byte_bound_verified') is True and capacity.get('token_count_bound')=='UTF8_BYTES',
            'CONTEXT_LIMIT','No exact tokenizer or attested conservative token bound for this model')
        count=len(serialized_request);method='CONSERVATIVE_BOUND'
    value={k:capacity[k] for k in required}
    value.update(reserved_output_tokens=reserved_output_tokens,prompt_overhead_tokens=prompt_overhead_tokens,
       safety_margin_tokens=safety_margin_tokens,input_tokens=count,token_count_method=method)
    validate_budget(value)
    return value

def validate_budget(value):
    C.fields(value,C.CONTEXT_BUDGET_FIELDS,'ContextBudget')
    for k in ('context_window_tokens','model_max_output_tokens','reserved_output_tokens','prompt_overhead_tokens','safety_margin_tokens','input_tokens'):
        require(type(value[k]) is int and 0<=value[k]<=C.MAX_INT,'CONTEXT_LIMIT','Invalid token count: '+k)
    require(0<value['reserved_output_tokens']<=value['model_max_output_tokens'],'CONTEXT_LIMIT','Output reserve outside model capacity')
    require(value['input_tokens']+value['prompt_overhead_tokens']+value['reserved_output_tokens']+value['safety_margin_tokens']<=value['context_window_tokens'],'CONTEXT_LIMIT','Full request plus output reserve exceeds model context')
    C.enum(value['token_count_method'],('EXACT','CONSERVATIVE_BOUND'),'token count method')
    require(all(isinstance(value[k],str) and value[k] for k in ('model_id','capacity_source','capacity_revision','tokenizer_revision')),'CONTEXT_LIMIT','Missing capacity/counter provenance')
    return value

def validate_coverage_plan(plan,requirement,*,part_packets=None):
    C.fields(plan,{'plan_id','target_revision_refs','required_scope','parts','integration_scope'},'CoveragePlan')
    validate_requirement(requirement);validate_scope(plan['required_scope'])
    require(plan['required_scope']==requirement['required_scope'],'RESPONSE_SCHEMA_INVALID','Coverage plan changed consumer scope')
    C.refs(plan['target_revision_refs'],'coverage targets',nonempty=True)
    slots={s['slot_id']:s for s in requirement['review_slots']};seen=set()
    for part in C.sequence(plan['parts'],'coverage parts'):
        C.fields(part,{'part_id','review_slot_id','checked_scope','required_input_refs','declared_boundary_refs','task_ref'},'coverage part')
        require(part['part_id'] not in seen and part['review_slot_id'] in slots,'RESPONSE_SCHEMA_INVALID','Unknown or duplicate coverage part/slot');seen.add(part['part_id'])
        validate_scope(part['checked_scope']);C.refs(part['required_input_refs'],'required inputs',nonempty=True);C.refs(part['declared_boundary_refs'],'boundaries')
        require(coverage(slots[part['review_slot_id']]['required_scope'],part['checked_scope'])['has_coverage'],'RESPONSE_SCHEMA_INVALID','Part outside requested scope')
        if part_packets is not None:
            packet=part_packets.get(part['part_id']);require(packet is not None,'INCOMPLETE_CONTEXT','Missing full part packet')
            require(set(part['required_input_refs'])<=set(packet['records'])|set(packet['sources']),'INCOMPLETE_CONTEXT','Part premises were omitted')
            validate_budget(packet['context_budget'])
    if plan['integration_scope']:validate_scope(plan['integration_scope'])
    return plan

def aggregate_coverage(plan,requirement,part_results,integration_result=None,*,empty_integration_attestation=None):
    validate_coverage_plan(plan,requirement);results={};complete=True
    for slot in requirement['review_slots']:
        checked=[]
        for part in plan['parts']:
            if part['review_slot_id']!=slot['slot_id']:continue
            result=part_results.get(part['part_id'],{})
            if result.get('result')=='QUALIFIED':checked+=result.get('checked_scope',[])
        result=coverage(slot['required_scope'],checked);results[slot['slot_id']]=result;complete &= result['complete']
    if plan['integration_scope']:
        integration_ok=bool(integration_result and integration_result.get('result')=='QUALIFIED' and integration_result.get('independent') and coverage(plan['integration_scope'],integration_result.get('checked_scope',[]))['complete'])
    else:
        integration_ok=bool(empty_integration_attestation and empty_integration_attestation.get('scope_reviewed') and empty_integration_attestation.get('reason'))
    complete &= integration_ok
    return {'result':'QUALIFIED' if complete else 'PARTIAL','slot_results':results,'integration_satisfied':integration_ok,
        'not_checked':[] if complete else [{'slot_id':sid,**r} for sid,res in results.items() for r in res['not_checked']]+([] if integration_ok else [{'integration_scope':plan['integration_scope'],'reason':'Independent interface review or explicit no-interface attestation missing'}])}

def freeze(obligation_binding,role,snapshot,*,blob_get,capacity=None,reserved_output_tokens=None,token_counter=None,independent=False):
    roots=obligation_binding.get('target_refs',[])
    packet=build_packet(snapshot,roots,blob_get,independent=independent)
    # Encode every supplied body verbatim; callers add prompt/schema/tool bytes
    # before dispatch and repeat this preflight on that complete request.
    wire={k:v for k,v in packet.items() if k not in ('bodies','source_bodies')}
    wire['body_text']={h:b.decode('utf-8') for h,b in packet['bodies'].items()}
    wire['source_text']={h:b.decode('utf-8') for h,b in packet['source_bodies'].items()}
    packet['context_budget']=token_preflight(canonical(wire),capacity or {},reserved_output_tokens=reserved_output_tokens or 0,token_counter=token_counter)
    return packet


def build_coverage_packet(snapshot,part,blob_get,*,independent=True,required_source_refs=(),sibling_tasks=()):
    """Supply declared target slices and every complete premise/boundary body.

    Slicing is explicit context evidence, never a changed scientific revision.
    The source locator, full original hash and omitted byte ranges stay visible.
    """
    validate_scope(part['checked_scope'])
    targets={x['target_ref'] for x in part['checked_scope']}
    full=set(part['required_input_refs'])|set(part['declared_boundary_refs'])
    require(targets.isdisjoint(full),'CONTEXT_LIMIT','A target required as a full premise cannot also be sliced')
    roots=sorted(targets|full)
    packet=build_packet(snapshot,roots,blob_get,independent=independent,required_source_refs=required_source_refs,
                        sibling_tasks=sibling_tasks,max_bytes=256*1024*1024)
    slices={}
    for ref in sorted(targets):
        require(ref in packet['records'],'INCOMPLETE_CONTEXT','Partial target must be an exact scientific record')
        h=packet['records'][ref]['body_sha256'];raw=blob_get(h)
        scopes=[row for row in part['checked_scope'] if row['target_ref']==ref]
        locs=[l for row in scopes for l in row['locators']]
        require(locs and all(l['blob_hash']==h for l in locs),'CONTEXT_LIMIT','Coverage slicing requires exact original target locators')
        entries=[{'locator':deepcopy(l),'text':validate_locator(l,blob_get).decode('utf-8')} for l in locs]
        packet['bodies'].pop(h,None)
        for item in packet['input_manifest']:
            if item.get('kind')=='record' and item['ref']==ref:item['body_coverage']={'state':'PARTIAL_TARGET_BODY','locators':deepcopy(locs)}
        for item in packet['read_set']:
            if item['record_ref']==ref:item['scope']=deepcopy(scopes)
        slices[ref]={'state':'PARTIAL_TARGET_BODY','original_blob_hash':h,'original_bytes':len(raw),
                     'checked_scope':deepcopy(scopes),'segments':entries,'unprovided_scope':'All original locations outside the explicitly supplied segments remain unprovided and unchecked.'}
    packet['partial_target_bodies']=slices;packet['complete']=False;packet['complete_for_declared_part']=True
    packet['input_manifest_hash']=C.digest(packet['input_manifest'])
    packet['bytes']=sum(len(b) for b in {**packet['bodies'],**packet['source_bodies']}.values())+len(canonical(slices))
    return packet
