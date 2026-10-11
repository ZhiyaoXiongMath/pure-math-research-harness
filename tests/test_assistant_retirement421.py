"""Current retirement behavior; old live-feature cases remain in legacy_420.

The former tests asserted that new paid assistant sessions existed. That feature
was explicitly removed in 4.2.2; these cases check refusal and historical reads.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from research_studio import assistant,model_policy
from research_studio.store import Store
from research_studio.util import PMRSError
from tests import test_intervention_surface as surface_helpers


def historical_session(store):
    """Seed a generated old-schema event through its replay reducer only."""
    sid='ASSISTANT-SESSION-generated-legacy'
    event=assistant.event('OPEN_SESSION',{'session':{'session_id':sid,'context':{},
        'created_at':'2026-01-01T00:00:00+00:00','budget_grant_id':'ASSISTANT-BUDGET-generated-legacy',
        'message_ids':[],'turn_ids':[]}},human=True)
    store._typed_commit(event,lambda state,e:assistant.apply_event(state,e,store.read_blob),assistant.MAPS,'Assistant')
    return sid


class AssistantRetirement421(unittest.TestCase):
    def test_new_session_and_old_session_writes_refuse_before_any_model(self):
        with TemporaryDirectory() as d:
            store=Store.create(Path(d)/'p','Generated retirement fixture',synthetic=True)
            sid=historical_session(store);before=store.read_snapshot()
            with patch('research_studio.runner.CodexExecutor.execute',side_effect=AssertionError('No assistant calls')):
                for action in (lambda:assistant.open_session(store,{},'new-session'),
                    lambda:assistant.authorize(store,sid,1,'new-grant'),
                    lambda:assistant.submit(store,sid,'A new live reply is unavailable.','new-message'),
                    lambda:model_policy.resolve_assistant({})):
                    with self.assertRaisesRegex(PMRSError,'PROJECT_ASSISTANT_REMOVED'):action()
            self.assertEqual(before,store.read_snapshot());store.audit()

    def test_historical_session_reads_and_full_replay_preserve_identity(self):
        with TemporaryDirectory() as d:
            store=Store.create(Path(d)/'p','Generated historical reader',synthetic=True)
            sid=historical_session(store);before=store.read_snapshot()
            self.assertEqual(assistant.status(store,sid)['session_id'],sid)
            self.assertEqual(before,store.read_snapshot())
            for path in (store.root/'checkpoints').glob('*.json'):path.unlink()
            self.assertEqual(before,store.read_snapshot());store.audit()


class AssistantRetirementSurface421(unittest.TestCase):
    setUp=surface_helpers.InterventionSurface.setUp
    tearDown=surface_helpers.InterventionSurface.tearDown
    req=surface_helpers.InterventionSurface.req
    create=surface_helpers.InterventionSurface.create

    def test_old_write_endpoints_are_absent_and_legacy_read_is_read_only(self):
        made=self.create('TRH');store=self.w.project(made['project']);sid=historical_session(store)
        before=store.read_snapshot()
        for action in ('assistant-open','assistant-authorize','assistant-send','assistant-recover','assistant-cancel'):
            status,body,_=self.req('POST','/api/action/'+action,{'project':made['project'],'session_id':sid})
            self.assertEqual(status,400,body);self.assertEqual(body['error'],'ACTION_UNKNOWN')
        status,body,_=self.req('GET','/api/legacy-assistant?project='+made['project']+'&session_id='+sid)
        self.assertEqual(status,200,body);self.assertTrue(body['read_only_legacy']);self.assertEqual(before,store.read_snapshot())


if __name__=='__main__':unittest.main()
