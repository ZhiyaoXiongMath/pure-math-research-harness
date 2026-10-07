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
        self.root=safe_path(Path(root));self.engine=Engine();self.login=Login();self.jobs={};self.lock=threading.RLock();self.project_locks={};self.object_labels={}
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
        grants=[g for g in s['budget_grants'].values() if not instance or g['instance_id']==instance]
        remaining=sum(budget_remaining(s,g['budget_grant_id']) for g in grants);total=project_remaining(s)
        v['synthetic']=s['synthetic_test_only'];v['budget']={'project':s['project_budget'],'grants':grants,
            'remaining_calls':remaining if remaining!=float('inf') else None,'project_remaining_calls':total if total!=float('inf') else None}
        v['tasks']=[{k:t.get(k) for k in ('task_id','instance_id','stage_id','role','model_policy','model_policy_resolution','request_id')} for t in s['tasks'].values() if not instance or t['instance_id']==instance]
        from .workflows.registry import spec
        for task in v['tasks']:task['activity_label']=spec(task['stage_id'])['ui_labels']['zh-CN']
        v['missions']=[m for m in s['missions'].values() if not instance or m['instance_id']==instance]
        selected=s['instances'].get(instance,{})
        mission=s['missions'].get(selected.get('current_mission_id'),{})
        grant=s['budget_grants'].get(mission.get('budget_grant_id'),{})
        v['model_configuration']={'instance_id':instance,'mission_id':selected.get('current_mission_id'),
            'model_overrides':grant.get('execution_policy',{}).get('model_overrides',[])}
        return v

    def workflow_inputs(self,key,query='',offset=0,limit=100):
        store=self.project(key);s=store.read_snapshot()
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=100,'PAGE_INVALID','请选择有效的材料范围。')
        statements=[];sources=[];query=query.casefold()
        for ref,r in sorted(s['records'].items()):
            if r['kind']!='Statement':continue
            body=store.read_blob(r['body_sha256']).decode()
            if not query or query in body.casefold():statements.append({'ref':ref,'title':body[:100],'body':body})
        for ref,r in sorted(s['sources'].items()):
            title=r.get('original_filename') or r.get('title') or r.get('filename') or ref
            if not query or query in title.casefold():sources.append({'source_ref':ref,'title':title,'bytes':r.get('bytes'),'media_type':r.get('media_type')})
        return {'commit':s['knowledge_commit'],'statements':statements[offset:offset+limit],'sources':sources[offset:offset+limit],
                'next_offset':offset+limit if max(len(statements),len(sources))>offset+limit else None,
                'read_only':True,'model_calls':0}

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
                'create','example','upload-archive','restore','add-source','new-workflow','configure-discovery','start','pause',
                'continue','end','recover','reconcile','report','revise-report','abandon-report','configure','handoff','export'},
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
            if name=='setup-select':return setup.select(p.get('kind'))
            if name=='setup-install':
                require(p.get('confirmed') is True,'SETUP_CONFIRMATION_REQUIRED','请先确认所选组件及安装来源。')
                return setup.start_install(p.get('component'),confirmed=True)
            raise PMRSError('ACTION_UNKNOWN','未登记的配置操作。')
        if name=='check-environment':
            from .runner import doctor
            from .render import doctor as pdf_doctor
            return {'client':self.login.inspect(),'execution':doctor(),'pdf':pdf_doctor(),'model_calls':0}
        if name in ('create','example'):
            kind=p.get('kind','TRW');require(kind in {'TRW','TFDW'},'WORKFLOW_KIND_INVALID','请选择研究方式。')
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
        if name=='add-source':
            raw=self._raw(p) if p.get('data') else str(p.get('text','')).encode()
            result=store.commit(changes.prepare_material_input(store.read_snapshot(),raw,title=str(p.get('filename','补充材料')),media_type=str(p.get('media_type','text/plain')),blob_get=store.read_blob))
            return {**result,'model_calls':0}
        if name=='new-workflow':
            require(isinstance(p.get('name'),str) and p['name'].strip(),'INSTANCE_NAME_REQUIRED','请为新的研究流程填写可识别的名称。')
            scope=self._discovery_form(p) if p['kind']=='TFDW' else None
            return self.engine.new_workflow(store,p['kind'],name=p['name'],target_ref=p.get('target_ref'),target=p.get('target_text'),discovery_scope=scope)
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
        if name=='start':
            from .codex_client import policy
            from .demo import policy as demo_policy
            synthetic=store.read_snapshot()['synthetic_test_only'];config=demo_policy() if synthetic else policy()
            if p.get('model_override'):config['model_override']=p['model_override']
            require(type(p.get('report_first',False)) is bool,'ACTION_INVALID','报告前置选项必须明确选择。')
            result=self.engine.start_round(store,iid,p['intent'],max_calls=int(p['max_calls']),max_workers=int(p.get('max_workers',1)),policy=config,
                model_overrides=p.get('model_overrides',[]),report_first_actions=['CONTINUE','END','ADOPT','ADOPT_HANDOFF'] if p.get('report_first') else [])
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
            result=reports.create(store,iid);self.launch(p['project'],iid,report=True);return {'report_id':result}
        if name=='revise-report':
            from . import reports
            result=reports.revise(store,iid,p['profile'],p['reason']);self.launch(p['project'],iid,report=True);return result
        if name=='abandon-report':
            from . import reports
            return reports.abandon(store,iid,p['reason'])
        if name=='configure':
            return self.engine.update_configuration(store,iid,p.get('model_overrides',[]),reset_scopes=p.get('reset_scopes',[]))
        if name=='handoff':
            direction=p['direction'];discovery=None
            scope={'candidate_refs':[p['candidate_ref']]} if direction=='TFDW_TO_TRW' else {'target_refs':[store.read_snapshot()['instances'][iid]['target_ref']]}
            if direction=='TRW_TO_TFDW':
                discovery=self.engine.prepare_discovery_scope(store,self._discovery_form(p, str(p.get('brief','')).encode() or None))
                scope['source_refs']=list(discovery.values());scope['discovery_scope']=discovery
            prepared=self.engine.prepare_handoff(store,iid,direction,scope)
            s=store.read_snapshot();decision=self.engine.decide(store,iid,'ADOPT' if direction=='TFDW_TO_TRW' else 'ADOPT_HANDOFF',p['note'],snapshot_commit=s['knowledge_commit'],candidate_ref=p.get('candidate_ref'),report_ref=s.get('active_reports',{}).get(iid))
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

    def launch(self,key,iid,*,report=False):
        with self.lock:
            current=self.jobs.get((key,iid))
            if current and current['state'] in {'RUNNING','QUEUED'}:
                if report:current['report_requested']=True
                return current
            project_lock=self.project_locks.setdefault(key,threading.Lock())
            job={'state':'QUEUED','instance_id':iid,'kind':'REPORT' if report else 'RESEARCH','started_at':now(),'report_requested':report};self.jobs[(key,iid)]=job
            def work():
                try:
                    with project_lock:
                        job['state']='RUNNING'
                        store=self.project(key);synthetic=store.read_snapshot()['synthetic_test_only']
                        from .runner import CodexExecutor
                        from .demo import executor as demo_executor
                        executor=demo_executor() if synthetic else CodexExecutor()
                        result=self.engine.run_round(store,iid,executor=executor) if not report else None
                        with self.lock:
                            requested=job['report_requested']
                            if not requested:job.update(state='WAITING',result=result,finished_at=now())
                        if requested:
                            from . import reports
                            from .render import Renderer
                            job['kind']='REPORT'
                            result=reports.run(store,iid,executor=executor,policy=self.engine.policy(store,iid),renderer=Renderer())
                            with self.lock:job.update(state='WAITING',result=result,finished_at=now())
                except Exception as e:
                    job.update(state='BLOCKED',error=getattr(e,'code','EXECUTION_FAILED'),message=str(e),finished_at=now())
            threading.Thread(target=work,name='pmrs-'+iid[-12:],daemon=True).start();return job

    def live_jobs(self):return any(j['state'] in {'RUNNING','QUEUED'} for j in self.jobs.values())

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
