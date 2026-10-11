"""Clearly synthetic example responses sent through the ordinary kernel.

The fixture never calls a model. Its candidates and reviews remain attached to
SYNTHETIC_TEST_ONLY projects and do not certify a user's mathematical problem.
"""
from . import contracts as C
from .knowledge import locator
from .util import canonical,sha
from .runner import FakeExecutor

ARITHMETIC=b'For every integer n, n + 0 = n.'
CANDIDATE='For every real symmetric 2 by 2 matrix A, if A is positive definite, then every eigenvalue of A is positive.'


def discovery_scope(phenomenon=None):
    """Explicit fixture scope, used only when a caller chooses the synthetic demo."""
    return {'phenomenon':phenomenon or 'Compare candidate formulations about real symmetric 2 by 2 matrices.',
            'immutable_background':'Synthetic fixture only: retain real symmetric 2 by 2 matrices, real vectors, and the usual definitions of positivity and eigenvalue.',
            'allowed_axes':'Synthetic fixture only: explore additional matrix hypotheses and candidate conclusions; keep unproved candidates and unknown comparisons explicitly open.'}


def policy():
    return {'capacity':{'model_id':'gpt-6-astra','capacity_source':'SYNTHETIC_TEST_ONLY','capacity_revision':'demo-1',
                'context_window_tokens':2_000_000,'model_max_output_tokens':8192,'tokenizer_revision':'synthetic-utf8-bound',
                'tokenizer_byte_bound_verified':True,'token_count_bound':'UTF8_BYTES'},
            'model_capabilities':{'source':'SYNTHETIC_TEST_ONLY','revision':'demo-1','executor':'fake',
                'isolated_ultra_verified':True,'internal_delegation':False,
                'models':{'gpt-6-astra':{'reasoning_efforts':['high','xhigh','max','ultra'],'service_tiers':['default']}}},
            'executor_contract':{'executor':'fake','sandbox':'SYNTHETIC_TEST_ONLY','environment_revision':'demo-1'},
            'reserved_output_tokens':4096}


def response(task,snapshot,*,blob_get=None):
    if task.get('actor_kind')=='MAIN':return main_response(task,snapshot,blob_get=blob_get)
    ops=[];evidence=[];role=task['role'];stage=task['stage_id']
    prerequisite=bool(snapshot.get('synthetic_test_only') and stage in {'P1','P2','P3'} and
        task.get('target_refs') and all(snapshot['records'][ref]['body_sha256']==sha(ARITHMETIC) for ref in task['target_refs']))
    if role.startswith('REPORT_'):
        from .reports import demo_payload
        payload_kind='REPORT_OUTPUT' if role=='REPORT_AUTHOR' else 'REPORT_REVIEW'
        return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],
                          'payload_kind':payload_kind,'payload':demo_payload(task,snapshot,blob_get=blob_get)})
    if stage.startswith('S'):
        from .survey import demo_response
        return demo_response(task,snapshot)
    if prerequisite:
        body={'P1':'Synthetic teaching conventions: n is an arbitrary integer. Addition and zero are the ordinary integer operation and its additive identity. The quantifier ranges over all integers; no hypothesis is weakened.',
              'P2':'Synthetic teaching backward implication: to establish the original target it suffices to apply the additive identity axiom to an arbitrary integer n. This is a sufficient implication in the given integer structure, not an inference from finitely many examples.',
              'P3':'Synthetic teaching route: fix an arbitrary integer n and apply the additive identity axiom directly. A sample computation alone would not cover the universal quantifier. The executable next question is whether that axiom gives n + 0 = n under exactly the original conventions.'}[stage]
        loc=locator(body)
        if stage=='P1':
            ops=[{'op':'NEW','local_key':'prerequisite','kind':'Context','context_refs':[],'body':body,
                  'data':{'definitions':[{'key':'integer_additive_identity','locator':loc}],'objects':[],
                          'assumptions':[],'quantifiers':[],'conventions':[],'parent_context_refs':[]}}]
        else:
            ops=[{'op':'NEW','local_key':'prerequisite','kind':'Statement','context_refs':[],'body':body,
                  'data':{'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[loc],
                          'conclusion_locators':[loc],'quantifier_locators':[loc],'form':'CONJECTURE',
                          'representation':'AUTHORED','source_binding':None}}]
        evidence=['local:prerequisite']
    elif task.get('independent'):
        req=task.get('required_assurance')
        slots=[x for x in req['review_slots'] if role in x['allowed_roles']] if req else []
        if slots:
            scopes=[r for slot in slots for r in slot['required_scope']]
            body='Synthetic independent-review fixture. The exact assigned scope is retained, but this demonstration does not establish mathematical validity. Further actual research review is required.'
            data={'review_kind':slots[0]['review_kind'],'target_refs':sorted({r['target_ref'] for r in scopes}),
                  'checked':[],'unchecked':[{'ref':r['target_ref'],'aspect':aspect,'reason':'Synthetic demonstration; actual independent mathematical review remains open.'} for r in scopes for aspect in r['aspects']],
                  'verdict':'INCONCLUSIVE','findings':[],'scope_context_refs':[]}
            # checked/unchecked schema is deliberately read from the same runtime
            # contract, and no success verdict is used to make the UI look solved.
            ops=[{'op':'NEW','local_key':'review','kind':'Assessment','context_refs':[],'body':body,'data':data}];evidence=['local:review']
    elif stage.startswith('D') and role in {'LEARN','RESEARCH','DIRECT','PLAN'}:
        loc=locator(CANDIDATE);example='Take A = diag(1, 2). For every nonzero real vector x, x^T A x = x_1^2 + 2 x_2^2 > 0, and the two eigenvalues are 1 and 2. This is one finite calibration example only; the universal candidate remains unproved in this synthetic demonstration.'
        ops=[{'op':'NEW','local_key':'candidate','kind':'Statement','context_refs':[],'body':CANDIDATE,
            'data':{'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[loc],'conclusion_locators':[loc],
                    'quantifier_locators':[loc],'form':'CONJECTURE','representation':'AUTHORED','source_binding':None}},
            {'op':'NEW','local_key':'example','kind':'Example','context_refs':[],'body':example,
             'data':{'target_refs':['local:candidate'],'construction_locator':locator(example),
                     'hypothesis_checks':[{'hypothesis_locator':loc,'result':'SATISFIED','evidence_refs':[],
                                           'explanation_locator':locator(example)}],
                     'observations':[{'locator':locator(example),'evidence_refs':[]}],'scope':'MODEL_CASE','realization_argument_ref':None}}]
        evidence=['local:candidate','local:example']
    elif role=='RESEARCH' and task['target_refs'] and snapshot['records'][task['target_refs'][0]]['body_sha256']==sha(ARITHMETIC):
        body='Let n be an arbitrary integer. By the additive identity axiom for the integers, adding zero leaves n unchanged, so n + 0 = n. The argument applies to every integer n. This is a synthetic demonstration of candidate admission, not a real model review.'
        ops=[{'op':'NEW','local_key':'argument','kind':'Argument','context_refs':[],'body':body,
            'data':{'conclusion_ref':task['target_refs'][0],'premise_bindings':[],
                    'steps':[{'step_id':'identity','locator':locator(body),'premise_refs':[]}],
                    'discharged_assumptions':[],'open_conditions':[],'witness_bindings':[],'mode':'PROOF','mode_payload':{}}}]
        evidence=['local:argument']
    effects=[{'binding_id':b['binding_id'],'expected_definition_revision':b['expected_definition_revision'],
        'work_disposition':'ADDRESSED' if ops else 'NO_RESULT','resolution_proposal':'CANDIDATE_RESPONSE' if ops else 'UNRESOLVED',
        'evidence_refs':evidence,'remaining_conditions':[] if prerequisite else ['Synthetic demonstration only; no real mathematical certification.'],
        'blocker_proposals':[]} for b in task['obligation_bindings']]
    payload={'schema':C.CHANGE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'base_knowledge_commit':task['knowledge_commit'],
        'read_set_digest':C.digest(task['read_set']),'query_guard_digest':C.digest(task['query_guards']),'write_guard_digest':C.digest(task['write_guards']),
        'operations':ops,'obligation_effects':effects,'new_obligation_proposals':[],'work_outcome':'RESULT' if ops else 'NO_RESULT',
        'attempt_account':'A deterministic synthetic fixture inspected the frozen task and produced only the declared candidate or inconclusive review. No model or network was called.',
        'claimed_change':'Synthetic example artifacts are available; mathematical certification is not granted.',
        'semantic_novelty':'NOT_AUTOMATICALLY_CERTIFIED'}
    return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'payload_kind':'KNOWLEDGE_CHANGE','payload':payload})


def executor(*,blob_get=None):
    return FakeExecutor(response if blob_get is None else lambda task,snapshot:response(task,snapshot,blob_get=blob_get))


def main_response(task,snapshot,*,blob_get=None):
    """A synthetic state-machine example, never evidence of real research."""
    from copy import deepcopy
    from .util import loads
    worker=deepcopy(task);worker.pop('actor_kind',None)
    value=loads(response(worker,snapshot,blob_get=blob_get))
    payload=value['payload'];p=payload.get('knowledge_change',payload)
    stage=task['stage_id'];context=task['strategy_context']
    if stage=='D2':p['operations']=[op for op in p['operations'] if op['kind']!='Example']
    if not p['operations'] and stage not in {'S1','D5'}:
        body='Synthetic global account: the additive identity follows axiomatically. This fixture tests native accounting only; it provides no real model judgment. Every listed work binding has been inspected, and any inconclusive review remains inconclusive.'
        loc=locator(body)
        p['operations']=[{'op':'NEW','local_key':'main_account','kind':'Statement','context_refs':[],
            'body':body,'data':{'statement_locator':loc,'scope_context_refs':[],'hypothesis_locators':[loc],
                'conclusion_locators':[loc],'quantifier_locators':[loc],'form':'CONJECTURE','representation':'AUTHORED','source_binding':None}}]
    refs=['local:'+op['local_key'] for op in p['operations'] if 'local_key' in op]
    if stage=='D5':refs=[row['ref'] for row in task['input_manifest'] if row['kind']=='record'][:8]
    for effect in p['obligation_effects']:
        effect.update(work_disposition='ADDRESSED',resolution_proposal='CANDIDATE_RESPONSE',evidence_refs=refs,remaining_conditions=[])
    p['work_outcome']='RESULT' if refs else 'NO_RESULT'
    target=snapshot['instances'][task['instance_id']].get('target_ref')
    work=[]
    if stage=='P3':
        work=[{'key':'identity','stage_id':'P4','role':'RESEARCH','purpose':'DEFAULT','obligation_type':'ESTABLISH',
            'question':'Does the additive identity axiom establish the fixed universally quantified integer identity?',
            'success_criterion':'Give the argument for arbitrary integer n or retain the precise missing premise.',
            'target_refs':[target],'input_refs':[target]+refs,'source_refs':[],'depends_on':[],
            'route_key':'axiom','communication_group':None}]
    if stage=='D2' and not any(t['stage_id']=='D3' and t['instance_id']==task['instance_id'] for t in snapshot['tasks'].values()):
        work=[{'key':'candidate-discrimination','stage_id':'D3','role':'DIRECT','purpose':'DEFAULT','obligation_type':'DISCRIMINATE',
            'question':'Which examples distinguish the exact candidate formulation?',
            'success_criterion':'State distinguishing evidence and every unknown comparison.',
            'target_refs':refs,'input_refs':refs,'source_refs':[],'depends_on':[],'route_key':'','communication_group':None}]
    routes=[]
    if stage=='P3':
        routes=[{'route_key':'axiom','status':'ACTIVE','origin':'Synthetic exact target','mechanism':'Use the integer additive identity axiom for an arbitrary integer.',
            'target_relation':'Direct sufficient argument','sufficient_chain':'Additive identity implies n + 0 = n.',
            'unproved_arrows':[],'extra_assumptions':[],'decisive_probe':'Write the universal argument.',
            'failure_evidence_refs':[],'reactivation_condition':'New exact premise evidence','allocation_rationale':'One direct synthetic responsibility suffices.',
            'reason':'The target is an axiom instance, not an empirical pattern.','evidence_refs':refs}]
    p['strategy_proposal']={'schema':'pmrs.strategy-proposal/1','base_strategy_revision':context['revision'],
        'trigger_refs':context['pending_trigger_refs'],'route_updates':routes,'work_items':work,'input_plan_proposals':[],
        'progress_account':{'summary':'Synthetic native strategy/accounting example; no external model evidence.',
            'record_refs':refs,'remaining_difficulties':['Actual research certification was not performed.'],
            'scope_limitations':['SYNTHETIC_TEST_ONLY'],'failed_or_unperformed':[],
            'covered_binding_ids':context['covered_binding_ids'],'frontier_complete':stage in {'P11','D5','S3'}},
        'direction_answers':[{'direction_id':did,'answer':'The synthetic fixture recorded this exact user direction; no real mathematical answer is certified.',
            'record_refs':refs,'work_keys':[w['key'] for w in work],'needs_human':False} for did in context['direction_ids']],
        'next_action':'CONTINUE' if work else 'DELIVER' if stage in {'P11','D5','S3'} else 'WAIT' if stage=='S1' else 'ACCOUNT',
        'human_decision_needed':[],'no_change_reason':'Synthetic exact frontier accounting.'}
    return canonical(value)


def scenario(kind):
    return ARITHMETIC.decode() if kind=='TRH' else 'Observe positive definite real symmetric 2 by 2 matrices. Discover a precise relationship between positive definiteness and eigenvalues, retaining positive, negative and unknown evidence.'
