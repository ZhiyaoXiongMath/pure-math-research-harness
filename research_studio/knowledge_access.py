"""One bounded native knowledge read service for UI and request-scoped tools.

No persistent or permission-insensitive cache is used. Each query shares one
fixed-budget confined reader for snapshot verification. Body reads use a separate
per-query verified-stream budget; neither budget is reset during a query.
"""
from copy import deepcopy
from functools import wraps
import re
import codecs
import base64
import json
from .util import canonical,require,identity,safe_path

MAX_SCAN_REFS = 64
MAX_SCAN_BYTES = 4 * 1024**3
MAX_GET_BYTES = 256 * 1024**2
MAX_RANGE_BYTES = 65536
MAX_CURSOR_BYTES = 4096


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
    relevant={instance.get('target_ref')}
    for source, row in snapshot.get('survey_sources', {}).items():
        if row.get('instance_id') == instance_id and row.get('mission_id') == instance.get('current_mission_id'):
            relevant.add(source)
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


def _digest(value):
    from .util import sha
    return sha(canonical(value))


def _bounded_query(operation):
    @wraps(operation)
    def call(store,*args,**kwargs):
        from pmrh.adapters.storage.io import _ConfinedReader,_BodyReadBudget,_Unavailable
        from pmrh.adapters.storage.journal import Journal
        # One unchanged metadata budget and one explicit body budget per query;
        # replay/as-of/continuation cannot reset either during the operation.
        try:
            with _ConfinedReader(store.root) as reader:
                journal=Journal(store.root,reader=reader)
                journal._knowledge_body_budget=_BodyReadBudget()
                # A token owns only this active confined query, never a caller's
                # projection. Clear retained replay data before the reader exits.
                journal._query_replay_token=object()
                try:
                    return operation(journal,*args,**kwargs)
                finally:
                    journal._validated_query_history=None
                    journal._query_replay_token=None
        except _Unavailable as exc:
            require(False,'KNOWLEDGE_UNAVAILABLE',exc.reason)
    return call


def _view(store, task, instance_id, as_of_commit):
    """Pin one snapshot, intersect historical rights with current persisted rights."""
    current=store.read_snapshot()
    selected=current if as_of_commit is None or as_of_commit==current['knowledge_commit'] else store.read_snapshot(as_of_commit)
    if task is not None:
        actual = current.get('tasks', {}).get(task.get('task_id'))
        require(actual is not None and actual == task, 'KNOWLEDGE_FORBIDDEN', 'Current exact task context required.')
        request = current.get('requests', {}).get(task['request_id'], {})
        require(request and not request.get('fenced'), 'KNOWLEDGE_FORBIDDEN', 'Read authorization unavailable.')
        grant = current.get('budget_grants', {}).get(request.get('budget_grant_id'), {})
        # read_snapshot has validated the full published ancestry, including
        # no extension downgrade. This pinned, digest-checked native HEAD is
        # therefore an all-native profile, not an absent-status permission.
        from pmrh.adapters.storage.journal import COMMIT_SCHEMA
        profile=store._commit_record(current['_head'])['schema']
        if profile == COMMIT_SCHEMA:
            from .communication import bound_request
            from .reports import dispatch_current,dispatch_authorized,dispatch_budget
            from .scheduler import validate_task_control
            require(request.get('task_id')==task['task_id'] and
                    all(request.get(k)==task.get(k) for k in ('request_id','instance_id','mission_id')) and
                    grant and grant.get('budget_grant_id')==request.get('budget_grant_id')==task.get('budget_grant') and
                    grant.get('instance_id')==task['instance_id'],
                    'KNOWLEDGE_FORBIDDEN','Exact native request and grant scope required.')
            report_only=False
            if task.get('report_context'):
                dispatch_current(current,task['report_context'])
                report_only=dispatch_authorized(current,task)
            bound_request(current,task['request_id'],request['execution_id'],active=not report_only)
            if report_only:
                # Preserve the existing explicitly authorized report exception;
                # it does not authorize research or reopen a closed input window.
                require(dispatch_budget(current,task)==request['budget_grant_id'] and
                        request['execution_state'] in {'RESERVED','SENT'} and
                        not current.get('input_windows',{}).get(task['request_id'],{}).get('sealed'),
                        'KNOWLEDGE_FORBIDDEN','Report input authorization unavailable.')
            else:
                mission=current.get('missions',{}).get(task['mission_id'],{})
                instance=current.get('instances',{}).get(task['instance_id'],{})
                require(mission.get('status')=='ACTIVE' and mission.get('instance_id')==task['instance_id'] and
                        mission.get('budget_grant_id')==request['budget_grant_id'] and
                        grant.get('mission_id')==task['mission_id'] and
                        (task.get('report_context') or instance.get('current_mission_id')==task['mission_id']),
                        'KNOWLEDGE_FORBIDDEN','Current native mission authorization unavailable.')
                validate_task_control(current,task)
        else:
            require(profile in {'pmrh.commit/2','pmrh.control-fast.commit/1'} and grant.get('grant_status')=='ACTIVE',
                    'KNOWLEDGE_FORBIDDEN','Read authorization unavailable.')
        instance_id = instance_id or task['instance_id']
        require(instance_id == task['instance_id'] and task.get('mission_id') is not None,
                'KNOWLEDGE_FORBIDDEN', 'Exact task scope required.')
    current_refs = scoped_refs(current, task, instance_id)
    refs = scoped_refs(selected, task, instance_id) & current_refs
    partial = _partial_refs(task)
    # No body read or title is needed to exclude partial materials.
    full = refs - partial
    current_full = current_refs - partial
    mission = task['mission_id'] if task else current.get('instances', {}).get(instance_id, {}).get('current_mission_id')
    context = dict(project_id=current['project_id'],instance_id=instance_id,mission_id=mission,
                   task_id=task.get('task_id') if task else None,request_id=task.get('request_id') if task else None)
    deliveries = [d for d in current.get('input_deliveries', {}).values() if task and d['request_id']==task['request_id']]
    remaining = (task.get('communication_contract', {}).get('max_dynamic_input_tokens',0) - sum(d['bytes'] for d in deliveries)) if task else MAX_SCAN_BYTES
    exposure = dict(refs=sorted(full),current_refs=sorted(current_full),partial=sorted(partial & refs),
        task=task,remaining=remaining,source_policy={r:current['sources'][r] for r in refs if r in current.get('sources',{})},
        derived_visibility=_digest({k:current.get(k,{}) for k in ('relations','translations','supports','qualifications',
            'review_executions','withdrawals','conflicts','fast_selected','fast_claim_links','fast_revisions')}))
    return selected,current,full,current_full,partial & refs,context,_digest(exposure),max(0,remaining)


def _fast_visible(snapshot,current,refs,task,context):
    from pmrh.domain.fastmath.validation import native_refs, fast_refs, required_guards
    isolated = (task or {}).get('communication_contract',{}).get('mode') in {'INDEPENDENT_EXPLORE','REVIEW_ISOLATED'}
    if isolated: return set()
    rows=snapshot.get('fast_revisions',{}); visible=set(); pending=set(rows)
    from .context import _source_tainted
    while pending:
        progress=False
        for ref in sorted(pending):
            row=rows[ref]; boundary=row['scope']
            if boundary['project_id']!=context['project_id']:continue
            if context['instance_id'] is not None and (boundary['instance_id']!=context['instance_id'] or boundary['mission_id']!=context['mission_id']):continue
            closure=native_refs(row); dependencies=fast_refs(row['payload']) | fast_refs(row['dependencies'])
            # Dependencies belong to the selected verified state. Current
            # permission intersection and source taint still gate every ref;
            # current derived output is checked separately against current refs.
            for collection,identity in required_guards(snapshot,[dict(ref=ref,body=row)]):
                closure |= native_refs(snapshot[collection][identity])
            if row['kind']=='RefinementBinding':
                for sid in row['payload']['support_ids']+row['payload']['applicability_refs']:
                    if sid not in snapshot.get('supports',{}):closure.add('UNAVAILABLE')
            if not closure<=refs or not dependencies<=visible:continue
            if any(_source_tainted(r,current) for r in closure if r in current.get('sources',{})):continue
            visible.add(ref);pending.remove(ref);progress=True
        if not progress:break
    # A whole upper card includes its derived bindings. An unauthorized reverse
    # association excludes the whole card rather than leaking a verdict/count.
    changed=True
    while changed:
        changed=False
        for ref in list(visible):
            reverse={r for r,b in rows.items() if b['kind']=='RefinementBinding' and b['payload']['upper_revision_ref']==ref}
            reverse |= {l['source_binding_ref'] for l in snapshot.get('fast_claim_links',{}).values() if l['new_upper_ref']==ref}
            dependencies=fast_refs(rows[ref]['payload']) | fast_refs(rows[ref]['dependencies'])
            if not (reverse | dependencies)<=visible:
                visible.remove(ref);changed=True
    return visible


def _route_rows(snapshot, refs, task, context):
    from pmrh.domain.fastmath.validation import native_refs
    if task and task.get('actor_kind')!='MAIN': return {}
    result={}
    for collection in ('research_routes','attempt_accounts','incidents'):
        for ref,row in snapshot.get(collection,{}).items():
            iid=row.get('instance_id');mid=row.get('mission_id')
            if iid is None or mid is None:continue
            if context['instance_id'] is not None and (iid!=context['instance_id'] or mid!=context['mission_id']):continue
            if not native_refs(row)<=refs:continue
            result[ref]=(collection,row)
    return result


def _cursor_value(cursor):
    if type(cursor) is int:return cursor
    require(type(cursor) is str and cursor.startswith('k1.') and len(cursor)<=MAX_CURSOR_BYTES,
            'KNOWLEDGE_QUERY_INVALID','Invalid versioned continuation.')
    try:
        raw=base64.urlsafe_b64decode(cursor[3:].encode('ascii'))
        value=json.loads(raw)
    except (ValueError,UnicodeError):
        require(False,'KNOWLEDGE_QUERY_INVALID','Invalid continuation encoding.')
    require(type(value) is dict and set(value)=={'version','as_of_commit','query_digest','scope_digest','exposure_digest','position'} and value['version']==1,
            'KNOWLEDGE_QUERY_INVALID','Invalid continuation fields.')
    require(canonical(value)==raw,'KNOWLEDGE_QUERY_INVALID','Noncanonical continuation.')
    return value


def _page_context(cursor,continuation,as_of_commit):
    require(continuation is None or cursor==0,'KNOWLEDGE_QUERY_INVALID','Specify one continuation.')
    value=_cursor_value(continuation if continuation is not None else cursor)
    if isinstance(value,dict):
        require(as_of_commit is None or as_of_commit==value['as_of_commit'],'KNOWLEDGE_QUERY_INVALID','Pinned commit differs.')
        as_of_commit=value['as_of_commit']
    return value,as_of_commit


def _start(value,binding,count):
    if isinstance(value,dict):
        require({k:value[k] for k in binding}==binding,'KNOWLEDGE_QUERY_INVALID','Query, scope or current exposure changed; restart explicitly.')
        position=value['position']
    else:position=value
    require(type(position) is int and 0<=position<=count,'KNOWLEDGE_QUERY_INVALID','Position is not an enumeration boundary.')
    return position


def _coverage(binding,start,next_position,count,scanned,categories):
    encoded=base64.urlsafe_b64encode(canonical({**binding,'version':1,'position':next_position})).decode('ascii')
    return dict(**binding,start_position=start,next_position=next_position,cursor=next_position,
        continuation='k1.'+encoded if next_position<count else None,
        scanned_ranges_this_call=scanned,has_more_after_position=next_position<count,more=next_position<count,
        not_scanned_by_this_call={'before':[0,start],'after':[next_position,count]},
        categories=categories,complete_for_this_call_scope=start==0 and next_position==count and not any(categories.values()),
        coverage='THIS_CALL_ONLY; continuation attests no earlier scans',index_as_of=binding['as_of_commit'])


def _allow_response(result,remaining):
    require(len(canonical(result))<=remaining,'DYNAMIC_INPUT_LIMIT','Exact response exceeds the remaining frozen allowance; no delivery was truncated.')
    return result


def _presentation(snapshot, visible, row, evidence_refs):
    selected=[(ref,value) for ref,value in snapshot.get('fast_revisions',{}).items()
        if ref in visible and value['kind']=='ReaderProfile' and value['scope']==row['scope'] and
        snapshot.get('fast_selected',{}).get(value['object_id'])==ref]
    # Ambiguous multiple profiles never silently select an authority. Default
    # expansion remains full evidence; the caller can inspect each exact profile.
    profile_ref,profile=selected[0] if len(selected)==1 else (None,None)
    depth=profile['payload']['explanation_depth'] if profile else 'EVIDENCE'
    expanded=[] if depth=='OVERVIEW' else [r for r in row['dependencies'] if r.startswith('FM-')] if depth=='INTERFACES' else evidence_refs
    return dict(reader_profile_ref=profile_ref,explanation_depth=depth,expansion_refs=list(expanded),
                claim_and_assurance='UNCHANGED_BY_PRESENTATION')


class _MatchVisitor:
    """Bounded tentative literal-IGNORECASE match, never a delivery callback."""
    def __init__(self,query):
        self.query=query;self.pattern=re.compile(re.escape(query),re.IGNORECASE) if query else None
        self.decoder=codecs.getincrementaldecoder('utf-8')('strict')
        self.buffer='';self.offset=0;self.hit=None;self.right=0;self.prefix=''

    def _text(self,text):
        if not self.query:
            self.prefix=(self.prefix+text)[:176]
            return
        if self.hit is not None:
            take=text[:self.right];self.hit['excerpt']+=take;self.right-=len(take)
            return
        self.buffer+=text
        match=self.pattern.search(self.buffer)
        if match is not None:
            from .util import sha
            a,b=match.span();matched=self.buffer[a:b].encode('utf-8')
            right=self.buffer[b:b+96]
            self.hit=dict(start=self.offset+len(self.buffer[:a].encode('utf-8')),
                end=self.offset+len(self.buffer[:b].encode('utf-8')),quoted_sha256=sha(matched),
                excerpt=self.buffer[max(0,a-64):b]+right)
            self.right=96-len(right);self.buffer=''
        else:
            keep=len(self.query)-1+64
            cut=max(0,len(self.buffer)-keep)
            self.offset+=len(self.buffer[:cut].encode('utf-8'));self.buffer=self.buffer[cut:]

    def feed(self,chunk,byte_offset):
        self._text(self.decoder.decode(chunk,final=False))

    def finish(self):
        self._text(self.decoder.decode(b'',final=True))
        if not self.query:
            from .util import sha
            match=self.prefix[:80].encode('utf-8')
            return dict(start=0,end=len(match),quoted_sha256=sha(match),excerpt=self.prefix)
        return self.hit

    def abort(self):
        self.buffer='';self.prefix='';self.hit=None;self.decoder=None;self.right=0


class _GetVisitor:
    """Whole get preserves old O(body) memory; range get keeps <=64KiB."""
    def __init__(self,body_range):
        self.range=body_range;self.chunks=[];self.size=0
        self.decoder=codecs.getincrementaldecoder('utf-8')('strict')

    def feed(self,chunk,byte_offset):
        self.decoder.decode(chunk,final=False)  # Validate all text, not just output.
        self.size=byte_offset+len(chunk)
        if self.range is None:self.chunks.append(chunk)
        else:
            a=max(byte_offset,self.range['start']);b=min(self.size,self.range['end'])
            if a<b:self.chunks.append(chunk[a-byte_offset:b-byte_offset])

    def finish(self):
        self.decoder.decode(b'',final=True)
        if self.range is not None:
            require(self.range['end']<=self.size,'KNOWLEDGE_QUERY_INVALID','Requested range exceeds exact body.')
        raw=b''.join(self.chunks)
        body=raw.decode('utf-8')  # Also rejects an output window cutting a codepoint.
        from .util import sha
        return dict(body=body,quoted_sha256=sha(raw))

    def abort(self):
        self.chunks.clear();self.decoder=None;self.size=0


def _body_range(value):
    if value is None:return None
    require(type(value) is dict and set(value)=={'start','end','unit'},'KNOWLEDGE_QUERY_INVALID','Exact output range fields required.')
    require(type(value['start']) is int and type(value['end']) is int and value['unit']=='UTF8_BYTE' and
            0<=value['start']<value['end']<=MAX_SCAN_BYTES and value['end']-value['start']<=MAX_RANGE_BYTES,
            'KNOWLEDGE_QUERY_INVALID','Bounded UTF8 byte output range required.')
    return dict(value)


def _verified_body(store,digest,visitor,maximum=MAX_SCAN_BYTES):
    return store._reader.read_verified_body(digest,budget=store._knowledge_body_budget,
                                           visitor=visitor,maximum=maximum)


@_bounded_query
def get(store,ref,*,task=None,instance_id=None,as_of_commit=None,body_range=None):
    body_range=_body_range(body_range)
    s,current,refs,current_refs,partial,context,exposure,remaining=_view(store,task,instance_id,as_of_commit)
    fast=_fast_visible(s,current,refs,task,context) & _fast_visible(current,current,current_refs,task,context)
    routes=_route_rows(s,refs,task,context)
    require(ref in refs or ref in partial or ref in fast or ref in routes,'KNOWLEDGE_FORBIDDEN','Reference is outside the authorized knowledge view.')
    require(ref not in partial,'KNOWLEDGE_SCOPE_LIMIT','Only declared frozen ranges are authorized; full get would widen scope.')
    require(body_range is None or ref not in fast|set(routes),'KNOWLEDGE_QUERY_INVALID','Body ranges apply only to whole-body-authorized native records and sources.')
    if ref in fast:
        from pmrh.domain.fastmath.qualification import project
        row=s['fast_revisions'][ref];derived=project(ref,s)
        raw=store.read_blob(ref[3:]);require(raw==canonical(row),'BLOB_CHANGED','Exact fast body differs.')
        result=dict(kind=row['kind'],ref=ref,revision=ref,body=row['body'],body_sha256=row['body_sha256'],
                    payload=deepcopy(row['payload']),derived=derived,latest_status=project(ref,current),as_of_commit=s['knowledge_commit'],
                    presentation=_presentation(s,fast,row,derived['evidence_refs']),
                    index_as_of=s['knowledge_commit'],read_scope='EXACT_FAST_REVISION')
    elif ref in routes:
        collection,row=routes[ref]
        result=dict(kind=collection.upper(),ref=ref,revision=identity(row),record=deepcopy(row),
                    body=canonical(row).decode(),body_sha256=_digest(row),as_of_commit=s['knowledge_commit'],
                    index_as_of=s['knowledge_commit'],read_scope='ORGANIZATIONAL_ONLY; NO_PROOF_STATUS')
    else:
        row=s.get('records',{}).get(ref) or s['sources'][ref]
        digest=row.get('body_sha256',row.get('blob_hash'))
        from pmrh.adapters.storage.io import _Unavailable
        maximum=MAX_SCAN_BYTES if body_range is not None else MAX_GET_BYTES
        if task and body_range is None:maximum=min(maximum,remaining)
        try:
            verified=_verified_body(store,digest,_GetVisitor(body_range),maximum)
        except _Unavailable as exc:
            if exc.reason=='QUERY_READ_LIMIT' and task and body_range is None and remaining<MAX_GET_BYTES:
                require(False,'DYNAMIC_INPUT_LIMIT','The entire exact body exceeds remaining allowance.')
            raise
        except UnicodeDecodeError:
            require(False,'SOURCE_TEXT_UNAVAILABLE','The exact whole body and requested output window must be valid UTF8.')
        body=verified.result['body']
        if ref in s.get('records',{}):
            result={'kind':'RECORD','ref':ref,'revision':ref,'record':deepcopy(row),'body':body,'body_sha256':digest,
                    'status':_record_status(s,ref,task),'index_as_of':s['knowledge_commit'],'read_scope':'EXACT_BODY'}
        else:
            result={'kind':'SOURCE','ref':ref,'revision':row.get('revision',ref),'source':deepcopy(row),'body':body,'body_sha256':digest,
                    'index_as_of':s['knowledge_commit'],'read_scope':'EXACT_REGISTERED_OCCURRENCE'}
        result['as_of_commit']=s['knowledge_commit']
        if body_range is not None:
            result.update(read_scope='PARTIAL_BODY_RANGE',body_complete=False,body_range=body_range,
                range_locator=dict(blob_hash=digest,**body_range,quoted_sha256=verified.result['quoted_sha256']),
                verified_full_body_bytes=verified.size,verified_full_body_sha256=verified.sha256,
                next_byte_offset=body_range['end'] if body_range['end']<verified.size else None)
    return _allow_response(result,remaining) if task else result


@_bounded_query
def search(store,query='',*,task=None,instance_id=None,kind=None,target_ref=None,route_ref=None,
           limit=8,cursor=0,continuation=None,as_of_commit=None):
    require(type(query) is str and len(query)<=512 and type(limit) is int and 1<=limit<=20,
            'KNOWLEDGE_QUERY_INVALID','Bounded search required.')
    value,as_of_commit=_page_context(cursor,continuation,as_of_commit)
    s,current,refs,current_refs,partial,context,exposure,remaining=_view(store,task,instance_id,as_of_commit)
    fast=_fast_visible(s,current,refs,task,context) & _fast_visible(current,current,current_refs,task,context)
    routes=_route_rows(s,refs,task,context)
    candidates=[]
    for ref in sorted(refs):
        row=s.get('records',{}).get(ref) or s['sources'][ref]
        candidates.append((ref,row.get('kind','SOURCE'),row))
    candidates += [(r,s['fast_revisions'][r]['kind'],s['fast_revisions'][r]) for r in sorted(fast)]
    candidates += [(r,collection.upper(),row) for r,(collection,row) in sorted(routes.items())]
    candidates.sort(key=lambda x:x[0])
    candidates=[x for x in candidates if (kind is None or x[1]==kind) and
        (route_ref is None or x[0]==route_ref) and (target_ref is None or x[0]==target_ref or target_ref in canonical(x[2]).decode())]
    binding=dict(as_of_commit=s['knowledge_commit'],query_digest=_digest(dict(query=query,kind=kind,target_ref=target_ref,route_ref=route_ref)),
                 scope_digest=_digest(context),exposure_digest=exposure)
    start=_start(value,binding,len(candidates));position=start;used=0;rows=[];scanned=[]
    categories={'unsupported':[],'corrupt':[],'limited':[],'partial_material_excluded':sorted(partial)}
    from pmrh.adapters.storage.io import _Unavailable
    from .util import PMRSError, sha
    journal=store
    while position<len(candidates) and position-start<MAX_SCAN_REFS and len(rows)<limit:
        ref,record_kind,row=candidates[position]
        visitor=_MatchVisitor(query)
        if ref in routes:
            raw=canonical(row);digest=sha(raw)
            visitor.feed(raw,0);hit=visitor.finish();size=len(raw)
        else:
            digest=ref[3:] if ref in fast else row.get('body_sha256',row.get('blob_hash'))
            try:
                verified=_verified_body(journal,digest,visitor)
                hit=verified.result;size=verified.size
            except UnicodeDecodeError:
                categories['unsupported'].append(ref);position+=1;continue
            except (_Unavailable,PMRSError,OSError) as exc:
                category='limited' if isinstance(exc,_Unavailable) and exc.reason=='QUERY_READ_LIMIT' else 'corrupt'
                categories[category].append(ref)
                if category=='limited':break  # Same ref; no skipped-body completeness.
                position+=1;continue
        used+=size;position+=1
        scanned.append({'ref':ref,'blob_hash':digest,'unit':'UTF8_BYTE','start':0,'end':size})
        if hit is None:continue
        rows.append(dict(kind=record_kind,ref=ref,revision=ref if ref not in routes else identity(row),
            body_sha256=digest,excerpt=hit['excerpt'],
            locator=dict(blob_hash=digest,unit='UTF8_BYTE',start=hit['start'],end=hit['end'],quoted_sha256=hit['quoted_sha256']),
            reason='Exact authorized bytes; navigation grants no scientific qualification'))
    budget=store._knowledge_body_budget
    result=dict(results=rows,scan_bytes_this_call=used,scan_reference_budget=MAX_SCAN_REFS,scan_byte_budget=MAX_SCAN_BYTES,
        body_bytes_read_this_call=MAX_SCAN_BYTES-budget.remaining_bytes,
        body_attempts_this_call=64-budget.remaining_files,integrity_probe_bytes_this_call=budget.integrity_probe_bytes,
        integrity_probe_attempts_this_call=budget.integrity_probe_attempts,
        **_coverage(binding,start,position,len(candidates),scanned,categories))
    return _allow_response(result,remaining) if task else result


@_bounded_query
def _relations_page(store,ref,operation,*,task=None,instance_id=None,as_of_commit=None,limit=16,cursor=0,continuation=None):
    require(type(limit) is int and 1<=limit<=32,'KNOWLEDGE_QUERY_INVALID','Bounded page required.')
    value,as_of_commit=_page_context(cursor,continuation,as_of_commit)
    s,current,refs,current_refs,partial,context,exposure,remaining=_view(store,task,instance_id,as_of_commit)
    fast=_fast_visible(s,current,refs,task,context) & _fast_visible(current,current,current_refs,task,context)
    routes=_route_rows(s,refs,task,context)
    require(ref in refs or ref in fast or ref in routes,'KNOWLEDGE_FORBIDDEN','Exact authorized reference required.')
    if ref in fast:
        row=s['fast_revisions'][ref]
        if operation=='history':
            rows=[dict(ref=r,predecessor=v['predecessor'],selected=s.get('fast_selected',{}).get(v['object_id'])==r,
                       reason=v['reason']) for r,v in s['fast_revisions'].items() if r in fast and v['object_id']==row['object_id']]
        else:
            from pmrh.domain.fastmath.validation import native_refs,fast_refs
            closure=(native_refs(row)|fast_refs(row['payload'])|set(row['dependencies'])) & (refs|fast)
            rows=[{'source_ref':ref,'target_ref':r,'relation':'EXACT_DEPENDENCY'} for r in sorted(closure)]
            rows += [{'source_ref':ref,'target_ref':r,'relation':'REFINEMENT_ASSOCIATION'} for r,v in s['fast_revisions'].items()
                     if r in fast and v['kind']=='RefinementBinding' and v['payload']['upper_revision_ref']==ref]
            rows += [{'source_ref':ref,'reuse_link_ref':key,**deepcopy(link)} for key,link in s.get('fast_claim_links',{}).items()
                     if link['new_upper_ref']==ref and link['source_binding_ref'] in fast]
    elif ref in routes:
        row=routes[ref][1]
        rows=deepcopy(row.get('history',[])) if operation=='history' else []
    elif operation=='dependencies':
        from .relations import edges
        rows=[deepcopy(x) for x in edges(s) if x.get('source_ref')==ref and x.get('target_ref') in refs]
    else:
        rows=[{'object_id':key,'selected_revision':row.get('selected_revision'),
              'revisions':[r for r in row.get('revisions',[]) if r in refs]} for key,row in s.get('objects',{}).items()
              if ref in row.get('revisions',[]) or row.get('selected_revision')==ref]
    binding=dict(as_of_commit=s['knowledge_commit'],query_digest=_digest(dict(operation=operation,ref=ref)),scope_digest=_digest(context),exposure_digest=exposure)
    start=_start(value,binding,len(rows));end=min(len(rows),start+limit)
    result=dict(ref=ref,**{operation if operation=='dependencies' else 'objects':rows[start:end]},
        **_coverage(binding,start,end,len(rows),[{'start':start,'end':end}],{}))
    if ref in refs:result['status']=_record_status(s,ref,task)
    return _allow_response(result,remaining) if task else result


def dependencies(store,ref,**kwargs):
    return _relations_page(store,ref,'dependencies',**kwargs)


def history(store,ref,**kwargs):
    if isinstance(ref,str) and ref.startswith('MAIN_HISTORY/'):
        from .main_history import get as get_main_history
        return get_main_history(store,ref,task=kwargs.get('task'))
    return _relations_page(store,ref,'history',**kwargs)


def web_tool(store,method,query):
    """Trusted human project view after ui session/workspace authorization.

    ui.do_GET authenticates the session and workspace before selecting the
    project Store. No instance filter intentionally means this project view;
    an explicit instance constrains it. None/cursors grant no permission.
    TaskTools always uses its current persisted task and cannot enter here.
    """
    def value(name,default=None):
        item=query.get(name,default)
        return item[0] if isinstance(item,list) and item else item
    operation=method.replace('-','_').replace('.','_')
    args=dict(instance_id=value('instance_id',value('instance')),as_of_commit=value('as_of_commit'))
    if operation in {'knowledge','knowledge_search','search'}:
        cursor=value('cursor',0)
        if isinstance(cursor,str) and cursor.isdecimal():cursor=int(cursor)
        return search(store,value('query',value('q','')),**args,kind=value('kind'),target_ref=value('target_ref'),
            route_ref=value('route_ref'),limit=int(value('limit',8)),cursor=cursor,continuation=value('continuation'))
    ref=value('ref');require(isinstance(ref,str),'KNOWLEDGE_QUERY_INVALID','Exact reference required.')
    if operation in {'knowledge_get','get'}:
        window=value('body_range')
        if isinstance(window,str):
            require(len(window)<=256,'KNOWLEDGE_QUERY_INVALID','Bounded output range encoding required.')
            try:window=json.loads(window)
            except ValueError:require(False,'KNOWLEDGE_QUERY_INVALID','Invalid output range JSON.')
        return get(store,ref,body_range=window,**args)
    cursor=value('cursor',0)
    if isinstance(cursor,str) and cursor.isdecimal():cursor=int(cursor)
    args.update(limit=int(value('limit',16)),cursor=cursor,continuation=value('continuation'))
    if operation in {'knowledge_dependencies','dependencies'}:return dependencies(store,ref,**args)
    if operation in {'knowledge_history','history'}:return history(store,ref,**args)
    require(False,'KNOWLEDGE_QUERY_INVALID','Unknown knowledge read operation.')
