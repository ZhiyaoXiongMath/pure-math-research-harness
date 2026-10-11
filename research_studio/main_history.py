"""Exact versioned MAIN history navigation; never scientific read qualification."""
from copy import deepcopy
from urllib.parse import parse_qs
from .util import canonical,sha,require

PREFIX='MAIN_HISTORY/'
COLLECTIONS={'tasks','requests','obligations','strategy_proposals','research_clocks','research_routes','effective_guidance','instance_tasks','instance_obligations'}


def owns_obligation(snapshot,row,iid):
    d=row['definition']
    if any(c.get('instance_id')==iid for c in d['consumer_bindings']):return True
    if d['consumer_bindings']:return False
    origin=d.get('created_by','')
    return any(r.get('instance_id')==iid and r.get('acceptance_state')=='ACCEPTED' and origin=='CHANGE-'+str(r.get('capture_ref')) for r in snapshot.get('requests',{}).values())


def document(snapshot,collection,key,iid):
    require(collection in COLLECTIONS,'KNOWLEDGE_FORBIDDEN','Unsupported MAIN history collection.')
    if collection=='effective_guidance':
        require(key==iid,'KNOWLEDGE_FORBIDDEN','Guidance belongs to this instance.')
        from .research_audit import effective_guidance
        return effective_guidance(snapshot,iid)
    if collection in {'instance_tasks','instance_obligations'}:
        require(key==iid,'KNOWLEDGE_FORBIDDEN','History index belongs to this instance.')
        if collection=='instance_tasks':return {k:deepcopy(t) for k,t in snapshot.get('tasks',{}).items() if t['instance_id']==iid}
        return {k:deepcopy(o) for k,o in snapshot.get('obligations',{}).items() if owns_obligation(snapshot,o,iid)}
    row=snapshot.get(collection,{}).get(key)
    require(row is not None,'KNOWLEDGE_UNKNOWN','Exact native history entry is unavailable.')
    owned=owns_obligation(snapshot,row,iid) if collection=='obligations' else row.get('instance_id')==iid
    require(owned,'KNOWLEDGE_FORBIDDEN','MAIN history cannot cross instances.')
    return deepcopy(row)


def reference(snapshot,collection,key,iid):
    row=document(snapshot,collection,key,iid);raw=canonical(row)
    return {'ref':PREFIX+snapshot['knowledge_commit']+'/'+collection+'/'+key,
            'canonical_sha256':sha(raw),'utf8_bytes':len(raw),'read_with':'knowledge_history',
            'read_scope':'NATIVE_METADATA_NAVIGATION_NOT_SCIENTIFIC_BODY'}


def get(store,ref,*,task):
    require(task and task.get('actor_kind')=='MAIN','KNOWLEDGE_FORBIDDEN','Only the owning MAIN can read its native history.')
    path,_,query=ref.partition('?');parts=path.split('/')
    require(len(parts)==4 and parts[0]=='MAIN_HISTORY' and len(parts[1])==64,'KNOWLEDGE_QUERY_INVALID','Use the exact versioned MAIN_HISTORY reference.')
    try:options=parse_qs(query,strict_parsing=True) if query else {}
    except ValueError:require(False,'KNOWLEDGE_QUERY_INVALID','History query must use start and length assignments.')
    require(set(options)<={'start','length'} and all(len(v)==1 for v in options.values()),'KNOWLEDGE_QUERY_INVALID','Only start and length history pagination are accepted.')
    try:start=int(options.get('start',['0'])[0]);length=int(options.get('length',['4096'])[0])
    except ValueError:require(False,'KNOWLEDGE_QUERY_INVALID','History pagination uses integers.')
    require(start>=0 and 1<=length<=8192,'KNOWLEDGE_QUERY_INVALID','Use a bounded 1–8192 character page.')
    historical=store.read_snapshot(parts[1]);iid=task['instance_id']
    require(iid in historical.get('instances',{}),'KNOWLEDGE_FORBIDDEN','Instance did not exist in this history snapshot.')
    raw=canonical(document(historical,parts[2],parts[3],iid));text=raw.decode();require(start<=len(text),'KNOWLEDGE_QUERY_INVALID','History offset exceeds the exact document.')
    end=min(len(text),start+length);body=text[start:end]
    return {'ref':path,'as_of_commit':parts[1],'collection':parts[2],'native_id':parts[3],
        'canonical_sha256':sha(raw),'utf8_bytes':len(raw),'character_range':[start,end],'character_count':len(text),
        'body':body,'chunk_utf8_sha256':sha(body.encode()),'complete':start==0 and end==len(text),
        'next_ref':path+'?start='+str(end)+'&length='+str(length) if end<len(text) else None,
        'read_scope':'NATIVE_METADATA_NAVIGATION_NOT_SCIENTIFIC_BODY',
        'scientific_use':'Historical metadata is not a premise, support qualification, or full scientific-body read. Use knowledge_get on the exact record/source for scientific evidence; its actual delivery and current support guards apply.'}
