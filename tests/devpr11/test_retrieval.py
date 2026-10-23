"""Real persisted native/combined reads; no final reader dictionary injection."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from pmrh.domain.primitives import canonical,sha,PMRSError
from research_studio.store import Store
from research_studio import changes,knowledge_access as Q,strategy
from .fixtures import Harness,six_entries,delta_for


def native_project(root):
    return Store.create(Path(root)/'native','Synthetic bounded retrieval',synthetic=True)


def add_source(store,raw,sid):
    return store.commit(changes.prepare_material_input(store.read_snapshot(),raw,source_id=sid,
        title='Synthetic exact occurrence',media_type='text/plain',blob_get=store.read_blob))


def manifest(root):
    return {str(p.relative_to(root)):sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}


class RetrievalTests(unittest.TestCase):
    def test_FM12_beyond_2048_UTF8_exact_locator_and_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);raw=('x'*4097+'\nα needle\nβ end').encode()
            add_source(store,raw,'SO-late');add_source(store,b'\xff\x00needle','SO-binary')
            page=Q.search(Store(store.root),'needle')
            hit=next(r for r in page['results'] if r['ref']=='SO-late');loc=hit['locator']
            self.assertGreater(loc['start'],2048);self.assertEqual(raw[loc['start']:loc['end']],b'needle')
            self.assertEqual(loc['quoted_sha256'],sha(b'needle'));self.assertIn('needle',hit['excerpt'])
            self.assertIn('SO-binary',page['categories']['unsupported'])
            self.assertFalse(page['complete_for_this_call_scope'])
            with self.assertRaises(PMRSError):Q.get(store,'SO-binary')

    def test_FM26_bounded_continuation_and_forged_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp)
            for n in range(70):add_source(store,b'late needle' if n==69 else b'shared ordinary body','SO-%04d'%n)
            first=Q.search(store,'needle');self.assertEqual(first['results'],[]);self.assertTrue(first['has_more_after_position'])
            second=Q.search(Store(store.root),'needle',continuation=first['continuation'])
            self.assertEqual(second['results'][0]['ref'],'SO-0069');self.assertEqual(second['as_of_commit'],first['as_of_commit'])
            self.assertFalse(second['complete_for_this_call_scope']);self.assertEqual(second['not_scanned_by_this_call']['before'],[0,64])
            with self.assertRaises(PMRSError):Q.search(store,'different',continuation=first['continuation'])
            wire=json.loads(base64.urlsafe_b64decode(first['continuation'][3:]));wire['position']=70
            forged='k1.'+base64.urlsafe_b64encode(canonical(wire)).decode()
            tail=Q.search(store,'needle',continuation=forged)
            self.assertFalse(tail['complete_for_this_call_scope']);self.assertEqual(tail['scanned_ranges_this_call'],[])
            wire['position']=71
            with self.assertRaises(PMRSError):Q.search(store,'needle',continuation='k1.'+base64.urlsafe_b64encode(canonical(wire)).decode())
            wire['position']=0;wire['scanned']=70
            with self.assertRaises(PMRSError):Q.search(store,'needle',continuation='k1.'+base64.urlsafe_b64encode(canonical(wire)).decode())

    def test_FM13_FEASIBILITY_shared_blobs_distinct_native_occurrences_only(self):
        # This is a feasibility subcase, explicitly NOT the >4096 acceptance.
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);add_source(store,b'shared bytes','SO-one');add_source(store,b'shared bytes','SO-two')
            state=Store(store.root).read_snapshot()
            self.assertEqual(state['sources']['SO-one']['blob_hash'],state['sources']['SO-two']['blob_hash'])
            self.assertEqual(set(state['sources']),{'SO-one','SO-two'})
            self.assertNotEqual(state['sources']['SO-one']['source_id'],state['sources']['SO-two']['source_id'])
            self.assertEqual(len(store.history()),3)
            before=store._head()
            with self.assertRaises(PMRSError):add_source(store,b'changed immutable bytes','SO-one')
            self.assertEqual(store._head(),before)

    def test_FM17_pinned_native_read_purity_and_missing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);add_source(store,b'original needle','SO-original');old=store._head()['commit']
            add_source(store,b'new needle','SO-new');before=manifest(store.root)
            page=Q.search(store,'needle',as_of_commit=old)
            self.assertEqual([r['ref'] for r in page['results']],['SO-original']);self.assertEqual(page['as_of_commit'],old)
            self.assertEqual(before,manifest(store.root))
            missing=Path(tmp)/'missing'
            with self.assertRaises(Exception):Q.search(Store(missing),'needle')
            self.assertFalse(missing.exists())

    def test_FM15_all_six_persisted_objects_through_human_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot()
            entries=six_entries(s,worker['task']);_,captured,_=h.capture_fast(worker,delta_for(s,worker['task'],entries));h.apply_fast(captured['proposal_ref'],main)
            h.reopen()
            for entry in entries:
                ref=entry['ref'];kind=entry['body']['kind']
                result=Q.web_tool(h.store,'get',{'ref':[ref],'instance_id':[h.iid]})
                self.assertEqual(result['kind'],kind);self.assertEqual(result['ref'],ref)
                with self.assertRaises(PMRSError):Q.get(h.store,ref,body_range=dict(start=0,end=1,unit='UTF8_BYTE'))
                self.assertEqual(Q.web_tool(h.store,'get',{'ref':[ref]})['ref'],ref)
                with self.assertRaises(PMRSError):Q.web_tool(h.store,'get',{'ref':[ref],'instance_id':['wrong-instance']})
                page=Q.web_tool(h.store,'search',{'query':[''],'kind':[kind],'limit':['1'],'instance_id':[h.iid]})
                self.assertEqual(page['results'][0]['ref'],ref)
                self.assertIn('objects',Q.web_tool(h.store,'history',{'ref':[ref],'instance_id':[h.iid]}))
                self.assertIn('dependencies',Q.web_tool(h.store,'dependencies',{'ref':[ref],'instance_id':[h.iid]}))
            with self.assertRaises(PMRSError):Q.web_tool(h.store,'get',{'ref':['FM-'+'0'*64],'instance_id':[h.iid]})
            with tempfile.TemporaryDirectory() as other:
                foreign=native_project(other)
                with self.assertRaises(PMRSError):Q.web_tool(foreign,'get',{'ref':[entries[0]['ref']]})

    def test_FM14_authentic_native_research_route_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(tmp);main,worker=h.running_pair();s=h.store.read_snapshot();st=strategy.current(s,h.iid);target=s['instances'][h.iid]['target_ref']
            route=dict(route_key='retained-route',status='ACTIVE',origin='Exact synthetic examination',mechanism='Late route mechanism needle',
                target_relation='UNKNOWN',sufficient_chain='No established chain.',unproved_arrows=['The implication remains open.'],extra_assumptions=[],
                decisive_probe='Obtain exact independent support.',failure_evidence_refs=[target],reactivation_condition='New exact evidence.',
                allocation_rationale='Bounded local probe.',reason='Retain failed mechanism history.',evidence_refs=[target])
            proposal=dict(schema='pmrs.strategy-proposal/1',base_strategy_revision=st['revision'],trigger_refs=list(st['pending_trigger_refs']),
                route_updates=[route],work_items=[],input_plan_proposals=[],progress_account=dict(summary='Retain exact open route.',record_refs=[target],
                remaining_difficulties=['Missing proof.'],scope_limitations=['SYNTHETIC_TEST_ONLY'],failed_or_unperformed=['No proof delivered.'],
                covered_binding_ids=[],frontier_complete=False),direction_answers=[],next_action='CONTINUE',human_decision_needed=[],no_change_reason=None)
            command=h.command('STRATEGY_APPLIED',{'native_event':{}})
            args={k:command[k] for k in ('operation_id','idempotency_key','scope','expected_head','owner_epoch','control_version')}
            with h.control.native_context(h.service,**args,grant_ref=h.grant(),manifest_ref=main['manifest_ref']):
                strategy.dispatch_from_main(h.store,main['spec'].request_id,proposal,'route-operation')
            state=h.reopen();ref=next(iter(state['research_routes']))
            page=Q.web_tool(h.store,'search',{'query':['needle'],'instance_id':[h.iid]})
            self.assertIn(ref,{r['ref'] for r in page['results']});self.assertEqual(state['research_routes'][ref]['failure_evidence_refs'],[target])
            foreign=deepcopy(main['task']);foreign['mission_id']='not-authorized'
            with self.assertRaises(PMRSError):Q.search(h.store,'needle',task=foreign)

    def test_source16_FM17_pinned_HEAD_during_public_writer_commit(self):
        from unittest.mock import patch
        from pmrh.adapters.storage.io import _ConfinedReader
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);add_source(store,b'original needle','SO-before')
            old=store._head();original=_ConfinedReader.read;publication=[]
            def publish_after_read(reader,relative,*args,**kwargs):
                raw=original(reader,relative,*args,**kwargs)
                if relative=='HEAD' and not publication:
                    publication.append(None)
                    add_source(Store(store.root),b'later needle','SO-after')
                    publication[0]=(store._head(),manifest(store.root))
                return raw
            with patch.object(_ConfinedReader,'read',publish_after_read):
                page=Q.web_tool(Store(store.root),'search',{'q':['needle']})
            self.assertEqual(page['as_of_commit'],old['commit'])
            self.assertEqual([hit['ref'] for hit in page['results']],['SO-before'])
            self.assertEqual(len(publication),1);self.assertNotEqual(publication[0][0],old)
            self.assertEqual(store._head(),publication[0][0]);self.assertEqual(manifest(store.root),publication[0][1])
            fresh=Q.web_tool(Store(store.root),'search',{'q':['needle']})
            self.assertEqual({hit['ref'] for hit in fresh['results']},{'SO-before','SO-after'})
            self.assertEqual(fresh['as_of_commit'],publication[0][0]['commit'])



class VerifiedBodyTests(unittest.TestCase):
    def test_P01_01_public_material_beyond_eight_MiB_and_real_web_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);raw=b'x'*(9*1024**2)+b' late Needle end'
            add_source(store,raw,'SO-large');reopened=Store(store.root)
            page=Q.web_tool(reopened,'search',{'q':['needle']});hit=page['results'][0]
            self.assertGreater(hit['locator']['start'],8*1024**2)
            self.assertEqual(raw[hit['locator']['start']:hit['locator']['end']],b'Needle')
            self.assertEqual(hit['locator']['quoted_sha256'],sha(b'Needle'))
            self.assertEqual(page['body_bytes_read_this_call'],len(raw))
            self.assertEqual(page['integrity_probe_attempts_this_call'],1)
            self.assertEqual(page['integrity_probe_bytes_this_call'],0)
            whole=Q.web_tool(reopened,'get',{'ref':['SO-large']})
            self.assertEqual(whole['body'].encode(),raw);self.assertEqual(whole['body_sha256'],sha(raw))
            self.assertTrue({'kind','ref','revision','source','body','body_sha256','index_as_of','read_scope'}<=set(whole))
            self.assertFalse(Q.search(reopened,'absent term')['results'])

    def test_P01_04_chunk_split_UTF8_IGNORECASE_exact_byte_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);needle='αNeeDle\nβ';raw=b'x'*65535+needle.encode()+b'z'*200
            add_source(store,raw,'SO-split')
            hit=Q.search(Store(store.root),'αneedle\nβ')['results'][0];loc=hit['locator']
            self.assertEqual(loc['start'],65535);self.assertEqual(raw[loc['start']:loc['end']],needle.encode())
            self.assertEqual(loc['quoted_sha256'],sha(needle.encode()));self.assertIn(needle,hit['excerpt'])
            self.assertEqual(Q.search(store,'αneedle\nβ!')['results'],[])
            # Python IGNORECASE's Unicode behavior is retained without casefold expansion.
            add_source(store,'İ ı ſ K'.encode(),'SO-unicode')
            for query,piece in (('i','İ'),('s','ſ'),('k','K')):
                result=Q.search(store,query,target_ref='SO-unicode')['results'][0]
                data='İ ı ſ K'.encode();r=result['locator']
                self.assertEqual(data[r['start']:r['end']],piece.encode())

    def test_P01_05_corrupt_tail_discards_earlier_hit_and_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);raw=b'needle '+b'x'*131072;add_source(store,raw,'SO-tail')
            self.assertEqual(Q.search(store,'needle')['results'][0]['ref'],'SO-tail')
            blob=store.root/'blobs'/sha(raw);blob.write_bytes(raw[:-1]+b'y')
            page=Q.search(Store(store.root),'needle')
            self.assertEqual(page['results'],[]);self.assertEqual(page['scanned_ranges_this_call'],[])
            self.assertIn('SO-tail',page['categories']['corrupt']);self.assertFalse(page['complete_for_this_call_scope'])
            with self.assertRaises(PMRSError):Q.get(store,'SO-tail',body_range=dict(start=0,end=6,unit='UTF8_BYTE'))

    def test_P01_03_05_small_exact_budget_real_EOF_and_growth_rejection(self):
        # Ordinary exact-budget analogue only; NOT the real4GiB boundary case.
        from unittest.mock import patch
        from pmrh.adapters.storage import io as I
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);raw=b'needle '+b'a'*65536;digest=store.put_blob(raw);blob=store.root/'blobs'/digest
            budget=I._BodyReadBudget(remaining_bytes=len(raw));calls=[];original=I.os.read
            def observed(fd,n):
                calls.append(n);return original(fd,n)
            with I._ConfinedReader(store.root) as reader,patch.object(I.os,'read',side_effect=observed):
                result=reader.read_verified_body(digest,budget=budget,visitor=Q._MatchVisitor('needle'))
                self.assertEqual(result.result['start'],0);self.assertEqual(reader.remaining_bytes,128*1024**2)
            self.assertEqual(budget.remaining_bytes,0);self.assertEqual(calls[-1],1)
            self.assertEqual(budget.integrity_probe_attempts,1);self.assertEqual(budget.integrity_probe_bytes,0)
            budget=I._BodyReadBudget(remaining_bytes=len(raw));visitor=Q._MatchVisitor('needle');payload=0
            def grow_before_real_probe(fd,n):
                nonlocal payload
                if payload==len(raw) and n==1:
                    with blob.open('ab') as output:output.write(b'!')
                data=original(fd,n);payload+=len(data);return data
            with I._ConfinedReader(store.root) as reader,patch.object(I.os,'read',side_effect=grow_before_real_probe):
                with self.assertRaisesRegex(I._Unavailable,'BLOB_CHANGED'):
                    reader.read_verified_body(digest,budget=budget,visitor=visitor)
            self.assertIsNone(visitor.hit);self.assertEqual(budget.remaining_bytes,0)
            self.assertEqual(budget.integrity_probe_bytes,1);self.assertEqual(budget.integrity_probe_attempts,1)

    def test_P01_06_private_budget_attempts_failure_accounting_and_no_reset(self):
        from pmrh.adapters.storage import io as I
        for kwargs in ({'remaining_bytes':True},{'remaining_files':65},{'remaining_bytes':4294967297}):
            with self.assertRaises(I._Unavailable):I._BodyReadBudget(**kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);first=store.put_blob(b'first body');second=store.put_blob(b'second body')
            budget=I._BodyReadBudget(remaining_bytes=15,remaining_files=3)
            with I._ConfinedReader(store.root) as reader:
                reader.read_verified_body(first,budget=budget,visitor=Q._MatchVisitor('body'))
                remaining=budget.remaining_bytes
                with self.assertRaisesRegex(I._Unavailable,'QUERY_READ_LIMIT'):
                    reader.read_verified_body(second,budget=budget,visitor=Q._MatchVisitor('body'))
                self.assertEqual(budget.remaining_bytes,remaining);self.assertEqual(budget.remaining_files,1)
                with self.assertRaises(FileNotFoundError):reader.read_verified_body('0'*64,budget=budget,visitor=Q._MatchVisitor('body'))
                self.assertEqual(budget.remaining_files,0)
                with self.assertRaisesRegex(I._Unavailable,'QUERY_READ_LIMIT'):
                    reader.read_verified_body(first,budget=budget,visitor=Q._MatchVisitor('body'))
            with I._ConfinedReader(store.root) as reader:
                fresh=I._BodyReadBudget();verified=reader.read_verified_body(second,budget=fresh,visitor=Q._MatchVisitor('body'))
                self.assertEqual(verified.size,len(b'second body'))
            # Full4GiB public paging shortage still needs the heavyweight pair;
            # this private small-budget pair does not claim that acceptance.

    def test_P01_08_real_reopened_range_full_identity_and_invalid_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);raw=('start α needle β '+'z'*70000).encode();add_source(store,raw,'SO-window')
            offset=raw.index(b'needle');window=dict(start=offset,end=offset+6,unit='UTF8_BYTE')
            before=manifest(store.root)
            value=Q.web_tool(Store(store.root),'get',{'ref':['SO-window'],'body_range':[json.dumps(window)]})
            self.assertEqual(value['body'],'needle');self.assertFalse(value['body_complete'])
            self.assertEqual(value['verified_full_body_bytes'],len(raw));self.assertEqual(value['verified_full_body_sha256'],sha(raw))
            self.assertEqual(value['range_locator']['quoted_sha256'],sha(b'needle'));self.assertEqual(value['body_sha256'],sha(raw))
            self.assertEqual(before,manifest(store.root))
            for bad in (dict(start=0,end=65537,unit='UTF8_BYTE'),dict(start=True,end=6,unit='UTF8_BYTE'),
                        dict(start=0,end=10,unit='CODEPOINT'),dict(start=0,end=len(raw)+1,unit='UTF8_BYTE'),
                        dict(start=7,end=8,unit='UTF8_BYTE')):
                with self.subTest(window=bad),self.assertRaises(PMRSError):Q.get(Store(store.root),'SO-window',body_range=bad)
            with tempfile.TemporaryDirectory() as foreign:
                with self.assertRaises(PMRSError):Q.web_tool(native_project(foreign),'get',{'ref':['SO-window'],'body_range':[json.dumps(window)]})

    def test_P01_05_09_actual_shared_reader_symlink_hardlink_nonregular_pairs(self):
        import os
        from pmrh.adapters.storage import io as I
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);raw=b'needle';digest=store.put_blob(raw);blob=store.root/'blobs'/digest
            for attack in ('symlink','hardlink','directory'):
                with self.subTest(attack=attack):
                    blob.unlink()
                    other=store.root/('other-'+attack);other.write_bytes(raw)
                    if attack=='symlink':blob.symlink_to(other)
                    elif attack=='hardlink':os.link(other,blob)
                    else:blob.mkdir()
                    with I._ConfinedReader(store.root) as reader:
                        for action in (lambda:reader.read('blobs/'+digest),
                                       lambda:reader.read_verified_body(digest,budget=I._BodyReadBudget(),visitor=Q._MatchVisitor('needle'))):
                            with self.assertRaises((I._Unavailable,OSError)):action()
                    if attack=='directory':blob.rmdir()
                    else:blob.unlink()
                    blob.write_bytes(raw)
            with I._ConfinedReader(store.root) as reader:
                self.assertEqual(reader.read('blobs/'+digest),raw)
                self.assertEqual(reader.read_verified_body(digest,budget=I._BodyReadBudget(),visitor=Q._MatchVisitor('needle')).size,len(raw))

    def test_P01_09_legacy_read_signature_order_errors_and_accounting_on_new_code(self):
        from pmrh.adapters.storage import io as I
        with tempfile.TemporaryDirectory() as tmp:
            store=native_project(tmp);digest=store.put_blob(b'1234')
            with I._ConfinedReader(store.root,max_files=3,max_bytes=4) as reader:
                with self.assertRaisesRegex(I._Unavailable,'PATH_UNSAFE'):reader.read('../escape')
                self.assertEqual(reader.remaining_files,3)
                self.assertIsNone(reader.read('missing',missing_ok=True))
                self.assertEqual((reader.remaining_files,reader.remaining_bytes),(2,4))
                with self.assertRaisesRegex(I._Unavailable,'QUERY_READ_LIMIT'):reader.read('blobs/'+digest,maximum=3)
                self.assertEqual((reader.remaining_files,reader.remaining_bytes),(1,4))
                self.assertEqual(reader.read('blobs/'+digest),b'1234')
                self.assertEqual((reader.remaining_files,reader.remaining_bytes),(0,0))
                with self.assertRaisesRegex(I._Unavailable,'PATH_UNSAFE'):reader.read('../escape')
                with self.assertRaisesRegex(I._Unavailable,'QUERY_READ_LIMIT'):reader.read('missing',missing_ok=True)
            with self.assertRaisesRegex(I._Unavailable,'READ_CONTEXT_CLOSED'):reader.read('blobs/'+digest)


    def test_source16_P01_05_stream_mutation_and_intermediate_symlink(self):
        import os
        from unittest.mock import patch
        from pmrh.adapters.storage import io as I
        for attack in ('truncate','same_bytes_changed_stat','replaced_inode'):
            with self.subTest(attack=attack),tempfile.TemporaryDirectory() as tmp:
                store=native_project(tmp);raw=b'needle '+b'x'*131072;digest=store.put_blob(raw);blob=store.root/'blobs'/digest
                visitor=Q._MatchVisitor('needle');original=I.os.read;altered=[]
                def mutate(fd,n):
                    data=original(fd,n)
                    if data and not altered:
                        altered.append(True)
                        if attack=='truncate':
                            with blob.open('r+b') as output:output.truncate(65536)
                        elif attack=='same_bytes_changed_stat':
                            with blob.open('r+b') as output:
                                output.seek(0,2);output.write(b'!');output.flush();output.truncate(len(raw))
                        else:
                            blob.unlink();blob.write_bytes(raw)
                    return data
                with I._ConfinedReader(store.root) as reader,patch.object(I.os,'read',mutate):
                    budget=I._BodyReadBudget()
                    with self.assertRaises(I._Unavailable):reader.read_verified_body(digest,budget=budget,visitor=visitor)
                self.assertEqual(altered,[True]);self.assertIsNone(visitor.hit)
                self.assertGreater(4294967296-budget.remaining_bytes,0)
                blob.write_bytes(raw)
                with I._ConfinedReader(store.root) as reader:
                    result=reader.read_verified_body(digest,budget=I._BodyReadBudget(),visitor=Q._MatchVisitor('needle'))
                    self.assertEqual(result.result['start'],0);self.assertEqual(result.sha256,digest)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'reader';root.mkdir();(root/'blobs').mkdir();raw=b'needle';digest=sha(raw)
            (root/'blobs'/digest).write_bytes(raw)
            with I._ConfinedReader(root) as reader:
                self.assertEqual(reader.read('blobs/'+digest),raw)
                self.assertEqual(reader.read_verified_body(digest,budget=I._BodyReadBudget(),visitor=Q._MatchVisitor('needle')).size,len(raw))
            (root/'blobs'/digest).unlink();(root/'blobs').rmdir()
            other=Path(tmp)/'outside';other.mkdir();(other/digest).write_bytes(raw);(root/'blobs').symlink_to(other,target_is_directory=True)
            with I._ConfinedReader(root) as reader:
                with self.assertRaises(OSError):reader.read('blobs/'+digest)
                visitor=Q._MatchVisitor('needle')
                with self.assertRaises(OSError):reader.read_verified_body(digest,budget=I._BodyReadBudget(),visitor=visitor)
                self.assertIsNone(visitor.hit)


def p01_large_get_case():
    """Explicitly selected heavyweight case; excluded from unittest discovery.

    129MiB ordinary compatibility boundary, NOT4GiB acceptance. Controller
    must approve its isolated resource plan before selecting this function.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store=native_project(tmp);raw=b'x'*(129*1024**2)+b' needle'
        add_source(store,raw,'SO-over-metadata-cap');reopened=Store(store.root)
        result=Q.web_tool(reopened,'get',{'ref':['SO-over-metadata-cap']})
        assert result['body'].encode()==raw and result['body_sha256']==sha(raw)
        assert Q.web_tool(reopened,'search',{'q':['needle']})['results'][0]['ref']=='SO-over-metadata-cap'



def _p01_get_boundary(size):
    """Real admitted bytes; explicitly selected moderate boundary, never4GiB."""
    assert size in (256*1024**2,256*1024**2+1)
    with tempfile.TemporaryDirectory() as tmp:
        store=native_project(tmp);tail=b' boundary needle'
        raw=b'x'*(size-len(tail))+tail;digest=sha(raw)
        assert len(raw)==size
        add_source(store,raw,'SO-get-boundary');reopened=Store(store.root)
        state=reopened.read_snapshot()
        assert state['sources']['SO-get-boundary']['blob_hash']==digest
        assert (reopened.root/'blobs'/digest).stat().st_size==size
        before=reopened._head()
        if size==256*1024**2:
            result=Q.web_tool(reopened,'get',{'ref':['SO-get-boundary']})
            assert set(result)=={'kind','ref','revision','source','body','body_sha256','index_as_of','read_scope','as_of_commit'}
            assert result['body'].encode()==raw and result['body_sha256']==digest
            assert result['read_scope']=='EXACT_REGISTERED_OCCURRENCE'
            del result
        else:
            try:Q.web_tool(reopened,'get',{'ref':['SO-get-boundary']})
            except PMRSError as exc:assert exc.code=='KNOWLEDGE_UNAVAILABLE' and 'QUERY_READ_LIMIT' in str(exc)
            else:raise AssertionError('Default get exceeded the unchanged256MiB envelope')
        page=Q.web_tool(Store(store.root),'search',{'q':['needle']})
        assert len(page['results'])==1 and page['complete_for_this_call_scope']
        hit=page['results'][0];loc=hit['locator']
        assert hit['ref']=='SO-get-boundary' and hit['body_sha256']==digest
        assert raw[loc['start']:loc['end']]==b'needle' and loc['end']==size
        assert page['body_bytes_read_this_call']==size and page['integrity_probe_attempts_this_call']==1
        window=dict(start=size-65536,end=size,unit='UTF8_BYTE')
        for attempt in range(2):
            ranged=Q.web_tool(Store(store.root),'get',{'ref':['SO-get-boundary'],'body_range':[json.dumps(window)]})
            assert ranged['body'].encode()==raw[window['start']:]
            assert ranged['body_range']==window and ranged['range_locator']['quoted_sha256']==sha(raw[window['start']:])
            assert ranged['verified_full_body_bytes']==size and ranged['verified_full_body_sha256']==digest
            assert ranged['body_complete'] is False and ranged['read_scope']=='PARTIAL_BODY_RANGE'
            assert ranged['next_byte_offset'] is None
        assert reopened._head()==before
        print('DEV11_P01_BOUNDARY '+json.dumps(dict(material_bytes=size,full_get='RETURNED' if size==256*1024**2 else 'REJECTED_AT_256MiB',
            search_and_range='ASSERTIONS_COMPLETED',scope='EXACT_MODERATE_BOUNDARY_ONLY_NO_4GiB')),flush=True)


def p01_256_mib_case():
    """Separate256MiB admission/get/search/range; excluded from default discovery."""
    _p01_get_boundary(256*1024**2)


def p01_256_mib_plus_one_case():
    """Separate256MiB+1 admission/search/range, default whole-get rejection."""
    _p01_get_boundary(256*1024**2+1)



def p01_4_gib_case():
    """Controller disk/resource-gated EXACT_4GiB; never default discovery.

    The Controller must bind its approved exclusive retained disk at /tmp/tests
    and run this alone in a separate subprocess. No cleanup or automatic retry.
    """
    import gc,resource,time
    assert Path(tempfile.gettempdir()).resolve()==Path('/tmp/tests')
    root=Path('/tmp/tests/p01-exact-4gib');root.mkdir(exist_ok=False)
    started=time.monotonic();status='FAIL';metrics={};store=None
    try:
        store=native_project(root);size=4*1024**3;tail=b' boundary needle'
        chunk=b'x'*(1024**2);endchunk=chunk[:-len(tail)]+tail
        raw=b''.join([chunk]*4095+[endchunk])
        assert type(raw) is bytes and len(raw)==size
        digest=sha(raw);expected_tail=endchunk[-65536:]
        metrics.update(material_bytes=len(raw),material_sha256=digest)
        prepared=changes.prepare_material_input(store.read_snapshot(),raw,source_id='SO-exact-4gib',
            title='Synthetic exact four GiB material',media_type='text/plain',blob_get=store.read_blob)
        committed=store.commit(prepared)
        # All references retaining the whole input (including _material/blobs)
        # leave scope before the first bounded streaming consumer.
        del prepared,raw,chunk,endchunk
        gc.collect()
        reopened=Store(store.root);state=reopened.read_snapshot();source=state['sources']['SO-exact-4gib']
        assert source['source_id']=='SO-exact-4gib' and source['bytes']==size and source['blob_hash']==digest
        assert source['coverage']=='FULL_DOCUMENT' and state['synthetic_test_only'] is True
        assert (reopened.root/'blobs'/digest).stat().st_size==size
        assert all(e['schema']=='pmrs.commit/4.2.2' for _,e in reopened.history())
        before=reopened._head();metrics.update(committed=committed,source=source,blob_stat_bytes=size)
        try:Q.web_tool(reopened,'get',{'ref':['SO-exact-4gib']})
        except PMRSError as exc:
            assert exc.code=='KNOWLEDGE_UNAVAILABLE' and 'QUERY_READ_LIMIT' in str(exc)
            metrics['default_get_error']=str(exc)
        else:raise AssertionError('Default get exceeded the unchanged256MiB envelope')
        page=Q.web_tool(Store(store.root),'search',{'q':['needle']})
        assert len(page['results'])==1 and page['complete_for_this_call_scope']
        hit=page['results'][0]
        assert hit['ref']=='SO-exact-4gib' and hit['body_sha256']==digest
        assert hit['locator']==dict(blob_hash=digest,unit='UTF8_BYTE',start=size-6,end=size,quoted_sha256=sha(b'needle'))
        assert page['body_bytes_read_this_call']==size and page['body_attempts_this_call']==1
        assert page['integrity_probe_attempts_this_call']==1 and page['integrity_probe_bytes_this_call']==0
        metrics['search']=page
        window=dict(start=size-65536,end=size,unit='UTF8_BYTE')
        ranged=Q.web_tool(Store(store.root),'get',{'ref':['SO-exact-4gib'],'body_range':[json.dumps(window)]})
        assert ranged['body'].encode()==expected_tail and ranged['body_range']==window
        assert ranged['range_locator']==dict(blob_hash=digest,**window,quoted_sha256=sha(expected_tail))
        assert ranged['verified_full_body_bytes']==size and ranged['verified_full_body_sha256']==digest
        assert ranged['read_scope']=='PARTIAL_BODY_RANGE' and ranged['body_complete'] is False and ranged['next_byte_offset'] is None
        metrics['range']={key:ranged[key] for key in ('body_range','range_locator','verified_full_body_bytes',
            'verified_full_body_sha256','read_scope','body_complete','next_byte_offset')}
        assert reopened._head()==before
        status='EXACT_4GiB_ASSERTIONS_PASSED'
    finally:
        files=[p for p in root.rglob('*') if p.is_file()]
        print('DEV11_P01_EXTREME '+json.dumps(dict(case='EXACT_4GiB',status=status,project=str(root/'native'),
            retained=True,metrics=metrics,elapsed_seconds=time.monotonic()-started,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            logical_disk_bytes=sum(p.stat().st_size for p in files),allocated_disk_bytes=sum(p.stat().st_blocks*512 for p in files))),flush=True)


def p01_4_gib_plus_one_case():
    """Controller disk/resource-gated REAL_4GiB_PLUS_ONE; nondiscovered.

    Separate sequential subprocess and retained project; no fabricated lengths,
    sparse material, private publication, whole-body decode, or budget changes.
    """
    import gc,hashlib,resource,time
    assert Path(tempfile.gettempdir()).resolve()==Path('/tmp/tests')
    root=Path('/tmp/tests/p01-4gib-plus-one');root.mkdir(exist_ok=False)
    started=time.monotonic();status='FAIL';metrics={}
    def file_manifest():
        rows={}
        for path in sorted(root.rglob('*')):
            if not path.is_file():continue
            digest=hashlib.sha256()
            with path.open('rb') as stream:
                while data:=stream.read(65536):digest.update(data)
            rows[str(path.relative_to(root))]=dict(bytes=path.stat().st_size,sha256=digest.hexdigest())
        return rows
    try:
        store=native_project(root);before=store._head();snapshot=store.read_snapshot();files_before=file_manifest()
        size=4*1024**3+1;chunk=b'x'*(1024**2)
        raw=b''.join([chunk]*4096+[b'x'])
        assert type(raw) is bytes and len(raw)==size
        metrics.update(material_bytes=len(raw),material_sha256=sha(raw))
        try:
            changes.prepare_material_input(snapshot,raw,source_id='SO-over-4gib',
                title='Synthetic over-limit material',media_type='text/plain',blob_get=store.read_blob)
        except PMRSError as exc:
            assert exc.code=='PAYLOAD_LIMIT';metrics['admission_error']=str(exc)
        else:raise AssertionError('Real4GiB+1 bytes were admitted beyond the fixed material bound')
        finally:
            del raw,chunk
            gc.collect()
        reopened=Store(store.root)
        assert reopened._head()==before and reopened.read_snapshot()==snapshot
        files_after=file_manifest();assert files_after==files_before
        assert 'SO-over-4gib' not in reopened.read_snapshot()['sources']
        metrics.update(head=before,unchanged_file_count=len(files_after),
            unchanged_file_manifest_sha256=sha(canonical(files_after)))
        status='REAL_4GiB_PLUS_ONE_ASSERTIONS_PASSED'
    finally:
        files=[p for p in root.rglob('*') if p.is_file()]
        print('DEV11_P01_EXTREME '+json.dumps(dict(case='REAL_4GiB_PLUS_ONE',status=status,project=str(root/'native'),
            retained=True,metrics=metrics,elapsed_seconds=time.monotonic()-started,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            logical_disk_bytes=sum(p.stat().st_size for p in files),allocated_disk_bytes=sum(p.stat().st_blocks*512 for p in files))),flush=True)



def p01_public_budget_continuation_case():
    """Controller-only retained4GiB public P01-06; never default discovery.

    One bounded verified copy, then two public pages. No new large material,
    private budget replacement, cleanup or full-blob rehash outside the copy.
    """
    import hashlib,os,resource,stat,time
    assert Path(tempfile.gettempdir()).resolve()==Path('/tmp/tests')
    source=Path('/retained');root=Path('/tmp/tests/p01-public-budget')
    raw_manifest=Path('/input/retained-manifest.json').read_bytes()
    assert sha(raw_manifest)=='b3f9cbf8bfe9ab15c06088e384b2d90a3bfd920d110079e5f7bef765ffd14aa8'
    retained=json.loads(raw_manifest);prefix='exact/p01-exact-4gib/native/'
    expected={name[len(prefix):]:row for name,row in retained['files'].items() if name.startswith(prefix)}
    assert expected and all(name and not Path(name).is_absolute() and '..' not in Path(name).parts for name in expected)
    directories={'.'}
    for name in expected:
        directories.update(str(parent) for parent in Path(name).parents)
    def attributes(info):
        return dict(device=info.st_dev,inode=info.st_ino,mode=info.st_mode,nlink=info.st_nlink,
            bytes=info.st_size,mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)
    def inventory():
        found={};dirs={}
        for directory,children,files in os.walk(source,followlinks=False):
            directory=Path(directory);info=directory.lstat()
            assert stat.S_ISDIR(info.st_mode) and not directory.is_symlink()
            dirs[str(directory.relative_to(source))]=attributes(info)
            for name in children:
                child=directory/name;info=child.lstat()
                assert stat.S_ISDIR(info.st_mode) and not child.is_symlink()
            for name in files:
                child=directory/name;info=child.lstat()
                assert stat.S_ISREG(info.st_mode) and info.st_nlink==1
                found[str(child.relative_to(source))]=attributes(info)
        assert set(found)==set(expected) and set(dirs)==directories
        return found,dirs
    original_files,original_dirs=inventory();root.mkdir(exist_ok=False);copy_root=root/'native';copy_root.mkdir()
    started=time.monotonic();status='FAIL';metrics={'copy':{},'retained_manifest_sha256':sha(raw_manifest)}
    large='blobs/1952054362df0716ce6d9f21909766507afdaadca706729907290beb04604384';size=4*1024**3
    try:
        for name,row in sorted(expected.items()):
            source_file=source/name;destination=copy_root/name;destination.parent.mkdir(parents=True,exist_ok=True)
            before=source_file.lstat();assert attributes(before)==original_files[name]
            assert before.st_size==row['bytes'] and oct(stat.S_IMODE(before.st_mode))==row['mode']
            digest=hashlib.sha256();copied=0
            fd=os.open(source_file,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as original:
                assert attributes(os.fstat(original.fileno()))==attributes(before)
                outfd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,stat.S_IMODE(before.st_mode))
                with os.fdopen(outfd,'wb') as output:
                    while chunk:=original.read(65536):
                        copied+=len(chunk);assert copied<=row['bytes']
                        digest.update(chunk);assert output.write(chunk)==len(chunk)
                    output.flush();os.fsync(output.fileno())
                assert attributes(os.fstat(original.fileno()))==attributes(before)
            after=source_file.lstat();assert attributes(after)==attributes(before)
            assert copied==row['bytes'] and digest.hexdigest()==row['sha256']
            copied_stat=destination.lstat()
            assert stat.S_ISREG(copied_stat.st_mode) and copied_stat.st_nlink==1 and copied_stat.st_size==copied
            assert stat.S_IMODE(copied_stat.st_mode)==stat.S_IMODE(before.st_mode)
            metrics['copy'][name]=dict(bytes=copied,sha256=digest.hexdigest(),before=attributes(before),
                after=attributes(after),copied_stat=attributes(copied_stat))
        assert inventory()==(original_files,original_dirs)
        store=Store(copy_root);initial=store.read_snapshot();original_head=store._head()
        digest=expected[large]['sha256'];native=initial['sources']['SO-exact-4gib']
        assert initial['synthetic_test_only'] is True and not initial['records']
        assert set(initial['sources'])=={'SO-exact-4gib'} and native['bytes']==size and native['blob_hash']==digest
        assert native['coverage']=='FULL_DOCUMENT' and all(e['schema']=='pmrs.commit/4.2.2' for _,e in store.history())
        small=b'after budget needle';add_source(store,small,'SO-zz-after-budget')
        state=Store(copy_root).read_snapshot();head=store._head()
        assert head!=original_head and state['sources']['SO-exact-4gib']==native
        assert sorted(state['sources'])==['SO-exact-4gib','SO-zz-after-budget'] and not state['records']
        assert not state.get('fast_revisions') and not state.get('research_routes')
        assert state['sources']['SO-zz-after-budget']['blob_hash']==sha(small)
        def metadata():
            result={}
            for path in sorted(copy_root.rglob('*')):
                if path.is_dir():continue
                info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_nlink==1
                name=str(path.relative_to(copy_root));row=attributes(info)
                if name!=large:
                    assert info.st_size<8*1024**2
                    row['sha256']=sha(path.read_bytes())
                result[name]=row
            return result
        before=metadata();first=Q.web_tool(Store(copy_root),'search',{'q':['needle']})
        assert first['as_of_commit']==head['commit'] and first['scan_reference_budget']==64 and first['scan_byte_budget']==size
        assert first['body_bytes_read_this_call']==size and first['body_attempts_this_call']==2
        assert first['integrity_probe_attempts_this_call']==1 and first['integrity_probe_bytes_this_call']==0
        assert [hit['ref'] for hit in first['results']]==['SO-exact-4gib']
        assert first['results'][0]['body_sha256']==digest
        assert first['results'][0]['locator']==dict(blob_hash=digest,unit='UTF8_BYTE',start=size-6,end=size,quoted_sha256=sha(b'needle'))
        assert first['scanned_ranges_this_call']==[dict(ref='SO-exact-4gib',blob_hash=digest,unit='UTF8_BYTE',start=0,end=size)]
        assert first['categories']==dict(unsupported=[],corrupt=[],limited=['SO-zz-after-budget'],partial_material_excluded=[])
        assert first['start_position']==0 and first['next_position']==1 and first['has_more_after_position']
        assert first['not_scanned_by_this_call']==dict(before=[0,0],after=[1,2]) and not first['complete_for_this_call_scope']
        cursor=json.loads(base64.urlsafe_b64decode(first['continuation'][3:]));assert cursor['position']==1
        assert store._head()==head and metadata()==before
        second=Q.web_tool(Store(copy_root),'search',{'q':['needle'],'continuation':[first['continuation']]})
        assert all(second[key]==first[key] for key in ('as_of_commit','query_digest','scope_digest','exposure_digest'))
        assert [hit['ref'] for hit in second['results']]==['SO-zz-after-budget']
        hit=second['results'][0];assert hit['body_sha256']==sha(small) and 'needle' in hit['excerpt']
        assert hit['locator']==dict(blob_hash=sha(small),unit='UTF8_BYTE',start=small.index(b'needle'),end=len(small),quoted_sha256=sha(b'needle'))
        assert second['body_bytes_read_this_call']==len(small) and second['body_attempts_this_call']==1
        assert second['integrity_probe_attempts_this_call']==1 and second['integrity_probe_bytes_this_call']==0
        assert second['scanned_ranges_this_call']==[dict(ref='SO-zz-after-budget',blob_hash=sha(small),unit='UTF8_BYTE',start=0,end=len(small))]
        assert second['start_position']==1 and second['next_position']==2 and second['continuation'] is None
        assert not second['has_more_after_position'] and not second['complete_for_this_call_scope']
        assert second['not_scanned_by_this_call']==dict(before=[0,1],after=[2,2]) and not any(second['categories'].values())
        assert store._head()==head and metadata()==before and inventory()==(original_files,original_dirs)
        metrics.update(original_head=original_head,pinned_head=head,first_page=first,second_page=second,
            copied_metadata_sha256=sha(canonical(before)),candidate_refs=sorted(state['sources']))
        status='PUBLIC_BODY_BUDGET_CONTINUATION_ASSERTIONS_PASSED'
    finally:
        files=[p for p in root.rglob('*') if p.is_file()]
        print('DEV11_P01_EXTREME '+json.dumps(dict(case='PUBLIC_BUDGET',status=status,project=str(copy_root),retained=True,
            metrics=metrics,elapsed_seconds=time.monotonic()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            logical_disk_bytes=sum(p.stat().st_size for p in files),allocated_disk_bytes=sum(p.stat().st_blocks*512 for p in files))),flush=True)
