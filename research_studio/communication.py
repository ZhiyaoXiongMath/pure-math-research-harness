"""Host-owned, request-scoped research communication.

Messages are candidate information, never scientific support.  In particular,
main's routing privilege does not allow its mixed context into independent work.
"""
from pmrh.domain.assurance import (
    independence_status,
)
from copy import deepcopy
from .util import canonical, identity, require, sha

SCHEMA='pmrs.communication/1'
MAPS=frozenset({'communication_events','collaboration_groups','research_messages',
                'message_acks','input_deliveries','input_windows','communication_impacts','communication_links','communication_link_revisions'})
KINDS={'QUESTION','LEAD','INTERMEDIATE_RESULT','COUNTEREVIDENCE','SOURCE_POINTER','WITHDRAWAL','STATUS_REQUEST'}
ISOLATED={'INDEPENDENT_EXPLORE','REVIEW_ISOLATED'}


def event(kind,payload):
    e={'actor':'host','capability_ref':'CAP-HOST','event_type':kind,'payload':deepcopy(payload)}
    e['event_id']=identity(e,'COMM-EVENT-');return e


def frozen_contract(snapshot,consumer,policy=None,*,initial_material_complete=False):
    policy=policy or {};stage=consumer.get('stage_id');role=consumer.get('role')
    basis=consumer.get('entry_basis',{})
    mode='COOPERATIVE'
    from .tasks import INDEPENDENT
    if role in INDEPENDENT or stage in {'P9','P12','D4','S4'} or role=='REPORT_SEMANTIC':mode='REVIEW_ISOLATED'
    elif stage=='P7' and role in {'LEARN','DIRECT'}:mode='INDEPENDENT_EXPLORE'
    if consumer.get('actor_kind')=='MAIN':mode='COOPERATIVE'
    values={'schema':SCHEMA,'mode':mode,'required':True,'task_main':True,
            'group_ref':consumer.get('communication_group',basis.get('collaboration_group_ref')),'max_messages':32,
            'cross_mission_main_contact':'STABLE_SAME_INSTANCE_MAIN_INBOX; original stage contracts remain frozen; late messages never imply a sealed request read them',
            'max_message_bytes':4096,'max_dynamic_input_tokens':8192,'max_tool_calls':24,
            'tool_trajectory_reserve_tokens':4096,'token_count_bound':'UTF8_BYTES',
            'allowed_supplements':['FROZEN_MATERIAL','CANDIDATE_HINT']}
    if consumer.get('actor_kind')=='MAIN':
        values.update(max_messages=1024,max_message_bytes=32768,max_dynamic_input_tokens=65536,max_tool_calls=1024,tool_trajectory_reserve_tokens=32768,
            capacity_basis='Top-level request context capacity only. No PMRS limit applies to native internal delegation.')
    same_mission=[t for t in snapshot.get('tasks',{}).values() if _same_scope(t,consumer)]
    initial_reading=(initial_material_complete and stage in {'P1','P2'} and consumer.get('actor_kind')!='MAIN'
                     and not values['group_ref'] and not any(t.get('actor_kind')=='MAIN' for t in same_mission)
                     and not any(snapshot['requests'][t['request_id']]['execution_state'] in {'PREPARED','RESERVED','SENT','UNKNOWN'}
                                 for t in same_mission))
    if initial_reading:
        values.update(profile='INITIAL_MATERIAL_READING',max_messages=8,max_message_bytes=512,max_dynamic_input_tokens=2048,
                      max_tool_calls=8,tool_trajectory_reserve_tokens=1024,
                      capacity_basis='Complete necessary frozen files; no prior main, group, or concurrent mission request. Status/questions remain available; larger new reading requires a later authorized material plan.')
    overrides=policy.get('communication',{})
    require(isinstance(overrides,dict) and set(overrides)<={'max_messages','max_message_bytes','max_dynamic_input_tokens','max_tool_calls','tool_trajectory_reserve_tokens'},
            'COMMUNICATION_CONTRACT_INVALID','Only finite communication capacity may be configured.')
    values.update(overrides)
    for key,limit in [('max_messages',4096),('max_message_bytes',32768),('max_dynamic_input_tokens',131072),('max_tool_calls',4096),('tool_trajectory_reserve_tokens',32768)]:
        require(type(values[key]) is int and 1<=values[key]<=limit,'COMMUNICATION_CONTRACT_INVALID','Finite '+key+' is required.')
    return values


def bound_request(snapshot,request_id,execution_id=None,*,active=True):
    request=snapshot.get('requests',{}).get(request_id)
    require(request is not None,'REQUEST_UNKNOWN','Original task request is required.')
    task=snapshot['tasks'][request['task_id']]
    require(task.get('communication_contract',{}).get('schema')==SCHEMA,'COMMUNICATION_NOT_FROZEN','Legacy tasks have no dynamic input permission.')
    if execution_id is not None:require(request['execution_id']==execution_id,'TASK_FENCED','Execution identity differs.')
    if active:
        require(request['execution_state'] in {'RESERVED','SENT'} and not request.get('fenced'),'TASK_FENCED','Only the current running request may call tools.')
        require(snapshot['instances'][request['instance_id']]['status']=='ACTIVE','TASK_FENCED','New tool delivery is paused.')
        require(not snapshot.get('input_windows',{}).get(request_id,{}).get('sealed'),'INPUT_WINDOW_SEALED','The final input window has closed.')
    return request,task


def _same_scope(a,b):
    return a.get('instance_id')==b.get('instance_id') and a.get('mission_id')==b.get('mission_id')


def _recipient(snapshot,sender,to):
    if to=='main':return {'kind':'MAIN','instance_id':sender['instance_id'],'main_session_id':snapshot.get('main_sessions',{}).get(sender['instance_id'],{}).get('session_id')}
    task=snapshot.get('tasks',{}).get(to)
    if task is None:
        req=snapshot.get('requests',{}).get(to,{})
        task=snapshot.get('tasks',{}).get(req.get('task_id'))
    require(task is not None,'COMMUNICATION_FORBIDDEN','Recipient is not a native task in this project.')
    if task.get('actor_kind')=='MAIN':
        require(sender['instance_id']==task['instance_id'],'COMMUNICATION_FORBIDDEN','MAIN inbox belongs to this instance only.')
        return _recipient(snapshot,sender,'main')
    main_link=sender.get('actor_kind')=='MAIN' or task.get('actor_kind')=='MAIN'
    require(sender['instance_id']==task['instance_id'],'COMMUNICATION_SCOPE_HANDOFF_REQUIRED',
            'Cross-instance knowledge and contact require an explicit native handoff and recipient authorization.')
    require(main_link or _same_scope(sender,task),'COMMUNICATION_FORBIDDEN','Worker peers require the same authorized mission and cooperation group.')
    if main_link:
        require(task.get('communication_contract'),'COMMUNICATION_RECIPIENT_INACTIVE','Recipient requires a native communication contract.')
    return {'kind':'TASK','task_id':task['task_id'],'request_id':task['request_id'],
            'instance_id':task['instance_id'],'mission_id':task['mission_id']}


def _group(snapshot,sender,recipient):
    for group in snapshot.get('collaboration_groups',{}).values():
        if group.get('state')=='ACTIVE' and {sender['request_id'],recipient['request_id']}<=set(group['request_ids']):return group
    return None


def _can_route(snapshot,sender,recipient):
    if recipient['kind']=='MAIN' or sender.get('actor_kind')=='MAIN':return True
    target=snapshot['tasks'][recipient['task_id']]
    if target.get('actor_kind')=='MAIN':return True
    link=snapshot.get('communication_links',{}).get(identity([sender['request_id'],recipient['request_id']],'LINK-'))
    if link and link.get('enabled'):return True
    group=_group(snapshot,sender,recipient)
    return bool(group and (group.get('allow_independence_loss') or sender['communication_contract']['mode']=='COOPERATIVE' and target.get('communication_contract',{}).get('mode')=='COOPERATIVE'))


def can_read(snapshot,task,message):
    recipient=message['recipient']
    if task['instance_id']!=message['instance_id']:return False
    if recipient['kind']=='MAIN':return task.get('actor_kind')=='MAIN'
    if not _same_scope(task,message) and message.get('channel')!='TASK_MAIN':return False
    return recipient.get('request_id')==task['request_id']


def _host_original_status(snapshot,sender,recipient):
    task=snapshot['tasks'].get(recipient.get('task_id'),{})
    original=task if sender.get('actor_kind')=='MAIN' and task.get('actor_kind')!='MAIN' else sender
    request=snapshot['requests'][original['request_id']]
    return canonical({'host_original_request_status':{'task_id':original['task_id'],'request_id':original['request_id'],
        'execution_id':request['execution_id'],'instance_id':original['instance_id'],'mission_id':original['mission_id'],
        'stage_id':original.get('stage_id'),'role':original.get('role'),'execution_state':request['execution_state']},
        'instruction':'Continue only the original frozen contract. Scientific transfer requires native scope authorization.'})


def exposure_domains(snapshot,request_id):
    request=snapshot['requests'][request_id];task=snapshot['tasks'][request['task_id']]
    domains=set()
    if task.get('communication_contract',{}).get('mode') in ISOLATED:domains.add(request_id)
    for delivery in snapshot.get('input_deliveries',{}).values():
        if delivery['request_id']==request_id:domains.update(delivery.get('exposure_domains',[]))
    # main has project-global mixed exposure even if it omits used/provenance.
    if task.get('actor_kind')=='MAIN':domains.add('MAIN_MIXED:'+task['instance_id'])
    return sorted(domains)


def _validate_message(snapshot,row,blob_get):
    request,sender=bound_request(snapshot,row['sender_request_id'],row['sender_execution_id'])
    require(row['sender_task_id']==sender['task_id'] and _same_scope(row,sender),'COMMUNICATION_FORBIDDEN','Sender identity must be host-bound.')
    recipient=_recipient(snapshot,sender,row['recipient'].get('request_id','main'))
    require(recipient==row['recipient'] and _can_route(snapshot,sender,recipient),'COMMUNICATION_FORBIDDEN','No authorized communication route.')
    require(row['kind'] in KINDS and row['kind']!='WITHDRAWAL','MESSAGE_INVALID','Use the append-only withdrawal operation.')
    require(row['exposure_domains']==exposure_domains(snapshot,request['request_id']),'COMMUNICATION_FORBIDDEN','Exposure provenance must be derived by the host.')
    contract=sender['communication_contract'];raw=blob_get(row['body_ref'])
    require(0<len(raw)<=contract['max_message_bytes'] and sha(raw)==row['body_ref'],'MESSAGE_LIMIT','Message body exceeds the frozen bound.')
    sent=[m for m in snapshot.get('research_messages',{}).values() if m['sender_request_id']==request['request_id']]
    require(len(sent)<contract['max_messages'],'MESSAGE_LIMIT','This request exhausted its finite message allowance.')
    target=snapshot['tasks'].get(recipient.get('task_id'),{})
    if target.get('communication_contract',{}).get('mode') in ISOLATED and not row.get('host_sanitized'):
        link=snapshot.get('communication_links',{}).get(identity([sender['request_id'],target['request_id']],'LINK-'),{})
        require((sender.get('actor_kind')=='MAIN' and row.get('allow_independence_loss') is True) or link.get('allow_independence_loss') is True or (_group(snapshot,sender,recipient) or {}).get('allow_independence_loss') is True,
                'INDEPENDENCE_EXPOSURE_REQUIRED','Scientific contact with an independent task requires MAIN explicit exposure authorization; the result loses independent review eligibility.')
    if target and row.get('host_sanitized'):
        require(sender.get('actor_kind')=='MAIN','COMMUNICATION_FORBIDDEN','Only MAIN may request host-generated neutral clarification.')
        if row['kind']=='STATUS_REQUEST':
            require(raw==b'HOST status request: continue the original frozen task and report any missing material or execution blocker to main.' and not row['record_refs'],
                    'COMMUNICATION_FORBIDDEN','Neutral status text must be host-generated.')
        else:
            reply=snapshot.get('research_messages',{}).get(row.get('reply_to'),{})
            require(row['kind']=='SOURCE_POINTER' and reply.get('sender_request_id')==target['request_id'] and row['record_refs']
                    and set(row['record_refs'])<=set(reply.get('record_refs',[])) and raw==canonical({'host_frozen_material_refs':row['record_refs']}),
                    'COMMUNICATION_FORBIDDEN','Neutral material replies may contain only exactly requested frozen references.')
    if target and sender.get('actor_kind')!='MAIN' and target.get('actor_kind')!='MAIN':
        link=snapshot.get('communication_links',{}).get(identity([sender['request_id'],target['request_id']],'LINK-'),{})
        if link:require(set(row['record_refs'])<=set(link.get('shared_refs',[])),'COMMUNICATION_FORBIDDEN','Attachments exceed MAIN specified link scope.')
    from .knowledge_access import allowed_refs
    require(set(row['record_refs'])<=allowed_refs(snapshot,sender),'COMMUNICATION_FORBIDDEN','A sender may cite only its authorized knowledge view.')
    if target:require(set(row['record_refs'])<=allowed_refs(snapshot,target),'COMMUNICATION_FORBIDDEN','Attachments exceed the recipient frozen scope.')


def apply_event(snapshot,e,blob_get=None):
    require(set(e)=={'event_id','actor','capability_ref','event_type','payload'} and e['actor']=='host'
            and snapshot.get('capabilities',{}).get(e['capability_ref'],{}).get('actor')=='host','AUTHORIZATION_REQUIRED','Communication is a typed host operation.')
    old=snapshot.get('communication_events',{}).get(e['event_id'])
    if old:
        require(old==e,'ALREADY_SETTLED_CONTENT_CONFLICT','Communication event identity differs.');return deepcopy(snapshot)
    s=deepcopy(snapshot);p=e['payload'];kind=e['event_type']
    if kind=='COMMUNICATION_LINKS_REVISED':
        _,main=bound_request(s,p['request_id'],p['execution_id'])
        require(main.get('actor_kind')=='MAIN','AUTHORIZATION_REQUIRED','Only the instance MAIN may revise task links.')
        require(p.get('reason') and 0<len(p['links'])<=64,'COMMUNICATION_GROUP_INVALID','A reason and bounded exact link update are required.')
        for link in p['links']:
            a=bound_request(s,link['from_request_id'],active=False)[1];b=bound_request(s,link['to_request_id'],active=False)[1]
            require(a['instance_id']==b['instance_id']==main['instance_id'] and a['request_id']!=b['request_id'],'COMMUNICATION_FORBIDDEN','Links stay inside this MAIN instance.')
            require(_same_scope(a,b),'COMMUNICATION_FORBIDDEN','Peer scientific contact must retain its authorized mission.')
            require(type(link['enabled']) is bool and type(link['allow_independence_loss']) is bool and link.get('reason'),'COMMUNICATION_GROUP_INVALID','Typed link state and reason required.')
            if (a['communication_contract']['mode'] in ISOLATED or b['communication_contract']['mode'] in ISOLATED) and link['enabled']:
                require(link['allow_independence_loss'],'INDEPENDENCE_EXPOSURE_REQUIRED','Opening isolated scientific cooperation requires an explicit MAIN independence-loss decision.')
            from .knowledge_access import allowed_refs
            require(set(link['shared_refs'])<=allowed_refs(s,a)&allowed_refs(s,b),'COMMUNICATION_FORBIDDEN','Shared references must be in both exact task scopes.')
            lid=identity([a['request_id'],b['request_id']],'LINK-')
            previous=s.get('communication_links',{}).get(lid,{})
            s.setdefault('communication_links',{})[lid]={**deepcopy(link),'link_id':lid,'revision':previous.get('revision',0)+1,'main_request_id':main['request_id'],'strategy_revision':p['strategy_revision'],'decision_ref':e['event_id']}
        s.setdefault('communication_link_revisions',{})[p['decision_id']]=deepcopy(p)
    elif kind=='COLLAB_GROUP_BOUND':
        row=deepcopy(p);refs=row['request_ids'];require(len(refs)>=2 and len(refs)==len(set(refs)),'COMMUNICATION_GROUP_INVALID','A collaboration group needs distinct exact requests.')
        members=[bound_request(s,r,active=False)[1] for r in refs]
        require(all(_same_scope(members[0],t) for t in members),'COMMUNICATION_FORBIDDEN','Group members require the same mission.')
        isolated=[t for t in members if t['communication_contract']['mode'] in ISOLATED]
        require(not isolated or all(t.get('allow_independence_loss') is True or t.get('entry_basis',{}).get('strategy',{}).get('allow_independence_loss') is True for t in isolated),
                'INDEPENDENCE_EXPOSURE_REQUIRED','MAIN must explicitly authorize scientific sharing for isolated group members.')
        row['allow_independence_loss']=bool(isolated)
        require(row.get('reason') and row.get('topic'),'COMMUNICATION_GROUP_INVALID','Scientific topic and reason are required.')
        previous=s.get('collaboration_groups',{}).get(row['group_id'])
        if previous:require(set(previous['request_ids'])<=set(refs) and previous['topic']==row['topic'],
                            'COMMUNICATION_GROUP_INVALID','An existing group may gain authorized members, not rewrite prior membership.')
        if not s.get('synthetic_test_only'):
            require(all(t['communication_contract'].get('group_ref')==row['group_id'] for t in members),
                    'COMMUNICATION_FORBIDDEN','A group must match every member original authorized collaboration assignment.')
        row.update(state='ACTIVE',schema=SCHEMA);s.setdefault('collaboration_groups',{})[row['group_id']]=row
    elif kind=='MESSAGE_PUBLISHED':
        row=deepcopy(p);_validate_message(s,row,blob_get)
        previous=s.get('research_messages',{}).get(row['message_id'])
        if previous:require(previous==row,'IDEMPOTENCY_CONFLICT','The send key was reused for different content.')
        else:
            row['created_seq']=len(s.get('research_messages',{}))+1;row['withdrawn']=False
            s.setdefault('research_messages',{})[row['message_id']]=row
    elif kind=='MESSAGE_WITHDRAWN':
        _,sender=bound_request(s,p['request_id'],p['execution_id'])
        msg=s.get('research_messages',{}).get(p['message_id'])
        require(msg is not None and msg['sender_request_id']==sender['request_id'],'COMMUNICATION_FORBIDDEN','Only the original sender may withdraw this message.')
        require(p.get('reason'),'MESSAGE_INVALID','Withdrawal requires a reason.')
        msg.update(withdrawn=True,withdrawal_reason=p['reason'],withdrawal_event=e['event_id'])
        for d in s.get('input_deliveries',{}).values():
            if msg['message_id'] in d.get('message_ids',[]):
                key=identity([msg['message_id'],d['request_id']],'IMPACT-')
                s.setdefault('communication_impacts',{})[key]={'message_id':msg['message_id'],'request_id':d['request_id'],
                    'state':'RECHECK_REQUIRED','possible_exposure':True,'withdrawal_event':e['event_id']}
    elif kind=='MESSAGE_ACKED':
        _,task=bound_request(s,p['request_id'],p['execution_id'])
        validate_dispositions(s,task,[{k:p[k] for k in ('message_id','disposition','reason','record_refs')}],require_seal=False)
        s.setdefault('message_acks',{})[p['ack_id']]=deepcopy(p)
    elif kind=='TOOL_CONTROL_REJECTED':
        bound_request(s,p['request_id'],p['execution_id'],active=False)
        require(p.get('scientific_input_delivered') is False
                and p.get('error_code') in {'TASK_FENCED','INPUT_WINDOW_SEALED','DYNAMIC_INPUT_LIMIT','DYNAMIC_TRAJECTORY_LIMIT'},
                'COMMUNICATION_EVENT_INVALID','Control rejection must not expose scientific inputs')
        from .util import loads
        response=loads(blob_get(p['response_ref']))
        require(response.get('isError') is True and len(canonical(response))<=1024
                and len(response.get('content',[]))==1 and response['content'][0].get('type')=='text'
                and loads(response['content'][0]['text'].encode()).get('error')==p['error_code'],
                'COMMUNICATION_EVENT_INVALID','Preserve the exact bounded control rejection')
    elif kind in {'INPUT_DELIVERY_PREPARED','INPUT_DELIVERY_CONFIRMED','INPUT_WINDOW_SEALED'}:
        from .input_delivery import reduce_event
        s=reduce_event(s,e,blob_get)
    else:require(False,'COMMUNICATION_EVENT_INVALID','Unknown communication event.')
    s.setdefault('communication_events',{})[e['event_id']]=deepcopy(e);return s


def bind_group(store,request_ids,topic,reason,*,group_id=None):
    refs=sorted(set(request_ids));gid=group_id or identity([refs,topic],'COLLAB-')
    store.commit_communication(event('COLLAB_GROUP_BOUND',{'group_id':gid,'request_ids':refs,'topic':topic,'reason':reason}))
    return store.read_snapshot()['collaboration_groups'][gid]


def send(store,request_id,execution_id,*,to,body,kind='QUESTION',idempotency_key,record_refs=(),reply_to=None,allow_independence_loss=False):
    s=store.read_snapshot();_,sender=bound_request(s,request_id,execution_id)
    require(isinstance(idempotency_key,str) and 0<len(idempotency_key)<=128,'MESSAGE_INVALID','A bounded request-specific send key is required.')
    recipient=_recipient(s,sender,to);require(_can_route(s,sender,recipient),'COMMUNICATION_FORBIDDEN','No authorized communication route.')
    require(isinstance(body,str) and body.strip(),'MESSAGE_INVALID','A message needs exact text.')
    target=s['tasks'].get(recipient.get('task_id'),{});sanitized=False;refs=list(record_refs)
    require(not allow_independence_loss or sender.get('actor_kind')=='MAIN','AUTHORIZATION_REQUIRED','Only MAIN may explicitly expose an independent stage to mixed scientific guidance.')
    if target.get('communication_contract',{}).get('mode') in ISOLATED and not allow_independence_loss and sender.get('actor_kind')=='MAIN':
        if kind=='STATUS_REQUEST':body='HOST status request: continue the original frozen task and report any missing material or execution blocker to main.';refs=[];sanitized=True
        elif kind=='SOURCE_POINTER':body=canonical({'host_frozen_material_refs':refs}).decode();sanitized=True
    mid=identity([request_id,idempotency_key],'MESSAGE-')
    row={'schema':SCHEMA,'message_id':mid,'sender_request_id':request_id,'sender_execution_id':execution_id,
         'sender_task_id':sender['task_id'],'instance_id':sender['instance_id'],'mission_id':sender['mission_id'],
         'recipient':recipient,'channel':'TASK_MAIN' if recipient['kind']=='MAIN' or sender.get('actor_kind')=='MAIN' or target.get('actor_kind')=='MAIN' else 'COLLABORATION',
         'kind':kind,'body_ref':store.put_blob(body.encode()),'record_refs':refs,'reply_to':reply_to,
         'evidence_state':'CANDIDATE_HINT','exposure_domains':exposure_domains(s,request_id),'host_sanitized':sanitized,
         'idempotency_key':idempotency_key,'allow_independence_loss':allow_independence_loss,
         'strategy_revision':s.get('strategies',{}).get(sender['instance_id'],{}).get('revision'),
         'late_after_seal':bool(target and s.get('input_windows',{}).get(target['request_id'],{}).get('sealed'))}
    old=s.get('research_messages',{}).get(mid)
    if old:
        require(all(old.get(k)==row[k] for k in ('recipient','kind','body_ref','record_refs','reply_to','idempotency_key','allow_independence_loss')),
                'IDEMPOTENCY_CONFLICT','Retry must preserve the exact original message.')
    if not old or store.history()[-1][1]['schema'] == 'pmrh.commit/2':
        original = {k:v for k,v in old.items() if k not in {'created_seq','withdrawn','withdrawal_reason','withdrawal_event'}} if old else row
        store.commit_communication(event('MESSAGE_PUBLISHED',original))
    return {'message_id':mid,'state':'WITHDRAWN' if old and old.get('withdrawn') else 'LATE_AFTER_SEAL' if row['late_after_seal'] else 'QUEUED','evidence_state':'CANDIDATE_HINT'}


def inbox(store,request_id,execution_id,*,cursor=0,limit=8):
    s=store.read_snapshot();_,task=bound_request(s,request_id,execution_id)
    require(type(cursor) is int and cursor>=0 and type(limit) is int and 1<=limit<=16,'MESSAGE_INVALID','Bounded inbox page required.')
    rows=[]
    for msg in sorted(s.get('research_messages',{}).values(),key=lambda x:x['created_seq']):
        if msg['created_seq']<=cursor or not can_read(s,task,msg):continue
        # No inaccessible title or summary is ever built.
        summary=('Withdrawn: '+msg.get('withdrawal_reason','')) if msg.get('withdrawn') else store.read_blob(msg['body_ref']).decode()[:160]
        rows.append({'message_id':msg['message_id'],'sequence':msg['created_seq'],'sender_task_id':msg['sender_task_id'],
                     'kind':msg['kind'],'summary':summary,'withdrawn':msg['withdrawn'],'evidence_state':msg['evidence_state']})
        if len(rows)>=limit:break
    notices=[deepcopy(x) for x in s.get('communication_impacts',{}).values() if x['request_id']==request_id]
    return {'messages':rows,'withdrawals':notices[:16],'cursor':rows[-1]['sequence'] if rows else cursor}


def read_message(store,request_id,execution_id,message_id,*,attachment_ref=None):
    s=store.read_snapshot();_,task=bound_request(s,request_id,execution_id);msg=s.get('research_messages',{}).get(message_id)
    require(msg is not None and can_read(s,task,msg),'COMMUNICATION_FORBIDDEN','Message is not in this request inbox.')
    if msg.get('withdrawn'):return {'message_id':message_id,'state':'WITHDRAWN','reason':msg['withdrawal_reason']}
    if attachment_ref is not None:
        require(attachment_ref in msg['record_refs'],'COMMUNICATION_FORBIDDEN','Attachment is not an exact message reference.')
        from .knowledge_access import get
        return {'message_id':message_id,'attachment':get(store,attachment_ref,task=task)}
    return {'message_id':message_id,'body':store.read_blob(msg['body_ref']).decode(),'body_sha256':msg['body_ref'],
            'record_refs':msg['record_refs'],'kind':msg['kind'],'evidence_state':msg['evidence_state'],'sender_task_id':msg['sender_task_id']}


def ack(store,request_id,execution_id,*,message_id,disposition,reason,record_refs=()):
    p={'request_id':request_id,'execution_id':execution_id,'message_id':message_id,'disposition':disposition,'reason':reason,'record_refs':list(record_refs)}
    p['ack_id']=identity(p,'ACK-');store.commit_communication(event('MESSAGE_ACKED',p));return {'ack_id':p['ack_id'],'disposition':disposition}


def withdraw(store,request_id,execution_id,message_id,reason):
    store.commit_communication(event('MESSAGE_WITHDRAWN',{'request_id':request_id,'execution_id':execution_id,'message_id':message_id,'reason':reason}))
    return {'message_id':message_id,'state':'WITHDRAWN'}


def validate_dispositions(snapshot,task,items,resolved_refs=None,*,require_seal=True):
    require(isinstance(items,list),'RESPONSE_SCHEMA_INVALID','message_dispositions must be an array.')
    request_id=task['request_id'];deliveries=[d for d in snapshot.get('input_deliveries',{}).values() if d['request_id']==request_id]
    exposed={m for d in deliveries for m in d.get('message_ids',[])};seen=set()
    if items and require_seal:require(snapshot.get('input_windows',{}).get(request_id,{}).get('sealed'),'INPUT_WINDOW_UNSEALED','Dispositions require the captured input window.')
    for row in items:
        require(set(row)=={'message_id','disposition','reason','record_refs'} and row['disposition'] in {'VIEWED','USED','REJECTED','NEEDS_CLARIFICATION'}
                and isinstance(row['reason'],str) and row['reason'].strip() and isinstance(row['record_refs'],list),
                'RESPONSE_SCHEMA_INVALID','Typed message disposition required.')
        require(row['message_id'] in exposed and row['message_id'] not in seen,'MESSAGE_NOT_DELIVERED','A disposition must identify a distinct actually or possibly delivered message.');seen.add(row['message_id'])
        if row['disposition']=='USED':
            message=snapshot['research_messages'][row['message_id']]
            require(not message.get('withdrawn'),'WITHDRAWN_MESSAGE_DEPENDENCY','A withdrawn hint cannot remain an adopted premise.')
            require(row['record_refs'],'MESSAGE_DEPENDENCY_REQUIRED','Used hints must identify the resulting reconstructed records or explicit premises.')
        if resolved_refs is not None:
            available=set(snapshot.get('records',{}))|set(resolved_refs)
            require(set(row['record_refs'])<=available,'INCOMPLETE_CONTEXT','Message disposition references missing scientific records.')
    if require_seal:
        unresolved={x['message_id'] for x in snapshot.get('communication_impacts',{}).values() if x['request_id']==request_id}
        handled={x['message_id'] for x in items if x['disposition'] in {'REJECTED','NEEDS_CLARIFICATION'}}
        require(unresolved<=handled,'WITHDRAWN_MESSAGE_UNRESOLVED','The final response must explicitly dispose of withdrawn possible inputs.')


def view(store,instance_id=None):
    s=store.read_snapshot();messages=[m for m in s.get('research_messages',{}).values() if not instance_id or m['instance_id']==instance_id]
    requests={r['request_id'] for r in s.get('requests',{}).values() if not instance_id or r['instance_id']==instance_id}
    return {'as_of_commit':s['knowledge_commit'],'model_calls':0,'messages':[dict(deepcopy(m),body_preview=store.read_blob(m['body_ref']).decode()[:320]) for m in messages[-64:]],
            'message_count':len(messages),'groups':[deepcopy(g) for g in s.get('collaboration_groups',{}).values() if set(g['request_ids'])&requests],
            'delivery_count':sum(d['request_id'] in requests for d in s.get('input_deliveries',{}).values()),
            'confirmed_delivery_count':sum(d['request_id'] in requests and d['confirmed'] for d in s.get('input_deliveries',{}).values()),
            'ack_count':sum(a['request_id'] in requests for a in s.get('message_acks',{}).values()),
            'seals':[{'request_id':rid,**{k:w[k] for k in ('delivery_manifest_hash','delivery_cutoff','dynamic_input_bytes')}} for rid,w in s.get('input_windows',{}).items() if rid in requests],
            'withdrawal_impacts':[deepcopy(x) for x in s.get('communication_impacts',{}).values() if x['request_id'] in requests]}


def revise_links(store,request_id,execution_id,links,reason,idempotency_key):
    s=store.read_snapshot();_,main=bound_request(s,request_id,execution_id)
    require(main.get('actor_kind')=='MAIN','AUTHORIZATION_REQUIRED','Only MAIN may revise communication links.')
    require(isinstance(idempotency_key,str) and 0<len(idempotency_key)<=128,'MESSAGE_INVALID','Stable decision key required.')
    rows=[]
    for item in links:
        def recipient(ref):
            target=_recipient(s,main,ref);require(target['kind']=='TASK','COMMUNICATION_GROUP_INVALID','Peer links require exact stage task IDs.');return target['request_id']
        a=recipient(item['from_task_id']);b=recipient(item['to_task_id'])
        pairs=[(a,b),(b,a)] if item.get('bidirectional') else [(a,b)]
        rows.extend({'from_request_id':x,'to_request_id':y,'enabled':item.get('enabled',True),'shared_refs':item.get('shared_refs',[]),
            'reason':item.get('reason',reason),'allow_independence_loss':item.get('allow_independence_loss',False)} for x,y in pairs)
    did=identity([request_id,idempotency_key],'LINK-DECISION-')
    payload={'decision_id':did,'request_id':request_id,'execution_id':execution_id,'links':rows,'reason':reason,
        'strategy_revision':s.get('strategies',{}).get(main['instance_id'],{}).get('revision'),'idempotency_key':idempotency_key}
    old=s.get('communication_link_revisions',{}).get(did)
    if old:require(old==payload,'IDEMPOTENCY_CONFLICT','Communication decision key already has different content.')
    else:store.commit_communication(event('COMMUNICATION_LINKS_REVISED',payload))
    return {'decision_id':did,'links':rows,'state':'APPLIED','independence':'Scientific deliveries record exposure; disabling a link never erases prior exposure.'}
