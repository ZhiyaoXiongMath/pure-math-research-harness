"""S2 authored actual-Journal tests; known pool profile blocker is not patched."""
from copy import deepcopy
import tempfile
import unittest
from pmrh.domain.primitives import canonical,sha,PMRSError
from pmrh.domain.fastmath.model import FastMathError
from pmrh.adapters.storage.journal import Journal
from .fixtures import Harness,six_entries,delta_for


def source21_FM07_persisted_donor_and_open_target():
    """Public S2 pair: exact donor proof survives, missing target transfer stays open."""
    import json
    from research_studio import demo,input_delivery,knowledge_access as Q,strategy
    from research_studio.task_tools import TaskTools
    from research_studio.store import Store
    from pmrh.domain import knowledge as K,assurance as A
    from pmrh.domain.fastmath.validation import native_projection,claim_fingerprint
    from .fixtures import scientific_worker,admit_scientific_response
    from .test_domain import rehash
    check=unittest.TestCase()
    with tempfile.TemporaryDirectory() as tmp:
        h=Harness(tmp);h.authorize(4,attempts=4,communication=True)
        main=h.prepare();h.send(main);h.dispatch(main,'SENT')
        target=h.store.read_snapshot()['instances'][h.iid]['target_ref']
        author=scientific_worker(h,main,'source21-donor')
        envelope=json.loads(demo.response(author['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
        body='For every integer n satisfying condition T, n + 0 = n.'
        loc=K.locator(body);hypothesis=K.locator(body,body.index('condition T'),body.index('condition T')+len('condition T'))
        donor_op=dict(op='NEW',local_key='donor',kind='Statement',context_refs=[],body=body,
            data=dict(statement_locator=loc,scope_context_refs=[],hypothesis_locators=[hypothesis],
                conclusion_locators=[loc],quantifier_locators=[loc],form='PROPOSITION',representation='AUTHORED',source_binding=None))
        argument_op=deepcopy(envelope['payload']['operations'][0])
        argument_op['data']['conclusion_ref']='local:donor'
        envelope['payload']['operations']=[donor_op,argument_op]
        for effect in envelope['payload']['obligation_effects']:
            effect['evidence_refs']=['local:donor','local:'+argument_op['local_key']]
        admit_scientific_response(h,author,envelope)
        state=h.reopen();support=next(iter(state['supports'].values()))
        donor=support['statement_ref'];argument=support['argument_ref'];sid=support['support_id']
        check.assertNotEqual(donor,target)
        check.assertEqual(state['records'][donor]['data']['hypothesis_locators'],[hypothesis])
        check.assertEqual(state['records'][target]['data']['hypothesis_locators'],[])
        # Actual delivery/confirmation supplies both new native bodies to MAIN
        # before it assigns an independent review of this distinct donor.
        for ref in (donor,argument):
            command=h.command('COMMUNICATION_APPLIED',{})
            frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                did,response=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id).call('knowledge_get',{'ref':ref})
            check.assertFalse(response['isError'],response)
            command=h.command('COMMUNICATION_APPLIED',{})
            frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**frame):
                input_delivery.confirm(h.store,main['spec'].request_id,main['spec'].execution_id,did)
            check.assertIn(ref,input_delivery.supplied_records(h.store.read_snapshot(),main['task'],h.store.read_blob,live=True))
        state=h.store.read_snapshot();st=strategy.current(state,h.iid)
        proposal=dict(schema='pmrs.strategy-proposal/1',base_strategy_revision=st['revision'],
            trigger_refs=list(st['pending_trigger_refs']),route_updates=[],input_plan_proposals=[],
            work_items=[dict(key='source21-donor-review',stage_id='P4',role='PROOF',purpose='DEFAULT',obligation_type='VERIFY',
                question='Review the exact donor proof under its declared condition T.',
                success_criterion='Check the complete donor statement and argument; do not infer applicability to the original target.',
                target_refs=[donor],input_refs=[donor,argument],source_refs=[],depends_on=[],route_key='',communication_group=None)],
            progress_account=dict(summary='A candidate donor proof needs independent exact review.',record_refs=[donor,argument],
                remaining_difficulties=['Condition T is absent from the original target.'],scope_limitations=['SYNTHETIC_TEST_ONLY'],
                failed_or_unperformed=['No target applicability proof.'],covered_binding_ids=[],frontier_complete=False),
            direction_answers=[],next_action='CONTINUE',human_decision_needed=[],no_change_reason=None)
        command=h.command('STRATEGY_APPLIED',{'native_event':{}})
        frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
        with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
            strategy.dispatch_from_main(h.store,main['spec'].request_id,proposal,'source21-donor-review')
        review=h.prepare(actor='WORKER');h.slot(review);h.send(review);h.dispatch(review,'SENT')
        check.assertNotEqual(review['spec'].request_id,author['spec'].request_id)
        requirement=review['task']['required_assurance']
        envelope=json.loads(demo.response(review['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
        op=envelope['payload']['operations'][0]
        op['body']='Synthetic exact donor review under declared condition T; no real mathematical or target applicability claim.'
        op['data'].update(verdict='SUPPORTED_WITHIN_SCOPE',unchecked=[],checked=[
            dict(ref=row['target_ref'],locators=row['locators'],aspect=aspect,**{k:row[k] for k in A.SCOPE_META})
            for row in requirement['required_scope'] for aspect in row['aspects']])
        admit_scientific_response(h,review,envelope)
        state=h.reopen();support=deepcopy(state['supports'][sid]);native=deepcopy(state['records'])
        requirement=support['consumer_requirement'];policy=support['policy_digest']
        check.assertEqual(A.evaluate_requirement(state,sid,requirement,policy)['result'],'QUALIFIED')
        check.assertFalse(any(v['statement_ref']==target for v in state['supports'].values()))
        # Reuse the existing six-kind constructors, changing only authored
        # proposal fields. No persisted/native snapshot is replaced or patched.
        entries=six_entries(state,main['task']);upper,probe,binding=entries[0],entries[2],entries[-1]
        slot=native_projection(state,donor,argument)
        upper['body']['payload'].update(title='Exact donor under T',input_refs=[donor],output_ref=donor,
            obstacle='The original target has no condition T.',open_conditions=[],claim_slots={'result':slot})
        upper['body']['dependencies']=[donor,argument];rehash(upper)
        binding['body']['payload'].update(upper_revision_ref=upper['ref'],claim_fingerprint=claim_fingerprint(slot),
            statement_ref=donor,argument_ref=argument,context_refs=sorted(slot['context_fields']),support_ids=[sid],
            requirement=requirement,policy_digest=policy,required_review_scope=requirement['required_scope'],
            open_conditions=slot['argument_fields']['open_conditions'],applicability_refs=[],invalidation_refs=[sid])
        binding['body']['dependencies']=[upper['ref'],donor,argument];rehash(binding)
        probe['body']['payload'].update(title='Missing target applicability of donor T',unknown_ref=target,
            question='Can condition T be discharged for the original target without changing its hypotheses?',
            frozen_input_refs=[target,donor,argument],
            outcomes=[dict(outcome='NO_PROGRESS',consequence='Retain donor qualification; original target applicability remains OPEN.',evidence_refs=[donor,argument])])
        probe['body']['dependencies']=[target,donor,argument];rehash(probe)
        _,captured,args=h.capture_fast(main,delta_for(state,main['task'],[upper,probe,binding]))
        original=h.store.read_blob(args['capture_ref']['sha256'])
        h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=main['spec'].request_id,capture_ref=args['capture_ref'])),
            h.service,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
        check.assertEqual(h.reopen()['requests'][main['spec'].request_id]['acceptance_state'],'REJECTED_CONTRACT')
        h.observation(main,'TERMINATED')
        reader=h.prepare(actor='MAIN');h.send(reader);h.dispatch(reader,'SENT')
        check.assertNotEqual(reader['spec'].request_id,main['spec'].request_id)
        applied,_=h.apply_fast(captured['proposal_ref'],reader);state=h.reopen()
        check.assertEqual(h.store.read_blob(args['capture_ref']['sha256']),original)
        check.assertEqual(state['records'],native);check.assertEqual(state['supports'][sid],support)
        check.assertEqual(state['instances'][h.iid]['target_ref'],target)
        check.assertEqual(A.evaluate_requirement(state,sid,requirement,policy)['result'],'QUALIFIED')
        for historical in (False,True):
            extra={'as_of_commit':applied['commit']} if historical else {}
            human=Q.web_tool(Store(h.store.root),'get',dict(ref=[upper['ref']],instance_id=[h.iid],**{k:[v] for k,v in extra.items()}))
            command=h.command('COMMUNICATION_APPLIED',{})
            frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=reader['manifest_ref']):
                did,response=TaskTools(h.store,reader['spec'].request_id,reader['spec'].execution_id).call('knowledge_get',dict(ref=upper['ref'],**extra))
            check.assertFalse(response['isError'],response)
            delivered=json.loads(response['content'][0]['text'])['result']
            for view in (human,delivered):
                result=view['derived']['bindings'][0]['qualification']
                check.assertEqual(result['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
                check.assertEqual(result['project_applicability'],'OPEN')
                check.assertEqual(result['exact_claim'],slot);check.assertEqual(result['applicability_results'],[])
            check.assertEqual(h.store.read_snapshot()['input_deliveries'][did]['supplements'],[])
        probe_view=Q.web_tool(Store(h.store.root),'get',{'ref':[probe['ref']],'instance_id':[h.iid]})
        check.assertEqual(probe_view['payload']['unknown_ref'],target)
        check.assertEqual(probe_view['payload']['question'],probe['body']['payload']['question'])
        check.assertEqual(probe_view['payload']['outcomes'][0]['outcome'],'NO_PROGRESS')


def measured_knowledge_query(label, operation):
    """Transparent, query-local accounting; never replace a result or a budget."""
    import json
    from unittest.mock import patch
    from pmrh.adapters.storage.io import _ConfinedReader
    original_read=_ConfinedReader.read
    original_body=_ConfinedReader.read_verified_body
    original_snapshot=Journal.read_snapshot
    readers={};phases=['query'];error=None
    def row(reader):
        # Keep the reader object alive: recycled object ids cannot merge readers.
        return readers.setdefault(reader,dict(reader=len(readers)+1,metadata={},body={}))
    def counter(reader,kind,path):
        return row(reader)[kind].setdefault((phases[-1],path),dict(
            calls=0,charged_attempts=0,successful_reads=0,successful_bytes=0,
            charged_bytes=0,integrity_probe_attempts=0,integrity_probe_bytes=0,errors=[]))
    def read(reader,relative,*args,**kwargs):
        item=counter(reader,'metadata',relative);item['calls']+=1
        before=(reader.remaining_files,reader.remaining_bytes)
        try:
            result=original_read(reader,relative,*args,**kwargs)
            if result is not None:
                item['successful_reads']+=1;item['successful_bytes']+=len(result)
            return result
        except BaseException as exc:
            item['errors'].append(repr(exc));raise
        finally:
            item['charged_attempts']+=before[0]-reader.remaining_files
            item['charged_bytes']+=before[1]-reader.remaining_bytes
    def body(reader,digest,*args,**kwargs):
        item=counter(reader,'body',digest);item['calls']+=1;budget=kwargs['budget']
        before=(budget.remaining_files,budget.remaining_bytes,budget.integrity_probe_attempts,budget.integrity_probe_bytes)
        try:
            result=original_body(reader,digest,*args,**kwargs)
            item['successful_reads']+=1
            item['successful_bytes']+=before[1]-budget.remaining_bytes
            return result
        except BaseException as exc:
            item['errors'].append(repr(exc));raise
        finally:
            item['charged_attempts']+=before[0]-budget.remaining_files
            item['charged_bytes']+=before[1]-budget.remaining_bytes
            item['integrity_probe_attempts']+=budget.integrity_probe_attempts-before[2]
            item['integrity_probe_bytes']+=budget.integrity_probe_bytes-before[3]
    def snapshot(journal,commit=None):
        phases.append('current_snapshot' if commit is None else 'as_of_snapshot')
        try:return original_snapshot(journal,commit)
        finally:phases.pop()
    def summarize(items):
        paths={path for phase,path in items};calls=sum(item['calls'] for item in items.values())
        counts={key:sum(item[key] for item in items.values()) for key in (
            'charged_attempts','successful_reads','successful_bytes','charged_bytes',
            'integrity_probe_attempts','integrity_probe_bytes')}
        return dict(calls=calls,unique_paths=len(paths),repeat_calls=calls-len(paths),**counts)
    try:
        with patch.object(_ConfinedReader,'read',read),patch.object(_ConfinedReader,'read_verified_body',body),patch.object(Journal,'read_snapshot',snapshot):
            return operation()
    except BaseException as exc:
        error=repr(exc);raise
    finally:
        output=[]
        for reader,record in readers.items():
            report=dict(reader=record['reader'],remaining_metadata_attempts=reader.remaining_files,
                remaining_metadata_bytes=reader.remaining_bytes)
            for kind in ('metadata','body'):
                items=record[kind]
                report[kind]=dict(total=summarize(items),phases={phase:summarize({key:value for key,value in items.items() if key[0]==phase})
                    for phase in sorted({key[0] for key in items})},paths=[dict(phase=phase,path=path,**value)
                    for (phase,path),value in sorted(items.items())])
            output.append(report)
        print('SOURCE10_QUERY_MEASUREMENTS '+json.dumps(dict(label=label,error=error,readers=output),sort_keys=True),flush=True)


def fm19_combined_quantitative_capacity_case():
    """Explicit selector only: real combined closure exhaustion, never lower caps."""
    import json
    import resource
    import time
    from unittest.mock import patch
    from pmrh.adapters.storage.io import _ConfinedReader, _Unavailable
    from pmrh.adapters.storage import control as D
    check=unittest.TestCase()
    for dimension,count,size in (('files',4096,64),('bytes',128,1024**2)):
        with tempfile.TemporaryDirectory() as tmp:
            started=time.monotonic();report=dict(dimension=dimension,input_count=count,input_bytes=count*size,
                metadata_max_attempts=4096,metadata_max_bytes=128*1024**2,phases=[])
            h=Harness(tmp);main,worker=h.running_pair();state=h.reopen()
            entries=six_entries(state,worker['task'])
            _,captured,_=h.capture_fast(worker,delta_for(state,worker['task'],entries))
            before=h.reopen();head=h.store._head();head_bytes=(h.store.root/'HEAD').read_bytes()
            check.assertEqual(h.store._commit_record(head)['schema'],'pmrh.control-fast.commit/1')
            check.assertEqual(before['fast_proposals'][captured['proposal_ref']['sha256']]['status'],'PENDING')
            # Legal raw takeover evidence reaches the same combined closure as
            # the already captured fast proposal; no port /1 batch is grafted in.
            refs=[]
            for number in range(count):
                prefix=('SYNTHETIC source19 '+dimension+' '+str(number)+'\n').encode()
                raw=prefix+b'x'*(size-len(prefix))
                check.assertEqual(len(raw),size)
                refs.append(h.blob('source19-'+dimension+'-'+str(number),raw,raw=True))
            del raw
            digests={ref['sha256'] for ref in refs};check.assertEqual(len(digests),count)
            paths={'blobs/'+digest for digest in digests}
            check.assertEqual(sum((h.store.root/'blobs'/digest).stat().st_size for digest in digests),count*size)
            value=h.command('OWNER_ACQUIRED',dict(owner_id='source19-next-owner',backend_binding_ref=None,takeover_evidence_refs=refs))
            D.command(value,combined=True)
            check.assertLess(len(canonical(value)),8*1024**2)
            check.assertEqual(h.store._head(),head)  # Sealing originals is not publication.
            real_read=_ConfinedReader.read;real_preflight=Journal._preflight_extended_head
            failures=[];candidates=[];preflight_active=[];initial_budgets={}
            def observe_read(reader,relative,*args,**kwargs):
                initial_budgets.setdefault(reader,(reader.remaining_files,reader.remaining_bytes))
                try:return real_read(reader,relative,*args,**kwargs)
                except _Unavailable as exc:
                    failures.append(dict(reader=reader,path=relative,reason=exc.reason,
                        preflight=bool(preflight_active),remaining_files=reader.remaining_files,
                        remaining_bytes=reader.remaining_bytes,maximum=args[0] if args else kwargs.get('maximum',64*1024**2)))
                    raise
            def observe_preflight(journal,candidate):
                candidates.append(deepcopy(candidate));preflight_active.append(candidate)
                try:return real_preflight(journal,candidate)
                finally:preflight_active.pop()
            try:
                with patch.object(_ConfinedReader,'read',observe_read),patch.object(Journal,'_preflight_extended_head',observe_preflight):
                    with check.assertRaisesRegex(PMRSError,'RESOURCE_LIMIT') as refused:
                        measured_knowledge_query('source19:'+dimension+':candidate-preflight',lambda:h.control.apply(value,h.operator))
                check.assertIsInstance(refused.exception.__cause__,_Unavailable)
                check.assertEqual(refused.exception.__cause__.reason,'QUERY_READ_LIMIT')
                check.assertEqual(len(candidates),1);check.assertEqual(len(failures),1)
                # The only initial debit is the candidate's real future HEAD;
                # observations never change reader arguments, counters or results.
                for files,byte_count in initial_budgets.values():
                    check.assertIn(files,(4096,4095));check.assertLessEqual(byte_count,128*1024**2)
                check.assertEqual(initial_budgets[failures[0]['reader']],(4095,128*1024**2-len(canonical(candidates[0]))))
                failure=failures[0];check.assertTrue(failure['preflight']);check.assertIn(failure['path'],paths)
                check.assertEqual(failure['maximum'],1024**2)
                check.assertIsNone(failure['reader'].fd)
                if dimension=='files':
                    check.assertEqual(failure['remaining_files'],0)
                    check.assertGreater(failure['remaining_bytes'],0)
                else:
                    check.assertGreater(failure['remaining_files'],0)
                    check.assertGreaterEqual(failure['remaining_bytes'],0)
                    check.assertLess(failure['remaining_bytes'],size)
                report['refusal']={key:item for key,item in failure.items() if key!='reader'}
                candidate=candidates[0];orphan=h.store.root/candidate['path'];orphan_bytes=orphan.read_bytes()
                check.assertEqual(sha(orphan_bytes),candidate['commit'])
                record=json.loads(orphan_bytes);check.assertEqual(record['schema'],'pmrh.control-fast.commit/1')
                event=next(event for event in record['events'] if event['type']!='CHECKPOINT')
                check.assertEqual(event['type'],'OWNER_ACQUIRED');check.assertEqual(event['payload'],value['payload'])
                check.assertEqual((h.store.root/'HEAD').read_bytes(),head_bytes)
                check.assertEqual(h.reopen(),before)
                with check.assertRaisesRegex(PMRSError,'SNAPSHOT_NOT_FOUND'):Journal(h.store.root).read_snapshot(candidate['commit'])
                with check.assertRaisesRegex(PMRSError,'NOT_FOUND'):
                    h.control.recover_receipt(h.scope,value['operation_id'],h.operator)
                def readable(label,expected):
                    def read():
                        with _ConfinedReader(h.store.root) as reader:
                            check.assertEqual((reader.remaining_files,reader.remaining_bytes),(4096,128*1024**2))
                            journal=Journal(reader.root,reader=reader);actual=journal.read_snapshot()
                            check.assertEqual(actual,expected)
                            check.assertGreater(reader.remaining_files,0);check.assertGreaterEqual(reader.remaining_bytes,0)
                            report['phases'].append(dict(label=label,commit=actual['knowledge_commit'],
                                charged_attempts=4096-reader.remaining_files,charged_bytes=128*1024**2-reader.remaining_bytes))
                    measured_knowledge_query('source19:'+dimension+':'+label,read)
                readable('old-HEAD-after-refusal',before)
                # Real unchanged original fast capture remains applicable under
                # the still-current owner, grant and manifest after rejection.
                applied,args=measured_knowledge_query('source19:'+dimension+':small-fast-publication',
                    lambda:h.apply_fast(captured['proposal_ref'],main))
                after=h.reopen();check.assertEqual(after['knowledge_commit'],applied['commit'])
                check.assertEqual(set(after['fast_selected'].values()),{entry['ref'] for entry in entries})
                check.assertEqual(after['instances'][h.iid]['ownership'],before['instances'][h.iid]['ownership'])
                check.assertEqual(after['requests'],before['requests']);check.assertEqual(after['usage'],before['usage'])
                check.assertNotIn(candidate['commit'],{entry_head['commit'] for entry_head,_ in h.store.history()})
                check.assertEqual(orphan.read_bytes(),orphan_bytes)
                readable('small-fast-HEAD',after)
                duplicate=h.store.fastmath_service().commit_delta(captured['proposal_ref'],**args)
                check.assertEqual(duplicate['commit'],applied['commit']);check.assertEqual(h.reopen(),after)
                check.assertEqual(h.restart_read()['commit'],applied['commit'])
                report['result']='ASSERTIONS_COMPLETED'
            finally:
                report['elapsed_seconds']=time.monotonic()-started
                report['process_maxrss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                report['synthetic_disk_bytes']=sum(path.stat().st_size for path in h.root.rglob('*') if path.is_file())
                report['synthetic_file_count']=sum(1 for path in h.root.rglob('*') if path.is_file())
                report['published_commit_count']=h.store._head()['sequence']
                report['attempted_candidate_count']=len(candidates)
                print('SOURCE19_CAPACITY_MEASUREMENTS '+json.dumps(report,sort_keys=True),flush=True)
                check.assertLess(report['synthetic_disk_bytes'],256*1024**2)


class StorageTests(unittest.TestCase):
    def test_source28_public_transition_reuse_rejection_and_display_restart(self):
        """One genuine qualified arrow, rejected changes, and a display-only successor."""
        import json
        from research_studio import demo,input_delivery,knowledge_access as Q
        from research_studio.task_tools import TaskTools
        from research_studio.store import Store
        from pmrh.domain import knowledge as K,assurance as A
        from pmrh.domain.fastmath.model import FastReadContext
        from .fixtures import scientific_worker,admit_scientific_response
        from .test_domain import rehash
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);h.authorize(5,attempts=5,communication=True)
            main=h.prepare();h.send(main);h.dispatch(main,'SENT')
            target=h.store.read_snapshot()['instances'][h.iid]['target_ref']
            # P1/PLAN can author this Context and comparison; P4 excludes Context.
            h.dispatch_workers(main,1,label='source28-arrow-author',stage='P1',role='PLAN',duty='ESTABLISH')
            author=h.prepare(actor='WORKER');h.slot(author);h.send(author);h.dispatch(author,'SENT')
            self.assertEqual((author['task']['stage_id'],author['task']['role']),('P1','PLAN'))
            self.assertTrue({'Context','Statement','Argument'}<=set(author['task']['permission_manifest']['allowed_record_kinds']))
            envelope=json.loads(demo.response(author['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            body='For every integer n, 0 + n = n.';loc=K.locator(body)
            premise=dict(op='NEW',local_key='premise',kind='Statement',context_refs=[],body=body,
                data=dict(statement_locator=loc,scope_context_refs=[],hypothesis_locators=[],conclusion_locators=[loc],
                    quantifier_locators=[loc],form='PROPOSITION',representation='AUTHORED',source_binding=None))
            context_body='An additional synthetic mathematical context, not a display label.'
            context_op=dict(op='NEW',local_key='extra_context',kind='Context',context_refs=[],body=context_body,
                data=dict(definitions=[],objects=[],assumptions=[],quantifiers=[],
                    conventions=[dict(key='source28_extra',locator=K.locator(context_body))],parent_context_refs=[]))
            argument_body=('Let n be an arbitrary integer. The additive identity axiom gives n + 0 = n, '
                'so the declared implication from 0 + n = n holds without additional assumptions. '
                'This synthetic candidate requires an independent exact-scope review; it is not real mathematical certification.')
            argument_op=dict(op='NEW',local_key='argument',kind='Argument',context_refs=[],body=argument_body,
                data=dict(conclusion_ref=target,premise_bindings=[],
                    steps=[dict(step_id='identity',locator=K.locator(argument_body),premise_refs=[])],
                    discharged_assumptions=[],open_conditions=[],witness_bindings=[],mode='COMPARISON',
                    mode_payload=dict(relation_type='IMPLIES',from_statement_ref='local:premise',to_statement_ref=target,
                        direction_argument_refs=[],scope_context_refs=[])))
            envelope['payload']['operations']=[premise,context_op,argument_op]
            for effect in envelope['payload']['obligation_effects']:
                effect['evidence_refs']=['local:premise','local:extra_context','local:'+argument_op['local_key']]
            admit_scientific_response(h,author,envelope)
            state=h.reopen()
            self.assertEqual(state['requests'][author['spec'].request_id]['acceptance_state'],'ACCEPTED')
            support=next(row for row in state['supports'].values()
                if state['records'][row['argument_ref']]['data']['mode']=='COMPARISON')
            sid=support['support_id'];argument=support['argument_ref']
            start=state['records'][argument]['data']['mode_payload']['from_statement_ref']
            context_ref=next(ref for ref,row in state['records'].items() if row['kind']=='Context' and
                any(c['key']=='source28_extra' for c in row['data']['conventions']))
            self.assertNotEqual(start,target)

            def delivered(reader,ref,as_of=None,confirm=False):
                command=h.command('COMMUNICATION_APPLIED',{})
                frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                args={'ref':ref}
                if as_of is not None:args['as_of_commit']=as_of
                with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=reader['manifest_ref']):
                    did,response=TaskTools(h.store,reader['spec'].request_id,reader['spec'].execution_id).call('knowledge_get',args)
                self.assertFalse(response['isError'],response)
                saved=h.store.read_snapshot()['input_deliveries'][did]
                self.assertEqual(h.store.read_blob(saved['response_ref']),canonical(response))
                if confirm:
                    self.assertTrue(saved['supplements'])
                    command=h.command('COMMUNICATION_APPLIED',{})
                    frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                    with h.control.native_context(h.service,**frame):
                        input_delivery.confirm(h.store,reader['spec'].request_id,reader['spec'].execution_id,did)
                    self.assertIn(ref,input_delivery.supplied_records(h.store.read_snapshot(),reader['task'],h.store.read_blob,live=True))
                else:self.assertEqual(saved['supplements'],[])
                return json.loads(response['content'][0]['text'])['result']

            for ref in (start,context_ref,argument):delivered(main,ref,confirm=True)
            review=scientific_worker(h,main,'source28-arrow-review',role='PROOF',inputs=[target,start,context_ref,argument])
            self.assertNotEqual(review['spec'].request_id,author['spec'].request_id)
            req=review['task']['required_assurance']
            envelope=json.loads(demo.response(review['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            op=envelope['payload']['operations'][0]
            op['body']='Synthetic independent whole-scope arrow review; no real mathematical certification.'
            op['data'].update(verdict='SUPPORTED_WITHIN_SCOPE',unchecked=[],checked=[
                dict(ref=row['target_ref'],locators=row['locators'],aspect=aspect,**{k:row[k] for k in A.SCOPE_META})
                for row in req['required_scope'] for aspect in row['aspects']])
            admit_scientific_response(h,review,envelope)
            state=h.reopen();support=state['supports'][sid]
            self.assertEqual(A.evaluate_requirement(state,sid,support['consumer_requirement'],support['policy_digest'])['result'],'QUALIFIED')
            native=deepcopy(state['records']);supports=deepcopy(state['supports'])
            entries=six_entries(state,main['task'],argument_ref=argument,support_ids=[sid]);old=entries[1];binding=entries[-1]
            old['body']['payload'].update(start_ref=start,end_ref=target,relation='IMPLICATION',direction='FORWARD',missing_interface='')
            rehash(old);binding['body']['payload'].update(upper_revision_ref=old['ref'],upper_claim_slot='arrow')
            binding['body']['dependencies']=[old['ref'],target,argument];rehash(binding)

            def capture_settle_apply(producer,proposal):
                _,captured,args=h.capture_fast(producer,proposal)
                raw=h.store.read_blob(args['capture_ref']['sha256'])
                h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=producer['spec'].request_id,
                    capture_ref=args['capture_ref'])),h.service,grant_ref=h.grant(),manifest_ref=producer['manifest_ref'])
                rejected=h.reopen()['requests'][producer['spec'].request_id]
                self.assertEqual((rejected['execution_state'],rejected['acceptance_state']),('SETTLED','REJECTED_CONTRACT'))
                h.observation(producer,'TERMINATED')
                successor=h.prepare(actor='MAIN');h.send(successor);h.dispatch(successor,'SENT')
                self.assertNotEqual(successor['spec'].request_id,producer['spec'].request_id)
                applied,_=h.apply_fast(captured['proposal_ref'],successor);h.reopen()
                self.assertEqual(h.store.read_blob(args['capture_ref']['sha256']),raw)
                return successor,applied['commit']

            successor,old_head=capture_settle_apply(main,delta_for(state,main['task'],[old,binding]))
            old_view=Q.web_tool(Store(h.store.root),'get',{'ref':[old['ref']],'instance_id':[h.iid]})
            self.assertEqual(old_view['derived']['bindings'][0]['qualification']['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
            original_binding=h.store.read_blob(binding['ref'][3:]);state=h.store.read_snapshot()
            display=deepcopy(old);display['body'].update(predecessor=old['ref'],body='Clearer display of the identical qualified arrow.',
                author_attempt=dict(request_id=successor['task']['request_id'],attempt_id=successor['task']['attempt_key']),reason='Display-only revision.')
            display['body']['payload'].update(title='Same qualified arrow',explanatory_order=1);rehash(display)
            link=dict(old_upper_ref=old['ref'],new_upper_ref=display['ref'],old_slot='arrow',new_slot='arrow',
                claim_fingerprint=binding['body']['payload']['claim_fingerprint'],source_binding_ref=binding['ref'])
            context=FastReadContext(h.project,h.iid,successor['task']['mission_id'],successor['task']['task_id'])
            h.storage.fast.bind_read_context(context,h.service);service=h.store.fastmath_service();head=h.store._head()
            for change in (dict(start_ref=target,end_ref=start),dict(relation='CONDITIONAL_IMPLICATION'),
                           dict(relation='EQUIVALENCE',direction='BOTH'),dict(shared_context_refs=[context_ref])):
                with self.subTest(rejected_arrow=change):
                    bad=deepcopy(display);bad['body']['payload'].update(change);rehash(bad)
                    bad_link={**link,'new_upper_ref':bad['ref']}
                    with self.assertRaises(FastMathError) as caught:
                        service.prepare_delta(delta_for(state,successor['task'],[bad],links=[bad_link]),
                            read_context=context,as_of_commit=state['knowledge_commit'])
                    self.assertEqual(caught.exception.code,'FAST_SCHEMA_INVALID')
                    self.assertIn('Changed declared claim identity',str(caught.exception))
                    self.assertEqual(h.store._head(),head)
                    with self.assertRaises((FastMathError,PMRSError)):
                        Q.get(Store(h.store.root),bad['ref'],instance_id=h.iid)
            self.assertEqual(h.store.read_snapshot(),state)
            reader,new_head=capture_settle_apply(successor,delta_for(state,successor['task'],[display],links=[link]))
            reopened=Journal(h.store.root).read_snapshot()
            self.assertEqual(reopened['fast_selected'][old['body']['object_id']],display['ref'])
            self.assertEqual(reopened['records'],native);self.assertEqual(reopened['supports'],supports)
            self.assertEqual(Q.web_tool(Store(h.store.root),'get',{'ref':[display['ref']],'instance_id':[h.iid],
                'as_of_commit':[new_head]})['derived']['bindings'][0]['displayed_upper'],display['ref'])
            for ref,pinned,shown in ((display['ref'],None,display['ref']),(old['ref'],old_head,old['ref'])):
                args={'ref':[ref],'instance_id':[h.iid]}
                if pinned is not None:args['as_of_commit']=[pinned]
                human=Q.web_tool(Store(h.store.root),'get',args);tool=delivered(reader,ref,pinned)
                self.assertEqual(tool['derived']['bindings'],human['derived']['bindings'])
                row=human['derived']['bindings'][0]
                self.assertEqual((row['binding_ref'],row['binding_target'],row['displayed_upper']),
                    (binding['ref'],old['ref'],shown))
                self.assertEqual(row['qualification']['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
                self.assertEqual(row['qualification'],old_view['derived']['bindings'][0]['qualification'])
            self.assertEqual(h.store.read_blob(binding['ref'][3:]),original_binding)
            self.assertEqual({row['ref'] for row in Q.history(Store(h.store.root),display['ref'],instance_id=h.iid)['objects']},
                             {old['ref'],display['ref']})
            for checkpoint in (h.store.root/'checkpoints').glob('*.json'):checkpoint.unlink()
            replayed=Journal(h.store.root).read_snapshot()
            self.assertEqual(replayed['fast_revisions'][binding['ref']],binding['body'])
            self.assertEqual(replayed['fast_selected'][old['body']['object_id']],display['ref'])

    def test_FM01_FM15_FM24_original_six_revisions_restart_and_exact_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair()
            before=h.store.read_snapshot();entries=six_entries(before,worker['task']);delta=delta_for(before,worker['task'],entries)
            prepared,captured,args=h.capture_fast(worker,delta)
            pending=h.store.read_snapshot()
            self.assertEqual(pending.get('fast_selected',{}),{})
            self.assertEqual(pending['fast_proposals'][captured['proposal_ref']['sha256']]['status'],'PENDING')
            applied,_=h.apply_fast(captured['proposal_ref'],main)
            state=h.reopen();restart=h.restart_read()
            self.assertEqual(state['knowledge_commit'],restart['commit'])
            self.assertEqual(set(state['fast_revisions']),{e['ref'] for e in entries})
            self.assertEqual(restart['fast_revisions'],{e['ref']:sha(canonical(e['body'])) for e in entries})
            for entry in entries:self.assertEqual(h.store.read_blob(entry['ref'][3:]),canonical(entry['body']))
            self.assertEqual(applied['commit'],state['knowledge_commit'])
            self.assertNotIn('commit',state['fast_receipts'][applied['operation_id']])
            self.assertEqual(before['records'],state['records']);self.assertEqual(before['usage'],state['usage'])
            corrupt=h.store.root/'blobs'/entries[0]['ref'][3:];corrupt.write_bytes(b'corrupt')
            with self.assertRaises((PMRSError,FastMathError)):Journal(h.store.root).read_snapshot()

    def test_FM09_exact_command_retry_conflict_and_unrelated_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot()
            prepared,captured,args=h.capture_fast(worker,delta_for(s,worker['task'],six_entries(s,worker['task'])))
            duplicate=h.store.fastmath_service().capture_delta(prepared,**args)
            self.assertEqual(captured['commit'],duplicate['commit'])
            bad={**args,'expected_head':h.store._head()['commit']}
            with self.assertRaises(FastMathError):h.store.fastmath_service().capture_delta(prepared,**bad)
            before=h.store._head();self.assertEqual(before['commit'],captured['commit'])
            result,apply_args=h.apply_fast(captured['proposal_ref'],main)
            retry=h.store.fastmath_service().commit_delta(captured['proposal_ref'],**apply_args)
            self.assertEqual(result['commit'],retry['commit'])
            h.registry.revoke(apply_args['session'])
            with self.assertRaises(FastMathError):h.store.fastmath_service().commit_delta(captured['proposal_ref'],**apply_args)
            self.assertEqual(h.store._head()['commit'],result['commit'])

    def test_FM19_before_head_crash_then_after_head_recovery(self):
        for fault in ('before_head','after_head'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot()
                _,captured,_=h.capture_fast(worker,delta_for(s,worker['task'],six_entries(s,worker['task'])))
                before=h.store._head()
                session=h.session(acting_request_id=main['spec'].request_id)
                args=h.fast_arguments('crash',session,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
                def fail(boundary):
                    if boundary==fault:raise OSError('synthetic '+fault)
                h.store._test_fault_hook=fail
                with self.assertRaisesRegex(OSError,'synthetic '+fault):h.store.fastmath_service().commit_delta(captured['proposal_ref'],**args)
                h.store._test_fault_hook=None;h.reopen()
                if fault=='before_head':
                    self.assertEqual(h.store._head(),before)
                    with self.assertRaises(FastMathError):h.store.fastmath_service().recover_receipt(h.scope,args['operation_id'],session)
                else:
                    receipt=h.store.fastmath_service().recover_receipt(h.scope,args['operation_id'],session)
                    self.assertEqual(receipt['commit'],h.store._head()['commit']);self.assertNotEqual(receipt['commit'],before['commit'])
                    for path in (h.store.root/'checkpoints').glob('*.json'):path.unlink()
                    self.assertEqual(Journal(h.store.root).read_snapshot()['knowledge_commit'],receipt['commit'])

    def test_FM11_empty_delta_is_durable_no_change_without_native_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot()
            _,captured,_=h.capture_fast(worker,delta_for(s,worker['task'],[],empty_reason='No new exact evidence.'))
            before=h.store.read_snapshot();applied,_=h.apply_fast(captured['proposal_ref'],main);after=h.reopen()
            self.assertEqual(applied['outcome'],'NO_CHANGE');self.assertNotEqual(applied['commit'],before['knowledge_commit'])
            for name in ('records','instances','requests','budget_grants','usage'):self.assertEqual(before[name],after[name])
            self.assertEqual(after.get('fast_selected',{}),{})

    def test_FM21_FM24_persisted_display_reuse_keeps_old_binding_identity(self):
        from research_studio import knowledge_access as Q
        from .test_domain import rehash
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();before=h.store.read_snapshot()
            entries=six_entries(before,worker['task'])
            _,capture,_=h.capture_fast(worker,delta_for(before,worker['task'],entries))
            applied,_=h.apply_fast(capture['proposal_ref'],main)
            old=Q.get(h.store,entries[0]['ref'],instance_id=h.iid)
            self.assertTrue(old['presentation']['expansion_refs'])
            original_binding_bytes=h.store.read_blob(entries[-1]['ref'][3:])
            h.dispatch_workers(main,1,label='display-')
            display=h.prepare(actor='WORKER');h.slot(display);h.send(display);h.dispatch(display,'SENT')
            state=h.store.read_snapshot();author={k:display['task'][v] for k,v in [('request_id','request_id'),('attempt_id','attempt_key')]}
            module=deepcopy(entries[0]);module['body'].update(predecessor=entries[0]['ref'],author_attempt=author,
                body='A clearer explanation of the identical native claim.',reason='Display wording only.')
            module['body']['payload']['title']='Revised explanatory title';rehash(module)
            reader=deepcopy(entries[4]);reader['body'].update(predecessor=entries[4]['ref'],author_attempt=author,reason='Overview expansion.')
            reader['body']['payload']['explanation_depth']='OVERVIEW';rehash(reader)
            link=dict(old_upper_ref=entries[0]['ref'],new_upper_ref=module['ref'],old_slot='result',new_slot='result',
                claim_fingerprint=entries[-1]['body']['payload']['claim_fingerprint'],source_binding_ref=entries[-1]['ref'])
            _,capture,_=h.capture_fast(display,delta_for(state,display['task'],[module,reader],links=[link]))
            h.apply_fast(capture['proposal_ref'],main);h.reopen()
            current=Q.get(h.store,module['ref'],instance_id=h.iid)
            reuse=current['derived']['bindings'][0]
            self.assertEqual(reuse['binding_target'],entries[0]['ref']);self.assertEqual(reuse['displayed_upper'],module['ref'])
            self.assertEqual(reuse['binding_ref'],entries[-1]['ref']);self.assertIsNotNone(reuse['reuse_link_ref'])
            self.assertEqual(reuse['qualification'],old['derived']['bindings'][0]['qualification'])
            self.assertEqual(current['presentation']['expansion_refs'],[])
            self.assertEqual(current['presentation']['explanation_depth'],'OVERVIEW')
            self.assertEqual(h.store.read_blob(entries[-1]['ref'][3:]),original_binding_bytes)
            historical=Q.get(h.store,entries[0]['ref'],instance_id=h.iid,as_of_commit=applied['commit'])
            self.assertEqual(historical['payload'],old['payload']);self.assertEqual(historical['as_of_commit'],applied['commit'])
            self.assertEqual({r['ref'] for r in Q.history(h.store,module['ref'],instance_id=h.iid)['objects']},{entries[0]['ref'],module['ref']})

    def test_source09_native_qualification_withdrawal_preserves_other_path(self):
        import json
        from pmrh.domain import assurance as A
        from research_studio import changes,demo,knowledge_access as Q
        from research_studio.store import Store
        from .fixtures import native_qualified_pair,scientific_worker,admit_scientific_response
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);seed=native_qualified_pair(h);main=seed['main']
            state=h.reopen();paths=seed['paths'];self.assertEqual(len(paths),2)
            qualified_head=state['knowledge_commit'];original=deepcopy(state['records'][seed['target']])
            for path in paths:
                sid=path['support_id'];support=state['supports'][sid]
                result=A.evaluate_requirement(state,sid,support['consumer_requirement'],support['policy_digest'])
                self.assertEqual(result['result'],'QUALIFIED')
                self.assertEqual(support['argument_ref'],path['argument_ref'])
                self.assertEqual(support['author_task_id'],seed['author']['task']['task_id'])
                for qid in support['qualification_refs']:
                    q=state['qualifications'][qid];event=state['review_executions'][q['review_execution_event']]
                    self.assertEqual(q['evidence_origin'],'MODEL_CAPTURE')
                    self.assertTrue(event['independent']);self.assertTrue(event['excluded_verdicts']);self.assertTrue(event['synthetic'])
                    self.assertNotEqual(event['task_id'],support['author_task_id'])
                self.assertEqual(h.store.read_blob(path['admitted']['capture']['sha256']),path['admitted']['raw'])
                human=measured_knowledge_query('qualified-current:'+path['support_id'],lambda:
                    Q.web_tool(Store(h.store.root),'get',{'ref':[path['argument_ref']],'instance_id':[h.iid]}))
                self.assertEqual(human['body_sha256'],state['records'][path['argument_ref']]['body_sha256'])
            self.assertNotEqual(paths[0]['review']['task']['task_id'],paths[1]['review']['task']['task_id'])
            for delivery,response in seed['deliveries']:
                row=state['input_deliveries'][delivery]
                self.assertTrue(row['confirmed']);self.assertEqual(h.store.read_blob(row['response_ref']),canonical(response))
            self.assertEqual(h.store.history()[-1][1]['schema'],'pmrh.control-fast.commit/1')

            affected,survivor=paths
            review=scientific_worker(h,main,'source09-defect',role='PROOF',inputs=[seed['target'],affected['argument_ref']])
            # Queue the native disposition before the defect changes MAIN's
            # dynamic support guards. Freeze its actual packet after the review.
            h.dispatch_workers(main,1,label='source09-withdraw',stage='P4',role='RESEARCH',duty='ESTABLISH',inputs=[seed['target']])
            envelope=json.loads(demo.response(review['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            requirement=review['task']['required_assurance'];op=envelope['payload']['operations'][0]
            op['body']='Synthetic scoped defect in the first argument only; the original statement is not refuted.'
            op['data'].update(verdict='DEFECT_FOUND',unchecked=[],checked=[
                dict(ref=row['target_ref'],locators=row['locators'],aspect=aspect,**{key:row[key] for key in A.SCOPE_META})
                for row in requirement['required_scope'] for aspect in row['aspects']])
            admit_scientific_response(h,review,envelope)
            state=h.reopen();sid=affected['support_id'];support=state['supports'][sid]
            defect=next(q['assessment_ref'] for q in state['qualifications'].values()
                if state['review_executions'][q['review_execution_event']]['task_id']==review['task']['task_id'])
            self.assertEqual(A.evaluate_requirement(state,sid,support['consumer_requirement'],support['policy_digest'])['result'],'CONFLICTED')
            worker=h.prepare(actor='WORKER');h.slot(worker);h.send(worker);h.dispatch(worker,'SENT')
            envelope=json.loads(demo.response(worker['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            withdrawal=dict(op='WITHDRAW_SUPPORT',support_id=sid,
                expected_qualification_head=sha(canonical(support['qualification_refs'])),reason_code='SYNTHETIC_SCOPED_DEFECT',
                evidence_refs=[defect],scope=deepcopy(support['consumer_requirement']['required_scope']))
            envelope['payload']['operations']=[withdrawal]
            for effect in envelope['payload']['obligation_effects']:
                effect.update(work_disposition='ADDRESSED',resolution_proposal='NEEDS_RECHECK',evidence_refs=[seed['target']])
            # Native host authorization consumes the already admitted independent
            # credential. No human withdrawal permission is inserted in a task.
            self.assertNotIn('human_review_withdrawal',worker['task']['permission_manifest'])
            wrong=deepcopy(envelope);other=state['supports'][survivor['support_id']]
            wrong['payload']['operations'][0].update(support_id=survivor['support_id'],
                expected_qualification_head=sha(canonical(other['qualification_refs'])),scope=deepcopy(other['consumer_requirement']['required_scope']))
            before=h.store._head()
            with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                changes.validate_response(worker['task'],h.store.read_snapshot(),canonical(wrong),blob_get=h.store.read_blob)
            self.assertEqual(h.store._head(),before)
            admit_scientific_response(h,worker,envelope)
            current=h.reopen();historical=Store(h.store.root).read_snapshot(qualified_head)
            self.assertEqual(current['records'][seed['target']],original)
            self.assertEqual({w['support_id'] for w in current['withdrawals'].values()},{sid})
            for path,expected in ((affected,'WITHDRAWN'),(survivor,'QUALIFIED')):
                support=current['supports'][path['support_id']]
                self.assertEqual(A.evaluate_requirement(current,path['support_id'],support['consumer_requirement'],support['policy_digest'])['result'],expected)
                old=historical['supports'][path['support_id']]
                self.assertEqual(A.evaluate_requirement(historical,path['support_id'],old['consumer_requirement'],old['policy_digest'])['result'],'QUALIFIED')
                body=measured_knowledge_query('withdrawal-historical:'+path['support_id'],lambda:
                    Q.web_tool(Store(h.store.root),'get',{'ref':[path['argument_ref']],'instance_id':[h.iid],'as_of_commit':[qualified_head]}))
                self.assertEqual(body['as_of_commit'],qualified_head)
                self.assertEqual(body['body_sha256'],historical['records'][path['argument_ref']]['body_sha256'])
            self.assertEqual(h.restart_read()['commit'],current['knowledge_commit'])

    def test_source09_qualified_fast_lifecycle_boundary_is_not_bypassed(self):
        from pmrh.domain.fastmath.model import FastReadContext
        from pmrh.domain.fastmath.qualification import qualify_binding
        from .fixtures import native_qualified_pair,scientific_worker
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);seed=native_qualified_pair(h);main=seed['main'];path=seed['paths'][0]
            worker=scientific_worker(h,main,'source09-fast-candidate',inputs=[seed['target'],path['argument_ref']])
            state=h.reopen();entries=six_entries(state,worker['task'],argument_ref=path['argument_ref'],support_ids=[path['support_id']])
            self.assertEqual(qualify_binding(entries[-1]['body'],entries[0]['body'],state)['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
            context=FastReadContext(h.project,h.iid,worker['task']['mission_id'],worker['task']['task_id'])
            h.storage.fast.bind_read_context(context,h.service);head=h.store._head()
            with self.assertRaises(FastMathError) as caught:
                h.store.fastmath_service().prepare_delta(delta_for(state,worker['task'],entries),read_context=context,as_of_commit=state['knowledge_commit'])
            self.assertEqual(caught.exception.code,'FAST_REF_UNAVAILABLE')
            self.assertEqual(h.store._head(),head)
            # MAIN is allowed the credential closure and authentic capture, but
            # that seal closes its live application state. This is a blocker
            # regression, NOT a persisted qualified fast-reuse success fixture.
            entries=six_entries(state,main['task'],argument_ref=path['argument_ref'],support_ids=[path['support_id']])
            _,captured,_=h.capture_fast(main,delta_for(state,main['task'],entries))
            pending=h.reopen();self.assertEqual(pending['requests'][main['spec'].request_id]['execution_state'],'CAPTURED')
            self.assertEqual(pending['fast_proposals'][captured['proposal_ref']['sha256']]['status'],'PENDING')
            self.assertEqual(pending.get('fast_selected',{}),{})
            head=h.store._head()
            with self.assertRaises(FastMathError) as caught:h.apply_fast(captured['proposal_ref'],main)
            self.assertEqual(caught.exception.code,'FAST_STATE_DENIED')
            self.assertEqual(h.store._head(),head)
            self.assertEqual(h.restart_read()['fast_selected'],{})

    def test_source10_original_capture_recovery_precedes_successor_MAIN_apply(self):
        """Root-approved route: authenticated rejection settlement, then successor."""
        import json
        from pmrh.application.read_projections import control_lane_closed,budget_remaining
        from research_studio import knowledge_access as Q
        from research_studio.task_tools import TaskTools
        from .fixtures import native_qualified_pair,scientific_worker,admit_scientific_response
        from .test_domain import rehash
        from research_studio import demo,changes
        from pmrh.domain import assurance as A
        with tempfile.TemporaryDirectory() as tmp:
            # Ten finite invocations are authorized before any task is frozen:
            # the original eight plus two post-withdrawal reader MAINs.
            h=Harness(tmp);seed=native_qualified_pair(h,calls=10);main=seed['main'];path=seed['paths'][0]
            state=h.reopen();rid=main['spec'].request_id
            authorized_grants=deepcopy(state['budget_grants']);authorized_project=deepcopy(state['project_budget'])
            grant_id=main['task']['budget_grant']
            entries=six_entries(state,main['task'],argument_ref=path['argument_ref'],support_ids=[path['support_id']])
            # A second independently qualified binding retains its own exact
            # argument/scope. Neither branch can borrow the other's credential.
            independent=seed['paths'][1]
            second=six_entries(state,main['task'],argument_ref=independent['argument_ref'],support_ids=[independent['support_id']])
            second[0]['body']['object_id']='module-independent';rehash(second[0])
            second[-1]['body']['object_id']='binding-independent'
            second[-1]['body']['payload']['upper_revision_ref']=second[0]['ref']
            second[-1]['body']['dependencies']=[second[0]['ref'],seed['target']];rehash(second[-1])
            entries.extend([second[0],second[-1]])
            _,captured,capture_args=h.capture_fast(main,delta_for(state,main['task'],entries))
            capture=capture_args['capture_ref'];proposal=captured['proposal_ref']
            original=h.store.read_blob(capture['sha256']);proposal_bytes=h.store.read_blob(proposal['sha256'])
            identity=dict(original_request=rid,original_attempt=main['task']['attempt_key'],
                original_input_commit=main['task']['knowledge_commit'],original_capture=capture,
                original_proposal=proposal,applying_request=None)
            print('SOURCE10_LIFECYCLE '+json.dumps(dict(phase='original_sealed_proposal',**identity),sort_keys=True),flush=True)
            # No legacy recovery or raw writer is allowed. If the bounded
            # authenticated rejection bridge is unavailable, this remains an
            # ordinary failing positive test; no expected-failure success.
            rejection=h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=rid,capture_ref=capture)),
                h.service,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            print('SOURCE11_LIFECYCLE '+json.dumps(dict(phase='authenticated_native_settlement',
                receipt=rejection,**identity),sort_keys=True),flush=True)
            settled=h.reopen();request=settled['requests'][rid]
            self.assertEqual(request['execution_state'],'SETTLED');self.assertEqual(request['acceptance_state'],'REJECTED_CONTRACT')
            self.assertFalse(control_lane_closed(request));self.assertFalse(request['fenced'])
            self.assertEqual(h.store.read_blob(capture['sha256']),original)
            with self.assertRaises((PMRSError,FastMathError)):h.apply_fast(proposal,main)
            from research_studio import scheduler
            plan=scheduler.plan(h.store.read_snapshot(),[h.iid],h.policy)
            self.assertFalse([c for c in plan['selected'] if c['consumer'].get('actor_kind')=='MAIN'])
            h.observation(main,'TERMINATED');self.assertTrue(control_lane_closed(h.reopen()['requests'][rid]))
            successor=h.prepare(actor='MAIN');h.send(successor);h.dispatch(successor,'SENT')
            identity['applying_request']=successor['spec'].request_id
            self.assertNotEqual(identity['applying_request'],rid)
            self.assertNotEqual(successor['task']['attempt_key'],main['task']['attempt_key'])
            self.assertEqual(successor['task']['mission_id'],main['task']['mission_id'])
            print('SOURCE10_LIFECYCLE '+json.dumps(dict(phase='successor_prepared',**identity),sort_keys=True),flush=True)
            applied,apply_args=h.apply_fast(proposal,successor)
            retry=h.store.fastmath_service().commit_delta(proposal,**apply_args)
            self.assertEqual(retry['commit'],applied['commit']);h.reopen()
            self.assertEqual(h.store.read_blob(capture['sha256']),original)
            self.assertEqual(h.store.read_blob(proposal['sha256']),proposal_bytes)
            current=measured_knowledge_query('successor-qualified-current',lambda:
                Q.web_tool(h.store,'get',{'ref':[entries[0]['ref']],'instance_id':[h.iid]}))
            self.assertEqual(current['derived']['bindings'][0]['qualification']['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
            tools=TaskTools(h.store,successor['spec'].request_id,successor['spec'].execution_id)
            frame=h.command('COMMUNICATION_APPLIED',{})
            args={key:frame[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**args,grant_ref=h.grant(),manifest_ref=successor['manifest_ref']):
                delivery,response=measured_knowledge_query('successor-qualified-TaskTools',lambda:tools.call('knowledge_get',{'ref':entries[0]['ref']}))
            self.assertFalse(response['isError']);delivered=json.loads(response['content'][0]['text'])['result']
            self.assertEqual(delivered['derived']['bindings'][0]['qualification']['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
            row=h.store.read_snapshot()['input_deliveries'][delivery]
            self.assertEqual(h.store.read_blob(row['response_ref']),canonical(response))
            old=measured_knowledge_query('successor-qualified-historical',lambda:
                Q.web_tool(h.store,'get',{'ref':[entries[0]['ref']],'instance_id':[h.iid],'as_of_commit':[applied['commit']]}))
            self.assertEqual(old['derived']['bindings'],current['derived']['bindings'])
            print('SOURCE10_LIFECYCLE '+json.dumps(dict(phase='qualified_apply_and_reads',fast_commit=applied['commit'],
                native_acceptance='REJECTED_CONTRACT',**identity),sort_keys=True),flush=True)

            # U1 -> B1 -> display U2: a new capture belongs to the successor,
            # then a distinct third MAIN applies those unchanged captured bytes.
            state=h.reopen();binding=entries[5];binding_bytes=h.store.read_blob(binding['ref'][3:])
            module=deepcopy(entries[0]);module['body'].update(predecessor=entries[0]['ref'],
                author_attempt=dict(request_id=successor['task']['request_id'],attempt_id=successor['task']['attempt_key']),
                body='Clearer presentation of the identical qualified claim.',reason='Display only; preserve B1 target U1.')
            module['body']['payload']['title']='Qualified display U2';rehash(module)
            link=dict(old_upper_ref=entries[0]['ref'],new_upper_ref=module['ref'],old_slot='result',new_slot='result',
                claim_fingerprint=binding['body']['payload']['claim_fingerprint'],source_binding_ref=binding['ref'])
            _,display_capture,display_args=h.capture_fast(successor,delta_for(state,successor['task'],[module],links=[link]))
            display_bytes=h.store.read_blob(display_capture['proposal_ref']['sha256'])
            h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=successor['spec'].request_id,
                capture_ref=display_args['capture_ref'])),h.service,grant_ref=h.grant(),manifest_ref=successor['manifest_ref'])
            self.assertEqual(h.reopen()['requests'][successor['spec'].request_id]['acceptance_state'],'REJECTED_CONTRACT')
            h.observation(successor,'TERMINATED')
            reader_main=h.prepare(actor='MAIN');h.send(reader_main);h.dispatch(reader_main,'SENT')
            self.assertNotIn(reader_main['spec'].request_id,{rid,successor['spec'].request_id})
            reused,_=h.apply_fast(display_capture['proposal_ref'],reader_main);reuse_head=reused['commit'];h.reopen()
            self.assertEqual(h.store.read_blob(display_capture['proposal_ref']['sha256']),display_bytes)
            self.assertEqual(h.store.read_blob(binding['ref'][3:]),binding_bytes)

            def delivered_get(ref,as_of=None,*,confirm_native=False,reader=None,expected_error=None):
                reader=reader_main if reader is None else reader
                arguments={'ref':ref}
                if as_of:arguments['as_of_commit']=as_of
                tools=TaskTools(h.store,reader['spec'].request_id,reader['spec'].execution_id)
                command=h.command('COMMUNICATION_APPLIED',{})
                frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**frame,grant_ref=h.grant(),manifest_ref=reader['manifest_ref']):
                    delivery,response=tools.call('knowledge_get',arguments)
                delivered_state=h.store.read_snapshot();row=delivered_state['input_deliveries'][delivery]
                self.assertEqual(h.store.read_blob(row['response_ref']),canonical(response))
                result=json.loads(response['content'][0]['text'])['result']
                if expected_error:
                    self.assertTrue(response['isError'],response);self.assertEqual(result['error'],expected_error)
                    self.assertEqual(row['supplements'],[])
                    return result
                self.assertFalse(response['isError'],response)
                if confirm_native:
                    from research_studio import input_delivery
                    native=delivered_state['records'][ref];body=h.store.read_blob(native['body_sha256'])
                    self.assertEqual(result['read_scope'],'EXACT_BODY')
                    self.assertEqual(result['record'],native);self.assertEqual(result['body'].encode(),body)
                    self.assertEqual(result['body_sha256'],sha(body))
                    self.assertEqual((row['request_id'],row['execution_id'],row['tool_name']),
                        (reader['spec'].request_id,reader['spec'].execution_id,'knowledge_get'))
                    self.assertEqual(row['supplements'],[dict(schema='pmrs.input-supplement/1',kind='record',
                        ref=ref,revision=ref,native_digest=sha(canonical(native)),body_sha256=sha(body),
                        read_scope='EXACT_BODY',source='EXACT_TOOL_BODY',support_guards={
                            item['support_ref']:sha(canonical(delivered_state['supports'][item['support_ref']]))
                            for item in result['status']['support']})])
                    command=h.command('COMMUNICATION_APPLIED',{})
                    frame={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                    with h.control.native_context(h.service,**frame):
                        input_delivery.confirm(h.store,reader['spec'].request_id,reader['spec'].execution_id,delivery)
                    confirmed=h.store.read_snapshot();saved=confirmed['input_deliveries'][delivery]
                    self.assertTrue(saved['confirmed']);self.assertEqual(saved['supplements'],row['supplements'])
                    event=confirmed['communication_events'][saved['confirmation_event']]
                    self.assertEqual(event['event_type'],'INPUT_DELIVERY_CONFIRMED')
                    self.assertEqual(event['payload'],dict(request_id=row['request_id'],execution_id=row['execution_id'],delivery_id=delivery))
                    self.assertIn(ref,input_delivery.supplied_records(confirmed,reader['task'],h.store.read_blob,live=True))
                return result

            shown=Q.web_tool(h.store,'get',{'ref':[module['ref']],'instance_id':[h.iid]})
            reuse=shown['derived']['bindings'][0]
            self.assertEqual((reuse['binding_ref'],reuse['binding_target'],reuse['displayed_upper']),
                (binding['ref'],entries[0]['ref'],module['ref']))
            self.assertIsNotNone(reuse['reuse_link_ref'])
            self.assertEqual(reuse['qualification']['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
            self.assertEqual(delivered_get(module['ref'])['derived']['bindings'],shown['derived']['bindings'])
            self.assertEqual(delivered_get(entries[0]['ref'],applied['commit'])['derived']['bindings'],old['derived']['bindings'])

            affected,survivor=seed['paths']
            from research_studio import input_delivery
            # Fast-card metadata did not supply this native argument body to
            # this distinct MAIN. Deliver and confirm it before scientific use.
            supplied={item['ref'] for item in reader_main['task']['input_manifest'] if item['kind']=='record'}
            supplied.update(input_delivery.supplied_records(h.store.read_snapshot(),reader_main['task'],h.store.read_blob,live=True))
            self.assertNotIn(affected['argument_ref'],supplied)
            delivered_get(affected['argument_ref'],confirm_native=True)
            review=scientific_worker(h,reader_main,'source13-defect',role='PROOF',inputs=[seed['target'],affected['argument_ref']])
            h.dispatch_workers(reader_main,1,label='source13-withdraw',stage='P4',role='RESEARCH',duty='ESTABLISH',inputs=[seed['target']])
            envelope=json.loads(demo.response(review['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            requirement=review['task']['required_assurance'];op=envelope['payload']['operations'][0]
            op['body']='Synthetic scoped defect in the first argument only; the original statement is not refuted.'
            op['data'].update(verdict='DEFECT_FOUND',unchecked=[],checked=[
                dict(ref=row['target_ref'],locators=row['locators'],aspect=aspect,**{key:row[key] for key in A.SCOPE_META})
                for row in requirement['required_scope'] for aspect in row['aspects']])
            admit_scientific_response(h,review,envelope)
            state=h.reopen();sid=affected['support_id'];support=state['supports'][sid]
            defect=next(q['assessment_ref'] for q in state['qualifications'].values()
                if state['review_executions'][q['review_execution_event']]['task_id']==review['task']['task_id'])
            worker=h.prepare(actor='WORKER');h.slot(worker);h.send(worker);h.dispatch(worker,'SENT')
            envelope=json.loads(demo.response(worker['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            withdrawal=dict(op='WITHDRAW_SUPPORT',support_id=sid,
                expected_qualification_head=sha(canonical(support['qualification_refs'])),reason_code='SYNTHETIC_SCOPED_DEFECT',
                evidence_refs=[defect],scope=deepcopy(support['consumer_requirement']['required_scope']))
            envelope['payload']['operations']=[withdrawal]
            for effect in envelope['payload']['obligation_effects']:
                effect.update(work_disposition='ADDRESSED',resolution_proposal='NEEDS_RECHECK',evidence_refs=[seed['target']])
            wrong=deepcopy(envelope);other=state['supports'][survivor['support_id']]
            wrong['payload']['operations'][0].update(support_id=survivor['support_id'],
                expected_qualification_head=sha(canonical(other['qualification_refs'])),scope=deepcopy(other['consumer_requirement']['required_scope']))
            unchanged=h.store._head()
            with self.assertRaisesRegex(PMRSError,'AUTHORIZATION_REQUIRED'):
                changes.validate_response(worker['task'],h.store.read_snapshot(),canonical(wrong),blob_get=h.store.read_blob)
            self.assertEqual(h.store._head(),unchanged)
            admit_scientific_response(h,worker,envelope);current_state=h.reopen()
            self.assertEqual({w['support_id'] for w in current_state['withdrawals'].values()},{sid})
            # Preserve the real exhausted-window rejection; no frozen allowance
            # or existing delivery is reset when a later MAIN is prepared.
            delivered_get(module['ref'],expected_error='DYNAMIC_INPUT_LIMIT')
            original_deliveries=input_delivery.manifest(h.store.read_snapshot(),reader_main['spec'].request_id)
            self.assertEqual(budget_remaining(h.store.read_snapshot(),grant_id),2)
            readers=[]
            def next_reader(previous):
                state=h.reopen();remaining=budget_remaining(state,grant_id)
                self.assertGreater(remaining,0)
                self.assertEqual(state['budget_grants'],authorized_grants)
                self.assertEqual(state['project_budget'],authorized_project)
                _,_,capture_args=measured_knowledge_query('next-reader-capture:'+previous['spec'].request_id,lambda:
                    h.capture_fast(previous,delta_for(state,previous['task'],[],
                        empty_reason='No new fast evidence; continue exact current and historical reading in a later authorized input window.')))
                h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=previous['spec'].request_id,
                    capture_ref=capture_args['capture_ref'])),h.service,grant_ref=h.grant(),manifest_ref=previous['manifest_ref'])
                state=h.reopen();prior=state['requests'][previous['spec'].request_id]
                self.assertEqual(prior['acceptance_state'],'REJECTED_CONTRACT')
                self.assertEqual(prior['admission']['charge'],'SPENT_OR_SETTLED')
                self.assertFalse(control_lane_closed(prior))
                self.assertFalse([c for c in scheduler.plan(state,[h.iid],h.policy)['selected']
                    if c['consumer'].get('actor_kind')=='MAIN'])
                h.observation(previous,'TERMINATED')
                self.assertTrue(control_lane_closed(h.reopen()['requests'][previous['spec'].request_id]))
                reader=h.prepare(actor='MAIN');h.send(reader);h.dispatch(reader,'SENT')
                self.assertEqual(reader['task']['mission_id'],reader_main['task']['mission_id'])
                self.assertEqual(reader['task']['budget_grant'],grant_id)
                self.assertEqual(reader['task']['communication_contract'],reader_main['task']['communication_contract'])
                self.assertNotIn(reader['spec'].request_id,{rid,successor['spec'].request_id,
                    reader_main['spec'].request_id,*readers})
                state=h.reopen();self.assertEqual(budget_remaining(state,grant_id),remaining-1)
                self.assertEqual(state['budget_grants'],authorized_grants)
                self.assertEqual(state['project_budget'],authorized_project)
                self.assertEqual(input_delivery.manifest(state,reader_main['spec'].request_id),original_deliveries)
                self.assertFalse([d for d in state['input_deliveries'].values() if d['request_id']==reader['spec'].request_id])
                readers.append(reader['spec'].request_id)
                return reader
            current_reader=reader_main
            for upper,basis in ((module['ref'],'OPEN'),(second[0]['ref'],'QUALIFIED_WITHIN_EXACT_SCOPE')):
                current_reader=next_reader(current_reader)
                human=Q.web_tool(h.store,'get',{'ref':[upper],'instance_id':[h.iid]})
                self.assertEqual(human['derived']['bindings'][0]['qualification']['support_basis'],basis)
                self.assertEqual(delivered_get(upper,reader=current_reader)['derived']['bindings'],human['derived']['bindings'])
                historical=Q.web_tool(h.store,'get',{'ref':[upper],'instance_id':[h.iid],'as_of_commit':[reuse_head]})
                self.assertEqual(historical['derived']['bindings'][0]['qualification']['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
                self.assertEqual(delivered_get(upper,reuse_head,reader=current_reader)['derived']['bindings'],historical['derived']['bindings'])
            self.assertEqual(h.store.read_blob(binding['ref'][3:]),binding_bytes)
            self.assertEqual(h.store.read_blob(second[-1]['ref'][3:]),canonical(second[-1]['body']))
            state=h.reopen();self.assertEqual(h.restart_read()['commit'],state['knowledge_commit'])
            self.assertEqual(budget_remaining(state,grant_id),0)
            self.assertEqual(state['budget_grants'],authorized_grants);self.assertEqual(state['project_budget'],authorized_project)
            self.assertEqual(state['records'][seed['target']],settled['records'][seed['target']])
            print('SOURCE13_QUALIFIED_REUSE_WITHDRAWAL '+json.dumps(dict(original=rid,
                applying=successor['spec'].request_id,display_applying=reader_main['spec'].request_id,
                U1=entries[0]['ref'],B1=binding['ref'],U2=module['ref'],surviving_binding=second[-1]['ref'],
                native_disposition='REJECTED_CONTRACT',fast_disposition='APPLIED',withdrawn_support=sid,reading_requests=readers),sort_keys=True),flush=True)


    def test_source16_FM09_two_commands_same_object_and_explicit_reprepare(self):
        from .test_domain import rehash
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,first=h.running_pair()
            h.dispatch_workers(main,1,label='source16-second')
            second=h.prepare(actor='WORKER');h.slot(second);h.send(second);h.dispatch(second,'SENT')
            state=h.reopen();a=six_entries(state,first['task'])[0];b=six_entries(state,second['task'])[0]
            b['body']['payload']['title']='Independent competing proposal';rehash(b)
            self.assertEqual(a['body']['object_id'],b['body']['object_id']);self.assertNotEqual(a['ref'],b['ref'])
            _,one,_=h.capture_fast(first,delta_for(state,first['task'],[a]))
            state=h.reopen();_,two,_=h.capture_fast(second,delta_for(state,second['task'],[b]))
            session=h.session(acting_request_id=main['spec'].request_id)
            stale=h.fast_arguments('source16-stale',session,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            h.observation(main,'RUNNING');before=h.store._head()
            with self.assertRaises(FastMathError):h.store.fastmath_service().commit_delta(one['proposal_ref'],**stale)
            self.assertEqual(h.store._head(),before)
            applied,_=h.apply_fast(one['proposal_ref'],main)
            self.assertNotEqual(applied['operation_id'],stale['operation_id'])
            self.assertEqual(h.reopen()['fast_selected'][a['body']['object_id']],a['ref'])
            before=h.store._head()
            with self.assertRaises(FastMathError):h.apply_fast(two['proposal_ref'],main)
            self.assertEqual(h.store._head(),before)
            state=h.reopen();self.assertEqual(state['fast_selected'][a['body']['object_id']],a['ref'])
            self.assertNotIn(b['ref'],state['fast_revisions'])

    def test_source16_FM19_disk_refusal_and_damaged_manifest_keep_HEAD(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from pmrh.adapters.storage import io as I
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();state=h.reopen()
            _,captured,_=h.capture_fast(worker,delta_for(state,worker['task'],six_entries(state,worker['task'])))
            session=h.session(acting_request_id=main['spec'].request_id)
            args=h.fast_arguments('source16-capacity',session,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            before=h.store._head();head_bytes=(h.store.root/'HEAD').read_bytes()
            with patch.object(I.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaises(FastMathError) as denied:
                    h.store.fastmath_service().commit_delta(captured['proposal_ref'],**args)
            self.assertIsInstance(denied.exception.__cause__,PMRSError)
            self.assertEqual(denied.exception.__cause__.code,'RESOURCE_DISK_LOW')
            self.assertEqual((h.store.root/'HEAD').read_bytes(),head_bytes);self.assertEqual(h.store._head(),before)
            self.assertEqual(Journal(h.store.root).read_snapshot()['knowledge_commit'],before['commit'])
            manifest_path=h.store.root/'blobs'/main['manifest_ref']['sha256'];original=manifest_path.read_bytes()
            manifest_path.write_bytes(original[:-1]+b'!')
            with self.assertRaises((PMRSError,FastMathError)):
                h.store.fastmath_service().commit_delta(captured['proposal_ref'],**args)
            self.assertEqual((h.store.root/'HEAD').read_bytes(),head_bytes);self.assertEqual(h.store._head(),before)
            with self.assertRaises(PMRSError):Journal(h.store.root).read_snapshot()
            manifest_path.write_bytes(original)
            applied,_=h.apply_fast(captured['proposal_ref'],main)
            self.assertEqual(h.reopen()['knowledge_commit'],applied['commit'])

    def test_source18_historical_qualified_fast_withdrawal_keeps_current_authority(self):
        import json
        from .fixtures import native_qualified_pair,scientific_worker,admit_scientific_response
        from research_studio import demo,input_delivery,knowledge_access as Q
        from research_studio.task_tools import TaskTools
        from research_studio.store import Store
        from pmrh.domain import assurance as A
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);seed=native_qualified_pair(h);main=seed['main'];branch=seed['paths'][0]
            state=h.reopen();entries=six_entries(state,main['task'],argument_ref=branch['argument_ref'],support_ids=[branch['support_id']])
            from .test_domain import rehash
            from research_studio.context import _source_tainted
            assessment=next(q['assessment_ref'] for q in state['qualifications'].values()
                if state['review_executions'][q['review_execution_event']]['task_id']==branch['review']['task']['task_id'])
            self.assertTrue(_source_tainted(assessment,state))
            tainted=deepcopy(entries[0]);tainted['body']['object_id']='source18-review-derived'
            tainted['body']['payload']['title']='source18 prior verdict private title'
            tainted['body']['body']='source18 prior verdict private body'
            tainted['body']['dependencies']=[seed['target'],assessment];rehash(tainted)
            _,captured,args=h.capture_fast(main,delta_for(state,main['task'],[entries[0],entries[-1],tainted]))
            h.control.apply(h.command('SCIENCE_ADMITTED',dict(request_id=main['spec'].request_id,capture_ref=args['capture_ref'])),
                h.service,grant_ref=h.grant(),manifest_ref=main['manifest_ref'])
            self.assertEqual(h.reopen()['requests'][main['spec'].request_id]['acceptance_state'],'REJECTED_CONTRACT')
            h.observation(main,'TERMINATED')
            reader=h.prepare(actor='MAIN');h.send(reader);h.dispatch(reader,'SENT')
            applied,_=h.apply_fast(captured['proposal_ref'],reader);pinned=applied['commit'];upper=entries[0]['ref']
            original=Q.web_tool(Store(h.store.root),'get',{'ref':[upper],'instance_id':[h.iid]})
            self.assertEqual(original['derived']['bindings'][0]['qualification']['support_basis'],'QUALIFIED_WITHIN_EXACT_SCOPE')
            def delivered(ref,as_of=None,confirm=False):
                frame=h.command('COMMUNICATION_APPLIED',{})
                keys={key:frame[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**keys,grant_ref=h.grant(),manifest_ref=reader['manifest_ref']):
                    did,response=TaskTools(h.store,reader['spec'].request_id,reader['spec'].execution_id).call(
                        'knowledge_get',dict(ref=ref,**({'as_of_commit':as_of} if as_of else {})))
                self.assertFalse(response['isError'],response)
                saved=h.store.read_snapshot()['input_deliveries'][did]
                self.assertEqual(h.store.read_blob(saved['response_ref']),canonical(response))
                if confirm:
                    frame=h.command('COMMUNICATION_APPLIED',{})
                    keys={key:frame[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                    with h.control.native_context(h.service,**keys):
                        input_delivery.confirm(h.store,reader['spec'].request_id,reader['spec'].execution_id,did)
                    self.assertIn(ref,input_delivery.supplied_records(h.store.read_snapshot(),reader['task'],h.store.read_blob,live=True))
                return json.loads(response['content'][0]['text'])['result']
            # A real cooperative worker still cannot receive an upper whose
            # native dependency is a prior Assessment. This is not the isolated
            # review mode's unconditional fast-object exclusion.
            self.assertEqual(Q.web_tool(Store(h.store.root),'get',{'ref':[tainted['ref']],'instance_id':[h.iid]})['body'],tainted['body']['body'])
            limited=scientific_worker(h,reader,'source18-taint-reader',inputs=[seed['target']])
            self.assertEqual(limited['task']['communication_contract']['mode'],'COOPERATIVE')
            for name,arguments in (('knowledge_search',{'query':'source18 prior verdict','kind':'KnowledgeModule'}),
                                   ('knowledge_search',{'query':'source18 prior verdict','kind':'KnowledgeModule','as_of_commit':pinned}),
                                   ('knowledge_get',{'ref':tainted['ref']}),
                                   ('knowledge_get',{'ref':tainted['ref'],'as_of_commit':pinned})):
                frame=h.command('COMMUNICATION_APPLIED',{})
                keys={key:frame[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                with h.control.native_context(h.service,**keys,grant_ref=h.grant(),manifest_ref=limited['manifest_ref']):
                    did,response=TaskTools(h.store,limited['spec'].request_id,limited['spec'].execution_id).call(name,arguments)
                value=json.loads(response['content'][0]['text'])['result']
                if name=='knowledge_search':
                    self.assertFalse(response['isError']);self.assertEqual(value['results'],[])
                    self.assertEqual(value['next_position'],0);self.assertEqual(value['body_bytes_read_this_call'],0)
                else:self.assertTrue(response['isError']);self.assertEqual(value['error'],'KNOWLEDGE_FORBIDDEN')
                for secret in (tainted['ref'],tainted['body']['body'],tainted['body']['payload']['title']):
                    self.assertNotIn(secret,canonical(response).decode())
                self.assertEqual(h.store.read_snapshot()['input_deliveries'][did]['supplements'],[])
            delivered(branch['argument_ref'],confirm=True)
            review=scientific_worker(h,reader,'source18-defect',role='PROOF',inputs=[seed['target'],branch['argument_ref']])
            h.dispatch_workers(reader,1,label='source18-withdraw',stage='P4',role='RESEARCH',duty='ESTABLISH',inputs=[seed['target']])
            envelope=json.loads(demo.response(review['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            requirement=review['task']['required_assurance'];op=envelope['payload']['operations'][0]
            op['body']='Synthetic exact-scope defect for the first branch; no claim about real mathematics.'
            op['data'].update(verdict='DEFECT_FOUND',unchecked=[],checked=[
                dict(ref=row['target_ref'],locators=row['locators'],aspect=aspect,**{key:row[key] for key in A.SCOPE_META})
                for row in requirement['required_scope'] for aspect in row['aspects']])
            admit_scientific_response(h,review,envelope)
            state=h.reopen();support=state['supports'][branch['support_id']]
            defect=next(q['assessment_ref'] for q in state['qualifications'].values()
                if state['review_executions'][q['review_execution_event']]['task_id']==review['task']['task_id'])
            worker=h.prepare(actor='WORKER');h.slot(worker);h.send(worker);h.dispatch(worker,'SENT')
            envelope=json.loads(demo.response(worker['task'],h.store.read_snapshot(),blob_get=h.store.read_blob))
            envelope['payload']['operations']=[dict(op='WITHDRAW_SUPPORT',support_id=branch['support_id'],
                expected_qualification_head=sha(canonical(support['qualification_refs'])),reason_code='SYNTHETIC_SCOPED_DEFECT',
                evidence_refs=[defect],scope=deepcopy(support['consumer_requirement']['required_scope']))]
            for effect in envelope['payload']['obligation_effects']:
                effect.update(work_disposition='ADDRESSED',resolution_proposal='NEEDS_RECHECK',evidence_refs=[seed['target']])
            admit_scientific_response(h,worker,envelope);current=h.reopen()
            self.assertEqual({x['support_id'] for x in current['withdrawals'].values()},{branch['support_id']})
            now=Q.web_tool(Store(h.store.root),'get',{'ref':[upper],'instance_id':[h.iid]})
            self.assertEqual(now['derived']['bindings'][0]['qualification']['support_basis'],'OPEN')
            old=Q.web_tool(Store(h.store.root),'get',{'ref':[upper],'instance_id':[h.iid],'as_of_commit':[pinned]})
            self.assertEqual(old['derived'],original['derived']);self.assertEqual(old['latest_status'],now['derived'])
            self.assertEqual(delivered(upper,pinned)['derived'],old['derived'])
            found=Q.web_tool(Store(h.store.root),'search',{'query':['Addition interface'],'kind':['KnowledgeModule'],'instance_id':[h.iid],'as_of_commit':[pinned]})
            self.assertIn(upper,{row['ref'] for row in found['results']})
            self.assertTrue(Q.dependencies(Store(h.store.root),upper,task=reader['task'],as_of_commit=pinned)['dependencies'])
            foreign=deepcopy(reader['task']);foreign['mission_id']='source18-foreign-mission'
            with self.assertRaises(PMRSError):Q.get(Store(h.store.root),upper,task=foreign,as_of_commit=pinned)
            reason=h.blob('source18-revoke',b'Actual synthetic current read revocation',raw=True)
            h.control.apply(h.command('GRANT_REVOKED',dict(budget_grant_id='BUDGET-synthetic',expected_revision=1,reason_ref=reason)),h.operator,grant_ref=h.grant())
            revoked=h.store.read_snapshot();head=h.store._head()
            with self.assertRaisesRegex(PMRSError,'KNOWLEDGE_FORBIDDEN'):
                Q.get(Store(h.store.root),upper,task=reader['task'],as_of_commit=pinned)
            with self.assertRaisesRegex(PMRSError,'CONTROL_INVALID'):delivered(upper,pinned)
            self.assertEqual(h.store._head(),head)
            self.assertEqual(h.store.read_snapshot()['input_deliveries'],revoked['input_deliveries'])


    def test_source17_same_scan_native_closure_new_blob_corruption_and_duplicate_authority(self):
        from collections import Counter
        from unittest.mock import patch
        from pmrh.adapters.storage.io import _ConfinedReader
        from tests.devpr06.test_control import Harness as ControlHarness
        for fixture,schema in ((ControlHarness,'pmrh.commit/2'),(Harness,'pmrh.control-fast.commit/1')):
            with self.subTest(profile=schema),tempfile.TemporaryDirectory() as tmp:
                h=fixture(tmp);h.authorize(2,attempts=2,communication=True)
                main=h.prepare();h.send(main);h.dispatch(main,'SENT')
                duplicate=h.observation(main,'RUNNING');h.observation(main,'RUNNING')
                original_record=Journal.read_record;counts=Counter();readers=[]
                def read_record(journal,reference):
                    record=original_record(journal,reference);counts[reference]+=1
                    return record
                def reopen(label):
                    counts.clear()
                    def read():
                        with _ConfinedReader(h.store.root) as reader:
                            readers.append(reader)
                            self.assertEqual((reader.remaining_files,reader.remaining_bytes),(4096,128*1024**2))
                            journal=Journal(reader.root,reader=reader)
                            history=journal.history();state=journal.read_snapshot()
                            self.assertEqual(history[-1][1]['schema'],schema)
                            self.assertEqual(set(journal._control_index.states),{head['commit'] for head,_ in history})
                            self.assertEqual(counts,Counter({ref:1 for ref in state['records']}))
                            for past in journal._control_index.states.values():
                                for ref,record in past.get('records',{}).items():
                                    self.assertEqual(record,state['records'][ref])
                            if label=='before-new-capture':
                                remaining=(reader.remaining_files,reader.remaining_bytes)
                                self.assertEqual(journal.read_snapshot(),state)
                                self.assertEqual(counts,Counter({ref:2 for ref in state['records']}))
                                self.assertLess(reader.remaining_files,remaining[0]);self.assertLess(reader.remaining_bytes,remaining[1])
                            self.assertGreater(reader.remaining_files,0);self.assertLess(reader.remaining_files,4096)
                            self.assertGreaterEqual(reader.remaining_bytes,0);self.assertLess(reader.remaining_bytes,128*1024**2)
                            return state
                    with patch.object(Journal,'read_record',read_record):
                        return measured_knowledge_query('source17:'+schema+':'+label,read)
                before=reopen('before-new-capture');target=before['instances'][h.iid]['target_ref']
                self.assertIsNone(before['requests'][main['spec'].request_id].get('capture_ref'))
                captured,raw=h.capture(main,b'Synthetic newly sealed source17 capture; no scientific admission.')
                current=reopen('after-new-capture')
                self.assertEqual(current['requests'][main['spec'].request_id]['capture_ref'],captured['sha256'])
                self.assertEqual(current['records'],before['records'])
                self.assertIsNot(readers[0],readers[1]);self.assertTrue(all(r.fd is None for r in readers))
                head=h.store._head()
                # Both an old native body and the newly introduced capture must
                # be read/hash-checked again by a fresh public reader.
                for digest in (before['records'][target]['body_sha256'],captured['sha256']):
                    path=h.store.root/'blobs'/digest;original=path.read_bytes()
                    try:
                        path.write_bytes(bytes([original[0]^1])+original[1:])
                        with self.assertRaisesRegex(PMRSError,'BLOB_CHANGED'):
                            reopen('corrupt:'+digest)
                        self.assertEqual(h.store._head(),head)
                    finally:path.write_bytes(original)
                    self.assertEqual(reopen('restored:'+digest)['knowledge_commit'],head['commit'])
                retry=h.control.apply(duplicate,h.service)
                self.assertTrue(retry['duplicate']);self.assertEqual(h.store._head(),head)
                h.registry.revoke(h.service)
                with self.assertRaises(PMRSError):h.control.apply(duplicate,h.service)
                self.assertEqual(h.store._head(),head)


    def test_source11_same_query_history_reuse_keeps_checkpoint_and_fresh_ancestry_checks(self):
        import json
        from unittest.mock import patch
        from pmrh.adapters.storage import control_fast
        from research_studio import knowledge_access as Q
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True)
            before=h.store.read_snapshot();old=before['knowledge_commit'];target=before['instances'][h.iid]['target_ref']
            _,capture,_=h.capture_fast(worker,delta_for(before,worker['task'],six_entries(before,worker['task'])))
            h.apply_fast(capture['proposal_ref'],main);current=h.reopen()
            original_scan=control_fast.scan;readers=[];budgets=[]
            def counted_scan(store,*args,**kwargs):
                readers.append(store._reader);start=store._reader.remaining_files
                result=original_scan(store,*args,**kwargs)
                budgets.append((start,store._reader.remaining_files));return result
            with patch.object(control_fast,'scan',counted_scan):
                first=Q.web_tool(Store(h.store.root),'get',{'ref':[target],'instance_id':[h.iid],'as_of_commit':[old]})
                self.assertEqual(len(readers),1)
                second=Q.web_tool(Store(h.store.root),'get',{'ref':[target],'instance_id':[h.iid],'as_of_commit':[old]})
                self.assertEqual(len(readers),2);self.assertIsNot(readers[0],readers[1])
            self.assertEqual(first,second);self.assertEqual(first['as_of_commit'],old)
            self.assertTrue(all(0<=end<start<=4096 for start,end in budgets))
            self.assertTrue(all(reader.fd is None for reader in readers))
            with self.assertRaisesRegex(PMRSError,'SNAPSHOT_NOT_FOUND'):
                Q.get(Store(h.store.root),target,instance_id=h.iid,as_of_commit='0'*64)

            # Corrupt only after the current snapshot completed. Historical
            # selection must still inspect the real selected/fallback checkpoint.
            checkpoint=h.store.root/'checkpoints'/(h.genesis+'.json')
            raw=checkpoint.read_bytes();original_snapshot=Journal.read_snapshot
            for mode in ('unknown_field','wrong_digest','wrong_commit','forged_state','missing_fallback'):
                row=json.loads(raw)
                if mode=='unknown_field':row['extra']=True
                elif mode=='wrong_digest':row['state_sha256']='0'*64
                elif mode=='wrong_commit':row['commit']=old
                elif mode=='forged_state':
                    row['state']['title']='Forged synthetic checkpoint title';row['state_sha256']=sha(canonical(row['state']))
                def tamper_after_current(journal,commit=None):
                    result=original_snapshot(journal,commit)
                    if commit is None:
                        if mode=='missing_fallback':checkpoint.unlink()
                        else:checkpoint.write_bytes(canonical(row))
                    return result
                try:
                    with self.subTest(checkpoint=mode),patch.object(Journal,'read_snapshot',tamper_after_current):
                        if mode=='missing_fallback':
                            self.assertEqual(Q.get(Store(h.store.root),target,instance_id=h.iid,as_of_commit=old),first)
                        else:
                            code='CHECKPOINT_INVALID' if mode=='unknown_field' else 'CHECKPOINT_CHANGED'
                            with self.assertRaisesRegex(PMRSError,code):
                                Q.get(Store(h.store.root),target,instance_id=h.iid,as_of_commit=old)
                finally:checkpoint.write_bytes(raw)
            selected=h.store.root/'checkpoints'/(old+'.json')
            self.assertFalse(selected.exists())
            def unbound_selected(journal,commit=None):
                result=original_snapshot(journal,commit)
                if commit is None:
                    forged=json.loads(raw);forged['commit']=old
                    selected.write_bytes(canonical(forged))
                return result
            try:
                with patch.object(Journal,'read_snapshot',unbound_selected),self.assertRaisesRegex(PMRSError,'CHECKPOINT_CHANGED'):
                    Q.get(Store(h.store.root),target,instance_id=h.iid,as_of_commit=old)
            finally:selected.unlink(missing_ok=True)
            head_file=h.store.root/current['_head']['path'];head_raw=head_file.read_bytes()
            try:
                head_file.write_bytes(head_raw+b' ')
                with self.assertRaises(PMRSError):Q.get(Store(h.store.root),target,instance_id=h.iid,as_of_commit=old)
            finally:head_file.write_bytes(head_raw)
            self.assertEqual(Q.get(Store(h.store.root),target,instance_id=h.iid,as_of_commit=old),first)

    def test_source11_historical_query_rechecks_current_task_permission(self):
        import json
        from research_studio import knowledge_access as Q
        from research_studio.task_tools import TaskTools
        from research_studio.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair(communication=True)
            state=h.store.read_snapshot();old=state['knowledge_commit'];target=state['instances'][h.iid]['target_ref']
            h.capture(worker,b'Synthetic original capture; no scientific admission.')
            self.assertEqual(Q.get(Store(h.store.root),target,task=main['task'],as_of_commit=old)['ref'],target)
            tools=TaskTools(h.store,main['spec'].request_id,main['spec'].execution_id)
            def delivered_get(*,live=True):
                command=h.command('COMMUNICATION_APPLIED',{})
                frame={key:command[key] for key in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
                authority=dict(grant_ref=h.grant(),manifest_ref=main['manifest_ref']) if live else {}
                with h.control.native_context(h.service,**frame,**authority):
                    return tools.call('knowledge_get',dict(ref=target,as_of_commit=old))
            delivery,response=delivered_get();self.assertFalse(response['isError'])
            self.assertEqual(json.loads(response['content'][0]['text'])['result']['as_of_commit'],old)
            saved=h.store.read_snapshot()['input_deliveries'][delivery]
            self.assertEqual(h.store.read_blob(saved['response_ref']),canonical(response))
            prior=Q.search(Store(h.store.root),'',task=main['task'],limit=1)
            self.assertIsNotNone(prior['continuation'])
            active=Q.get(Store(h.store.root),target,task=main['task'],as_of_commit=old)
            h.pause();paused=h.store.read_snapshot();head=h.store._head()
            gid=paused['requests'][main['spec'].request_id]['budget_grant_id']
            self.assertEqual(paused['instances'][h.iid]['status'],'PAUSED')
            self.assertEqual(paused['budget_grants'][gid]['grant_status'],'ACTIVE')
            self.assertFalse(paused['requests'][main['spec'].request_id]['fenced'])
            # PAUSE preserves the authorized internal projection. New TaskTools
            # delivery is separately denied by the active request boundary.
            self.assertEqual(Q.get(Store(h.store.root),target,task=main['task'],as_of_commit=old),active)
            self.assertEqual(h.store._head(),head)
            # TOOL_CONTROL_REJECTED is an existing recovery receipt. Its native
            # context carries no live-delivery grant/manifest; it grants no body.
            denied_delivery,denied=delivered_get(live=False)
            self.assertIsNone(denied_delivery);self.assertTrue(denied['isError'])
            denied_body=json.loads(denied['content'][0]['text'])
            self.assertEqual(denied_body['error'],'TASK_FENCED')
            self.assertNotIn('body',denied_body);self.assertNotIn('result',denied_body)
            after=h.store.read_snapshot()
            self.assertNotEqual(after['knowledge_commit'],head['commit'])
            self.assertEqual(after['_snapshot_sequence'],head['sequence']+1)
            self.assertEqual(after['input_deliveries'],paused['input_deliveries'])
            self.assertEqual(after['input_windows'],paused['input_windows'])
            events=[e for key,e in after['communication_events'].items() if key not in paused['communication_events']]
            self.assertEqual(len(events),1);event=events[0]
            self.assertEqual(event['event_type'],'TOOL_CONTROL_REJECTED')
            self.assertIs(event['payload']['scientific_input_delivered'],False)
            self.assertEqual(event['payload']['request_id'],main['spec'].request_id)
            self.assertEqual(h.store.read_blob(event['payload']['response_ref']),canonical(denied))
            self.assertEqual(h.store.read_blob(saved['response_ref']),canonical(response))

            # Public grant revocation, unlike PAUSE, removes task read authority
            # even for the previously pinned historical view and continuation.
            reason=h.blob('source12-revoke',b'Synthetic explicit read-authority revocation',raw=True)
            h.control.apply(h.command('GRANT_REVOKED',dict(budget_grant_id=gid,
                expected_revision=after['budget_grants'][gid]['grant_revision'],reason_ref=reason)),
                h.operator,grant_ref=h.grant())
            revoked=h.store.read_snapshot();head=h.store._head()
            self.assertEqual(revoked['budget_grants'][gid]['grant_status'],'REVOKED')
            with self.assertRaisesRegex(PMRSError,'KNOWLEDGE_FORBIDDEN'):
                Q.get(Store(h.store.root),target,task=main['task'],as_of_commit=old)
            with self.assertRaisesRegex(PMRSError,'KNOWLEDGE_FORBIDDEN'):
                Q.search(Store(h.store.root),'',task=main['task'],continuation=prior['continuation'])
            # Human web_tool project scope comes from the trusted upstream
            # session/workspace; this is an adapter test, not HTTP auth evidence.
            human=Q.web_tool(Store(h.store.root),'get',{'ref':[target],'as_of_commit':[old]})
            self.assertEqual(human['body'],active['body']);self.assertEqual(human['body_sha256'],active['body_sha256'])
            self.assertEqual(h.store._head(),head)
