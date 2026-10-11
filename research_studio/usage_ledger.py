"""Backend lifecycle evidence, independent of scientific admission.

Only bounded executor logs supply counts. Cumulative checkpoints are maxima per
turn, never increments; an unknown count stays null. Recovery is idempotent.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import threading
from .util import canonical,identity,require,sha,PMRSError

SCHEMA='pmrs.backend-usage/1'
MAPS=frozenset({'usage_events','backend_usage','usage_log_cursors','requests','usage','delegation_observations','backend_internal_usage','native_usage_cursors'})
MAX_LINE=1024*1024
MAX_LOG=64*1024*1024
TOKEN_FIELDS=('input_tokens','output_tokens','cached_input_tokens','reasoning_output_tokens','total_tokens')


def event(kind,payload):
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':kind,'payload':deepcopy(payload)}
    e['event_id']=identity(e,'USAGE-EVENT-');return e



DELEGATION_CLASSIFIER_REVISION='pmrs.native-delegation-classifier/2'
# Exact native Codex event/item discriminators only. In particular ordinary
# agent_message is the main agent's text output, never delegation evidence.
NATIVE_DELEGATION_TYPES=frozenset({'collabAgentToolCall','collab_tool_call','collab_agent_tool_call',
    'collab_agent_spawn_begin','collab_agent_spawn_end',
    'collab_agent_interaction_begin','collab_agent_interaction_end',
    'collab_waiting_begin','collab_waiting_end','collab_close_begin','collab_close_end',
    'collab_resume_begin','collab_resume_end'})

def native_delegation_kind(row):
    if not isinstance(row,dict):return None
    if row.get('method') in {'item/started','item/updated','item/completed'}:
        item=row.get('params',{}).get('item',{})
        return item.get('type') if item.get('type') in NATIVE_DELEGATION_TYPES else None
    item=row.get('item') if row.get('type') in {'item.started','item.updated','item.completed'} else row.get('msg') if row.get('type')=='event_msg' else row
    if not isinstance(item,dict):return None
    kind=item.get('type')
    return kind if kind in NATIVE_DELEGATION_TYPES else None

def delegation_observations(snapshot):
    return [x for x in snapshot.get('delegation_observations',{}).values()
            if x.get('event_type') in NATIVE_DELEGATION_TYPES and x.get('classification')!='NOT_NATIVE_DELEGATION']

def reconcile_delegation_classifications(store,request_id=None):
    """Append classification corrections from original exact native evidence.

    No capture, scientific decision, token count, budget, original observation
    event or evidence blob is replaced. Safe to call during normal recovery.
    """
    s=store.read_snapshot();corrected=[]
    for oid,row in list(s.get('delegation_observations',{}).items()):
        if request_id and row['request_id']!=request_id:continue
        raw=store.read_blob(row['evidence_ref'])
        require(sha(raw)==row['evidence_ref'],'ORIGINAL_BYTES_MISMATCH','Native delegation evidence changed.')
        decoded=json.loads(raw);native=native_delegation_kind(decoded)
        classification='NATIVE_DELEGATION' if native else 'NOT_NATIVE_DELEGATION'
        if row.get('classification')==classification and row.get('classifier_revision')==DELEGATION_CLASSIFIER_REVISION:continue
        if classification=='NATIVE_DELEGATION' and row.get('event_type')==native and 'classification' not in row:continue
        payload={'schema':SCHEMA,'request_id':row['request_id'],'execution_id':row['execution_id'],
            'observation_id':oid,'evidence_ref':row['evidence_ref'],'original_event_type':row.get('event_type'),
            'classification':classification,'native_event_type':native,'classifier_revision':DELEGATION_CLASSIFIER_REVISION,
            'classifier_sha256':sha(Path(__file__).read_bytes()),
            'reason':'Reclassified the original exact CLI event using native collaboration discriminators. Ordinary MAIN agent_message is not internal delegation.'}
        receipt=store.commit_usage(event('DELEGATION_CLASSIFICATION_CORRECTED',payload))
        corrected.append({'observation_id':oid,'classification':classification,'receipt':receipt})
    return {'state':'RECONCILED','corrections':corrected,'model_calls':0}

def counts(value):
    value=value if isinstance(value,dict) else {}
    aliases={'cached_input_tokens':'cache_read_input_tokens','reasoning_output_tokens':'reasoning_tokens'}
    result={}
    for key in TOKEN_FIELDS:
        item=value.get(key,value.get(aliases.get(key,'')))
        result[key]=item if type(item) is int and item>=0 else None
    # Cache and reasoning figures are included subcategories, not additions.
    if result['total_tokens'] is None and result['input_tokens'] is not None and result['output_tokens'] is not None:
        result['total_tokens']=result['input_tokens']+result['output_tokens']
    return result


def internal_usage(snapshot,request_ids):
    """Expose native thread counters separately; inclusion is not specified."""
    ids=set(request_ids)
    rows=[deepcopy(r) for r in snapshot.get('backend_internal_usage',{}).values() if ids.intersection(r['request_ids'])]
    rows.sort(key=lambda r:(r['thread_id'],r['root_thread_id']))
    return {'threads':rows,'observed_threads':len(rows),
            'observed_tokens_by_thread':{r['thread_id']:r['counts']['total_tokens'] for r in rows},
            'tokens':None,'coverage':'NATIVE_THREAD_COUNTERS_OBSERVED' if rows else 'NO_NATIVE_THREAD_COUNTER_OBSERVED',
            'included_in_parent_total':'UNSPECIFIED_BY_NATIVE_CLIENT' if rows else 'NOT_EXPOSED_BY_CLI',
            'add_to_parent_total':False,'aggregate_semantics':'Independent cumulative thread observations. Parent/descendant overlap is unspecified; no cross-thread sum is asserted.',
            'internal_model_requests':None,'pmrs_top_level_requests':0,'stage_slots':0}


def request_usage(snapshot,request_id):
    rows=[r for r in snapshot.get('backend_usage',{}).values() if r['request_id']==request_id]
    result={field:sum(r['counts'][field] for r in rows) if rows and all(r['counts'][field] is not None and not r.get('conflicts') for r in rows) else None for field in TOKEN_FIELDS}
    result.update(schema=SCHEMA,backend_turns=len(rows),backend_started=sum(r['started'] for r in rows),
                  backend_completed=sum(r['completed'] for r in rows),
                  known_input_tokens=sum(r['counts']['input_tokens'] or 0 for r in rows),
                  known_output_tokens=sum(r['counts']['output_tokens'] or 0 for r in rows),
                  coverage='COMPLETE' if rows and all(r['completed'] and not r.get('conflicts') and r['counts']['input_tokens'] is not None and r['counts']['output_tokens'] is not None for r in rows) else 'PARTIAL_OR_UNKNOWN',
                  internal_model_requests=None,native_delegation_observation_count=sum(x['request_id']==request_id for x in delegation_observations(snapshot)),
                  native_delegation_observation_semantics='Explicit CLI collaboration events only; zero observed events does not establish zero native delegates. MAIN self-reports remain in the original response, not counted as native evidence.',
                  internal_delegation_tokens=None,internal_usage_included_in_parent='NOT_EXPOSED_BY_CLI',internal_request_coverage='CLI_JSONL_DOES_NOT_EXPOSE_EVERY_PROVIDER_INFERENCE_REQUEST',
                  evidence_refs=sorted({ref for r in rows for ref in r['evidence_refs']}))
    internal=internal_usage(snapshot,[request_id]);result['native_internal_usage']=internal
    if internal['observed_threads']:
        result['internal_usage_included_in_parent']='UNSPECIFIED_BY_NATIVE_CLIENT'
        result['internal_request_coverage']='NATIVE_THREAD_USAGE_OBSERVED_PROVIDER_REQUEST_COUNT_UNKNOWN'
    return result


def summary(snapshot,*,instance_id=None,mission_id=None,budget_domain=None):
    requests=[r for r in snapshot.get('requests',{}).values() if (not instance_id or r['instance_id']==instance_id)
              and (not mission_id or r['mission_id']==mission_id) and (not budget_domain or r.get('budget_domain','SCIENCE')==budget_domain)]
    real=[r for r in requests if r.get('execution_kind')=='MODEL'];ids={r['request_id'] for r in real}
    turns=[r for r in snapshot.get('backend_usage',{}).values() if r['request_id'] in ids]
    return {'schema':SCHEMA,'as_of_commit':snapshot.get('knowledge_commit'),'model_calls':sum(r['started'] for r in turns),
            'actual_started':sum(r['started'] for r in turns),'actual_completed':sum(r['completed'] for r in turns),
            'accepted':sum(r.get('acceptance_state')=='ACCEPTED' for r in real),
            'rejected':sum(r.get('acceptance_state','').startswith('REJECTED') for r in real),
            'unknown_requests':sum(r['execution_state']=='UNKNOWN' for r in real),
            'sent_requests':sum(r['execution_state'] not in {'PREPARED','CANCELLED_BEFORE_SEND'} for r in real),
            'reserved_requests':sum(r['execution_state'] in {'PREPARED','RESERVED','SENT','UNKNOWN'} for r in requests),
            'science_samples':len({r.get('attempt_key',r['request_id']) for r in real if r.get('budget_domain','SCIENCE')=='SCIENCE' and not r.get('repair_of')}),
            'pmrs_top_level_requests':len(real),
            'main_top_level_requests':sum(snapshot.get('tasks',{}).get(r['task_id'],{}).get('actor_kind')=='MAIN' for r in real),
            'stage_cli_requests':sum(snapshot.get('tasks',{}).get(r['task_id'],{}).get('actor_kind')!='MAIN' for r in real),
            'native_delegation':{**internal_usage(snapshot,ids),'observed_events':sum(x['request_id'] in ids for x in delegation_observations(snapshot)),
                'model_requests':None,
                'observation_semantics':'Zero observable collaboration events does not prove no internal delegation. MAIN self-report stays in original output and is not native usage evidence.','pmrs_limits':None},
            'format_calls':sum(r.get('repair_kind')=='FORMAT' and any(t['request_id']==r['request_id'] and t['started'] for t in turns) for r in real),
            'known_input_tokens':sum(t['counts']['input_tokens'] or 0 for t in turns),
            'known_output_tokens':sum(t['counts']['output_tokens'] or 0 for t in turns),
            'input_tokens':sum(t['counts']['input_tokens'] for t in turns) if turns and all(t['counts']['input_tokens'] is not None and not t.get('conflicts') for t in turns) else None,
            'output_tokens':sum(t['counts']['output_tokens'] for t in turns) if turns and all(t['counts']['output_tokens'] is not None and not t.get('conflicts') for t in turns) else None,
            'unknown_usage_requests':sum(request_usage(snapshot,r['request_id'])['coverage']!='COMPLETE' for r in real),
            'synthetic_requests':sum(r.get('execution_kind')=='SYNTHETIC_TEST_ONLY' for r in requests),
            'count_semantics':'Per-backend-turn cumulative maximum; cached/reasoning are included subcategories; no price inferred.'}


def apply_event(snapshot,e,blob_get=None):
    require(set(e)=={'event_id','actor','capability_ref','event_type','payload'} and e['actor']=='host'
            and snapshot.get('capabilities',{}).get(e['capability_ref'],{}).get('actor')=='host','AUTHORIZATION_REQUIRED','Usage observations require host capability.')
    old=snapshot.get('usage_events',{}).get(e['event_id'])
    if old:
        require(old==e,'USAGE_EVIDENCE_CONFLICT','Usage event identity differs.');return deepcopy(snapshot)
    s=deepcopy(snapshot);p=e['payload'];rid=p['request_id'];request=s.get('requests',{}).get(rid)
    require(request and p['execution_id']==request['execution_id'],'USAGE_EVIDENCE_CONFLICT','Usage belongs to an exact original execution.')
    require(request['execution_state']!='PREPARED','USAGE_EVIDENCE_CONFLICT','An unsent request has no backend lifecycle evidence.')
    if e['event_type']=='BACKEND_OBSERVATION':
        raw=blob_get(p['evidence_ref']);require(sha(raw)==p['evidence_ref'],'ORIGINAL_BYTES_MISMATCH','Backend log evidence differs.')
        require(p.get('schema')==SCHEMA and p['phase'] in {'STARTED','COMPLETED','CHECKPOINT','FAILED'}
                and p['semantics']=='TURN_CUMULATIVE','USAGE_EVIDENCE_INVALID','Typed backend lifecycle and counting semantics required.')
        key=identity([rid,p['execution_id'],p['thread_id'],p['turn_id']],'BACKEND-TURN-')
        row=s.setdefault('backend_usage',{}).setdefault(key,{'schema':SCHEMA,'request_id':rid,'execution_id':p['execution_id'],
            'task_id':request['task_id'],'mission_id':request['mission_id'],'thread_id':p['thread_id'],'turn_id':p['turn_id'],
            'started':False,'completed':False,'counts':counts(None),'evidence_refs':[],'conflicts':[]})
        row['started']|=p['phase']=='STARTED';incoming=counts(p.get('counts'))
        for field,value in incoming.items():
            current=row['counts'][field]
            if value is None:continue
            if current is not None and value<current:
                row['conflicts'].append({'kind':'COUNT_REGRESSION','field':field,'before':current,'observed':value,'evidence_ref':p['evidence_ref']})
            if row['completed'] and current is not None and value!=current:
                row['conflicts'].append({'kind':'CONFLICTING_TERMINAL_USAGE','field':field,'observed':value,'evidence_ref':p['evidence_ref']})
            row['counts'][field]=max(current,value) if current is not None else value
        row['completed']|=p['phase']=='COMPLETED'
        if p['evidence_ref'] not in row['evidence_refs']:row['evidence_refs'].append(p['evidence_ref'])
        request['usage']=request_usage(s,rid)
    elif e['event_type']=='NATIVE_DELEGATION_OBSERVATION':
        raw=blob_get(p['evidence_ref']);require(sha(raw)==p['evidence_ref'],'ORIGINAL_BYTES_MISMATCH','Delegation event evidence differs.')
        require(s['tasks'][request['task_id']].get('actor_kind')=='MAIN','USAGE_EVIDENCE_INVALID','Only MAIN has native internal delegation.')
        require(native_delegation_kind(json.loads(raw))==p.get('event_type'),'USAGE_EVIDENCE_INVALID','Only an explicit native collaboration event counts as delegation.')
        s.setdefault('delegation_observations',{})[identity([rid,p['evidence_ref']],'DELEGATION-')]=deepcopy(p)
        request['usage']=request_usage(s,rid)
    elif e['event_type']=='DELEGATION_CLASSIFICATION_CORRECTED':
        observation=s.get('delegation_observations',{}).get(p['observation_id'])
        require(observation and observation['request_id']==rid and observation['execution_id']==p['execution_id']
            and observation['evidence_ref']==p['evidence_ref'] and observation.get('event_type')==p.get('original_event_type'),
            'USAGE_EVIDENCE_CONFLICT','Classification correction must bind an existing original observation.')
        raw=blob_get(p['evidence_ref']);require(sha(raw)==p['evidence_ref'],'ORIGINAL_BYTES_MISMATCH','Original classification evidence changed.')
        native=native_delegation_kind(json.loads(raw));classification='NATIVE_DELEGATION' if native else 'NOT_NATIVE_DELEGATION'
        require(p.get('classification')==classification and p.get('native_event_type')==native
                and p.get('classifier_revision')==DELEGATION_CLASSIFIER_REVISION and p.get('reason'),
                'USAGE_EVIDENCE_INVALID','Correction must follow the exact native event discriminator.')
        observation.update(classification=classification,classifier_revision=p['classifier_revision'])
        observation.setdefault('classification_correction_events',[]).append(e['event_id'])
        request['usage']=request_usage(s,rid)
    elif e['event_type']=='NATIVE_INTERNAL_OBSERVATION':
        require(s['tasks'][request['task_id']].get('actor_kind')=='MAIN','USAGE_EVIDENCE_INVALID','Native internal usage belongs to MAIN.')
        root=next((x for x in s.get('native_main_turns',{}).values() if x['request_id']==rid and x['turn_id']==p['root_turn_id'] and x['thread_id']==p['root_thread_id']),None)
        require(root and p['thread_id']!=p['root_thread_id'],'USAGE_EVIDENCE_CONFLICT','Internal observation requires exact admitted root lineage.')
        link=p['turn_id']
        for ref in p['lineage_evidence_refs']:
            raw=blob_get(ref);require(sha(raw)==ref,'ORIGINAL_BYTES_MISMATCH','Native lineage evidence differs.')
            native=loads_native(raw);params=native.get('params',{});turn=params.get('turn',{})
            require(native.get('method')=='turn/started' and turn.get('id')==link,'USAGE_EVIDENCE_CONFLICT','Native child turn lineage is incomplete.')
            if link==p['turn_id']:require(params.get('threadId')==p['thread_id'],'USAGE_EVIDENCE_CONFLICT','Child thread differs from lineage.')
            link=turn.get('rootTurnId')
        require(link==p['root_turn_id'],'USAGE_EVIDENCE_CONFLICT','Native child lineage does not reach the admitted root.')
        raw=blob_get(p['evidence_ref']);require(sha(raw)==p['evidence_ref'],'ORIGINAL_BYTES_MISMATCH','Internal native evidence differs.')
        native=loads_native(raw);params=native.get('params',{});phase=native_internal_phase(native)
        require(phase and p['phase']==phase and params.get('threadId')==p['thread_id'] and (params.get('turnId') or params.get('turn',{}).get('id'))==p['turn_id'],
                'USAGE_EVIDENCE_CONFLICT','Exact child lifecycle or usage evidence required.')
        incoming=native_internal_counts(native)
        require(incoming==p['counts'],'USAGE_EVIDENCE_CONFLICT','Internal counters must equal the observed native values.')
        key=identity([p['root_thread_id'],p['thread_id']],'INTERNAL-THREAD-')
        row=s.setdefault('backend_internal_usage',{}).setdefault(key,{'thread_id':p['thread_id'],'root_thread_id':p['root_thread_id'],
            'request_ids':[],'turns':{},'counts':counts(None),'evidence_refs':[],'conflicts':[],
            'semantics':'NATIVE_THREAD_CUMULATIVE','included_in_parent_total':'UNSPECIFIED_BY_NATIVE_CLIENT','add_to_parent_total':False})
        if rid not in row['request_ids']:row['request_ids'].append(rid)
        turn=row['turns'].setdefault(p['turn_id'],{'request_id':rid,'root_turn_id':p['root_turn_id'],'started':False,'completed':False,'failed':False,'lineage_evidence_refs':deepcopy(p['lineage_evidence_refs'])})
        require(turn['request_id']==rid,'USAGE_EVIDENCE_CONFLICT','One child turn cannot change root request attribution.')
        turn['started']|=phase=='STARTED';turn['completed']|=phase=='COMPLETED';turn['failed']|=phase=='FAILED'
        for field,value in incoming.items():
            if value is None:continue
            old=row['counts'][field]
            if old is not None and value<old:row['conflicts'].append({'field':field,'before':old,'observed':value,'evidence_ref':p['evidence_ref']})
            row['counts'][field]=max(old,value) if old is not None else value
        if p['evidence_ref'] not in row['evidence_refs']:row['evidence_refs'].append(p['evidence_ref'])
        row['usage_coverage']='COUNTER_OBSERVED_TERMINAL' if all(t['completed'] for t in row['turns'].values()) and row['counts']['total_tokens'] is not None else 'PARTIAL_OR_UNKNOWN'
        for owner in row['request_ids']:s['requests'][owner]['usage']=request_usage(s,owner)
    elif e['event_type']=='NATIVE_INTERNAL_LOG_CURSOR':
        old=s.setdefault('native_usage_cursors',{}).get(p['instance_id'],{})
        require(p['offset']>=old.get('offset',0),'USAGE_LOG_TRUNCATED','Native protocol cannot lose confirmed bytes.')
        s['native_usage_cursors'][p['instance_id']]=deepcopy(p)
    elif e['event_type']=='BACKEND_LOG_CURSOR':
        old=s.setdefault('usage_log_cursors',{}).get(rid,{})
        require(p['offset']>=old.get('offset',0),'USAGE_LOG_TRUNCATED','Backend log cannot lose confirmed bytes.')
        s['usage_log_cursors'][rid]=deepcopy(p)
    elif e['event_type']=='BACKEND_LOG_DIAGNOSTIC':
        # Diagnostics never erase a completion or a scientific capture.
        pass
    else:require(False,'USAGE_EVENT_INVALID','Unknown usage event.')
    s.setdefault('usage_events',{})[e['event_id']]=deepcopy(e);s['usage']=summary(s)
    # as_of is supplied by the read projection, not a self-referential commit.
    s['usage'].pop('as_of_commit',None)
    return s


def _decode_event(row,thread_id,turn_id,ordinal,native_baseline=None):
    method=row.get('method');params=row.get('params',{})
    if method:
        native_thread=params.get('threadId',thread_id);native_turn=params.get('turnId') or params.get('turn',{}).get('id') or turn_id
        if method=='turn/started':return {'phase':'STARTED','counts':None},native_thread,native_turn,ordinal+1
        if method=='turn/completed':return {'phase':'COMPLETED' if params.get('turn',{}).get('status')=='completed' else 'FAILED','counts':None},native_thread,native_turn,ordinal
        if method=='thread/tokenUsage/updated':
            mapping={'input_tokens':'inputTokens','output_tokens':'outputTokens','cached_input_tokens':'cachedInputTokens','reasoning_output_tokens':'reasoningOutputTokens','total_tokens':'totalTokens'}
            total=params.get('tokenUsage',{}).get('total',{});out={}
            for field,camel in mapping.items():
                value=total.get(camel);base=(native_baseline or {}).get(camel,0)
                out[field]=value-base if native_baseline is not None and type(value) is int and type(base) is int and value>=base else None
            return {'phase':'CHECKPOINT','counts':out},native_thread,native_turn,ordinal
        return None,thread_id,turn_id,ordinal
    kind=row.get('type');payload=row.get('msg',row)
    if kind=='event_msg':kind=payload.get('type')
    if kind in {'thread.started','session_meta'}:
        thread_id=row.get('thread_id',payload.get('id',thread_id));return None,thread_id,turn_id,ordinal
    if kind in {'turn.started','task_started'}:
        ordinal+=1;turn_id=row.get('turn_id',payload.get('turn_id',str(ordinal)))
        return {'phase':'STARTED','counts':None},thread_id,turn_id,ordinal
    if kind in {'turn.completed','task_complete'}:
        turn_id=row.get('turn_id',payload.get('turn_id',turn_id or '1'))
        return {'phase':'COMPLETED','counts':payload.get('usage',row.get('usage'))},thread_id,turn_id,ordinal
    if kind in {'turn.failed','error'}:return {'phase':'FAILED','counts':None},thread_id,turn_id or '1',ordinal
    if kind=='token_count':
        info=payload.get('info') or {};usage=info.get('total_token_usage',payload.get('usage'))
        return {'phase':'CHECKPOINT','counts':usage},thread_id,turn_id or '1',ordinal
    return None,thread_id,turn_id,ordinal


def ingest_log(store,request_id,execution_id,path=None,*,final=False):
    """Read complete bounded JSONL lines; no malformed usage drops a capture."""
    snapshot=store.read_snapshot();request=snapshot['requests'][request_id]
    expected=store.root/'runs'/request['task_id']/'events.jsonl'
    path=Path(path) if path is not None else expected
    require(path.absolute()==expected.absolute(),'USAGE_EVIDENCE_INVALID','Only this execution exact runner log can provide usage.')
    if not path.exists():return {'state':'NO_LOG','model_calls':0}
    native_info=expected.parent/'native-request.json';native_baseline=None
    if native_info.exists():
        info=json.loads(native_info.read_bytes())
        if info.get('baseline_known'):native_baseline=info.get('usage_baseline',{})
    cursor=snapshot.get('usage_log_cursors',{}).get(request_id,{})
    offset=cursor.get('offset',0);size=path.stat().st_size
    def diagnostic(code,detail):
        store.commit_usage(event('BACKEND_LOG_DIAGNOSTIC',{'schema':SCHEMA,'request_id':request_id,'execution_id':execution_id,
            'code':code,'detail':detail,'offset':offset}));return {'state':code,'model_calls':0}
    if size>MAX_LOG:return diagnostic('USAGE_LOG_LIMIT','Bounded original log exceeds 64 MiB; evidence is incomplete.')
    if size<offset:return diagnostic('USAGE_LOG_TRUNCATED','Original log shrank; previous observations were preserved.')
    digest=hashlib.sha256();thread_id=cursor.get('thread_id','unknown');turn_id=cursor.get('turn_id');ordinal=cursor.get('ordinal',0);observed=0
    with path.open('rb') as stream:
        remaining=offset
        while remaining:
            chunk=stream.read(min(262144,remaining));digest.update(chunk);remaining-=len(chunk)
        if cursor.get('prefix_sha256') and digest.hexdigest()!=cursor['prefix_sha256']:return diagnostic('USAGE_LOG_CHANGED','Previously observed log prefix changed.')
        while True:
            raw=stream.readline(MAX_LINE+1)
            if not raw:break
            if len(raw)>MAX_LINE:return diagnostic('USAGE_LINE_LIMIT','One backend line exceeded 1 MiB.')
            if not raw.endswith(b'\n'):
                if final:return diagnostic('USAGE_LOG_PARTIAL_TAIL','An incomplete terminal log line was preserved without inventing a completion.')
                break
            line_start=offset;digest.update(raw);offset+=len(raw)
            try:row=json.loads(raw)
            except (ValueError,UnicodeDecodeError):
                store.commit_usage(event('BACKEND_LOG_DIAGNOSTIC',{'schema':SCHEMA,'request_id':request_id,'execution_id':execution_id,
                    'code':'USAGE_LOG_INVALID_JSON','offset':line_start,'evidence_ref':store.put_blob(raw)}));continue
            if not isinstance(row,dict):continue
            item=row.get('params',{}).get('item',{}) if row.get('method') else row.get('item',row.get('msg',{}));kind=native_delegation_kind(row)
            if snapshot['tasks'][request['task_id']].get('actor_kind')=='MAIN' and kind is not None:
                store.commit_usage(event('NATIVE_DELEGATION_OBSERVATION',{'schema':SCHEMA,'request_id':request_id,'execution_id':execution_id,
                    'event_type':kind,'evidence_ref':store.put_blob(raw),'log_offset':line_start,
                    'child_thread_ids':item.get('receiverThreadIds',item.get('receiver_thread_ids',item.get('agent_ids',[]))),
                    'native_sender_thread_id':item.get('senderThreadId',item.get('sender_thread_id')),
                    'native_usage':item.get('usage'),'aggregation':'DO_NOT_ADD_WITHOUT_NATIVE_INCLUSION_SEMANTICS'}))
            parsed,thread_id,turn_id,ordinal=_decode_event(row,thread_id,turn_id,ordinal,native_baseline)
            if parsed:
                payload={'schema':SCHEMA,'request_id':request_id,'execution_id':execution_id,'thread_id':thread_id,'turn_id':str(turn_id),
                    'semantics':'TURN_CUMULATIVE','evidence_ref':store.put_blob(raw),'log_offset':line_start,**parsed}
                store.commit_usage(event('BACKEND_OBSERVATION',payload));observed+=1
    progress={'schema':SCHEMA,'request_id':request_id,'execution_id':execution_id,'offset':offset,'prefix_sha256':digest.hexdigest(),
              'thread_id':thread_id,'turn_id':turn_id,'ordinal':ordinal,'complete_log_sha256':digest.hexdigest() if final and offset==size else None}
    store.commit_usage(event('BACKEND_LOG_CURSOR',progress))
    return {'state':'RECORDED','observations':observed,'usage':request_usage(store.read_snapshot(),request_id),'model_calls':0}


def ingest_safely(store,request_id,execution_id,*,final=False):
    try:return ingest_log(store,request_id,execution_id,final=final)
    except (PMRSError,OSError,ValueError,KeyError) as exc:
        # This is a usage diagnostic boundary only, never an admission handler.
        try:
            store.commit_usage(event('BACKEND_LOG_DIAGNOSTIC',{'schema':SCHEMA,'request_id':request_id,'execution_id':execution_id,
                'code':getattr(exc,'code','USAGE_PARSE_FAILED'),'detail':str(exc)[:240]}))
        except (PMRSError,OSError,ValueError,KeyError):pass
        return {'state':'USAGE_EVIDENCE_INCOMPLETE','model_calls':0}


def loads_native(raw):
    value=json.loads(raw)
    return value.get('message',value)


def native_internal_phase(row):
    if row.get('method')=='turn/started':return 'STARTED'
    if row.get('method')=='thread/tokenUsage/updated':return 'CHECKPOINT'
    if row.get('method')=='turn/completed':return 'COMPLETED' if row.get('params',{}).get('turn',{}).get('status')=='completed' else 'FAILED'
    return None


def native_internal_counts(row):
    if row.get('method')!='thread/tokenUsage/updated':return counts(None)
    source=row.get('params',{}).get('tokenUsage',{}).get('total',{})
    return counts({key:source.get(native) for key,native in {'input_tokens':'inputTokens','output_tokens':'outputTokens',
        'cached_input_tokens':'cachedInputTokens','reasoning_output_tokens':'reasoningOutputTokens','total_tokens':'totalTokens'}.items()})


_NATIVE_USAGE_LOCK=threading.Lock()
def ingest_native_internal(store,instance_id):
    """Append zero-inference observations from the original native protocol.

    Child turn rootTurnId proves attribution even when its root already sealed.
    Root request counts and stage slots never include these observations.
    """
    if not _NATIVE_USAGE_LOCK.acquire(blocking=False):return {'state':'OBSERVER_BUSY','model_calls':0}
    try:
        s=store.read_snapshot();binding=s.get('native_main_bindings',{}).get(instance_id)
        if not binding:return {'state':'UNBOUND','model_calls':0}
        roots={x['turn_id']:x for x in s.get('native_main_turns',{}).values() if x['instance_id']==instance_id}
        if not roots:return {'state':'NO_ADMITTED_ROOT','model_calls':0}
        path=store.root/'execution'/'native-main'/instance_id/'protocol.jsonl'
        if not path.exists():return {'state':'NO_LOG','model_calls':0}
        cursor=s.get('native_usage_cursors',{}).get(instance_id,{})
        offset=cursor.get('offset',0);data=path.read_bytes();require(len(data)>=offset,'USAGE_LOG_TRUNCATED','Native protocol shrank.')
        require(not cursor.get('prefix_sha256') or sha(data[:offset])==cursor['prefix_sha256'],'USAGE_LOG_CHANGED','Native protocol prefix changed.')
        children=deepcopy(cursor.get('child_turns',{}));observed=0;position=offset;last_owner=next(reversed(roots.values()))
        for raw in data[offset:].splitlines(keepends=True):
            if not raw.endswith(b'\n'):break
            position+=len(raw)
            try:row=loads_native(raw)
            except (ValueError,UnicodeDecodeError):continue
            params=row.get('params',{});tid=params.get('threadId');turnid=params.get('turnId') or params.get('turn',{}).get('id')
            if tid==binding['thread_id']:continue
            phase=native_internal_phase(row)
            if not phase:continue
            if phase=='STARTED':
                parent=params.get('turn',{}).get('rootTurnId');parent_child=children.get(parent)
                if parent in roots:owner=roots[parent];lineage=[]
                elif parent_child:owner=roots.get(parent_child['root_turn_id']);lineage=parent_child['lineage_evidence_refs']
                else:continue
                if not owner:continue
                children[turnid]={'thread_id':tid,'root_turn_id':owner['turn_id'],'lineage_evidence_refs':[store.put_blob(raw),*lineage]}
            child=children.get(turnid)
            if not child or child['thread_id']!=tid:continue
            owner=roots.get(child['root_turn_id'])
            if not owner:continue
            last_owner=owner
            payload={'schema':SCHEMA,'request_id':owner['request_id'],'execution_id':owner['execution_id'],'instance_id':instance_id,
                'thread_id':tid,'turn_id':turnid,'root_thread_id':binding['thread_id'],'root_turn_id':owner['turn_id'],
                'lineage_evidence_refs':child['lineage_evidence_refs'],'evidence_ref':store.put_blob(raw),'phase':phase,'counts':native_internal_counts(row)}
            store.commit_usage(event('NATIVE_INTERNAL_OBSERVATION',payload));observed+=1
        if position>offset:
            store.commit_usage(event('NATIVE_INTERNAL_LOG_CURSOR',{'schema':SCHEMA,'request_id':last_owner['request_id'],'execution_id':last_owner['execution_id'],
                'instance_id':instance_id,'offset':position,'prefix_sha256':sha(data[:position]),'child_turns':children}))
        return {'state':'RECORDED','observations':observed,'model_calls':0}
    finally:_NATIVE_USAGE_LOCK.release()


def ingest_native_internal_safely(store,instance_id):
    try:return ingest_native_internal(store,instance_id)
    except (PMRSError,OSError,ValueError,KeyError) as exc:
        # A metering diagnostic must never suppress a requested Goal pause.
        try:
            s=store.read_snapshot();roots=[x for x in s.get('native_main_turns',{}).values() if x['instance_id']==instance_id]
            if roots:
                owner=roots[-1]
                store.commit_usage(event('BACKEND_LOG_DIAGNOSTIC',{'schema':SCHEMA,'request_id':owner['request_id'],'execution_id':owner['execution_id'],
                    'code':getattr(exc,'code','NATIVE_INTERNAL_USAGE_PARSE_FAILED'),'detail':str(exc)[:400],'source':'PERSISTENT_NATIVE_PROTOCOL'}))
        except (PMRSError,OSError,ValueError,KeyError):pass
        return {'state':'USAGE_EVIDENCE_INCOMPLETE','model_calls':0}
