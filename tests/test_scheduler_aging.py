"""One bounded native aging regression, with no model transport."""
from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from research_studio import demo,execution,reports,scheduler
from research_studio.engine import Engine
from research_studio.util import canonical,loads


class SchedulerAging(unittest.TestCase):
    def test_native_prepare_order_promotes_report_and_account_with_legacy_fallback(self):
        for kind in ('REPORT','ACCOUNT'):
            with self.subTest(kind=kind),TemporaryDirectory() as tmp,patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':tmp+'/pool'}):
                engine=Engine();store=engine.create(Path(tmp)/'p',demo.ARITHMETIC,synthetic=True)
                target=next(iter(store.read_snapshot()['records']));iid=engine.new_workflow(store,'TRW',target_ref=target)['instance_id']
                items=[{'key':'ordinary'+str(n),'stage':'P4','role':'RESEARCH','intent':'Different bounded native aging responsibility '+str(n)} for n in range(12)]
                items.append({'key':'previous-account','stage':'P11','role':'SYNTHESIS','intent':'Earlier explicit global account.'})
                if kind=='ACCOUNT':items.append({'key':'waiting-account','stage':'P11','role':'SYNTHESIS','intent':'Later explicit global account.'})
                planned=engine.plan_work(store,iid,'Finite native preparation aging test.',items,max_calls=30,max_workers=1,policy=demo.policy(),allow_reports=True)
                ids={row['key']:row['obligation_id'] for row in planned['bindings']}
                def freeze(oid=None):
                    policy={**demo.policy(),**({'only_obligation_ids':[oid]} if oid else {})}
                    plan=scheduler.plan(store.read_snapshot(),[iid],policy);self.assertTrue(plan['selected'],plan['waits'])
                    self.assertEqual(len(plan['selected']),1)
                    row=scheduler.commit_dispatch(store,plan,policy=policy)['prepared'][0]
                    return store.read_snapshot()['tasks'][row['task_id']]
                previous=freeze(ids['previous-account'])
                self.assertEqual(scheduler.ordinary_preparations_since_account(store.read_snapshot()),0)
                for n in range(8):freeze(ids['ordinary'+str(n)])
                state=store.read_snapshot();self.assertEqual(state['scheduler_state']['ordinary_preparations_since_account'],8)
                if kind=='REPORT':
                    prepared=reports.prepare(store,iid);expected=reports._assign_role(store,iid,prepared)
                else:expected=ids['waiting-account']
                state=store.read_snapshot();original=canonical(state)
                variants=[deepcopy(state),loads(canonical(state))]
                # The old ACCOUNT is chronologically first but can be last in
                # an arbitrary content-addressed map traversal.
                variants[0]['tasks']={**{k:v for k,v in reversed(list(state['tasks'].items())) if k!=previous['task_id']},previous['task_id']:state['tasks'][previous['task_id']]}
                legacy=deepcopy(variants[0]);legacy['scheduler_state'].pop('ordinary_preparations_since_account')
                legacy['execution_events']=dict(reversed(list(legacy['execution_events'].items())))
                variants.append(legacy)
                for view in variants:
                    plan=scheduler.plan(view,[iid],demo.policy())
                    self.assertEqual(plan['selected'][0]['obligation_id'],expected)
                    self.assertEqual(plan['selected'][0]['priority'],-1)
                self.assertEqual(canonical(store.read_snapshot()),original)
                selected=freeze(expected);state=store.read_snapshot()
                self.assertEqual(state['scheduler_state']['ordinary_preparations_since_account'],0)
                self.assertIn(scheduler.plan(state,[iid],demo.policy())['selected'][0]['obligation_id'],
                              {ids['ordinary'+str(n)] for n in range(8,12)})
                event=next(e for e in state['execution_events'].values() if e['event_type']=='PREPARE' and e['payload']['task']['task_id']==selected['task_id'])
                store.commit_execution(event)
                self.assertEqual(store.read_snapshot()['scheduler_state']['ordinary_preparations_since_account'],0)
                # An old projection can accept its next original PREPARE without
                # rewriting historical task/event identities or needing migration.
                migrated=execution.apply_event(legacy,event)
                self.assertEqual(migrated['scheduler_state']['ordinary_preparations_since_account'],0)
                self.assertEqual(migrated['tasks'][previous['task_id']],legacy['tasks'][previous['task_id']])
                self.assertEqual(state['usage']['model_calls'],0);store.audit()
