"""Native guidance, persistent MAIN identity and evidence-bound recovery views."""
from copy import deepcopy
from .util import require,identity,now
from . import strategy

def authorize_execution_recovery(store,instance_id,request_id,capture_ref,repair_reason,authorization_note,*,client_action_id):
    from .main_recovery import authorize
    return authorize(store,instance_id,request_id,capture_ref,repair_reason,authorization_note,client_action_id=client_action_id)

def submit_direction(store,instance_id,text,*,client_action_id,refs=None,kind='GUIDANCE',source='DIRECT_USER',supersedes=None,revokes=None):
    s=store.read_snapshot();require(instance_id in s['instances'],'INSTANCE_UNKNOWN',instance_id)
    require(s['instances'][instance_id]['kind'] in {'TRH','FDH'},'MAIN_NOT_APPLICABLE','SURVEY has a sequential workflow and no MAIN session')
    require(isinstance(client_action_id,str) and client_action_id,'IDEMPOTENCY_REQUIRED','A client action identity is required')
    require(kind in {'GUIDANCE','QUESTION','DISCUSSION','EXECUTION_INSTRUCTION','SOURCE_REQUIREMENT','ROUTE_CONSTRAINT'},'DIRECTION_INVALID','Classify the actual human wording without promoting discussion to authorization')
    prior=list(supersedes or [])+list(revokes or [])
    require(all(s.get('human_directions',{}).get(ref,{}).get('instance_id')==instance_id for ref in prior),'DIRECTION_INVALID','Only this MAIN instance\'s original guidance may be superseded or revoked')
    mid=s['instances'][instance_id].get('current_mission_id');did=identity([instance_id,client_action_id],'DIRECTION-')
    d={'schema':'pmrs.human-direction/1','direction_id':did,'client_action_id':client_action_id,
       'instance_id':instance_id,'mission_id':mid,'text':text,'refs':list(refs or []),
       'kind':kind,'source':source,'supersedes':list(supersedes or []),'revokes':list(revokes or []),
       'submitted_at_commit':s['knowledge_commit'],'created_at':now(),'status':'QUEUED','request_id':None,'reply_ref':None}
    result=store.commit_strategy(strategy.event('HUMAN_DIRECTION_SUBMITTED',{'instance_id':instance_id,'mission_id':mid,'direction':d}))
    return {**result,'direction_id':did,'status':store.read_snapshot()['human_directions'][did]['status'],'model_calls':0}

def view(store,instance_id,*,cursor=0,snapshot=None):
    from pmrh.application.read_projections import main_view
    return main_view(store.read_snapshot() if snapshot is None else snapshot,instance_id,cursor=cursor)
