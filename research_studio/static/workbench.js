/* Local operation receipts survive response loss and reload. No payload deduplication. */
(function () {
'use strict';
const L=typeof module!=='undefined'&&module.exports?require('./i18n.js'):window.PMRS_I18N;
const m=L.message;
function uiError(template){const error=Error(L.render(template));error.uiTemplate=template;return error;}
function workflowStageDescription(stage){return m('stage.'+stage+'.description');}
const scopeKey = s => ['workflow_kind','stage_id','role','purpose'].map(k=>s[k]).join('|');
function amendOverrides(existing, updates, resets=[]) {
  const removed=new Set(resets.map(scopeKey));
  const merged=new Map(existing.filter(x=>!removed.has(scopeKey(x.scope))).map(x=>[scopeKey(x.scope),x]));
  for(const row of updates)merged.set(scopeKey(row.scope),row);
  return [...merged.values()];
}
function stagePresentation(activity, stage) {
  const row=(activity?.stages||[]).find(x=>x.stage_id===stage)||{};
  const active=(activity?.active_stages||[]).includes(stage);
  const waiting=(activity?.waiting_stages||[]).includes(stage);
  return {...row,stage_id:stage,active,waiting,recent:(activity?.recent_stages||[]).includes(stage),
    status:active?'RUNNING':waiting?'WAITING':row.status||'UNVISITED'};
}
function workflowStageLabel(stage) {
  const labels={P0:m("stage.P0.name"),P1:m("stage.P1.name"),P2:m("stage.P2.name"),P3:m("stage.P3.name"),P4:m("stage.P4.name"),P5:m("stage.P5.name"),P6:m("stage.P6.name"),P7:m("stage.P7.name"),P8:m("stage.P8.name"),P9:m("stage.P9.name"),P10:m("stage.P10.name"),P11:m("stage.P11.name"),P12:m("stage.P12.name"),P13:m("stage.P13.name"),P14:m("stage.P14.name"),D0:m("stage.D0.name"),D1:m("stage.D1.name"),D2:m("stage.D2.name"),D3:m("stage.D3.name"),D4:m("stage.D4.name"),D5:m("stage.D5.name"),S0:m("stage.S0.name"),S1:m("stage.S1.name"),S2:m("stage.S2.name"),S3:m("stage.S3.name"),S4:m("stage.S4.name"),S5:m("stage.S5.name"),S6:m("stage.S6.name"),S7:m("stage.S7.name")};
  return labels[stage]||stage;
}
function workflowStagePresentation(activity,kind,stage) {
  if(!activity?.instance_id||activity.workflow_kind!==kind)return {stage_id:stage,known:false,status:'UNKNOWN',active:false,waiting:false,recent:false};
  return {...stagePresentation(activity,stage),known:true};
}
function workflowGraphEdges(workflow,selectedStage=null,showAll=false) {
  const order=new Map((workflow.nodes||[]).map((node,index)=>[node.stage_id,index]));
  const edges=(workflow.edges||[]).filter(edge=>order.has(edge.from)&&order.has(edge.to));
  const selfLoops=edges.filter(edge=>edge.from===edge.to);
  const main=edges.filter(edge=>edge.from!==edge.to&&edge.kind==='forward'&&order.get(edge.to)===order.get(edge.from)+1);
  const related=edges.filter(edge=>edge.from!==edge.to&&!main.includes(edge)&&(edge.from===selectedStage||edge.to===selectedStage));
  return {main,related,selfLoops,visible:showAll?edges.filter(edge=>edge.from!==edge.to):[...main,...related]};
}
class OperationLifecycle {
  constructor(storage, transport, uuid) {this.storage=storage;this.transport=transport;this.uuid=uuid;this.busy=false;}
  async current(){return this.storage.get();}
  async discover() {
    let operation=await this.current();if(operation||!this.transport.discover)return operation;
    const page=await this.transport.discover(),row=page.operations?.[0];if(!row)return null;
    operation={key:row.id,receipt_id:row.id,name:row.name,payload:row.payload||{},workspace_id:page.workspace_id,
      state:row.state,created_at:row.created_at,remote_only:true};
    await this.storage.claim(operation);return this.current();
  }
  async query(operation){return this.transport.query(operation.key,operation);}
  async acknowledge(operation,receipt){if(this.transport.ack)await this.transport.ack(operation,receipt);await this.storage.clear(operation.key);}
  async execute(name,payload) {
    if(this.busy)throw uiError(m("ui.144cc80ad85d"));
    this.busy=true;
    try {
      if(await this.discover())throw uiError(m("ui.3df9951071ae"));
      const operation={key:this.uuid(),name,payload,state:'PENDING',created_at:new Date().toISOString()};
      if(!await this.storage.claim(operation))throw uiError(m("ui.3df9951071ae"));
      return await this.send(operation);
    } finally {this.busy=false;}
  }
  async send(operation) {
    // Any response or acknowledgement loss retains the same key and original payload.
    const result=await this.transport.send(operation);
    // Quit closes the transport; confirm its durable receipt after the next launch.
    if(operation.name==='quit'&&result?.stopped===true)return result;
    if(this.transport.ack){const receipt=await this.query(operation);if(receipt.state!=='COMPLETED')throw uiError(m("ui.adc1a3b8e171"));await this.acknowledge(operation,receipt);}
    else await this.storage.clear(operation.key);
    return result;
  }
  async inspect() {
    const operation=await this.discover();if(!operation)return null;
    return {operation,receipt:await this.query(operation)};
  }
  async recover() {
    const found=await this.inspect();if(!found)return null;
    if(found.receipt.state==='COMPLETED') {
      await this.acknowledge(found.operation,found.receipt);
      return {result:found.receipt.result,operation:found.operation};
    }
    return found;
  }
  async replay() {
    if(this.busy)throw uiError(m("ui.6e3771f50c5b"));this.busy=true;
    try {
      const found=await this.inspect();if(!found)return null;
      if(found.receipt.state==='COMPLETED'){await this.acknowledge(found.operation,found.receipt);return found.receipt.result;}
      if(found.receipt.state!=='NOT_FOUND'||found.operation.remote_only)throw uiError(m("ui.16ea65d30545"));
      return await this.send(found.operation);
    } finally {this.busy=false;}
  }
  async acknowledgeFailure() {
    const found=await this.inspect();
    if(found?.receipt.state!=='FAILED')throw uiError(m("ui.76235d0316ac"));
    await this.acknowledge(found.operation,found.receipt);
  }
}
function indexedOperationStorage(indexedDB,workspaceId='') {
  let connection;const active=workspaceId?'active:'+workspaceId:'active';
  function db(){if(!connection)connection=new Promise((resolve,reject)=>{
    const r=indexedDB.open('pmrs-4.0-business-operations',1);
    r.onupgradeneeded=()=>r.result.createObjectStore('operations');
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(uiError(m("ui.0130e8fbdbdd")));
  });return connection;}
  async function transaction(mode,fn){const d=await db();return new Promise((resolve,reject)=>{
    const tx=d.transaction('operations',mode),store=tx.objectStore('operations');let value;
    tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(uiError(m("ui.57f75468fca9")));tx.onabort=tx.onerror;
    fn(store,x=>{value=x;});
  });}
  return {
    get:()=>transaction('readonly',(s,done)=>{const r=s.get(active);r.onsuccess=()=>done(r.result||null);}),
    claim:value=>transaction('readwrite',(s,done)=>{const r=s.get(active);r.onsuccess=()=>{if(r.result)done(false);else{s.put(value,active);done(true);}};}),
    clear:key=>transaction('readwrite',(s,done)=>{const r=s.get(active);r.onsuccess=()=>{if(r.result?.key===key)s.delete(active);done(true);};})
  };
}
if(typeof module!=='undefined'&&module.exports)module.exports={OperationLifecycle,amendOverrides,scopeKey,stagePresentation,indexedOperationStorage,workflowStageLabel:stage=>L.render(workflowStageLabel(stage)),workflowStagePresentation,workflowGraphEdges};
if(typeof document==='undefined')return;
L.initializeStatic(document);
const $=id=>document.getElementById(id);
let refreshGeneration=0,projectGeneration=0,progressBusy=false,graphDefinition=null,graphSelection=null;
let renderedGraphKind='', latestCommit='';
let navigationScope='',contentProgressFingerprint='',allInstances=[];
let csrf='',workspaceId='',project=localStorage.getItem('pmrs_4_0_project')||'',snapshot='',view='current',nextOffset=null,currentStatus=null,modelPolicy=null;
const kindNames={Context:m("ui.6fc38ef3602f"),Statement:m("ui.ca4f23713721"),Argument:m("ui.e79bae2b9a1d"),Example:m("ui.283ba9f1bcbc"),SourceEvidence:m("ui.c1ef66481c90"),Assessment:m("ui.39c684d9c94b")};
const names={current:m("ui.2385a717b1ce"),candidates:m("ui.69d9cbd04d6b"),frontier:m("ui.a277b84498c2"),sources:m("ui.6ba353b57da0"),history:m("ui.30b2234e9456"),tasks:m("ui.7f06274ac6da"),reports:m("ui.dc121db5a7d2"),diff:m("ui.ee2072057ec5"),survey:m("ui.cb484d48f1fc")};
const states={ACTIVE:m("ui.dfb802238b38"),PAUSED:m("ui.eb0c326b60ae"),ENDED:m("ui.d79b1d0e5c61"),QUEUED:m("ui.341cb8d38169"),RUNNING:m("ui.2b5729f89dac"),WAITING:m("ui.0b2d19d68015"),BLOCKED:m("ui.b7e3e715f18b"),PREPARED:m("ui.8bef70b00989"),RESERVED:m("ui.f56978f61027"),SENT:m("ui.610d1d07317a"),UNKNOWN:m("ui.c14f3724774c"),CAPTURED:m("ui.ac33baebfba1"),SETTLED:m("ui.aaea0fc7d720"),CONSIDERED:m("ui.1af26ccba71e"),COMPLETE:m("ui.f28461bb49c8"),COMPLETED_CURRENT_REPORT:m("ui.9158e8454382"),COORDINATOR_ACTIVE:m("ui.a345bc2849f5"),CANDIDATE:m("ui.605791981ef7"),WAIT:m("ui.e75f04ccfd3c"),UNRESOLVED:m("ui.b702cc107dbe"),SATISFIED_FOR_CONSUMER:m("ui.eca6b448a060")};
const show=x=>states[x]||(L.has('state.'+x)?m('state.'+x):x);
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined){if(['body','excerpt','diagnostic','ref'].includes(cls))n.textContent=String(text);else L.text(n,text);}if(cls)n.className=cls;return n;}
function button(text,fn,cls){const b=el('button',text,cls);b.type='button';b.addEventListener('click',guarded(fn));return b;}
function guarded(fn){return async e=>{if(e)e.preventDefault();const trigger=e?.currentTarget;const lock=trigger?.tagName==='BUTTON'&&!trigger.disabled;if(lock)trigger.disabled=true;L.text($('error'),'');try{await fn(e);}catch(e){L.text($('error'),e.uiTemplate||e.message);if($('dialog').open){let message=$('dialog-error');if(!message){message=el('p',undefined,'error');message.id='dialog-error';message.setAttribute('role','alert');$('dialog-content').prepend(message);}L.text(message,e.uiTemplate||e.message);}}finally{if(lock)trigger.disabled=false;}};}

async function request(path,{method='GET',data,params={},operationKey}={}) {
  const u=new URL(path,location.origin);for(const [k,v] of Object.entries(params))if(v!==undefined&&v!==null&&v!=='')u.searchParams.set(k,v);
  const headers={};if(workspaceId)headers['X-PMRS-Workspace']=workspaceId;if(method==='POST'){headers['Content-Type']='application/json';headers['X-PMRS-CSRF']=csrf;if(operationKey)headers['Idempotency-Key']=operationKey;}
  const r=await fetch(u,{method,headers,body:data===undefined?undefined:JSON.stringify(data),cache:'no-store'});
  const value=await r.json();if(!r.ok){const assistantRequest=path.startsWith('/api/assistant')||path.startsWith('/api/action/assistant-');const key=value.message_key||'error.'+value.error;const template=m(L.has(key)?key:'error.generic')+' ('+(value.error||r.status)+')'+(!assistantRequest&&value.message?'\n'+L.systemMessage(value.message):'')+(!assistantRequest&&value.guidance?'\n'+L.systemMessage(value.guidance):'');const e=uiError(template);e.code=value.error;e.status=r.status;throw e;}return value;
}
const operations=new OperationLifecycle(indexedOperationStorage(window.indexedDB),{
  send:op=>request('/api/action/'+op.name,{method:'POST',data:op.payload,operationKey:op.key}),
  discover:()=>request('/api/operations'),
  query:(key,op)=>request('/api/operation',{params:op?.receipt_id?{id:op.receipt_id}:{key}}),
  ack:(op,receipt)=>request('/api/operation/ack',{method:'POST',data:{id:receipt.operation.id,digest:receipt.digest}})
},()=>crypto.randomUUID());
async function action(name,data={}) {
  try{return await operations.execute(name,{project,instance:$('instance').value,...data});}
  finally{await renderOperationRecovery();if(await operations.current())L.text($('notice'),m("ui.9ad56e71c323"));}
}
async function applyRecovered(result,operation) {
  if(operation?.name?.startsWith('assistant-')&&result?.session_id){initializeAssistantPanel();assistantPanel.open=true;$('project-assistant-panel').hidden=false;await selectAssistantSession(operation.payload.project,result.session_id);return;}
  if(operation?.name==='upload-archive'&&result?.upload_id){showImportConfirmation(result);return;}
  if(!result?.project&&operation?.payload.project&&operation.payload.project!==project)await listProjects(operation.payload.project);
  if(result?.project)await listProjects(result.project);
  else if(project)await openProject();
  if(result?.instance_id){$('instance').value=result.instance_id;await refresh();}
  if(result?.download){const a=el('a',m("ui.dfab872bd7cf"));a.href=result.download;$('notice').replaceChildren(a);}
  else L.text($('notice'),m("ui.7c05b81358f8"));
}
async function renderOperationRecovery(inspected) {
  const box=$('operation-recovery');if(!box)return;
  const op=await operations.current();box.replaceChildren();box.hidden=!op;if(!op)return;
  const identity=el('p',undefined,'ref');identity.append(el('span',m("ui.762059f0790c")),el('span',op.name+' · '+op.key,'ref'));
  box.append(el('strong',m("ui.9293bcaa38ca")),identity,el('p',m("ui.349204d8461a")));
  const receipt=inspected?.operation?.key===op.key?inspected.receipt:null;
  if(receipt)box.append(el('p',m("ui.d889949369df")+receipt.state+(receipt.error?' · '+(typeof receipt.error==='string'?receipt.error:JSON.stringify(receipt.error)):'')));
  box.append(button(m("ui.4fa1f184f9d0"),async()=>{const found=await operations.recover();await renderOperationRecovery(found);if(found?.result!==undefined)await applyRecovered(found.result,found.operation);}));
  if(receipt?.state==='NOT_FOUND'&&!op.remote_only)box.append(button(m("ui.d0d584cacbc3"),async()=>{const original=await operations.current();const result=await operations.replay();await renderOperationRecovery();await applyRecovered(result,original);}));
  if(receipt?.state==='FAILED')box.append(button(m("ui.9e7646c620bc"),async()=>{await operations.acknowledgeFailure();await renderOperationRecovery();L.text($('notice'),m("ui.ba68d4cf7472"));if(project)await openProject();}));
}
function readApi(path,params={}){return request('/api/'+path,{params:{project,instance:$('instance').value,...params}});}
function card(title,ref){const c=el('article',undefined,'card');c.append(el('h3',title));if(ref){const d=el('details');d.append(el('summary',m("ui.07edd6ac944a")),el('div',ref,'ref'));c.append(d);}return c;}
function note(c,text){c.append(el('p',text,'muted'));}
function field(form,label,id,type='text',value=''){const l=el('label',label);const n=el(type==='textarea'?'textarea':type==='select'?'select':'input');n.id=id;n.name=id;if(type!=='textarea'&&type!=='select')n.type=type;n.value=L.render(value);l.append(n);form.append(l);return n;}
function options(select,rows){for(const [value,text] of rows){const o=el('option',text);o.value=value;select.append(o);}}
function dialog(title){$('dialog-locale').value=L.getLocale();L.text($('dialog-title'),title);$('dialog-content').replaceChildren();if(!$('dialog').open)$('dialog').showModal();return $('dialog-content');}
function closeDialog(){$('dialog').close();}
function submit(form,label,fn,disabledAfter=null){const b=el('button',label,'primary');form.append(b);form.addEventListener('submit',guarded(async()=>{b.disabled=true;try{await fn();}finally{b.disabled=disabledAfter?disabledAfter():false;}}));}
async function fileData(file,limitMiB=32){if(!file)return null;if(file.size>limitMiB*1024*1024)throw uiError(m("ui.87756f62e3ff")+limitMiB+m("ui.2d82269461c1"));return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});}
async function typeset(node){if(window.MathJax&&MathJax.typesetPromise){await MathJax.startup.promise;await MathJax.typesetPromise([node]);}}
async function listProjects(selectKey){const d=await request('/api/workspace');$('project').replaceChildren();options($('project'),[['',m("ui.3464e74e1356")],...d.projects.map(p=>[p.key,p.title+(p.synthetic?m("ui.7e2180ae9884"):'')])]);project=selectKey||project;localStorage.setItem('pmrs_4_0_project',project);if(!d.projects.some(p=>p.key===project))project='';$('project').value=project;$('empty-workspace').hidden=!!project;$('workspace').hidden=!project;if(project)await openProject();}
async function openProject(){const selectedProject=project,generation=++projectGeneration;const s=await request('/api/status',{params:{project:selectedProject}});if(generation!==projectGeneration||selectedProject!==project)return;allInstances=s.workflow.instances;const prior=$('instance').value;$('instance').replaceChildren();options($('instance'),[['',m("ui.2b83be55cd42")],...s.workflow.instances.map(i=>[i.instance_id,instanceLabel(i)])]);$('instance').value=s.workflow.instances.some(i=>i.instance_id===prior)?prior:(s.workflow.instances[0]?.instance_id||'');await refresh();}
function requireInstance(){if(!$('instance').value)throw uiError(m("ui.13146a7fa7a9"));}
function record(row){const readScope={project,instance:$('instance').value,commit:snapshot};const c=card(kindNames[row.kind]||row.kind,row.ref);c.append(el('p',row.excerpt,'excerpt'));for(const f of row.result_families||[]){const family=el('details');family.append(el('summary',m("ui.f45c3b8d88b2")+f.label+m("ui.a62251e39ec6")));for(const m of f.members||[])family.append(el('p',(m.display_role||m("ui.6e6d6ddbb7c1"))+' · '+(m.record_ref||m),'ref'));note(family,m("ui.5b185af2235c"));c.append(family);}if(row.kind==='Assessment'){note(c,m("ui.dc2432b030a7"));const assessment=el('details');assessment.append(el('summary',m("ui.3dbfe5c6acb5")),el('pre',JSON.stringify({verdict:row.data.verdict,checked:row.data.checked,unchecked:row.data.unchecked},null,2),'diagnostic'));c.append(assessment);}const checked=new Set(),unchecked=new Set(),supportStates=new Set();const aspects={original_target:m("ui.6643c71db375"),full_argument:m("ui.cef2ef4f998b"),formulation_and_counterevidence:m("ui.5890b99e053a")};for(const b of row.support_boundaries||[]){supportStates.add(show(b.support_state||b.result||m("ui.898f3c720c27")));for(const x of b.checked_scope||[])for(const a of x.aspects||[])checked.add(aspects[a]||a);for(const x of b.not_checked||[])for(const a of x.aspects||[])unchecked.add(aspects[a]||a);}for(const x of supportStates)note(c,m("ui.2204f16b93b8")+x);if(checked.size)note(c,m("ui.d35a7d8c4801")+[...checked].join('、'));if(unchecked.size)note(c,m("ui.f3b9c9210ff5")+[...unchecked].join('、'));if(!(row.support_boundaries||[]).length)note(c,m("ui.be6cab6cb1c8"));for(const u of row.source_uses||[]){note(c,m("ui.285942812cbe")+(u.usage.some(x=>x.usage_mode==='METHOD_INSPIRATION')?m("ui.3de362765cb4"):m("ui.7d586c5e5f13")));}if(row.support_boundaries?.length||row.source_uses?.length){const info=el('details');info.append(el('summary',m("ui.6898b8bc0552")),el('pre',JSON.stringify({support:row.support_boundaries,sources:row.source_uses},null,2),'diagnostic'));c.append(info);}const d=el('details');d.append(el('summary',m("ui.233225fcbcb9")));const body=el('div',undefined,'body');d.append(body);let loaded=false;d.addEventListener('toggle',guarded(async()=>{if(d.open&&!loaded){const r=await readApi('body',{...readScope,ref:row.ref});L.text(body,r.body);loaded=true;await typeset(body);}}));c.append(d);return c;}
function frontier(row){const c=card(show(row.resolution),row.obligation_id);c.append(el('div',row.criterion,'body'));note(c,m("ui.9e34bb6921ad")+show(row.work_state));for(const a of row.attempt_accounts||[])note(c,typeof a.account==='string'?a.account:typeof a==='string'?a:m("ui.00906446d87d"));note(c,row.blockers.length?m("ui.cdb56dff6462"):m("ui.d1e9a437c934"));return c;}
function source(row){const c=card(row.filename||m("ui.6ba353b57da0"),row.source_ref);const sd=row.survey_source_details,ss=row.survey_source_status||{};if(sd){note(c,m('survey.field.version')+': '+sd.version);note(c,show(sd.access_status));for(const limitation of sd.limitations||[])note(c,limitation);}if(typeof row.in_selected_scope==='boolean')note(c,m(row.in_selected_scope?'source.in_scope':'source.shared'));if(ss.withdrawn)note(c,m('source.withdrawn'));if(ss.version_conflict)note(c,m('source.conflict'));if(ss.reason)note(c,ss.reason);if(selectedInstanceRow()?.kind==='SURVEY')c.append(button(m('source.status_title'),()=>sourceStatusForm(row)));if(row.text!==null){const d=el('details');d.append(el('summary',m("ui.57d1248b4f8d")),el('div',row.text,'body'));c.append(d);}else{const a=el('a',m(sd?.access_status==='METADATA_ONLY'?'source.download_metadata':'ui.07ae2eb55573'));a.href='/api/source-file?project='+project+'&instance='+$('instance').value+'&ref='+row.source_ref+'&commit='+snapshot;a.target='_blank';a.rel='noopener';c.append(a);}note(c,m("ui.777a3628efd0")+row.bytes+m("ui.91c3013986af"));return c;}
function report(row){const c=card(row.classification==='REPORT_ABANDONED'?m('report.abandoned') :row.classification==='COMPLETED_CURRENT_REPORT'?m("ui.5e3b9055e108"):m("ui.9302743b4e67"),row.report_id);c.dataset.reportId=row.report_id;const reportProject=project,reportInstance=$('instance').value||row.instance_ids?.[0]||'';for(const profile of row.selected_profiles||Object.keys(row.profiles||{})){const version=row.profiles?.[profile]||{};const target={project:reportProject,instance_id:reportInstance,report_id:row.report_id,profile,revision:version.revision,body_hash:version.raw_body_sha256};c.append(button(m('assistant.discuss_report')+' · '+profile+(version.revision!==undefined?' · '+m('assistant.revision')+' '+version.revision:''),()=>openAssistant(target)));}note(c,m("ui.86344fd28ab4")+show(row.state));for(const x of row.missing_checks||[])note(c,m("ui.c87861444dc1")+x);for(const f of row.failure_history||[])note(c,m("ui.63e4cd0e0fbd")+(f.message||f.code||f.reason||m("ui.6fc2d0fa06da")));for(const gap of row.open_research_requests||[]){note(c,m("ui.ad3eebe6926f")+gap.description);note(c,m("ui.46baf4e1caf2"));}if(row.open_research_requests?.length)c.append(button(m("ui.c3ae027fe415"),async()=>{view='frontier';await refresh();}));for(const d of row.downloads||[]){const a=el('a',d.profile==='lecture'?m("ui.1a59e47c906f"):d.profile==='thematic'?m("ui.15ec25a0a390"):m("ui.8aa416e83bdc"));a.href=d.url;a.target='_blank';a.rel='noopener';c.append(a);}note(c,m("ui.767a4692fe9c"));if(row.active&&$('instance').value){c.append(button(m("ui.d794cb7e9e19"),()=>reportRevision(false,row)),button(m("ui.2c382cda2c8c"),()=>reportRevision(true,row)));}return c;}
function reportRevision(abandon,row){requireInstance();const box=dialog(abandon?m("ui.d7ca85cdf564"):m("ui.d794cb7e9e19"));const f=el('form',undefined,'stack');let profile;const reportId=row.report_id,owner=$('instance').value;
  if(!abandon){profile=field(f,m("ui.f3d6cf15a49a"),'report-profile','select');const names=row.selected_profiles||Object.keys(row.profiles||{}),labels=selectedInstanceRow()?.kind==='SURVEY'?{minimal:m("ui.08543cf39ae5"),thematic:m("ui.268960d94561"),lecture:m("ui.fd14fc2f1c6d")}:{lecture:m("ui.5192200360fd"),minimal:m("ui.76764fb75d57")};options(profile,names.filter(name=>labels[name]).map(name=>[name,labels[name]]));profile.required=true;}
  note(f,reportId,'ref');const reason=field(f,m("ui.31b22ac63611"),'report-reason','textarea');reason.required=true;note(f,m("ui.6ee93b2057dd"));submit(f,abandon?m("ui.ead611c56aee"):m("ui.c8c35b7ed477"),async()=>{await action(abandon?'abandon-report':'revise-report',{instance:owner,report_id:reportId,profile:profile?.value,reason:reason.value});closeDialog();await refresh();});box.append(f);}

function taskRequest(s,t){return (s?.execution?.requests||[]).find(r=>r.request_id===t.request_id);}
function updateTaskCard(c,t,s){
  const r=taskRequest(s,t),label=c.querySelector('[data-request-status]');
  L.text(label,m("ui.5d1da28c2af7")+show(r?.execution_state||'PREPARED')+(r?.unknown_disposition==='ABANDON_UNKNOWN'?m("ui.219d3e031383"):''));
  const controls=c.querySelector('[data-task-actions]'),state=[r?.execution_state,r?.unknown_disposition,r?.fenced].join('|');
  if(controls.dataset.actionState===state)return;
  controls.dataset.actionState=state;controls.replaceChildren();
  if(r?.execution_state==='CAPTURED')controls.append(button(m("ui.642f3015f18d"),async()=>{await action('recover',{instance:t.instance_id,request_id:r.request_id});await refresh();}));
  if(r?.execution_state==='UNKNOWN'&&r?.unknown_disposition!=='ABANDON_UNKNOWN')controls.append(button(m("ui.a1b23d17b798"),()=>reconcile(r.request_id,t.instance_id)));
}
function task(t){
  const assistantContext={project,instance_id:t.instance_id,task_id:t.task_id,request_id:t.request_id};
  const c=card(workflowStageLabel(t.stage_id)+' · '+t.stage_id+' / '+t.role,t.task_id);c.dataset.taskId=t.task_id;
  if(!$('instance').value)note(c,m("ui.fe2493f947e5")+t.instance_id);
  const p=t.model_policy||{};note(c,m("ui.ca6ecc4226f0")+p.model+' · '+p.reasoning_effort+' · '+p.service_tier);
  const label=el('p',undefined,'muted');label.dataset.requestStatus=t.request_id;c.append(label);
  note(c,m("ui.91280e77e813"));c.append(button(m('assistant.ask_issue'),()=>openAssistant(assistantContext)));
  const controls=el('div',undefined,'task-actions');controls.dataset.taskActions=t.task_id;c.append(controls);updateTaskCard(c,t,currentStatus);return c;
}
function pendingDuty(r){const c=card(r.stage_id+' · '+workflowStageLabel(r.stage_id)+' · '+r.role,r.obligation_id);c.dataset.pendingBinding=r.binding_id;note(c,m('plan.pending')+(r.branch_key?' · '+r.branch_key:''));note(c,m('plan.dependency_count')+' '+r.dependencies);c.append(button(m('plan.inspect'),()=>selectView('frontier',{keepGraph:true})),button(m('plan.defer'),()=>deferDutyForm(r)));return c;}
function progressFingerprint(s){return JSON.stringify({tasks:s?.tasks||[],pending_work:s?.pending_work||[],corrections:s?.corrections||[],round_result:s?.round_result||{},requests:s?.execution?.requests||[],reports:s?.reports||[],survey:s?.survey||{},workflow:s?.workflow||{},controls:s?.controls||{}});}
function syncViewSelection(){for(const b of $('tabs').querySelectorAll('button')){const active=b.dataset.view===view;b.classList.toggle('active',active);b.setAttribute('aria-current',active?'page':'false');}L.text($('view-title'),names[view]);}
function clearStageSelection(){graphSelection=null;if(typeof resetWorkflowGraphSelection==='function')resetWorkflowGraphSelection();else{$('stage-detail').replaceChildren();$('stage-detail').hidden=true;}}
async function selectView(next,{stage=null,keepGraph=false}={}){view=next;if(!keepGraph)clearStageSelection();graphSelection=next==='tasks'?stage:null;syncViewSelection();await refresh();}
function candidate(c){const n=card(c.label||m("ui.b5d076fad9ab"),c.statement_ref);n.append(el('div',c.body,'body'));note(n,m("ui.86344fd28ab4")+show(c.candidate_state||m("ui.416c1a9f49fb"))+m("ui.214006610e65"));note(n,m("ui.31f7a60cd744"));for(const r of c.related_records||[]){const d=el('details');d.append(el('summary',(kindNames[r.kind]||r.kind)+' · '+(r.data.verdict||r.data.scope||m("ui.7e9e41bfdc00"))),el('div',r.body,'body'));if(r.data.unchecked?.length)note(d,m("ui.f3b9c9210ff5")+r.data.unchecked.map(x=>x.aspect+' — '+x.reason).join('；'));n.append(d);}const scopes=el('details');scopes.append(el('summary',m("ui.1fed3f05ba83")),el('pre',JSON.stringify({statement_ref:c.statement_ref,comparison_refs:c.comparison_refs,change_axes:c.change_axes,support:c.support_boundaries},null,2),'diagnostic'));n.append(scopes);n.append(button(m("ui.09fd963b09d2"),async()=>{const box=dialog(m("ui.587c2579f429"));const newName=field(box,m("ui.4a59c7047bc5"),'adopt-name','text',c.label||m("ui.b7fcc8179859"));box.append(el('div',c.body,'body'),el('p',m("ui.dc22a47768a9")));box.append(button(m("ui.d81a8e961ea3"),async()=>{if(!newName.value.trim())throw uiError(m("ui.b036c543c664"));const r=await action('handoff',{direction:'TFDW_TO_TRW',name:newName.value,candidate_ref:c.statement_ref,note:"The user selected this exact candidate from its full-text view."});closeDialog();await openProject();$('instance').value=r.instance_id;await refresh();},'primary'));}));return n;}
async function refresh(append=false){syncViewSelection();const scope=project+'|'+$('instance').value;if(scope!==navigationScope){clearStageSelection();navigationScope=scope;if(view==='survey'&&(allInstances.find(i=>i.instance_id===$('instance').value)||selectedInstanceRow())?.kind!=='SURVEY')view='current';syncViewSelection();}if(!project)return;const generation=++refreshGeneration,selectedProject=project,selectedInstance=$('instance').value,selectedView=view;const stale=()=>generation!==refreshGeneration||selectedProject!==project||selectedInstance!==$('instance').value||selectedView!==view;const selectedRead=(path,params={})=>readApi(path,{project:selectedProject,instance:selectedInstance,...params});requireInstanceOptional();if(!append){const latest=await selectedRead('status');if(stale())return;currentStatus=latest;requireInstanceOptional();snapshot=currentStatus.commit;latestCommit=snapshot;contentProgressFingerprint=progressFingerprint(latest);renderProgress(latest);L.text($('snapshot'),m("ui.bca21103166f")+snapshot.slice(0,12));$('content-update').hidden=true;$('content').replaceChildren();nextOffset=null;}
L.text($('view-title'),names[view]);let rows=[];let data;const params={commit:snapshot};const frozenReadScope={project:selectedProject,instance:selectedInstance,commit:snapshot};if(view==='survey'){data=await selectedRead('survey');if(stale())return;rows=[data];renderSurvey(data,$('content'));}else if(view==='tasks'){rows=currentStatus.tasks.filter(t=>!graphSelection||t.stage_id===graphSelection);for(const r of rows)$('content').append(task(r));const pending=(currentStatus.pending_work||[]).filter(t=>!graphSelection||t.stage_id===graphSelection);for(const r of pending){$('content').append(pendingDuty(r));}rows=rows.concat(pending);}else if(view==='candidates'){rows=currentStatus.candidates;for(const r of rows)$('content').append(candidate(r));if($('instance').value&&currentStatus.workflow.instances.some(i=>i.kind==='TRW'))$('content').append(button(m("ui.a3f63564960d"),()=>reformulate()));}else if(view==='diff'){const mission=currentStatus.missions.find(m=>m.mission_id===selectedInstanceRow()?.current_mission_id);if(mission?.input_knowledge_commit){data=await selectedRead('diff',{...params,from:mission.input_knowledge_commit});if(stale())return;rows=[data];const c=card(m("ui.39a6ee0faf5b"));note(c,m("ui.14384da832a4")+data.content_added.length+m("ui.846b9d3de461")+data.content_reused.length+m("ui.631c6278898d")+data.support_changes.length+m("ui.4449aa9fa6f8")+data.support_withdrawals.length);note(c,m("ui.99d5626bccc3"));for(const [label,refs] of [[m("ui.ca827e3e9a64"),data.content_added],[m("ui.0ab5a2478493"),data.content_reused]])for(const ref of refs){const d=el('details');d.append(el('summary',label+' · '+ref.slice(-12)),el('p',ref,'ref'));let loaded=false;d.addEventListener('toggle',guarded(async()=>{if(d.open&&!loaded){const full=await readApi('body',{...frozenReadScope,ref});d.append(el('div',full.body,'body'));loaded=true;await typeset(d);}}));c.append(d);}const scope=el('details');scope.append(el('summary',m("ui.51e2569f82aa")),el('pre',JSON.stringify({changes:data.support_changes,withdrawals:data.support_withdrawals},null,2),'diagnostic'));c.append(scope);$('content').append(c);}}else{data=await selectedRead(selectedView,{...params,query:$('query').value,offset:append?nextOffset:0,limit:20});if(stale())return;rows=data.records||data.obligations||data.sources||data.artifacts||data.reports||[];for(const r of rows)$('content').append(({current:record,frontier,sources:source,history:nativeHistory,reports:report})[view](r));nextOffset=data.next_offset;}if(!rows.length&&!append)$('content').append(el('p',view==='candidates'?m("ui.923fa77b82c9"):m("ui.a9d1c50ac56d"),'empty'));$('more').hidden=nextOffset===undefined||nextOffset===null;await typeset($('content'));}
function requireInstanceOptional(){$('survey-tab').hidden=selectedInstanceRow()?.kind!=='SURVEY';for(const id of ['start-round','plan-work','request-correction','pause','continue','end','request-report','handoff-workflow'])$(id).disabled=!$('instance').value;$('edit-discovery').hidden=selectedInstanceRow()?.kind!=='TFDW'||!!selectedInstanceRow()?.current_mission_id;}
function nativeHistory(r){const c=card(r.title||r.event_type,r.event_id);note(c,m("ui.4a3a525f8169")+r.sequence+' · '+r.event_type+(r.at?' · '+r.at:''));note(c,r.summary||'');note(c,m("ui.9dd84fe5b300")+r.commit);note(c,r.instance_ids?.length?m("ui.daf783c241ee")+r.instance_ids.join('、'):m("ui.578795c650c1"));const d=el('details');d.append(el('summary',m("ui.270246ebdb57")),el('pre',JSON.stringify(r.details||{},null,2),'body'));c.append(d);return c;}
function sourceForm(){const box=dialog(m("ui.4543dcfea3c3"));const f=el('form',undefined,'stack');const file=field(f,m("ui.b955da5396bf"),'source-file','file');const text=field(f,m("ui.933c22020ec8"),'source-text','textarea');submit(f,m("ui.5be20c99dea4"),async()=>{const chosen=file.files[0];await action('add-source',{filename:chosen?.name||L.render(m("ui.e52d8c7f3957")),media_type:chosen?.type||'text/plain',data:await fileData(chosen),text:text.value});closeDialog();$('instance').value='';view='sources';await refresh();});box.append(f);}
function showImportConfirmation(r){if(r.mode!=='restore')throw uiError(m("ui.8915f1167653"));const area=dialog(m("ui.d5465449ca0e"));const labels={format:m("ui.75a5aad7994c"),files:m("ui.b3fa95f830ed"),title:m("ui.7a688306423b"),processes_restored:m("ui.a424525dad15")};for(const [k,v] of Object.entries(r.summary||{}))area.append(el('p',(labels[k]||k)+'：'+(k==='format'||(k==='title'&&v==='原生完整备份')?m("ui.c59d014f56e6"):v)));area.append(el('p',m("ui.4fcab817dbbd")));area.append(button(m("ui.fd84055d148f"),async()=>{const done=await action('restore',{upload_id:r.upload_id});closeDialog();await listProjects(done.project);},'primary'));}
function importForm(){const box=dialog(m("ui.ac4729557de8")),f=el('form',undefined,'stack');const file=field(f,m("ui.2a58c21cbc8f"),'import-file','file');file.accept='.zip';note(f,m("ui.b47bb4ef778b"));submit(f,m("ui.0f9e09d95a23"),async()=>{if(!file.files[0])throw uiError(m("ui.83fbfcf09a9d"));const r=await action('upload-archive',{data:await fileData(file.files[0],128),mode:'restore'});showImportConfirmation(r);});box.append(f);}
async function settings(){const d=await request('/api/settings');modelPolicy=d.policy;const box=dialog(m("ui.34fcf7af27f9"));box.append(el('p',d.client.installed?m("ui.92230489f299")+(d.client.version||m("ui.a8b6c39dcabf")):m("ui.ea87d6730b9b")));box.append(el('p',d.client.authenticated?m("ui.318e4e66e753"):m("ui.82a9a017e318")));const actions=el('div',undefined,'actions');actions.append(button(m("ui.943d1cf39d37"),async()=>{const r=await action('login');L.text($('notice'),r.login_state==='ALREADY_AUTHENTICATED'?m("ui.13fa1f274754"):m("ui.e8a5d8ae01ba"));}),button(m("ui.2e1b7b66ded9"),settings),button(m("ui.f447a13e8775"),async()=>{const r=await action('check-environment');const c=card(m("ui.0d90ab2d28aa"));c.append(el('pre',JSON.stringify(r,null,2),'diagnostic'));box.append(c);}));box.append(actions);const a=el('a',m("ui.2e5457d0d4f9"));a.href='https://developers.openai.com/codex/cli/';a.target='_blank';a.rel='noopener';box.append(a);await environmentSettings(box,d.setup);note(box,m("ui.486a84fcda2d"));const table=el('table');const head=el('tr');for(const t of [m("ui.59eb8d03efea"),m("ui.c47b54e84e79"),m("ui.409a2e016a5a")])head.append(el('th',t));table.append(head);for(const r of d.policy.rules){const tr=el('tr');for(const t of [r.stage_id,r.role,r.call_model?r.reasoning_effort:m("ui.239f2d0f2cdb")])tr.append(el('td',t));table.append(tr);}box.append(table);if(project&&$('instance').value)box.append(button(m("ui.3be8455ab12b"),configureForm));}
function help(){
  const box=dialog(m('guide.title'));box.append(el('p',m('guide.intro')));
  const sections=[['setup',['1','2','3']],['choose',['1','2','3']],['start',['1','4','5','6','2','3']],
    ['observe',['1','2','3','4']],['budget',['1','2','3','4']],['intervene',['1','3','4','5','2']],
    ['trw',['1','input','2','3']],['tfdw',['1','input','2','3']],['survey',['1','input','2','3','4','5']],
    ['reports',['1','2','3']],['trouble',[]],['save',['1','2','3']],['assistant',['1','2','3','diagnose','4','revise','5','6','7','8']]];
  for(const [name,parts] of sections){
    const section=el('details',undefined,'scope');section.dataset.guideSection=name;section.open=name==='setup';
    section.append(el('summary',m('guide.'+name+'.title')));
    for(const part of parts){
      const example=['input','diagnose','revise'].includes(part);const node=el(example?'pre':'p',undefined,example?'body':undefined);
      L.text(node,m('guide.'+name+'.'+part));section.append(node);
    }
    if(name==='trouble'){
      const table=el('table'),head=el('tr');for(const col of ['state','meaning','next'])head.append(el('th',m('guide.trouble.'+col)));table.append(head);
      for(const row of ['dependencies','resources','budget','context','capture','unknown','receipt','report']){
        const tr=el('tr');for(const col of ['state','meaning','next'])tr.append(el('td',m('guide.trouble.'+row+'.'+col)));table.append(tr);
      }section.append(table);
    }box.append(section);
  }
  box.append(el('p',m('guide.demo.note')),button(m("ui.3340dae33d4f"),()=>createForm('TRW',true)),button(m("ui.92d9e1bc4720"),()=>createForm('TFDW',true)));
}

// The assistant has a pinned project/session, independent of workbench selectors.
const assistantPanel={open:false,project:'',session_id:'',generation:0,busy:false,data:null,offset:0};
function assistantReportState(action){return action?.report_result_state||action?.result?.state||(['WAITING_REPORT_BUDGET','BLOCKED','RESOURCE_WAIT'].includes(action?.state)?action.state:action?.report_state||action?.state||action?.status);}
function assistantReportChecks(parent,action){for(const [profile,check] of Object.entries(action?.checks||{})){const parts=[profile,m('assistant.semantic')+': '+(check.semantic||m('assistant.not_checked'))];if(check.requirements?.verdict)parts.push(m('assistant.requirements_verdict')+': '+check.requirements.verdict);parts.push(m('assistant.rendered')+': '+m(check.rendered?'assistant.yes':'assistant.no'));if(check.reviewed_pages!==undefined||check.total_pages!==undefined)parts.push(m('assistant.visual_pages')+': '+(check.reviewed_pages??'?')+'/'+(check.total_pages??'?'));note(parent,parts.join(' · '));}}
function assistantReportComplete(action){return ['COMPLETE','COMPLETED_CURRENT_REPORT'].includes(assistantReportState(action));}
function assistantStateLabel(state){return L.has('assistant.state.'+state)?m('assistant.state.'+state):show(state||'READY');}
function assistantStorageKey(key){return 'pmrs_4_0_assistant_session:'+workspaceId+':'+key;}
function assistantFailure(error){const code=typeof error==='string'?error:error?.code;if(code&&L.has('error.'+code))return m('error.'+code)+' ('+code+')';return m('assistant.failure_help')+(code?' ('+code+')':'');}
function assistantError(error){const area=$('assistant-error');if(area)L.text(area,assistantFailure(error));}
function assistantBusy(data){return (data.turns||[]).some(t=>['QUEUED','PREPARED','RUNNING','RESOURCE_WAIT'].includes(t.state)||['PREPARED','RESERVED','SENT','UNKNOWN','CAPTURED'].includes(t.execution_state))||(data.jobs||[]).some(j=>['QUEUED','RUNNING'].includes(j.state));}
function initializeAssistantPanel(){
  const box=$('project-assistant-panel');if(box.dataset.initialized)return;box.dataset.initialized='true';
  const heading=el('div',undefined,'view-heading');heading.append(el('h2',m('assistant.title')),button(m('assistant.close'),()=>{assistantPanel.open=false;box.hidden=true;}));box.append(heading);
  const context=el('div',undefined,'scope');context.id='assistant-context';box.append(context);
  note(box,m('assistant.scope_notice'));note(box,m('assistant.close_notice'));
  const tools=el('div',undefined,'actions');tools.append(button(m('assistant.new_conversation'),()=>openAssistant({project:assistantPanel.project,instance_id:assistantPanel.data?.context?.instance_id||''},true)),button(m('assistant.refresh'),()=>loadAssistant()),button(m('assistant.evidence'),()=>assistantEvidence()),button(m('assistant.download_evidence'),()=>assistantEvidence(true)),button(m('assistant.settings'),settings),button(m('assistant.guide'),()=>{help();const section=$('dialog-content').querySelector('[data-guide-section="assistant"]');if(section)section.open=true;}));box.append(tools);
  const navigation=el('div',undefined,'actions');const previous=button(m('assistant.previous'),async()=>{assistantPanel.offset=Math.max(0,assistantPanel.offset-30);await loadAssistant();});previous.id='assistant-previous';previous.hidden=true;const latest=button(m('assistant.latest'),async()=>{assistantPanel.offset=Math.max(0,Math.floor(((assistantPanel.data?.message_count||1)-1)/30)*30);await loadAssistant();});navigation.append(previous,latest);box.append(navigation);
  const history=field(box,m('assistant.history'),'assistant-history','select');history.onchange=guarded(async()=>{if(history.value)await selectAssistantSession(assistantPanel.project,history.value);});
  const status=el('div',undefined,'notice');status.id='assistant-status';status.setAttribute('role','status');box.append(status);
  const budget=el('div',undefined,'scope');budget.id='assistant-budget';box.append(budget);
  const grant=el('form',undefined,'stack');const calls=field(grant,m('assistant.additional_calls'),'assistant-calls','number','3');calls.min='1';calls.max='1000';calls.required=true;note(grant,m('assistant.budget_help'));
  submit(grant,m('assistant.authorize'),async()=>{const pinned={project:assistantPanel.project,session_id:assistantPanel.session_id,generation:assistantPanel.generation};if(!pinned.session_id)throw uiError(m('assistant.missing_session'));await action('assistant-authorize',{project:pinned.project,instance:'',session_id:pinned.session_id,max_calls:Number(calls.value)});if(pinned.generation===assistantPanel.generation)await loadAssistant();});box.append(grant);
  const requirements=el('details');requirements.id='assistant-requirements';requirements.append(el('summary',m('assistant.requirements')));box.append(requirements);
  const messages=el('div');messages.id='assistant-messages';messages.setAttribute('aria-live','polite');box.append(messages);
  const turns=el('div');turns.id='assistant-turns';box.append(turns);
  const more=button(m('assistant.more'),async()=>{const next=assistantPanel.data?.next_offset;if(next!==undefined&&next!==null){assistantPanel.offset=next;await loadAssistant();}});more.id='assistant-more';more.hidden=true;box.append(more);
  const evidence=el('details');evidence.id='assistant-evidence';evidence.hidden=true;evidence.append(el('summary',m('assistant.evidence')));box.append(evidence);
  const form=el('form',undefined,'stack');const message=field(form,m('assistant.message'),'assistant-message','textarea');message.required=true;message.rows=5;
  const reportCalls=field(form,m('assistant.report_calls'),'assistant-report-calls','number');reportCalls.min='1';reportCalls.max='1000';note(form,m('assistant.report_budget_help'));note(form,m('assistant.send_help'));
  submit(form,m('assistant.send'),async()=>{
    const pinned={project:assistantPanel.project,session_id:assistantPanel.session_id,generation:assistantPanel.generation};if(!pinned.session_id)throw uiError(m('assistant.missing_session'));
    const text=message.value;if(!text.trim())throw uiError(m('assistant.empty_message'));
    const payload={project:pinned.project,instance:'',session_id:pinned.session_id,text};if(reportCalls.value!=='')payload.report_calls=Number(reportCalls.value);
    try{const result=await action('assistant-send',payload);if(pinned.generation===assistantPanel.generation){if(message.value===text)message.value='';reportCalls.value='';assistantPanel.offset=0;await loadAssistant();if(assistantPanel.data?.message_count>30){assistantPanel.offset=Math.floor((assistantPanel.data.message_count-1)/30)*30;await loadAssistant();}}return result;}catch(error){assistantError(error);throw error;}
  },()=>assistantBusy(assistantPanel.data||{})||(assistantPanel.data?.budget?.remaining??0)<=0);const send=form.querySelector('button');send.id='assistant-send';box.append(form);
  const error=el('p',undefined,'error');error.id='assistant-error';error.setAttribute('role','alert');box.append(error);
  note(box,m('assistant.operation_help'));
}
async function openAssistant(context={},fresh=false){
  if(!project&&!context.project)throw uiError(m('assistant.open_project_required'));
  initializeAssistantPanel();assistantPanel.open=true;$('project-assistant-panel').hidden=false;
  const key=context.project||project,owner=context.instance_id===undefined?$('instance').value:context.instance_id;
  const generation=++assistantPanel.generation;assistantPanel.project=key;assistantPanel.session_id='';assistantPanel.offset=0;assistantPanel.data=null;
  L.text($('assistant-error'),'');$('assistant-status').replaceChildren(el('strong',m('assistant.state.QUEUED')));$('assistant-messages').replaceChildren();delete $('assistant-messages').dataset.fingerprint;$('assistant-turns').replaceChildren();$('assistant-send').disabled=true;
  // The general entry restores the last conversation; explicit issue/report entries pin a new exact context.
  const explicit=!!(context.task_id||context.request_id||context.report_id),saved=!fresh&&!explicit&&localStorage.getItem(assistantStorageKey(key));
  if(saved){await selectAssistantSession(key,saved,generation);return;}
  const payload={project:key,instance:owner||'',...context};delete payload.instance_id;
  const result=await action('assistant-open',payload);
  if(generation!==assistantPanel.generation)return;
  await selectAssistantSession(key,result.session_id,generation);
  $('project-assistant-panel').scrollIntoView({block:'start',behavior:'smooth'});
}
async function selectAssistantSession(key,session,generation){
  if(generation===undefined)generation=++assistantPanel.generation;
  assistantPanel.project=key;assistantPanel.session_id=session;assistantPanel.offset=0;
  localStorage.setItem(assistantStorageKey(key),session);await loadAssistant(generation);
}
async function loadAssistant(expected=assistantPanel.generation){
  if(!assistantPanel.session_id)return;const key=assistantPanel.project,session=assistantPanel.session_id;
  try{const data=await request('/api/assistant',{params:{project:key,session_id:session,offset:assistantPanel.offset,limit:30}});
    if(expected!==assistantPanel.generation||key!==assistantPanel.project||session!==assistantPanel.session_id)return;
    assistantPanel.data=data;L.text($('assistant-error'),'');renderAssistant(data);
  }catch(error){if(expected!==assistantPanel.generation)return;assistantError(error);$('assistant-status').replaceChildren(el('p',m('assistant.read_error')));throw error;}
}
function assistantReportLinks(parent,action){
  if(!action)return;const links=[];
  for(const version of action.versions||[]){const row=el('div',undefined,'scope');row.append(el('strong',version.profile+' · '+m('assistant.revision')+' '+version.revision+' · '+m(version.current?'assistant.current_version':'assistant.past_version')));note(row,m('assistant.semantic')+': '+(version.semantic_status||m('assistant.not_checked'))+' · '+m('assistant.rendered')+': '+m(version.rendered?'assistant.yes':'assistant.no')+' · '+m('assistant.visual_pages')+': '+(version.visual_pages??0));if(typeof version.url==='string'&&version.url.startsWith('/api/report-file?')){const a=el('a',m(version.current?'assistant.new_report':'assistant.old_report'));a.href=version.url;a.target='_blank';a.rel='noopener';row.append(a);}parent.append(row);}
  if(action.old_url)links.push({url:action.old_url,label:m('assistant.old_report')});
  if(action.new_url)links.push({url:action.new_url,label:m('assistant.new_report')});
  for(const entry of action.links||[])links.push({url:entry.url,label:entry.label||m(entry.kind==='old'?'assistant.old_report':'assistant.new_report')});
  for(const entry of links){if(typeof entry.url!=='string'||!entry.url.startsWith('/api/report-file?'))continue;const a=el('a',entry.label);a.href=entry.url;a.target='_blank';a.rel='noopener';parent.append(a);}
}
function renderAssistant(data){
  const ctx=data.context||{},box=$('assistant-context');box.replaceChildren();
  box.append(el('strong',m('assistant.scope')),el('p',(data.project_title||assistantPanel.project)+' · '+(ctx.instance_name||ctx.instance_id||m('assistant.project_scope'))));
  const model=data.model||{};note(box,model.model==='gpt-6-astra'&&model.reasoning_effort==='xhigh'?m('assistant.model'):(model.model||'?')+' · '+(model.reasoning_effort||'?'));
  for(const [key,label] of [['task_id','task'],['request_id','request'],['report_id','report']])if(ctx[key])note(box,m('assistant.'+label)+': '+ctx[key]);
  if(ctx.profile)note(box,ctx.profile+' · '+m('assistant.revision')+' '+(ctx.revision??'?'));
  const sections=ctx.sections||[];if(sections.length){const detail=el('details');detail.append(el('summary',m('assistant.report')));for(const section of sections)detail.append(el('p',typeof section==='string'?section:(section.number!==undefined?section.number+'. ':'')+(section.title||section.name||section.selector||section.id||'')));box.append(detail);}
  assistantReportLinks(box,{versions:data.report_versions||ctx.versions});
  const history=$('assistant-history'),selected=assistantPanel.session_id;history.replaceChildren();options(history,[['',m('assistant.select_history')],...(data.sessions||[]).map(s=>[s.session_id,(s.title||s.context?.profile||s.context?.instance_id||s.session_id)+(s.created_at?' · '+s.created_at:'')])]);history.value=selected;
  const turns=data.turns||[],latest=turns[turns.length-1],job=(data.jobs||[]).find(j=>j.turn_id===latest?.turn_id),state=latest?.execution_state==='UNKNOWN'?'UNKNOWN':assistantReportState(latest?.action)||(['QUEUED','RUNNING','REPORT_RUNNING','WAITING_RESOURCE','WAITING_REPORT_BUDGET','BLOCKED'].includes(job?.state)?job.state:latest?.state||'READY');
  const status=$('assistant-status');status.replaceChildren(el('strong',assistantStateLabel(state)));if(latest?.evidence_at)note(status,m('assistant.evidence_time')+': '+latest.evidence_at);
  if(latest?.action){assistantReportChecks(status,latest.action);if(typeof latest.action.change_summary?.summary==='string')status.append(el('p',latest.action.change_summary.summary,'body'));}
  if(latest?.request_id)note(status,m('assistant.request')+': '+latest.request_id+' · '+assistantStateLabel(latest.execution_state||latest.state));
  if(state==='UNKNOWN'||latest?.execution_state==='UNKNOWN')note(status,m('assistant.unknown_help'));
  const budget=$('assistant-budget'),allowance=data.budget||{};budget.replaceChildren(el('strong',m('assistant.authorization')),el('p',m('assistant.remaining')+': '+(allowance.remaining??0)+' · '+m('assistant.consumed')+': '+(allowance.used??0)));
  if(data.report_budget)note(budget,m('assistant.report_budget')+': '+(data.report_budget.remaining??data.report_budget.remaining_calls??m('assistant.state.NEEDS_BUDGET')));
  const requirements=$('assistant-requirements');requirements.replaceChildren(el('summary',m('assistant.requirements')));for(const row of data.effective_requirements||[])requirements.append(el('p',row.text,'body'));requirements.hidden=!(data.effective_requirements||[]).length;if(data.message_count>30)note(requirements,m('assistant.requirements_page'));
  const messages=$('assistant-messages'),stamp=JSON.stringify(data.messages||[]);if(messages.dataset.fingerprint!==stamp){messages.dataset.fingerprint=stamp;messages.replaceChildren();for(const row of data.messages||[]){const card=el('article',undefined,'card');card.dataset.messageId=row.message_id;card.append(el('h3',m(row.role==='user'?'assistant.user':'assistant.reply')),el('div',row.text||'','body'));if(row.created_at)note(card,row.created_at);const structured=row.structured||{};for(const [key,label] of [['facts','facts'],['inferences','inferences'],['unknowns','unknowns'],['advice','suggestions']])if(structured[key]?.length){const detail=el('details');detail.append(el('summary',m('assistant.'+label)));for(const item of structured[key]){detail.append(el('p',typeof item==='string'?item:item.text,'body'));if(item.evidence_ids?.length)note(detail,item.evidence_ids.join(' · '));}card.append(detail);}messages.append(card);}if(!data.messages?.length)messages.append(el('p',m('assistant.empty')));}
  const actions=$('assistant-turns');actions.replaceChildren();for(const turn of turns){const item=el('details');item.append(el('summary',assistantStateLabel(assistantReportState(turn.action)||turn.state)+(turn.created_at?' · '+turn.created_at:'')));note(item,m('assistant.original_operation')+': '+(turn.operation_id||turn.turn_id));if(turn.request_id)note(item,m('assistant.request')+': '+turn.request_id);if(turn.error)note(item,assistantFailure(turn.error));
    const action=turn.action;if(action){note(item,m('assistant.report_processing')+': '+assistantStateLabel(assistantReportState(action)));if(action.error)note(item,assistantFailure(action.error));if(action.change_summary){const detail=el('details');detail.append(el('summary',m('assistant.change_summary')),el('pre',typeof action.change_summary==='string'?action.change_summary:JSON.stringify(action.change_summary,null,2),'diagnostic'));item.append(detail);}if(action.previous_revision!==undefined||action.old_revision!==undefined||action.revision!==undefined)note(item,m('assistant.revision')+': '+(action.previous_revision??action.old_revision??'?')+' → '+(action.revision??'?'));for(const warning of action.unmet_requirements||[])note(item,typeof warning==='string'?warning:warning.text||warning.reason);if(action.checks){assistantReportChecks(item,action);const check=el('details');check.append(el('summary',m('assistant.report_checks')),el('pre',JSON.stringify(action.checks,null,2),'diagnostic'));item.append(check);}assistantReportLinks(item,action);if(!assistantReportComplete(action))note(item,m('assistant.report_not_complete'));}
    if(['CAPTURED','RESOURCE_WAIT','REPORT_WAITING','NEEDS_BUDGET'].includes(turn.state)||turn.execution_state==='CAPTURED'||['REPORT_BUDGET_REQUIRED','BUDGET_EXHAUSTED','ASSISTANT_REPORT_BUDGET_REQUIRED'].includes(turn.error?.code)||['NEEDS_BUDGET','WAITING_REPORT_BUDGET'].includes(turn.action?.state)||turn.action?.error==='REPORT_BUDGET_REQUIRED'){const key=assistantPanel.project,session=assistantPanel.session_id,generation=assistantPanel.generation;item.append(button(m(turn.execution_state==='CAPTURED'||turn.state==='CAPTURED'?'assistant.recover':'assistant.resume'),async()=>{await actionAssistantRecovery(key,session,turn.turn_id);if(generation===assistantPanel.generation)await loadAssistant();}));}
    actions.append(item);
  }
  $('assistant-send').disabled=assistantBusy(data)||(allowance.remaining??0)<=0;
  $('assistant-previous').hidden=assistantPanel.offset===0;
  $('assistant-more').hidden=data.next_offset===undefined||data.next_offset===null;
}
async function actionAssistantRecovery(key,session,turn){const payload={project:key,instance:'',session_id:session,turn_id:turn};const field=$('assistant-report-calls');if(field.value!=='')payload.report_calls=Number(field.value);const result=await action('assistant-recover',payload);field.value='';return result;}
async function assistantEvidence(download=false){
  const key=assistantPanel.project,session=assistantPanel.session_id,generation=assistantPanel.generation;if(!session)throw uiError(m('assistant.missing_session'));
  const data=await request('/api/assistant-evidence',{params:{project:key,session_id:session}});if(generation!==assistantPanel.generation)return;
  const area=$('assistant-evidence');area.hidden=false;area.open=true;area.replaceChildren(el('summary',m('assistant.evidence')),el('p',m('assistant.evidence_time')+': '+(data.collected_at||'')),el('pre',data.summary_text||L.render(m('assistant.evidence_empty')),'body'));note(area,m('assistant.evidence_help'));
  if(download&&data.summary_text){const blob=new Blob([data.summary_text],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='PMRS-diagnostic-summary.txt';a.click();URL.revokeObjectURL(url);}
}
async function pollAssistant(){if(!assistantPanel.open||assistantPanel.busy||!assistantPanel.session_id)return;assistantPanel.busy=true;try{await loadAssistant();}catch(error){/* Last known messages remain visible; no action is replayed. */}finally{assistantPanel.busy=false;}}

function selectedInstanceRow(){return currentStatus?.workflow.instances.find(x=>x.instance_id===$('instance').value);}
function instanceLabel(i){return (i.name||i.display_name||i.title||i.target_title||m("ui.b8eb45bed72d"))+(i.object_text?' · '+i.object_text.replace(/\s+/g,' ').slice(0,70):'')+' · '+i.kind+' · '+show(i.status)+' · '+i.instance_id.slice(-6);}
function discoveryFields(form,prefix,{phenomenon='',background='',axes='',sources=[],initialRefs={}}={}) {
  const group=el('fieldset',undefined,'stack');group.append(el('legend',m("ui.007c900220ef")));const inputs={};
  for(const [key,label,value,placeholder] of [
    ['phenomenon',m("ui.11fa360d1929"),phenomenon,m("ui.e443c0bc683e")],
    ['immutable_background',m("ui.19f80652e36b"),background,m("ui.672a972c5f33")],
    ['allowed_axes',m("ui.5532055288c6"),axes,m("ui.2bcaf922f4ed")]
  ]) {
    const mode=field(group,label+m("ui.21098f151237"),prefix+'-'+key+'-source','select');options(mode,[['text',m("ui.11e41254f9e5")],...sources.map(source=>[source.source_ref,m("ui.4a9700599b2f")+source.title])]);
    const text=field(group,label,prefix+'-'+key,'textarea',value);L.attribute(text,'placeholder',placeholder);
    const download=el('a',m("ui.bfc044a1d501"));download.target='_blank';download.rel='noopener';download.hidden=true;group.append(download);
    const update=()=>{text.disabled=mode.value!=='text';download.hidden=!text.disabled;if(text.disabled)download.href='/api/source-file?'+new URLSearchParams({project,ref:mode.value});};mode.onchange=update;
    if(initialRefs[key+'_ref']&&sources.some(source=>source.source_ref===initialRefs[key+'_ref']))mode.value=initialRefs[key+'_ref'];update();inputs[key]={mode,text};
  }
  const draft=field(group,m("ui.2333914ef114"),prefix+'-draft','checkbox');
  note(group,m("ui.5df6d951b007"));form.append(group);
  return {group,value(){const scope={};for(const [key,{mode,text}] of Object.entries(inputs)){if(mode.value==='text')scope[key]=text.value;else scope[key+'_ref']=mode.value;if(!draft.checked&&mode.value==='text'&&!text.value.trim())throw uiError(m("ui.a5ed68f2c391"));}return scope;},draft:()=>draft.checked};
}
function createForm(kind='TRW',demo=false){
  if(kind==='SURVEY')return surveyCreateForm();
  const box=dialog(demo?m("ui.dda36107ffe1"):m("ui.01c84c54121e")),f=el('form',undefined,'stack');
  const title=field(f,m("ui.867698fb7b0c"),'create-title','text',demo?m("ui.146d439f8fec")+(kind==='TRW'?m("ui.aa2bfb72e817"):m("ui.3102840a3a99")):'');title.required=true;
  const name=field(f,m("ui.90d6e5264dbd"),'create-name','text',kind==='TRW'?m("ui.9f6f44361950"):m("ui.4d6f3b2e3df8"));name.required=true;
  const k=field(f,m("ui.07465e359c61"),'create-kind','select');options(k,[['TRW',m("ui.e51242cffa0d")],['TFDW',m("ui.cb060acba3fd")]]);k.value=kind;
  const target=el('fieldset',undefined,'stack');target.append(el('legend',m("ui.0ea59770d0ac")));
  const text=field(target,m("ui.8293238f4612"),'create-text','textarea',demo?'For every integer n, n + 0 = n.':'');L.attribute(text,'placeholder',m("ui.e24c46615d28"));
  const file=field(target,m("ui.aaf7ce343ee5"),'create-file','file');file.accept='.txt,.md,.tex';f.append(target);
  const discovery=discoveryFields(f,'create-discovery',{phenomenon:demo?'Observe positive definite real symmetric 2 by 2 matrices and their eigenvalues.':'',background:demo?'Real symmetric 2 by 2 matrices; preserve the meanings of positive definiteness and real eigenvalues.':'',axes:demo?'Explore necessary or sufficient relationships between positive definiteness and positive eigenvalues, using positive, negative and unknown examples.':''});
  const update=()=>{target.hidden=k.value!=='TRW';discovery.group.hidden=k.value!=='TFDW';};k.onchange=update;update();
  note(f,demo?m("ui.431c09cbed6c"):m("ui.10ed58201e74"));
  submit(f,demo?m("ui.c3b3bd32e066"):m("ui.43d7d2b51d75"),async()=>{const payload={title:title.value,name:name.value,kind:k.value};if(k.value==='TFDW'){payload.discovery_scope=discovery.value();payload.text=payload.discovery_scope.phenomenon;payload.draft=discovery.draft();}else{if(!text.value.trim()&&!file.files[0])throw uiError(m("ui.804b4d141650"));payload.text=text.value;payload.data=await fileData(file.files[0]);}const r=await action(demo?'example':'create',payload);closeDialog();await listProjects(r.project);if(demo)await startForm();});box.append(f);
}
async function workflowInputs(){const result={statements:[],records:[],sources:[]};let offset=0;do{const page=await readApi('workflow-inputs',{offset,limit:100});result.statements.push(...page.statements);result.records.push(...(page.records||page.statements||[]));result.sources.push(...page.sources);offset=page.next_offset;}while(offset!==null&&offset!==undefined);return result;}
async function newWorkflowForm(){
  const inputs=await workflowInputs(),box=dialog(m("ui.0a1562dbb3f8")),f=el('form',undefined,'stack');
  const name=field(f,m("ui.2a32b8e07d5f"),'workflow-name');name.required=true;
  const kind=field(f,m("ui.07465e359c61"),'workflow-kind','select');options(kind,[['TRW',m("ui.c2a3603c77ad")],['TFDW',m("ui.63a9a0acb77c")],['SURVEY',m("ui.158b86e1bb36")]]);
  const targetBox=el('fieldset',undefined,'stack');targetBox.append(el('legend',m("ui.3d11110664be")));
  const target=field(targetBox,m("ui.666fa205212d"),'workflow-target','select');options(target,[['',m("ui.d98ada42e309")],...inputs.statements.map(s=>[s.ref,s.title||s.body.slice(0,100)])]);
  const body=field(targetBox,m("ui.15aef2e9bd24"),'workflow-target-text','textarea');const preview=el('div',undefined,'body');targetBox.append(preview);target.onchange=()=>{body.hidden=!!target.value;L.text(preview,inputs.statements.find(x=>x.ref===target.value)?.body||'');};f.append(targetBox);
  const discovery=discoveryFields(f,'workflow-discovery',{sources:inputs.sources});const survey=surveyScopeFields(f,'workflow-survey',inputs);kind.onchange=()=>{for(const [group,selected] of [[survey.group,kind.value==='SURVEY'],[targetBox,kind.value==='TRW'],[discovery.group,kind.value==='TFDW']]){group.hidden=!selected;group.disabled=!selected;}};kind.onchange();
  note(f,m("ui.b3c10221ab66"));
  submit(f,m("ui.e22c9fc782bd"),async()=>{const payload={kind:kind.value,name:name.value};if(kind.value==='TRW'){if(target.value)payload.target_ref=target.value;else{if(!body.value.trim())throw uiError(m("ui.000107343b5a"));payload.target_text=body.value;}}else if(kind.value==='SURVEY'){payload.survey_scope=survey.value();}else{payload.discovery_scope=discovery.value();payload.draft=discovery.draft();}const r=await action('new-workflow',payload);closeDialog();await openProject();$('instance').value=r.instance_id;graphSelection=null;await refresh();});box.append(f);
}
async function discoveryConfigForm(){
  requireInstance();const inputs=await workflowInputs(),box=dialog(m("ui.5e07b265083d")),f=el('form',undefined,'stack');
  const instance=selectedInstanceRow(),scope={...(instance?.discovery_scope||{})};if(!scope.phenomenon_ref&&instance?.discovery_brief_ref)scope.phenomenon_ref=instance.discovery_brief_ref;
  const bodyFor=ref=>inputs.sources.find(s=>s.source_ref===ref)?.body||'';
  const fields=discoveryFields(f,'edit-discovery',{phenomenon:bodyFor(scope.phenomenon_ref),background:bodyFor(scope.immutable_background_ref),axes:bodyFor(scope.allowed_axes_ref),sources:inputs.sources,initialRefs:scope});
  note(f,m("ui.826c2943011c"));
  submit(f,m("ui.917d993d794f"),async()=>{await action('configure-discovery',{discovery_scope:fields.value()});closeDialog();await refresh();});box.append(f);
}
async function policyEditor(parent,{kind,existing=[],prefix='policy'}={}) {
  if(!modelPolicy)modelPolicy=(await request('/api/settings')).policy;
  const details=el('details');details.append(el('summary',m("ui.e4041c15a7c6")));parent.append(details);
  const area=el('div',undefined,'stack');details.append(area);
  const rules=modelPolicy.rules.filter(r=>r.call_model&&r.workflow_kind===kind);
  const stage=field(area,m("ui.59eb8d03efea"),prefix+'-stage','select');options(stage,[...new Set(rules.map(x=>x.stage_id))].map(x=>[x,x]));
  const role=field(area,m("ui.c47b54e84e79"),prefix+'-role','select'),purpose=field(area,m("ui.3496ec610fdb"),prefix+'-purpose','select');
  const model=field(area,m("ui.c98e118e0a43"),prefix+'-model','text','gpt-6-astra');
  const effort=field(area,m("ui.c8c14507b2d3"),prefix+'-effort','select');options(effort,['low','medium','high','xhigh','max'].map(x=>[x,x]));
  const tier=field(area,m("ui.292b1337e98b"),prefix+'-tier','select');options(tier,[['default','default'],['priority','priority']]);
  const explanation=el('p',undefined,'muted'),list=el('div',undefined,'override-list');area.append(explanation,list);
  let changes=[],resets=[];
  const scope=()=>({workflow_kind:kind,stage_id:stage.value,role:role.value,purpose:purpose.value});
  const merged=()=>amendOverrides(existing,changes,resets);
  function showRows(){list.replaceChildren();for(const item of merged())list.append(el('p',item.scope.stage_id+' / '+item.scope.role+' / '+item.scope.purpose+' → '+item.model+' · '+item.reasoning_effort+' · '+item.service_tier));if(!merged().length)list.append(el('p',m("ui.a31072b7ee97")));}
  function selection(){const row=rules.find(x=>x.stage_id===stage.value&&x.role===role.value),exception=modelPolicy.purpose_exceptions.find(x=>x.stage_id===stage.value&&x.role===role.value&&x.purpose===purpose.value);const baseEffort=purpose.value==='LAYOUT_ONLY'?'high':exception?.reasoning_effort||row.reasoning_effort;const override=merged().find(x=>scopeKey(x.scope)===scopeKey(scope()));model.value=override?.model||row.model;effort.value=override?.reasoning_effort||baseEffort;tier.value=override?.service_tier||row.service_tier;L.text(explanation,m("ui.baaec726d38d")+row.model+' · '+baseEffort+' · '+row.service_tier+(override?m("ui.039eb8f65928"):'。'));}
  function purposes(){purpose.replaceChildren();const uses=[['DEFAULT',m("ui.fa24d13f5a23")],...modelPolicy.purpose_exceptions.filter(x=>x.stage_id===stage.value&&x.role===role.value).map(x=>[x.purpose,x.purpose])];if(role.value.startsWith('REPORT_'))uses.push(['CONTENT',m("ui.cde63c6e590d")],['LAYOUT_ONLY',m("ui.fc596981ce36")]);if(stage.value==='D0')uses.push(['BRIEF_ORGANIZATION',m("ui.1f286e5088bb")]);options(purpose,uses);selection();}
  function roles(){role.replaceChildren();options(role,rules.filter(x=>x.stage_id===stage.value).map(x=>[x.role,x.role]));purposes();}
  stage.onchange=roles;role.onchange=purposes;purpose.onchange=selection;roles();showRows();
  area.append(button(m("ui.1c5e28dc5334"),()=>{const row={explicit:true,scope:scope(),model:model.value.trim(),reasoning_effort:effort.value,service_tier:tier.value};if(!row.model)throw uiError(m("ui.cd51931f73c6"));changes=amendOverrides(changes,[row]);resets=resets.filter(x=>scopeKey(x)!==scopeKey(row.scope));showRows();selection();}),button(m("ui.461ec4124a51"),()=>{const current=scope();changes=changes.filter(x=>scopeKey(x.scope)!==scopeKey(current));resets=resets.filter(x=>scopeKey(x)!==scopeKey(current));resets.push(current);showRows();selection();}));
  note(area,m("ui.ac5474b14bda"));
  return {value:()=>changes,resetScopes:()=>resets};
}
async function startForm(){
  requireInstance();const box=dialog(m("ui.3a89783cb297")),f=el('form',undefined,'stack');
  const intent=field(f,m("ui.901fb478ebe7"),'round-intent','textarea',m("ui.0cdebd2e64bf"));intent.required=true;
  const calls=field(f,m("ui.fefbc4bb7421"),'round-calls','number','12');calls.min='1';calls.max='1000';calls.required=true;
  const workers=field(f,m("ui.34908be5e604"),'round-workers','number',String(currentStatus?.budget?.max_workers||1));workers.min='1';workers.max='8';workers.required=true;
  note(f,m('concurrency.policy'));
  note(f,m('round.automatic_help'));
  const inputs=await workflowInputs(),materials=field(f,m('round.materials'),'round-materials','select');materials.multiple=true;materials.size=5;
  options(materials,inputs.sources.map(x=>[x.source_ref,x.filename||x.title||x.source_ref]));
  const records=field(f,m('round.knowledge'),'round-knowledge','select');records.multiple=true;records.size=4;
  options(records,inputs.records.map(x=>[x.ref,x.title||x.body?.slice(0,120)||x.ref]));
  note(f,m('round.materials_help'));
  const reportFirst=field(f,m("ui.a8ae720f4b7f"),'round-report-first','checkbox');
  const editor=await policyEditor(f,{kind:selectedInstanceRow().kind,prefix:'round-policy'});
  note(f,currentStatus.synthetic?m("ui.dbc2cb6b59ea"):m("ui.5b906d308872"));
  note(f,m("ui.342da98883d3"));
  submit(f,m("ui.4d266e31b24b"),async()=>{await action('start',{intent:intent.value,max_calls:Number(calls.value),max_workers:Number(workers.value),report_first:reportFirst.checked,model_overrides:editor.value(),source_refs:[...materials.selectedOptions].map(x=>x.value),selected_refs:[...records.selectedOptions].map(x=>x.value)});closeDialog();await openProject();});box.append(f);
}
function extendBudgetForm(){
  requireInstance();const box=dialog(m('round.extend')),f=el('form',undefined,'stack');
  const calls=field(f,m('round.extra_calls'),'extra-calls','number');calls.min='1';calls.max='1000';calls.required=true;
  const reason=field(f,m('round.extra_reason'),'extra-reason','textarea');reason.required=true;
  note(f,m('round.extra_help'));submit(f,m('round.authorize_only'),async()=>{await action('extend-budget',{added_calls:Number(calls.value),reason:reason.value});closeDialog();await refresh();});box.append(f);
}
function correctionForm(){
  requireInstance();const box=dialog(m('correction.button')),f=el('form',undefined,'stack');
  const duty=field(f,m('correction.affected'),'correction-duty','select');
  options(duty,(currentStatus.correctable_work||[]).map(r=>[r.binding_id,r.stage_id+' · '+r.role+' · '+r.description]));
  const instruction=field(f,m('correction.instruction'),'correction-instruction','textarea');instruction.required=true;
  const success=field(f,m('correction.success'),'correction-success','textarea');success.required=true;
  note(f,m('correction.help'));submit(f,m('correction.save'),async()=>{await action('request-correction',{binding_id:duty.value,instruction:instruction.value,success_criterion:success.value});closeDialog();view='tasks';await refresh();});box.append(f);
}
function renderRoundResult(s){
  const r=s.round_result;if(!r||r.state==='NOT_STARTED')return;
  const box=el('section',undefined,'scope');box.append(el('h3',m('round.result')),el('strong',m('round.state.'+r.state)));
  note(box,m('round.new_records')+': '+(r.produced_refs?.length||0)+' · '+m('round.open_duties')+': '+(r.unfinished_bindings?.length||0)+' · '+m('round.unperformed_duties')+': '+(r.unperformed_bindings?.length||0));
  if(r.state==='READY_FOR_DECISION'||r.state==='BUDGET_EXHAUSTED'||r.state==='HUMAN_INPUT_REQUIRED')note(box,m('round.human_next'));
  for(const reason of r.autoflow?.waiting_human||[])note(box,L.has('round.reason.'+reason)?m('round.reason.'+reason):L.systemMessage(reason));
  for(const reason of r.waiting_reasons||[])note(box,L.has('round.reason.'+reason.code)?m('round.reason.'+reason.code):L.systemMessage(reason.reason||reason.code));
  for(const failure of r.failures||[])note(box,L.systemMessage(failure.error?.message||failure.error?.code||failure.state));
  for(const ref of r.produced_refs||[])box.append(button(ref.slice(-12),async()=>{const full=await readApi('body',{ref,commit:latestCommit||snapshot});const d=dialog(m('round.result'));d.append(el('div',full.body,'body'));await typeset(d);}));
  if(r.remaining_calls===0&&r.state!=='ENDED')box.append(button(m('round.extend'),extendBudgetForm));
  box.append(button(m('round.open_questions'),()=>selectView('frontier',{keepGraph:true})));
  for(const c of s.corrections||[]){const row=el('div',undefined,'scope');row.append(el('strong',m(c.complete?'correction.complete':c.assigned?'correction.assigned':'correction.recorded')),el('p',c.instruction),el('p',m('correction.success')+': '+c.success_criterion));box.append(row);}
  $('activity').append(box);
}
function deferDutyForm(duty){const box=dialog(m('plan.defer')),f=el('form',undefined,'stack');note(f,m('plan.defer_help'));const reason=field(f,m('plan.defer_reason'),'defer-reason','textarea');reason.required=true;submit(f,m('plan.defer'),async()=>{await action('defer-work',{binding_id:duty.binding_id,reason:reason.value});closeDialog();await refresh();});box.append(f);}
async function workPlanForm(){
  requireInstance();const inputs=await workflowInputs(),kind=selectedInstanceRow().kind;
  if(!modelPolicy)modelPolicy=(await request('/api/settings')).policy;
  const rules=modelPolicy.rules.filter(r=>r.call_model&&r.workflow_kind===kind&&!r.role.startsWith('REPORT_'));
  const box=dialog(m('plan.title')),f=el('form',undefined,'stack');
  const intent=field(f,m('plan.intent'),'plan-intent','textarea');intent.required=true;
  const mission=selectedInstanceRow().current_mission_id;
  const append=field(f,m('plan.append'),'plan-append','checkbox');append.disabled=!mission||kind==='SURVEY';
  const calls=field(f,m('ui.fefbc4bb7421'),'plan-calls','number','8');calls.min='1';calls.max='1000';calls.required=true;
  const workers=field(f,m('ui.34908be5e604'),'plan-workers','number',String(currentStatus?.budget?.max_workers||1));workers.min='1';workers.max='8';
  append.onchange=()=>{calls.disabled=append.checked;workers.disabled=append.checked;};
  note(f,m('concurrency.policy'));note(f,m('plan.help'));
  const rows=el('div',undefined,'stack');f.append(rows);let duties=[],ordinal=0;
  const selected=select=>[...select.selectedOptions].map(o=>o.value);
  function links(){for(const d of duties){const old=selected(d.dependencies);d.dependencies.replaceChildren();options(d.dependencies,duties.filter(x=>x!==d).map(x=>[x.key,x.key+' · '+(x.intent.value||workflowStageLabel(x.stage.value))]));for(const o of d.dependencies.options)o.selected=old.includes(o.value);}}
  function add(){
    if(duties.length>=32)throw uiError(m('plan.limit'));
    const key='work-'+(++ordinal),row=el('fieldset',undefined,'stack');row.append(el('legend',key));
    const stage=field(row,m('ui.2612dc4025d2'),key+'-stage','select');options(stage,[...new Set(rules.map(x=>x.stage_id))].map(x=>[x,x+' · '+workflowStageLabel(x)]));
    const role=field(row,m('plan.role'),key+'-role','select');
    const intent=field(row,m('plan.duty'),key+'-intent','textarea');intent.required=true;
    const criterion=field(row,m('plan.criterion'),key+'-criterion','textarea');
    const framework=field(row,m('plan.framework'),key+'-framework','textarea');
    const refs=field(row,m('ui.62c6fd021260'),key+'-refs','select');refs.multiple=true;refs.size=3;options(refs,(inputs.records||inputs.statements||[]).map(x=>[x.ref,x.title||x.ref]));
    const sources=field(row,m('ui.bbbeea89fa50'),key+'-sources','select');sources.multiple=true;sources.size=3;options(sources,(inputs.sources||[]).map(x=>[x.source_ref,x.title||x.source_ref]));
    const dependencies=field(row,m('plan.dependencies'),key+'-dependencies','select');dependencies.multiple=true;
    const required=field(row,m('plan.required'),key+'-required','checkbox');required.checked=true;
    const d={key,row,stage,role,intent,criterion,framework,refs,sources,dependencies,required};duties.push(d);
    function roles(){role.replaceChildren();options(role,rules.filter(x=>x.stage_id===stage.value).map(x=>[x.role,x.role]));links();}
    stage.onchange=roles;intent.onchange=links;roles();
    row.append(button(m('survey.remove'),()=>{duties=duties.filter(x=>x!==d);row.remove();links();}));rows.append(row);links();
  }
  f.append(button(m('plan.add'),add));add();
  const run=field(f,m('plan.run'),'plan-run','checkbox');note(f,m('plan.save_only'));
  submit(f,m('plan.save'),async()=>{
    const items=duties.map(d=>({key:d.key,stage:d.stage.value,role:d.role.value,intent:d.intent.value,
      ...(d.criterion.value.trim()?{success_criterion:d.criterion.value}:{}),
      ...(d.framework.value.trim()?{framework_scope:d.framework.value}:{}),
      input_refs:selected(d.refs),source_refs:selected(d.sources),depends_on:selected(d.dependencies),required:d.required.checked,
      ...(d.stage.value==='P7'&&d.role.value==='SYNTHESIS'?{synthesis_of:duties.filter(x=>x.stage.value==='P7'&&['LEARN','DIRECT'].includes(x.role.value)).map(x=>x.key)}:{})}));
    if(!items.length)throw uiError(m('plan.empty'));
    await action('plan-work',{intent:intent.value,items,max_calls:Number(calls.value),max_workers:Number(workers.value),run:run.checked,...(append.checked?{mission_id:mission}:{})});closeDialog();view='tasks';await openProject();
  });box.append(f);
}
async function configureForm(){
  requireInstance();const box=dialog(m("ui.3be8455ab12b")),f=el('form',undefined,'stack'),instance=selectedInstanceRow();
  const mission=currentStatus.missions.find(m=>m.mission_id===instance.current_mission_id);
  if(!mission){box.append(el('p',m("ui.313aa1134692")));return;}
  const grant=currentStatus.budget.grants.find(g=>g.budget_grant_id===mission.budget_grant_id);const existing=currentStatus.model_configuration?.model_overrides||grant?.execution_policy?.model_overrides||[];
  const editor=await policyEditor(f,{kind:instance.kind,existing,prefix:'config'});
  submit(f,m("ui.b399c3019248"),async()=>{await action('configure',{model_overrides:editor.value(),reset_scopes:editor.resetScopes()});closeDialog();view='tasks';graphSelection=null;await refresh();});box.append(f);
}
async function reconcile(rid,instance=$('instance').value){
  const inputs=await workflowInputs(),box=dialog(m("ui.df28e3e7785c")),f=el('form',undefined,'stack');
  note(f,m("ui.b9fd00df1be2"));
  const choice=field(f,m("ui.9e09420bc999"),'reconcile-choice','select');options(choice,[['ABANDON_UNKNOWN',m("ui.27ca9fb333a0")],['CONFIRMED_NOT_SENT',m("ui.6e6a1aaec0ed")]]);
  const evidence=field(f,m("ui.2a52602145e7"),'reconcile-evidence','select');options(evidence,[['',m("ui.e7bca25f652b")],...inputs.sources.map(s=>[s.source_ref,s.title||s.source_ref])]);
  const description=el('div',undefined,'body');f.append(description);
  evidence.onchange=()=>{L.text(description,inputs.sources.find(s=>s.source_ref===evidence.value)?.body||'');};
  const reason=field(f,m("ui.f61181f69507"),'reconcile-note','textarea');reason.required=true;
  choice.onchange=()=>{evidence.disabled=choice.value!=='CONFIRMED_NOT_SENT';evidence.required=!evidence.disabled;description.hidden=evidence.disabled;};choice.onchange();
  note(f,m("ui.884664b51620"));
  submit(f,m("ui.a587596e4331"),async()=>{if(choice.value==='CONFIRMED_NOT_SENT'&&!evidence.value)throw uiError(m("ui.ef8ad6d0e93f"));const data={instance,request_id:rid,disposition:choice.value,note:reason.value};if(choice.value==='CONFIRMED_NOT_SENT')data.not_sent_evidence_ref=evidence.value;await action('reconcile',data);closeDialog();await refresh();});box.append(f);
}
async function reformulate(){
  requireInstance();if(selectedInstanceRow()?.kind==='SURVEY')return surveyHandoffForm();if(selectedInstanceRow()?.kind==='TFDW'){view='candidates';graphSelection=null;return refresh();}
  const inputs=await workflowInputs(),box=dialog(m("ui.2e81e3e2add6")),f=el('form',undefined,'stack');
  const name=field(f,m("ui.7d1175080ef6"),'handoff-name','text',m("ui.852e9c63245d"));name.required=true;
  const fields=discoveryFields(f,'handoff-discovery',{sources:inputs.sources});
  note(f,m("ui.6187112aeda7"));
  submit(f,m("ui.9f4218381fcf"),async()=>{const r=await action('handoff',{direction:'TRW_TO_TFDW',name:name.value,discovery_scope:fields.value(),draft:fields.draft(),note:"The user explicitly selected a formulation-discovery handoff from the original target."});closeDialog();await openProject();$('instance').value=r.instance_id;graphSelection=null;await refresh();});box.append(f);
}
function renderProgress(s){
  latestCommit=s.commit||latestCommit;L.text($('project-title'),s.title||currentStatus?.title||m("ui.f3cc0471a810"));$('demo-banner').hidden=!(s.synthetic??currentStatus?.synthetic);
  const remaining=s.budget.remaining_calls,instances=s.workflow.instances||[];
  $('status').replaceChildren();
  for(const [label,value,small] of [
    [m("ui.2ce2847cbc47"),s.mathematical.records+m("ui.1d453ee99329"),m("ui.d3bc559795e7")],
    [m("ui.f9c60d15b268"),instances.map(i=>show(i.status)).join('、')||m("ui.2b83be55cd42"),m("ui.a1a380456b65")],
    [m("ui.97cf231639da"),s.execution.running_processes+m("ui.c128a7cd63b1"),m("ui.c5dcd67e5206")],
    [m("ui.41ae8cf96233"),s.execution.unknown+m("ui.2216504d0bdc"),m("ui.0946204cc25c")],
    [m("ui.6cf2531ab111"),remaining===null?m("ui.5b21759c2e23"):Math.max(0,remaining)+m("ui.91204b75194f"),m("ui.6dd02aad1be8")+(s.budget.project_remaining_calls??m("ui.5b21759c2e23"))+m("ui.ed0ddabb4bb1")]
  ]){const n=el('div',undefined,'stat');n.append(el('small',label),el('strong',value),el('small',small));$('status').append(n);}
  $('activity').replaceChildren();
  note($('activity'),m('concurrency.current')+' '+(s.budget.max_workers||1)+' / 8 · '+m('concurrency.host')+' 10');
  const jobs=s.project_jobs||s.jobs||[];
  for(const j of jobs){const n=el('div',undefined,'scope');const iid=j.initiated_by_instance_id||j.instance_id;const instance=instances.find(i=>i.instance_id===iid);n.append(el('strong',m("ui.9daf9db078f2")+show(j.state)),el('p',m("ui.27214cc67d7a")+(instance?instanceLabel(instance):iid||m("ui.87a6f4d53d19"))));note(n,L.systemMessage(j.message)||show(j.result?.state)||m("ui.3dbee941199f"));$('activity').append(n);}
  if(!jobs.length)$('activity').append(el('p',m("ui.fa90450f77f9"),'muted'));
  renderRoundResult(s);
  renderWorkflowGraph(s.activity);
  const changed=contentProgressFingerprint&&progressFingerprint(s)!==contentProgressFingerprint;if(snapshot&&(latestCommit!==snapshot||changed)){$('content-update').hidden=false;L.text($('content-update-label'),(latestCommit!==snapshot?m("ui.3ef1465f0035"):m("ui.8cb7018f21b3"))+m("ui.8c221d54a252")+snapshot.slice(0,12)+'。');}
}
async function pollProgress(){
  if(!project||progressBusy)return;progressBusy=true;
  const selectedProject=project,selectedInstance=$('instance').value,generation=refreshGeneration;
  try{const s=await request('/api/progress',{params:{project:selectedProject,instance:selectedInstance}});
    if(project!==selectedProject||$('instance').value!==selectedInstance||generation!==refreshGeneration)return;
    // Readers keep their DOM, open details, scroll position and frozen commit.
    currentStatus={...currentStatus,...s,candidates:s.candidates||currentStatus?.candidates||[]};renderProgress(s);requireInstanceOptional();
    if(view==='tasks')patchTaskStates(s);if(view==='reports')await patchReportStates(s);if(view==='survey')patchSurveyState(s);
  }catch(e){L.text($('notice'),m("ui.780b696d7ec1")+e.message+m("ui.9440aa28a04f"));}
  finally{progressBusy=false;}
}
function patchTaskStates(s){
  const content=$('content'),wanted=(s.tasks||[]).filter(t=>!graphSelection||t.stage_id===graphSelection);
  const cards=new Map([...content.querySelectorAll('[data-task-id]')].map(c=>[c.dataset.taskId,c]));
  const ids=new Set(wanted.map(t=>t.task_id));
  for(const [id,c] of cards)if(!ids.has(id))c.remove();
  for(const t of wanted){const c=cards.get(t.task_id);if(c)updateTaskCard(c,t,s);else content.append(task(t));}
  const pending=(s.pending_work||[]).filter(t=>!graphSelection||t.stage_id===graphSelection),existing=new Map([...content.querySelectorAll('[data-pending-binding]')].map(c=>[c.dataset.pendingBinding,c]));
  for(const [id,c] of existing)if(!pending.some(r=>r.binding_id===id))c.remove();
  for(const r of pending)if(!existing.has(r.binding_id))content.append(pendingDuty(r));
  if(wanted.length||pending.length){for(const empty of content.querySelectorAll('.empty'))empty.remove();}
  else if(!content.querySelector('.empty'))content.append(el('p',m("ui.98421493ae54"),'empty'));
  contentProgressFingerprint=progressFingerprint(s);
  if(latestCommit===snapshot)$('content-update').hidden=true;
}
const workflowGraphView={scope:null,mode:null,focus:null,allPaths:false,definition:null,observers:[],detailKey:null};
function workflowGraphScope(){return project+'|'+($('instance').value||'');}
function selectedGraphActivity(activity){return activity?.instance_id&&activity.instance_id===$('instance').value?activity:null;}
function resetWorkflowGraphSelection(){
  workflowGraphView.focus=null;workflowGraphView.detailKey=null;
  const box=$('stage-detail');box.hidden=true;box.replaceChildren();
  for(const node of $('workflow-graph').querySelectorAll('[data-stage]')){node.classList.remove('selected-stage');node.setAttribute('aria-pressed','false');}
  for(const block of $('workflow-graph').querySelectorAll('.workflow-map')){const workflow=graphDefinition?.workflows.find(row=>row.kind===block.dataset.kind);if(workflow)drawWorkflowEdges(block,workflow);}
}
function selectGraphStage(kind,stage){
  const workflow=graphDefinition?.workflows.find(row=>row.kind===kind);
  if(!workflow?.nodes.some(node=>node.stage_id===stage))return;
  workflowGraphView.focus={kind,stage,scope:workflowGraphScope()};workflowGraphView.detailKey=null;
  if(workflowGraphView.mode!=='overview')workflowGraphView.mode=kind;
  renderWorkflowGraph(currentStatus?.activity);
}
function graphStateLabel(state){return !state.known?m("ui.93e474c68ed5"):state.active?m("ui.3b7e27cb4379"):state.waiting?m("ui.8fb3a3261b43"):state.recent?m("ui.98f6424d7d29"):state.status==='VISITED'?m("ui.f696de34bf23"):m("ui.a7ed7a3a69ef");}
function graphEdgeLabel(edge){return edge.from===edge.to?m("ui.69a10944fda6"):({forward:m("ui.a251448a845f"),return:m("ui.0c1f44e64da5"),early_delivery:m("ui.16053f320194")}[edge.kind]||edge.kind);}
function redrawWorkflowGraphs(){
  const draw=()=>{for(const block of $('workflow-graph').querySelectorAll('.workflow-map')){const row=graphDefinition.workflows.find(w=>w.kind===block.dataset.kind);if(row&&!block.hidden)drawWorkflowEdges(block,row);}};
  if(typeof requestAnimationFrame==='function')requestAnimationFrame(draw);else draw();
}
function drawWorkflowEdges(block,workflow){
  if(typeof document.createElementNS!=='function'||block.hidden)return;
  const nodes=block.querySelector('.stage-nodes'),bounds=nodes.getBoundingClientRect();if(!bounds.width||!bounds.height)return;
  const focus=workflowGraphView.focus?.kind===workflow.kind?workflowGraphView.focus.stage:null;
  const paths=workflowGraphEdges(workflow,focus,workflowGraphView.allPaths);
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('class','stage-wires');svg.setAttribute('viewBox','0 0 '+bounds.width+' '+bounds.height);svg.setAttribute('aria-hidden','true');
  const defs=document.createElementNS(ns,'defs');
  for(const [kind,color] of [['main','#8b9b90'],['forward','#527a69'],['return','#aa7934'],['early_delivery','#627fad']]){
    const marker=document.createElementNS(ns,'marker');marker.setAttribute('id','arrow-'+workflow.kind+'-'+kind);marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','9');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','5');marker.setAttribute('markerHeight','5');marker.setAttribute('orient','auto');const arrow=document.createElementNS(ns,'path');arrow.setAttribute('d','M 0 0 L 10 5 L 0 10 z');arrow.setAttribute('fill',color);marker.append(arrow);defs.append(marker);
  }
  svg.append(defs);const buttons=[...nodes.querySelectorAll('[data-stage]')];
  for(const [index,edge] of paths.visible.entries()){
    const from=buttons.find(b=>b.dataset.stage===edge.from),to=buttons.find(b=>b.dataset.stage===edge.to);if(!from||!to)continue;
    const a=from.getBoundingClientRect(),b=to.getBoundingClientRect();const main=paths.main.includes(edge);let d;
    if(main&&Math.abs(a.top-b.top)<5){const right=b.left>a.left;const x1=(right?a.right:a.left)-bounds.left,x2=(right?b.left:b.right)-bounds.left,y=a.top+a.height/2-bounds.top;d='M '+x1+' '+y+' H '+x2;}
    else if(main){const down=b.top>a.top,x1=a.left+a.width/2-bounds.left,x2=b.left+b.width/2-bounds.left,y1=(down?a.bottom:a.top)-bounds.top,y2=(down?b.top:b.bottom)-bounds.top,mid=(y1+y2)/2;d='M '+x1+' '+y1+' C '+x1+' '+mid+' '+x2+' '+mid+' '+x2+' '+y2;}
    else if(Math.abs(a.top-b.top)<5){const x1=a.left+a.width/2-bounds.left,x2=b.left+b.width/2-bounds.left,y1=a.top-bounds.top,y2=b.top-bounds.top,lane=Math.max(6,Math.min(y1,y2)-10-(index%3)*5);d='M '+x1+' '+y1+' V '+lane+' H '+x2+' V '+y2;}
    else {const down=b.top>a.top,x1=a.left+a.width/2-bounds.left,x2=b.left+b.width/2-bounds.left,y1=(down?a.bottom:a.top)-bounds.top,y2=(down?b.top:b.bottom)-bounds.top,gap=12+(index%3)*4,lane=index%2?bounds.width-7-(index%3)*5:7+(index%3)*5;d='M '+x1+' '+y1+' V '+(y1+(down?gap:-gap))+' H '+lane+' V '+(y2+(down?-gap:gap))+' H '+x2+' V '+y2;}
    const path=document.createElementNS(ns,'path');path.setAttribute('d',d);path.setAttribute('class','stage-wire '+(main?'main':edge.kind)+(edge.from===focus||edge.to===focus?' related':''));path.setAttribute('marker-end','url(#arrow-'+workflow.kind+'-'+(main?'main':edge.kind)+')');svg.append(path);
  }
  const old=nodes.querySelector('.stage-wires');if(old)old.remove();nodes.prepend(svg);
}
function buildWorkflowGraph(container){
  for(const observer of workflowGraphView.observers)observer.disconnect();workflowGraphView.observers=[];
  container.replaceChildren();workflowGraphView.definition=graphDefinition;
  const toolbar=el('div',undefined,'graph-toolbar'),switches=el('div',undefined,'graph-switches');switches.setAttribute('role','group');L.attribute(switches,'aria-label',m("ui.724ed941262f"));
  for(const [kind,label] of [['TRW',m("ui.c2a3603c77ad")],['TFDW',m("ui.63a9a0acb77c")],['SURVEY',m("ui.158b86e1bb36")],['overview',m("ui.8854d59539fd")]]){const b=button(label,()=>{workflowGraphView.mode=kind;resetWorkflowGraphSelection();renderWorkflowGraph(currentStatus?.activity);},'graph-switch');b.dataset.graphMode=kind;switches.append(b);}toolbar.append(switches);
  const all=button(m("ui.6a2f17496e5a"),()=>{workflowGraphView.allPaths=!workflowGraphView.allPaths;renderWorkflowGraph(currentStatus?.activity);},'graph-path-toggle');all.dataset.graphPaths='all';all.setAttribute('aria-pressed','false');toolbar.append(all);container.append(toolbar);
  const legend=el('p',m("ui.199750025f17"),'graph-legend');container.append(legend);
  const maps=el('div',undefined,'workflow-maps');
  for(const workflow of graphDefinition.workflows){
    const block=el('section',undefined,'workflow-map');block.dataset.kind=workflow.kind;
    const header=el('div',undefined,'workflow-map-heading');header.append(el('h3',workflow.kind==='TRW'?m("ui.28f68e286af4"):workflow.kind==='TFDW'?m("ui.ad603c8fc085"):m("ui.9dd6dbcdb820")));const context=el('span',undefined,'graph-context');context.dataset.graphContext=workflow.kind;header.append(context);block.append(header);
    const viewport=el('div',undefined,'graph-viewport'),nodes=el('div',undefined,'stage-nodes');nodes.dataset.columns=workflow.kind==='TRW'?'5':workflow.kind==='SURVEY'?'4':'3';const columns=workflow.kind==='TRW'?5:workflow.kind==='SURVEY'?4:3;
    for(const [index,stage] of workflow.nodes.entries()){
      const b=button('',()=>selectGraphStage(workflow.kind,stage.stage_id),'stage-node');b.dataset.stage=stage.stage_id;b.dataset.kind=workflow.kind;
      const row=Math.floor(index/columns),column=row%2?columns-index%columns:index%columns+1;b.style.gridRow=String(row+1);b.style.gridColumn=String(column);
      const heading=el('span',undefined,'stage-node-heading');heading.append(el('strong',stage.stage_id),el('span',workflowStageLabel(stage.stage_id)));b.append(heading);
      const state=el('small',m("ui.93e474c68ed5"));state.dataset.stageState=stage.stage_id;b.append(state);
      if((workflow.edges||[]).some(edge=>edge.from===stage.stage_id&&edge.to===stage.stage_id)){const loop=el('span','↻','stage-iteration');L.attribute(loop,'title',m("ui.984e25155d2e"));L.attribute(loop,'aria-label',m("ui.5f8342a5df94"));b.append(loop);}
      L.attribute(b,'title',workflowStageLabel(stage.stage_id));nodes.append(b);
    }
    viewport.append(nodes);block.append(viewport);maps.append(block);
    if(typeof ResizeObserver==='function'){const observer=new ResizeObserver(()=>drawWorkflowEdges(block,workflow));observer.observe(nodes);workflowGraphView.observers.push(observer);}
  }
  container.append(maps);
  const links=el('details',undefined,'graph-registered-links');links.append(el('summary',m("ui.a8871abbeee5")));links.append(el('div',undefined,'edge-list'));container.append(links);
}
function renderWorkflowGraph(activity){
  if(!graphDefinition)return;const scope=workflowGraphScope(),bound=selectedGraphActivity(activity),container=$('workflow-graph');
  if(workflowGraphView.scope!==scope){workflowGraphView.scope=scope;workflowGraphView.mode=bound?.workflow_kind||selectedInstanceRow()?.kind||'overview';workflowGraphView.allPaths=false;resetWorkflowGraphSelection();}
  if(workflowGraphView.focus?.scope!==scope)workflowGraphView.focus=null;
  if(workflowGraphView.definition!==graphDefinition||!container.childNodes.length)buildWorkflowGraph(container);
  container.classList.toggle('graph-overview-mode',workflowGraphView.mode==='overview');
  for(const b of container.querySelectorAll('[data-graph-mode]')){const selected=b.dataset.graphMode===workflowGraphView.mode;b.setAttribute('aria-pressed',String(selected));b.classList.toggle('selected',selected);}
  const toggle=container.querySelector('[data-graph-paths]');toggle.setAttribute('aria-pressed',String(workflowGraphView.allPaths));L.text(toggle,workflowGraphView.allPaths?m("ui.32749151a9c8"):m("ui.6a2f17496e5a"));
  for(const block of container.querySelectorAll('.workflow-map')){
    const known=bound?.workflow_kind===block.dataset.kind;block.hidden=workflowGraphView.mode!=='overview'&&workflowGraphView.mode!==block.dataset.kind;block.classList.toggle('selected-workflow',known);block.classList.toggle('structure-preview',!known);L.text(block.querySelector('.graph-context'),known?(bound.name||m("ui.5e96c8ea4820"))+' · '+bound.instance_id.slice(-6)+' · '+show(bound.instance_status):m("ui.066fff0630eb"));
  }
  for(const b of container.querySelectorAll('[data-stage]')){
    const state=workflowStagePresentation(bound,b.dataset.kind,b.dataset.stage),selected=workflowGraphView.focus?.kind===b.dataset.kind&&workflowGraphView.focus?.stage===b.dataset.stage;
    for(const [name,value] of [['running',state.active],['waiting',state.waiting],['visited',state.known&&state.status==='VISITED'],['recent',state.recent],['unknown-state',!state.known],['selected-stage',selected]])b.classList.toggle(name,value);
    b.setAttribute('aria-pressed',String(selected));L.text(b.querySelector('small'),graphStateLabel(state));L.attribute(b,'aria-label',b.dataset.stage+' '+workflowStageLabel(b.dataset.stage)+'; '+graphStateLabel(state));
  }
  const list=container.querySelector('.edge-list');const edgeSignature=JSON.stringify([workflowGraphView.mode,workflowGraphView.focus?.kind,workflowGraphView.focus?.stage,workflowGraphView.allPaths]);
  if(list.dataset.signature!==edgeSignature){
    list.replaceChildren();list.dataset.signature=edgeSignature;
    for(const workflow of graphDefinition.workflows.filter(w=>workflowGraphView.mode==='overview'||w.kind===workflowGraphView.mode)){
      const selected=workflowGraphView.focus?.kind===workflow.kind?workflowGraphView.focus.stage:null,edges=workflowGraphEdges(workflow,selected,workflowGraphView.allPaths);
      for(const edge of edges.visible){const label=edges.main.includes(edge)?m("ui.1bd48634763c"):graphEdgeLabel(edge);list.append(button(edge.from+' → '+edge.to+' · '+label,()=>selectGraphStage(workflow.kind,edge.to),'edge'));}
      for(const edge of edges.selfLoops.filter(edge=>workflowGraphView.allPaths||edge.from===selected))list.append(button(edge.from+m("ui.0d018c5cf594"),()=>selectGraphStage(workflow.kind,edge.from),'edge iteration'));
    }
  }
  if(bound){
    const active=bound.active_stages||[],waiting=bound.waiting_stages||[],recent=bound.recent_stages||[];
    const reasons=[...new Set((bound.stages||[]).flatMap(stage=>(stage.waiting_reasons||[]).map(reason=>stage.stage_id+'：'+(typeof reason==='string'?L.systemMessage(reason):JSON.stringify(reason)))))];
    L.text($('workflow-summary'),show(bound.instance_status)+' · '+(active.length?m("ui.f337a0d2ae1d")+active.map(id=>id+' '+workflowStageLabel(id)).join('、'):m("ui.8996422e9358"))+' · '+(waiting.length?m("ui.96c90fd38ce2")+waiting.map(id=>id+' '+workflowStageLabel(id)).join('、'):m("ui.78d87fc87f70"))+m("ui.4fa267e5cfb7")+(recent.join('、')||m("ui.f6df5b84e134"))+(reasons.length?m("ui.9dccda60ad88")+reasons.join('；'):''));
  }else L.text($('workflow-summary'),m("ui.a68e0c3114e3"));
  renderStageDetail(bound);redrawWorkflowGraphs();
}
async function navigateStage(kind,stage){
  const row=selectedInstanceRow();if(!row||row.kind!==kind){L.text($('notice'),m("ui.f982c5481672")+kind+m("ui.8b569e047155")+stage+m("ui.6361dccd5286"));return;}
  await selectView('tasks',{stage,keepGraph:true});$('view-title').scrollIntoView({block:'nearest',behavior:'smooth'});
}
function renderStageDetail(activity){
  const box=$('stage-detail'),focus=workflowGraphView.focus;box.hidden=!focus;
  if(!focus){if(box.childNodes.length)box.replaceChildren();workflowGraphView.detailKey=null;return;}
  const definition=graphDefinition.workflows.find(w=>w.kind===focus.kind)?.nodes.find(n=>n.stage_id===focus.stage);if(!definition)return;
  const bound=focus.scope===workflowGraphScope()?selectedGraphActivity(activity):null;
  const stage=workflowStagePresentation(bound,focus.kind,focus.stage),policy=graphDefinition.policy||modelPolicy;
  const tasks=stage.known?(currentStatus?.tasks||[]).filter(t=>(!t.instance_id||t.instance_id===bound.instance_id)&&t.stage_id===focus.stage):[];
  const overrides=stage.known?(currentStatus?.model_configuration?.model_overrides||[]):[];
  const detailKey=JSON.stringify([focus,stage,tasks,overrides,policy]);if(detailKey===workflowGraphView.detailKey)return;workflowGraphView.detailKey=detailKey;
  const openSections=new Set([...box.querySelectorAll('details')].filter(d=>d.open).map(d=>d.dataset.detailSection));box.replaceChildren();
  const header=el('div',undefined,'stage-detail-heading');header.append(el('h3',focus.stage+' · '+workflowStageLabel(focus.stage)),el('span',graphStateLabel(stage),'badge'));header.append(button(m("ui.9071cfe7cd01"),()=>{resetWorkflowGraphSelection();renderWorkflowGraph(currentStatus?.activity);},'stage-detail-close'));box.append(header);
  box.append(el('p',workflowStageDescription(focus.stage),'stage-description'));
  note(box,stage.known?m("ui.7c16109e9c6d"):m("ui.2f08635e6c18"));
  function section(id,title,open=false){const d=el('details',undefined,'stage-detail-section');d.dataset.detailSection=id;d.open=openSections.has(id)||open;d.append(el('summary',title));box.append(d);return d;}
  const workflow=graphDefinition.workflows.find(w=>w.kind===focus.kind),related=(workflow.edges||[]).filter(e=>e.from===focus.stage||e.to===focus.stage);
  const routes=section('paths',m("ui.96b5f465245f"),true),links=el('div',undefined,'stage-related-paths');
  for(const edge of related){const target=edge.from===focus.stage?edge.to:edge.from;links.append(button(edge.from===edge.to?edge.from+m("ui.0d018c5cf594"):edge.from+' → '+edge.to+' · '+graphEdgeLabel(edge),()=>selectGraphStage(focus.kind,target),'edge '+edge.kind));}routes.append(links);
  if(focus.stage==='P7')for(const route of graphDefinition.analysis_routes||[]){const r=el('p',undefined,'graph-route');r.append(el('strong',L.has('route.'+route.id)?m('route.'+route.id):L.systemMessage(route.label||route.id)),el('span',' · '+(route.roles||[]).map(role=>typeof role==='string'?role:role.role).join(' → ')));routes.append(r);}
  for(const handoff of (graphDefinition.handoffs||[]).filter(row=>row.from===focus.kind)){
    const h=el('p',handoff.from+' → '+handoff.to+' · '+(L.has('handoff.'+handoff.from+'.'+handoff.to)?m('handoff.'+handoff.from+'.'+handoff.to):L.systemMessage(handoff.label||'')),'graph-handoff');routes.append(h);
    if(stage.known)routes.append(button(m("ui.42f0c2523ec3"),()=>{requireInstance();if(selectedInstanceRow()?.kind!==focus.kind)throw uiError(m("ui.c0163b2c853b"));return reformulate();},'edge'));
  }
  const model=section('policy',m("ui.8ff3aaea9ff3"));
  if(definition.roles?.length)note(model,m("ui.6b6dd7215f8b")+definition.roles.join('、'));
  if(!policy)note(model,m("ui.53343c0f0849"));
  else {
    const rules=(policy.rules||[]).filter(r=>r.workflow_kind===focus.kind&&r.stage_id===focus.stage);
    for(const rule of rules){
      const override=overrides.find(o=>scopeKey(o.scope)===scopeKey({workflow_kind:focus.kind,stage_id:focus.stage,role:rule.role,purpose:rule.purpose||'DEFAULT'}));
      note(model,rule.role+' · '+(rule.call_model?m("ui.0a63a8195f55")+rule.model+' / '+rule.reasoning_effort+' / '+rule.service_tier:m("ui.28ad04a4ac19")));
      if(override)note(model,m("ui.f875b629d62b")+(override.model||rule.model)+' / '+(override.reasoning_effort||rule.reasoning_effort)+' / '+(override.service_tier||rule.service_tier));
    }
    for(const exception of (policy.purpose_exceptions||[]).filter(r=>r.stage_id===focus.stage))note(model,exception.role+m("ui.39bb928373b2")+exception.purpose+'：'+exception.reasoning_effort);
    if(rules.some(r=>r.role.startsWith('REPORT_')))note(model,m("ui.f78767ccbf95")+policy.layout_only_reasoning_effort+m("ui.791883092d3a"));
    for(const override of overrides.filter(o=>o.scope.workflow_kind===focus.kind&&o.scope.stage_id===focus.stage&&o.scope.purpose!=='DEFAULT'))note(model,m("ui.4c1c8ead9145")+override.scope.role+' / '+override.scope.purpose+'：'+override.model+' / '+override.reasoning_effort+' / '+override.service_tier);
    note(model,m("ui.080f835e8b0c"));
  }
  if(!stage.known)return;
  for(const route of stage.analysis_routes||[])note(box,m("ui.2870dcba8ccf")+route);
  if((stage.waiting_reasons||[]).length||(stage.next_actions||[]).length){const waiting=section('waiting',m("ui.5084bbdeae6a"),true);for(const reason of stage.waiting_reasons||[])note(waiting,m("ui.ca634bb89740")+(typeof reason==='string'?L.systemMessage(reason):JSON.stringify(reason)));for(const next of stage.next_actions||[])note(waiting,m("ui.108241984e46")+(typeof next==='string'?L.systemMessage(next):L.systemMessage(next.label||next.action||JSON.stringify(next))));}
  const actual=section('actual',m("ui.25ca7248d2f5"));
  if(!(stage.task_ids||[]).length&&!(stage.control_event_ids||[]).length)note(actual,m("ui.7815c05b5e51"));
  for(const t of tasks){const p=t.model_policy;note(actual,t.task_id+' · '+t.role+(p?m("ui.cac41e010997")+(p.call_model===false?m("ui.239f2d0f2cdb"):p.model+' / '+p.reasoning_effort+' / '+p.service_tier):''));}
  for(const id of (stage.task_ids||[]).filter(id=>!tasks.some(t=>t.task_id===id)))note(actual,m("ui.da0d55598c01")+id);
  for(const id of stage.request_ids||[])note(actual,m("ui.a6474ea684e5")+id);for(const id of stage.control_event_ids||[])note(actual,m("ui.30678e5c2f28")+id);
  if((stage.record_refs||[]).length){const products=section('products',m("ui.021abf8bd52f")+stage.record_refs.length+m("ui.ff8c55f7a900"),true),readScope={project,instance:bound.instance_id,commit:latestCommit||snapshot};
    for(const ref of stage.record_refs)products.append(button(m("ui.ca44584f3782")+ref.slice(-12),async()=>{const r=await readApi('body',{...readScope,ref});if(project!==readScope.project||$('instance').value!==readScope.instance)return;const d=dialog(m("ui.250e7a43cf08"));d.append(el('p',ref,'ref'),el('div',r.body,'body'));await typeset(d);},'edge'));
  }
  const actions=el('div',undefined,'stage-detail-actions');actions.append(button(m("ui.f58bfae730b2"),()=>navigateStage(focus.kind,focus.stage)),button(m("ui.eee061f6b5c9"),()=>selectView('frontier',{keepGraph:true})),button(m("ui.93088070ea79"),()=>selectView('tasks',{keepGraph:true})));box.append(actions);
}
async function environmentSettings(box,setup){
  if(!setup)return;
  const section=el('section',undefined,'dependency-settings');section.append(el('h3',m("ui.70cc0502b974")));
  note(section,(setup.research_ready?m("ui.1944ff5a1457"):m("ui.3a3e53a6be1e"))+' '+(setup.pdf_dependencies_present?m("ui.c9b80ea2f0e3"):m("ui.170d09c94039")));
  for(const component of setup.components||[]){const row=el('div',undefined,'scope');row.append(el('strong',L.systemMessage(component.label||component.id)));note(row,(component.installed?m("ui.cc4f95807889"):m("ui.f51bc1439591"))+(component.version?' · '+component.version:'')+(component.source?' · '+component.source:''));
    if(component.install_available)row.append(button(m("ui.10ab2c430705")+(L.systemMessage(component.label||component.id)),async()=>{const confirmBox=dialog(m("ui.76e486937151"));confirmBox.append(el('p',m("ui.efb893de7ed1")+(L.systemMessage(component.label||component.id))+m("ui.97e6dcb6903a")));confirmBox.append(button(m("ui.0c49c2ddfe15"),async()=>{await action('setup-install',{component:component.id,confirmed:true});await settings();},'primary'));}));section.append(row);}
  for(const job of setup.jobs||[]){const row=el('p',(job.component||job.job_id)+' · '+(show(job.state)||job.state)+' · '+L.systemMessage(job.message||''),'scope');row.dataset.setupJob=job.job_id;section.append(row);}
  const form=el('form',undefined,'stack');const fields={};
  for(const [key,label] of [['codex',m("ui.5bb1688f3a94")],['tectonic',m("ui.18c1b68c59f2")],['tectonic_cache',m("ui.bc884d246b20")],['ca_bundle',m("ui.5144cafc3d68")]]){
    fields[key]=field(form,label+m("ui.77e1ea5c5688"),'setup-'+key,'text',setup.paths?.[key]||'');L.attribute(fields[key],'placeholder',setup.resolved?.[key]||m("ui.1a64d45e9763"));
    form.append(button(m("ui.beb4816bf802")+label,async()=>{const r=await action('setup-select',{kind:key});if(!r.cancelled)await settings();}));
  }
  note(form,m("ui.da37a8544cce"));
  submit(form,m("ui.ae4709e2b18c"),async()=>{await action('setup-configure',{paths:Object.fromEntries(Object.entries(fields).map(([k,input])=>[k,input.value.trim()||null]))});await settings();});section.append(form);box.append(section);
}
async function pollSetup(){
  if(!$('dialog').open||!$('dialog-content').querySelector('[data-setup-job]'))return;
  const d=await request('/api/settings');
  for(const job of d.setup?.jobs||[]){const row=[...$('dialog-content').querySelectorAll('[data-setup-job]')].find(n=>n.dataset.setupJob===job.job_id);if(row)L.text(row,(job.component||job.job_id)+' · '+job.state+' · '+L.systemMessage(job.message||''));}
}

function surveyScopeFields(parent,prefix,inputs={statements:[],sources:[]},entry='NEW_TOPIC'){
  const group=el('fieldset',undefined,'stack');group.append(el('legend',m("ui.4180a9a25644")));parent.append(group);
  const mode=field(group,m("ui.811ad42aa2a9"),prefix+'-entry','select');options(mode,[['NEW_TOPIC',m("ui.6c15f60b9b25")],['EXISTING_KNOWLEDGE',m("ui.f16342fc897e")],['UPDATE',m("ui.fb02954e869d")]]);mode.value=entry;
  const topic=field(group,m("ui.788db1cfec2a"),prefix+'-topic');topic.required=true;
  const questions=field(group,m("ui.fff090c643e0"),prefix+'-questions','textarea');questions.required=true;
  const objects=field(group,m("ui.cc7e0557096f"),prefix+'-objects','textarea');
  const conditions=field(group,m("ui.4231e7bb92be"),prefix+'-conditions','textarea');
  const include=field(group,m("ui.53e0789c7039"),prefix+'-include','textarea');
  const exclude=field(group,m("ui.a90de7d505e0"),prefix+'-exclude','textarea');
  const goal=field(group,m("ui.b835b36aa4dc"),prefix+'-goal','select');options(goal,[['KNOWLEDGE_ONLY',m("ui.971e38141a70")],['SURVEY_MANUSCRIPT',m("ui.7bb8822b5917")]]);
  const refs=field(group,m("ui.62c6fd021260"),prefix+'-refs','select');refs.multiple=true;refs.size=4;options(refs,(inputs.records||inputs.statements||[]).map(r=>[r.ref,r.title||r.body?.slice(0,100)||r.ref]));
  const sources=field(group,m("ui.bbbeea89fa50"),prefix+'-sources','select');sources.multiple=true;sources.size=4;options(sources,(inputs.sources||[]).map(r=>[r.source_ref,r.title||r.source_ref]));
  const previous=field(group,m("ui.9fe63a2a2c74"),prefix+'-parent','select');options(previous,[['',m("ui.0fd4f1eb4bff")],...(allInstances.length?allInstances:currentStatus?.workflow.instances||[]).filter(i=>i.kind==='SURVEY').map(i=>[i.instance_id,instanceLabel(i)])]);
  const update=()=>{(refs.parentElement||refs.parentNode).hidden=mode.value==='NEW_TOPIC';(previous.parentElement||previous.parentNode).hidden=mode.value!=='UPDATE';};mode.onchange=update;update();
  note(group,m("ui.c2419408a1eb"));
  const lines=input=>input.value.split('\n').map(x=>x.trim()).filter(Boolean);
  return {group,value(){if(!topic.value.trim()||!questions.value.trim())throw uiError(m("ui.c10e4bace6e0"));if(mode.value==='UPDATE'&&!previous.value)throw uiError(m("ui.375291d86995"));return {topic:topic.value,questions:lines(questions),objects:lines(objects),conditions:lines(conditions),include:lines(include),exclude:lines(exclude),entry:mode.value,delivery_goal:goal.value,selected_refs:[...refs.selectedOptions].map(o=>o.value),source_refs:[...sources.selectedOptions].map(o=>o.value),...(previous.value?{parent_instance_id:previous.value}:{})};}};
}
async function surveyCreateForm(entry='NEW_TOPIC'){
  const existing=!!project,inputs=existing?await workflowInputs():undefined,box=dialog(m("ui.c7f2b4633f20")),f=el('form',undefined,'stack');
  const title=existing?null:field(f,m("ui.867698fb7b0c"),'survey-project');if(title)title.required=true;
  const name=field(f,m("ui.2a32b8e07d5f"),'survey-name');name.required=true;
  const scope=surveyScopeFields(f,'survey-create',inputs,entry);
  submit(f,m("ui.cfd48911418d"),async()=>{const payload={kind:'SURVEY',name:name.value,survey_scope:scope.value(),...(title?{title:title.value}:{})};const r=await action(existing?'new-workflow':'create',payload);closeDialog();if(r.project)await listProjects(r.project);else await openProject();if(r.instance_id)$('instance').value=r.instance_id;view='survey';await refresh();});box.append(f);
}
async function surveyActivityForm(){
  requireInstance();const inputs=await workflowInputs(),box=dialog(m("ui.8e990cc1a2d9")),f=el('form',undefined,'stack');
  const stage=field(f,m("ui.2612dc4025d2"),'survey-stage','select');options(stage,[...['S1','S2','S3','S4'].map(s=>[s,s+' · '+workflowStageLabel(s)]),['S5',m('survey.output_budget')]]);
  const intent=field(f,m("ui.3e76bb95c071"),'survey-intent','textarea');intent.required=true;
  const calls=field(f,m("ui.fefbc4bb7421"),'survey-calls','number','4');calls.min='1';calls.max='1000';
  const workers=field(f,m("ui.34908be5e604"),'survey-workers','number',String(currentStatus?.budget?.max_workers||1));workers.min='1';workers.max='8';
  note(f,m('concurrency.policy'));
  const sources=field(f,m('ui.bbbeea89fa50'),'survey-activity-sources','select');sources.multiple=true;sources.size=5;options(sources,inputs.sources.map(row=>[row.source_ref,row.title||row.source_ref]));
  const refs=field(f,m('ui.62c6fd021260'),'survey-activity-records','select');refs.multiple=true;refs.size=5;options(refs,(inputs.records||inputs.statements).map(row=>[row.ref,row.title||row.ref]));
  note(f,m('survey.activity_selection'));note(f,m("ui.e58a2171f421"));
  submit(f,m("ui.5cacd33e3905"),async()=>{const selected=[...refs.selectedOptions].map(row=>row.value),sourceRefs=[...sources.selectedOptions].map(row=>row.value);await action('survey-activity',{stage:stage.value,intent:intent.value,max_calls:Number(calls.value),max_workers:Number(workers.value),...(selected.length?{selected_refs:selected}:{}),...(sourceRefs.length?{source_refs:sourceRefs}:{})});closeDialog();view='survey';await refresh();});box.append(f);
}
function surveyPlanEditor(parent,data,snapshotInput,inputs){
  const section=el('section',undefined,'stack'),proofBox=el('div',undefined,'stack'),omissionBox=el('div',undefined,'stack');section.append(el('h3',m('survey.proofs')),proofBox,el('h3',m('survey.omitted')),omissionBox);parent.append(section);let proofs=[],omissions=[];
  const frozen=()=>surveyRows(data,'snapshots').find(row=>row.id===snapshotInput.value);
  const refs=()=>{const f=frozen();const closure=f?.material?.closure||f?.selected_refs||[];return (inputs.records||inputs.statements).filter(r=>closure.includes(r.ref));};
  section.append(button(m('survey.add_proof'),()=>{if(!frozen())throw uiError(m('survey.select_first'));const row=el('fieldset',undefined,'stack'),ref=field(row,m('survey.record'),'proof-record-'+proofs.length,'select');options(ref,refs().map(r=>[r.ref,r.title||r.body?.slice(0,100)||r.ref]));ref.required=true;const treatment=field(row,m('survey.treatment'),'proof-treatment-'+proofs.length,'select');options(treatment,['complete','sketch','mechanism','citation','none'].map(t=>[t,m('survey.'+t)]));const steps=field(row,m('survey.steps'),'proof-steps-'+proofs.length,'textarea');const entry={row,ref,treatment,steps};proofs.push(entry);row.append(button(m('survey.remove'),()=>{proofs=proofs.filter(x=>x!==entry);row.remove();}));proofBox.append(row);}),button(m('survey.add_omission'),async()=>{if(!frozen())throw uiError(m('survey.select_first'));const inputs=await workflowInputs(),row=el('fieldset',undefined,'stack'),ref=field(row,m('survey.record'),'omission-record-'+omissions.length,'select');options(ref,(inputs.records||inputs.statements).filter(x=>!(frozen()?.selected_refs||[]).includes(x.ref)).map(x=>[x.ref,x.title||x.ref]));const reason=field(row,m('survey.reason'),'omission-reason-'+omissions.length,'textarea');const entry={row,ref,reason};omissions.push(entry);row.append(button(m('survey.remove'),()=>{omissions=omissions.filter(x=>x!==entry);row.remove();}));omissionBox.append(row);}));note(section,m('survey.proof_scope'));
  snapshotInput.onchange=()=>{proofs=[];omissions=[];proofBox.replaceChildren();omissionBox.replaceChildren();};
  return {value:()=>({proof_promises:proofs.map(x=>({record_ref:x.ref.value,treatment:x.treatment.value,required_steps:x.steps.value.split('\n').map(x=>x.trim()).filter(Boolean)})),omissions:omissions.map(x=>({record_ref:x.ref.value,reason:x.reason.value}))})};
}

function surveyRows(data,key){const value=data?.[key];return Array.isArray(value)?value:value&&typeof value==='object'?Object.values(value):[];}
function renderSurvey(data,parent){
  const intro=card(m("ui.cb484d48f1fc"));intro.dataset.surveyOverview='true';note(intro,m("ui.e7bd0e5bb935"));
  const actions=el('div',undefined,'actions');actions.append(button(m("ui.f63b963bcf94"),surveyActivityForm),button(m("ui.655fc2553939"),surveyRetrieveForm),button(m('survey.freeze'),surveyFreezeForm),button(m("ui.e3ff77ea54af"),surveyReportForm));intro.append(actions);parent.append(intro);
  const status=el('div');status.id='survey-live-state';parent.append(status);renderSurveyState(data,status);
}
function surveyFact(parent,key,value){
  if(value===undefined||value===null||(Array.isArray(value)&&!value.length)||value==='')return;
  const box=el('div',undefined,'survey-fact');box.append(el('strong',m('survey.field.'+key)),el('p',Array.isArray(value)?value.map(item=>typeof item==='object'?item.message||item.reason||JSON.stringify(item):item).join('\n'):typeof value==='object'?value.message||value.reason||JSON.stringify(value):String(value),'body'));parent.append(box);
}
function surveyReferences(parent,label,refs){
  if(!refs?.length)return;const box=el('div',undefined,'survey-references');box.append(el('strong',m('survey.field.'+label)));
  for(const ref of refs)box.append(button(ref.slice(0,10)+'…'+ref.slice(-8),async()=>{const row=await readApi('body',{ref,commit:latestCommit||snapshot});const box=dialog(m('survey.field.'+label));box.append(el('p',ref,'ref'),el('div',row.body,'body'));await typeset(box);},'edge'));
  parent.append(box);
}
function surveyRecord(key,row){
  const c=el('article',undefined,'survey-record');
  if(key==='search_plans'||key==='retrievals'){
    if(row.status)c.append(el('p',show(row.status),'badge'));for(const query of row.queries||[]){const box=el('div',undefined,'scope');surveyFact(box,'provider',query.provider);surveyFact(box,'query',query.query);surveyFact(box,'rationale',query.reason);if(query.status)box.append(el('p',show(query.status),'badge'));surveyFact(box,'time',query.at);if(query.failure_reason)surveyFact(box,'failure',typeof query.failure_reason==='string'?query.failure_reason:query.failure_reason.reason||query.failure_reason.http_status||query.status);c.append(box);}
    surveyFact(c,'stop_reason',row.stop_reason);if(row.simulated_network_requests!==undefined)surveyFact(c,'synthetic_requests',row.simulated_network_requests);if(row.network_requests!==undefined)surveyFact(c,row.simulated_network_requests===undefined&&(row.queries||[]).length&&(row.queries||[]).every(q=>q.provider==='mock')?'synthetic_requests':'network_requests',row.network_requests);
    for(const item of row.candidates||[]){const box=el('section',undefined,'scope');box.append(el('h4',item.title||item.candidate_id));box.append(el('p',show(item.access_status||'METADATA_ONLY')+' · '+m(item.selected?'survey.selected':'survey.excluded_candidate'),'badge'));surveyFact(box,'version',item.version);surveyFact(box,'rationale',item.selection_reason);surveyFact(box,'limitations',item.acquisition_limitation);if(item.url&&/^https:\/\//.test(item.url)){const link=el('a',m('survey.original_link'));link.href=item.url;link.target='_blank';link.rel='noopener';box.append(link);}c.append(box);}
  }else if(key==='readings'){
    c.append(el('p',show(row.access_status),'badge'));surveyFact(c,'source',row.source_ref);surveyFact(c,'version',row.version);surveyFact(c,'read_scope',row.read_scope);surveyFact(c,'unread_scope',row.unread_scope);surveyFact(c,'limitations',row.limitations);surveyFact(c,'locators',(row.locators||[]).map(loc=>[loc.unit||loc.kind,loc.start!==undefined?loc.start+'–'+loc.end:null,loc.page!==undefined?'p. '+loc.page:null,loc.quote].filter(Boolean).join(' · ')));surveyReferences(c,'claims',row.claim_refs);
  }else if(key==='coverage'){
    for(const item of row.coverage||[]){const box=el('section',undefined,'scope');surveyFact(box,'question',item.question);box.append(el('p',show(item.assessment),'badge'));surveyFact(box,'rationale',item.rationale);surveyReferences(box,'answers',item.answer_refs);surveyReferences(box,'mechanisms',item.mechanism_refs);surveyReferences(box,'boundaries',item.boundary_refs);for(const gap of item.gaps||[]){surveyFact(box,'gap',gap.description);box.append(el('p',show(gap.disposition)+' · '+(gap.return_stage||''),'badge'));}c.append(box);}
  }else if(key==='reviews'){
    c.append(el('p',show(row.verdict),'badge'));surveyFact(c,'questions',row.coverage_questions);surveyReferences(c,'checked',row.checked_refs);surveyReferences(c,'unchecked',row.unchecked_refs);for(const finding of row.findings||[]){const box=el('section',undefined,'scope');box.append(el('strong',m(finding.blocking?'survey.blocking':'survey.nonblocking')+' · '+(finding.return_stage||'')));surveyFact(box,'finding',finding.message);c.append(box);}surveyFact(c,'limitations',row.limitations);
  }else if(key==='snapshots'){
    surveyFact(c,'questions',row.question_ids);surveyReferences(c,'selected',row.selected_refs);surveyFact(c,'created',row.at);note(c,m('survey.freeze_note'));
  }else if(key==='output_plans'){
    c.append(el('h4',m('survey.edition.'+row.profile)));surveyFact(c,'audience',row.audience);surveyFact(c,'perspective',row.view);surveyFact(c,'prerequisites',row.prerequisites);for(const promise of row.proof_promises||[]){const box=el('div',undefined,'scope');box.append(el('strong',m('survey.'+promise.treatment)));surveyReferences(box,'claims',[promise.record_ref]);surveyFact(box,'proof_steps',promise.required_steps);c.append(box);}for(const omission of row.omissions||[]){const box=el('div',undefined,'scope');surveyReferences(box,'omitted',[omission.record_ref]);surveyFact(box,'rationale',omission.reason);c.append(box);}surveyFact(c,'limitations',row.limitations);surveyFact(c,'language',row.language);
  }
  const raw=el('details');raw.append(el('summary',m('survey.native_details')),el('pre',JSON.stringify(row,null,2),'diagnostic'));c.append(raw);return c;
}
function surveyReadinessDetails(value,parent){
  parent.append(el('p',m('survey.state.'+(value.status||'NEEDS_WORK')),'badge'));surveyReferences(parent,'selected',value.selected_refs);for(const issue of value.errors||[]){const box=el('div',undefined,'scope');box.append(el('strong',issue.return_stage||''),el('p',L.has('error.'+issue.code)?m('error.'+issue.code):issue.message));parent.append(box);}for(const item of value.unchecked||[])surveyFact(parent,'deferred',item.description||item.reason);const raw=el('details');raw.append(el('summary',m('survey.native_details')),el('pre',JSON.stringify(value,null,2),'diagnostic'));parent.append(raw);
}
function sourceStatusForm(row){
  requireInstance();const box=dialog(m('source.status_title')),f=el('form',undefined,'stack'),status=row.survey_source_status||{};f.append(el('p',row.filename||row.source_ref));const withdrawn=field(f,m('source.withdrawn'),'source-withdrawn','checkbox'),conflict=field(f,m('source.conflict'),'source-conflict','checkbox');withdrawn.checked=!!status.withdrawn;conflict.checked=!!status.version_conflict;const reason=field(f,m('source.reason'),'source-status-reason','textarea');reason.required=true;note(f,m('source.status_note'));submit(f,m('source.save_status'),async()=>{await action('survey-source-status',{source_ref:row.source_ref,withdrawn:withdrawn.checked,version_conflict:conflict.checked,reason:reason.value});closeDialog();await refresh();});box.append(f);
}

function renderSurveyState(data,box){
  const signature=JSON.stringify(data);if(box.dataset.signature===signature)return;box.dataset.signature=signature;
  const open=new Set([...box.querySelectorAll('details[open]')].map(d=>d.dataset.surveySection));box.replaceChildren();
  const readiness=data?.readiness||{},status=el('section',undefined,'survey-state');status.append(el('strong',m('survey.readiness_status')+': '+m('survey.state.'+(readiness.status||'NEEDS_WORK'))));
  for(const issue of readiness.errors||[])note(status,(issue.return_stage?issue.return_stage+' · ':'')+(L.has('error.'+issue.code)?m('error.'+issue.code):issue.message));if(data?.next_activity)note(status,m('survey.next_activity')+': '+data.next_activity+' · '+workflowStageLabel(data.next_activity));box.append(status);
  for(const [key,label] of [['scope',m("ui.4180a9a25644")],['search_plans',m("ui.18ca4f0f5f6c")],['retrievals',m("ui.e791d2c9f87d")],['readings',m("stage.S2.name")],['coverage',m("ui.09805f795aee")],['reviews',m("ui.fd69af510ae6")],['readiness',m("stage.S4.name")],['snapshots',m("ui.3e89c4e562da")],['output_plans',m("ui.5f82ef1163fb")]]){
    const d=el('details');d.dataset.surveySection=key;d.open=open.has(key)||key==='scope';d.append(el('summary',label));const value=data?.[key];
    if(key==='scope'&&value){const facts=el('dl',undefined,'survey-facts');for(const [field,label] of [['topic',m('ui.788db1cfec2a')],['questions',m('survey.questions')],['objects',m('ui.cc7e0557096f')],['conditions',m('ui.4231e7bb92be')],['include',m('survey.included')],['exclude',m('survey.excluded')],['delivery_goal',m('ui.b835b36aa4dc')]]){let text=value[field];if(field==='delivery_goal')text=m(text==='KNOWLEDGE_ONLY'?'ui.971e38141a70':'ui.7bb8822b5917');else if(Array.isArray(text))text=text.join('\n');facts.append(el('dt',label),el('dd',text||m('survey.not_specified')));}d.append(facts);const raw=el('details');raw.append(el('summary',m('survey.native_details')),el('pre',JSON.stringify(value,null,2),'diagnostic'));d.append(raw);}
    else if(key==='readiness'&&value)surveyReadinessDetails(value,d);
    else if(Array.isArray(value)&&value.length)for(const row of value)d.append(surveyRecord(key,row));
    else d.append(el('p',m("ui.add69dd04ab3"),'empty'));box.append(d);
  }
}
function patchSurveyState(s){const box=$('survey-live-state');if(box&&s.survey)renderSurveyState(s.survey,box);}
async function surveyRetrieveForm(){
  const data=await readApi('survey'),box=dialog(m("ui.655fc2553939")),f=el('form',undefined,'stack');
  const plan=field(f,m("ui.837e5dc94f92"),'survey-retrieval-plan','select');plan.required=true;options(plan,[['',m('survey.choose_plan')],...surveyRows(data,'search_plans').map(row=>[row.id,row.id])]);
  note(f,m("ui.c9cd53473720"));
  const plans=surveyRows(data,'search_plans');if(plans.length){const d=el('details');d.append(el('summary',m("ui.08386d74f5cd")),el('pre',JSON.stringify(plans,null,2),'diagnostic'));f.append(d);}
  submit(f,m("ui.cbae6446d244"),async()=>{await action('survey-retrieve',{plan_ref:plan.value.trim()});closeDialog();view='survey';await refresh();});box.append(f);
}
async function surveyFreezeForm(){
  const box=dialog(m('survey.freeze')),f=el('form',undefined,'stack'),inputs=await workflowInputs(),data=await readApi('survey');
  const refs=field(f,m("ui.b93a33d8a235"),'survey-freeze-refs','select');refs.multiple=true;refs.size=6;options(refs,(inputs.records||inputs.statements).map(r=>[r.ref,r.title||r.body.slice(0,100)]));
  const questions=field(f,m('survey.freeze_questions'),'survey-freeze-questions','select');questions.multiple=true;questions.size=Math.min(6,Math.max(2,(data.scope?.questions||[]).length));options(questions,(data.scope?.questions||[]).map(q=>[q,q]));for(const option of questions.options||questions.children)option.selected=true;
  note(f,m('survey.freeze_note'));note(f,m('survey.freeze_questions_note'));
  submit(f,m('survey.freeze'),async()=>{const selected=[...refs.selectedOptions].map(o=>o.value),questionIds=[...questions.selectedOptions].map(o=>o.value);await action('survey-freeze',{...(selected.length?{selected_refs:selected}:{}),...(questionIds.length?{question_ids:questionIds}:{})});closeDialog();view='survey';await refresh();});box.append(f);
}
async function surveyReportForm(){
  const data=await readApi('survey'),box=dialog(m("ui.6ea984526e40")),f=el('form',undefined,'stack');
  const snapshot=field(f,m("ui.5650e38d4113"),'survey-snapshot','select');snapshot.required=true;options(snapshot,[['',L.message('survey.choose_snapshot')],...surveyRows(data,'snapshots').map(row=>[row.id,row.id])]);
  const snapshots=surveyRows(data,'snapshots');if(snapshots.length){const d=el('details');d.append(el('summary',m("ui.8e2a118d8070")),el('pre',JSON.stringify(snapshots,null,2),'diagnostic'));f.append(d);}
  const profile=field(f,m("ui.a95c1785e219"),'survey-profile','select');options(profile,[['minimal',m("ui.08543cf39ae5")],['thematic',m("ui.268960d94561")],['lecture',m("ui.fd14fc2f1c6d")]]);
  const perspective=field(f,m("ui.a14e6140b192"),'survey-perspective','text','integrated'),audience=field(f,m("ui.37ef33fff6b8"),'survey-audience','text','Readers of the selected mathematical question'),prerequisites=field(f,m("ui.aab8ed1c780b"),'survey-prerequisites','textarea'),limitations=field(f,m('survey.limitations'),'survey-limitations','textarea');audience.required=true;perspective.required=true;
  const commitments=surveyPlanEditor(f,data,snapshot,await workflowInputs());
  note(f,m("ui.96d3b24fff02"));
  submit(f,m('survey.save_plan'),async()=>{const rows=commitments.value(),r=await action('survey-plan',{snapshot_ref:snapshot.value.trim(),profile:profile.value,view:perspective.value,audience:audience.value,prerequisites:prerequisites.value.split('\n').filter(x=>x.trim()),limitations:limitations.value.split('\n').filter(x=>x.trim()),...rows});closeDialog();view='survey';await refresh();const box=dialog(m('survey.plan_saved'));box.append(el('p',r.plan_ref,'ref'),el('p',m('survey.plan_saved_note')),button(m('survey.request_selected'),async()=>{await action('report',{profiles:[profile.value],plan_ref:r.plan_ref});closeDialog();view='reports';await refresh();},'primary'));});box.append(f);
  const plans=surveyRows(data,'output_plans');if(plans.length){const old=el('form',undefined,'stack'),choice=field(old,m('survey.saved_plan'),'survey-existing-plan','select');options(choice,plans.map(row=>[row.id,row.profile+' · '+row.id]));submit(old,m('survey.request_selected'),async()=>{const plan=plans.find(row=>row.id===choice.value);await action('report',{profiles:[plan.profile],plan_ref:plan.id});closeDialog();view='reports';await refresh();});box.append(old);}

}
async function surveyHandoffForm(){
  const inputs=await workflowInputs(),box=dialog(m("ui.b3766a115969")),f=el('form',undefined,'stack');
  const kind=field(f,m("ui.8728acbb9848"),'survey-handoff-kind','select');options(kind,[['TRW',m("ui.c2a3603c77ad")],['TFDW',m("ui.63a9a0acb77c")]]);
  const name=field(f,m("ui.46e54f3b89cc"),'survey-handoff-name');name.required=true;
  const ref=field(f,m("ui.de7bf556ff90"),'survey-handoff-ref','select');options(ref,inputs.statements.map(r=>[r.ref,r.title||r.body.slice(0,100)]));
  const noteField=field(f,m("ui.e590a9728353"),'survey-handoff-note','textarea');noteField.required=true;
  const discovery=discoveryFields(f,'survey-handoff-discovery',{sources:inputs.sources});kind.onchange=()=>{discovery.group.hidden=kind.value!=='TFDW';};kind.onchange();
  note(f,m("ui.61dd080ba086"));
  submit(f,m("ui.66374d074b1a"),async()=>{const r=await action('handoff',{direction:'SURVEY_TO_'+kind.value,name:name.value,target_ref:ref.value,candidate_ref:ref.value,note:noteField.value,...(kind.value==='TFDW'?{discovery_scope:discovery.value()}: {})});closeDialog();await openProject();$('instance').value=r.instance_id;view='current';await refresh();});box.append(f);
}
let reportsPollFingerprint='';
async function patchReportStates(s){
  const stamp=JSON.stringify(s.reports||s.report_status||s.execution||{});if(stamp===reportsPollFingerprint)return;
  const selectedProject=project,selectedInstance=$('instance').value,generation=refreshGeneration;
  const data=await readApi('reports');if(view!=='reports'||selectedProject!==project||selectedInstance!==$('instance').value||generation!==refreshGeneration)return;
  reportsPollFingerprint=stamp;const box=$('content'),rows=data.reports||[];const old=new Map([...box.querySelectorAll('[data-report-id]')].map(c=>[c.dataset.reportId,c]));
  for(const row of rows){const c=old.get(row.report_id),fingerprint=JSON.stringify(row);if(c?.dataset.reportFingerprint===fingerprint)continue;const replacement=report(row);replacement.dataset.reportFingerprint=fingerprint;if(c){const open=[...c.querySelectorAll('details')].map(d=>d.open);[...replacement.querySelectorAll('details')].forEach((d,i)=>{d.open=!!open[i];});c.replaceWith(replacement);}else box.append(replacement);}
  if(rows.length)for(const empty of box.querySelectorAll('.empty'))empty.remove();
}

function applyLocale(locale){
  const position={x:window.scrollX||0,y:window.scrollY||0},scrolls=[...document.querySelectorAll('*')].filter(n=>n.scrollTop||n.scrollLeft).map(n=>[n,n.scrollTop,n.scrollLeft]);
  L.setLocale(locale);$('ui-locale').value=L.getLocale();$('dialog-locale').value=L.getLocale();
  for(const [node,top,left] of scrolls){node.scrollTop=top;node.scrollLeft=left;}if(window.scrollTo)window.scrollTo(position.x,position.y);redrawWorkflowGraphs();
}
async function initial(){
  const token=new URLSearchParams(location.hash.slice(1)).get('session');if(token){await request('/api/session',{method:'POST',data:{token}});history.replaceState(null,'',location.pathname);}
  try{const s=await request('/api/session');csrf=s.csrf;workspaceId=s.workspace_id;L.setLocale(s.ui_locale||'en');$('ui-locale').value=L.getLocale();operations.storage=indexedOperationStorage(window.indexedDB,workspaceId);$('app').hidden=false;graphDefinition=await request('/api/workflow-graph');await listProjects();const recovered=await operations.recover();await renderOperationRecovery(recovered);if(recovered?.result!==undefined)await applyRecovered(recovered.result,recovered.operation);}
  catch(e){if(!csrf)$('session-warning').hidden=false;throw e;}
}
for(const id of ['ui-locale','dialog-locale'])$(id).onchange=guarded(async()=>{const selected=$(id).value,previous=L.getLocale();try{const result=await request('/api/preferences',{method:'POST',data:{ui_locale:selected}});applyLocale(result.ui_locale);}catch(e){$(id).value=previous;throw e;}});
$('survey-existing').onclick=guarded(()=>surveyCreateForm('EXISTING_KNOWLEDGE'));$('survey-update').onclick=guarded(()=>surveyCreateForm('UPDATE'));
$('close-dialog').onclick=closeDialog;$('new-project').onclick=()=>createForm();$('new-workflow').onclick=guarded(newWorkflowForm);$('handoff-workflow').onclick=guarded(reformulate);$('edit-discovery').onclick=guarded(discoveryConfigForm);$('import-project').onclick=importForm;$('settings-button').onclick=guarded(settings);$('help-button').onclick=help;$('start-round').onclick=guarded(startForm);$('plan-work').onclick=guarded(workPlanForm);$('request-correction').onclick=guarded(correctionForm);$('add-source').onclick=sourceForm;$('project-assistant').onclick=guarded(()=>openAssistant());
$('project').onchange=guarded(async()=>{project=$('project').value;$('instance').value='';clearStageSelection();projectGeneration++;refreshGeneration++;localStorage.setItem('pmrs_4_0_project',project);await listProjects();});$('instance').onchange=guarded(()=>{clearStageSelection();return refresh();});$('refresh').onclick=guarded(()=>refresh());$('refresh-content').onclick=guarded(()=>refresh());$('search-form').onsubmit=guarded(()=>refresh());$('more').onclick=guarded(()=>refresh(true));
for(const name of ['pause','continue','end'])$(name).onclick=guarded(async()=>{requireInstance();await action(name,{commit:latestCommit||snapshot});await openProject();});
$('request-report').onclick=guarded(async()=>{requireInstance();if(selectedInstanceRow()?.kind==='SURVEY')return surveyReportForm();await action('report');view='reports';await refresh();});
$('export').onclick=guarded(async()=>{const r=await action('export');const a=el('a',m("ui.c57b4eb10542"));a.href=r.download;a.download='PMRS-4.2.0-backup.zip';$('notice').replaceChildren(a);a.click();});
$('quit').onclick=guarded(async()=>{await action('quit');L.text($('notice'),m("ui.319637648a55"));$('app').hidden=true;});
for(const b of document.querySelectorAll('[data-new]'))b.onclick=()=>createForm(b.dataset.new);for(const b of document.querySelectorAll('[data-example]'))b.onclick=()=>createForm(b.dataset.example==='TRW'?'TRW':'TFDW',true);
for(const b of $('tabs').querySelectorAll('button'))b.onclick=guarded(()=>selectView(b.dataset.view));
setInterval(()=>{pollProgress();pollAssistant();pollSetup().catch(e=>{L.text($('notice'),m("ui.a4359a44a7d2")+e.message);});},5000);guarded(initial)();
})();
