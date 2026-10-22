"""Closed format, exact startup, sticky lineage and consumer rejections."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

from pmrh.adapters.storage import control as D
from pmrh.domain.primitives import PMRSError, canonical, sha, loads
from research_studio import changes, workflow_instances as W, execution
from research_studio.storage_compat import SyntheticSetup
from .test_control import Harness


class FormatTests(unittest.TestCase):
    @contextmanager
    def forged_visit_head(self, h, mutate):
        """Publish an attacker-rehashed last entry, then restore exact HEAD.

        This is negative input only. Lawful setup always uses native operations;
        a forged projection is never used to manufacture a positive fixture.
        """
        from pmrh.adapters.storage.io import immutable, atomic
        from pmrh.adapters.storage.journal import _diff, _persistent
        from research_studio.store import Store
        head=h.store._head();entry=deepcopy(h.store._commit_record(head));after=h.store.read_snapshot()
        before=Store(h.store.root).read_snapshot(entry['previous_commit']['commit'])
        mutate(after,entry)
        # These selected last entries contain only original control-map deltas.
        self.assertIsNone(entry['knowledge_delta_ref']);self.assertIsNone(entry['report_delta_ref']);self.assertIsNone(entry['registry_delta_ref'])
        entry['control_delta_ref']=h.store.put_blob(canonical(_diff(before,after)))
        state=_persistent(after)
        for event in entry['events']:
            if event.get('type')=='CHECKPOINT':event['state_sha256']=sha(canonical(state))
        raw=canonical(entry);digest=sha(raw);path=f"journal/{head['sequence']:012d}-{digest}.json"
        immutable(h.store.root/path,raw)
        if any(e.get('type')=='CHECKPOINT' for e in entry['events']):
            immutable(h.store.root/'checkpoints'/f'{digest}.json',canonical(dict(commit=digest,state=state,state_sha256=sha(canonical(state)))))
        atomic(h.store.root/'HEAD',canonical(dict(sequence=head['sequence'],commit=digest,path=path)))
        try:yield entry
        finally:atomic(h.store.root/'HEAD',canonical(head))

    def test_visit_correct_hash_forgery_rejected(self):
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(5);main=h.prepare();h.send(main);h.dispatch(main,'SENT')
            h.dispatch_workers(main,2,label='reader-visit');first=h.prepare(actor='WORKER');p=h.prepare(actor='WORKER')
            original=Store(h.store.root).read_snapshot();vid=p['task']['visit_id'];old=first['task']['visit_id'];mid=p['task']['mission_id']
            opening=p['visit']['opening']['event_id']
            attacks=('id','binding','entry','mission','count','task','extra','delete_old','edit_old','duplicate_list',
                     'reorder_list','missing_open','extra_open','edit_open','retry','scheduler','old_request')
            for attack in attacks:
                def mutate(state,entry):
                    visit=state['visits'][vid]
                    if attack=='id':visit['visit_id']='VISIT-nonexistent'
                    elif attack=='binding':visit['assigned_obligation_bindings']=deepcopy(state['visits'][old]['assigned_obligation_bindings'])
                    elif attack=='entry':visit['entry_basis']['unapproved_entry']=True
                    elif attack=='mission':visit['mission_id']='MISSION-not-authorized'
                    elif attack=='count':
                        core={k:v for k,v in p['visit']['visit'].items() if k!='visit_id'}
                        visit['visit_id']=D.identity(dict(core,sequence=len(state['visits'])+1),'VISIT-')
                    elif attack=='task':state['tasks'][p['task']['task_id']]['visit_id']=old
                    elif attack=='extra':state['visits']['VISIT-extra']=deepcopy(visit)
                    elif attack=='delete_old':state['visits'].pop(old)
                    elif attack=='edit_old':state['visits'][old]['outcome']='FULFILLED_FOR_SCOPE'
                    elif attack=='duplicate_list':state['missions'][mid]['stage_visit_ids'].append(vid)
                    elif attack=='reorder_list':state['missions'][mid]['stage_visit_ids'].reverse()
                    elif attack=='missing_open':state['execution_events'].pop(opening)
                    elif attack=='extra_open':
                        event=D.native_event('VISIT_OPENED',{'visit':dict(p['visit']['visit'],visit_id='VISIT-extra')})
                        state['execution_events'][event['event_id']]=event
                    elif attack=='edit_open':
                        event=state['execution_events'].pop(opening);event['payload']['visit']['entry_basis']['unapproved_entry']=True
                        event=D.native_event('VISIT_OPENED',event['payload']);state['execution_events'][event['event_id']]=event
                    elif attack=='retry':state['retry_grants'][p['candidate']['consumer']['retry_grant_id']]['remaining_uses']+=1
                    elif attack=='scheduler':state['scheduler_state']['ordinary_preparations_since_account']=8
                    else:state['requests'][first['task']['request_id']]['reserved_calls']=0
                with self.subTest(attack=attack),self.forged_visit_head(h,mutate):
                    for asof in (None,h.genesis):
                        with self.assertRaises(PMRSError):Store(h.store.root).read_snapshot(asof)
            self.assertEqual(Store(h.store.root).read_snapshot(),original)
            # Non-CALL transitions cannot dispose a visit, even with valid hashes.
            h.pause();paused=Store(h.store.root).read_snapshot()
            for collection in ('visits','missions','execution_events'):
                def mutate(state,entry):
                    if collection=='visits':state['visits'][old]['outcome']='FULFILLED_FOR_SCOPE'
                    elif collection=='missions':state['missions'][mid]['stage_visit_ids'].reverse()
                    else:state['execution_events'].pop(opening)
                with self.subTest(non_call=collection),self.forged_visit_head(h,mutate):
                    with self.assertRaisesRegex(PMRSError,'CAPABILITY_VIOLATION'):Store(h.store.root).read_snapshot()
            self.assertEqual(Store(h.store.root).read_snapshot(),paused)

    def test_visit_legacy_and_mixed_history_rules(self):
        from research_studio.store import Store
        for mixed in (False,True):
            with self.subTest(mixed=mixed),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);h.authorize(4);first=h.prepare()
                if mixed:
                    h.send(first);h.dispatch(first,'SENT');h.dispatch_workers(first,1,label='mixed-visit');p=h.prepare(actor='WORKER')
                else:p=first
                original=h.store.read_snapshot();ledger=h.pool.read();vid=p['task']['visit_id'];rid=p['task']['request_id']
                send=h.command('SEND_STARTED',dict(request_id=rid,send_boundary_id='downgrade-send'))
                intake=h.observation(p,'TERMINATED',publish=False)
                science=h.command('SCIENCE_ADMITTED',dict(request_id=rid,capture_ref=h.blob('unadmitted-capture',b'SYNTHETIC',raw=True)))
                def downgrade(state,entry):
                    event=next(e for e in entry['events'] if e.get('schema')==D.EVENT_SCHEMA)
                    task=state['tasks'][p['task']['task_id']];task['visit_id']=None
                    candidate=deepcopy(p['candidate']);candidate['consumer'].pop('visit_id')
                    event['payload']['task_ref']=h.blob('downgraded-task',task)
                    event['payload']['candidate_ref']=h.blob('downgraded-candidate',candidate)
                    decision=D.read_json(h.store,event['decision_ref'],h.project)
                    decision['payload_sha256']=sha(canonical({k:v for k,v in event.items() if k!='decision_ref'}))
                    event['decision_ref']=h.blob('downgraded-decision',decision)
                    state['visits'].pop(vid);state['missions'][task['mission_id']]['stage_visit_ids'].remove(vid)
                    state['execution_events'].pop(p['visit']['opening']['event_id'])
                    old_event=next(e for e in state['execution_events'].values() if e.get('event_type')=='PREPARE' and e['payload']['task']['request_id']==rid)
                    state['execution_events'].pop(old_event['event_id'])
                    changed=D.native_event('PREPARE',dict(old_event['payload'],task=deepcopy(task),candidate=candidate))
                    state['execution_events'][changed['event_id']]=changed
                # Attacker downgrade tests, NOT a claim of genuine R7 provenance.
                # Genuine validation007 bytes and the independent validation008
                # HEAD/as-of/pool probe are separate Controller evidence.
                with self.forged_visit_head(h,downgrade):
                    for asof in (None,h.genesis):
                        with self.assertRaisesRegex(PMRSError,'CONTROL_INVALID'):Store(h.store.root).read_snapshot(asof)
                    operations=(lambda:h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref']),
                        lambda:h.control.send(send,h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'],boundary=h.boundary),
                        lambda:h.control.apply(intake,h.service),lambda:h.control.apply(science,h.service),
                        lambda:h.control.recover_receipt(h.scope,p['command']['operation_id'],h.service))
                    for operation in operations:
                        with self.assertRaisesRegex(PMRSError,'CONTROL_INVALID'):operation()
                    with h.pool.locked(),self.assertRaisesRegex(PMRSError,'CONTROL_INVALID'):h.pool.inspect(sending=True)
                    self.assertEqual(h.pool.read(),ledger)
                self.assertEqual(Store(h.store.root).read_snapshot(),original)
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare(publish=False);head=h.store._head()
            task=deepcopy(p['task']);task['visit_id']=None;candidate=deepcopy(p['candidate']);candidate['consumer'].pop('visit_id')
            command=deepcopy(p['command']);command['payload'].update(task_ref=h.blob('old-orphan-task',task),candidate_ref=h.blob('old-orphan-candidate',candidate))
            with self.assertRaisesRegex(PMRSError,'ORIGINAL_BYTES_MISMATCH'):
                h.control.apply(command,h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertEqual(h.store._head(),head)
            h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertEqual(len(Store(h.store.root).read_snapshot()['visits']),1)

    def assert_forged_instance_rejected(self, h, changed):
        from pmrh.adapters.storage.io import immutable, atomic
        from research_studio.store import Store
        head = h.store._head(); entry = deepcopy(h.store._commit_record(head))
        delta = loads(h.store.read_blob(entry['control_delta_ref']))
        delta.setdefault('instances', {'op':'map','set':{},'delete':[]})['set'][h.iid] = changed
        entry['control_delta_ref'] = h.store.put_blob(canonical(delta))
        raw = canonical(entry); digest = sha(raw)
        path = f"journal/{head['sequence']:012d}-{digest}.json"
        immutable(h.store.root/path, raw)
        atomic(h.store.root/'HEAD', canonical(dict(sequence=head['sequence'],commit=digest,path=path)))
        try:
            for asof in (None, h.genesis):
                with self.assertRaises(PMRSError):Store(h.store.root).read_snapshot(asof)
        finally:atomic(h.store.root/'HEAD', canonical(head))
        self.assertEqual(Store(h.store.root).read_snapshot()['instances'][h.iid], h.store.read_snapshot()['instances'][h.iid])

    def test_Q1_hashed_receipt_liability_and_cursor_effects_require_exact_originals(self):
        from pmrh.adapters.storage.io import immutable,atomic
        from pmrh.ports.dto import events as V, enums as E
        from pmrh.ports.dto.wire import ContractViolation
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare();h.send(p);rid=p['spec'].request_id
            for intake in ('direct','page'):
                if intake=='direct':h.dispatch(p,'SENT')
                else:h.page(p,[h.event(p,1)])
                original=h.store.read_snapshot();head=h.store._head();entry=h.store._commit_record(head)
                for field in ('charge','receipts','cursor','malformed_cursor'):
                    forged=deepcopy(entry);delta=loads(h.store.read_blob(forged['control_delta_ref']))
                    request=deepcopy(original['requests'][rid])
                    if field=='charge':request['admission']['charge']='UNKNOWN_RESERVED'
                    elif field=='receipts':request['admission']['receipt_ids']=[]
                    else:
                        cursor=request['execution_inbox']['cursor']
                        cursor['after_sequence']+=1
                        # Distinguish schema rejection from semantic replay:
                        # the valid cursor names an event absent at this position.
                        cursor['last_event_id']=None if field=='malformed_cursor' else 'synthetic:unobserved-event'
                        if field=='cursor':V.EventCursor.from_wire(cursor)
                    delta.setdefault('requests',{'op':'map','set':{},'delete':[]})['set'][rid]=request
                    forged['control_delta_ref']=h.store.put_blob(canonical(delta));raw=canonical(forged);digest=sha(raw)
                    path=f"journal/{head['sequence']:012d}-{digest}.json";immutable(h.store.root/path,raw)
                    atomic(h.store.root/'HEAD',canonical(dict(sequence=head['sequence'],commit=digest,path=path)))
                    try:
                        with self.subTest(intake=intake,field=field):
                            for asof in (None,h.genesis):
                                if field=='malformed_cursor':
                                    with self.assertRaisesRegex(ContractViolation,'A nonzero cursor must bind the preceding event identity') as caught:
                                        Store(h.store.root).read_snapshot(asof)
                                    self.assertEqual(caught.exception.code,E.ErrorCode.INVALID_FIELD)
                                else:
                                    code='CONTROL_INVALID' if field=='cursor' or field=='receipts' and intake=='page' else 'CAPABILITY_VIOLATION'
                                    with self.assertRaisesRegex(PMRSError,code):
                                        Store(h.store.root).read_snapshot(asof)
                    finally:atomic(h.store.root/'HEAD',canonical(head))
                self.assertEqual(Store(h.store.root).read_snapshot(),original)

    def test_F3_native_status_run_control_and_mission_effects_are_exact(self):
        # Actual native transitions, then correct-hash hostile deltas through a
        # fresh reader. A writer's refusal alone cannot satisfy this regression.
        for workflow in ('TRH','FDH','SURVEY'):
            with self.subTest(workflow=workflow), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp, kind=workflow); h.authorize(2)
                self.assertEqual(h.store.read_snapshot()['instances'][h.iid]['status'], 'ACTIVE')
                steps = ['PAUSE','EXTEND_MISSION_BUDGET','CONFIGURATION']
                if workflow=='TRH':steps += ['SET_P14_MODE','REQUEST_STOP_AT_P14','CANCEL_STOP_AT_P14']
                steps += ['CONTINUE','RESUME','HUMAN_PAUSE','END']
                continuation = None
                for step in steps:
                    before = h.store.read_snapshot()
                    if step in {'CONTINUE','HUMAN_PAUSE','END'}:
                        action = ('CONTINUE_DISCOVERY' if workflow=='FDH' else 'CONTINUE') if step=='CONTINUE' else ('PAUSE' if step=='HUMAN_PAUSE' else 'END')
                        native = W.decide_event(before,h.iid,action,'Explicit synthetic control decision.')
                        if step=='CONTINUE':continuation=native['event_id']
                    else:
                        payloads = {'PAUSE':{'reason':'Explicit synthetic pause'},
                            'EXTEND_MISSION_BUDGET':{'added_calls':1,'reason':'One further synthetic call'},
                            'CONFIGURATION':{'future_configuration':{'mission_id':'MISSION-synthetic','model_overrides':[],
                                'reason_ref':h.store.put_blob(b'Future configuration without continuation')}},
                            'SET_P14_MODE':{'mode':'HUMAN_P14'},
                            'REQUEST_STOP_AT_P14':{'requested_at':'2026-10-16T00:00:00Z'},
                            'CANCEL_STOP_AT_P14':{}, 'RESUME':{'decision_ref':continuation}}
                        native = W.event(before,'AUTHORIZE_MISSION' if step=='CONFIGURATION' else step,payloads[step],
                            instance_id=h.iid,mission_id='MISSION-synthetic')
                    extra = {'grant_ref':h.grant()} if step in {'CONFIGURATION','EXTEND_MISSION_BUDGET','CONTINUE','RESUME'} else {}
                    command = h.command('CONTROL_APPLIED', {'native_event':native})
                    frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                    with h.control.native_context(h.operator,**frame,**extra):h.store.commit_control(native)
                    state = h.store.read_snapshot(); original = deepcopy(state['instances'][h.iid])
                    expected_status = 'ACTIVE' if step in {'CONTINUE','RESUME'} else 'ENDED' if step=='END' else 'PAUSED'
                    self.assertEqual(original['status'],expected_status)
                    self.assertEqual(original['current_mission_id'],'MISSION-synthetic')
                    self.assertEqual(original['mission_ids'],['MISSION-synthetic'])
                    mutations = []
                    wrong = deepcopy(original); wrong['status']='ACTIVE' if expected_status!='ACTIVE' else 'PAUSED'; mutations.append(wrong)
                    wrong = deepcopy(original); wrong['mission_ids'].append('HIDDEN-MISSION'); mutations.append(wrong)
                    if workflow!='SURVEY':
                        wrong = deepcopy(original); wrong['run_control']['round_number']+=1; mutations.append(wrong)
                        wrong = deepcopy(original); wrong['run_control']['state']='RUNNING' if expected_status!='ACTIVE' else 'PAUSED'; mutations.append(wrong)
                    for changed in mutations:
                        with self.subTest(step=step,changed=changed):self.assert_forged_instance_rejected(h,changed)
                    # Even an exact outer duplicate requires current human action
                    # authority. No cached success may bypass this check.
                    denied = h.session(actions=set(),human=True)
                    head = h.store._head()
                    with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                        h.control.apply(command,denied,**extra)
                    with h.control.native_context(denied,**frame,**extra):
                        with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):h.store.commit_control(native)
                    self.assertEqual(h.store._head(),head)

    def test_closed_structured_eight_mib_and_node_bounds_on_actual_blob_reads(self):
        from pmrh.ports.dto import core as C
        from pmrh.ports.dto.wire import ContractViolation
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp); head = h.store._head(); limit = 8*1024**2
            # Canonical object is exactly the advertised document byte bound.
            value = {'text':'x'*(limit-len(canonical({'text':''})))}
            ref = h.blob('exact-eight-mib', value)
            self.assertEqual(len(h.store.read_blob(ref['sha256'])), limit)
            self.assertEqual(D.read_json(h.store, ref, h.project), value)
            data = canonical({'text':value['text']+'x'}); digest = h.store.put_blob(data)
            over = C.ExactRef(project_id=h.project, object_id='one-byte-over', revision='sha256:'+digest, sha256=digest).to_wire()
            with self.assertRaises(PMRSError):D.read_json(h.store, over, h.project)
            nodes = [[None]*4096 for _ in range(64)]
            reference = h.blob('too-many-nodes', nodes)
            with self.assertRaises(ContractViolation):D.read_json(h.store, reference, h.project)
            self.assertEqual(h.store._head(), head)

    def test_closed_complete_four_thousand_file_and_128_mib_closure_before_head(self):
        for mode, count, size in [('files',4096,24), ('bytes',129,1024**2)]:
            with self.subTest(bound=mode), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp); head = h.store._head()
                references = []
                for number in range(count):
                    prefix = ('SYNTHETIC-'+str(number)+':').encode()
                    references.append(h.blob(mode+str(number), prefix+b'x'*(size-len(prefix)), raw=True))
                command = h.command('OWNER_ACQUIRED', dict(owner_id='bounded-next-owner', backend_binding_ref=None,
                    takeover_evidence_refs=references))
                with self.assertRaisesRegex(PMRSError, 'RESOURCE_LIMIT'):h.control.apply(command, h.operator)
                self.assertEqual(h.store._head(), head)
                self.assertEqual(h.store.read_snapshot()['instances'][h.iid]['ownership']['owner_epoch'], 1)

    def test_F2_hashed_control_subactions_cannot_smuggle_grant_or_project_limits(self):
        from pmrh.adapters.storage.io import immutable, atomic
        from research_studio.store import Store
        cases = [('PAUSE', {'reason':'Explicit pause'}), ('SET_P14_MODE', {'mode':'HUMAN_P14'}),
                 ('REQUEST_STOP_AT_P14', {'requested_at':'2026-10-16T00:00:00Z'}), ('CANCEL_STOP_AT_P14', {})]
        for kind, payload in cases:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp); h.authorize(2)
                before = h.store.read_snapshot()
                native = W.event(before, kind, payload, instance_id=h.iid)
                h.control.apply(h.command('CONTROL_APPLIED', {'native_event':native}), h.operator)
                state = h.store.read_snapshot(); head = h.store._head()
                self.assertEqual(state['budget_grants'], before['budget_grants'])
                self.assertEqual(state['project_budget'], before['project_budget'])
                entry = h.store._commit_record(head)
                event = next(e for e in entry['events'] if e['type'] != 'CHECKPOINT')
                for field, value in [('max_calls', 3), ('max_calls', 12345), ('explicit_unlimited', True), ('max_workers', 7), ('project_budget', 9)]:
                    with self.subTest(field=field, value=value):
                        forged = deepcopy(entry); delta = loads(h.store.read_blob(forged['control_delta_ref']))
                        if field == 'project_budget':
                            delta['project_budget'] = {'op':'map', 'set':{'max_calls':value}, 'delete':[]}
                        else:
                            grant = deepcopy(state['budget_grants']['BUDGET-synthetic'])
                            grant.update({field:value}, grant_revision=grant['grant_revision']+1, authorization_ref=event['decision_ref'])
                            delta['budget_grants'] = {'op':'map', 'set':{'BUDGET-synthetic':grant}, 'delete':[]}
                        forged['control_delta_ref'] = h.store.put_blob(canonical(delta))
                        raw = canonical(forged); digest = sha(raw)
                        path = f"journal/{head['sequence']:012d}-{digest}.json"
                        immutable(h.store.root/path, raw)
                        atomic(h.store.root/'HEAD', canonical(dict(sequence=head['sequence'], commit=digest, path=path)))
                        try:
                            with self.assertRaises(PMRSError):Store(h.store.root).read_snapshot()
                            with self.assertRaises(PMRSError):Store(h.store.root).read_snapshot(h.genesis)
                        finally:atomic(h.store.root/'HEAD', canonical(head))
                self.assertEqual(Store(h.store.root).read_snapshot(), state)

    def test_F2_authorize_extend_and_future_configuration_have_exact_budget_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp); h.authorize(2); h.pause()
            for amount in (1, 3):
                before = h.store.read_snapshot(); grant = before['budget_grants']['BUDGET-synthetic']
                native = W.event(before, 'EXTEND_MISSION_BUDGET', dict(added_calls=amount, reason='Explicit synthetic allowance'),
                    instance_id=h.iid, mission_id='MISSION-synthetic')
                h.control.apply(h.command('CONTROL_APPLIED', {'native_event':native}), h.operator, grant_ref=h.grant())
                state = h.store.read_snapshot(); changed = state['budget_grants']['BUDGET-synthetic']
                self.assertEqual(changed['max_calls'], grant['max_calls']+amount)
                self.assertEqual(changed['grant_revision'], grant['grant_revision']+1)
                self.assertEqual(state['project_budget']['max_calls'], before['project_budget']['max_calls']+amount)
                self.assertEqual(state['instances'][h.iid]['status'], 'PAUSED')
            before = h.store.read_snapshot()
            config = dict(mission_id='MISSION-synthetic', model_overrides=[],
                reason_ref=h.store.put_blob(b'Explicit synthetic future configuration; no budget change.'))
            native = W.event(before, 'AUTHORIZE_MISSION', {'future_configuration':config}, instance_id=h.iid, mission_id='MISSION-synthetic')
            h.control.apply(h.command('CONTROL_APPLIED', {'native_event':native}), h.operator, grant_ref=h.grant())
            state = h.store.read_snapshot()
            self.assertEqual(state['budget_grants']['BUDGET-synthetic']['max_calls'], 6)
            self.assertEqual(state['project_budget'], before['project_budget'])
            self.assertEqual(state['instances'][h.iid]['status'], 'PAUSED')
            self.assertEqual(state['budget_grants']['BUDGET-synthetic']['execution_policy']['configuration_event_ref'], native['event_id'])

    def test_F1_hashed_instance_forgery_rejects_trh_fdh_survey_and_old_asof(self):
        from pmrh.adapters.storage.io import immutable, atomic
        from research_studio.store import Store

        for kind in ('TRH', 'FDH', 'SURVEY'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                h = Harness(tmp, kind=kind)
                original = deepcopy(h.store.read_snapshot()['instances'][h.iid])
                fields = ['instance_id', 'kind', 'target_ref', 'created_by_decision']
                if kind == 'FDH':
                    fields += ['discovery_brief_ref', 'discovery_scope']
                if kind == 'SURVEY':
                    fields += ['survey_scope']
                for action in ('ACTIVATED', 'CONTROL_APPLIED', 'OWNER_ACQUIRED'):
                    if action == 'CONTROL_APPLIED':
                        h.pause()
                    elif action == 'OWNER_ACQUIRED':
                        proof = h.blob('takeover', b'SYNTHETIC explicit owner takeover', raw=True)
                        h.control.apply(h.command(action, dict(owner_id='next-owner',
                            backend_binding_ref=None, takeover_evidence_refs=[proof])), h.operator)
                    state = h.store.read_snapshot()
                    instance = state['instances'][h.iid]
                    # Valid control actions must preserve all original scientific
                    # identity, while changing only their authorized control data.
                    for name in fields:
                        self.assertEqual(instance.get(name), original.get(name))
                    self.assertEqual(instance['status'], 'PAUSED')
                    head = h.store._head()
                    entry = deepcopy(h.store._commit_record(head))
                    self.assertEqual(next(e['type'] for e in entry['events'] if e['type'] != 'CHECKPOINT'), action)
                    mutations = [(name, None) for name in fields if name != 'discovery_scope']
                    if kind == 'FDH':
                        mutations += [('discovery_scope', name) for name in
                            ('phenomenon_ref', 'immutable_background_ref', 'allowed_axes_ref')]
                    for name, nested in mutations:
                        with self.subTest(action=action, field=name, nested=nested):
                            forged = deepcopy(entry)
                            delta = loads(h.store.read_blob(forged['control_delta_ref']))
                            changed = deepcopy(instance)
                            if nested:
                                changed[name][nested] = 'UNAUTHORIZED-REPLACEMENT'
                            elif name == 'survey_scope':
                                changed[name]['topic'] = 'UNAUTHORIZED-REPLACEMENT'
                            else:
                                changed[name] = 'UNAUTHORIZED-REPLACEMENT'
                            delta.setdefault('instances', {'op':'map', 'set':{}, 'delete':[]})['set'][h.iid] = changed
                            forged['control_delta_ref'] = h.store.put_blob(canonical(delta))
                            raw = canonical(forged); digest = sha(raw)
                            path = f"journal/{head['sequence']:012d}-{digest}.json"
                            immutable(h.store.root/path, raw)
                            atomic(h.store.root/'HEAD', canonical(dict(sequence=head['sequence'], commit=digest, path=path)))
                            try:
                                # Reopen through the reader, with valid hashes;
                                # producer-side checks and stale caches cannot help.
                                for asof in (None, h.genesis):
                                    with self.assertRaises(PMRSError):
                                        Store(h.store.root).read_snapshot(asof)
                            finally:
                                atomic(h.store.root/'HEAD', canonical(head))
                    self.assertEqual(Store(h.store.root).read_snapshot(), state)

    def test_F1_hashed_activation_budget_delta_is_rejected(self):
        from pmrh.adapters.storage.io import immutable, atomic
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp)
            self.assertEqual(h.store.read_snapshot()['project_budget'], {'max_calls':0})
            head = h.store._head(); forged = deepcopy(h.store._commit_record(head))
            delta = loads(h.store.read_blob(forged['registry_delta_ref'])) if forged['registry_delta_ref'] else {}
            delta['project_budget'] = {'op':'map', 'set':{'max_calls':12345}, 'delete':[]}
            forged['registry_delta_ref'] = h.store.put_blob(canonical(delta))
            raw = canonical(forged); digest = sha(raw)
            path = f"journal/{head['sequence']:012d}-{digest}.json"
            immutable(h.store.root/path, raw)
            atomic(h.store.root/'HEAD', canonical(dict(sequence=head['sequence'], commit=digest, path=path)))
            with self.assertRaises(PMRSError):Store(h.store.root).read_snapshot()

    def test_F1_setup_capability_cannot_adopt_another_or_modified_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp)/'one',activate=False)
            other=SyntheticSetup(Path(tmp)/'two',kind='TRH',inputs=(b'A distinct original.',))
            with self.assertRaises(PMRSError):h.setup.verify(other.store)
            before=h.store.read_snapshot()
            h.store.commit(changes.prepare_source_input(before,b'Extra source is outside the closed prefix.',purpose='PHENOMENON',blob_get=h.store.read_blob))
            with self.assertRaises(PMRSError):h.setup.verify(h.store)
            with self.assertRaises(PMRSError):D.validate_prefix(h.store,h.store.history())

    def test_F1_injected_initial_state_and_missing_originals_reject(self):
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            for kind,inputs in [('TRH',()),('FDH',(b'Only one original.',)),('SURVEY',(b'Unexpected source.',))]:
                with self.assertRaises(PMRSError):SyntheticSetup(Path(tmp)/kind,kind=kind,inputs=inputs)
            with self.assertRaises(PMRSError):Store.create(Path(tmp)/'injected','Synthetic',synthetic=True,initial={'requests':{}})

    def test_F1_missing_target_and_native_extra_mission_cannot_activate(self):
        from pmrh.adapters.storage.io import immutable,atomic
        for fault in ('missing_target','extra_mission'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp,activate=False)
                if fault=='missing_target':
                    # A hostile but correctly hashed native prefix; both its
                    # event and delta agree. The closed prefix must still reject.
                    head=h.store._head();entry=deepcopy(h.store._commit_record(head))
                    delta=loads(h.store.read_blob(entry['control_delta_ref']))
                    delta['instances']['set'][h.iid]['target_ref']=None
                    event=next(e for e in entry['events'] if e.get('event_type')=='CREATE_INSTANCE')
                    event['payload']['instance']['target_ref']=None
                    delta['control_events']['set'][event['event_id']]=deepcopy(event)
                    entry['control_delta_ref']=h.store.put_blob(canonical(delta))
                    raw=canonical(entry);digest=sha(raw);path=f"journal/{head['sequence']:012d}-{digest}.json"
                    immutable(h.store.root/path,raw);atomic(h.store.root/'HEAD',canonical(dict(sequence=head['sequence'],commit=digest,path=path)))
                else:
                    state=h.store.read_snapshot()
                    mission=dict(mission_id='MISSION-extra',instance_id=h.iid,intent_ref=h.store.put_blob(b'Explicit synthetic pre-activation mission'),
                        authorized_scope={'target_refs':[state['instances'][h.iid]['target_ref']]},budget_grant_id='BUDGET-extra')
                    h.store.commit_control(W.authorize_event(state,h.iid,mission,dict(budget_grant_id='BUDGET-extra',max_calls=1,max_workers=1)))
                    h.store.commit_control(W.event(h.store.read_snapshot(),'PAUSE',{'reason':'Paused is insufficient for activation'},instance_id=h.iid))
                    self.assertTrue(h.store.read_snapshot()['missions'])
                head=h.store._head()
                with self.assertRaises(PMRSError):D.validate_prefix(h.store,h.store.history())
                profile=D.record('PROFILE',profile='SYNTHETIC_TEST_ONLY',project_id=h.project,
                    genesis_commit=h.genesis,setup_head=head['commit'],resource_policy='COMPAT_8_20_SURVEY1',pool_id=h.pool.pool_id)
                with self.assertRaises(PMRSError):
                    h.control.apply(h.command('ACTIVATED',dict(profile_ref=h.blob('profile',profile),owner_id='fixture-owner',backend_binding_ref=None)),h.operator)
                self.assertEqual(h.store._head(),head)
                self.assertNotIn('ownership',h.store.read_snapshot()['instances'][h.iid])

    def test_F1_future_orphan_and_cross_scope_evidence_never_supply_authority(self):
        from pmrh.adapters.storage.io import immutable
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare(publish=False);head=h.store._head()
            orphan=h.dispatch(p,'SENT',publish=False)
            with self.assertRaisesRegex(PMRSError,'REQUEST_UNKNOWN'):h.control.apply(orphan,h.service)
            future=deepcopy(D.read_json(h.store,p['grant_ref'],h.project));future['grant_revision']+=1;future['max_calls']+=10
            foreign={**p['grant_ref'],'project_id':'another-synthetic-project'}
            for grant in (h.blob('unpublished-future-grant',future),foreign):
                with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                    h.control.apply(p['command'],h.service,grant_ref=grant,manifest_ref=p['manifest_ref'])
            self.assertEqual(h.store._head(),head)
            entry=deepcopy(h.store._commit_record(head));entry['at']='2026-10-17T00:00:00Z'
            raw=canonical(entry);digest=sha(raw)
            immutable(h.store.root/f"journal/{head['sequence']:012d}-{digest}.json",raw)
            with self.assertRaisesRegex(PMRSError,'SNAPSHOT_NOT_FOUND'):Store(h.store.root).read_snapshot(digest)
            self.assertFalse(Store(h.store.root).read_snapshot()['requests'])
            h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertIn(p['spec'].request_id,Store(h.store.root).read_snapshot()['requests'])
            self.assertFalse(Store(h.store.root).read_snapshot(head['commit'])['requests'])

    def test_closed_command_fields_tags_bool_versions_and_readonly_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp)
            command=h.command('CANCEL_REQUESTED',{'request_id':'absent','reason_ref':h.blob('reason',b'Synthetic reason',raw=True)})
            for mutate in (lambda c:c.update(extra=True),lambda c:c.update(type='RECOVER_RECEIPT'),
                           lambda c:c.update(owner_epoch=True),lambda c:c['payload'].update(callback='arbitrary'),
                           lambda c:c.update(schema='pmrh.control-event/2')):
                bad=deepcopy(command);mutate(bad)
                with self.assertRaises((PMRSError,ValueError,TypeError)):D.command(bad)

    def test_closed_record_dictionary_missing_unknown_and_null_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);owner=h.store.read_snapshot()['instances'][h.iid]['ownership']
            for mutate in (lambda v:v.update(extra=1),lambda v:v.pop('authorization_ref'),
                           lambda v:v.update(owner_epoch=False),lambda v:v.update(kind='NEW_OWNER'),
                           lambda v:v.update(authorization_ref=None)):
                bad=deepcopy(owner);mutate(bad)
                with self.assertRaises((PMRSError,ValueError,TypeError)):D.validate_record(bad)

    def test_F1_port_binding_and_all_unlisted_writers_reject_without_head(self):
        from tests.devpr05.fixtures import assemble
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);head=h.store._head()
            storage,_,_=assemble(h.store,h.iid)
            self.assertEqual(storage.current_boundary().code.value,'UNSUPPORTED_CAPABILITY')
            with self.assertRaises(PMRSError):assemble(h.store,h.iid,install=True)
            for name in ('commit_usage','commit_report','commit_survey','commit_incident','commit_native_main','commit_assistant'):
                with self.subTest(writer=name),self.assertRaises(PMRSError):
                    getattr(h.store,name)({'event_type':'UNKNOWN','payload':{}})
                self.assertEqual(h.store._head(),head)
            with self.assertRaises(PMRSError):h.store.commit(changes.prepare_source_input(h.store.read_snapshot(),b'No source upload after activation.',blob_get=h.store.read_blob))
            self.assertEqual(h.store._head(),head)

    def test_F1_unknown_or_downgraded_head_rejects_even_old_asof(self):
        from pmrh.adapters.storage.io import immutable, atomic
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);old=h.setup.heads[0];head=h.store._head();entry=h.store._commit_record(head)
            for schema in ('pmrh.commit/99','pmrs.commit/4.2.2','pmrh.commit/1'):
                forged=deepcopy(entry);forged['schema']=schema
                raw=canonical(forged);digest=sha(raw);path=f"journal/{head['sequence']:012d}-{digest}.json"
                immutable(h.store.root/path,raw);atomic(h.store.root/'HEAD',canonical(dict(sequence=head['sequence'],commit=digest,path=path)))
                with self.assertRaises(PMRSError):h.store.read_snapshot(old)
                atomic(h.store.root/'HEAD',canonical(head))

    def test_F1_checkpoint_projection_loss_keeps_full_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare();expected=h.store.read_snapshot()
            for path in (h.store.root/'checkpoints').glob('*.json'):path.unlink()
            h.store.rebuild_projection()
            (h.store.root/'.runtime/projection.sqlite').unlink()
            self.assertEqual(h.store.read_snapshot(),expected)
            duplicate=h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertTrue(duplicate['duplicate'])

    def test_F1_checkpoint_cannot_supply_unjournaled_authority(self):
        from pmrh.adapters.storage.io import atomic
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);genesis=h.setup.heads[0]
            path=h.store.root/'checkpoints'/f'{genesis}.json'
            from pmrh.domain.primitives import loads
            wrapper=loads(path.read_bytes());wrapper['state']['capabilities']['CAP-FORGED']={'actor':'human','actions':['*']}
            wrapper['state_sha256']=sha(canonical(wrapper['state']));atomic(path,canonical(wrapper))
            with self.assertRaises(PMRSError):h.store.read_snapshot(genesis)

    def test_F3_native_control_with_host_context_and_without_context_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);state=h.store.read_snapshot()
            event=W.event(state,'PAUSE',{'reason':'Keep paused'},instance_id=h.iid)
            with self.assertRaises(PMRSError):h.store.commit_control(event)
            command=h.command('CONTROL_APPLIED',{'native_event':event})
            args={key:command[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.operator,**args):result=h.store.commit_control(event)
            self.assertEqual(result['outcome'],'COMMITTED')
            with h.control.native_context(h.operator,**args),self.assertRaises(PMRSError):h.store.commit_control(event)

    def test_F3_failed_original_live_guard_leaves_no_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare(publish=False)
            task=deepcopy(p['task']);task['input_fingerprint']='changed-frozen-science'
            p['command']['payload']['task_ref']=h.blob('invalid-task',task)
            head=h.store._head()
            with self.assertRaises(PMRSError):h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            self.assertEqual(h.store._head(),head);self.assertFalse(h.store.read_snapshot()['requests'])

    def test_F3_ready_cannot_send_after_pause_and_old_main_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare();h.pause()
            with self.assertRaises(PMRSError):h.send(p)
            self.assertEqual(h.boundary.effects,0)
            request=h.store.read_snapshot()['requests'][p['spec'].request_id]
            self.assertEqual(request['admission']['send_phase'],'READY')
            self.assertEqual(request['admission']['charge'],'RESERVED')

    def test_M2_clone_new_pool_and_main_without_registration_reject(self):
        import shutil
        from pmrh.application.control import Control
        from pmrh.adapters.storage.pool import Pool,RootBinding
        from research_studio.storage_compat import ControlNativeBridge
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp)/'one');h.authorize(1);p=h.prepare()
            clone=Path(tmp)/'clone';shutil.copytree(h.store.root,clone);store=Store(clone)
            copied=Control(D.ControlStorage(store,ControlNativeBridge(store)),h.pool,h.registry,binding_id=h.binding.binding_id)
            command=h.command('SEND_STARTED',dict(request_id=p['spec'].request_id,send_boundary_id='no-clone'))
            copied.storage.register_boundary(h.boundary,h.scope)
            with self.assertRaises(PMRSError):copied.send(command,h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'],boundary=h.boundary)
            runtime=Path(tmp)/'split-runtime';runtime.mkdir()
            other=Pool(RootBinding.register('other-runtime',runtime),'another-pool',[h.binding])
            other.register(h.binding.binding_id,genesis=h.genesis,project=h.project)
            with other.locked(),self.assertRaises(PMRSError):other.inspect(sending=True)
            # MAIN has no worker slot, but its original project registration is
            # still mandatory. This synthetic corruption is never repaired by
            # reading a project-controlled path or creating an automatic pool.
            with h.pool.locked():
                before=h.pool.read();after=deepcopy(before);after['projects'].clear();h.pool.write(before,after)
            with self.assertRaises(PMRSError):h.control.send(command,h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'],boundary=h.boundary)
            self.assertEqual(h.boundary.effects,0)

    def test_closed_record_depth_array_and_evidence_limits(self):
        from pmrh.ports.dto import core as C
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);head=h.store._head()
            with self.assertRaises(PMRSError):h.blob('oversize',b'x'*(1024**2+1),raw=True)
            proof=h.blob('proof',b'Explicit synthetic takeover original',raw=True)
            command=h.command('OWNER_ACQUIRED',dict(owner_id='next',backend_binding_ref=None,takeover_evidence_refs=[proof]*4097))
            with self.assertRaises((PMRSError,ValueError)):h.control.apply(command,h.operator)
            deep={}
            for _ in range(65):deep={'nested':deep}
            native=W.event(h.store.read_snapshot(),'PAUSE',{'reason':'Synthetic','extra':deep},instance_id=h.iid)
            with self.assertRaises((PMRSError,ValueError)):h.control.apply(h.command('CONTROL_APPLIED',{'native_event':native}),h.operator)
            # Existing blob bytes are also bounded when reached through a new
            # decision; bypassing the convenience writer cannot enlarge reads.
            data=b'x'*(1024**2+1);digest=h.store.put_blob(data)
            oversize=C.ExactRef(project_id=h.project,object_id='oversize-raw',revision='sha256:'+digest,sha256=digest).to_wire()
            with self.assertRaises(PMRSError):h.control.apply(h.command('OWNER_ACQUIRED',dict(owner_id='next',backend_binding_ref=None,takeover_evidence_refs=[oversize])),h.operator)
            self.assertEqual(h.store._head(),head)
