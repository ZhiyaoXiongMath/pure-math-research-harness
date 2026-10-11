"""One atomic user-wide 20-stage pool with independent 8-stage instance caps.

MAIN and its native delegates are excluded. Native UNKNOWN requests retain slots.
"""
from contextlib import contextmanager
from pathlib import Path
import fcntl,json,os
from .util import PMRSError,atomic,canonical,read,require,safe_path,sha
HOST_LIMIT=20
PROJECT_LIMIT=8
INFLIGHT={'RESERVED','SENT','UNKNOWN'}
def is_stage(s,r):return s.get('tasks',{}).get(r.get('task_id'),{}).get('actor_kind')!='MAIN'
def instance_limit(s,iid):return 1 if s['instances'][iid]['kind']=='SURVEY' else 8
def runnable_request(s,r):
    task=s.get('tasks',{}).get(r.get('task_id'),{})
    if task.get('report_context'):
        from .reports import dispatch_authorized
        if dispatch_authorized(s,task):return True
    i=s.get('instances',{}).get(r.get('instance_id'),{})
    return i.get('status')=='ACTIVE' and (r.get('execution_state')!='PREPARED' or task.get('report_context') or i.get('current_mission_id')==r.get('mission_id'))
def runtime_root():
    # No project/working-directory override can split this one global pool.
    base=safe_path(Path.home()/'.local/state/pmrs/host-runtime-4.2.2');base.mkdir(parents=True,exist_ok=True,mode=0o700)
    require(base.stat().st_uid==os.geteuid(),'RESOURCE_FILE_INVALID','Shared runtime must belong to this user.');return base
def process_start(pid):
    try:return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
    except (OSError,IndexError):return None
def alive(row):return bool(row.get('start')) and process_start(row.get('pid'))==row['start']
@contextmanager
def ledger(name):
    root=runtime_root();path=root/(name+'.json');fd=os.open(root/(name+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX);original=read(path,4*1024**2) if path.exists() else None;data=json.loads(original) if original else {}
        try:yield data
        finally:
            encoded=canonical(data)
            if encoded!=original:atomic(path,encoded)
    finally:os.close(fd)
def project_key(store):return sha(str(Path(store.root).resolve()).encode())
def instance_key(project,iid):return project+':'+iid

def allocations(demands,*,limit=HOST_LIMIT,cursor=0):
    keys=sorted(k for k,v in demands.items() if v>0);out={k:0 for k in demands}
    if not keys:return out
    offset=cursor%len(keys);keys=keys[offset:]+keys[:offset];left=limit
    while left:
        progress=False
        for key in keys:
            if out[key]<min(PROJECT_LIMIT,demands[key]):
                out[key]+=1;left-=1;progress=True
                if not left:break
        if not progress:break
    return out

def _clean(data,snapshots=None,roots=None):
    demands=data.setdefault('demands',{});slots=data.setdefault('slots',{});registry=data.setdefault('projects',{});registry.update(roots or {});states=dict(snapshots or {})
    for project,root in registry.items():
        if project not in states:
            try:
                from .store import Store
                states[project]=Store(Path(root)).read_snapshot()
            except (PMRSError,OSError,ValueError):states[project]=None
    for key,row in list(demands.items()):
        if not alive(row):demands.pop(key)
    for project,s in states.items():
        if not s:continue
        for rid,r in s.get('requests',{}).items():
            if is_stage(s,r) and r.get('execution_kind') in {'MODEL','SYNTHETIC_TEST_ONLY'} and r['execution_state'] in INFLIGHT:
                slots.setdefault(project+':'+rid,{'project':project,'instance_id':r['instance_id'],'instance':instance_key(project,r['instance_id']),
                    'root':registry[project],'request_id':rid,'pid':0,'start':None,'state':'UNKNOWN'})
    for token,row in list(slots.items()):
        s=states.get(row['project']);r=(s or {}).get('requests',{}).get(row['request_id'])
        if r:
            state=r['execution_state']
            if not is_stage(s,r) or state in {'CAPTURED','SETTLED','CANCELLED_BEFORE_SEND'}:
                slots.pop(token);data['cursor']=data.get('cursor',0)+1;continue
            if state in INFLIGHT:row['state']=state
            elif state=='PREPARED' and not alive(row):slots.pop(token)
        elif not alive(row) and row['state']=='ACQUIRED':slots.pop(token)
    for key,row in list(demands.items()):
        s=states.get(row['project'])
        if row.get('auto') and s:
            pending=sum(is_stage(s,r) and r['instance_id']==row['instance_id'] and r['execution_state'] in {'PREPARED',*INFLIGHT} and not r.get('fenced') and runnable_request(s,r) for r in s.get('requests',{}).values())
            row['demand']=min(row['limit'],pending)

def _view(data):
    occupied={};by_instance={}
    for r in data['slots'].values():
        occupied[r['project']]=occupied.get(r['project'],0)+1;by_instance[r['instance']]=by_instance.get(r['instance'],0)+1
    demand={k:max(r['demand'],by_instance.get(k,0)) for k,r in data['demands'].items()}
    for k,count in by_instance.items():demand[k]=max(demand.get(k,0),count)
    return {'limit':HOST_LIMIT,'instance_limit':8,'survey_instance_limit':1,'occupied':occupied,'instance_occupied':by_instance,'demand':demand,
        'shares':allocations(demand,cursor=data.get('cursor',0)),'active':len(data['slots']),'main_excluded':True,'internal_delegation_excluded':True}

def update_demand(store,demand,project_limit=None,*,demands=None):
    s=store.read_snapshot();project=project_key(store);require(type(demand) is int and demand>=0,'RESOURCE_LIMIT','Nonnegative ready demand required.')
    with ledger('model-pool') as data:
        _clean(data,{project:s},{project:str(store.root)})
        for iid in s['instances']:
            cap=instance_limit(s,iid);pending=sum(is_stage(s,r) and r['instance_id']==iid and r['execution_state'] in {'PREPARED',*INFLIGHT} and not r.get('fenced') and runnable_request(s,r) for r in s.get('requests',{}).values())
            data['demands'][instance_key(project,iid)]={'project':project,'instance_id':iid,'root':str(store.root),'pid':os.getpid(),'start':process_start(os.getpid()),'demand':min(cap,max(pending,(demands or {}).get(iid,pending))),'limit':cap,'auto':False}
        return _view(data)
def clear_demand(store):
    with ledger('model-pool') as data:
        _clean(data)
        for key,row in list(data['demands'].items()):
            if row['project']==project_key(store):data['demands'].pop(key)
def acquire(store,request_id):
    s=store.read_snapshot();r=s['requests'][request_id]
    if not is_stage(s,r):return {'request_id':request_id,'exempt':'MAIN_TOP_LEVEL'}
    project=project_key(store);iid=r['instance_id'];key=instance_key(project,iid);token=project+':'+request_id;cap=instance_limit(s,iid)
    with ledger('model-pool') as data:
        _clean(data,{project:s},{project:str(store.root)});require(token not in data['slots'],'EXISTING_REQUEST','Original request already owns a global stage slot.')
        if key not in data['demands'] or data['demands'][key]['demand']==0:
            data['demands'][key]={'project':project,'instance_id':iid,'root':str(store.root),'pid':os.getpid(),'start':process_start(os.getpid()),'demand':cap,'limit':cap,'auto':True}
        view=_view(data);count=view['instance_occupied'].get(key,0)
        if not (view['active']<HOST_LIMIT and count<cap and count<view['shares'].get(key,0)):
            exc=PMRSError('RESOURCE_WAIT','Waiting for instance stage capacity or its fair share of the shared 20-stage pool; original request preserved.');exc.resource='MODEL_SLOT';raise exc
        data['slots'][token]={'project':project,'instance':key,'instance_id':iid,'root':str(store.root),'request_id':request_id,'pid':os.getpid(),'start':process_start(os.getpid()),'state':'ACQUIRED'}
        return {'token':token,'project':project,'instance_id':iid,'request_id':request_id}
def mark(store,request_id,state):
    with ledger('model-pool') as data:
        token=project_key(store)+':'+request_id
        if token in data.setdefault('slots',{}):data['slots'][token]['state']=state
def release(store,request_id,*,before_send=False):
    s=store.read_snapshot();r=s.get('requests',{}).get(request_id,{})
    if not is_stage(s,r):return
    safe=r.get('execution_state') in {'CAPTURED','SETTLED','CANCELLED_BEFORE_SEND'}
    require(safe or (before_send and r.get('execution_state')=='PREPARED'),'EXISTING_REQUEST','Uncertain sends retain original stage reservation.')
    with ledger('model-pool') as data:
        if data.setdefault('slots',{}).pop(project_key(store)+':'+request_id,None) is not None:data['cursor']=data.get('cursor',0)+1
def status():
    with ledger('model-pool') as data:
        _clean(data);return {**_view(data),'slots':list(data['slots'].values())}
