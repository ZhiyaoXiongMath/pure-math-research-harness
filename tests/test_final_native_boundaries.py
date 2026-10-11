"""Current product boundaries and native journal history, using generated inputs only."""
from copy import deepcopy
from pathlib import Path
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from research_studio import changes, demo, reports, views, workflow_instances as W, setup, desktop
from research_studio.engine import Engine
from research_studio.store import Store, _native_only
from research_studio.util import PMRSError, canonical

ROOT=Path(__file__).resolve().parents[1]


class NativeVersionBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_removed_cli_commands_fail_before_creating_destination(self):
        for command in ('upgrade','continuation'):
            destination=self.root/command
            result=subprocess.run([sys.executable,'-B','-m','research_studio','project',command,str(self.root/'input.zip'),'--out',str(destination)],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('invalid choice',result.stderr)
            self.assertFalse(destination.exists())

    def test_imported_authority_is_rejected_and_source_input_cannot_write_it(self):
        store=Store.create(self.root/'project','Native only',synthetic=True);state=store.read_snapshot()
        for key,value in [('imports',{'old':{}}),('legacy_artifacts',{'LA':{}}),('migration',{'old':True}),
                          ('historical_usage',{'model_calls':1}),('qualifications',{'Q':{'evidence_origin':'LEGACY_ASSERTION'}}),
                          ('reports',{'R':{'historical_only':True}})]:
            bad=deepcopy(state);bad[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(PMRSError,'UNSUPPORTED_PROJECT_DATA'):_native_only(bad)
        self.assertFalse(hasattr(changes,'prepare_import'))
        proposal=changes.prepare_source_input(state,'中文原始问题保持原文。'.encode(),blob_get=store.read_blob)
        proposal['imports']={'foreign':{}}
        receipt=store.commit(proposal)  # Regenerated from the original input; extra fields carry no authority.
        after=store.read_snapshot();self.assertNotIn('imports',after)
        self.assertEqual(store.read_blob(after['sources'][receipt['source_ref']]['blob_hash']),'中文原始问题保持原文。'.encode())
        self.assertFalse(after['qualifications']);self.assertFalse(after['requests'])

    def test_default_workspace_and_dependency_paths_are_major_version_isolated(self):
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data'),'XDG_CONFIG_HOME':str(self.root/'config')},clear=False):
            self.assertEqual(desktop.default_workspace(),self.root/'data/pure-math-research-studio/4.0/workspace')
            self.assertEqual(setup.config_root(),self.root/'config/pure-math-research-studio/4.0')
            self.assertEqual(setup.data_root(),self.root/'data/pure-math-research-studio/4.0/dependencies')
            self.assertFalse((self.root/'data').exists());self.assertFalse((self.root/'config').exists())

    def test_native_history_is_commit_pinned_paginated_read_only_and_instance_scoped(self):
        e=Engine();store=e.create(self.root/'history',demo.ARITHMETIC,synthetic=True)
        target=next(iter(store.read_snapshot()['records']))
        first=e.new_workflow(store,'TRH',target_ref=target,name='First exact target')['instance_id']
        second=e.new_workflow(store,'TRH',target_ref=target,name='Second exact target')['instance_id']
        report1=reports.create(store,first);old=store.read_snapshot();report2=reports.create(store,second)
        store.commit_control(W.event(store.read_snapshot(),'PAUSE',{'reason':'Second workflow pause'},instance_id=second))
        current=store.read_snapshot();before={p.relative_to(store.root):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        for iid,rid,other in ((first,report1,report2),(second,report2,report1)):
            rows=[];offset=0
            while True:
                page=views.history(current,store,instance_id=iid,offset=offset,limit=2);rows+=page['records']
                if page['next_offset'] is None:break
                offset=page['next_offset']
            self.assertEqual(len(rows),len({row['event_id'] for row in rows}))
            self.assertTrue(all(not row['instance_ids'] or iid in row['instance_ids'] for row in rows))
            body=canonical(rows);self.assertIn(rid.encode(),body);self.assertNotIn(other.encode(),body)
        pinned=views.history(old,store,limit=100)
        self.assertEqual(pinned['commit'],old['knowledge_commit']);self.assertNotIn(report2.encode(),canonical(pinned))
        self.assertEqual(views.history(current,store,query='Second workflow pause',limit=100)['total'],1)
        self.assertEqual(before,{p.relative_to(store.root):p.read_bytes() for p in store.root.rglob('*') if p.is_file()})
        self.assertFalse(store.read_snapshot()['requests']);self.assertEqual(store.read_snapshot()['usage']['model_calls'],0)

    def test_removed_http_routes_and_foreign_upload_do_not_create_receipts_or_projects(self):
        from tests.test_final_surface import WebApplicationTests as _HttpFixture
        http=_HttpFixture();http.setUp();self.addCleanup(http.tearDown)
        before=http.w.list()
        for path in ('/api/legacy','/api/legacy-body'):
            status,body,_=http.req('GET',path)
            self.assertEqual(status,404,body);self.assertEqual(body['error'],'ROUTE_NOT_FOUND')
        for action in ('upgrade','migration-check','continuation'):
            status,body,_=http.req('POST','/api/action/'+action,{},key='removed-'+action+'-123456789')
            self.assertEqual(body['error'],'ACTION_UNKNOWN');self.assertNotEqual(status,200)
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('notes.md','Generated non-native document')
        payload={'name':'non-native.zip','data':base64.b64encode(stream.getvalue()).decode(),'mode':'restore'}
        for n,raw in enumerate((stream.getvalue(),b'not a zip',b'PK\x03\x04broken')):
            payload['data']=base64.b64encode(raw).decode()
            status,body,_=http.req('POST','/api/action/upload-archive',payload,key='invalid-native-upload-123456789-'+str(n))
            self.assertEqual(body['error'],'NATIVE_BACKUP_REQUIRED');self.assertNotEqual(status,200)
        self.assertEqual(http.w.list()['projects'],before['projects'])
        self.assertFalse(list((http.w.root/'uploads').glob('*')))
        # An explicit rejected current action may retain its failure receipt;
        # removed action names never become replayable operations.
        operations=http.w.operations()['operations']
        self.assertTrue(all(row['name']=='upload-archive' for row in operations))

    def test_handoff_history_keeps_source_visits_private_and_adoption_visible_to_both_instances(self):
        e=Engine();store=e.create(self.root/'handoff-history',demo.scenario('FDH').encode(),phenomenon=True,synthetic=True)
        source=e.new_workflow(store,'FDH',discovery_scope=demo.discovery_scope('Discover exact candidates within this user scope.'))['instance_id']
        e.start_round(store,source,'Keep the background fixed.',max_calls=5,policy=demo.policy())
        fake=demo.executor();e.run_round(store,source,executor=fake)
        initial=store.read_snapshot();self.assertEqual(fake.calls,2)
        self.assertEqual(fake.network_calls+fake.spawn_calls,0)
        candidate=next(iter(initial['candidates'].values()))['statement_ref']
        prepared=e.prepare_handoff(store,source,'FDH_TO_TRH',{'candidate_refs':[candidate]})
        decision=e.decide(store,source,'ADOPT','Study this exact candidate in a separate workflow.',snapshot_commit=store.read_snapshot()['knowledge_commit'],candidate_ref=candidate)
        before_adoption=store.read_snapshot()
        target=e.adopt_handoff(store,prepared['handoff_id'],decision)['instance_id']
        current=store.read_snapshot();head=current['knowledge_commit']
        original={p.relative_to(store.root):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        def rows(snapshot,iid):
            result=[];offset=0
            while True:
                page=views.history(snapshot,store,instance_id=iid,offset=offset,limit=5);result.extend(page['records'])
                if page['next_offset'] is None:return result
                offset=page['next_offset']
        source_rows=rows(current,source);target_rows=rows(current,target)
        source_work=[r for r in source_rows if r['event_type'] in {'VISIT_OPENED','VISIT_DISPOSED','AUTHORIZE_MISSION','PREPARE','CAPTURE','KNOWLEDGE_CHANGE_ACCEPTED'}]
        self.assertTrue(any(r['event_type']=='VISIT_DISPOSED' for r in source_work))
        self.assertTrue(any(r['event_type']=='AUTHORIZE_MISSION' for r in source_work))
        self.assertTrue(all(r['instance_ids']==[source] for r in source_work))
        self.assertFalse({r['event_id'] for r in source_work}&{r['event_id'] for r in target_rows})
        for collection in (source_rows,target_rows):
            adopted=[r for r in collection if r['event_type']=='HANDOFF_ADOPTED']
            self.assertEqual(len(adopted),1);self.assertEqual(set(adopted[0]['instance_ids']),{source,target})
        # Later adoption cannot retroactively change the prepared/decision event's participants.
        for row in source_rows:
            if row['event_type'] in {'HANDOFF_PREPARED','HUMAN_DECISION'}:self.assertEqual(row['instance_ids'],[source])
        pinned=rows(before_adoption,source)
        self.assertFalse(any(r['event_type']=='HANDOFF_ADOPTED' for r in pinned))
        self.assertTrue(all(target not in r['instance_ids'] for r in pinned))
        self.assertEqual(current['instances'][target]['status'],'PAUSED')
        self.assertEqual(current['instances'][target]['target_ref'],candidate)
        self.assertEqual(current['instances'][target]['mission_ids'],[])
        self.assertEqual(store.read_snapshot()['knowledge_commit'],head)
        self.assertEqual(original,{p.relative_to(store.root):p.read_bytes() for p in store.root.rglob('*') if p.is_file()})
        self.assertEqual(len(current['requests']),2);self.assertEqual(current['usage']['model_calls'],0)
