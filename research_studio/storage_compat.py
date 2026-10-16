"""Trusted static legacy writer assembly; never used by the confined query."""
from copy import deepcopy
import secrets
from pmrh.adapters.storage.journal import (
    SCIENCE_MAPS, CONTROL_MAPS, EXECUTION_MAPS, REPORT_MAPS, _diff,
)
from .util import canonical, sha, require, immutable, now
from .version import VERSIONS, SCHEMA_VERSION
from .language import policy
from .survey import MAPS as SURVEY_MAPS
from .assistant import MAPS as ASSISTANT_MAPS
from .native_main import MAPS as NATIVE_MAIN_MAPS

def initial_state(title, language=None, *, synthetic=False):
    from .strategy import MAPS as STRATEGY_MAPS
    from .communication import MAPS as COMMUNICATION_MAPS
    from .usage_ledger import MAPS as USAGE_MAPS
    maps = (SCIENCE_MAPS | CONTROL_MAPS | EXECUTION_MAPS | REPORT_MAPS | SURVEY_MAPS | ASSISTANT_MAPS) - {'relations'}
    maps |= STRATEGY_MAPS | COMMUNICATION_MAPS | USAGE_MAPS | NATIVE_MAIN_MAPS
    state = {name: {} for name in sorted(maps)}
    state.update(schema=SCHEMA_VERSION, project_id='P34F-'+secrets.token_hex(12),
        title=title, versions=dict(VERSIONS), language_policy=policy(language),
        relations=[], knowledge_changes=[], synthetic_test_only=bool(synthetic),
        usage={'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0},
        project_budget={'max_calls': 0}, max_workers=8,
        capabilities={'CAP-HUMAN': {'actor': 'human', 'actions': ['*'], 'instance_ids': ['*']},
                      'CAP-HOST': {'actor': 'host', 'actions': ['*'], 'instance_ids': ['*']}},
        scope_versions={'project': 0})
    return state

class LegacyWriters:
    @classmethod
    def create(cls, root, title, *, language=None, initial=None, synthetic=False):
        require(initial is None, 'STATE_PATCH_FORBIDDEN', 'Use typed knowledge and control events')
        store = cls(root)
        require(not store.root.exists(), 'PROJECT_EXISTS', 'A new project directory is required')
        state = initial_state(title, language, synthetic=synthetic)
        store.root.mkdir(parents=True, mode=0o700)
        immutable(store.root/'project.json', canonical({'schema': SCHEMA_VERSION, 'project_id': state['project_id'],
                                                      'synthetic_test_only': state['synthetic_test_only']}))
        immutable(store.root/'.runtime/writer.lock', b'')
        store._publish(None, {}, state, actor='HOST', events=[{'type': 'PROJECT_CREATED', 'model_calls': 0}])
        return store

    def commit(self, validated, expected_relevant_guards=None, *, admission_recheck=None):
        """Revalidate the same frozen response on the live state under one lock."""
        from . import changes
        with self._locked():
            state, head = self.read()
            if admission_recheck is not None:
                from .execution import validate_recheck_context
                validate_recheck_context(state,admission_recheck,self.read_blob)
                require(getattr(validated,'_task',{}).get('request_id')==admission_recheck['request_id']
                        and sha(getattr(validated,'_raw',b''))==admission_recheck['capture_ref'],
                        'ORIGINAL_BYTES_MISMATCH','Maintenance admission must validate exactly the original response.')
            frozen=getattr(validated,'_task',None)
            if isinstance(frozen,dict):
                original=state.get('requests',{}).get(frozen.get('request_id'),{})
                require(not (original.get('execution_state')=='SETTLED' and original.get('acceptance_state') in {'REJECTED_CONTRACT','REJECTED_STALE'})
                        or admission_recheck is not None,'ADMISSION_RECHECK_REQUIRED',
                        'A settled rejection requires explicit maintenance recheck of its original capture; ordinary scientific commit cannot erase rejection history.')
                for item in frozen.get('read_set',[]):
                    ref=item['record_ref']
                    require(self.read_record(ref)==state['records'].get(ref),'RECORD_CHANGED',ref)
            # changes owns scientific semantics; a forged dictionary is not an
            # accepted plan. Its entry point must re-run validation from raw.
            proposal = changes.revalidate(validated, state, blob_get=self.read_blob)
            if proposal.get('outcome') == 'EXACT_DUPLICATE':
                return proposal['receipt']
            for digest, data in proposal.get('blobs', {}).items():
                require(self.put_blob(data) == digest, 'BLOB_CHANGED', 'Candidate blob hash differs')
            after = changes.apply_validated(state, proposal)
            if admission_recheck is not None:
                from . import execution
                recheck_event=execution.event('ADMISSION_RECHECKED',{**deepcopy(admission_recheck),'outcome':'ACCEPTED',
                    'receipt_ref':proposal.get('receipt',{}).get('receipt_id'),'diagnostic':None})
                after=execution.apply_event(after,recheck_event,self.read_blob)
                proposal.setdefault('events',[]).append(recheck_event)
            self._fault('after_blobs')
            result = self._publish(head, state, after, actor=proposal.get('actor', 'MODEL_CAPTURE'),
                events=proposal.get('events', []), base=proposal.get('base_knowledge_commit'),
                accepted=proposal.get('accepted_request_bindings', []))
            return dict(proposal.get('receipt', {}), **result)

    def _typed_commit(self, event, apply, allowed, category):
        require(apply is None, 'CAPABILITY_VIOLATION', 'Reducers are selected by trusted assembly only')
        apply, registered = _reducer(category, self.read_blob)
        require(allowed == registered, 'CAPABILITY_VIOLATION', 'Reducer collection contract differs')
        require(isinstance(event, dict), 'RESPONSE_SCHEMA_INVALID', 'Typed event required')
        with self._locked():
            state, head = self.read()
            payload=event.get('payload',{})
            if event.get('event_type')=='AUTHORIZE_MISSION':
                mission=payload.get('mission',{})
                for obligation in mission.get('obligations',[]):self.read_blob(obligation['definition']['criterion_body_ref'])
                if mission.get('intent_ref'):self.read_blob(mission['intent_ref'])
                if payload.get('future_configuration'):self.read_blob(payload['future_configuration']['reason_ref'])
            if event.get('event_type')=='ASSIGN_OBLIGATION':self.read_blob(payload['obligation']['definition']['criterion_body_ref'])
            after = apply(deepcopy(state), deepcopy(event))
            require(isinstance(after, dict), 'EVENT_INVALID', 'Event reducer must return a snapshot')
            touched = set(_diff(state, after))
            require(touched <= allowed, 'CAPABILITY_VIOLATION', category+' event changed an unauthorized collection')
            if after == state:
                return {'commit': head['commit'], 'sequence': head['sequence'], 'outcome': 'EXACT_DUPLICATE'}
            if event.get('event_type')=='HUMAN_DECISION':
                instance=state['instances'][event['instance_id']]
                mission=state.get('missions',{}).get(instance.get('current_mission_id'),{})
                action={'CONTINUE_DISCOVERY':'CONTINUE','END_WITHOUT_ADOPTION':'END'}.get(payload.get('action'),payload.get('action'))
                if action in mission.get('report_first_actions',[]):
                    from .report_catalog import classify
                    report=state.get('reports',{}).get(payload['decision_basis'].get('report_ref'))
                    require(report is not None and classify(self,state,report)=='COMPLETED_CURRENT_REPORT',
                            'REPORT_BLOCKED','The explicitly required report must be complete, intact and current for this decision')
            return self._publish(head, state, after, actor=event.get('actor', 'HOST'),
                events=[event], base=event.get('base_knowledge_commit'))

    def commit_control(self, event):
        from .workflow_instances import apply_control
        from .research_audit import MAPS as AUDIT_MAPS
        result=self._typed_commit(event, None, CONTROL_MAPS | AUDIT_MAPS, 'Control')
        if event.get('event_type')=='HUMAN_DECISION' and event.get('payload',{}).get('action') in {'END','END_WITHOUT_ADOPTION'}:
            from .rounds import record
            record(self,event['instance_id'])
        return result

    def commit_execution(self, event):
        from .execution import apply_event
        from .research_audit import MAPS as AUDIT_MAPS
        return self._typed_commit(event, None, EXECUTION_MAPS | AUDIT_MAPS, 'Execution')

    def commit_survey(self, event):
        from .survey import apply_event
        return self._typed_commit(event, None, SURVEY_MAPS | {'sources'}, 'Survey')

    def commit_report(self, event):
        from .reports import apply_event
        return self._typed_commit(event, None, REPORT_MAPS, 'Report')

    def commit_assistant(self, event):
        from .assistant import apply_event
        require(event.get('event_type') not in {'OPEN_SESSION','AUTHORIZE','USER_MESSAGE','REPORT_ALLOWANCE','PREPARE_TURN','PREPARE'},
                'PROJECT_ASSISTANT_REMOVED','New assistant work is unavailable; use the native main researcher.')
        return self._typed_commit(event,None,ASSISTANT_MAPS,'Assistant')

    def _commit_extension(self, module, event):
        require(module.__name__ in {'research_studio.strategy', 'research_studio.communication',
                                  'research_studio.usage_ledger', 'research_studio.incidents'},
                'CAPABILITY_VIOLATION', 'Unknown trusted extension')
        return self._typed_commit(event, None,
                                  module.MAPS, module.__name__)

    def commit_strategy(self, event):
        from . import strategy
        return self._commit_extension(strategy,event)

    def commit_communication(self, event):
        from . import communication
        return self._commit_extension(communication,event)

    def commit_usage(self, event):
        from . import usage_ledger
        return self._commit_extension(usage_ledger,event)

    def commit_native_main(self, event):
        from . import native_main
        from .research_audit import MAPS as AUDIT_MAPS
        return self._typed_commit(event, None, NATIVE_MAIN_MAPS | EXECUTION_MAPS | AUDIT_MAPS, 'NativeMain')

    def commit_incident(self, event):
        from . import incidents
        return self._commit_extension(incidents,event)



def _reducer(category, blob_get):
    """Closed trusted code registry. Data cannot name a module or callback."""
    from . import workflow_instances, execution, survey, reports, assistant
    from . import native_main, strategy, communication, usage_ledger, incidents
    from .research_audit import MAPS as AUDIT_MAPS
    registry = {
        'Control': (workflow_instances.apply_control, CONTROL_MAPS | AUDIT_MAPS),
        'Execution': (lambda s,e: execution.apply_event(s,e,blob_get), EXECUTION_MAPS | AUDIT_MAPS),
        'Survey': (survey.apply_event, SURVEY_MAPS | {'sources'}),
        'Report': (reports.apply_event, REPORT_MAPS),
        'Assistant': (lambda s,e: assistant.apply_event(s,e,blob_get), ASSISTANT_MAPS),
        'NativeMain': (native_main.apply_event, NATIVE_MAIN_MAPS | EXECUTION_MAPS | AUDIT_MAPS),
        'research_studio.strategy': (lambda s,e: strategy.apply_event(s,e,blob_get), strategy.MAPS),
        'research_studio.communication': (lambda s,e: communication.apply_event(s,e,blob_get), communication.MAPS),
        'research_studio.usage_ledger': (lambda s,e: usage_ledger.apply_event(s,e,blob_get), usage_ledger.MAPS),
        'research_studio.incidents': (lambda s,e: incidents.apply_event(s,e,blob_get), incidents.MAPS),
    }
    require(category in registry, 'CAPABILITY_VIOLATION', 'Unknown trusted reducer')
    return registry[category]
