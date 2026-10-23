"""Same-instance native control and fast command pairs; real authority only."""
from copy import deepcopy
import tempfile
import unittest
from pmrh.application.control import Session
from pmrh.domain.primitives import canonical,sha,PMRSError
from pmrh.domain.fastmath.model import FastMathError
from pmrh.adapters.storage import control as D
from .fixtures import Harness,six_entries,delta_for


class ControlFastTests(unittest.TestCase):
    def test_source41_scan_spec_errors_match_public_decode_after_read_json(self):
        from unittest.mock import patch
        from tests.devpr06.test_control import Harness as NativeHarness
        from pmrh.adapters.storage.journal import Journal, _apply_delta, _persistent
        from pmrh.ports.dto import enums as E, specs as S, wire as W
        original_read_json = D.read_json
        original_read_ref = D.read_ref
        for factory in (NativeHarness, Harness):
            with self.subTest(profile=factory.__module__), tempfile.TemporaryDirectory() as tmp:
                h = factory(tmp); h.authorize(1); prepared = h.prepare()
                journal = Journal(h.store.root); expected = journal.read_snapshot()
                history = journal.history(); combined = factory is Harness
                head_bytes = (h.store.root/'HEAD').read_bytes()
                index = D.scan(journal, history, _apply_delta, combined=combined)
                self.assertEqual(index.states[history[-1][0]['commit']], _persistent(expected))
                good = prepared['spec'].to_wire()
                wrong_schema = dict(good, schema_version='unsupported', dto_type='ModelSelection')
                wrong_type = dict(good, dto_type='ModelSelection')
                missing = dict(good, unexpected=None); missing.pop('request_id')
                semantic = dict(good, owner_epoch=0)
                deep = None
                for _ in range(W.MAX_WIRE_DEPTH + 1): deep = [deep]
                # Conflicting schema/type defects must not precede the first
                # structural budget; a non-object still rejects with its old code.
                cases = [
                    ('non-object', [], E.ErrorCode.TYPE_MISMATCH),
                    ('schema-before-identity', wrong_schema, E.ErrorCode.UNSUPPORTED_SCHEMA_VERSION),
                    ('fixed-dto-identity', wrong_type, E.ErrorCode.INVALID_WIRE),
                    ('missing-before-extra', missing, E.ErrorCode.MISSING_FIELD),
                    ('constructor-semantic', semantic, E.ErrorCode.INVALID_FIELD),
                    ('depth-before-schema', dict(wrong_schema, unexpected=deep), E.ErrorCode.INVALID_FIELD),
                    ('array-before-root-type', [None]*(W.MAX_TUPLE_ITEMS + 1), E.ErrorCode.INVALID_FIELD),
                ]
                for name, value, code in cases:
                    with self.subTest(case=name):
                        replacement = h.blob('source41:'+name, value)
                        with self.assertRaises(W.ContractViolation) as oracle:
                            S.AgentInvocationSpec.from_wire(original_read_json(h.store, replacement, h.project))
                        self.assertEqual(oracle.exception.code, code)
                        selected = []

                        def select_spec_blob(store, reference, project, *, maximum=D.MAX_JSON_BYTES):
                            if reference == prepared['spec_ref'] and not selected:
                                selected.append(reference)
                                # Inject only the reference at scan's first spec
                                # conversion. Authenticate the replacement with
                                # the actual read_ref reader; scan must still
                                # parse, canonical-check, budget and decode it.
                                return original_read_ref(store, replacement, project, maximum=maximum)
                            return original_read_ref(store, reference, project, maximum=maximum)

                        with patch.object(D, 'read_ref', side_effect=select_spec_blob):
                            with self.assertRaises(W.ContractViolation) as caught:
                                D.scan(journal, history, _apply_delta, combined=combined)
                        self.assertEqual(selected, [prepared['spec_ref']])
                        self.assertIs(type(caught.exception), type(oracle.exception))
                        self.assertEqual(caught.exception.code, oracle.exception.code)
                        self.assertEqual(str(caught.exception), str(oracle.exception))
                        self.assertEqual((h.store.root/'HEAD').read_bytes(), head_bytes)
                self.assertEqual(Journal(h.store.root).read_snapshot(), expected)

    def test_source42_spec_cache_uses_fresh_bytes_and_stays_scan_local(self):
        import sys
        from dataclasses import FrozenInstanceError
        from unittest.mock import patch
        from tests.devpr06.test_control import Harness as NativeHarness
        from pmrh.adapters.storage.io import _ConfinedReader
        from pmrh.adapters.storage.journal import Journal, _apply_delta, _persistent
        from pmrh.ports.dto import specs as S, wire as W
        read_ref, decode, identity = D.read_ref, W._decode_dto, S.AgentInvocationSpec.identity
        for factory in (NativeHarness, Harness):
            with self.subTest(profile=factory.__module__), tempfile.TemporaryDirectory() as tmp:
                h = factory(tmp); h.authorize(1); prepared = h.prepare(); h.pause()
                journal = Journal(h.store.root); expected = journal.read_snapshot()
                history = journal.history(); combined = factory is Harness
                head_bytes = (h.store.root/'HEAD').read_bytes()
                good = prepared['spec'].to_wire(); good_raw = canonical(good)
                alternate = dict(good, correlation_id='source42-alternate')
                alternate_ref = h.blob('source42-alternate', alternate)
                previous = []
                with _ConfinedReader(h.store.root) as reader:
                    store = Journal(h.store.root, reader=reader)
                    for change_bytes in (False, False, True):
                        reads, decoded, observed = [], [], []

                        def read_current(store, reference, project, *, maximum=D.MAX_JSON_BYTES):
                            # Observe this exact scan conversion, excluding the
                            # independent public-decoder reads that must remain.
                            if sys._getframe(1).f_code is not D.scan.__code__ or reference != prepared['spec_ref']:
                                return read_ref(store, reference, project, maximum=maximum)
                            before = (reader.remaining_files, reader.remaining_bytes)
                            selected = alternate_ref if change_bytes and reads else reference
                            raw = read_ref(store, selected, project, maximum=maximum)
                            reads.append((raw, before, (reader.remaining_files, reader.remaining_bytes)))
                            return raw

                        def decode_current(cls, value):
                            result = decode(cls, value)
                            if cls is S.AgentInvocationSpec and sys._getframe(1).f_code is D.scan.__code__:
                                decoded.append(result)
                            return result

                        def observe_identity(spec):
                            if sys._getframe(1).f_code is D.scan.__code__: observed.append(spec)
                            return identity(spec)

                        with patch.object(D, 'read_ref', read_current), patch.object(W, '_decode_dto', decode_current), patch.object(S.AgentInvocationSpec, 'identity', observe_identity):
                            index = D.scan(store, history, _apply_delta, combined=combined)
                        self.assertEqual(len(reads), 2); self.assertEqual(len(observed), 2)
                        self.assertEqual(len(decoded), 2 if change_bytes else 1)
                        self.assertIs(observed[0], decoded[0])
                        if change_bytes:
                            self.assertIs(observed[1], decoded[1])
                            self.assertIsNot(observed[0], observed[1])
                            self.assertEqual(observed[1].correlation_id, alternate['correlation_id'])
                        else:
                            self.assertIs(observed[0], observed[1])
                        self.assertEqual(reads[0][0], good_raw)
                        self.assertEqual(reads[1][0], canonical(alternate) if change_bytes else good_raw)
                        for raw, before, after in reads:
                            self.assertEqual(before[0] - after[0], 1)
                            self.assertEqual(before[1] - after[1], len(raw))
                        # Even a second scan on the same reader must decode anew.
                        for prior in previous: self.assertIsNot(observed[0], prior)
                        previous.append(observed[0])
                        with self.assertRaises(FrozenInstanceError): observed[0].owner_epoch = 0
                        with self.assertRaises(FrozenInstanceError): observed[0].model_selection.model_id = 'caller-only'
                        exported = observed[0].to_wire()
                        exported['model_selection']['model_id'] = 'caller-only'
                        exported['capability_requirements']['continuation'].append('caller-only')
                        self.assertEqual(observed[0].to_wire(), good)
                        self.assertEqual(index.states[history[-1][0]['commit']], _persistent(expected))
                self.assertEqual((h.store.root/'HEAD').read_bytes(), head_bytes)
                self.assertEqual(Journal(h.store.root).read_snapshot(), expected)

    def test_source42_spec_cache_hit_preserves_corruption_and_read_quota_refusal(self):
        import sys
        from unittest.mock import patch
        from tests.devpr06.test_control import Harness as NativeHarness
        from pmrh.adapters.storage.io import _ConfinedReader, _Unavailable
        from pmrh.adapters.storage.journal import Journal, _apply_delta
        from pmrh.ports.dto import specs as S, wire as W
        read_ref, decode = D.read_ref, W._decode_dto
        for factory in (NativeHarness, Harness):
            with self.subTest(profile=factory.__module__), tempfile.TemporaryDirectory() as tmp:
                h = factory(tmp); h.authorize(1); prepared = h.prepare(); h.pause()
                journal = Journal(h.store.root); expected = journal.read_snapshot()
                history = journal.history(); combined = factory is Harness
                blob_path = h.store.root/'blobs'/prepared['spec_ref']['sha256']
                original = blob_path.read_bytes(); head_bytes = (h.store.root/'HEAD').read_bytes()
                for failure in ('corruption', 'file-quota', 'byte-quota'):
                    with self.subTest(failure=failure):
                        reads, decoded = [], []

                        def decode_current(cls, value):
                            result = decode(cls, value)
                            if cls is S.AgentInvocationSpec and sys._getframe(1).f_code is D.scan.__code__:
                                decoded.append(result)
                            return result

                        def read_current(store, reference, project, *, maximum=D.MAX_JSON_BYTES):
                            if sys._getframe(1).f_code is not D.scan.__code__ or reference != prepared['spec_ref']:
                                return read_ref(store, reference, project, maximum=maximum)
                            if reads:
                                self.assertEqual(len(reads), 1)
                                self.assertEqual(len(decoded), 1)  # A real entry is already cached.
                                if failure == 'corruption': blob_path.write_bytes(original[:-1] + b' ')
                                elif failure == 'file-quota': reader.remaining_files = 0
                                else: reader.remaining_bytes = len(original) - 1
                            row = [(reader.remaining_files, reader.remaining_bytes)]
                            reads.append(row)
                            try:
                                return read_ref(store, reference, project, maximum=maximum)
                            finally:
                                row.append((reader.remaining_files, reader.remaining_bytes))

                        try:
                            with _ConfinedReader(h.store.root) as reader:
                                store = Journal(h.store.root, reader=reader)
                                with patch.object(D, 'read_ref', read_current), patch.object(W, '_decode_dto', decode_current):
                                    with self.assertRaises(PMRSError if failure == 'corruption' else _Unavailable) as caught:
                                        D.scan(store, history, _apply_delta, combined=combined)
                            if failure == 'corruption': self.assertEqual(caught.exception.code, 'BLOB_CHANGED')
                            else: self.assertEqual(caught.exception.reason, 'QUERY_READ_LIMIT')
                            self.assertEqual(len(reads), 2); self.assertEqual(len(decoded), 1)
                            self.assertEqual(reads[0][0][0] - reads[0][1][0], 1)
                            self.assertEqual(reads[0][0][1] - reads[0][1][1], len(original))
                            before, after = reads[1]
                            self.assertEqual(before[0] - after[0], 0 if failure == 'file-quota' else 1)
                            self.assertEqual(before[1] - after[1], len(original) if failure == 'corruption' else 0)
                            self.assertEqual((h.store.root/'HEAD').read_bytes(), head_bytes)
                        finally:
                            if failure == 'corruption': blob_path.write_bytes(original)
                self.assertEqual(Journal(h.store.root).read_snapshot(), expected)

    def test_source39_native_and_combined_replay_snapshot_isolation(self):
        from tests.devpr06.test_control import Harness as NativeHarness
        from pmrh.adapters.storage.journal import Journal, _persistent
        for factory, schema in ((NativeHarness, 'pmrh.commit/2'), (Harness, 'pmrh.control-fast.commit/1')):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as tmp:
                h=factory(tmp)
                observed=[h.store.read_snapshot(h.setup.heads[-1]), h.store.read_snapshot()]
                h.authorize(3);observed.append(h.store.read_snapshot())
                main=h.prepare();observed.append(h.store.read_snapshot())
                h.send(main);h.dispatch(main,'SENT');h.pause()
                observed.append(h.store.read_snapshot())
                journal=Journal(h.store.root);current=journal.read_snapshot()
                history=journal.history();index=journal._control_index
                first=next(i for i,(_,entry) in enumerate(history) if entry['schema']==schema)
                self.assertGreaterEqual(first,2)
                self.assertEqual(len(index.states),len(history))
                self.assertTrue(all(entry['schema']==schema for _,entry in history[first:]))
                for expected in observed:
                    commit=expected['knowledge_commit']
                    self.assertEqual(index.states[commit],_persistent(expected))
                    returned=journal.read_snapshot(commit)
                    returned_index=journal._control_index
                    self.assertEqual(returned,expected)
                    returned['capabilities']['CAP-HUMAN']['actions'].append('caller-only')
                    returned['instances'][h.iid]['mission_ids'].append('caller-only')
                    self.assertEqual(index.states[commit],_persistent(expected))
                    self.assertEqual(returned_index.states[commit],_persistent(expected))
                for (prior,_),(head,entry) in zip(history[first-1:],history[first:]):
                    before=index.states[prior['commit']];after=index.states[head['commit']]
                    self.assertIsNot(before['instances'][h.iid]['run_control'],after['instances'][h.iid]['run_control'])
                    event=next(e for e in entry['events'] if e.get('type')!='CHECKPOINT')
                    saved_before=deepcopy(before);saved_after=deepcopy(after)
                    D.validate_transition(before,after,event)
                    self.assertEqual(before,saved_before);self.assertEqual(after,saved_after)
                # A real PAUSE transition rejects a hidden authority change;
                # its failure leaves the cached historical input untouched too.
                bad=deepcopy(after);bad['capabilities']['CAP-HUMAN']['actions'].append('ungranted')
                saved_bad=deepcopy(bad)
                with self.assertRaises(PMRSError) as caught:D.validate_transition(before,bad,event)
                self.assertEqual(caught.exception.code,'CAPABILITY_VIOLATION')
                self.assertEqual(before,saved_before);self.assertEqual(bad,saved_bad)
                current['instances'][h.iid]['run_control']['control_version']=-1
                self.assertEqual(Journal(h.store.root).read_snapshot(),observed[-1])

    def test_source39_combined_fast_replay_validators_preserve_prior_state(self):
        from pmrh.adapters.storage.journal import Journal, _persistent
        from pmrh.adapters.storage.fastmath import validate_effects
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();state=h.store.read_snapshot()
            _,captured,_=h.capture_fast(worker,delta_for(state,worker['task'],six_entries(state,worker['task'])))
            applied,_=h.apply_fast(captured['proposal_ref'],main)
            expected=h.reopen();journal=Journal(h.store.root)
            self.assertEqual(journal.read_snapshot(),expected)
            index=journal._control_index;seen=[]
            for head,entry in journal.history():
                event=next(e for e in entry['events'] if e.get('type')!='CHECKPOINT')
                if event.get('type') not in {'FAST_PROPOSAL_CAPTURED','FAST_DELTA_APPLIED'}:continue
                seen.append(event['type'])
                before=index.states[entry['previous_commit']['commit']];after=index.states[head['commit']]
                saved_before=deepcopy(before);saved_after=deepcopy(after)
                decision=D.read_json(journal,event['decision_ref'],h.project)
                validate_effects(journal,before,after,event,decision)
                self.assertEqual(before,saved_before);self.assertEqual(after,saved_after)
                bad=deepcopy(after);bad['fast_receipts'][event['operation_id']]['outcome']='unpublished-outcome'
                saved_bad=deepcopy(bad)
                with self.assertRaises(FastMathError) as caught:validate_effects(journal,before,bad,event,decision)
                self.assertEqual(caught.exception.code,'FAST_INTEGRITY_ERROR')
                self.assertEqual(before,saved_before);self.assertEqual(bad,saved_bad)
            self.assertEqual(seen,['FAST_PROPOSAL_CAPTURED','FAST_DELTA_APPLIED'])
            captured_state=index.states[captured['commit']];applied_state=index.states[applied['commit']]
            key=captured['proposal_ref']['sha256']
            self.assertEqual(captured_state['fast_proposals'][key]['status'],'PENDING')
            self.assertEqual(applied_state['fast_proposals'][key]['status'],'APPLIED')
            self.assertIsNot(captured_state['fast_proposals'][key],applied_state['fast_proposals'][key])
            self.assertEqual(applied_state,_persistent(expected))
            historical=journal.read_snapshot(captured['commit'])
            historical_index=journal._control_index
            historical['fast_proposals'][key]['proposal_ref']['object_id']='caller-only'
            self.assertEqual(captured_state['fast_proposals'][key]['proposal_ref'],captured['proposal_ref'])
            self.assertEqual(historical_index.states[captured['commit']],captured_state)
            self.assertEqual(Journal(h.store.root).read_snapshot(),expected)

    def test_source39_native_and_combined_replay_reject_old_corruption(self):
        from tests.devpr06.test_control import Harness as NativeHarness
        from pmrh.adapters.storage.journal import Journal
        for factory in (NativeHarness,Harness):
            with self.subTest(profile=factory.__module__),tempfile.TemporaryDirectory() as tmp:
                h=factory(tmp);h.authorize(2);h.pause()
                journal=Journal(h.store.root);expected=journal.read_snapshot();history=journal.history()
                first=next(i for i,(_,entry) in enumerate(history) if entry['schema'] in {'pmrh.commit/2','pmrh.control-fast.commit/1'})
                old_path=h.store.root/history[first][0]['path']
                source=next(iter(expected['sources'].values()))
                blob_path=h.store.root/'blobs'/source['blob_hash']
                head_bytes=(h.store.root/'HEAD').read_bytes()
                for path,code in ((old_path,'COMMIT_CHANGED'),(blob_path,'BLOB_CHANGED')):
                    with self.subTest(corruption=code):
                        original=path.read_bytes()
                        try:
                            path.write_bytes(original+b' ')
                            with self.assertRaises(PMRSError) as caught:Journal(h.store.root).read_snapshot()
                            self.assertEqual(caught.exception.code,code)
                            self.assertEqual((h.store.root/'HEAD').read_bytes(),head_bytes)
                        finally:path.write_bytes(original)
                        self.assertEqual(Journal(h.store.root).read_snapshot(),expected)

    def test_source28_prepare_malformed_delta_closed_and_current_authority(self):
        from pmrh.domain.fastmath.model import FastReadContext, MAX_REVISIONS
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();state=h.store.read_snapshot()
            context=FastReadContext(h.project,h.iid,worker['task']['mission_id'],worker['task']['task_id'])
            session=h.session();h.storage.fast.bind_read_context(context,session)
            service=h.store.fastmath_service();head=h.store._head()
            good=delta_for(state,worker['task'],six_entries(state,worker['task']))
            malformed=[('empty',{}),('null',None),('list',[])]
            missing=deepcopy(good);missing.pop('input_commit');malformed.append(('missing-input',missing))
            for path,value in [
                (('scope',),None), (('input_commit',),[]), (('read_guards',),None),
                (('read_guards',0),{}), (('read_guards',0,'identity'),[]),
                (('expected_selected',),[]), (('expected_selected','module'),{}),
                (('revision_entries',),{}), (('revision_entries',0),None),
                (('revision_entries',0,'body'),[]), (('revision_entries',0,'body','kind'),[]),
                (('revision_entries',0,'body','payload'),None),
                (('revision_entries',0,'body','payload','claim_slots'),[]),
                (('revision_entries',0,'body','payload','claim_slots','result'),{}),
                (('revision_entries',0,'body','payload','claim_slots','result','statement_ref'),{}),
                (('revision_entries',5,'body','payload','support_ids'),[[]]),
                (('revision_entries',5,'body','payload','requirement'),None),
                (('same_claim_links',),None), (('same_claim_links',),[{}]),
            ]:
                bad=deepcopy(good);parent=bad
                for key in path[:-1]:parent=parent[key]
                parent[path[-1]]=value;malformed.append((str(path),bad))
            for name,bad in malformed:
                with self.subTest(shape=name):
                    with self.assertRaises(FastMathError) as caught:
                        service.prepare_delta(bad,read_context=context,as_of_commit=state['knowledge_commit'])
                    self.assertEqual(caught.exception.code,'FAST_SCHEMA_INVALID')
                    self.assertEqual(h.store._head(),head)
            empty=delta_for(state,worker['task'],[],empty_reason='No new evidence in this bounded attempt.')
            for value in (empty,good):
                prepared=service.prepare_delta(value,read_context=context,as_of_commit=state['knowledge_commit'])
                self.assertEqual(prepared.raw,canonical(value))
            oversized=deepcopy(empty);oversized['revision_entries']=[good['revision_entries'][4]]*(MAX_REVISIONS+1)
            with self.assertRaises(FastMathError) as caught:
                service.prepare_delta(oversized,read_context=context,as_of_commit=state['knowledge_commit'])
            self.assertEqual(caught.exception.code,'FAST_LIMIT_EXCEEDED')
            hidden=deepcopy(empty);hidden['reason']='KR-unavailable-private-reference'
            with self.assertRaises(FastMathError) as caught:
                service.prepare_delta(hidden,read_context=context,as_of_commit=state['knowledge_commit'])
            self.assertEqual(caught.exception.code,'FAST_REF_UNAVAILABLE')
            self.assertNotIn(hidden['reason'],str(caught.exception))
            unregistered=FastReadContext(h.project,h.iid,worker['task']['mission_id'],worker['task']['task_id'])
            with self.assertRaises(FastMathError) as caught:
                service.prepare_delta({},read_context=unregistered,as_of_commit=state['knowledge_commit'])
            self.assertEqual(caught.exception.code,'FAST_AUTHORITY_DENIED')
            h.registry.revoke(session)
            for value in ({},good):
                with self.assertRaises(FastMathError) as caught:
                    service.prepare_delta(value,read_context=context,as_of_commit=state['knowledge_commit'])
                self.assertEqual(caught.exception.code,'FAST_AUTHORITY_DENIED')
            self.assertEqual(h.store._head(),head)
            self.assertEqual(h.reopen(),state)

    def test_FM23_FM25_PAUSED_worker_ingress_retains_without_MAIN_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot()
            delta=delta_for(s,worker['task'],six_entries(s,worker['task']))
            # Seal through actual native receipt ingress, then pause before the
            # fast proposal publication. Preserve original attempt epoch.
            from pmrh.domain.fastmath.model import FastReadContext
            context=FastReadContext(h.project,h.iid,worker['task']['mission_id'],worker['task']['task_id'])
            h.storage.fast.bind_read_context(context,h.service)
            prepared=h.store.fastmath_service().prepare_delta(delta,read_context=context,as_of_commit=s['knowledge_commit'])
            output,_=h.capture(worker,canonical({'payload':{'fast_delta':delta}}));h.pause()
            state=h.store.read_snapshot();request=state['requests'][worker['spec'].request_id]
            receipt=next(state['execution_events'][r]['receipt_ref'] for r in request['admission']['receipt_ids'] if state['execution_events'][r].get('receipt_kind')=='CAPTURE')
            args=h.fast_arguments('paused-ingress',h.ingress(worker['spec'].request_id),request_id=worker['spec'].request_id,capture_ref=output,receipt_ref=receipt)
            captured=h.store.fastmath_service().capture_delta(prepared,**args)
            after=h.reopen();self.assertEqual(after['instances'][h.iid]['status'],'PAUSED');self.assertEqual(after.get('fast_selected',{}),{})
            self.assertEqual(after['requests'],state['requests']);self.assertEqual(after['usage'],state['usage'])
            with self.assertRaises(FastMathError):h.apply_fast(captured['proposal_ref'],main)
            self.assertEqual(h.store._head()['commit'],captured['commit'])

    def test_FM18_FM25_current_registry_required_even_on_exact_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot()
            prepared,captured,args=h.capture_fast(worker,delta_for(s,worker['task'],six_entries(s,worker['task'])))
            for session in (Session('forged'),h.session(proposal_only=True),h.session(human=True),h.session(actions=set())):
                with self.subTest(session=session.session_id):
                    with self.assertRaises(FastMathError):h.store.fastmath_service().capture_delta(prepared,**{**args,'session':session})
            self.assertEqual(h.store._head()['commit'],captured['commit'])
            h.registry.revoke(args['session'])
            with self.assertRaises(FastMathError):h.store.fastmath_service().capture_delta(prepared,**args)
            with self.assertRaises(FastMathError):h.store.fastmath_service().recover_receipt(h.scope,captured['operation_id'],args['session'])

    def test_FM23_unknown_liability_preserved_and_old_epoch_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(main_status='UNKNOWN');s=h.store.read_snapshot()
            # The running MAIN remains an original invocation, never restarted.
            _,captured,_=h.capture_fast(worker,delta_for(s,worker['task'],six_entries(s,worker['task'])))
            before=h.store.read_snapshot();self.assertEqual(before['requests'][main['spec'].request_id]['execution_state'],'UNKNOWN')
            result,args=h.apply_fast(captured['proposal_ref'],main);after=h.reopen()
            for name in ('requests','usage','budget_grants','instances'):self.assertEqual(before[name],after[name])
            self.assertEqual(h.boundary.effects,2)
            evidence=h.blob('takeover',b'Explicit synthetic takeover',raw=True)
            h.control.apply(h.command('OWNER_ACQUIRED',dict(owner_id='new-owner',backend_binding_ref=None,takeover_evidence_refs=[evidence])),h.operator)
            head=h.store._head()
            with self.assertRaises(FastMathError):h.store.fastmath_service().commit_delta(captured['proposal_ref'],**args)
            self.assertEqual(h.store._head(),head)

    def test_FM20_native_control2_and_combined_are_distinct(self):
        from tests.devpr06.test_control import Harness as NativeHarness
        with tempfile.TemporaryDirectory() as tmp:
            old=NativeHarness(tmp);before=old.store._head()
            value=old.command('FAST_DELTA_APPLIED',{'proposal_ref':old.producer})
            with self.assertRaises(PMRSError):old.control.apply(value,old.service)
            self.assertEqual(old.store._head(),before)
            with self.assertRaises(PMRSError):old.store.fastmath_service()
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);history=h.store.history()
            self.assertEqual(history[-1][1]['schema'],'pmrh.control-fast.commit/1')
            self.assertEqual(history[-1][1]['events'][0]['schema'],'pmrh.control-fast-event/1')
            from research_studio.storage_compat import CombinedSyntheticSetup
            with self.assertRaises(PMRSError):CombinedSyntheticSetup(h.store.root,kind='TRH',inputs=(b'Cannot replace old root.',))


    def test_FM23_actual_pool_native_and_combined_wrongpool_pairs(self):
        from pathlib import Path
        from tests.devpr06.test_control import Harness as NativeHarness
        from pmrh.adapters.storage.pool import Pool,RootBinding
        from research_studio.store import Store
        for factory,schema in ((NativeHarness,'pmrh.commit/2'),(Harness,'pmrh.control-fast.commit/1')):
            with self.subTest(schema=schema),tempfile.TemporaryDirectory() as tmp:
                h=factory(tmp);h.authorize(2)
                expected=Store(h.store.root).read_snapshot()
                with h.pool.locked():ledger,states,effective,blocked=h.pool.inspect()
                self.assertEqual(states[h.key],expected)
                self.assertEqual(h.store.history()[-1][1]['schema'],schema)
                self.assertEqual(effective,[]);self.assertFalse(blocked)
                wrongroot=Path(tmp)/'wrong-pool';wrongroot.mkdir()
                wrong=Pool(RootBinding.register('wrong-runtime',wrongroot),'different-pool',[h.binding])
                wrong.register(h.binding.binding_id,genesis=h.genesis,project=h.project)
                before=wrong.read()
                with wrong.locked(),self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                    wrong.inspect()
                self.assertEqual(wrong.read(),before);self.assertEqual(h.pool.read(),ledger)
                self.assertEqual(Store(h.store.root).read_snapshot(),expected)

    def test_FM23_combined_pool_rejects_corrupt_unknown_mixed_unvalidated(self):
        # Only adversarial journal inputs are forged. Each positive root is
        # produced by actual native setup and authorized shared Control calls.
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(2)
            head=h.store._head();entry=h.store._commit_record(head)
            head_bytes=(h.store.root/'HEAD').read_bytes();original=(h.store.root/head['path']).read_bytes()
            before=Store(h.store.root).read_snapshot();ledger=h.pool.read()
            for attack in ('corrupt','unknown','mixed','unvalidated'):
                with self.subTest(attack=attack):
                    changed=deepcopy(entry)
                    if attack=='corrupt':(h.store.root/head['path']).write_bytes(original+b'corrupt')
                    else:
                        if attack=='unknown':changed['schema']='pmrh.control-fast.commit/unknown'
                        elif attack=='mixed':
                            changed['schema']='pmrh.commit/2'
                            for event in changed['events']:
                                if event.get('schema')=='pmrh.control-fast-event/1':event['schema']=D.EVENT_SCHEMA
                        else:
                            event=next(e for e in changed['events'] if e.get('schema')=='pmrh.control-fast-event/1')
                            event['decision_ref']=h.blob('unvalidated-decision',{'schema':'unvalidated'})
                        raw=canonical(changed);digest=sha(raw);relative='journal/%012d-%s.json'%(head['sequence'],digest)
                        (h.store.root/relative).write_bytes(raw)
                        (h.store.root/'HEAD').write_bytes(canonical(dict(sequence=head['sequence'],commit=digest,path=relative)))
                    try:
                        with h.pool.locked(),self.assertRaises(PMRSError):h.pool.inspect()
                        self.assertEqual(h.pool.read(),ledger)
                    finally:
                        (h.store.root/'HEAD').write_bytes(head_bytes)
                        (h.store.root/head['path']).write_bytes(original)
                    self.assertEqual(Store(h.store.root).read_snapshot(),before)
            with h.pool.locked():self.assertEqual(h.pool.inspect()[1][h.key],before)

    def test_FM23_native_combined_pause_unknown_reservation_and_budget_pairs(self):
        from tests.devpr06.test_control import Harness as NativeHarness
        from research_studio import scheduler
        for factory in (NativeHarness,Harness):
            with self.subTest(profile=factory.__module__),tempfile.TemporaryDirectory() as tmp:
                h=factory(tmp);h.authorize(2,attempts=2)
                main=h.prepare();h.send(main);h.dispatch(main,'SENT');h.dispatch_workers(main,2)
                worker=h.prepare(actor='WORKER');h.slot(worker);send=h.send(worker)
                state=h.store.read_snapshot();request=state['requests'][worker['spec'].request_id]
                self.assertEqual(request['execution_state'],'UNKNOWN')
                self.assertEqual(request['admission']['charge'],'UNKNOWN_RESERVED')
                with h.pool.locked():ledger,states,effective,blocked=h.pool.inspect(sending=True)
                self.assertEqual(len(effective),1);self.assertFalse(blocked)
                self.assertEqual(effective[0]['reservation_ref'],request['admission']['reservation_ref'])
                self.assertFalse(scheduler.plan(state,[h.iid],h.policy)['selected'])
                # Exact duplicate cannot cause an UNKNOWN request's second effect.
                h.control.send(send,h.service,grant_ref=worker['grant_ref'],manifest_ref=worker['manifest_ref'],boundary=h.boundary)
                self.assertEqual(h.boundary.effects,2);self.assertEqual(h.pool.read(),ledger)
                h.pause();paused=h.store.read_snapshot()
                self.assertEqual(paused['instances'][h.iid]['status'],'PAUSED')
                self.assertEqual(paused['requests'][worker['spec'].request_id]['admission']['reservation_ref'],request['admission']['reservation_ref'])
                with h.pool.locked():after,states,effective,blocked=h.pool.inspect()
                self.assertEqual(after,ledger);self.assertEqual(len(effective),1)
                self.assertFalse(scheduler.plan(paused,[h.iid],h.policy)['selected'])
                self.assertEqual(h.boundary.effects,2)


    def test_FM23_FM25_acquire_slot_uses_trusted_profile_and_rejects_wrong_schema(self):
        from tests.devpr06.test_control import Harness as NativeHarness
        for factory in (NativeHarness,Harness):
            with self.subTest(profile=factory.__module__),tempfile.TemporaryDirectory() as tmp:
                h=factory(tmp);h.authorize(3);main=h.prepare();h.send(main);h.dispatch(main,'SENT')
                h.dispatch_workers(main,1);worker=h.prepare(actor='WORKER');value=h.slot(worker,publish=False)
                head=h.store._head();ledger=h.pool.read();wrong=deepcopy(value)
                wrong['schema']=D.EVENT_SCHEMA if h.storage.combined else 'pmrh.control-fast-event/1'
                with self.assertRaisesRegex(PMRSError,'UNSUPPORTED_SCHEMA_VERSION'):
                    h.storage.acquire_slot(h.control,wrong,h.service,grant_ref=h.grant(),manifest_ref=worker['manifest_ref'])
                self.assertEqual(h.store._head(),head);self.assertEqual(h.pool.read(),ledger)
                h.storage.acquire_slot(h.control,value,h.service,grant_ref=h.grant(),manifest_ref=worker['manifest_ref'])
                with h.pool.locked():after,states,effective,blocked=h.pool.inspect()
                self.assertEqual(len(effective),1);self.assertFalse(blocked)
                self.assertEqual(effective[0]['request_id'],worker['spec'].request_id)
                self.assertEqual(states[h.key]['requests'][worker['spec'].request_id]['admission']['slot_token'],value['payload']['token'])



    def test_source18_FM25_distinct_authenticated_producer_request_and_role(self):
        from datetime import timedelta
        from .fixtures import NOW
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();state=h.reopen()
            prepared,captured,args=h.capture_fast(worker,delta_for(state,worker['task'],six_entries(state,worker['task'])))
            other=h.blob('source18-other-producer',b'SYNTHETIC distinct authenticated ingress principal',raw=True)
            authentication=dict(scope=h.scope,root_binding_id=h.binding.binding_id,principal_ref=other,
                authn_evidence_ref=other,authority_ref=other,actions={'FAST_PROPOSAL_CAPTURED','RECOVER_RECEIPT'},
                issued_at=NOW-timedelta(minutes=1),expires_at=NOW+timedelta(hours=1),owner_id=None,
                human=False,proposal_only=False,request_ids={main['spec'].request_id})
            wrong_request=h.registry.register_fast_ingress(request_id=main['spec'].request_id,**authentication)
            wrong_role=h.registry.authenticate(**{**authentication,'request_ids':{worker['spec'].request_id},'human':True})
            head=h.store._head()
            for session in (wrong_request,wrong_role):
                with self.assertRaises(FastMathError):h.store.fastmath_service().capture_delta(prepared,**{**args,'session':session})
                self.assertEqual(h.store._head(),head)
            # Exact original receipt ownership cannot be rebound to this other
            # producer. This uses the real trusted registry, not a forged replay.
            request=h.store.read_snapshot()['requests'][worker['spec'].request_id]
            with self.assertRaises(PMRSError):
                h.registry.original(args['receipt_ref'],producer_ref=other,
                    binding_ref=request['execution_inbox']['binding_ref'],identity=worker['spec'].identity().to_wire())
            self.assertEqual(h.store.fastmath_service().capture_delta(prepared,**args)['commit'],captured['commit'])
            self.assertEqual(h.store._head(),head)
            self.assertEqual(h.reopen()['requests'][worker['spec'].request_id]['capture_ref'],args['capture_ref']['sha256'])


    def test_source16_FM18_FM25_expiry_root_request_and_manifest_retry_pairs(self):
        from datetime import timedelta
        from .fixtures import NOW
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();state=h.reopen()
            prepared,captured,capture_args=h.capture_fast(worker,delta_for(state,worker['task'],six_entries(state,worker['task'])))
            self.assertEqual(h.store.fastmath_service().capture_delta(prepared,**capture_args)['commit'],captured['commit'])
            before=h.store._head()
            for replacement in ({'request_id':main['spec'].request_id},
                    {'receipt_ref':{**capture_args['receipt_ref'],'object_id':'wrong-original-receipt'}}):
                with self.subTest(field=next(iter(replacement))),self.assertRaises(FastMathError):
                    h.store.fastmath_service().capture_delta(prepared,**{**capture_args,**replacement})
                self.assertEqual(h.store._head(),before)
            applied,args=h.apply_fast(captured['proposal_ref'],main);before=h.store._head()
            wrongroot=h.registry.authenticate(scope=h.scope,root_binding_id='foreign-root',principal_ref=h.producer,
                authn_evidence_ref=h.producer,authority_ref=h.producer,actions={'FAST_DELTA_APPLIED','RECOVER_RECEIPT'},
                issued_at=NOW-timedelta(minutes=1),expires_at=NOW+timedelta(hours=1),owner_id='fixture-owner',
                acting_request_id=main['spec'].request_id)
            for replacement in ({'session':wrongroot},{'manifest_ref':{**main['manifest_ref'],'object_id':'wrong-manifest'}}):
                with self.subTest(field=next(iter(replacement))),self.assertRaises(FastMathError):
                    h.store.fastmath_service().commit_delta(captured['proposal_ref'],**{**args,**replacement})
                self.assertEqual(h.store._head(),before)
            self.assertEqual(h.store.fastmath_service().commit_delta(captured['proposal_ref'],**args)['commit'],applied['commit'])
            h.registry.clock=lambda:NOW+timedelta(hours=2)
            for call in (lambda:h.store.fastmath_service().commit_delta(captured['proposal_ref'],**args),
                    lambda:h.store.fastmath_service().capture_delta(prepared,**capture_args),
                    lambda:h.store.fastmath_service().recover_receipt(h.scope,applied['operation_id'],args['session'])):
                with self.assertRaises(FastMathError):call()
                self.assertEqual(h.store._head(),before)

    def test_source13_native_rejection_exact_replay_and_current_authority(self):
        from pmrh.adapters.storage.journal import Journal
        from pmrh.adapters.storage.control_fast import validate_rejection
        from research_studio import changes
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(4,attempts=4,communication=True)
            main=h.prepare();h.send(main);h.dispatch(main,'SENT');state=h.store.read_snapshot()
            _,captured,args=h.capture_fast(main,delta_for(state,main['task'],six_entries(state,main['task'])))
            before=h.store.read_snapshot();rid=main['spec'].request_id
            raw=h.store.read_blob(args['capture_ref']['sha256'])
            diagnostics=changes.response_diagnostics(main['task'],before,raw,h.store.read_blob)
            value=h.command('SCIENCE_ADMITTED',dict(request_id=rid,capture_ref=args['capture_ref']))
            session=h.session(acting_request_id=rid)
            for grant,manifest in ((None,main['manifest_ref']),(h.grant(),None)):
                with self.assertRaises(PMRSError):h.control.apply(value,session,grant_ref=grant,manifest_ref=manifest)
            self.assertEqual(h.store._head(),before['_head'])
            receipt=h.control.apply(value,session,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            after=h.reopen();request=after['requests'][rid]
            self.assertEqual(request['acceptance_state'],'REJECTED_CONTRACT')
            self.assertEqual(request['admission_diagnostic']['details'],diagnostics['diagnostics'])
            self.assertFalse(request['admission_diagnostic']['format_repair_eligible'])
            head,entry=h.store.history()[-1];event=entry['events'][0]
            decision=D.read_json(h.store,event['decision_ref'],h.project)
            self.assertEqual(entry['accepted_request_bindings'],[])
            validate_rejection(h.store,before,after,event,decision,[])
            self.assertEqual(Journal(h.store.root).read_snapshot()['requests'][rid],request)
            for path in (h.store.root/'checkpoints').glob('*.json'):path.unlink()
            self.assertEqual(Journal(h.store.root).read_snapshot()['requests'][rid],request)
            settles=[e for key,e in after['execution_events'].items() if key not in before['execution_events'] and e.get('event_type')=='SETTLE']
            self.assertEqual(len(settles),1);eid=settles[0]['event_id']
            for mutation in ('diagnostic','time','time_in_window','charge','science','accepted','decision','capture'):
                bad=deepcopy(after);ev=deepcopy(event);dec=deepcopy(decision);accepted=[]
                if mutation=='diagnostic':bad['requests'][rid]['admission_diagnostic']['message']='forged'
                elif mutation=='time':bad['execution_events'][eid]['payload']['issued_at']='2000-01-01T00:00:00Z'
                elif mutation=='time_in_window':
                    from datetime import timedelta
                    bad['execution_events'][eid]['payload']['issued_at']=(D.timestamp(decision['issued_at'])+timedelta(seconds=1)).isoformat().replace('+00:00','Z')
                elif mutation=='charge':bad['requests'][rid]['admission']['charge']='RELEASED'
                elif mutation=='science':bad['records'].clear()
                elif mutation=='accepted':accepted=[{'request_id':rid}]
                elif mutation=='decision':dec['capability_manifest_ref']=None
                else:ev['payload']['capture_ref']=captured['proposal_ref']
                with self.subTest(mutation=mutation),self.assertRaises(PMRSError):
                    validate_rejection(h.store,before,bad,ev,dec,accepted)
            duplicate=h.control.apply(value,session,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            self.assertEqual(duplicate['commit'],receipt['commit'])
            h.registry.revoke(session)
            with self.assertRaises(PMRSError):h.control.apply(value,session,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            self.assertEqual(h.store._head()['commit'],receipt['commit'])
            # Actual immutable evidence corruption must also fail bare replay.
            path=h.store.root/'blobs'/event['decision_ref']['sha256'];path.write_bytes(b'corrupt')
            with self.assertRaises(PMRSError):Journal(h.store.root).read_snapshot()

    def test_source13_original_native_entry_FORMAT_and_SETTLE_clock_compatibility(self):
        from research_studio import contracts as C,changes,execution,research_audit,strategy,demo
        from pmrh.domain import native_response as N,native_settlement as S
        self.assertIs(C.authoring_contract,N.authoring_contract)
        self.assertIs(strategy.authoring_schema,N.strategy_authoring_schema)
        self.assertIs(research_audit.authoring_schema,N.audit_authoring_schema)
        self.assertIs(research_audit.DEFAULT_POLICY,S.DEFAULT_POLICY)
        self.assertEqual(C.RESPONSE_SCHEMA,'pmrs.response/4.2.2')
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();state=h.store.read_snapshot()
            raw=canonical({'payload':{'fast_delta':{}}})
            with self.assertRaises(PMRSError) as native:
                changes.validate_response(main['task'],state,raw,blob_get=h.store.read_blob)
            self.assertEqual((native.exception.code,native.exception.message),
                ('RESPONSE_SCHEMA_INVALID','/schema: expected Required field'))
            bounded=N.bounded_fast_rejection(main['task'],state,raw)
            self.assertEqual((bounded['code'],bounded['message']),(native.exception.code,native.exception.message))
            self.assertEqual(bounded['details'],changes.response_diagnostics(main['task'],state,raw,h.store.read_blob)['diagnostics'])
            self.assertIsNone(N.bounded_fast_rejection(worker['task'],state,raw))
            format_task={**main['task'],'repair_kind':'FORMAT'}
            self.assertIsNone(N.bounded_fast_rejection(format_task,state,raw))
            with self.assertRaisesRegex(PMRSError,'REPAIR_SCIENCE_UNVERIFIABLE'):
                changes.validate_response(format_task,state,raw,blob_get=h.store.read_blob)
            envelope=demo.response(worker['task'],state,blob_get=h.store.read_blob)
            self.assertIsNone(N.bounded_fast_rejection(worker['task'],state,envelope))
            # Native success and its full diagnostics still execute all later checks.
            changes.validate_response(worker['task'],state,envelope,blob_get=h.store.read_blob)
            captured,_=h.capture(worker,envelope);state=h.store.read_snapshot();rid=worker['spec'].request_id
            at='2026-10-21T12:00:10Z';start='2026-10-21T12:00:00Z'
            unit=deepcopy(state)
            unit['research_clocks'][h.iid]=research_audit.initial_clock(unit,h.iid,start)
            payload=dict(request_id=rid,acceptance_state='REJECTED_CONTRACT',receipt_ref=None,error='RESPONSE_SCHEMA_INVALID',issued_at=at)
            native_event=execution.event('SETTLE',payload);pure_event=S.event(payload)
            self.assertEqual(native_event,pure_event)
            pure=S.apply_event(unit,pure_event);legacy=execution.apply_event(unit,native_event,h.store.read_blob)
            self.assertEqual(legacy,pure)
            self.assertEqual(pure['research_clocks'][h.iid]['last_observed_at'],at)
            self.assertEqual(pure['research_clocks'][h.iid]['effective_seconds'],10)
            self.assertEqual(S.apply_event(pure,pure_event),pure)
            for bad in ({**pure_event,'capability_ref':'missing'},
                        {**pure_event,'payload':{**payload,'acceptance_state':'INVENTED'}},
                        {**pure_event,'payload':{**payload,'request_id':'missing'}}):
                with self.assertRaises(PMRSError):S.apply_event(unit,bad)
            conflict=deepcopy(pure_event);conflict['payload']['error']='different'
            with self.assertRaisesRegex(PMRSError,'ALREADY_SETTLED_CONTENT_CONFLICT'):S.apply_event(pure,conflict)


    def test_source13_control_v2_rejection_stays_nondurable_and_native_success(self):
        from tests.devpr06.test_control import Harness as NativeControlHarness
        from .fixtures import scientific_worker
        from research_studio import demo
        with tempfile.TemporaryDirectory() as tmp:
            h=NativeControlHarness(tmp);h.authorize(4,attempts=4,communication=True)
            main=h.prepare();h.send(main);h.dispatch(main,'SENT')
            worker=scientific_worker(h,main,'source13-native-v2')
            captured,_=h.capture(main,canonical({'payload':{'fast_delta':{}}}))
            before=h.store._head()
            with self.assertRaisesRegex(PMRSError,'RESPONSE_SCHEMA_INVALID'):
                h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=main['spec'].request_id,capture_ref=captured)),
                    h.service,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            self.assertEqual(h.store._head(),before)
            self.assertEqual(h.store.read_snapshot()['requests'][main['spec'].request_id]['execution_state'],'CAPTURED')
            capture,_=h.capture(worker,demo.response(worker['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=worker['spec'].request_id,capture_ref=capture)),h.service)
            state=h.store.read_snapshot()
            self.assertEqual(state['requests'][worker['spec'].request_id]['acceptance_state'],'ACCEPTED')
            self.assertEqual(h.store.history()[-1][1]['schema'],'pmrh.commit/2')
