"""Reusable reader fixture constructed only by typed native transactions."""
from research_studio import changes,contracts as C,demo,execution,knowledge as K,obligations as O,scheduler
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor
from research_studio.util import canonical,sha


def build(root, *, store=None, target_ref=None, argument_bodies=None):
    e=Engine()
    if store is None: store=e.create(root,demo.ARITHMETIC,synthetic=True)
    target=target_ref or next(iter(store.read_snapshot()['records']))
    original='可去性与光滑正则性。原文仅提供方法启发，不提供本项目结论的证明。'.encode()
    source=store.commit(changes.prepare_material_input(store.read_snapshot(),original,title='中文方法原件.txt',media_type='text/plain'))['source_ref']
    iid=e.new_workflow(store,'TRH',target_ref=target)['instance_id'];mid='M-reader'
    e.authorize(store,iid,{'mission_id':mid,'intent':'Read exact records, alternative paths and partial review boundaries.',
      'authorized_scope':{'target_refs':[target],'allow_derived_work':True,'reports':True},'obligations':[]},
      {'max_calls':12,'max_workers':2,'execution_policy':demo.policy()})
    counter=0
    def submit(label,role,refs,factory,requirement=None,selected=None):
        nonlocal counter
        counter+=1;oid='O-reader-'+label;bid='B-reader-'+label;gid='G-reader-'+label
        c={'binding_id':bid,'instance_id':iid,'mission_id':mid,'stage_id':'P4','role':role,'retry_grant_id':gid,
           'method_ref':'METHOD-'+label,'scope':{'target_ref':target},'entry_basis':{},'input_refs':refs,'source_refs':[source],
           'threshold':'SUPPORT_QUALIFIED' if requirement else 'WORK_DISPOSITION_RECORDED'}
        if requirement:c.update(required_assurance=requirement,selected_support=selected,policy_digest=C.digest(requirement),entry_basis={'dependency_threshold':'SUPPORT_QUALIFIED','consumer_requirement':requirement})
        duty=O.make(oid,'VERIFY' if requirement else 'ESTABLISH',[target],store.blob(('Perform only the exact '+label+' responsibility.').encode()),consumer_bindings=[c])
        store.commit_execution(execution.event('ASSIGN_OBLIGATION',{'instance_id':iid,'mission_id':mid,'obligation':duty,
          'retry_grant':{'grant_id':gid,'obligation_id':oid,'method_ref':'METHOD-'+label,'max_research_attempts':1},'authorization_basis_ref':mid}))
        view=store.read_snapshot()
        for key,o in view['obligations'].items():
            if key!=oid:o['definition']['consumer_bindings']=[]
        plan=scheduler.plan(view,[iid],demo.policy());made=scheduler.commit_dispatch(store,plan,policy=demo.policy());task_id=made['prepared'][0]['task_id']
        def respond(t,s):
            operations,evidence=factory(t,s)
            effects=[{'binding_id':b['binding_id'],'expected_definition_revision':b['expected_definition_revision'],'work_disposition':'ADDRESSED','resolution_proposal':'CANDIDATE_RESPONSE',
                'evidence_refs':evidence,'remaining_conditions':['The remaining exact scope stays open.'],'blocker_proposals':[]} for b in t['obligation_bindings']]
            payload={'schema':C.CHANGE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'base_knowledge_commit':t['knowledge_commit'],
              'read_set_digest':C.digest(t['read_set']),'query_guard_digest':C.digest(t['query_guards']),'write_guard_digest':C.digest(t['write_guards']),
              'operations':operations,'obligation_effects':effects,'new_obligation_proposals':[],'work_outcome':'RESULT',
              'attempt_account':'The exact assigned synthetic scope and original material were preserved. Unchecked portions remain open.',
              'claimed_change':'Only the declared scoped candidate or review was recorded.','semantic_novelty':'NOT_AUTOMATICALLY_CERTIFIED'}
            return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],'payload_kind':'KNOWLEDGE_CHANGE','payload':payload})
        FakeExecutor(respond).execute(store,task_id)
        return task_id
    bodies=argument_bodies or ['For every integer n, the first candidate uses the additive identity. The remaining scope has not been independently checked.',
            'The alternative candidate keeps the same fixed arithmetic assertion and uses its own explicit argument.']
    def author(t,s):
        ops=[]
        for i,body in enumerate(bodies,1):
            data={'conclusion_ref':target,'premise_bindings':[],'steps':[{'step_id':'step','locator':K.locator(body),'premise_refs':[]}],
              'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'PROOF','mode_payload':{}}
            ops.append({'op':'NEW','local_key':'a'+str(i),'kind':'Argument','context_refs':[],'body':body,'data':data})
        ops.append({'op':'LINK','type':'USED_SOURCE','source_ref':'local:a1','target_ref':source,'scope_context_refs':[],
          'evidence_bindings':[{'source_ref':source,'locators':[K.locator(original)],'usage_mode':'METHOD_INSPIRATION','trust_boundary':'Technique inspiration only; this source is not a premise or proof of the target.'}],'assertion_state':'PROPOSED'})
        return ops,['local:a1','local:a2']
    before=store.read_snapshot()['knowledge_commit'];submit('two-alternatives','RESEARCH',[],author)
    s=store.read_snapshot();args=[next(r for r,v in s['records'].items() if v['body_sha256']==sha(b.encode())) for b in bodies]
    supports=[next(k for k,v in s['supports'].items() if v['argument_ref']==r) for r in args]
    full=[{'target_ref':args[0],'locators':[K.locator(bodies[0])],'aspects':['proof']}]
    from research_studio.assurance import requirement
    req=requirement('PROOF_SUPPORT',full);partial=K.locator(bodies[0],0,bodies[0].index('.')+1)
    def review(verdict):
        def factory(t,s):
            data={'review_kind':'PROOF','target_refs':[args[0]],'checked':[{'ref':args[0],'locators':[partial],'aspect':'proof'}],
              'unchecked':[{'ref':args[0],'aspect':'proof','reason':'The remainder of the supplied argument has not been checked.'}],
              'verdict':verdict,'findings':[],'scope_context_refs':[]}
            return [{'op':'NEW','local_key':'review','kind':'Assessment','body':'The exact first interval was inspected independently; the remaining interval stays unchecked.','context_refs':[],'data':data}],['local:review']
        return factory
    submit('partial-review','PROOF',[args[0]],review('SUPPORTED_WITHIN_SCOPE'),req,supports[0]);partial_commit=store.read_snapshot()['knowledge_commit']
    defect_task=submit('scoped-defect','PROOF',[args[0]],review('DEFECT_FOUND'),req,supports[0]);s=store.read_snapshot()
    assessment=next(p['record_ref'] for p in s['production_events'].values() if p.get('task_id')==defect_task)
    def withdraw(t,s):
        return [{'op':'WITHDRAW_SUPPORT','support_id':supports[0],'expected_qualification_head':C.digest(s['supports'][supports[0]]['qualification_refs']),
          'scope':[{'target_ref':args[0],'locators':[partial],'aspects':['proof']}],'reason_code':'INDEPENDENT_SCOPED_DEFECT','evidence_refs':[assessment]}],[]
    submit('withdraw-one-path','RESEARCH',[args[0],assessment],withdraw)
    store.commit(changes.prepare_result_family(store.read_snapshot(),{'family_id':'F-reader','members':[
       {'record_ref':target,'display_role':'MAIN_RESULT'},{'record_ref':args[0],'display_role':'SUPPORTING_ARGUMENT'},{'record_ref':args[1],'display_role':'ALTERNATIVE_PROOF'}]}))
    store.audit()
    return store,{'instance_id':iid,'target_ref':target,'source_ref':source,'argument_refs':args,'support_refs':supports,
                  'before_commit':before,'partial_commit':partial_commit,'after_commit':store.read_snapshot()['knowledge_commit'],
                  'family_id':'F-reader','original_source_sha256':sha(original)}
