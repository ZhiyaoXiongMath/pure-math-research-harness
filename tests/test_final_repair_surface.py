"""Scoped live navigation and browser operation receipts, without model calls."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_studio import activity, demo, execution, views
from research_studio.workspace import Workspace


class RepairSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.w = Workspace(Path(self.tmp.name) / 'workspace')
        self.created = self.w.action('example', {'kind':'TRH','title':'导航与重试','text':demo.ARITHMETIC.decode()}, 'create-repair-1234567890')
        self.key = self.created['project']; self.iid = self.created['instance_id']
        self.store = self.w.project(self.key); self.e = self.w.engine

    def test_lost_response_reload_reuses_native_receipt_and_explicit_new_operation_is_new(self):
        # The server has committed; the browser loses the response. Reload only
        # queries the durable receipt, and a replay preserves every native byte.
        before = self.store.read_snapshot()
        restarted = Workspace(self.w.root)
        result = restarted.operation_status('create-repair-1234567890')
        self.assertEqual(result['state'],'COMPLETED'); self.assertEqual(result['result'],self.created)
        replay = restarted.action('example',{'kind':'TRH','title':'导航与重试','text':demo.ARITHMETIC.decode()},'create-repair-1234567890')
        self.assertEqual(replay,self.created); self.assertEqual(len(restarted.list()['projects']),1)
        self.assertEqual(before,self.store.read_snapshot())
        new = restarted.action('example',{'kind':'TRH','title':'导航与重试','text':demo.ARITHMETIC.decode()},'explicit-new-1234567890')
        self.assertNotEqual(new['project'],self.key); self.assertEqual(len(restarted.list()['projects']),2)
        with patch.object(restarted,'_action',side_effect=AssertionError('GET cannot dispatch')):
            self.assertEqual(restarted.operation_status('never-sent-1234567890')['state'],'NOT_FOUND')
        self.assertEqual(restarted.action('quit',{},'quit-once-1234567890'),{'stopped':True})
        self.assertEqual(Workspace(self.w.root).operation_status('quit-once-1234567890')['state'],'COMPLETED')

    def test_progress_scopes_requests_and_keeps_project_coordinator_separate(self):
        target=self.store.read_snapshot()['instances'][self.iid]['target_ref']
        other=self.e.new_workflow(self.store,'TRH',name='另一个活动实例',target_ref=target)['instance_id']
        self.e.start_round(self.store,other,'Inspect exact target.',max_calls=2,policy=demo.policy())
        task=self.e.prepare(self.store,other)['prepared'][0]
        row=self.store.read_snapshot()['tasks'][task['task_id']]
        self.store.commit_execution(execution.event('RESERVE',{'request_id':task['request_id'],'executor_contract':row['executor_contract'],'model_policy':row['model_policy'],'execution_kind':'SYNTHETIC_TEST_ONLY'}))
        self.w.jobs[(self.key,self.iid)]={'state':'RUNNING','kind':'RESEARCH'}
        quiet=self.w.progress(self.key,self.iid); live=self.w.progress(self.key,other)
        self.assertEqual(quiet['execution']['active_requests'],0); self.assertEqual(quiet['activity']['active_stages'],[])
        self.assertEqual(quiet['project_execution']['running_coordinators'],1)
        self.assertEqual(quiet['project_jobs'][0]['scope'],'PROJECT_COORDINATOR')
        self.assertEqual(live['execution']['active_requests'],1); self.assertEqual(live['activity']['active_stages'],['P4'])
        self.assertEqual(live['workflow']['instances'][0]['display_name'],'另一个活动实例')
        # Once the immutable object preview is cached, polling does not load
        # record bodies or report PDFs, and it cannot change native state.
        before=self.store.read_snapshot()
        bodies={r['body_sha256'] for r in before['records'].values()}
        from research_studio.store import Store
        original=Store.read_blob
        def control_only(store,digest):
            self.assertNotIn(digest,bodies,'No mathematical body reload while polling')
            return original(store,digest)
        with patch.object(Store,'read_blob',control_only):
            self.w.progress(self.key,other)
        self.assertEqual(before,self.store.read_snapshot())

    def test_complete_graph_and_nonmonotonic_native_activity(self):
        graph=activity.graph(); workflows={w['kind']:w for w in graph['workflows']}
        self.assertEqual([n['stage_id'] for n in workflows['TRH']['nodes']],['P'+str(i) for i in range(15)])
        self.assertEqual([n['stage_id'] for n in workflows['FDH']['nodes']],['D'+str(i) for i in range(6)])
        self.assertEqual(len(graph['analysis_routes']),3); self.assertEqual(len(graph['handoffs']),2)
        self.assertFalse(graph['automatic_next']); self.assertTrue(any(e['kind']=='return' for e in workflows['TRH']['edges']))
        initial=activity.project(self.store.read_snapshot(),self.iid)
        p0=next(row for row in initial['stages'] if row['stage_id']=='P0')
        self.assertEqual(p0['status'],'VISITED'); self.assertTrue(p0['control_event_ids'])
        self.assertFalse(initial['active_stages'])
        # Projection reads native chronological visit arrays rather than the
        # largest phase or alphabetically sorted immutable identifiers.
        s=deepcopy(self.store.read_snapshot()); s['instances'][self.iid]['mission_ids']=['m']
        s['missions']={'m':{'stage_visit_ids':['z','a']}}
        s['visits']={'a':{'instance_id':self.iid,'stage_id':'P4'},'z':{'instance_id':self.iid,'stage_id':'P10'}}
        s['tasks']={t:{'instance_id':self.iid,'stage_id':stage,'request_id':t} for t,stage in [('r1','P7'),('r2','P9'),('r3','P4')]}
        s['requests']={'r1':{'execution_state':'SENT'},'r2':{'execution_state':'RESERVED'},'r3':{'execution_state':'UNKNOWN','unknown_disposition':'ABANDON_UNKNOWN'}}
        projected=activity.project(s,self.iid)
        self.assertEqual(projected['recent_stages'],['P4']); self.assertEqual(projected['active_stages'],['P7','P9'])
        self.assertFalse(projected['waiting_stages'])
        p4=next(row for row in projected['stages'] if row['stage_id']=='P4')
        self.assertEqual(p4['status'],'VISITED'); self.assertIn('禁止重发',p4['waiting_reasons'][0])

    def test_stage_products_are_readable_only_in_their_exact_producing_instance(self):
        other=self.e.new_workflow(self.store,'TRH',name='另一个目标',target='For every real x, x * 1 = x.')['instance_id']
        s=deepcopy(self.store.read_snapshot()); ref=s['instances'][other]['target_ref']
        self.assertNotIn(ref,views.scope_refs(s,self.iid))
        s['tasks']['production-task']={'instance_id':self.iid}
        s['production_events']['production']={'task_id':'production-task','record_ref':ref}
        self.assertIn(ref,views.scope_refs(s,self.iid))
        self.assertEqual(s['instances'][self.iid]['target_ref'],self.store.read_snapshot()['instances'][self.iid]['target_ref'])

    def test_scoped_discovery_sources_and_web_completion_preserve_original_bytes(self):
        draft=self.w.action('new-workflow',{'project':self.key,'kind':'FDH','name':'可补齐的发现','draft':True,'discovery_scope':{'phenomenon':'原现象\n中文。'}},'draft-scope-1234567890')
        iid=draft['instance_id']; before=self.store.read_snapshot()['instances'][iid]['discovery_brief_ref']
        self.w.action('configure-discovery',{'project':self.key,'instance':iid,'discovery_scope':{'immutable_background':'固定实数背景。','allowed_axes':'只探索正定性假设。'}},'complete-scope-1234567890')
        s=self.store.read_snapshot(); scope=s['instances'][iid]['discovery_scope']
        self.assertEqual(scope['phenomenon_ref'],before)
        visible=views.sources(s,self.store.read_blob,instance_id=iid)['sources']
        self.assertEqual({row['source_ref'] for row in visible},set(scope.values()))
        self.assertEqual({row['text'] for row in visible},{'原现象\n中文。','固定实数背景。','只探索正定性假设。'})
        self.assertFalse(s['missions']); self.assertFalse(s['requests'])


if __name__ == '__main__': unittest.main()
