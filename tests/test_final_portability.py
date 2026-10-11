"""Current-format backup integrity and recovery; all fixtures are generated locally."""
from pathlib import Path
import ast
import io
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from research_studio.archive import inventory
from research_studio.portability import export_project, restore
from research_studio.store import Store
from research_studio.util import PMRSError

class NativePortabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_native_backup_preserves_actual_capture_budget_and_resumes_without_resend(self):
        from tests.test_final_workflows import RuntimeIntegration
        from research_studio import scheduler,execution,workflow_instances as W
        from research_studio.runner import FakeExecutor,SimulatedCrash
        store,policy=RuntimeIntegration().make_project(self.root/'captured',n=2)
        prepared=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),['I']),policy=policy)['prepared'][0]
        fake=FakeExecutor(RuntimeIntegration.no_result,fault_at='AFTER_CAPTURE_RECEIPT_BEFORE_ADMISSION')
        with self.assertRaises(SimulatedCrash):fake.execute(store,prepared['task_id'])
        before=store.read_snapshot();rid=prepared['request_id'];capture=before['requests'][rid]['capture_ref']
        export_project(store,self.root/'native-backup.zip');restore(self.root/'native-backup.zip',self.root/'restored')
        restored=Store(self.root/'restored');after=restored.read_snapshot()
        self.assertEqual(after['budget_grants'],before['budget_grants']);self.assertEqual(after['usage'],before['usage'])
        self.assertEqual(after['requests'][rid]['capture_ref'],capture)
        self.assertEqual(restored.read_blob(capture),store.read_blob(capture));self.assertEqual(after['instances']['I']['status'],'PAUSED')
        with self.assertRaisesRegex(PMRSError,'TASK_FENCED'):execution.recover(restored,rid)
        restored.commit_control(W.decide_event(restored.read_snapshot(),'I','CONTINUE','Resume saved authorized response'))
        with patch('subprocess.Popen',side_effect=AssertionError('second provider call')):
            self.assertEqual(execution.recover(restored,rid)['state'],'ACCEPTED')
        self.assertEqual(fake.calls,1);self.assertEqual(restored.read_snapshot()['usage']['model_calls'],0)
        self.assertTrue(restored.audit()['valid'])


    def test_backup_interruption_before_publication_keeps_authority_and_no_partial_archive(self):
        store=Store.create(self.root/'backup-fault-project','Original project')
        before={p.relative_to(store.root).as_posix():p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        destination=self.root/'interrupted-backup.zip'
        with patch('research_studio.portability.os.link',side_effect=OSError('publication interrupted')):
            with self.assertRaisesRegex(OSError,'publication interrupted'):export_project(store,destination)
        self.assertFalse(destination.exists());self.assertFalse(list(self.root.glob('.native-backup-incomplete-*')))
        after={p.relative_to(store.root).as_posix():p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after);self.assertTrue(store.audit()['valid'])
        export_project(store,destination);restore(destination,self.root/'after-interruption')
        self.assertTrue(Store(self.root/'after-interruption').audit()['valid'])


    def test_archive_paths_case_unicode_aliases_and_symlinks_fail_closed(self):
        for paths in (['../escape'], ['a.md', 'A.md'], ['x/./y'], ['/root'], ['é', 'e\u0301']):
            z = self.root / 'bad.zip'
            with zipfile.ZipFile(z, 'w') as archive:
                for p in paths: archive.writestr(p, b'x')
            with self.assertRaises(PMRSError): inventory(z)
        d = self.root / 'd'; d.mkdir(); (d / 'bad').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(PMRSError, 'IMPORT_SYMLINK'): inventory(d)


    def test_native_schema_and_destination_boundaries(self):
        store=Store.create(self.root/'native','Native boundary')
        alias=Store(store.root.parent/'native'/'..'/'native')
        with self.assertRaisesRegex(PMRSError,'EXPORT_DESTINATION'):export_project(alias,store.root/'forbidden.zip')
        self.assertFalse((store.root/'forbidden.zip').exists())
        (store.root/'project.json').write_text('{"schema":"unrecognized.foreign/project"}')
        with self.assertRaisesRegex(PMRSError,'NATIVE_SCHEMA_REQUIRED'):store.read()

    def test_native_backup_roundtrip_and_foreign_archive_rejection(self):
        from research_studio.engine import Engine
        from research_studio import demo
        e=Engine();store=e.create(self.root/'native-roundtrip',demo.ARITHMETIC,synthetic=True)
        target=next(r for r,v in store.read_snapshot()['records'].items() if v['kind']=='Statement')
        e.new_workflow(store,'TRH',target_ref=target)
        before=store.read_snapshot();archive=self.root/'current.zip';export_project(store,archive)
        restore(archive,self.root/'restored');after=Store(self.root/'restored').read_snapshot()
        for field in ('records','sources','supports','qualifications','requests','budget_grants'):
            self.assertEqual(before[field],after[field])
        self.assertTrue(all(i['status']=='PAUSED' for i in after['instances'].values()))
        with zipfile.ZipFile(self.root/'not-native.zip','w') as z:z.writestr('notes.txt','A reading file is not a backup.')
        with self.assertRaisesRegex(PMRSError,'NATIVE_BACKUP_REQUIRED'):restore(self.root/'not-native.zip',self.root/'invalid')
        self.assertFalse((self.root/'invalid').exists())

    def test_native_distribution_has_no_retired_runtime_or_reader_imports(self):
        root=Path(__file__).resolve().parents[1]
        self.assertFalse((root/'historical').exists());self.assertFalse((root/'research_studio/migration').exists())
        for path in (root/'research_studio').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom):names=[node.module or '',*[n.name for n in node.names]]
                elif isinstance(node,ast.Import):names=[n.name for n in node.names]
                elif isinstance(node,ast.Call) and isinstance(node.func,(ast.Name,ast.Attribute)) and getattr(node.func,'id',getattr(node.func,'attr','')) in {'__import__','import_module'} and node.args and isinstance(node.args[0],ast.Constant):names=[str(node.args[0].value)]
                else:continue
                self.assertFalse(any({'migration','historical'}&set(n.split('.')) for n in names),str(path))

    def test_directory_change_during_inventory_is_detected(self):
        source=self.root/'source';source.mkdir();(source/'original.txt').write_bytes(b'Original bytes')
        original=Path.rglob;calls=[]
        def changing(path,pattern):
            if path==source:
                calls.append(True)
                if len(calls)==2:(source/'concurrent').write_bytes(b'new')
            return original(path,pattern)
        with patch.object(Path,'rglob',changing):
            with self.assertRaisesRegex(PMRSError,'SOURCE_MEMBER_SET_CHANGED'):inventory(source)

    def test_tampered_backup_members_and_rehashed_corrupt_body_never_publish(self):
        import json
        from research_studio import changes
        from research_studio.util import sha
        store=Store.create(self.root/'tamper-native','Exact original')
        receipt=store.commit(changes.prepare_source_input(store.read_snapshot(),b'Original immutable bytes.',blob_get=store.read_blob))
        archive=self.root/'valid.zip';export_project(store,archive)
        with zipfile.ZipFile(archive) as z:members={name:z.read(name) for name in z.namelist()}
        h=store.read_snapshot()['sources'][receipt['source_ref']]['blob_hash'];name='blobs/'+h
        self.assertIn(name,members)
        original={p.relative_to(store.root):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        for rehash in (False,True):
            bad=dict(members);bad[name]=b'Altered mathematical original.'
            if rehash:
                manifest=json.loads(bad['BACKUP-MANIFEST.json']);manifest['files'][name]={'sha256':sha(bad[name]),'bytes':len(bad[name])}
                bad['BACKUP-MANIFEST.json']=json.dumps(manifest).encode()
            path=self.root/('bad-'+str(rehash)+'.zip')
            with zipfile.ZipFile(path,'w') as z:
                for key,value in bad.items():z.writestr(key,value)
            destination=self.root/('must-not-exist-'+str(rehash))
            with self.assertRaises(PMRSError):restore(path,destination)
            self.assertFalse(destination.exists())
        self.assertEqual(original,{p.relative_to(store.root):p.read_bytes() for p in store.root.rglob('*') if p.is_file()})
