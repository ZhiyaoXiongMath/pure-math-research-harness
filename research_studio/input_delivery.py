"""Append-only dynamic inputs and the atomic final exposure boundary."""
from copy import deepcopy
import secrets
from .util import canonical, identity, require, sha,loads

SCHEMA='pmrs.input-delivery/1'


def _supplements(snapshot,task,result,*,original_response=False):
    """Only exact fully returned bodies become native scientific supplements."""
    from .knowledge_access import allowed_refs
    if not isinstance(result,dict):return []
    item=result.get('attachment',result)
    if not isinstance(item,dict) or item.get('read_scope') not in {'EXACT_BODY','EXACT_REGISTERED_OCCURRENCE'}:return []
    ref=item.get('ref');require(ref in allowed_refs(snapshot,task),'KNOWLEDGE_FORBIDDEN','Exact supplement is outside the authorized view.')
    collection='records' if item['read_scope']=='EXACT_BODY' else 'sources'
    native=item.get('record' if collection=='records' else 'source') if original_response else snapshot[collection][ref]
    require(isinstance(native,dict),'ORIGINAL_BYTES_MISMATCH','The exact delivered native metadata is required.')
    digest=native.get('body_sha256',native.get('blob_hash'))
    require(isinstance(item.get('body'),str) and sha(item['body'].encode())==digest==item.get('body_sha256'),
            'ORIGINAL_BYTES_MISMATCH','A full exact body is required for a scientific input supplement.')
    status=item.get('status',{});supports={row['support_ref']:identity({k:v for k,v in row.items() if k!='support_ref'} if original_response else snapshot.get('supports',{}).get(row['support_ref']))
                                      for row in status.get('support',[]) if row.get('support_ref')}
    return [{'schema':'pmrs.input-supplement/1','kind':'record' if collection=='records' else 'source','ref':ref,
             'revision':item.get('revision',ref),'native_digest':identity(native),'body_sha256':digest,
             'read_scope':item['read_scope'],'support_guards':supports,'source':'EXACT_TOOL_BODY'}]


def _main_support_append_only(snapshot,task,ref,guard,delivered):
    """A later positive review does not unread MAIN's unchanged exact body.

    This grants no qualification and does not expose the new assessment. The
    original response authenticates the older support view. Stage read guards,
    scientific premises and independent review admission remain unchanged.
    """
    if task.get('actor_kind')!='MAIN' or not isinstance(delivered,dict) or identity(delivered)!=guard:return False
    current=snapshot.get('supports',{}).get(ref)
    if not current or current.get('needs_recheck') or not current.get('integrity_valid',True):return False
    derived={'qualification_refs','consumer_requirement','policy_digest'}
    if {k:v for k,v in delivered.items() if k not in derived}!={k:v for k,v in current.items() if k not in derived}:return False
    before=delivered.get('qualification_refs',[]);after=current.get('qualification_refs',[])
    if not isinstance(before,list) or not isinstance(after,list) or after[:len(before)]!=before or len(after)<=len(before):return False
    for field in ('consumer_requirement','policy_digest'):
        if delivered.get(field) is not None and delivered[field]!=current.get(field):return False
    if current.get('consumer_requirement') and identity(current['consumer_requirement'])!=current.get('policy_digest'):return False
    from . import assurance,relations
    roots={w['support_id'] for w in snapshot.get('withdrawals',{}).values() if w.get('active',True)}
    if ref in relations.affected_supports(snapshot,roots):return False
    if any(c.get('active',True) and c.get('statement_ref')==current.get('statement_ref') for c in snapshot.get('conflicts',{}).values()):return False
    for qid in after:
        q=snapshot.get('qualifications',{}).get(qid)
        a=snapshot.get('records',{}).get(q.get('assessment_ref')) if q else None
        if not a or a.get('kind')!='Assessment' or a['data'].get('verdict') not in {'SUPPORTED_WITHIN_SCOPE','INCONCLUSIVE'}:return False
        event,error=assurance._credential(snapshot,q,a,None)
        if error or not event or not event.get('independent') or current['argument_ref'] not in q.get('target_revision_hashes',[]):return False
    return True


def manifest(snapshot,request_id):
    # Confirmation is transport metadata.  A PREPARED result may already have
    # escaped, so both confirmed and unconfirmed entries bind the final capture.
    rows=[{k:deepcopy(v) for k,v in d.items() if k not in {'confirmed','confirmation_event'}}
          for d in snapshot.get('input_deliveries',{}).values() if d['request_id']==request_id]
    return sorted(rows,key=lambda x:x['sequence'])


def reduce_event(snapshot,event,blob_get):
    from .communication import bound_request,can_read
    s=deepcopy(snapshot);p=event['payload'];kind=event['event_type'];rid=p['request_id']
    if kind=='INPUT_DELIVERY_PREPARED':
        request,task=bound_request(s,rid,p['execution_id']);contract=task['communication_contract']
        raw=blob_get(p['response_ref']);require(sha(raw)==p['response_ref'] and len(raw)==p['bytes'],
                                             'ORIGINAL_BYTES_MISMATCH','Delivery must preserve the exact MCP response bytes.')
        response=loads(raw);content=loads(response['content'][0]['text'].encode())
        require(p.get('supplements',[])==_supplements(s,task,content.get('result',{})),
                'INPUT_DELIVERY_INVALID','Scientific supplements must match the exact exposed tool response.')
        rows=[d for d in s.get('input_deliveries',{}).values() if d['request_id']==rid]
        bound=contract['max_dynamic_input_tokens'];calls=contract['max_tool_calls']
        require(len(rows)<calls and sum(d['bytes'] for d in rows)+len(raw)<=bound,'DYNAMIC_INPUT_LIMIT','The frozen dynamic input allowance is exhausted.')
        trajectory=p.get('trajectory_bytes',0)
        require(type(trajectory) is int and trajectory>=0
                and sum(d.get('trajectory_bytes',0) for d in rows)+trajectory<=contract['tool_trajectory_reserve_tokens'],
                'DYNAMIC_TRAJECTORY_LIMIT','The frozen tool-argument and transport trajectory allowance is exhausted.')
        for mid in p['message_ids']:
            msg=s.get('research_messages',{}).get(mid)
            require(msg and can_read(s,task,msg),'COMMUNICATION_FORBIDDEN','Delivery cannot expose inaccessible message identities.')
        require(isinstance(p.get('exposure_domains'),list),'INPUT_DELIVERY_INVALID','Host exposure domains are required.')
        expected=sorted({domain for mid in p['message_ids'] for domain in s['research_messages'][mid]['exposure_domains']})
        require(expected==p['exposure_domains'],'COMMUNICATION_FORBIDDEN','The host derives delivery provenance.')
        row=deepcopy(p);row.update(sequence=max([d['sequence'] for d in rows],default=0)+1,confirmed=False)
        s.setdefault('input_deliveries',{})[row['delivery_id']]=row
    elif kind=='INPUT_DELIVERY_CONFIRMED':
        row=s.get('input_deliveries',{}).get(p['delivery_id'])
        require(row and row['request_id']==rid and row['execution_id']==p['execution_id'],
                'INPUT_DELIVERY_INVALID','Confirmation must bind the exact prepared delivery.')
        row.update(confirmed=True,confirmation_event=event['event_id'])
    elif kind=='INPUT_WINDOW_SEALED':
        request,task=bound_request(s,rid,p['execution_id'],active=False)
        old=s.get('input_windows',{}).get(rid)
        if old:
            require(old['execution_id']==p['execution_id'],'TASK_FENCED','Original input window belongs to another execution.');return s
        rows=manifest(s,rid)
        body={'schema':SCHEMA,'request_id':rid,'execution_id':p['execution_id'],
              'initial_manifest_hash':task.get('initial_manifest_hash',task['input_manifest_hash']),'deliveries':rows,
              'delivery_cutoff':max([d['sequence'] for d in rows],default=0)}
        digest=sha(canonical(body));window={'schema':SCHEMA,'request_id':rid,'execution_id':p['execution_id'],
            'sealed':True,'delivery_manifest_hash':digest,'input_window_seal':identity(body,'INPUT-SEAL-'),
            'delivery_cutoff':body['delivery_cutoff'],'manifest':body,'dynamic_input_bytes':sum(d['bytes'] for d in rows)}
        s.setdefault('input_windows',{})[rid]=window
    else:require(False,'INPUT_DELIVERY_INVALID','Unknown input event.')
    return s


def prepare(store,request_id,execution_id,tool_name,result,*,message_ids=(),is_error=False,trajectory_bytes=0):
    """Persist before stdout.  Call confirm only after the write has flushed."""
    from .communication import event,bound_request
    s=store.read_snapshot();_,task=bound_request(s,request_id,execution_id)
    did='DELIVERY-'+secrets.token_hex(16)
    payload={'delivery_id':did,'result':result}
    response={'content':[{'type':'text','text':canonical(payload).decode()}],'isError':bool(is_error)}
    raw=canonical(response);rows=[d for d in s.get('input_deliveries',{}).values() if d['request_id']==request_id]
    left=task['communication_contract']['max_dynamic_input_tokens']-sum(d['bytes'] for d in rows)
    if len(raw)>left-768 or len(rows)>=task['communication_contract']['max_tool_calls']-1:
        # One bounded terminal capacity response is itself exposure evidence.
        message=('This response does not fit the remaining frozen input window. Request a smaller page when available. '
                 'If more input is required, finish this turn with an explicit MAIN continuation need; the same Goal and cumulative budget remain. '
                 'No unseen body or message was read.' if task.get('actor_kind')=='MAIN' else
                 'No further dynamic input fits. Preserve incomplete coverage; finish using frozen evidence.')
        response={'content':[{'type':'text','text':canonical({'delivery_id':did,'error':'DYNAMIC_INPUT_LIMIT',
                    'remaining_input_bytes':max(0,left),'message':message}).decode()}],'isError':True}
        raw=canonical(response);message_ids=[]
    mids=sorted(set(message_ids));domains=sorted({d for mid in mids for d in s['research_messages'][mid]['exposure_domains']})
    response_content=loads(response['content'][0]['text'].encode())
    supplements=_supplements(s,task,response_content.get('result',{}))
    row={'schema':SCHEMA,'delivery_id':did,'request_id':request_id,'execution_id':execution_id,'tool_name':tool_name,
         'response_ref':store.put_blob(raw),'bytes':len(raw),'trajectory_bytes':trajectory_bytes,
         'message_ids':mids,'exposure_domains':domains,'supplements':supplements}
    store.commit_communication(event('INPUT_DELIVERY_PREPARED',row))
    return did,response


def confirm(store,request_id,execution_id,delivery_id):
    from .communication import event
    return store.commit_communication(event('INPUT_DELIVERY_CONFIRMED',{'request_id':request_id,'execution_id':execution_id,'delivery_id':delivery_id}))


def seal(store,request_id,execution_id):
    from .communication import event
    s=store.read_snapshot();task=s['tasks'][s['requests'][request_id]['task_id']]
    if not task.get('communication_contract'):return {}
    if not s.get('input_windows',{}).get(request_id):
        store.commit_communication(event('INPUT_WINDOW_SEALED',{'request_id':request_id,'execution_id':execution_id}))
    return capture_binding(store.read_snapshot(),request_id)


def capture_binding(snapshot,request_id):
    request=snapshot['requests'][request_id];task=snapshot['tasks'][request['task_id']]
    if not task.get('communication_contract'):return {}
    window=snapshot.get('input_windows',{}).get(request_id)
    require(window and window['sealed'],'INPUT_WINDOW_UNSEALED','Capture requires the final dynamic input manifest.')
    body=window['manifest']
    require(window.get('request_id')==request_id and window.get('execution_id')==request['execution_id']
            and body.get('request_id')==request_id and body.get('execution_id')==request['execution_id']
            and body.get('initial_manifest_hash')==task.get('initial_manifest_hash',task['input_manifest_hash'])
            and window.get('input_window_seal')==identity(body,'INPUT-SEAL-')
            and window.get('delivery_cutoff')==body.get('delivery_cutoff')==max([d['sequence'] for d in body['deliveries']],default=0),
            'ORIGINAL_BYTES_MISMATCH','Dynamic input seal does not bind this exact original task execution.')
    require(window['delivery_manifest_hash']==sha(canonical(window['manifest'])) and
            window['manifest']['deliveries']==manifest(snapshot,request_id),'ORIGINAL_BYTES_MISMATCH','Final dynamic input manifest differs.')
    return {k:window[k] for k in ('delivery_manifest_hash','input_window_seal','delivery_cutoff')}


def _supplied(snapshot,task,kind,blob_get=None,*,live=False):
    rid=task['request_id'];rows=[d for d in snapshot.get('input_deliveries',{}).values() if d['request_id']==rid]
    selected=[(d,item) for d in rows for item in d.get('supplements',[]) if item['kind']==kind]
    if not selected:return set()
    if live:
        # MAIN live dispatch occurs before the final capture seal. Only exact
        # already persisted tool deliveries of this still-active request may
        # extend its read set; scientific admission still requires the seal.
        from .communication import bound_request
        request=snapshot['requests'][rid]
        bound_request(snapshot,rid,request['execution_id'])
    else:capture_binding(snapshot,rid)
    result=set()
    for delivery,item in selected:
        exposed_supports={}
        if blob_get:
            raw=blob_get(delivery['response_ref']);require(sha(raw)==delivery['response_ref'],'ORIGINAL_BYTES_MISMATCH','Delivered response blob differs.')
            response=loads(raw);payload=loads(response['content'][0]['text'].encode());exposed=payload.get('result',{})
            require(item in _supplements(snapshot,task,exposed,original_response=True),'ORIGINAL_BYTES_MISMATCH','Exact scientific body and original support view were not present in the sealed response.')
            exposed=exposed.get('attachment',exposed)
            exposed_supports={row['support_ref']:{k:v for k,v in row.items() if k!='support_ref'} for row in exposed.get('status',{}).get('support',[]) if row.get('support_ref')}
        collection='records' if kind=='record' else 'sources';native=snapshot.get(collection,{}).get(item['ref'])
        require(native and identity(native)==item['native_digest'] and native.get('body_sha256',native.get('blob_hash'))==item['body_sha256'],
                'STALE_DYNAMIC_INPUT','The exact delivered native version has changed or disappeared.')
        require(all(identity(snapshot.get('supports',{}).get(ref))==guard or
                    _main_support_append_only(snapshot,task,ref,guard,exposed_supports.get(ref))
                    for ref,guard in item.get('support_guards',{}).items()),
                'STALE_DYNAMIC_INPUT','Support changed after dynamic scientific delivery; retain the capture as a candidate.')
        if blob_get:
            require(sha(blob_get(item['body_sha256']))==item['body_sha256'],'ORIGINAL_BYTES_MISMATCH','Native supplement source bytes differ.')
        result.add(item['ref'])
    return result


def supplied_records(snapshot,task,blob_get=None,*,live=False):return _supplied(snapshot,task,'record',blob_get,live=live)
def supplied_sources(snapshot,task,blob_get=None,*,live=False):return _supplied(snapshot,task,'source',blob_get,live=live)


def observed_main_dispatch_bindings(snapshot,task,blob_get=None,*,live=False):
    """Own duties actually returned by a confirmed, execution-bound dispatch.

    This proves MAIN observed the assignment, not its later state or results.
    It grants no scientific input, qualification or fresh global frontier.
    """
    if task.get('actor_kind')!='MAIN' or not task.get('communication_contract') or blob_get is None:return set()
    rid=task['request_id'];request=snapshot['requests'][rid]
    rows=[d for d in snapshot.get('input_deliveries',{}).values() if d.get('request_id')==rid
          and d.get('tool_name')=='main_stage_dispatch' and d.get('confirmed')]
    if not rows:return set()
    if live:
        from .communication import bound_request
        bound_request(snapshot,rid,request['execution_id'])
    else:capture_binding(snapshot,rid)
    bindings=set()
    for delivery in rows:
        require(delivery['execution_id']==request['execution_id'],'INPUT_DELIVERY_INVALID','Dispatch response belongs to the original MAIN execution.')
        raw=blob_get(delivery['response_ref'])
        require(sha(raw)==delivery['response_ref'] and len(raw)==delivery['bytes'],'ORIGINAL_BYTES_MISMATCH','Dispatch response bytes changed.')
        response=loads(raw)
        if response.get('isError'):continue
        payload=loads(response['content'][0]['text']);value=payload.get('result',{})
        receipt=snapshot.get('live_main_dispatches',{}).get(value.get('dispatch_id'))
        require(payload.get('delivery_id')==delivery['delivery_id'] and receipt
                and receipt['request_id']==value.get('request_id')==rid
                and receipt['proposal_id']==value.get('proposal_id')
                and receipt['work_bindings']==value.get('work_bindings'),
                'INPUT_DELIVERY_INVALID','Observed duties require the exact owning MAIN dispatch receipt.')
        for binding in value['work_bindings'].values():
            consumers=snapshot.get('obligations',{}).get(binding['oid'],{}).get('definition',{}).get('consumer_bindings',[])
            require(any(c['binding_id']==binding['bid'] and c['instance_id']==task['instance_id']
                        and c['mission_id']==task['mission_id'] for c in consumers),
                    'INPUT_DELIVERY_INVALID','Observed dispatch duty must belong to this instance and mission.')
            bindings.add(binding['bid'])
    return bindings
