"""Closed DEV06 control records and journal verification.

This module reads immutable evidence. It imports no legacy reducers, runtime or
transport. Trusted writer assembly supplies native transitions separately.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pmrh.domain.primitives import canonical, identity, loads, require, sha, PMRSError
from pmrh.domain import protocols
from pmrh.ports.dto import core as C, events as V, execution as X, specs as S, enums as E, capability as K
from pmrh.ports.capabilities import check_capabilities
from pmrh.ports.dto.wire import MAX_JSON_BYTES, _wire_budget

SCHEMA = 'pmrh.commit/2'
RECORD_SCHEMA = 'pmrh.control/1'
EVENT_SCHEMA = 'pmrh.control-event/1'
MAX_ITEMS = 4096
GENESIS_FIELDS = frozenset('accepted_requests active_reports assistant_events assistant_messages assistant_sessions assistant_turns attempt_groups attempt_outcomes backend_internal_usage backend_usage budget_grants candidates capabilities captures collaboration_groups communication_events communication_impacts communication_link_revisions communication_links consumer_controls consumers control_events corrections coverage_plans delegation_observations dispatch_plans execution_events fences handoff_adoptions handoffs human_decisions human_directions inferences input_deliveries input_windows instances knowledge_changes language_policy leases live_main_dispatches main_decisions main_execution_recoveries main_replies max_workers message_acks missions native_main_bindings native_main_events native_main_turns native_usage_cursors objects obligation_bindings obligations production_events project_budget project_id qualifications records relations report_authorizations report_events report_receipts reports requests research_audit_events research_audits research_checkpoints research_clocks research_guidance research_messages research_routes responses result_families retired_consumers retry_grants review_executions round_accounts round_deliveries scheduler_state schema scope_versions selected_reports selection_events sources strategies strategy_events strategy_proposals strategy_triggers supports survey_coverage survey_events survey_output_plans survey_readings survey_retrievals survey_reviews survey_search_plans survey_snapshots survey_source_status survey_sources synthetic_test_only tasks title translations usage usage_events usage_log_cursors versions visits withdrawals'.split())
RECORD_FIELDS = {
    'PROFILE': 'profile project_id genesis_commit setup_head resource_policy pool_id',
    'OWNER': 'logical_main_id owner_id owner_epoch backend_binding_ref authorization_ref',
    'DECISION': 'decision_id scope principal_ref authn_evidence_ref authority_ref action payload_sha256 owner_epoch control_version issued_at expires_at budget_grant_ref capability_manifest_ref',
    'RESERVATION': 'reservation_id identity grant_ref unit amount owner_epoch control_version',
    'CALL': 'operation_id idempotency_key invocation_id logical_agent_id attempt_id owner_epoch control_version spec_ref reservation_ref capability_manifest_ref send_phase slot_token send_boundary_id charge receipt_ids not_sent_ref termination_ref evidence_conflict',
    'INBOX': 'producer_ref binding_ref cursor state gap last_page_ref',
    'RECEIPT': 'receipt_id identity binding_ref producer_ref receipt_kind receipt_ref',
    'GUIDANCE': 'principal_ref authorization_ref message_kind guidance_version receipt_ids',
}
PAYLOAD_FIELDS = {
    'ACTIVATED': 'profile_ref owner_id backend_binding_ref',
    'OWNER_ACQUIRED': 'owner_id backend_binding_ref takeover_evidence_refs',
    'CONTROL_APPLIED': 'native_event',
    'GRANT_REVOKED': 'budget_grant_id expected_revision reason_ref',
    'CALL_PREPARED': 'task_ref candidate_ref spec_ref reservation_ref',
    'SLOT_CONFIRMED': 'request_id pool_id token pool_revision',
    'SEND_STARTED': 'request_id send_boundary_id',
    'EXECUTION_RECEIVED': 'receipt',
    'INBOX_PAGE_RECEIVED': 'request_id producer_ref binding_ref page_ref',
    'CANCEL_UNSENT': 'request_id not_sent_evidence_ref',
    'CANCEL_REQUESTED': 'request_id reason_ref',
    'UNKNOWN_DISPOSED': 'request_id disposition evidence_refs',
    'SCIENCE_ADMITTED': 'request_id capture_ref',
    'STRATEGY_APPLIED': 'native_event',
    'COMMUNICATION_APPLIED': 'native_event',
    'GUIDANCE_SAVED': 'direction_ref',
    'GUIDANCE_OBSERVED': 'steering_receipt_ref',
}
EVENT_FIELDS = set('schema type operation_id idempotency_key scope expected_head owner_epoch control_version payload decision_ref'.split())
CONTROL_TYPES = frozenset('AUTHORIZE_MISSION EXTEND_MISSION_BUDGET PAUSE RESUME HUMAN_DECISION SET_P14_MODE REQUEST_STOP_AT_P14 CANCEL_STOP_AT_P14'.split())
STRATEGY_TYPES = frozenset('STRATEGY_INITIALIZED STRATEGY_TRIGGERED STRATEGY_LIVE_PROPOSAL'.split())
COMMUNICATION_LIVE = frozenset('COMMUNICATION_LINKS_REVISED COLLAB_GROUP_BOUND MESSAGE_PUBLISHED MESSAGE_ACKED INPUT_DELIVERY_PREPARED'.split())
COMMUNICATION_RECOVERY = frozenset('MESSAGE_WITHDRAWN INPUT_DELIVERY_CONFIRMED INPUT_WINDOW_SEALED TOOL_CONTROL_REJECTED'.split())
RECEIPT_TYPES = {'DISPATCH': X.DispatchReceipt, 'OBSERVATION': X.ExecutionObservation,
                 'CAPTURE': X.CaptureReceipt, 'USAGE': X.UsageObservation,
                 'CANCELLATION': X.CancellationReceipt}


def check(condition, code='CONTROL_INVALID'):
    require(condition, code, 'Closed synthetic control contract failed')


def fields(value, names):
    check(type(value) is dict and set(value) == set(names.split() if isinstance(names, str) else names))


def string(value):
    check(type(value) is str and 0 < len(value.encode('utf-8')) <= 4096 and '\x00' not in value)


def integer(value, minimum=0):
    check(type(value) is int and minimum <= value < 2**63)


def digest(value):
    check(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value))


def scope(value):
    fields(value, 'project_id instance_id')
    for v in value.values():
        string(v)
    return C.Scope(**value)


def timestamp(value):
    string(value)
    check(value.endswith('Z') or value.endswith('+00:00'))
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    check(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0)
    return parsed


def ref(value, project=None, *, nullable=False):
    if nullable and value is None:
        return None
    result = C.ExactRef.from_wire(value)
    check(project is None or result.project_id == project, 'AUTHORIZATION_REQUIRED')
    return result


def record(kind, **values):
    result = {'schema': RECORD_SCHEMA, 'kind': kind, **values}
    validate_record(result)
    return result


def validate_record(value, *, combined=False):
    check(type(value) is dict and value.get('kind') in RECORD_FIELDS)
    kind = value['kind']
    fields(value, {'schema', 'kind', *RECORD_FIELDS[kind].split()})
    check(value['schema'] == RECORD_SCHEMA, 'UNSUPPORTED_SCHEMA_VERSION')
    _wire_budget(value, wire=True)
    nullable_refs = ({'budget_grant_ref', 'capability_manifest_ref'} if kind == 'DECISION' else
                     {'backend_binding_ref'} if kind == 'OWNER' else
                     {'not_sent_ref', 'termination_ref'} if kind == 'CALL' else
                     {'last_page_ref'} if kind == 'INBOX' else set())
    for name, v in value.items():
        if name.endswith('_ref'):
            ref(v, nullable=name in nullable_refs)
        elif name in {'owner_epoch', 'control_version', 'guidance_version'}:
            integer(v, 1 if name == 'guidance_version' or name == 'owner_epoch' and kind != 'DECISION' else 0)
        elif name == 'scope':
            scope(v)
        elif name == 'identity':
            C.InvocationIdentity.from_wire(v)
        elif name in {'genesis_commit', 'setup_head', 'payload_sha256'}:
            digest(v)
        elif name in {'issued_at', 'expires_at'}:
            timestamp(v)
        elif name == 'receipt_ids':
            check(type(v) is list and len(v) <= MAX_ITEMS and len(v) == len(set(v)))
            for item in v:
                string(item)
        elif name == 'evidence_conflict':
            check(type(v) is bool)
        elif name in {'logical_main_id', 'slot_token', 'send_boundary_id'}:
            if v is not None:
                string(v)
        elif name == 'cursor':
            V.EventCursor.from_wire(v)
        elif name == 'gap':
            if v is not None:
                V.EventGap.from_wire(v)
        elif name == 'amount':
            check(type(v) is int and v == 1)
        else:
            string(v)
    if kind == 'PROFILE':
        check(value['profile'] == 'SYNTHETIC_TEST_ONLY' and value['resource_policy'] == 'COMPAT_8_20_SURVEY1')
    elif kind == 'DECISION':
        allowed_actions = set(PAYLOAD_FIELDS) | {'RECOVER_RECEIPT'}
        if combined:
            from .control_fast import FAST_PAYLOAD_FIELDS
            allowed_actions.update(FAST_PAYLOAD_FIELDS)
        check(value['action'] in allowed_actions)
        check(timestamp(value['issued_at']) < timestamp(value['expires_at']))
    elif kind == 'RESERVATION':
        check(value['unit'] == 'AGENT_INVOCATION')
    elif kind == 'CALL':
        check(value['send_phase'] in {'READY', 'ATTEMPTED', 'CLOSED'})
        check(value['charge'] in {'RESERVED', 'UNKNOWN_RESERVED', 'SPENT_OR_SETTLED', 'RELEASED'})
        check(value['send_phase'] != 'READY' or value['send_boundary_id'] is None)
        check(value['send_phase'] != 'ATTEMPTED' or value['send_boundary_id'] is not None)
        check(not value['evidence_conflict'] or value['send_phase'] == 'CLOSED' and value['charge'] == 'SPENT_OR_SETTLED')
    elif kind == 'INBOX':
        check(value['state'] in {'OPEN', 'GAP'} and (value['state'] == 'OPEN') == (value['gap'] is None))
        check(value['cursor']['stream_kind'] == 'RUNNER')
    elif kind == 'RECEIPT':
        check(value['receipt_kind'] in RECEIPT_TYPES)
    elif kind == 'GUIDANCE':
        check(value['message_kind'] in {'HUMAN_GUIDANCE', 'GUIDANCE_PROPOSAL'})
    return value


def command(value, *, published=False, combined=False):
    fields(value, EVENT_FIELDS if published else EVENT_FIELDS - {'decision_ref'})
    event_schema = EVENT_SCHEMA; payload_fields = PAYLOAD_FIELDS
    if combined:
        from .control_fast import EVENT_SCHEMA as event_schema, FAST_PAYLOAD_FIELDS
        payload_fields = {**PAYLOAD_FIELDS, **FAST_PAYLOAD_FIELDS}
    check(value['schema'] == event_schema, 'UNSUPPORTED_SCHEMA_VERSION')
    kind = value['type']
    check(kind in payload_fields, 'UNSUPPORTED_CAPABILITY')
    _wire_budget(value, wire=True)
    for name in ('operation_id', 'idempotency_key'):
        string(value[name])
    boundary = scope(value['scope'])
    digest(value['expected_head'])
    integer(value['owner_epoch']); integer(value['control_version'])
    if published:
        ref(value['decision_ref'], boundary.project_id)
    p = value['payload']
    fields(p, payload_fields[kind])
    for name, v in p.items():
        if name.endswith('_refs'):
            check(type(v) is list and len(v) <= MAX_ITEMS)
            for item in v:
                ref(item, boundary.project_id)
        elif name.endswith('_ref'):
            ref(v, boundary.project_id, nullable=name == 'backend_binding_ref')
        elif name in {'expected_revision', 'pool_revision'}:
            integer(v, 1 if name == 'expected_revision' else 0)
        elif name == 'receipt':
            validate_record(v); check(v['kind'] == 'RECEIPT')
        elif name != 'native_event':
            string(v)
    if kind == 'UNKNOWN_DISPOSED':
        check(p['disposition'] in {'ABANDON_UNKNOWN', 'CONFIRMED_NOT_SENT'})
    if 'native_event' in p:
        native = p['native_event']; check(type(native) is dict)
        allowed = {'CONTROL_APPLIED': CONTROL_TYPES, 'STRATEGY_APPLIED': STRATEGY_TYPES,
                   'COMMUNICATION_APPLIED': COMMUNICATION_LIVE | COMMUNICATION_RECOVERY}[kind]
        check(native.get('event_type') in allowed, 'UNSUPPORTED_CAPABILITY')
        if kind == 'CONTROL_APPLIED':
            check(native.get('instance_id') == boundary.instance_id and native.get('project_id') == boundary.project_id)
            if native['event_type'] == 'HUMAN_DECISION':
                check(native['payload'].get('action') in {'CONTINUE', 'CONTINUE_DISCOVERY', 'PAUSE', 'END', 'END_WITHOUT_ADOPTION'}, 'UNSUPPORTED_CAPABILITY')
    return value


def current_version(instance):
    return (instance.get('infrastructure_control_version', 0) if instance['kind'] == 'SURVEY'
            else instance['run_control']['control_version'])


def is_controlled(state):
    return any('ownership' in row for row in state.get('instances', {}).values())


def lane_closed(request):
    call = request.get('admission', {})
    return bool(call and not call['evidence_conflict'] and request['execution_inbox']['state'] == 'OPEN' and
                (call['not_sent_ref'] or call['termination_ref'] and
                 (request['execution_state'] == 'SETTLED' or request['fenced'])))


def releasable(request):
    call = request['admission']
    return bool(not call['evidence_conflict'] and request['execution_inbox']['state'] == 'OPEN' and
                (call['not_sent_ref'] or call['termination_ref']))


@dataclass
class ControlIndex:
    project: str
    profile: dict | None = None
    operations: dict = field(default_factory=dict)
    keys: dict = field(default_factory=dict)
    closure: set = field(default_factory=set)
    receipts: dict = field(default_factory=dict)
    streams: dict = field(default_factory=dict)
    refs: dict = field(default_factory=dict)
    visit_origins: dict = field(default_factory=dict)


def read_ref(store, wire, project, *, maximum=MAX_JSON_BYTES):
    reference = ref(wire, project)
    return store._read_blob(reference.sha256, maximum)


def read_json(store, wire, project):
    raw = read_ref(store, wire, project)
    value = loads(raw, maximum=MAX_JSON_BYTES)
    check(canonical(value) == raw)
    _wire_budget(value, wire=True)
    return value


def without_visit(candidate):
    result = deepcopy(candidate)
    result['consumer'].pop('visit_id', None)
    return result


def native_event(kind, payload):
    """Original event encoding only; this pure reader never runs a reducer."""
    result = dict(actor='host', capability_ref='CAP-HOST', event_type=kind, payload=deepcopy(payload))
    return dict(result, event_id=identity(result, 'EXEC-EVENT-'))


def visit_plan(state, candidate, origins):
    """Derive one original visit from the exact authorized duty at this HEAD.

    Origins come only from earlier fully validated CALLs, never a checkpoint or
    caller-selected identity. No field in this result grants execution authority.
    """
    fields(candidate, 'obligation_id definition_revision consumer instance_id mission_id stage_id role stage_spec_digest '
           'budget_grant_id budget_domain priority ready_since purpose_key responsibility_key input_fingerprint '
           'attempt_group_key state code retry_grant remaining_uses')
    check(type(candidate['consumer']) is dict)
    string(candidate['obligation_id']); string(candidate['budget_grant_id']); integer(candidate['definition_revision'], 1)
    consumer = candidate['consumer']
    obligation = state['obligations'].get(candidate.get('obligation_id'))
    check(obligation is not None, 'AUTHORIZATION_REQUIRED')
    definition = obligation['definition']
    check(candidate.get('definition_revision') == definition['definition_revision'], 'STALE_OBLIGATION_DEFINITION')
    assigned = [c for c in definition['consumer_bindings'] if c['binding_id'] == consumer.get('binding_id')]
    check(len(assigned) == 1 and
          {k:v for k,v in assigned[0].items() if k != 'visit_id'} ==
          {k:v for k,v in consumer.items() if k != 'visit_id'}, 'AUTHORIZATION_REQUIRED')
    assigned = assigned[0]
    for name in ('instance_id', 'mission_id', 'stage_id', 'role'):
        check(candidate.get(name) == assigned.get(name), 'AUTHORIZATION_REQUIRED')
    iid, mid = assigned['instance_id'], assigned['mission_id']
    instance = state['instances'].get(iid); mission = state['missions'].get(mid)
    check(instance is not None and mission is not None and instance['status'] == 'ACTIVE' and
          instance['current_mission_id'] == mid and mission['instance_id'] == iid and
          mission['status'] == 'ACTIVE', 'AUTHORIZATION_REQUIRED')
    contract = protocols.spec(assigned['stage_id'])
    check(contract['workflow_kind'] == instance['kind'] and
          candidate.get('stage_spec_digest') == contract['digest'], 'STAGE_SPEC_CHANGED')
    protocols.validate_assignment(assigned['stage_id'], definition['type'], assigned['role'], assigned.get('entry_basis', {}))
    grant = state['budget_grants'].get(candidate.get('budget_grant_id'))
    check(grant is not None and grant['instance_id'] == iid and grant['mission_id'] == mid and
          grant['grant_status'] == 'ACTIVE' and mission['budget_grant_id'] == candidate['budget_grant_id'], 'AUTHORIZATION_REQUIRED')
    check(candidate['state'] == 'READY' and candidate['code'] == 'AUTHORIZED_RELEVANT_WORK' and
          candidate['retry_grant'] == state['retry_grants'].get(assigned['retry_grant_id']) and
          candidate['budget_domain'] == grant.get('budget_domain', 'SCIENCE'))
    priority = (-1000000 if assigned.get('actor_kind') == 'MAIN' else
                state['consumer_controls'].get(assigned['binding_id'], {}).get('priority', assigned.get('priority', 0)))
    check(candidate['priority'] == priority and candidate['ready_since'] == assigned.get('ready_since', 0))
    core = dict(instance_id=iid, mission_id=mid, stage_id=assigned['stage_id'],
        stage_spec_digest=contract['digest'], entry_basis=deepcopy(assigned.get('entry_basis', {})),
        assigned_obligation_bindings=[dict(binding_id=assigned['binding_id'], obligation_id=definition['obligation_id'],
                                         expected_definition_revision=definition['definition_revision'])])
    check(set(state['visits']) == set(origins), 'CONTROL_INVALID')
    matches = []
    for vid, row in state['visits'].items():
        check(row == origins[vid]['row'], 'CONTROL_INVALID')
        expected = dict(core, visit_id=vid, outcome=None, exit_evidence=[], unperformed_duties=[])
        if row == expected:
            check(mission['stage_visit_ids'].count(vid) == 1)
            matches.append(vid)
    if matches:
        vid = min(matches); opening = None
        visit = dict(core, visit_id=vid)
    else:
        vid = identity(dict(core, sequence=len(state['visits'])), 'VISIT-')
        check(vid not in state['visits'], 'VISIT_EXISTS')
        visit = dict(core, visit_id=vid)
        opening = native_event('VISIT_OPENED', {'visit': visit})
    for supplied in (assigned.get('visit_id'), consumer.get('visit_id')):
        check(supplied is None or supplied == vid, 'AUTHORIZATION_REQUIRED')
    bound = deepcopy(candidate); bound['consumer']['visit_id'] = vid
    return dict(visit=visit, opening=opening), bound


def task_visit_link(state, head, task, candidate, plan):
    visit = plan['visit']
    check(task.get('knowledge_commit') == head, 'VERSION_CONFLICT')
    check(task.get('visit_id') == candidate['consumer'].get('visit_id') == visit['visit_id'])
    for name in ('instance_id', 'mission_id', 'stage_id', 'stage_spec_digest'):
        check(task.get(name) == visit[name])
    check(task.get('role') == candidate['consumer']['role'] and
          task.get('obligation_bindings') == visit['assigned_obligation_bindings'])
    check(task.get('actor_kind') == candidate['consumer'].get('actor_kind') and
          task.get('retry_grant') == candidate['consumer']['retry_grant_id'])
    independent = task['role'] in protocols.INDEPENDENT
    check(task.get('independent') is independent and task.get('excluded_verdicts') is independent)
    for name in ('purpose_key', 'responsibility_key', 'attempt_group_key', 'input_fingerprint'):
        check(task.get(name) == candidate.get(name))
    slot = 1 + max((r['sample_slot'] for r in state['requests'].values()
                    if r['attempt_group_key'] == task['attempt_group_key']), default=0)
    check(type(task.get('sample_slot')) is int and task['sample_slot'] == slot)
    check(task['attempt_key'] == identity({'group':task['attempt_group_key'], 'sample_slot':slot}, 'ATTEMPT-'))
    check(task['task_id'] == identity(dict(attempt=task['attempt_key'], contract=task['stage_spec_digest'],
                                         instance=task['instance_id'], mission=task['mission_id']), 'TASK-'))
    check(task['request_id'] == identity({'task':task['task_id']}, 'REQUEST-'))


def visit_effects(before, plan):
    """Exact optional VISIT_OPENED mechanical projection, without execution."""
    expected = deepcopy(before)
    visit = plan['visit']; vid = visit['visit_id']; mid = visit['mission_id']
    if plan['opening'] is not None:
        check(vid not in expected['visits'] and vid not in expected['missions'][mid]['stage_visit_ids'])
        expected['visits'][vid] = dict(deepcopy(visit), outcome=None, exit_evidence=[], unperformed_duties=[])
        expected['missions'][mid]['stage_visit_ids'].append(vid)
        event = plan['opening']
        check(event['event_id'] not in expected['execution_events'])
        expected['execution_events'][event['event_id']] = deepcopy(event)
    return expected


def validate_call_effects(store, index, before, after, event, decision):
    """Closed original preparation bookkeeping; never imports task execution."""
    from .journal import _persistent
    p = event['payload']; project = index.project
    task = read_json(store, p['task_ref'], project)
    candidate = read_json(store, p['candidate_ref'], project)
    plan, bound = visit_plan(before, candidate, index.visit_origins)
    check(bound == candidate)  # No visitless /2 mode, including the first CALL.
    task_visit_link(before, event['expected_head'], task, candidate, plan)
    spec = S.AgentInvocationSpec.from_wire(read_json(store, p['spec_ref'], project))
    reservation = read_json(store, p['reservation_ref'], project)
    check(reservation['grant_ref'] == decision['budget_grant_ref'] == spec.budget_grant_ref.to_wire())
    check(read_json(store, reservation['grant_ref'], project) == before['budget_grants'][candidate['budget_grant_id']])
    check(task['request_id'] == spec.request_id and task['attempt_key'] == spec.attempt_id and
          task['mission_id'] == spec.research_goal_id and task['instance_id'] == event['scope']['instance_id'] == spec.instance_id)
    check(spec.purpose == task.get('work_purpose', 'DEFAULT') and spec.read_set_digest == sha(canonical(task['read_set'])))
    check((spec.role is E.AgentRole.MAIN) == (task.get('actor_kind') == 'MAIN'))
    check(spec.stage_responsibility == (None if spec.role is E.AgentRole.MAIN else task['stage_id']))
    for reference, native_value in ((spec.input_manifest_ref, task['input_manifest']),
            (spec.output_contract_ref, task['permission_manifest']),
            (spec.communication_contract_ref, task.get('communication_contract', {})),
            (spec.sandbox_policy_ref, task['executor_contract'])):
        check(read_ref(store, reference.to_wire(), project) == canonical(native_value))
    instance = before['instances'][task['instance_id']]
    original_scope = (instance['target_ref'] if instance['kind'] == 'TRH' else
                      instance['discovery_scope'] if instance['kind'] == 'FDH' else instance['survey_scope'])
    check(read_ref(store, spec.original_scope_ref.to_wire(), project) == canonical(original_scope))
    model = task['model_policy']
    check((spec.model_selection.model_id, spec.model_selection.effort, spec.model_selection.service_tier) ==
          (model['model'], model.get('reasoning_effort'), model.get('service_tier')))
    expected = visit_effects(before, plan)
    rid, tid = task['request_id'], task['task_id']
    check(rid not in before['requests'] and tid not in before['tasks'])
    expected['tasks'][tid] = deepcopy(task)
    request = {k:task[k] for k in ('request_id', 'task_id', 'instance_id', 'mission_id', 'purpose_key',
                'responsibility_key', 'attempt_group_key', 'attempt_key', 'sample_slot', 'input_fingerprint')}
    request.update(execution_state='RESERVED', acceptance_state='NOT_SUBMITTED', execution_kind='SYNTHETIC_TEST_ONLY',
        execution_id=identity({'request':rid}, 'EXECUTION-'), budget_grant_id=candidate['budget_grant_id'],
        reserved_calls=1, capture_ref=None, usage=None, fenced=False, receipt_ref=None)
    if task.get('budget_domain'):request['budget_domain'] = task['budget_domain']
    request['admission'] = record('CALL', operation_id=event['operation_id'], idempotency_key=event['idempotency_key'],
        invocation_id=spec.invocation_id, logical_agent_id=spec.logical_agent_id, attempt_id=spec.attempt_id,
        owner_epoch=spec.owner_epoch, control_version=spec.expected_control_version, spec_ref=p['spec_ref'],
        reservation_ref=p['reservation_ref'], capability_manifest_ref=decision['capability_manifest_ref'],
        send_phase='READY', slot_token=None, send_boundary_id=None, charge='RESERVED', receipt_ids=[],
        not_sent_ref=None, termination_ref=None, evidence_conflict=False)
    producer = after['requests'][rid]['execution_inbox']['producer_ref']
    request['execution_inbox'] = record('INBOX', producer_ref=producer, binding_ref=spec.runner_binding_ref.to_wire(),
        cursor=V.EventCursor(scope=spec.identity().scope, stream_kind=E.StreamKind.RUNNER,
            stream_id=spec.invocation_id, after_sequence=0, last_event_id=None).to_wire(),
        state='OPEN', gap=None, last_page_ref=None)
    expected['requests'][rid] = request
    grant = expected['retry_grants'][candidate['consumer']['retry_grant_id']]
    used = [r for r in before['requests'].values() if r['execution_state'] != 'CANCELLED_BEFORE_SEND' and not r.get('repair_of')]
    remaining = min(grant['max_research_attempts'] - sum(r['attempt_group_key'] == task['attempt_group_key'] for r in used),
        grant.get('max_responsibility_attempts', grant['max_research_attempts']) - sum(r['responsibility_key'] == task['responsibility_key'] for r in used))
    check(remaining > 0 and candidate.get('remaining_uses') == remaining)
    grant['remaining_uses'] = remaining - 1
    group = expected['attempt_groups'].setdefault(task['attempt_group_key'], dict(request_ids=[], highest_sample_slot=0))
    group['request_ids'].append(rid); group['highest_sample_slot'] = task['sample_slot']
    scheduler = expected['scheduler_state']
    scheduler.setdefault('last_instance_by_tier', {})[str(candidate['priority'])] = task['instance_id']
    age = before['scheduler_state'].get('ordinary_preparations_since_account')
    if age is None:
        events = before['execution_events']
        age = min(8, sum(e.get('event_type') == 'PREPARE' for e in events.values()) if events else len(before['tasks']))
    check(type(age) is int and 0 <= age <= 8)
    definition = before['obligations'][candidate['obligation_id']]['definition']
    scheduler['ordinary_preparations_since_account'] = 0 if definition['type'] in {'ACCOUNT', 'REPORT'} else min(8, age+1)
    if task.get('actor_kind') == 'MAIN':
        strategy = expected['strategies'].get(task.get('strategy_ref'))
        check(strategy is not None and strategy['instance_id'] == task['instance_id'] and strategy['revision'] == task['strategy_revision'])
        active = strategy.get('active_main_request_id')
        if active:
            previous = before['requests'][active]; call = previous['admission']
            check(releasable(previous) and (call['not_sent_ref'] or
                  call['termination_ref'] and (previous['execution_state'] == 'SETTLED' or previous['fenced'])), 'MAIN_BUSY')
        strategy['active_main_request_id'] = rid
        for did in task.get('strategy_context', {}).get('direction_ids', []):
            direction = expected['human_directions'].get(did)
            check(direction is not None and direction['instance_id'] == task['instance_id'] and not direction.get('request_id'))
            direction['request_id'] = rid
    preparations = [e for key,e in after['execution_events'].items() if key not in before['execution_events'] and e.get('event_type') == 'PREPARE']
    check(len(preparations) == 1)
    at = preparations[0].get('payload', {}).get('issued_at')
    check(timestamp(decision['issued_at']) <= timestamp(at) < timestamp(decision['expires_at']))
    events = [native_event('PREPARE', dict(task=task, candidate=candidate, max_workers=8, issued_at=at)),
              native_event('RESERVE', dict(request_id=rid, executor_contract=task['executor_contract'],
                  model_policy=task['model_policy'], execution_kind='SYNTHETIC_TEST_ONLY', issued_at=at))]
    for original in events:
        check(original['event_id'] not in expected['execution_events'])
        expected['execution_events'][original['event_id']] = original
    check(_persistent(after) == _persistent(expected), 'CAPABILITY_VIOLATION')
    if plan['opening'] is not None:
        vid = plan['visit']['visit_id']
        index.visit_origins[vid] = dict(row=deepcopy(expected['visits'][vid]), opening=deepcopy(plan['opening']),
                                       operation_id=event['operation_id'], head=event['expected_head'])
    return plan


def exact(store, project, object_id, value, *, raw=False):
    data = value if raw else canonical(value)
    check(type(data) is bytes and len(data) <= (1024**2 if raw else MAX_JSON_BYTES), 'RESOURCE_LIMIT')
    digest_value = store.put_blob(data)
    return C.ExactRef(project_id=project, object_id=object_id,
                      revision='sha256:'+digest_value, sha256=digest_value).to_wire()


def validate_entry(entry, *, combined=False):
    schema = SCHEMA
    if combined:
        from .control_fast import SCHEMA as schema
    if entry['schema'] != schema:
        check(not any(e.get('schema') == EVENT_SCHEMA for e in entry['events']), 'JOURNAL_INVALID')
        return
    events = [e for e in entry['events'] if e.get('type') != 'CHECKPOINT']
    check(len(events) == 1 and entry['actor'] == 'SYNTHETIC_TEST_ONLY', 'JOURNAL_INVALID')
    command(events[0], published=True, combined=combined)
    check(entry['previous_commit'] is not None and
          events[0]['expected_head'] == entry['previous_commit']['commit'], 'JOURNAL_INVALID')


def validate_state(state):
    """Cross-field checks independent of authentication and disposable indexes."""
    for iid, instance in state['instances'].items():
        owner = instance['ownership']; validate_record(owner)
        check(owner['kind'] == 'OWNER')
        check(owner['logical_main_id'] == (None if instance['kind'] == 'SURVEY' else 'MAIN-'+iid))
        if instance['kind'] == 'SURVEY':
            check('run_control' not in instance); integer(instance['infrastructure_control_version'])
    for grant in state['budget_grants'].values():
        check(grant['budget_unit'] == 'AGENT_INVOCATION' and grant['grant_status'] in {'ACTIVE', 'REVOKED'})
        integer(grant['grant_revision'], 1); ref(grant['authorization_ref'], state['project_id'])
        check((grant.get('explicit_unlimited') is True) != (type(grant.get('max_calls')) is int))
    for rid, request in state['requests'].items():
        call = request['admission']; inbox = request['execution_inbox']
        validate_record(call); validate_record(inbox)
        check(call['kind'] == 'CALL' and inbox['kind'] == 'INBOX')
        check(request['execution_kind'] == 'SYNTHETIC_TEST_ONLY' and request['execution_state'] != 'PREPARED')
        check(inbox['cursor']['scope'] == C.Scope(project_id=state['project_id'], instance_id=request['instance_id']).to_wire())
        check(inbox['cursor']['stream_id'] == call['invocation_id'])
        check(call['charge'] != 'RELEASED' or call['not_sent_ref'] is not None)
        check(not call['evidence_conflict'] or request['fenced'])
    for direction in state.get('human_directions', {}).values():
        validate_record(direction['provenance'])


def validate_control_writes(before, after, event):
    """Read-side write contract for each closed native control subaction.

    These are constraints on persisted effects, not a second native reducer.
    In particular a control decision never grants fields absent from its input.
    """
    from .journal import _diff
    native = event['payload']['native_event']; kind = native['event_type']
    payload = native['payload']; iid = event['scope']['instance_id']
    common = {'instances', 'control_events', 'scope_versions', 'research_clocks'}
    grants = deepcopy(before['budget_grants']); project = deepcopy(before['project_budget'])
    workers = before['max_workers']; permitted = set(common)
    current = before['instances'][iid]
    new_mission = kind == 'AUTHORIZE_MISSION' and 'future_configuration' not in payload
    duplicate_native = native['event_id'] in before['control_events']

    def normalized_policy(policy, updates, resets=()):
        # Mirror only the exact keyed replacement shape. Scientific/model
        # eligibility remains with the original native writer validation.
        result = deepcopy(policy)
        existing = list(result.get('model_overrides', []))
        if result.get('model_override'):existing.append(result['model_override'])
        keys = ('workflow_kind', 'stage_id', 'role', 'purpose')
        def key(scope):
            check(set(scope) == set(keys))
            return tuple(scope[k] for k in keys)
        merged = {key(item['scope']):deepcopy(item) for item in existing}
        check(len(merged) == len(existing))
        for scope in resets:merged.pop(key(scope), None)
        for item in updates:merged[key(item['scope'])] = deepcopy(item)
        result.pop('model_override', None)
        result.update(model_overrides=[merged[k] for k in sorted(merged)],
                      configuration_authorized=True, configuration_event_ref=native['event_id'])
        return result

    if new_mission and not duplicate_native:
        permitted |= {'missions', 'obligations', 'retry_grants', 'budget_grants', 'project_budget', 'max_workers'}
        mission = payload['mission']; grant = deepcopy(payload['budget']); gid = mission['budget_grant_id']
        check(gid not in grants and grant['budget_grant_id'] == gid, 'CAPABILITY_VIOLATION')
        policy = grant.setdefault('execution_policy', {})
        overrides = list(policy.get('model_overrides', []))
        if policy.get('model_override'):overrides.append(policy.pop('model_override'))
        if overrides:grant['execution_policy'] = normalized_policy({}, overrides) | {
            k:v for k,v in policy.items() if k not in {'model_overrides','configuration_authorized','configuration_event_ref'}}
        if 'project_limit' in grant:project['max_calls'] = grant.pop('project_limit')
        elif grant.get('explicit_unlimited') is True:project['explicit_unlimited'] = True
        elif not project.get('explicit_unlimited'):project['max_calls'] += grant['max_calls']
        workers = grant.get('max_workers', workers)
        grant.update(instance_id=iid, mission_id=mission['mission_id'], authorized_by=native['event_id'])
        grants[gid] = grant
    elif kind == 'EXTEND_MISSION_BUDGET' and not duplicate_native:
        permitted |= {'budget_grants', 'project_budget'}
        gid = before['missions'][current['current_mission_id']]['budget_grant_id']
        amount = payload['added_calls']
        check(type(amount) is int and 1 <= amount <= 1000)
        grants[gid]['max_calls'] += amount; project['max_calls'] += amount
    elif kind == 'AUTHORIZE_MISSION' and not duplicate_native:
        permitted.add('budget_grants')
        config = payload['future_configuration']
        check(config['mission_id'] == current['current_mission_id'] == native['mission_id'])
        gid = before['missions'][config['mission_id']]['budget_grant_id']
        grants[gid]['execution_policy'] = normalized_policy(grants[gid].get('execution_policy', {}),
            config['model_overrides'], config.get('reset_scopes', []))
    # A native exact duplicate has no native effects. The outer command still
    # has its independently authenticated decision/control-version transition.
    if duplicate_native:
        check(before['control_events'][native['event_id']] == native)
        grants = deepcopy(before['budget_grants']); project = deepcopy(before['project_budget']); workers = before['max_workers']
    else:
        for gid, grant in grants.items():
            previous = before['budget_grants'].get(gid)
            if previous != grant:
                grant.update(budget_unit='AGENT_INVOCATION', grant_revision=previous['grant_revision']+1 if previous else 1,
                    grant_status=previous['grant_status'] if previous else 'ACTIVE', authorization_ref=event['decision_ref'])
    check(after['budget_grants'] == grants and after['project_budget'] == project and after['max_workers'] == workers,
          'CAPABILITY_VIOLATION')
    check(set(_diff(before, after)) <= permitted, 'CAPABILITY_VIOLATION')
    # Check the effects of the named native instruction, not merely the names
    # of fields it may write. In particular PAUSE cannot carry a hidden resume,
    # and configuration/extension cannot erase a pending P14/D5 human wait.
    expected = deepcopy(current)
    control = expected.get('run_control')
    eid = native['event_id']; at = native['issued_at']
    waiting = {'WAITING_HUMAN_AT_P14', 'WAITING_HUMAN_AT_D5'}
    instruction = False
    missions = deepcopy(before['missions'])
    obligations = deepcopy(before['obligations'])
    retries = deepcopy(before['retry_grants'])
    events = deepcopy(before['control_events']); versions = deepcopy(before['scope_versions'])
    if not duplicate_native:
        check(native['expected_scope_version'] == versions.get(iid, 0))
        events[eid] = native; versions[iid] = native['expected_scope_version']+1
        if new_mission:
            mission = deepcopy(payload['mission']); mid = mission['mission_id']
            check(mid == native['mission_id'] and mission['instance_id'] == iid and mid not in missions)
            for obligation in mission.pop('obligations', []):
                oid = obligation['definition']['obligation_id']
                check(oid not in obligations)
                obligations[oid] = obligation
            for grant in mission.pop('retry_grants', []):
                grant.setdefault('max_research_attempts', 1)
                grant.update(authorized_by=eid, source_decision_or_mission_grant=mid,
                    remaining_uses=grant['max_research_attempts'], scope_version=versions[iid])
                grant.setdefault('stop_conditions', ['CONSUMER_SATISFIED','BUDGET_EXHAUSTED','HARD_BLOCKER','PAUSED','CANCELLED'])
                check(grant['grant_id'] not in retries or retries[grant['grant_id']] == grant)
                retries[grant['grant_id']] = grant
            mission.update(status='ACTIVE', stage_visit_ids=[], delivery_ref=None,
                           input_knowledge_commit=event['expected_head'])
            missions[mid] = mission
            expected['mission_ids'].append(mid)
            expected.update(current_mission_id=mid, status='ACTIVE')
            if control is not None:
                control.update(state='RUNNING', automatic_authorization_ref=eid if control['mode']=='AUTO_P14' else None)
                instruction = True
        elif kind in {'PAUSE','RESUME','HUMAN_DECISION'}:
            action = payload['action'] if kind == 'HUMAN_DECISION' else kind
            if action == 'RESUME':
                ref = payload.get('decision_ref'); decision = before['control_events'].get(ref, {})
                check(decision.get('event_type') == 'HUMAN_DECISION' and decision.get('instance_id') == iid and
                      decision.get('mission_id') == current['current_mission_id'] and
                      decision['payload']['action'] == ('CONTINUE_DISCOVERY' if current['kind']=='FDH' else 'CONTINUE'))
                if control is not None:check(control.get('human_continue_ref') == control.get('last_instruction_ref') == ref)
            if action in {'RESUME','CONTINUE','CONTINUE_DISCOVERY'}:
                mission = missions.get(current['current_mission_id'], {})
                check(mission.get('status') == 'ACTIVE' and mission.get('budget_grant_id') in grants)
                if action != 'RESUME':check((action=='CONTINUE_DISCOVERY') == (current['kind']=='FDH'))
                expected['status'] = 'ACTIVE'
                if control is not None:
                    if action != 'RESUME':
                        if control['state'] in waiting:control['round_number'] += 1
                        control.update(stop_request=None, human_continue_ref=eid)
                    control.update(state='RUNNING', pause_reason=None)
            elif action == 'PAUSE':
                expected['status'] = 'PAUSED'
                if control is not None:
                    if control['state'] not in waiting:control['state'] = 'PAUSED'
                    control['pause_reason'] = payload.get('note') if kind=='HUMAN_DECISION' else payload.get('reason')
            else:
                check(action in {'END','END_WITHOUT_ADOPTION'})
                expected['status'] = 'ENDED'
                if control is not None:control['state'] = 'OPEN_ENDED'
            instruction = control is not None
        elif kind in {'SET_P14_MODE','REQUEST_STOP_AT_P14','CANCEL_STOP_AT_P14'}:
            check(current['kind']=='TRH' and current['status'] not in {'ENDED','COMPLETE'})
            if kind == 'SET_P14_MODE':
                check(payload['mode'] in {'AUTO_P14','HUMAN_P14'})
                control.update(mode=payload['mode'], automatic_authorization_ref=eid if payload['mode']=='AUTO_P14' else None)
            elif kind == 'REQUEST_STOP_AT_P14':
                old_stop = control.get('stop_request')
                if not old_stop or old_stop['status'] not in {'PENDING','REACHED'}:
                    control['stop_request'] = dict(requested_at=payload['requested_at'], requested_round=control['round_number'],
                        status='REACHED' if control['state']=='WAITING_HUMAN_AT_P14' else 'PENDING', event_ref=eid)
            elif control.get('stop_request'):
                control['stop_request'].update(status='CANCELLED', cancel_event_ref=eid)
            instruction = True
        else:
            check(kind in {'AUTHORIZE_MISSION','EXTEND_MISSION_BUDGET'})
    if control is not None:
        control['control_version'] = current_version(current)+1
        if instruction:control.update(last_instruction_ref=eid, last_instruction_at=at)
    else:expected['infrastructure_control_version'] = current_version(current)+1
    check(after['instances'][iid] == expected and after['missions'] == missions and
          after['obligations'] == obligations and after['retry_grants'] == retries and
          after['control_events'] == events and after['scope_versions'] == versions, 'CAPABILITY_VIOLATION')


def validate_transition(before, after, event):
    """Enforce monotonic identity, phase, evidence and version relationships."""
    iid = event['scope']['instance_id']; action = event['type']
    from .journal import _diff, SCIENCE_MAPS, CONTROL_MAPS, EXECUTION_MAPS, REPORT_MAPS
    strategy_maps = set('strategies research_routes strategy_triggers strategy_proposals human_directions main_replies strategy_events consumer_controls live_main_dispatches main_execution_recoveries obligations retry_grants execution_events instances missions visits requests round_accounts round_deliveries main_decisions retired_consumers research_clocks research_audit_events research_checkpoints research_audits research_guidance'.split())
    communication_maps = set('communication_events collaboration_groups research_messages message_acks input_deliveries input_windows communication_impacts communication_links communication_link_revisions'.split())
    survey_maps = set('survey_events survey_search_plans survey_retrievals survey_sources survey_source_status survey_readings survey_coverage survey_reviews survey_snapshots survey_output_plans'.split())
    allowed = {
        'ACTIVATED': {'instances'}, 'OWNER_ACQUIRED': {'instances', 'requests'},
        'CONTROL_APPLIED': CONTROL_MAPS | set('research_clocks research_audit_events research_checkpoints research_audits research_guidance retry_grants'.split()),
        'GRANT_REVOKED': {'budget_grants', 'instances'},
        'CALL_PREPARED': EXECUTION_MAPS,
        'SLOT_CONFIRMED': {'requests'}, 'SEND_STARTED': {'requests'},
        'EXECUTION_RECEIVED': {'requests', 'execution_events', 'review_executions', 'human_directions'},
        'INBOX_PAGE_RECEIVED': {'requests', 'execution_events', 'review_executions', 'human_directions'},
        'CANCEL_UNSENT': {'requests', 'execution_events'},
        'UNKNOWN_DISPOSED': {'requests', 'execution_events'}, 'CANCEL_REQUESTED': {'requests'},
        'SCIENCE_ADMITTED': SCIENCE_MAPS | EXECUTION_MAPS | REPORT_MAPS | strategy_maps | survey_maps | {'blockers', 'candidates'},
        'STRATEGY_APPLIED': strategy_maps,
        'COMMUNICATION_APPLIED': communication_maps,
        'GUIDANCE_SAVED': {'human_directions', 'strategy_events'},
        'GUIDANCE_OBSERVED': {'human_directions'},
    }[action]
    check(set(_diff(before, after)) <= allowed, 'CAPABILITY_VIOLATION')
    if action == 'CONTROL_APPLIED':validate_control_writes(before, after, event)
    check(before['capabilities'] == after['capabilities'])
    for name in ('records', 'tasks', 'captures'):
        check(all(after.get(name, {}).get(key) == value for key, value in before.get(name, {}).items()), 'CAPABILITY_VIOLATION')
    if action != 'CALL_PREPARED':
        check(before['tasks'] == after['tasks'], 'CAPABILITY_VIOLATION')
        check(before['visits'] == after['visits'], 'CAPABILITY_VIOLATION')
        for mid, mission in after['missions'].items():
            check(mission['stage_visit_ids'] == before['missions'].get(mid, {}).get('stage_visit_ids', []), 'CAPABILITY_VIOLATION')
        check(all(mid in after['missions'] for mid in before['missions']), 'CAPABILITY_VIOLATION')
        openings = lambda s: {k:v for k,v in s['execution_events'].items() if v.get('event_type') == 'VISIT_OPENED'}
        check(openings(before) == openings(after), 'CAPABILITY_VIOLATION')
    if action not in {'CONTROL_APPLIED', 'GRANT_REVOKED'}:
        check(before['budget_grants'] == after['budget_grants'], 'CAPABILITY_VIOLATION')
    check(set(before['instances']) == set(after['instances']))
    old = before['instances'][iid]; new = after['instances'][iid]
    for name in ('instance_id','kind','target_ref','discovery_brief_ref','discovery_scope','survey_scope','created_by_decision'):
        check(old.get(name) == new.get(name), 'CAPABILITY_VIOLATION')
    for other in before['instances']:
        if other != iid:
            check(before['instances'][other] == after['instances'][other])
    changes_control = action in {'ACTIVATED', 'OWNER_ACQUIRED', 'CONTROL_APPLIED', 'GRANT_REVOKED'}
    if action == 'SCIENCE_ADMITTED' and current_version(new) != current_version(old):
        # Original captured MAIN P14/D5 admission advances control as part of
        # the scientific transaction. Require its actual accepted disposition.
        proposals = [row for key, row in after['strategy_proposals'].items()
                     if key not in before['strategy_proposals'] and row.get('request_id') == event['payload']['request_id']]
        check(len(proposals) == 1 and proposals[0].get('status') == 'APPLIED' and
              proposals[0]['proposal']['next_action'] in {'DELIVER','P14','COMPLETE'} and
              proposals[0].get('delivery_disposition', {}).get('state') == new['run_control']['state'])
        expected = deepcopy(old); control = expected['run_control']
        disposition = proposals[0]['delivery_disposition']; did = disposition['delivery_id']
        delivery = after['round_deliveries'][did]
        check(did not in before['round_deliveries'] and delivery['instance_id'] == iid and
              delivery['summary']['main_request_id'] == event['payload']['request_id'])
        control.update(last_delivery_ref=did, control_version=current_version(old)+1)
        if old['kind'] == 'FDH':
            expected['status'] = 'PAUSED'
            control.update(state='WAITING_HUMAN_AT_D5', pause_reason='Formal D5 delivery awaits the researcher’s explicit choice.')
        elif control['mode']=='HUMAN_P14' or control.get('stop_request') and control['stop_request']['status'] in {'PENDING','REACHED'}:
            expected['status'] = 'PAUSED'; control['state'] = 'WAITING_HUMAN_AT_P14'
            if control.get('stop_request') and control['stop_request']['status']=='PENDING':
                control['stop_request'].update(status='REACHED', reached_round=control['round_number'], delivery_ref=did)
        else:
            decision = after['main_decisions'][disposition['decision_ref']]
            check(disposition['decision_ref'] not in before['main_decisions'] and
                  decision['request_id'] == event['payload']['request_id'] and decision['delivery_ref'] == did and
                  decision['automatic_authorization_ref'] == control['automatic_authorization_ref'] and
                  decision['action'] == proposals[0]['proposal']['p14_decision']['action'])
            control['last_decision_ref'] = disposition['decision_ref']
            if decision['action']=='COMPLETE':expected['status']='COMPLETE'; control['state']='COMPLETE'
            elif decision['action']=='CONTINUE':control['round_number']+=1; control['state']='RUNNING'
            else:check(decision['action']=='WAIT'); control['state']='WAITING_CONDITION'
        check(new == expected, 'CAPABILITY_VIOLATION')
        changes_control = True
    check(current_version(new) == current_version(old) + int(changes_control))
    if action == 'ACTIVATED':
        check('ownership' not in old and new['ownership']['owner_epoch'] == 1 and new['status'] == 'PAUSED')
    else:
        check(event['owner_epoch'] == old['ownership']['owner_epoch'] and event['control_version'] == current_version(old))
        check(new['ownership']['owner_epoch'] == old['ownership']['owner_epoch'] + int(action == 'OWNER_ACQUIRED'))
        if action != 'OWNER_ACQUIRED':
            check(new['ownership'] == old['ownership'])
    if action in {'ACTIVATED','OWNER_ACQUIRED'}:
        expected = deepcopy(old)
        expected['ownership'] = deepcopy(new['ownership'])
        if old['kind'] == 'SURVEY':expected['infrastructure_control_version'] = current_version(old)+1
        else:expected['run_control']['control_version'] = current_version(old)+1
        check(new == expected)
        check(new['ownership']['authorization_ref'] == event['decision_ref'] and
              new['ownership']['owner_id'] == event['payload']['owner_id'] and
              new['ownership']['backend_binding_ref'] == event['payload']['backend_binding_ref'])
    if action != 'CALL_PREPARED':
        check(set(before['requests']) == set(after['requests']))
    if action == 'GRANT_REVOKED':
        gid=event['payload']['budget_grant_id'];expected=deepcopy(before['budget_grants'])
        expected[gid].update(grant_status='REVOKED',grant_revision=expected[gid]['grant_revision']+1,
                             authorization_ref=event['decision_ref'])
        check(after['budget_grants']==expected)
        expected_instance = deepcopy(old)
        if old['kind']=='SURVEY':expected_instance['infrastructure_control_version'] += 1
        else:expected_instance['run_control']['control_version'] += 1
        check(new == expected_instance, 'CAPABILITY_VIOLATION')
    elif action not in {'ACTIVATED','OWNER_ACQUIRED','CONTROL_APPLIED'} and not changes_control:
        check(new == old, 'CAPABILITY_VIOLATION')
    for gid,grant in after['budget_grants'].items():
        previous=before['budget_grants'].get(gid)
        if previous != grant:
            check(grant['authorization_ref']==event['decision_ref'])
            check(grant['grant_revision']==(previous['grant_revision']+1 if previous else 1))
            if previous:
                check(all(grant[k]==previous[k] for k in ('budget_grant_id','mission_id','instance_id','budget_unit')))
    for rid, previous in before.get('requests', {}).items():
        check(rid in after['requests'])
        current = after['requests'][rid]
        fixed = {'request_id', 'task_id', 'instance_id', 'mission_id', 'execution_id', 'purpose_key',
                 'responsibility_key', 'attempt_group_key', 'attempt_key', 'sample_slot', 'input_fingerprint',
                 'budget_grant_id', 'reserved_calls', 'execution_kind'}
        check(all(previous.get(k) == current.get(k) for k in fixed))
        if action in {'SEND_STARTED', 'SLOT_CONFIRMED'}:
            mutable_request = {'admission'} | ({'execution_state'} if action == 'SEND_STARTED' else set())
            check({k: v for k, v in previous.items() if k not in mutable_request} ==
                  {k: v for k, v in current.items() if k not in mutable_request})
        a, b = previous['admission'], current['admission']
        if action in {'SLOT_CONFIRMED','SEND_STARTED'}:
            expected=deepcopy(previous)
            if rid == event['payload']['request_id']:
                if action=='SLOT_CONFIRMED':
                    check(a['send_phase']=='READY' and a['slot_token'] in (None,event['payload']['token']))
                    expected['admission']['slot_token']=event['payload']['token']
                else:
                    check(a['send_phase']=='READY' and a['send_boundary_id'] is None and not previous['fenced'])
                    expected['execution_state']='UNKNOWN'
                    expected['admission'].update(send_phase='ATTEMPTED',send_boundary_id=event['payload']['send_boundary_id'],charge='UNKNOWN_RESERVED')
            check(current==expected)
        if action in {'OWNER_ACQUIRED','CANCEL_REQUESTED'} or (action=='UNKNOWN_DISPOSED' and event['payload']['disposition']=='ABANDON_UNKNOWN'):
            expected=deepcopy(previous)
            affected=(after['tasks'][previous['task_id']].get('actor_kind')=='MAIN' if action=='OWNER_ACQUIRED'
                      else rid==event['payload']['request_id'])
            if affected:expected['fenced']=True
            check(current==expected)
        if action in {'CONTROL_APPLIED','GRANT_REVOKED','STRATEGY_APPLIED','COMMUNICATION_APPLIED','GUIDANCE_SAVED','GUIDANCE_OBSERVED'}:
            check(a==b and previous['execution_inbox']==current['execution_inbox'])
        mutable = {'send_phase', 'slot_token', 'send_boundary_id', 'charge', 'receipt_ids',
                   'not_sent_ref', 'termination_ref', 'evidence_conflict'}
        check({k: v for k, v in a.items() if k not in mutable} == {k: v for k, v in b.items() if k not in mutable})
        check({'READY': 0, 'ATTEMPTED': 1, 'CLOSED': 2}[b['send_phase']] >= {'READY': 0, 'ATTEMPTED': 1, 'CLOSED': 2}[a['send_phase']])
        check(not a['evidence_conflict'] or b['evidence_conflict'])
        if b['charge']=='RELEASED' and a['charge']!='RELEASED':
            check(current['execution_inbox']['state']=='OPEN' and b['not_sent_ref'] is not None)
        for name in ('not_sent_ref', 'termination_ref', 'slot_token', 'send_boundary_id'):
            check(a[name] is None or a[name] == b[name])
        check(b['receipt_ids'][:len(a['receipt_ids'])] == a['receipt_ids'])
        check(current['execution_inbox']['cursor']['after_sequence'] >= previous['execution_inbox']['cursor']['after_sequence'])
        for name in ('producer_ref', 'binding_ref'):
            check(previous['execution_inbox'][name] == current['execution_inbox'][name])
    validate_state(after)


def validate_prefix(store, history):
    """Verify the closed native prefix without importing writer/runtime code."""
    from .journal import _apply_delta
    from .native_format import COMMIT_SCHEMA, DEFAULT
    from pmrh.domain.protocols import validate_discovery_scope
    check(2 <= len(history) <= 5, 'SETUP_PREFIX_INVALID')
    state = {}
    source_order = []
    for position, (head, entry) in enumerate(history):
        check(entry['schema'] == COMMIT_SCHEMA, 'SETUP_PREFIX_INVALID')
        events = [e for e in entry['events'] if e.get('type') != 'CHECKPOINT']
        check(len(events) == 1, 'SETUP_PREFIX_INVALID')
        event = events[0]; before = deepcopy(state)
        for name in ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref'):
            if entry[name]:
                _apply_delta(state, loads(store.read_blob(entry[name])))
        check(state.get('synthetic_test_only') is True)
        if position == 0:
            check(event == {'type': 'PROJECT_CREATED', 'model_calls': 0})
            check(set(state) == GENESIS_FIELDS, 'SETUP_PREFIX_INVALID')
            check(state['project_budget'] == {'max_calls': 0} and state['max_workers'] == 8)
            check(state['capabilities'] == {
                'CAP-HUMAN': {'actor': 'human', 'actions': ['*'], 'instance_ids': ['*']},
                'CAP-HOST': {'actor': 'host', 'actions': ['*'], 'instance_ids': ['*']}})
            check(state['scope_versions'] == {'project': 0} and state['language_policy'] == DEFAULT)
            check(state['usage'] == {'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0})
            exempt = {'schema', 'project_id', 'title', 'versions', 'language_policy', 'synthetic_test_only',
                      'project_budget', 'max_workers', 'capabilities', 'scope_versions', 'usage'}
            check(all(v in ({}, []) for k, v in state.items() if k not in exempt))
        elif position == len(history)-1:
            check(event.get('event_type') == 'CREATE_INSTANCE' and len(state['instances']) == 1)
            instance = next(iter(state['instances'].values()))
            check(event['payload'] == {'instance': instance} and instance['status'] == 'PAUSED')
            check(not instance['mission_ids'] and instance['current_mission_id'] is None)
            check(instance['input_knowledge_commit'] == entry['previous_commit']['commit'])
            check(not (set(state) - set(before)))
            check(all(before[k] == v for k, v in state.items() if k not in {'instances', 'control_events', 'scope_versions'}))
            if instance['kind'] == 'TRH':
                check(len(source_order) == 1 and source_order[0]['purpose'] == 'PROBLEM')
                check(instance['target_ref'] == source_order[0]['target_ref'] and len(state['records']) == 1)
            elif instance['kind'] == 'FDH':
                check(len(source_order) == 3 and all(e['purpose'] == 'PHENOMENON' for e in source_order))
                check(not state['records'] and instance['target_ref'] is None)
                expected = dict(zip(('phenomenon_ref', 'immutable_background_ref', 'allowed_axes_ref'),
                                    (e['source_ref'] for e in source_order)))
                check(instance['discovery_scope'] == expected and instance['discovery_brief_ref'] == expected['phenomenon_ref'])
                validate_discovery_scope(state, instance)
            else:
                check(instance['kind'] == 'SURVEY' and not source_order and not state['records'])
                survey = instance['survey_scope']
                check(not survey['source_refs'] and not survey['selected_refs'] and survey['parent_instance_id'] is None)
                check('run_control' not in instance)
        else:
            check(event.get('kind') == 'ORIGINAL_SOURCE_RECEIVED')
            fields(event, 'kind source_ref target_ref purpose')
            check(event['purpose'] in {'PROBLEM', 'PHENOMENON'})
            source_order.append(event)
            source = state['sources'][event['source_ref']]
            check(source['bytes'] > 0 and store.read_blob(source['blob_hash']).strip())
            check(source['origin']['kind'] == 'USER_INPUT' and source['access_class'] == 'SCIENTIFIC_SOURCE')
            check(len(state['sources']) == len(source_order))
            for production in state['production_events'].values():
                check(production['authorship'] == 'SOURCE_PRESERVED' and production['task_id'] is None)
            check(all(before[k] == v for k, v in state.items() if k not in
                      {'sources', 'records', 'objects', 'production_events', 'knowledge_changes'}))
        check(not any(state[k] for k in ('missions', 'tasks', 'requests', 'budget_grants', 'captures', 'strategies')))
    return state


def scan(store, history, apply_delta, *, combined=False):
    """Replay the actual complete HEAD ancestry; never trust an as-of shortcut."""
    from .io import _ConfinedReader
    schema = SCHEMA
    if combined:
        from .control_fast import SCHEMA as schema
    if not any(entry['schema'] == schema for _, entry in history):
        return None
    if store._reader is None:
        with _ConfinedReader(store.root) as reader:
            from .journal import Journal
            confined = Journal(reader.root, reader=reader)
            check(confined.history() == history)
            return scan(confined, history, apply_delta, combined=combined)
    from pmrh.ports.dto.wire import _decode_dto

    def copy_snapshot(value, memo):
        # Replay states are JSON graphs. Keep every mutable snapshot detached,
        # with one fresh memo per snapshot; no cross-state structural sharing.
        kind = type(value)
        if kind in (str, int, float, bool, type(None)):
            return value
        key = id(value)
        if key in memo:
            return memo[key]
        if kind is dict:
            result = {}; memo[key] = result
            for name, item in value.items():
                result[name if type(name) is str else deepcopy(name, memo)] = copy_snapshot(item, memo)
            return result
        if kind is list:
            result = []; memo[key] = result
            result.extend(copy_snapshot(item, memo) for item in value)
            return result
        return deepcopy(value, memo)

    checked_json = set()
    def read_scan_json(wire):
        # Reads and debits are never cached. Reparse even a hit so no mutable
        # JSON container is shared with another caller or historical state.
        raw = read_ref(store, wire, index.project)
        value = loads(raw, maximum=MAX_JSON_BYTES)
        if raw not in checked_json:
            check(canonical(value) == raw)
            _wire_budget(value, wire=True)
            checked_json.add(raw)
        return value

    first = next(i for i, (_, entry) in enumerate(history) if entry['schema'] == schema)
    state = validate_prefix(store, history[:first])
    index = ControlIndex(state['project_id'])
    index.states = {}
    prefix_state = {}
    for prefix_head, prefix_entry in history[:first]:
        for name in ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref'):
            if prefix_entry[name]:
                apply_delta(prefix_state, loads(store.read_blob(prefix_entry[name])))
        index.states[prefix_head['commit']] = copy_snapshot(prefix_state, {})
    replay_prior_commit = history[first-1][0]['commit']

    raw_fields=frozenset('raw_output_ref raw_event_ref raw_event_refs raw_evidence_ref raw_evidence_refs evidence_refs request_evidence_refs termination_evidence_refs test_receipt_refs principal_ref authn_evidence_ref authority_ref producer_ref binding_ref backend_binding_ref runner_binding_ref reason_ref takeover_evidence_refs endpoint_ref credential_ref capture_ref'.split())
    closure_sizes={}
    parsed_closure=set()
    # These facts live only for this complete scan and its actual reader. A
    # first safe read authenticates each immutable native object; every replay
    # state still has to match the exact authenticated record. No authority or
    # mutable checkpoint is cached, and new digests consume the same budget.
    native_records={}
    native_blobs=set()
    # Only pure decoded values are reused within this scan; reads stay fresh.
    specs_by_raw={}
    # A cached ExactRef is pure metadata, never closure/authority evidence.
    # Add at most one signature per actual successful closure byte read.
    checked_refs={}
    ref_names=('schema_version', 'dto_type', 'project_id', 'object_id', 'revision', 'sha256')
    def native_blob(digest):
        if digest not in native_blobs:
            store.read_blob(digest)
            native_blobs.add(digest)
    def closure(value, iid, raw_reference=False):
        if isinstance(value, dict):
            if value.get('dto_type') == 'ExactRef':
                signature = (tuple(value[name] for name in ref_names)
                    if type(value) is dict and len(value) == len(ref_names) and
                    all(type(value.get(name)) is str for name in ref_names) else None)
                known = checked_refs.get(signature) if signature is not None else None
                if known is None:
                    r = ref(value, index.project)
                    key = canonical(value)
                else:
                    r, key = known
                check(index.refs.get(key, iid) == iid, 'AUTHORIZATION_REQUIRED')
                index.refs[key] = iid
                if r.sha256 in index.closure:
                    if raw_reference:check(closure_sizes[r.sha256]<=1024**2,'RESOURCE_LIMIT')
                    if raw_reference or r.sha256 in parsed_closure:return
                index.closure.add(r.sha256)
                raw = store._read_blob(r.sha256, 1024**2 if raw_reference else MAX_JSON_BYTES)
                if signature is not None and known is None:
                    checked_refs[signature] = (r, key)
                closure_sizes[r.sha256]=len(raw)
                if raw_reference:return
                parsed_closure.add(r.sha256)
                try:
                    parsed = loads(raw, maximum=MAX_JSON_BYTES)
                except PMRSError as exc:
                    check(exc.code == 'JSON_INVALID', exc.code)
                    check(len(raw) <= 1024**2, 'RESOURCE_LIMIT')
                    return
                # Reference closure is evidence reachability, never a callable
                # decoder or a grant of the authority described in those bytes.
                _wire_budget(parsed,wire=True)
                closure(parsed, iid)
            else:
                for key,item in value.items():
                    closure(item, iid, key in raw_fields)
        elif isinstance(value, list):
            check(len(value) <= MAX_ITEMS, 'RESOURCE_LIMIT')
            for item in value:
                closure(item, iid, raw_reference)

    for head, entry in history[first:]:
        validate_entry(entry, combined=combined)
        event = next(e for e in entry['events'] if e.get('type') != 'CHECKPOINT')
        before = index.states[replay_prior_commit]
        for name in ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref'):
            if entry[name]:
                apply_delta(state, loads(store.read_blob(entry[name])))
        check(event['scope']['project_id'] == index.project)
        iid = event['scope']['instance_id']
        check(iid in before['instances'])
        action = event['type']; p = event['payload']
        if index.profile is None:
            check(action == 'ACTIVATED' and event['owner_epoch'] == event['control_version'] == 0)
            profile = read_scan_json(p['profile_ref'])
            if combined:
                from .control_fast import unwrap_profile
                profile = unwrap_profile(profile)
            validate_record(profile)
            check(profile['kind'] == 'PROFILE' and profile['project_id'] == index.project)
            check(profile['genesis_commit'] == history[0][0]['commit'] and profile['setup_head'] == history[first-1][0]['commit'])
            index.profile = profile
        else:
            check(action != 'ACTIVATED')
        closure(event, iid)
        # Native scientific and frozen-input bytes share the same bounded
        # reader budget; new DTO refs cannot hide the underlying native closure.
        for reference in state.get('records', {}):
            if reference not in native_records:
                record=store.read_record(reference)
                native_records[reference]=record
                native_blobs.add(record['body_sha256'])
            check(native_records[reference] == state['records'][reference])
        for source in state.get('sources', {}).values():
            native_blob(source['blob_hash'])
        for obligation in state.get('obligations', {}).values():
            native_blob(obligation['definition']['criterion_body_ref'])
        for task in state.get('tasks', {}).values():
            for field_name in ('input_packet_ref', 'model_packet_ref', 'prompt_ref'):
                if task.get(field_name):
                    native_blob(task[field_name])
        for request in state.get('requests', {}).values():
            if request.get('capture_ref'):
                native_blob(request['capture_ref'])
        decision = read_scan_json(event['decision_ref']); validate_record(decision, combined=combined)
        check(decision['kind'] == 'DECISION' and decision['action'] == action and decision['scope'] == event['scope'])
        bare = {k: v for k, v in event.items() if k != 'decision_ref'}
        check(decision['payload_sha256'] == sha(canonical(bare)))
        check((decision['owner_epoch'], decision['control_version']) == (event['owner_epoch'], event['control_version']))
        check(event['operation_id'] not in index.operations and event['idempotency_key'] not in index.keys)
        if combined and action.startswith('FAST_'):
            from .fastmath import validate_effects
            validate_effects(store, before, state, event, decision)
        else:
            validate_transition(before, state, event)
        if action == 'SCIENCE_ADMITTED':
            if combined:
                from .control_fast import validate_rejection
                validate_rejection(store,before,state,event,decision,entry['accepted_request_bindings'])
            original = before['requests'][p['request_id']]
            check(p['capture_ref']['sha256'] == original.get('capture_ref') and
                  not original['fenced'] and not original['admission']['evidence_conflict'] and
                  original['execution_inbox']['state'] == 'OPEN')
            task = before['tasks'][original['task_id']]
            instance = before['instances'][iid]
            if task.get('actor_kind') == 'MAIN':
                check(instance['status'] == 'ACTIVE' and original['admission']['owner_epoch'] == instance['ownership']['owner_epoch'])
                captured = loads(read_ref(store,p['capture_ref'],index.project,maximum=1024**2))
                authored = captured['payload'].get('knowledge_change',captured['payload'])
                proposals = [row for key,row in state['strategy_proposals'].items() if key not in before['strategy_proposals']]
                for proposal in proposals:
                    check(proposal['request_id'] == original['request_id'] and
                          proposal['proposal']['next_action'] == authored['strategy_proposal']['next_action'] and
                          (proposal['proposal'].get('p14_decision') or {}).get('action') ==
                          (authored['strategy_proposal'].get('p14_decision') or {}).get('action'))
        for instance in state['instances'].values():closure(instance['ownership'], iid)
        for grant in state['budget_grants'].values():closure(grant['authorization_ref'], iid)
        for direction in state['human_directions'].values():closure(direction['provenance'], iid)
        for request in state['requests'].values():
            call = request['admission']
            closure(call, iid);closure(request['execution_inbox'], iid)
            spec_raw = read_ref(store, call['spec_ref'], index.project)
            spec = specs_by_raw.get(spec_raw)
            if spec is None:
                spec_wire = loads(spec_raw, maximum=MAX_JSON_BYTES)
                check(canonical(spec_wire) == spec_raw)
                _wire_budget(spec_wire, wire=True)
                spec = _decode_dto(S.AgentInvocationSpec, spec_wire)
                specs_by_raw[spec_raw] = spec
            reservation = read_scan_json(call['reservation_ref']); validate_record(reservation)
            check(reservation['kind'] == 'RESERVATION' and reservation['identity'] == spec.identity().to_wire())
            check(reservation['grant_ref'] == spec.budget_grant_ref.to_wire() and spec.reservation_ref.to_wire() == call['reservation_ref'])
            check((call['owner_epoch'], call['control_version']) == (spec.owner_epoch, spec.expected_control_version) ==
                  (reservation['owner_epoch'], reservation['control_version']))
            check((request['request_id'], request['execution_id'], request['instance_id']) ==
                  (spec.request_id, spec.execution_id, spec.instance_id))
            check(call['invocation_id'] == spec.invocation_id and call['attempt_id'] == spec.attempt_id and call['logical_agent_id'] == spec.logical_agent_id)
            check(request['execution_inbox']['binding_ref'] == spec.runner_binding_ref.to_wire())
            task = state['tasks'][request['task_id']]
            check(task['request_id']==request['request_id'] and task['instance_id']==request['instance_id'])
            check(task['attempt_key']==call['attempt_id'] and task['mission_id']==spec.research_goal_id)
            check(spec.purpose==task.get('work_purpose','DEFAULT') and spec.read_set_digest==sha(canonical(task['read_set'])))
            check((spec.role is E.AgentRole.MAIN)==(task.get('actor_kind')=='MAIN'))
            if spec.role is E.AgentRole.MAIN:check(spec.logical_agent_id=='MAIN-'+request['instance_id'])
        if action=='CALL_PREPARED':
            validate_call_effects(store, index, before, state, event, decision)
            task=read_scan_json(p['task_ref']);request=state['requests'][task['request_id']]
            check(state['tasks'][task['task_id']]==task and task['task_id'] not in before['tasks'])
            check(set(state['tasks'])==set(before['tasks'])|{task['task_id']})
            check(set(state['requests'])==set(before['requests'])|{task['request_id']})
            call=request['admission'];inbox=request['execution_inbox']
            check(call['operation_id']==event['operation_id'] and call['idempotency_key']==event['idempotency_key'])
            check(call['spec_ref']==p['spec_ref'] and call['reservation_ref']==p['reservation_ref'])
            check(call['owner_epoch']==event['owner_epoch'] and call['control_version']==event['control_version'])
            check(request['execution_state']=='RESERVED' and call['charge']=='RESERVED' and call['send_phase']=='READY')
            check(call['receipt_ids']==[] and all(call[k] is None for k in ('slot_token','send_boundary_id','not_sent_ref','termination_ref')))
            check(not call['evidence_conflict'] and inbox['state']=='OPEN' and inbox['last_page_ref'] is None and inbox['cursor']['after_sequence']==0)
        if action in {'EXECUTION_RECEIVED','INBOX_PAGE_RECEIVED','CANCEL_UNSENT','UNKNOWN_DISPOSED'}:
            validate_intake_effects(store,index,before,state,event)
        if action == 'EXECUTION_RECEIVED':
            intake_index(index, store, p['receipt'])
        elif action == 'INBOX_PAGE_RECEIVED':
            page = V.RunnerEventPage.from_wire(read_scan_json(p['page_ref']))
            request = state['requests'][p['request_id']]
            previous = before['requests'][p['request_id']]['execution_inbox']['cursor']['after_sequence']
            current = request['execution_inbox']['cursor']['after_sequence']
            if current > previous:
                check(page.requested_cursor.after_sequence == previous and page.next_cursor.after_sequence == current)
                for observed in page.events:
                    receipt = runner_receipt(store, request, observed, index.project)
                    intake_index(index, store, receipt)
                    stream = index.streams.setdefault(p['request_id'], {})
                    check(observed.sequence not in stream)
                    stream[observed.sequence] = (observed.envelope.event_id, observed.wire_digest())
        receipt = dict(commit=head['commit'], sequence=head['sequence'], outcome='COMMITTED', operation_id=event['operation_id'])
        if combined and action.startswith('FAST_'):
            from .fastmath import receipt_for
            receipt = receipt_for(state, event, head)
        index.operations[event['operation_id']] = dict(command=bare, receipt=receipt, decision=decision)
        index.keys[event['idempotency_key']] = event['operation_id']
        index.states[head['commit']] = copy_snapshot(state, {})
        replay_prior_commit = head['commit']
    return index


def validate_intake_effects(store, index, before, after, event):
    """Check durable cursor and liability against the original typed evidence.

    No native reducer, backend or caller callback is imported by a reader.
    Native capture bookkeeping remains native; the admission consequences must
    nevertheless be exactly supported by the retained original receipts.
    """
    p=event['payload']; action=event['type']; project=before['project_id']
    rid=p['receipt']['identity']['request_id'] if action=='EXECUTION_RECEIVED' else p['request_id']
    old=before['requests'][rid]; new=after['requests'][rid]
    inbox=deepcopy(old['execution_inbox']); call=deepcopy(old['admission']); wrappers=[]
    fold=True
    if action=='EXECUTION_RECEIVED':wrappers=[p['receipt']]
    elif action=='INBOX_PAGE_RECEIVED':
        page=V.RunnerEventPage.from_wire(read_json(store,p['page_ref'],project))
        durable=V.EventCursor.from_wire(inbox['cursor']); stream=index.streams.get(rid,{})
        check(p['producer_ref']==inbox['producer_ref'] and p['binding_ref']==inbox['binding_ref'])
        check(page.requested_cursor.scope==durable.scope and page.requested_cursor.stream_id==durable.stream_id)
        check(set(page.duplicate_event_ids)<={item[0] for item in stream.values()})
        for observed in page.events:
            envelope=observed.envelope
            check(envelope.status is E.EventStatus.OBSERVATION and envelope.actor_kind=='SYNTHETIC' and
                  envelope.classification is E.Classification.SYNTHETIC_TEST_ONLY and envelope.trust_origin is E.TrustOrigin.SYNTHETIC_TEST_ONLY)
            check(envelope.actor_principal_ref.to_wire()==inbox['producer_ref'] and envelope.backend_binding_ref.to_wire()==inbox['binding_ref'])
            check((envelope.owner_epoch,envelope.control_version)==(call['owner_epoch'],call['control_version']))
            check((envelope.request_id,envelope.execution_id,envelope.invocation_id,envelope.attempt_id)==
                  (rid,old['execution_id'],call['invocation_id'],call['attempt_id']))
            check(envelope.payload_sha256==envelope.payload_ref.sha256)
            for seq,(eid,digest_value) in stream.items():
                if eid==envelope.event_id:check(seq==observed.sequence and digest_value==observed.wire_digest())
        start=page.requested_cursor.after_sequence; cursor=durable.after_sequence
        if page.status is E.PageStatus.EMPTY:
            check(page.requested_cursor==durable); fold=False
        elif start<cursor:
            check(page.status is E.PageStatus.COMPLETE and page.next_cursor.after_sequence<=cursor)
            check(all(stream.get(item.sequence)==(item.envelope.event_id,item.wire_digest()) for item in page.events)); fold=False
        elif start>cursor or page.status is E.PageStatus.GAP:
            if start>cursor:
                check(page.status is E.PageStatus.COMPLETE)
                gap=V.EventGap(first_missing_sequence=cursor+1,last_missing_sequence=start,reason=E.GapReason.DISCONTINUITY,resnapshot_ref=None)
            else:
                check(page.requested_cursor==durable and page.gap.first_missing_sequence==cursor+1); gap=page.gap
            if inbox['gap'] and inbox['gap']['last_missing_sequence']>gap.last_missing_sequence:
                gap=V.EventGap.from_wire(inbox['gap'])
            inbox.update(state='GAP',gap=gap.to_wire(),last_page_ref=p['page_ref']); fold=False
        else:
            check(page.requested_cursor==durable)
            wrappers=[runner_receipt(store,old,item,project) for item in page.events]
            inbox.update(cursor=page.next_cursor.to_wire(),last_page_ref=p['page_ref'])
            if inbox['gap'] and page.next_cursor.after_sequence<inbox['gap']['last_missing_sequence']:
                inbox['gap']=V.EventGap(first_missing_sequence=page.next_cursor.after_sequence+1,
                    last_missing_sequence=inbox['gap']['last_missing_sequence'],reason=E.GapReason.DISCONTINUITY,resnapshot_ref=None).to_wire()
            else:inbox.update(state='OPEN',gap=None)
    else:
        reference=p.get('not_sent_evidence_ref') if action=='CANCEL_UNSENT' else (p['evidence_refs'][0] if p['disposition']=='CONFIRMED_NOT_SENT' else None)
        if reference is None:return
        receipt=X.DispatchReceipt.from_wire(read_json(store,reference,project))
        check(receipt.status is E.DispatchState.NOT_SENT)
        wrappers=[record('RECEIPT',receipt_id='not-sent:'+event['operation_id'],identity=receipt.handle.identity.to_wire(),
            binding_ref=inbox['binding_ref'],producer_ref=inbox['producer_ref'],receipt_kind='DISPATCH',receipt_ref=reference)]
    check(new['execution_inbox']==inbox)
    for wrapper in wrappers:
        validate_record(wrapper)
        check(wrapper['identity']==S.AgentInvocationSpec.from_wire(read_json(store,call['spec_ref'],project)).identity().to_wire())
        check(wrapper['producer_ref']==inbox['producer_ref'] and wrapper['binding_ref']==inbox['binding_ref'])
        key=wrapper['receipt_id']
        check(before['execution_events'].get(key,wrapper)==wrapper and after['execution_events'].get(key)==wrapper)
        if key not in call['receipt_ids']:call['receipt_ids'].append(key)
    execution=old['execution_state']; fenced=old['fenced']; capture_ref=old.get('capture_ref'); acceptance=old['acceptance_state']
    if fold:
        executed=False; not_sent=None; terminal=None; capture=None
        for key in call['receipt_ids']:
            wrapper=after['execution_events'][key]
            receipt=RECEIPT_TYPES[wrapper['receipt_kind']].from_wire(read_json(store,wrapper['receipt_ref'],project))
            if isinstance(receipt,X.DispatchReceipt):
                executed |= receipt.status is E.DispatchState.SENT
                if receipt.status is E.DispatchState.NOT_SENT:not_sent=not_sent or wrapper['receipt_ref']
            elif isinstance(receipt,X.ExecutionObservation):
                executed |= receipt.state in {E.ExecutionState.SENT,E.ExecutionState.RUNNING,E.ExecutionState.TERMINATED}
                if receipt.state is E.ExecutionState.TERMINATED:terminal=terminal or wrapper['receipt_ref']
            elif isinstance(receipt,X.CancellationReceipt) and receipt.termination is E.ObservationKind.OBSERVED:
                executed=True; terminal=terminal or wrapper['receipt_ref']
            elif isinstance(receipt,X.CaptureReceipt):
                executed=True
                check(capture is None or capture.raw_output_ref==receipt.raw_output_ref)
                capture=capture or receipt
        call['not_sent_ref']=call['not_sent_ref'] or not_sent; call['termination_ref']=call['termination_ref'] or terminal
        call['evidence_conflict'] |= executed and (not_sent is not None or call['send_boundary_id'] is None)
        if call['evidence_conflict']:
            call.update(send_phase='CLOSED',charge='SPENT_OR_SETTLED'); fenced=True
            if execution not in {'CAPTURED','SETTLED'}:execution='UNKNOWN'
        elif inbox['state']!='GAP':
            if executed:
                call['charge']='SPENT_OR_SETTLED'
                if execution not in {'CAPTURED','SETTLED'} and (not terminal or capture):execution='SENT'
            if capture and not capture_ref:
                capture_ref=capture.raw_output_ref.sha256; execution='CAPTURED'; acceptance='PENDING'
            if terminal:
                call.update(send_phase='CLOSED',charge='SPENT_OR_SETTLED')
                if not capture_ref or before['tasks'][old['task_id']].get('actor_kind')=='MAIN' and call['owner_epoch']!=before['instances'][old['instance_id']]['ownership']['owner_epoch']:fenced=True
            if not_sent:
                call.update(send_phase='CLOSED',charge='RELEASED'); execution='CANCELLED_BEFORE_SEND'; acceptance='NOT_SUBMITTED'; fenced=True
    check(new['admission']==call and new['execution_state']==execution and new['fenced']==fenced and
          new.get('capture_ref')==capture_ref and new['acceptance_state']==acceptance,'CAPABILITY_VIOLATION')
    for other,request in before['requests'].items():
        if other!=rid:check(after['requests'][other]==request)


def intake_index(index, store, receipt):
    validate_record(receipt)
    raw = read_ref(store, receipt['receipt_ref'], index.project)
    parsed = RECEIPT_TYPES[receipt['receipt_kind']].from_json(raw.decode('utf-8'))
    identity = parsed.handle.identity if isinstance(parsed, X.DispatchReceipt) else parsed.identity
    check(identity.to_wire() == receipt['identity'])
    key = receipt['receipt_id']
    check(key not in index.receipts or index.receipts[key] == receipt, 'IDEMPOTENCY_CONFLICT')
    index.receipts[key] = deepcopy(receipt)
    return parsed


def runner_receipt(store, request, observed, project):
    envelope = observed.envelope
    mapping = {'STARTED': ('OBSERVATION', X.ExecutionObservation),
               'OUTPUT_AVAILABLE': ('CAPTURE', X.CaptureReceipt),
               'TERMINATED': ('OBSERVATION', X.ExecutionObservation),
               'USAGE': ('USAGE', X.UsageObservation)}
    check(observed.kind.value in mapping, 'UNTRUSTED_EVENT')
    kind, cls = mapping[observed.kind.value]
    payload = cls.from_wire(read_json(store, envelope.payload_ref.to_wire(), project))
    if observed.kind.value == 'STARTED':
        check(payload.state.value in {'SENT', 'RUNNING'})
    elif observed.kind.value == 'TERMINATED':
        check(payload.state.value == 'TERMINATED')
    return record('RECEIPT', receipt_id=envelope.event_id, identity=payload.identity.to_wire(),
                  binding_ref=request['execution_inbox']['binding_ref'], producer_ref=request['execution_inbox']['producer_ref'],
                  receipt_kind=kind, receipt_ref=envelope.payload_ref.to_wire())


class ControlStorage:
    """One native writer, one static bridge, and original operation recovery."""
    validate_command = staticmethod(command)
    validate_transition = staticmethod(validate_transition)
    event_schema = EVENT_SCHEMA
    combined = False

    def decision_record(self, **values):
        result = {'schema': RECORD_SCHEMA, 'kind': 'DECISION', **values}
        validate_record(result, combined=self.combined)
        return result

    def __init__(self, store, native):
        check(native.store is store, 'AUTHORIZATION_REQUIRED')
        self.store = store
        self.native = native
        self.boundaries = {}

    def register_boundary(self, boundary, scope):
        """Trusted fixture assembly; commands cannot register/select callbacks."""
        check(callable(getattr(boundary, 'first_effect', None)), 'UNSUPPORTED_CAPABILITY')
        self.boundaries[boundary] = deepcopy(scope)

    def command_request(self, value):
        p = value['payload']
        if 'request_id' in p:
            return p['request_id']
        if 'receipt' in p:
            return p['receipt']['identity']['request_id']
        if 'native_event' in p:
            native = p['native_event']['payload']
            return native.get('request_id', native.get('sender_request_id'))
        if 'spec_ref' in p:
            return read_json(self.store, p['spec_ref'], value['scope']['project_id'])['request_id']
        if 'steering_receipt_ref' in p:
            return X.SteeringReceipt.from_wire(read_json(self.store, p['steering_receipt_ref'],
                value['scope']['project_id'])).identity.request_id
        return None

    def _root(self, service, scope_value):
        check(service.pool.roots[service.binding_id].verify() == self.store.root.resolve(), 'AUTHORIZATION_REQUIRED')
        history = self.store.history()
        project = self.store._marker()['project_id']
        check(scope_value['project_id'] == project)
        genesis = history[0][0]['commit']
        key = sha(canonical([project, genesis]))
        registered = service.pool.read()['projects'].get(key)
        check(registered == dict(project_id=project, genesis_commit=genesis, root_binding_id=service.binding_id), 'AUTHORIZATION_REQUIRED')
        return project, genesis, key

    def _authorize(self, service, value, session, state, grant_ref, manifest_ref):
        iid = value['scope']['instance_id']; action = value['type']; p = value['payload']
        rid = self.command_request(value)
        if action == 'COMMUNICATION_APPLIED' and p['native_event']['event_type'] == 'COLLAB_GROUP_BOUND':
            rid = service.registry.acting_request(session)
            check(rid is not None, 'AUTHORIZATION_REQUIRED')
        auth = service.registry.authenticate_current(session, action, value['scope'], service.binding_id, request_id=rid)
        instance = state['instances'][iid]
        if action == 'ACTIVATED':
            check(value['owner_epoch'] == value['control_version'] == 0 and 'ownership' not in instance)
        else:
            check(value['owner_epoch'] == instance['ownership']['owner_epoch'] and
                  value['control_version'] == current_version(instance), 'STALE_CONTROL_VERSION')
        request = state['requests'].get(rid)
        if rid is not None and action!='CALL_PREPARED':check(request is not None,'REQUEST_UNKNOWN')
        spec = None
        if action == 'CALL_PREPARED':
            spec = S.AgentInvocationSpec.from_wire(read_json(self.store, p['spec_ref'], state['project_id']))
        elif request is not None:
            check(request['instance_id'] == iid)
            spec = S.AgentInvocationSpec.from_wire(read_json(self.store, request['admission']['spec_ref'], state['project_id']))
        native = p.get('native_event', {})
        subtype = native.get('event_type')
        control_payload = native.get('payload', {})
        requires_grant = action in {'CALL_PREPARED', 'SLOT_CONFIRMED', 'SEND_STARTED', 'STRATEGY_APPLIED'}
        requires_manifest = action in {'CALL_PREPARED', 'SLOT_CONFIRMED', 'SEND_STARTED'}
        delegated = requires_grant
        if action == 'CONTROL_APPLIED':
            requires_grant = subtype in {'EXTEND_MISSION_BUDGET', 'RESUME'} or (
                subtype == 'AUTHORIZE_MISSION' and set(control_payload) == {'future_configuration'}) or (
                subtype == 'HUMAN_DECISION' and control_payload['action'] in {'CONTINUE', 'CONTINUE_DISCOVERY'})
            check(auth['human'])
        elif action == 'GRANT_REVOKED':
            requires_grant = True; check(auth['human'])
        elif action == 'OWNER_ACQUIRED':
            check(auth['human'])
        elif action == 'STRATEGY_APPLIED' and subtype == 'STRATEGY_LIVE_PROPOSAL':
            requires_manifest = True
        elif action == 'COMMUNICATION_APPLIED':
            requires_grant = requires_manifest = delegated = subtype in COMMUNICATION_LIVE
            if subtype=='COLLAB_GROUP_BOUND':
                check(request is not None and (state['tasks'][request['task_id']].get('actor_kind')=='MAIN' or
                      rid in native['payload']['request_ids']), 'AUTHORIZATION_REQUIRED')
        elif action == 'SCIENCE_ADMITTED':
            check(request is not None)
            requires_grant = requires_manifest = delegated = state['tasks'][request['task_id']].get('actor_kind') == 'MAIN'
        if delegated:
            check(auth['owner_id'] == instance['ownership']['owner_id'])
        if action in {'GUIDANCE_SAVED', 'GUIDANCE_OBSERVED', 'STRATEGY_APPLIED'}:
            check(instance['kind'] in {'TRH', 'FDH'}, 'UNSUPPORTED_CAPABILITY')
        if action == 'GUIDANCE_SAVED':
            check(auth['human'] or auth['proposal_only'])
        if requires_grant:
            check(grant_ref is not None)
            historical = read_json(self.store, grant_ref, state['project_id'])
            gid = historical['budget_grant_id']
            grant = state['budget_grants'].get(gid)
            check(grant == historical and grant['instance_id'] == iid, 'AUTHORIZATION_REQUIRED')
            check(action == 'GRANT_REVOKED' or grant['grant_status'] == 'ACTIVE')
            if action == 'GRANT_REVOKED':
                check(gid == p['budget_grant_id'] and grant['grant_revision'] == p['expected_revision'])
            else:
                check(instance['current_mission_id'] == grant['mission_id'])
            if request is not None:
                check(request['budget_grant_id'] == gid)
        else:
            check(grant_ref is None)
        if requires_manifest:
            check(spec is not None and manifest_ref is not None)
            spec_ref = p['spec_ref'] if action == 'CALL_PREPARED' else request['admission']['spec_ref']
            registered = service.registry.manifest(spec_ref)
            check(registered['manifest_ref'] == manifest_ref and registered['binding_ref'] == spec.runner_binding_ref.to_wire())
            check(registered['identity'] == spec.identity().to_wire())
            if request is not None:
                check(manifest_ref==request['admission']['capability_manifest_ref'] and
                      registered['producer_ref']==request['execution_inbox']['producer_ref'], 'AUTHORIZATION_REQUIRED')
            manifest = K.CapabilityManifest.from_wire(read_json(self.store, manifest_ref, state['project_id']))
            check(check_capabilities(manifest, spec.capability_requirements) is None, 'UNSUPPORTED_CAPABILITY')
            check(spec.owner_epoch == instance['ownership']['owner_epoch'] and spec.expected_control_version == current_version(instance), 'STALE_CONTROL_VERSION')
            check(instance['status'] == 'ACTIVE' and spec.instance_id == iid, 'TASK_FENCED')
            if request is not None and action in {'COMMUNICATION_APPLIED', 'STRATEGY_APPLIED'}:
                check(not request['fenced'] and request['execution_state'] in {'SENT', 'UNKNOWN'}, 'TASK_FENCED')
                check(request['execution_inbox']['state'] == 'OPEN' and not request['admission']['evidence_conflict'], 'EXECUTION_UNRESOLVED')
            if spec.role is E.AgentRole.MAIN and instance['ownership']['backend_binding_ref'] is not None:
                check(instance['ownership']['backend_binding_ref'] == spec.runner_binding_ref.to_wire())
        else:
            check(manifest_ref is None)
        if spec is not None:
            check(spec.project_id == state['project_id'] and spec.instance_id == iid)
            reservation = read_json(self.store, spec.reservation_ref.to_wire(), state['project_id'])
            validate_record(reservation)
            check(reservation['kind'] == 'RESERVATION' and reservation['identity'] == spec.identity().to_wire())
            check(reservation['grant_ref'] == spec.budget_grant_ref.to_wire() and reservation['unit'] == spec.budget_unit.value == 'AGENT_INVOCATION')
            original_grant = read_json(self.store, reservation['grant_ref'], state['project_id'])
            check(original_grant['budget_grant_id'] in state['budget_grants'])
            if request is not None:
                check(request['admission']['reservation_ref'] == spec.reservation_ref.to_wire() and
                      original_grant['budget_grant_id'] == request['budget_grant_id'])
        return auth, spec

    def execute(self, service, value, session, grant_ref, manifest_ref, *, boundary=None):
        self.validate_command(value)
        project, genesis, key = self._root(service, value['scope'])
        iid = value['scope']['instance_id']; action = value['type']
        if action == 'SEND_STARTED':
            check(boundary in self.boundaries and self.boundaries[boundary] == value['scope'], 'UNSUPPORTED_CAPABILITY')
        verified = None
        if action == 'CALL_PREPARED':
            # The original freezer can use a physical preparation lease. Never
            # acquire that resource ledger under the egress/pool/project locks.
            snapshot = self.store.read_snapshot()
            self._authorize(service, value, session, snapshot, grant_ref, manifest_ref)
            index = self.store._control_index
            if value['operation_id'] not in index.operations:
                check(value['expected_head'] == snapshot['knowledge_commit'], 'VERSION_CONFLICT')
                verified = self.native._verify_frozen_call(snapshot, value)
                self.store._fault('after_control_freeze')
        with service.pool.egress(project, genesis, [iid]):
            with service.pool.locked():
                self._root(service, value['scope'])
                ledger, snapshots, _, blocked = service.pool.inspect(sending=action in {'CALL_PREPARED', 'SLOT_CONFIRMED', 'SEND_STARTED'})
                with self.store._locked():
                    state = self.store.read_snapshot()
                    check(state['_head'] == snapshots[key]['_head'], 'VERSION_CONFLICT')
                    auth, spec = self._authorize(service, value, session, state, grant_ref, manifest_ref)
                    index = self.store._control_index
                    if index is not None:
                        previous = index.operations.get(value['operation_id'])
                        operation = index.keys.get(value['idempotency_key'])
                        check(operation in (None, value['operation_id']), 'IDEMPOTENCY_CONFLICT')
                        if previous is not None:
                            check(previous['command'] == value, 'IDEMPOTENCY_CONFLICT')
                            # Current auth, versions, grant revision, manifest and
                            # original reservation have all been rechecked above.
                            return dict(previous['receipt'], duplicate=True)
                    check(value['expected_head'] == state['knowledge_commit'], 'VERSION_CONFLICT')
                    if action == 'CALL_PREPARED':
                        check(verified is not None and verified['head'] == state['knowledge_commit'], 'VERSION_CONFLICT')
                        check(verified['command'] == sha(canonical(value)))
                        task = read_json(self.store, value['payload']['task_ref'], project)
                        candidate = read_json(self.store, value['payload']['candidate_ref'], project)
                        check(verified['task'] == sha(canonical(task)) and verified['candidate'] == sha(canonical(candidate)))
                        plan, bound = visit_plan(state, candidate, index.visit_origins)
                        check(plan == verified['plan'] and bound == candidate, 'VERSION_CONFLICT')
                        task_visit_link(state, state['knowledge_commit'], task, candidate, plan)
                    decision_at=auth['issued_at']
                    if self.combined and action=='SCIENCE_ADMITTED':
                        # Bind this transaction's native rejection time in the
                        # existing authenticated decision, not in a new schema.
                        decision_at=service.registry.clock()
                        check(auth['issued_at']<=decision_at<auth['expires_at'],'AUTHORIZATION_REQUIRED')
                    decision = self.decision_record(decision_id='decision:'+value['operation_id'], scope=value['scope'],
                        principal_ref=auth['principal_ref'], authn_evidence_ref=auth['authn_evidence_ref'], authority_ref=auth['authority_ref'],
                        action=action, payload_sha256=sha(canonical(value)), owner_epoch=value['owner_epoch'], control_version=value['control_version'],
                        issued_at=decision_at.isoformat().replace('+00:00', 'Z'), expires_at=auth['expires_at'].isoformat().replace('+00:00', 'Z'),
                        budget_grant_ref=grant_ref, capability_manifest_ref=manifest_ref)
                    decision_ref = exact(self.store, project, decision['decision_id'], decision)
                    event = {**deepcopy(value), 'decision_ref': decision_ref}
                    after, accepted = self.reduce(service, state, event, auth, spec, ledger, key)
                    if after == state:
                        return dict(commit=state['knowledge_commit'], sequence=state['_snapshot_sequence'], outcome='NO_CHANGE')
                    self.validate_transition(state, after, event)
                    if action == 'CALL_PREPARED':
                        validation_index = ControlIndex(project, visit_origins=deepcopy(index.visit_origins))
                        validate_call_effects(self.store, validation_index, state, after, event, decision)
                    self.store._fault('after_blobs')
                    self.store._control_publication = self
                    try:
                        result = self.store._publish(state['_head'], state, after, actor='SYNTHETIC_TEST_ONLY', events=[event], accepted=accepted)
                    finally:
                        self.store._control_publication = None
                    if action == 'ACTIVATED':
                        self.native.setup.used = True
            if action == 'SEND_STARTED':
                # HEAD is UNKNOWN before the actual first effect. Pool/project
                # locks are released, egress stays held through the boundary.
                self.store._fault('before_first_effect')
                service.registry.authenticate_current(session, action, value['scope'], service.binding_id,
                                                       request_id=value['payload']['request_id'])
                service.registry.manifest(after['requests'][value['payload']['request_id']]['admission']['spec_ref'])
                boundary.first_effect()
                self.store._fault('after_first_effect')
            return dict(result, operation_id=value['operation_id'], duplicate=False)

    def recover_receipt(self, service, scope_value, operation_id, session):
        self._root(service, scope_value)
        state = self.store.read_snapshot()
        service.registry.authenticate_current(session, 'RECOVER_RECEIPT', scope_value, service.binding_id)
        index = self.store._control_index
        row = index.operations.get(operation_id) if index else None
        check(row is not None and row['command']['scope'] == scope_value, 'NOT_FOUND')
        return deepcopy(row['receipt'])

    def acquire_slot(self, service, value, session, *, grant_ref, manifest_ref):
        """Persist HELD before project confirmation; either gap is recoverable."""
        command(value, combined=self.combined); check(value['type'] == 'SLOT_CONFIRMED')
        project, genesis, key = self._root(service, value['scope'])
        with service.pool.egress(project, genesis, [value['scope']['instance_id']]):
            with service.pool.locked():
                ledger, snapshots, _, _ = service.pool.inspect(sending=True)
                with self.store._locked():
                    state = self.store.read_snapshot()
                    check(state['_head'] == snapshots[key]['_head'])
                    self._authorize(service, value, session, state, grant_ref, manifest_ref)
                    index=self.store._control_index
                    previous=index.operations.get(value['operation_id'])
                    check(index.keys.get(value['idempotency_key']) in (None,value['operation_id']),'IDEMPOTENCY_CONFLICT')
                    if previous is not None:
                        check(previous['command']==value,'IDEMPOTENCY_CONFLICT')
                        return dict(previous['receipt'],duplicate=True)
                    check(value['expected_head'] == state['knowledge_commit'], 'VERSION_CONFLICT')
                    request=state['requests'][value['payload']['request_id']]
                    token=service.pool.token(key,request['instance_id'],request['admission']['operation_id'],request['request_id'],ledger)
                    check(value['payload']['pool_id']==service.pool.pool_id and value['payload']['token']==token)
                    expected=ledger['revision']+int(token not in ledger['slots'])
                    check(value['payload']['pool_revision']<=expected if token in ledger['slots'] else
                          value['payload']['pool_revision']==expected,'VERSION_CONFLICT')
                token, revision = service.pool.acquire_locked(key, value['payload']['request_id'])
                check(token == value['payload']['token'])
                self.store._fault('after_pool_held')
        return service.apply(value, session, grant_ref=grant_ref, manifest_ref=manifest_ref)

    def acquire_native_slot(self, service, request_id, frame):
        project,genesis,key=self._root(service,frame['scope'])
        state=self.store.read_snapshot();request=state['requests'][request_id];call=request['admission']
        check(request['instance_id']==frame['scope']['instance_id'])
        with service.pool.locked():
            ledger=service.pool.read()
            token=service.pool.token(key,request['instance_id'],call['operation_id'],request_id,ledger)
            revision=ledger['revision']+int(token not in ledger['slots'])
        previous=self.store._control_index.operations.get(frame['operation_id'])
        if previous is not None and previous['command']['type']=='SLOT_CONFIRMED':
            revision=previous['command']['payload']['pool_revision']
        value={k:deepcopy(frame[k]) for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
        value.update(schema=self.event_schema,type='SLOT_CONFIRMED',payload=dict(request_id=request_id,
            pool_id=service.pool.pool_id,token=token,pool_revision=revision))
        return self.acquire_slot(service,value,frame['session'],grant_ref=frame['grant_ref'],manifest_ref=frame['manifest_ref'])

    def release_slot(self, service, scope_value, request_id, session, *, expected_epoch=None, expected_version=None):
        project, genesis, key = self._root(service, scope_value)
        with service.pool.egress(project, genesis, [scope_value['instance_id']]):
            with service.pool.locked():
                service.registry.authenticate_current(session, 'EXECUTION_RECEIVED', scope_value, service.binding_id, request_id=request_id)
                _, states, _, _ = service.pool.inspect()
                request = states[key]['requests'][request_id]
                check(request['instance_id'] == scope_value['instance_id'])
                instance=states[key]['instances'][scope_value['instance_id']]
                if expected_epoch is not None:
                    check(expected_epoch==instance['ownership']['owner_epoch'] and
                          expected_version==current_version(instance),'STALE_CONTROL_VERSION')
                check(states[key]['tasks'][request['task_id']].get('actor_kind')!='MAIN','UNSUPPORTED_CAPABILITY')
                token = service.pool.token(key,request['instance_id'],request['admission']['operation_id'],request_id)
                check(request['admission']['slot_token'] in (None,token))
                return service.pool.release_locked(token)

    def prove_unsent(self, service, scope_value, request_id, session):
        """Seal local READY evidence under the same exclusion as first effect.

        The resulting original is evidence only. CANCEL_UNSENT authenticates
        again, and rejects it if any sender crossed the boundary in between.
        """
        project, genesis, key = self._root(service, scope_value)
        with service.pool.egress(project, genesis, [scope_value['instance_id']]):
            with service.pool.locked():
                _, snapshots, _, _ = service.pool.inspect()
                with self.store._locked():
                    state = self.store.read_snapshot()
                    check(state['_head'] == snapshots[key]['_head'], 'VERSION_CONFLICT')
                    service.registry.authenticate_current(session, 'CANCEL_UNSENT', scope_value,
                        service.binding_id, request_id=request_id)
                    request = state['requests'][request_id]; call = request['admission']
                    check(request['instance_id'] == scope_value['instance_id'])
                    check(call['send_phase'] == 'READY' and call['send_boundary_id'] is None and
                          not call['evidence_conflict'], 'EXECUTION_UNRESOLVED')
                    spec = S.AgentInvocationSpec.from_wire(read_json(self.store, call['spec_ref'], project))
                    raw = exact(self.store, project, 'local-unsent:'+request_id,
                        ('SYNTHETIC_TEST_ONLY: complete native ancestry '+state['knowledge_commit']+
                         ' verifies READY with no SEND_STARTED for '+request_id).encode(), raw=True)
                    raw_ref = C.ExactRef.from_wire(raw)
                    receipt = X.DispatchReceipt(status=E.DispatchState.NOT_SENT,
                        handle=X.InvocationHandle(identity=spec.identity(), backend_binding_ref=spec.runner_binding_ref,
                            backend_invocation_id=C.ObservedIdentifier(kind=E.ObservationKind.UNOBSERVED, value=None)),
                        observed_at=C.TimePoint(utc=service.registry.clock().isoformat().replace('+00:00', 'Z'),
                            clock_source=E.ClockSource.SYNTHETIC), raw_evidence_refs=(raw_ref,),
                        error=C.port_error(E.ErrorCode.NOT_SENT, E.Operation.START,
                            identity=spec.identity(), evidence=(raw_ref,)))
                    evidence = exact(self.store, project, 'local-unsent-receipt:'+request_id, receipt.to_wire())
                    service.registry.register_original(evidence, producer_ref=request['execution_inbox']['producer_ref'],
                        binding_ref=request['execution_inbox']['binding_ref'], identity=spec.identity().to_wire(),
                        raw_refs=[raw], local_unsent=True)
                    return evidence

    def reduce(self, service, state, event, auth, spec, ledger, project_key):
        after = deepcopy(state); p = event['payload']; action = event['type']; iid = event['scope']['instance_id']
        instance = after['instances'][iid]; project = state['project_id']; accepted = []
        at = service.registry.clock().isoformat().replace('+00:00', 'Z')
        if self.combined and action=='SCIENCE_ADMITTED':
            at=read_json(self.store,event['decision_ref'],project)['issued_at']
        if action == 'ACTIVATED':
            after = self.native.activate(state); instance = after['instances'][iid]
            profile = read_json(self.store, p['profile_ref'], project)
            if self.combined:
                from .control_fast import unwrap_profile
                profile = unwrap_profile(profile)
            validate_record(profile)
            check(profile['kind'] == 'PROFILE' and profile['pool_id'] == service.pool.pool_id and profile['project_id'] == project)
            instance['ownership'] = record('OWNER', logical_main_id=None if instance['kind'] == 'SURVEY' else 'MAIN-'+iid,
                owner_id=p['owner_id'], owner_epoch=1, backend_binding_ref=p['backend_binding_ref'], authorization_ref=event['decision_ref'])
        elif action == 'OWNER_ACQUIRED':
            check(bool(p['takeover_evidence_refs']))
            instance['ownership'] = record('OWNER', logical_main_id=instance['ownership']['logical_main_id'], owner_id=p['owner_id'],
                owner_epoch=instance['ownership']['owner_epoch']+1, backend_binding_ref=p['backend_binding_ref'], authorization_ref=event['decision_ref'])
            for request in after['requests'].values():
                if request['instance_id'] == iid and after['tasks'][request['task_id']].get('actor_kind') == 'MAIN':
                    request['fenced'] = True
        elif action in {'CONTROL_APPLIED', 'STRATEGY_APPLIED', 'COMMUNICATION_APPLIED'}:
            after = self.native.native(state, action, p['native_event'])
            for gid, grant in after['budget_grants'].items():
                previous = state['budget_grants'].get(gid)
                if previous != grant:
                    grant.update(budget_unit='AGENT_INVOCATION', grant_revision=1 if previous is None else previous['grant_revision']+1,
                                 grant_status='ACTIVE' if previous is None else previous['grant_status'], authorization_ref=event['decision_ref'])
        elif action == 'GRANT_REVOKED':
            grant = after['budget_grants'][p['budget_grant_id']]
            grant.update(grant_status='REVOKED', grant_revision=grant['grant_revision']+1, authorization_ref=event['decision_ref'])
        elif action == 'CALL_PREPARED':
            check(not any(r['instance_id'] == iid and (r['admission']['evidence_conflict'] or r['execution_inbox']['state'] == 'GAP') for r in state['requests'].values()), 'EXECUTION_UNRESOLVED')
            task = read_json(self.store, p['task_ref'], project); candidate = read_json(self.store, p['candidate_ref'], project)
            check(task['request_id'] == spec.request_id and task['instance_id'] == iid and
                  task['attempt_key'] == spec.attempt_id and task['mission_id'] == spec.research_goal_id)
            check(p['reservation_ref'] == spec.reservation_ref.to_wire())
            check(spec.purpose == task.get('work_purpose', 'DEFAULT') and spec.read_set_digest == sha(canonical(task['read_set'])))
            for reference, native_value in ((spec.input_manifest_ref, task['input_manifest']),
                    (spec.output_contract_ref, task['permission_manifest']),
                    (spec.communication_contract_ref, task.get('communication_contract', {})),
                    (spec.sandbox_policy_ref, task['executor_contract'])):
                check(read_ref(self.store, reference.to_wire(), project) == canonical(native_value))
            original_scope = (instance.get('target_ref') if instance['kind'] == 'TRH' else
                              instance['discovery_scope'] if instance['kind'] == 'FDH' else instance['survey_scope'])
            check(read_ref(self.store, spec.original_scope_ref.to_wire(), project) == canonical(original_scope))
            model = task['model_policy']
            check(spec.model_selection.model_id == model['model'] and spec.model_selection.effort == model.get('reasoning_effort') and
                  spec.model_selection.service_tier == model.get('service_tier'))
            check((spec.role is E.AgentRole.MAIN) == (task.get('actor_kind') == 'MAIN'))
            check(spec.role is E.AgentRole.MAIN or spec.stage_responsibility == task['stage_id'])
            check(spec.logical_agent_id == ('MAIN-'+iid if task.get('actor_kind') == 'MAIN' else spec.logical_agent_id))
            after = self.native.prepare(state, task, candidate, at)
            request = after['requests'][spec.request_id]
            check(request['execution_id'] == spec.execution_id)
            registered = service.registry.manifest(p['spec_ref'])
            request['admission'] = record('CALL', operation_id=event['operation_id'], idempotency_key=event['idempotency_key'],
                invocation_id=spec.invocation_id, logical_agent_id=spec.logical_agent_id, attempt_id=spec.attempt_id,
                owner_epoch=spec.owner_epoch, control_version=spec.expected_control_version, spec_ref=p['spec_ref'],
                reservation_ref=p['reservation_ref'], capability_manifest_ref=registered['manifest_ref'],
                send_phase='READY', slot_token=None, send_boundary_id=None, charge='RESERVED', receipt_ids=[],
                not_sent_ref=None, termination_ref=None, evidence_conflict=False)
            request['execution_inbox'] = record('INBOX', producer_ref=registered['producer_ref'], binding_ref=registered['binding_ref'],
                cursor=V.EventCursor(scope=spec.identity().scope, stream_kind=E.StreamKind.RUNNER,
                    stream_id=spec.invocation_id, after_sequence=0, last_event_id=None).to_wire(),
                state='OPEN', gap=None, last_page_ref=None)
        elif action == 'SLOT_CONFIRMED':
            request = after['requests'][p['request_id']]; call = request['admission']
            check(after['tasks'][request['task_id']].get('actor_kind') != 'MAIN', 'UNSUPPORTED_CAPABILITY')
            check(call['send_phase'] == 'READY' and p['pool_id'] == service.pool.pool_id)
            slot = ledger['slots'].get(p['token'])
            check(slot is not None and slot['state'] == 'HELD' and slot['project_key'] == project_key and
                  slot['request_id'] == p['request_id'] and slot['reservation_ref'] == call['reservation_ref'])
            check(p['pool_revision'] <= ledger['revision'])
            call['slot_token'] = p['token']
        elif action == 'SEND_STARTED':
            request = after['requests'][p['request_id']]; call = request['admission']
            check(request['execution_inbox']['state'] == 'OPEN' and not call['evidence_conflict'])
            if after['tasks'][request['task_id']].get('actor_kind') != 'MAIN':
                check(call['slot_token'] is not None and ledger['slots'][call['slot_token']]['state'] == 'HELD', 'SLOT_REQUIRED')
            prepared = self.store._control_index.operations[call['operation_id']]['command']
            candidate = read_json(self.store, prepared['payload']['candidate_ref'], project)
            self.native.send_check(after, p['request_id'], prepared, at)
            request.update(execution_state='UNKNOWN')
            call.update(send_phase='ATTEMPTED', send_boundary_id=p['send_boundary_id'], charge='UNKNOWN_RESERVED')
        elif action == 'EXECUTION_RECEIVED':
            self.receive(service, after, p['receipt'], at)
        elif action == 'INBOX_PAGE_RECEIVED':
            self.page(service, after, p, at)
        elif action in {'CANCEL_UNSENT', 'UNKNOWN_DISPOSED'}:
            request = after['requests'][p['request_id']]
            if action == 'UNKNOWN_DISPOSED' and p['disposition'] == 'ABANDON_UNKNOWN':
                request['fenced'] = True
            else:
                evidence = p.get('not_sent_evidence_ref') or (p['evidence_refs'][0] if p['evidence_refs'] else None)
                check(evidence is not None)
                receipt = X.DispatchReceipt.from_wire(read_json(self.store, evidence, project))
                check(receipt.status is E.DispatchState.NOT_SENT)
                wrapper = record('RECEIPT', receipt_id='not-sent:'+event['operation_id'], identity=receipt.handle.identity.to_wire(),
                    binding_ref=request['execution_inbox']['binding_ref'], producer_ref=request['execution_inbox']['producer_ref'],
                    receipt_kind='DISPATCH', receipt_ref=evidence)
                self.receive(service, after, wrapper, at)
        elif action == 'CANCEL_REQUESTED':
            after['requests'][p['request_id']]['fenced'] = True
        elif action == 'SCIENCE_ADMITTED':
            request = after['requests'][p['request_id']]
            check(not request['admission']['evidence_conflict'] and request['execution_inbox']['state'] == 'OPEN', 'EXECUTION_UNRESOLVED')
            after, accepted = self.native.science(after, p['request_id'], ref(p['capture_ref'], project), **({'at':at} if self.combined else {}))
            after['requests'][p['request_id']]['admission']['charge'] = 'SPENT_OR_SETTLED'
        elif action == 'GUIDANCE_SAVED':
            direction = read_json(self.store, p['direction_ref'], project)
            check(direction['instance_id'] == iid and 'provenance' not in direction)
            after = self.native.guidance(after, direction)
            saved = after['human_directions'][direction['direction_id']]
            if direction['direction_id'] in state['human_directions']:
                return after, accepted
            version = max((r['provenance']['guidance_version'] for r in state['human_directions'].values() if r['instance_id'] == iid), default=0)+1
            saved['provenance'] = record('GUIDANCE', principal_ref=auth['principal_ref'], authorization_ref=event['decision_ref'],
                message_kind='HUMAN_GUIDANCE' if auth['human'] and not auth['proposal_only'] else 'GUIDANCE_PROPOSAL', guidance_version=version, receipt_ids=[])
        elif action == 'GUIDANCE_OBSERVED':
            receipt = X.SteeringReceipt.from_wire(read_json(self.store, p['steering_receipt_ref'], project))
            request = after['requests'][receipt.identity.request_id]
            original_spec=S.AgentInvocationSpec.from_wire(read_json(self.store,request['admission']['spec_ref'],project))
            check(receipt.identity==original_spec.identity())
            registered=service.registry.original(p['steering_receipt_ref'], producer_ref=request['execution_inbox']['producer_ref'],
                binding_ref=request['execution_inbox']['binding_ref'], identity=receipt.identity.to_wire())
            check(registered['raw_refs']==[r.to_wire() for r in receipt.evidence_refs], 'UNTRUSTED_EVENT')
            for reference in receipt.evidence_refs:read_ref(self.store,reference.to_wire(),project,maximum=1024**2)
            direction = after['human_directions'][receipt.message_id]
            check(direction['instance_id'] == iid and request['instance_id'] == iid)
            if receipt.status is E.GuidanceStatus.ADOPTED:
                check(original_spec.role is E.AgentRole.MAIN and request['admission']['owner_epoch'] == instance['ownership']['owner_epoch'] and not request['fenced'])
                confirmation = read_json(self.store, receipt.consumer_confirmation_ref.to_wire(), project)
                check(confirmation.get('proposal_id') in after['strategy_proposals'] and
                      after['strategy_proposals'][confirmation['proposal_id']] == confirmation, 'UNTRUSTED_EVENT')
                check(confirmation.get('status')=='APPLIED' and direction.get('reply_ref')==confirmation['proposal_id'] and
                      confirmation['request_id']==request['request_id'] and confirmation['instance_id']==iid and
                      any(answer['direction_id']==receipt.message_id for answer in confirmation['proposal']['direction_answers']), 'UNTRUSTED_EVENT')
            elif receipt.consumer_confirmation_ref is not None:
                read_ref(self.store,receipt.consumer_confirmation_ref.to_wire(),project,maximum=1024**2)
            receipt_id = p['steering_receipt_ref']['sha256']
            ids = direction['provenance']['receipt_ids']
            if receipt_id not in ids:
                ids.append(receipt_id)
        else:
            check(False, 'UNSUPPORTED_CAPABILITY')
        if action in {'ACTIVATED', 'OWNER_ACQUIRED', 'CONTROL_APPLIED', 'GRANT_REVOKED'}:
            instance = after['instances'][iid]
            desired = current_version(state['instances'][iid])+1
            if instance['kind'] == 'SURVEY':
                instance['infrastructure_control_version'] = desired
            else:
                check(current_version(instance) in {desired-1, desired})
                instance['run_control']['control_version'] = desired
        return after, accepted

    def _verified_receipt(self, service, state, wrapper):
        validate_record(wrapper)
        check(wrapper['kind'] == 'RECEIPT')
        identity = C.InvocationIdentity.from_wire(wrapper['identity'])
        check(identity.scope.project_id == state['project_id'])
        request = state['requests'].get(identity.request_id)
        check(request is not None and request['instance_id'] == identity.scope.instance_id)
        spec = S.AgentInvocationSpec.from_wire(read_json(self.store, request['admission']['spec_ref'], state['project_id']))
        check(identity == spec.identity() and wrapper['binding_ref'] == spec.runner_binding_ref.to_wire())
        check(wrapper['producer_ref'] == request['execution_inbox']['producer_ref'])
        registered = service.registry.original(wrapper['receipt_ref'], producer_ref=wrapper['producer_ref'],
            binding_ref=wrapper['binding_ref'], identity=wrapper['identity'])
        if registered['local_unsent']:
            call = request['admission']
            check(call['send_boundary_id'] is None and
                  (call['send_phase'] == 'READY' or call['not_sent_ref'] == wrapper['receipt_ref']), 'EXECUTION_UNRESOLVED')
        raw = read_ref(self.store, wrapper['receipt_ref'], state['project_id'])
        receipt = RECEIPT_TYPES[wrapper['receipt_kind']].from_json(raw.decode('utf-8'))
        check(canonical(receipt.to_wire()) == raw)
        check((receipt.handle.identity if isinstance(receipt, X.DispatchReceipt) else receipt.identity) == identity)
        if isinstance(receipt, X.DispatchReceipt):
            check(receipt.handle.backend_binding_ref.to_wire() == wrapper['binding_ref'])
        if isinstance(receipt, X.CaptureReceipt):
            raw_refs = [receipt.raw_output_ref, receipt.actual_input_manifest_ref, *receipt.raw_event_refs]
        elif isinstance(receipt, X.CancellationReceipt):
            raw_refs = [*receipt.request_evidence_refs, *receipt.termination_evidence_refs]
        else:
            raw_refs = list(receipt.raw_evidence_refs)
        check(registered['raw_refs'] == [r.to_wire() for r in raw_refs], 'UNTRUSTED_EVENT')
        for reference in raw_refs:
            read_ref(self.store, reference.to_wire(), state['project_id'], maximum=1024**2)
        return request, receipt

    def receive(self, service, state, wrapper, at, *, fold=True):
        request, receipt = self._verified_receipt(service, state, wrapper)
        key = wrapper['receipt_id']
        previous = state['execution_events'].get(key)
        check(previous is None or previous == wrapper, 'IDEMPOTENCY_CONFLICT')
        state['execution_events'][key] = deepcopy(wrapper)
        ids = request['admission']['receipt_ids']
        if key not in ids:
            check(len(ids) < MAX_ITEMS, 'RESOURCE_LIMIT')
            ids.append(key)
        if fold:
            self.fold(state, request['request_id'], at)

    def fold(self, state, request_id, at):
        """Derive one liability from all original evidence, in either order."""
        request = state['requests'][request_id]; call = request['admission']
        executed = False; not_sent = None; terminal = None; capture = None
        for rid in call['receipt_ids']:
            wrapper = state['execution_events'][rid]
            parsed = RECEIPT_TYPES[wrapper['receipt_kind']].from_wire(read_json(self.store, wrapper['receipt_ref'], state['project_id']))
            if isinstance(parsed, X.DispatchReceipt):
                executed |= parsed.status is E.DispatchState.SENT
                if parsed.status is E.DispatchState.NOT_SENT:
                    not_sent = not_sent or wrapper['receipt_ref']
            elif isinstance(parsed, X.ExecutionObservation):
                executed |= parsed.state in {E.ExecutionState.SENT, E.ExecutionState.RUNNING, E.ExecutionState.TERMINATED}
                if parsed.state is E.ExecutionState.TERMINATED:
                    terminal = terminal or wrapper['receipt_ref']
            elif isinstance(parsed, X.CancellationReceipt) and parsed.termination is E.ObservationKind.OBSERVED:
                executed = True; terminal = terminal or wrapper['receipt_ref']
            elif isinstance(parsed, X.CaptureReceipt):
                executed = True
                check(capture is None or capture.raw_output_ref == parsed.raw_output_ref, 'IDEMPOTENCY_CONFLICT')
                capture = capture or parsed
        call['not_sent_ref'] = call['not_sent_ref'] or not_sent
        call['termination_ref'] = call['termination_ref'] or terminal
        if executed and (not_sent is not None or call['send_boundary_id'] is None):
            call['evidence_conflict'] = True
        if call['evidence_conflict']:
            call.update(send_phase='CLOSED', charge='SPENT_OR_SETTLED')
            request['fenced'] = True
            if request['execution_state'] not in {'CAPTURED', 'SETTLED'}:
                request['execution_state'] = 'UNKNOWN'
            return
        if request['execution_inbox']['state'] == 'GAP':
            return
        if executed:
            call['charge'] = 'SPENT_OR_SETTLED'
            if request['execution_state'] not in {'CAPTURED', 'SETTLED'} and (not terminal or capture):
                request['execution_state'] = 'SENT'
                self.native.sent(state, request_id)
        if capture and not request.get('capture_ref'):
            changed = self.native.capture(state, request_id, capture, at)
            state.clear(); state.update(changed)
            request = state['requests'][request_id]; call = request['admission']
        if terminal:
            call.update(send_phase='CLOSED', charge='SPENT_OR_SETTLED')
            if not request.get('capture_ref'):
                request['fenced'] = True
            instance = state['instances'][request['instance_id']]
            if state['tasks'][request['task_id']].get('actor_kind') == 'MAIN' and call['owner_epoch'] != instance['ownership']['owner_epoch']:
                request['fenced'] = True
        if not_sent:
            call.update(send_phase='CLOSED', charge='RELEASED')
            request.update(execution_state='CANCELLED_BEFORE_SEND', acceptance_state='NOT_SUBMITTED', fenced=True)

    def page(self, service, state, payload, at):
        request = state['requests'][payload['request_id']]; inbox = request['execution_inbox']; call = request['admission']
        project = state['project_id']
        check(payload['producer_ref'] == inbox['producer_ref'] and payload['binding_ref'] == inbox['binding_ref'], 'UNTRUSTED_EVENT')
        page = V.RunnerEventPage.from_wire(read_json(self.store, payload['page_ref'], project))
        durable = V.EventCursor.from_wire(inbox['cursor'])
        check(page.requested_cursor.scope == durable.scope and page.requested_cursor.stream_id == durable.stream_id)
        index = self.store._control_index
        stream = index.streams.get(payload['request_id'], {})
        known_ids = {value[0] for value in stream.values()}
        check(set(page.duplicate_event_ids) <= known_ids, 'UNTRUSTED_EVENT')
        wrappers = []
        for observed in page.events:
            envelope = observed.envelope
            check(envelope.status is E.EventStatus.OBSERVATION and envelope.actor_kind == 'SYNTHETIC' and
                  envelope.trust_origin is E.TrustOrigin.SYNTHETIC_TEST_ONLY and envelope.classification is E.Classification.SYNTHETIC_TEST_ONLY)
            check(envelope.actor_principal_ref is not None and envelope.backend_binding_ref is not None, 'UNTRUSTED_EVENT')
            check(envelope.actor_principal_ref.to_wire() == inbox['producer_ref'] and
                  envelope.backend_binding_ref.to_wire() == inbox['binding_ref'], 'UNTRUSTED_EVENT')
            check((envelope.owner_epoch, envelope.control_version) == (call['owner_epoch'], call['control_version']))
            check((envelope.request_id, envelope.execution_id, envelope.attempt_id, envelope.invocation_id) ==
                  (request['request_id'], request['execution_id'], call['attempt_id'], call['invocation_id']))
            check(envelope.payload_sha256 == envelope.payload_ref.sha256)
            read_ref(self.store, observed.raw_event_ref.to_wire(), project, maximum=1024**2)
            wrapper = runner_receipt(self.store, request, observed, project)
            self._verified_receipt(service, state, wrapper)
            for sequence, (event_id, event_hash) in stream.items():
                if event_id == envelope.event_id:
                    check(sequence == observed.sequence and event_hash == observed.wire_digest(), 'IDEMPOTENCY_CONFLICT')
            wrappers.append(wrapper)
        if page.status is E.PageStatus.EMPTY:
            check(page.requested_cursor == durable, 'VERSION_CONFLICT')
            return
        if page.requested_cursor.after_sequence < durable.after_sequence:
            check(page.status is E.PageStatus.COMPLETE and page.next_cursor.after_sequence <= durable.after_sequence, 'VERSION_CONFLICT')
            check(all(stream.get(item.sequence) == (item.envelope.event_id, item.wire_digest()) for item in page.events), 'IDEMPOTENCY_CONFLICT')
            return
        if page.requested_cursor.after_sequence > durable.after_sequence:
            check(page.status is E.PageStatus.COMPLETE, 'VERSION_CONFLICT')
            gap = V.EventGap(first_missing_sequence=durable.after_sequence+1,
                last_missing_sequence=page.requested_cursor.after_sequence, reason=E.GapReason.DISCONTINUITY, resnapshot_ref=None)
            if inbox['gap'] is not None:
                previous = V.EventGap.from_wire(inbox['gap'])
                if previous.last_missing_sequence > gap.last_missing_sequence:
                    gap = previous
            inbox.update(state='GAP', gap=gap.to_wire(), last_page_ref=payload['page_ref'])
            return
        check(page.requested_cursor == durable, 'INVALID_CURSOR')
        if page.status is E.PageStatus.GAP:
            check(page.gap.first_missing_sequence == durable.after_sequence+1, 'INVALID_CURSOR')
            gap = page.gap
            if inbox['gap'] is not None and inbox['gap']['last_missing_sequence'] > gap.last_missing_sequence:
                gap = V.EventGap.from_wire(inbox['gap'])
            inbox.update(state='GAP', gap=gap.to_wire(), last_page_ref=payload['page_ref'])
            return
        old_gap = inbox['gap']
        for wrapper in wrappers:
            self.receive(service, state, wrapper, at, fold=False)
        inbox['cursor'] = page.next_cursor.to_wire()
        inbox['last_page_ref'] = payload['page_ref']
        if old_gap and page.next_cursor.after_sequence < old_gap['last_missing_sequence']:
            inbox['gap'] = V.EventGap(first_missing_sequence=page.next_cursor.after_sequence+1,
                last_missing_sequence=old_gap['last_missing_sequence'], reason=E.GapReason.DISCONTINUITY, resnapshot_ref=None).to_wire()
        else:
            inbox.update(state='OPEN', gap=None)
        self.fold(state, payload['request_id'], at)
