"""4.2.2 contract safety, exact scope and typed-assumption regressions.

Small synthetic records, no model calls and no real project reads or writes.
"""
from copy import deepcopy
import json
import unittest
from research_studio import contracts as C,changes,knowledge as K,assurance,relations
from research_studio.util import canonical,sha,PMRSError
from tests.test_final_kernel import Fixture,statement,argument
from tests import test_final_kernel as kernel_fixtures


def operation(kind,body,data,key='new',contexts=()):
    return {'op':'NEW','local_key':key,'kind':kind,'context_refs':list(contexts),'body':body,'data':data}


def context_record(f,body='The number x is real.'):
    loc=K.locator(body);data={k:[] for k in ('definitions','objects','assumptions','quantifiers','conventions')}
    data['assumptions']=[{'key':'real_x','locator':loc}];data['parent_context_refs']=[]
    return f.add(K.make_record('Context',body,data,[])),loc


class FormatContract421(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.target=self.f.add(statement());self.task=self.f.task([self.target]);self.task['response_contract_revision']=C.AUTHORING_REVISION
    def arg_op(self):
        _,record,body=argument(self.target,records=self.f.s['records'])
        return operation('Argument',body.decode(),record['data'],'arg')
    def repair_task(self,original):
        h=sha(original);self.f.blobs[h]=original
        self.f.s['requests'][self.task['request_id']]={'task_id':self.task['task_id'],'capture_ref':h}
        t=deepcopy(self.task);t.update(task_id='repair-task',request_id='repair-request',repair_kind='FORMAT',repair_of=self.task['request_id'])
        return t
    def repaired(self,original,task):
        value=json.loads(original);value['task_id']=task['task_id'];value['request_id']=task['request_id']
        value['payload']['task_id']=task['task_id'];value['payload']['request_id']=task['request_id']
        return value
    def test_complete_schema_drives_admission_and_prunes_other_roles(self):
        schema=C.authoring_contract(self.task,self.f.s)['response_schema']
        raw=self.f.raw(self.task,[self.arg_op()]);self.assertFalse(C.schema_diagnostics(json.loads(raw),schema))
        self.assertEqual(changes.validate_response(self.task,self.f.s,raw,blob_get=self.f.get)['outcome'],'ACCEPTED')
        self.assertNotIn('SurveyResult',schema['$defs']);self.assertNotIn('ReportOutput',schema['$defs'])
        bad=json.loads(raw);bad['payload']['operations'][0]['data']['open_conditions']='none'
        ds=C.schema_diagnostics(bad,schema);self.assertEqual(ds[0]['pointer'],'/payload/operations/0/data/open_conditions')
        with self.assertRaises(PMRSError) as err:changes.validate_response(self.task,self.f.s,canonical(bad),blob_get=self.f.get)
        self.assertEqual(err.exception.diagnostic['pointer'],ds[0]['pointer'])
    def test_compact_schema_restores_every_original_branch_and_required_field(self):
        from unittest.mock import patch
        def normal(node,defs,active=()):
            if not isinstance(node,dict):return node
            if '$ref' in node:
                ref=node['$ref'];name=ref[8:] if ref.startswith('#/$defs/') else next(k for k,v in defs.items() if v.get('$anchor')==ref[1:])
                if name in active:return {'$ref':'#/$defs/'+name}  # Retain the same recursive retry edge.
                return normal(defs[name],defs,active+(name,))
            result={k:v for k,v in node.items() if k not in ('$defs','$anchor')}
            for key,item in tuple(result.items()):
                if key=='properties':result[key]={k:normal(v,defs,active) for k,v in item.items()}
                elif key in ('items','not','additionalProperties') and isinstance(item,dict):result[key]=normal(item,defs,active)
                elif key in ('oneOf','anyOf','allOf'):result[key]=[normal(v,defs,active) for v in item]
            props=result.get('properties',{})
            if result.get('additionalProperties') is False and result.get('minProperties')==len(props):
                result.pop('minProperties');result['required']=list(props)
            if 'required' in result:result['required']=sorted(result['required'])
            factors=result.get('allOf',[])
            if len(factors)==1 and set(factors[0])=={'oneOf'} and props.get('kind')=={} and props.get('data')=={}:
                branches=[]
                for pair in factors[0]['oneOf']:
                    self.assertEqual(set(pair),{'properties'});self.assertEqual(set(pair['properties']),{'kind','data'})
                    branch={k:deepcopy(v) for k,v in result.items() if k!='allOf'}
                    branch['properties'].update(pair['properties']);branches.append(branch)
                result={'oneOf':branches}
            if 'oneOf' in result:
                result['oneOf']=[branch for child in result['oneOf'] for branch in (child['oneOf'] if set(child)=={'oneOf'} else [child])]
            return result
        cases=[None,self.task,{**self.task,'actor_kind':'MAIN'}]
        for payload,role in [('SURVEY_RESULT',r) for r in ('SEARCH_PLAN','SOURCE_READ','ORGANIZE','READINESS_REVIEW')]+[('REPORT_OUTPUT','REPORT_AUTHOR'),('REPORT_REVIEW','REPORT_SEMANTIC'),('REPORT_REVIEW','REPORT_VISUAL')]:
            task=deepcopy(self.task);task['role']=role;task['permission_manifest']['allowed_payload_kinds']=[payload]
            if payload.startswith('REPORT'):task['report_context']={'profile':'lecture'}
            cases.append(task)
        section=deepcopy(cases[-3]);section['report_context']['revision_request']={'scope':{'kind':'SECTIONS'}};cases.append(section)
        for task in cases:
            with self.subTest(role=(task or {}).get('role'),actor=(task or {}).get('actor_kind')):
                with patch.object(C,'_compact_authoring_schema',side_effect=lambda s:s):before=C.authoring_contract(task,self.f.s)['response_schema']
                after=C.authoring_contract(task,self.f.s)['response_schema']
                self.assertEqual(normal(before,before['$defs']),normal(after,after['$defs']))
                self.assertLess(len(canonical(after)),len(canonical(before)))
        schema=C.authoring_contract(self.task,self.f.s)['response_schema'];value=json.loads(self.f.raw(self.task,[self.arg_op()]))
        for path in [(),('payload',),('payload','operations',0)]:
            original=value
            for key in path:original=original[key]
            for key in original:
                changed=deepcopy(value);node=changed
                for part in path:node=node[part]
                node.pop(key)
                diagnostics=C.schema_diagnostics(changed,schema)
                self.assertIn('/'+'/'.join(str(part) for part in (*path,key)),[d['pointer'] for d in diagnostics],[path,key])
    def test_wire_only_repair_has_capture_snapshot_and_implementation_proof(self):
        raw=json.loads(self.f.raw(self.task,[self.arg_op()]));raw['request_id']='wrong';raw['payload']['read_set_digest']='wrong';raw=canonical(raw)
        proof=changes.format_repair_evidence(self.task,self.f.s,raw,self.f.get)
        self.assertTrue(proof['eligible'],proof);self.assertEqual(proof['capture_sha256'],sha(raw));self.assertEqual(proof['snapshot_digest'],C.digest(self.f.s))
        self.assertIn('changes.py',proof['validator_revision']['modules']);self.assertTrue(proof['projection_digest'])
        repair=self.repair_task(raw);fixed=changes._wire_repair(json.loads(raw),repair)
        changes.validate_response(repair,self.f.s,canonical(fixed),blob_get=self.f.get)
    def test_five_premise_kinds_use_the_native_endpoint_matrix(self):
        ctx,loc=context_record(self.f);upstream=self.f.add(argument(self.target,records=self.f.s['records']))
        endpoints={'DEFINITION':ctx,'CONTEXT_ASSUMPTION':ctx,'SUPPORTED_STATEMENT':self.target,'DERIVATION_COMPONENT':upstream,'CONDITIONAL_CANDIDATE':self.target}
        for kind,ref in endpoints.items():
            with self.subTest(kind=kind):
                op=self.arg_op();binding={'premise_ref':ref,'kind':kind,'context_ref':ctx if kind=='CONTEXT_ASSUMPTION' else None,'scope_locator':None,'binding_mode':'PINNED','support_ref':'SUP-exact' if kind=='SUPPORTED_STATEMENT' else None,'assumption_locator':loc if kind=='CONTEXT_ASSUMPTION' else None}
                op['data']['premise_bindings']=[binding]
                if kind=='CONDITIONAL_CANDIDATE':op['data']['open_conditions']=[{'condition_ref':self.target,'locator':K.locator(op['body'])}]
                K.make_record('Argument',op['body'],op['data'],[ctx],records=self.f.s['records'],blob_get=self.f.get)
                wrong=deepcopy(op['data']);wrong['premise_bindings'][0]['premise_ref']=upstream if kind=='CONTEXT_ASSUMPTION' else self.target if kind in {'DEFINITION','DERIVATION_COMPONENT'} else ctx
                with self.assertRaisesRegex(PMRSError,'RELATION_ENDPOINT_INVALID'):K.make_record('Argument',op['body'],wrong,[ctx],records=self.f.s['records'],blob_get=self.f.get)
        t=self.f.task([self.target]);t['read_set'][0]['required_support_refs']=['SUP-exact'];op=self.arg_op()
        op['data']['premise_bindings']=[{'premise_ref':self.target,'kind':'SUPPORTED_STATEMENT','context_ref':None,'scope_locator':None,'binding_mode':'PINNED','support_ref':'SUP-exact','assumption_locator':None}]
        self.f.s['supports']['SUP-exact']={'statement_ref':self.target,'argument_ref':upstream,'qualification_refs':[]}
        with self.assertRaisesRegex(PMRSError,'DEPENDENCY_UNQUALIFIED'):changes.validate_response(t,self.f.s,self.f.raw(t,[op]),blob_get=self.f.get)

    def test_mixed_structure_and_endpoint_cannot_get_format(self):
        op=self.arg_op();op['data']['premise_bindings']=[{'premise_ref':self.target,'kind':'DEFINITION','context_ref':None,'scope_locator':None,'binding_mode':'PINNED','support_ref':None,'assumption_locator':None}]
        raw=json.loads(self.f.raw(self.task,[op]));raw['request_id']='wrong'
        proof=changes.format_repair_evidence(self.task,self.f.s,canonical(raw),self.f.get)
        self.assertFalse(proof['eligible']);d=next(x for x in proof['diagnostics'] if x['code']=='RELATION_ENDPOINT_INVALID')
        self.assertEqual(d['pointer'],'/payload/operations/0/data/premise_bindings/0/premise_ref');self.assertEqual(d['actual']['record_kind'],'Statement')
    def test_mixed_structure_and_permission_cannot_get_format(self):
        self.task['permission_manifest']['allowed_record_kinds']=['Context']
        value=json.loads(self.f.raw(self.task,[self.arg_op()]));value['task_id']='wrong'
        proof=changes.format_repair_evidence(self.task,self.f.s,canonical(value),self.f.get)
        self.assertFalse(proof['eligible'])
    def test_unparseable_duplicate_and_missing_payload_never_get_format(self):
        for raw in (b'{',b'{"payload":{},"payload":{"operations":[]}}',b'{}'):
            with self.subTest(raw=raw):
                proof=changes.format_repair_evidence(self.task,self.f.s,raw,self.f.get);self.assertFalse(proof['eligible'])
                repair=self.repair_task(raw)
                with self.assertRaisesRegex(PMRSError,'REPAIR_SCIENCE_UNVERIFIABLE'):changes.validate_response(repair,self.f.s,self.f.raw(repair),blob_get=self.f.get)
    def test_science_mutation_matrix_locks_full_nested_payload(self):
        op=self.arg_op();p=op['data'];p['premise_bindings']=[{'premise_ref':self.target,'kind':'CONDITIONAL_CANDIDATE','context_ref':None,'scope_locator':None,'binding_mode':'PINNED','support_ref':None,'assumption_locator':None}]
        p['open_conditions']=[{'condition_ref':self.target,'locator':K.locator(op['body'])}]
        value=json.loads(self.f.raw(self.task,[op]));value['payload']['obligation_effects']=[{'binding_id':'B','expected_definition_revision':1,'work_disposition':'PARTIAL','resolution_proposal':'UNRESOLVED','evidence_refs':[],'remaining_conditions':['The gap remains.'],'blocker_proposals':[]}]
        value['payload']['new_obligation_proposals']=[{'local_key':'gap','type':'ESTABLISH','reason_code':None,'target_refs':[self.target],'criterion_body':'Establish this exact remaining implication.','scope_context_refs':[],'dependency_bindings':[],'consumer_binding_proposals':[],'effect_on_goal':'REQUIRED','reason_refs':[]}]
        original=canonical(value);repair=self.repair_task(original)
        cases=[('kind',lambda v:v['payload']['operations'][0].update(kind='Context')),
          ('body',lambda v:v['payload']['operations'][0].update(body='A changed mathematical assertion.')),
          ('contexts',lambda v:v['payload']['operations'][0].update(context_refs=['KR-other'])),
          ('premise kind',lambda v:v['payload']['operations'][0]['data']['premise_bindings'][0].update(kind='SUPPORTED_STATEMENT')),
          ('premise ref',lambda v:v['payload']['operations'][0]['data']['premise_bindings'][0].update(premise_ref='KR-other')),
          ('support',lambda v:v['payload']['operations'][0]['data']['premise_bindings'][0].update(support_ref='SUP-other')),
          ('open',lambda v:v['payload']['operations'][0]['data'].update(open_conditions=[])),
          ('discharged',lambda v:v['payload']['operations'][0]['data'].update(discharged_assumptions=[K.locator(op['body'])])),
          ('mode',lambda v:v['payload']['operations'][0]['data'].update(mode='DERIVATION')),
          ('conclusion',lambda v:v['payload']['operations'][0]['data'].update(conclusion_ref='KR-other')),
          ('effects removal',lambda v:v['payload'].update(obligation_effects=[])),
          ('effect conditions',lambda v:v['payload']['obligation_effects'][0].update(remaining_conditions=[])),
          ('gap type',lambda v:v['payload']['new_obligation_proposals'][0].update(type='REFUTE')),
          ('gap criterion',lambda v:v['payload']['new_obligation_proposals'][0].update(criterion_body='A different gap.')),
          ('gap dependency',lambda v:v['payload']['new_obligation_proposals'][0].update(dependency_bindings=[{'binding_ref':'OB-new'}])),
          ('account',lambda v:v['payload'].update(attempt_account='Another attempt was performed.')),
          ('claimed',lambda v:v['payload'].update(claimed_change='The original target is established.')),
          ('strategy',lambda v:v['payload'].update(strategy_proposal={'next_action':'DELIVER'})),
          ('message',lambda v:v['payload'].update(message_dispositions=[{'message_id':'M','disposition':'USED','reason':'Used.','record_refs':[]}]))]
        for name,mutate in cases:
            with self.subTest(name=name):
                after=self.repaired(original,repair);mutate(after)
                with self.assertRaisesRegex(PMRSError,'REPAIR_SCIENCE_CHANGED'):changes.validate_response(repair,self.f.s,canonical(after),blob_get=self.f.get)
    def test_review_and_survey_fields_cannot_be_rewritten(self):
        body='The assigned exact argument is inconclusive.'
        data={'review_kind':'PROOF','target_refs':[self.target],'checked':[],'unchecked':[{'ref':self.target,'aspect':'proof','reason':'Not established.'}],'verdict':'INCONCLUSIVE','findings':[],'scope_context_refs':[]}
        value=json.loads(self.f.raw(self.task,[operation('Assessment',body,data)]));original=canonical(value);repair=self.repair_task(original)
        for field,new in [('verdict','SUPPORTED_WITHIN_SCOPE'),('checked',[{'ref':self.target,'locators':[],'aspect':'proof'}]),('unchecked',[])]:
            after=self.repaired(original,repair);after['payload']['operations'][0]['data'][field]=new
            with self.assertRaisesRegex(PMRSError,'REPAIR_SCIENCE_CHANGED'):changes.validate_response(repair,self.f.s,canonical(after),blob_get=self.f.get)
        survey={**value,'payload_kind':'SURVEY_RESULT','payload':{'schema':'pmrs.survey-result/1','knowledge_change':value['payload'],'action':'REVIEW','data':{'verdict':'NEEDS_WORK'}}}
        a=changes.science_projection(survey);survey['payload']['data']['verdict']='READY';self.assertNotEqual(a,changes.science_projection(survey))
    def test_locator_alias_and_explicit_full_body_have_identical_projection(self):
        op=self.arg_op();loc=op['data']['steps'][0]['locator'];original=json.loads(self.f.raw(self.task,[op]));aliased=deepcopy(original)
        aliased['payload']['operations'][0]['data']['steps'][0]['locator']={**loc,'blob_hash':'body:arg','quoted_sha256':None}
        self.assertEqual(changes.science_projection(original),changes.science_projection(aliased))


class ScopeConditions421(unittest.TestCase):
    def test_whole_and_full_range_equivalence_without_legacy_promotion(self):
        f=Fixture();target=f.add(statement());body=f.get(f.s['records'][target]['body_sha256']);legacy=[{'target_ref':target,'locators':[],'aspects':['proof']}]
        concrete=[{**legacy[0],'locators':[K.locator(body)]}]
        self.assertFalse(assurance.coverage(legacy,concrete)['complete'])
        whole=assurance.normalize_scope(legacy,f.s,f.get);full=assurance.normalize_scope(concrete,f.s,f.get)
        self.assertTrue(assurance.coverage(whole,full)['complete']);self.assertTrue(assurance.coverage(full,whole)['complete'])
        partial=assurance.normalize_scope([{**legacy[0],'locators':[K.locator(body,0,len(body)//2)]}],f.s,f.get)
        self.assertFalse(assurance.coverage(whole,partial)['complete']);self.assertFalse(assurance.coverage(whole,legacy)['complete'])
        forged=deepcopy(full);forged[0]['locators'][0]['blob_hash']='0'*64;self.assertFalse(assurance.coverage(whole,forged)['complete'])
        with self.assertRaises(PMRSError):assurance.validate_scope(forged)
    def conditional(self):
        f=Fixture();ctx,loc=context_record(f);body='Under the declared real-number hypothesis, the square of x is nonnegative.'
        _,st,_=statement(body);st['data']['hypothesis_locators']=[loc];st['data']['scope_context_refs']=[ctx]
        target=f.add(K.make_record('Statement',body,st['data'],[ctx],records=f.s['records'],blob_get=f.get))
        abody='For a real number x, its square is nonnegative by the ordered-field axioms.'
        data={'conclusion_ref':target,'premise_bindings':[{'premise_ref':ctx,'kind':'CONTEXT_ASSUMPTION','context_ref':ctx,'scope_locator':None,'binding_mode':'PINNED','support_ref':None,'assumption_locator':loc}],
            'steps':[],'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'PROOF','mode_payload':{}}
        a=f.add(K.make_record('Argument',abody,data,[ctx],records=f.s['records'],blob_get=f.get));sid='SUP'
        f.s['supports'][sid]={'support_id':sid,'statement_ref':target,'argument_ref':a,'premise_support_refs':[],'open_assumption_refs':[ctx],'qualification_refs':[],'author_task_id':'AUTHOR'}
        scope=[{'target_ref':r,'locators':[K.locator(f.get(f.s['records'][r]['body_sha256']))],'aspects':['complete_scientific_argument']} for r in (target,a)]
        req=assurance.requirement('PROOF_SUPPORT',scope,assumption_policy=assurance.declared_assumption_policy(f.s,target,a))
        q=kernel_fixtures.AssuranceContextTests().review(f,sid,scope);f.s['qualifications'][q]['policy_digest']=C.digest(req)
        return f,target,a,sid,req,q
    def test_declared_hypothesis_qualified_only_for_exact_typed_consumer(self):
        f,target,a,sid,req,q=self.conditional();result=assurance.evaluate_requirement(f.s,sid,req)
        self.assertEqual(result['result'],'QUALIFIED',result);self.assertFalse(result['open_conditions']);self.assertTrue(result['declared_context'])
        original=f.add(statement('The property holds without the real-number restriction.'));other=deepcopy(req);other['assumption_policy']['statement_ref']=original
        result=assurance.evaluate_requirement(f.s,sid,other,C.digest(req));self.assertEqual(result['result'],'UNQUALIFIED');self.assertTrue(result['accepted_checked_scope']);self.assertTrue(result['qualification_blockers'])
    def test_legacy_review_remains_visible_without_typed_requalification(self):
        f,target,a,sid,req,q=self.conditional();legacy=deepcopy(req);legacy.pop('assumption_policy')
        f.s['qualifications'][q]['policy_digest']='legacy'
        result=assurance.evaluate_requirement(f.s,sid,legacy,'legacy');self.assertEqual(result['result'],'UNQUALIFIED');self.assertTrue(result['checked_scope']);self.assertFalse(result['missing_slots']);self.assertEqual(result['review_coverage_result'],'QUALIFIED')
        typed=assurance.evaluate_requirement(f.s,sid,req);self.assertNotEqual(typed['result'],'QUALIFIED');self.assertTrue(typed['review_evidence']);self.assertIn('Policy requires requalification',typed['reasons'])
    def test_condition_allowlist_without_exact_hypothesis_binding_cannot_qualify(self):
        f,target,a,sid,req,q=self.conditional();unresolved=f.add(statement('An additional unresolved condition is required.'))
        f.s['supports'][sid]['open_assumption_refs'].append(unresolved)
        req['assumption_policy']['accepted_condition_refs']=[unresolved]
        f.s['qualifications'][q]['policy_digest']=C.digest(req)
        result=assurance.evaluate_requirement(f.s,sid,req)
        self.assertEqual(result['result'],'UNQUALIFIED',result)
        self.assertTrue(result['accepted_checked_scope']);self.assertIn(unresolved,result['open_conditions'])
    def test_no_review_no_independence_and_defect_still_block(self):
        for fault in ('missing','shared','defect'):
            f,target,a,sid,req,q=self.conditional()
            if fault=='missing':f.s['supports'][sid]['qualification_refs']=[]
            elif fault=='shared':f.s['review_executions'][f.s['qualifications'][q]['review_execution_event']]['independent']=False
            else:
                q2=kernel_fixtures.AssuranceContextTests().review(f,sid,req['required_scope'],verdict='DEFECT_FOUND');f.s['qualifications'][q2]['policy_digest']=C.digest(req)
            result=assurance.evaluate_requirement(f.s,sid,req);self.assertNotEqual(result['result'],'QUALIFIED',fault)


class SourceBinding421(unittest.TestCase):
    def test_source_evidence_closure_keeps_occurrence_and_rejects_wrong_blob(self):
        f=Fixture();raw=b'This exact original source contains the claim.';sid='SO-original';h=sha(raw);f.blobs[h]=raw
        f.s['sources'][sid]={'source_id':sid,'blob_hash':h,'bytes':len(raw),'access_class':'SCIENTIFIC_SOURCE','provenance_refs':[],'coverage':'FULL_DOCUMENT'}
        data={'source_occurrence_refs':[sid],'locators':[K.locator(raw)],'evidence_type':'ORIGINAL_TEXT','coverage':'FULL_DOCUMENT','reproducibility_refs':[]}
        r=f.add(K.make_record('SourceEvidence','The original source was read.',data,[],sources=f.s['sources'],blob_get=f.get))
        self.assertIn(sid,relations.premise_closure([r],f.s));pkt=__import__('research_studio.context',fromlist=['build_packet']).build_packet(f.s,[r],f.get)
        self.assertTrue(any(x.get('ref')==sid for x in pkt['input_manifest']))
        other=b'Another unrelated source.';f.blobs[sha(other)]=other;data['locators']=[K.locator(other)]
        with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):K.make_record('SourceEvidence','The original source was read.',data,[],sources=f.s['sources'],blob_get=f.get)
    def test_excerpt_cannot_cite_undelivered_body_or_claim_full_reading(self):
        raw=b'First exact paragraph. Second exact paragraph.';sid='SO-original';h=sha(raw);part=K.locator(raw,0,22)
        task={'input_manifest':[{'kind':'source','ref':sid,'sha256':h,'body_coverage':{'source_ref':sid,'source_blob_hash':h,'coverage':'DECLARED_RANGE','segments':[{'locator':part}]}}]}
        changes.validate_source_delivery(task,sid,[part])
        for loc,coverage in [(K.locator(raw),None),(part,'FULL_DOCUMENT')]:
            with self.assertRaisesRegex(PMRSError,'INCOMPLETE_CONTEXT'):changes.validate_source_delivery(task,sid,[loc],coverage=coverage)


class NativeFormat421(unittest.TestCase):
    def test_native_proof_finite_repair_and_historical_identity(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from research_studio import demo,execution,reports,scheduler
        from research_studio.engine import Engine
        from research_studio.runner import FakeExecutor
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine();store=engine.create(Path(tmp)/'project',demo.ARITHMETIC,synthetic=True)
            target=next(iter(store.read_snapshot()['records']));iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
            engine.authorize(store,iid,{'intent':'Exercise one finite format allowance with exact captured science.',
                'authorized_scope':{'target_refs':[target],'reports':True,'allow_derived_work':True},'obligations':[]},
                {'max_calls':4,'max_workers':1,'execution_policy':demo.policy()})
            rid=reports.create(store,iid);prepared=reports.prepare(store,iid,report_id=rid);oid=reports._assign_role(store,iid,prepared)
            policy={**demo.policy(),'only_obligation_ids':[oid]};plan=scheduler.plan(store.read_snapshot(),[iid],policy)
            made=scheduler.commit_dispatch(store,plan,policy=policy);tid=made['prepared'][0]['task_id']
            def bad_wire(t,s):
                v=json.loads(demo.response(t,s,blob_get=store.read_blob));v['schema']='bad-wire';return canonical(v)
            result=FakeExecutor(bad_wire).execute(store,tid);self.assertEqual(result['state'],'REJECTED_CONTRACT',result)
            before=store.read_snapshot();request=before['requests'][before['tasks'][tid]['request_id']];capture=request['capture_ref'];original=store.read_blob(capture)
            receipt=execution.prepare_repair(store,request['request_id'],'FORMAT');state=store.read_snapshot()
            event=next(e for e in state['execution_events'].values() if e['event_type']=='PREPARE_REPAIR')
            self.assertEqual(event['payload']['format_proof']['schema'],'pmrs.format-repair-proof/1')
            self.assertEqual(state['requests'][request['request_id']]['acceptance_state'],'REJECTED_CONTRACT')
            self.assertEqual(state['requests'][receipt['request_id']]['sample_slot'],request['sample_slot'])
            self.assertEqual(execution.apply_event(before,event,store.read_blob,historical=True)['requests'][receipt['request_id']]['repair_kind'],'FORMAT')
            implementation=changes.validator_identity();implementation['modules']['changes.py']='f'*64
            with patch('research_studio.changes.validator_identity',return_value=implementation):
                self.assertTrue(execution.verify_format_proof(before,request['request_id'],event['payload']['format_proof'],store.read_blob,historical=True))
                with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):execution.verify_format_proof(before,request['request_id'],event['payload']['format_proof'],store.read_blob)
            no_proof=deepcopy(event);no_proof['payload'].pop('format_proof')
            with self.assertRaisesRegex(PMRSError,'REPAIR_NOT_ALLOWED'):execution.apply_event(before,no_proof,store.read_blob)
            fixed=FakeExecutor(lambda t,s:canonical(changes._wire_repair(json.loads(original),t))).execute(store,receipt['task_id'])
            self.assertEqual(fixed['state'],'ACCEPTED',fixed);self.assertEqual(store.read_blob(capture),original)
            with self.assertRaisesRegex(PMRSError,'REPAIR_LIMIT|REPAIR_NOT_ALLOWED'):execution.prepare_repair(store,request['request_id'],'FORMAT')
            store.audit()


if __name__=='__main__':unittest.main()
