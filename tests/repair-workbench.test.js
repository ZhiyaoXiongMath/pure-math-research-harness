'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const sourcePath=path.join(__dirname,'../research_studio/static/workbench.js');
const i18n=require('../research_studio/static/i18n.js');i18n.setLocale('zh-CN');
const {OperationLifecycle,indexedOperationStorage,amendOverrides,stagePresentation,workflowGraphEdges,workflowStagePresentation,workflowStageLabel}=require(sourcePath);
const {execFileSync}=require('node:child_process');
function memoryStorage(){let row=null;return {get:async()=>row,claim:async value=>{if(row)return false;row=structuredClone(value);return true;},clear:async key=>{if(row?.key===key)row=null;}};}
test('lost successful response recovers the original operation after reload without sending again',async()=>{
  const disk=memoryStorage();const sent=[];let receipt={state:'NOT_FOUND'};
  const wire={send:async op=>{sent.push(structuredClone(op));receipt={state:'COMPLETED',result:{instance_id:'I-one'}};throw Error('response lost');},query:async()=>receipt};
  const first=new OperationLifecycle(disk,wire,()=> 'original-operation');
  await assert.rejects(first.execute('start',{max_calls:3}),/response lost/);
  const restored=new OperationLifecycle(disk,wire,()=> 'must-not-be-used');
  await assert.rejects(restored.execute('start',{max_calls:3}),/原操作/);
  const found=await restored.recover();assert.equal(found.operation.key,'original-operation');assert.equal(found.result.instance_id,'I-one');assert.equal(sent.length,1);assert.equal(await disk.get(),null);
});
test('request lost before arrival replays exactly the same original payload and ID',async()=>{
  const disk=memoryStorage();let fail=true;const sent=[];
  const wire={send:async op=>{sent.push(structuredClone(op));if(fail)throw Error('offline');return {project:'WP-1'};},query:async()=>({state:'NOT_FOUND'})};
  const first=new OperationLifecycle(disk,wire,()=> 'one-key');await assert.rejects(first.execute('new-workflow',{target_text:'原题\nunchanged',kind:'TRW'}));
  fail=false;const restored=new OperationLifecycle(disk,wire,()=> 'new-key');await restored.replay();assert.equal(sent.length,2);assert.deepEqual(sent[1],sent[0]);
});
test('pending operations cannot be replayed or dismissed, and later explicit equal-payload actions get new IDs',async()=>{
  const disk=memoryStorage();let state='PENDING',calls=0,next=0;
  const wire={send:async()=>{calls++;throw Error('lost');},query:async()=>({state,error:'VALIDATION_ERROR'})};const life=new OperationLifecycle(disk,wire,()=> 'key-'+(++next));
  await assert.rejects(life.execute('start',{max_calls:2}));await assert.rejects(life.replay(),/尚未确认/);await assert.rejects(life.acknowledgeFailure(),/尚未确定/);assert.equal(calls,1);
  state='FAILED';await life.acknowledgeFailure();wire.send=async op=>{calls++;return {key:op.key};};const a=await life.execute('start',{max_calls:2});const b=await life.execute('start',{max_calls:2});assert.notEqual(a.key,b.key);assert.equal(calls,3);
});
test('durable storage failure prevents dispatch, concurrent clicks cannot dispatch two operations',async()=>{
  let calls=0;const broken={get:async()=>null,claim:async()=>{throw Error('quota');},clear:async()=>{}};
  const a=new OperationLifecycle(broken,{send:async()=>{calls++;}},()=> 'key');await assert.rejects(a.execute('upload-archive',{data:'large'}),/quota/);assert.equal(calls,0);
  let finish;const disk=memoryStorage(),b=new OperationLifecycle(disk,{send:()=>{calls++;return new Promise(resolve=>finish=resolve);}},()=> 'one');const pending=b.execute('start',{});await new Promise(setImmediate);await assert.rejects(b.execute('start',{}),/正在提交/);finish({});await pending;assert.equal(calls,1);
});
const scope=(stage,role='SYNTHESIS',purpose='DEFAULT')=>({workflow_kind:'TRW',stage_id:stage,role,purpose});
const override=(stage,effort)=>({explicit:true,scope:scope(stage),model:'gpt-6-astra',reasoning_effort:effort,service_tier:'default'});
test('configuration merge and reset affect only the exact scope',()=>{
  const prior=[override('P7','xhigh'),override('P10','max')];const changed=amendOverrides(prior,[override('P7','high')]);assert.equal(changed.find(x=>x.scope.stage_id==='P10').reasoning_effort,'max');assert.equal(changed.find(x=>x.scope.stage_id==='P7').reasoning_effort,'high');
  const reset=amendOverrides(changed,[],[scope('P7')]);assert.deepEqual(reset,[prior[1]]);assert.equal(prior[0].reasoning_effort,'xhigh');
});
test('workflow activity shows multiple real active stages and native recent return, never highest stage',()=>{
  const activity={active_stages:['P4','P7'],waiting_stages:['P9'],recent_stages:['P3'],stages:[{stage_id:'P12',status:'VISITED'}]};
  assert.equal(stagePresentation(activity,'P4').active,true);assert.equal(stagePresentation(activity,'P7').active,true);assert.equal(stagePresentation(activity,'P9').waiting,true);assert.equal(stagePresentation(activity,'P3').recent,true);assert.equal(stagePresentation(activity,'P12').recent,false);assert.equal(stagePresentation(activity,'P8').status,'UNVISITED');
});
// A minimal DOM exercises the shipped script; no browser automation or third-party dependency.
class Node {
  constructor(tag,doc){this.tagName=tag.toUpperCase();this.doc=doc;this.children=[];this.dataset={};this.style={};this.listeners={};this.attributes={};this.hidden=false;this.disabled=false;this.open=false;this.value='';this.checked=false;this.files=[];this._text='';this.className='';this.scrollTop=0;this.classList={contains:name=>this.className.split(' ').includes(name),toggle:(name,active)=>{const values=new Set(this.className.split(' ').filter(Boolean));const enabled=active===undefined?!values.has(name):active;if(enabled)values.add(name);else values.delete(name);this.className=[...values].join(' ');return enabled;},remove:(...names)=>{this.className=this.className.split(' ').filter(x=>!names.includes(x)).join(' ');},add:(...names)=>{this.className=[...new Set([...this.className.split(' ').filter(Boolean),...names])].join(' ');}};}
  set id(v){this._id=v;this.doc.ids[v]=this;}get id(){return this._id;}
  set textContent(value){this._text=String(value);for(const n of this.children||[])n.parent=null;this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
  get childNodes(){return this.children;}get parentNode(){return this.parent||null;}get parentElement(){return this.parent||null;}get selectedOptions(){return this.children.filter(n=>n.selected||n.value===this.value);}
  append(...nodes){for(const n of nodes){n.remove();n.parent=this;this.children.push(n);if(this.tagName==='SELECT'&&this.children.length===1)this.value=n.value;}}
  prepend(...nodes){for(const n of nodes)n.remove();for(const n of nodes)n.parent=this;this.children.unshift(...nodes);}
  replaceChildren(...nodes){for(const n of this.children)n.parent=null;this.children=[];this._text='';this.append(...nodes);}
  replaceWith(node){const parent=this.parent;if(!parent)return;const index=parent.children.indexOf(this);node.remove();parent.children[index]=node;node.parent=parent;this.parent=null;}
  remove(){if(this.parent){this.parent.children=this.parent.children.filter(n=>n!==this);this.parent=null;}}
  addEventListener(type,fn){this.listeners[type]=fn;}setAttribute(k,v){this.attributes[k]=String(v);if(k==='class')this.className=String(v);}getAttribute(k){return this.attributes[k]??null;}
  querySelectorAll(selector){const match=n=>selector.startsWith('.')?n.className.split(' ').includes(selector.slice(1)):selector.startsWith('[data-')?Object.hasOwn(n.dataset,selector.slice(6,-1).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())):selector==='details[open]'?n.tagName==='DETAILS'&&n.open:n.tagName===selector.toUpperCase();const result=[];for(const child of this.children){if(match(child))result.push(child);result.push(...child.querySelectorAll(selector));}return result;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  getBoundingClientRect(){
    // Synthetic geometry only exercises edge routing; this is not pixel/browser acceptance.
    if(this.dataset.stage){const left=27+(Number(this.style.gridColumn||1)-1)*123,top=28+(Number(this.style.gridRow||1)-1)*93;return {left,top,right:left+100,bottom:top+57,width:100,height:57};}
    const columns=Number(this.dataset.columns||5),rows=Math.max(1,...this.children.filter(n=>n.dataset.stage).map(n=>Number(n.style.gridRow)));
    return {left:0,top:0,right:columns*123+31,bottom:rows*93+19,width:columns*123+31,height:rows*93+19};
  }
  showModal(){this.open=true;}close(){this.open=false;}scrollIntoView(){this.doc.scrolls++;}
  async click(){return (this.onclick||this.listeners.click)?.({preventDefault(){},currentTarget:this});}
}
function domHarness(){
  const document={ids:{},scrolls:0,scrollY:0,createElement(tag){return new Node(tag,this);},createElementNS(ns,tag){return this.createElement(tag);},getElementById(id){return this.ids[id]||null;},querySelectorAll(selector){const roots=[...new Set(Object.values(this.ids))].filter(n=>!n.parent);return [...new Set(roots.flatMap(n=>n.querySelectorAll(selector)))];}};
  const html=fs.readFileSync(path.join(__dirname,'../research_studio/static/index.html'),'utf8').replace(/<!--[\s\S]*?-->/g,'');for(const m of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"([^>]*)/g)){const n=document.createElement(m[1]);n.id=m[2];n.hidden=/\bhidden\b/.test(m[3]);}
  for(const match of html.matchAll(/<button data-view="([^"]+)"([^>]*)>([^<]+)<\/button>/g)){const b=document.createElement('button');b.dataset.view=match[1];b.className=/class="([^"]+)"/.exec(match[2])?.[1]||'';b.textContent=match[3];document.ids.tabs.append(b);}
  const requests=[],localKeys=[],receipts=new Map();let response=async()=>({}),counter=0;
  const context={document,window:{indexedDB:{},get scrollY(){return document.scrollY;}},URL,URLSearchParams,Date,Set,Map,Object,JSON,Error,Promise,crypto:{randomUUID:()=> 'test-key-'+String(++counter).padStart(20,'0')},location:{origin:'http://localhost:18400',hash:'',pathname:'/'},history:{replaceState(){}},localStorage:{getItem(key){localKeys.push({method:'get',key});return key==='pmrs_project'?'WP-old-installation':'';},setItem(key,value){localKeys.push({method:'set',key,value});}},FileReader:class {readAsDataURL(file){this.result='data:application/zip;base64,'+file.base64;Promise.resolve().then(()=>this.onload());}},setInterval(){},requestAnimationFrame(fn){fn();},ResizeObserver:class {observe(){}disconnect(){}},fetch:async(url,options)=>{
    requests.push({url:String(url),options});const parsed=new URL(url);let value;
    if(parsed.pathname==='/api/operations')value={operations:[],workspace_id:'WORKSPACE-test'};
    else if(parsed.pathname==='/api/operation')value=receipts.get(parsed.searchParams.get('key'))||{state:'NOT_FOUND'};
    else if(parsed.pathname==='/api/operation/ack'){const data=JSON.parse(options.body);assert.match(data.id,/^[a-f0-9]{64}$/);assert.match(data.digest,/^[a-f0-9]{64}$/);value={acknowledged:true};}
    else {value=await response(parsed,options);if(options.method==='POST'&&parsed.pathname.startsWith('/api/action/'))receipts.set(options.headers['Idempotency-Key'],{state:'COMPLETED',result:value,operation:{id:'a'.repeat(64)},digest:'b'.repeat(64)});}
    return {ok:true,status:200,json:async()=>value};
  }};
  const tail=`globalThis.testUI={renderOperationRecovery,report,reportRevision,surveyFreezeForm,surveyScopeFields,surveyCreateForm,surveyActivityForm,surveyReportForm,applyLocale,patchReportStates,importForm,showImportConfirmation,nativeHistory,discoveryFields,policyEditor,renderWorkflowGraph,renderStageDetail,selectGraphStage,resetWorkflowGraphSelection,selectView,navigateStage,syncViewSelection,refresh,task,patchTaskStates,pollProgress,newWorkflowForm,discoveryConfigForm,reconcile,startForm,configureForm,settings,operations,action,setState(s,{projectKey='WP-test',instance='I-1',viewName='current',readSnapshot='frozen'}={}){project=projectKey;snapshot=readSnapshot;latestCommit=readSnapshot;currentStatus=s;view=viewName;graphSelection=null;document.getElementById('instance').value=instance;navigationScope=project+'|'+instance;contentProgressFingerprint=progressFingerprint(s);},setScope(p,i){project=p;document.getElementById('instance').value=i;},setGraph(g){graphDefinition=g;},setPolicy(p){modelPolicy=p;},getState(){return {project,snapshot,latestCommit,currentStatus,view,graphSelection,graphFocus:workflowGraphView.focus,graphMode:workflowGraphView.mode};}};`;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../research_studio/static/messages.js'),'utf8'),context);
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../research_studio/static/i18n.js'),'utf8'),context);
  context.window.PMRS_I18N.setLocale('zh-CN');
  vm.runInNewContext(fs.readFileSync(sourcePath,'utf8').replace('guarded(initial)();',tail),context);
  context.testUI.operations.storage=memoryStorage();return {ui:context.testUI,document,requests,localKeys,setResponse(fn){response=fn;}};
}
function status(){return {commit:'new-commit',title:'Test',synthetic:true,workflow:{instances:[{instance_id:'I-1',kind:'TRW',name:'目标一',status:'ACTIVE'}]},mathematical:{records:2},budget:{remaining_calls:3,project_remaining_calls:4,grants:[]},execution:{running_processes:1,unknown:0,requests:[]},activity:{instance_id:'I-1',workflow_kind:'TRW',instance_status:'ACTIVE',active_stages:['P4','P7'],recent_stages:['P3'],stages:[]},project_jobs:[{state:'RUNNING',initiated_by_instance_id:'I-other',message:'Project work'}],tasks:[],missions:[],candidates:[]};}
const policy={rules:[{workflow_kind:'TRW',stage_id:'P7',role:'SYNTHESIS',call_model:true,reasoning_effort:'xhigh',model:'gpt-6-astra',service_tier:'default'},{workflow_kind:'TRW',stage_id:'P10',role:'SYNTHESIS',call_model:true,reasoning_effort:'max',model:'gpt-6-astra',service_tier:'default'}],purpose_exceptions:[{stage_id:'P7',role:'SYNTHESIS',purpose:'MATHEMATICAL_INTEGRATION',reasoning_effort:'max'}]};
test('five-second progress path updates status while retaining expanded reader DOM and frozen snapshot',async()=>{
  const h=domHarness(),s=status();h.ui.setState(s);const reader=h.document.createElement('details');reader.open=true;reader.append(h.document.createElement('div'));h.document.ids.content.append(reader);h.document.ids.dialog.open=true;
  h.setResponse(async url=>{assert.equal(url.pathname,'/api/progress');return s;});await h.ui.pollProgress();
  assert.equal(h.document.ids.content.children[0],reader);assert.equal(reader.open,true);assert.equal(h.document.scrolls,0);assert.equal(h.ui.getState().snapshot,'frozen');assert.equal(h.ui.getState().latestCommit,'new-commit');assert.equal(h.document.ids['content-update'].hidden,false);assert.equal(h.requests.length,1);
  assert.match(h.document.ids.activity.children[0].children[0].textContent,/项目协调器/);assert.match(h.document.ids.activity.children[0].children[1].textContent,/I-other/);
});
test('late progress for a changed selector does not replace the selected state',async()=>{
  const h=domHarness(),s=status();h.ui.setState(s);let resolve;h.setResponse(()=>new Promise(r=>resolve=r));const pending=h.ui.pollProgress();await new Promise(setImmediate);h.document.ids.instance.value='I-other';resolve({...s,commit:'stale'});await pending;assert.equal(h.ui.getState().latestCommit,'frozen');
});
test('all registered nodes, return edges, P7 routes and handoffs appear without synthetic passed stages',()=>{
  const h=domHarness();h.ui.setState(status());h.ui.setGraph({workflows:[{kind:'TRW',nodes:Array.from({length:15},(_,i)=>({stage_id:'P'+i,label:'阶段 '+i})),edges:[{from:'P9',to:'P4',kind:'return'}]},{kind:'TFDW',nodes:Array.from({length:6},(_,i)=>({stage_id:'D'+i,label:'发现 '+i})),edges:[]}],analysis_routes:[{id:'A',roles:['DIRECT'],label:'直接分析'},{id:'B',roles:['LEARN'],label:'学习后分析'},{id:'C',roles:['PROOF','COUNTEREXAMPLE'],label:'双审分析'}],handoffs:[{from:'TRW',to:'TFDW'},{from:'TFDW',to:'TRW'}]});h.ui.renderWorkflowGraph(status().activity);
  const nodes=h.document.ids['workflow-graph'].querySelectorAll('[data-stage]');assert.equal(nodes.length,21);assert.equal(nodes.filter(n=>n.className.split(' ').includes('running')).length,2);assert.equal(nodes.find(n=>n.dataset.stage==='P12').className.includes('visited'),false);assert.equal(h.document.ids['workflow-graph'].querySelector('.edge-list').children.length,0);h.ui.selectGraphStage('TRW','P9');assert.equal(h.document.ids['workflow-graph'].querySelector('.edge-list').children.length,1);h.ui.selectGraphStage('TRW','P7');assert.match(h.document.ids['stage-detail'].textContent,/直接分析/);assert.match(h.document.ids['stage-detail'].textContent,/学习后分析/);assert.match(h.document.ids['stage-detail'].textContent,/双审分析/);assert.match(h.document.ids['stage-detail'].textContent,/TRW → TFDW/);assert.equal(h.requests.length,0);
});
test('TFDW preserves explicit originals and cannot silently invent missing background or axes',()=>{
  const h=domHarness(),form=h.document.createElement('form');h.ui.setState(status());const fields=h.ui.discoveryFields(form,'d',{phenomenon:'现象\noriginal'});assert.throws(()=>fields.value(),/完整/);
  h.document.ids['d-immutable_background'].value='  无额外背景约束\n';h.document.ids['d-allowed_axes'].value='仅改变参数 λ。';const values=fields.value();assert.equal(values.phenomenon,'现象\noriginal');assert.equal(values.immutable_background,'  无额外背景约束\n');assert.equal(values.allowed_axes,'仅改变参数 λ。');
  h.document.ids['d-allowed_axes'].value='';h.document.ids['d-draft'].checked=true;assert.equal(fields.value().allowed_axes,'');
});
test('policy editor keeps precise P7 defaults/exceptions and queues a reset for only selected scope',async()=>{
  const h=domHarness();h.ui.setPolicy(policy);const form=h.document.createElement('form');const editor=await h.ui.policyEditor(form,{kind:'TRW',existing:[override('P7','high'),override('P10','max')],prefix:'test'});
  assert.equal(h.document.ids['test-effort'].value,'high');h.document.ids['test-purpose'].value='MATHEMATICAL_INTEGRATION';h.document.ids['test-purpose'].onchange();assert.equal(h.document.ids['test-effort'].value,'max');h.document.ids['test-purpose'].value='DEFAULT';h.document.ids['test-purpose'].onchange();
  const reset=form.querySelectorAll('button').find(b=>b.textContent.includes('恢复默认'));await reset.listeners.click({preventDefault(){},currentTarget:reset});assert.equal(editor.resetScopes().length,1);assert.equal(editor.resetScopes()[0].stage_id,'P7');assert.equal(h.document.ids['test-effort'].value,'xhigh');assert.equal(editor.value().length,0);
});
test('UNKNOWN form separates abandonment from actual source-bound not-sent evidence',async()=>{
  const h=domHarness();h.ui.setState(status());h.setResponse(async()=>({statements:[],sources:[{source_ref:'SO-log',title:'实际发送日志.txt'}],next_offset:null}));await h.ui.reconcile('R-unknown');const choice=h.document.ids['reconcile-choice'],evidence=h.document.ids['reconcile-evidence'];assert.equal(choice.value,'ABANDON_UNKNOWN');assert.equal(evidence.disabled,true);choice.value='CONFIRMED_NOT_SENT';choice.onchange();assert.equal(evidence.required,true);assert.equal(evidence.disabled,false);assert.equal(evidence.children[1].value,'SO-log');assert.equal(h.requests.every(x=>x.options.method==='GET'),true);
});
function fullResponse(s,posts){return async(url,options)=>{
  if(options.method==='POST'&&url.pathname.startsWith('/api/action/')){const payload=JSON.parse(options.body);posts.push({path:url.pathname,payload,key:options.headers['Idempotency-Key']});return {instance_id:'I-1'};}
  if(url.pathname==='/api/workflow-inputs')return {statements:[{ref:'KR-existing',title:'Existing exact statement',body:'For all n, n + 0 = n.'}],sources:[{source_ref:'SO-log',title:'发送日志'}],next_offset:null};
  if(url.pathname==='/api/status')return s;
  if(url.pathname==='/api/settings')return {policy,client:{installed:true,authenticated:true}};
  return {records:[],next_offset:null};
};}
async function submitDialog(h){const form=h.document.ids['dialog-content'].querySelector('form');assert.ok(form);await form.listeners.submit({preventDefault(){},currentTarget:form});}
test('generic named second TRW selects an existing exact target and sends no handoff action',async()=>{
  const h=domHarness(),posts=[];h.ui.setState(status());h.setResponse(fullResponse(status(),posts));await h.ui.newWorkflowForm();h.document.ids['workflow-name'].value='独立第二条研究';h.document.ids['workflow-target'].value='KR-existing';h.document.ids['workflow-target'].onchange();await submitDialog(h);
  assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/action/new-workflow');assert.equal(posts[0].payload.name,'独立第二条研究');assert.equal(posts[0].payload.target_ref,'KR-existing');assert.equal(posts[0].payload.kind,'TRW');assert.ok(posts[0].key);
});
test('generic named TFDW reuses a source only after explicit selection and preserves the other two originals',async()=>{
  const h=domHarness(),posts=[];h.ui.setState(status());h.setResponse(fullResponse(status(),posts));await h.ui.newWorkflowForm();h.document.ids['workflow-name'].value='新现象研究';h.document.ids['workflow-kind'].value='TFDW';h.document.ids['workflow-kind'].onchange();h.document.ids['workflow-discovery-phenomenon-source'].value='SO-log';h.document.ids['workflow-discovery-phenomenon-source'].onchange();h.document.ids['workflow-discovery-immutable_background'].value='  固定背景\n';h.document.ids['workflow-discovery-allowed_axes'].value='只变 λ';await submitDialog(h);
  assert.equal(posts[0].payload.kind,'TFDW');assert.equal(posts[0].payload.discovery_scope.phenomenon_ref,'SO-log');assert.equal(posts[0].payload.discovery_scope.immutable_background,'  固定背景\n');assert.equal(posts[0].payload.discovery_scope.allowed_axes,'只变 λ');
});
test('initial authorization submits explicit policy override before any first dispatch',async()=>{
  const h=domHarness(),posts=[];h.ui.setState(status());h.ui.setPolicy(policy);h.setResponse(fullResponse(status(),posts));await h.ui.startForm();h.document.ids['round-policy-effort'].value='high';const add=h.document.ids['dialog-content'].querySelectorAll('button').find(n=>n.textContent.includes('加入或更新'));await add.listeners.click({preventDefault(){},currentTarget:add});await submitDialog(h);
  assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/action/start');assert.equal(posts[0].payload.model_overrides[0].scope.stage_id,'P7');assert.equal(posts[0].payload.model_overrides[0].reasoning_effort,'high');assert.equal(posts[0].payload.max_calls,12);assert.equal(posts[0].payload.report_first,false);
});
test('future configuration submits scoped reset and retains other mission overrides in the editor',async()=>{
  const h=domHarness(),posts=[],s=status();s.workflow.instances[0].current_mission_id='M-1';s.missions=[{mission_id:'M-1',budget_grant_id:'B-1'}];s.budget.grants=[{budget_grant_id:'B-1',execution_policy:{model_overrides:[override('P7','high'),override('P10','max')]}}];h.ui.setState(s);h.ui.setPolicy(policy);h.setResponse(fullResponse(s,posts));await h.ui.configureForm();const reset=h.document.ids['dialog-content'].querySelectorAll('button').find(n=>n.textContent.includes('恢复默认'));await reset.listeners.click({preventDefault(){},currentTarget:reset});await submitDialog(h);assert.equal(posts[0].path,'/api/action/configure');assert.deepEqual(posts[0].payload.model_overrides,[]);assert.deepEqual(posts[0].payload.reset_scopes,[scope('P7')]);
});
test('not-sent submission sends actual source ref separately from the human note; abandonment sends no evidence',async()=>{
  for(const disposition of ['CONFIRMED_NOT_SENT','ABANDON_UNKNOWN']){const h=domHarness(),posts=[];h.ui.setState(status());h.setResponse(fullResponse(status(),posts));await h.ui.reconcile('R-original');h.document.ids['reconcile-choice'].value=disposition;h.document.ids['reconcile-choice'].onchange();h.document.ids['reconcile-evidence'].value='SO-log';h.document.ids['reconcile-note'].value='人工判断依据原日志';await submitDialog(h);assert.equal(posts[0].payload.request_id,'R-original');assert.equal(posts[0].payload.note,'人工判断依据原日志');assert.equal(posts[0].payload.not_sent_evidence_ref,disposition==='CONFIRMED_NOT_SENT'?'SO-log':undefined);}
});

test('paused discovery draft preserves its original phenomenon when completing background and axes',async()=>{
  const h=domHarness(),posts=[],s=status();s.workflow.instances[0].kind='TFDW';s.workflow.instances[0].discovery_brief_ref='SO-log';h.ui.setState(s);h.setResponse(fullResponse(s,posts));await h.ui.discoveryConfigForm();assert.equal(h.document.ids['edit-discovery-phenomenon-source'].value,'SO-log');assert.equal(h.document.ids['edit-discovery-phenomenon'].disabled,true);h.document.ids['edit-discovery-immutable_background'].value='原背景保持不变';h.document.ids['edit-discovery-allowed_axes'].value='仅比较参数范围';await submitDialog(h);assert.equal(posts[0].path,'/api/action/configure-discovery');assert.equal(posts[0].payload.discovery_scope.phenomenon_ref,'SO-log');assert.equal(posts[0].payload.discovery_scope.immutable_background,'原背景保持不变');assert.equal(posts[0].payload.discovery_scope.allowed_axes,'仅比较参数范围');
});

let registeredGraph;
function nativeGraph(){
  if(!registeredGraph)registeredGraph=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-B','-c','import json; from research_studio.activity import graph; print(json.dumps(graph()))'],{cwd:path.join(__dirname,'..'),encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}}));
  return structuredClone(registeredGraph);
}
function fakeTask(id,stage='P4',role='RESEARCH'){return {task_id:'TASK-'+id,request_id:'REQUEST-'+id,instance_id:'I-1',stage_id:stage,role,activity_label:'研究',model_policy:{model:'gpt-6-astra',reasoning_effort:'max',service_tier:'default'}};}
function withTasks(tasks,requestStates){const s=status();s.commit='fixed-commit';s.tasks=tasks;s.execution.requests=tasks.map((t,i)=>({request_id:t.request_id,execution_state:requestStates[i],fenced:false}));return s;}
function activeTab(h){return h.document.ids.tabs.querySelectorAll('button').filter(n=>n.classList.contains('active')).map(n=>n.dataset.view);}
function findButton(node,text){return node.querySelectorAll('button').find(n=>n.textContent===text);}
async function click(h,node){assert.ok(node,'Expected real UI button');await node.click();assert.equal(h.document.ids.error.textContent,'');}

test('actual registry graph retains original TRW/TFDW edges and all registered Survey paths',()=>{
  const graph=nativeGraph(),before=JSON.stringify(graph);let nodeCount=0,edgeCount=0,mainCount=0,loopCount=0;
  for(const workflow of graph.workflows){
    const main=workflowGraphEdges(workflow),all=workflowGraphEdges(workflow,null,true);
    nodeCount+=workflow.nodes.length;edgeCount+=workflow.edges.length;mainCount+=main.visible.length;loopCount+=main.selfLoops.length;
    assert.equal(all.visible.length+all.selfLoops.length,workflow.edges.length);
    assert.ok(main.visible.every(e=>e.kind==='forward'&&e.from!==e.to));assert.ok(all.visible.every(e=>e.from!==e.to));
    for(const node of workflow.nodes){const local=workflowGraphEdges(workflow,node.stage_id);assert.ok(local.visible.every(e=>workflow.edges.includes(e)));assert.ok(local.related.every(e=>e.from===node.stage_id||e.to===node.stage_id));}
  }
  assert.deepEqual({nodeCount,edgeCount,mainCount,loopCount},{nodeCount:29,edgeCount:140,mainCount:26,loopCount:28});assert.equal(JSON.stringify(graph),before);
  assert.equal(workflowStageLabel('P7'),'义务分析');assert.equal(workflowStagePresentation(null,'TRW','P0').status,'UNKNOWN');
});

test('graph defaults to current kind and preview selection stays read-only with explicit unknown state',async()=>{
  const h=domHarness(),s=status(),graph=nativeGraph();s.activity.waiting_stages=['P9'];s.activity.stages=[{stage_id:'P9',status:'WAITING',waiting_reasons:['已有捕获等待接纳'],next_actions:['检查原始捕获并接纳']}];h.ui.setState(s);h.ui.setGraph(graph);h.ui.renderWorkflowGraph(s.activity);
  const container=h.document.ids['workflow-graph'],maps=container.querySelectorAll('.workflow-map'),nodes=container.querySelectorAll('[data-stage]');
  assert.equal(h.ui.getState().graphMode,'TRW');assert.equal(maps.find(n=>n.dataset.kind==='TRW').hidden,false);assert.equal(maps.find(n=>n.dataset.kind==='TFDW').hidden,true);
  assert.equal(nodes.find(n=>n.dataset.stage==='D0').querySelector('small').textContent,'状态未知');assert.equal(nodes.find(n=>n.dataset.stage==='P8').querySelector('small').textContent,'未访问');
  assert.match(h.document.ids['workflow-summary'].textContent,/实际活动：P4 推导构造、P7 义务分析/);assert.match(h.document.ids['workflow-summary'].textContent,/等待阶段：P9 独立检查/);assert.match(h.document.ids['workflow-summary'].textContent,/P9：已有捕获等待接纳/);
  h.ui.selectGraphStage('TFDW','D2');assert.equal(h.ui.getState().view,'current');assert.equal(h.ui.getState().graphSelection,null);assert.equal(h.ui.getState().graphMode,'TFDW');assert.match(h.document.ids['stage-detail'].textContent,/结构预览/);assert.match(h.document.ids['stage-detail'].textContent,/状态未知/);assert.equal(findButton(h.document.ids['stage-detail'],'查看此阶段任务'),undefined);
  await click(h,container.querySelectorAll('[data-graph-mode]').find(n=>n.dataset.graphMode==='overview'));
  await click(h,container.querySelector('[data-graph-paths]'));
  assert.equal(maps.every(n=>!n.hidden),true);assert.equal(container.querySelectorAll('.stage-wire').length,112);assert.equal(container.querySelectorAll('.stage-iteration').length,28);assert.equal(container.querySelector('.edge-list').children.length,140);assert.equal(h.requests.length,0);
});

test('same-commit progress adds new tasks and updates captured actions in place using original request',async()=>{
  const first=fakeTask('first'),second=fakeTask('second','P9','PROOF'),s=withTasks([first],['SENT']);const h=domHarness();h.ui.setState(s,{viewName:'tasks',readSnapshot:s.commit});
  const original=h.ui.task(first);h.document.ids.content.append(original);const expanded=original.querySelector('details');expanded.open=true;h.document.ids.content.scrollTop=124;h.document.scrollY=820;
  let now=withTasks([first,second],['CAPTURED','PREPARED']);const posts=[];
  h.setResponse(async(url,options)=>{if(url.pathname==='/api/progress'||url.pathname==='/api/status')return now;if(url.pathname==='/api/action/recover'){posts.push(JSON.parse(options.body));now=withTasks([first,second],['SETTLED','PREPARED']);return {request_id:first.request_id};}throw Error('Unexpected route '+url.pathname);});
  await h.ui.pollProgress();const cards=h.document.ids.content.querySelectorAll('[data-task-id]');assert.equal(cards.length,2);assert.equal(cards[0],original);assert.equal(expanded.open,true);assert.equal(h.document.ids.content.scrollTop,124);assert.equal(h.document.scrollY,820);assert.equal(h.document.scrolls,0);assert.equal(h.ui.getState().snapshot,s.commit);assert.equal(h.document.ids['content-update'].hidden,true);
  assert.match(original.querySelector('[data-request-status]').textContent,/已捕获/);const recover=findButton(original,'接纳已捕获结果');assert.ok(recover);assert.equal(h.requests.every(x=>x.options.method==='GET'),true);
  await click(h,recover);assert.equal(posts.length,1);assert.equal(posts[0].request_id,first.request_id);assert.equal(posts[0].instance,'I-1');assert.equal(findButton(h.document.ids.content,'接纳已捕获结果'),undefined);assert.equal(h.requests.filter(x=>x.options.method==='POST'&&new URL(x.url).pathname.startsWith('/api/action/')).length,1);
});

test('same-commit task change notifies readers without changing expanded body DOM or scroll',async()=>{
  const h=domHarness(),s=withTasks([],[]);h.ui.setState(s,{readSnapshot:s.commit});
  const reader=h.document.createElement('details'),body=h.document.createElement('div');body.textContent='Long original proof\n'.repeat(200);reader.open=true;reader.scrollTop=77;reader.append(body);h.document.ids.content.append(reader);h.document.scrollY=1390;h.document.ids['content-update'].hidden=true;
  const after=withTasks([fakeTask('new')],['CAPTURED']);h.setResponse(async url=>{assert.equal(url.pathname,'/api/progress');return after;});await h.ui.pollProgress();
  assert.equal(h.document.ids.content.children[0],reader);assert.equal(reader.children[0],body);assert.equal(body.textContent,'Long original proof\n'.repeat(200));assert.equal(reader.open,true);assert.equal(reader.scrollTop,77);assert.equal(h.document.scrollY,1390);assert.equal(h.document.scrolls,0);assert.equal(h.ui.getState().snapshot,s.commit);assert.equal(h.document.ids['content-update'].hidden,false);assert.match(h.document.ids['content-update-label'].textContent,/任务进展已更新/);assert.equal(h.requests.length,1);
});

test('incremental task polling respects selected stage and removes obsolete controls without rewriting cards',async()=>{
  const h=domHarness(),a=fakeTask('a'),b=fakeTask('b','P9','PROOF'),s=withTasks([a,b],['UNKNOWN','SENT']);h.ui.setState(s,{readSnapshot:s.commit});let now=s;h.setResponse(async()=>now);await h.ui.navigateStage('TRW','P4');
  const original=h.document.ids.content.querySelector('[data-task-id]');assert.equal(original.dataset.taskId,a.task_id);assert.equal(h.document.ids.content.querySelectorAll('[data-task-id]').length,1);assert.ok(findButton(original,'处理不确定请求'));
  now=withTasks([a,b,fakeTask('c','P9','COUNTEREXAMPLE')],['UNKNOWN','CAPTURED','PREPARED']);now.execution.requests[0].unknown_disposition='ABANDON_UNKNOWN';await h.ui.pollProgress();
  assert.equal(h.document.ids.content.querySelector('[data-task-id]'),original);assert.equal(h.document.ids.content.querySelectorAll('[data-task-id]').length,1);assert.equal(findButton(original,'处理不确定请求'),undefined);assert.match(original.querySelector('[data-request-status]').textContent,/已放弃等待/);assert.equal(h.ui.getState().graphSelection,'P4');assert.deepEqual(activeTab(h),['tasks']);
});

test('explicit graph task navigation and tab changes keep view title highlight and stage filter synchronized',async()=>{
  const h=domHarness(),s=withTasks([fakeTask('p4'),fakeTask('p9','P9','PROOF')],['SETTLED','CAPTURED']);h.ui.setState(s,{readSnapshot:s.commit});h.ui.setGraph(nativeGraph());h.setResponse(fullResponse(s,[]));h.ui.renderWorkflowGraph(s.activity);
  h.ui.selectGraphStage('TRW','P4');assert.equal(h.ui.getState().view,'current');assert.equal(h.ui.getState().graphSelection,null);assert.equal(h.requests.length,0);
  await click(h,findButton(h.document.ids['stage-detail'],'查看此阶段任务'));assert.equal(h.ui.getState().view,'tasks');assert.equal(h.ui.getState().graphSelection,'P4');assert.deepEqual(activeTab(h),['tasks']);assert.equal(h.document.ids['view-title'].textContent,'任务与配置');assert.equal(h.document.ids.content.querySelectorAll('[data-task-id]').length,1);assert.equal(h.document.ids['stage-detail'].hidden,false);
  await click(h,findButton(h.document.ids['stage-detail'],'查看相关开放问题'));assert.equal(h.ui.getState().view,'frontier');assert.equal(h.ui.getState().graphSelection,null);assert.deepEqual(activeTab(h),['frontier']);assert.equal(h.document.ids['view-title'].textContent,'开放问题');assert.equal(h.ui.getState().graphFocus.stage,'P4');
  await click(h,h.document.ids.tabs.querySelectorAll('button').find(b=>b.dataset.view==='reports'));assert.equal(h.document.ids['stage-detail'].hidden,true);assert.equal(h.ui.getState().graphFocus,null);assert.equal(h.ui.getState().graphSelection,null);assert.deepEqual(activeTab(h),['reports']);assert.equal(h.document.ids['view-title'].textContent,'研究报告');
});

test('project and instance scope switches clear old graph detail and task stage filter before new reads',async()=>{
  const h=domHarness(),s=withTasks([fakeTask('old')],['SETTLED']);h.ui.setState(s,{readSnapshot:s.commit});h.ui.setGraph(nativeGraph());let now=s;h.setResponse(async(url)=>url.pathname==='/api/status'?now:{records:[],next_offset:null});h.ui.renderWorkflowGraph(s.activity);h.ui.selectGraphStage('TRW','P4');await h.ui.navigateStage('TRW','P4');assert.equal(h.ui.getState().graphSelection,'P4');
  now=withTasks([fakeTask('new-d1','D1','LEARN'),fakeTask('new-d4','D4','FORMULATION_REVIEW')],['SETTLED','PREPARED']);now.workflow.instances=[{instance_id:'I-2',kind:'TFDW',name:'另一发现实例',status:'PAUSED'}];now.tasks.forEach(t=>t.instance_id='I-2');now.activity={instance_id:'I-2',workflow_kind:'TFDW',instance_status:'PAUSED',active_stages:[],waiting_stages:['D4'],recent_stages:['D1'],stages:[]};
  h.ui.setScope('WP-other','I-2');await h.ui.refresh();assert.equal(h.ui.getState().graphSelection,null);assert.equal(h.ui.getState().graphFocus,null);assert.equal(h.ui.getState().graphMode,'TFDW');assert.equal(h.document.ids['stage-detail'].hidden,true);assert.deepEqual(h.document.ids.content.querySelectorAll('[data-task-id]').map(n=>n.dataset.taskId),['TASK-new-d1','TASK-new-d4']);
  const preview=h.document.ids['workflow-graph'].querySelectorAll('[data-stage]').find(n=>n.dataset.stage==='P4');assert.equal(preview.querySelector('small').textContent,'状态未知');assert.equal(preview.getAttribute('aria-pressed'),'false');const last=new URL(h.requests.at(-1).url);assert.equal(last.searchParams.get('project'),'WP-other');assert.equal(last.searchParams.get('instance'),'I-2');
});

test('shared tasks UNKNOWN reconciliation submits the task owner while all instances remain selected',async()=>{
  const h=domHarness(),unknown=fakeTask('shared-unknown'),posts=[];unknown.instance_id='I-owner';
  const s=withTasks([unknown],['UNKNOWN']);s.workflow.instances.push({instance_id:'I-owner',kind:'TRW',name:'共享任务所属实例',status:'ACTIVE'});
  h.ui.setState(s,{instance:'',viewName:'tasks',readSnapshot:s.commit});h.setResponse(fullResponse(s,posts));
  const card=h.ui.task(unknown);h.document.ids.content.append(card);assert.equal(h.document.ids.instance.value,'');
  await click(h,findButton(card,'处理不确定请求'));h.document.ids['reconcile-note'].value='放弃等待此实例的原请求，不确认未发送';
  assert.equal(h.document.ids['reconcile-choice'].value,'ABANDON_UNKNOWN');await submitDialog(h);
  assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/action/reconcile');assert.equal(posts[0].payload.instance,'I-owner');
  assert.equal(posts[0].payload.request_id,unknown.request_id);assert.equal(posts[0].payload.disposition,'ABANDON_UNKNOWN');assert.equal(posts[0].payload.not_sent_evidence_ref,undefined);assert.equal(h.document.ids.instance.value,'');
});


test('4.0 browser persistence cannot pick up an old selected project or pending operation',async()=>{
  const h=domHarness();assert.equal(h.ui.getState().project,'');assert.deepEqual(h.localKeys,[{method:'get',key:'pmrs_4_0_project'}]);
  const opened=[],keys=[];const indexedDB={open(name,version){opened.push({name,version});const request={result:{transaction(storeName,mode){assert.equal(storeName,'operations');assert.equal(mode,'readonly');const tx={objectStore(){return {get(key){keys.push(key);const result={result:null};queueMicrotask(()=>{result.onsuccess();tx.oncomplete();});return result;}};}};return tx;}}};queueMicrotask(()=>request.onsuccess());return request;}};
  assert.equal(await indexedOperationStorage(indexedDB,'WORKSPACE-new').get(),null);assert.deepEqual(opened,[{name:'pmrs-4.0-business-operations',version:1}]);assert.deepEqual(keys,['active:WORKSPACE-new']);
  const html=fs.readFileSync(path.join(__dirname,'../research_studio/static/index.html'),'utf8');assert.match(html,/<title[^>]*>PMRS 4\.1\.0/);assert.match(html,/<footer><!--[^>]+-->PMRS 4\.1\.0/);assert.doesNotMatch(html,/data-view="legacy"|导入与恢复/);
});
test('backup UI checks and restores only native archives with the preserved 128 MiB bound',async()=>{
  const h=domHarness(),posts=[];h.ui.setState(status());h.setResponse(async(url,options)=>{
    if(url.pathname==='/api/workspace')return {projects:[]};
    if(url.pathname.startsWith('/api/action/')){posts.push({path:url.pathname,payload:JSON.parse(options.body)});return url.pathname.endsWith('/upload-archive')?{mode:'restore',upload_id:'UP-native',summary:{format:'pmrs.project/3.4-final-1',files:8,title:'原生完整备份',processes_restored:false}}:{project:'WP-restored'};}
    throw Error('Unexpected request '+url.pathname);
  });h.ui.importForm();assert.equal(h.document.ids['dialog-content'].querySelectorAll('select').length,0);assert.match(h.document.ids['dialog-content'].textContent,/128 MiB/);
  h.document.ids['import-file'].files=[{size:128*1024*1024+1,base64:'bmF0aXZl'}];await submitDialog(h);assert.equal(posts.length,0);assert.match(h.document.ids.error.textContent,/128 MiB/);
  h.document.ids['import-file'].files=[{size:33*1024*1024,base64:'bmF0aXZl'}];await submitDialog(h);assert.equal(posts[0].path,'/api/action/upload-archive');assert.equal(posts[0].payload.mode,'restore');assert.equal(posts[0].payload.data,'bmF0aXZl');assert.match(h.document.ids['dialog-content'].textContent,/当前原生项目备份/);assert.doesNotMatch(h.document.ids['dialog-content'].textContent,/3\.4/);h.ui.applyLocale('en');assert.match(h.document.ids['dialog-content'].textContent,/Content[:：]\s*Current native project backup/);assert.doesNotMatch(h.document.ids['dialog-content'].textContent,/原生完整备份/);h.ui.applyLocale('zh-CN');assert.match(h.document.ids['dialog-content'].textContent,/内容：当前原生项目备份/);
  await h.document.ids['dialog-content'].querySelectorAll('button').find(b=>b.textContent==='恢复到新项目').click();assert.equal(posts.length,2);assert.equal(posts[1].path,'/api/action/restore');assert.equal(posts[1].payload.upload_id,'UP-native');assert.ok(h.localKeys.filter(r=>r.method==='set').every(r=>r.key==='pmrs_4_0_project'));h.ui.showImportConfirmation({mode:'restore',upload_id:'UP-other',summary:{title:'原始 archive title 未修改'}});h.ui.applyLocale('en');assert.match(h.document.ids['dialog-content'].textContent,/原始 archive title 未修改/);assert.equal(posts.length,2);
});
test('recovered non-native archive mode cannot dispatch an obsolete action',()=>{
  const h=domHarness();for(const mode of ['upgrade',undefined,'other'])assert.throws(()=>h.ui.showImportConfirmation({mode,upload_id:'UP-unsupported',summary:{}}),/只支持恢复当前原生/);assert.equal(h.requests.length,0);
});
test('project research history reads native instance-scoped journal pages at the frozen commit',async()=>{
  const h=domHarness(),s=status();h.ui.setState(s,{viewName:'history'});const event={event_id:'EVENT-own',title:'本轮研究已授权',event_type:'AUTHORIZE_MISSION',sequence:7,commit:s.commit,at:'2026-10-08T00:00:00Z',instance_ids:['I-1'],summary:'当前项目的研究记录',details:{event:{type:'AUTHORIZE_MISSION'},delta_counts:{missions:1}}};
  h.setResponse(async url=>{if(url.pathname==='/api/status')return s;if(url.pathname==='/api/history'){assert.equal(url.searchParams.get('project'),'WP-test');assert.equal(url.searchParams.get('instance'),'I-1');assert.equal(url.searchParams.get('commit'),s.commit);return {records:[event],next_offset:20};}throw Error('Unexpected read '+url.pathname);});
  await h.ui.refresh();assert.equal(h.document.ids['view-title'].textContent,'研究历史');assert.match(h.document.ids.content.textContent,/本轮研究已授权/);assert.match(h.document.ids.content.textContent,/关联流程：I-1/);assert.match(h.document.ids.content.textContent,/AUTHORIZE_MISSION/);assert.equal(h.document.ids.more.hidden,false);assert.equal(h.requests.every(r=>r.options.method==='GET'),true);assert.equal(h.requests.some(r=>new URL(r.url).pathname.includes('legacy')),false);
  const projectEvent=h.ui.nativeHistory({...event,instance_ids:[]});assert.match(projectEvent.textContent,/项目级记录/);
});

test('Survey creation saves complete paused scope using the native action without research dispatch',async()=>{
  const h=domHarness(),s=status(),posts=[];s.workflow.instances=[];h.ui.setState(s,{instance:''});h.setResponse(async(url,opts)=>{if(opts.method==='POST'&&url.pathname.startsWith('/api/action/')){posts.push({path:url.pathname,payload:JSON.parse(opts.body)});return {instance_id:'I-survey'};}if(url.pathname==='/api/workflow-inputs')return {statements:[],sources:[],next_offset:null};if(url.pathname==='/api/status')return {...s,workflow:{instances:[{instance_id:'I-survey',kind:'SURVEY',status:'PAUSED',name:'Survey'}]}};if(url.pathname==='/api/workspace')return {projects:[{key:'WP-test',title:'Test'}]};return {scope:{},readiness:{status:'NEEDS_WORK'},records:[]};});
  await h.ui.surveyCreateForm();h.document.ids['survey-name'].value='Geometric sums';h.document.ids['survey-create-topic'].value='Finite geometric sums';h.document.ids['survey-create-questions'].value='Find the formula.\nCheck q = 1.';h.document.ids['survey-create-objects'].value='Fields\nFinite sequences';h.document.ids['survey-create-conditions'].value='n is nonnegative';h.document.ids['survey-create-include'].value='q = 1';h.document.ids['survey-create-exclude'].value='Infinite series';await submitDialog(h);
  assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/action/new-workflow');assert.equal(posts[0].payload.kind,'SURVEY');assert.equal(posts[0].payload.survey_scope.delivery_goal,'KNOWLEDGE_ONLY');assert.deepEqual(posts[0].payload.survey_scope.questions,['Find the formula.','Check q = 1.']);assert.deepEqual(posts[0].payload.survey_scope.objects,['Fields','Finite sequences']);assert.equal(posts[0].payload.max_calls,undefined);
});
test('Survey output plan and selected edition request are distinct explicit actions',async()=>{
  const h=domHarness(),s=status(),posts=[];s.workflow.instances=[{instance_id:'I-1',kind:'SURVEY',status:'PAUSED',name:'Survey'}];h.ui.setState(s);const data={scope:{},readiness:{status:'READY'},snapshots:[{id:'SN-exact',selected_refs:['KR-one'],material:{closure:['KR-one']}}],output_plans:[]};h.setResponse(async(url,opts)=>{if(opts.method==='POST'&&url.pathname.startsWith('/api/action/')){posts.push({path:url.pathname,payload:JSON.parse(opts.body)});return {plan_ref:'PLAN-exact'};}if(url.pathname==='/api/status')return s;if(url.pathname==='/api/survey')return data;if(url.pathname==='/api/workflow-inputs')return {records:[{ref:'KR-one',title:'Result'}],statements:[],sources:[]};return {reports:[]};});
  await h.ui.surveyReportForm();h.document.ids['survey-snapshot'].value='SN-exact';h.document.ids['survey-profile'].value='thematic';h.document.ids['survey-prerequisites'].value='Finite fields\nFinite sequences';await submitDialog(h);assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/action/survey-plan');assert.equal(posts[0].payload.profile,'thematic');assert.deepEqual(posts[0].payload.prerequisites,['Finite fields','Finite sequences']);assert.deepEqual(posts[0].payload.proof_promises,[]);assert.equal(posts[0].payload.perspective,undefined);
  await click(h,findButton(h.document.ids['dialog-content'],'请求选定的英文稿件'));assert.equal(posts.length,2);assert.equal(posts[1].path,'/api/action/report');assert.deepEqual(posts[1].payload.profiles,['thematic']);assert.equal(posts[1].payload.plan_ref,'PLAN-exact');
});
test('locale saving uses only preferences endpoint and preserves workflow and content selection',async()=>{
  const h=domHarness(),s=status();h.ui.setState(s,{viewName:'tasks'});h.document.ids['ui-locale'].value='en';h.setResponse(async(url,opts)=>{assert.equal(url.pathname,'/api/preferences');assert.deepEqual(JSON.parse(opts.body),{ui_locale:'en'});return {ui_locale:'en',model_calls:0};});await h.document.ids['ui-locale'].onchange();assert.equal(h.requests.length,1);assert.equal(h.ui.getState().project,'WP-test');assert.equal(h.ui.getState().view,'tasks');assert.equal(h.document.ids.instance.value,'I-1');assert.equal(h.document.ids['ui-locale'].value,'en');assert.equal(h.document.ids['dialog-locale'].value,'en');
});

test('report revision binds the clicked report and only its selected edition',async()=>{
  const h=domHarness(),s=status(),posts=[];s.workflow.instances=[{instance_id:'I-1',kind:'SURVEY',status:'PAUSED',name:'Survey'}];h.ui.setState(s);h.setResponse(async(url,opts)=>{if(opts.method==='POST'&&url.pathname.startsWith('/api/action/')){posts.push(JSON.parse(opts.body));return {};}if(url.pathname==='/api/status')return s;return {records:[],reports:[]};});
  h.ui.reportRevision(false,{report_id:'REPORT-original',selected_profiles:['thematic']});assert.deepEqual(h.document.ids['report-profile'].children.map(o=>o.value),['thematic']);h.document.ids['report-reason'].value='Fix the comparison';h.document.ids.instance.value='I-other';await submitDialog(h);assert.equal(posts[0].report_id,'REPORT-original');assert.equal(posts[0].profile,'thematic');assert.equal(posts[0].instance,'I-1');
  h.ui.reportRevision(true,{report_id:'REPORT-original',selected_profiles:['thematic']});h.document.ids['report-reason'].value='Retain history';await submitDialog(h);assert.equal(posts[1].report_id,'REPORT-original');
});
test('Survey freeze sends an explicit question subset with selected knowledge',async()=>{
  const h=domHarness(),s=status(),posts=[];s.workflow.instances=[{instance_id:'I-1',kind:'SURVEY',status:'PAUSED',name:'Survey'}];h.ui.setState(s);h.setResponse(async(url,opts)=>{if(opts.method==='POST'&&url.pathname.startsWith('/api/action/')){posts.push(JSON.parse(opts.body));return {};}if(url.pathname==='/api/workflow-inputs')return {records:[{ref:'KR-one',title:'Result'}],statements:[],sources:[]};if(url.pathname==='/api/survey')return {scope:{questions:['Ready question','Open question']},readiness:{status:'READY'}};if(url.pathname==='/api/status')return s;return {records:[]};});
  await h.ui.surveyFreezeForm();const questions=h.document.ids['survey-freeze-questions'];assert.equal(questions.children.every(o=>o.selected),true);questions.children[1].selected=false;questions.value='Ready question';h.document.ids['survey-freeze-refs'].value='KR-one';await submitDialog(h);assert.deepEqual(posts[0].question_ids,['Ready question']);assert.deepEqual(posts[0].selected_refs,['KR-one']);
});

test('unchanged knowledge commit still updates report controls without replacing unrelated reader',async()=>{
  const h=domHarness(),s=status();s.reports=[{report_id:'REPORT-one',state:'AUTHORING'}];h.ui.setState(s,{viewName:'reports',readSnapshot:s.commit});const original={report_id:'REPORT-one',classification:'RECOVERABLE_ACTIVE_CANDIDATE',state:'AUTHORING',active:true,selected_profiles:['lecture']},card=h.ui.report(original);h.document.ids.content.append(card);const reader=h.document.createElement('details');reader.open=true;reader.textContent='Unchanged proof body';h.document.ids.content.append(reader);h.document.scrollY=840;h.document.ids.content.scrollTop=110;
  const next={...s,reports:[{report_id:'REPORT-one',state:'ABANDONED'}]};h.setResponse(async url=>{if(url.pathname==='/api/progress')return next;if(url.pathname==='/api/reports')return {reports:[{...original,classification:'REPORT_ABANDONED',state:'ABANDONED',active:false}]};throw Error('Unexpected request '+url.pathname);});await h.ui.pollProgress();
  const updated=h.document.ids.content.querySelector('[data-report-id]');assert.notEqual(updated,card);assert.match(updated.textContent,/已放弃报告/);assert.equal(updated.querySelectorAll('button').some(b=>b.textContent==='修订报告'),false);assert.equal(reader.parent,h.document.ids.content);assert.equal(reader.open,true);assert.equal(reader.textContent,'Unchanged proof body');assert.equal(h.document.scrollY,840);assert.equal(h.document.ids.content.scrollTop,110);assert.equal(h.ui.getState().snapshot,s.commit);assert.equal(h.requests.every(r=>r.options.method==='GET'),true);
});

test('pending operation label localizes while its exact raw identity survives locale changes',async()=>{
  const h=domHarness();h.ui.setState(status());await h.ui.operations.storage.claim({key:'original-operation-id',name:'upload-archive',payload:{}});await h.ui.renderOperationRecovery();const banner=h.document.ids['operation-recovery'];assert.match(banner.textContent,/操作 upload-archive · original-operation-id/);assert.doesNotMatch(banner.textContent,/[\uE000\uE001]/);h.ui.applyLocale('en');assert.match(banner.textContent,/Operation upload-archive · original-operation-id/);assert.doesNotMatch(banner.textContent,/[\uE000\uE001]/);assert.equal(h.requests.length,0);assert.equal((await h.ui.operations.current()).key,'original-operation-id');
});
test('a view clicked during project loading never combines a new project with the old instance',async()=>{
  const h=domHarness(),old=status(),next=status();h.ui.setState(old);next.workflow.instances=[{instance_id:'I-new',kind:'TRW',name:'New project workflow',status:'PAUSED'}];next.activity={instance_id:'I-new',workflow_kind:'TRW',instance_status:'PAUSED',active_stages:[],waiting_stages:[],recent_stages:[],stages:[]};let releaseWorkspace;h.setResponse(async url=>{if(url.pathname==='/api/workspace')return new Promise(resolve=>releaseWorkspace=resolve);if(url.pathname==='/api/status'){assert.equal(url.searchParams.get('project'),'WP-new');assert.notEqual(url.searchParams.get('instance'),'I-1');return next;}return {records:[]};});
  h.document.ids.project.value='WP-new';const changing=h.document.ids.project.onchange();assert.equal(h.document.ids.instance.value,'');await h.ui.selectView('tasks');releaseWorkspace({projects:[{key:'WP-new',title:'New'}]});await changing;assert.equal(h.document.ids.instance.value,'I-new');assert.equal(h.ui.getState().project,'WP-new');assert.equal(h.document.ids.error.textContent,'');assert.equal(h.requests.every(r=>new URL(r.url).searchParams.get('instance')!=='I-1'),true);
});
