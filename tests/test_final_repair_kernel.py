"""R02/R03/R04/R08 regressions through the ordinary native application services."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from research_studio import changes,cli,demo,execution,model_policy,scheduler,workflow_instances as W
from research_studio.engine import Engine
from research_studio.util import PMRSError


def override(stage,role,effort,kind='TRW',purpose='DEFAULT'):
    return {'explicit':True,'scope':{'workflow_kind':kind,'stage_id':stage,'role':role,'purpose':purpose},
            'model':'gpt-6-astra','reasoning_effort':effort,'service_tier':'default'}


class Repairs(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Engine();self.store=self.e.create(Path(self.tmp.name)/'project',demo.ARITHMETIC,synthetic=True)
        self.target=next(iter(self.store.read_snapshot()['records']))

    def trw(self,name='原目标'):
        return self.e.new_workflow(self.store,'TRW',name=name,target_ref=self.target)['instance_id']

    def assertCode(self,code,fn):
        with self.assertRaises(PMRSError) as error:fn()
        self.assertEqual(error.exception.code,code)

    def uncertain(self,iid):
        self.e.start_round(self.store,iid,'Inspect the fixed target.',max_calls=3,policy=demo.policy())
        row=self.e.prepare(self.store,iid)['prepared'][0];s=self.store.read_snapshot();task=s['tasks'][row['task_id']]
        self.store.commit_execution(execution.event('RESERVE',{'request_id':row['request_id'],'executor_contract':task['executor_contract'],
                'model_policy':task['model_policy'],'execution_kind':'SYNTHETIC_TEST_ONLY'}))
        request=self.store.read_snapshot()['requests'][row['request_id']]
        self.store.commit_execution(execution.event('UNKNOWN',{'request_id':row['request_id'],'execution_id':request['execution_id'],'reason':'Instrumented uncertain transport.'}))
        return row['request_id']

    def test_r04_merge_reset_and_first_frozen_task(self):
        iid=self.trw();p4=override('P4','RESEARCH','high');p9=override('P9','PROOF','xhigh')
        self.e.start_round(self.store,iid,'Apply the explicitly selected first-call policy.',max_calls=4,policy=demo.policy(),model_overrides=[p4])
        frozen=self.e.prepare(self.store,iid)['prepared'][0]
        fake=demo.executor();fake.execute(self.store,frozen['task_id']);self.assertEqual(fake.calls,1)
        before=self.store.read_snapshot();task=deepcopy(before['tasks'][frozen['task_id']])
        self.assertEqual(task['model_policy']['reasoning_effort'],'high')
        self.e.update_configuration(self.store,iid,[p9])
        self.assertEqual(self.e.policy(self.store,iid)['model_overrides'],[p4,p9])
        new_p4=override('P4','RESEARCH','xhigh');self.e.update_configuration(self.store,iid,[new_p4])
        self.assertEqual(self.e.policy(self.store,iid)['model_overrides'],[new_p4,p9])
        self.e.update_configuration(self.store,iid,[],reset_scopes=[p4['scope']])
        after=self.store.read_snapshot();self.assertEqual(self.e.policy(self.store,iid)['model_overrides'],[p9])
        self.assertEqual(after['tasks'][task['task_id']],task)
        for key in ('requests','retry_grants','attempt_groups','project_budget','obligations'):self.assertEqual(after[key],before[key],key)
        self.assertEqual(model_policy.resolve('TRW','P4','RESEARCH',require_capability=False)['reasoning_effort'],'max')
        for kind,stage in [('TRW','P10'),('TFDW','D2')]:self.assertEqual(model_policy.resolve(kind,stage,'SYNTHESIS',require_capability=False)['reasoning_effort'],'max')
        self.assertCode('MODEL_CONFIGURATION_UNSUPPORTED',lambda:self.e.update_configuration(self.store,iid,[override('P4','RESEARCH','ultra')]))

    def test_r04_complete_scope_distinguishes_purpose_and_role(self):
        ordinary=override('D1','LEARN','high','TFDW');special=override('D1','LEARN','max','TFDW','NEW_CONSTRUCTION')
        merged=model_policy.merge_overrides([ordinary],[special],workflow_kind='TFDW',capabilities=demo.policy()['model_capabilities'])
        self.assertEqual(len(merged),2)
        reset=model_policy.merge_overrides(merged,[],reset_scopes=[ordinary['scope']],workflow_kind='TFDW',capabilities=demo.policy()['model_capabilities'])
        self.assertEqual(reset,[special])

    def test_r02_incomplete_draft_does_not_authorize_and_exact_text_enters_packet(self):
        iid=self.e.new_workflow(self.store,'TFDW',name='中文发现草稿',brief='现象原文\n保持换行。')['instance_id']
        before=self.store.read_snapshot()
        self.assertCode('DISCOVERY_SCOPE_REQUIRED',lambda:self.e.start_round(self.store,iid,'Explore.',policy=demo.policy()))
        self.assertEqual(self.store.read_snapshot(),before)
        text={'immutable_background':'不可改变：底域为实数。\n','allowed_axes':'用户明确允许只改变矩阵的正定性假设；其它背景不变。'}
        self.e.configure_discovery(self.store,iid,text)
        self.e.start_round(self.store,iid,'按所选范围开展发现。',max_calls=2,policy=demo.policy())
        prepared=self.e.prepare(self.store,iid)['prepared'][0];s=self.store.read_snapshot();task=s['tasks'][prepared['task_id']]
        scope=s['instances'][iid]['discovery_scope'];self.assertEqual(task['discovery_scope'],scope)
        packet=json.loads(self.store.read_blob(task['input_packet_ref']));exact={'phenomenon':'现象原文\n保持换行。',**text}
        for name,raw in exact.items():
            source=s['sources'][scope[name+'_ref']]
            self.assertEqual(self.store.read_blob(source['blob_hash']),raw.encode())
            self.assertEqual(base64.b64decode(packet['source_bytes_base64'][source['blob_hash']]),raw.encode())
        self.assertCode('DISCOVERY_SCOPE_IMMUTABLE',lambda:self.e.configure_discovery(self.store,iid,{'allowed_axes':'Alter every assumption.'}))

    def test_r03_two_named_instances_of_each_kind_preserve_old_targets(self):
        first=self.trw('固定原目标');second=self.e.new_workflow(self.store,'TRW',name='另一目标',target=b'For every real x, x * 1 = x.')['instance_id']
        d1=self.e.new_workflow(self.store,'TFDW',name='矩阵发现一',discovery_scope=demo.discovery_scope())['instance_id']
        d2=self.e.new_workflow(self.store,'TFDW',name='矩阵发现二',discovery_scope=demo.discovery_scope('Compare another exact matrix observation.'))['instance_id']
        s=self.store.read_snapshot();self.assertEqual(len(s['instances']),4)
        self.assertEqual([s['instances'][i]['name'] for i in (first,second,d1,d2)],['固定原目标','另一目标','矩阵发现一','矩阵发现二'])
        self.assertEqual(s['instances'][first]['target_ref'],self.target)
        self.assertNotEqual(s['instances'][second]['target_ref'],self.target)
        self.assertTrue(all(i['status']=='PAUSED' for i in s['instances'].values()))
        self.assertFalse(s['missions']);self.assertFalse(s['requests'])

    def test_r02_partial_native_draft_requires_explicit_scope_completion(self):
        source=self.store.commit(changes.prepare_source_input(self.store.read_snapshot(),b'Original user phenomenon.',purpose='PHENOMENON',blob_get=self.store.read_blob))['source_ref']
        state=self.store.read_snapshot();row=W.new_instance(state,'TFDW',discovery_brief_ref=source,discovery_scope={'phenomenon_ref':source})
        self.store.commit_control(W.event(state,'CREATE_INSTANCE',{'instance':row}));iid=row['instance_id']
        self.assertEqual(self.store.read_snapshot()['instances'][iid]['discovery_brief_ref'],source)
        self.assertCode('DISCOVERY_SCOPE_REQUIRED',lambda:self.e.start_round(self.store,iid,'Investigate.',policy=demo.policy()))
        self.e.configure_discovery(self.store,iid,{'immutable_background':'Retain the exact original setting.','allowed_axes':'The user explicitly allows no additional axes.'})
        completed=self.store.read_snapshot()['instances'][iid]
        self.assertEqual(completed['discovery_scope']['phenomenon_ref'],source)
        self.e.start_round(self.store,iid,'Investigate exactly this scope.',max_calls=1,policy=demo.policy())
        self.assertEqual(len(self.e.prepare(self.store,iid)['prepared']),1)

    def test_r02_handoff_binds_scope_without_replacing_fixed_target(self):
        iid=self.trw();scope=self.e.prepare_discovery_scope(self.store,demo.discovery_scope())
        prepared=self.e.prepare_handoff(self.store,iid,'TRW_TO_TFDW',{'discovery_scope':scope})
        decision=self.e.decide(self.store,iid,'ADOPT_HANDOFF','Explore a separate formulation scope.',snapshot_commit=self.store.read_snapshot()['knowledge_commit'])
        decision.update(discovery_scope=scope,name='交接发现')
        adopted=self.e.adopt_handoff(self.store,prepared['handoff_id'],decision)['instance_id'];s=self.store.read_snapshot()
        self.assertEqual(s['instances'][adopted]['discovery_scope'],scope)
        self.assertEqual(s['instances'][adopted]['name'],'交接发现');self.assertEqual(s['instances'][adopted]['status'],'PAUSED')
        self.assertEqual(s['instances'][iid]['target_ref'],self.target);self.assertFalse(s['requests'])

    def test_r08_abandon_retains_budget_and_prevents_resend_without_blocking_other_work(self):
        iid=self.trw();rid=self.uncertain(iid);before=self.store.read_snapshot();remaining=scheduler.project_remaining(before)
        self.e.reconcile_unknown(self.store,iid,rid,'ABANDON_UNKNOWN','Stop waiting; sending remains unknown.')
        after=self.store.read_snapshot();request=after['requests'][rid]
        self.assertEqual(request['execution_state'],'UNKNOWN');self.assertTrue(request['fenced'])
        self.assertEqual(scheduler.project_remaining(after),remaining)
        for key in ('tasks','attempt_groups','retry_grants','records','supports','obligations'):self.assertEqual(after[key],before[key],key)
        self.assertFalse(self.e.schedule(self.store,iid)['selected'])
        head=after['knowledge_commit'];self.assertEqual(self.e.reconcile_unknown(self.store,iid,rid,'ABANDON_UNKNOWN','Stop waiting; sending remains unknown.')['outcome'],'EXACT_DUPLICATE')
        self.assertEqual(self.store.read_snapshot()['knowledge_commit'],head)
        second=self.trw('另一独立工作');self.e.start_round(self.store,second,'Investigate independently.',max_calls=1,policy=demo.policy())
        row=self.e.prepare(self.store,second)['prepared'][0];s=self.store.read_snapshot();task=s['tasks'][row['task_id']]
        self.store.commit_execution(execution.event('RESERVE',{'request_id':row['request_id'],'executor_contract':task['executor_contract'],
                'model_policy':task['model_policy'],'execution_kind':'SYNTHETIC_TEST_ONLY'}))
        self.assertEqual(self.store.read_snapshot()['requests'][rid],request)

    def test_r08_confirmed_not_sent_needs_original_evidence_and_cli_same_service(self):
        iid=self.trw();rid=self.uncertain(iid);before=self.store.read_snapshot();remaining=scheduler.project_remaining(before)
        self.assertCode('UNKNOWN_REQUIRES_EVIDENCE',lambda:self.e.reconcile_unknown(self.store,iid,rid,'CONFIRMED_NOT_SENT','A note alone is not evidence.'))
        self.assertEqual(self.store.read_snapshot(),before)
        receipt=self.store.commit(changes.prepare_material_input(before,b'Instrumented transport log: this synthetic original request did not cross the send boundary.',title='actual test transport log',media_type='text/plain',blob_get=self.store.read_blob))
        argv=['reconcile',str(self.store.root),'--instance',iid,'--request',rid,'--disposition','CONFIRMED_NOT_SENT','--reason','I inspected the attached transport log.','--not-sent-evidence',receipt['source_ref']]
        out=cli.execute(cli.parser().parse_args(argv));self.assertEqual(out['execution_state'],'CANCELLED_BEFORE_SEND')
        s=self.store.read_snapshot();request=s['requests'][rid];decision=s['control_events'][request['reconciliation_event']]
        self.assertEqual(scheduler.project_remaining(s),remaining+1)
        self.assertEqual(decision['actor'],'human');self.assertEqual(decision['payload']['execution_id'],request['execution_id'])
        self.assertEqual(decision['payload']['not_sent_evidence_ref'],receipt['source_ref'])
        self.assertEqual(len(s['requests']),1);self.assertEqual(s['usage']['model_calls'],0)
        self.assertEqual(cli.execute(cli.parser().parse_args(argv))['outcome'],'EXACT_DUPLICATE')


if __name__=='__main__':unittest.main()
