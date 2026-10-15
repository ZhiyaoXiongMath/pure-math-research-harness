from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest

from pmrh.adapters.storage.repositories import EventRepository
from pmrh.ports.dto import core as C, enums as E, storage as T
from . import fixtures as F


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store,self.iid,self.disk,self.policy,self.uow = F.project(self.root/'p')
        self.boundary = self.disk.current_boundary()

    def payload(self, batch):
        path = self.root/'operation.json'
        path.write_text(json.dumps({'boundary':self.boundary.to_wire(),'batch':batch.to_wire()}))
        return path

    def test_five_fault_boundaries_and_actual_process_reopen(self):
        for point in ('after_blobs','after_records','after_commit','before_head','after_head'):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as tmp:
                store,iid,disk,policy,uow = F.project(Path(tmp)/'p')
                boundary = disk.current_boundary(); batch = F.batch(boundary)
                payload = Path(tmp)/'operation.json'
                payload.write_text(json.dumps({'boundary':boundary.to_wire(),'batch':batch.to_wire()}))
                head = (store.root/'HEAD').read_bytes()
                child = F.child('crash', store.root, iid, payload, point)
                self.assertEqual(child.returncode,73,child.stderr)
                reopened = F.Store(store.root); state = reopened.read_snapshot()
                self.assertTrue(reopened.audit()['valid'])
                self.assertEqual((store.root/'HEAD').read_bytes()==head, point!='after_head')
                files = {p.name:p.read_bytes() for p in (store.root/'blobs').iterdir()}
                retry = F.child('retry',store.root,iid,payload)
                self.assertEqual(retry.returncode,0,retry.stderr)
                receipt = T.CommitReceipt.from_json(retry.stdout.strip())
                self.assertEqual(receipt.duplicate_status, E.DuplicateStatus.EXACT_DUPLICATE if point=='after_head' else E.DuplicateStatus.NEW)
                self.assertTrue(all((store.root/'blobs'/name).read_bytes()==raw for name,raw in files.items()))
                second = F.child('retry',store.root,iid,payload)
                self.assertEqual(second.returncode,0,second.stderr)
                duplicate = T.CommitReceipt.from_json(second.stdout.strip())
                self.assertEqual(duplicate,replace(receipt,duplicate_status=E.DuplicateStatus.EXACT_DUPLICATE))

    def test_changed_persistent_expectation_and_content_rejected(self):
        batch = F.batch(self.boundary,count=2)
        receipt = F.commit(self.uow,self.policy,self.boundary,batch)
        for altered, boundary in [(F.batch(self.boundary,count=2,data=b'Changed'),self.boundary),
                                  (replace(batch,operation_id='operation:changed'),self.boundary),
                                  (replace(batch,events=tuple(reversed(batch.events))),self.boundary),
                                  (batch,receipt.boundary),
                                  (replace(batch,evidence=(replace(batch.evidence[0],evidence_ref=replace(batch.evidence[0].evidence_ref,revision='2')),)),self.boundary)]:
            disk,policy,uow = F.assemble(F.Store(self.store.root),self.iid)
            result = F.commit(uow,policy,boundary,altered)
            self.assertIsInstance(result,C.ErrorEnvelope); self.assertEqual(result.code,E.ErrorCode.IDEMPOTENCY_CONFLICT)
        disk,policy,uow = F.assemble(F.Store(self.store.root),self.iid)
        duplicate = F.commit(uow,policy,self.boundary,batch)
        self.assertEqual(duplicate,replace(receipt,duplicate_status=E.DuplicateStatus.EXACT_DUPLICATE))
        # Same project key in another scope is a conflict, never a receipt leak.
        iid2 = F.Engine().new_workflow(self.store,'TRH',target_ref=next(iter(self.store.read_snapshot()['records'])))['instance_id']
        disk2,policy2,uow2 = F.assemble(self.store,iid2,install=True)
        other = F.batch(disk2.current_boundary(),count=2)
        result = F.commit(uow2,policy2,disk2.current_boundary(),other)
        self.assertEqual(result.code,E.ErrorCode.IDEMPOTENCY_CONFLICT)

    def test_physical_cas_and_two_process_writer_competition(self):
        payload = self.payload(F.batch(self.boundary))
        children=[]
        for n in range(2):
            # Distinct keys, same physical expectation; only one may publish.
            value=F.batch(self.boundary,str(n)); p=self.root/('op'+str(n)+'.json')
            p.write_text(json.dumps({'boundary':self.boundary.to_wire(),'batch':value.to_wire()}))
            children.append(F.child('compete',self.store.root,self.iid,p,self.root/('ready'+str(n)),self.root/'go',wait=False))
        end=time.monotonic()+10
        while not all((self.root/('ready'+str(n))).exists() for n in range(2)):
            self.assertLess(time.monotonic(),end); time.sleep(.01)
        (self.root/'go').write_text('go')
        outputs=[]
        for child in children:
            out,err=child.communicate(timeout=15); self.assertEqual(child.returncode,0,err);outputs.append(json.loads(out))
        self.assertEqual(sorted(x['dto_type'] for x in outputs),['CommitReceipt','ErrorEnvelope'])
        self.assertEqual(next(x for x in outputs if x['dto_type']=='ErrorEnvelope')['code'],'VERSION_CONFLICT')
        self.assertEqual(self.disk.current_boundary().through_journal_sequence,1)

    def test_shared_lock_blocks_other_process_until_release(self):
        acquired=self.root/'acquired';release=self.root/'release'
        child=F.child('lock',self.store.root,acquired,release,wait=False)
        end=time.monotonic()+10
        while not acquired.exists():self.assertLess(time.monotonic(),end);time.sleep(.01)
        import fcntl,os
        fd=os.open(self.store.root/'.runtime/writer.lock',os.O_RDONLY)
        try:
            with self.assertRaises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            release.write_text('release');out,err=child.communicate(timeout=10);self.assertEqual(child.returncode,0,err)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(fd)

    def test_fixed_pages_mixed_instances_checkpoints_and_true_gap(self):
        from unittest.mock import patch
        first=F.batch(self.boundary,'first',count=2)
        receipt=F.commit(self.uow,self.policy,self.boundary,first)
        events=EventRepository(self.disk)
        page=events.read_events(F.cursor(receipt.boundary),receipt.boundary,limit=1)
        iid2=F.Engine().new_workflow(self.store,'TRH',target_ref=next(iter(self.store.read_snapshot()['records'])))['instance_id']
        disk2,policy2,uow2=F.assemble(self.store,iid2,install=True)
        F.commit(uow2,policy2,disk2.current_boundary(),F.batch(disk2.current_boundary(),'other'))
        with patch('research_studio.store.CHECKPOINT_INTERVAL',1):
            F.Engine().pause(self.store,self.iid,'Another native pause')
        current=self.disk.current_boundary()
        last=F.commit(self.uow,self.policy,current,F.batch(current,'last'))
        historical=events.read_events(page.next_cursor,receipt.boundary)
        self.assertEqual([e.event_id for e in historical.events],[first.events[1].event_id])
        all_events=events.read_events(F.cursor(last.boundary),last.boundary)
        self.assertEqual([e.journal_sequence for e in all_events.events],[1,2,3])
        self.assertEqual([e.aggregate_sequence for e in all_events.events],[1,2,3])
        wrong=replace(page.next_cursor,last_event_id='wrong')
        self.assertEqual(events.read_events(wrong,receipt.boundary).code,E.ErrorCode.INVALID_CURSOR)
        missing=F.F.envelope_ref(self.boundary.scope,first.events[1])
        (self.store.root/'blobs'/missing.sha256).unlink()
        gap=events.read_events(page.next_cursor,receipt.boundary)
        self.assertEqual(gap.status,E.PageStatus.GAP)
        self.assertEqual((gap.gap.first_missing_sequence,gap.gap.last_missing_sequence),(2,2))
        self.assertEqual(gap.next_cursor,page.next_cursor)
        # A missing manifest is unindexable, not a fabricated gap.
        entry=self.store._commit_record(self.store._head())
        manifest=next(e['manifest_sha256'] for e in entry['events'] if e.get('type')==F.F.BATCH)
        (self.store.root/'blobs'/manifest).unlink()
        self.assertIsInstance(events.read_events(F.cursor(last.boundary),last.boundary),C.ErrorEnvelope)
