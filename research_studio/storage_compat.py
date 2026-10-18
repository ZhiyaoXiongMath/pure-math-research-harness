"""Trusted static legacy writer assembly; never used by the confined query."""
from copy import deepcopy
import secrets
from pmrh.adapters.storage.journal import (
    SCIENCE_MAPS, CONTROL_MAPS, EXECUTION_MAPS, REPORT_MAPS, _diff,
)
from .util import canonical, sha, require, immutable, now
from .version import VERSIONS, SCHEMA_VERSION
from .language import policy
from .survey import MAPS as SURVEY_MAPS
from .assistant import MAPS as ASSISTANT_MAPS
from .native_main import MAPS as NATIVE_MAIN_MAPS

def initial_state(title, language=None, *, synthetic=False):
    from .strategy import MAPS as STRATEGY_MAPS
    from .communication import MAPS as COMMUNICATION_MAPS
    from .usage_ledger import MAPS as USAGE_MAPS
    maps = (SCIENCE_MAPS | CONTROL_MAPS | EXECUTION_MAPS | REPORT_MAPS | SURVEY_MAPS | ASSISTANT_MAPS) - {'relations'}
    maps |= STRATEGY_MAPS | COMMUNICATION_MAPS | USAGE_MAPS | NATIVE_MAIN_MAPS
    state = {name: {} for name in sorted(maps)}
    state.update(schema=SCHEMA_VERSION, project_id='P34F-'+secrets.token_hex(12),
        title=title, versions=dict(VERSIONS), language_policy=policy(language),
        relations=[], knowledge_changes=[], synthetic_test_only=bool(synthetic),
        usage={'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0},
        project_budget={'max_calls': 0}, max_workers=8,
        capabilities={'CAP-HUMAN': {'actor': 'human', 'actions': ['*'], 'instance_ids': ['*']},
                      'CAP-HOST': {'actor': 'host', 'actions': ['*'], 'instance_ids': ['*']}},
        scope_versions={'project': 0})
    return state

class LegacyWriters:
    @classmethod
    def create(cls, root, title, *, language=None, initial=None, synthetic=False):
        require(initial is None, 'STATE_PATCH_FORBIDDEN', 'Use typed knowledge and control events')
        store = cls(root)
        require(not store.root.exists(), 'PROJECT_EXISTS', 'A new project directory is required')
        state = initial_state(title, language, synthetic=synthetic)
        store.root.mkdir(parents=True, mode=0o700)
        immutable(store.root/'project.json', canonical({'schema': SCHEMA_VERSION, 'project_id': state['project_id'],
                                                      'synthetic_test_only': state['synthetic_test_only']}))
        immutable(store.root/'.runtime/writer.lock', b'')
        store._publish(None, {}, state, actor='HOST', events=[{'type': 'PROJECT_CREATED', 'model_calls': 0}])
        return store

    def commit(self, validated, expected_relevant_guards=None, *, admission_recheck=None):
        """Revalidate the same frozen response on the live state under one lock."""
        from . import changes
        with self._locked():
            state, head = self.read()
            if admission_recheck is not None:
                from .execution import validate_recheck_context
                validate_recheck_context(state,admission_recheck,self.read_blob)
                require(getattr(validated,'_task',{}).get('request_id')==admission_recheck['request_id']
                        and sha(getattr(validated,'_raw',b''))==admission_recheck['capture_ref'],
                        'ORIGINAL_BYTES_MISMATCH','Maintenance admission must validate exactly the original response.')
            frozen=getattr(validated,'_task',None)
            if isinstance(frozen,dict):
                original=state.get('requests',{}).get(frozen.get('request_id'),{})
                require(not (original.get('execution_state')=='SETTLED' and original.get('acceptance_state') in {'REJECTED_CONTRACT','REJECTED_STALE'})
                        or admission_recheck is not None,'ADMISSION_RECHECK_REQUIRED',
                        'A settled rejection requires explicit maintenance recheck of its original capture; ordinary scientific commit cannot erase rejection history.')
                for item in frozen.get('read_set',[]):
                    ref=item['record_ref']
                    require(self.read_record(ref)==state['records'].get(ref),'RECORD_CHANGED',ref)
            # changes owns scientific semantics; a forged dictionary is not an
            # accepted plan. Its entry point must re-run validation from raw.
            proposal = changes.revalidate(validated, state, blob_get=self.read_blob)
            if proposal.get('outcome') == 'EXACT_DUPLICATE':
                return proposal['receipt']
            for digest, data in proposal.get('blobs', {}).items():
                require(self.put_blob(data) == digest, 'BLOB_CHANGED', 'Candidate blob hash differs')
            after = changes.apply_validated(state, proposal)
            if admission_recheck is not None:
                from . import execution
                recheck_event=execution.event('ADMISSION_RECHECKED',{**deepcopy(admission_recheck),'outcome':'ACCEPTED',
                    'receipt_ref':proposal.get('receipt',{}).get('receipt_id'),'diagnostic':None})
                after=execution.apply_event(after,recheck_event,self.read_blob)
                proposal.setdefault('events',[]).append(recheck_event)
            self._fault('after_blobs')
            result = self._publish(head, state, after, actor=proposal.get('actor', 'MODEL_CAPTURE'),
                events=proposal.get('events', []), base=proposal.get('base_knowledge_commit'),
                accepted=proposal.get('accepted_request_bindings', []))
            return dict(proposal.get('receipt', {}), **result)

    def _typed_commit(self, event, apply, allowed, category):
        require(apply is None, 'CAPABILITY_VIOLATION', 'Reducers are selected by trusted assembly only')
        if self.history()[-1][1]['schema'] == 'pmrh.commit/2':
            actions = {'Control':'CONTROL_APPLIED', 'research_studio.strategy':'STRATEGY_APPLIED',
                       'research_studio.communication':'COMMUNICATION_APPLIED'}
            require(category in actions, 'UNSUPPORTED_CAPABILITY', 'Raw native writer is not available on the control profile')
            if category == 'research_studio.strategy' and event.get('event_type') == 'HUMAN_DIRECTION_SUBMITTED':
                from pmrh.adapters.storage.control import exact
                state = self.read_snapshot(); direction = event['payload']['direction']
                reference = exact(self, state['project_id'], 'direction:'+direction['direction_id'], direction)
                return self._control_native('GUIDANCE_SAVED', {'direction_ref':reference})
            return self._control_native(actions[category], {'native_event':event})
        apply, registered = _reducer(category, self.read_blob)
        require(allowed == registered, 'CAPABILITY_VIOLATION', 'Reducer collection contract differs')
        require(isinstance(event, dict), 'RESPONSE_SCHEMA_INVALID', 'Typed event required')
        with self._locked():
            state, head = self.read()
            # Activation may have won the writer lock after the initial format
            # dispatch. Do not let a native no-change/duplicate escape its gate.
            require(self._commit_record(head)['schema'] != 'pmrh.commit/2',
                    'UNSUPPORTED_CAPABILITY', 'Control activation requires a fresh gated native command')
            payload=event.get('payload',{})
            if event.get('event_type')=='AUTHORIZE_MISSION':
                mission=payload.get('mission',{})
                for obligation in mission.get('obligations',[]):self.read_blob(obligation['definition']['criterion_body_ref'])
                if mission.get('intent_ref'):self.read_blob(mission['intent_ref'])
                if payload.get('future_configuration'):self.read_blob(payload['future_configuration']['reason_ref'])
            if event.get('event_type')=='ASSIGN_OBLIGATION':self.read_blob(payload['obligation']['definition']['criterion_body_ref'])
            after = apply(deepcopy(state), deepcopy(event))
            require(isinstance(after, dict), 'EVENT_INVALID', 'Event reducer must return a snapshot')
            touched = set(_diff(state, after))
            require(touched <= allowed, 'CAPABILITY_VIOLATION', category+' event changed an unauthorized collection')
            if after == state:
                return {'commit': head['commit'], 'sequence': head['sequence'], 'outcome': 'EXACT_DUPLICATE'}
            if event.get('event_type')=='HUMAN_DECISION':
                instance=state['instances'][event['instance_id']]
                mission=state.get('missions',{}).get(instance.get('current_mission_id'),{})
                action={'CONTINUE_DISCOVERY':'CONTINUE','END_WITHOUT_ADOPTION':'END'}.get(payload.get('action'),payload.get('action'))
                if action in mission.get('report_first_actions',[]):
                    from .report_catalog import classify
                    report=state.get('reports',{}).get(payload['decision_basis'].get('report_ref'))
                    require(report is not None and classify(self,state,report)=='COMPLETED_CURRENT_REPORT',
                            'REPORT_BLOCKED','The explicitly required report must be complete, intact and current for this decision')
            return self._publish(head, state, after, actor=event.get('actor', 'HOST'),
                events=[event], base=event.get('base_knowledge_commit'))

    def commit_control(self, event):
        from .workflow_instances import apply_control
        from .research_audit import MAPS as AUDIT_MAPS
        result=self._typed_commit(event, None, CONTROL_MAPS | AUDIT_MAPS, 'Control')
        if self.history()[-1][1]['schema'] != 'pmrh.commit/2' and event.get('event_type')=='HUMAN_DECISION' and event.get('payload',{}).get('action') in {'END','END_WITHOUT_ADOPTION'}:
            from .rounds import record
            record(self,event['instance_id'])
        return result

    def commit_execution(self, event):
        from .execution import apply_event
        from .research_audit import MAPS as AUDIT_MAPS
        return self._typed_commit(event, None, EXECUTION_MAPS | AUDIT_MAPS, 'Execution')

    def commit_survey(self, event):
        from .survey import apply_event
        return self._typed_commit(event, None, SURVEY_MAPS | {'sources'}, 'Survey')

    def commit_report(self, event):
        from .reports import apply_event
        return self._typed_commit(event, None, REPORT_MAPS, 'Report')

    def commit_assistant(self, event):
        from .assistant import apply_event
        require(event.get('event_type') not in {'OPEN_SESSION','AUTHORIZE','USER_MESSAGE','REPORT_ALLOWANCE','PREPARE_TURN','PREPARE'},
                'PROJECT_ASSISTANT_REMOVED','New assistant work is unavailable; use the native main researcher.')
        return self._typed_commit(event,None,ASSISTANT_MAPS,'Assistant')

    def _commit_extension(self, module, event):
        require(module.__name__ in {'research_studio.strategy', 'research_studio.communication',
                                  'research_studio.usage_ledger', 'research_studio.incidents'},
                'CAPABILITY_VIOLATION', 'Unknown trusted extension')
        return self._typed_commit(event, None,
                                  module.MAPS, module.__name__)

    def commit_strategy(self, event):
        from . import strategy
        return self._commit_extension(strategy,event)

    def commit_communication(self, event):
        from . import communication
        return self._commit_extension(communication,event)

    def commit_usage(self, event):
        from . import usage_ledger
        return self._commit_extension(usage_ledger,event)

    def commit_native_main(self, event):
        from . import native_main
        from .research_audit import MAPS as AUDIT_MAPS
        return self._typed_commit(event, None, NATIVE_MAIN_MAPS | EXECUTION_MAPS | AUDIT_MAPS, 'NativeMain')

    def commit_incident(self, event):
        from . import incidents
        return self._commit_extension(incidents,event)

    def _control_guard(self, category):
        """Native direct writers cannot use CAP-HOST/HUMAN to bypass /2."""
        if self.history()[-1][1]['schema'] == 'pmrh.commit/2':
            require(False, 'AUTHORIZATION_REQUIRED' if category in
                    {'Control', 'Execution', 'Science', 'research_studio.strategy', 'research_studio.communication'}
                    else 'UNSUPPORTED_CAPABILITY', 'Use the authenticated closed control command service')

    def _control_native(self, action, payload):
        service = getattr(self, '_control_service', None)
        require(service is not None, 'AUTHORIZATION_REQUIRED', 'Current host authentication context required')
        return service.native(action, payload)



def _reducer(category, blob_get):
    """Closed trusted code registry. Data cannot name a module or callback."""
    from . import workflow_instances, execution, survey, reports, assistant
    from . import native_main, strategy, communication, usage_ledger, incidents
    from .research_audit import MAPS as AUDIT_MAPS
    registry = {
        'Control': (workflow_instances.apply_control, CONTROL_MAPS | AUDIT_MAPS),
        'Execution': (lambda s,e: execution.apply_event(s,e,blob_get), EXECUTION_MAPS | AUDIT_MAPS),
        'Survey': (survey.apply_event, SURVEY_MAPS | {'sources'}),
        'Report': (reports.apply_event, REPORT_MAPS),
        'Assistant': (lambda s,e: assistant.apply_event(s,e,blob_get), ASSISTANT_MAPS),
        'NativeMain': (native_main.apply_event, NATIVE_MAIN_MAPS | EXECUTION_MAPS | AUDIT_MAPS),
        'research_studio.strategy': (lambda s,e: strategy.apply_event(s,e,blob_get), strategy.MAPS),
        'research_studio.communication': (lambda s,e: communication.apply_event(s,e,blob_get), communication.MAPS),
        'research_studio.usage_ledger': (lambda s,e: usage_ledger.apply_event(s,e,blob_get), usage_ledger.MAPS),
        'research_studio.incidents': (lambda s,e: incidents.apply_event(s,e,blob_get), incidents.MAPS),
    }
    require(category in registry, 'CAPABILITY_VIOLATION', 'Unknown trusted reducer')
    return registry[category]


class SyntheticSetup:
    """One-use capability held only by the assembly that created this root.

    There is deliberately no load(path), migration, synthetic-flag adoption or
    arbitrary initial-state argument. The exact native outputs are frozen here.
    """
    def __init__(self, root, *, kind, inputs=(), survey_scope=None, title='Synthetic control fixture'):
        from .store import Store
        from . import changes, workflow_instances as W
        require(kind in {'TRH', 'FDH', 'SURVEY'} and len(inputs) == {'TRH': 1, 'FDH': 3, 'SURVEY': 0}[kind],
                'SETUP_PREFIX_INVALID', 'Exact original-source prefix required')
        require(all(type(raw) is bytes and raw.strip() for raw in inputs), 'SETUP_PREFIX_INVALID', 'Nonempty exact originals required')
        self.store = Store.create(root, title, synthetic=True, initial=None)
        originals = []
        for raw in inputs:
            before = self.store.read_snapshot()
            proposal = changes.prepare_source_input(before, raw, purpose='PROBLEM' if kind == 'TRH' else 'PHENOMENON', blob_get=self.store.read_blob)
            expected = changes.apply_validated(before, proposal)
            result = self.store.commit(proposal)
            self._same_output(expected)
            originals.append(result)
        state = self.store.read_snapshot()
        discovery = dict(zip(('phenomenon_ref', 'immutable_background_ref', 'allowed_axes_ref'),
                             (r['source_ref'] for r in originals))) if kind == 'FDH' else None
        instance = W.new_instance(state, kind,
            target_ref=originals[0]['target_ref'] if kind == 'TRH' else None,
            discovery_brief_ref=originals[0]['source_ref'] if kind == 'FDH' else None,
            discovery_scope=discovery, survey_scope=survey_scope)
        event = W.event(state, 'CREATE_INSTANCE', {'instance': instance})
        expected = W.apply_control(state, event)
        self.store.commit_control(event)
        self._same_output(expected)
        self.instance_id = instance['instance_id']
        self.heads = tuple(h['commit'] for h, _ in self.store.history())
        self.state_digest = sha(canonical(self.store.read_snapshot()))
        self.used = False

    def _same_output(self, expected):
        from pmrh.adapters.storage.journal import _persistent
        require(_persistent(expected) == _persistent(self.store.read_snapshot()),
                'SETUP_PREFIX_INVALID', 'Native setup output differs')

    def verify(self, store):
        require(not self.used and store.root == self.store.root and
                tuple(h['commit'] for h, _ in store.history()) == self.heads and
                sha(canonical(store.read_snapshot())) == self.state_digest,
                'AUTHORIZATION_REQUIRED', 'Fresh setup capability no longer matches')


class ControlNativeBridge:
    """Static reducer selection owned by trusted legacy composition only."""
    def __init__(self, store, *, setup=None):
        self.store = store
        self.setup = setup

    def activate(self, state):
        require(type(self.setup) is SyntheticSetup, 'AUTHORIZATION_REQUIRED', 'Fresh setup capability required')
        self.setup.verify(self.store)
        return deepcopy(state)

    def _freeze_call(self, state, candidate):
        """Freeze on the real committed HEAD with a proven visit annotation.

        Native preview is disposable validation, never a pretend committed
        snapshot. The original freezer and scientific input guards stay intact.
        """
        import pmrh.adapters.storage.control as D
        from pmrh.adapters.storage.journal import _persistent
        from . import execution, scheduler, tasks
        index = self.store._control_index
        require(state.get('synthetic_test_only') is True and index is not None and
                index.states.get(state.get('knowledge_commit')) == _persistent(state),
                'AUTHORIZATION_REQUIRED', 'Verified current synthetic control snapshot required')
        plan, bound = D.visit_plan(state, candidate, index.visit_origins)
        grant = state['budget_grants'].get(candidate.get('budget_grant_id'))
        require(grant is not None, 'AUTHORIZATION_REQUIRED', 'Canonical native grant required')
        policy = grant['execution_policy']
        selected = scheduler.plan(state, [candidate['instance_id']], policy)['selected']
        require(any(D.without_visit(row) == D.without_visit(candidate) for row in selected),
                'AUTHORIZATION_REQUIRED', 'Exact selected native duty required')
        if plan['opening'] is not None:
            preview = execution.apply_event(state, plan['opening'], self.store.read_blob)
            require(_persistent(preview) == _persistent(D.visit_effects(state, plan)),
                    'CAPABILITY_VIOLATION', 'Closed original visit preview required')
        task = tasks.freeze(self.store, state, bound, policy)
        D.task_visit_link(state, state['knowledge_commit'], task, bound, plan)
        return task, bound, plan

    def _verify_frozen_call(self, state, command):
        import pmrh.adapters.storage.control as D
        p = command['payload']; project = state['project_id']
        candidate = D.read_json(self.store, p['candidate_ref'], project)
        task, bound, plan = self._freeze_call(state, candidate)
        require(canonical(task) == D.read_ref(self.store, p['task_ref'], project) and
                canonical(bound) == D.read_ref(self.store, p['candidate_ref'], project),
                'ORIGINAL_BYTES_MISMATCH', 'Full frozen task and candidate bytes must match at the same HEAD')
        return dict(head=state['knowledge_commit'], command=sha(canonical(command)),
                    task=sha(canonical(task)), candidate=sha(canonical(bound)), plan=plan)

    def _prepare_reserve_only(self, state, task, candidate, at):
        from . import execution
        prepared = execution.apply_event(state, execution.event('PREPARE',
            {'task': task, 'candidate': candidate, 'max_workers': 8, 'issued_at': at}), self.store.read_blob)
        return execution.apply_event(prepared, execution.event('RESERVE',
            {'request_id': task['request_id'], 'executor_contract': task['executor_contract'],
             'model_policy': task['model_policy'], 'execution_kind': 'SYNTHETIC_TEST_ONLY', 'issued_at': at}), self.store.read_blob)

    def prepare(self, state, task, candidate, at):
        import pmrh.adapters.storage.control as D
        from . import execution
        plan, bound = D.visit_plan(state, candidate, self.store._control_index.visit_origins)
        require(bound == candidate, 'AUTHORIZATION_REQUIRED', 'Derived visit must already be frozen')
        D.task_visit_link(state, state['knowledge_commit'], task, candidate, plan)
        opened = execution.apply_event(state, plan['opening'], self.store.read_blob) if plan['opening'] else deepcopy(state)
        self.store._fault('after_control_visit')
        result = self._prepare_reserve_only(opened, task, candidate, at)
        expected = D.visit_effects(state, plan)
        require(result['visits'] == expected['visits'] and result['missions'] == expected['missions'],
                'CAPABILITY_VIOLATION', 'Preparation cannot rewrite visits or missions')
        return result

    def send_check(self, state, request_id, prepared, at):
        """Re-run original mutable admission guards without a second charge.

        Only this reservation is removed in a private validation snapshot. No
        validation snapshot or restored allowance is ever published.
        """
        import pmrh.adapters.storage.control as D
        request = state['requests'][request_id]
        require(request['execution_state'] == 'RESERVED' and not request['fenced'] and
                request['admission']['send_phase'] == 'READY', 'EXISTING_REQUEST', 'Only the original READY boundary can send')
        index = self.store._control_index
        require(index.operations[request['admission']['operation_id']]['command'] == prepared,
                'ORIGINAL_BYTES_MISMATCH', 'Original validated CALL required')
        candidate = D.read_json(self.store, prepared['payload']['candidate_ref'], state['project_id'])
        original_task = D.read_json(self.store, prepared['payload']['task_ref'], state['project_id'])
        historical = index.states[prepared['expected_head']]
        origins = {vid:index.visit_origins[vid] for vid in historical['visits']}
        plan, bound = D.visit_plan(historical, candidate, origins)
        require(bound == candidate and original_task == state['tasks'][request['task_id']],
                'ORIGINAL_BYTES_MISMATCH', 'Original frozen visit/task binding required')
        D.task_visit_link(historical, prepared['expected_head'], original_task, candidate, plan)
        visit = plan['visit']; vid = visit['visit_id']
        require(state['visits'].get(vid) == dict(visit, outcome=None, exit_evidence=[], unperformed_duties=[]) and
                state['missions'][visit['mission_id']]['stage_visit_ids'].count(vid) == 1 and
                state['execution_events'].get(index.visit_origins[vid]['opening']['event_id']) == index.visit_origins[vid]['opening'],
                'CONTROL_INVALID', 'Original open visit and opening evidence required')
        shadow = deepcopy(state)
        task = shadow['tasks'].pop(request['task_id'])
        shadow['requests'].pop(request_id)
        grant = shadow['retry_grants'][candidate['consumer']['retry_grant_id']]
        grant['remaining_uses'] += 1
        group = shadow['attempt_groups'][task['attempt_group_key']]
        group['request_ids'] = [r for r in group['request_ids'] if r != request_id]
        group['highest_sample_slot'] = max((r['sample_slot'] for r in shadow['requests'].values()
                                         if r['attempt_group_key'] == task['attempt_group_key']), default=0)
        for strategy in shadow['strategies'].values():
            if strategy.get('active_main_request_id') == request_id:
                strategy['active_main_request_id'] = None
        for direction in shadow.get('human_directions', {}).values():
            if direction.get('request_id') == request_id:
                direction['request_id'] = None
        # Original generated PREPARE/RESERVE events must not hit legacy duplicate
        # returns while validating this current send boundary.
        shadow['execution_events'] = {key: value for key, value in shadow['execution_events'].items()
            if not (value.get('event_type') in {'PREPARE', 'RESERVE'} and
                    (value.get('payload', {}).get('request_id') == request_id or
                     value.get('payload', {}).get('task', {}).get('request_id') == request_id))}
        checked = self._prepare_reserve_only(shadow, task, candidate, at)
        openings = lambda s: {k:v for k,v in s['execution_events'].items() if v.get('event_type') == 'VISIT_OPENED'}
        require(checked['visits'] == state['visits'] and checked['missions'] == state['missions'] and
                openings(checked) == openings(state), 'CAPABILITY_VIOLATION', 'Send validation cannot select or mutate visits')

    def native(self, state, action, event):
        from pmrh.adapters.storage.control import CONTROL_TYPES, STRATEGY_TYPES, COMMUNICATION_LIVE, COMMUNICATION_RECOVERY
        from . import workflow_instances, strategy, communication
        kind = event.get('event_type')
        if action == 'CONTROL_APPLIED':
            require(kind in CONTROL_TYPES, 'UNSUPPORTED_CAPABILITY', 'Closed native control bridge required')
            if kind == 'HUMAN_DECISION':
                require(event['payload']['action'] in {'CONTINUE', 'CONTINUE_DISCOVERY', 'PAUSE', 'END', 'END_WITHOUT_ADOPTION'},
                        'UNSUPPORTED_CAPABILITY', 'Closed human decision subset required')
                instance = state['instances'][event['instance_id']]
                mission = state['missions'].get(instance['current_mission_id'], {})
                action_name = {'CONTINUE_DISCOVERY': 'CONTINUE', 'END_WITHOUT_ADOPTION': 'END'}.get(event['payload']['action'], event['payload']['action'])
                if action_name in mission.get('report_first_actions', []):
                    from .report_catalog import classify
                    report = state['reports'].get(event['payload']['decision_basis'].get('report_ref'))
                    require(report is not None and classify(self.store, state, report) == 'COMPLETED_CURRENT_REPORT',
                            'REPORT_BLOCKED', 'Current intact report required')
            result = workflow_instances.apply_control(state, event)
        elif action == 'STRATEGY_APPLIED':
            require(kind in STRATEGY_TYPES, 'UNSUPPORTED_CAPABILITY', 'Closed strategy bridge required')
            result = strategy.apply_event(state, event, self.store.read_blob)
        else:
            require(action == 'COMMUNICATION_APPLIED' and kind in COMMUNICATION_LIVE | COMMUNICATION_RECOVERY,
                    'UNSUPPORTED_CAPABILITY', 'Closed communication bridge required')
            result = communication.apply_event(state, event, self.store.read_blob)
        return result

    def sent(self, state, request_id):
        from .strategy import request_sent
        request_sent(state, state['tasks'][state['requests'][request_id]['task_id']])

    def capture(self, state, request_id, receipt, at):
        from . import execution, input_delivery
        request = state['requests'][request_id]
        raw = self.store.read_blob(receipt.raw_output_ref.sha256)
        require(sha(raw) == receipt.raw_output_ref.sha256, 'ORIGINAL_BYTES_MISMATCH', 'Original sealed capture required')
        payload = dict(request_id=request_id, execution_id=request['execution_id'],
                       capture_ref=receipt.raw_output_ref.sha256, issued_at=at)
        task = state['tasks'][request['task_id']]
        if task.get('communication_contract'):
            binding = input_delivery.capture_binding(state, request_id)
            payload.update(binding)
            actual = self.store.read_blob(receipt.actual_input_manifest_ref.sha256)
            require(actual == canonical(input_delivery.manifest(state, request_id)),
                    'INPUT_DELIVERY_INVALID', 'Capture must seal the actual input manifest')
        return execution.apply_event(state, execution.event('CAPTURE', payload), self.store.read_blob)

    def science(self, state, request_id, capture):
        from . import changes
        request = state['requests'][request_id]; task = state['tasks'][request['task_id']]
        require(request['capture_ref'] == capture.sha256 and request['execution_kind'] == 'SYNTHETIC_TEST_ONLY',
                'ORIGINAL_BYTES_MISMATCH', 'Original synthetic capture required')
        for binding in task.get('read_set', []):
            require(self.store.read_record(binding['record_ref']) == state['records'][binding['record_ref']], 'RECORD_CHANGED', 'Exact input record required')
        raw = self.store.read_blob(capture.sha256)
        proposal = changes.validate_response(task, state, raw, 'live', self.store.read_blob)
        proposal = changes.revalidate(proposal, state, blob_get=self.store.read_blob)
        for digest_value, data in proposal.get('blobs', {}).items():
            require(self.store.put_blob(data) == digest_value, 'BLOB_CHANGED', 'Validated bytes differ')
        return changes.apply_validated(state, proposal), proposal.get('accepted_request_bindings', [])

    def guidance(self, state, direction):
        from . import strategy
        event = strategy.event('HUMAN_DIRECTION_SUBMITTED', dict(instance_id=direction['instance_id'],
            mission_id=direction['mission_id'], direction=direction))
        return strategy.apply_event(state, event, self.store.read_blob)
