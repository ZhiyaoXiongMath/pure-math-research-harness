"""Consumer, path and exact-scope assurance. No natural-language truth oracle."""
from copy import deepcopy
from . import contracts as C
from .util import require
from .knowledge import validate_locator
from .relations import affected_supports, validate_support_graph

PATHS={'MODEL_CAPTURE','HUMAN_ATTESTATION'}
PURPOSES={'PROOF_SUPPORT','REFUTATION_SUPPORT','APPLICABILITY','INTEGRATION','FORMULATION','WORK_CHECK'}
STAGE_ROLES={'APPLICABILITY':('APPLICABILITY_REVIEW','APPLICABILITY'),'INTEGRATION':('INDEPENDENT','INTEGRATION'),'FORMULATION':('FORMULATION_REVIEW','FORMULATION'),'WORK_CHECK':('WORK_CHECK','WORK_CHECK')}

def validate_scope(scope):
    require(isinstance(scope,list) and scope,'RESPONSE_SCHEMA_INVALID','Nonempty exact scope required')
    for row in scope:
        C.fields(row,C.SCOPE_FIELDS,'scope')
        require(isinstance(row['target_ref'],str) and row['target_ref'].startswith(('KR-','IB-')),'RESPONSE_SCHEMA_INVALID','Exact target required')
        C.refs(row['aspects'],'scope aspects',nonempty=True)
        require(isinstance(row['locators'],list),'RESPONSE_SCHEMA_INVALID','Scope locators list required')
        for loc in row['locators']:validate_locator(loc,None)
    return scope

def requirement(purpose,scope,*,review_mode=None,accepted_evidence_paths=None):
    review_mode=review_mode or ('SCOPED_SINGLE' if purpose in ('PROOF_SUPPORT','REFUTATION_SUPPORT') else 'STAGE_SPECIFIC')
    if review_mode=='TARGET_DUAL':pairs=[('PROOF','PROOF'),('COUNTEREXAMPLE','COUNTEREXAMPLE')]
    elif review_mode=='SCOPED_SINGLE':pairs=[('PROOF','PROOF')] if purpose=='PROOF_SUPPORT' else [('COUNTEREXAMPLE','COUNTEREXAMPLE')]
    else:pairs=[STAGE_ROLES[purpose]]
    paths=list(accepted_evidence_paths or ['MODEL_CAPTURE'])
    value={'purpose':purpose,'required_scope':deepcopy(scope),'accepted_evidence_paths':paths,'review_mode':review_mode,
      'review_slots':[{'slot_id':role.lower(),'allowed_roles':[role],'review_kind':kind,'required_scope':deepcopy(scope),'independence_required':True} for role,kind in pairs] if 'MODEL_CAPTURE' in paths else []}
    validate_requirement(value);return value

def validate_requirement(value):
    C.fields(value,C.ASSURANCE_FIELDS,'ConsumerAssuranceRequirement')
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
    return [{'target_ref':r['ref'],'locators':r['locators'],'aspects':[r['aspect']]} for r in assessment['data']['checked']]

def _intervals(scope,target,aspect,blob,unit):
    return sorted((l['start'],l['end']) for s in scope if s['target_ref']==target and aspect in s['aspects'] for l in s['locators'] if l['blob_hash']==blob and l['unit']==unit)

def coverage(required,checked):
    """Pure interval/aspect set coverage; no semantic extension or role pooling."""
    missing=[];covered=[]
    for row in required:
        for aspect in row['aspects']:
            if not row['locators']:
                ok=any(s['target_ref']==row['target_ref'] and aspect in s['aspects'] and not s['locators'] for s in checked)
                (covered if ok else missing).append({'target_ref':row['target_ref'],'locators':[],'aspects':[aspect]});continue
            for loc in row['locators']:
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
            if not x['locators'] or not y['locators']:return True
            for l in x['locators']:
                for r in y['locators']:
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
    base['open_conditions']=deepcopy(argument['data']['open_conditions'])+list(support.get('open_assumption_refs',[]))
    mode=argument['data']['mode'];payload=argument['data']['mode_payload']
    if mode=='REDUCTION':base['open_conditions']+=deepcopy(payload['inference_spec']['additional_assumption_refs'])
    elif mode=='APPLICABILITY':base['open_conditions']+=deepcopy(payload['open_conditions'])
    elif mode=='COMPATIBILITY':base['open_conditions']+=deepcopy(payload['witness_compatibility']['open_condition_refs'])
    # Conditional proofs qualify only explicitly conditional consumer scopes.
    if base['open_conditions'] and not all('conditional' in r['aspects'] or 'under_assumptions' in r['aspects'] for r in requirement['required_scope']):
        base['reasons']=['Open assumptions prevent unconditional support'];return base
    for dep in support.get('premise_support_refs',[]):
        ds=snapshot.get('supports',{}).get(dep,{})
        dr=ds.get('consumer_requirement')
        if not dr:base['reasons']=['Selected premise has no frozen assurance requirement'];return base
        result=evaluate_requirement(snapshot,dep,dr,ds.get('policy_digest'),_stack+(support_id,))
        if result['result']!='QUALIFIED':base['reasons']=['Selected premise support is '+result['result']];return base
    structural_error=_structural_support_conditions(snapshot,support,argument,_stack+(support_id,))
    if structural_error:base['reasons']=[structural_error];return base
    qs=[]
    for qid in support.get('qualification_refs',[]):
        q=snapshot.get('qualifications',{}).get(qid)
        if not q:continue
        a=snapshot.get('records',{}).get(q.get('assessment_ref'))
        if not a or a['kind']!='Assessment':continue
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
