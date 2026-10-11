"""Direct report authorization without an assistant or renderer/model call."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from research_studio import reports,report_revisions,demo,scheduler
from research_studio.engine import Engine
from research_studio.util import PMRSError
from research_studio.runner import FakeExecutor


class DirectReport421(unittest.TestCase):
    def test_exact_sections_cumulative_requirements_and_native_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine();store=engine.create(Path(tmp)/'project',demo.ARITHMETIC,synthetic=True)
            target=next(iter(store.read_snapshot()['records']));iid=engine.new_workflow(store,'TRH',target_ref=target)['instance_id']
            engine.authorize(store,iid,{'intent':'Create one synthetic manuscript for report API validation.',
                'authorized_scope':{'target_refs':[target],'reports':True,'allow_derived_work':True},'obligations':[]},
                {'max_calls':4,'max_workers':2,'execution_policy':demo.policy()})
            rid=reports.create(store,iid)
            def author_once():
                prepared=reports.prepare(store,iid,report_id=rid);oid=reports._assign_role(store,iid,prepared)
                policy={**demo.policy(),'only_obligation_ids':[oid]};plan=scheduler.plan(store.read_snapshot(),[iid],policy)
                made=scheduler.commit_dispatch(store,plan,policy=policy);task=store.read_snapshot()['tasks'][made['prepared'][0]['task_id']]
                self.assertEqual(task['role'],'REPORT_AUTHOR')
                outcome=FakeExecutor(lambda t,s:demo.response(t,s,blob_get=store.read_blob)).execute(store,task['task_id'])
                self.assertEqual(outcome['state'],'ACCEPTED');return task
            author_once();engine.pause(store,iid,'Research stays paused for the explicit report-only test.')
            old=reports.revision_target(store,iid,rid,'lecture');old_bytes=store.read_blob(old['body_hash']);old_records=deepcopy(store.read_snapshot()['records'])
            section=old['sections'][0]['id'];kwargs={'body_hash':old['body_hash'],'operation_id':'edit-1'}
            receipt=reports.revise_direct(store,iid,rid,'lecture',old['revision'],'Clarify the alpha requirement in the selected introduction.',{'kind':'SECTIONS','sections':[section]},3,**kwargs)
            snapshot=store.read_snapshot();auth=next(iter(snapshot['report_authorizations'].values()))
            self.assertEqual(auth['origin'],'HUMAN_UI');self.assertNotIn('turn_id',auth);self.assertNotIn('message_id',auth)
            self.assertEqual(snapshot['budget_grants'][receipt['budget_grant_id']]['budget_domain'],'REPORT')
            self.assertEqual(snapshot['instances'][iid]['status'],'PAUSED');self.assertFalse(snapshot.get('assistant_turns',{}));self.assertEqual(snapshot['records'],old_records)
            head=store._head();self.assertEqual(reports.revise_direct(store,iid,rid,'lecture',old['revision'],'Clarify the alpha requirement in the selected introduction.',{'kind':'SECTIONS','sections':[section]},3,**kwargs),receipt);self.assertEqual(store._head(),head)
            with self.assertRaisesRegex(PMRSError,'REPORT_OPERATION_CONFLICT'):
                reports.revise_direct(store,iid,rid,'lecture',old['revision'],'A conflicting instruction.',{'kind':'FULL'},3,**kwargs)
            task=author_once();new=reports.revision_target(store,iid,rid,'lecture');new_bytes=store.read_blob(new['body_hash'])
            original_ranges=report_revisions.normalize_scope(old_bytes,{'kind':'SECTIONS','sections':[section]})['ranges'];end=original_ranges[0]['end_byte']
            self.assertTrue(new_bytes.endswith(old_bytes[end:]));self.assertEqual(task['report_context']['revision_request']['requirement_refs'],auth['requirement_refs'])
            second=reports.revise_direct(store,iid,rid,'lecture',new['revision'],'Also retain beta in the exposition.',{'kind':'FULL'},3,operation_id='edit-2',body_hash=new['body_hash'])
            latest=store.read_snapshot()['reports'][rid]['revision_requests'][second['operation_id']]
            self.assertEqual(len(latest['requirement_refs']),2);self.assertTrue(set(auth['requirement_refs'])<=set(latest['requirement_refs']))
            self.assertEqual(store.read_blob(old['body_hash']),old_bytes);store.audit()


if __name__=='__main__':unittest.main()
