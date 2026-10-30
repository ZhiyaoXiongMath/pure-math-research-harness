"""Derived exact-claim assurance through DEV04; never a stored badge."""
from copy import deepcopy
from pmrh.domain import assurance
from .model import check, claim_fingerprint, FastMathError
from .validation import native_projection, native_refs, required_guards, claim_identity


def _relation_matches(upper, slot):
    if upper['kind'] != 'Transition': return True
    p = upper['payload']; a = slot['argument_fields']
    if p['relation'] in {'UNKNOWN', 'HEURISTIC', 'ANALOGY'} or not a: return False
    mode = a['mode']; data = a['mode_payload']
    if p['relation'] == 'EQUIVALENCE':
        return mode == 'COMPARISON' and data['relation_type'] == 'EQUIVALENT_ON_SCOPE' and \
            data['from_statement_ref'] == p['start_ref'] and data['to_statement_ref'] == p['end_ref'] and \
            len(data['direction_argument_refs']) == 2 and data['scope_context_refs'] == p['shared_context_refs']
    if p['relation'] == 'APPLICABILITY':
        return mode == 'APPLICABILITY' and p['start_ref'] in data['donor_refs'] and data['recipient_ref'] == p['end_ref']
    if mode == 'COMPARISON':
        return data['relation_type'] == 'IMPLIES' and data['from_statement_ref'] == p['start_ref'] and data['to_statement_ref'] == p['end_ref']
    return a['conclusion_ref'] == p['end_ref'] and p['start_ref'] in {x['premise_ref'] for x in a['premise_bindings']} and \
        (p['relation'] == 'CONDITIONAL_IMPLICATION' or not a['open_conditions'])


def qualify_binding(binding, upper, snapshot):
    """A conditional native support can be qualified while applicability stays OPEN."""
    p = binding['payload']; slot = upper['payload'].get('claim_slots', {}).get(p['upper_claim_slot'])
    result = dict(support_basis='OPEN', project_applicability='OPEN', freshness='CURRENT',
                  exact_claim=deepcopy(slot), native_results=[], open_conditions=deepcopy(p['open_conditions']),
                  author_prose='UNQUALIFIED_EXPLANATION', variable_annotations='UNQUALIFIED_AUTHOR_ANNOTATIONS')
    try:
        check(slot is not None and slot == native_projection(snapshot,p['statement_ref'],p['argument_ref']) and
              claim_fingerprint(slot) == p['claim_fingerprint'], 'Native claim changed')
        if not _relation_matches(upper, slot):
            result['reason'] = 'No exact native relation supports the displayed direction'
            return result
        results = []
        for sid in p['support_ids']:
            support = snapshot.get('supports', {}).get(sid)
            check(support is not None and support['statement_ref'] == p['statement_ref'] and
                  support['argument_ref'] == p['argument_ref'], 'Exact support unavailable')
            results.append(assurance.evaluate_requirement(snapshot, sid, p['requirement'], p['policy_digest']))
        result['native_results'] = results
        endpoint=p['argument_ref'] or p['statement_ref']
        extent=[r for r in p['required_review_scope'] if r['target_ref']==endpoint and
                r.get('scope_version')==assurance.SCOPE_VERSION and r.get('extent')=='WHOLE_TARGET' and
                r.get('target_body_sha256')==snapshot['records'][endpoint]['body_sha256']]
        # Slots project full native fields. Regional reviews remain regional;
        # they cannot confer a whole-slot status merely by changing the label.
        qualified = bool(extent) and any(r['result'] == 'QUALIFIED' for r in results)
        result['mapped_review_extent']='WHOLE_EXACT_TARGET' if extent else 'INSUFFICIENT_FOR_WHOLE_SLOT'
        result['support_basis'] = 'QUALIFIED_WITHIN_EXACT_SCOPE' if qualified else 'OPEN'
        if any(r['result'] == 'WITHDRAWN' for r in results): result['freshness'] = 'STALE'
        # Target use must have its own exact native APPLICABILITY support; donor
        # proof alone cannot discharge a target-specific missing hypothesis.
        applicable = []
        for sid in p['applicability_refs']:
            support = snapshot.get('supports', {}).get(sid, {})
            argument = snapshot.get('records', {}).get(support.get('argument_ref'), {})
            req = support.get('consumer_requirement')
            data = argument.get('data', {})
            if data.get('mode') == 'APPLICABILITY' and req and req['purpose'] == 'APPLICABILITY' and \
               data['mode_payload']['recipient_ref'] == upper['original_target_ref'] and \
               p['statement_ref'] in data['mode_payload']['donor_refs']:
                applicable.append(assurance.evaluate_requirement(snapshot,sid,req,support.get('policy_digest')))
        result['applicability_results'] = applicable
        if qualified and not p['open_conditions'] and (
            p['statement_ref'] == upper['original_target_ref'] or any(x['result']=='QUALIFIED' for x in applicable)):
            result['project_applicability'] = 'QUALIFIED_WITHIN_EXACT_SCOPE'
        # Native scope overlap and premise propagation alone decide whether a
        # withdrawal affects this binding. No global fast withdrawal policy.
        for collection,sid in required_guards(snapshot,[dict(ref='',body=binding)]):
            if collection!='supports':continue
            support=snapshot['supports'][sid];requirement=support.get('consumer_requirement')
            if requirement and assurance.evaluate_requirement(snapshot,sid,requirement,support.get('policy_digest'))['result']=='WITHDRAWN':
                result['freshness']='STALE'
        return result
    except (FastMathError, KeyError) as exc:
        result.update(freshness='STALE', reason=str(exc))
        return result


def project(ref, snapshot):
    """Derived reverse association preserves actual old and displayed identities."""
    rows = snapshot.get('fast_revisions', {}); upper = rows.get(ref)
    check(upper is not None, 'Fast reference unavailable', 'FAST_REF_UNAVAILABLE')
    bindings = []
    for bref, binding in rows.items():
        if binding['kind'] != 'RefinementBinding': continue
        p = binding['payload']
        if p['upper_revision_ref'] == ref:
            bindings.append(dict(binding_ref=bref, binding_target=ref, displayed_upper=ref,
                reuse_link_ref=None, claim_slot=p['upper_claim_slot'], qualification=qualify_binding(binding,upper,snapshot)))
    for link_ref, link in snapshot.get('fast_claim_links', {}).items():
        if link['new_upper_ref'] != ref: continue
        binding = rows[link['source_binding_ref']]; old = rows[link['old_upper_ref']]
        check(claim_identity(old, link['old_slot']) == claim_identity(upper, link['new_slot']),
              'Changed declared claim identity cannot reuse binding')
        bindings.append(dict(binding_ref=link['source_binding_ref'], binding_target=link['old_upper_ref'],
            displayed_upper=ref, reuse_link_ref=link_ref, claim_slot=link['new_slot'],
            qualification=qualify_binding(binding, old, snapshot)))
    return dict(ref=ref, revision=deepcopy(upper), bindings=bindings,
        selected=snapshot.get('fast_selected', {}).get(upper['object_id'])==ref,
        evidence_refs=sorted(set(upper['dependencies']) | native_refs(upper)), qualification_scope='EXACT_BOUND_CLAIMS_ONLY',
        as_of_commit=snapshot.get('knowledge_commit'))
