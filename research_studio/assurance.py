"""Consumer, path and exact-scope assurance. No natural-language truth oracle."""
from copy import deepcopy
from . import contracts as C
from .util import require
from .knowledge import validate_locator
from .relations import affected_supports, validate_support_graph

PATHS={'MODEL_CAPTURE','HUMAN_ATTESTATION'}
PURPOSES={'PROOF_SUPPORT','REFUTATION_SUPPORT','APPLICABILITY','INTEGRATION','FORMULATION','WORK_CHECK'}
STAGE_ROLES={'APPLICABILITY':('APPLICABILITY_REVIEW','APPLICABILITY'),'INTEGRATION':('INDEPENDENT','INTEGRATION'),'FORMULATION':('FORMULATION_REVIEW','FORMULATION'),'WORK_CHECK':('WORK_CHECK','WORK_CHECK')}

SCOPE_VERSION='pmrs.exact-scope/1'
SCOPE_META={'scope_version','extent','target_body_sha256','whole_locator'}
ASSUMPTION_POLICY='pmrs.assumption-policy/1'
CONDITION_ROLES={'TARGET_HYPOTHESIS','DEFINITION_NORMALIZATION','DISCHARGED_CONDITION','ADDITIONAL_CONDITION'}


def validate_scope(scope):
    require(isinstance(scope,list) and scope,'RESPONSE_SCHEMA_INVALID','Nonempty exact scope required')
    for row in scope:
        C.optional_fields(row,C.SCOPE_FIELDS,SCOPE_META,'scope')
        require(isinstance(row['target_ref'],str) and row['target_ref'].startswith(('KR-','IB-')),'RESPONSE_SCHEMA_INVALID','Exact target required')
        C.refs(row['aspects'],'scope aspects',nonempty=True)
        require(isinstance(row['locators'],list),'RESPONSE_SCHEMA_INVALID','Scope locators list required')
        for loc in row['locators']:validate_locator(loc,None)
        if set(row)&SCOPE_META:
            require(SCOPE_META<=set(row) and row['scope_version']==SCOPE_VERSION,'RESPONSE_SCHEMA_INVALID','Complete exact scope codec required')
            C.enum(row['extent'],('WHOLE_TARGET','EXACT_REGIONS'),'scope extent')
            validate_locator(row['whole_locator'],None)
            whole=row['whole_locator'];require(whole['start']==0 and whole['blob_hash']==row['target_body_sha256'],'RESPONSE_SCHEMA_INVALID','Whole scope must bind the exact body from its beginning')
            require(not row['locators'] if row['extent']=='WHOLE_TARGET' else bool(row['locators']),'RESPONSE_SCHEMA_INVALID','Scope extent and regions differ')
            require(all(l['blob_hash']==whole['blob_hash'] and l['unit']==whole['unit'] and l['start']>=whole['start'] and l['end']<=whole['end'] for l in row['locators']),'RESPONSE_SCHEMA_INVALID','Region exceeds its exact whole body')
    return scope


def normalize_scope(scope,snapshot,blob_get):
    """Freeze a future exact scope. Never call this to promote old captures."""
    from .knowledge import locator
    validate_scope(scope);result=[]
    for row in scope:
        ref=row['target_ref'];backing=snapshot.get('inferences',{}).get(ref,{}).get('argument_ref',ref)
        record=snapshot.get('records',{}).get(backing)
        require(record is not None,'INCOMPLETE_CONTEXT','Exact scope target is missing')
        body=blob_get(record['body_sha256']);unit=row['locators'][0]['unit'] if row['locators'] else row.get('whole_locator',{}).get('unit','UTF8_BYTE')
        whole=locator(body,unit=unit)
        require(whole['blob_hash']==record['body_sha256'],'ORIGINAL_BYTES_MISMATCH','Scope body differs')
        for loc in row['locators']:
            validate_locator(loc,blob_get)
            require(loc['blob_hash']==whole['blob_hash'] and loc['unit']==unit,'RESPONSE_SCHEMA_INVALID','Scope regions must bind one exact body and unit')
        if row.get('scope_version'):
            require(row['whole_locator']==whole and row['target_body_sha256']==whole['blob_hash'],'ORIGINAL_BYTES_MISMATCH','Declared whole target is not the entire exact body')
        result.append({**deepcopy(row),'scope_version':SCOPE_VERSION,'extent':'EXACT_REGIONS' if row['locators'] else 'WHOLE_TARGET','target_body_sha256':whole['blob_hash'],'whole_locator':whole})
    validate_scope(result);return result


def normalize_requirement(value,snapshot,blob_get):
    result=deepcopy(value);result['required_scope']=normalize_scope(value['required_scope'],snapshot,blob_get)
    for slot in result['review_slots']:slot['required_scope']=normalize_scope(slot['required_scope'],snapshot,blob_get)
    validate_requirement(result);return result


def _scope_regions(row):
    if row.get('scope_version')==SCOPE_VERSION and row.get('extent')=='WHOLE_TARGET':return [row['whole_locator']]
    return row['locators']


def requirement(purpose,scope,*,review_mode=None,accepted_evidence_paths=None,assumption_policy=None):
    review_mode=review_mode or ('SCOPED_SINGLE' if purpose in ('PROOF_SUPPORT','REFUTATION_SUPPORT') else 'STAGE_SPECIFIC')
    if review_mode=='TARGET_DUAL':pairs=[('PROOF','PROOF'),('COUNTEREXAMPLE','COUNTEREXAMPLE')]
    elif review_mode=='SCOPED_SINGLE':pairs=[('PROOF','PROOF')] if purpose=='PROOF_SUPPORT' else [('COUNTEREXAMPLE','COUNTEREXAMPLE')]
    else:pairs=[STAGE_ROLES[purpose]]
    paths=list(accepted_evidence_paths or ['MODEL_CAPTURE'])
    value={'purpose':purpose,'required_scope':deepcopy(scope),'accepted_evidence_paths':paths,'review_mode':review_mode,
      'review_slots':[{'slot_id':role.lower(),'allowed_roles':[role],'review_kind':kind,'required_scope':deepcopy(scope),'independence_required':True} for role,kind in pairs] if 'MODEL_CAPTURE' in paths else []}
    if assumption_policy is not None:value['assumption_policy']=deepcopy(assumption_policy)
    validate_requirement(value);return value

def validate_requirement(value):
    C.optional_fields(value,C.ASSURANCE_FIELDS,{'assumption_policy'},'ConsumerAssuranceRequirement')
    if 'assumption_policy' in value:validate_assumption_policy(value['assumption_policy'])
    C.enum(value['purpose'],PURPOSES,'assurance purpose');validate_scope(value['required_scope'])
    C.refs(value['accepted_evidence_paths'],'evidence paths',nonempty=True)
    require(set(value['accepted_evidence_paths'])<=PATHS,'AUTHORIZATION_REQUIRED','FORMAL_TOOL is reserved and cannot be granted or consumed')
    C.enum(value['review_mode'],('SCOPED_SINGLE','TARGET_DUAL','STAGE_SPECIFIC'),'review mode')
    slots=C.sequence(value['review_slots'],'review slots');seen=set()
    for slot in slots:
        C.fields(slot,C.SLOT_FIELDS,'review slot');validate_scope(slot['required_scope'])
        C.refs(slot['allowed_roles'],'slot roles',nonempty=True)
        require(isinstance(slot['slot_id'],str) and slot['slot_id'] and slot['slot_id'] not in seen,'RESPONSE_SCHEMA_INVALID','Unique slot ID required')
        seen.add(slot['slot_id']);require(type(slot['independence_required']) is bool,'RESPONSE_SCHEMA_INVALID','Slot independence must be bool')
    if 'MODEL_CAPTURE' not in value['accepted_evidence_paths']:return value
    require(slots,'RESPONSE_SCHEMA_INVALID','Model path cannot have zero required slots')
    purpose=value['purpose'];mode=value['review_mode']
    if purpose in ('PROOF_SUPPORT','REFUTATION_SUPPORT'):
        require(mode in ('SCOPED_SINGLE','TARGET_DUAL'),'RESPONSE_SCHEMA_INVALID','Proof/refutation mode mismatch')
        expected=[('PROOF','PROOF'),('COUNTEREXAMPLE','COUNTEREXAMPLE')] if mode=='TARGET_DUAL' else [('PROOF','PROOF')] if purpose=='PROOF_SUPPORT' else [('COUNTEREXAMPLE','COUNTEREXAMPLE')]
        actual=sorted((s['allowed_roles'],s['review_kind']) for s in slots)
        require(actual==sorted(([r],k) for r,k in expected),'RESPONSE_SCHEMA_INVALID','Mode and slots differ')
        require(all(s['independence_required'] and s['required_scope']==value['required_scope'] for s in slots),'RESPONSE_SCHEMA_INVALID','Mode requires independent slots on same exact scope')
    else:
        require(mode=='STAGE_SPECIFIC','RESPONSE_SCHEMA_INVALID','Stage-specific purpose required')
        # Integration and formulation have fixed duties. Applicability/work checks
        # may use explicitly frozen StageSpec specialist roles, never proof slots.
        require(all(s['review_kind']==purpose for s in slots),'RESPONSE_SCHEMA_INVALID','Review kind cannot impersonate another purpose')
        if purpose in ('INTEGRATION','FORMULATION'):
            role,kind=STAGE_ROLES[purpose]
            require(len(slots)==1 and slots[0]['allowed_roles']==[role] and slots[0]['independence_required'],'RESPONSE_SCHEMA_INVALID','Stage-specific role mismatch')
    return value

def checked_scope(assessment):
    return [{'target_ref':r['ref'],'locators':r['locators'],'aspects':[r['aspect']],**{k:r[k] for k in SCOPE_META if k in r}} for r in assessment['data']['checked']]

def _intervals(scope,target,aspect,blob,unit):
    return sorted((l['start'],l['end']) for s in scope if s['target_ref']==target and aspect in s['aspects'] for l in _scope_regions(s) if l['blob_hash']==blob and l['unit']==unit)

def coverage(required,checked):
    """Pure interval/aspect set coverage; no semantic extension or role pooling."""
    missing=[];covered=[]
    for row in required:
        for aspect in row['aspects']:
            if not _scope_regions(row):
                ok=any(s['target_ref']==row['target_ref'] and aspect in s['aspects'] and not _scope_regions(s) for s in checked)
                (covered if ok else missing).append({'target_ref':row['target_ref'],'locators':[],'aspects':[aspect]});continue
            for loc in _scope_regions(row):
                cursor=loc['start'];gaps=[]
                for a,b in _intervals(checked,row['target_ref'],aspect,loc['blob_hash'],loc['unit']):
                    if b<=cursor or a>=loc['end']:continue
                    if a>cursor:gaps.append((cursor,min(a,loc['end'])))
                    cursor=max(cursor,b)
                    if cursor>=loc['end']:break
                if cursor<loc['end']:gaps.append((cursor,loc['end']))
                if gaps:
                    missing.append({'target_ref':row['target_ref'],'locators':[{**loc,'start':a,'end':b,'quoted_sha256':None} for a,b in gaps],'aspects':[aspect]})
                if cursor>loc['start'] or len(gaps)!=1 or gaps[0]!=(loc['start'],loc['end']):covered.append({'target_ref':row['target_ref'],'locators':[loc],'aspects':[aspect]})
    return {'complete':not missing,'checked_scope':deepcopy(checked),'not_checked':missing,'has_coverage':bool(covered)}

def scope_overlaps(a,b):
    for x in a:
        for y in b:
            if x['target_ref']!=y['target_ref'] or not set(x['aspects'])&set(y['aspects']):continue
            if not _scope_regions(x) or not _scope_regions(y):return True
            for l in _scope_regions(x):
                for r in _scope_regions(y):
                    if l['blob_hash']==r['blob_hash'] and l['unit']==r['unit'] and max(l['start'],r['start'])<min(l['end'],r['end']):return True
    return False

def _execution(snapshot,event_id):
    for name in ('review_executions','execution_events'):
        events=snapshot.get(name,{})
        if isinstance(events,dict) and event_id in events:return events[event_id]
    return None

def _credential(snapshot,q,assessment,policy_digest):
    if q.get('withdrawn') or not q.get('integrity_valid',True):return None,'Evidence withdrawn or damaged'
    if q.get('evidence_origin')=='FORMAL_TOOL' or q.get('formal_claim',False):return None,'Formal evidence is not enabled'
    if policy_digest and q.get('policy_digest')!=policy_digest and policy_digest not in q.get('compatible_policy_digests',[]):return None,'Policy requires requalification'
    if not (set(assessment['data']['target_refs'])-{r for r in assessment['data']['target_refs'] if r.startswith('IB-')})<=set(q.get('target_revision_hashes',[])):return None,'Targets not bound'
    for ref in assessment['data']['target_refs']:
        if ref.startswith('IB-') and snapshot.get('inferences',{}).get(ref,{}).get('argument_ref') not in q.get('target_revision_hashes',[]):return None,'Inference backing argument not bound'
    origin=q.get('evidence_origin');event=None
    if origin=='MODEL_CAPTURE':
        event=_execution(snapshot,q.get('review_execution_event'))
        if not event or event.get('input_manifest_hash')!=q.get('input_manifest_hash'):return None,'No authentic bound review execution'
        if not event.get('integrity_valid',False) or not event.get('excluded_verdicts',False):return None,'Review input integrity/isolation absent'
        if event.get('task_id') in snapshot.get('tasks',{}) and snapshot['tasks'][event['task_id']].get('communication_contract'):
            from .communication import independence_status
            if not independence_status(snapshot,event['task_id'])['independent']:return None,'Execution consumed shared scientific communication; it is not an independent vote'
        if event.get('synthetic',False) and not snapshot.get('synthetic_test_only',False):return None,'Synthetic evidence cannot qualify a real project'
        if not set(q.get('target_revision_hashes',[]))<=set(event.get('target_revision_hashes',[])):return None,'Execution target binding differs'
    elif origin=='HUMAN_ATTESTATION':
        event=snapshot.get('human_attestations',{}).get(q.get('attestation_ref'))
        if not event or event.get('kind')!='SCOPED_MATHEMATICAL_ATTESTATION' or not event.get('explicit_check'):return None,'Adoption is not a human check'
        if not set(q.get('target_revision_hashes',[]))<=set(event.get('target_revision_hashes',[])) or not coverage(q.get('actual_checked_scope',[]),event.get('checked_scope',[]))['complete']:return None,'Human attestation does not bind the exact target and checked scope'
    else:return None,'Evidence origin unsupported'
    return event,None

def coverage_plan_evidence(snapshot,plan_id):
    """Recompute a plan from authentic accepted captures, never a status label."""
    from .context import aggregate_coverage
    row=snapshot.get('coverage_plans',{}).get(plan_id)
    require(row is not None,'INCOMPLETE_CONTEXT','Coverage plan missing')
    plan=row['plan'];req=row['requirement'];support=snapshot.get('supports',{}).get(row['support_id'],{})
    slots={x['slot_id']:x for x in req['review_slots']};parts={x['part_id']:x for x in plan['parts']}
    results={};integration=None
    for task in snapshot.get('tasks',{}).values():
        if task.get('coverage_plan_id')!=plan_id:continue
        request=snapshot.get('requests',{}).get(task.get('request_id'),{})
        if request.get('acceptance_state')!='ACCEPTED':continue
        part_id=task.get('coverage_part_id');part=parts.get(part_id)
        if part_id and part is None:continue
        scope=part['checked_scope'] if part else plan['integration_scope']
        if not scope:continue
        slot=slots[part['review_slot_id']] if part else {'allowed_roles':['INDEPENDENT'],'review_kind':'INTEGRATION'}
        checked=[];defect=False;valid_events=set()
        for q in snapshot.get('qualifications',{}).values():
            if q.get('review_execution_event')!=request.get('execution_id'):continue
            assessment=snapshot.get('records',{}).get(q.get('assessment_ref'))
            if not assessment or assessment['kind']!='Assessment':continue
            event,error=_credential(snapshot,q,assessment,C.digest(req))
            if error or not event or event.get('task_id')!=task['task_id'] or not event.get('independent'):continue
            if event.get('role') not in slot['allowed_roles'] or assessment['data']['review_kind']!=slot['review_kind']:continue
            if event.get('task_id')==support.get('author_task_id') or q['review_execution_event']==support.get('author_execution_event'):continue
            actual=q.get('actual_checked_scope',checked_scope(assessment))
            if not coverage(actual,checked_scope(assessment))['complete']:continue
            if assessment['data']['verdict']=='DEFECT_FOUND' and scope_overlaps(scope,actual):defect=True
            if assessment['data']['verdict']=='SUPPORTED_WITHIN_SCOPE':checked+=actual;valid_events.add(q['review_execution_event'])
        complete=not defect and coverage(scope,checked)['complete'] and bool(valid_events)
        result={'result':'QUALIFIED' if complete else 'PARTIAL','checked_scope':checked,'independent':bool(valid_events),'execution_events':sorted(valid_events)}
        if part_id:results[part_id]=result
        else:integration=result
    # One capture cannot be counted as both a part review and integration.
    if integration and set(integration['execution_events'])&{e for p in results.values() for e in p['execution_events']}:
        integration={**integration,'result':'PARTIAL','independent':False}
    return aggregate_coverage(plan,req,results,integration),results,integration


def _part_consumable(snapshot,event,requirement,cache):
    task=snapshot.get('tasks',{}).get(event.get('task_id'),{});pid=task.get('coverage_plan_id')
    if not pid or not task.get('coverage_part_id'):return True
    row=snapshot.get('coverage_plans',{}).get(pid)
    if row is None:return False
    part=next((p for p in row['plan']['parts'] if p['part_id']==task['coverage_part_id']),None)
    if part and coverage(requirement['required_scope'],part['checked_scope'])['complete']:return True
    if pid not in cache:cache[pid]=coverage_plan_evidence(snapshot,pid)[0]
    return cache[pid]['result']=='QUALIFIED'


def _structural_support_conditions(snapshot,support,argument,stack):
    """Consume explicit inference duties without treating structure as a proof."""
    data=argument['data'];mode=data['mode'];payload=data['mode_payload']
    def qualified_path(sid):
        selected=snapshot.get('supports',{}).get(sid,{})
        req=selected.get('consumer_requirement')
        return bool(req and evaluate_requirement(snapshot,sid,req,selected.get('policy_digest'),stack)['result']=='QUALIFIED')
    def qualified_argument(ref):
        return any(qualified_path(sid) for sid,p in snapshot.get('supports',{}).items() if p.get('argument_ref')==ref)
    if mode=='REDUCTION':
        inference=payload['inference_spec']
        for check_name in ('lifting_check','compatibility_check'):
            check=inference[check_name]
            if check['status']=='REQUIRED':
                for oid in check['obligation_ids']:
                    duty=snapshot.get('obligations',{}).get(oid,{})
                    definition=duty.get('definition',{});projection=duty.get('projection',{})
                    consumers=definition.get('consumer_bindings',[])
                    if (definition.get('type') not in ('APPLICABILITY','COMPATIBILITY','VERIFY') or
                        projection.get('resolution')!='SATISFIED_FOR_CONSUMER' or not consumers or
                        not any(c.get('threshold',c.get('required_threshold'))=='SUPPORT_QUALIFIED' for c in consumers)):
                        return 'Reduction '+check_name+' remains an open mathematical duty'
                    mathematical=[c for c in consumers if c.get('threshold',c.get('required_threshold'))=='SUPPORT_QUALIFIED']
                    for consumer in mathematical:
                        selected=consumer.get('selected_support_refs',consumer.get('selected_supports',consumer.get('selected_support')))
                        selected=[selected] if isinstance(selected,str) else selected
                        needed=consumer.get('required_assurance')
                        if not needed or not selected or not any(evaluate_requirement(snapshot,sid,needed,consumer.get('policy_digest'),stack)['result']=='QUALIFIED' for sid in selected):
                            return 'Reduction '+check_name+' qualification is no longer valid'
        if inference['operator']=='AND':
            bindings={b['premise_ref']:b for b in data['premise_bindings']}
            for ref in inference['premise_refs']:
                binding=bindings.get(ref)
                if not binding:return 'AND child has no exact qualified or conditional premise binding'
                if binding['kind']=='SUPPORTED_STATEMENT':
                    sid=binding['support_ref'];selected=snapshot.get('supports',{}).get(sid,{})
                    if selected.get('statement_ref')!=ref or not qualified_path(sid):return 'AND child support remains unqualified'
                elif binding['kind']=='DERIVATION_COMPONENT':
                    if not qualified_argument(ref):return 'AND component remains unqualified'
                elif binding['kind'] not in ('DEFINITION','CONTEXT_ASSUMPTION','CONDITIONAL_CANDIDATE'):
                    return 'AND child has no supported premise'
        elif not any(qualified_argument(ref) for ref in inference['alternative_argument_refs']):
            return 'No OR alternative has a complete qualified reduction and applicability path'
    if mode=='COMPATIBILITY':
        witness=payload['witness_compatibility']
        if not witness['variable_mapping'] or not witness['quantifier_locators'] or not (witness['common_data_refs'] or witness['evidence_refs']):
            return 'A common witness requires explicit variable, quantifier and compatibility evidence bindings'
        if any(not qualified_argument(ref) for ref in witness['component_argument_refs']):return 'A witness component remains unqualified'
    return None


def evaluate_requirement(snapshot,support_id,requirement,policy_digest=None,_stack=()):
    validate_requirement(requirement);support=snapshot.get('supports',{}).get(support_id)
    base={'consumer_requirement_digest':C.digest(requirement),'support_id':support_id,'review_mode':requirement['review_mode'],'result':'UNQUALIFIED','checked_scope':[],'not_checked':deepcopy(requirement['required_scope']),'missing_slots':[s['slot_id'] for s in requirement['review_slots']],'assurance_sources':[],'open_conditions':[],'reasons':[],'slot_results':{}}
    if not support:base['reasons']=['No argument/support path'];return base
    require(support_id not in _stack,'CYCLIC_MATH_SUPPORT',support_id)
    direct_withdrawals={w.get('support_id') for w in snapshot.get('withdrawals',{}).values() if w.get('active',True)
       and (w.get('scope') is None or scope_overlaps(w['scope'],requirement['required_scope']))}
    if support_id in direct_withdrawals:base.update(result='WITHDRAWN',reasons=['Exact support withdrawn']);return base
    if support.get('needs_recheck'):base['reasons']=['A selected premise support needs recheck'];return base
    argument=snapshot.get('records',{}).get(support.get('argument_ref'))
    if not argument or argument['kind']!='Argument' or argument['data']['conclusion_ref']!=support.get('statement_ref'):
        base['reasons']=['Missing or mismatched argument'];return base
    if not support.get('integrity_valid',True):base['reasons']=['Argument or premise bytes damaged'];return base
    assumptions=_assumption_evaluation(snapshot,support,argument,requirement,_stack+(support_id,))
    base.update({k:v for k,v in assumptions.items() if k!='blocking_reasons'})
    blockers=list(assumptions['blocking_reasons'])
    for dep in support.get('premise_support_refs',[]):
        ds=snapshot.get('supports',{}).get(dep,{});dr=ds.get('consumer_requirement')
        if not dr:blockers.append('Selected premise has no frozen assurance requirement');continue
        result=evaluate_requirement(snapshot,dep,dr,ds.get('policy_digest'),_stack+(support_id,))
        if result['result']!='QUALIFIED':blockers.append('Selected premise support is '+result['result'])
    structural_error=_structural_support_conditions(snapshot,support,argument,_stack+(support_id,))
    if structural_error:blockers.append(structural_error)
    # Typed policy is part of this consumer's immutable identity. Old evidence
    # cannot be promoted merely by replacing a legacy free-form aspect label.
    if requirement.get('assumption_policy'):
        expected_policy=C.digest(requirement)
        if policy_digest is not None and policy_digest!=expected_policy:blockers.append('Typed assurance policy digest does not match this exact consumer')
        policy_digest=expected_policy
    qs=[];base['review_evidence']=[];base['accepted_checked_scope']=[]
    for qid in support.get('qualification_refs',[]):
        q=snapshot.get('qualifications',{}).get(qid)
        if not q:continue
        a=snapshot.get('records',{}).get(q.get('assessment_ref'))
        if not a or a['kind']!='Assessment':continue
        base['accepted_checked_scope']+=checked_scope(a)
        base['review_evidence'].append({'qualification_ref':qid,'assessment_ref':q['assessment_ref'],'accepted':True,'verdict':a['data']['verdict'],'checked_scope':checked_scope(a)})
        # A new consumer policy may require additional positive evidence, but it
        # cannot erase an authentic defect on the same exact mathematical scope.
        event,error=_credential(snapshot,q,a,None if a['data']['verdict']=='DEFECT_FOUND' else policy_digest)
        if error:base['reasons'].append(error);continue
        scope=q.get('actual_checked_scope',checked_scope(a))
        require(coverage(scope,checked_scope(a))['complete'],'RESPONSE_SCHEMA_INVALID','Qualification exceeds assessment scope')
        if a['data']['verdict']=='DEFECT_FOUND' and scope_overlaps(requirement['required_scope'],scope):
            base.update(result='CONFLICTED',reasons=['Active defect affecting this support path']);return base
        qs.append((q,a,event,scope))
    for conflict in snapshot.get('conflicts',{}).values():
        if conflict.get('active',True) and conflict.get('statement_ref')==support['statement_ref'] and scope_overlaps(requirement['required_scope'],conflict['scope']):
            base.update(result='CONFLICTED',reasons=['Explicit scoped support/refutation conflict']);return base
    allowed=requirement['accepted_evidence_paths'];allchecked=[];used_events=set();slot_event_options={};plan_cache={}
    for slot in requirement['review_slots']:
        checked=[];events=set()
        for q,a,event,scope in qs:
            if q['evidence_origin']!='MODEL_CAPTURE' or 'MODEL_CAPTURE' not in allowed:continue
            if event.get('role') not in slot['allowed_roles'] or a['data']['review_kind']!=slot['review_kind']:continue
            if slot['independence_required'] and (not event.get('independent') or q['review_execution_event']==support.get('author_execution_event') or event.get('task_id')==support.get('author_task_id')):continue
            if a['data']['verdict']=='SUPPORTED_WITHIN_SCOPE':
                if not _part_consumable(snapshot,event,requirement,plan_cache):
                    allchecked+=scope
                    if 'Independent coverage integration remains incomplete' not in base['reasons']:base['reasons'].append('Independent coverage integration remains incomplete')
                    continue
                checked+=scope;events.add(q['review_execution_event'])
            elif a['data']['verdict']=='INCONCLUSIVE':allchecked+=scope
        cv=coverage(slot['required_scope'],checked);base['slot_results'][slot['slot_id']]={**cv,'execution_events':sorted(events)}
        slot_event_options[slot['slot_id']]=events
        allchecked+=checked
    # Distinct execution events must admit a matching for independent slots.
    slots=requirement['review_slots']
    def match(i,used):
        if i==len(slots):return True
        s=slots[i]
        if not base['slot_results'][s['slot_id']]['complete']:return False
        for event in slot_event_options[s['slot_id']]-used:
            if match(i+1,used|{event}):return True
        return False
    model_ok='MODEL_CAPTURE' in allowed and bool(slots) and match(0,set())
    other_ok=False
    for origin,label in [('HUMAN_ATTESTATION','HUMAN_ATTESTED')]:
        if origin not in allowed:continue
        checked=[]
        for q,a,event,scope in qs:
            if q['evidence_origin']==origin and a['data']['verdict']=='SUPPORTED_WITHIN_SCOPE' and a['data']['review_kind'] in {s['review_kind'] for s in slots} | {requirement['purpose'].removesuffix('_SUPPORT')}:
                checked+=scope
        if coverage(requirement['required_scope'],checked)['complete']:other_ok=True;base['assurance_sources'].append(label)
        allchecked+=checked
    if model_ok:base['assurance_sources'].append('MODEL_CROSSCHECKED')
    base['checked_scope']=allchecked
    base['missing_slots']=[s['slot_id'] for s in slots if not base['slot_results'][s['slot_id']]['complete']]
    if model_ok or other_ok:base.update(result='QUALIFIED',not_checked=[],missing_slots=[])
    else:
        base['not_checked']=[{'slot_id':s['slot_id'],**r} for s in slots for r in base['slot_results'][s['slot_id']]['not_checked']] or coverage(requirement['required_scope'],allchecked)['not_checked']
        if coverage(requirement['required_scope'],allchecked)['has_coverage']:base['result']='PARTIAL'
        if not base['reasons']:base['reasons']=['Required exact scope or independent review slots remain incomplete']
    base['review_coverage_result']=base['result']
    if blockers:
        base['qualification_blockers']=list(dict.fromkeys(blockers))
        base['reasons']=list(dict.fromkeys(blockers+base['reasons']))
        base['result']='PARTIAL' if base['result']=='PARTIAL' else 'UNQUALIFIED'
    else:base['qualification_blockers']=[]
    return base

def evaluate(statement_ref,consumer_binding,snapshot):
    req=consumer_binding['required_assurance'];validate_requirement(req)
    selected=consumer_binding.get('selected_support_refs',consumer_binding.get('selected_supports',consumer_binding.get('selected_support')))
    if isinstance(selected,str):selected=[selected]
    paths=selected if selected is not None else [k for k,s in snapshot.get('supports',{}).items() if s['statement_ref']==statement_ref]
    results=[evaluate_requirement(snapshot,s,req,consumer_binding.get('policy_digest')) for s in paths]
    good=[r for r in results if r['result']=='QUALIFIED'];conflict=any(r['result']=='CONFLICTED' for r in results)
    # A path-local defect does not invalidate an independent qualified path.
    explicit_conflict=any(c.get('active',True) and c.get('statement_ref')==statement_ref and scope_overlaps(c['scope'],req['required_scope']) for c in snapshot.get('conflicts',{}).values())
    state='CONFLICTED' if explicit_conflict or conflict and not good else 'SUPPORTED_WITHIN_SCOPE' if good else 'SUPPORT_WITHDRAWN' if results and all(r['result']=='WITHDRAWN' for r in results) else 'CANDIDATE' if paths else 'NO_ARGUMENT'
    conditional=any(r['open_conditions'] for r in results)
    outcome='CONFLICTED' if state=='CONFLICTED' else 'CONDITIONAL' if conditional else ('SCOPED_REFUTATION' if req['purpose']=='REFUTATION_SUPPORT' else 'SUPPORTED_ASSERTION') if good else 'OPEN'
    return {'statement_ref':statement_ref,'support_state':state,'claim_outcome':outcome,'support_paths':results,'assurance_sources':sorted({x for r in results for x in r['assurance_sources']}) or ['UNREVIEWED'],'open_conditions':[x for r in results for x in r['open_conditions']],'checked_scope':[x for r in results for x in r['checked_scope']],'not_checked':[] if good and not explicit_conflict else [x for r in results for x in r['not_checked']] or req['required_scope']}


def validate_assumption_policy(policy):
    C.fields(policy,{'schema','statement_ref','bindings','accepted_condition_refs'},'AssumptionPolicy')
    require(policy['schema']==ASSUMPTION_POLICY and isinstance(policy['statement_ref'],str) and policy['statement_ref'].startswith('KR-'),'RESPONSE_SCHEMA_INVALID','Versioned exact-statement assumption policy required')
    C.refs(policy['accepted_condition_refs'],'accepted condition refs')
    seen=set()
    for row in C.sequence(policy['bindings'],'typed assumption bindings'):
        C.fields(row,{'role','premise_ref','context_ref','assumption_locator','hypothesis_locator','argument_ref','support_ref'},'AssumptionPolicy.binding')
        C.enum(row['role'],CONDITION_ROLES,'condition role')
        require(isinstance(row['premise_ref'],str) and isinstance(row['argument_ref'],str),'RESPONSE_SCHEMA_INVALID','Exact premise and argument required')
        for name in ('context_ref','support_ref'):require(row[name] is None or isinstance(row[name],str),'RESPONSE_SCHEMA_INVALID','Nullable exact reference required')
        for name in ('assumption_locator','hypothesis_locator'):
            if row[name] is not None:validate_locator(row[name],None)
        identity=C.digest(row);require(identity not in seen,'RESPONSE_SCHEMA_INVALID','Duplicate typed condition binding');seen.add(identity)
    return policy


def condition_evidence(argument_ref,argument):
    """Persist actual use separately from a consumer's permitted hypotheses."""
    return {'schema':'pmrs.condition-evidence/1','argument_ref':argument_ref,'statement_ref':argument['data']['conclusion_ref'],
        'premise_bindings':deepcopy(argument['data']['premise_bindings']),
        'open_conditions':deepcopy(argument['data']['open_conditions']),
        'discharged_assumptions':deepcopy(argument['data']['discharged_assumptions'])}


def declared_assumption_policy(snapshot,statement_ref,argument_ref,*,accepted_condition_refs=()):
    """Construct a future policy from exact locator equality, never wording.

    An unmatched assumption remains unmatched and blocks qualification. This
    helper does not label all Context premises as discharged or target facts.
    The caller must freeze the returned policy in a newly authorized consumer.
    """
    statement=snapshot.get('records',{}).get(statement_ref,{})
    argument=snapshot.get('records',{}).get(argument_ref,{})
    require(statement.get('kind')=='Statement' and argument.get('kind')=='Argument' and argument['data']['conclusion_ref']==statement_ref,'RELATION_ENDPOINT_INVALID','Exact statement and argument required')
    bindings=[];hypotheses=statement['data']['hypothesis_locators']
    for p in argument['data']['premise_bindings']:
        if p['kind']=='CONTEXT_ASSUMPTION' and p['assumption_locator'] in hypotheses:
            bindings.append({'role':'ADDITIONAL_CONDITION' if p['premise_ref'] in accepted_condition_refs else 'TARGET_HYPOTHESIS',
                'premise_ref':p['premise_ref'],'context_ref':p['context_ref'],'assumption_locator':deepcopy(p['assumption_locator']),
                'hypothesis_locator':deepcopy(p['assumption_locator']),'argument_ref':argument_ref,'support_ref':None})
        elif p['kind']=='CONDITIONAL_CANDIDATE' and p['premise_ref'] in accepted_condition_refs:
            candidate=snapshot['records'].get(p['premise_ref'],{})
            loc=candidate.get('data',{}).get('statement_locator')
            if loc in hypotheses:bindings.append({'role':'ADDITIONAL_CONDITION','premise_ref':p['premise_ref'],'context_ref':p['context_ref'],
                'assumption_locator':None,'hypothesis_locator':deepcopy(loc),'argument_ref':argument_ref,'support_ref':None})
    result={'schema':ASSUMPTION_POLICY,'statement_ref':statement_ref,'bindings':bindings,'accepted_condition_refs':list(accepted_condition_refs)}
    validate_assumption_policy(result);return result


def _assumption_evaluation(snapshot,support,argument,requirement,stack):
    policy=requirement.get('assumption_policy');data=argument['data']
    raw_conditions=deepcopy(data['open_conditions'])+list(support.get('open_assumption_refs',[]))
    if data['mode']=='REDUCTION':raw_conditions+=deepcopy(data['mode_payload']['inference_spec']['additional_assumption_refs'])
    elif data['mode']=='APPLICABILITY':raw_conditions+=deepcopy(data['mode_payload']['open_conditions'])
    elif data['mode']=='COMPATIBILITY':raw_conditions+=deepcopy(data['mode_payload']['witness_compatibility']['open_condition_refs'])
    result={'policy_digest':C.digest(policy) if policy else None,'policy_version':policy.get('schema') if policy else 'LEGACY_ASPECT_POLICY',
        'declared_context':[],'remaining_assumptions':deepcopy(raw_conditions),'open_conditions':deepcopy(raw_conditions),'blocking_reasons':[]}
    if policy is None:
        if raw_conditions and not all('conditional' in r['aspects'] or 'under_assumptions' in r['aspects'] for r in requirement['required_scope']):result['blocking_reasons']=['Open assumptions prevent unconditional support']
        return result
    statement=snapshot.get('records',{}).get(support['statement_ref'],{})
    if policy['statement_ref']!=support['statement_ref'] or not any(r['target_ref']==support['statement_ref'] for r in requirement['required_scope']):
        result['blocking_reasons']=['Typed assumptions apply only to this exact consumer statement; they cannot strengthen another target'];return result
    # No historical support is silently reclassified by a newly introduced
    # policy. Its new evidence must bind this policy in _credential below.
    hypotheses=statement.get('data',{}).get('hypothesis_locators',[]);remaining=[];declared={};accepted=set(policy['accepted_condition_refs'])
    def bound(p,role=None):
        return [b for b in policy['bindings'] if b['argument_ref']==support['argument_ref'] and b['premise_ref']==p['premise_ref'] and b['context_ref']==p['context_ref'] and b['assumption_locator']==p['assumption_locator'] and (role is None or b['role']==role)]
    def exact_additional_condition(ref,item):
        if ref not in accepted:return False
        native=snapshot.get('records',{}).get(ref,{})
        matches=[]
        for b in policy['bindings']:
            if b['role']!='ADDITIONAL_CONDITION' or b['argument_ref']!=support['argument_ref'] or b['premise_ref']!=ref or b['support_ref'] is not None or b['hypothesis_locator'] not in hypotheses:continue
            if native.get('kind')=='Statement':
                if b['assumption_locator'] is None and b['hypothesis_locator']==native['data']['statement_locator'] and (b['context_ref'] is None or b['context_ref'] in native['data']['scope_context_refs']):matches.append(b)
            elif native.get('kind')=='Context':
                loc=b['assumption_locator']
                if b['context_ref']==ref and b['hypothesis_locator']==loc and loc in [x['locator'] for x in native['data']['assumptions']] and (not isinstance(item,dict) or item.get('locator')==loc):matches.append(b)
        return len(matches)==1
    for p in data['premise_bindings']:
        if p['kind']=='CONTEXT_ASSUMPTION':
            choices=bound(p);valid=[]
            for b in choices:
                if b['role'] in {'TARGET_HYPOTHESIS','ADDITIONAL_CONDITION'}:
                    actual=snapshot.get('records',{}).get(p['context_ref'],{}).get('data',{}).get('assumptions',[])
                    if b['hypothesis_locator']!=p['assumption_locator'] or b['hypothesis_locator'] not in hypotheses or p['assumption_locator'] not in [x['locator'] for x in actual]:continue
                    if b['role']=='ADDITIONAL_CONDITION' and p['premise_ref'] not in accepted:continue
                    valid.append(b)
                elif b['role']=='DISCHARGED_CONDITION' and p['assumption_locator'] in data['discharged_assumptions'] and b['support_ref']:
                    discharge=snapshot.get('supports',{}).get(b['support_ref'],{})
                    req=discharge.get('consumer_requirement')
                    if req and discharge.get('statement_ref')==p['premise_ref'] and evaluate_requirement(snapshot,b['support_ref'],req,discharge.get('policy_digest'),stack)['result']=='QUALIFIED':valid.append(b)
            if len(valid)==1:
                b=valid[0]
                if b['role']=='ADDITIONAL_CONDITION':remaining.append(p['premise_ref'])
                else:declared.setdefault(p['premise_ref'],[]).append(p['assumption_locator']);result['declared_context'].append(deepcopy(b))
            else:
                remaining.append(p['premise_ref']);result['blocking_reasons'].append('Context assumption lacks one exact declared-hypothesis or discharged-condition binding: '+p['premise_ref'])
        elif p['kind']=='CONDITIONAL_CANDIDATE':
            candidate=snapshot.get('records',{}).get(p['premise_ref'],{})
            matches=[b for b in bound(p,'ADDITIONAL_CONDITION') if b['hypothesis_locator'] in hypotheses and b['hypothesis_locator']==candidate.get('data',{}).get('statement_locator')]
            remaining.append(p['premise_ref'])
            if p['premise_ref'] not in accepted or len(matches)!=1:result['blocking_reasons'].append('An unresolved candidate is not explicitly accepted by this conditional consumer: '+p['premise_ref'])
    for item in raw_conditions:
        ref=item.get('condition_ref') if isinstance(item,dict) else item
        if ref in declared and (not isinstance(item,dict) or item.get('locator') in declared[ref]):continue
        if item not in remaining:remaining.append(deepcopy(item))
        if not exact_additional_condition(ref,item):
            result['blocking_reasons'].append('An open or inherited condition remains outside the exact consumer policy: '+str(ref))
    # The allow-list cannot bless an unrelated conditional statement or an
    # unlabeled Context without one of the precise bindings above.
    used={p['premise_ref'] for p in data['premise_bindings']}|{x.get('condition_ref') if isinstance(x,dict) else x for x in raw_conditions}
    if accepted-used:result['blocking_reasons'].append('Conditional policy lists conditions absent from this argument')
    result['remaining_assumptions']=remaining;result['open_conditions']=remaining
    return result
