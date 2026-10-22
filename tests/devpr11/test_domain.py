"""S1 exact native policy pairs, never persisted integration evidence."""
from copy import deepcopy
import unittest
from pmrh.domain.primitives import canonical,sha,PMRSError
from pmrh.domain import knowledge as K,assurance as A
from pmrh.domain.fastmath.model import FastMathError,revision_ref,make_revision
from pmrh.domain.fastmath.validation import validate_delta,native_projection,claim_fingerprint
from pmrh.domain.fastmath.qualification import qualify_binding,project
from .fixtures import semantic_fixture,six_entries,delta_for,add_exact_path


def rehash(entry):
    row=entry['body'];row['payload_sha256']=sha(canonical(row['payload']));row['body_sha256']=sha(row['body'].encode())
    entry['ref']=revision_ref(row)
    return entry


class DomainTests(unittest.TestCase):
    def fixture(self):
        f,task,target,arg,sid=semantic_fixture()
        entries=six_entries(f.s,task,argument_ref=arg,support_ids=[sid])
        return f,task,target,arg,sid,entries

    def test_FM01_six_useful_closed_kinds_and_missing_interface(self):
        f,t,_,_,_,entries=self.fixture();delta=delta_for(f.s,t,entries)
        revisions=validate_delta(delta,f.s)
        self.assertEqual({r['kind'] for r in revisions.values()}, {'KnowledgeModule','Transition','ResearchMap','Frontier/Probe','ReaderProfile','RefinementBinding'})
        self.assertEqual(canonical(delta),canonical(__import__('json').loads(canonical(delta))))
        for key in ('input_refs','output_ref','mechanism'):
            bad=deepcopy(delta);bad['revision_entries'][0]['body']['payload'].pop(key);rehash(bad['revision_entries'][0])
            with self.assertRaises(FastMathError):validate_delta(bad,f.s)
        bad=deepcopy(delta);bad['revision_entries'][0]['body']['checked']=True
        with self.assertRaises(FastMathError):validate_delta(bad,f.s)

    def test_FM02_native_quantifier_order_and_conditions_cannot_be_rewritten(self):
        f,t,target,arg,sid,entries=self.fixture()
        good=entries[0];self.assertEqual(good['body']['payload']['claim_slots']['result'],native_projection(f.s,target,arg))
        for field,replacement in [('quantifier_locators',[]),('hypothesis_locators',[f.s['records'][target]['data']['statement_locator']])]:
            bad=deepcopy(good);bad['body']['payload']['claim_slots']['result']['statement_fields'][field]=replacement;rehash(bad)
            with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[bad]),f.s)
        bad=deepcopy(good);bad['body']['payload']['claim_slots']['result']['argument_fields']['witness_bindings']=[{'variable':'invented'}];rehash(bad)
        with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[bad]),f.s)

    def test_FM03_exact_support_policy_and_self_review_rejection(self):
        f,t,_,_,_,entries=self.fixture();validate_delta(delta_for(f.s,t,entries),f.s)
        binding=entries[-1]['body'];upper=entries[0]['body']
        self.assertEqual(qualify_binding(binding,upper,f.s)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        bad=deepcopy(f.s);bad['review_executions']['review-event']['independent']=False
        self.assertEqual(qualify_binding(binding,upper,bad)['support_basis'],'OPEN')
        wrong=deepcopy(entries);wrong[-1]['body']['payload']['policy_digest']='0'*64;rehash(wrong[-1])
        with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,wrong),f.s)

    def test_FM04_forward_native_argument_does_not_support_reverse_or_equivalence(self):
        from tests.test_final_kernel import AssuranceContextTests,statement
        f,t,target,arg,sid,entries=self.fixture();helper=AssuranceContextTests()
        end=f.add(statement('The scoped consequence follows.'))
        premise=dict(premise_ref=target,kind='SUPPORTED_STATEMENT',context_ref=None,scope_locator=None,binding_mode='PINNED',support_ref=sid,assumption_locator=None)
        a,s,req=add_exact_path(f,end,'The known premise implies the exact scoped consequence.',premises=[premise])
        f.s['instances'][t['instance_id']]['target_ref']=end
        f.s['supports'][s]['policy_digest']=sha(canonical(req))
        for q in f.s['supports'][s]['qualification_refs']:f.s['qualifications'][q]['policy_digest']=sha(canonical(req))
        fresh=six_entries(f.s,t,argument_ref=a,support_ids=[s]);upper=fresh[1]['body']
        upper['payload'].update(start_ref=target,end_ref=end,relation='IMPLICATION',direction='FORWARD',claim_slots={'arrow':native_projection(f.s,end,a)})
        binding=deepcopy(fresh[-1]['body']);binding['payload']['upper_claim_slot']='arrow'
        self.assertEqual(qualify_binding(binding,upper,f.s)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        wrong=deepcopy(upper);wrong['payload'].update(start_ref=end,end_ref=target)
        self.assertEqual(qualify_binding(binding,wrong,f.s)['support_basis'],'OPEN')
        wrong=deepcopy(upper);wrong['payload'].update(relation='EQUIVALENCE',direction='BOTH')
        self.assertEqual(qualify_binding(binding,wrong,f.s)['support_basis'],'OPEN')

    def test_FM05_native_AND_OR_requires_exact_complete_route(self):
        from tests.test_final_kernel import AssuranceContextTests,statement
        f,t,target,arg,sid,entries=self.fixture();helper=AssuranceContextTests()
        child=f.add(statement('The independent exact child holds.'));ca,cs,cr=add_exact_path(f,child,'Independent scoped child proof.')
        body='The exact child lifts to the original target.';loc=K.locator(body)
        duty={k:dict(status='NOT_REQUIRED',reason_locator=loc,evidence_refs=[]) for k in ('lifting_check','compatibility_check')}
        inference=dict(premise_refs=[child],conclusion_ref=target,operator='AND',alternative_argument_refs=[],additional_assumption_refs=[],**duty)
        premise=dict(premise_ref=child,kind='SUPPORTED_STATEMENT',context_ref=None,scope_locator=None,binding_mode='PINNED',support_ref=cs,assumption_locator=None)
        a,s,req=add_exact_path(f,target,body,mode='REDUCTION',payload={'inference_spec':inference},premises=[premise])
        digest=sha(canonical(req));f.s['supports'][s]['policy_digest']=digest
        for q in f.s['supports'][s]['qualification_refs']:f.s['qualifications'][q]['policy_digest']=digest
        rows=six_entries(f.s,t,argument_ref=a,support_ids=[s])
        self.assertEqual(qualify_binding(rows[-1]['body'],rows[0]['body'],f.s)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        missing=deepcopy(f.s);missing['supports'][cs]['qualification_refs']=[]
        self.assertEqual(qualify_binding(rows[-1]['body'],rows[0]['body'],missing)['support_basis'],'OPEN')
        obody='Either complete alternative is sufficient.';oloc=K.locator(obody)
        outer=dict(premise_refs=[],conclusion_ref=target,operator='OR',alternative_argument_refs=[a],additional_assumption_refs=[],
            **{k:dict(status='NOT_REQUIRED',reason_locator=oloc,evidence_refs=[]) for k in ('lifting_check','compatibility_check')})
        oa,os,oreq=add_exact_path(f,target,obody,mode='REDUCTION',payload={'inference_spec':outer})
        self.assertEqual(A.evaluate_requirement(f.s,os,oreq,sha(canonical(oreq)))['result'],'QUALIFIED')
        missing['records'][oa]=f.s['records'][oa];missing['supports'][os]=f.s['supports'][os]
        self.assertNotEqual(A.evaluate_requirement(missing,os,oreq,sha(canonical(oreq)))['result'],'QUALIFIED')

    def test_FM06_navigation_cycle_does_not_create_support_cycle(self):
        f,t,_,_,sid,entries=self.fixture();validate_delta(delta_for(f.s,t,entries),f.s)
        self.assertEqual(qualify_binding(entries[-1]['body'],entries[0]['body'],f.s)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        cyclic=deepcopy(f.s);cyclic['supports'][sid]['premise_support_refs']=[sid]
        with self.assertRaisesRegex(PMRSError,'CYCLIC_MATH_SUPPORT'):
            qualify_binding(entries[-1]['body'],entries[0]['body'],cyclic)

    def test_FM07_donor_qualification_and_target_applicability_are_separate(self):
        from tests.test_final_kernel import statement
        f,t,_,_,_,entries=self.fixture();upper=deepcopy(entries[0]['body'])
        upper['original_target_ref']=f.add(statement('A different target needs an extra condition.'))
        result=qualify_binding(entries[-1]['body'],upper,f.s)
        self.assertEqual(result['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE');self.assertEqual(result['project_applicability'],'OPEN')
        self.assertEqual(result['author_prose'],'UNQUALIFIED_EXPLANATION')

    def test_FM08_withdrawal_is_path_scoped_and_historical(self):
        f,t,_,_,sid,entries=self.fixture();before=deepcopy(f.s)
        f.s['withdrawals']['W']=dict(support_id=sid,scope=f.s['supports'][sid]['consumer_requirement']['required_scope'],active=True)
        result=qualify_binding(entries[-1]['body'],entries[0]['body'],f.s)
        self.assertEqual((result['support_basis'],result['freshness']),('OPEN','STALE'))
        self.assertEqual(qualify_binding(entries[-1]['body'],entries[0]['body'],before)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        self.assertNotIn('negation',result)

    def test_FM10_FM11_no_progress_unknown_and_empty_proposal(self):
        f,t,_,_,_,entries=self.fixture();delta=delta_for(f.s,t,entries);validate_delta(delta,f.s)
        self.assertEqual(entries[1]['body']['payload']['relation'],'UNKNOWN')
        empty=delta_for(f.s,t,[],empty_reason='No new evidence in this bounded attempt.');validate_delta(empty,f.s)
        self.assertEqual(empty['input_commit'],t['knowledge_commit'])
        for mutation in ('empty_reason','capture_payload_path'):
            bad=deepcopy(empty);bad[mutation]=None if mutation=='empty_reason' else '/invented'
            with self.assertRaises(FastMathError):validate_delta(bad,f.s)
        bad=deepcopy(entries[2]);bad['body']['payload']['outcomes'][0]['outcome']='ORIGINAL_TARGET_REFUTED';rehash(bad)
        with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[bad]),f.s)

    def test_FM21_profile_has_no_qualification_fields(self):
        f,t,_,_,_,entries=self.fixture();profile=entries[4];validate_delta(delta_for(f.s,t,[profile]),f.s)
        changed=deepcopy(profile);changed['body']['payload']['explanation_depth']='OVERVIEW';rehash(changed)
        validate_delta(delta_for(f.s,t,[changed]),f.s)
        self.assertEqual(qualify_binding(entries[-1]['body'],entries[0]['body'],f.s)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        changed['body']['payload']['checked']=True;rehash(changed)
        with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[changed]),f.s)

    def test_FM24_acyclic_U1_B1_and_truthful_display_reuse(self):
        f,t,_,_,_,entries=self.fixture();delta=delta_for(f.s,t,entries)
        revisions=validate_delta(delta,f.s)
        state=deepcopy(f.s);state['fast_revisions']=revisions;state['fast_selected']={r['object_id']:ref for ref,r in revisions.items()}
        old=entries[0];new=deepcopy(old);new['body']['predecessor']=old['ref'];new['body']['body']='Display-only new explanation.';rehash(new)
        link=dict(old_upper_ref=old['ref'],new_upper_ref=new['ref'],old_slot='result',new_slot='result',
            claim_fingerprint=claim_fingerprint(old['body']['payload']['claim_slots']['result']),source_binding_ref=entries[-1]['ref'])
        validate_delta(delta_for(state,t,[new],links=[link]),state)
        state['fast_revisions'][new['ref']]=new['body'];state['fast_claim_links']={'event:0':link}
        result=project(new['ref'],state)['bindings'][0]
        self.assertEqual(result['binding_target'],old['ref']);self.assertEqual(result['displayed_upper'],new['ref'])
        self.assertEqual(result['reuse_link_ref'],'event:0')
        circular=deepcopy(old);circular['body']['payload']['refinement_refs']=[entries[-1]['ref']];rehash(circular)
        with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[circular]),f.s)
        changed=deepcopy(new);changed['body']['payload']['claim_slots']['result']['statement_fields']['quantifier_locators']=[];rehash(changed)
        with self.assertRaises(FastMathError):validate_delta(delta_for(state,t,[changed],links=[link]),state)

    def test_FM09_native_guard_detects_new_scoped_withdrawal_not_unrelated_state(self):
        f,t,_,_,sid,entries=self.fixture();proposal=delta_for(f.s,t,entries)
        unrelated=deepcopy(f.s);unrelated['unrelated_navigation_note']='No relevant evidence changed.'
        validate_delta(proposal,unrelated)
        withdrawn=deepcopy(f.s);withdrawn['withdrawals']['W-new']=dict(support_id=sid,active=True,
            scope=f.s['supports'][sid]['consumer_requirement']['required_scope'])
        with self.assertRaises(FastMathError) as caught:validate_delta(proposal,withdrawn)
        self.assertEqual(caught.exception.code,'FAST_VERSION_CONFLICT')
        refreshed=delta_for(withdrawn,t,entries);validate_delta(refreshed,withdrawn)
        self.assertEqual(qualify_binding(entries[-1]['body'],entries[0]['body'],withdrawn)['support_basis'],'OPEN')

    def test_FM03_partial_native_review_never_qualifies_whole_projected_slot(self):
        f,t,target,arg,sid,entries=self.fixture()
        whole=deepcopy(f.s['supports'][sid]['consumer_requirement']['required_scope'][0])
        region=K.locator(f.get(whole['target_body_sha256']),end=max(1,whole['whole_locator']['end']//2))
        partial=A.requirement('PROOF_SUPPORT',[dict(target_ref=arg,locators=[region],aspects=['proof'])])
        partial=A.normalize_requirement(partial,f.s,f.get);digest=sha(canonical(partial))
        state=deepcopy(f.s);state['supports'][sid].update(consumer_requirement=partial,policy_digest=digest)
        state['qualifications']['Q-synthetic']['policy_digest']=digest
        # The existing full authentic review covers the smaller native consumer.
        self.assertEqual(A.evaluate_requirement(state,sid,partial,digest)['result'],'QUALIFIED')
        binding=deepcopy(entries[-1]['body']);binding['payload'].update(requirement=partial,policy_digest=digest,required_review_scope=partial['required_scope'])
        projected=qualify_binding(binding,entries[0]['body'],state)
        self.assertEqual(projected['support_basis'],'OPEN')
        self.assertEqual(projected['mapped_review_extent'],'INSUFFICIENT_FOR_WHOLE_SLOT')

    def test_source09_FM02_ordered_witness_quantifier_and_constant_pairs(self):
        f,t,donor,_,_,_=self.fixture()
        body='Fix an integer n. Choose witnesses u and v. The constant C depends only on n.'
        def loc(text,phrase):
            start=text.index(phrase);return K.locator(text,start,start+len(phrase))
        context=f.add(K.make_record('Context',body,dict(definitions=[],objects=[
            dict(key='n',locator=loc(body,'integer n')),dict(key='u',locator=loc(body,'witnesses u')),
            dict(key='v',locator=loc(body,'and v')),dict(key='C',locator=loc(body,'constant C'))],
            assumptions=[],quantifiers=[dict(key='all_n',locator=loc(body,'Fix an integer n')),
            dict(key='exists_uv',locator=loc(body,'Choose witnesses u and v'))],conventions=[],parent_context_refs=[]),
            records=f.s['records'],blob_get=f.get))
        text='For every integer n there exist witnesses u and v with a constant C depending only on n.'
        data=dict(statement_locator=K.locator(text),scope_context_refs=[context],hypothesis_locators=[],
            conclusion_locators=[K.locator(text)],quantifier_locators=[loc(text,'For every integer n'),loc(text,'there exist witnesses u and v')],
            form='PROPOSITION',representation='AUTHORED',source_binding=None)
        target=f.add(K.make_record('Statement',text,data,[context],records=f.s['records'],blob_get=f.get))
        explanation='Use u(n) first and v(n,u) second. The constant C(n) depends on n; the bound D(n,C) depends on n and C.'
        argument=dict(conclusion_ref=target,premise_bindings=[],steps=[],discharged_assumptions=[],open_conditions=[],
            witness_bindings=[dict(variable='u',context_ref=context,locator=loc(explanation,'u(n)')),
                              dict(variable='v',context_ref=context,locator=loc(explanation,'v(n,u)'))],mode='APPLICABILITY',
            mode_payload=dict(donor_refs=[donor],recipient_ref=target,substitution_map={'u':'u(n)','v':'v(n,u)'},
                hypothesis_discharge_refs=[],constant_dependency_locators=[loc(explanation,'C(n) depends on n'),
                    loc(explanation,'D(n,C) depends on n and C')],open_conditions=[]))
        arg=f.add(K.make_record('Argument',explanation,argument,[context],records=f.s['records'],blob_get=f.get))
        f.s['instances'][t['instance_id']]['target_ref']=target
        upper=six_entries(f.s,t,argument_ref=arg)[0]
        validate_delta(delta_for(f.s,t,[upper]),f.s)
        slot=upper['body']['payload']['claim_slots']['result']
        self.assertEqual(slot,native_projection(f.s,target,arg))
        for mutation in ('quantifier_order','witness_order','constant_order','constant_missing','parameter_dependency','context_order'):
            with self.subTest(mutation=mutation):
                bad=deepcopy(upper);changed=bad['body']['payload']['claim_slots']['result']
                if mutation=='quantifier_order':changed['statement_fields']['quantifier_locators'].reverse()
                elif mutation=='witness_order':changed['argument_fields']['witness_bindings'].reverse()
                elif mutation=='constant_order':changed['argument_fields']['mode_payload']['constant_dependency_locators'].reverse()
                elif mutation=='constant_missing':changed['argument_fields']['mode_payload']['constant_dependency_locators'].pop()
                elif mutation=='parameter_dependency':changed['argument_fields']['mode_payload']['substitution_map']['v']='v(n)'
                else:changed['context_fields'][context]['quantifiers'].reverse()
                self.assertNotEqual(claim_fingerprint(changed),claim_fingerprint(slot));rehash(bad)
                with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[bad]),f.s)

    def test_source09_FM04_two_independent_directions_and_missing_reverse(self):
        from tests.test_final_kernel import statement
        f,t,start,_,base,entries=self.fixture();end=f.add(statement('The exact second formulation holds.'))
        def premise(ref,support):
            return dict(premise_ref=ref,kind='SUPPORTED_STATEMENT',context_ref=None,scope_locator=None,
                        binding_mode='PINNED',support_ref=support,assumption_locator=None)
        forward,fs,_=add_exact_path(f,end,'The first formulation implies the second.',premises=[premise(start,base)])
        reverse,rs,_=add_exact_path(f,start,'The second formulation implies the first.',premises=[premise(end,fs)])
        compare,cs,req=add_exact_path(f,end,'Both independently reviewed directions identify the two exact formulations.',
            mode='COMPARISON',payload=dict(relation_type='EQUIVALENT_ON_SCOPE',from_statement_ref=start,
                to_statement_ref=end,direction_argument_refs=[forward,reverse],scope_context_refs=[]),
            premises=[premise(start,rs),premise(end,fs)])
        f.s['instances'][t['instance_id']]['target_ref']=end
        rows=six_entries(f.s,t,argument_ref=compare,support_ids=[cs]);upper=rows[1]
        upper['body']['payload'].update(start_ref=start,end_ref=end,relation='EQUIVALENCE',direction='BOTH',
            claim_slots={'arrow':native_projection(f.s,end,compare)});rehash(upper)
        binding=rows[-1];binding['body']['payload'].update(upper_revision_ref=upper['ref'],upper_claim_slot='arrow')
        binding['body']['dependencies']=[upper['ref'],end];rehash(binding)
        validate_delta(delta_for(f.s,t,[upper,binding]),f.s)
        self.assertEqual(qualify_binding(binding['body'],upper['body'],f.s)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        missing=deepcopy(f.s);missing['supports'][rs]['qualification_refs']=[]
        self.assertEqual(A.evaluate_requirement(missing,cs,req,sha(canonical(req)))['result'],'UNQUALIFIED')
        self.assertEqual(qualify_binding(binding['body'],upper['body'],missing)['support_basis'],'OPEN')
        wrong=deepcopy(upper);wrong['body']['payload'].update(start_ref=end,end_ref=start);rehash(wrong)
        self.assertEqual(qualify_binding(binding['body'],wrong['body'],f.s)['support_basis'],'OPEN')
        self.assertNotEqual(f.s['supports'][fs]['qualification_refs'],f.s['supports'][rs]['qualification_refs'])

    def test_source09_FM05_common_witness_order_and_AND_OR_survival(self):
        from tests.test_final_kernel import statement
        f,t,target,_,_,_=self.fixture();children=[]
        for index in range(2):
            ref=f.add(statement('There exists a local witness for property '+str(index)+'.'))
            arg,sid,_=add_exact_path(f,ref,'A separate exact witness establishes property '+str(index)+'.')
            children.append((ref,arg,sid))
        text='One common witness must work for every parameter with the declared dependency order.'
        witness=dict(target_ref=target,component_argument_refs=[x[1] for x in children],context_refs=[],
            variable_mapping={'parameter':'parameter','witness':'witness(parameter)'},common_data_refs=[target],
            quantifier_locators=[K.locator(text)],evidence_refs=[x[1] for x in children],open_condition_refs=[])
        arg,sid,req=add_exact_path(f,target,text,mode='COMPATIBILITY',payload={'witness_compatibility':witness})
        self.assertEqual(A.evaluate_requirement(f.s,sid,req,sha(canonical(req)))['result'],'QUALIFIED')
        rows=six_entries(f.s,t,argument_ref=arg,support_ids=[sid]);validate_delta(delta_for(f.s,t,rows),f.s)
        wrong=deepcopy(rows[0]);wrong['body']['payload']['claim_slots']['result']['argument_fields']['mode_payload']['witness_compatibility']['variable_mapping']['witness']='constant_witness'
        rehash(wrong)
        with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[wrong]),f.s)
        for field in ('variable_mapping','quantifier_locators'):
            bad=deepcopy(witness);bad[field]={} if field=='variable_mapping' else []
            _,negative,nreq=add_exact_path(f,target,text+' The common witness evidence is missing '+field+'.',
                mode='COMPATIBILITY',payload={'witness_compatibility':bad})
            self.assertEqual(A.evaluate_requirement(f.s,negative,nreq,sha(canonical(nreq)))['result'],'UNQUALIFIED')
        def route(label,selected):
            body='Exact complete reduction route '+label+'.';loc=K.locator(body)
            premises=[dict(premise_ref=ref,kind='SUPPORTED_STATEMENT',context_ref=None,scope_locator=None,
                binding_mode='PINNED',support_ref=child_sid,assumption_locator=None) for ref,_,child_sid in selected]
            inference=dict(premise_refs=[x[0] for x in selected],conclusion_ref=target,operator='AND',
                alternative_argument_refs=[],additional_assumption_refs=[],**{name:dict(status='NOT_REQUIRED',
                    reason_locator=loc,evidence_refs=[]) for name in ('lifting_check','compatibility_check')})
            return add_exact_path(f,target,body,mode='REDUCTION',payload={'inference_spec':inference},premises=premises)
        a,sa,ra=route('both children',children);b,sb,rb=route('second child suffices',children[1:])
        body='Either separately complete native reduction route suffices.';loc=K.locator(body)
        outer=dict(premise_refs=[],conclusion_ref=target,operator='OR',alternative_argument_refs=[a,b],additional_assumption_refs=[],
            **{name:dict(status='NOT_REQUIRED',reason_locator=loc,evidence_refs=[]) for name in ('lifting_check','compatibility_check')})
        _,sid,req=add_exact_path(f,target,body,mode='REDUCTION',payload={'inference_spec':outer})
        self.assertEqual(A.evaluate_requirement(f.s,sid,req,sha(canonical(req)))['result'],'QUALIFIED')
        missing=deepcopy(f.s);missing['supports'][children[0][2]]['qualification_refs']=[]
        self.assertEqual(A.evaluate_requirement(missing,sa,ra,sha(canonical(ra)))['result'],'UNQUALIFIED')
        self.assertEqual(A.evaluate_requirement(missing,sb,rb,sha(canonical(rb)))['result'],'QUALIFIED')
        self.assertEqual(A.evaluate_requirement(missing,sid,req,sha(canonical(req)))['result'],'QUALIFIED')
        missing['supports'][children[1][2]]['qualification_refs']=[]
        self.assertEqual(A.evaluate_requirement(missing,sid,req,sha(canonical(req)))['result'],'UNQUALIFIED')

    def test_source09_FM07_exact_applicability_is_separate_from_donor(self):
        from tests.test_final_kernel import statement
        f,t,donor,_,_,entries=self.fixture();recipient=f.add(statement('The recipient has its own exact input conditions.'))
        upper=deepcopy(entries[0]['body']);upper['original_target_ref']=recipient
        binding=deepcopy(entries[-1]['body'])
        before=qualify_binding(binding,upper,f.s)
        self.assertEqual(before['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE');self.assertEqual(before['project_applicability'],'OPEN')
        body='The exact substitution discharges the recipient conditions; the constant depends only on the stated inputs.'
        _,sid,req=add_exact_path(f,recipient,body,mode='APPLICABILITY',purpose='APPLICABILITY',payload=dict(
            donor_refs=[donor],recipient_ref=recipient,substitution_map={'input':'exact_input'},hypothesis_discharge_refs=[donor],
            constant_dependency_locators=[K.locator(body)],open_conditions=[]))
        binding['payload']['applicability_refs']=[sid]
        result=qualify_binding(binding,upper,f.s)
        self.assertEqual(A.evaluate_requirement(f.s,sid,req,sha(canonical(req)))['result'],'QUALIFIED')
        self.assertEqual(result['project_applicability'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        missing=deepcopy(f.s);missing['supports'][sid]['qualification_refs']=[]
        result=qualify_binding(binding,upper,missing)
        self.assertEqual(result['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE');self.assertEqual(result['project_applicability'],'OPEN')
        wrong=deepcopy(upper);wrong['original_target_ref']=f.add(statement('A third target has not been checked.'))
        self.assertEqual(qualify_binding(binding,wrong,f.s)['project_applicability'],'OPEN')

    def test_source09_FM10_local_failures_do_not_refute_original_target(self):
        f,t,target,argument,sid,entries=self.fixture();before=canonical(f.s)
        probe=deepcopy(entries[2]);probe['body']['payload']['outcomes'] += [
            dict(outcome='METHOD_FAILURE',consequence='Only this attempted method failed; the original target remains open.',evidence_refs=[argument]),
            dict(outcome='LOCAL_LEMMA_FAILURE',consequence='The stronger local lemma failed; no negation of the original target follows.',evidence_refs=[target]),
            dict(outcome='SCOPED_DEFECT',consequence='Recheck only the exact affected argument scope.',evidence_refs=[argument])]
        rehash(probe);validate_delta(delta_for(f.s,t,[probe]),f.s)
        self.assertEqual(canonical(f.s),before)
        self.assertEqual(qualify_binding(entries[-1]['body'],entries[0]['body'],f.s)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
        self.assertEqual(entries[1]['body']['payload']['relation'],'UNKNOWN')
        bad=deepcopy(probe);bad['body']['payload']['outcomes'][-1]['outcome']='ORIGINAL_TARGET_REFUTED';rehash(bad)
        with self.assertRaises(FastMathError):validate_delta(delta_for(f.s,t,[bad]),f.s)
