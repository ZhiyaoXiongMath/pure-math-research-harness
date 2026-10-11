"""Exact consumer material plans, separate from upstream work completion.

The same builder runs before assignment and again before freezing.  It never
grants support, chooses a new scientific sample, or reads another capture's
verdict.  Plans retain identity/provenance; bodies live only in frozen files.
"""
from copy import deepcopy

from .util import identity, require
from . import relations

SCHEMA = 'pmrs.input-plan/1'
SCIENTIFIC_KINDS = {'Context', 'Statement', 'Argument', 'Example'}
SOURCE_DUTIES = {'MATERIAL', 'APPLICABILITY', 'ESTABLISH', 'REFUTE', 'REDUCE',
                 'COMPARE', 'INTEGRATE', 'DISCRIMINATE', 'FORMULATE'}


def task_brief(snapshot,obligation,consumer,plan,*,blob_get=None,independent=False):
    """Self-contained task navigation; actual mathematical bodies stay exact."""
    d=_definition(obligation);basis=consumer.get('entry_basis',{});decision=basis.get('strategy',{})
    iid=consumer['instance_id'];instance=snapshot['instances'][iid]
    from .research_audit import effective_guidance
    guidance=effective_guidance(snapshot,iid)
    references=[]
    for ref in plan.get('roots',[]):
        record=snapshot.get('records',{}).get(ref,{})
        body=blob_get(record['body_sha256']).decode('utf-8') if blob_get and record.get('body_sha256') else ''
        references.append({'record_ref':ref,'kind':record.get('kind'),'body_sha256':record.get('body_sha256'),
            'navigation_excerpt':body[:1200],'excerpt_only':len(body)>1200,'instruction':'Read the complete bound original body before using this premise.'})
    sources=[{'source_ref':r,'title':snapshot['sources'][r].get('title'),
        'version':snapshot['sources'][r].get('version'),'blob_hash':snapshot['sources'][r]['blob_hash'],
        'selection':plan.get('source_selections',{}).get(r),'purpose':snapshot['sources'][r].get('purpose')}
        for r in plan.get('required_source_refs',[])]
    handoffs=[]
    if not independent:
        dependencies={v.get('binding_id') for v in d.get('dependency_bindings',[])}
        for upstream in snapshot.get('obligations',{}).values():
            if not any(c['binding_id'] in dependencies for c in upstream['definition']['consumer_bindings']):continue
            handoffs.extend(deepcopy(upstream.get('projection',{}).get('attempt_accounts',[])))
    return {'schema':'pmrs.stage-task-brief/4.2.2','original_target_ref':instance.get('target_ref'),
        'd0_scope':deepcopy(instance.get('discovery_scope')),'stage_id':consumer['stage_id'],'role':consumer['role'],
        'duty_body':blob_get(d['criterion_body_ref']).decode('utf-8') if blob_get else None,
        'main_proposal_ref':decision.get('proposal_ref'),'route_ref':decision.get('route_ref'),
        'selection_reason':None if independent else decision.get('selection_reason'),
        'exact_material_navigation':references,'exact_sources':sources,
        'compatible_prior_handoffs':handoffs,
        'effective_guidance':{'version':guidance['version'],'original_directions':[] if independent else guidance['original_directions'],
            'filtered_reason':'Independent input excludes MAIN opinions, prior verdicts and subjective route/guidance summaries' if independent else None},
        'communication':'Use task.json communication_contract and actual scoped tools. MAIN is reachable; other links are explicit. Reading substantive shared conclusions can remove independent-vote eligibility.',
        'handoff_requirement':'In the ordinary attempt_account, explain what you actually did, exact evidence, reusable partial work, open gaps, failed attempts, blocking conditions and suggested next work. Recommendations go to MAIN; do not independently expand to another stage or the whole project. A failed process or absent handoff does not prove mathematical failure.',
        'replacement_basis':None if independent else deepcopy(basis.get('replacement_basis'))}


def _definition(obligation):
    return obligation.get('definition', obligation)


def _accepted(snapshot, consumer, *, binding_id=None, change_ref=None):
    rows = []
    for request in snapshot.get('requests', {}).values():
        task = snapshot.get('tasks', {}).get(request.get('task_id'), {})
        if request.get('acceptance_state') != 'ACCEPTED':
            continue
        if task.get('instance_id') != consumer['instance_id'] or request.get('mission_id', task.get('mission_id')) != consumer['mission_id']:
            continue
        if binding_id is not None and not any(b['binding_id'] == binding_id for b in task.get('obligation_bindings', [])):
            continue
        if change_ref is not None and 'CHANGE-' + str(request.get('capture_ref')) != change_ref:
            continue
        rows.append((request, task))
    return sorted(rows, key=lambda pair: pair[0]['request_id'])


def _produced(snapshot, requests):
    ids = {task['task_id'] for _, task in requests}
    return {row['record_ref'] for row in snapshot.get('production_events', {}).values()
            if row.get('task_id') in ids}


def _record_provenance(snapshot, ref, consumer):
    rows = []
    for event in snapshot.get('production_events', {}).values():
        if event.get('record_ref') != ref:
            continue
        task = snapshot.get('tasks', {}).get(event.get('task_id'), {})
        request = snapshot.get('requests', {}).get(event.get('request_id'), {})
        if task and (task.get('instance_id') != consumer['instance_id'] or
                     request.get('acceptance_state') != 'ACCEPTED'):
            continue
        rows.append({'production_ref': event.get('event_id'), 'task_id': event.get('task_id'),
                     'request_id': event.get('request_id'),
                     'capture_ref': event.get('capture_hash', request.get('capture_ref')),
                     'origin_ref': event.get('origin_ref'),
                     'obligation_bindings': deepcopy(task.get('obligation_bindings', []))})
    return sorted(rows, key=lambda row: str(row['production_ref']))


def _same_producer_arguments(snapshot, roots, consumer):
    """Use the actual producer of a conclusion, never any accepted proof of it."""
    records = snapshot.get('records', {})
    productions = snapshot.get('production_events', {})
    result = set()
    for ref in roots:
        if records.get(ref, {}).get('kind') != 'Statement':
            continue
        producer_ids = {p.get('task_id') for p in productions.values() if p.get('record_ref') == ref and p.get('task_id')}
        producer_ids = {tid for tid in producer_ids
                        if snapshot.get('tasks', {}).get(tid, {}).get('instance_id') == consumer['instance_id']
                        and snapshot.get('requests', {}).get(snapshot['tasks'][tid].get('request_id'), {}).get('acceptance_state') == 'ACCEPTED'}
        for p in productions.values():
            if p.get('task_id') not in producer_ids:
                continue
            argument = records.get(p.get('record_ref'), {})
            if argument.get('kind') == 'Argument' and argument.get('data', {}).get('conclusion_ref') == ref:
                result.add(p['record_ref'])
    return result


def _source_version(snapshot, ref):
    source = snapshot.get('sources', {}).get(ref)
    require(source is not None, 'INCOMPLETE_CONTEXT', 'Required exact source occurrence missing: ' + str(ref))
    status = snapshot.get('survey_source_status', {}).get(ref, {})
    require(not status.get('withdrawn') and not status.get('version_conflict'),
            'INPUT_SOURCE_STALE', 'Required source is withdrawn or has an unresolved version conflict: ' + ref)
    return {'source_ref': ref, 'source_revision': identity(source), 'blob_hash': source['blob_hash'],
            'version': source.get('version', source.get('source_version', source.get('source_key'))),
            'bytes': source.get('bytes'), 'status_guard': identity(status)}


def build(snapshot, obligation, consumer, *, blob_get=None):
    from .obligations import dependency_inputs
    from .corrections import resolve_dependency
    from .workflows.registry import INDEPENDENT
    d = _definition(obligation)
    records = snapshot.get('records', {})
    reasons = {}
    def add(refs, reason):
        for ref in refs:
            reasons.setdefault(ref, set()).add(reason)
    add(d.get('target_refs', []), 'EXACT_DUTY_TARGET')
    add(d.get('scope_context_refs', []), 'DUTY_SCOPE_CONTEXT')
    add(consumer.get('input_refs', []), 'DECLARED_SCIENTIFIC_INPUT')
    original = snapshot.get('instances', {}).get(consumer['instance_id'], {}).get('target_ref')
    if original:
        add([original], 'ORIGINAL_WORKFLOW_TARGET')
    add(dependency_inputs(snapshot, d), 'EXPLICIT_SCIENTIFIC_DEPENDENCY')
    independent = consumer.get('role') in INDEPENDENT
    source_reasons = {ref: {'DECLARED_DUTY_SOURCE'} for ref in consumer.get('source_refs', [])}
    completed = []
    # A completion token is not the body of every record in the upstream duty.
    # The automatic scientific chain nevertheless needs its exact conventions
    # and mathematical results, selected by type and exact producer binding.
    for declared in d.get('dependency_bindings', []):
        dep = resolve_dependency(snapshot, declared)
        if dep is None or dep.get('threshold') != 'WORK_DISPOSITION_RECORDED':
            continue
        upstream = snapshot.get('obligations', {}).get(dep.get('binding_ref'), {})
        requests = _accepted(snapshot, consumer, binding_id=dep.get('binding_id')) if dep.get('binding_id') else []
        evidence = _produced(snapshot, requests) & set(upstream.get('projection', {}).get('evidence_refs', []))
        selected = set()
        if consumer.get('entry_basis', {}).get('research_plan'):
            for request, task in requests:
                if independent and task.get('role') in INDEPENDENT:
                    continue
                produced = _produced(snapshot, [(request, task)]) & evidence
                selected |= {ref for ref in produced if records.get(ref, {}).get('kind') in SCIENTIFIC_KINDS}
                if consumer.get('stage_id') in {'P2', 'P3'} and task.get('stage_id') == 'P1':
                    for item in task.get('input_manifest', []):
                        if item['kind'] == 'source':
                            source_reasons.setdefault(item['ref'], set()).add('EXACT_BACKGROUND_DUTY_SOURCE')
                if consumer.get('stage_id', '').startswith('S'):
                    selected |= {ref for ref in produced if records.get(ref, {}).get('kind') == 'SourceEvidence'}
            add(selected, 'EXACT_UPSTREAM_MATHEMATICAL_RESULT')
        completed.append({'dependency': deepcopy(dep),
                          'accepted_requests': [{'request_id': r['request_id'], 'task_id': t['task_id'],
                                                 'capture_ref': r.get('capture_ref')} for r, t in requests],
                          'selected_scientific_refs': sorted(selected),
                          'excluded_outputs': [{'record_ref': ref, 'reason': 'NOT_A_PREMISE_OF_THIS_DUTY'}
                                               for ref in sorted(evidence - selected)]})
    # A concrete accepted gap inherits the exact producing duty's material,
    # including ESTABLISH (not only the old MATERIAL/APPLICABILITY cases).
    origin = _accepted(snapshot, consumer, change_ref=d.get('created_by')) if str(d.get('created_by', '')).startswith('CHANGE-') else []
    if origin and d['type'] in SOURCE_DUTIES:
        for _, task in origin:
            for row in task.get('input_manifest', []):
                if row['kind'] == 'source':
                    source_reasons.setdefault(row['ref'], set()).add('EXACT_ORIGIN_DUTY_SOURCE')
    # Full global accounting consumes real mathematical attempts, with review
    # verdicts excluded.  Preserve account text separately in plan context.
    if consumer.get('stage_id') == 'P11':
        from .obligations import plan_input_refs
        add([r for r in plan_input_refs(snapshot, consumer) if records.get(r, {}).get('kind') in SCIENTIFIC_KINDS],
            'GLOBAL_FRONTIER_MATHEMATICAL_RESULT')
    add(_same_producer_arguments(snapshot, list(reasons), consumer), 'EXACT_SAME_PRODUCER_ARGUMENT')
    for sid in consumer.get('selected_support_refs', []) or consumer.get('selected_supports', []) or ([consumer['selected_support']] if consumer.get('selected_support') else []):
        support = snapshot.get('supports', {}).get(sid)
        require(support is not None, 'INCOMPLETE_CONTEXT', 'Selected exact support is missing: ' + sid)
        add([support['statement_ref'], support['argument_ref']], 'EXACT_SELECTED_SUPPORT_INPUT')
    roots = sorted(reasons)
    closure = relations.premise_closure(roots, snapshot)
    for ref in closure - set(roots):add([ref], 'NECESSARY_PREMISE_CLOSURE')
    opposing={edge['source_ref'] for edge in relations.edges(snapshot)
        if edge['type']=='COUNTEREXAMPLE_TO' and edge.get('assertion_state')!='WITHDRAWN'
        and edge['target_ref'] in closure}
    reverse=relations.premise_closure(opposing,snapshot)
    for ref in reverse-set(closure):add([ref],'NECESSARY_REVERSE_COUNTEREVIDENCE')
    closure|=reverse
    # Provenance and methods have explicit purposes; they are not proof support.
    for edge in relations.edges(snapshot):
        if edge.get('assertion_state') == 'WITHDRAWN' or edge['source_ref'] not in closure:
            continue
        if edge['type'] == 'SOURCE_PROVENANCE' or edge['type'] == 'USED_SOURCE':
            source_reasons.setdefault(edge['target_ref'], set()).add(
                'SOURCE_ATTRIBUTION' if edge['type'] == 'SOURCE_PROVENANCE' else 'DUTY_METHOD_OR_SOURCE_USE')
    for ref in closure:
        if ref in snapshot.get('sources', {}):
            source_reasons.setdefault(ref, set()).add('NECESSARY_SOURCE_CLOSURE')
    # Exact supplied source versions are validated at assignment and freeze.
    declared_selections = consumer.get('source_selections', {})
    if isinstance(declared_selections, list):
        require(len({row.get('source_ref') for row in declared_selections}) == len(declared_selections),
                'INPUT_PLAN_INVALID', 'Duplicate source selections')
        declared_selections = {row['source_ref']: row for row in declared_selections}
    require(isinstance(declared_selections, dict), 'INPUT_PLAN_INVALID', 'Source selections must be an exact source mapping')
    require(set(declared_selections) <= set(source_reasons), 'INPUT_PLAN_INVALID', 'Source selection is outside this duty input plan')
    sources = []
    selections = {}
    for ref in sorted(source_reasons):
        version = _source_version(snapshot, ref)
        selected = deepcopy(declared_selections.get(ref, {'coverage': 'FULL_DOCUMENT', 'locators': [],
                                                        'reason': 'Exact original material required by the declared duty or its premises.'}))
        selected.pop('source_ref', None)
        require(selected.get('coverage') in {'FULL_DOCUMENT', 'DECLARED_RANGE', 'METADATA_ONLY'} and
                isinstance(selected.get('locators', []), list) and isinstance(selected.get('reason'), str) and selected['reason'].strip(),
                'INPUT_PLAN_INVALID', 'Source coverage and scientific reason are required')
        if selected['coverage'] == 'DECLARED_RANGE':
            require(selected.get('locators'), 'INPUT_PLAN_INVALID', 'An excerpt needs exact original locators')
            from .knowledge import validate_locator
            allowed = {version['blob_hash'], *snapshot['sources'][ref].get('extraction_blob_hashes', [])}
            for locator in selected['locators']:
                require(locator['blob_hash'] in allowed, 'ORIGINAL_BYTES_MISMATCH', 'Excerpt does not belong to the exact source occurrence')
                validate_locator(locator, blob_get)
        else:
            require(not selected.get('locators'), 'INPUT_PLAN_INVALID', 'Only declared-range selection accepts locators')
        selections[ref] = selected
        sources.append({**version, 'coverage': selected['coverage'], 'reasons': sorted(source_reasons[ref])})
    for ref in reasons:
        require(ref in records or ref in snapshot.get('sources', {}) or ref in snapshot.get('inferences', {}),
                'INCOMPLETE_CONTEXT', 'Required exact scientific input missing: ' + str(ref))
    plan = {'schema': SCHEMA, 'instance_id': consumer['instance_id'], 'mission_id': consumer['mission_id'],
            'binding_id': consumer['binding_id'], 'obligation_id': d['obligation_id'],
            'definition_revision': d['definition_revision'], 'original_target_ref': original,
            'roots': roots, 'required_source_refs': sorted(source_reasons), 'source_selections': selections,
            'completion_dependencies': completed,
            'scientific_input_refs': sorted(ref for ref in reasons if ref in records),
            'selected_records': [{'record_ref': ref, 'kind': records[ref]['kind'],
                                  'body_sha256': records[ref]['body_sha256'], 'reasons': sorted(reasons[ref]),
                                  'provenance': _record_provenance(snapshot, ref, consumer)}
                                 for ref in sorted(reasons) if ref in records],
            'source_versions': sources,
            'rationale': 'Completion identities and scientific premises are distinct. Full necessary record bodies and open premises are retained; source coverage is explicit.'}
    plan['plan_hash'] = identity(plan, 'INPUTPLAN-')
    return plan


def enrich_consumer(snapshot, obligation, consumer, *, blob_get=None):
    result = deepcopy(consumer)
    requirement=result.get('required_assurance',result.get('entry_basis',{}).get('consumer_requirement'))
    if requirement and blob_get is not None:
        from .assurance import normalize_scope
        from . import contracts as C
        requirement=deepcopy(requirement)
        requirement['required_scope']=normalize_scope(requirement['required_scope'],snapshot,blob_get)
        for slot in requirement['review_slots']:
            slot['required_scope']=normalize_scope(slot['required_scope'],snapshot,blob_get)
        result['required_assurance']=requirement
        result['policy_digest']=C.digest(requirement)
        if 'consumer_requirement' in result.get('entry_basis',{}):
            result['entry_basis']['consumer_requirement']=deepcopy(requirement)
    plan = build(snapshot, obligation, result, blob_get=blob_get)
    # Keep declared roots stable. Inherited inputs belong to the plan, so later
    # recomputation cannot relabel them as fresh explicit user choices.
    result['input_plan'] = plan
    return result


def model_view(plan):
    """Scientific reading view; immutable host provenance remains native.

    This does not omit any selected scientific record or source body. Metadata
    already present in records/sources or task bindings is not copied again.
    """
    fields=('schema','original_target_ref','source_selections','rationale')
    view={key:deepcopy(plan[key]) for key in fields if key in plan}
    view['representation']='MODEL_VIEW_V1'
    view['selected_records']=[{'record_ref':row['record_ref'],'reasons':deepcopy(row['reasons'])}
        for row in plan['selected_records']]
    view['completion_dependencies']=[{'dependency':deepcopy(row['dependency']),
        'accepted_request_refs':[r['request_id'] for r in row['accepted_requests']],
        'selected_scientific_refs':deepcopy(row['selected_scientific_refs'])}
        for row in plan['completion_dependencies']]
    return view

def compact_context(context, plan):
    """One copy of actual attempt accounts, without completion-only evidence."""
    if not context:
        return None
    result = deepcopy(context)
    selected = set(plan['scientific_input_refs'])
    for name in ('dependency_work', 'synthesis_work', 'global_gap_inventory'):
        for branch in result.get(name, []):
            branch['evidence_refs'] = [ref for ref in branch.get('evidence_refs', []) if ref in selected]
            # The input plan already carries these exact accepted receipts.
            # Keep scientific attempt accounts here, without a second copy.
            if any(item['dependency'].get('binding_id') == branch.get('binding_id')
                   for item in plan['completion_dependencies']):
                branch.pop('accepted_requests', None)
        if not result.get(name):result.pop(name, None)
    if isinstance(result.get('plan'), dict):
        view=result['plan']
        for key in ('common_input_refs', 'common_source_refs'):
            view.pop(key, None)  # input_plan is the complete exact authority.
        if 'selected_branches' in view:
            view['selected_binding_ids']=[row['binding_id'] for row in view.pop('selected_branches')]
    # The immutable plan includes completion receipts; old full reused_work
    # copies would repeat accounts and inject outputs excluded from the duty.
    result.pop('reused_prerequisites', None)
    return result
