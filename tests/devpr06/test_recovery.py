"""Real reopen/process/crash boundaries; all fixtures are synthetic and new."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

from pmrh.adapters.storage import control as D
from pmrh.application.read_projections import budget_remaining, control_lane_closed, control_releasable
from pmrh.domain.primitives import PMRSError
from pmrh.ports.dto import events as V, enums as E
from research_studio.store import Store
from research_studio import workflow_instances as W, scheduler
from .test_control import Harness


def child(mode,*args):
    return subprocess.Popen([sys.executable,'-B','/source/tests/devpr06/child.py',mode,*map(str,args)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)


def line(process):
    if not select.select([process.stdout],[],[],20)[0]:
        process.kill()
        raise AssertionError('Child barrier timed out: '+process.communicate()[1])
    result=process.stdout.readline().strip()
    if not result:raise AssertionError('Child exited before barrier: '+process.stderr.read())
    return result


def go(process):
    process.stdin.write('GO\n');process.stdin.flush()


def done(process,expected=0):
    output,error=process.communicate(timeout=25)
    if process.returncode!=expected:raise AssertionError((process.returncode,expected,output,error))
    return [json.loads(s[7:]) for s in output.splitlines() if s.startswith('RESULT ')]


class RecoveryTests(unittest.TestCase):
    def test_visit_preview_cas_and_atomic_reopen(self):
        from research_studio import strategy
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare(publish=False);head=h.store._head()
            # Use the existing child barrier. Its lawful trigger wins after the
            # parent's full freeze verification and before parent writer locks.
            digest=strategy.frontier_digest(h.store.read_snapshot(),h.iid,'MISSION-synthetic')
            trigger=dict(schema='pmrs.strategy-trigger/1',instance_id=h.iid,mission_id='MISSION-synthetic',
                reason='SYNTHETIC_EVENT',stage_id='P1',frontier_digest=digest,direction_ids=[],
                trigger_id=D.identity([h.iid,'MISSION-synthetic','SYNTHETIC_EVENT','P1',digest,[]],'TRIGGER-'))
            native=strategy.event('STRATEGY_TRIGGERED',dict(instance_id=h.iid,mission_id='MISSION-synthetic',trigger=trigger))
            other=h.command('STRATEGY_APPLIED',{'native_event':native})
            config=h.export(Path(tmp)/'visit-cas.json',other,grant_ref=h.grant())
            contender=child('compete',config);self.assertEqual(line(contender),'READY');observed=[]
            def barrier(point):
                if point=='after_control_freeze':
                    observed.append(point);self.assertEqual(h.store._head(),head)
                    go(contender);self.assertTrue(done(contender)[0]['ok'])
            h.store._test_fault_hook=barrier
            try:
                with self.assertRaisesRegex(PMRSError,'VERSION_CONFLICT'):
                    h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
            finally:
                h.store._test_fault_hook=None
                if contender.poll() is None:contender.kill();contender.communicate()
            self.assertEqual(observed,['after_control_freeze'])
            state=Store(h.store.root).read_snapshot();self.assertFalse(state['visits']);self.assertFalse(state['requests'])
            self.assertNotEqual(state['_head'],head)
            self.assertEqual(D.read_json(h.store,p['command']['payload']['task_ref'],h.project),p['task'])
            winning_head=state['knowledge_commit'];fresh=h.prepare();state=Store(h.store.root).read_snapshot()
            self.assertEqual(fresh['task']['knowledge_commit'],winning_head)
            self.assertNotEqual(fresh['task']['knowledge_commit'],p['task']['knowledge_commit'])
            self.assertEqual(len(state['visits']),1);self.assertEqual(len(state['requests']),1)

    def test_F3_source_commit_waiting_on_writer_lock_cannot_cross_activation(self):
        from pmrh.domain.primitives import canonical
        for wait in ('immediate','barrier'):
            with self.subTest(wait=wait),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp,activate=False)
                source=Path(tmp)/'source.json';source.write_bytes(canonical({'source_input':'SYNTHETIC late original source.'}))
                pending=child('native_duplicate',h.store.root,source,wait)
                try:
                    if wait=='immediate':
                        self.assertTrue(done(pending)[0]['ok'])
                        self.assertIn('SO-synthetic-racing-source',h.store.read_snapshot()['sources'])
                        with self.assertRaises(PMRSError):D.validate_prefix(h.store,h.store.history())
                        continue
                    self.assertEqual(line(pending),'BEFORE_NATIVE_LOCK')
                    profile=D.record('PROFILE',profile='SYNTHETIC_TEST_ONLY',project_id=h.project,
                        genesis_commit=h.genesis,setup_head=h.setup.heads[-1],resource_policy='COMPAT_8_20_SURVEY1',pool_id=h.pool.pool_id)
                    h.control.apply(h.command('ACTIVATED',dict(profile_ref=h.blob('profile',profile),
                        owner_id='fixture-owner',backend_binding_ref=None)),h.operator)
                    head=h.store._head();go(pending);result=done(pending)[0]
                    self.assertFalse(result['ok']);self.assertEqual(result['code'],'AUTHORIZATION_REQUIRED')
                    self.assertEqual(Store(h.store.root)._head(),head)
                    self.assertNotIn('SO-synthetic-racing-source',Store(h.store.root).read_snapshot()['sources'])
                finally:
                    if pending.poll() is None:pending.kill();pending.communicate(timeout=5)

    def test_F3_old_native_duplicate_waiting_on_writer_lock_rejects_after_activation(self):
        from pmrh.domain.primitives import canonical
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp,activate=False)
            original=next(e for e in h.store.history()[-1][1]['events'] if e.get('type')!='CHECKPOINT')
            event_path=Path(tmp)/'native-event.json';event_path.write_bytes(canonical(original))
            # Native compatibility before activation, using its actual old event.
            result=done(child('native_duplicate',h.store.root,event_path,'immediate'))[0]
            self.assertTrue(result['ok']);self.assertEqual(result['value']['outcome'],'EXACT_DUPLICATE')
            pending=child('native_duplicate',h.store.root,event_path,'barrier')
            try:
                self.assertEqual(line(pending),'BEFORE_NATIVE_LOCK')
                profile=D.record('PROFILE',profile='SYNTHETIC_TEST_ONLY',project_id=h.project,
                    genesis_commit=h.genesis,setup_head=h.setup.heads[-1],resource_policy='COMPAT_8_20_SURVEY1',pool_id=h.pool.pool_id)
                h.control.apply(h.command('ACTIVATED',dict(profile_ref=h.blob('profile',profile),
                    owner_id='fixture-owner',backend_binding_ref=None)),h.operator)
                head=h.store._head();go(pending);result=done(pending)[0]
                self.assertFalse(result['ok']);self.assertEqual(result['code'],'UNSUPPORTED_CAPABILITY')
                self.assertEqual(Store(h.store.root)._head(),head)
            finally:
                if pending.poll() is None:pending.kill();pending.communicate(timeout=5)

    def test_Q1_direct_same_original_different_ids_usage_and_cursor_rebuild(self):
        from pmrh.ports.dto import core as C, execution as X
        from .test_control import TIME
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(1);p=h.prepare();h.send(p);rid=p['spec'].request_id
            before=h.store.read_snapshot()['requests'][rid]['execution_inbox']['cursor']
            original=h.dispatch(p,'SENT')
            wrapper=deepcopy(original['payload']['receipt']);wrapper['receipt_id']='same-original-new-envelope'
            h.control.apply(h.command('EXECUTION_RECEIVED',{'receipt':wrapper}),h.service)
            raw=C.ExactRef.from_wire(h.blob('usage-raw',b'SYNTHETIC opaque managed usage, no inference count',raw=True))
            usage=X.UsageObservation(identity=p['spec'].identity(),execution_mode=E.ExecutionMode.MANAGED_AGENT,
                coverage=E.UsageCoverage.NONE,observed_at=TIME,raw_evidence_refs=(raw,),values=(),
                parent_usage_ref=None,inclusion=E.UsageInclusion.RELATION_UNKNOWN)
            received=h.receipt(p,'USAGE',usage)
            state=h.store.read_snapshot();request=state['requests'][rid]
            self.assertEqual(request['execution_inbox']['cursor'],before)
            self.assertEqual(request['admission']['charge'],'SPENT_OR_SETTLED')
            self.assertEqual(budget_remaining(state,'BUDGET-synthetic'),0)
            self.assertEqual(len(request['admission']['receipt_ids']),3)
            self.assertEqual(D.read_json(h.store,received['payload']['receipt']['receipt_ref'],h.project),usage.to_wire())
            for directory in ('checkpoints','index'):
                import shutil
                shutil.rmtree(h.store.root/directory,ignore_errors=True)
            state=Store(h.store.root).read_snapshot()
            self.assertEqual(state['requests'][rid]['execution_inbox']['cursor'],before)
            h.page(p,[h.event(p,1)])
            self.assertEqual(Store(h.store.root).read_snapshot()['requests'][rid]['execution_inbox']['cursor']['after_sequence'],1)
            self.assertEqual(budget_remaining(h.store.read_snapshot(),'BUDGET-synthetic'),0)

    def test_crash_real_head_replace_fsync_uncertainty_recovers_original_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp); h.authorize(1); p = h.prepare(); before = h.store._head()
            command = h.command('SEND_STARTED', dict(request_id=p['spec'].request_id, send_boundary_id='fsync-uncertain'))
            config = h.export(Path(tmp)/'uncertain.json', command, mode='send', grant_ref=h.grant(),
                manifest_ref=p['manifest_ref'], fault='head_fsync')
            result = done(child('crash', config))[0]
            self.assertFalse(result['ok']); self.assertEqual(result['code'], 'IO_UNCERTAIN')
            state = Store(h.store.root).read_snapshot()
            self.assertNotEqual(state['_head'], before)
            self.assertEqual(state['requests'][p['spec'].request_id]['execution_state'], 'UNKNOWN')
            recovered = h.control.recover_receipt(h.scope, command['operation_id'], h.service)
            self.assertEqual(recovered['commit'], state['knowledge_commit'])
            duplicate = h.control.send(command, h.service, grant_ref=h.grant(), manifest_ref=p['manifest_ref'], boundary=h.boundary)
            self.assertTrue(duplicate['duplicate']); self.assertEqual(h.boundary.effects, 0)
            self.assertFalse((Path(tmp)/'effects').exists())

    def test_M2_owner_takeover_while_original_process_is_live_keeps_single_main_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp); h.authorize(3); p = h.prepare()
            command = h.command('SEND_STARTED', dict(request_id=p['spec'].request_id, send_boundary_id='still-live'))
            config = h.export(Path(tmp)/'live.json', command, mode='send', grant_ref=h.grant(),
                manifest_ref=p['manifest_ref'], remain_live=True)
            running = child('control', config)
            try:
                self.assertEqual(line(running), 'LIVE'); self.assertIsNone(running.poll())
                proof = h.blob('operator-takeover', b'SYNTHETIC explicit takeover with old invocation still live', raw=True)
                h.control.apply(h.command('OWNER_ACQUIRED', dict(owner_id='next-owner', backend_binding_ref=None,
                    takeover_evidence_refs=[proof])), h.operator)
                state = Store(h.store.root).read_snapshot(); request = state['requests'][p['spec'].request_id]
                self.assertEqual(state['instances'][h.iid]['ownership']['owner_epoch'], 2)
                self.assertEqual(request['admission']['owner_epoch'], 1)
                self.assertTrue(request['fenced']); self.assertFalse(control_lane_closed(request))
                self.assertEqual(request['admission']['charge'], 'UNKNOWN_RESERVED')
                self.assertIsNone(running.poll())
                with self.assertRaises(PMRSError):h.control.send(command, h.service, grant_ref=h.grant(),
                    manifest_ref=p['manifest_ref'], boundary=h.boundary)
                plan = scheduler.plan(state, [h.iid], h.policy)
                self.assertFalse([c for c in plan['selected'] if c['consumer'].get('actor_kind')=='MAIN'])
                h.observation(p, 'TERMINATED')
                self.assertTrue(control_lane_closed(h.store.read_snapshot()['requests'][p['spec'].request_id]))
            finally:
                if running.poll() is None:go(running)
                done(running)
            self.assertEqual((Path(tmp)/'effects').read_text().splitlines(), ['one synthetic first effect'])

    def test_M2_shared_pool_real_8_20_fair_demand_and_release_cursor(self):
        from pmrh.adapters.storage.pool import Pool, RootBinding
        from pmrh.adapters.storage.pool_read import control_pool_view
        from pmrh.domain.primitives import canonical, sha
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)/'shared'; runtime.mkdir()
            pool = Pool(RootBinding.register('shared-runtime', runtime), 'synthetic-test-pool', [])
            projects = []; work = []; mains = []
            for number in range(2):
                h = Harness(Path(tmp)/str(number), pool=pool); h.authorize(24)
                main = h.prepare(actor='MAIN'); h.send(main); h.dispatch(main, 'SENT')
                h.dispatch_workers(main, 8)
                batch = [h.prepare(actor='WORKER') for _ in range(8)]
                for p in batch:h.slot(p)
                projects.append(h); work.append(batch); mains.append(main)
                self.assertEqual(budget_remaining(h.store.read_snapshot(), 'BUDGET-synthetic'), 15)
                with pool.locked():
                    ledger, states, effective, _ = pool.inspect()
                    self.assertEqual(sum(r['project_key']==h.key for r in effective), 8)
                    self.assertTrue(all(r['request_id']!=main['spec'].request_id for r in ledger['slots'].values()))
            with pool.locked():self.assertEqual(len(pool.inspect()[2]), 16)
            # Free real READY calls, preserving release tombstones, and use a
            # further accepted MAIN plan for distinct replacement duties.
            for h, batch, main in zip(projects, work, mains):
                for p in batch[:2]:
                    rid = p['spec'].request_id
                    proof = h.storage.prove_unsent(h.control, h.scope, rid, h.service)
                    h.control.apply(h.command('CANCEL_UNSENT', dict(request_id=rid, not_sent_evidence_ref=proof)), h.service)
                    h.storage.release_slot(h.control, h.scope, rid, h.service)
                h.dispatch_workers(main, 2, label='replacement')
                batch[:2] = [h.prepare(actor='WORKER') for _ in range(2)]
            h = Harness(Path(tmp)/'third', pool=pool); h.authorize(24)
            main = h.prepare(actor='MAIN'); h.send(main); h.dispatch(main, 'SENT'); h.dispatch_workers(main, 8)
            projects.append(h); mains.append(main); work.append([h.prepare(actor='WORKER') for _ in range(8)])
            with pool.locked():
                ledger, states, effective, _ = pool.inspect(); view = control_pool_view(ledger, states)
                self.assertEqual(ledger['cursor'], 4); self.assertEqual(len(effective), 12)
                self.assertEqual(sorted(view['shares'].values()), [6, 7, 7])
                self.assertTrue(all(row['ready']==8 for row in view['demands'].values()))
                keys = sorted(view['shares']); self.assertEqual(view['shares'][keys[(ledger['cursor']+2)%3]], 6)
            # Reach each actual fair share. The next waiter is rejected while
            # capacity still exists; other projects then consume the remainder.
            for h, batch in reversed(list(zip(projects, work))):
                key = sha(canonical([h.key, h.iid])); share = view['shares'][key]
                occupied = 0 if h is projects[-1] else 6
                for p in batch[:share-occupied]:h.slot(p)
                if h is projects[-1]:
                    with pool.locked():self.assertLess(len(pool.inspect()[2]), 20)
                    with self.assertRaisesRegex(PMRSError, 'RESOURCE_WAIT'):h.slot(batch[share])
            with pool.locked():
                ledger, states, effective, _ = pool.inspect()
                self.assertEqual(len(effective), 20); self.assertEqual(ledger['demands'], view['demands'])
            for h, batch in zip(projects, work):
                held = {r['request_id'] for r in ledger['slots'].values() if r['state']=='HELD'}
                waiting = next(p for p in batch if p['spec'].request_id not in held)
                with self.assertRaisesRegex(PMRSError, 'BUDGET_OR_WORKER_LIMIT'):h.slot(waiting)
                plan = scheduler.plan(h.store.read_snapshot(), [h.iid], h.policy)
                self.assertFalse([c for c in plan['selected'] if c['consumer'].get('actor_kind')!='MAIN'])

    def test_M2_shared_survey_one_slot_and_main_is_charged_without_slot(self):
        from pmrh.adapters.storage.pool import Pool, RootBinding
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)/'shared'; runtime.mkdir()
            pool = Pool(RootBinding.register('shared-runtime', runtime), 'synthetic-test-pool', [])
            survey = Harness(Path(tmp)/'survey', kind='SURVEY', pool=pool); survey.authorize(3)
            first = survey.prepare(); survey.slot(first)
            survey.authorize(1, name='next-survey-duty')
            plan = scheduler.plan(survey.store.read_snapshot(), [survey.iid], survey.policy)
            self.assertFalse(plan['selected']); self.assertTrue(any(w['code']=='BUDGET_OR_WORKER_LIMIT' for w in plan['waits']))
            main = Harness(Path(tmp)/'main', pool=pool); main.authorize(1); prepared = main.prepare()
            main.send(prepared)
            self.assertEqual(budget_remaining(main.store.read_snapshot(), 'BUDGET-synthetic'), 0)
            with pool.locked():
                ledger, _, effective, _ = pool.inspect()
                self.assertEqual(len(ledger['projects']), 2); self.assertEqual(len(effective), 1)
                self.assertEqual(effective[0]['request_id'], first['spec'].request_id)

    def test_conflicting_not_sent_after_terminal_release_and_reuse_keeps_original_spend(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(tmp, kind='SURVEY'); h.authorize(2)
            first = h.prepare(); slot = h.slot(first)
            h.send(first); h.dispatch(first, 'SENT'); h.observation(first, 'TERMINATED')
            h.storage.release_slot(h.control, h.scope, first['spec'].request_id, h.service)
            h.authorize(1, name='separately-authorized-next-work')
            second = h.prepare(); h.slot(second)
            self.assertEqual(budget_remaining(h.store.read_snapshot(), 'BUDGET-synthetic'), 1)
            self.assertEqual(budget_remaining(h.store.read_snapshot(), 'BUDGET-separately-authorized-next-work'), 0)
            h.dispatch(first, 'NOT_SENT')
            state = Store(h.store.root).read_snapshot()
            call = state['requests'][first['spec'].request_id]['admission']
            self.assertTrue(call['evidence_conflict'])
            self.assertEqual(call['charge'], 'SPENT_OR_SETTLED')
            self.assertEqual(budget_remaining(state, 'BUDGET-synthetic'), 1)
            self.assertEqual(budget_remaining(state, 'BUDGET-separately-authorized-next-work'), 0)
            with h.pool.locked():
                ledger, _, effective, blocked = h.pool.inspect()
                self.assertEqual(ledger['slots'][slot['payload']['token']]['state'], 'RELEASED')
                self.assertEqual(len(effective), 2); self.assertTrue(blocked)
                with self.assertRaises(PMRSError):h.pool.inspect(sending=True)
            with self.assertRaises(PMRSError):h.send(second)

    def test_M2_two_processes_same_send_have_one_first_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare()
            command=h.command('SEND_STARTED',dict(request_id=p['spec'].request_id,send_boundary_id='once'))
            config=h.export(Path(tmp)/'fixture.json',command,mode='send',grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
            a=child('compete',config);b=child('compete',config)
            self.assertEqual(line(a),'READY');self.assertEqual(line(b),'READY');go(a);go(b)
            results=done(a)+done(b)
            self.assertEqual(len(results),2);self.assertTrue(all(r['ok'] for r in results))
            self.assertEqual(sorted(r['value']['duplicate'] for r in results),[False,True])
            self.assertEqual((Path(tmp)/'effects').read_text().splitlines(),['one synthetic first effect'])
            self.assertEqual(Store(h.store.root).read_snapshot()['requests'][p['spec'].request_id]['execution_state'],'UNKNOWN')

    def test_M2_send_then_pause_keeps_egress_through_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare()
            command=h.command('SEND_STARTED',dict(request_id=p['spec'].request_id,send_boundary_id='before-pause'))
            config=h.export(Path(tmp)/'send.json',command,mode='send',grant_ref=h.grant(),manifest_ref=p['manifest_ref'],barrier=True)
            sending=child('control',config);self.assertEqual(line(sending),'BOUNDARY')
            probe=child('lock',config);self.assertEqual(line(probe),'BLOCKED');done(probe)
            native=W.event(h.store.read_snapshot(),'PAUSE',{'reason':'Synthetic competing pause'},instance_id=h.iid)
            pause=h.export(Path(tmp)/'pause.json',h.command('CONTROL_APPLIED',{'native_event':native}))
            pausing=child('compete',pause);self.assertEqual(line(pausing),'READY');go(pausing)
            # The OS probe established actual lock ownership; no sleep is used
            # as evidence of what the pause process could or could not do.
            go(sending);self.assertTrue(done(sending)[0]['ok']);self.assertTrue(done(pausing)[0]['ok'])
            state=Store(h.store.root).read_snapshot()
            self.assertEqual(state['instances'][h.iid]['status'],'PAUSED')
            self.assertEqual(state['requests'][p['spec'].request_id]['admission']['charge'],'UNKNOWN_RESERVED')

    def test_M2_pause_then_send_rejects_without_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare()
            command=h.command('SEND_STARTED',dict(request_id=p['spec'].request_id,send_boundary_id='after-pause'))
            config=h.export(Path(tmp)/'send.json',command,mode='send',grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
            sending=child('compete',config);self.assertEqual(line(sending),'READY')
            h.pause();go(sending);self.assertFalse(done(sending)[0]['ok'])
            self.assertFalse((Path(tmp)/'effects').exists())
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['admission']['send_phase'],'READY')

    def test_crash_prepare_orphans_and_intent_response_recovery(self):
        for point in ('after_control_freeze','after_control_visit','after_blobs','after_records','after_commit','before_head','after_head'):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);h.authorize(1);p=h.prepare(publish=False);before=h.store._head()
                config=h.export(Path(tmp)/'prepare.json',p['command'],grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'],fault=point)
                done(child('crash',config),73)
                state=Store(h.store.root).read_snapshot()
                if point=='after_head':
                    self.assertIn(p['spec'].request_id,state['requests'])
                    self.assertEqual(state['visits'][p['task']['visit_id']],dict(p['visit']['visit'],outcome=None,exit_evidence=[],unperformed_duties=[]))
                    self.assertEqual(state['missions'][p['task']['mission_id']]['stage_visit_ids'],[p['task']['visit_id']])
                    self.assertEqual(h.control.recover_receipt(h.scope,p['command']['operation_id'],h.service)['commit'],state['knowledge_commit'])
                else:
                    self.assertEqual(h.store._head(),before);self.assertFalse(state['requests'])
                    self.assertFalse(state['visits']);self.assertFalse(state['missions'][p['task']['mission_id']]['stage_visit_ids'])
                    self.assertFalse([e for e in state['execution_events'].values() if e['event_type'] in {'VISIT_OPENED','PREPARE','RESERVE'}])
                result=h.control.apply(p['command'],h.service,grant_ref=p['grant_ref'],manifest_ref=p['manifest_ref'])
                self.assertEqual(result['duplicate'],point=='after_head')
                state=h.store.read_snapshot();self.assertEqual(budget_remaining(state,'BUDGET-synthetic'),0)
                self.assertEqual(len(state['visits']),1)
                self.assertEqual(sum(e['event_type']=='VISIT_OPENED' for e in state['execution_events'].values()),1)
                self.assertEqual(state['requests'][p['task']['request_id']]['execution_state'],'RESERVED')
                h.send(p);sent=Store(h.store.root).read_snapshot()
                self.assertEqual(sent['visits'],state['visits']);self.assertEqual(sent['missions'],state['missions'])

    def test_crash_unknown_before_and_after_first_effect_never_retries(self):
        for point,effects in (('after_head',0),('before_first_effect',0),('after_first_effect',1)):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);h.authorize(1);p=h.prepare()
                command=h.command('SEND_STARTED',dict(request_id=p['spec'].request_id,send_boundary_id='original'))
                config=h.export(Path(tmp)/'send.json',command,mode='send',grant_ref=h.grant(),manifest_ref=p['manifest_ref'],fault=point)
                done(child('crash',config),73)
                request=Store(h.store.root).read_snapshot()['requests'][p['spec'].request_id]
                self.assertEqual(request['execution_state'],'UNKNOWN')
                self.assertEqual(request['admission']['charge'],'UNKNOWN_RESERVED')
                effect_file=Path(tmp)/'effects';self.assertEqual(len(effect_file.read_text().splitlines()) if effect_file.exists() else 0,effects)
                h.control.send(command,h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'],boundary=h.boundary)
                self.assertEqual(h.boundary.effects,0)
                new=h.command('SEND_STARTED',dict(request_id=p['spec'].request_id,send_boundary_id='forbidden-retry'))
                with self.assertRaises(PMRSError):h.control.send(new,h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'],boundary=h.boundary)

    def test_crash_worker_held_before_confirmation_and_terminal_before_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp,kind='SURVEY');h.authorize(2);p=h.prepare();command=h.slot(p,publish=False)
            config=h.export(Path(tmp)/'slot.json',command,mode='slot',grant_ref=h.grant(),manifest_ref=p['manifest_ref'],fault='after_pool_held')
            done(child('crash',config),73)
            request=Store(h.store.root).read_snapshot()['requests'][p['spec'].request_id]
            self.assertIsNone(request['admission']['slot_token'])
            with h.pool.locked():self.assertEqual(len(h.pool.inspect()[2]),1)
            with self.assertRaises(PMRSError):h.send(p)
            h.storage.acquire_slot(h.control,command,h.service,grant_ref=h.grant(),manifest_ref=p['manifest_ref'])
            h.send(p);h.observation(p,'TERMINATED')
            state=Store(h.store.root).read_snapshot();request=state['requests'][p['spec'].request_id]
            self.assertNotEqual(request['execution_state'],'SETTLED');self.assertTrue(request['fenced'])
            with h.pool.locked():self.assertEqual(len(h.pool.inspect()[2]),1)
            first=h.storage.release_slot(h.control,h.scope,p['spec'].request_id,h.service)
            second=h.storage.release_slot(h.control,h.scope,p['spec'].request_id,h.service)
            self.assertEqual(first,second)
            with h.pool.locked():self.assertEqual(h.pool.inspect()[2],[])

    def test_crash_held_then_pause_cancel_releases_original_unconfirmed_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp,kind='SURVEY');h.authorize(2);p=h.prepare();command=h.slot(p,publish=False)
            config=h.export(Path(tmp)/'slot.json',command,mode='slot',grant_ref=h.grant(),manifest_ref=p['manifest_ref'],fault='after_pool_held')
            done(child('crash',config),73);h.pause();rid=p['spec'].request_id
            proof=h.storage.prove_unsent(h.control,h.scope,rid,h.service)
            h.control.apply(h.command('CANCEL_UNSENT',dict(request_id=rid,not_sent_evidence_ref=proof)),h.service)
            h.storage.release_slot(h.control,h.scope,rid,h.service)
            with h.pool.locked():
                ledger,_,risk,_=h.pool.inspect();self.assertEqual(risk,[])
                self.assertEqual(ledger['slots'][command['payload']['token']]['state'],'RELEASED')
            # A real original contradicting the local proof is quarantined;
            # the old tombstone is retained even though confirmation was lost.
            h.dispatch(p,'SENT')
            with h.pool.locked():
                ledger,_,risk,blocked=h.pool.inspect();self.assertTrue(blocked);self.assertEqual(len(risk),1)
                self.assertEqual(ledger['slots'][command['payload']['token']]['state'],'RELEASED')

    def test_conflicting_sent_after_slot_and_budget_reuse_preserves_tombstone(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp,kind='SURVEY');h.authorize(1);first=h.prepare();slot=h.slot(first);h.send(first);h.dispatch(first,'NOT_SENT')
            h.storage.release_slot(h.control,h.scope,first['spec'].request_id,h.service)
            second=h.prepare();h.slot(second);h.send(second);h.dispatch(second,'SENT')
            late=h.dispatch(first,'SENT',publish=False)
            config=h.export(Path(tmp)/'conflict.json',late,fault='after_head')
            done(child('crash',config),73)
            # Actual process death after conflict HEAD, before any pool scan.
            state=Store(h.store.root).read_snapshot();self.assertEqual(budget_remaining(state,'BUDGET-synthetic'),-1)
            with h.pool.locked():
                ledger,_,risk,blocked=h.pool.inspect();self.assertEqual(len(risk),2);self.assertTrue(blocked)
                self.assertEqual(ledger['slots'][slot['payload']['token']]['state'],'RELEASED')
                with self.assertRaises(PMRSError):h.pool.inspect(sending=True)

    def test_crash_inbox_receipts_charge_and_cursor_are_atomic(self):
        for point in ('after_blobs','after_commit','before_head','after_head'):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);h.authorize(1);p=h.prepare();h.send(p)
                command,page=h.page(p,[h.event(p,1)],publish=False)
                config=h.export(Path(tmp)/'page.json',command,fault=point)
                done(child('crash',config),73)
                request=Store(h.store.root).read_snapshot()['requests'][p['spec'].request_id]
                committed=point=='after_head'
                self.assertEqual(request['execution_inbox']['cursor']['after_sequence'],int(committed))
                self.assertEqual(request['admission']['receipt_ids'],['event:1'] if committed else [])
                self.assertEqual(request['admission']['charge'],'SPENT_OR_SETTLED' if committed else 'UNKNOWN_RESERVED')
                h.control.apply(command,h.service)
                for path in (h.store.root/'checkpoints').glob('*.json'):path.unlink()
                state=Store(h.store.root).read_snapshot();self.assertEqual(state['requests'][p['spec'].request_id]['admission']['receipt_ids'],['event:1'])
                head=h.store._head();h.control.apply(command,h.service);self.assertEqual(h.store._head(),head)

    def test_Q1_gap_contiguous_partial_refill_and_duplicate_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare();h.send(p)
            cursor=V.EventCursor.from_wire(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['cursor'])
            gap=V.EventGap(first_missing_sequence=1,last_missing_sequence=2,reason=E.GapReason.DISCONTINUITY,resnapshot_ref=None)
            h.page(p,status=E.PageStatus.GAP,gap=gap)
            h.dispatch(p,'NOT_SENT');request=h.store.read_snapshot()['requests'][p['spec'].request_id]
            self.assertEqual(request['admission']['charge'],'UNKNOWN_RESERVED');self.assertFalse(control_releasable(request))
            h.page(p,status=E.PageStatus.EMPTY)
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['state'],'GAP')
            # Confirmed NOT_SENT contradicts later RUNNING; both originals must
            # be retained, including while the stream is incomplete.
            one=h.event(p,1);first,_=h.page(p,[one],start=cursor)
            inbox=h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']
            self.assertEqual(inbox['gap']['first_missing_sequence'],2)
            two=h.event(p,2,'TERMINATED');h.page(p,[two])
            request=Store(h.store.root).read_snapshot()['requests'][p['spec'].request_id]
            self.assertEqual(request['execution_inbox']['state'],'OPEN')
            self.assertTrue(request['admission']['evidence_conflict']);self.assertFalse(control_lane_closed(request))
            head=h.store._head();h.control.apply(first,h.service);self.assertEqual(h.store._head(),head)
            h.page(p,[one],start=cursor);self.assertEqual(h.store._head(),head)

    def test_Q1_ahead_diagnostic_does_not_register_events_or_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare();h.send(p)
            zero=V.EventCursor.from_wire(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['cursor'])
            ahead=replace(zero,after_sequence=2,last_event_id='event:2')
            h.page(p,[h.event(p,3)],start=ahead)
            request=h.store.read_snapshot()['requests'][p['spec'].request_id]
            self.assertEqual(request['execution_inbox']['cursor']['after_sequence'],0)
            self.assertEqual(request['admission']['receipt_ids'],[])
            self.assertNotIn(p['spec'].request_id,h.store._control_index.streams)
            h.page(p,[h.event(p,1),h.event(p,2)],start=zero)
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['state'],'OPEN')
            # The original diagnostic event was not consumed; it may now be
            # ingested from the exact durable cursor, once.
            h.page(p,[h.event(p,3)])
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['cursor']['after_sequence'],3)

    def test_Q1_overlap_and_same_id_changed_bytes_reject_whole_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare();h.send(p)
            zero=V.EventCursor.from_wire(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['cursor'])
            one=h.event(p,1);h.page(p,[one],start=zero);head=h.store._head()
            with self.assertRaises(PMRSError):h.page(p,[one,h.event(p,2)],start=zero)
            self.assertEqual(h.store._head(),head)
            changed=h.event(p,1,'TERMINATED',event_id='event:1')
            with self.assertRaises(PMRSError):h.page(p,[changed],start=zero)
            self.assertEqual(h.store._head(),head)

    def test_Q1_wrong_producer_scope_payload_or_sequence_rejects_entire_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2);p=h.prepare();h.send(p)
            one=h.event(p,1);two=h.event(p,2)
            command,page=h.page(p,[one,two],publish=False);head=h.store._head()
            mutations=(lambda w:w['events'][1]['envelope'].update(instance_id='different-instance'),
                lambda w:w['events'][1].update(sequence=3),
                lambda w:w['events'][1]['envelope'].update(payload_sha256='0'*64),
                lambda w:w['events'][1]['envelope'].update(actor_principal_ref=h.blob('other-producer',b'Unregistered producer',raw=True)),
                lambda w:w['events'][1].update(kind='CUSTOM'),
                lambda w:w['events'][1]['envelope'].update(actor_kind='HUMAN'))
            for mutate in mutations:
                wire=deepcopy(page.to_wire());mutate(wire)
                invalid=deepcopy(command);invalid['payload']['page_ref']=h.blob('invalid-page',wire)
                with self.assertRaises((PMRSError,ValueError,TypeError)):h.control.apply(invalid,h.service)
                self.assertEqual(h.store._head(),head)
                self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['cursor']['after_sequence'],0)
            h.control.apply(command,h.service)
            self.assertEqual(h.store.read_snapshot()['requests'][p['spec'].request_id]['execution_inbox']['cursor']['after_sequence'],2)
            head=h.store._head();ledger=h.pool.read()
            with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                h.control.apply(command,h.session(actions=set(D.PAYLOAD_FIELDS)-{'INBOX_PAGE_RECEIVED'}))
            self.assertEqual(h.store._head(),head);self.assertEqual(h.pool.read(),ledger)

    def test_compatibility_exact_native_trace_and_old_reader_head_asof_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            values=[]
            for variant in ('baseline','current'):
                output=Path(tmp)/(variant+'.json')
                done(child('oracle',variant,'trace',Path(tmp)/variant,output))
                values.append(json.loads(output.read_text()))
            self.assertEqual(values[0],values[1])
            h=Harness(Path(tmp)/'control');head=h.store._head()
            for action in ('read','historical:'+h.genesis,'write'):
                output=Path(tmp)/'old.json';done(child('oracle','baseline',action,h.store.root,output))
                self.assertFalse(json.loads(output.read_text())['ok']);self.assertEqual(h.store._head(),head)
