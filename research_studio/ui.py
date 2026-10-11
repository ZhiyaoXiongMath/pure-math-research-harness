"""Authenticated loopback research reader. Every GET is strictly read-only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
import hmac
import json
import secrets
import threading
import os
import stat
from http.cookies import SimpleCookie
from . import views
from .util import require, read, safe_path, canonical, PMRSError

STATIC=Path(__file__).with_name('static')
MIME={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
      '.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8'}
MAX_RESPONSE=16*1024*1024


def handler(store,token,*,allowed_instances=None):
    assets={p.relative_to(STATIC).as_posix():p for p in STATIC.rglob('*') if p.is_file() and not p.is_symlink()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,code,body,kind='application/json; charset=utf-8'):
            if isinstance(body,dict):body=json.dumps(body,ensure_ascii=False).encode()
            require(len(body)<=MAX_RESPONSE,'PAYLOAD_LIMIT','Response exceeds bounded reader size; select a smaller scope')
            self.send_response(code);self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            try:
                require(len(self.path)<=8192,'PATH_INVALID','Request path too long')
                host=self.headers.get('Host','')
                require(host.split(':')[0] in ('127.0.0.1','localhost'),'UNAUTHORIZED','Loopback Host required')
                parsed=urlsplit(self.path);path=unquote(parsed.path)
                require(not parsed.scheme and not parsed.netloc and '\\' not in path and '..' not in path.split('/') and '\x00' not in path,'PATH_INVALID','Invalid reader path')
                if path=='/':self.reply(200,read(STATIC/'index.html'),'text/html; charset=utf-8');return
                if path.startswith('/static/'):
                    name=path[len('/static/'):];require(name in assets,'PATH_INVALID','Unknown static asset')
                    self.reply(200,read(assets[name]),MIME.get(assets[name].suffix,'application/octet-stream'));return
                require(hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token),'UNAUTHORIZED','Session token required')
                query=parse_qs(parsed.query,keep_blank_values=True,strict_parsing=True)
                require(all(len(v)==1 for v in query.values()),'PAGE_INVALID','Repeated parameters are not accepted')
                allowed={'instance','commit','query','offset','limit','ref','from'}
                require(set(query)<=allowed,'PAGE_INVALID','Unknown reader query')
                q={k:v[0] for k,v in query.items()};iid=q.get('instance') or None
                if allowed_instances is not None:
                    require(iid in allowed_instances,'UNAUTHORIZED','Select an authorized instance scope')
                # Pin one snapshot for the entire response. Later pages explicitly
                # carry that same commit, so concurrent writes cannot splice text.
                snapshot=store.read_snapshot(q.get('commit') or None)
                if path=='/api/status':result=views.status(snapshot,store,instance_id=iid)
                elif path=='/api/current':result=views.current(snapshot,store.read_blob,instance_id=iid,
                    query=q.get('query'),offset=int(q.get('offset',0)),limit=int(q.get('limit',20)),include_body=False)
                elif path=='/api/frontier':result=views.frontier(snapshot,store.read_blob,instance_id=iid)
                elif path=='/api/sources':result=views.sources(snapshot,store.read_blob,instance_id=iid)
                elif path=='/api/history':result=views.history(snapshot,store,instance_id=iid,query=q.get('query'),offset=int(q.get('offset',0)),limit=int(q.get('limit',20)))
                elif path=='/api/reports':
                    from .report_catalog import catalog
                    result={'commit':snapshot['knowledge_commit'],'reports':catalog(store,snapshot,iid)}
                elif path=='/api/diff':
                    require(q.get('from'),'SNAPSHOT_REQUIRED','Select a starting commit')
                    result=views.diff(store.read_snapshot(q['from']),snapshot,instance_id=iid)
                elif path=='/api/body':
                    ref=q.get('ref');require(ref in views.scope_refs(snapshot,iid) and ref in snapshot['records'],'UNAUTHORIZED','Exact record is outside the selected scope')
                    record=store.read_record(ref)
                    require(record==snapshot['records'][ref],'RECORD_CHANGED','Frozen record differs')
                    result={'commit':snapshot['knowledge_commit'],'ref':ref,'body_sha256':record['body_sha256'],
                            'body':store.read_blob(record['body_sha256']).decode('utf-8')}
                else:raise PMRSError('ROUTE_NOT_FOUND','Unknown reader endpoint')
                self.reply(200,result)
            except (PMRSError,ValueError,KeyError,UnicodeError) as error:
                self.reply(403 if getattr(error,'code',None)=='UNAUTHORIZED' else 404 if getattr(error,'code',None)=='ROUTE_NOT_FOUND' else 400,
                    {'error':getattr(error,'code','READER_INPUT_INVALID'),'message':str(error)})
        def do_POST(self): self.reply(405,{'error':'READ_ONLY_UI','message':'Human operations use the explicit CLI.'})
        do_PUT=do_POST
        do_DELETE=do_POST
        do_PATCH=do_POST
    return Handler


def serve(store,port=8765,host='127.0.0.1'):
    require(host=='127.0.0.1','HOST_INVALID','Only loopback listening is supported')
    require(type(port) is int and 1024<=port<=65535,'PORT_INVALID','Use a nonprivileged loopback port')
    from .workspace import Workspace
    from .util import identity
    import webbrowser
    key='WP-'+identity(str(store.root))[:32]
    class ProjectWorkspace(Workspace):
        def project(self,selected):return store if selected==key else super().project(selected)
        def list(self):
            state=store.read_snapshot();result=super().list()
            result['projects'].insert(0,{'key':key,'title':state['title'],'project_id':state['project_id'],
                'instances':list(state['instances'].values()),'synthetic':state['synthetic_test_only']})
            return result
    workspace=ProjectWorkspace(store.root/'.runtime/ui-workspace');token=secrets.token_urlsafe(32)
    with ThreadingHTTPServer((host,port),app_handler(workspace,token)) as server:
        webbrowser.open(f'http://127.0.0.1:{port}/#session='+token,new=2)
        print(f'网页工作区已打开：http://127.0.0.1:{port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass


def app_handler(workspace,bootstrap_token):
    """Same-origin local sessions; GETs never perform research actions."""
    sessions={};session_lock=threading.Lock()
    assets={p.relative_to(STATIC).as_posix():p for p in STATIC.rglob('*') if p.is_file() and not p.is_symlink()}
    class App(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value,mime='application/json; charset=utf-8',*,cookie=None,filename=None):
            body=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,(dict,list)) else value
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if cookie:self.send_header('Set-Cookie',cookie)
            if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
            self.end_headers();self.wfile.write(body)
        def reply_native_stream(self,path):
            # The exact saved extent at open is streamed without a size cap or
            # text conversion. Later appends belong to a subsequent download.
            fd=os.open(safe_path(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as source:
                info=os.fstat(source.fileno());require(stat.S_ISREG(info.st_mode),'FILE_INVALID','Native evidence must be a regular file.')
                self.send_response(200);self.send_header('Content-Type','application/octet-stream')
                self.send_header('Content-Length',str(info.st_size));self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Disposition','attachment; filename="instance-shared-'+path.name+'"')
                self.send_header('X-PMRS-Evidence-Scope','INSTANCE_SHARED_NATIVE_MAIN_STREAM')
                self.send_header('X-PMRS-Bytes-at-Open',str(info.st_size));self.end_headers()
                remaining=info.st_size
                while remaining:
                    chunk=source.read(min(1024*1024,remaining))
                    if not chunk:raise ConnectionError('Native evidence changed while streaming')
                    self.wfile.write(chunk);remaining-=len(chunk)
        def route(self):
            require(len(self.path)<=8192,'PATH_INVALID','请求地址过长。')
            require(self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}','UNAUTHORIZED','无效的本机服务地址。')
            parsed=urlsplit(self.path);path=unquote(parsed.path)
            require(not parsed.scheme and not parsed.netloc and '\\' not in path and '..' not in path.split('/') and '\x00' not in path,'PATH_INVALID','无效地址。')
            q=parse_qs(parsed.query,keep_blank_values=True)
            require(all(len(x)==1 for x in q.values()),'PAGE_INVALID','参数不得重复。')
            return path,{k:v[0] for k,v in q.items()}
        def session(self):
            cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
            sid=cookie['pmrs_session'].value if 'pmrs_session' in cookie else ''
            with session_lock:s=sessions.get(sid)
            require(s is not None,'SESSION_REQUIRED','请从桌面启动器重新打开 PMRS。')
            return s
        def origin(self):
            require(self.headers.get('Origin')==f'http://127.0.0.1:{self.server.server_port}','UNAUTHORIZED','操作须来自当前 PMRS 页面。')
            require(self.headers.get('Sec-Fetch-Site','same-origin') in {'same-origin','none'},'UNAUTHORIZED','跨站操作已拒绝。')
        def workspace_scope(self):
            value=self.headers.get('X-PMRS-Workspace')
            require(value is None or value==workspace.workspace_id,'WORKSPACE_MISMATCH','当前地址对应另一个工作区，请重新打开页面；原操作不会重放。')
        def error(self,e):
            code=getattr(e,'code','INPUT_INVALID')
            self.reply(403 if code in {'UNAUTHORIZED','SESSION_REQUIRED','CSRF_INVALID','WORKSPACE_MISMATCH'} else 404 if code=='ROUTE_NOT_FOUND' else 400,
                {'error':code,'message_key':'error.'+code,'params':{},'message':str(e),
                 'guidance_key':'error.guidance','guidance':'Check the selected project, scope and authorization. Detailed diagnostics are available for maintenance.'})
        def do_GET(self):
            try:
                path,q=self.route()
                if path=='/':self.reply(200,read(STATIC/'index.html'),MIME['.html']);return
                if path.startswith('/static/'):
                    name=path[8:];require(name in assets,'PATH_INVALID','未找到资源。')
                    self.reply(200,read(assets[name]),MIME.get(assets[name].suffix,'application/octet-stream'));return
                session=self.session()
                self.workspace_scope()
                require(path in {'/api/session','/api/preferences','/api/survey','/api/workspace','/api/operations','/api/operation','/api/workflow-graph',
                    '/api/progress','/api/workflow-inputs','/api/settings','/api/capabilities','/api/download','/api/status',
                    '/api/current','/api/frontier','/api/sources','/api/history','/api/source-file','/api/diff',
                    '/api/body','/api/reports','/api/report-file','/api/round-file','/api/task-detail','/api/task-artifact','/api/research-memory','/api/research-memory-file',
                    '/api/native-main-files','/api/native-main-file','/api/main','/api/incidents','/api/knowledge','/api/knowledge-get','/api/knowledge-dependencies','/api/knowledge-history','/api/report-revision-target'},'ROUTE_NOT_FOUND','未找到页面。')
                if path=='/api/session':result={'csrf':session['csrf'],'workspace_id':workspace.workspace_id,**workspace.preferences()}
                elif path=='/api/preferences':result=workspace.preferences()
                elif path=='/api/workspace':result=workspace.list()
                elif path=='/api/operations':result=workspace.operations(int(q.get('offset',0)),int(q.get('limit',50)))
                elif path=='/api/operation':result=workspace.operation_status(q.get('key'),operation_id=q.get('id'))
                elif path=='/api/main':
                    from .main_session import view
                    require(workspace.project(q['project']).read_snapshot()['instances'][q['instance']]['kind']!='SURVEY',
                            'WORKFLOW_KIND_INVALID','SURVEY uses a sequential controller and has no MAIN session.')
                    result=view(workspace.project(q['project']),q['instance'],cursor=int(q.get('cursor',0)))
                elif path=='/api/incidents':
                    state=workspace.project(q['project']).read_snapshot()
                    from .incidents import project as incident_projection
                    result={'incidents':[incident_projection(state,row) for row in state.get('incidents',{}).values() if not q.get('instance') or row['instance_id']==q['instance']],
                            'as_of_commit':state['knowledge_commit'],'model_calls':0}
                elif path=='/api/report-revision-target':
                    from .reports import revision_target
                    result=revision_target(workspace.project(q['project']),q['instance'],q['report'],q['profile'])
                elif path.startswith('/api/knowledge'):
                    from . import knowledge_access
                    method={'/api/knowledge':'search','/api/knowledge-get':'get','/api/knowledge-dependencies':'dependencies','/api/knowledge-history':'history'}[path]
                    result=knowledge_access.web_tool(workspace.project(q['project']),method,q)
                elif path=='/api/workflow-graph':
                    from .activity import graph
                    from .model_policy import describe
                    result={**graph(),'policy':describe()}
                elif path=='/api/progress':result=workspace.progress(q.get('project'),q.get('instance') or None,q.get('commit') or None)
                elif path=='/api/workflow-inputs':result=workspace.workflow_inputs(q.get('project'),q.get('query',''),int(q.get('offset',0)),int(q.get('limit',100)))
                elif path=='/api/settings':
                    from . import setup
                    result={'client':workspace.login.inspect(),'policy':__import__('research_studio.model_policy',fromlist=['describe']).describe(),'setup':setup.status(),'model_calls':0}
                elif path=='/api/capabilities':
                    from .codex_client import capabilities
                    result=capabilities()
                elif path=='/api/download':
                    name=q.get('file','');require(len(name)==68 and name.endswith('.zip') and all(c in '0123456789abcdef' for c in name[:-4]),'PATH_INVALID','下载文件编号无效。')
                    self.reply(200,read(safe_path(workspace.root,'downloads/'+name),1024**3),'application/zip',filename='PMRS-backup.zip');return
                else:
                    store=workspace.project(q.get('project'));iid=q.get('instance') or None;s=store.read_snapshot(q.get('commit') or None)
                    if path=='/api/status':result=workspace.info(q['project'],iid,q.get('commit'))
                    elif path=='/api/native-main-files':result=views.native_main_files(s,store,iid)
                    elif path=='/api/native-main-file':
                        self.reply_native_stream(views.native_main_file_path(s,store,iid,q.get('file')));return
                    elif path=='/api/research-memory':
                        result=views.research_memory(s,store,q['kind'],q['id'],instance_id=iid,
                            offset=int(q.get('offset',0)),limit=int(q.get('limit',24000)))
                    elif path=='/api/research-memory-file':
                        form=q.get('format','body')
                        raw,mime=views.research_memory_bytes(s,store,q['kind'],q['id'],instance_id=iid,format=form)
                        name=q['kind']+'-'+q['id']+('-'+form+'.json' if form!='body' else '.md')
                        self.reply(200,raw,mime,filename=name);return
                    elif path=='/api/task-detail':result=views.task_detail(s,store,q['task'],instance_id=iid)
                    elif path=='/api/task-artifact':
                        artifacts=views.task_artifacts(s,store,q['task'],instance_id=iid)
                        require(q.get('artifact') in artifacts,'UNAUTHORIZED','The selected file does not belong to this task.')
                        row=artifacts[q['artifact']];raw=views.task_artifact_bytes(row,store)
                        if q.get('download')=='1':
                            filename=Path(row['name']).name
                            self.reply(200,raw,'application/octet-stream',filename=filename);return
                        offset=int(q.get('offset',0));limit=int(q.get('limit',24000))
                        require(offset>=0 and 1<=limit<=64000,'PAGE_INVALID','Choose a bounded text page.')
                        body=raw.decode('utf-8');require('\0' not in body,'BINARY_ARTIFACT','Download binary original files.')
                        result={'body':body[offset:offset+limit],'offset':offset,'next_offset':offset+limit if offset+limit<len(body) else None,
                            'total_chars':len(body),'commit':s['knowledge_commit'],'live':row['section']=='logs'}
                    elif path=='/api/round-file':
                        delivery=s.get('round_deliveries',{}).get(q.get('delivery'))
                        require(delivery is not None and (iid is None or delivery.get('instance_id',delivery.get('summary',{}).get('instance_id'))==iid),
                                'UNAUTHORIZED','The selected round report is outside this instance.')
                        summary=delivery.get('summary',delivery);body=delivery.get('report_body') or summary.get('report_body')
                        ref=delivery.get('report_body_ref') or summary.get('report_body_ref')
                        raw=store.read_blob(ref) if ref else body.encode() if isinstance(body,str) else canonical(delivery)
                        self.reply(200,raw,'text/plain; charset=utf-8',filename=q['delivery']+'.md');return
                    elif path=='/api/survey':
                        from . import survey
                        result=survey.status(s,iid)
                    elif path=='/api/current':result=views.current(s,store.read_blob,instance_id=iid,query=q.get('query'),offset=int(q.get('offset',0)),limit=int(q.get('limit',20)),include_body=False)
                    elif path=='/api/frontier':result=views.frontier(s,store.read_blob,instance_id=iid)
                    elif path=='/api/sources':result=views.sources(s,store.read_blob,instance_id=iid)
                    elif path=='/api/history':result=views.history(s,store,instance_id=iid,query=q.get('query'),offset=int(q.get('offset',0)),limit=int(q.get('limit',20)))
                    elif path=='/api/source-file':
                        source=q.get('ref');visible={row['source_ref'] for row in views.sources(s,store.read_blob,instance_id=iid)['sources']}
                        require(source in visible,'UNAUTHORIZED','材料不在当前可见范围。')
                        raw=store.read_blob(s['sources'][source]['blob_hash']);pdf=raw.startswith(b'%PDF-')
                        self.reply(200,raw,'application/pdf' if pdf else 'application/octet-stream',filename=None if pdf else 'original-source');return
                    elif path=='/api/diff':result=views.diff(store.read_snapshot(q['from']),s,instance_id=iid)
                    elif path=='/api/body':
                        ref=q.get('ref');require(ref in views.scope_refs(s,iid) and ref in s['records'],'UNAUTHORIZED','正文不在当前范围。')
                        record=store.read_record(ref);require(record==s['records'][ref],'RECORD_CHANGED','正文版本与快照不符。')
                        result={'body':store.read_blob(record['body_sha256']).decode(),'commit':s['knowledge_commit'],'ref':ref}
                    elif path=='/api/reports':
                        from .report_catalog import catalog
                        rows=catalog(store,s,iid)
                        for row in rows:
                            entry=s['reports'].get(row['report_id'],{});row['failure_history']=entry.get('failure_history',[])
                            row['open_research_requests']=entry.get('open_research_requests',[])
                            row['profiles']={name:{'revision':p['revision'],'body_sha256':p.get('body_sha256'),
                                'raw_body_sha256':p.get('raw_body_sha256')} for name,p in entry.get('profiles',{}).items()}
                            row['versions']=workspace.report_versions(q['project'],entry)
                            row['downloads']=[{'profile':name,'url':'/api/report-file?project='+q['project']+'&report='+row['report_id']+'&profile='+name+'&commit='+s['knowledge_commit']} for name,p in entry.get('profiles',{}).items() if p.get('render')]
                        result={'reports':rows,'commit':s['knowledge_commit']}
                    elif path=='/api/report-file':
                        from .report_catalog import check_files
                        entry=s['reports'][q['report']];check_files(store,entry);profile=entry['profiles'][q['profile']]
                        if q.get('revision') is not None:
                            revision=int(q['revision']);matches=[p for p in [*profile.get('history',[]),profile] if p['revision']==revision]
                            require(len(matches)==1,'REPORT_REVISION_STALE','Select an available exact report revision.')
                            profile=matches[0]
                        require(bool(profile.get('render')),'REPORT_RENDER_REQUIRED','This revision has no rendered PDF yet.')
                        self.reply(200,store.read_blob(profile['render']['pdf_sha256']),'application/pdf');return
                    else:raise PMRSError('PATH_INVALID','未找到页面。')
                self.reply(200,result)
            except (PMRSError,ValueError,KeyError,UnicodeError,OSError) as e:self.error(e)
        def do_POST(self):
            try:
                path,q=self.route();self.origin()
                require(not q and self.headers.get('Content-Type','').split(';')[0]=='application/json','ACTION_INVALID','操作须使用标准表单编码。')
                # Archive backups include immutable history and original files;
                # their base64 envelope needs a larger bound than source uploads.
                limit_mib=172 if path=='/api/action/upload-archive' else 46
                size=int(self.headers.get('Content-Length','0'));require(0<size<=limit_mib*1024**2,'PAYLOAD_LIMIT','上传文件超出限制。')
                from .util import loads
                p=loads(self.rfile.read(size),maximum=limit_mib*1024**2);require(isinstance(p,dict),'ACTION_INVALID','表单无效。')
                if path=='/api/session':
                    require(isinstance(p.get('token'),str) and hmac.compare_digest(p['token'],bootstrap_token),'UNAUTHORIZED','启动会话已失效，请从桌面重新打开。')
                    sid=secrets.token_urlsafe(32);session={'csrf':secrets.token_urlsafe(32)}
                    with session_lock:sessions[sid]=session
                    self.reply(200,{**session,'workspace_id':workspace.workspace_id,**workspace.preferences()},cookie='pmrs_session='+sid+'; HttpOnly; SameSite=Strict; Path=/');return
                session=self.session();require(hmac.compare_digest(self.headers.get('X-PMRS-CSRF',''),session['csrf']),'CSRF_INVALID','页面会话已变化，请刷新。')
                self.workspace_scope()
                if path=='/api/preferences':
                    require(set(p)=={'ui_locale'},'ACTION_INVALID','Only the display language preference is accepted.')
                    self.reply(200,workspace.set_preferences(p['ui_locale']));return
                if path=='/api/operation/ack':
                    require(set(p)=={'id','digest'},'ACTION_INVALID','确认只接受原操作回执编号与摘要。')
                    self.reply(200,workspace.acknowledge_operation(p['id'],p['digest']));return
                key=self.headers.get('Idempotency-Key','')
                if path=='/api/action/quit':
                    result=workspace.action('quit',p,key)
                    try:self.reply(200,result)
                    finally:threading.Thread(target=self.server.shutdown,daemon=True).start()
                    return
                require(path.startswith('/api/action/'),'PATH_INVALID','未登记的操作地址。')
                self.reply(200,workspace.action(path[12:],p,key))
            except (PMRSError,ValueError,KeyError,UnicodeError,OSError) as e:self.error(e)
        def do_PUT(self):self.reply(405,{'error':'METHOD_NOT_ALLOWED'})
        do_DELETE=do_PUT
        do_PATCH=do_PUT
    return App
