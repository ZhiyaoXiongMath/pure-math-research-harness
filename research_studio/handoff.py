"""Cross-workflow references and human adoption, without copying the shared KB."""
from copy import deepcopy
from .util import identity,require
from .workflow_instances import new_instance,decision_basis,decision_guard,event

DIRECTIONS={'TRH_TO_FDH','FDH_TO_TRH','DIRECT_DISCOVERY','SURVEY_TO_TRH','SURVEY_TO_FDH'}

def prepare(snapshot,scope,direction,*,from_instance_id=None,selection_rationale_ref=None):
    require(direction in DIRECTIONS,'HANDOFF_INVALID','Unknown handoff direction')
    instance=snapshot.get('instances',{}).get(from_instance_id)
    if direction!='DIRECT_DISCOVERY':require(instance is not None,'INSTANCE_SELECTOR_REQUIRED','Select the source workflow')
    if direction.startswith('SURVEY_'):
        from .survey import handoff_scope
        targets=scope.get('target_refs',scope.get('candidate_refs',[]))
        require(len(targets)==1,'TARGET_REQUIRED','Survey handoff requires one exact selected statement')
        scope={**handoff_scope(snapshot,from_instance_id,targets[0]),**deepcopy(scope),'candidate_refs':list(targets)}
    candidates=scope.get('candidate_refs',[])
    discovery_scope=scope.get('discovery_scope')
    if discovery_scope is not None:
        from .workflow_instances import validate_discovery_scope
        require(direction in {'TRH_TO_FDH','DIRECT_DISCOVERY','SURVEY_TO_FDH'},'HANDOFF_INVALID','Discovery scope is only for a discovery handoff')
        validate_discovery_scope(snapshot,{'kind':'FDH','discovery_brief_ref':discovery_scope.get('phenomenon_ref'),'discovery_scope':discovery_scope},required=False)
    if direction.startswith('SURVEY_'):
        require(instance and instance['kind']=='SURVEY','HANDOFF_INVALID','Survey handoff requires a native Survey source instance')
        require(all(r in snapshot.get('records',{}) and snapshot['records'][r]['kind']=='Statement' for r in candidates),'HANDOFF_INVALID','Exact native statements are required')
    if direction in {'FDH_TO_TRH','SURVEY_TO_TRH'}:require(len(candidates)==1,'CANDIDATE_SELECTOR_REQUIRED','Handoff selects one exact candidate')
    basis=decision_basis(snapshot,from_instance_id,candidate_ref=candidates[0] if len(candidates)==1 and instance['kind']=='FDH' else None) if instance else {'checked_scope':[],'unchecked_scope':[],'open_obligation_refs':[]}
    manifest={'project_id':snapshot['project_id'],'from_instance_id':from_instance_id,
              'from_mission_id':instance['current_mission_id'] if instance else None,
              'source_knowledge_commit':snapshot.get('knowledge_commit'),'direction':direction,
              'target_ref':instance['target_ref'] if instance else None,'candidate_refs':candidates,
              'context_refs':scope.get('context_refs',[]),'argument_refs':scope.get('argument_refs',[]),
              'example_refs':scope.get('example_refs',[]),'source_refs':scope.get('source_refs',[]),
              'open_obligation_bindings':basis['open_obligation_refs'],
              'assurance_boundaries':{'checked_scope':basis['checked_scope'],'unchecked_scope':basis['unchecked_scope']},
              'selection_rationale_ref':selection_rationale_ref,'requested_scope':deepcopy(scope),
              'allowed_entry':scope.get('allowed_entry',[]),'budget_request':scope.get('budget_request',{}),
              'no_automatic_start':True}
    if discovery_scope is not None:
        manifest['discovery_scope']=deepcopy(discovery_scope)
        manifest['source_refs']=list(dict.fromkeys(manifest['source_refs']+list(discovery_scope.values())))
    manifest['relevant_guard']=_guard(snapshot,manifest);manifest['handoff_id']=identity(manifest,'HANDOFF-')
    validate_manifest(snapshot,manifest);return manifest

def _guard(snapshot,m):
    refs=m['candidate_refs']+m['context_refs']+m['argument_refs']+m['example_refs']+([m['target_ref']] if m['target_ref'] else [])
    return identity({'records':{r:snapshot.get('records',{}).get(r) for r in refs},
                     'sources':{r:snapshot.get('sources',{}).get(r) for r in m['source_refs']},
                     'obligations':{b['obligation_id']:snapshot.get('obligations',{}).get(b['obligation_id']) for b in m['open_obligation_bindings']}},'HANDOFF-SCOPE-')

def validate_manifest(snapshot,m):
    require(m['project_id']==snapshot['project_id'] and m['direction'] in DIRECTIONS and m['no_automatic_start'] is True,
            'HANDOFF_INVALID','One shared project and explicit paused adoption required')
    refs=m['candidate_refs']+m['context_refs']+m['argument_refs']+m['example_refs']
    require(all(ref in snapshot.get('records',{}) for ref in refs),'STALE_READ','Exact handoff records are unavailable')
    require(all(ref in snapshot.get('sources',{}) for ref in m['source_refs']),'INCOMPLETE_CONTEXT','Exact source bytes are unavailable')
    require(m['relevant_guard']==_guard(snapshot,m),'STALE_READ','Related handoff inputs changed')
    return m

def adopt_event(snapshot,handoff_id,decision_ref,*,discovery_brief_ref=None,discovery_scope=None,name=None):
    m=snapshot['handoffs'][handoff_id]
    payload={'handoff_id':handoff_id,'decision_ref':decision_ref,'discovery_brief_ref':discovery_brief_ref}
    if discovery_scope is not None:payload['discovery_scope']=deepcopy(discovery_scope)
    if name is not None:payload['name']=name
    return event(snapshot,'HANDOFF_ADOPTED',payload,instance_id=m['from_instance_id'],mission_id=m['from_mission_id'])

def apply_adoption(snapshot,p,event_row):
    s=deepcopy(snapshot);m=s.get('handoffs',{}).get(p['handoff_id']);require(m is not None,'HANDOFF_INVALID','Prepare the exact handoff first')
    validate_manifest(s,m);d=s.get('control_events',{}).get(p['decision_ref'],{})
    require(d.get('event_type')=='HUMAN_DECISION' and d.get('actor')=='human' and d.get('instance_id')==m['from_instance_id']
            and d.get('payload',{}).get('action') in {'ADOPT','ADOPT_HANDOFF'},'AUTHORIZATION_REQUIRED','Exact human adoption decision required')
    basis=d['payload']['decision_basis']
    require(d['payload']['decision_guard']==decision_guard(s,basis),'STALE_READ','Decision inputs changed')
    if m['direction'] in {'FDH_TO_TRH','SURVEY_TO_TRH'}:
        require(len(m['candidate_refs'])==1 and (m['direction']=='SURVEY_TO_TRH' or basis['candidate_refs']==m['candidate_refs']),'CANDIDATE_SELECTOR_REQUIRED','Adoption must select the prepared candidate')
        row=new_instance(s,'TRH',target_ref=m['candidate_refs'][0],created_by_decision=p['decision_ref'],name=p.get('name'))
    else:
        scope=p.get('discovery_scope',m.get('discovery_scope'))
        if m.get('discovery_scope') is not None:require(scope==m['discovery_scope'],'HANDOFF_INVALID','Adoption must preserve the prepared discovery scope')
        row=new_instance(s,'FDH',discovery_brief_ref=(scope or {}).get('phenomenon_ref',p.get('discovery_brief_ref')),
                created_by_decision=p['decision_ref'],name=p.get('name'),discovery_scope=scope)
    row['inherited_handoff_ref']=m['handoff_id']
    previous=s.setdefault('handoff_adoptions',{}).get(p['decision_ref'])
    if previous:return s
    s.setdefault('instances',{})[row['instance_id']]=row;s['handoff_adoptions'][p['decision_ref']]={'handoff_id':m['handoff_id'],'instance_id':row['instance_id']}
    return s

class Handoff:
    prepare=staticmethod(prepare)
