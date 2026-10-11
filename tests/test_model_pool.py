"""Finite local transports through CodexExecutor, never a paid model call."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,os,subprocess,sys,time,unittest
from research_studio import demo,execution,host_pool,resources,runner,scheduler
from research_studio.engine import Engine
from research_studio.store import Store
from research_studio.util import PMRSError,canonical

TRANSPORT = r'''#!/usr/bin/env python3
import fcntl,json,os,pathlib,sys,time
sys.stdin.buffer.read()
work=pathlib.Path(sys.argv[sys.argv.index('-C')+1]);task=json.loads((work/'task.json').read_bytes())
root=pathlib.Path(os.environ['PMRS_CONTROLLED_TRANSPORT']);rid=task['request_id']
config=json.loads((root/'config.json').read_text());delay=config['delays'].get(rid,config['delay'])
# Read actual files presented to this isolated synthetic transport, not just refs.
for row in task.get('material_refs',{}).values():
 with (work/row['path']).open('rb') as f:
  while f.read(262144):pass
project=str(work.parents[2])
def event(phase):
 with (root/'events.jsonl').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX);f.write(json.dumps({'phase':phase,'request_id':rid,'project':project,'pid':os.getpid(),'time':time.monotonic()})+'\n');f.flush()
event('start')
start=time.monotonic()
barrier=config.get('barriers',{}).get(rid,config.get('barrier',0))
while barrier and time.monotonic()-start<20:
 rows=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
 if sum(row['phase']=='start' for row in rows)>=barrier:break
 time.sleep(.05)
while config.get('release_file') and not pathlib.Path(config['release_file']).exists() and time.monotonic()-start<25:time.sleep(.05)
time.sleep(delay)
pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_bytes((root/'responses'/rid).read_bytes())
event('finish');sys.exit(config.get('exit_code',0))
'''


def fixture(root,count=10,workers=8):
    engine=Engine();store=Store.create(root,'Controlled transport only',synthetic=True)
    iid=engine.new_workflow(store,'TRH',target=b'Synthetic finite test target. No mathematical result is asserted.')['instance_id']
    policy=demo.policy();policy['executor_contract']={'executor':'codex','sandbox':'required','environment_revision':'controlled-local-transport'}
    items=[{'key':str(i),'stage':'P4','role':'RESEARCH','intent':'Controlled distinct finite responsibility '+str(i)} for i in range(count)]
    engine.plan_work(store,iid,'Explicit finite transport validation only.',items,max_calls=count,max_workers=workers,policy=policy)
    return store,iid,{'max_workers':workers,'mission_policies':True}


def prepare(store,iid,policy):
    made=scheduler.commit_dispatch(store,scheduler.plan(store.read_snapshot(),[iid],policy),policy=policy)
    return made['prepared']


def transport_root(root,stores,*,delay=1.5,delays=None,exit_code=0,barrier=0,barriers=None):
    root.mkdir();(root/'responses').mkdir();binary=root/'transport';binary.write_text(TRANSPORT);binary.chmod(0o700)
    (root/'config.json').write_text(json.dumps({'delay':delay,'delays':delays or {},'exit_code':exit_code,'barrier':barrier,'barriers':barriers or {}}))
    for store in stores:
        for task in store.read_snapshot()['tasks'].values():(root/'responses'/task['request_id']).write_bytes(demo.response(task,store.read_snapshot()))
    return binary


def events(path):
    return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []


def peaks(rows):
    current={};peak=0;by_project={}
    for row in sorted(rows,key=lambda x:x['time']):
        key=row['project'];current[key]=current.get(key,0)+(1 if row['phase']=='start' else -1)
        peak=max(peak,sum(current.values()));by_project[key]=max(by_project.get(key,0),current[key])
    return peak,by_project


def evidence(name,payload):
    target=os.environ.get('PMRS_ACCEPTANCE_OUT')
    if target:
        root=Path(target);root.mkdir(parents=True,exist_ok=True)
        (root/(name+'.json')).write_text(json.dumps(payload,indent=2)+'\n')


def controlled_run(project,iid,binary,policy,maximum):
    store=Store(Path(project));real_freeze=scheduler.commit_dispatch
    def freeze(*args,**kwargs):
        made=real_freeze(*args,**kwargs)
        for row in made['prepared']:
            task=store.read_snapshot()['tasks'][row['task_id']]
            (Path(os.environ['PMRS_CONTROLLED_TRANSPORT'])/'responses'/row['request_id']).write_bytes(demo.response(task,store.read_snapshot()))
        return made
    with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}),patch('research_studio.scheduler.commit_dispatch',side_effect=freeze):
        return runner.run(store,instance_id=iid,executor=runner.CodexExecutor(str(binary),timeout=30),policy=policy,max_tasks=maximum)


class ModelPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'host'),'PMRS_CONTROLLED_TRANSPORT':str(self.root/'transport')})
        self.env.start();self.addCleanup(self.env.stop)

    def test_waterfill_unequal_rotation_and_more_than_ten_projects(self):
        self.assertEqual(host_pool.allocations({'a':2,'b':8}),{'a':2,'b':2})
        self.assertEqual(sorted(host_pool.allocations({'a':1,'b':8,'c':8}).values()),[1,1,2])
        allocations=[host_pool.allocations({'a':8,'b':8,'c':8},cursor=i) for i in range(3)]
        self.assertEqual([next(k for k,v in row.items() if v==2) for row in allocations],['a','b','c'])
        many={str(i):8 for i in range(12)}
        self.assertTrue(all(any(host_pool.allocations(many,cursor=i)[key]>0 for i in range(12)) for key in many))

    def test_real_wrapper_reaches_four_and_refills_before_slow_task_finishes(self):
        store,iid,policy=fixture(self.root/'project',10,workers=4);prepared=prepare(store,iid,policy)
        slow=prepared[0]['request_id'];binary=transport_root(self.root/'transport',[store],delay=.2,barrier=4,barriers={slow:10})
        result=controlled_run(store.root,iid,binary,policy,10);rows=events(self.root/'transport/events.jsonl')
        self.assertEqual(len(result['tasks']),10);self.assertEqual(peaks(rows)[0],4)
        self.assertEqual(len({r['request_id'] for r in rows if r['phase']=='start'}),10)
        slow_end=next(r['time'] for r in rows if r['request_id']==slow and r['phase']=='finish')
        original={r['request_id'] for r in prepared}
        self.assertTrue(any(r['phase']=='start' and r['request_id'] not in original and r['time']<slow_end for r in rows))
        self.assertEqual(host_pool.status()['active'],0)
        self.assertEqual(resources.resource_status()['leases'],[])
        evidence('T4-wrapper-four-refill',{'events':rows,'peak':peaks(rows)[0],'result':result,'paid_calls':0,'transport':'controlled local subprocess through CodexExecutor'})

    def test_separate_processes_share_four_and_preserve_lower_project_limit(self):
        for limits in ((4,4),(1,4)):
            projects=[]
            for index,limit in enumerate(limits):
                store,iid,policy=fixture(self.root/('p'+str(limits[0])+'-'+str(index)),limit,limit);prepare(store,iid,policy)
                projects.append((store,iid,policy))
            transport=self.root/('transport-'+str(limits[0]));binary=transport_root(transport,[x[0] for x in projects],delay=1,barrier=4)
            env={**os.environ,'PMRS_CONTROLLED_TRANSPORT':str(transport),'PYTHONDONTWRITEBYTECODE':'1'}
            processes=[subprocess.Popen([sys.executable,'-B','-m','tests.test_model_pool','worker',str(s.root),iid,str(binary),str(p['max_workers'])],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for s,iid,p in projects]
            try:outputs=[process.communicate(timeout=35) for process in processes]
            finally:
                for process in processes:
                    if process.poll() is None:process.terminate();process.communicate(timeout=3)
            self.assertTrue(all(process.returncode==0 for process in processes),outputs)
            self.assertEqual([len(json.loads(out)['tasks']) for out,err in outputs],list(limits))
            peak,by=peaks(events(transport/'events.jsonl'));self.assertEqual(peak,4,{'limits':limits,'by':by})
            self.assertTrue(all(by[str(s.root)]<=p['max_workers'] for s,_,p in projects))
            self.assertEqual(host_pool.status()['active'],0)
            evidence('T5-wrapper-'+str(limits[0])+'-'+str(limits[1]),{'events':events(transport/'events.jsonl'),'peak':peak,'project_peaks':by,'paid_calls':0})

    def test_project_arriving_to_full_host_waits_without_preemption_or_new_identity(self):
        projects=[]
        for index,limit in enumerate((3,1,1)):
            store,iid,policy=fixture(self.root/('late-'+str(index)),limit,limit);made=prepare(store,iid,policy)
            projects.append((store,iid,policy,made))
        slow=projects[0][3][0]['request_id']
        binary=transport_root(self.root/'transport',[x[0] for x in projects],delay=2,delays={slow:6},barrier=4)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        def spawn(item):
            s,iid,p,_=item
            return subprocess.Popen([sys.executable,'-B','-m','tests.test_model_pool','worker',str(s.root),iid,str(binary),str(p['max_workers'])],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        processes=[spawn(item) for item in projects[:2]]
        try:
            deadline=time.monotonic()+20
            while len([r for r in events(self.root/'transport/events.jsonl') if r['phase']=='start'])<4 and time.monotonic()<deadline:time.sleep(.05)
            self.assertEqual(host_pool.status()['active'],4)
            processes.append(spawn(projects[2]))
            outputs=[p.communicate(timeout=35) for p in processes]
            self.assertTrue(all(p.returncode==0 for p in processes),outputs)
        finally:
            for process in processes:
                if process.poll() is None:process.terminate();process.communicate(timeout=3)
        rows=events(self.root/'transport/events.jsonl');peak,by=peaks(rows)
        self.assertEqual(peak,4)
        late=[r for r in rows if r['project']==str(projects[2][0].root) and r['phase']=='start']
        self.assertEqual(len(late),1)
        self.assertGreaterEqual(late[0]['time'],min(r['time'] for r in rows if r['phase']=='finish'))
        self.assertLess(late[0]['time'],next(r['time'] for r in rows if r['request_id']==slow and r['phase']=='finish'))
        self.assertEqual([len(s.read_snapshot()['requests']) for s,_,_,_ in projects],[3,1,1])
        evidence('T5-late-project-full-host',{'events':rows,'peak':peak,'project_peaks':by,'late_request':late[0]['request_id'],'paid_calls':0})

    def test_before_send_wait_and_unknown_capture_recovery_preserve_identity(self):
        store,iid,policy=fixture(self.root/'project',1,1);prepared=prepare(store,iid,policy)[0]
        binary=transport_root(self.root/'transport',[store],delay=.01,exit_code=17)
        executor=runner.CodexExecutor(str(binary),timeout=5)
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}):
            with resources.reserve(store.root,owner='one',temporary_bytes=0,memory_bytes=1,max_preparations=1):
                result=executor.execute(store,prepared['task_id'])
            self.assertEqual(result['state'],'RESOURCE_WAIT');self.assertEqual(store.read_snapshot()['requests'][prepared['request_id']]['execution_state'],'PREPARED')
            with self.assertRaisesRegex(PMRSError,'MODEL_PROCESS_FAILED'):executor.execute(store,prepared['task_id'])
            request=store.read_snapshot()['requests'][prepared['request_id']]
            self.assertEqual(request['execution_state'],'UNKNOWN');self.assertEqual(host_pool.status()['active'],1)
            with self.assertRaisesRegex(PMRSError,'EXISTING_REQUEST'):executor.execute(Store(store.root),prepared['task_id'])
        self.assertEqual(len([r for r in events(self.root/'transport/events.jsonl') if r['phase']=='start']),1)
        raw=(self.root/'transport/responses'/prepared['request_id']).read_bytes()
        execution.capture(store,prepared['request_id'],raw,execution_id=request['execution_id'])
        self.assertEqual(host_pool.status()['active'],0)
        with patch('research_studio.execution._recover',side_effect=PMRSError('RESOURCE_DISK_LOW','Controlled admission wait')):
            self.assertEqual(executor.execute(store,prepared['task_id'])['state'],'RESOURCE_WAIT')
        self.assertEqual(store.read_snapshot()['requests'][prepared['request_id']]['execution_state'],'CAPTURED')
        self.assertEqual(executor.execute(Store(store.root),prepared['task_id'])['state'],'ACCEPTED')
        self.assertEqual(len(store.read_snapshot()['requests']),1)
        self.assertEqual(resources.resource_status()['leases'],[])
        self.assertEqual(host_pool.status()['demand'],{})
        evidence('T6-original-request-recovery',{'events':events(self.root/'transport/events.jsonl'),'request_id':prepared['request_id'],
                  'native_request_count':1,'final_state':store.read_snapshot()['requests'][prepared['request_id']]['execution_state'],'paid_calls':0})

    def test_unknown_survives_executor_process_exit_until_original_capture(self):
        store,iid,policy=fixture(self.root/'project',1,1);prepared=prepare(store,iid,policy)[0]
        binary=transport_root(self.root/'transport',[store],delay=.01,exit_code=17)
        process=subprocess.run([sys.executable,'-B','-m','tests.test_model_pool','worker',str(store.root),iid,str(binary),'1'],
                               env=os.environ,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(process.returncode,0);self.assertIn('MODEL_PROCESS_FAILED',process.stderr)
        self.assertEqual(host_pool.status()['active'],1)
        rows=resources.resource_status()['leases'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['memory_bytes'],0);self.assertTrue(rows[0]['persistent'])
        restarted=Store(store.root);request=restarted.read_snapshot()['requests'][prepared['request_id']]
        self.assertEqual(request['execution_state'],'UNKNOWN');self.assertEqual(request['reserved_calls'],1)
        # Simulate a native backup restored without this host's runtime ledger.
        with host_pool.ledger('model-pool') as data:data['slots'].clear()
        host_pool.update_demand(restarted,0);self.assertEqual(host_pool.status()['active'],1)
        host_pool.clear_demand(restarted)
        execution.capture(restarted,prepared['request_id'],(self.root/'transport/responses'/prepared['request_id']).read_bytes(),execution_id=request['execution_id'])
        self.assertEqual(execution.recover(restarted,prepared['request_id'])['state'],'ACCEPTED')
        self.assertEqual(host_pool.status()['active'],0);self.assertEqual(resources.resource_status()['leases'],[])
        self.assertEqual(len([r for r in events(self.root/'transport/events.jsonl') if r['phase']=='start']),1)
        evidence('T6-cross-process-unknown',{'events':events(self.root/'transport/events.jsonl'),'request_id':prepared['request_id'],
                 'dead_executor_returncode':process.returncode,'native_request_count':len(restarted.read_snapshot()['requests']),'paid_calls':0})

    def test_concurrent_driver_waits_for_exact_original_executor(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        store,iid,policy=fixture(self.root/'project',1,1);prepared=prepare(store,iid,policy)[0]
        binary=transport_root(self.root/'transport',[store],delay=.1);entered=Event();release=Event()
        def doctor(_):
            entered.set();self.assertTrue(release.wait(5));return {'ready':True,'binary':str(binary)}
        with patch('research_studio.runner.doctor',side_effect=doctor),ThreadPoolExecutor(max_workers=2) as pool:
            original=pool.submit(runner.CodexExecutor(str(binary),timeout=10).execute,store,prepared['task_id'])
            self.assertTrue(entered.wait(5))
            follower=pool.submit(runner.run,store,instance_id=iid,executor=runner.CodexExecutor(str(binary),timeout=10),policy=policy,max_tasks=1)
            time.sleep(.15);release.set()
            self.assertEqual(original.result(timeout=10)['state'],'ACCEPTED')
            self.assertEqual(len(follower.result(timeout=10)['tasks']),1)
        self.assertEqual(len([r for r in events(self.root/'transport/events.jsonl') if r['phase']=='start']),1)

    def test_transport_seal_survives_capture_resource_wait_and_recovers_without_send(self):
        from contextlib import contextmanager
        store,iid,policy=fixture(self.root/'project',1,1);prepared=prepare(store,iid,policy)[0]
        binary=transport_root(self.root/'transport',[store],delay=.01);reserve=resources.reserve
        @contextmanager
        def gate(*args,**kwargs):
            if kwargs.get('phase')=='capture':raise PMRSError('RESOURCE_WAIT','Controlled capture memory wait')
            with reserve(*args,**kwargs) as lease:yield lease
        with patch('research_studio.runner.doctor',return_value={'ready':True,'binary':str(binary)}),patch('research_studio.resources.reserve',side_effect=gate):
            result=runner.CodexExecutor(str(binary),timeout=5).execute(store,prepared['task_id'])
        self.assertEqual(result['state'],'UNKNOWN');self.assertEqual(host_pool.status()['active'],1)
        with patch('research_studio.runner.subprocess.Popen',side_effect=AssertionError('Recovery never sends')):
            self.assertEqual(execution.recover(Store(store.root),prepared['request_id'])['state'],'ACCEPTED')
        self.assertEqual(host_pool.status()['active'],0)
        self.assertEqual(len([r for r in events(self.root/'transport/events.jsonl') if r['phase']=='start']),1)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        _,_,project,iid,binary,workers=sys.argv
        result=controlled_run(project,iid,binary,{'max_workers':int(workers),'mission_policies':True},int(workers))
        print(json.dumps(result))
    else:unittest.main()
