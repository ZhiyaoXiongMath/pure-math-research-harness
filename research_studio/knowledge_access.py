"""One bounded native knowledge read service for UI and request-scoped tools.

The cache contains only navigation text.  Authority, visibility and withdrawals
are always read from the current native snapshot before producing any snippet.
"""
from copy import deepcopy
import re
import threading
from .util import canonical,require,identity,safe_path

_CACHE={}
_LOCK=threading.Lock()
MAX_INDEX=4096
NAVIGATION_PREFIX_BYTES=2048


def _initial_refs(task):
    return {x['ref'] for x in task.get('input_manifest',[]) if 'ref' in x}|set(task.get('source_refs',[]))|set(task.get('target_refs',[]))


def allowed_refs(snapshot,task=None):
    allrefs=set(snapshot.get('records',{}))|set(snapshot.get('sources',{}))
    if task is None:return allrefs
    initial=_initial_refs(task)
    # Frozen tasks also retain read_set even where only the manifest hash was
    # kept in older layouts.
    initial.update(r['record_ref'] for r in task.get('read_set',[]) if 'record_ref' in r)
    initial.update(task.get('material_source_refs',[]))
    if task.get('communication_contract',{}).get('mode') in {'INDEPENDENT_EXPLORE','REVIEW_ISOLATED'}:return initial&allrefs
    result=set(initial)
    for producer in snapshot.get('production_events',{}).values():
        origin=snapshot.get('tasks',{}).get(producer.get('task_id'),{})
        if origin.get('instance_id')!=task.get('instance_id') or origin.get('mission_id')!=task.get('mission_id'):continue
        if task.get('actor_kind')!='MAIN' and origin.get('communication_contract',{}).get('mode') in {'INDEPENDENT_EXPLORE','REVIEW_ISOLATED'}:continue
        result.add(producer.get('record_ref'))
    # Source visibility follows the same instance's actual frozen task packets;
    # a project library by itself does not authorize every project source.
    if task.get('actor_kind')=='MAIN':
        for t in snapshot.get('tasks',{}).values():
            if t.get('instance_id')==task.get('instance_id') and t.get('mission_id')==task.get('mission_id'):result|=_initial_refs(t)
    from .relations import premise_closure
    valid=result&allrefs
    if valid:valid|=premise_closure(valid,snapshot)
    if task.get('actor_kind')!='MAIN':
        from .context import _source_tainted
        valid={ref for ref in valid if not _source_tainted(ref,snapshot)}
    return valid&allrefs


def scoped_refs(snapshot,task=None,instance_id=None):
    refs=allowed_refs(snapshot,task)
    if not instance_id:return refs
    instance=snapshot.get('instances',{}).get(instance_id);require(instance,'INSTANCE_UNKNOWN',instance_id)
    if task:
        require(instance_id==task['instance_id'],'KNOWLEDGE_FORBIDDEN','No cross-instance knowledge read.');return refs
    relevant={instance.get('target_ref')}|set(snapshot.get('sources',{}))
    for frozen in snapshot.get('tasks',{}).values():
        if frozen.get('instance_id')==instance_id:relevant|=_initial_refs(frozen)
    relevant|={p.get('record_ref') for p in snapshot.get('production_events',{}).values()
               if snapshot.get('tasks',{}).get(p.get('task_id'),{}).get('instance_id')==instance_id}
    from .relations import premise_closure
    return refs&(relevant|premise_closure(relevant&refs,snapshot))


def _partial_refs(task):
    return {item['ref'] for item in (task or {}).get('input_manifest',[]) if item.get('body_coverage')}


def _record_status(snapshot,ref,task=None):
    from . import relations
    supports=[{'support_ref':key,**deepcopy(row)} for key,row in snapshot.get('supports',{}).items()
              if ref in (row.get('statement_ref'),row.get('argument_ref'),row.get('target_ref')) or ref in row.get('target_refs',[])]
    edges=[deepcopy(row) for row in relations.edges(snapshot) if ref in (row.get('source_ref'),row.get('target_ref'))]
    if task:
        allowed=allowed_refs(snapshot,task)
        edges=[row for row in edges if {row.get('source_ref'),row.get('target_ref')}<=allowed]
        if task.get('communication_contract',{}).get('mode') in {'INDEPENDENT_EXPLORE','REVIEW_ISOLATED'}:
            frozen={support for entry in task.get('read_set',[]) if entry.get('record_ref')==ref for support in entry.get('required_support_refs',[])}
            supports=[row for row in supports if row['support_ref'] in frozen]
    withdrawn=any(row.get('state') in {'WITHDRAWN','INVALIDATED'} or row.get('status')=='WITHDRAWN' for row in supports)
    return {'support':supports,'relations':edges,'withdrawn_support_present':withdrawn,
            'qualification':'CONSUMER_SPECIFIC; message and admission do not grant support'}


def get(store,ref,*,task=None,instance_id=None):
    s=store.read_snapshot();require(ref in scoped_refs(s,task,instance_id),'KNOWLEDGE_FORBIDDEN','Reference is outside the authorized knowledge view.')
    require(ref not in _partial_refs(task),'KNOWLEDGE_SCOPE_LIMIT',
            'Only declared frozen ranges are authorized for this reference. Read their exact material files; a full-body tool read would silently widen the frozen scope.')
    if task:
        from . import resources
        row=s.get('records',{}).get(ref) or s['sources'][ref]
        digest=row.get('body_sha256',row.get('blob_hash'))
        require(resources.blob_info(store,digest)['bytes']<=task['communication_contract']['max_dynamic_input_tokens'],
                'DYNAMIC_INPUT_LIMIT','The exact body exceeds the frozen dynamic allowance. Use frozen material or an authorized material plan; no body was truncated.')
    if ref in s.get('records',{}):
        row=s['records'][ref];body=store.read_blob(row['body_sha256']).decode()
        return {'kind':'RECORD','ref':ref,'revision':ref,'record':deepcopy(row),'body':body,'body_sha256':row['body_sha256'],
                'status':_record_status(s,ref,task),'index_as_of':s['knowledge_commit'],'read_scope':'EXACT_BODY'}
    row=s['sources'][ref];raw=store.read_blob(row['blob_hash'])
    try:body=raw.decode()
    except UnicodeDecodeError:
        require(False,'SOURCE_TEXT_UNAVAILABLE','This source is binary. Read a registered exact extracted-text occurrence.')
    return {'kind':'SOURCE','ref':ref,'revision':row.get('revision',ref),'source':deepcopy(row),'body':body,'body_sha256':row['blob_hash'],
            'index_as_of':s['knowledge_commit'],'read_scope':'EXACT_REGISTERED_OCCURRENCE'}


def _navigation(store,snapshot,refs):
    key=(str(store.root),snapshot['knowledge_commit']);cached=_CACHE.get(key)
    if cached is None:
        cached={}
        # Build incrementally on visible demand, not by reading hidden bodies.
        with _LOCK:
            if len(_CACHE)>=8:_CACHE.pop(next(iter(_CACHE)))
            _CACHE[key]=cached
    for ref in sorted(refs)[:MAX_INDEX]:
        if ref not in cached:
            row=snapshot.get('records',{}).get(ref) or snapshot['sources'][ref]
            h=row.get('body_sha256',row.get('blob_hash'))
            # Search is explicitly prefix navigation, not proof delivery. Never
            # load an arbitrarily large native body to create a short snippet.
            with safe_path(store.root,'blobs/'+h).open('rb') as source:raw=source.read(NAVIGATION_PREFIX_BYTES)
            text=raw.decode(errors='replace')
            cached[ref]={'text':text,'kind':row.get('kind','SOURCE'),'hash':h}
    return cached


def search(store,query='',*,task=None,instance_id=None,kind=None,target_ref=None,route_ref=None,limit=8,cursor=0):
    require(isinstance(query,str) and len(query)<=512 and type(limit) is int and 1<=limit<=20
            and type(cursor) is int and cursor>=0,'KNOWLEDGE_QUERY_INVALID','Use a bounded native search.')
    s=store.read_snapshot();refs=scoped_refs(s,task,instance_id)
    partial=_partial_refs(task)
    nav=_navigation(store,s,refs-partial);terms=set(re.findall(r'\w+',query.lower()));rows=[]
    for ref in refs:
        item=nav.get(ref) if ref not in partial else {'text':'','kind':s.get('records',{}).get(ref,{}).get('kind','SOURCE'),
                                                      'hash':(s.get('records',{}).get(ref) or s['sources'][ref]).get('body_sha256',(s.get('sources',{}).get(ref) or {}).get('blob_hash'))}
        if not item or kind and item['kind']!=kind:continue
        record=s.get('records',{}).get(ref,{})
        if target_ref and ref!=target_ref and target_ref not in canonical(record).decode():continue
        score=len(terms&set(re.findall(r'\w+',item['text'].lower())))
        if terms and not score:continue
        rows.append({'kind':item['kind'],'ref':ref,'revision':ref,'body_sha256':item['hash'],'excerpt':item['text'][:180],
                     'score':score,'status':_record_status(s,ref,task) if ref in s.get('records',{}) else {'source_only':True},
                     'reason':'Frozen partial material; full-body navigation is excluded' if ref in partial else 'Visible exact native reference; keyword navigation only'})
    rows.sort(key=lambda x:(-x['score'],x['ref']))
    # Route/attempt indexes are typed navigation, never scientific evidence.
    if task is None or task.get('actor_kind')=='MAIN':
        for collection in ('routes','strategy_routes','attempt_accounts','incidents'):
            for ref,row in list(s.get(collection,{}).items())[:MAX_INDEX]:
                if task and row.get('instance_id') not in {None,task['instance_id']}:continue
                if instance_id and row.get('instance_id') not in {None,instance_id}:continue
                if route_ref and ref!=route_ref:continue
                text=canonical(row).decode()
                if terms and not any(t in text.lower() for t in terms):continue
                rows.append({'kind':collection.upper(),'ref':ref,'revision':identity(row),'excerpt':text[:180],'reason':'Organizational navigation; no proof qualification'})
    return {'results':rows[cursor:cursor+limit],'cursor':cursor+min(limit,max(0,len(rows)-cursor)),
            'index_as_of':s['knowledge_commit'],'index_state':'BOUNDED_NATIVE','more':cursor+limit<len(rows),
            'indexed_reference_limit':MAX_INDEX,'navigation_prefix_bytes':NAVIGATION_PREFIX_BYTES,'coverage':'BOUNDED_PREFIX_NAVIGATION_ONLY'}


def dependencies(store,ref,*,task=None,instance_id=None):
    s=store.read_snapshot();allowed=scoped_refs(s,task,instance_id);require(ref in allowed,'KNOWLEDGE_FORBIDDEN','Reference is outside the authorized view.')
    from .relations import edges
    rows=[deepcopy(x) for x in edges(s) if x.get('source_ref')==ref and x.get('target_ref') in allowed]
    return {'ref':ref,'dependencies':rows[:64],'more':len(rows)>64,'index_as_of':s['knowledge_commit']}


def history(store,ref,*,task=None,instance_id=None):
    if isinstance(ref,str) and ref.startswith('MAIN_HISTORY/'):
        from .main_history import get as get_main_history
        return get_main_history(store,ref,task=task)
    s=store.read_snapshot();allowed=scoped_refs(s,task,instance_id);require(ref in allowed,'KNOWLEDGE_FORBIDDEN','Reference is outside the authorized view.')
    objects=[{'object_id':key,'selected_revision':row.get('selected_revision'),
              'revisions':[r for r in row.get('revisions',[]) if r in allowed]} for key,row in s.get('objects',{}).items()
             if ref in row.get('revisions',[]) or row.get('selected_revision')==ref]
    return {'ref':ref,'objects':objects[:32],'status':_record_status(s,ref,task),'index_as_of':s['knowledge_commit']}


def web_tool(store,method,query):
    """Thin human HTTP adapter; the UI and MCP reuse the same read service."""
    def value(name,default=None):
        item=query.get(name,default)
        return item[0] if isinstance(item,list) and item else item
    iid=value('instance_id',value('instance'))
    if iid:require(iid in store.read_snapshot().get('instances',{}),'INSTANCE_UNKNOWN','Unknown workflow instance.')
    operation=method.replace('-','_').replace('.','_')
    if operation in {'knowledge','knowledge_search','search'}:
        try:limit=int(value('limit',8));cursor=int(value('cursor',0))
        except (TypeError,ValueError):raise ValueError('Bounded integer query pagination required')
        return search(store,value('query',value('q','')),instance_id=iid,kind=value('kind'),target_ref=value('target_ref'),route_ref=value('route_ref'),limit=limit,cursor=cursor)
    ref=value('ref');require(isinstance(ref,str),'KNOWLEDGE_QUERY_INVALID','Exact native reference is required.')
    if operation in {'knowledge_get','get'}:return get(store,ref,instance_id=iid)
    if operation in {'knowledge_dependencies','dependencies'}:return dependencies(store,ref,instance_id=iid)
    if operation in {'knowledge_history','history'}:return history(store,ref,instance_id=iid)
    require(False,'KNOWLEDGE_QUERY_INVALID','Unknown knowledge read operation.')
