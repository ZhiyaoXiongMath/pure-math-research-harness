"""Real native setup, journal, admission and out-of-band synthetic authority.

Run only through offline_control.py. No fixture patches canonical state or
replaces a reducer; rejected calls must leave the actual native HEAD intact.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest

from pmrh.application.control import AuthorityRegistry, Control, Session
from pmrh.application.read_projections import budget_remaining, control_lane_closed
from pmrh.adapters.storage import control as D
from pmrh.adapters.storage.pool import Pool, RootBinding
from pmrh.ports.dto import core as C, enums as E, events as V, execution as X, specs as S
from research_studio.storage_compat import SyntheticSetup, ControlNativeBridge
from research_studio import workflow_instances as W, obligations as O, strategy, scheduler, tasks
from research_studio.util import canonical, identity, sha, loads, PMRSError
from tests.devpr02 import fixtures as DTO
from tests.devpr05.fixtures import scientific_policy

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
TIME = C.TimePoint(utc='2026-10-16T00:00:00Z', clock_source=E.ClockSource.SYNTHETIC)


class Boundary:
    def __init__(self):
        self.effects = 0

    def first_effect(self):
        self.effects += 1


class Harness:
    def __init__(self, root, *, kind='TRH', activate=True, pool=None):
        self.root = Path(root)
        inputs = {'TRH': (b'For every integer n, n + 0 = n.',),
                  'FDH': (b'Compare integer addition patterns.', b'Keep the integers and addition fixed.',
                          b'Vary only the candidate statements.'), 'SURVEY': ()}[kind]
        self.setup = SyntheticSetup(self.root/'project', kind=kind, inputs=inputs,
            survey_scope={'topic':'Synthetic addition survey', 'questions':['Which original statements remain open?']} if kind == 'SURVEY' else None)
        self.store = self.setup.store
        self.iid = self.setup.instance_id
        self.project = self.store._marker()['project_id']
        self.scope = dict(project_id=self.project, instance_id=self.iid)
        self.binding = RootBinding.register('fixture-project' if pool is None else 'fixture-project:'+self.project, self.store.root)
        if pool is None:
            runtime = self.root/'runtime'; runtime.mkdir()
            self.pool = Pool(RootBinding.register('fixture-runtime', runtime), 'synthetic-test-pool', [self.binding])
        else:
            # This is the trusted fixture assembly channel, outside commands
            # and project data. Registration still checks the native prefix.
            self.pool = pool
            self.pool.roots[self.binding.binding_id] = self.binding
        self.genesis = self.setup.heads[0]
        self.key = self.pool.register(self.binding.binding_id, genesis=self.genesis, project=self.project)
        self.registry = AuthorityRegistry(clock=lambda: NOW)
        self.storage = D.ControlStorage(self.store, ControlNativeBridge(self.store, setup=self.setup))
        self.control = Control(self.storage, self.pool, self.registry, binding_id=self.binding.binding_id)
        self.serial = 0
        self.producer = self.blob('producer', b'SYNTHETIC_TEST_ONLY original producer', raw=True)
        self.binding_ref = self.blob('runner-binding', b'SYNTHETIC_TEST_ONLY bounded execution binding', raw=True)
        self.operator = self.session(human=True)
        self.service = self.session()
        self.boundary = Boundary(); self.storage.register_boundary(self.boundary, self.scope)
        if activate:
            profile = D.record('PROFILE', profile='SYNTHETIC_TEST_ONLY', project_id=self.project,
                genesis_commit=self.genesis, setup_head=self.setup.heads[-1], resource_policy='COMPAT_8_20_SURVEY1', pool_id=self.pool.pool_id)
            self.activation = self.command('ACTIVATED', dict(profile_ref=self.blob('profile', profile), owner_id='fixture-owner', backend_binding_ref=None))
            self.control.apply(self.activation, self.operator)

    def blob(self, name, value, *, raw=False):
        return D.exact(self.store, self.project, 'synthetic:'+name, value, raw=raw)

    def session(self, *, actions=None, human=False, owner='fixture-owner', request_ids=None, scope=None, proposal_only=False, acting_request_id=None):
        return self.registry.authenticate(scope=scope or self.scope, root_binding_id=self.binding.binding_id,
            principal_ref=self.blob('principal:'+str(human), b'SYNTHETIC authenticated fixture principal', raw=True),
            authn_evidence_ref=self.blob('authentication', b'Out-of-band fixture registration', raw=True),
            authority_ref=self.blob('authority', b'Explicit synthetic-only scope grant', raw=True),
            actions=set(D.PAYLOAD_FIELDS)|{'RECOVER_RECEIPT'} if actions is None else set(actions),
            issued_at=NOW-timedelta(minutes=1), expires_at=NOW+timedelta(hours=1), owner_id=owner,
            human=human, proposal_only=proposal_only, request_ids=request_ids, acting_request_id=acting_request_id)

    def command(self, action, payload):
        state = self.store.read_snapshot(); instance = state['instances'][self.iid]
        self.serial += 1
        return dict(schema=D.EVENT_SCHEMA, type=action, operation_id='operation:'+str(self.serial), idempotency_key='key:'+str(self.serial),
            scope=self.scope, expected_head=state['knowledge_commit'], owner_epoch=instance.get('ownership', {}).get('owner_epoch', 0),
            control_version=D.current_version(instance), payload=payload)

    def grant(self):
        state = self.store.read_snapshot()
        mid = state['instances'][self.iid]['current_mission_id']
        grant = state['budget_grants'][state['missions'][mid]['budget_grant_id']]
        return self.blob('grant:'+grant['budget_grant_id']+':'+str(grant['grant_revision']), grant)

    def authorize(self, limit=3, *, attempts=3, name='synthetic', communication=False,
                  threshold='WORK_DISPOSITION_RECORDED'):
        state = self.store.read_snapshot(); instance = state['instances'][self.iid]
        mid = 'MISSION-'+name; gid = 'BUDGET-'+name; oid = 'OB-'+name; bid = 'BINDING-'+name
        retry_id = 'RETRY-'+name
        refs = [instance['target_ref']] if instance['target_ref'] else []
        source_refs = list(state['sources'])
        question = ('Read the exact original scope and report only evidence-supported progress and open gaps.'
                    if name == 'synthetic' else 'Examine the separately authorized scope question '+name+' and report its unresolved assumptions.')
        criterion = self.store.put_blob(question.encode())
        main = instance['kind'] != 'SURVEY'
        consumer = dict(binding_id=bid, instance_id=self.iid, mission_id=mid,
            stage_id='MAIN_'+instance['kind'] if main else 'S1', role='MAIN_DECIDE' if main else 'SEARCH_PLAN',
            retry_grant_id=retry_id, method_ref='MAIN_EVENT_DECISION' if main else 'SURVEY_SEARCH',
            scope={'target_refs':refs}, entry_basis={'main_event_key':'synthetic-initial'} if main else {},
            input_refs=refs, source_refs=source_refs, threshold=threshold, success_criterion=criterion, ready_since=0)
        if main:
            consumer.update(actor_kind='MAIN', work_purpose='MAIN_STRATEGY', strategy_ref=strategy.strategy_id(self.iid), strategy_revision=0, round_number=1)
        else:
            from research_studio import survey
            context = survey.task_context(state, self.iid, [], [], 'S1')
            consumer.update(survey_context=context, method_ref='SURVEY_SEARCH_PLAN',
                entry_basis={'survey_scope_fingerprint':context['scope_fingerprint'], 'survey_stage':'S1'})
        obligation = O.make(oid, 'ACCOUNT' if main else 'MATERIAL', refs, criterion, consumer_bindings=[consumer],
                            created_by='MAIN_EVENT_ADMISSION' if main else 'AUTHORIZED_SYNTHETIC_SURVEY', effect='MAIN_DECISION_REQUIRED' if main else 'BOUNDED_SCIENTIFIC_DUTY')
        scope_value = dict(target_refs=refs, source_refs=source_refs, allow_derived_work=True, max_research_attempts=attempts, reports=False)
        scope_value['autoflow'] = dict(schema='pmrs.harness-runtime/4.2.2', main_enabled=main, selected_refs=refs,
            source_refs=source_refs, intent_source_ref=source_refs[0] if source_refs else None, method_version='pmrs.harness-methods/4.2.2')
        if instance['kind'] == 'FDH':
            scope_value['discovery_scope'] = instance['discovery_scope']
        if not main:
            scope_value['survey_scope'] = instance['survey_scope']
        mission = dict(mission_id=mid, instance_id=self.iid, intent_ref=self.store.put_blob(b'Explicit synthetic finite test mission.'),
            authorized_scope=scope_value, budget_grant_id=gid, obligations=[obligation],
            retry_grants=[dict(grant_id=retry_id, obligation_id=oid, method_ref=consumer['method_ref'], max_research_attempts=attempts)])
        self.policy = scientific_policy()
        if communication:
            # Native task freezing, before PREPARE, owns these permissions.
            # An empty override selects the original finite communication policy.
            self.policy['communication'] = {}
        budget = dict(budget_grant_id=gid, max_calls=limit, max_workers=8, execution_policy=self.policy)
        event = W.authorize_event(state, self.iid, mission, budget)
        self.control.apply(self.command('CONTROL_APPLIED', {'native_event':event}), self.operator)
        if main:
            native = strategy.event('STRATEGY_INITIALIZED', dict(instance_id=self.iid, mission_id=mid,
                target_or_scope_ref=instance['target_ref'] or instance['discovery_brief_ref'], previous_revision=None))
            self.control.apply(self.command('STRATEGY_APPLIED', {'native_event':native}), self.service, grant_ref=self.grant())

    def prepare(self, *, publish=True, actor=None):
        state = self.store.read_snapshot(); instance = state['instances'][self.iid]
        plan = scheduler.plan(state, [self.iid], self.policy)
        selected = [c for c in plan['selected'] if actor is None or (c['consumer'].get('actor_kind')=='MAIN') == (actor=='MAIN')]
        assert selected, plan['waits']
        candidate = selected[0]
        task, candidate, visit = self.storage.native._freeze_call(state, candidate)
        epoch = instance['ownership']['owner_epoch']; version = D.current_version(instance)
        identity_value = C.InvocationIdentity(scope=C.Scope(**self.scope),
            logical_agent_id='MAIN-'+self.iid if task.get('actor_kind') == 'MAIN' else 'worker:'+candidate['consumer']['binding_id'],
            invocation_id='invocation:'+task['request_id'], request_id=task['request_id'],
            execution_id=identity({'request':task['request_id']}, 'EXECUTION-'), attempt_id=task['attempt_key'])
        grant = self.grant()
        reservation = D.record('RESERVATION', reservation_id='reservation:'+task['request_id'], identity=identity_value.to_wire(),
            grant_ref=grant, unit='AGENT_INVOCATION', amount=1, owner_epoch=epoch, control_version=version)
        reservation_ref = self.blob(reservation['reservation_id'], reservation)
        endpoint = C.ExactRef.from_wire(self.blob('no-endpoint', b'SYNTHETIC no external endpoint', raw=True))
        model = S.ModelSelection(provider_id='synthetic', model_id=task['model_policy']['model'], effort=task['model_policy']['reasoning_effort'],
            service_tier=task['model_policy']['service_tier'], endpoint_ref=endpoint, credential_ref=endpoint,
            tool_definition_refs=(), response_schema_ref=None, parameters=())
        cap = replace(DTO.manifest(), test_receipt_refs=(C.ExactRef.from_wire(self.blob('capability-proof', b'SYNTHETIC_TEST_ONLY capability evidence', raw=True)),))
        manifest_ref = self.blob('manifest', cap.to_wire())
        original_scope = instance['target_ref'] if instance['kind'] == 'TRH' else instance['discovery_scope'] if instance['kind'] == 'FDH' else instance['survey_scope']
        def reference(name, value):
            return C.ExactRef.from_wire(self.blob(name, value))
        spec = S.AgentInvocationSpec(**self.scope, research_goal_id=task['mission_id'], logical_agent_id=identity_value.logical_agent_id,
            role=E.AgentRole.MAIN if task.get('actor_kind') == 'MAIN' else E.AgentRole.WORKER,
            stage_responsibility=None if task.get('actor_kind') == 'MAIN' else task['stage_id'], purpose=task.get('work_purpose','DEFAULT'),
            invocation_id=identity_value.invocation_id, request_id=task['request_id'], execution_id=identity_value.execution_id,
            attempt_id=identity_value.attempt_id, owner_epoch=epoch, expected_control_version=version,
            original_scope_ref=reference('original-scope', original_scope), method_version='pmrs.harness-methods/4.2.2', guidance_version=0,
            input_manifest_ref=reference('inputs:'+task['task_id'],task['input_manifest']), read_set_digest=sha(canonical(task['read_set'])),
            visibility_policy_ref=reference('visibility',{'profile':'SYNTHETIC_TEST_ONLY'}),
            output_contract_ref=reference('output-contract',task['permission_manifest']),
            communication_contract_ref=reference('communication-contract',task.get('communication_contract',{})),
            runner_binding_ref=C.ExactRef.from_wire(self.binding_ref), authorized_model_selection_ref=reference('model',model.to_wire()),
            budget_grant_ref=C.ExactRef.from_wire(grant), budget_unit=E.BudgetUnit.AGENT_INVOCATION,
            reservation_ref=C.ExactRef.from_wire(reservation_ref), sandbox_policy_ref=reference('sandbox',task['executor_contract']),
            tool_capability_ref=reference('tools',task['permission_manifest']), idempotency_key='invoke:'+task['request_id'],
            parent_invocation_ref=None, correlation_id='synthetic-correlation', execution_mode=E.ExecutionMode.MANAGED_AGENT,
            model_selection=model, capability_requirements=DTO.requirements(cap))
        spec_ref = self.blob('spec:'+task['task_id'], spec.to_wire())
        self.registry.register_manifest(manifest_ref, self.binding_ref, producer_ref=self.producer, spec_ref=spec_ref, identity=identity_value.to_wire())
        value = self.command('CALL_PREPARED', dict(task_ref=self.blob('task:'+task['task_id'],task),
            candidate_ref=self.blob('candidate:'+task['task_id'],candidate), spec_ref=spec_ref, reservation_ref=reservation_ref))
        assert value['expected_head'] == state['knowledge_commit'] == task['knowledge_commit']
        if publish:
            self.control.apply(value, self.service, grant_ref=grant, manifest_ref=manifest_ref)
        return dict(command=value, task=task, candidate=candidate, visit=visit, spec=spec, spec_ref=spec_ref,
                    manifest_ref=manifest_ref, grant_ref=grant)

    def send(self, prepared):
        value = self.command('SEND_STARTED', dict(request_id=prepared['spec'].request_id, send_boundary_id='boundary:'+prepared['spec'].invocation_id))
        self.control.send(value, self.service, grant_ref=self.grant(), manifest_ref=prepared['manifest_ref'], boundary=self.boundary)
        return value

    def dispatch_workers(self, main, count, *, label='scope', stage='P1', role='PLAN', duty='MATERIAL', inputs=None):
        """Ask the original running MAIN strategy bridge for distinct duties."""
        state = self.store.read_snapshot(); st = strategy.current(state, self.iid)
        target = state['instances'][self.iid]['target_ref']
        targets = [target] if target is not None else []
        proposal = dict(schema='pmrs.strategy-proposal/1', base_strategy_revision=st['revision'],
            trigger_refs=list(st['pending_trigger_refs']), route_updates=[], input_plan_proposals=[],
            work_items=[dict(key=label+str(i), stage_id=stage, role=role, purpose='DEFAULT', obligation_type=duty,
                question='Inspect distinct synthetic scope condition '+label+str(i)+'.',
                success_criterion='Report the exact scope condition and its unresolved assumptions.',
                target_refs=targets, input_refs=targets if inputs is None else inputs, source_refs=[], depends_on=[], route_key='', communication_group=None)
                for i in range(count)],
            progress_account=dict(summary='Explicit synthetic bounded work plan.', record_refs=[],
                remaining_difficulties=['The separately named scope conditions remain unexamined.'],
                scope_limitations=['SYNTHETIC_TEST_ONLY'], failed_or_unperformed=['No mathematical conclusion.'],
                covered_binding_ids=[], frontier_complete=False),
            direction_answers=[], next_action='CONTINUE', human_decision_needed=[], no_change_reason=None)
        command = self.command('STRATEGY_APPLIED', {'native_event':{}})
        args = {k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
        with self.control.native_context(self.service, **args, grant_ref=self.grant(), manifest_ref=main['manifest_ref']):
            return strategy.dispatch_from_main(self.store, main['spec'].request_id, proposal, 'dispatch:'+label)

    def dispatch(self, prepared, status, *, receipt_id=None, publish=True):
        spec = prepared['spec']; raw = C.ExactRef.from_wire(self.blob('raw:'+status+':'+str(self.serial), ('SYNTHETIC original '+status).encode(), raw=True))
        identity_value = spec.identity()
        handle = X.InvocationHandle(identity=identity_value, backend_binding_ref=spec.runner_binding_ref, backend_invocation_id=DTO.unknown())
        code = E.ErrorCode.NOT_SENT if status == 'NOT_SENT' else E.ErrorCode.SEND_OUTCOME_UNKNOWN
        error = None if status == 'SENT' else C.port_error(code, E.Operation.START, identity=identity_value, evidence=(raw,))
        receipt = X.DispatchReceipt(status=E.DispatchState(status), handle=handle, observed_at=TIME, raw_evidence_refs=(raw,), error=error)
        receipt_ref = self.blob('dispatch:'+str(self.serial), receipt.to_wire())
        self.registry.register_original(receipt_ref, producer_ref=self.producer, binding_ref=self.binding_ref,
            identity=identity_value.to_wire(), raw_refs=[raw.to_wire()])
        wrapper = D.record('RECEIPT', receipt_id=receipt_id or 'receipt:'+str(self.serial), identity=identity_value.to_wire(),
            binding_ref=self.binding_ref, producer_ref=self.producer, receipt_kind='DISPATCH', receipt_ref=receipt_ref)
        value = self.command('EXECUTION_RECEIVED', {'receipt':wrapper})
        if publish:
            self.control.apply(value, self.service)
        return value

    def pause(self):
        native = W.event(self.store.read_snapshot(), 'PAUSE', {'reason':'Explicit synthetic pause'}, instance_id=self.iid)
        return self.control.apply(self.command('CONTROL_APPLIED', {'native_event':native}), self.operator)

    def receipt(self, prepared, kind, receipt, *, receipt_id=None, publish=True):
        value = receipt.to_wire(); reference = self.blob('receipt:'+str(self.serial), value)
        if kind == 'CAPTURE':
            raw_refs = [receipt.raw_output_ref, receipt.actual_input_manifest_ref, *receipt.raw_event_refs]
        elif kind == 'CANCELLATION':
            raw_refs = [*receipt.request_evidence_refs, *receipt.termination_evidence_refs]
        else:
            raw_refs = list(receipt.raw_evidence_refs)
        self.registry.register_original(reference, producer_ref=self.producer, binding_ref=self.binding_ref,
            identity=prepared['spec'].identity().to_wire(), raw_refs=[r.to_wire() for r in raw_refs])
        wrapper = D.record('RECEIPT', receipt_id=receipt_id or 'observation:'+str(self.serial),
            identity=prepared['spec'].identity().to_wire(), binding_ref=self.binding_ref,
            producer_ref=self.producer, receipt_kind=kind, receipt_ref=reference)
        command = self.command('EXECUTION_RECEIVED', {'receipt':wrapper})
        if publish:self.control.apply(command, self.service)
        return command

    def observation(self, prepared, status, *, publish=True):
        raw = C.ExactRef.from_wire(self.blob('original-observation', ('SYNTHETIC original '+status).encode(), raw=True))
        receipt = X.ExecutionObservation(identity=prepared['spec'].identity(), state=E.ExecutionState(status),
            observed_at=TIME, raw_evidence_refs=(raw,), actual_model_id=DTO.unknown(), provider_request_id=DTO.unknown())
        return self.receipt(prepared, 'OBSERVATION', receipt, publish=publish)

    def capture(self, prepared, raw=None):
        from research_studio import demo, communication, input_delivery
        task = prepared['task']; rid = prepared['spec'].request_id
        if raw is None:
            envelope = loads(demo.response(task, self.store.read_snapshot(), blob_get=self.store.read_blob))
            authored = envelope['payload'].get('knowledge_change', envelope['payload'])
            if 'strategy_proposal' in authored:authored['strategy_proposal']['next_action'] = 'CONTINUE'
            raw = canonical(envelope)
        if task.get('communication_contract'):
            native = communication.event('INPUT_WINDOW_SEALED', dict(request_id=rid, execution_id=prepared['spec'].execution_id))
            self.control.apply(self.command('COMMUNICATION_APPLIED', {'native_event':native}), self.service)
        output = C.ExactRef.from_wire(self.blob('original-output', raw, raw=True))
        inputs = C.ExactRef.from_wire(self.blob('actual-inputs', input_delivery.manifest(self.store.read_snapshot(),rid)))
        seal = C.ExactRef.from_wire(self.blob('capture-seal', b'SYNTHETIC original sealed bytes', raw=True))
        receipt = X.CaptureReceipt(capture_id='capture:'+rid, identity=prepared['spec'].identity(), raw_output_ref=output,
            actual_input_manifest_ref=inputs, raw_event_refs=(seal,), sealed_at=TIME)
        self.receipt(prepared, 'CAPTURE', receipt)
        return output.to_wire(), raw

    def page(self, prepared, events=(), *, start=None, status=E.PageStatus.COMPLETE, gap=None, publish=True):
        inbox = self.store.read_snapshot()['requests'][prepared['spec'].request_id]['execution_inbox']
        before = V.EventCursor.from_wire(inbox['cursor']) if start is None else start
        after = replace(before, after_sequence=events[-1].sequence, last_event_id=events[-1].envelope.event_id) if events else before
        page = V.RunnerEventPage(requested_cursor=before, next_cursor=after, status=status, events=tuple(events), duplicate_event_ids=(), gap=gap)
        command = self.command('INBOX_PAGE_RECEIVED', dict(request_id=prepared['spec'].request_id,
            producer_ref=self.producer, binding_ref=self.binding_ref, page_ref=self.blob('page',page.to_wire())))
        if publish:self.control.apply(command,self.service)
        return command, page

    def event(self, prepared, sequence, status='RUNNING', *, event_id=None):
        command = self.observation(prepared,status,publish=False)
        reference = C.ExactRef.from_wire(command['payload']['receipt']['receipt_ref'])
        original = X.ExecutionObservation.from_wire(D.read_json(self.store,reference.to_wire(),self.project))
        envelope = V.EventEnvelope(event_id=event_id or 'event:'+str(sequence), event_type=status,
            event_domain=E.EventDomain.EXECUTION, status=E.EventStatus.OBSERVATION, **self.scope,
            journal_id=DTO.unknown(), aggregate_id=prepared['spec'].invocation_id, aggregate_sequence=None,
            journal_sequence=None, commit_ref=None, occurred_at=None, observed_at=TIME, committed_at=None,
            clock_source=E.ClockSource.SYNTHETIC, actor_principal_ref=C.ExactRef.from_wire(self.producer), actor_kind='SYNTHETIC',
            correlation_id='synthetic-stream', causation_id=None, operation_id=None, idempotency_key=None,
            invocation_id=prepared['spec'].invocation_id, execution_id=prepared['spec'].execution_id,
            request_id=prepared['spec'].request_id, attempt_id=prepared['spec'].attempt_id, activation_id=None,
            logical_main_id=prepared['spec'].logical_agent_id if prepared['spec'].role is E.AgentRole.MAIN else None,
            owner_epoch=prepared['spec'].owner_epoch, control_version=prepared['spec'].expected_control_version,
            backend_id=DTO.unknown(), provider_id=DTO.unknown(), provider_request_id=DTO.unknown(),
            backend_binding_ref=prepared['spec'].runner_binding_ref, payload_ref=reference,
            raw_evidence_ref=original.raw_evidence_refs[0], payload_sha256=reference.sha256,
            classification=E.Classification.SYNTHETIC_TEST_ONLY, trust_origin=E.TrustOrigin.SYNTHETIC_TEST_ONLY,
            visibility_policy_ref=prepared['spec'].visibility_policy_ref)
        return V.RunnerEvent(sequence=sequence, kind=E.RunnerEventKind.TERMINATED if status=='TERMINATED' else E.RunnerEventKind.STARTED,
            envelope=envelope, raw_event_ref=original.raw_evidence_refs[0])

    def slot(self, prepared, *, publish=True):
        state = self.store.read_snapshot(); rid=prepared['spec'].request_id; call=state['requests'][rid]['admission']
        with self.pool.locked():
            ledger=self.pool.read();token=self.pool.token(self.key,self.iid,call['operation_id'],rid,ledger)
            revision=ledger['revision']+int(token not in ledger['slots'])
        command=self.command('SLOT_CONFIRMED',dict(request_id=rid,pool_id=self.pool.pool_id,token=token,pool_revision=revision))
        if publish:self.storage.acquire_slot(self.control,command,self.service,grant_ref=self.grant(),manifest_ref=prepared['manifest_ref'])
        return command

    def export(self, path, command, *, mode='apply', grant_ref=None, manifest_ref=None, fault=None, barrier=False, remain_live=False):
        """Trusted fixture assembly channel, separate from command/evidence roots."""
        value=dict(root=str(self.root), scope=self.scope, key=self.key, genesis=self.genesis,
            producer=self.producer, binding_ref=self.binding_ref, serial=self.serial,
            manifests=list(self.registry._manifests.items()), originals=list(self.registry._producers.items()),
            command=command, mode=mode, grant_ref=grant_ref, manifest_ref=manifest_ref, fault=fault, barrier=barrier, remain_live=remain_live)
        # Registry dictionary keys are canonical bytes, so persist their exact
        # JSON input separately; the child re-registers each trusted original.
        for field in ('manifests','originals'):
            value[field]=[(json.loads(key),row) for key,row in value[field]]
        Path(path).write_bytes(canonical(value))
        return path


class ControlTests(unittest.TestCase):
    def test_visit_prepare_binds_native_role_and_stage(self):
        for kind in ('TRH', 'FDH', 'SURVEY'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp, kind=kind); h.authorize(4)
                original = deepcopy(h.store.read_snapshot()['instances'][h.iid])
                first = h.prepare(); prepared = [first]
                if kind != 'SURVEY':
                    self.assertIsNone(first['spec'].stage_responsibility)
                    self.assertFalse(h.pool.read()['slots'])
                    h.send(first); h.dispatch(first, 'SENT')
                    h.dispatch_workers(first, 1, stage='P1' if kind == 'TRH' else 'D1',
                        role='PLAN' if kind == 'TRH' else 'RESEARCH', duty='MATERIAL' if kind == 'TRH' else 'CALIBRATE')
                    prepared.append(h.prepare(actor='WORKER'))
                else:
                    self.assertIsNone(original['ownership']['logical_main_id'])
                    h.slot(first)
                    self.assertEqual(len(h.pool.read()['slots']), 1)
                state = h.store.read_snapshot()
                self.assertEqual(len(state['visits']), len(prepared))
                self.assertEqual(budget_remaining(state, 'BUDGET-synthetic'), 4-len(prepared))
                for p in prepared:
                    task, candidate = p['task'], p['candidate']; visit = state['visits'][task['visit_id']]
                    self.assertEqual(task['visit_id'], candidate['consumer']['visit_id'])
                    self.assertEqual(task['obligation_bindings'], visit['assigned_obligation_bindings'])
                    for field in ('instance_id', 'mission_id', 'stage_id', 'stage_spec_digest'):
                        self.assertEqual(task[field], visit[field])
                    self.assertEqual(visit['entry_basis'], candidate['consumer']['entry_basis'])
                    self.assertEqual(state['missions'][task['mission_id']]['stage_visit_ids'].count(task['visit_id']), 1)
                    self.assertEqual(state['requests'][task['request_id']]['execution_kind'], 'SYNTHETIC_TEST_ONLY')
                for field in ('target_ref', 'discovery_scope', 'discovery_brief_ref', 'survey_scope'):
                    self.assertEqual(state['instances'][h.iid].get(field), original.get(field))
        # Unsupported role/stage or a supplied identity cannot create authority.
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare(publish=False);state=h.store.read_snapshot();head=h.store._head()
            for field, value in (('role','HOST'),('role','HUMAN'),('stage_id',None),('visit_id','VISIT-forged')):
                candidate=deepcopy(p['candidate']);candidate['consumer'][field]=value
                if field in candidate:candidate[field]=value
                with self.subTest(field=field,value=value), self.assertRaises(PMRSError):
                    h.storage.native._freeze_call(state,candidate)
                self.assertEqual(h.store._head(),head)
            self.assertFalse(h.store.read_snapshot()['visits'])

    def test_visit_reuse_preserves_original_retry_and_identity(self):
        from research_studio import demo
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            # The human's initial duty requires an artifact, not merely an
            # attempt disposition. A native NO_RESULT therefore stays open.
            h=Harness(tmp,kind='SURVEY');h.authorize(3,attempts=2,threshold='ARTIFACT_AVAILABLE')
            first=h.prepare();h.slot(first);h.send(first);h.dispatch(first,'SENT')
            envelope=loads(demo.response(first['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            authored=envelope['payload']['knowledge_change'];self.assertEqual(authored['operations'],[])
            authored['work_outcome']='NO_RESULT'
            for effect in authored['obligation_effects']:
                effect.update(work_disposition='NO_RESULT',resolution_proposal='UNRESOLVED',evidence_refs=[])
            capture,_=h.capture(first,canonical(envelope))
            h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=first['task']['request_id'],capture_ref=capture)),h.service)
            h.observation(first,'TERMINATED');h.storage.release_slot(h.control,h.scope,first['task']['request_id'],h.service)
            before=h.store.read_snapshot();bid=first['task']['obligation_bindings'][0]
            self.assertEqual(before['obligations'][bid['obligation_id']]['projection']['consumer_resolutions'][bid['binding_id']],'UNRESOLVED')
            second=h.prepare();after=Store(h.store.root).read_snapshot()
            self.assertIsNone(second['visit']['opening'])
            self.assertEqual(after['visits'],before['visits']);self.assertEqual(after['missions'],before['missions'])
            self.assertEqual(second['task']['visit_id'],first['task']['visit_id'])
            self.assertEqual(second['task']['attempt_group_key'],first['task']['attempt_group_key'])
            self.assertEqual(second['task']['sample_slot'],first['task']['sample_slot']+1)
            self.assertNotEqual(second['task']['request_id'],first['task']['request_id'])
            self.assertEqual(after['retry_grants'][second['candidate']['consumer']['retry_grant_id']]['remaining_uses'],0)
            self.assertEqual(budget_remaining(after,'BUDGET-synthetic'),1)
            self.assertEqual(sum(e.get('event_type')=='VISIT_OPENED' for e in after['execution_events'].values()),1)
            # A successful duplicate consumes neither a third sample nor a unit.
            result=h.control.apply(second['command'],h.service,grant_ref=second['grant_ref'],manifest_ref=second['manifest_ref'])
            self.assertTrue(result['duplicate']);self.assertEqual(h.store.read_snapshot(),after)
            self.assertFalse(scheduler.plan(after,[h.iid],h.policy)['selected'])

    def test_visit_frozen_command_and_current_duplicate_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare(publish=False);state=h.store.read_snapshot();head=h.store._head()
            again,bound,plan=h.storage.native._freeze_call(state,p['candidate'])
            self.assertEqual(canonical(again),canonical(p['task']))
            self.assertEqual(canonical(bound),canonical(p['candidate']));self.assertEqual(plan,p['visit'])
            self.assertEqual(h.store._head(),head)
            # Correct hashes and manifest registration do not prove frozen bytes.
            for part,field,value in (('task','prompt_ref',h.store.put_blob(b'forged prompt')),
                                     ('candidate','priority',123),('task','visit_id',None)):
                forged=deepcopy(p[part]);forged[field]=value;command=deepcopy(p['command'])
                command['payload'][part+'_ref']=h.blob('forged-'+part,forged)
                with self.subTest(part=part,field=field),self.assertRaises(PMRSError):
                    h.control.apply(command,h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
                self.assertEqual(h.store._head(),head)
            result=h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            after=h.store.read_snapshot()
            self.assertEqual(budget_remaining(after,'BUDGET-synthetic'),0)
            duplicate=h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertTrue(duplicate['duplicate']);self.assertEqual(result['commit'],duplicate['commit'])
            altered=deepcopy(p['command']);candidate=deepcopy(p['candidate']);candidate['consumer']['visit_id']='VISIT-nonexistent'
            altered['payload']['candidate_ref']=h.blob('altered-cached-candidate',candidate)
            with self.assertRaisesRegex(PMRSError,'IDEMPOTENCY_CONFLICT'):
                h.control.apply(altered,h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                h.control.apply(p['command'],h.session(actions=[]),grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertEqual(h.store.read_snapshot(),after)

    def test_visit_send_check_is_reuse_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(4);main=h.prepare();h.send(main);h.dispatch(main,'SENT')
            h.dispatch_workers(main,2,label='visit-send');first=h.prepare(actor='WORKER');second=h.prepare(actor='WORKER')
            self.assertNotEqual(first['task']['visit_id'],second['task']['visit_id'])
            h.slot(first);before=h.store.read_snapshot();openings={k:v for k,v in before['execution_events'].items() if v.get('event_type')=='VISIT_OPENED'}
            self.assertEqual(len(before['visits']),3)
            # Exercise the actual private validation and the real outer send.
            h.storage.native.send_check(before,first['task']['request_id'],first['command'],TIME.utc)
            send=h.send(first);after=h.store.read_snapshot()
            self.assertEqual(after['visits'],before['visits']);self.assertEqual(after['missions'],before['missions'])
            self.assertEqual({k:v for k,v in after['execution_events'].items() if v.get('event_type')=='VISIT_OPENED'},openings)
            self.assertEqual(budget_remaining(after,'BUDGET-synthetic'),1)
            self.assertTrue(h.control.send(send,h.service,grant_ref=h.grant(),manifest_ref=first['manifest_ref'],boundary=h.boundary)['duplicate'])
            self.assertEqual(h.boundary.effects,2)  # MAIN plus first worker.
            h.pause();head=h.store._head()
            with self.assertRaisesRegex(PMRSError,'STALE_CONTROL_VERSION'):
                h.control.send(send,h.service,grant_ref=h.grant(),manifest_ref=first['manifest_ref'],boundary=h.boundary)
            self.assertEqual(h.store._head(),head)

    def assert_denied_actions(self,h,required):
        """Replay actual successful commands after removing their permission."""
        observed=set();head=h.store._head();ledger=h.pool.read();effects=h.boundary.effects
        for _,entry in h.store.history():
            for event in entry['events']:
                action=event.get('type')
                if event.get('schema')!=D.EVENT_SCHEMA or action not in required:continue
                observed.add(action)
                command={k:deepcopy(v) for k,v in event.items() if k!='decision_ref'}
                decision=D.read_json(h.store,event['decision_ref'],h.project)
                denied=h.session(human=True,actions=set(D.PAYLOAD_FIELDS)-{action})
                with self.subTest(denied_duplicate=action):
                    with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                        h.control.apply(command,denied,grant_ref=decision['budget_grant_ref'],manifest_ref=decision['capability_manifest_ref'])
        self.assertEqual(observed,set(required))
        self.assertEqual(h.store._head(),head);self.assertEqual(h.pool.read(),ledger);self.assertEqual(h.boundary.effects,effects)

    def test_F3_native_pool_and_science_bridges_check_current_context_on_retry(self):
        from research_studio import host_pool,changes
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp,kind='SURVEY');h.authorize(2);p=h.prepare();rid=p['spec'].request_id
            def frame(command,session,**extra):
                args={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                return h.control.native_context(session,**args,**extra)
            acquire=h.command('SLOT_CONFIRMED',{})
            extra=dict(grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
            with frame(acquire,h.service,**extra):host_pool.acquire(h.store,rid)
            head=h.store._head();ledger=h.pool.read()
            with frame(acquire,h.service,**extra):host_pool.acquire(h.store,rid)
            with frame(acquire,h.session(actions=set()),**extra):
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):host_pool.acquire(h.store,rid)
            with frame(acquire,h.service,grant_ref=extra['grant_ref'],manifest_ref=h.producer):
                with self.assertRaisesRegex(PMRSError,'CONTROL_INVALID'):host_pool.acquire(h.store,rid)
            self.assertEqual(h.store._head(),head);self.assertEqual(h.pool.read(),ledger)
            h.send(p);h.dispatch(p,'SENT');capture,raw=h.capture(p)
            validated=changes.validate_response(p['task'],h.store.read_snapshot(),raw,'live',h.store.read_blob)
            h.pause();science=h.command('SCIENCE_ADMITTED',{})
            with frame(science,h.service):h.store.commit(validated)
            head=h.store._head()
            with frame(science,h.service):h.store.commit(validated)
            with frame(science,h.session(actions=set())):
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):h.store.commit(validated)
            self.assertEqual(h.store._head(),head)
            self.assertEqual(h.store.read_snapshot()['requests'][rid]['acceptance_state'],'ACCEPTED')
            self.assertEqual(h.store.read_blob(capture['sha256']),raw)
            h.observation(p,'TERMINATED');release=h.command('EXECUTION_RECEIVED',{})
            with frame(release,h.service):host_pool.release(h.store,rid)
            head=h.store._head();ledger=h.pool.read()
            with frame(release,h.service):host_pool.release(h.store,rid)
            with frame(release,h.session(actions=set())):
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):host_pool.release(h.store,rid)
            stale={**release,'owner_epoch':0}
            with frame(stale,h.service):
                with self.assertRaisesRegex(PMRSError,'STALE_CONTROL_VERSION'):host_pool.release(h.store,rid)
            self.assertEqual(h.store._head(),head);self.assertEqual(h.pool.read(),ledger)

    def test_F3_strategy_and_guidance_facades_check_before_cached_success(self):
        from research_studio import main_session
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2)
            def frame(action,session,grant=None):
                command=h.command(action,{})
                args={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                return h.control.native_context(session,**args,grant_ref=grant)
            for invoke in (lambda:strategy.initialize(h.store,h.iid),lambda:strategy.trigger(h.store,h.iid,'SYNTHETIC_EVENT','P1')):
                with frame('STRATEGY_APPLIED',h.service,h.grant()):invoke()
                head=h.store._head()
                with frame('STRATEGY_APPLIED',h.service,h.grant()):invoke()
                with frame('STRATEGY_APPLIED',h.session(actions=set()),h.grant()):
                    with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):invoke()
                with frame('STRATEGY_APPLIED',h.service):
                    with self.assertRaisesRegex(PMRSError,'CONTROL_INVALID'):invoke()
                self.assertEqual(h.store._head(),head)
            with frame('GUIDANCE_SAVED',h.operator):
                main_session.submit_direction(h.store,h.iid,'Retain the exact original scope.',client_action_id='native-guidance')
            event=next(e for _,entry in reversed(h.store.history()) for e in entry['events'] if e.get('type')=='GUIDANCE_SAVED')
            original=D.read_json(h.store,event['payload']['direction_ref'],h.project)
            native=strategy.event('HUMAN_DIRECTION_SUBMITTED',dict(instance_id=h.iid,mission_id=original['mission_id'],direction=original))
            head=h.store._head()
            with frame('GUIDANCE_SAVED',h.operator):h.store.commit_strategy(native)
            with frame('GUIDANCE_SAVED',h.session(actions=set(),human=True)):
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):h.store.commit_strategy(native)
            self.assertEqual(h.store._head(),head)

    def test_science_scoped_synthetic_qualification_uses_original_independent_capture(self):
        from research_studio import demo,knowledge_access,input_delivery,changes
        from pmrh.domain import assurance
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(5,communication=True);main=h.prepare();h.send(main);h.dispatch(main,'SENT')
            h.dispatch_workers(main,1,label='qualification-author',stage='P4',role='RESEARCH',duty='ESTABLISH')
            author=h.prepare(actor='WORKER');h.slot(author);h.send(author);h.dispatch(author,'SENT');capture,_=h.capture(author)
            h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=author['spec'].request_id,capture_ref=capture)),h.service)
            h.observation(author,'TERMINATED');h.storage.release_slot(h.control,h.scope,author['spec'].request_id,h.service)
            state=h.store.read_snapshot();support=next(iter(state['supports'].values()));argument=support['argument_ref'];target=state['instances'][h.iid]['target_ref']
            body=knowledge_access.get(h.store,argument,task=main['task'])
            command=h.command('COMMUNICATION_APPLIED',{})
            frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                input_delivery.prepare(h.store,main['spec'].request_id,main['spec'].execution_id,'knowledge.get',body)
            h.dispatch_workers(main,1,label='qualification-review',stage='P4',role='PROOF',duty='VERIFY',inputs=[target,argument])
            reviewer=h.prepare(actor='WORKER');h.slot(reviewer);h.send(reviewer);h.dispatch(reviewer,'SENT')
            requirement=reviewer['task']['required_assurance'];sid=support['support_id']
            before=h.store.read_snapshot()
            self.assertNotEqual(assurance.evaluate_requirement(before,sid,requirement,reviewer['task']['policy_digest'])['result'],'QUALIFIED')
            envelope=loads(demo.response(reviewer['task'],before,blob_get=h.store.read_blob))
            data=envelope['payload']['operations'][0]['data']
            envelope['payload']['operations'][0]['body']='Synthetic test-only positive assessment on exactly the frozen scope. This fixture is not evidence for real mathematics.'
            data.update(verdict='SUPPORTED_WITHIN_SCOPE',unchecked=[],checked=[dict(ref=row['target_ref'],
                locators=row['locators'],aspect=aspect,**{key:row[key] for key in assurance.SCOPE_META if key in row})
                for row in requirement['required_scope'] for aspect in row['aspects']])
            # Explicit synthetic assessment fixture, never a real-math verdict.
            capture,raw=h.capture(reviewer,canonical(envelope))
            validated=changes.validate_response(reviewer['task'],h.store.read_snapshot(),raw,'live',h.store.read_blob)
            h.pause();command=h.command('SCIENCE_ADMITTED',{})
            # The fixed bridge must preserve the entire native derived result,
            # including dependency/obligation collections, in its one HEAD.
            before=h.store.read_snapshot()
            native=changes.apply_validated(before,changes.revalidate(validated,before,blob_get=h.store.read_blob))
            frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**frame):h.store.commit(validated)
            state=h.store.read_snapshot();credential=next(iter(state['qualifications'].values()))
            for collection in ('records','supports','qualifications','withdrawals','relations','obligations','review_executions','accepted_requests'):
                self.assertEqual(state[collection],native[collection],collection)
            self.assertEqual(credential['evidence_origin'],'MODEL_CAPTURE')
            review=state['review_executions'][credential['review_execution_event']]
            self.assertTrue(review['synthetic']);self.assertTrue(review['independent']);self.assertTrue(review['excluded_verdicts'])
            self.assertNotEqual(review['task_id'],support['author_task_id'])
            self.assertEqual(assurance.evaluate_requirement(state,sid,requirement,reviewer['task']['policy_digest'])['result'],'QUALIFIED')
            self.assertEqual(state['instances'][h.iid]['status'],'PAUSED');self.assertEqual(state['instances'][h.iid]['target_ref'],target)
            self.assertEqual(h.store.read_blob(capture['sha256']),raw)
            self.assertEqual({p['authorship'] for p in state['production_events'].values() if p.get('request_id')==reviewer['spec'].request_id},{'MODEL'})

    def test_science_native_support_independent_review_exposure_and_withdrawal(self):
        from research_studio import communication, input_delivery, knowledge_access, demo
        from pmrh.domain.assurance import independence_status
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(8,communication=True);main=h.prepare();h.send(main);h.dispatch(main,'SENT')
            self.assertEqual(main['task']['communication_contract']['schema'],communication.SCHEMA)
            def context(action, prepared=None, *, session=None):
                command=h.command(action,{})
                args={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                extra=dict(grant_ref=h.grant(),manifest_ref=prepared['manifest_ref']) if prepared else {}
                return h.control.native_context(session or h.service,**args,**extra)
            h.dispatch_workers(main,1,label='argument',stage='P4',role='RESEARCH',duty='ESTABLISH')
            old=next(iter(h.store.read_snapshot()['live_main_dispatches'].values()))
            head=h.store._head()
            denied=h.session(actions=set())
            with context('STRATEGY_APPLIED',main,session=denied):
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                    strategy.dispatch_from_main(h.store,main['spec'].request_id,old['proposal'],'dispatch:argument')
            with context('STRATEGY_APPLIED',main):
                strategy.dispatch_from_main(h.store,main['spec'].request_id,old['proposal'],'dispatch:argument')
            self.assertEqual(h.store._head(),head)
            author=h.prepare(actor='WORKER');h.slot(author);h.send(author);h.dispatch(author,'SENT')
            # Exercise the remaining closed communication subactions with real
            # native requests, not fabricated central state.
            link=communication.event('COMMUNICATION_LINKS_REVISED',dict(request_id=main['spec'].request_id,
                execution_id=main['spec'].execution_id,decision_id='synthetic-links',strategy_revision=strategy.current(h.store.read_snapshot(),h.iid)['revision'],
                reason='Bounded synthetic sharing',links=[dict(from_request_id=main['spec'].request_id,to_request_id=author['spec'].request_id,
                    enabled=True,allow_independence_loss=False,reason='Share the fixed target',shared_refs=[author['task']['target_refs'][0]])]))
            with context('COMMUNICATION_APPLIED',main):h.store.commit_communication(link)
            group=communication.event('COLLAB_GROUP_BOUND',dict(group_id='synthetic-group',request_ids=[main['spec'].request_id,author['spec'].request_id],
                topic='Exact synthetic target',reason='Explicit same-mission bounded collaboration'))
            actor=h.session(acting_request_id=main['spec'].request_id)
            with context('COMMUNICATION_APPLIED',main,session=actor):h.store.commit_communication(group)
            rejected_response={'isError':True,'content':[{'type':'text','text':canonical({
                'error':'DYNAMIC_INPUT_LIMIT','message':'Synthetic bounded rejection; no scientific material delivered.'}).decode()}]}
            rejection=communication.event('TOOL_CONTROL_REJECTED',dict(request_id=author['spec'].request_id,
                execution_id=author['spec'].execution_id,tool_name='knowledge.get',error_code='DYNAMIC_INPUT_LIMIT',
                response_ref=h.store.put_blob(canonical(rejected_response)),at=TIME.utc,scientific_input_delivered=False))
            with context('COMMUNICATION_APPLIED'):h.store.commit_communication(rejection)
            capture,raw=h.capture(author)
            h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=author['spec'].request_id,capture_ref=capture)),h.service)
            h.observation(author,'TERMINATED');h.storage.release_slot(h.control,h.scope,author['spec'].request_id,h.service)
            state=h.store.read_snapshot();support=next(iter(state['supports'].values()));argument=support['argument_ref']
            target=state['instances'][h.iid]['target_ref'];original_record=deepcopy(state['records'][target])
            self.assertFalse(state['qualifications']);self.assertEqual(h.store.read_blob(capture['sha256']),raw)
            self.assertEqual({p['authorship'] for p in state['production_events'].values() if p.get('request_id')==author['spec'].request_id},{'MODEL'})
            # Supply exact newly admitted argument bytes through the original
            # dynamic-input bridge before MAIN may name them in a review plan.
            body=knowledge_access.get(h.store,argument,task=main['task'])
            with context('COMMUNICATION_APPLIED',main):
                did,_=input_delivery.prepare(h.store,main['spec'].request_id,main['spec'].execution_id,'knowledge.get',body)
            with context('COMMUNICATION_APPLIED'):
                input_delivery.confirm(h.store,main['spec'].request_id,main['spec'].execution_id,did)
            h.dispatch_workers(main,1,label='review',stage='P9',role='PROOF',duty='VERIFY',inputs=[target,argument])
            review=h.prepare(actor='WORKER');h.slot(review);h.send(review);h.dispatch(review,'SENT')
            self.assertTrue(review['task']['independent'])
            self.assertFalse([row for row in review['task']['input_manifest'] if row.get('kind')=='record' and
                h.store.read_snapshot()['records'][row['ref']]['kind']=='Assessment'])
            with context('COMMUNICATION_APPLIED',main):
                sent=communication.send(h.store,main['spec'].request_id,main['spec'].execution_id,to=review['spec'].request_id,
                    body='Consider this synthetic candidate hint, preserving all uncertainty.',idempotency_key='exposure',allow_independence_loss=True)
            message=sent['message_id']
            body=communication.read_message(h.store,review['spec'].request_id,review['spec'].execution_id,message)
            with context('COMMUNICATION_APPLIED',review):
                delivered,response=input_delivery.prepare(h.store,review['spec'].request_id,review['spec'].execution_id,'communication.get',body,message_ids=[message])
            with context('COMMUNICATION_APPLIED'):
                input_delivery.confirm(h.store,review['spec'].request_id,review['spec'].execution_id,delivered)
            with context('COMMUNICATION_APPLIED',review):
                communication.ack(h.store,review['spec'].request_id,review['spec'].execution_id,message_id=message,
                    disposition='VIEWED',reason='This candidate hint was actually supplied.')
            exposed=deepcopy(h.store.read_snapshot()['input_deliveries'][delivered])
            self.assertFalse(independence_status(h.store.read_snapshot(),review['task']['task_id'])['independent'])
            with context('COMMUNICATION_APPLIED'):
                communication.withdraw(h.store,main['spec'].request_id,main['spec'].execution_id,message,'The candidate hint is withdrawn.')
            state=h.store.read_snapshot()
            self.assertEqual(state['input_deliveries'][delivered],exposed)
            self.assertTrue(next(iter(state['communication_impacts'].values()))['possible_exposure'])
            self.assertEqual(state['research_messages'][message]['exposure_domains'],['MAIN_MIXED:'+h.iid])
            envelope=loads(demo.response(review['task'],state,blob_get=h.store.read_blob))
            capture,raw=h.capture(review,canonical(envelope));h.pause();head=h.store._head()
            # A sealed paused worker is eligible for admission only if its
            # original scientific input/withdrawal duties are satisfied.
            with self.assertRaisesRegex(PMRSError,'WITHDRAWN_MESSAGE_UNRESOLVED'):
                h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=review['spec'].request_id,capture_ref=capture)),h.service)
            self.assertEqual(h.store._head(),head)
            state=Store(h.store.root).read_snapshot()
            self.assertEqual(state['records'][target],original_record)
            self.assertEqual(state['requests'][review['spec'].request_id]['capture_ref'],capture['sha256'])
            self.assertFalse(state['qualifications'])
            self.assertEqual(h.store.read_blob(capture['sha256']),raw)
            self.assertEqual(state['input_deliveries'][delivered]['exposure_domains'],exposed['exposure_domains'])
            # All nine allowed communication subactions must pass the native
            # bridge's current gate even when their native event already exists.
            observed=set()
            for _,entry in h.store.history():
                for event in entry['events']:
                    if event.get('type')!='COMMUNICATION_APPLIED':continue
                    native=event['payload']['native_event'];observed.add(native['event_type'])
                    decision=D.read_json(h.store,event['decision_ref'],h.project)
                    denied=h.session(actions=set(),acting_request_id=main['spec'].request_id)
                    command=h.command('COMMUNICATION_APPLIED',{'native_event':native})
                    args={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                    with h.control.native_context(denied,**args,grant_ref=decision['budget_grant_ref'],manifest_ref=decision['capability_manifest_ref']):
                        with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):h.store.commit_communication(native)
            self.assertEqual(observed,D.COMMUNICATION_LIVE|D.COMMUNICATION_RECOVERY)
            self.assertEqual(h.store._head(),head)

    def test_F3_each_recorded_action_checks_its_current_permission_before_duplicate(self):
        observed = set()
        for kind in ('TRH', 'SURVEY'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp, kind=kind); h.authorize(3,communication=True); p = h.prepare()
                if kind == 'SURVEY':h.slot(p)
                h.send(p); h.dispatch(p, 'SENT'); capture, _ = h.capture(p)
                extra = {} if kind=='SURVEY' else dict(grant_ref=h.grant(), manifest_ref=p['manifest_ref'])
                h.control.apply(h.command('SCIENCE_ADMITTED', dict(request_id=p['spec'].request_id, capture_ref=capture)), h.service, **extra)
                h.observation(p, 'TERMINATED'); h.pause()
                before = h.store._head()
                for _, entry in h.store.history():
                    for event in entry['events']:
                        if event.get('schema') != D.EVENT_SCHEMA:continue
                        action = event['type']; observed.add(action)
                        command = {k:deepcopy(v) for k,v in event.items() if k!='decision_ref'}
                        decision = D.read_json(h.store, event['decision_ref'], h.project)
                        denied = h.session(human=True, actions=set(D.PAYLOAD_FIELDS)-{action})
                        with self.subTest(action=action, native=command['payload'].get('native_event',{}).get('event_type')):
                            try:
                                if action == 'SEND_STARTED':
                                    h.control.send(command, denied, grant_ref=decision['budget_grant_ref'],
                                        manifest_ref=decision['capability_manifest_ref'], boundary=h.boundary)
                                elif action == 'SLOT_CONFIRMED':
                                    h.storage.acquire_slot(h.control, command, denied, grant_ref=decision['budget_grant_ref'],
                                        manifest_ref=decision['capability_manifest_ref'])
                                else:
                                    h.control.apply(command, denied, grant_ref=decision['budget_grant_ref'],
                                        manifest_ref=decision['capability_manifest_ref'])
                            except PMRSError as exc:self.assertEqual(exc.code, 'AUTHORIZATION_REQUIRED')
                            else:self.fail('A stored action returned before its current action permission was checked')
                        self.assertEqual(h.store._head(), before)
                denied = h.session(actions=set())
                with self.assertRaisesRegex(PMRSError, 'AUTHORIZATION_REQUIRED'):
                    h.control.recover_receipt(h.scope, p['command']['operation_id'], denied)
        required={'ACTIVATED','CONTROL_APPLIED','STRATEGY_APPLIED','CALL_PREPARED','SLOT_CONFIRMED',
            'SEND_STARTED','EXECUTION_RECEIVED','COMMUNICATION_APPLIED','SCIENCE_ADMITTED'}
        self.assertEqual(required-observed,set(), 'Missing actual action witnesses: '+repr(sorted(required-observed)))

    def test_science_d5_p14_pending_wait_survives_timer_and_guidance(self):
        from research_studio import demo, main_session
        for kind, wait_state in [('TRH','WAITING_HUMAN_AT_P14'), ('FDH','WAITING_HUMAN_AT_D5')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp, kind=kind); h.authorize(3)
                if kind == 'TRH':
                    native = W.event(h.store.read_snapshot(), 'SET_P14_MODE', {'mode':'HUMAN_P14'}, instance_id=h.iid)
                    h.control.apply(h.command('CONTROL_APPLIED', {'native_event':native}), h.operator)
                p = h.prepare(); h.send(p); h.dispatch(p, 'SENT')
                envelope = loads(demo.response(p['task'], h.store.read_snapshot(), blob_get=h.store.read_blob))
                authored = envelope['payload'].get('knowledge_change', envelope['payload'])
                proposal = authored['strategy_proposal']; proposal['next_action'] = 'DELIVER'
                proposal['progress_account']['frontier_complete'] = True
                capture, _ = h.capture(p, canonical(envelope))
                h.control.apply(h.command('SCIENCE_ADMITTED', dict(request_id=p['spec'].request_id, capture_ref=capture)),
                    h.service, grant_ref=h.grant(), manifest_ref=p['manifest_ref'])
                h.observation(p, 'TERMINATED')
                state = h.store.read_snapshot(); original = deepcopy(state['instances'][h.iid])
                self.assertEqual(original['run_control']['state'], wait_state)
                self.assertEqual(original['status'], 'PAUSED')
                budget = deepcopy(state['budget_grants']); project_budget = deepcopy(state['project_budget'])
                h.registry.clock = lambda: NOW+timedelta(minutes=20)
                for action in ('timer', 'guidance'):
                    command = h.command('STRATEGY_APPLIED' if action=='timer' else 'GUIDANCE_SAVED', {})
                    args = {k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                    if action == 'timer':
                        with h.control.native_context(h.service, **args, grant_ref=h.grant()):
                            strategy.trigger(h.store, h.iid, 'SYNTHETIC_TIMER', 'P14' if kind=='TRH' else 'D5')
                    else:
                        with h.control.native_context(h.operator, **args):
                            main_session.submit_direction(h.store, h.iid, 'Keep the original question; this message grants no continuation.', client_action_id='wait-guidance')
                    state = h.store.read_snapshot()
                    self.assertEqual(state['instances'][h.iid], original)
                    self.assertEqual(state['budget_grants'], budget); self.assertEqual(state['project_budget'], project_budget)
                    self.assertFalse(scheduler.plan(state, [h.iid], h.policy)['selected'])

                for step in ('PAUSE','EXTEND_MISSION_BUDGET','CONFIGURATION'):
                    before=h.store.read_snapshot(); control=deepcopy(before['instances'][h.iid]['run_control'])
                    payload={'reason':'Keep the explicit delivery wait'} if step=='PAUSE' else (
                        {'added_calls':1,'reason':'More budget does not continue this wait'} if step=='EXTEND_MISSION_BUDGET' else
                        {'future_configuration':{'mission_id':'MISSION-synthetic','model_overrides':[],
                            'reason_ref':h.store.put_blob(b'Future model configuration preserves the delivery wait')}})
                    native=W.event(before,'AUTHORIZE_MISSION' if step=='CONFIGURATION' else step,payload,
                        instance_id=h.iid,mission_id='MISSION-synthetic')
                    extra={} if step=='PAUSE' else {'grant_ref':h.grant()}
                    h.control.apply(h.command('CONTROL_APPLIED',{'native_event':native}),h.operator,**extra)
                    actual=h.store.read_snapshot()['instances'][h.iid]
                    self.assertEqual(actual['status'],'PAUSED');self.assertEqual(actual['run_control']['state'],wait_state)
                    self.assertEqual(actual['run_control']['round_number'],control['round_number'])
                    self.assertFalse(scheduler.plan(h.store.read_snapshot(),[h.iid],h.policy)['selected'])
                decision=W.decide_event(h.store.read_snapshot(),h.iid,'CONTINUE_DISCOVERY' if kind=='FDH' else 'CONTINUE',
                    'Explicit synthetic continuation after inspecting the exact delivered scope.')
                h.control.apply(h.command('CONTROL_APPLIED',{'native_event':decision}),h.operator,grant_ref=h.grant())
                actual=h.store.read_snapshot()['instances'][h.iid]
                self.assertEqual(actual['status'],'ACTIVE');self.assertEqual(actual['run_control']['state'],'RUNNING')
                self.assertEqual(actual['run_control']['round_number'],original['run_control']['round_number']+1)

    def test_dispatch_error_envelope_uses_existing_public_evidence_parameter(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp); h.authorize(1); p = h.prepare()
            head = h.store._head()
            for status in ('NOT_SENT', 'SEND_OUTCOME_UNKNOWN'):
                command = h.dispatch(p, status, publish=False)
                receipt = X.DispatchReceipt.from_wire(D.read_json(h.store,
                    command['payload']['receipt']['receipt_ref'], h.project))
                self.assertEqual(receipt.error.raw_evidence_refs, receipt.raw_evidence_refs)
                self.assertEqual(receipt.error.identity, p['spec'].identity())
                self.assertEqual(receipt.error.code.value, status)
            self.assertEqual(h.store._head(), head)

    def test_F1_all_exact_native_prefixes_activate_paused(self):
        for kind in ('TRH','FDH','SURVEY'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp,kind=kind); state=h.store.read_snapshot(); row=state['instances'][h.iid]
                self.assertEqual(row['status'],'PAUSED'); self.assertEqual(D.current_version(row),1)
                self.assertEqual(row['ownership']['owner_epoch'],1)
                self.assertEqual(row['ownership']['logical_main_id'],None if kind=='SURVEY' else 'MAIN-'+h.iid)
                self.assertFalse(state['requests']); self.assertEqual(h.store.history()[-1][1]['schema'],D.SCHEMA)

    def test_F2_prepare_reserve_is_one_commit_and_synthetic_before_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp); h.authorize(1); before=h.store._head(); p=h.prepare()
            request=h.store.read_snapshot()['requests'][p['spec'].request_id]
            self.assertEqual(h.store._head()['sequence'],before['sequence']+1)
            self.assertEqual((request['execution_state'],request['execution_kind']),('RESERVED','SYNTHETIC_TEST_ONLY'))
            self.assertEqual(request['admission']['charge'],'RESERVED')
            self.assertEqual(budget_remaining(h.store.read_snapshot(),'BUDGET-synthetic'),0)
            head=h.store._head()
            duplicate=h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertTrue(duplicate['duplicate']); self.assertEqual(h.store._head(),head)

    def test_F3_forged_revoked_and_expired_sessions_before_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp); h.authorize(1); p=h.prepare(); head=h.store._head()
            for session in (Session(h.service.session_id), None):
                with self.assertRaises(PMRSError):h.control.apply(p['command'],session,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            h.registry.clock=lambda:NOW+timedelta(hours=2)
            with self.assertRaises(PMRSError):h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            h.registry.clock=lambda:NOW
            h.registry.revoke(h.service)
            with self.assertRaises(PMRSError):h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertEqual(h.store._head(),head)
            recovery=h.session(actions={'RECOVER_RECEIPT'})
            self.assertEqual(h.control.recover_receipt(h.scope,p['command']['operation_id'],recovery)['commit'],head['commit'])

    def test_F3_manifest_revocation_rejects_prepare_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare();head=h.store._head()
            h.registry.revoke_manifest(p['spec_ref'])
            with self.assertRaises(PMRSError):h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertEqual(h.store._head(),head)

    def test_F3_scope_proposal_and_receipt_labels_cannot_grant_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare();head=h.store._head()
            wrong=h.session(scope={**h.scope,'instance_id':'different-instance'})
            proposal=h.session(proposal_only=True)
            for session in (wrong,proposal):
                with self.assertRaises(PMRSError):h.control.apply(p['command'],session,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            value=h.dispatch(p,'SENT',publish=False)
            reference=value['payload']['receipt']['receipt_ref']
            h.registry._producers.pop(canonical(reference))
            with self.assertRaises(PMRSError):h.control.apply(value,h.service)
            self.assertEqual(h.store._head(),head)
            value=h.dispatch(p,'SENT',publish=False)
            value['payload']['receipt']['binding_ref']=h.blob('wrong-binding',b'A different synthetic binding',raw=True)
            with self.assertRaises(PMRSError):h.control.apply(value,h.service)
            self.assertEqual(h.store._head(),head)

    def test_F3_final_expiry_check_leaves_unknown_without_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare()
            def expire(point):
                if point=='before_first_effect':h.registry.clock=lambda:NOW+timedelta(hours=2)
            h.store._test_fault_hook=expire
            with self.assertRaises(PMRSError):h.send(p)
            request=h.store.read_snapshot()['requests'][p['spec'].request_id]
            self.assertEqual(request['execution_state'],'UNKNOWN');self.assertEqual(h.boundary.effects,0)
            self.assertEqual(request['admission']['charge'],'UNKNOWN_RESERVED')

    def test_F2_send_unknown_duplicate_has_one_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare();value=h.send(p)
            self.assertEqual(h.boundary.effects,1)
            h.control.send(value,h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'],boundary=h.boundary)
            self.assertEqual(h.boundary.effects,1)
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_state'],'UNKNOWN')
            h.dispatch(p,'SENT')
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_state'],'SENT')

    def test_F2_both_sent_not_sent_orders_quarantine_one_liability(self):
        for order in (('SENT','NOT_SENT'),('NOT_SENT','SENT')):
            with self.subTest(order=order),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);h.authorize(1);p=h.prepare();h.send(p)
                for status in order:h.dispatch(p,status)
                state=h.store.read_snapshot();request=state['requests'][p['spec'].request_id]
                self.assertTrue(request['admission']['evidence_conflict']);self.assertTrue(request['fenced'])
                self.assertEqual(request['admission']['charge'],'SPENT_OR_SETTLED')
                self.assertEqual(len(request['admission']['receipt_ids']),2)
                self.assertEqual(budget_remaining(state,'BUDGET-synthetic'),0)
                with h.pool.locked():
                    with self.assertRaises(PMRSError):h.pool.inspect(sending=True)

    def test_F2_not_sent_then_reused_budget_then_sent_has_deficit(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);first=h.prepare();h.send(first);h.dispatch(first,'NOT_SENT')
            second=h.prepare();h.send(second);h.dispatch(second,'SENT');h.dispatch(first,'SENT')
            state=h.store.read_snapshot()
            self.assertEqual(budget_remaining(state,'BUDGET-synthetic'),-1)
            self.assertEqual(len(state['requests']),2)
            self.assertFalse(control_lane_closed(state['requests'][first['spec'].request_id]))

    def test_F3_pause_and_revoke_do_not_reject_current_ingest_of_old_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare();send=h.send(p);h.pause()
            grant=h.grant();reason=h.blob('reason',b'Explicit synthetic revocation',raw=True)
            h.control.apply(h.command('GRANT_REVOKED',dict(budget_grant_id='BUDGET-synthetic',expected_revision=1,reason_ref=reason)),h.operator,grant_ref=grant)
            with self.assertRaises(PMRSError):h.control.send(send,h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'],boundary=h.boundary)
            recovery=h.session(actions={'EXECUTION_RECEIVED'})
            value=h.dispatch(p,'SENT',publish=False);h.control.apply(value,recovery)
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_state'],'SENT')
            self.assert_denied_actions(h,{'GRANT_REVOKED'})

    def test_F3_raw_native_and_legacy_transport_paths_reject(self):
        from research_studio import execution, runner, host_pool
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare();head=h.store._head()
            operations=(lambda:h.store.commit_execution(execution.event('SENT',dict(request_id=p['spec'].request_id,execution_id=p['spec'].execution_id))),
                lambda:execution.reserve(h.store,p['spec'].request_id),lambda:host_pool.acquire(h.store,p['spec'].request_id),
                lambda:runner.FakeExecutor(lambda *_:b'not called').execute(h.store,p['task']['task_id']),
                lambda:h.store.commit_usage({'event_type':'BACKEND_OBSERVATION'}))
            for operation in operations:
                with self.assertRaises(PMRSError):operation()
                self.assertEqual(h.store._head(),head)

    def test_F2_ready_local_proof_releases_but_stale_proof_cannot_refund_unknown(self):
        for send in (False,True):
            with self.subTest(send=send),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);h.authorize(1);p=h.prepare();rid=p['spec'].request_id
                proof=h.storage.prove_unsent(h.control,h.scope,rid,h.service)
                if send:h.send(p)
                command=h.command('CANCEL_UNSENT',dict(request_id=rid,not_sent_evidence_ref=proof))
                if send:
                    head=h.store._head()
                    with self.assertRaises(PMRSError):h.control.apply(command,h.service)
                    self.assertEqual(h.store._head(),head);self.assertEqual(budget_remaining(h.store.read_snapshot(),'BUDGET-synthetic'),0)
                else:
                    h.control.apply(command,h.service);request=h.store.read_snapshot()['requests'][rid]
                    self.assertEqual(request['execution_state'],'CANCELLED_BEFORE_SEND')
                    self.assertEqual(request['admission']['charge'],'RELEASED');self.assertTrue(control_lane_closed(request))
                    self.assert_denied_actions(h,{'CANCEL_UNSENT'})

    def test_F2_capture_and_termination_are_separate_from_scientific_settlement(self):
        from pmrh.application.read_projections import control_releasable
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare();h.send(p);h.dispatch(p,'SENT')
            capture,raw=h.capture(p,b'SYNTHETIC exact raw output; no scientific claim.')
            request=h.store.read_snapshot()['requests'][p['spec'].request_id]
            self.assertEqual(request['execution_state'],'CAPTURED');self.assertFalse(control_releasable(request))
            self.assertFalse(control_lane_closed(request))
            h.observation(p,'TERMINATED');request=h.store.read_snapshot()['requests'][p['spec'].request_id]
            self.assertTrue(control_releasable(request));self.assertFalse(control_lane_closed(request))
            self.assertEqual(request['acceptance_state'],'PENDING')
            self.assertEqual(h.store.read_blob(capture['sha256']),raw)

    def test_F2_cancel_ack_and_abandon_neither_release_nor_retry(self):
        from pmrh.application.read_projections import control_releasable
        observed=set()
        for first in ('CANCEL_REQUESTED','UNKNOWN_DISPOSED'):
            with self.subTest(first=first),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);h.authorize(2);p=h.prepare();h.send(p);rid=p['spec'].request_id
                raw=C.ExactRef.from_wire(h.blob('cancel-ack',b'SYNTHETIC cancel request acknowledged only',raw=True))
                receipt=X.CancellationReceipt(identity=p['spec'].identity(), request_status=E.CancelStatus.REQUEST_ACKNOWLEDGED,
                    termination=E.ObservationKind.UNOBSERVED,request_evidence_refs=(raw,),termination_evidence_refs=())
                h.receipt(p,'CANCELLATION',receipt)
                payloads={'CANCEL_REQUESTED':dict(request_id=rid,reason_ref=raw.to_wire()),
                    'UNKNOWN_DISPOSED':dict(request_id=rid,disposition='ABANDON_UNKNOWN',evidence_refs=[raw.to_wire()])}
                before=h.store._head();command=h.command(first,payloads[first])
                result=h.control.apply(command,h.service)
                self.assertFalse(result['duplicate']);self.assertNotEqual(h.store._head(),before)
                head=h.store._head();ledger=h.pool.read()
                duplicate=h.control.apply(command,h.service)
                self.assertTrue(duplicate['duplicate']);self.assertEqual(duplicate['commit'],result['commit'])
                # Both actions fence. The first one must have a real journal
                # witness and a current-authorized cached result in its own root.
                self.assert_denied_actions(h,{first})
                events=[e for _,entry in h.store.history() for e in entry['events']]
                observed.update(e['type'] for e in events if e.get('operation_id')==command['operation_id'])
                second=next(action for action in payloads if action!=first)
                noop=h.command(second,payloads[second])
                self.assertEqual(h.control.apply(noop,h.service)['outcome'],'NO_CHANGE')
                self.assertEqual(h.control.apply(noop,h.service)['outcome'],'NO_CHANGE')
                self.assertNotIn(noop['operation_id'],h.store._control_index.operations)
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                    h.control.apply(noop,h.session(actions=set(D.PAYLOAD_FIELDS)-{second}))
                request=h.store.read_snapshot()['requests'][rid]
                self.assertTrue(request['fenced']);self.assertFalse(control_releasable(request))
                self.assertEqual(request['admission']['charge'],'UNKNOWN_RESERVED')
                self.assertEqual(budget_remaining(h.store.read_snapshot(),'BUDGET-synthetic'),1)
                with self.assertRaises((PMRSError,AssertionError)):h.prepare()
                self.assertEqual(h.boundary.effects,1)
                self.assertEqual(h.store._head(),head);self.assertEqual(h.pool.read(),ledger)
        self.assertEqual(observed,{'CANCEL_REQUESTED','UNKNOWN_DISPOSED'})

    def test_F3_owner_takeover_rejects_old_send_but_preserves_old_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(3);p=h.prepare();h.send(p)
            evidence=h.blob('takeover',b'Explicit synthetic takeover evidence; old effect remains in flight',raw=True)
            h.control.apply(h.command('OWNER_ACQUIRED',dict(owner_id='next-owner',backend_binding_ref=None,takeover_evidence_refs=[evidence])),h.operator)
            with self.assertRaises(PMRSError):h.control.apply(p['command'],h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
            capture,raw=h.capture(p,b'SYNTHETIC old owner original capture')
            h.observation(p,'TERMINATED')
            state=h.store.read_snapshot();request=state['requests'][p['spec'].request_id]
            self.assertEqual(request['admission']['owner_epoch'],1);self.assertEqual(state['instances'][h.iid]['ownership']['owner_epoch'],2)
            self.assertTrue(request['fenced']);self.assertTrue(control_lane_closed(request))
            self.assertEqual(h.store.read_blob(capture['sha256']),raw)
            with self.assertRaises(PMRSError):h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=p['spec'].request_id,capture_ref=capture)),h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
            self.assert_denied_actions(h,{'OWNER_ACQUIRED'})

    def test_science_legitimate_main_capture_admits_only_original_bytes_and_keeps_target(self):
        from research_studio import changes
        for kind in ('TRH','FDH'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp,kind=kind);h.authorize(3);original=deepcopy(h.store.read_snapshot()['instances'][h.iid])
                p=h.prepare();h.send(p);h.dispatch(p,'SENT');capture,raw=h.capture(p)
                bad=h.command('SCIENCE_ADMITTED',dict(request_id=p['spec'].request_id,capture_ref=h.blob('altered-output',raw+b' ',raw=True)))
                before=h.store._head()
                with self.assertRaises(PMRSError):h.control.apply(bad,h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
                self.assertEqual(h.store._head(),before)
                command=h.command('SCIENCE_ADMITTED',dict(request_id=p['spec'].request_id,capture_ref=capture))
                validated=changes.validate_response(p['task'],h.store.read_snapshot(),raw,'live',h.store.read_blob)
                frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=p['manifest_ref']):h.store.commit(validated)
                head=h.store._head()
                for session,grant,manifest,code in ((h.session(actions=set()),h.grant(),p['manifest_ref'],'AUTHORIZATION_REQUIRED'),
                        (h.service,None,p['manifest_ref'],'CONTROL_INVALID'),(h.service,h.grant(),None,'CONTROL_INVALID')):
                    with h.control.native_context(session,**frame,grant_ref=grant,manifest_ref=manifest):
                        with self.assertRaisesRegex(PMRSError,code):h.store.commit(validated)
                    self.assertEqual(h.store._head(),head)
                state=h.store.read_snapshot();request=state['requests'][p['spec'].request_id]
                self.assertEqual(request['execution_state'],'SETTLED');self.assertEqual(request['acceptance_state'],'ACCEPTED')
                self.assertEqual(state['instances'][h.iid]['target_ref'],original['target_ref'])
                self.assertEqual(state['instances'][h.iid].get('discovery_scope'),original.get('discovery_scope'))
                self.assertFalse(control_lane_closed(request));h.observation(p,'TERMINATED')
                self.assertTrue(control_lane_closed(h.store.read_snapshot()['requests'][p['spec'].request_id]))
                self.assertEqual(h.store.read_blob(capture['sha256']),raw)

    def test_science_paused_sealed_survey_positive_main_negative(self):
        for kind in ('SURVEY','TRH'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp,kind=kind);h.authorize(3);p=h.prepare()
                if kind=='SURVEY':h.slot(p)
                h.send(p);h.dispatch(p,'SENT');capture,_=h.capture(p);h.pause()
                command=h.command('SCIENCE_ADMITTED',dict(request_id=p['spec'].request_id,capture_ref=capture))
                if kind=='SURVEY':
                    h.control.apply(command,h.service)
                    self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['acceptance_state'],'ACCEPTED')
                else:
                    with self.assertRaises(PMRSError):h.control.apply(command,h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
                self.assertEqual(h.store.read_snapshot()['instances'][h.iid]['status'],'PAUSED')

    def test_guidance_human_proposal_no_resume_and_adopted_requires_strategy_evidence(self):
        from research_studio import main_session
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(3);p=h.prepare();h.send(p);h.dispatch(p,'SENT')
            for label,session,expected in [('human',h.operator,'HUMAN_GUIDANCE'),('proposal',h.session(proposal_only=True),'GUIDANCE_PROPOSAL')]:
                command=h.command('GUIDANCE_SAVED',{'direction_ref':h.producer})
                args={key:command[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(session,**args):result=main_session.submit_direction(h.store,h.iid,'Inspect only the original assumptions.',client_action_id=label)
                direction=h.store.read_snapshot()['human_directions'][result['direction_id']]
                self.assertEqual(direction['provenance']['message_kind'],expected)
                if label=='human':direction_id=result['direction_id']
            raw=C.ExactRef.from_wire(h.blob('steering-observation',b'SYNTHETIC delivery acknowledged; no read inferred',raw=True))
            saved=X.SteeringReceipt(identity=p['spec'].identity(),message_id=direction_id,status=E.GuidanceStatus.DELIVERED,
                evidence_refs=(raw,),consumer_confirmation_ref=None)
            reference=h.blob('guidance-delivered',saved.to_wire())
            h.registry.register_original(reference,producer_ref=h.producer,binding_ref=h.binding_ref,identity=p['spec'].identity().to_wire(),raw_refs=[raw.to_wire()])
            h.control.apply(h.command('GUIDANCE_OBSERVED',{'steering_receipt_ref':reference}),h.service)
            adopted=replace(saved,status=E.GuidanceStatus.ADOPTED,consumer_confirmation_ref=raw)
            reference=h.blob('guidance-adopted-without-strategy',adopted.to_wire())
            h.registry.register_original(reference,producer_ref=h.producer,binding_ref=h.binding_ref,identity=p['spec'].identity().to_wire(),raw_refs=[raw.to_wire()])
            with self.assertRaises(PMRSError):h.control.apply(h.command('GUIDANCE_OBSERVED',{'steering_receipt_ref':reference}),h.service)
            h.pause();state=h.store.read_snapshot();version=D.current_version(state['instances'][h.iid])
            command=h.command('GUIDANCE_SAVED',{'direction_ref':h.producer})
            args={key:command[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.operator,**args):main_session.submit_direction(h.store,h.iid,'Continue considering the question; no new budget.',client_action_id='paused')
            state=h.store.read_snapshot();self.assertEqual(state['instances'][h.iid]['status'],'PAUSED')
            self.assertEqual(D.current_version(state['instances'][h.iid]),version)
            self.assert_denied_actions(h,{'GUIDANCE_SAVED','GUIDANCE_OBSERVED'})

    def test_guidance_adopted_requires_applied_strategy_exact_direction_and_receiver(self):
        from research_studio import main_session
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp); h.authorize(3)
            def direction(key):
                command = h.command('GUIDANCE_SAVED', {'direction_ref':h.producer})
                args = {k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.operator, **args):
                    return main_session.submit_direction(h.store, h.iid,
                        'Retain the original assumptions and report open gaps.', client_action_id=key)['direction_id']
            did = direction('frozen-original')
            p = h.prepare(); h.send(p); h.dispatch(p, 'SENT')
            self.assertIn(did, p['task']['strategy_context']['direction_ids'])
            capture, _ = h.capture(p)
            h.control.apply(h.command('SCIENCE_ADMITTED', dict(request_id=p['spec'].request_id,
                capture_ref=capture)), h.service, grant_ref=h.grant(), manifest_ref=p['manifest_ref'])
            state = h.store.read_snapshot(); saved = state['human_directions'][did]
            proposal = state['strategy_proposals'][saved['reply_ref']]
            self.assertEqual(proposal['status'], 'APPLIED')
            self.assertEqual(proposal['request_id'], p['spec'].request_id)
            confirmation = C.ExactRef.from_wire(h.blob('accepted-strategy', proposal))
            raw = C.ExactRef.from_wire(h.blob('adoption-evidence', b'SYNTHETIC exact receiver observation', raw=True))
            receipt = X.SteeringReceipt(identity=p['spec'].identity(), message_id=did,
                status=E.GuidanceStatus.ADOPTED, evidence_refs=(raw,), consumer_confirmation_ref=confirmation)
            def observe(value):
                reference = h.blob('adoption-receipt', value.to_wire())
                h.registry.register_original(reference, producer_ref=h.producer, binding_ref=h.binding_ref,
                    identity=value.identity.to_wire(), raw_refs=[raw.to_wire()])
                h.control.apply(h.command('GUIDANCE_OBSERVED', {'steering_receipt_ref':reference}), h.service)
                return reference
            accepted = observe(receipt)
            self.assertIn(accepted['sha256'], h.store.read_snapshot()['human_directions'][did]['provenance']['receipt_ids'])
            unrelated = direction('not-in-original-receiver-input')
            head = h.store._head()
            with self.assertRaises(PMRSError):observe(replace(receipt, message_id=unrelated))
            with self.assertRaises(PMRSError):observe(replace(receipt,
                identity=replace(receipt.identity, invocation_id='another-receiver')))
            unaccepted = deepcopy(proposal); unaccepted['status'] = 'VALIDATED'
            with self.assertRaises(PMRSError):observe(replace(receipt,
                consumer_confirmation_ref=C.ExactRef.from_wire(h.blob('unaccepted-strategy', unaccepted))))
            self.assertEqual(h.store._head(), head)
