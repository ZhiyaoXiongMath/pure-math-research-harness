"""Bounded native metadata reuse: no models, no real research, no large stress load.

The body-size tiers are measured separately. Here exact read/copy counts cover
100 same-scope operations, 10 native revisions, and 50 read-only refreshes.
"""
from copy import deepcopy
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from research_studio import changes, demo, report_catalog, reports, survey
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor
from research_studio.util import canonical, identity, loads
from research_studio.knowledge import locator
from research_studio.workspace import Workspace
from tests.test_survey import ready_survey


class SurveyResources(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_res_t01_one_hundred_operations_reuse_content_and_keep_receipts(self):
        store,iid,e=ready_survey(self.root/'project',None)
        s=store.read_snapshot();digest=s['sources'][e['source_ref']]['blob_hash']
        original=(store.root/'blobs'/digest).stat()
        before_events=len(s['survey_events']);before_requests=len(s['requests'])
        result_refs=[]
        with patch('research_studio.survey.now',return_value='2099-01-01T00:00:00+00:00'):
            for _ in range(100):result_refs.append(survey.freeze_knowledge(store,iid)['snapshot_ref'])
        after=store.read_snapshot()
        self.assertEqual(set(result_refs),{e['snapshot_ref']})
        self.assertEqual(len(after['survey_snapshots']),1)
        self.assertEqual(len(after['survey_events'])-before_events,100)
        self.assertEqual(len(after['requests']),before_requests)
        self.assertEqual((store.root/'blobs'/digest).stat().st_ino,original.st_ino)
        self.assertEqual(len(list(store.root.rglob(digest))),1)
        # A replay of the exact operation retains the original receipt identity.
        event=deepcopy(max(after['survey_events'].values(),key=lambda row:row['accepted_sequence']))
        event.pop('accepted_sequence');head=store._head();store.commit_survey(event)
        self.assertEqual(store._head(),head)
        # Runtime and presentation data cannot enter mathematical content identity.
        runtime=deepcopy(after);runtime['ui_locale']='zh-CN';runtime['_snapshot_sequence']+=1000
        runtime['requests']['unused-counter']={'execution_state':'SENT','instance_id':'unrelated'}
        self.assertEqual(survey._snapshot(runtime,iid,None,runtime['instances'][iid]['survey_scope']['questions'])['id'],e['snapshot_ref'])

    def test_res_t02_ten_native_revisions_preserve_originals_and_old_records(self):
        store,iid,e=ready_survey(self.root/'project');s=store.read_snapshot()
        frozen_scope=survey.report_scope(s,iid,e['plan_ref'])
        original_ref=next(r for r in e['selected_refs'] if s['records'][r]['kind']=='Context')
        object_id=next(oid for oid,obj in s['objects'].items() if obj['selected_revision']==original_ref)
        digest=s['sources'][e['source_ref']]['blob_hash'];original=(store.root/'blobs'/digest).stat()
        baseline_scope=survey.demo_scope();baseline_scope.update(entry='EXISTING_KNOWLEDGE',selected_refs=[original_ref])
        other=Engine().new_workflow(store,'SURVEY',survey_scope=baseline_scope)['instance_id']
        # An unrelated empty selection's mathematical fingerprint is stable.
        unrelated=survey.scope_fingerprint(store.read_snapshot(),other,[])
        versions=[original_ref]
        for number in range(10):
            parent=store.read_snapshot()['objects'][object_id]['selected_revision']
            survey.start_activity(store,iid,'S3','Explicit synthetic context revision '+str(number),max_calls=1,policy=demo.policy())
            def revised(task,state):
                response=loads(survey.demo_response(task,state));kcs=response['payload']['knowledge_change']
                body='Let q be a complex number and n an integer with n >= 1. Only finite sums are considered. Synthetic explanatory revision '+str(number)+'.'
                row={'kind':'Context','context_refs':[],'body':body,'data':{'definitions':[{'key':'finite_sum','locator':locator(body)}],
                    'objects':[],'assumptions':[],'quantifiers':[],'conventions':[],'parent_context_refs':[]}}
                kcs['operations']=[{'op':'REVISE','local_key':'context','object_id':object_id,'expected_parent':parent,'new_record':row}]
                chosen=[r for r in task['survey_context']['selected_refs'] if r!=parent]+['local:context']
                prior=survey._coverage_for(state,iid,task['survey_context']['selected_refs'])
                response['payload']['data']={'selected_refs':chosen,'coverage':prior,'dependencies':[]}
                for effect in kcs['obligation_effects']:effect['evidence_refs']=['local:context']
                return canonical(response)
            Engine().run_round(store,iid,executor=FakeExecutor(revised),max_tasks=1)
            version=store.read_snapshot()['objects'][object_id]['selected_revision'];self.assertNotEqual(parent,version);versions.append(version)
            survey.freeze_knowledge(store,iid)
        final=store.read_snapshot()
        self.assertEqual(final['objects'][object_id]['revisions'],versions)
        for ref in versions:self.assertEqual(store.read_record(ref),final['records'][ref])
        self.assertFalse(survey.report_current(final,frozen_scope))
        self.assertEqual(survey.scope_fingerprint(final,other,[]),unrelated)
        self.assertEqual((store.root/'blobs'/digest).stat().st_ino,original.st_ino)
        self.assertEqual(len(list(store.root.rglob(digest))),1)

    def test_res_t03_fifty_refreshes_reuse_integrity_and_detect_real_changes(self):
        workspace=Workspace(self.root/'workspace');key='WP-'+identity('resource-refresh')[:32]
        store,iid,e=ready_survey(workspace.root/'projects'/key)
        survey.start_activity(store,iid,'S5','Explicit report budget for synthetic refresh checks',max_calls=3,policy=demo.policy())
        rid=reports.create(store,iid);s=store.read_snapshot();entry=s['reports'][rid]
        workspace.progress(key,iid);head=store._head();files={str(p.relative_to(store.root)) for p in store.root.rglob('*') if p.is_file()}
        with patch('research_studio.resources.hash_file',wraps=__import__('research_studio.resources',fromlist=['hash_file']).hash_file) as hashes, \
             patch('research_studio.survey._dependency_closure',wraps=survey._dependency_closure) as closure:
            for n in range(50):
                workspace.set_preferences('en' if n%2 else 'zh-CN')
                view=workspace.progress(key,iid)
                self.assertEqual(view['reports'][0]['classification'],'RECOVERABLE_ACTIVE_CANDIDATE')
            self.assertEqual(hashes.call_count,0);self.assertEqual(closure.call_count,0)
            # Critical use retains an unconditional full original-material check.
            report_catalog.classify(store,s,entry)
            self.assertGreater(hashes.call_count,0)
        self.assertEqual(store._head(),head)
        self.assertEqual({str(p.relative_to(store.root)) for p in store.root.rglob('*') if p.is_file()},files)
        unrelated=store.commit(changes.prepare_material_input(store.read_snapshot(),b'Unrelated material.','Unrelated','text/plain',blob_get=store.read_blob))
        survey.mark_source(store,iid,unrelated['source_ref'],withdrawn=True,reason='Unrelated source status change.')
        self.assertEqual(workspace.progress(key,iid)['reports'][0]['classification'],'RECOVERABLE_ACTIVE_CANDIDATE')
        survey.mark_source(store,iid,e['source_ref'],version_conflict=True,reason='Consumed source version conflict.')
        self.assertEqual(workspace.progress(key,iid)['reports'][0]['classification'],'STALE_CANDIDATE')
        digest=s['sources'][e['source_ref']]['blob_hash'];path=store.root/'blobs'/digest;info=path.stat()
        raw=path.read_bytes();path.write_bytes(b'X'+raw[1:]);os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
        self.assertEqual(workspace.progress(key,iid)['reports'][0]['classification'],'DAMAGED_ACTIVE_ARTIFACT')

    def test_res_t04_three_plans_share_one_knowledge_snapshot(self):
        store,iid,e=ready_survey(self.root/'project',None)
        plans=[survey.create_output_plan(store,iid,e['snapshot_ref'],profile)['plan_ref'] for profile in survey.PROFILES]
        snapshot=store.read_snapshot();self.assertEqual(len(set(plans)),3)
        self.assertEqual({snapshot['survey_output_plans'][p]['snapshot_ref'] for p in plans},{e['snapshot_ref']})
        self.assertEqual(len(snapshot['survey_snapshots']),1)
        digest=snapshot['sources'][e['source_ref']]['blob_hash']
        self.assertEqual(len(list(store.root.rglob(digest))),1)


if __name__=='__main__':unittest.main()
