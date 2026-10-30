"""Explicit combined profile of the existing control journal; no fast-only root."""
from copy import deepcopy
from . import control as D
from pmrh.domain.primitives import canonical

SCHEMA = 'pmrh.control-fast.commit/1'
EVENT_SCHEMA = 'pmrh.control-fast-event/1'
PROFILE_SCHEMA = 'pmrh.control-fast-profile/1'
FAST_PAYLOAD_FIELDS = {
    'FAST_PROPOSAL_CAPTURED': 'request_id capture_ref receipt_ref proposal_ref',
    'FAST_DELTA_APPLIED': 'proposal_ref',
}
CAPABILITY = {'schema': 'pmrh.fast-capability/1', 'profile': 'SYNTHETIC_TEST_ONLY',
              'actions': ['FAST_PROPOSAL_CAPTURED', 'FAST_DELTA_APPLIED']}


def profile(native_profile):
    D.validate_record(native_profile)
    D.check(native_profile['kind'] == 'PROFILE')
    return dict(schema=PROFILE_SCHEMA, native_profile=deepcopy(native_profile), fast_capability=deepcopy(CAPABILITY))


def unwrap_profile(value):
    D.fields(value, 'schema native_profile fast_capability')
    D.check(value['schema'] == PROFILE_SCHEMA and value['fast_capability'] == CAPABILITY)
    D.validate_record(value['native_profile'])
    D.check(value['native_profile']['kind'] == 'PROFILE')
    return value['native_profile']


def validate_entry(entry):
    if entry['schema'] == SCHEMA:
        D.validate_entry(entry, combined=True)
    else:
        D.check(not any(e.get('schema') == EVENT_SCHEMA or e.get('type') in FAST_PAYLOAD_FIELDS for e in entry['events']), 'JOURNAL_INVALID')


def scan(store, history, apply_delta):
    return D.scan(store, history, apply_delta, combined=True)


def publication_schema(store, previous, events):
    prior = store._commit_record(previous)['schema'] if previous else None
    proposed = any(e.get('schema') == EVENT_SCHEMA for e in events)
    if prior != SCHEMA and not proposed: return None
    capability = getattr(store, '_control_publication', None)
    D.check(type(capability) is CombinedControlStorage and capability.store is store, 'AUTHORIZATION_REQUIRED')
    D.check(len(events) == 1 and proposed and not getattr(store, '_fixture_publication', False), 'UNSUPPORTED_CAPABILITY')
    if prior != SCHEMA:
        # The actual one-use setup object is checked by the native bridge too.
        from .native_format import COMMIT_SCHEMA
        D.check(prior == COMMIT_SCHEMA and events[0]['type'] == 'ACTIVATED', 'UNSUPPORTED_CAPABILITY')
        capability.native.verify_combined_setup()
    return SCHEMA


def rejection_effects(store,before,request_id,capture_ref,at):
    """Exact original SETTLE projection for the frozen early-entry subset only."""
    from pmrh.domain.native_response import bounded_fast_rejection
    from pmrh.domain.native_settlement import event as settle_event, apply_event as settle
    from .fastmath import _capture
    request=before['requests'][request_id];task=before['tasks'][request['task_id']]
    raw=D.read_ref(store,capture_ref,before['project_id'],maximum=1024**2)
    diagnostic=bounded_fast_rejection(task,before,raw)
    if diagnostic is None:return None
    D.check(request['execution_kind']=='SYNTHETIC_TEST_ONLY' and request['execution_state']=='CAPTURED', 'EXECUTION_TRANSITION_INVALID')
    D.check(request['capture_ref']==capture_ref['sha256'], 'ORIGINAL_BYTES_MISMATCH')
    originals=[row for row in before.get('fast_proposals',{}).values() if
        row['request_id']==request_id and row['capture_ref']==capture_ref and row['status']=='PENDING']
    D.check(len(originals)==1,'ORIGINAL_BYTES_MISMATCH')
    _capture(store,before,originals[0])
    for binding in task.get('read_set',[]):
        D.check(store.read_record(binding['record_ref'])==before['records'][binding['record_ref']], 'RECORD_CHANGED')
    original=settle_event(dict(request_id=request_id,acceptance_state='REJECTED_CONTRACT',
        receipt_ref=None,error=diagnostic['code'],diagnostic=diagnostic,issued_at=at))
    after=settle(before,original)
    after['requests'][request_id]['admission']['charge']='SPENT_OR_SETTLED'
    return after


def validate_rejection(store,before,after,event,decision,accepted):
    """Live and bare-Journal proof of the exact bounded native rejection."""
    from pmrh.domain.native_response import bounded_fast_rejection
    from pmrh.ports.dto import specs as S, capability as K
    from pmrh.ports.capabilities import check_capabilities
    from .journal import _persistent
    p=event['payload'];rid=p['request_id'];request=before['requests'][rid]
    task=before['tasks'][request['task_id']];project=before['project_id']
    raw=D.read_ref(store,p['capture_ref'],project,maximum=1024**2)
    diagnostic=bounded_fast_rejection(task,before,raw)
    if diagnostic is None:
        # Unsupported FORMAT/later failures cannot acquire a settlement by a delta.
        D.check(after['requests'][rid]['acceptance_state'] not in {'REJECTED_CONTRACT','REJECTED_STALE'},'CAPABILITY_VIOLATION')
        return
    D.check(accepted==[], 'CAPABILITY_VIOLATION')
    instance=before['instances'][request['instance_id']]
    D.check(event['scope']==dict(project_id=project,instance_id=request['instance_id']) and
        instance['status']=='ACTIVE' and request['mission_id']==instance['current_mission_id'] and
        event['owner_epoch']==request['admission']['owner_epoch']==instance['ownership']['owner_epoch'] and
        event['control_version']==request['admission']['control_version']==D.current_version(instance),'AUTHORIZATION_REQUIRED')
    D.check(not request['fenced'] and request['execution_inbox']['state']=='OPEN' and
        not request['admission']['evidence_conflict'],'EXECUTION_UNRESOLVED')
    grant=D.read_json(store,decision['budget_grant_ref'],project)
    D.check(grant==before['budget_grants'][request['budget_grant_id']] and grant['grant_status']=='ACTIVE' and
        grant['instance_id']==request['instance_id'] and grant['mission_id']==request['mission_id'],'AUTHORIZATION_REQUIRED')
    D.check(decision['capability_manifest_ref']==request['admission']['capability_manifest_ref'],'AUTHORIZATION_REQUIRED')
    spec=S.AgentInvocationSpec.from_wire(D.read_json(store,request['admission']['spec_ref'],project))
    manifest=K.CapabilityManifest.from_wire(D.read_json(store,decision['capability_manifest_ref'],project))
    D.check(check_capabilities(manifest,spec.capability_requirements) is None,'UNSUPPORTED_CAPABILITY')
    settles=[e for key,e in after['execution_events'].items() if key not in before['execution_events'] and e.get('event_type')=='SETTLE']
    D.check(len(settles)==1,'CAPABILITY_VIOLATION');at=settles[0]['payload'].get('issued_at')
    time=D.timestamp(at)
    D.check(at==decision['issued_at'] and time<D.timestamp(decision['expires_at']),'AUTHORIZATION_REQUIRED')
    clock=before.get('research_clocks',{}).get(request['instance_id'])
    if clock:D.check(time>=D.timestamp(clock['last_observed_at']),'AUDIT_CLOCK_INVALID')
    for previous in before['execution_events'].values():
        payload=previous.get('payload',{})
        if previous.get('event_type') in {'PREPARE','RESERVE','SENT','CAPTURE','UNKNOWN','SETTLE'} and (
            payload.get('request_id')==rid or payload.get('task',{}).get('request_id')==rid) and payload.get('issued_at'):
            D.check(time>=D.timestamp(payload['issued_at']),'AUDIT_CLOCK_INVALID')
    expected=rejection_effects(store,before,rid,p['capture_ref'],at)
    D.check(expected is not None and _persistent(expected)==_persistent(after),'CAPABILITY_VIOLATION')


class CombinedControlStorage(D.ControlStorage):
    event_schema = EVENT_SCHEMA
    combined = True

    def __init__(self, store, native):
        D.check(getattr(native, 'combined_capability', None) == CAPABILITY, 'AUTHORIZATION_REQUIRED')
        super().__init__(store, native)
        from .fastmath import FastStorage
        self.fast = FastStorage(self)

    @staticmethod
    def validate_command(value):
        return D.command(value, combined=True)

    def _authorize(self, service, value, session, state, grant_ref, manifest_ref):
        if value['type'] in FAST_PAYLOAD_FIELDS:
            return self.fast.authorize(service,value,session,state,grant_ref,manifest_ref)
        auth,spec=super()._authorize(service,value,session,state,grant_ref,manifest_ref)
        if value['type']=='SCIENCE_ADMITTED':
            request=state['requests'][value['payload']['request_id']]
            D.check(not request['fenced'],'TASK_FENCED')
            D.check(request['execution_inbox']['state']=='OPEN' and not request['admission']['evidence_conflict'],'EXECUTION_UNRESOLVED')
            D.check(request['capture_ref']==value['payload']['capture_ref']['sha256'],'ORIGINAL_BYTES_MISMATCH')
            D.read_ref(self.store,value['payload']['capture_ref'],state['project_id'],maximum=1024**2)
        return auth,spec

    def reduce(self, service, state, event, auth, spec, ledger, project_key):
        if event['type'] in FAST_PAYLOAD_FIELDS:
            return self.fast.reduce(service,state,event), []
        after,accepted=super().reduce(service,state,event,auth,spec,ledger,project_key)
        if event['type']=='SCIENCE_ADMITTED' and after['requests'][event['payload']['request_id']]['acceptance_state']=='REJECTED_CONTRACT':
            D.check(accepted==[],'CAPABILITY_VIOLATION')
        return after,accepted

    def validate_transition(self, before, after, event):
        if event['type'] in FAST_PAYLOAD_FIELDS:
            from .fastmath import validate_effects
            decision = D.read_json(self.store,event['decision_ref'],before['project_id'])
            validate_effects(self.store,before,after,event,decision)
        else:
            D.validate_transition(before,after,event)
            if event['type']=='SCIENCE_ADMITTED':
                decision=D.read_json(self.store,event['decision_ref'],before['project_id'])
                validate_rejection(self.store,before,after,event,decision,[])

    def execute(self, service, value, session, grant_ref, manifest_ref, *, boundary=None):
        # Use the actual shared Pool. Its exact combined discriminator follows
        # Journal validation; reservations and capacity retain native authority.
        result = super().execute(service,value,session,grant_ref,manifest_ref,boundary=boundary)
        if value['type'] not in FAST_PAYLOAD_FIELDS: return result
        if result.get('schema') == 'pmrh.fast-receipt/1': return result
        state = self.store.read_snapshot()
        return deepcopy(self.store._control_index.operations[value['operation_id']]['receipt'])
