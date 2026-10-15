"""Deterministic, read-only research views tied to one exact journal commit."""
from copy import deepcopy
from .util import require, identity, loads, sha
from .relations import premise_closure, edges
from .language import tokens


from pmrh.application.read_projections import scope_refs as scope_refs


def boundaries(snapshot,ref):
    from .assurance import evaluate
    views=[]
    if snapshot['records'][ref]['kind']=='Statement':
        for o in snapshot.get('obligations',{}).values():
            if ref not in o['definition']['target_refs']:continue
            for c in o['definition']['consumer_bindings']:
                if c.get('required_assurance'):
                    views.append({'consumer_binding':c['binding_id'],**evaluate(ref,c,snapshot)})
    return views


def current(snapshot,blob_get,*,instance_id=None,query=None,offset=0,limit=25,include_body=True):
    require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'PAGE_INVALID','Bounded page required')
    refs=scope_refs(snapshot,instance_id);rows=[];expanded=tokens(query) if query else set()
    for ref in sorted(refs):
        if ref not in snapshot['records']:continue
        record=snapshot['records'][ref];body=blob_get(record['body_sha256']).decode('utf-8')
        if expanded and not expanded&tokens(body+' '+record['kind']):continue
        family=[]
        for fid,f in snapshot.get('result_families',{}).items():
            members=f.get('members',[])
            if any(m==ref or isinstance(m,dict) and m.get('record_ref',m.get('statement_ref'))==ref for m in members):
                family.append({'family_id':fid,'label':f.get('display_title',f.get('label',fid)),'members':deepcopy(members),'authority':'NAVIGATION_ONLY'})
        sources=[{'source_ref':e['target_ref'],'usage':e.get('evidence_bindings',[])} for e in edges(snapshot)
                 if e['source_ref']==ref and e['type']=='USED_SOURCE']
        row={'ref':ref,'kind':record['kind'],'body_sha256':record['body_sha256'],'body_bytes':len(body.encode()),
             'body':body if include_body else None,'excerpt':body[:320],'context_refs':record['context_refs'],
             'data':deepcopy(record['data']),'support_boundaries':boundaries(snapshot,ref),
             'source_uses':sources,'result_families':family,'formal_verification':'NOT_PROVIDED_BY_PMRS'}
        rows.append(row)
    return {'commit':snapshot['knowledge_commit'],'instance_id':instance_id,'total':len(rows),
            'offset':offset,'limit':limit,'next_offset':offset+limit if offset+limit<len(rows) else None,
            'query':query,'expanded_terms':sorted(expanded),'records':rows[offset:offset+limit],
            'authority':'PER_EXACT_REVISION_AND_CHECKED_SCOPE'}


def diff(before,after,*,instance_id=None):
    refs=scope_refs(after,instance_id)|scope_refs(before,instance_id) if instance_id else set(before['records'])|set(after['records'])
    added=sorted((set(after['records'])-set(before['records']))&refs)
    supports=[]
    for sid,value in after.get('supports',{}).items():
        if value!=before.get('supports',{}).get(sid) and (value.get('statement_ref') in refs or value.get('argument_ref') in refs):
            supports.append({'support_id':sid,'before':deepcopy(before.get('supports',{}).get(sid)),'after':deepcopy(value)})
    withdrawals=[{'withdrawal_id':key,**deepcopy(v)} for key,v in after.get('withdrawals',{}).items()
                 if key not in before.get('withdrawals',{}) and
                 (instance_id is None or after.get('supports',{}).get(v.get('support_id'),{}).get('statement_ref') in refs)]
    reused=[]
    for key,event in after.get('production_events',{}).items():
        if key not in before.get('production_events',{}) and event.get('record_ref') in before['records'] and event['record_ref'] in refs:
            reused.append(event['record_ref'])
    changes=[]
    old=before.get('knowledge_changes',[]);new=after.get('knowledge_changes',[])
    for item in new[len(old):]: changes.extend(item.get('items',[]))
    return {'from_commit':before['knowledge_commit'],'to_commit':after['knowledge_commit'],'instance_id':instance_id,
            'content_added':added,'content_reused':sorted(set(reused)),'support_changes':supports,'support_withdrawals':withdrawals,
            'changes':changes,'classification':'CONTENT_OR_SCOPE_CHANGE' if added or supports or withdrawals else 'CONTROL_ONLY',
            'automatic_new_theorem_count':None,'originality':'NOT_AUTOMATICALLY_CERTIFIED'}


def frontier(snapshot,blob_get,*,instance_id=None):
    from .workflow_instances import report_obligation_ids
    report_duties=report_obligation_ids(snapshot,instance_id) if instance_id else set()
    rows=[]
    for oid,o in snapshot.get('obligations',{}).items():
        d,p=o['definition'],o['projection']
        bindings=[c for c in d['consumer_bindings'] if instance_id is None or c['instance_id']==instance_id]
        if instance_id and not bindings and oid not in report_duties:continue
        if p['resolution']=='SATISFIED_FOR_CONSUMER':continue
        criterion=blob_get(d['criterion_body_ref']).decode('utf-8')
        rows.append({'obligation_id':oid,'definition_revision':d['definition_revision'],'type':d['type'],
                     'targets':d['target_refs'],'criterion':criterion,'criterion_body_ref':d['criterion_body_ref'],
                     'work_state':p['work_state'],'resolution':p['resolution'],'consumer_bindings':deepcopy(bindings),
                     'blockers':deepcopy(p.get('blocker_refs',[])),'retry_gate_ref':p.get('retry_gate_ref'),
                     'attempt_accounts':deepcopy(p.get('attempt_accounts',[])),'evidence_refs':p.get('evidence_refs',[])})
    return {'commit':snapshot['knowledge_commit'],'instance_id':instance_id,'obligations':rows,'model_calls':0}


def sources(snapshot,blob_get,*,instance_id=None):
    refs=scope_refs(snapshot,instance_id) if instance_id else None
    is_survey=bool(instance_id and snapshot.get('instances',{}).get(instance_id,{}).get('kind')=='SURVEY')
    rows=[]
    for sid,source in snapshot.get('sources',{}).items():
        if refs is not None and sid not in refs and not is_survey:continue
        if source.get('visibility')=='OPERATOR_ONLY':continue
        digest=source['blob_hash'];raw=blob_get(digest)
        uses=[u for e in edges(snapshot) if e['type']=='USED_SOURCE' and e['target_ref']==sid for u in e['evidence_bindings']]
        rows.append({'source_ref':sid,'sha256':digest,'bytes':len(raw),'origin':deepcopy(source.get('origin')),
                     'coverage':source.get('coverage'),'uses':deepcopy(uses),
                     'media_type':source.get('media_type','application/octet-stream'),'filename':source.get('original_filename','Original material'),
                     'text':raw.decode('utf-8',errors='replace') if source.get('media_type','').startswith('text/') else None,
                     'authority':'SOURCE_CLAIM_NOT_NATIVE_PROOF'})
        if is_survey:
            from .survey import source_details
            rows[-1]['in_selected_scope']=sid in refs
            rows[-1]['survey_source_status']=deepcopy(snapshot.get('survey_source_status',{}).get(sid,{}))
            rows[-1]['survey_source_details']=source_details(snapshot,sid)
    return {'commit':snapshot['knowledge_commit'],'sources':rows}


def status(snapshot,store,*,instance_id=None,verify_report_files=True):
    from pmrh.application.read_projections import status as project_status
    require(instance_id is None or instance_id in snapshot['instances'],'INSTANCE_UNKNOWN','Unknown workflow selector')
    report = None
    if verify_report_files:
        from .report_catalog import catalog
        report = catalog(store,snapshot,instance_id)
    return project_status(snapshot,instance_id=instance_id,report=report)


def task_artifacts(snapshot,store,task_id,*,instance_id=None):
    """An exact task-scoped allowlist, never an arbitrary blob/path reader."""
    from .util import canonical, safe_path
    from .tasks import model_task_payload
    from .runner import input_files
    task=snapshot.get('tasks',{}).get(task_id)
    require(task is not None and (instance_id is None or task['instance_id']==instance_id),
            'TASK_UNKNOWN','Choose an existing task in the selected instance.')
    request=snapshot['requests'][task['request_id']];artifacts={}
    def add(section,name,*,digest=None,raw=None,path=None,math=False,metadata=None):
        key=identity([section,name,digest], 'ARTIFACT-')
        artifacts[key]={'artifact_id':key,'section':section,'name':name,'sha256':digest,
            'math':math,'metadata':deepcopy(metadata or {}),'_raw':raw,'_path':path}
    add('inputs','task.json',raw=canonical(model_task_payload(task)))
    add('metadata','native-task.json',raw=canonical(task))
    add('metadata','request.json',raw=canonical(request))
    accepted=snapshot.get('accepted_requests',{}).get(request['request_id'])
    if accepted:add('acceptance','accepted-request.json',raw=canonical(accepted))
    if request.get('acceptance_state','').startswith('REJECTED'):
        add('acceptance','rejection.json',raw=canonical({k:request.get(k) for k in
            ('request_id','capture_ref','acceptance_state','admission_error','admission_diagnostic','receipt_ref')}))
    for path,digest in input_files(task).items():
        add('inputs' if path in {'packet.json','prompt.md'} else 'materials',path,digest=digest,
            metadata=task.get('material_refs',{}).get(digest,{}))
    for name in ('client-system.md','bootstrap.txt'):
        path=safe_path(store.root,'runs/'+task_id+'/'+name)
        if path.is_file():add('inputs',name,path=path)
    if task.get('method_manual',{}).get('blob_ref'):
        add('materials','MAIN-method-handbook.md',digest=task['method_manual']['blob_ref'],metadata=task['method_manual'])
    if task.get('input_packet_ref')!=task.get('model_packet_ref',task.get('input_packet_ref')):
        add('metadata','native-input-packet.json',digest=task['input_packet_ref'])
    origin=request.get('repair_of',request['request_id'])
    family=[r for r in snapshot['requests'].values() if r['request_id']==origin or r.get('repair_of')==origin]
    for row in family:
        if row.get('capture_ref'):
            add('repairs' if row.get('repair_of') else 'outputs',row['request_id']+'.json',digest=row['capture_ref'],
                metadata={k:row.get(k) for k in ('request_id','task_id','repair_kind','repair_index','acceptance_state','admission_error','admission_diagnostic')})
    for production in snapshot.get('production_events',{}).values():
        if production.get('task_id')!=task_id:continue
        ref=production.get('record_ref');record=snapshot['records'].get(ref)
        if record:add('science',ref+'.md',digest=record['body_sha256'],math=True,metadata=record)
    rid=request['request_id']
    message_ids={d for row in snapshot.get('input_deliveries',{}).values() if row.get('request_id')==rid for d in row.get('message_ids',[])}
    for mid,row in snapshot.get('research_messages',{}).items():
        if row.get('sender_request_id')==rid or row.get('recipient_request_id')==rid or mid in message_ids:
            add('communication',mid+'.txt',digest=row['body_ref'],metadata=row)
    for did,row in snapshot.get('input_deliveries',{}).items():
        if row.get('request_id')==rid:add('deliveries',did+'.json',digest=row['response_ref'],metadata=row)
    for name in ('events.jsonl','stderr.log','capture.json','command.json','execution-profile.json','client-profile.json','input-manifest.json',
            'native-request.json','native-input-mapping.json','thread-resume.json','thread-resume-result.json'):
        path=safe_path(store.root,'runs/'+task_id+'/'+name)
        if path.is_file():add('logs',name,path=path)
    for turn in snapshot.get('native_main_turns',{}).values():
        if turn.get('request_id')==rid:
            add('metadata','native-turn-'+turn['turn_id']+'.json',raw=canonical(turn))
    for recovery in snapshot.get('main_execution_recoveries',{}).values():
        if recovery.get('instance_id')!=task['instance_id'] or recovery.get('request_id')!=rid:continue
        key=recovery['recovery_id'];add('metadata',key+'.json',raw=canonical(recovery))
        for field,name,section in [('native_rollout_ref','original-native-failure.jsonl','logs'),
                ('repaired_runtime_manifest_ref','repaired-runtime-manifest.json','metadata'),
                ('thread_start_evidence_ref','original-thread-start.json','metadata')]:
            if recovery.get(field):add(section,key+'-'+name,digest=recovery[field])
    return artifacts


def task_artifact_bytes(row,store):
    from .util import read
    if row['_raw'] is not None:return row['_raw']
    if row['_path'] is not None:return read(row['_path'],64*1024**2)
    return store.read_blob(row['sha256'])


def task_detail(snapshot,store,task_id,*,instance_id=None):
    from .usage_ledger import request_usage
    from .incidents import project as incident_projection
    rows=task_artifacts(snapshot,store,task_id,instance_id=instance_id)
    task=snapshot['tasks'][task_id];rid=task['request_id'];request=snapshot['requests'][rid]
    artifacts=[]
    for row in rows.values():
        raw=task_artifact_bytes(row,store)
        try:raw.decode('utf-8');textual=b'\0' not in raw
        except UnicodeDecodeError:textual=False
        artifacts.append({k:v for k,v in row.items() if not k.startswith('_')} | {
            'sha256':row['sha256'] or sha(raw),'bytes':len(raw),'textual':textual,
            'live':row['section']=='logs' and request['execution_state'] in {'RESERVED','SENT','UNKNOWN'}})
    dependencies=[]
    for binding in task.get('obligation_bindings',[]):
        obligation=snapshot.get('obligations',{}).get(binding['obligation_id'],{})
        definition=obligation.get('definition',{})
        dependencies.append({'binding':binding,'definition':deepcopy(definition),
            'criterion':store.read_blob(definition['criterion_body_ref']).decode() if definition.get('criterion_body_ref') else None,
            'projection':deepcopy(obligation.get('projection',{}))})
    return {'commit':snapshot['knowledge_commit'],'task':deepcopy(task),'request':deepcopy(request),
        'artifacts':artifacts,'duties':dependencies,'usage':request_usage(snapshot,rid),
        'message_acks':[deepcopy(row) for row in snapshot.get('message_acks',{}).values() if row.get('request_id')==rid],
        'input_window':deepcopy(snapshot.get('input_windows',{}).get(rid)),
        'backend_turns':[deepcopy(row) for row in snapshot.get('backend_usage',{}).values() if row.get('request_id')==rid],
        'native_delegation':[deepcopy(row) for row in snapshot.get('delegation_observations',{}).values() if row.get('request_id')==rid],
        'incidents':[incident_projection(snapshot,row) for row in snapshot.get('incidents',{}).values() if row.get('request_id')==rid or row.get('task_id')==task_id],
        'read_only':True,'model_calls':0}


RESEARCH_MEMORY_MAPS={'checkpoint':'research_checkpoints','audit':'research_audits',
    'guidance':'research_guidance','event':'research_audit_events','recovery':'main_execution_recoveries'}


def research_memory(snapshot,store,kind,record_id,*,instance_id,offset=0,limit=24000):
    """Read published research or immutable recovery evidence, not replay caches."""
    require(kind in RESEARCH_MEMORY_MAPS,'RESEARCH_MEMORY_UNKNOWN','Choose an instance-bound research or maintenance record.')
    row=snapshot.get(RESEARCH_MEMORY_MAPS[kind],{}).get(record_id)
    require(row is not None and row.get('instance_id')==instance_id,'UNAUTHORIZED','Research memory belongs to another instance or does not exist.')
    require(kind not in {'checkpoint','audit','guidance'} or row.get('status')=='PUBLISHED','RESEARCH_MEMORY_UNPUBLISHED','Only published MAIN research records are readable as research memory.')
    require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=64000,'PAGE_INVALID','Choose a bounded body page.')
    body_ref=next((row.get(key) for key in ('body_ref','body_sha256','checkpoint_body_ref','summary_body_ref') if isinstance(row.get(key),str)),None)
    body=store.read_blob(body_ref).decode('utf-8') if body_ref else next((row[key] for key in ('body','summary','text') if isinstance(row.get(key),str)),'')
    rid=row.get('author_request_id') or row.get('request_id') or row.get('main_request_id')
    request=snapshot.get('requests',{}).get(rid,{})
    if request.get('instance_id')!=instance_id:request={}
    task=snapshot.get('tasks',{}).get(request.get('task_id'),{})
    invalidated=[]
    for ref in row.get('evidence_refs',[]):
        source_status=snapshot.get('survey_source_status',{}).get(ref,{})
        linked=[(sid,support) for sid,support in snapshot.get('supports',{}).items()
            if ref in {support.get('statement_ref'),support.get('argument_ref')}]
        if ref not in snapshot.get('records',{}) and ref not in snapshot.get('sources',{}):invalidated.append(ref)
        elif source_status.get('withdrawn') or source_status.get('version_conflict'):invalidated.append(ref)
        elif any(support.get('needs_recheck') or any(w.get('support_id')==sid and w.get('active',True)
            for w in snapshot.get('withdrawals',{}).values()) for sid,support in linked):invalidated.append(ref)
    return {'commit':snapshot['knowledge_commit'],'instance_id':instance_id,'kind':kind,'record_id':record_id,
        'record':deepcopy(row),'body':body[offset:offset+limit],'body_ref':body_ref,'total_chars':len(body),
        'offset':offset,'next_offset':offset+limit if offset+limit<len(body) else None,
        'origin_task':{**{k:task.get(k) for k in ('task_id','stage_id','role','instance_id')},
            'request_id':request.get('request_id')} if task else None,
        'author_request_id':request.get('request_id'),
        'applicability':{'as_of_commit':snapshot['knowledge_commit'],'invalidated_refs':invalidated,
            'assessment':'INVALIDATED_EVIDENCE' if invalidated else 'NO_INVALIDATION_DETECTED_IN_NATIVE_FLAGS',
            'mathematical_qualification':False},
        'original_output_available':bool(request.get('capture_ref')),'read_only':True,'model_calls':0}


def research_memory_bytes(snapshot,store,kind,record_id,*,instance_id,format='body'):
    from .util import canonical
    detail=research_memory(snapshot,store,kind,record_id,instance_id=instance_id,limit=1)
    require(format in {'body','record','output'},'PATH_INVALID','Choose body, native record or original output.')
    row=detail['record']
    if format=='record':return canonical(row),'application/json; charset=utf-8'
    if format=='output':
        rid=detail['author_request_id'];request=snapshot.get('requests',{}).get(rid,{})
        require(request.get('capture_ref'),'RESEARCH_OUTPUT_UNAVAILABLE','No original MAIN output is bound to this record.')
        expected=row.get('author_capture_ref') or (row.get('capture_ref') if kind=='recovery' else None)
        if expected:require(expected==request['capture_ref'],'ORIGINAL_BYTES_MISMATCH','Record and original MAIN capture identity differ.')
        return store.read_blob(request['capture_ref']),'application/json; charset=utf-8'
    if detail['body_ref']:return store.read_blob(detail['body_ref']),'text/plain; charset=utf-8'
    text=next((row[key] for key in ('body','summary','text') if isinstance(row.get(key),str)),'')
    require(bool(text),'RESEARCH_BODY_UNAVAILABLE','This event has no separate research body; download its native record.')
    return text.encode('utf-8'),'text/plain; charset=utf-8'


NATIVE_MAIN_FILES={'protocol':'protocol.jsonl','stderr':'stderr.log'}


def native_main_files(snapshot,store,instance_id):
    """Instance-owned shared transport streams, distinct from a task capture."""
    from .util import safe_path
    instance=snapshot.get('instances',{}).get(instance_id)
    require(instance and instance['kind'] in {'TRH','FDH'},'MAIN_NOT_APPLICABLE','Select a harness instance with its own MAIN.')
    rows=[]
    for key,name in NATIVE_MAIN_FILES.items():
        path=safe_path(store.root,'execution/native-main/'+instance_id+'/'+name)
        if path.is_file():rows.append({'file':key,'name':name,'bytes':path.stat().st_size,'live':True})
    return {'commit':snapshot['knowledge_commit'],'instance_id':instance_id,'scope':'INSTANCE_SHARED_NATIVE_MAIN_STREAM',
        'files':rows,'read_only':True,'model_calls':0}


def native_main_file_path(snapshot,store,instance_id,file):
    from .util import safe_path
    listing=native_main_files(snapshot,store,instance_id)
    require(file in {row['file'] for row in listing['files']},'PATH_INVALID','Select an existing original stream from this MAIN instance.')
    return safe_path(store.root,'execution/native-main/'+instance_id+'/'+NATIVE_MAIN_FILES[file])



def history(snapshot,store,*,instance_id=None,query=None,offset=0,limit=25):
    """Read exact native journal events; snapshots and old entries are untouched."""
    require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'PAGE_INVALID','Bounded history page required')
    require(instance_id is None or instance_id in snapshot['instances'],'INSTANCE_UNKNOWN','Select an existing workflow')
    labels={'PROJECT_CREATED':'创建项目','ORIGINAL_SOURCE_RECEIVED':'保存研究原文','ORIGINAL_MATERIAL_RECEIVED':'保存补充材料',
        'CREATE_INSTANCE':'创建研究流程','AUTHORIZE_MISSION':'授权研究任务','PAUSE':'暂停流程','RESUME':'继续流程',
        'PREPARE':'准备执行请求','RESERVE':'预留调用预算','SENT':'发送请求','UNKNOWN':'请求结果不确定',
        'CAPTURE':'保存响应原件','SETTLE':'登记响应处理结果','NATIVE_RESTORED':'恢复原生备份',
        'HUMAN_DECISION':'保存人工决定','DISCOVERY_SCOPE_DEFINED':'保存探索范围','RECONCILE_UNKNOWN':'处置不确定请求'}
    project_events={'PROJECT_CREATED','ORIGINAL_SOURCE_RECEIVED','ORIGINAL_MATERIAL_RECEIVED','NATIVE_RESTORED','RESULT_FAMILY_INDEXED'}
    def instance_refs(event,native_delta):
        refs=set()
        def visit(value):
            if isinstance(value,dict):
                for key,child in value.items():
                    if (key=='instance_id' or key.endswith('_instance_id')) and isinstance(child,str) and child in snapshot['instances']:refs.add(child)
                    if key=='instance_ids' and isinstance(child,list):refs.update(i for i in child if isinstance(i,str) and i in snapshot['instances'])
                    if key=='report_id' and isinstance(child,str):refs.update(snapshot.get('reports',{}).get(child,{}).get('scope',{}).get('instance_ids',[]))
                    if (key=='visit_id' or key.endswith('_visit_id')) and isinstance(child,str):
                        iid=snapshot.get('visits',{}).get(child,{}).get('instance_id')
                        if iid:refs.add(iid)
                    if (key=='mission_id' or key.endswith('_mission_id')) and isinstance(child,str):
                        iid=snapshot.get('missions',{}).get(child,{}).get('instance_id')
                        if iid:refs.add(iid)
                    if key=='handoff_id' and isinstance(child,str):
                        iid=snapshot.get('handoffs',{}).get(child,{}).get('from_instance_id')
                        if iid:refs.add(iid)
                    if key=='request_id' and isinstance(child,str):
                        iid=snapshot.get('requests',{}).get(child,{}).get('instance_id')
                        if iid:refs.add(iid)
                    if key=='task_id' and isinstance(child,str):
                        iid=snapshot.get('tasks',{}).get(child,{}).get('instance_id')
                        if iid:refs.add(iid)
                    visit(child)
            elif isinstance(value,list):
                for child in value:visit(child)
        visit(event)
        if event.get('event_type')=='HANDOFF_ADOPTED':
            payload=event['payload'];adoptions=native_delta.get('handoff_adoptions',{})
            adopted=adoptions.get('set',{}).get(payload.get('decision_ref')) if adoptions.get('op')=='map' else None
            # Resolve the destination from this immutable commit, never from a
            # later adoption projected back onto an earlier prepared handoff.
            if adopted and adopted.get('handoff_id')==payload.get('handoff_id'):
                iid=adopted.get('instance_id')
                created=native_delta.get('instances',{}).get('set',{}).get(iid,{})
                if iid in snapshot['instances'] and created.get('created_by_decision')==payload.get('decision_ref'):refs.add(iid)
        return sorted(refs)
    rows=[];head=deepcopy(snapshot['_head']);search=(query or '').casefold()
    while head:
        entry=store._commit_record(head);counts={};native_delta={}
        for group in ('knowledge_delta_ref','control_delta_ref','report_delta_ref','registry_delta_ref'):
            digest=entry[group]
            if not digest:continue
            delta=loads(store.read_blob(digest));native_delta.update(delta)
            for name,value in delta.items():
                counts[name]=len(value.get('set',{}))+len(value.get('delete',[])) if value['op']=='map' else len(value['items']) if value['op']=='append' else 1
        for index,event in reversed(list(enumerate(entry['events']))):
            kind=event.get('event_type') or event.get('kind') or event.get('type') or 'JOURNAL_EVENT'
            if kind=='CHECKPOINT':continue
            refs=instance_refs(event,native_delta)
            if instance_id and instance_id not in refs and not (not refs and kind in project_events):continue
            title=labels.get(kind,kind)
            summary='；'.join(name+': '+str(count) for name,count in sorted(counts.items())) or '仅登记事件；没有修改研究内容'
            row={'event_id':event.get('event_id') or identity([head['commit'],index],'HISTORY-'),
                'title':title,'event_type':kind,'sequence':entry['sequence'],'commit':head['commit'],'at':entry['at'],
                'instance_ids':refs,'summary':summary,'details':{'event':deepcopy(event),'delta_counts':dict(counts)}}
            if search and search not in (title+' '+kind+' '+summary+' '+str(event)).casefold():continue
            rows.append(row)
        head=entry['previous_commit']
    return {'commit':snapshot['knowledge_commit'],'instance_id':instance_id,'records':rows[offset:offset+limit],
        'offset':offset,'limit':limit,'next_offset':offset+limit if offset+limit<len(rows) else None,
        'total':len(rows),'read_only':True,'model_calls':0}
