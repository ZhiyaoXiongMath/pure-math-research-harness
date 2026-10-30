"""Closed structural validation and exact native projections, not mathematics."""
from copy import deepcopy
from pmrh.domain.primitives import canonical, sha
from pmrh.domain import assurance
from .model import (SCHEMA, DELTA_SCHEMA, KINDS, MAX_BODY, MAX_DELTA, MAX_REVISIONS,
    MAX_LINKS, MAX_REFS, MAX_DEPTH, MAX_ID, check, revision_ref, claim_fingerprint)

ENVELOPE = set('schema object_id kind scope predecessor payload payload_sha256 body body_sha256 author_attempt original_target_ref d0_ref reason dependencies'.split())
PAYLOAD = {
    'KnowledgeModule': 'title obstacle use input_refs output_ref mechanism boundaries project_use source_refs open_conditions claim_slots variable_annotations',
    'Transition': 'title start_ref end_ref relation direction shared_context_refs mechanism missing_interface probe_refs evidence_refs explanatory_order claim_slots variable_annotations',
    'ResearchMap': 'title node_refs transition_refs routes and_obligations or_alternatives shared_context_refs witness_constraints parameter_constraints gaps revision_cause affected_decisions next_probe_or_wait navigation_cycles claim_slots',
    'Frontier/Probe': 'title unknown_ref question frozen_input_refs outcomes stop retry_basis task_ref claim_slots',
    'ReaderProfile': 'title general_prerequisites specialty_entry_points project_definitions explanation_depth',
    'RefinementBinding': 'upper_revision_ref upper_claim_slot claim_fingerprint statement_ref argument_ref context_refs source_refs support_ids requirement policy_digest required_review_scope open_conditions applicability_refs invalidation_refs version_provenance',
}
DELTA_FIELDS = set('schema scope original_target_ref d0_ref request_id attempt_id input_commit capture_payload_path expected_selected read_guards revision_entries same_claim_links reason empty_reason'.split())
LINK_FIELDS = set('old_upper_ref new_upper_ref old_slot new_slot claim_fingerprint source_binding_ref'.split())
GUARD_MAPS = frozenset(('records', 'sources', 'supports', 'qualifications', 'withdrawals',
    'objects', 'inferences', 'review_executions', 'execution_events', 'obligations', 'tasks',
    'human_attestations', 'coverage_plans', 'conflicts', 'translations'))


def fields(value, names):
    check(type(value) is dict and set(value) == set(names.split() if isinstance(names, str) else names),
          'Unknown or missing fields')


def text(value, *, identifier=False, empty=False):
    check(type(value) is str and (empty or bool(value.strip())) and '\x00' not in value, 'Text required')
    check(len(value.encode('utf-8')) <= (MAX_ID if identifier else MAX_BODY), 'Text limit', 'FAST_LIMIT_EXCEEDED')


def bounded(value, maximum):
    count = 0
    def walk(x, depth):
        nonlocal count
        check(depth <= MAX_DEPTH, 'JSON depth limit', 'FAST_LIMIT_EXCEEDED')
        check(type(x) in (dict, list, str, int, bool, type(None)), 'JSON values only')
        if isinstance(x, dict):
            for k, v in x.items():
                text(k, identifier=True); walk(v, depth + 1)
        elif isinstance(x, list):
            check(len(x) <= MAX_REFS, 'Sequence limit', 'FAST_LIMIT_EXCEEDED')
            for v in x: walk(v, depth + 1)
        elif isinstance(x, str):
            count += int(x.startswith(('KR-', 'SO-', 'FM-', 'IB-')))
    walk(value, 0)
    check(count <= MAX_REFS and len(canonical(value)) <= maximum, 'Canonical byte/reference limit', 'FAST_LIMIT_EXCEEDED')
    return count


def reference_list(value, *, nonempty=False):
    check(type(value) is list and (not nonempty or value) and len(value) <= MAX_REFS, 'Reference list required')
    for r in value: text(r, identifier=True)
    check(len(value) == len(set(value)), 'Duplicate references')


def revision_structure(entry):
    """Check wire types without looking up or disclosing any referenced row."""
    fields(entry, 'ref body'); text(entry['ref'], identifier=True)
    row = entry['body']; fields(row, ENVELOPE)
    for name in ('schema', 'kind', 'object_id', 'payload_sha256', 'body_sha256'):
        text(row[name], identifier=True)
    check(row['kind'] in KINDS, 'Unknown fast revision kind')
    text(row['body']); text(row['reason'])
    for name in ('predecessor', 'original_target_ref'):
        if row[name] is not None: text(row[name], identifier=True)
    fields(row['scope'], 'project_id instance_id mission_id')
    fields(row['author_attempt'], 'request_id attempt_id')
    for value in (*row['scope'].values(), *row['author_attempt'].values()): text(value, identifier=True)
    reference_list(row['dependencies'])
    p = row['payload']; fields(p, PAYLOAD[row['kind']])
    for name in ('output_ref', 'start_ref', 'end_ref', 'unknown_ref', 'task_ref', 'upper_revision_ref',
                 'upper_claim_slot', 'claim_fingerprint', 'statement_ref', 'argument_ref', 'policy_digest'):
        if name in p and not (name in ('task_ref', 'argument_ref') and p[name] is None):
            text(p[name], identifier=True)
    for name in ('relation', 'direction', 'explanation_depth'):
        if name in p: text(p[name], identifier=True)
    for name in ('input_refs', 'source_refs', 'shared_context_refs', 'probe_refs', 'evidence_refs',
                 'node_refs', 'transition_refs', 'frozen_input_refs', 'context_refs', 'support_ids',
                 'applicability_refs', 'invalidation_refs'):
        if name in p: reference_list(p[name])
    if 'open_conditions' in p: check(type(p['open_conditions']) is list, 'Open conditions required')
    if 'claim_slots' in p:
        check(type(p['claim_slots']) is dict, 'Named claims required')
        for name, slot in p['claim_slots'].items():
            text(name, identifier=True)
            fields(slot, 'statement_ref argument_ref statement_fields argument_fields context_fields')
            text(slot['statement_ref'], identifier=True)
            if slot['argument_ref'] is not None: text(slot['argument_ref'], identifier=True)
            check(type(slot['statement_fields']) is dict and type(slot['context_fields']) is dict and
                  (slot['argument_fields'] is None or type(slot['argument_fields']) is dict), 'Native projection fields required')
    if row['kind'] == 'RefinementBinding':
        assurance.validate_requirement(p['requirement'])
        assurance.validate_scope(p['required_review_scope'])


def validate_delta_structure(value):
    """Closed input shape before authorization-sensitive reference traversal."""
    fields(value, DELTA_FIELDS); count = bounded(value, MAX_DELTA)
    fields(value['scope'], 'project_id instance_id mission_id')
    for item in value['scope'].values(): text(item, identifier=True)
    for name in ('schema', 'request_id', 'attempt_id', 'input_commit', 'capture_payload_path'):
        text(value[name], identifier=True)
    if value['original_target_ref'] is not None: text(value['original_target_ref'], identifier=True)
    text(value['reason'])
    if value['empty_reason'] is not None: text(value['empty_reason'])
    for name, limit in (('revision_entries', MAX_REVISIONS), ('same_claim_links', MAX_LINKS)):
        check(type(value[name]) is list, 'Proposal entries must be lists')
        check(len(value[name]) <= limit, 'Proposal entry limit', 'FAST_LIMIT_EXCEEDED')
    check(type(value['expected_selected']) is dict, 'Selected-revision CAS required')
    for oid, previous in value['expected_selected'].items():
        text(oid, identifier=True)
        if previous is not None: text(previous, identifier=True)
    check(type(value['read_guards']) is list, 'Read guards required')
    for g in value['read_guards']:
        fields(g, 'collection identity sha256 requirement policy_digest')
        for name in ('collection', 'identity', 'sha256'): text(g[name], identifier=True)
        if g['policy_digest'] is not None: text(g['policy_digest'], identifier=True)
    for entry in value['revision_entries']: revision_structure(entry)
    for link in value['same_claim_links']:
        fields(link, LINK_FIELDS)
        for item in link.values(): text(item, identifier=True)
    return count


def claim_identity(upper, slot_name):
    """Machine identity of a declared claim, not a semantic equivalence test."""
    identity = {key:upper[key] for key in ('kind', 'scope', 'original_target_ref', 'd0_ref')}
    identity['slot'] = upper['payload'].get('claim_slots', {}).get(slot_name)
    if upper['kind'] == 'Transition':
        identity['arrow'] = {key:upper['payload'][key] for key in
            ('start_ref', 'end_ref', 'relation', 'direction', 'shared_context_refs')}
    return identity


def scope(value, snapshot):
    fields(value, 'project_id instance_id mission_id')
    for x in value.values(): text(x, identifier=True)
    check(value['project_id'] == snapshot['project_id'], 'Project mismatch', 'FAST_REF_UNAVAILABLE')
    instance = snapshot.get('instances', {}).get(value['instance_id'])
    mission = snapshot.get('missions', {}).get(value['mission_id'])
    check(instance is not None and mission is not None and mission['instance_id'] == value['instance_id'],
          'Scope unavailable', 'FAST_REF_UNAVAILABLE')
    return instance


def target(value, snapshot):
    instance = scope(value['scope'], snapshot)
    check(value['original_target_ref'] == instance.get('target_ref') and
          value['d0_ref'] == instance.get('discovery_scope'), 'Original target/D0 changed')


def native_projection(snapshot, statement_ref, argument_ref=None):
    """Every qualified field is copied from exact lower records, without prose inference."""
    statement = snapshot.get('records', {}).get(statement_ref)
    check(statement is not None and statement['kind'] == 'Statement', 'Statement unavailable', 'FAST_REF_UNAVAILABLE')
    argument = snapshot['records'].get(argument_ref) if argument_ref else None
    if argument_ref:
        check(argument is not None and argument['kind'] == 'Argument' and
              argument['data']['conclusion_ref'] == statement_ref, 'Argument does not conclude exact statement')
    contexts = sorted(set(statement['context_refs']) | set(argument['context_refs'] if argument else []))
    check(all(snapshot['records'].get(r, {}).get('kind') == 'Context' for r in contexts), 'Context unavailable')
    # Full named native fields retain ordered quantifiers, hypotheses, witness
    # assignments, directions, inference AND/OR and applicability conditions.
    return dict(statement_ref=statement_ref, argument_ref=argument_ref,
        statement_fields=deepcopy(statement['data']), argument_fields=deepcopy(argument['data']) if argument else None,
        context_fields={r:deepcopy(snapshot['records'][r]['data']) for r in contexts})


def native_refs(value):
    result = set()
    def walk(x):
        if isinstance(x, str) and x.startswith(('KR-', 'SO-', 'IB-')): result.add(x)
        elif isinstance(x, dict):
            for k,v in x.items(): walk(k); walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(value)
    return result


def fast_refs(value):
    result = set()
    def walk(x):
        if isinstance(x, str) and x.startswith('FM-'): result.add(x)
        elif isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(value)
    return result


def validate_slot(slot, snapshot):
    fields(slot, 'statement_ref argument_ref statement_fields argument_fields context_fields')
    check(slot == native_projection(snapshot, slot['statement_ref'], slot['argument_ref']),
          'Claim is not an exact native field projection')


def validate_revision(entry, snapshot, revisions):
    revision_structure(entry)
    fields(entry, 'ref body'); row = entry['body']; fields(row, ENVELOPE)
    bounded(row, MAX_BODY)
    check(row['schema'] == SCHEMA and row['kind'] in KINDS, 'Unknown fast revision schema/kind')
    text(row['object_id'], identifier=True); text(row['reason']); text(row['body'])
    fields(row['author_attempt'], 'request_id attempt_id')
    for v in row['author_attempt'].values(): text(v, identifier=True)
    check(row['payload_sha256'] == sha(canonical(row['payload'])) and row['body_sha256'] == sha(row['body'].encode()), 'Body digest differs')
    check(entry['ref'] == revision_ref(row), 'Revision digest differs')
    target(row, snapshot)
    reference_list(row['dependencies'])
    p = row['payload']; fields(p, PAYLOAD[row['kind']])
    if row['predecessor'] is not None:
        previous = revisions.get(row['predecessor'])
        check(previous is not None and previous['object_id'] == row['object_id'] and
              previous['kind'] == row['kind'] and previous['scope'] == row['scope'], 'Predecessor lineage differs')
    check(all(r in revisions or any(r in snapshot.get(c,{}) for c in ('records','sources','inferences'))
              for r in row['dependencies']), 'Dependency is not an exact available reference','FAST_REF_UNAVAILABLE')
    refs = fast_refs(p) | fast_refs(row['dependencies'])
    check(all(r in revisions for r in refs), 'Unresolved or cyclic exact fast reference')
    check(all(revisions[r]['scope'] == row['scope'] for r in refs), 'Cross-scope fast reference')
    check(all(revisions[r]['kind']!='RefinementBinding' for r in refs),'Bindings are reverse projections, never upper dependencies')
    for r in native_refs(p) | native_refs(row['dependencies']):
        check(r in snapshot.get('records', {}) or r in snapshot.get('sources', {}) or r in snapshot.get('inferences', {}),
              'Exact native reference unavailable', 'FAST_REF_UNAVAILABLE')
    if 'claim_slots' in p:
        check(type(p['claim_slots']) is dict, 'Named claims required')
        for name, slot in p['claim_slots'].items(): text(name, identifier=True); validate_slot(slot, snapshot)
    for name in ('title', 'mechanism', 'obstacle', 'use', 'boundaries', 'project_use', 'question', 'stop', 'retry_basis', 'revision_cause', 'next_probe_or_wait'):
        if name in p: text(p[name])
    for name in ('input_refs', 'source_refs', 'shared_context_refs', 'probe_refs', 'evidence_refs', 'node_refs', 'transition_refs', 'frozen_input_refs'):
        if name in p:
            reference_list(p[name])
            check(all(r in revisions or any(r in snapshot.get(c,{}) for c in ('records','sources','inferences')) for r in p[name]),
                  'Dangling typed reference','FAST_REF_UNAVAILABLE')
            if name=='source_refs':check(all(r in snapshot.get('sources',{}) for r in p[name]),'Source occurrence reference required')
            if name=='shared_context_refs':check(all(snapshot.get('records',{}).get(r,{}).get('kind')=='Context' for r in p[name]),'Context reference required')
            if name=='transition_refs':check(all(revisions.get(r,{}).get('kind')=='Transition' for r in p[name]),'Transition reference required')
            if name=='probe_refs':check(all(revisions.get(r,{}).get('kind')=='Frontier/Probe' for r in p[name]),'Probe reference required')
    if 'variable_annotations' in p:
        check(type(p['variable_annotations']) is list, 'Variable annotations required')
        for variable in p['variable_annotations']:
            fields(variable, 'variable_id domain_locator depends_on quantifier_locator witness_ref parameter_dependencies shared_witness_group')
            text(variable['variable_id'], identifier=True)
            reference_list(variable['depends_on']); reference_list(variable['parameter_dependencies'])
            from pmrh.domain.knowledge import validate_locator
            for name in ('domain_locator', 'quantifier_locator'):
                validate_locator(variable[name], None)
    kind = row['kind']
    if kind == 'KnowledgeModule':
        reference_list(p['input_refs'], nonempty=True)
        check(p['claim_slots'] and p['output_ref'] in {s['statement_ref'] for s in p['claim_slots'].values()}, 'Callable exact output required')
        check(type(p['open_conditions']) is list, 'Open conditions required')
        conditions = [c for s in p['claim_slots'].values() for c in (s['argument_fields'] or {}).get('open_conditions', [])]
        check(all(c in p['open_conditions'] for c in conditions), 'Dropped open condition')
    elif kind == 'Transition':
        check(all(snapshot.get('records',{}).get(p[k],{}).get('kind')=='Statement' for k in ('start_ref','end_ref')),
              'Transition endpoints must be exact native statements')
        check(p['relation'] in {'IMPLICATION', 'CONDITIONAL_IMPLICATION', 'APPLICABILITY', 'EQUIVALENCE', 'HEURISTIC', 'ANALOGY', 'UNKNOWN'}, 'Unknown relation')
        check(p['direction'] in {'FORWARD', 'BOTH', 'OPEN'}, 'Direction required')
        check(type(p['explanatory_order']) is int and p['explanatory_order'] >= 0, 'Explanatory order required')
        text(p['missing_interface'], empty=True)
        check(p['direction'] == ('BOTH' if p['relation']=='EQUIVALENCE' else 'OPEN' if p['relation'] in {'HEURISTIC','ANALOGY','UNKNOWN'} else 'FORWARD'), 'Relation/direction mismatch')
    elif kind == 'ResearchMap':
        for name in ('routes','and_obligations','or_alternatives','witness_constraints','parameter_constraints','gaps','affected_decisions','navigation_cycles'):
            check(type(p[name]) is list, 'Explicit map lists required')
        for route in p['routes']:
            fields(route, 'route_id node_refs transition_refs operator native_argument_ref')
            text(route['operator'], identifier=True)
            check(route['operator'] in {'AND','OR'}, 'Explicit AND/OR required')
            reference_list(route['node_refs']); reference_list(route['transition_refs'])
        # Cycles contain stable navigation IDs only, never recursive exact hashes.
        for cycle in p['navigation_cycles']:
            check(type(cycle) is list and len(cycle)>=2 and cycle[0]==cycle[-1], 'Closed navigation cycle required')
            reference_list(cycle[:-1], nonempty=True)
            check(not any(x.startswith('FM-') for x in cycle), 'Navigation cycles use stable IDs')
    elif kind == 'Frontier/Probe':
        check(p['unknown_ref'] in revisions or any(p['unknown_ref'] in snapshot.get(c,{}) for c in ('records','sources','inferences')),
              'Exact unknown/interface required')
        check(p['task_ref'] is None or p['task_ref'] in snapshot.get('tasks',{}), 'Unknown actual probe task')
        check(type(p['outcomes']) is list and p['outcomes'], 'Bounded outcome consequences required')
        names = set()
        for outcome in p['outcomes']:
            fields(outcome, 'outcome consequence evidence_refs')
            text(outcome['outcome'], identifier=True); text(outcome['consequence']); reference_list(outcome['evidence_refs'])
            names.add(outcome['outcome'])
        check('NO_PROGRESS' in names, 'No-progress outcome must remain explicit')
        check(names <= {'SUPPORTED_WITHIN_SCOPE','SCOPED_DEFECT','METHOD_FAILURE','LOCAL_LEMMA_FAILURE','NO_PROGRESS','UNKNOWN'}, 'No global refutation from a probe')
    elif kind == 'ReaderProfile':
        check(p['explanation_depth'] in {'OVERVIEW','INTERFACES','EVIDENCE'}, 'Explanation depth')
        for name in ('general_prerequisites','specialty_entry_points','project_definitions'):
            check(type(p[name]) is list, 'Reader prerequisites required')
            for x in p[name]: text(x)
    elif kind == 'RefinementBinding':
        upper = revisions.get(p['upper_revision_ref'])
        check(upper is not None and upper['kind'] != 'RefinementBinding', 'Exact upper revision required')
        slot = upper['payload'].get('claim_slots', {}).get(p['upper_claim_slot'])
        check(slot is not None and claim_fingerprint(slot) == p['claim_fingerprint'], 'Claim slot differs')
        check((p['statement_ref'], p['argument_ref']) == (slot['statement_ref'], slot['argument_ref']), 'Lower endpoint mismatch')
        check(p['context_refs'] == sorted(slot['context_fields']), 'Context mismatch')
        check(p['open_conditions'] == (slot['argument_fields'] or {}).get('open_conditions', []), 'Open conditions differ')
        assurance.validate_requirement(p['requirement'])
        check(p['policy_digest'] == sha(canonical(p['requirement'])), 'Consumer policy digest differs')
        check(p['required_review_scope'] == p['requirement']['required_scope'], 'Review extent differs')
        reference_list(p['support_ids']); reference_list(p['applicability_refs']); reference_list(p['invalidation_refs'])
        selected=set(p['support_ids']) | set(p['applicability_refs']);pending=list(selected)
        while pending:
            sid=pending.pop();support=snapshot.get('supports',{}).get(sid)
            check(support is not None,'Exact selected support unavailable','FAST_REF_UNAVAILABLE')
            for dependency in support.get('premise_support_refs',[]):
                if dependency not in selected:selected.add(dependency);pending.append(dependency)
        check(set(p['invalidation_refs'])<=selected,'Invalidation dependencies must belong to the selected native support closure')
        check(all(snapshot.get('supports', {}).get(s, {}).get('statement_ref') == p['statement_ref'] and
                  snapshot['supports'][s].get('argument_ref') == p['argument_ref'] for s in p['support_ids']), 'Support does not conclude bound claim')
        check(all(r['target_ref'] in {p['statement_ref'], p['argument_ref']} for r in p['required_review_scope']), 'Unrelated review scope')
        check(all(snapshot['supports'][sid].get('consumer_requirement') == p['requirement'] and
                  snapshot['supports'][sid].get('policy_digest') == p['policy_digest'] for sid in p['support_ids']),
              'Use the exact existing native consumer policy; a new policy needs native support')
        check(type(p['version_provenance']) is dict and p['version_provenance'] == row['author_attempt'], 'Version provenance differs')
    return row


def guard(snapshot, collection, identity, requirement=None):
    check(collection in GUARD_MAPS and identity in snapshot.get(collection, {}), 'Guard unavailable', 'FAST_REF_UNAVAILABLE')
    row = snapshot[collection][identity]
    material = row
    if collection == 'supports':
        # Freeze the existing native consumer and its exact derived outcome.
        # This also detects a newly added scoped withdrawal/conflict, or changed
        # independence/coverage evidence, without inventing a fast proof policy.
        requirement = deepcopy(row.get('consumer_requirement')) if requirement is None else requirement
        check(requirement is not None and requirement == row.get('consumer_requirement'), 'Exact support consumer required')
        material = dict(row=row, native_assurance=assurance.evaluate_requirement(
            snapshot, identity, requirement, row.get('policy_digest')))
    return dict(collection=collection, identity=identity, sha256=sha(canonical(material)),
                requirement=deepcopy(requirement), policy_digest=sha(canonical(requirement)) if requirement is not None else None)


def required_guards(snapshot, entries, links=()):
    """Exact native rows reached by revisions and reuse, including credentials."""
    required = set(); visited_fast=set(); pending = [entry['body'] for entry in entries]
    for link in links:
        for ref in (link['old_upper_ref'], link['source_binding_ref']):
            if ref in snapshot.get('fast_revisions',{}):pending.append(snapshot['fast_revisions'][ref])
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,dict):
            for k,v in value.items():
                yield k
                yield from strings(v)
        elif isinstance(value,list):
            for v in value:yield from strings(v)
    while pending:
        value=pending.pop()
        for ref in strings(value):
            if ref in snapshot.get('fast_revisions',{}) and ref not in visited_fast:
                visited_fast.add(ref);pending.append(snapshot['fast_revisions'][ref])
            for collection in GUARD_MAPS:
                if ref in snapshot.get(collection,{}) and (collection,ref) not in required:
                    required.add((collection,ref));pending.append(snapshot[collection][ref])
    return required


def validate_delta(value, snapshot, *, check_guards=True):
    reference_entries=validate_delta_structure(value)
    check(value['schema'] == DELTA_SCHEMA and value['capture_payload_path'] == '/payload/fast_delta', 'Proposal schema/path')
    target(value, snapshot)
    for k in ('request_id','attempt_id','input_commit'): text(value[k], identifier=True)
    text(value['reason'])
    check(type(value['revision_entries']) is list and len(value['revision_entries']) <= MAX_REVISIONS, 'Revision count', 'FAST_LIMIT_EXCEEDED')
    check(type(value['same_claim_links']) is list and len(value['same_claim_links']) <= MAX_LINKS, 'Claim link count', 'FAST_LIMIT_EXCEEDED')
    check(len({sha(canonical(link)) for link in value['same_claim_links']})==len(value['same_claim_links']),'Duplicate same-claim link')
    check(type(value['expected_selected']) is dict, 'Selected-revision CAS required')
    check(bool(value['revision_entries'] or value['same_claim_links']) == (value['empty_reason'] is None), 'Honest empty delta reason required')
    if value['empty_reason'] is not None: text(value['empty_reason'])
    check(type(value['read_guards']) is list, 'Read guards required')
    check(reference_entries+len(value['read_guards'])<=MAX_REFS,'Combined guard/reference limit','FAST_LIMIT_EXCEEDED')
    for g in value['read_guards']:
        fields(g, 'collection identity sha256 requirement policy_digest')
        check(g['collection'] in GUARD_MAPS, 'Unknown guard collection')
        if g['requirement'] is not None: assurance.validate_requirement(g['requirement'])
        check(g['policy_digest'] == (sha(canonical(g['requirement'])) if g['requirement'] is not None else None), 'Guard policy mismatch')
        if check_guards:
            check(g['identity'] in snapshot.get(g['collection'], {}) and g == guard(snapshot,g['collection'],g['identity'],g['requirement']), 'Relevant native guard changed', 'FAST_VERSION_CONFLICT')
    revisions = dict(snapshot.get('fast_revisions', {})); changed = set()
    for entry in value['revision_entries']:
        row = validate_revision(entry, snapshot, revisions)
        check(row['scope'] == value['scope'] and row['author_attempt'] == {k:value[k] for k in ('request_id','attempt_id')}, 'Attempt/scope differs')
        oid = row['object_id']; check(oid not in changed, 'Two selected revisions for one object')
        check(oid in value['expected_selected'] and row['predecessor'] == value['expected_selected'][oid], 'Predecessor/CAS differs')
        if check_guards:
            check(snapshot.get('fast_selected', {}).get(oid) == value['expected_selected'][oid], 'Selected revision changed', 'FAST_VERSION_CONFLICT')
        check(entry['ref'] not in revisions, 'Immutable revision already exists')
        revisions[entry['ref']] = row; changed.add(oid)
    check(changed == set(value['expected_selected']), 'Extraneous/missing selected guard')
    for link in value['same_claim_links']:
        fields(link, LINK_FIELDS)
        old = revisions.get(link['old_upper_ref']); new = revisions.get(link['new_upper_ref']); binding = revisions.get(link['source_binding_ref'])
        check(old is not None and new is not None and binding is not None, 'Reuse reference unavailable')
        check(old['scope'] == new['scope'] == binding['scope'] == value['scope'] and old['object_id'] == new['object_id'] and
              new['predecessor'] == link['old_upper_ref'], 'Reuse lineage differs')
        a = old['payload'].get('claim_slots', {}).get(link['old_slot']); b = new['payload'].get('claim_slots', {}).get(link['new_slot'])
        check(a is not None and a == b and claim_fingerprint(a) == link['claim_fingerprint'], 'Changed mathematical claim cannot reuse binding')
        check(claim_identity(old, link['old_slot']) == claim_identity(new, link['new_slot']),
              'Changed declared claim identity cannot reuse binding')
        check(binding['kind'] == 'RefinementBinding' and binding['payload']['upper_revision_ref'] == link['old_upper_ref'] and
              binding['payload']['upper_claim_slot'] == link['old_slot'], 'Invented binding target')
    # Existing linked bindings are validated again without retargeting them.
    for link in value['same_claim_links']:
        binding = revisions[link['source_binding_ref']]
        validate_revision({'ref':link['source_binding_ref'],'body':binding},snapshot,revisions)
    required = required_guards(snapshot,value['revision_entries'],value['same_claim_links'])
    supplied = {(g['collection'],g['identity']) for g in value['read_guards']}
    check(len(supplied)==len(value['read_guards']) and len(supplied)<=MAX_REFS, 'Duplicate/excessive read guards')
    check(required <= supplied, 'Missing exact dependency/credential guards')
    for g in value['read_guards']:
        if g['collection']=='supports':
            check(g['requirement']==snapshot['supports'][g['identity']].get('consumer_requirement'), 'Unbound support guard')
    return revisions
