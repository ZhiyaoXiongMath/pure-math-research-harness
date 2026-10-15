"""Independent-oracle trace, run in separate guarded baseline/facade/domain processes.

All bodies and execution facts below are synthetic. This script tests explicit
record/qualification contracts, not natural-language mathematical truth.
"""
from copy import deepcopy
import json
import sys


def trace(interface):
    if interface == 'domain':
        from pmrh.domain import contracts as C, knowledge as K, assurance as A, relations as R, protocols as P
        from pmrh.domain import primitives as U
        coverage = A
        independence = A
        lifecycle = P
    else:
        from research_studio import contracts as C, knowledge as K, assurance as A, relations as R, util as U
        from research_studio import context as coverage, communication as independence, workflow_instances as lifecycle
        from research_studio.workflows import registry as P
    output = {}

    def observe(key, function, *args, **kwargs):
        before = deepcopy((args, kwargs))
        results = []
        for _ in range(2):
            try:
                result = function(*args, **kwargs)
                result = sorted(result) if isinstance(result, set) else result
                results.append({'value': result})
            except U.PMRSError as exc:
                results.append({'error': exc.code, 'message': exc.message})
            assert before == (args, kwargs), key + ': input mutation'
        assert results[0] == results[1], key + ': nondeterministic'
        output[key] = results[0]
        return results[0]

    records, blobs, sources = {}, {}, {}
    state = {'records': records, 'sources': sources, 'supports': {}, 'qualifications': {},
             'review_executions': {}, 'withdrawals': {}, 'synthetic_test_only': True}

    def add(kind, body, data, contexts=()):
        ref, record, raw = K.make_record(kind, body, data, contexts, records=records,
                                       sources=sources, blob_get=blobs.__getitem__)
        records[ref] = record
        blobs[U.sha(raw)] = raw
        return ref

    def statement(body):
        loc = K.locator(body)
        return add('Statement', body, {'statement_locator': loc, 'scope_context_refs': [],
            'hypothesis_locators': [], 'conclusion_locators': [loc], 'quantifier_locators': [loc],
            'form': 'PROPOSITION', 'representation': 'AUTHORED', 'source_binding': None})

    ctxbody = 'Let x be an integer.'
    ctx = add('Context', ctxbody, {**{k: [] for k in ('definitions', 'objects', 'quantifiers', 'conventions')},
        'assumptions': [{'key': 'integer', 'locator': K.locator(ctxbody)}], 'parent_context_refs': []})
    target = statement('For every integer x, x + 0 = x.')
    weaker = statement('For the integer zero, 0 + 0 = 0.')

    def path(statement_ref, body, mode='PROOF', payload=None, premises=()):
        argument = add('Argument', body, {'conclusion_ref': statement_ref, 'premise_bindings': list(premises),
            'steps': [], 'discharged_assumptions': [], 'open_conditions': [], 'witness_bindings': [],
            'mode': mode, 'mode_payload': payload or {}})
        scope = [{'target_ref': argument, 'locators': [K.locator(body)], 'aspects': ['proof']}]
        req = A.requirement('PROOF_SUPPORT', scope)
        sid = 'SUP-' + argument
        state['supports'][sid] = {'support_id': sid, 'statement_ref': statement_ref, 'argument_ref': argument,
            'premise_support_refs': [p['support_ref'] for p in premises if p['support_ref']],
            'open_assumption_refs': [], 'qualification_refs': [], 'author_task_id': 'AUTHOR',
            'author_execution_event': 'AUTHOR-E', 'consumer_requirement': req, 'policy_digest': 'policy'}
        return argument, sid, req

    def review(sid, scope, role='PROOF', kind='PROOF', verdict='SUPPORTED_WITHIN_SCOPE', event=None):
        event = event or 'E-' + str(len(state['qualifications']))
        data = {'review_kind': kind, 'target_refs': sorted({x['target_ref'] for x in scope}),
            'checked': [{'ref': x['target_ref'], 'locators': x['locators'], 'aspect': aspect,
                         **{k: x[k] for k in A.SCOPE_META if k in x}} for x in scope for aspect in x['aspects']],
            'unchecked': [], 'verdict': verdict, 'findings': [], 'scope_context_refs': []}
        ref = add('Assessment', 'Synthetic review of the explicitly assigned scope.', data)
        qid = 'Q-' + str(len(state['qualifications']))
        state['qualifications'][qid] = {'assessment_ref': ref, 'review_execution_event': event,
            'input_manifest_hash': 'synthetic-input', 'target_revision_hashes': data['target_refs'],
            'actual_checked_scope': deepcopy(scope), 'evidence_origin': 'MODEL_CAPTURE',
            'policy_digest': 'policy', 'integrity_valid': True}
        state['review_executions'][event] = {'event_id': event, 'task_id': event, 'role': role,
            'input_manifest_hash': 'synthetic-input', 'target_revision_hashes': data['target_refs'],
            'independent': True, 'excluded_verdicts': True, 'synthetic': True, 'integrity_valid': True}
        state['supports'][sid]['qualification_refs'].append(qid)
        return qid

    argument, sid, req = path(target, 'Addition of zero preserves the given integer.')
    observe('03.candidate', A.evaluate_requirement, state, sid, req, 'policy')
    qid = review(sid, req['required_scope'], role='FORMULATION_REVIEW', kind='FORMULATION')
    observe('03.formulation_not_proof', A.evaluate_requirement, state, sid, req, 'policy')
    qid = review(sid, req['required_scope'])
    observe('03.qualified', A.evaluate_requirement, state, sid, req, 'policy')
    dual = A.requirement('PROOF_SUPPORT', req['required_scope'], review_mode='TARGET_DUAL')
    observe('08.missing_dual_slot', A.evaluate_requirement, state, sid, dual, 'policy')
    review(sid, req['required_scope'], 'COUNTEREXAMPLE', 'COUNTEREXAMPLE')
    observe('08.dual', A.evaluate_requirement, state, sid, dual, 'policy')
    author = deepcopy(state)
    for event in author['review_executions'].values():
        event['task_id'] = 'AUTHOR'
    observe('08.self_review', A.evaluate_requirement, author, sid, dual, 'policy')
    real = deepcopy(state); real['synthetic_test_only'] = False
    observe('08.synthetic_rejected', A.evaluate_requirement, real, sid, dual, 'policy')
    contaminated = deepcopy(state)
    contaminated.update(tasks={}, input_deliveries={}, research_messages={})
    for eid, event in contaminated['review_executions'].items():
        contaminated['tasks'][eid] = {'request_id': eid, 'communication_contract': {'enabled': True}}
        contaminated['input_deliveries'][eid] = {'request_id': eid, 'message_ids': ['m']}
    contaminated['research_messages']['m'] = {'sender_request_id': 'prior-verdict', 'host_sanitized': False}
    observe('08.exposure', independence.independence_status, contaminated, eid)
    observe('08.exposure_blocks', A.evaluate_requirement, contaminated, sid, dual, 'policy')
    narrow = deepcopy(req['required_scope']); narrow[0]['locators'] = [K.locator(blobs[records[argument]['body_sha256']], 0, 5)]
    observe('08.partial_scope', A.coverage, req['required_scope'], narrow)

    source = b'Exact original source passage.'
    blobs[U.sha(source)] = source
    sources['SO'] = {'blob_hash': U.sha(source), 'bytes': len(source), 'access_class': 'SCIENTIFIC_SOURCE'}
    se = add('SourceEvidence', 'The exact source is retained.', {'source_occurrence_refs': ['SO'],
        'locators': [K.locator(source)], 'evidence_type': 'ORIGINAL_TEXT', 'coverage': 'FULL_DOCUMENT', 'reproducibility_refs': []})
    example = add('Example', 'Take the integer zero.', {'target_refs': [target],
        'construction_locator': K.locator('Take the integer zero.'), 'hypothesis_checks': [], 'observations': [],
        'scope': 'MODEL_CASE', 'realization_argument_ref': None})
    output['01.records'] = {ref: {'canonical_hex': U.canonical(record).hex(),
        'identity': K.identify(record, blobs[record['body_sha256']])} for ref, record in records.items()}
    assert {r['kind'] for r in records.values()} == set(C.KINDS)
    observe('01.source_closure', R.premise_closure, [se], state)
    observe('01.unicode', K.locator, '原文 x', 0, 2, 'UNICODE_CODEPOINT')
    loc = K.locator('原文 x')
    for label, change in [('hash', {'blob_hash': '0'*64}), ('quote', {'quoted_sha256': '0'*64}),
                          ('utf8', {'end': 1}), ('range', {'end': 100})]:
        observe('01.bad_' + label, K.validate_locator, {**loc, **change}, lambda h: '原文 x'.encode())
    observe('01.duplicate', C.bounded_json, b'{"x":1,"x":2}')
    observe('01.unknown', C.fields, {'unexpected': True}, set())
    use = {'source_ref': 'SO', 'locators': [K.locator(source)], 'usage_mode': 'FULL_ARGUMENT', 'trust_boundary': 'Exact source only.'}
    data = deepcopy(records[target]['data']); data.update(statement_locator=K.locator(source), conclusion_locators=[],
        quantifier_locators=[], representation='SOURCE_BOUND', source_binding=use)
    bound = add('Statement', source, data)
    observe('01.source_bound', K.identify, records[bound], source)
    observe('01.source_bound_bad', K.make_record, 'Statement', b'Altered source', data,
            sources=sources, blob_get=blobs.__getitem__)

    state['instances'] = {'I': {'kind': 'TRH', 'target_ref': target}}
    observe('02.weaker_not_completion', lifecycle.completion_evidence, state, 'I', [weaker])

    complete_scope = A.normalize_scope([
        {'target_ref': target, 'locators': [], 'aspects': ['original_target']},
        {'target_ref': argument, 'locators': [], 'aspects': ['full_argument']}], state, blobs.__getitem__)
    complete_req = A.requirement('PROOF_SUPPORT', complete_scope, review_mode='TARGET_DUAL',
        assumption_policy=A.declared_assumption_policy(state, target, argument))
    for role in ('PROOF', 'COUNTEREXAMPLE'):
        q = review(sid, complete_scope, role, role)
        state['qualifications'][q]['policy_digest'] = C.digest(complete_req)
    completed = observe('02.exact_completion', lifecycle.completion_evidence, state, 'I', [argument])
    assert len(completed['value']) == 1
    global_state = deepcopy(state)
    global_state['inferences'] = {'global': {'argument_ref': argument, 'kind': 'GLOBAL_ASSEMBLY'}}
    observe('02.global_integration_missing', lifecycle.completion_evidence, global_state, 'I', [argument])
    q = review(sid, complete_scope, 'INDEPENDENT', 'INTEGRATION')
    global_state['records'] = deepcopy(records)
    global_state['qualifications'] = deepcopy(state['qualifications'])
    global_state['review_executions'] = deepcopy(state['review_executions'])
    global_state['supports'] = deepcopy(state['supports'])
    integrated = observe('02.global_integrated', lifecycle.completion_evidence, global_state, 'I', [argument])
    assert len(integrated['value']) == 1

    discovery = {'kind': 'FDH', 'discovery_brief_ref': 'SO',
                 'discovery_scope': dict.fromkeys(lifecycle.DISCOVERY_FIELDS, 'SO')}
    observe('02.d0', lifecycle.validate_discovery_scope, state, discovery)
    for field in lifecycle.DISCOVERY_FIELDS:
        bad = deepcopy(discovery); bad['discovery_scope'].pop(field)
        observe('02.missing_' + field, lifecycle.validate_discovery_scope, state, bad)
    bad = deepcopy(discovery); bad['discovery_brief_ref'] = 'different'
    observe('02.misbound', lifecycle.validate_discovery_scope, state, bad)

    conditional = deepcopy(state); conditional['supports'][sid]['open_assumption_refs'] = [ctx]
    observe('04.unconditional_blocked', A.evaluate_requirement, conditional, sid, req, 'policy')
    assumption = deepcopy(records[target]['data']); assumption['hypothesis_locators'] = [K.locator(ctxbody)]
    typed_target = add('Statement', 'Under the integer hypothesis, adding zero preserves x.', assumption, [ctx])
    p = {'premise_ref': ctx, 'kind': 'CONTEXT_ASSUMPTION', 'context_ref': ctx, 'scope_locator': None,
         'binding_mode': 'PINNED', 'support_ref': None, 'assumption_locator': K.locator(ctxbody)}
    typed_body = 'Use the declared integer assumption with the addition identity.'
    typed_data = {**deepcopy(records[argument]['data']), 'conclusion_ref': typed_target, 'premise_bindings': [p]}
    typed_arg = add('Argument', typed_body, typed_data, [ctx])
    typed_sid = 'typed'; state['supports'][typed_sid] = {**deepcopy(state['supports'][sid]),
        'support_id': typed_sid, 'statement_ref': typed_target, 'argument_ref': typed_arg, 'qualification_refs': [], 'open_assumption_refs': [ctx]}
    typed_scope = [{'target_ref': x, 'locators': [K.locator(blobs[records[x]['body_sha256']])], 'aspects': ['proof']} for x in (typed_target, typed_arg)]
    typed_req = A.requirement('PROOF_SUPPORT', typed_scope,
        assumption_policy=A.declared_assumption_policy(state, typed_target, typed_arg))
    tq = review(typed_sid, typed_scope); state['qualifications'][tq]['policy_digest'] = C.digest(typed_req)
    observe('04.typed_qualified', A.evaluate_requirement, state, typed_sid, typed_req)
    bad_req = deepcopy(typed_req); bad_req['assumption_policy']['statement_ref'] = target
    observe('04.no_strengthening', A.evaluate_requirement, state, typed_sid, bad_req)

    witness_body = 'The explicitly bound witness satisfies the reviewed component for every parameter.'
    witness = {'target_ref': target, 'component_argument_refs': [argument], 'context_refs': [],
        'variable_mapping': {'x': 'x'}, 'common_data_refs': [example],
        'quantifier_locators': [K.locator(witness_body)], 'evidence_refs': [argument], 'open_condition_refs': []}
    wa, ws, wr = path(target, witness_body, 'COMPATIBILITY', {'witness_compatibility': witness})
    review(ws, wr['required_scope'])
    witnessed = observe('04.bound_witness', A.evaluate_requirement, state, ws, wr, 'policy')
    assert witnessed['value']['result'] == 'QUALIFIED'
    for field in ('variable_mapping', 'quantifier_locators'):
        unbound = deepcopy(state)
        unbound['records'][wa]['data']['mode_payload']['witness_compatibility'][field] = {} if field == 'variable_mapping' else []
        observe('04.missing_' + field, A.evaluate_requirement, unbound, ws, wr, 'policy')
    open_witness = deepcopy(state)
    open_witness['records'][wa]['data']['mode_payload']['witness_compatibility']['open_condition_refs'] = [weaker]
    observe('04.open_quantifier_condition', A.evaluate_requirement, open_witness, ws, wr, 'policy')

    no_duties = lambda body: {k: {'status': 'NOT_REQUIRED', 'reason_locator': K.locator(body), 'evidence_refs': []}
                             for k in ('lifting_check', 'compatibility_check')}
    body = 'Both the explicit child and its interface are required.'
    inference = {'premise_refs': [target], 'conclusion_ref': weaker, 'operator': 'AND',
        'alternative_argument_refs': [], 'additional_assumption_refs': [], **no_duties(body)}
    binding = {'premise_ref': target, 'kind': 'SUPPORTED_STATEMENT', 'context_ref': None, 'scope_locator': None,
               'binding_mode': 'PINNED', 'support_ref': sid, 'assumption_locator': None}
    ra, rs, rr = path(weaker, body, 'REDUCTION', {'inference_spec': inference}, [binding]); review(rs, rr['required_scope'])
    observe('05.and', A.evaluate_requirement, state, rs, rr, 'policy')
    observe('01.inference', K.derive_inference, ra, records[ra])
    missing = deepcopy(state); missing['supports'][sid]['qualification_refs'] = []
    observe('05.and_missing_child', A.evaluate_requirement, missing, rs, rr, 'policy')
    open_lift = deepcopy(state)
    open_lift['records'][ra]['data']['mode_payload']['inference_spec']['lifting_check'] = {'status': 'REQUIRED', 'obligation_ids': ['missing'], 'evidence_refs': []}
    observe('05.lifting_open', A.evaluate_requirement, open_lift, rs, rr, 'policy')
    body = 'One complete alternative is sufficient.'
    oa, osid, oreq = path(weaker, body, 'REDUCTION', {'inference_spec': {
        'premise_refs': [], 'conclusion_ref': weaker, 'operator': 'OR', 'alternative_argument_refs': [ra],
        'additional_assumption_refs': [], **no_duties(body)}})
    review(osid, oreq['required_scope'])
    observe('05.or', A.evaluate_requirement, state, osid, oreq, 'policy')
    observe('06.acyclic', R.validate_support_graph, state)
    cyclic = deepcopy(state); cyclic['supports'][sid]['premise_support_refs'] = [rs]
    observe('06.cyclic_graph', R.validate_support_graph, cyclic)
    observe('06.cyclic_qualification', A.evaluate_requirement, cyclic, rs, rr, 'policy')
    other_arg, other_sid, other_req = path(target, 'An independent unchanged support path.'); review(other_sid, other_req['required_scope'])
    withdrawn = deepcopy(state); withdrawn['withdrawals']['W'] = {'support_id': sid, 'scope': req['required_scope'], 'active': True}
    observe('07.closure', R.affected_supports, withdrawn, [sid])
    observe('07.downstream', A.evaluate_requirement, withdrawn, rs, rr, 'policy')
    observe('07.independent_path', A.evaluate_requirement, withdrawn, other_sid, other_req, 'policy')
    observe('07.withdrawal_not_negation', A.evaluate, target, {'required_assurance': req, 'selected_support_refs': [sid]}, withdrawn)
    outside = deepcopy(withdrawn); outside['withdrawals']['W']['scope'][0]['aspects'] = ['unrelated']
    observe('07.outside_scope', A.evaluate_requirement, outside, sid, req, 'policy')
    failure = deepcopy(state); failure['supports'] = {rs: deepcopy(state['supports'][rs])}
    observe('09.failed_route_target_open', A.evaluate, target, {'required_assurance': req}, failure)

    output['11.registry'] = P.definition()
    observe('11.p7_valid', P.validate_assignment, 'P7', 'ESTABLISH', 'LEARN', {'analysis_route': 'SOURCE_APPLICATION'})
    observe('11.p7_invalid', P.validate_assignment, 'P7', 'ESTABLISH', 'DIRECT', {'analysis_route': 'SOURCE_APPLICATION'})
    observe('11.dynamic_return', P.exit_allowed, 'P8', 'P6')
    assert output['03.qualified']['value']['result'] == 'QUALIFIED'
    assert output['04.typed_qualified']['value']['result'] == 'QUALIFIED'
    assert output['05.and']['value']['result'] == output['05.or']['value']['result'] == 'QUALIFIED'
    assert output['06.cyclic_graph']['error'] == output['06.cyclic_qualification']['error'] == 'CYCLIC_MATH_SUPPORT'
    assert output['07.independent_path']['value']['result'] == 'QUALIFIED'
    assert output['07.withdrawal_not_negation']['value']['claim_outcome'] == 'OPEN'
    assert output['09.failed_route_target_open']['value']['claim_outcome'] == 'OPEN'
    if interface == 'domain':
        assert not any(n == 'research_studio' or n.startswith(('research_studio.', 'pmrh.ports', 'pmrh.application')) for n in sys.modules)
    return output


if __name__ == '__main__':
    print(json.dumps(trace(sys.argv[1]), ensure_ascii=False, sort_keys=True, separators=(',', ':')))
