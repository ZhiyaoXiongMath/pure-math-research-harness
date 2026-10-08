"""Deterministic, read-only research views tied to one exact journal commit."""
from copy import deepcopy
from .util import require, identity, loads, sha
from .relations import premise_closure, edges
from .language import tokens


def scope_refs(snapshot,instance_id=None):
    if instance_id is None:return set(snapshot['records'])
    require(instance_id in snapshot['instances'],'INSTANCE_UNKNOWN','Select an existing workflow')
    instance=snapshot['instances'][instance_id];roots=set()
    if instance.get('target_ref'):roots.add(instance['target_ref'])
    if instance.get('discovery_brief_ref'):roots.add(instance['discovery_brief_ref'])
    roots.update(instance.get('discovery_scope',{}).values())
    roots.update(instance.get('survey_scope',{}).get('selected_refs',[]))
    roots.update(instance.get('survey_scope',{}).get('source_refs',[]))
    for event in snapshot.get('production_events',{}).values():
        task=snapshot.get('tasks',{}).get(event.get('task_id'),{})
        if task.get('instance_id')==instance_id and event.get('record_ref') in snapshot['records']:
            roots.add(event['record_ref'])
    roots.update(c['statement_ref'] for c in snapshot.get('candidates',{}).values() if c['instance_id']==instance_id)
    for o in snapshot.get('obligations',{}).values():
        if any(c['instance_id']==instance_id for c in o['definition']['consumer_bindings']):
            roots.update(o['definition']['target_refs']);roots.update(o['projection'].get('evidence_refs',[]))
    for ref,r in snapshot['records'].items():
        if r['kind']=='Argument' and r['data']['conclusion_ref'] in roots:roots.add(ref)
        if r['kind']=='Example' and set(r['data']['target_refs'])&roots:roots.add(ref)
    return premise_closure(roots,snapshot,include_method_sources=True)


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


def status(snapshot,store,*,instance_id=None):
    from .report_catalog import catalog
    instances={k:v for k,v in snapshot['instances'].items() if instance_id is None or k==instance_id}
    require(instance_id is None or instance_id in instances,'INSTANCE_UNKNOWN','Unknown workflow selector')
    requests=[r for r in snapshot.get('requests',{}).values() if instance_id is None or r['instance_id']==instance_id]
    return {'commit':snapshot['knowledge_commit'],'project_id':snapshot['project_id'],'title':snapshot['title'],
            'mathematical':{'target_refs':[i['target_ref'] for i in instances.values() if i.get('target_ref')],
                'records':len(scope_refs(snapshot,instance_id)&set(snapshot['records'])),'qualification':'EXACT_CONSUMER_SCOPE_ONLY','formal_proof':'NOT_GRANTED'},
            'workflow':{'instances':deepcopy(list(instances.values())),'automatic_next_round':False},
            'execution':{'requests':[{k:r.get(k) for k in ('request_id','execution_state','capture_ref','usage','fenced')} for r in requests],
                'running_processes':'NOT_INFERRED_FROM_WORKFLOW_STATUS','unknown':sum(r['execution_state']=='UNKNOWN' for r in requests)},
            'acceptance':{'pending_captures':sum(r['execution_state']=='CAPTURED' for r in requests),
                'accepted':sum(r.get('acceptance_state')=='ACCEPTED' for r in requests)},
            'report':catalog(store,snapshot,instance_id),'language_policy':snapshot['language_policy'],
            'native_usage':deepcopy(snapshot.get('usage',{})),
            'read_only':True,'model_calls':0}



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
