"""Confined global-pool observation; no reconciliation or process inspection."""
from pathlib import Path
import os
from pmrh.domain.primitives import PMRSError, canonical, loads, sha
from .io import _ConfinedReader, _Unavailable, _reason, _observed_at

HOST_LIMIT=20

PROJECT_LIMIT=8

INFLIGHT={'RESERVED','SENT','UNKNOWN'}

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

def _view(data):
    occupied={};by_instance={}
    for r in data['slots'].values():
        occupied[r['project']]=occupied.get(r['project'],0)+1;by_instance[r['instance']]=by_instance.get(r['instance'],0)+1
    demand={k:max(r['demand'],by_instance.get(k,0)) for k,r in data['demands'].items()}
    for k,count in by_instance.items():demand[k]=max(demand.get(k,0),count)
    return {'limit':HOST_LIMIT,'instance_limit':8,'survey_instance_limit':1,'occupied':occupied,'instance_occupied':by_instance,'demand':demand,
        'shares':allocations(demand,cursor=data.get('cursor',0)),'active':len(data['slots']),'main_excluded':True,'internal_delegation_excluded':True}

def read_status():
    """Observe existing ledger bytes only; retain stale and UNKNOWN rows.

    No runtime_root(), lock, reconciliation, process check or project traversal.
    Limits are policy constants; unavailable counts are null, never healthy zero.
    """
    root=Path.home()/'.local/state/pmrs/host-runtime-4.2.2'
    source={'kind':'GLOBAL_POOL_LEDGER','path_sha256':sha(str(root/'model-pool.json').encode()),'sha256':None}
    result={'available':False,'unavailable_reason':None,'observed_at':None,'source':source,
            'cross_store_atomicity':False,'reconciled':False,'owner_observation':'UNOBSERVED',
            'limit':HOST_LIMIT,'instance_limit':PROJECT_LIMIT,'survey_instance_limit':1,
            'active':None,'slots':None,'occupied':None,'instance_occupied':None,
            'demand':None,'shares':None,'main_excluded':True,'internal_delegation_excluded':True}
    try:
        with _ConfinedReader(root,max_bytes=4*1024**2,max_files=1) as reader:
            if os.fstat(reader.fd).st_uid!=os.geteuid():raise _Unavailable('POOL_OWNER_MISMATCH')
            raw=reader.read('model-pool.json',4*1024**2)
        source['sha256']=sha(raw);data=loads(raw,maximum=4*1024**2)
        def valid_text(value):return isinstance(value,str) and 0<len(value)<=512
        if not isinstance(data,dict) or not all(isinstance(data.get(k),dict) and len(data[k])<=4096 for k in ('slots','demands','projects')):
            raise _Unavailable('INVALID_POOL_DATA')
        if type(data.get('cursor',0)) is not int or not 0<=data.get('cursor',0)<2**63:
            raise _Unavailable('INVALID_POOL_DATA')
        for key,row in data['slots'].items():
            if (not valid_text(key) or not isinstance(row,dict) or
                not all(valid_text(row.get(k)) for k in ('project','instance','instance_id','request_id')) or
                row['instance']!=instance_key(row['project'],row['instance_id']) or
                row.get('state') not in {'ACQUIRED',*INFLIGHT} or
                type(row.get('pid')) is not int or row['pid']<0 or
                row.get('start') is not None and not valid_text(row['start'])):
                raise _Unavailable('INVALID_POOL_DATA')
        for key,row in data['demands'].items():
            if (not valid_text(key) or not isinstance(row,dict) or
                type(row.get('demand')) is not int or not 0<=row['demand']<=HOST_LIMIT):
                raise _Unavailable('INVALID_POOL_DATA')
        # Registered roots are data, not filesystem authority. Never follow them.
        projection={**_view(data),'slots':[{k:r.get(k) for k in
            ('project','instance','instance_id','request_id','pid','start','state')} for r in data['slots'].values()]}
        # Validate projected keys and values before publishing any pool counts.
        canonical(projection)
        result.update(projection,available=True)
    except (_Unavailable,PMRSError,OSError,ValueError,TypeError,KeyError,RecursionError) as exc:
        result['unavailable_reason']=_reason(exc) if not isinstance(exc,(PMRSError,UnicodeError)) else 'INVALID_POOL_DATA'
    result['observed_at']=_observed_at()
    return result
