"""Small user-local, nonpreemptive PMRS model pool shared by every entry point.

This is an admission ledger, not a claim that an UNKNOWN remote job is running.
Uncertain sends remain reserved until their original native evidence resolves them.
"""
from contextlib import contextmanager
from pathlib import Path
import fcntl,json,os,time
from .util import PMRSError,atomic,canonical,read,require,safe_path,sha

HOST_LIMIT=10
PROJECT_LIMIT=8

def runnable_request(snapshot,request):
    if request.get('purpose')=='PROJECT_ASSISTANT':return True
    task=snapshot.get('tasks',{}).get(request.get('task_id'),{})
    if task.get('report_context'):
        from .reports import dispatch_authorized
        if dispatch_authorized(snapshot,task):return True
    instance=snapshot.get('instances',{}).get(request.get('instance_id'),{})
    return instance.get('status')=='ACTIVE' and (request.get('execution_state')!='PREPARED' or task.get('report_context') or instance.get('current_mission_id')==request.get('mission_id'))

def runtime_root():
    override=os.environ.get('PMRS_HOST_POOL_ROOT')
    base=Path(override) if override else Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'pmrs/host-runtime-v1'
    base=safe_path(base);base.mkdir(parents=True,exist_ok=True,mode=0o700)
    require(base.stat().st_uid==os.geteuid(),'RESOURCE_FILE_INVALID','Shared runtime must belong to this user.')
    return base

def process_start(pid):
    try:return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
    except (OSError,IndexError):return None

def alive(row):
    return bool(row.get('start')) and process_start(row.get('pid'))==row['start']

@contextmanager
def ledger(name):
    root=runtime_root();path=root/(name+'.json')
    fd=os.open(root/(name+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        original=read(path,4*1024**2) if path.exists() else None
        data=json.loads(original) if original else {}
        try:yield data
        finally:
            encoded=canonical(data)
            # Read-only polls and unchanged demand do not grow runtime history.
            if encoded!=original:atomic(path,encoded)
    finally:os.close(fd)

def project_key(store):
    return sha(str(Path(store.root).resolve()).encode())

def allocations(demands, *, limit=HOST_LIMIT, cursor=0):
    """Progressive water filling, with a rotating indivisible remainder."""
    keys=sorted(k for k,v in demands.items() if v>0)
    out={k:0 for k in demands}
    if not keys:return out
    offset=cursor%len(keys);keys=keys[offset:]+keys[:offset]
    left=limit
    while left:
        progress=False
        for key in keys:
            if out[key]<min(PROJECT_LIMIT,demands[key]):
                out[key]+=1;left-=1;progress=True
                if not left:break
        if not progress:break
    return out

def _clean(data, snapshots=None, roots=None):
    demands=data.setdefault('demands',{});slots=data.setdefault('slots',{})
    for key,row in list(demands.items()):
        if not alive(row):demands.pop(key)
    # Native state is authoritative. Reading it does not acquire its writer lock.
    states=dict(snapshots or {})
    for key,snapshot in states.items():
        for rid,request in snapshot.get('requests',{}).items():
            if request.get('execution_kind')=='MODEL' and request['execution_state'] in {'RESERVED','SENT','UNKNOWN'} and request.get('unknown_disposition')!='ABANDON_UNKNOWN':
                token=key+':'+rid
                if token not in slots:
                    root=(roots or {}).get(key) or demands.get(key,{}).get('root')
                    if root:slots[token]={'project':key,'root':root,'request_id':rid,'pid':0,'start':None,'state':'UNKNOWN'}
    for token,row in list(slots.items()):
        key=row['project']
        if key not in states:
            try:
                from .store import Store
                states[key]=Store(Path(row['root'])).read_snapshot()
            except (PMRSError,OSError,ValueError):states[key]=None
        snapshot=states[key];request=(snapshot or {}).get('requests',{}).get(row['request_id'])
        if request:
            state=request['execution_state']
            if state in {'CAPTURED','SETTLED','CANCELLED_BEFORE_SEND'} or request.get('unknown_disposition')=='ABANDON_UNKNOWN':
                slots.pop(token);data['cursor']=data.get('cursor',0)+1;continue
            if state in {'RESERVED','SENT','UNKNOWN'}:row['state']=state
            elif state=='PREPARED' and not alive(row):slots.pop(token)
        # Missing native evidence cannot prove that an uncertain send ended.
        elif not alive(row) and row['state']=='ACQUIRED':slots.pop(token)
    for key,row in list(demands.items()):
        if not row.get('auto'):continue
        if not any(slot['project']==key for slot in slots.values()):demands.pop(key);continue
        snapshot=states.get(key)
        if snapshot:
            pending=sum(r['execution_state'] in {'PREPARED','RESERVED','SENT','UNKNOWN'} and r.get('unknown_disposition')!='ABANDON_UNKNOWN'
                        and not r.get('fenced') and runnable_request(snapshot,r) for r in snapshot.get('requests',{}).values())
            row['demand']=min(row['limit'],pending)

def _view(data):
    occupied={}
    for row in data['slots'].values():occupied[row['project']]=occupied.get(row['project'],0)+1
    demand={key:max(row['demand'],occupied.get(key,0)) for key,row in data['demands'].items()}
    for key,count in occupied.items():demand[key]=max(demand.get(key,0),count)
    shares=allocations(demand,cursor=data.get('cursor',0))
    return {'limit':HOST_LIMIT,'occupied':occupied,'demand':demand,'shares':shares,'active':len(data['slots'])}

def update_demand(store,demand,project_limit=None):
    snapshot=store.read_snapshot();key=project_key(store)
    cap=project_limit if project_limit is not None else snapshot.get('max_workers',1)
    require(type(cap) is int and 1<=cap<=PROJECT_LIMIT,'WORKERS_INVALID','Project model limit must be 1–8.')
    require(type(demand) is int and demand>=0,'RESOURCE_LIMIT','Demand must be a nonnegative ready responsibility count.')
    # The research coordinator reports its own ready duties. Independent
    # assistant replies already frozen in this same project add real demand.
    demand+=sum(r.get('purpose')=='PROJECT_ASSISTANT' and r['execution_state'] in {'PREPARED','RESERVED','SENT','UNKNOWN'}
                and not r.get('fenced') for r in snapshot.get('requests',{}).values())
    with ledger('model-pool') as data:
        data.setdefault('demands',{})[key]={'root':str(store.root),'pid':os.getpid(),'start':process_start(os.getpid()),'demand':min(cap,demand),'limit':cap,'auto':False}
        _clean(data,{key:snapshot},{key:str(store.root)})
        return _view(data)

def clear_demand(store):
    with ledger('model-pool') as data:
        _clean(data);data['demands'].pop(project_key(store),None)

def acquire(store,request_id):
    snapshot=store.read_snapshot();key=project_key(store);token=key+':'+request_id
    cap=min(PROJECT_LIMIT,snapshot.get('max_workers',1))
    with ledger('model-pool') as data:
        _clean(data,{key:snapshot},{key:str(store.root)})
        require(token not in data['slots'],'EXISTING_REQUEST','The original request already owns a host slot.')
        if key not in data['demands']:
            active=sum(r['execution_state'] in {'PREPARED','RESERVED','SENT','UNKNOWN'} and not r.get('fenced')
                       and runnable_request(snapshot,r) for r in snapshot.get('requests',{}).values())
            data['demands'][key]={'root':str(store.root),'pid':os.getpid(),'start':process_start(os.getpid()),'demand':min(cap,max(1,active)),'limit':cap,'auto':True}
        view=_view(data);count=view['occupied'].get(key,0)
        if not (view['active']<HOST_LIMIT and count<cap and count<view['shares'].get(key,0)):
            exc=PMRSError('RESOURCE_WAIT','Waiting for this project’s fair share of the shared PMRS model pool; the original request is unchanged.')
            exc.resource='MODEL_SLOT';raise exc
        data['slots'][token]={'project':key,'root':str(store.root),'request_id':request_id,'pid':os.getpid(),
                             'start':process_start(os.getpid()),'state':'ACQUIRED'}
        return {'token':token,'project':key,'request_id':request_id}

def mark(store,request_id,state):
    with ledger('model-pool') as data:
        token=project_key(store)+':'+request_id
        if token in data.setdefault('slots',{}):data['slots'][token]['state']=state

def release(store,request_id,*,before_send=False):
    snapshot=store.read_snapshot();request=snapshot.get('requests',{}).get(request_id,{})
    state=request.get('execution_state')
    safe=state in {'CAPTURED','SETTLED','CANCELLED_BEFORE_SEND'} or request.get('unknown_disposition')=='ABANDON_UNKNOWN'
    require(safe or (before_send and state=='PREPARED'),'EXISTING_REQUEST','Uncertain sends retain their original host reservation.')
    with ledger('model-pool') as data:
        token=project_key(store)+':'+request_id
        if data.setdefault('slots',{}).pop(token,None) is not None:data['cursor']=data.get('cursor',0)+1

def status():
    with ledger('model-pool') as data:
        _clean(data);return {**_view(data),'slots':list(data['slots'].values())}
