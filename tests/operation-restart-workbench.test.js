'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {OperationLifecycle,indexedOperationStorage}=require('../research_studio/static/workbench.js');
function memory(){let row=null;return {get:async()=>row,claim:async x=>{if(row)return false;row=structuredClone(x);return true;},clear:async k=>{if(row?.key===k)row=null;}};}
function server(){
  const ledger=new Map();let calls=0;let lose=false;let ackLost=false;
  const wire={
    discover:async()=>({workspace_id:'WS-test',operations:[...ledger.values()].filter(r=>!r.acknowledged).map(r=>({...r.operation,state:r.state}))}),
    send:async op=>{calls++;const result={project:'WP-'+calls};ledger.set(op.key,{state:'COMPLETED',digest:'digest-'+op.key,operation:{id:op.key,name:op.name,payload:{}},result});if(lose)throw Error('response lost');return result;},
    query:async(key,op)=>ledger.get(op.receipt_id||key)||{state:'NOT_FOUND'},
    ack:async(op,r)=>{ledger.get(r.operation.id).acknowledged=true;if(ackLost)throw Error('ack response lost');}
  };return {wire,ledger,get calls(){return calls;},set lose(v){lose=v;},set ackLost(v){ackLost=v;}};
}
test('new origin with empty IndexedDB discovers server result and only acknowledges; intentional repetition gets a new ID',async()=>{
  const s=server();s.lose=true;const old=new OperationLifecycle(memory(),s.wire,()=> 'old-key');await assert.rejects(old.execute('create',{title:'same'}),/response lost/);
  const disk=memory(),fresh=new OperationLifecycle(disk,s.wire,()=> 'new-key');await assert.rejects(fresh.execute('create',{title:'same'}),/原操作/);assert.equal(s.calls,1);
  const recovered=await fresh.recover();assert.equal(recovered.result.project,'WP-1');assert.equal(recovered.operation.remote_only,true);assert.equal(await disk.get(),null);assert.equal(s.calls,1);
  s.lose=false;const repeated=await fresh.execute('create',{title:'same'});assert.equal(repeated.project,'WP-2');assert.equal(s.calls,2);assert.equal(s.ledger.size,2);
});
test('lost acknowledgement retains local identity, re-query is safe even after server acknowledged',async()=>{
  const s=server(),disk=memory();s.ackLost=true;const life=new OperationLifecycle(disk,s.wire,()=> 'one-key');await assert.rejects(life.execute('start',{}),/ack response lost/);assert.equal((await disk.get()).key,'one-key');assert.equal(s.calls,1);
  s.ackLost=false;assert.equal((await life.recover()).result.project,'WP-1');assert.equal(s.calls,1);assert.equal(await disk.get(),null);
});
test('remote-only pending and disappeared receipts never become a reconstructed new action',async()=>{
  const s=server();s.ledger.set('old',{state:'PENDING',digest:'pending',operation:{id:'old',name:'start',payload:{instance:'I-one'}}});const life=new OperationLifecycle(memory(),s.wire,()=> 'new');
  assert.equal((await life.recover()).receipt.state,'PENDING');await assert.rejects(life.replay(),/尚未确认/);await assert.rejects(life.acknowledgeFailure(),/尚未确定/);
  s.ledger.clear();await assert.rejects(life.replay(),/尚未确认/);assert.equal(s.calls,0);
});
test('each unacknowledged receipt remains discoverable and failure acknowledgement is not a business retry',async()=>{
  const s=server();for(const id of ['a','b'])s.ledger.set(id,{state:id==='a'?'COMPLETED':'FAILED',result:{project:'WP-old'},digest:id,operation:{id,name:'create',payload:{}}});
  const life=new OperationLifecycle(memory(),s.wire,()=> 'new');await life.recover();await assert.rejects(life.execute('create',{}),/原操作/);assert.equal((await life.inspect()).receipt.state,'FAILED');await life.acknowledgeFailure();assert.equal(await life.discover(),null);assert.equal(s.calls,0);
});
// The fake IDB implements atomic single-store transactions, including completion events.
function fakeIndexedDB(){const values=new Map();const db={createObjectStore(){},transaction(){const tx={objectStore(){return {get(k){const r={};queueMicrotask(()=>{r.result=values.get(k);r.onsuccess();queueMicrotask(()=>tx.oncomplete());});return r;},put(v,k){values.set(k,structuredClone(v));},delete(k){values.delete(k);}};}};return tx;}};return {open(){const r={};queueMicrotask(()=>{r.result=db;r.onupgradeneeded();r.onsuccess();});return r;}};}
test('workspace identity separates pending browser operations on the same origin',async()=>{
  const idb=fakeIndexedDB(),a=indexedOperationStorage(idb,'WS-a'),b=indexedOperationStorage(idb,'WS-b'),legacy=indexedOperationStorage(idb);
  await legacy.claim({key:'unbound-old'});await a.claim({key:'a',payload:{secret:'a-only'}});assert.equal(await b.get(),null);await b.claim({key:'b'});await b.clear('a');assert.equal((await a.get()).key,'a');assert.equal((await b.get()).key,'b');assert.equal((await legacy.get()).key,'unbound-old');
});

test('successful quit does not query a stopped transport; original receipt is confirmed on next launch',async()=>{
  const disk=memory();let queries=0,ack=0;
  const wire={send:async()=>({stopped:true}),query:async()=>{queries++;return {state:'COMPLETED',result:{stopped:true}};},ack:async()=>{ack++;}};
  const life=new OperationLifecycle(disk,wire,()=> 'quit-key');assert.equal((await life.execute('quit',{})).stopped,true);assert.equal(queries,0);assert.equal((await disk.get()).key,'quit-key');
  await life.recover();assert.equal(queries,1);assert.equal(ack,1);assert.equal(await disk.get(),null);
});
