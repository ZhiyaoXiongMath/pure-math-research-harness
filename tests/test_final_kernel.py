"""Executed semantic regressions for the final shared scientific kernel."""
import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from research_studio import contracts as C,knowledge as K,changes,assurance,context,relations,language
from research_studio.util import canonical,sha,PMRSError


def statement(body='For every x there exists y.',**kw):
    loc=K.locator(body)
    d={'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[],'conclusion_locators':[loc],'quantifier_locators':[loc],'form':'PROPOSITION','representation':'AUTHORED','source_binding':None}
    return K.make_record('Statement',body,d,[],**kw)

def argument(conclusion,body='The displayed construction establishes the assertion.',**kw):
    d={'conclusion_ref':conclusion,'premise_bindings':[],'steps':[{'step_id':'s1','locator':K.locator(body),'premise_refs':[]}],'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'PROOF','mode_payload':{}}
    return K.make_record('Argument',body,d,[],**kw)

class Fixture:
    def __init__(self):
        self.s={'records':{},'objects':{},'sources':{},'inferences':{},'supports':{},'qualifications':{},'production_events':{},'withdrawals':{},'relations':[], 'obligations':{},'tasks':{},'requests':{},'accepted_requests':{},'review_executions':{},'knowledge_commit':'base','synthetic_test_only':True}
        self.blobs={}
    def add(self,triple):
        ref,r,b=triple;self.s['records'][ref]=r;self.blobs[sha(b)]=b
        self.s['objects']['KO-'+ref[3:]]={'object_id':'KO-'+ref[3:],'kind':r['kind'],'created_by_event':'test','selected_revision':ref,'revisions':[ref]}
        return ref
    def get(self,h):return self.blobs[h]
    def task(self,refs=(),request='request-1',role='AUTHOR'):
        pkt=context.build_packet(self.s,list(refs),self.get)
        task={'schema':C.TASK_SCHEMA,'task_id':'task-'+request,'request_id':request,'role':role,'knowledge_commit':self.s['knowledge_commit'],
           'permission_manifest':{'allowed_payload_kinds':['KNOWLEDGE_CHANGE'],'allowed_record_kinds':list(C.KINDS),'allowed_operations':['NEW','REVISE','LINK','WITHDRAW_SUPPORT']},
           'read_set':pkt['read_set'],'query_guards':[],'write_guards':[],'input_manifest':pkt['input_manifest'],'obligation_bindings':[], 'target_refs':list(refs),'input_manifest_hash':C.digest(pkt['input_manifest'])}
        self.s['tasks'][task['task_id']]=deepcopy(task)
        return task
    def raw(self,task,ops=(),effects=(),outcome='RESULT'):
        k={'schema':C.CHANGE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'base_knowledge_commit':task['knowledge_commit'],
         'read_set_digest':C.digest(task['read_set']),'query_guard_digest':C.digest(task['query_guards']),'write_guard_digest':C.digest(task['write_guards']),
         'operations':list(ops),'obligation_effects':list(effects),'new_obligation_proposals':[],'work_outcome':outcome,
         'attempt_account':'The proposed approach was inspected. The remaining gap is not localized. No new condition or next attempt is proposed.',
         'claimed_change':'The exact available content is recorded.','semantic_novelty':'NOT_AUTOMATICALLY_CERTIFIED'}
        return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'payload_kind':'KNOWLEDGE_CHANGE','payload':k})
    def accept(self,task,raw):
        self.blobs[sha(raw)]=raw;self.s['requests'][task['request_id']]={'request_id':task['request_id'],'task_id':task['task_id'],'capture_ref':sha(raw),'execution_kind':'SYNTHETIC_TEST_ONLY'}
        plan=changes.validate_response(task,self.s,raw,'live',self.get)
        self.blobs.update(plan.get('blobs',{}));self.s=changes.apply_validated(self.s,plan);return plan

class FinalIdentityAdmissionTests(unittest.TestCase):
    def test_content_identity_context_quantifiers_and_families(self):
        a,ar,ab=statement();b,br,bb=statement('There exists y for every x.')
        self.assertNotEqual(a,b)
        before=canonical(ar)
        family=K.result_family({'family_id':'F','members':[{'record_ref':a,'display_role':'MAIN_RESULT'},{'record_ref':b,'display_role':'COROLLARY'}]},{a:ar,b:br})
        family['family_id']='Changed title'
        self.assertEqual(before,canonical(ar));self.assertEqual(a,K.identify(ar,ab))
        with self.assertRaises(PMRSError):K.result_family({'family_id':'F','members':[{'record_ref':a,'display_role':'ALTERNATIVE_PROOF'}]},{a:ar})
        with self.assertRaises(PMRSError):K.identify({**ar,'task_id':'bad'},ab)

    def test_same_content_multiple_requests_reuses_revision(self):
        f=Fixture();r,record,body=statement();op={'op':'NEW','local_key':'s','kind':'Statement','context_refs':[],'body':body.decode(),'data':record['data']}
        first=f.accept(f.task(request='a'),f.raw(f.s['tasks']['task-a'],[op]));second_task=f.task(request='b');second=f.accept(second_task,f.raw(second_task,[op]))
        self.assertEqual(first['receipt']['content_added'],[r]);self.assertEqual(second['receipt']['content_added'],[])
        self.assertEqual(second['receipt']['content_reused'],[r]);self.assertEqual(len(f.s['production_events']),2);self.assertEqual(len(f.s['records']),1)

    def test_request_raw_idempotency_and_content_conflict(self):
        f=Fixture();t=f.task();raw=f.raw(t,outcome='NO_RESULT');first=f.accept(t,raw)
        f.s['knowledge_commit']='unrelated';before=canonical(f.s)
        for _ in range(3):
            p=changes.validate_response(t,f.s,raw,'live',f.get)
            self.assertEqual(p['outcome'],'EXACT_DUPLICATE');self.assertEqual(first['receipt']['receipt_id'],p['receipt']['receipt_id']);self.assertEqual(before,canonical(changes.apply_validated(f.s,p)))
        with self.assertRaisesRegex(PMRSError,'ALREADY_SETTLED_CONTENT_CONFLICT'):changes.validate_response(t,f.s,raw+b'\n','live',f.get)

    def test_zero_record_no_result_and_attempt_account_preserved(self):
        f=Fixture();t=f.task();oid='O';bid='B'
        f.s['obligations'][oid]={'definition':{'obligation_id':oid,'definition_revision':1,'type':'ESTABLISH','consumer_bindings':[]},'projection':{'work_state':'OPEN','resolution':'UNRESOLVED','attempt_refs':[],'evidence_refs':[]}}
        t['obligation_bindings']=[{'binding_id':bid,'obligation_id':oid,'expected_definition_revision':1}];f.s['tasks'][t['task_id']]=deepcopy(t)
        effect={'binding_id':bid,'expected_definition_revision':1,'work_disposition':'NO_RESULT','resolution_proposal':'UNRESOLVED','evidence_refs':[],'remaining_conditions':['The uniform estimate remains open.'],'blocker_proposals':[]}
        f.accept(t,f.raw(t,effects=[effect],outcome='NO_RESULT'))
        self.assertFalse(f.s['records']);p=f.s['obligations'][oid]['projection'];self.assertEqual(p['resolution'],'UNRESOLVED');self.assertIn('remaining gap',p['attempt_accounts'][0]['account']);self.assertEqual(p['work_state'],'ATTEMPTED')

    def test_topological_local_refs_body_staging_and_reduction_binding(self):
        f=Fixture();t=f.task();_,s,b=statement()
        sloc={'blob_hash':'body:s','unit':'UTF8_BYTE','start':0,'end':len(b),'quoted_sha256':None}
        sd=deepcopy(s['data']);sd.update(statement_locator=sloc,conclusion_locators=[sloc],quantifier_locators=[sloc])
        sop={'op':'NEW','local_key':'s','kind':'Statement','context_refs':[],'body':b.decode(),'data':sd}
        ab='This is an AND reduction with no additional obligations.';aloc={'blob_hash':'body:a','unit':'UTF8_BYTE','start':0,'end':len(ab),'quoted_sha256':None}
        inference={'premise_refs':[],'conclusion_ref':'local:s','operator':'AND','alternative_argument_refs':[],'additional_assumption_refs':[], 'lifting_check':{'status':'NOT_REQUIRED','reason_locator':aloc,'evidence_refs':[]},'compatibility_check':{'status':'NOT_REQUIRED','reason_locator':aloc,'evidence_refs':[]}}
        ad={'conclusion_ref':'local:s','premise_bindings':[],'steps':[],'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'REDUCTION','mode_payload':{'inference_spec':inference}}
        aop={'op':'NEW','local_key':'a','kind':'Argument','context_refs':[],'body':ab,'data':ad}
        rb='The reduction scope remains inconclusive.';rloc={'blob_hash':'body:r','unit':'UTF8_BYTE','start':0,'end':len(rb),'quoted_sha256':None}
        rd={'review_kind':'PROOF','target_refs':[{'inference_of':'local:a'}],'checked':[],'unchecked':[{'ref':{'inference_of':'local:a'},'aspect':'reduction','reason':'No proof yet.'}],'verdict':'INCONCLUSIVE','findings':[],'scope_context_refs':[]}
        rop={'op':'NEW','local_key':'r','kind':'Assessment','context_refs':[],'body':rb,'data':rd}
        p1=changes.validate_response(t,f.s,f.raw(t,[rop,aop,sop]),blob_get=f.get)
        p2=changes.validate_response(t,f.s,f.raw(t,[sop,aop,rop]),blob_get=f.get)
        self.assertEqual(p1['records'],p2['records']);self.assertEqual(p1['inferences'],p2['inferences']);self.assertEqual(len(p1['inferences']),1)
        self.assertNotIn('local:',canonical(p1['records']).decode());self.assertNotIn('body:',canonical(p1['records']).decode())
        explicit=deepcopy(sop);explicit['data']=s['data'];self.assertEqual(changes.validate_response(t,f.s,f.raw(t,[sop]),blob_get=f.get)['records'],changes.validate_response(t,f.s,f.raw(t,[explicit]),blob_get=f.get)['records'])
        broken=deepcopy(sop);broken['data']['statement_locator']['end']+=1
        with self.assertRaises(PMRSError):changes.validate_response(t,f.s,f.raw(t,[broken]),blob_get=f.get)
        bad=deepcopy(aop);bad['data']['conclusion_ref']='local:a'
        with self.assertRaisesRegex(PMRSError,'CYCLIC_MATH_SUPPORT'):changes.validate_response(t,f.s,f.raw(t,[bad]),blob_get=f.get)

    def test_strict_json_unknown_fields_duplicate_depth_float(self):
        for raw,code in [(b'{"x":1,"x":2}','DUPLICATE_JSON_KEY'),(b'['*34+b'0'+b']'*34,'PAYLOAD_LIMIT'),(b'{"x":1.2}','RESPONSE_SCHEMA_INVALID')]:
            with self.assertRaisesRegex(PMRSError,code):C.bounded_json(raw)
        f=Fixture();t=f.task();payload=json.loads(f.raw(t));payload['model_authority']=True
        with self.assertRaisesRegex(PMRSError,'UNKNOWN_FIELD'):changes.validate_response(t,f.s,canonical(payload),blob_get=f.get)

    def test_current_vs_pinned_relevant_cas_and_unrelated_rebase(self):
        f=Fixture();s=f.add(statement());t=f.task([s]);raw=f.raw(t,outcome='NO_RESULT')
        f.s['knowledge_commit']='other';changes.live_check(t,f.s,f.get)
        oid=t['read_set'][0]['selection_binding']['object_id'];f.s['objects'][oid]['selected_revision']='KR-other'
        changes.live_check(t,f.s,f.get)
        t['read_set'][0]['selection_binding']['mode']='CURRENT'
        with self.assertRaisesRegex(PMRSError,'STALE_READ'):changes.live_check(t,f.s,f.get)

    def test_source_input_store_commit_and_original_hash(self):
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store=Store.create(Path(tmp)/'project','Example')
            raw='证明：任意光滑对象是否具有此性质？'.encode()
            plan=changes.prepare_source_input(store.read_snapshot(),raw)
            receipt=store.commit(plan);s=store.read_snapshot();r=receipt['target_ref']
            self.assertEqual(store.read_blob(s['records'][r]['body_sha256']),raw);self.assertEqual(s['records'][r]['data']['representation'],'SOURCE_BOUND');self.assertFalse(s['supports'])
            before=store._head();store.audit();self.assertEqual(before,store._head())

    def test_statement_revision_keeps_fixed_target_and_rejects_late_current_capture(self):
        f=Fixture();old=f.add(statement());oid='KO-'+old[3:]
        f.s['instances']={'TRW':{'target_ref':old,'status':'ACTIVE'}}
        late=f.task([old],request='late');late['read_set'][0]['selection_binding']['mode']='CURRENT'
        f.s['tasks'][late['task_id']]=deepcopy(late);raw=f.raw(late,outcome='NO_RESULT')
        edit=f.task([old],request='edit');edit['write_guards']=[{'object_id':oid,'expected_parent':old}];f.s['tasks'][edit['task_id']]=deepcopy(edit)
        body='For every x satisfying the extra hypothesis there exists y.';new,r,b=statement(body)
        op={'op':'REVISE','local_key':'weaker','object_id':oid,'expected_parent':old,'new_record':{'kind':'Statement','context_refs':[],'body':body,'data':r['data']}}
        f.accept(edit,f.raw(edit,[op]));self.assertEqual(f.s['objects'][oid]['selected_revision'],new)
        self.assertEqual(f.s['instances']['TRW']['target_ref'],old);self.assertIn(old,f.s['records'])
        with self.assertRaisesRegex(PMRSError,'STALE_READ'):f.accept(late,raw)
        self.assertNotIn(late['request_id'],f.s['accepted_requests']);self.assertEqual(f.get(sha(raw)),raw)

    def test_binary_material_source_only_and_explicit_request_fence(self):
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store=Store.create(Path(tmp)/'project','Materials');raw=b'%PDF-1.7\n\xff\x00untrusted bytes'
            receipt=store.commit(changes.prepare_material_input(store.read_snapshot(),raw,media_type='application/pdf'))
            state=store.read_snapshot();source=state['sources'][receipt['source_ref']]
            self.assertEqual(store.read_blob(source['blob_hash']),raw);self.assertFalse(state['records']);self.assertFalse(state['supports']);store.audit()
        f=Fixture();t=f.task();f.s['requests'][t['request_id']]={'fenced':True}
        with self.assertRaisesRegex(PMRSError,'TASK_FENCED'):changes.live_check(t,f.s,f.get)

    def test_argument_revision_preserves_statement_author_and_target(self):
        f=Fixture();s=f.add(statement());a=f.add(argument(s,records=f.s['records']));t=f.task([a])
        oid='KO-'+a[3:];t['write_guards']=[{'object_id':oid,'expected_parent':a}];f.s['tasks'][t['task_id']]=deepcopy(t)
        old=deepcopy(f.s['records'][s]);old_arg=deepcopy(f.s['records'][a]);new_body='A revised explicit construction uses the same assertion.'
        _,new_record,_=argument(s,new_body,records=f.s['records'])
        op={'op':'REVISE','local_key':'revised','object_id':oid,'expected_parent':a,'new_record':{'kind':'Argument','context_refs':[],'body':new_body,'data':new_record['data']}}
        plan=f.accept(t,f.raw(t,[op]));new=f.s['objects'][oid]['selected_revision']
        self.assertNotEqual(a,new);self.assertEqual(f.s['records'][s],old);self.assertEqual(f.s['records'][a],old_arg);self.assertEqual(f.s['records'][new]['data']['conclusion_ref'],s)
        self.assertIn(a,f.s['objects'][oid]['revisions']);self.assertEqual(plan['receipt']['content_added'],[new])

    def test_query_guard_new_member_and_lifecycle_not_definition_stale(self):
        f=Fixture();s=f.add(statement());f.s['instances']={'I':{'target_ref':s,'status':'PAUSED'}};t=f.task([s])
        members=[s];t['query_guards']=[{'query_kind':'TARGET_SET','scope_binding':{},'member_refs':members,'member_digest':C.digest(members)}]
        changes.live_check(t,f.s,f.get)
        f.s['instances']['J']={'target_ref':'KR-other','status':'PAUSED'}
        with self.assertRaisesRegex(PMRSError,'STALE_QUERY'):changes.live_check(t,f.s,f.get)

    def test_bilingual_index_exact_locator_and_bound_quote(self):
        f=Fixture();raw='可去性与光滑正则性。'.encode();sid='SO-quote';h=sha(raw);f.blobs[h]=raw
        f.s['sources'][sid]={'source_id':sid,'blob_hash':h,'access_class':'SCIENTIFIC_SOURCE','provenance_refs':[]}
        loc=K.locator(raw);data={'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[],'conclusion_locators':[loc],'quantifier_locators':[],'form':'QUESTION','representation':'SOURCE_BOUND',
           'source_binding':{'source_ref':sid,'locators':[loc],'usage_mode':'DECLARED_EXCERPT','trust_boundary':'Exact original question.'}}
        chinese=f.add(K.make_record('Statement',raw,data,[],sources=f.s['sources'],blob_get=f.get))
        rows=language.search_bodies(f.s,'removability smooth',f.get);self.assertEqual({r['ref'] for r in rows},{sid,chinese});self.assertEqual(rows[0]['sha256'],h);K.validate_locator(rows[0]['locator'],f.get)
        s=f.add(statement());t=f.task([s]);t['input_manifest'].append({'kind':'source','ref':sid,'sha256':h})
        body='The source states: '+raw.decode()+' This quotation does not establish the present goal.'
        data={'conclusion_ref':s,'premise_bindings':[],'steps':[],'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'DERIVATION','mode_payload':{}}
        op={'op':'NEW','local_key':'a','kind':'Argument','context_refs':[],'body':body,'data':data}
        with self.assertRaisesRegex(PMRSError,'LANGUAGE_MISMATCH'):changes.validate_response(t,f.s,f.raw(t,[op]),blob_get=f.get)
        link={'op':'LINK','type':'USED_SOURCE','source_ref':'local:a','target_ref':sid,'scope_context_refs':[],
              'evidence_bindings':[{'source_ref':sid,'locators':[K.locator(raw)],'usage_mode':'METHOD_INSPIRATION','trust_boundary':'Exact quotation; no theorem reliance.'}],'assertion_state':'PROPOSED'}
        plan=changes.validate_response(t,f.s,f.raw(t,[op,link]),blob_get=f.get)
        self.assertEqual(len(plan['records']),1);self.assertEqual(plan['blobs'][next(iter(plan['records'].values()))['body_sha256']].decode(),body)
        self.assertEqual(f.blobs[h],raw)

    def test_forged_frozen_permissions_rejected_and_preflight_is_pure(self):
        f=Fixture();t=f.task();raw=f.raw(t,outcome='NO_RESULT');before=canonical(f.s)
        p=changes.validate_response(t,f.s,raw,blob_get=f.get);self.assertFalse(p['live_checked']);self.assertEqual(before,canonical(f.s))
        f.blobs[sha(raw)]=raw;f.s['requests'][t['request_id']]={'task_id':t['task_id'],'capture_ref':sha(raw)}
        forged=deepcopy(t);forged['permission_manifest']['human_review_withdrawal']=True
        with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):changes.validate_response(forged,f.s,raw,'live',f.get)

    def test_blocked_attempt_creates_persistent_retry_predicate(self):
        f=Fixture();s=f.add(statement());t=f.task([s]);oid='O';bid='B'
        f.s['obligations'][oid]={'definition':{'obligation_id':oid,'definition_revision':1,'type':'ESTABLISH','consumer_bindings':[]},'projection':{'work_state':'OPEN','resolution':'UNRESOLVED','attempt_refs':[],'evidence_refs':[]}}
        t['obligation_bindings']=[{'binding_id':bid,'obligation_id':oid,'expected_definition_revision':1}];f.s['tasks'][t['task_id']]=deepcopy(t)
        effect={'binding_id':bid,'expected_definition_revision':1,'work_disposition':'BLOCKED','resolution_proposal':'UNRESOLVED','evidence_refs':[], 'remaining_conditions':['The exact source theorem is missing.'],
          'blocker_proposals':[{'code':'INCOMPLETE_CONTEXT','evidence_refs':[s],'scope':{'target_ref':s},'hardness':'HARD','retry_condition':{'kind':'MATERIAL_VERIFIED','source_id':'SO-missing'}}]}
        f.accept(t,f.raw(t,effects=[effect],outcome='BLOCKED'));p=f.s['obligations'][oid]['projection']
        self.assertEqual(p['work_state'],'BLOCKED');self.assertEqual(len(p['blocker_refs']),1)
        blocker=f.s['blockers'][p['blocker_refs'][0]];self.assertEqual(blocker['hardness'],'HARD')
        from research_studio.obligations import condition_met
        self.assertFalse(condition_met(blocker['retry_condition'],f.s,blocker=blocker));self.assertEqual(f.s['obligations'][oid]['definition']['definition_revision'],1)

    def test_runtime_registry_resource_is_generated_from_same_fields(self):
        path=Path(C.__file__).parent/'schemas/contracts.json'
        self.assertEqual(json.loads(path.read_bytes()),C.registry())

    def test_nested_rejection_is_identical_and_raw_capture_remains(self):
        f=Fixture();t=f.task();_,record,body=statement();data=deepcopy(record['data']);data['conclusion_locators']=None
        op={'op':'NEW','local_key':'s','kind':'Statement','context_refs':[],'body':body.decode(),'data':data};raw=f.raw(t,[op]);f.blobs[sha(raw)]=raw
        f.s['requests'][t['request_id']]={'task_id':t['task_id'],'capture_ref':sha(raw)}
        codes=[]
        for mode in ('preflight','live'):
            with self.assertRaises(PMRSError) as error:changes.validate_response(t,f.s,raw,mode,f.get)
            codes.append(error.exception.code)
        self.assertEqual(codes[0],codes[1]);self.assertEqual(f.get(sha(raw)),raw);self.assertFalse(f.s['records'])
        cb='A new context.';cd={'definitions':[{'key':'新的定义','locator':K.locator(cb)}],'objects':[],'assumptions':[],'quantifiers':[],'conventions':[],'parent_context_refs':[]}
        with self.assertRaisesRegex(PMRSError,'LANGUAGE_MISMATCH'):K.make_record('Context',cb,cd,[])

class AssuranceContextTests(unittest.TestCase):
    def build(self):
        f=Fixture();s=f.add(statement());a=f.add(argument(s,records=f.s['records']));loc=K.locator(f.blobs[f.s['records'][a]['body_sha256']]);scope=[{'target_ref':a,'locators':[loc],'aspects':['proof']}]
        sid='SUP';f.s['supports'][sid]={'support_id':sid,'statement_ref':s,'argument_ref':a,'premise_support_refs':[],'open_assumption_refs':[],'scope_context_refs':[],'qualification_refs':[],'created_by_change':'c','author_task_id':'AUTHOR','author_execution_event':'AUTHOR-E'}
        return f,s,a,sid,scope
    def review(self,f,sid,scope,role='PROOF',kind='PROOF',verdict='SUPPORTED_WITHIN_SCOPE',event_id=None):
        event_id=event_id or 'EVENT-'+str(len(f.s['review_executions']))
        body='The explicitly assigned scope was checked independently.'
        data={'review_kind':kind,'target_refs':sorted({x['target_ref'] for x in scope}),'checked':[{'ref':x['target_ref'],'locators':x['locators'],'aspect':aspect} for x in scope for aspect in x['aspects']],'unchecked':[],'verdict':verdict,'findings':[],'scope_context_refs':[]}
        r=f.add(K.make_record('Assessment',body,data,[],records=f.s['records'],blob_get=f.get));q='Q'+event_id
        f.s['qualifications'][q]={'assessment_ref':r,'review_execution_event':event_id,'input_manifest_hash':'hash','target_revision_hashes':data['target_refs'],'actual_checked_scope':scope,'evidence_origin':'MODEL_CAPTURE','policy_digest':'p','integrity_valid':True}
        f.s['review_executions'][event_id]={'event_id':event_id,'task_id':event_id,'role':role,'input_manifest_hash':'hash','target_revision_hashes':data['target_refs'],'independent':True,'excluded_verdicts':True,'synthetic':True,'integrity_valid':True,'policy_digest':'p'}
        f.s['supports'][sid]['qualification_refs'].append(q);return q
    def add_path(self,f,target,body,mode='PROOF',payload=None,premises=(),review=True):
        d={'conclusion_ref':target,'premise_bindings':list(premises),'steps':[],'discharged_assumptions':[],'open_conditions':[],
           'witness_bindings':[],'mode':mode,'mode_payload':payload or {}}
        a=f.add(K.make_record('Argument',body,d,[],records=f.s['records'],blob_get=f.get));sid='SUP-'+a
        scope=[{'target_ref':a,'locators':[K.locator(body)],'aspects':['proof']}];req=assurance.requirement('PROOF_SUPPORT',scope)
        f.s['supports'][sid]={'support_id':sid,'statement_ref':target,'argument_ref':a,'premise_support_refs':[p['support_ref'] for p in premises if p['support_ref']],
          'open_assumption_refs':[],'qualification_refs':[],'author_task_id':'AUTHOR','consumer_requirement':req,'policy_digest':'p'}
        if review:self.review(f,sid,scope)
        return a,sid,req

    def test_and_three_children_and_or_complete_route_require_lifting(self):
        f=Fixture();target=f.add(statement('The original fixed target holds.'));children=[f.add(statement('Child '+str(i)+' holds.')) for i in range(3)]
        paths=[self.add_path(f,r,'The exact child '+str(i)+' has a proposed argument.',review=i<2) for i,r in enumerate(children)]
        bindings=[{'premise_ref':r,'kind':'SUPPORTED_STATEMENT','context_ref':None,'scope_locator':None,'binding_mode':'PINNED','support_ref':paths[i][1],'assumption_locator':None} for i,r in enumerate(children)]
        body='All three child assertions together imply the original target; the third remains necessary.';loc=K.locator(body)
        inf={'premise_refs':children,'conclusion_ref':target,'operator':'AND','alternative_argument_refs':[],'additional_assumption_refs':[],
          'lifting_check':{'status':'REQUIRED','obligation_ids':['LIFT'],'evidence_refs':[]},'compatibility_check':{'status':'NOT_REQUIRED','reason_locator':loc,'evidence_refs':[]}}
        a,sid,req=self.add_path(f,target,body,'REDUCTION',{'inference_spec':inf},bindings)
        lift_target=f.add(statement('The lifting hypotheses are discharged on the exact scope.'))
        la,ls,lr=self.add_path(f,lift_target,'The lifting construction is explicitly justified.')
        f.s['obligations']['LIFT']={'definition':{'type':'APPLICABILITY','consumer_bindings':[{'threshold':'SUPPORT_QUALIFIED','selected_support':ls,'required_assurance':lr,'policy_digest':'p'}]},'projection':{'resolution':'UNRESOLVED'}}
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'UNQUALIFIED')
        f.s['obligations']['LIFT']['projection']['resolution']='SATISFIED_FOR_CONSUMER'
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'UNQUALIFIED')
        self.review(f,paths[2][1],paths[2][2]['required_scope']);self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'QUALIFIED')
        otherbody='An alternative route has no supplied valid lifting argument.';other=deepcopy(inf);other['lifting_check']['obligation_ids']=['MISSING'];other['compatibility_check']['reason_locator']=K.locator(otherbody)
        a2,sid2,req2=self.add_path(f,target,otherbody,'REDUCTION',{'inference_spec':other},bindings)
        obody='Either complete route suffices, while incomplete routes do not.';oloc=K.locator(obody);outer={'premise_refs':[],'conclusion_ref':target,'operator':'OR','alternative_argument_refs':[a,a2],'additional_assumption_refs':[],
          'lifting_check':{'status':'NOT_REQUIRED','reason_locator':oloc,'evidence_refs':[]},'compatibility_check':{'status':'NOT_REQUIRED','reason_locator':oloc,'evidence_refs':[]}}
        oa,osid,oreq=self.add_path(f,target,obody,'REDUCTION',{'inference_spec':outer})
        self.assertEqual(assurance.evaluate_requirement(f.s,osid,oreq,'p')['result'],'QUALIFIED')
        f.s['withdrawals']['LIFT-W']={'support_id':ls,'scope':lr['required_scope'],'active':True}
        self.assertEqual(assurance.evaluate_requirement(f.s,osid,oreq,'p')['result'],'UNQUALIFIED');self.assertEqual(f.s['records'][target]['kind'],'Statement')

    def test_failed_sufficient_route_never_refutes_original_target(self):
        f=Fixture();target=f.add(statement('The original target T remains open.'));route=f.add(statement('An auxiliary sufficient condition A holds.'))
        a,sid,req=self.add_path(f,route,'A proposed sufficient-condition argument remains defective.')
        self.review(f,sid,req['required_scope'],verdict='DEFECT_FOUND')
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'CONFLICTED')
        view=assurance.evaluate(target,{'required_assurance':req},f.s)
        self.assertEqual(view['claim_outcome'],'OPEN');self.assertEqual(view['support_state'],'NO_ARGUMENT')

    def test_p6_gap_is_not_reduction_and_same_witness_is_not_boolean(self):
        f=Fixture();target=f.add(statement('There exists one witness satisfying both properties.'))
        comps=[self.add_path(f,f.add(statement('There exists a witness for property '+str(i)+'.')),'Witness '+str(i)+' satisfies its own local property.')[0] for i in range(2)]
        body='Separate local witnesses have not yet been identified with one common witness.'
        data={'conclusion_ref':target,'premise_bindings':[],'steps':[],'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[], 'mode':'REDUCTION','mode_payload':{'gap':'The lifting remains open.'}}
        with self.assertRaisesRegex(PMRSError,'UNKNOWN_FIELD|RESPONSE_SCHEMA_INVALID'):K.make_record('Argument',body,data,[],records=f.s['records'],blob_get=f.get)
        data['mode']='COMPATIBILITY';data['mode_payload']={'components':comps,'compatible':True}
        with self.assertRaisesRegex(PMRSError,'UNKNOWN_FIELD|RESPONSE_SCHEMA_INVALID'):K.make_record('Argument',body,data,[],records=f.s['records'],blob_get=f.get)
        witness={'target_ref':target,'component_argument_refs':comps,'context_refs':[],'variable_mapping':{},'common_data_refs':[],
          'quantifier_locators':[],'evidence_refs':[],'open_condition_refs':[]}
        a,sid,req=self.add_path(f,target,body,'COMPATIBILITY',{'witness_compatibility':witness})
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'UNQUALIFIED')
        self.assertIn('common witness',assurance.evaluate_requirement(f.s,sid,req,'p')['reasons'][0])

    def test_not_required_reduction_and_quantifier_gap_are_real_kcs_outcomes(self):
        f=Fixture();target=f.add(statement('There exists one P that works for every parameter lambda.'));t=f.task([target]);body='For every lambda there exists P; this does not supply one P for every lambda.'
        loc=K.locator(body);reduction={'premise_refs':[],'conclusion_ref':target,'operator':'AND','alternative_argument_refs':[],'additional_assumption_refs':[],
          'lifting_check':{'status':'NOT_REQUIRED','reason_locator':loc,'evidence_refs':[]},'compatibility_check':{'status':'NOT_REQUIRED','reason_locator':loc,'evidence_refs':[]}}
        d={'conclusion_ref':target,'premise_bindings':[],'steps':[],'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'REDUCTION','mode_payload':{'inference_spec':reduction}}
        op={'op':'NEW','local_key':'reduction','kind':'Argument','body':body,'context_refs':[],'data':d};f.accept(t,f.raw(t,[op]));self.assertFalse(f.s['obligations']);self.assertEqual(len(f.s['inferences']),1)
        gap=f.add(statement('One common witness for all parameters remains to be constructed.'))
        component=next(r for r,v in f.s['records'].items() if v['kind']=='Argument');cb='The unresolved quantifier exchange is explicitly retained as a condition.'
        w={'target_ref':target,'component_argument_refs':[component],'context_refs':[],'variable_mapping':{'lambda':'lambda','P':'P(lambda)'},'common_data_refs':[],
           'quantifier_locators':[K.locator(cb)],'evidence_refs':[component],'open_condition_refs':[gap]}
        a,sid,req=self.add_path(f,target,cb,'COMPATIBILITY',{'witness_compatibility':w})
        result=assurance.evaluate_requirement(f.s,sid,req,'p');self.assertEqual(result['result'],'UNQUALIFIED');self.assertIn(gap,result['open_conditions'])
        task=f.task([target,a],request='quantifier-gap');raw=json.loads(f.raw(task,outcome='NO_RESULT'))
        raw['payload']['new_obligation_proposals']=[{'local_key':'same-witness','type':'COMPATIBILITY','reason_code':None,
          'target_refs':[target],'criterion_body':'Construct one common witness valid for all parameters without exchanging quantifiers.',
          'scope_context_refs':[],'dependency_bindings':[],'consumer_binding_proposals':[],'effect_on_goal':'REQUIRED','reason_refs':[a]}]
        f.accept(task,canonical(raw));duty=next(iter(f.s['obligations'].values()))
        self.assertEqual(duty['definition']['type'],'COMPATIBILITY');self.assertEqual(duty['projection']['resolution'],'UNRESOLVED')

    def test_candidate_scoped_single_dual_missing_reuse_and_formulation(self):
        f,s,a,sid,scope=self.build();single=assurance.requirement('PROOF_SUPPORT',scope)
        from research_studio.obligations import dependency_met
        artifact={'threshold':'ARTIFACT_AVAILABLE','binding_ref':a,'scope':{}}
        qualified={'threshold':'SUPPORT_QUALIFIED','binding_ref':sid,'scope':{},'required_assurance':single,'policy_digest':'p'}
        self.assertTrue(dependency_met(f.s,artifact));self.assertFalse(dependency_met(f.s,qualified))
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,single,'p')['result'],'UNQUALIFIED')
        self.review(f,sid,scope,role='FORMULATION_REVIEW',kind='FORMULATION')
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,single,'p')['result'],'UNQUALIFIED')
        self.review(f,sid,scope)
        self.assertTrue(dependency_met(f.s,artifact));self.assertTrue(dependency_met(f.s,qualified))
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,single,'p')['result'],'QUALIFIED')
        dual=assurance.requirement('PROOF_SUPPORT',scope,review_mode='TARGET_DUAL');partial=assurance.evaluate_requirement(f.s,sid,dual,'p');self.assertEqual(partial['result'],'PARTIAL');self.assertEqual(partial['missing_slots'],['counterexample'])
        self.review(f,sid,scope,role='COUNTEREXAMPLE',kind='COUNTEREXAMPLE')
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,dual,'p')['result'],'QUALIFIED')
        bad=deepcopy(single);bad['review_slots']=[]
        with self.assertRaises(PMRSError):assurance.validate_requirement(bad)
        bad=deepcopy(single);bad['accepted_evidence_paths']=['FORMAL_TOOL']
        with self.assertRaises(PMRSError):assurance.validate_requirement(bad)
    def test_refutation_integration_defect_policy_and_formal_boundaries(self):
        f,s,a,sid,scope=self.build();refutation=assurance.requirement('REFUTATION_SUPPORT',scope)
        self.review(f,sid,scope,role='COUNTEREXAMPLE',kind='COUNTEREXAMPLE')
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,refutation,'p')['result'],'QUALIFIED')
        integration=assurance.requirement('INTEGRATION',scope)
        self.assertNotEqual(assurance.evaluate_requirement(f.s,sid,integration,'p')['result'],'QUALIFIED')
        self.review(f,sid,scope,role='INDEPENDENT',kind='INTEGRATION')
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,integration,'p')['result'],'QUALIFIED')
        self.review(f,sid,scope,verdict='DEFECT_FOUND');single=assurance.requirement('PROOF_SUPPORT',scope)
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,single,'different-policy')['result'],'CONFLICTED')
        g,st,ar,sp,sc=self.build();q=self.review(g,sp,sc);g.s['qualifications'][q]['evidence_origin']='FORMAL_TOOL'
        self.assertEqual(assurance.evaluate_requirement(g.s,sp,assurance.requirement('PROOF_SUPPORT',sc),'p')['result'],'UNQUALIFIED')
        for field,value in [('required_scope',[]),('review_slots',[])]:
            bad=deepcopy(single);bad[field]=value
            with self.assertRaises(PMRSError):assurance.validate_requirement(bad)
        bad=deepcopy(single);bad['review_slots'][0]['independence_required']=False
        with self.assertRaises(PMRSError):assurance.validate_requirement(bad)
        task=g.task([ar]);raw=json.loads(g.raw(task));raw['payload']['qualifications']=[{'evidence_origin':'FORMAL_TOOL','level':'FORMAL_CHECKED'}]
        with self.assertRaisesRegex(PMRSError,'UNKNOWN_FIELD'):changes.validate_response(task,g.s,canonical(raw),blob_get=g.get)

    def test_support_withdrawal_does_not_swap_paths_or_family(self):
        f,s,a,sid,scope=self.build();self.review(f,sid,scope);req=assurance.requirement('PROOF_SUPPORT',scope)
        a2=f.add(argument(s,body='A different witness proves the assertion.',records=f.s['records']));s2='SUP2';f.s['supports'][s2]={**deepcopy(f.s['supports'][sid]),'support_id':s2,'argument_ref':a2,'qualification_refs':[]}
        scope2=[{'target_ref':a2,'locators':[K.locator(f.blobs[f.s['records'][a2]['body_sha256']])],'aspects':['proof']}];self.review(f,s2,scope2)
        f.s['supports']['DOWN']={'support_id':'DOWN','premise_support_refs':[sid]};f.s['withdrawals']['W']={'support_id':sid,'active':True}
        self.assertEqual(relations.affected_supports(f.s,{sid}),{sid,'DOWN'})
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'WITHDRAWN')
        self.assertEqual(assurance.evaluate_requirement(f.s,s2,assurance.requirement('PROOF_SUPPORT',scope2),'p')['result'],'QUALIFIED')
        self.assertEqual(f.s['supports']['DOWN']['premise_support_refs'],[sid])
    def test_conflict_independent_scope_and_synthetic_authority(self):
        f,s,a,sid,scope=self.build();req=assurance.requirement('PROOF_SUPPORT',scope);self.review(f,sid,scope);self.review(f,sid,scope,verdict='DEFECT_FOUND')
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'CONFLICTED')
        for q in f.s['qualifications'].values():
            if f.s['records'][q['assessment_ref']]['data']['verdict']=='DEFECT_FOUND':q['withdrawn']=True
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'QUALIFIED')
        f.s['synthetic_test_only']=False;self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'UNQUALIFIED')

    def test_author_self_check_and_scope_extension_do_not_qualify(self):
        f,s,a,sid,scope=self.build();req=assurance.requirement('PROOF_SUPPORT',scope);q=self.review(f,sid,scope)
        e=f.s['review_executions'][f.s['qualifications'][q]['review_execution_event']];e['task_id']='AUTHOR'
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'UNQUALIFIED');e['task_id']='REVIEWER'
        larger=deepcopy(req);larger['required_scope'][0]['aspects'].append('quantifiers');larger['review_slots'][0]['required_scope']=deepcopy(larger['required_scope'])
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,larger,'p')['result'],'PARTIAL')
        body='A purported review.';d={'review_kind':'PROOF','target_refs':[a],'checked':[{'ref':a,'locators':[K.locator(body)],'aspect':'proof'}],'unchecked':[],'verdict':'SUPPORTED_WITHIN_SCOPE','findings':[],'scope_context_refs':[]}
        with self.assertRaisesRegex(PMRSError,'RESPONSE_SCHEMA_INVALID'):K.make_record('Assessment',body,d,[],records=f.s['records'],blob_get=f.get)

    def test_conditional_premise_remains_open_and_not_reverse_certified(self):
        f,s,a,sid,scope=self.build();p=f.add(statement('An unresolved premise P holds.'));ab='Assuming P, the conclusion follows conditionally.'
        d={'conclusion_ref':s,'premise_bindings':[{'premise_ref':p,'kind':'CONDITIONAL_CANDIDATE','context_ref':None,'scope_locator':None,'binding_mode':'PINNED','support_ref':None,'assumption_locator':None}],
           'steps':[],'discharged_assumptions':[],'open_conditions':[{'condition_ref':p,'locator':K.locator(ab)}],'witness_bindings':[],'mode':'PROOF','mode_payload':{}}
        a2=f.add(K.make_record('Argument',ab,d,[],records=f.s['records'],blob_get=f.get));f.s['supports'][sid]['argument_ref']=a2
        scope2=[{'target_ref':a2,'locators':[K.locator(ab)],'aspects':['proof']}];self.review(f,sid,scope2)
        r=assurance.evaluate_requirement(f.s,sid,assurance.requirement('PROOF_SUPPORT',scope2),'p');self.assertEqual(r['result'],'UNQUALIFIED');self.assertTrue(r['open_conditions'])
        self.assertFalse([v for v in f.s['supports'].values() if v['statement_ref']==p])

    def test_a1_defect_cannot_authorize_withdrawal_of_a2(self):
        f,s,a,sid,scope=self.build();q=self.review(f,sid,scope,verdict='DEFECT_FOUND')
        other,other_sid,other_req=self.add_path(f,s,'A separate complete argument uses its own source path.')
        evidence=f.s['qualifications'][q]['assessment_ref'];task=f.task([a,other,evidence],request='wrong-path')
        op={'op':'WITHDRAW_SUPPORT','support_id':other_sid,'expected_qualification_head':C.digest(f.s['supports'][other_sid]['qualification_refs']),
           'scope':scope,'reason_code':'WRONG_PATH','evidence_refs':[evidence]}
        with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):changes.validate_response(task,f.s,f.raw(task,[op]),blob_get=f.get)
        self.assertEqual(assurance.evaluate_requirement(f.s,other_sid,other_req,'p')['result'],'QUALIFIED')

    def test_scoped_withdrawal_outside_consumer_does_not_erase_support(self):
        f,s,a,sid,scope=self.build();self.review(f,sid,scope);req=assurance.requirement('PROOF_SUPPORT',scope)
        outside=deepcopy(scope);outside[0]['aspects']=['unrelated-application']
        f.s['withdrawals']['W']={'support_id':sid,'active':True,'scope':outside}
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'QUALIFIED')
        f.s['withdrawals']['W']['scope']=scope
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'WITHDRAWN')

    def test_human_adoption_is_not_scoped_mathematical_attestation(self):
        f,s,a,sid,scope=self.build();q=self.review(f,sid,scope);credential=f.s['qualifications'][q]
        credential.update(evidence_origin='HUMAN_ATTESTATION',attestation_ref='ADOPT')
        f.s['human_attestations']={'ADOPT':{'kind':'HUMAN_DECISION','explicit_check':False}}
        req=assurance.requirement('PROOF_SUPPORT',scope,accepted_evidence_paths=['HUMAN_ATTESTATION'])
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'UNQUALIFIED')
        f.s['human_attestations']['ADOPT']={'kind':'SCOPED_MATHEMATICAL_ATTESTATION','explicit_check':True,'target_revision_hashes':[a],'checked_scope':scope}
        self.assertEqual(assurance.evaluate_requirement(f.s,sid,req,'p')['result'],'QUALIFIED')
    def test_provenance_method_inspiration_and_feedback_isolation(self):
        f,s,a,sid,scope=self.build();q=self.review(f,sid,scope);review=f.s['qualifications'][q]['assessment_ref']
        source='SO-original';raw=b'A method can be tried without relying on its theorem.';h=sha(raw);f.blobs[h]=raw;f.s['sources'][source]={'source_id':source,'blob_hash':h,'access_class':'SCIENTIFIC_SOURCE','provenance_refs':[]}
        f.s['relations']=[relations.relation(a,source,'SOURCE_PROVENANCE'),relations.relation(a,review,'RESPONDS_TO_FEEDBACK')]
        packet=context.build_packet(f.s,[a],f.get,independent=True);self.assertIn(a,packet['records']);self.assertNotIn(review,packet['records']);self.assertFalse(packet['sources'])
        use={'source_ref':source,'locators':[K.locator(raw)],'usage_mode':'METHOD_INSPIRATION','trust_boundary':'Technique only.'}
        f.s['relations'].append(relations.relation(a,source,'USED_SOURCE',evidence_bindings=[use]))
        self.assertNotIn(source,relations.premise_closure([a],f.s));self.assertIn(source,context.build_packet(f.s,[a],f.get,include_method_sources=True)['sources'])
        f.s['relations'][-1]['evidence_bindings'][0]['usage_mode']='STATEMENT_RELIANCE';self.assertIn(source,relations.premise_closure([a],f.s))
        f.s['sources'][source]['access_class']='HISTORICAL_REVIEW'
        with self.assertRaisesRegex(PMRSError,'FORBIDDEN_REVIEW_DERIVATIVE'):context.build_packet(f.s,[a],f.get,independent=True)

    def test_complete_dependency_body_and_verdict_derivatives_fail_closed(self):
        f,s,a,sid,scope=self.build();q=self.review(f,sid,scope);review=f.s['qualifications'][q]['assessment_ref']
        cb='Let the fixed notation denote the complete ambient construction.';cl=K.locator(cb)
        cd={'definitions':[{'key':'ambient','locator':cl}],'objects':[],'assumptions':[],'quantifiers':[],'conventions':[],'parent_context_refs':[]}
        ctx=f.add(K.make_record('Context',cb,cd,[]))
        ab='With the complete ambient definition, the proposed argument remains explicit.'
        ad={'conclusion_ref':s,'premise_bindings':[{'premise_ref':ctx,'kind':'DEFINITION','context_ref':ctx,'scope_locator':cl,'binding_mode':'PINNED','support_ref':None,'assumption_locator':None}],
            'steps':[],'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'PROOF','mode_payload':{}}
        revised=f.add(K.make_record('Argument',ab,ad,[ctx],records=f.s['records'],blob_get=f.get))
        f.s['relations'].append(relations.relation(revised,review,'RESPONDS_TO_FEEDBACK'))
        packet=context.build_packet(f.s,[revised],f.get,independent=True)
        self.assertEqual(packet['bodies'][f.s['records'][ctx]['body_sha256']],cb.encode());self.assertNotIn(review,packet['records'])
        self.assertNotIn('SUPPORTED_WITHIN_SCOPE',str(packet))
        f.s['relations'].append(relations.relation(revised,review,'MATHEMATICAL_DEPENDENCY'))
        with self.assertRaisesRegex(PMRSError,'NON_SELF_CONTAINED'):context.build_packet(f.s,[revised],f.get,independent=True)
        f.s['relations'].pop();sid2='SO-summary';raw=b'The previous assessment confirms the construction.';h=sha(raw);f.blobs[h]=raw
        f.s['sources'][sid2]={'source_id':sid2,'blob_hash':h,'access_class':'SCIENTIFIC_SOURCE','provenance_refs':[review]}
        with self.assertRaisesRegex(PMRSError,'FORBIDDEN_REVIEW_DERIVATIVE'):context.build_packet(f.s,[revised],f.get,independent=True,required_source_refs=[sid2])
    def test_capacity_unknown_full_request_and_successful_slot_partition_integration(self):
        capacity={'model_id':'fixture','capacity_source':'SYNTHETIC_TEST_ONLY','capacity_revision':'1','context_window_tokens':70,'model_max_output_tokens':10,'tokenizer_revision':'test-byte-exact'}
        with self.assertRaisesRegex(PMRSError,'CONTEXT_LIMIT'):context.token_preflight(b'long',capacity,reserved_output_tokens=10)
        with self.assertRaisesRegex(PMRSError,'CONTEXT_LIMIT'):context.token_preflight(b'x'*100,capacity,reserved_output_tokens=10,token_counter=len)
        budget=context.token_preflight(b'x'*55,capacity,reserved_output_tokens=10,safety_margin_tokens=5,token_counter=len);self.assertEqual(budget['input_tokens'],55)
        raw=b'x'*100;target='KR-'+sha(b'target');scope=[{'target_ref':target,'locators':[K.locator(raw)],'aspects':['proof']}];req=assurance.requirement('PROOF_SUPPORT',scope,review_mode='TARGET_DUAL')
        parts=[];results={}
        for slot in req['review_slots']:
            for i,(a,b) in enumerate([(0,50),(50,100)]):
                pid=slot['slot_id']+str(i);partial=[{'target_ref':target,'locators':[K.locator(raw,a,b)],'aspects':['proof']}]
                parts.append({'part_id':pid,'review_slot_id':slot['slot_id'],'checked_scope':partial,'required_input_refs':[target],'declared_boundary_refs':[],'task_ref':'T'+pid});results[pid]={'result':'QUALIFIED','checked_scope':partial}
                context.token_preflight(raw[a:b],capacity,reserved_output_tokens=10,token_counter=len)
        integration=[{'target_ref':target,'locators':[K.locator(raw,49,51)],'aspects':['interface']}]
        plan={'plan_id':'PLAN','target_revision_refs':[target],'required_scope':scope,'parts':parts,'integration_scope':integration}
        self.assertEqual(context.aggregate_coverage(plan,req,results)['result'],'PARTIAL')
        result=context.aggregate_coverage(plan,req,results,{'result':'QUALIFIED','independent':True,'checked_scope':integration});self.assertEqual(result['result'],'QUALIFIED');self.assertEqual(result['not_checked'],[])
        del results['proof1'];del results['counterexample0']
        result=context.aggregate_coverage(plan,req,results,{'result':'QUALIFIED','independent':True,'checked_scope':integration});self.assertEqual(result['result'],'PARTIAL');self.assertTrue(result['not_checked'])

class PersistedKernelTests(unittest.TestCase):
    def setUp(self):
        from research_studio.engine import Engine
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.engine=Engine();self.store=self.engine.create(Path(self.tmp.name)/'project',b'Investigate the fixed original assertion.',synthetic=True)
        self.target=next(iter(self.store.read_snapshot()['records']))
        self.policy={'capacity':{'model_id':'gpt-6-astra','capacity_source':'SYNTHETIC_TEST_ONLY','capacity_revision':'1','context_window_tokens':1000000,'model_max_output_tokens':10000,'tokenizer_revision':'test-byte-bound','token_count_bound':'UTF8_BYTES','tokenizer_byte_bound_verified':True},
            'reserved_output_tokens':1024,'safety_margin_tokens':64,'resource_policy_revision':'test-resources/1','executor_contract':{'executor':'fake','sandbox':'test-only'}}

    def workflow(self,kind='TRW',name='one'):
        from research_studio.obligations import make
        from research_studio.demo import discovery_scope
        row=self.engine.new_workflow(self.store,kind,target_ref=self.target if kind=='TRW' else None,discovery_scope=None if kind=='TRW' else discovery_scope('Explore exact formulations and preserve the background.'))
        iid=row['instance_id'];mid='M-'+name;oid='O-'+name;bid='B-'+name;grant='G-'+name
        consumer={'binding_id':bid,'instance_id':iid,'mission_id':mid,'stage_id':'P4' if kind=='TRW' else 'D1','role':'RESEARCH','retry_grant_id':grant,'method_ref':'METHOD-'+name,
           'scope':{'target_ref':self.target},'entry_basis':{},'threshold':'ARTIFACT_AVAILABLE'}
        criterion=self.store.blob(('Investigate the exact assertion with method '+name+'.').encode())
        obligation=make(oid,'ESTABLISH' if kind=='TRW' else 'APPLICABILITY',[self.target],criterion,consumer_bindings=[consumer])
        mission={'mission_id':mid,'intent':'Investigate within the stated finite scope.','authorized_scope':{'target_refs':[self.target],'obligation_ids':[oid]},'obligations':[obligation],
          'retry_grants':[{'grant_id':grant,'obligation_id':oid,'method_ref':'METHOD-'+name,'max_research_attempts':3,'reason_ref':'Explicit synthetic fixture authorization.'}]}
        self.engine.authorize(self.store,iid,mission,{'max_calls':3,'max_workers':2,'execution_policy':self.policy})
        prepared=self.engine.prepare(self.store,iid,self.policy)['prepared'][0];task=self.store.read_snapshot()['tasks'][prepared['task_id']]
        return iid,task

    def capture(self,task,ops=(),outcome='NO_RESULT'):
        from research_studio import execution
        effect={'binding_id':task['obligation_bindings'][0]['binding_id'],'expected_definition_revision':1,'work_disposition':'NO_RESULT' if outcome=='NO_RESULT' else 'ADDRESSED',
           'resolution_proposal':'UNRESOLVED' if outcome=='NO_RESULT' else 'CANDIDATE_RESPONSE','evidence_refs':[],'remaining_conditions':[],'blocker_proposals':[]}
        raw=Fixture().raw(task,ops,effects=[effect],outcome=outcome)
        reservation=execution.reserve(self.store,task['request_id'],execution_kind='SYNTHETIC_TEST_ONLY')
        execution.capture(self.store,task['request_id'],raw,execution_id=reservation['execution_id'])
        return raw

    def test_two_workflows_shared_content_unrelated_commits_and_recovery(self):
        from research_studio import execution
        i1,t1=self.workflow('TRW','trw');i2,t2=self.workflow('TFDW','tfdw')
        ref,record,body=statement('A single shared lemma candidate has an explicit quantifier.')
        op={'op':'NEW','local_key':'lemma','kind':'Statement','context_refs':[],'body':body.decode(),'data':record['data']}
        other,other_record,other_body=statement('A different scoped candidate is also available.')
        other_op={'op':'NEW','local_key':'other','kind':'Statement','context_refs':[],'body':other_body.decode(),'data':other_record['data']}
        raw1=self.capture(t1,[op],'RESULT');raw2=self.capture(t2,[op,other_op],'RESULT')
        first=execution.recover(self.store,t1['request_id']);second=execution.recover(self.store,t2['request_id'])
        self.assertIn(ref,first['receipt']['content_added']);self.assertEqual(second['receipt']['content_added'],[other]);self.assertEqual(second['receipt']['content_reused'],[ref])
        state=self.store.read_snapshot();self.assertEqual(sum(p['record_ref']==ref for p in state['production_events'].values()),2)
        self.assertEqual(state['instances'][i1]['target_ref'],self.target);self.assertIsNone(state['instances'][i2]['target_ref'])
        self.assertTrue(any(c['statement_ref']==ref and c['instance_id']==i2 for c in state['candidates'].values()))
        self.assertFalse(state['supports']);head=self.store._head();requests=deepcopy(state['requests'])
        for _ in range(3):self.assertEqual(execution.recover(self.store,t1['request_id'])['state'],'EXACT_DUPLICATE')
        self.assertEqual(self.store._head(),head);self.assertEqual(self.store.read_snapshot()['requests'],requests)
        self.assertEqual(self.store.read_blob(sha(raw1)),raw1);self.assertEqual(self.store.read_blob(sha(raw2)),raw2);self.store.audit()
        # Reopening a new Store object replays the authoritative journal.
        from research_studio.store import Store
        reopened=Store(self.store.root);self.assertEqual(reopened.read_snapshot()['records'],state['records'])

    def test_pause_capture_and_preflight_do_not_admit_or_resend(self):
        from research_studio import execution
        iid,task=self.workflow();raw=self.capture(task)
        self.engine.pause(self.store,iid,'Pause after capture.');head=self.store._head()
        self.assertTrue(self.engine.preflight(self.store,task['task_id'],raw)['valid']);self.assertEqual(head,self.store._head())
        with self.assertRaisesRegex(PMRSError,'TASK_FENCED'):execution.recover(self.store,task['request_id'])
        self.assertEqual(self.store.read_snapshot()['requests'][task['request_id']]['execution_state'],'CAPTURED')
        s=self.store.read_snapshot();decision=self.engine.decide(self.store,iid,'CONTINUE','Resume this authorized scope.',snapshot_commit=s['knowledge_commit'])
        self.engine.resume(self.store,iid,decision);result=execution.recover(self.store,task['request_id']);self.assertEqual(result['state'],'ACCEPTED')
        self.assertEqual(len(self.store.read_snapshot()['requests']),1)

    def test_resource_revision_affects_only_future_frozen_task(self):
        from research_studio import execution
        iid,task=self.workflow();before=canonical(task);self.capture(task);execution.recover(self.store,task['request_id'])
        policy=deepcopy(self.policy);policy['resource_policy_revision']='test-resources/2';policy['capacity']['context_window_tokens']+=100000
        next_task=self.engine.prepare(self.store,iid,policy)['prepared'][0]
        state=self.store.read_snapshot();after=state['tasks'][task['task_id']];new=state['tasks'][next_task['task_id']]
        self.assertEqual(before,canonical(after));self.assertEqual(new['resource_policy_revision'],'test-resources/2');self.assertEqual(state['schema'],C.PROJECT_SCHEMA)
        self.assertGreater(new['context_budget']['context_window_tokens'],after['context_budget']['context_window_tokens'])

if __name__=='__main__':unittest.main()
