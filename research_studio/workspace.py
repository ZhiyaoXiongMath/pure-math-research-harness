"""Local workspace and explicit application actions shared by HTTP and CLI.

Only native stores hold research authority. Workspace receipts prevent browser
retries from repeating business actions, including across backend restarts.
"""
from pathlib import Path
from copy import deepcopy
from contextlib import contextmanager
import base64
import fcntl
import secrets
import threading
from .util import require, safe_path, read, loads, canonical, atomic, immutable, identity, PMRSError, now
from .store import Store
from .engine import Engine
from . import views, changes, workflow_instances as W, model_policy
from .codex_client import Login
from . import activity


class Workspace:
    def __init__(self,root,*,create=True):
        self.root=safe_path(Path(root));self.engine=Engine();self.login=Login();self.jobs={};self.assistant_jobs={};self.lock=threading.RLock();self.project_locks={};self.object_labels={};self.assistant_sections={}
        if create:
            for directory in ('projects','uploads','downloads','actions','runtime'):
                (self.root/directory).mkdir(parents=True,exist_ok=True,mode=0o700)
            # A browser origin can change on restart, or later serve another
            # workspace. Persist a random identity, never a local path or token.
            with (self.root/'runtime/actions.lock').open('a+b') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                path=self.root/'runtime/workspace.json'
                if not path.exists():atomic(path,canonical({'schema':'pmrs.workspace/1','workspace_id':'WS-'+secrets.token_hex(16)}))
        identity_record=loads(read(self.root/'runtime/workspace.json'))
        self.workspace_id=identity_record.get('workspace_id')
        require(identity_record.get('schema')=='pmrs.workspace/1' and isinstance(self.workspace_id,str) and
                len(self.workspace_id)==35 and self.workspace_id.startswith('WS-') and
                all(c in '0123456789abcdef' for c in self.workspace_id[3:]),'WORKSPACE_INVALID','工作区身份记录无效。')

    def project(self,key):
        require(isinstance(key,str) and key.startswith('WP-') and len(key)==35 and all(c in '0123456789abcdef' for c in key[3:]),'PROJECT_UNKNOWN','请选择工作区中的项目。')
        store=Store(safe_path(self.root,'projects/'+key));store.read_snapshot();return store

    def preferences(self):
        """Host-owned presentation preferences, independent of research authority."""
        from .localization import load_preferences
        value=load_preferences(self.root)
        return {'ui_locale':value['ui_locale'],'model_calls':0}

    def set_preferences(self,ui_locale):
        require(ui_locale in {'en','zh-CN'},'UI_LOCALE_INVALID','Choose English or Simplified Chinese.')
        with self.lock:
            atomic(self.root/'runtime/preferences.json',canonical({'ui_locale':ui_locale}))
        return self.preferences()

    def list(self):
        rows=[]
        for path in sorted((self.root/'projects').glob('WP-*')):
            if not (path/'project.json').exists():continue
            try:
                s=Store(path).read_snapshot()
                rows.append({'key':path.name,'title':s['title'],'project_id':s['project_id'],
                             'instances':list(s['instances'].values()),'synthetic':s['synthetic_test_only']})
            except PMRSError as e:rows.append({'key':path.name,'title':path.name,'error':e.code,'instances':[]})
        return {'projects':rows,'model_calls':0}

    def info(self,key,instance=None,commit=None):
        store=self.project(key);s=store.read_snapshot(commit);v=views.status(s,store,instance_id=instance)
        v.update(self._progress(key,store,s,instance))
        v['candidates']=[{**c,'body':store.read_blob(s['records'][c['statement_ref']]['body_sha256']).decode()} for c in s['candidates'].values() if not instance or c['instance_id']==instance]
        for candidate in v['candidates']:
            ref=candidate['statement_ref'];declared=set(candidate.get('evidence_refs',[])+candidate.get('comparison_refs',[])+candidate.get('calibration_refs',[]))
            candidate['related_records']=[{'ref':rid,'kind':r['kind'],'body':store.read_blob(r['body_sha256']).decode(),'data':r['data']}
                for rid,r in s['records'].items() if rid in declared or (r['kind'] in {'Example','Assessment'} and ref in r['data'].get('target_refs',[]))]
            candidate['support_boundaries']=views.boundaries(s,ref)
        v['handoffs']=list(s.get('handoffs',{}).values())
        return v

    def progress(self,key,instance=None,commit=None):
        """Poll control state without rereading mathematical bodies or PDFs."""
        store=self.project(key);s=store.read_snapshot(commit)
        return self._progress(key,store,s,instance)

    def _progress(self,key,store,s,instance):
        from .scheduler import budget_remaining,project_remaining
        require(instance is None or instance in s['instances'],'INSTANCE_UNKNOWN','请选择已有研究流程。')
        rows=[dict(row) for iid,row in s['instances'].items() if not instance or iid==instance]
        for row in rows:
            ref=row.get('target_ref') or row.get('discovery_brief_ref')
            record=s['records'].get(ref) or s['sources'].get(ref,{})
            blob=record.get('body_sha256') or record.get('blob_hash')
            if blob and blob not in self.object_labels:
                body=store.read_blob(blob).decode('utf-8',errors='replace')
                if len(self.object_labels)>=256:self.object_labels.pop(next(iter(self.object_labels)))
                self.object_labels[blob]=(body[:1000],len(body)>1000)
            body,truncated=self.object_labels.get(blob,('',False))
            row['object_text']=body;row['object_text_truncated']=truncated
            row['display_name']=row.get('name') or (row['kind']+' · '+(body[:60] or '未命名研究'))
        requests=[{**r,'stage_id':s['tasks'].get(r['task_id'],{}).get('stage_id')} for r in s.get('requests',{}).values() if not instance or r['instance_id']==instance]
        active=sum(r['execution_state'] in {'RESERVED','SENT'} for r in requests)
        project_jobs=[{**j,'scope':'PROJECT_COORDINATOR','initiated_by_instance_id':i}
                      for (p,i),j in self.jobs.items() if p==key]
        v={'commit':s['knowledge_commit'],'project_id':s['project_id'],'title':s['title'],
           'synthetic':s['synthetic_test_only'],'workflow':{'instances':rows,'automatic_next_round':False},
           'mathematical':{'records':len(views.scope_refs(s,instance)&set(s['records'])),
                          'target_refs':[r['target_ref'] for r in rows if r.get('target_ref')],
                          'qualification':'EXACT_CONSUMER_SCOPE_ONLY','formal_proof':'NOT_GRANTED'},
           'execution':{'requests':requests,'running_processes':active,'active_requests':active,
                        'scope':'SELECTED_INSTANCE' if instance else 'PROJECT',
                        'unknown':sum(r['execution_state']=='UNKNOWN' for r in requests)},
           'project_execution':{'running_coordinators':sum(j['state']=='RUNNING' for j in project_jobs),
                                'active_requests':sum(r['execution_state'] in {'RESERVED','SENT'} for r in s.get('requests',{}).values())},
           'project_jobs':project_jobs,'jobs':project_jobs,'activity':activity.project(s,instance),
           'read_only':True,'model_calls':0}
        grants=[g for g in s['budget_grants'].values() if g.get('budget_domain','SCIENCE')=='SCIENCE'
                and (not instance or g.get('instance_id')==instance)]
        remaining=sum(budget_remaining(s,g['budget_grant_id']) for g in grants);total=project_remaining(s)
        v['synthetic']=s['synthetic_test_only'];v['budget']={'project':s['project_budget'],'grants':grants,
            'remaining_calls':remaining if remaining!=float('inf') else None,'project_remaining_calls':total if total!=float('inf') else None,'max_workers':s.get('max_workers',1),'project_max_workers':8,'host_model_pool':10}
        v['tasks']=[{k:t.get(k) for k in ('task_id','instance_id','stage_id','role','model_policy','model_policy_resolution','request_id')}
                    for t in s['tasks'].values() if t.get('purpose')!='PROJECT_ASSISTANT' and (not instance or t['instance_id']==instance)]
        from .workflows.registry import spec
        for task in v['tasks']:task['activity_label']=spec(task['stage_id'])['ui_labels']['zh-CN']
        frozen_bindings={b['binding_id'] for t in s['tasks'].values() for b in t.get('obligation_bindings',[])}
        v['pending_work']=[{'obligation_id':oid,'binding_id':c['binding_id'],'stage_id':c['stage_id'],'role':c['role'],
                           'branch_key':c.get('entry_basis',{}).get('research_plan',{}).get('branch_key'),
                           'dependencies':len(o['definition'].get('dependency_bindings',[]))}
            for oid,o in s.get('obligations',{}).items() for c in o['definition']['consumer_bindings']
            if (not instance or c['instance_id']==instance) and c['binding_id'] not in frozen_bindings
            and c['binding_id'] not in s.get('retired_consumers',{})
            and c['mission_id']==s['instances'][c['instance_id']].get('current_mission_id')]
        v['missions']=[m for m in s['missions'].values() if not instance or m['instance_id']==instance]
        selected=s['instances'].get(instance,{})
        mission=s['missions'].get(selected.get('current_mission_id'),{})
        grant=s['budget_grants'].get(mission.get('budget_grant_id'),{})
        v['model_configuration']={'instance_id':instance,'mission_id':selected.get('current_mission_id'),
            'model_overrides':grant.get('execution_policy',{}).get('model_overrides',[])}
        from .report_catalog import catalog
        v['reports']=catalog(store,s,instance)
        if selected.get('kind')=='SURVEY':
            from . import survey
            v['survey']=survey.status(s,instance)
        from . import rounds,corrections
        runtime=next((j.get('result') or ({'state':'FAULT','error':j.get('error')} if j.get('error') else {})
            for j in reversed(project_jobs) if j.get('instance_id')==instance),{})
        v['round_result']=rounds.describe(s,instance,runtime) if instance else None
        v['corrections']=corrections.pending(s,instance) if instance else []
        v['correctable_work']=[{'binding_id':c['binding_id'],'stage_id':c['stage_id'],'role':c['role'],
            'description':store.read_blob(o['definition']['criterion_body_ref']).decode('utf-8')[:300]}
            for o in s['obligations'].values() for c in o['definition']['consumer_bindings']
            if c['instance_id']==instance and c['mission_id']==selected.get('current_mission_id')
            and o['definition']['type'] not in {'REPORT','CONTROL'}]
        v['control_fingerprint']=identity({k:v[k] for k in ('tasks','pending_work','execution','missions','reports','workflow','model_configuration','activity','project_jobs','project_execution','budget','round_result','corrections')} | {'survey':v.get('survey')})
        return v

    def workflow_inputs(self,key,query='',offset=0,limit=100):
        store=self.project(key);s=store.read_snapshot()
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'PAGE_INVALID','请选择有效的材料范围。')
        statements=[];sources=[];records=[];query=query.casefold()
        for ref,r in sorted(s['records'].items()):
            body=store.read_blob(r['body_sha256']).decode()
            if not query or query in body.casefold():
                item={'ref':ref,'kind':r['kind'],'title':body[:100],'body':body}
                if r['kind']!='Assessment':records.append(item)
                if r['kind']=='Statement':statements.append(item)
        for ref,r in sorted(s['sources'].items()):
            title=r.get('original_filename') or r.get('title') or r.get('filename') or ref
            if not query or query in title.casefold():sources.append({'source_ref':ref,'title':title,'bytes':r.get('bytes'),'media_type':r.get('media_type')})
        return {'commit':s['knowledge_commit'],'statements':statements[offset:offset+limit],'sources':sources[offset:offset+limit],'records':records[offset:offset+limit],
                'next_offset':offset+limit if max(len(records),len(sources))>offset+limit else None,
                'read_only':True,'model_calls':0}

    def assistant_status(self,key,session_id=None,offset=0,limit=30):
        """Conversation reads never run a model, recover a capture, or revise a report."""
        from . import assistant
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,
                'PAGE_INVALID','Select a bounded conversation page.')
        store=self.project(key);result=assistant.status(store,session_id,offset=offset,limit=limit)
        result['jobs']=[deepcopy(job) for (project,turn),job in self.assistant_jobs.items()
                        if project==key and (not session_id or job['session_id']==session_id)]
        snapshot=store.read_snapshot()
        context=result.get('context') or {}
        if context.get('report_id') in snapshot['reports']:
            result['report_versions']=self.report_versions(key,snapshot['reports'][context['report_id']])
            # Cache only the small directory of this exact immutable manuscript,
            # never full old reports on every status poll.
            body_hash=context.get('body_hash')
            if body_hash:
                from .report_revisions import sections
                if body_hash not in self.assistant_sections:
                    if len(self.assistant_sections)>=16:self.assistant_sections.pop(next(iter(self.assistant_sections)))
                    self.assistant_sections[body_hash]=sections(store.read_blob(body_hash))
                result['context']={**context,'sections':deepcopy(self.assistant_sections[body_hash])}
        for turn in result.get('turns',[]):
            action=turn.get('action') or {};rid=action.get('report_id')
            if rid in snapshot['reports']:
                entry=snapshot['reports'][rid]
                action['report_state']=entry['status']
                action['versions']=self.report_versions(key,entry)
                revision=action.get('revision');name=action.get('profile')
                profiles={}
                for profile in action.get('synchronized_profiles',[name] if name else []):
                    current=entry['profiles'].get(profile,{})
                    value=next((v for v in [current,*current.get('history',[])] if v.get('revision')==revision),{})
                    if value:profiles[profile]=value
                selected=profiles.get(name,{})
                preservation=selected.get('revision_check',{})
                semantic=(selected.get('semantic') or {}).get('revision_check',{})
                action['change_summary']={**deepcopy(preservation),'summary':semantic.get('summary'),
                    'requirements_verdict':semantic.get('verdict')}
                action['unmet_requirements']=semantic.get('unmet_requirement_refs',[])+semantic.get('uncertain_requirement_refs',[])
                action['checks']={profile:{'semantic':(value.get('semantic') or {}).get('verdict'),
                    'requirements':(value.get('semantic') or {}).get('revision_check',{}),
                    'rendered':bool(value.get('render')),'reviewed_pages':len(value.get('visual',{})),
                    'total_pages':len((value.get('render') or {}).get('pages',[]))} for profile,value in profiles.items()}
                turn['action']=action
        latest=(result.get('turns') or [{}])[-1]
        grant=snapshot['budget_grants'].get((latest.get('action') or {}).get('budget_grant_id'))
        if grant:
            from .scheduler import budget_remaining
            remaining=budget_remaining(snapshot,grant['budget_grant_id'])
            result['report_budget']={'max_calls':grant['max_calls'],'remaining':remaining,
                'used':grant['max_calls']-remaining,'budget_domain':grant.get('budget_domain','SCIENCE')}
        return result

    @staticmethod
    def report_versions(key,entry):
        rows=[]
        for profile,current in entry['profiles'].items():
            for value in [*current.get('history',[]),current]:
                row={'profile':profile,'revision':value['revision'],'body_sha256':value.get('body_sha256'),
                     'raw_body_sha256':value.get('raw_body_sha256'),'current':value is current,
                     'semantic_status':(value.get('semantic') or {}).get('verdict'),
                     'rendered':bool(value.get('render')),'visual_pages':len(value.get('visual',{}))}
                if value.get('render'):
                    row['url']='/api/report-file?project='+key+'&report='+entry['report_id']+'&profile='+profile+'&revision='+str(value['revision'])
                rows.append(row)
        return rows

    def assistant_evidence(self,key,session_id):
        from . import assistant
        import json
        result=assistant.export_summary(self.project(key),session_id)
        return {'summary_text':json.dumps(result,ensure_ascii=False,indent=2) if isinstance(result,dict) else str(result),
                'collected_at':result.get('exported_at',result.get('collected_at',now())) if isinstance(result,dict) else now(),
                'model_calls':0}

    def _operation_id(self,key=None,operation_id=None):
        require((key is None)!=(operation_id is None),'IDEMPOTENCY_REQUIRED','请指定一个原操作编号。')
        if key is not None:
            require(isinstance(key,str) and 16<=len(key)<=100 and key.replace('-','').isalnum(),'IDEMPOTENCY_REQUIRED','操作编号无效。')
            return identity(key)
        require(isinstance(operation_id,str) and len(operation_id)==64 and all(c in '0123456789abcdef' for c in operation_id),
                'IDEMPOTENCY_REQUIRED','原操作回执编号无效。')
        return operation_id

    def _operation_metadata(self,operation_id,receipt):
        operation=receipt.get('operation')
        require(isinstance(operation,dict) and set(operation)=={'id','name','payload','created_at'}
                and operation['id']==operation_id and isinstance(operation['name'],str)
                and isinstance(operation['payload'],dict) and isinstance(operation['created_at'],str),
                'OPERATION_RECEIPT_INVALID','操作回执缺少当前原生元数据。')
        return deepcopy(operation)

    def _operation_acknowledged(self,operation_id,receipt):
        path=self.root/'actions/acknowledgements'/(operation_id+'.json')
        if not path.exists():return False
        ack=loads(read(path))
        return ack.get('schema')=='pmrs.operation-ack/1' and ack.get('id')==operation_id and ack.get('digest')==receipt['digest'] and ack.get('state')==receipt['state']

    def operation_status(self,key=None,*,operation_id=None):
        operation_id=self._operation_id(key,operation_id);path=self.root/'actions'/(operation_id+'.json')
        if not path.exists():return {'state':'NOT_FOUND','workspace_id':self.workspace_id,'model_calls':0}
        receipt=loads(read(path))
        return {**receipt,'operation':self._operation_metadata(operation_id,receipt),
                'acknowledged':self._operation_acknowledged(operation_id,receipt),'workspace_id':self.workspace_id,'model_calls':0}

    def operations(self,offset=0,limit=50):
        """Discover durable, unacknowledged outcomes without replaying a form."""
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'PAGE_INVALID','请选择有效的操作回执范围。')
        rows=[]
        for path in sorted((self.root/'actions').glob('*.json')):
            operation_id=self._operation_id(operation_id=path.stem);receipt=loads(read(path))
            if self._operation_acknowledged(operation_id,receipt):continue
            row={**self._operation_metadata(operation_id,receipt),'state':receipt['state'],'digest':receipt['digest'],'at':receipt.get('at')}
            if 'error' in receipt:row['error']=receipt['error']
            rows.append(row)
        rows.sort(key=lambda r:(r.get('created_at') or '',r['id']),reverse=True)
        return {'operations':rows[offset:offset+limit],'next_offset':offset+limit if offset+limit<len(rows) else None,
                'workspace_id':self.workspace_id,'read_only':True,'model_calls':0}

    def acknowledge_operation(self,operation_id,digest):
        """Delivery acknowledgement only: preserves the business receipt."""
        operation_id=self._operation_id(operation_id=operation_id)
        with self.lock:
            with (self.root/'runtime/actions.lock').open('a+b') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                path=self.root/'actions'/(operation_id+'.json');require(path.exists(),'OPERATION_UNKNOWN','未找到原操作回执。')
                receipt=loads(read(path));self._operation_metadata(operation_id,receipt);require(receipt['digest']==digest,'ACTION_CONFLICT','确认必须绑定同一原操作回执。')
                require(receipt['state'] in {'COMPLETED','FAILED'},'ACTION_UNCERTAIN','原操作结果仍不确定；确认不会重发或撤销操作。')
                if not self._operation_acknowledged(operation_id,receipt):
                    folder=self.root/'actions/acknowledgements';folder.mkdir(exist_ok=True,mode=0o700)
                    atomic(folder/(operation_id+'.json'),canonical({'schema':'pmrs.operation-ack/1','id':operation_id,
                        'digest':digest,'state':receipt['state'],'acknowledged_at':now()}))
        return {'state':'ACKNOWLEDGED','id':operation_id,'workspace_id':self.workspace_id,'model_calls':0}

    def _raw(self,p,field='data',limit_mib=32):
        raw=base64.b64decode(p.get(field,''),validate=True)
        require(0<len(raw)<=limit_mib*1024**2,'PAYLOAD_LIMIT',f'请选择不超过 {limit_mib} MiB 的文件。')
        return raw

    def action(self,name,p,key):
        require(isinstance(key,str) and 16<=len(key)<=100 and key.replace('-','').isalnum(),'IDEMPOTENCY_REQUIRED','操作必须携带有效的重复提交保护编号。')
        require(isinstance(name,str) and 1<=len(name)<=80 and all(c in 'abcdefghijklmnopqrstuvwxyz-' for c in name),'ACTION_INVALID','操作名称无效。')
        require(isinstance(p,dict),'ACTION_INVALID','表单格式无效。')
        require(name in {'quit','login','setup-status','setup-configure','setup-select','setup-install','check-environment',
                'create','example','upload-archive','restore','add-source','new-workflow','configure-discovery','start','plan-work','defer-work','request-correction','extend-budget','pause',
                'continue','end','recover','reconcile','report','revise-report','abandon-report','configure','handoff','export',
                'assistant-open','assistant-authorize','assistant-send','assistant-recover',
                'survey-activity','survey-retrieve','survey-freeze','survey-plan','survey-source-status'},
                'ACTION_UNKNOWN','未登记的操作。')
        path=self.root/'actions'/(identity(key)+'.json');digest=identity({'action':name,'payload':p})
        with self.lock:
            # An OS lock also prevents two accidental backend processes from
            # accepting the same button click against this workspace.
            with (self.root/'runtime/actions.lock').open('a+b') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                if path.exists():
                    prior=loads(read(path));self._operation_metadata(identity(key),prior);require(prior['digest']==digest,'ACTION_CONFLICT','同一操作编号不能用于不同表单。')
                    require(prior['state']=='COMPLETED','ACTION_UNCERTAIN','上次操作尚未确认完成；请先刷新项目检查现有任务，不要重复授权。')
                    return prior['result']
                # Only navigation IDs accompany the receipt. Source bytes,
                # original form payloads and authentication tokens stay out.
                scope={}
                for field,prefix,size in (('project','WP-',35),('instance','INSTANCE-',73)):
                    value=p.get(field)
                    if isinstance(value,str) and value.startswith(prefix) and len(value)==size and all(c in '0123456789abcdef' for c in value[len(prefix):]):scope[field]=value
                metadata={'id':identity(key),'name':name,'payload':scope,'created_at':now()}
                base={'digest':digest,'operation':metadata}
                atomic(path,canonical({**base,'state':'PENDING','at':now()}))
                try:
                    result=self._action(name,p,key)
                except (PMRSError,ValueError,KeyError,OSError) as e:
                    # Preserve an inspectable failure. Never silently replay an
                    # operation which may have committed before failing.
                    atomic(path,canonical({**base,'state':'FAILED','at':now(),'error':getattr(e,'code','ACTION_FAILED')}))
                    raise
                atomic(path,canonical({**base,'state':'COMPLETED','at':now(),'result':result}))
                return result

    def _action(self,name,p,key):
        if name=='quit':
            require(not self.live_jobs(),'BACKGROUND_BUSY','请先暂停研究并等待当前请求结束，再退出后台。')
            return {'stopped':True}
        if name=='login':return self.login.start()
        if name.startswith('setup-'):
            from . import setup
            if name=='setup-status':return setup.status()
            if name=='setup-configure':return setup.configure(p.get('paths',{}))
            if name=='setup-select':return setup.select(p.get('kind'),ui_locale=self.preferences()['ui_locale'])
            if name=='setup-install':
                require(p.get('confirmed') is True,'SETUP_CONFIRMATION_REQUIRED','请先确认所选组件及安装来源。')
                return setup.start_install(p.get('component'),confirmed=True)
            raise PMRSError('ACTION_UNKNOWN','未登记的配置操作。')
        if name=='check-environment':
            from .runner import doctor
            from .render import doctor as pdf_doctor
            return {'client':self.login.inspect(),'execution':doctor(),'pdf':pdf_doctor(),'model_calls':0}
        if name in ('create','example'):
            kind=p.get('kind','TRW');require(kind in {'TRW','TFDW','SURVEY'},'WORKFLOW_KIND_INVALID','Choose a workflow.')
            if kind=='SURVEY':
                title=str(p.get('title') or p.get('name') or 'Literature survey').strip()
                require(0<len(title)<=200,'TITLE_INVALID','Project titles must contain 1–200 characters.')
                wid='WP-'+identity(key)[:32]
                result=self.engine.create_survey(self.root/'projects'/wid,p.get('survey_scope') or {},title=title,name=p.get('name') or title,synthetic=name=='example')
                store=result if isinstance(result,Store) else self.project(wid)
                iid=next(iter(store.read_snapshot()['instances']))
                return {'project':wid,'instance_id':iid,'synthetic':name=='example','model_calls':0}
            require(p.get('discovery_scope') is None or isinstance(p['discovery_scope'],dict),'DISCOVERY_SCOPE_INVALID','探索范围须包含现象、背景和允许范围。')
            raw=self._raw(p) if p.get('data') else str(p.get('text') or p.get('discovery_scope',{}).get('phenomenon','')).encode()
            require(raw.strip(),'SOURCE_REQUIRED','请输入完整题目或现象，或选择文件。')
            title=str(p.get('title','数学研究')).strip();require(0<len(title)<=200,'TITLE_INVALID','项目名称须为 1–200 字符。')
            discovery=None
            if kind=='TFDW':
                if name=='example':
                    from .demo import discovery_scope
                    discovery=discovery_scope(raw.decode('utf-8'))
                    discovery.update(p.get('discovery_scope') or {})
                else:discovery=self._discovery_form(p,raw)
            wid='WP-'+identity(key)[:32];root=self.root/'projects'/wid
            store=self.engine.create(root,raw,title=title,phenomenon=kind=='TFDW',synthetic=name=='example')
            s=store.read_snapshot();target=next(iter(s['records']),None)
            if kind=='TFDW':
                if discovery.get('phenomenon','').encode()==raw:
                    discovery.pop('phenomenon',None);discovery['phenomenon_ref']=next(iter(s['sources']))
                result=self.engine.new_workflow(store,kind,name=p.get('name') or title,discovery_scope=discovery)
            else:result=self.engine.new_workflow(store,kind,name=p.get('name') or title,target_ref=target)
            return {'project':wid,'instance_id':result['instance_id'],'synthetic':name=='example','model_calls':0}
        if name=='upload-archive':
            require(p.get('mode')=='restore','NATIVE_BACKUP_REQUIRED','这里只接受当前原生完整备份。')
            raw=self._raw(p,limit_mib=128);uid='UP-'+identity(raw.hex())[:32];path=self.root/'uploads'/(uid+'.zip')
            from .portability import verify_backup
            # Validate in memory before persisting an unsupported upload.
            manifest,_=verify_backup(raw)
            immutable(path,raw)
            summary={'format':manifest['project_schema'],'files':len(manifest['files']),'title':'原生完整备份','processes_restored':False}
            return {'upload_id':uid,'mode':'restore','summary':summary,'model_calls':0}
        if name=='restore':
            uid=p.get('upload_id','');require(uid.startswith('UP-') and len(uid)==35 and uid[3:].isalnum(),'UPLOAD_UNKNOWN','请先选择并检查原生备份。')
            source=safe_path(self.root,'uploads/'+uid+'.zip');wid='WP-'+identity(key)[:32];out=self.root/'projects'/wid
            from .portability import restore
            result=restore(source,out)
            return {'project':wid,'summary':result,'model_calls':0}
        store=self.project(p.get('project'));iid=p.get('instance')
        if name.startswith('assistant-'):
            from . import assistant
            if name=='assistant-open':
                context=deepcopy(p.get('context') or {})
                for source,destination in (('instance','instance_id'),('task_id','task_id'),('request_id','request_id'),
                        ('report_id','report_id'),('profile','profile'),('revision','revision'),('body_hash','body_hash')):
                    if p.get(source) is not None:context[destination]=p[source]
                return assistant.open_session(store,context,operation_id=identity(key))
            sid=p.get('session_id')
            if name=='assistant-authorize':return assistant.authorize(store,sid,p['max_calls'],operation_id=identity(key))
            if name=='assistant-send':
                result=assistant.submit(store,sid,p['text'],operation_id=identity(key),report_allowance=p.get('report_calls'))
                self.launch_assistant(p['project'],sid,result['turn_id'])
                return result
            # Recovery always names the original turn and therefore the original
            # request. A new finite report allowance does not add assistant calls.
            current=assistant.status(store,sid)
            require(any(t['turn_id']==p.get('turn_id') for t in current.get('turns',[])),
                    'ASSISTANT_TURN_UNKNOWN','Select a turn in this exact conversation.')
            if p.get('report_calls') is not None:
                assistant.authorize_report(store,sid,p['turn_id'],p['report_calls'],operation_id=identity(key))
            self.launch_assistant(p['project'],sid,p['turn_id'])
            return {'session_id':sid,'turn_id':p['turn_id'],'state':'QUEUED','model_calls':0}
        if name=='add-source':
            raw=self._raw(p) if p.get('data') else str(p.get('text','')).encode()
            result=store.commit(changes.prepare_material_input(store.read_snapshot(),raw,title=str(p.get('filename','补充材料')),media_type=str(p.get('media_type','text/plain')),blob_get=store.read_blob))
            return {**result,'model_calls':0}
        if name=='new-workflow':
            require(isinstance(p.get('name'),str) and p['name'].strip(),'INSTANCE_NAME_REQUIRED','请为新的研究流程填写可识别的名称。')
            scope=self._discovery_form(p) if p['kind']=='TFDW' else None
            return self.engine.new_workflow(store,p['kind'],name=p['name'],target_ref=p.get('target_ref'),target=p.get('target_text'),discovery_scope=scope,survey_scope=p.get('survey_scope'))
        if name.startswith('survey-'):
            from . import survey
            if name=='survey-source-status':return survey.mark_source(store,iid,p['source_ref'],withdrawn=p.get('withdrawn',False),version_conflict=p.get('version_conflict',False),reason=p['reason'])
            if name=='survey-retrieve':return survey.retrieve(store,iid,p['plan_ref'])
            if name=='survey-freeze':return survey.freeze_knowledge(store,iid,selected_refs=p.get('selected_refs'),question_ids=p.get('question_ids'))
            if name=='survey-plan':
                allowed=('view','audience','prerequisites','proof_promises','omissions','limitations','comparison_group')
                return survey.create_output_plan(store,iid,p['snapshot_ref'],profile=p['profile'],**{k:p[k] for k in allowed if k in p})
            from .codex_client import policy
            from .demo import policy as demo_policy
            config=demo_policy() if store.read_snapshot()['synthetic_test_only'] else policy()
            result=survey.start_activity(store,iid,p['stage'],p['intent'],max_calls=int(p['max_calls']),
                max_workers=int(p.get('max_workers',store.read_snapshot().get('max_workers',1))),policy=config,model_overrides=p.get('model_overrides',[]),
                allow_reports=p.get('allow_reports'),selected_refs=p.get('selected_refs'),source_refs=p.get('source_refs'),
                role=p.get('role'),max_research_attempts=int(p.get('max_research_attempts',1)))
            if p['stage']!='S5':self.launch(p['project'],iid)
            return result
        if name=='configure-discovery':
            existing=store.read_snapshot()['instances'][iid]
            incoming=p.get('discovery_scope') or {}
            require(isinstance(incoming,dict),'DISCOVERY_SCOPE_INVALID','请填写现象、不可改变的背景和允许探索的范围。')
            merged=dict(existing.get('discovery_scope',{}))
            if existing.get('discovery_brief_ref'):merged.setdefault('phenomenon_ref',existing['discovery_brief_ref'])
            for field in ('phenomenon','immutable_background','allowed_axes'):
                if incoming.get(field):merged.pop(field+'_ref',None)
            merged.update(incoming)
            return self.engine.configure_discovery(store,iid,self._discovery_form({**p,'discovery_scope':merged}))
        if name=='extend-budget':return self.engine.extend_budget(store,iid,p['added_calls'],p['reason'])
        if name=='request-correction':return self.engine.request_correction(store,iid,p['binding_id'],p['instruction'],p['success_criterion'])
        if name=='defer-work':return self.engine.defer_work(store,iid,p['binding_id'],p['reason'])
        if name=='plan-work':
            from .codex_client import policy
            from .demo import policy as demo_policy
            config=demo_policy() if store.read_snapshot()['synthetic_test_only'] else policy()
            require(type(p.get('run',False)) is bool,'ACTION_INVALID','Explicit run choice required')
            result=self.engine.plan_work(store,iid,p['intent'],p['items'],mission_id=p.get('mission_id'),
                max_calls=int(p.get('max_calls',8)),max_workers=int(p.get('max_workers',store.read_snapshot().get('max_workers',1))),
                policy=config,allow_reports=p.get('allow_reports',False))
            if p.get('run'):self.launch(p['project'],iid)
            return result
        if name=='start':
            from .codex_client import policy
            from .demo import policy as demo_policy
            synthetic=store.read_snapshot()['synthetic_test_only'];config=demo_policy() if synthetic else policy()
            if p.get('model_override'):config['model_override']=p['model_override']
            require(type(p.get('report_first',False)) is bool,'ACTION_INVALID','报告前置选项必须明确选择。')
            result=self.engine.start_round(store,iid,p['intent'],max_calls=int(p['max_calls']),max_workers=int(p.get('max_workers',store.read_snapshot().get('max_workers',1))),policy=config,
                model_overrides=p.get('model_overrides',[]),selected_refs=p.get('selected_refs'),source_refs=p.get('source_refs'),report_first_actions=['CONTINUE','END','ADOPT','ADOPT_HANDOFF'] if p.get('report_first') else [])
            self.launch(p['project'],iid);return result
        if name=='pause':return self.engine.pause(store,iid,'用户在网页中暂停研究；保留在途请求及捕获。')
        if name in ('continue','end'):
            selected=store.read_snapshot(p['commit']);report_ref=selected.get('active_reports',{}).get(iid)
            result=self.engine.decide(store,iid,'CONTINUE' if name=='continue' else 'END',p.get('note','用户在网页明确作出决定。'),snapshot_commit=p['commit'],report_ref=report_ref)
            if name=='continue':self.launch(p['project'],iid)
            return result
        if name=='recover':
            result=self.engine.recover(store,p['request_id']);return result
        if name=='reconcile':
            return self.engine.reconcile_unknown(store,iid,p['request_id'],p['disposition'],p['note'],not_sent_evidence_ref=p.get('not_sent_evidence_ref'))
        if name=='report':
            from . import reports
            result=reports.create(store,iid,profiles=p.get('profiles'),plan_ref=p.get('plan_ref'));self.launch(p['project'],iid,report=True,report_id=result);return {'report_id':result}
        if name=='revise-report':
            from . import reports
            result=reports.revise(store,iid,p['profile'],p['reason'],report_id=p.get('report_id'));self.launch(p['project'],iid,report=True,report_id=result['report_id']);return result
        if name=='abandon-report':
            from . import reports
            return reports.abandon(store,iid,p['reason'],report_id=p.get('report_id'))
        if name=='configure':
            return self.engine.update_configuration(store,iid,p.get('model_overrides',[]),reset_scopes=p.get('reset_scopes',[]))
        if name=='handoff':
            direction=p['direction'];discovery=None
            is_survey=direction in {'SURVEY_TO_TRW','SURVEY_TO_TFDW'}
            scope={'target_refs':[p.get('target_ref') or p.get('candidate_ref')]} if is_survey else {'candidate_refs':[p['candidate_ref']]} if direction=='TFDW_TO_TRW' else {'target_refs':[store.read_snapshot()['instances'][iid]['target_ref']]}
            if direction in {'TRW_TO_TFDW','SURVEY_TO_TFDW'}:
                discovery=self.engine.prepare_discovery_scope(store,self._discovery_form(p, str(p.get('brief','')).encode() or None))
                scope['source_refs']=list(discovery.values());scope['discovery_scope']=discovery
            prepared=self.engine.prepare_handoff(store,iid,direction,scope)
            s=store.read_snapshot();decision=self.engine.decide(store,iid,'ADOPT' if direction=='TFDW_TO_TRW' else 'ADOPT_HANDOFF',p['note'],snapshot_commit=s['knowledge_commit'],candidate_ref=None if is_survey else p.get('candidate_ref'),report_ref=s.get('active_reports',{}).get(iid))
            if discovery:
                decision['discovery_brief_ref']=discovery.get('phenomenon_ref');decision['discovery_scope']=discovery
            if p.get('name'):decision['name']=p['name']
            return self.engine.adopt_handoff(store,prepared['handoff_id'],decision)
        if name=='export':
            from .portability import export_project
            filename=identity(key)+'.zip';result=export_project(store,self.root/'downloads'/filename)
            return {'download':'/api/download?file='+filename,'sha256':result['sha256'],'bytes':result['bytes'],'model_calls':0}
        raise PMRSError('ACTION_UNKNOWN','未登记的操作。')

    def _discovery_form(self,p,raw=None):
        scope=p.get('discovery_scope') or {}
        require(isinstance(scope,dict),'DISCOVERY_SCOPE_INVALID','请填写现象、不可改变的背景和允许探索的范围。')
        scope=dict(scope)
        if raw is not None and not scope.get('phenomenon') and not scope.get('phenomenon_ref'):
            scope['phenomenon']=raw.decode('utf-8')
        if p.get('draft') is not True:
            labels={'phenomenon':'现象或出发问题','immutable_background':'不可改变的背景','allowed_axes':'允许探索的范围（若无附加限制，请明确说明）'}
            missing=[label for field,label in labels.items() if not (isinstance(scope.get(field),str) and scope[field].strip()) and not scope.get(field+'_ref')]
            require(not missing,'DISCOVERY_SCOPE_REQUIRED','请补充：'+'、'.join(missing)+'。也可先保存草稿，补齐后再开始。')
        return scope

    def launch(self,key,iid,*,report=False,report_id=None):
        with self.lock:
            if report and report_id is None:report_id=self.project(key).read_snapshot().get('active_reports',{}).get(iid)
            require(not report or bool(report_id),'REPORT_REQUIRED','Select an exact report before scheduling it.')
            # One Web driver serves every authorized instance in this project.
            # A late report is observed by the driver's host-only planning hook.
            current=next((j for (p,_),j in self.jobs.items() if p==key and
                          (j['state'] in {'RUNNING','QUEUED'} or j.get('retry_pending'))),None)
            if current:
                if report:
                    current['report_requested']=True
                    if report_id!=current.get('running_report_id') and report_id not in current['report_ids']:current['report_ids'].append(report_id)
                return current
            job={'state':'QUEUED','instance_id':iid,'kind':'REPORT' if report else 'RESEARCH','started_at':now(),'report_requested':report,
                 'report_ids':[report_id] if report else [],'running_report_id':None,'retry_pending':False};self.jobs[(key,iid)]=job
            def work():
                try:
                    store=self.project(key);synthetic=store.read_snapshot()['synthetic_test_only']
                    from .runner import CodexExecutor
                    from .demo import executor as demo_executor
                    executor=demo_executor() if synthetic else CodexExecutor()
                    def retry_same(operation,selected_instance):
                        while True:
                            job.update(state='RUNNING',retry_pending=False)
                            result=operation()
                            if result.get('state') not in {'RESOURCE_WAIT','WAITING_RESOURCE','COORDINATOR_ACTIVE'}:return result
                            if store.read_snapshot()['instances'][selected_instance]['status']!='ACTIVE':return {**result,'state':'PAUSED'}
                            job.update(state='WAITING_RESOURCE',result=result,retry_pending=True)
                            # The coordinator and preparation leases have already
                            # been released. Re-enter the same frozen request.
                            threading.Event().wait(.75)
                    result=retry_same(lambda:self.engine.run_round(store,iid,executor=executor),iid) if not report else None
                    while True:
                        with self.lock:
                            if not job['report_ids']:
                                job.update(state='WAITING',result=result,finished_at=now(),running_report_id=None,retry_pending=False);break
                            selected_report=job['report_ids'].pop(0);job['running_report_id']=selected_report
                        from . import reports
                        from .render import Renderer
                        report_instance=store.read_snapshot()['reports'][selected_report]['scope']['instance_ids'][0]
                        job['kind']='REPORT'
                        result=retry_same(lambda:reports.run(store,report_instance,executor=executor,
                            policy=self.engine.policy(store,report_instance),renderer=Renderer(),report_id=selected_report),report_instance)
                except Exception as e:
                    code=getattr(e,'code','EXECUTION_FAILED')
                    job.update(state='WAITING_RESOURCE' if code in {'RESOURCE_WAIT','RESOURCE_DISK_LOW'} else 'BLOCKED',error=code,message=str(e),finished_at=now(),retry_pending=False)
            threading.Thread(target=work,name='pmrs-'+iid[-12:],daemon=True).start();return job

    def launch_assistant(self,key,session_id,turn_id):
        """Run one original assistant turn, then only its authorized report action.

        This driver never resumes a research instance or invokes run_round.
        All durable state remains in the native service and operation ledger.
        """
        with self.lock:
            current=self.assistant_jobs.get((key,turn_id))
            if current and (current['state'] in {'RUNNING','QUEUED','REPORT_RUNNING'} or current.get('retry_pending')):
                return current
            job={'session_id':session_id,'turn_id':turn_id,'state':'QUEUED','started_at':now(),'retry_pending':False}
            self.assistant_jobs[(key,turn_id)]=job
            def work():
                from . import assistant,reports
                store=self.project(key)
                try:
                    synthetic=store.read_snapshot()['synthetic_test_only']
                    from .demo import policy as demo_policy,executor as report_demo_executor
                    from .runner import CodexExecutor
                    executor=assistant.demo_executor() if synthetic else CodexExecutor()
                    policy=demo_policy() if synthetic else None
                    while True:
                        job.update(state='RUNNING',retry_pending=False)
                        result=assistant.run_turn(store,turn_id,executor=executor,policy=policy)
                        if result.get('state') not in {'RESOURCE_WAIT','WAITING_RESOURCE'}:break
                        job.update(state='WAITING_RESOURCE',result=result,retry_pending=True)
                        threading.Event().wait(.75)
                    job['result']=result
                    if result.get('state') not in {'ACCEPTED','EXACT_DUPLICATE'}:
                        job.update(state=result.get('state','BLOCKED'),finished_at=now(),retry_pending=False)
                        return
                    # The helper checks accepted output and the actual original
                    # user message. A model's proposed action has no authority.
                    authorization=assistant.revision_authorization(store,turn_id)
                    if authorization is not None:
                        action=reports.revise_from_assistant(store,authorization,
                            operation_id=identity({'assistant_turn':turn_id},'REPORT-ACTION-'))
                        assistant.record_action(store,turn_id,action)
                        rid=action['report_id'];entry=store.read_snapshot()['reports'][rid]
                        # A new human allowance event extends only this original
                        # report. Repeated recovery of the same event adds zero.
                        reports.extend_revision_budget(store,rid,authorization)
                        iid=entry['scope']['instance_ids'][0]
                        from .render import Renderer
                        report_executor=report_demo_executor(blob_get=store.read_blob) if synthetic else CodexExecutor()
                        while True:
                            job.update(state='REPORT_RUNNING',report_id=rid,retry_pending=False)
                            result=reports.run(store,iid,executor=report_executor,
                                policy=reports.policy_for_report(store,rid),renderer=Renderer(),report_id=rid)
                            if result.get('state') not in {'RESOURCE_WAIT','WAITING_RESOURCE','COORDINATOR_ACTIVE'}:break
                            job.update(state='WAITING_RESOURCE',result=result,retry_pending=True)
                            threading.Event().wait(.75)
                        from .scheduler import budget_remaining
                        exhausted=(result.get('state')=='WAIT' and not result.get('code') and
                            budget_remaining(store.read_snapshot(),action['budget_grant_id'])<=0)
                        if exhausted:result={**result,'state':'WAITING_REPORT_BUDGET','code':'REPORT_BUDGET_REQUIRED'}
                        assistant.record_action(store,turn_id,{**action,'result':result,
                            **({'state':'WAITING_REPORT_BUDGET','error':'REPORT_BUDGET_REQUIRED'} if exhausted else {})})
                        job['result']=result
                    job.update(state='COMPLETED' if result.get('state') in {'ACCEPTED','EXACT_DUPLICATE','COMPLETED_CURRENT_REPORT'}
                               else result.get('state','BLOCKED'),finished_at=now(),retry_pending=False)
                except Exception as error:
                    code=getattr(error,'code','ASSISTANT_EXECUTION_FAILED')
                    job.update(state='WAITING_REPORT_BUDGET' if code=='REPORT_BUDGET_REQUIRED' else 'BLOCKED',
                               error=code,finished_at=now(),retry_pending=False)
                    # Store only a stable public error code here. Captured model
                    # bytes and bounded diagnostic evidence retain their native
                    # identities; raw process errors can contain sensitive text.
                    try:
                        previous=assistant.turn_status(store,turn_id).get('action') or {}
                        assistant.record_action(store,turn_id,{**previous,'state':job['state'],'error':code})
                    except (PMRSError,ValueError,KeyError,OSError):pass
            threading.Thread(target=work,name='pmrs-assistant-'+turn_id[-12:],daemon=True).start()
            return job

    def live_jobs(self):return any(j['state'] in {'RUNNING','QUEUED','REPORT_RUNNING'} or j.get('retry_pending')
                                  for j in [*self.jobs.values(),*self.assistant_jobs.values()])

    def recover_backend_state(self):
        """Startup reconciliation only; ordinary readers never change a store."""
        from .runner import coordinator
        from . import execution
        results=[]
        for row in self.list()['projects']:
            if row.get('error'):continue
            store=self.project(row['key'])
            try:
                with coordinator(store):
                    for request in store.read_snapshot()['requests'].values():
                        if request['execution_state'] in {'RESERVED','SENT'}:
                            store.commit_execution(execution.event('UNKNOWN',{'request_id':request['request_id'],
                                'execution_id':request['execution_id'],'reason':'Backend restarted; original request outcome must be reconciled before any retry.'}))
                            results.append(request['request_id'])
            except PMRSError as error:
                if error.code!='COORDINATOR_BUSY':raise
        return {'uncertain_requests':results,'resent':0,'admitted':0}
