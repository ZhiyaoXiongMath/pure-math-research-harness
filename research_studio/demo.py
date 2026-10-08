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
                'models':{'gpt-6-astra':{'reasoning_efforts':['high','xhigh','max'],'service_tiers':['default']}}},
            'executor_contract':{'executor':'fake','sandbox':'SYNTHETIC_TEST_ONLY','environment_revision':'demo-1'},
            'reserved_output_tokens':4096}


def response(task,snapshot):
    ops=[];evidence=[];role=task['role'];stage=task['stage_id']
    if role.startswith('REPORT_'):
        from .reports import demo_payload
        payload_kind='REPORT_OUTPUT' if role=='REPORT_AUTHOR' else 'REPORT_REVIEW'
        return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],
                          'payload_kind':payload_kind,'payload':demo_payload(task,snapshot)})
    if stage.startswith('S'):
        from .survey import demo_response
        return demo_response(task,snapshot)
    if task.get('independent'):
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
        'evidence_refs':evidence,'remaining_conditions':['Synthetic demonstration only; no real mathematical certification.'],
        'blocker_proposals':[]} for b in task['obligation_bindings']]
    payload={'schema':C.CHANGE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'base_knowledge_commit':task['knowledge_commit'],
        'read_set_digest':C.digest(task['read_set']),'query_guard_digest':C.digest(task['query_guards']),'write_guard_digest':C.digest(task['write_guards']),
        'operations':ops,'obligation_effects':effects,'new_obligation_proposals':[],'work_outcome':'RESULT' if ops else 'NO_RESULT',
        'attempt_account':'A deterministic synthetic fixture inspected the frozen task and produced only the declared candidate or inconclusive review. No model or network was called.',
        'claimed_change':'Synthetic example artifacts are available; mathematical certification is not granted.',
        'semantic_novelty':'NOT_AUTOMATICALLY_CERTIFIED'}
    return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':task['task_id'],'request_id':task['request_id'],'payload_kind':'KNOWLEDGE_CHANGE','payload':payload})


def executor():return FakeExecutor(response)


def scenario(kind):
    return ARITHMETIC.decode() if kind=='TRW' else 'Observe positive definite real symmetric 2 by 2 matrices. Discover a precise relationship between positive definiteness and eigenvalues, retaining positive, negative and unknown evidence.'
