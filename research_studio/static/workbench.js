/* Local operation receipts survive response loss and reload. No payload deduplication. */
(function () {
'use strict';
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
  const labels={P0:'目标授权',P1:'语境记号',P2:'关系路线',P3:'工作选择',P4:'推导构造',P5:'目标差距',P6:'问题归约',P7:'义务分析',P8:'修补反例',P9:'独立检查',P10:'结果拼接',P11:'变化盘点',P12:'整体复查',P13:'进展报告',P14:'研究决定',D0:'现象范围',D1:'正反证据',D2:'生成候选',D3:'研究筛选',D4:'独立审查',D5:'候选选择'};
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
    if(this.busy)throw Error('另一个操作正在提交，请先等待其结果。');
    this.busy=true;
    try {
      if(await this.discover())throw Error('上一次操作尚未确认，请先查询或恢复原操作。');
      const operation={key:this.uuid(),name,payload,state:'PENDING',created_at:new Date().toISOString()};
      if(!await this.storage.claim(operation))throw Error('上一次操作尚未确认，请先查询或恢复原操作。');
      return await this.send(operation);
    } finally {this.busy=false;}
  }
  async send(operation) {
    // Any response or acknowledgement loss retains the same key and original payload.
    const result=await this.transport.send(operation);
    // Quit closes the transport; confirm its durable receipt after the next launch.
    if(operation.name==='quit'&&result?.stopped===true)return result;
    if(this.transport.ack){const receipt=await this.query(operation);if(receipt.state!=='COMPLETED')throw Error('操作结果尚待确认，请查询原操作。');await this.acknowledge(operation,receipt);}
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
    if(this.busy)throw Error('原操作正在恢复，请等待。');this.busy=true;
    try {
      const found=await this.inspect();if(!found)return null;
      if(found.receipt.state==='COMPLETED'){await this.acknowledge(found.operation,found.receipt);return found.receipt.result;}
      if(found.receipt.state!=='NOT_FOUND'||found.operation.remote_only)throw Error('服务端尚未确认可重放；请保留原编号并查询，勿另建操作。');
      return await this.send(found.operation);
    } finally {this.busy=false;}
  }
  async acknowledgeFailure() {
    const found=await this.inspect();
    if(found?.receipt.state!=='FAILED')throw Error('结果尚未确定，不能结束原操作。');
    await this.acknowledge(found.operation,found.receipt);
  }
}
function indexedOperationStorage(indexedDB,workspaceId='') {
  let connection;const active=workspaceId?'active:'+workspaceId:'active';
  function db(){if(!connection)connection=new Promise((resolve,reject)=>{
    const r=indexedDB.open('pmrs-4.0-business-operations',1);
    r.onupgradeneeded=()=>r.result.createObjectStore('operations');
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('无法持久保存操作，尚未发送请求。'));
  });return connection;}
  async function transaction(mode,fn){const d=await db();return new Promise((resolve,reject)=>{
    const tx=d.transaction('operations',mode),store=tx.objectStore('operations');let value;
    tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(Error('操作保存失败，保留原编号后再试。'));tx.onabort=tx.onerror;
    fn(store,x=>{value=x;});
  });}
  return {
    get:()=>transaction('readonly',(s,done)=>{const r=s.get(active);r.onsuccess=()=>done(r.result||null);}),
    claim:value=>transaction('readwrite',(s,done)=>{const r=s.get(active);r.onsuccess=()=>{if(r.result)done(false);else{s.put(value,active);done(true);}};}),
    clear:key=>transaction('readwrite',(s,done)=>{const r=s.get(active);r.onsuccess=()=>{if(r.result?.key===key)s.delete(active);done(true);};})
  };
}
if(typeof module!=='undefined'&&module.exports)module.exports={OperationLifecycle,amendOverrides,scopeKey,stagePresentation,indexedOperationStorage,workflowStageLabel,workflowStagePresentation,workflowGraphEdges};
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);
let refreshGeneration=0,projectGeneration=0,progressBusy=false,graphDefinition=null,graphSelection=null;
let renderedGraphKind='', latestCommit='';
let navigationScope='',contentProgressFingerprint='';
let csrf='',workspaceId='',project=localStorage.getItem('pmrs_4_0_project')||'',snapshot='',view='current',nextOffset=null,currentStatus=null,modelPolicy=null;
const kindNames={Context:'上下文',Statement:'命题',Argument:'论证',Example:'例子',SourceEvidence:'来源证据',Assessment:'范围检查'};
const names={current:'当前知识',candidates:'候选比较与交接',frontier:'开放问题',sources:'原始材料',history:'研究历史',tasks:'任务与配置',reports:'研究报告',diff:'本轮变化'};
const states={ACTIVE:'已启用',PAUSED:'已暂停',ENDED:'已结束',QUEUED:'等待当前任务完成',RUNNING:'后台正在处理',WAITING:'等待下一项工作',BLOCKED:'需要处理',PREPARED:'已准备',RESERVED:'已预留调用',SENT:'请求已发送',UNKNOWN:'请求结果不确定',CAPTURED:'结果已捕获',SETTLED:'已接纳或结算',CONSIDERED:'已纳入考虑',COMPLETE:'已完成',COMPLETED_CURRENT_REPORT:'当前报告已完成',COORDINATOR_ACTIVE:'已有协调器正在处理项目',CANDIDATE:'候选，尚未获得范围支持',WAIT:'当前无可派发的已授权工作',UNRESOLVED:'仍待解决',SATISFIED_FOR_CONSUMER:'当前范围已满足'};
const show=x=>states[x]||x;
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,fn,cls){const b=el('button',text,cls);b.type='button';b.addEventListener('click',guarded(fn));return b;}
function guarded(fn){return async e=>{if(e)e.preventDefault();const trigger=e?.currentTarget;const lock=trigger?.tagName==='BUTTON'&&!trigger.disabled;if(lock)trigger.disabled=true;$('error').textContent='';try{await fn(e);}catch(e){$('error').textContent=e.message;if($('dialog').open){let message=$('dialog-error');if(!message){message=el('p',undefined,'error');message.id='dialog-error';message.setAttribute('role','alert');$('dialog-content').prepend(message);}message.textContent=e.message;}}finally{if(lock)trigger.disabled=false;}};}

async function request(path,{method='GET',data,params={},operationKey}={}) {
  const u=new URL(path,location.origin);for(const [k,v] of Object.entries(params))if(v!==undefined&&v!==null&&v!=='')u.searchParams.set(k,v);
  const headers={};if(workspaceId)headers['X-PMRS-Workspace']=workspaceId;if(method==='POST'){headers['Content-Type']='application/json';headers['X-PMRS-CSRF']=csrf;if(operationKey)headers['Idempotency-Key']=operationKey;}
  const r=await fetch(u,{method,headers,body:data===undefined?undefined:JSON.stringify(data),cache:'no-store'});
  const value=await r.json();if(!r.ok){const e=Error((value.message||value.error||'操作失败')+(value.guidance?'\n'+value.guidance:''));e.code=value.error;e.status=r.status;throw e;}return value;
}
const operations=new OperationLifecycle(indexedOperationStorage(window.indexedDB),{
  send:op=>request('/api/action/'+op.name,{method:'POST',data:op.payload,operationKey:op.key}),
  discover:()=>request('/api/operations'),
  query:(key,op)=>request('/api/operation',{params:op?.receipt_id?{id:op.receipt_id}:{key}}),
  ack:(op,receipt)=>request('/api/operation/ack',{method:'POST',data:{id:receipt.operation.id,digest:receipt.digest}})
},()=>crypto.randomUUID());
async function action(name,data={}) {
  try{return await operations.execute(name,{project,instance:$('instance').value,...data});}
  finally{await renderOperationRecovery();if(await operations.current())$('notice').textContent='操作编号已保存。若当前窗口仍打开，请关闭后在页首查询原操作；不要重新创建操作。';}
}
async function applyRecovered(result,operation) {
  if(operation?.name==='upload-archive'&&result?.upload_id){showImportConfirmation(result);return;}
  if(!result?.project&&operation?.payload.project&&operation.payload.project!==project)await listProjects(operation.payload.project);
  if(result?.project)await listProjects(result.project);
  else if(project)await openProject();
  if(result?.instance_id){$('instance').value=result.instance_id;await refresh();}
  if(result?.download){const a=el('a','下载已完成操作的备份');a.href=result.download;$('notice').replaceChildren(a);}
  else $('notice').textContent='已确认原操作结果；没有重新创建或再次启动。';
}
async function renderOperationRecovery(inspected) {
  const box=$('operation-recovery');if(!box)return;
  const op=await operations.current();box.replaceChildren();box.hidden=!op;if(!op)return;
  box.append(el('strong','有一项尚未确认的操作'),el('p','操作 '+op.name+' · '+op.key,'ref'),el('p','结果丢失不代表执行失败。先查询原编号；确认未到达服务端后才可使用原编号重放。'));
  const receipt=inspected?.operation?.key===op.key?inspected.receipt:null;
  if(receipt)box.append(el('p','服务端状态：'+receipt.state+(receipt.error?' · '+(typeof receipt.error==='string'?receipt.error:JSON.stringify(receipt.error)):'')));
  box.append(button('查询原操作',async()=>{const found=await operations.recover();await renderOperationRecovery(found);if(found?.result!==undefined)await applyRecovered(found.result,found.operation);}));
  if(receipt?.state==='NOT_FOUND'&&!op.remote_only)box.append(button('使用原编号重放',async()=>{const original=await operations.current();const result=await operations.replay();await renderOperationRecovery();await applyRecovered(result,original);}));
  if(receipt?.state==='FAILED')box.append(button('确认已失败，结束此次操作',async()=>{await operations.acknowledgeFailure();await renderOperationRecovery();$('notice').textContent='原失败记录已保留。请检查当前项目状态，修改输入后明确提交新操作。';if(project)await openProject();}));
}
function readApi(path,params={}){return request('/api/'+path,{params:{project,instance:$('instance').value,...params}});}
function card(title,ref){const c=el('article',undefined,'card');c.append(el('h3',title));if(ref){const d=el('details');d.append(el('summary','记录详情'),el('div',ref,'ref'));c.append(d);}return c;}
function note(c,text){c.append(el('p',text,'muted'));}
function field(form,label,id,type='text',value=''){const l=el('label',label);const n=el(type==='textarea'?'textarea':type==='select'?'select':'input');n.id=id;n.name=id;if(type!=='textarea'&&type!=='select')n.type=type;n.value=value;l.append(n);form.append(l);return n;}
function options(select,rows){for(const [value,text] of rows){const o=el('option',text);o.value=value;select.append(o);}}
function dialog(title){$('dialog-title').textContent=title;$('dialog-content').replaceChildren();if(!$('dialog').open)$('dialog').showModal();return $('dialog-content');}
function closeDialog(){$('dialog').close();}
function submit(form,label,fn){const b=el('button',label,'primary');form.append(b);form.addEventListener('submit',guarded(async()=>{b.disabled=true;try{await fn();}finally{b.disabled=false;}}));}
async function fileData(file,limitMiB=32){if(!file)return null;if(file.size>limitMiB*1024*1024)throw Error('请选择不超过 '+limitMiB+' MiB 的文件。');return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});}
async function typeset(node){if(window.MathJax&&MathJax.typesetPromise){await MathJax.startup.promise;await MathJax.typesetPromise([node]);}}
async function listProjects(selectKey){const d=await request('/api/workspace');$('project').replaceChildren();options($('project'),[['','选择或创建项目'],...d.projects.map(p=>[p.key,p.title+(p.synthetic?' · 模拟演示':'')])]);project=selectKey||project;localStorage.setItem('pmrs_4_0_project',project);if(!d.projects.some(p=>p.key===project))project='';$('project').value=project;$('empty-workspace').hidden=!!project;$('workspace').hidden=!project;if(project)await openProject();}
async function openProject(){const selectedProject=project,generation=++projectGeneration;const s=await request('/api/status',{params:{project:selectedProject}});if(generation!==projectGeneration||selectedProject!==project)return;const prior=$('instance').value;$('instance').replaceChildren();options($('instance'),[['','全部共享知识'],...s.workflow.instances.map(i=>[i.instance_id,instanceLabel(i)])]);$('instance').value=s.workflow.instances.some(i=>i.instance_id===prior)?prior:(s.workflow.instances[0]?.instance_id||'');await refresh();}
function requireInstance(){if(!$('instance').value)throw Error('请先选择一个研究流程。');}
function record(row){const readScope={project,instance:$('instance').value,commit:snapshot};const c=card(kindNames[row.kind]||row.kind,row.ref);c.append(el('p',row.excerpt,'excerpt'));for(const f of row.result_families||[]){const family=el('details');family.append(el('summary','结果族 · '+f.label+'（仅导航）'));for(const m of f.members||[])family.append(el('p',(m.display_role||'成员')+' · '+(m.record_ref||m),'ref'));note(family,'分组不授予等价关系、证明或撤回资格。');c.append(family);}if(row.kind==='Assessment'){note(c,'本记录只说明下列实际检查范围；不表示整个论证通过。');const assessment=el('details');assessment.append(el('summary','检查结论与已查、未查部分'),el('pre',JSON.stringify({verdict:row.data.verdict,checked:row.data.checked,unchecked:row.data.unchecked},null,2),'diagnostic'));c.append(assessment);}const checked=new Set(),unchecked=new Set(),supportStates=new Set();const aspects={original_target:'原始目标',full_argument:'完整论证',formulation_and_counterevidence:'表述与反面证据'};for(const b of row.support_boundaries||[]){supportStates.add(show(b.support_state||b.result||'未确定'));for(const x of b.checked_scope||[])for(const a of x.aspects||[])checked.add(aspects[a]||a);for(const x of b.not_checked||[])for(const a of x.aspects||[])unchecked.add(aspects[a]||a);}for(const x of supportStates)note(c,'支持状态：'+x);if(checked.size)note(c,'已检查：'+[...checked].join('、'));if(unchecked.size)note(c,'尚未检查：'+[...unchecked].join('、'));if(!(row.support_boundaries||[]).length)note(c,'尚无与当前范围匹配的数学检查记录。');for(const u of row.source_uses||[]){note(c,'来源用途：'+(u.usage.some(x=>x.usage_mode==='METHOD_INSPIRATION')?'方法启发；不自动授予证明支持':'按声明的精确材料范围使用'));}if(row.support_boundaries?.length||row.source_uses?.length){const info=el('details');info.append(el('summary','精确支持范围与来源引用'),el('pre',JSON.stringify({support:row.support_boundaries,sources:row.source_uses},null,2),'diagnostic'));c.append(info);}const d=el('details');d.append(el('summary','阅读全文与公式'));const body=el('div',undefined,'body');d.append(body);let loaded=false;d.addEventListener('toggle',guarded(async()=>{if(d.open&&!loaded){const r=await readApi('body',{...readScope,ref:row.ref});body.textContent=r.body;loaded=true;await typeset(body);}}));c.append(d);return c;}
function frontier(row){const c=card(show(row.resolution),row.obligation_id);c.append(el('div',row.criterion,'body'));note(c,'工作状态：'+show(row.work_state));for(const a of row.attempt_accounts||[])note(c,typeof a.account==='string'?a.account:typeof a==='string'?a:'已有尝试记录，可在任务详情中查看。');note(c,row.blockers.length?'有未解除的材料或范围阻塞。':'继续工作需要已有授权、预算和具体待解决条件。');return c;}
function source(row){const c=card(row.filename||'原始材料',row.source_ref);if(row.text!==null){const d=el('details');d.append(el('summary','阅读保存的原文'),el('div',row.text,'body'));c.append(d);}else{const a=el('a','打开或下载完整原件');a.href='/api/source-file?project='+project+'&instance='+$('instance').value+'&ref='+row.source_ref+'&commit='+snapshot;a.target='_blank';a.rel='noopener';c.append(a);}note(c,'完整保留 '+row.bytes+' 字节；来源中的数学主张不自动变成当前证明。');return c;}
function report(row){const c=card(row.classification==='COMPLETED_CURRENT_REPORT'?'已完成的当前报告':'报告制作与检查',row.report_id);note(c,'状态：'+show(row.state));for(const x of row.missing_checks||[])note(c,'待完成：'+x);for(const f of row.failure_history||[])note(c,'制作问题：'+(f.message||f.code||f.reason||'查看详细诊断'));for(const gap of row.open_research_requests||[]){note(c,'待研究：'+gap.description);note(c,'报告提出该缺口，不自动授权模型调用。');}if(row.open_research_requests?.length)c.append(button('查看报告提出的开放问题',async()=>{view='frontier';await refresh();}));for(const d of row.downloads||[]){const a=el('a',d.profile==='lecture'?'打开讲义版 PDF':'打开精简版 PDF');a.href=d.url;a.target='_blank';a.rel='noopener';c.append(a);}note(c,'报告制作问题独立显示；已有授权支持的研究可以继续。');if(row.active&&$('instance').value){c.append(button('请求修订当前报告',()=>reportRevision(false)),button('保留记录并放弃当前报告',()=>reportRevision(true)));}return c;}
function reportRevision(abandon){requireInstance();const box=dialog(abandon?'保留记录并放弃报告':'请求修订当前报告');const f=el('form',undefined,'stack');let profile;if(!abandon){profile=field(f,'修订版本','report-profile','select');options(profile,[['lecture','讲义版（精简版随后重新生成）'],['minimal','仅精简版']]);}const reason=field(f,'修订或放弃的原因','report-reason','textarea');reason.required=true;note(f,'旧稿、检查和失败记录会保留。修订继续使用已有授权及剩余预算。');submit(f,abandon?'记录放弃决定':'开始修订',async()=>{await action(abandon?'abandon-report':'revise-report',{profile:profile?.value,reason:reason.value});closeDialog();await refresh();});box.append(f);}
function taskRequest(s,t){return (s?.execution?.requests||[]).find(r=>r.request_id===t.request_id);}
function updateTaskCard(c,t,s){
  const r=taskRequest(s,t),label=c.querySelector('[data-request-status]');
  label.textContent='执行状态：'+show(r?.execution_state||'PREPARED')+(r?.unknown_disposition==='ABANDON_UNKNOWN'?' · 已放弃等待，消耗保留且不重发':'');
  const controls=c.querySelector('[data-task-actions]'),state=[r?.execution_state,r?.unknown_disposition,r?.fenced].join('|');
  if(controls.dataset.actionState===state)return;
  controls.dataset.actionState=state;controls.replaceChildren();
  if(r?.execution_state==='CAPTURED')controls.append(button('接纳已捕获结果',async()=>{await action('recover',{instance:t.instance_id,request_id:r.request_id});await refresh();}));
  if(r?.execution_state==='UNKNOWN'&&r?.unknown_disposition!=='ABANDON_UNKNOWN')controls.append(button('处理不确定请求',()=>reconcile(r.request_id,t.instance_id)));
}
function task(t){
  const c=card(t.activity_label+' · '+t.stage_id+' / '+t.role,t.task_id);c.dataset.taskId=t.task_id;
  if(!$('instance').value)note(c,'所属流程：'+t.instance_id);
  const p=t.model_policy||{};note(c,'冻结配置：'+p.model+' · '+p.reasoning_effort+' · '+p.service_tier);
  const label=el('p',undefined,'muted');label.dataset.requestStatus=t.request_id;c.append(label);
  note(c,'客户端未返回的有效配置及用量保持未知。');
  const controls=el('div',undefined,'task-actions');controls.dataset.taskActions=t.task_id;c.append(controls);updateTaskCard(c,t,currentStatus);return c;
}
function progressFingerprint(s){return JSON.stringify({tasks:s?.tasks||[],requests:s?.execution?.requests||[]});}
function syncViewSelection(){for(const b of $('tabs').querySelectorAll('button')){const active=b.dataset.view===view;b.classList.toggle('active',active);b.setAttribute('aria-current',active?'page':'false');}$('view-title').textContent=names[view];}
function clearStageSelection(){graphSelection=null;if(typeof resetWorkflowGraphSelection==='function')resetWorkflowGraphSelection();else{$('stage-detail').replaceChildren();$('stage-detail').hidden=true;}}
async function selectView(next,{stage=null,keepGraph=false}={}){view=next;if(!keepGraph)clearStageSelection();graphSelection=next==='tasks'?stage:null;syncViewSelection();await refresh();}
function candidate(c){const n=card(c.label||'候选命题',c.statement_ref);n.append(el('div',c.body,'body'));note(n,'状态：'+show(c.candidate_state||'保存的候选')+'。采用表示选择研究目标，不表示命题已证明。');note(n,'证据与未查范围请结合当前知识及开放问题阅读；尚无比较结论时保持未知。');for(const r of c.related_records||[]){const d=el('details');d.append(el('summary',(kindNames[r.kind]||r.kind)+' · '+(r.data.verdict||r.data.scope||'相关材料')),el('div',r.body,'body'));if(r.data.unchecked?.length)note(d,'尚未检查：'+r.data.unchecked.map(x=>x.aspect+' — '+x.reason).join('；'));n.append(d);}const scopes=el('details');scopes.append(el('summary','精确候选、比较与支持范围'),el('pre',JSON.stringify({statement_ref:c.statement_ref,comparison_refs:c.comparison_refs,change_axes:c.change_axes,support:c.support_boundaries},null,2),'diagnostic'));n.append(scopes);n.append(button('采用为新的定题研究',async()=>{const box=dialog('采用此候选');const newName=field(box,'新的定题研究名称','adopt-name','text',c.label||'候选命题的定题研究');box.append(el('div',c.body,'body'),el('p','将复用同一项目材料，并创建暂停的 TRW；原流程保留，新流程需要另行启动。'));box.append(button('采用并创建暂停的 TRW',async()=>{if(!newName.value.trim())throw Error('请为新流程填写名称。');const r=await action('handoff',{direction:'TFDW_TO_TRW',name:newName.value,candidate_ref:c.statement_ref,note:'用户在候选全文页面选择此精确候选。'});closeDialog();await openProject();$('instance').value=r.instance_id;await refresh();},'primary'));}));return n;}
async function refresh(append=false){syncViewSelection();const scope=project+'|'+$('instance').value;if(scope!==navigationScope){clearStageSelection();navigationScope=scope;}if(!project)return;const generation=++refreshGeneration,selectedProject=project,selectedInstance=$('instance').value,selectedView=view;const stale=()=>generation!==refreshGeneration||selectedProject!==project||selectedInstance!==$('instance').value||selectedView!==view;const selectedRead=(path,params={})=>readApi(path,{project:selectedProject,instance:selectedInstance,...params});requireInstanceOptional();if(!append){const latest=await selectedRead('status');if(stale())return;currentStatus=latest;requireInstanceOptional();snapshot=currentStatus.commit;latestCommit=snapshot;contentProgressFingerprint=progressFingerprint(latest);renderProgress(latest);$('snapshot').textContent='正文快照 '+snapshot.slice(0,12);$('content-update').hidden=true;$('content').replaceChildren();nextOffset=null;}
$('view-title').textContent=names[view];let rows=[];let data;const params={commit:snapshot};const frozenReadScope={project:selectedProject,instance:selectedInstance,commit:snapshot};if(view==='tasks'){rows=currentStatus.tasks.filter(t=>!graphSelection||t.stage_id===graphSelection);for(const r of rows)$('content').append(task(r));}else if(view==='candidates'){rows=currentStatus.candidates;for(const r of rows)$('content').append(candidate(r));if($('instance').value&&currentStatus.workflow.instances.some(i=>i.kind==='TRW'))$('content').append(button('从当前目标开展表述发现',()=>reformulate()));}else if(view==='diff'){const mission=currentStatus.missions.find(m=>m.mission_id===selectedInstanceRow()?.current_mission_id);if(mission?.input_knowledge_commit){data=await selectedRead('diff',{...params,from:mission.input_knowledge_commit});if(stale())return;rows=[data];const c=card('本轮知识变化');note(c,'新增内容 '+data.content_added.length+'；复用内容 '+data.content_reused.length+'；支持变化 '+data.support_changes.length+'；撤回 '+data.support_withdrawals.length);note(c,'机械差异不等于自动认定新定理。');for(const [label,refs] of [['新增正文',data.content_added],['复用正文',data.content_reused]])for(const ref of refs){const d=el('details');d.append(el('summary',label+' · '+ref.slice(-12)),el('p',ref,'ref'));let loaded=false;d.addEventListener('toggle',guarded(async()=>{if(d.open&&!loaded){const full=await readApi('body',{...frozenReadScope,ref});d.append(el('div',full.body,'body'));loaded=true;await typeset(d);}}));c.append(d);}const scope=el('details');scope.append(el('summary','支持变化与撤回范围'),el('pre',JSON.stringify({changes:data.support_changes,withdrawals:data.support_withdrawals},null,2),'diagnostic'));c.append(scope);$('content').append(c);}}else{data=await selectedRead(selectedView,{...params,query:$('query').value,offset:append?nextOffset:0,limit:20});if(stale())return;rows=data.records||data.obligations||data.sources||data.artifacts||data.reports||[];for(const r of rows)$('content').append(({current:record,frontier,sources:source,history:nativeHistory,reports:report})[view](r));nextOffset=data.next_offset;}if(!rows.length&&!append)$('content').append(el('p',view==='candidates'?'当前尚无候选。开展现象研究后，可在这里阅读完整候选、证据和未知比较。':'当前范围尚无记录。可以补充材料或设置本轮研究。','empty'));$('more').hidden=nextOffset===undefined||nextOffset===null;await typeset($('content'));}
function requireInstanceOptional(){for(const id of ['start-round','pause','continue','end','request-report','handoff-workflow'])$(id).disabled=!$('instance').value;$('edit-discovery').hidden=selectedInstanceRow()?.kind!=='TFDW'||!!selectedInstanceRow()?.current_mission_id;}
function nativeHistory(r){const c=card(r.title||r.event_type,r.event_id);note(c,'原生记录 #'+r.sequence+' · '+r.event_type+(r.at?' · '+r.at:''));note(c,r.summary||'');note(c,'知识快照：'+r.commit);note(c,r.instance_ids?.length?'关联流程：'+r.instance_ids.join('、'):'项目级记录');const d=el('details');d.append(el('summary','查看记录详情'),el('pre',JSON.stringify(r.details||{},null,2),'body'));c.append(d);return c;}
function sourceForm(){const box=dialog('补充原始材料');const f=el('form',undefined,'stack');const file=field(f,'选择材料文件（最多 32 MiB）','source-file','file');const text=field(f,'或粘贴文字材料','source-text','textarea');submit(f,'保存材料',async()=>{const chosen=file.files[0];await action('add-source',{filename:chosen?.name||'文字材料',media_type:chosen?.type||'text/plain',data:await fileData(chosen),text:text.value});closeDialog();$('instance').value='';view='sources';await refresh();});box.append(f);}
function showImportConfirmation(r){if(r.mode!=='restore')throw Error('只支持恢复当前原生项目备份。');const area=dialog('确认恢复范围');const labels={format:'备份类型',files:'文件数',title:'内容',processes_restored:'恢复运行中的进程'};for(const [k,v] of Object.entries(r.summary||{}))area.append(el('p',(labels[k]||k)+'：'+(k==='format'?'当前原生项目备份':v)));area.append(el('p','恢复到独立的新项目并保持暂停。研究记录与原件保留，不会自动恢复进程或授权新调用。'));area.append(button('恢复到新项目',async()=>{const done=await action('restore',{upload_id:r.upload_id});closeDialog();await listProjects(done.project);},'primary'));}
function importForm(){const box=dialog('恢复原生项目备份'),f=el('form',undefined,'stack');const file=field(f,'选择原生备份 ZIP 文件（最多 128 MiB）','import-file','file');file.accept='.zip';note(f,'仅支持当前原生备份。先检查备份，再恢复到新项目；原项目和上传原件均保留。');submit(f,'检查备份',async()=>{if(!file.files[0])throw Error('请选择原生备份。');const r=await action('upload-archive',{data:await fileData(file.files[0],128),mode:'restore'});showImportConfirmation(r);});box.append(f);}
async function settings(){const d=await request('/api/settings');modelPolicy=d.policy;const box=dialog('PMRS 4.0.0 · 执行环境与模型设置');box.append(el('p',d.client.installed?'官方 Codex 客户端：'+(d.client.version||'已安装'):'尚未检测到官方 Codex CLI。'));box.append(el('p',d.client.authenticated?'已登录，可复用当前官方会话。':'尚未登录。PMRS 不接收或保存账号密码。'));const actions=el('div',undefined,'actions');actions.append(button('通过官方 Codex 登录',async()=>{const r=await action('login');$('notice').textContent=r.login_state==='ALREADY_AUTHENTICATED'?'已复用现有官方登录。':'已启动官方登录页面。完成后回到 PMRS，点击重新检查。';}),button('重新检查登录',settings),button('检测执行与 PDF 环境',async()=>{const r=await action('check-environment');const c=card('环境诊断');c.append(el('pre',JSON.stringify(r,null,2),'diagnostic'));box.append(c);}));box.append(actions);const a=el('a','官方 Codex 安装说明');a.href='https://developers.openai.com/codex/cli/';a.target='_blank';a.rel='noopener';box.append(a);await environmentSettings(box,d.setup);note(box,'策略按职责配置，并非数学研究效果的比较实验结论。ultra 当前不可用；不支持的模型或档位明确阻塞，不自动降级。');const table=el('table');const head=el('tr');for(const t of ['阶段','角色','计划强度'])head.append(el('th',t));table.append(head);for(const r of d.policy.rules){const tr=el('tr');for(const t of [r.stage_id,r.role,r.call_model?r.reasoning_effort:'不调用模型'])tr.append(el('td',t));table.append(tr);}box.append(table);if(project&&$('instance').value)box.append(button('修改已有轮次的未来任务配置',configureForm));}
function help(){const box=dialog('从开始到交接');for(const [title,text] of [['1 · 选择研究方式','已给定精确命题时选择 TRW。只有现象、样例或猜想族时选择 TFDW。两类实例共用项目材料。'],['2 · 补充材料','题目以完整文字保存；补充材料可上传 PDF、文本或其他原件。检查只针对实际读到的精确版本和范围。'],['3 · 设置这一轮','写出目的，选择调用上限和并发数，然后开始。后台处理必要工作；关闭页面不会取消任务。'],['4 · 阅读与控制','当前知识展示全文和公式，开放问题说明缺口，任务页面展示冻结配置和真实执行状态。不确定请求先处理，避免重发。'],['5 · 报告与候选交接','报告有独立制作入口。TFDW 采用候选会创建暂停的 TRW；先阅读完整命题，再明确启动新研究。'],['保存与退出','导出备份后可恢复到新项目。暂停停止新派发；退出后台服务须等待当前任务结束。']]){box.append(el('h3',title),el('p',text));}box.append(button('运行命题示例',()=>createForm('TRW',true)),button('运行候选与交接示例',()=>createForm('TFDW',true)));}

function selectedInstanceRow(){return currentStatus?.workflow.instances.find(x=>x.instance_id===$('instance').value);}
function instanceLabel(i){return (i.name||i.display_name||i.title||i.target_title||'未命名流程')+(i.object_text?' · '+i.object_text.replace(/\s+/g,' ').slice(0,70):'')+' · '+i.kind+' · '+show(i.status)+' · '+i.instance_id.slice(-6);}
function discoveryFields(form,prefix,{phenomenon='',background='',axes='',sources=[],initialRefs={}}={}) {
  const group=el('fieldset',undefined,'stack');group.append(el('legend','表述发现的三项原始输入'));const inputs={};
  for(const [key,label,value,placeholder] of [
    ['phenomenon','现象、样例或猜想族（原文）',phenomenon,'保存观察到的现象原文。'],
    ['immutable_background','必须保持不变的背景与约束',background,'写明对象、前提及不可改变的条件；若无额外限制，请明确填写“无额外背景约束”。'],
    ['allowed_axes','允许探索或改变的范围',axes,'写明允许变化的假设、结论、参数或对象范围；不自动补成任意范围。']
  ]) {
    const mode=field(group,label+'的来源',prefix+'-'+key+'-source','select');options(mode,[['text','填写原文'],...sources.map(source=>[source.source_ref,'已有材料 · '+source.title])]);
    const text=field(group,label,prefix+'-'+key,'textarea',value);text.placeholder=placeholder;
    const download=el('a','打开所选材料原件');download.target='_blank';download.rel='noopener';download.hidden=true;group.append(download);
    const update=()=>{text.disabled=mode.value!=='text';download.hidden=!text.disabled;if(text.disabled)download.href='/api/source-file?'+new URLSearchParams({project,ref:mode.value});};mode.onchange=update;
    if(initialRefs[key+'_ref']&&sources.some(source=>source.source_ref===initialRefs[key+'_ref']))mode.value=initialRefs[key+'_ref'];update();inputs[key]={mode,text};
  }
  const draft=field(group,'仅保存为未完整草稿，稍后补齐三项再启动',prefix+'-draft','checkbox');
  note(group,'三项原文分别保存为材料。草稿可以暂停保存；未补齐时无法启动研究。');form.append(group);
  return {group,value(){const scope={};for(const [key,{mode,text}] of Object.entries(inputs)){if(mode.value==='text')scope[key]=text.value;else scope[key+'_ref']=mode.value;if(!draft.checked&&mode.value==='text'&&!text.value.trim())throw Error('请填写完整现象、不变背景和允许探索范围，或明确选择仅保存草稿。');}return scope;},draft:()=>draft.checked};
}
function createForm(kind='TRW',demo=false){
  const box=dialog(demo?'创建独立模拟演示':'新建研究项目'),f=el('form',undefined,'stack');
  const title=field(f,'项目名称','create-title','text',demo?'模拟演示 · '+(kind==='TRW'?'整数命题':'候选发现'):'');title.required=true;
  const name=field(f,'首个流程名称','create-name','text',kind==='TRW'?'原始命题研究':'现象与边界发现');name.required=true;
  const k=field(f,'研究方式','create-kind','select');options(k,[['TRW','定题研究：围绕精确命题'],['TFDW','表述发现：从现象与边界出发']]);k.value=kind;
  const target=el('fieldset',undefined,'stack');target.append(el('legend','精确目标'));
  const text=field(target,'完整题目','create-text','textarea',demo?'For every integer n, n + 0 = n.':'');text.placeholder='包括对象、假设、量词和结论。';
  const file=field(target,'或选择 UTF-8 题目文件','create-file','file');file.accept='.txt,.md,.tex';f.append(target);
  const discovery=discoveryFields(f,'create-discovery',{phenomenon:demo?'Observe positive definite real symmetric 2 by 2 matrices and their eigenvalues.':'',background:demo?'Real symmetric 2 by 2 matrices; preserve the meanings of positive definiteness and real eigenvalues.':'',axes:demo?'Explore necessary or sufficient relationships between positive definiteness and positive eigenvalues, using positive, negative and unknown examples.':''});
  const update=()=>{target.hidden=k.value!=='TRW';discovery.group.hidden=k.value!=='TFDW';};k.onchange=update;update();
  note(f,demo?'模拟演示不调用真实模型，输出带有测试隔离标记。':'原题与现象完整保存。研究开始前集中设置本轮目的、策略与预算。');
  submit(f,demo?'创建并打开模拟演示':'创建项目',async()=>{const payload={title:title.value,name:name.value,kind:k.value};if(k.value==='TFDW'){payload.discovery_scope=discovery.value();payload.text=payload.discovery_scope.phenomenon;payload.draft=discovery.draft();}else{if(!text.value.trim()&&!file.files[0])throw Error('请填写完整题目或选择原题文件。');payload.text=text.value;payload.data=await fileData(file.files[0]);}const r=await action(demo?'example':'create',payload);closeDialog();await listProjects(r.project);if(demo)await startForm();});box.append(f);
}
async function workflowInputs(){const result={statements:[],sources:[]};let offset=0;do{const page=await readApi('workflow-inputs',{offset,limit:100});result.statements.push(...page.statements);result.sources.push(...page.sources);offset=page.next_offset;}while(offset!==null&&offset!==undefined);return result;}
async function newWorkflowForm(){
  const inputs=await workflowInputs(),box=dialog('在当前项目新增研究流程'),f=el('form',undefined,'stack');
  const name=field(f,'流程名称','workflow-name');name.required=true;
  const kind=field(f,'研究方式','workflow-kind','select');options(kind,[['TRW','定题研究 TRW'],['TFDW','表述发现 TFDW']]);
  const targetBox=el('fieldset',undefined,'stack');targetBox.append(el('legend','选择或输入精确命题'));
  const target=field(targetBox,'目标来源','workflow-target','select');options(target,[['','输入新的精确命题'],...inputs.statements.map(s=>[s.ref,s.title||s.body.slice(0,100)])]);
  const body=field(targetBox,'完整命题原文','workflow-target-text','textarea');const preview=el('div',undefined,'body');targetBox.append(preview);target.onchange=()=>{body.hidden=!!target.value;preview.textContent=inputs.statements.find(x=>x.ref===target.value)?.body||'';};f.append(targetBox);
  const discovery=discoveryFields(f,'workflow-discovery',{sources:inputs.sources});kind.onchange=()=>{targetBox.hidden=kind.value!=='TRW';discovery.group.hidden=kind.value!=='TFDW';};kind.onchange();
  note(f,'新流程暂停保存，与当前项目共用材料。创建新流程不修改原目标，也不表示采用候选或授权调用。');
  submit(f,'创建暂停的新流程',async()=>{const payload={kind:kind.value,name:name.value};if(kind.value==='TRW'){if(target.value)payload.target_ref=target.value;else{if(!body.value.trim())throw Error('请选择已有目标或填写完整命题。');payload.target_text=body.value;}}else{payload.discovery_scope=discovery.value();payload.draft=discovery.draft();}const r=await action('new-workflow',payload);closeDialog();await openProject();$('instance').value=r.instance_id;graphSelection=null;await refresh();});box.append(f);
}
async function discoveryConfigForm(){
  requireInstance();const inputs=await workflowInputs(),box=dialog('补齐暂停草稿的发现范围'),f=el('form',undefined,'stack');
  const instance=selectedInstanceRow(),scope={...(instance?.discovery_scope||{})};if(!scope.phenomenon_ref&&instance?.discovery_brief_ref)scope.phenomenon_ref=instance.discovery_brief_ref;
  const bodyFor=ref=>inputs.sources.find(s=>s.source_ref===ref)?.body||'';
  const fields=discoveryFields(f,'edit-discovery',{phenomenon:bodyFor(scope.phenomenon_ref),background:bodyFor(scope.immutable_background_ref),axes:bodyFor(scope.allowed_axes_ref),sources:inputs.sources,initialRefs:scope});
  note(f,'用于尚未启动轮次的暂停草稿；已经授权的范围与冻结任务不能通过这里改写。');
  submit(f,'保存发现范围',async()=>{await action('configure-discovery',{discovery_scope:fields.value()});closeDialog();await refresh();});box.append(f);
}
async function policyEditor(parent,{kind,existing=[],prefix='policy'}={}) {
  if(!modelPolicy)modelPolicy=(await request('/api/settings')).policy;
  const details=el('details');details.append(el('summary','逐阶段模型策略 · 编辑未来任务'));parent.append(details);
  const area=el('div',undefined,'stack');details.append(area);
  const rules=modelPolicy.rules.filter(r=>r.call_model&&r.workflow_kind===kind);
  const stage=field(area,'阶段',prefix+'-stage','select');options(stage,[...new Set(rules.map(x=>x.stage_id))].map(x=>[x,x]));
  const role=field(area,'角色',prefix+'-role','select'),purpose=field(area,'实际工作用途',prefix+'-purpose','select');
  const model=field(area,'模型',prefix+'-model','text','gpt-6-astra');
  const effort=field(area,'推理强度',prefix+'-effort','select');options(effort,['low','medium','high','xhigh','max'].map(x=>[x,x]));
  const tier=field(area,'服务档位',prefix+'-tier','select');options(tier,[['default','default'],['priority','priority']]);
  const explanation=el('p',undefined,'muted'),list=el('div',undefined,'override-list');area.append(explanation,list);
  let changes=[],resets=[];
  const scope=()=>({workflow_kind:kind,stage_id:stage.value,role:role.value,purpose:purpose.value});
  const merged=()=>amendOverrides(existing,changes,resets);
  function showRows(){list.replaceChildren();for(const item of merged())list.append(el('p',item.scope.stage_id+' / '+item.scope.role+' / '+item.scope.purpose+' → '+item.model+' · '+item.reasoning_effort+' · '+item.service_tier));if(!merged().length)list.append(el('p','未设覆盖：使用职责默认策略。'));}
  function selection(){const row=rules.find(x=>x.stage_id===stage.value&&x.role===role.value),exception=modelPolicy.purpose_exceptions.find(x=>x.stage_id===stage.value&&x.role===role.value&&x.purpose===purpose.value);const baseEffort=purpose.value==='LAYOUT_ONLY'?'high':exception?.reasoning_effort||row.reasoning_effort;const override=merged().find(x=>scopeKey(x.scope)===scopeKey(scope()));model.value=override?.model||row.model;effort.value=override?.reasoning_effort||baseEffort;tier.value=override?.service_tier||row.service_tier;explanation.textContent='此精确用途的默认配置：'+row.model+' · '+baseEffort+' · '+row.service_tier+(override?'；当前已设置覆盖。':'。');}
  function purposes(){purpose.replaceChildren();const uses=[['DEFAULT','默认职责'],...modelPolicy.purpose_exceptions.filter(x=>x.stage_id===stage.value&&x.role===role.value).map(x=>[x.purpose,x.purpose])];if(role.value.startsWith('REPORT_'))uses.push(['CONTENT','报告内容'],['LAYOUT_ONLY','仅版式']);if(stage.value==='D0')uses.push(['BRIEF_ORGANIZATION','整理发现输入']);options(purpose,uses);selection();}
  function roles(){role.replaceChildren();options(role,rules.filter(x=>x.stage_id===stage.value).map(x=>[x.role,x.role]));purposes();}
  stage.onchange=roles;role.onchange=purposes;purpose.onchange=selection;roles();showRows();
  area.append(button('加入或更新此作用域',()=>{const row={explicit:true,scope:scope(),model:model.value.trim(),reasoning_effort:effort.value,service_tier:tier.value};if(!row.model)throw Error('请填写模型名称。');changes=amendOverrides(changes,[row]);resets=resets.filter(x=>scopeKey(x)!==scopeKey(row.scope));showRows();selection();}),button('仅将此作用域恢复默认',()=>{const current=scope();changes=changes.filter(x=>scopeKey(x.scope)!==scopeKey(current));resets=resets.filter(x=>scopeKey(x)!==scopeKey(current));resets.push(current);showRows();selection();}));
  note(area,'编辑后点击“加入或更新此作用域”，再提交表单。其他作用域不被清空。冻结任务、预算和累计尝试不变；不支持的设置会在发送前拒绝，ultra 不自动启用。');
  return {value:()=>changes,resetScopes:()=>resets};
}
async function startForm(){
  requireInstance();const box=dialog('设置本轮研究'),f=el('form',undefined,'stack');
  const intent=field(f,'本轮研究目的','round-intent','textarea','研究当前对象，说明实际得到的结果、适用条件和仍未解决的问题。');intent.required=true;
  const calls=field(f,'本轮最多调用次数','round-calls','number','12');calls.min='1';calls.max='1000';calls.required=true;
  const workers=field(f,'最多同时处理的任务','round-workers','number','2');workers.min='1';workers.max='4';workers.required=true;
  const reportFirst=field(f,'在继续、结束或采用候选前，要求完成本轮报告（可选）','round-report-first','checkbox');
  const editor=await policyEditor(f,{kind:selectedInstanceRow().kind,prefix:'round-policy'});
  note(f,currentStatus.synthetic?'模拟执行器：不发生真实模型调用。':'各阶段、角色和用途使用职责默认策略或本次明确覆盖；实际费用未知，调用上限生效。');
  note(f,'研究与明确请求的报告共享本轮调用上限；报告不会自动制作。点击即授权并启动这一轮必要工作。');
  submit(f,'开始本轮研究',async()=>{await action('start',{intent:intent.value,max_calls:Number(calls.value),max_workers:Number(workers.value),report_first:reportFirst.checked,model_overrides:editor.value()});closeDialog();await openProject();});box.append(f);
}
async function configureForm(){
  requireInstance();const box=dialog('修改已有轮次的未来任务配置'),f=el('form',undefined,'stack'),instance=selectedInstanceRow();
  const mission=currentStatus.missions.find(m=>m.mission_id===instance.current_mission_id);
  if(!mission){box.append(el('p','当前流程尚未授权轮次。请在“开始本轮研究”中设置首批任务策略。'));return;}
  const grant=currentStatus.budget.grants.find(g=>g.budget_grant_id===mission.budget_grant_id);const existing=currentStatus.model_configuration?.model_overrides||grant?.execution_policy?.model_overrides||[];
  const editor=await policyEditor(f,{kind:instance.kind,existing,prefix:'config'});
  submit(f,'保存未来配置',async()=>{await action('configure',{model_overrides:editor.value(),reset_scopes:editor.resetScopes()});closeDialog();view='tasks';graphSelection=null;await refresh();});box.append(f);
}
async function reconcile(rid,instance=$('instance').value){
  const inputs=await workflowInputs(),box=dialog('处理结果不确定的请求'),f=el('form',undefined,'stack');
  note(f,'此请求可能已发出。放弃等待后仍保留 UNKNOWN、消耗与尝试记录，不会自动重发，也不等于确认未发送。');
  const choice=field(f,'处理方式','reconcile-choice','select');options(choice,[['ABANDON_UNKNOWN','放弃等待：仍为 UNKNOWN，保留消耗且不重发'],['CONFIRMED_NOT_SENT','依据实际外部证据确认未发送']]);
  const evidence=field(f,'实际未发送证据原件','reconcile-evidence','select');options(evidence,[['','请选择已保存的实际发送日志或外部证据'],...inputs.sources.map(s=>[s.source_ref,s.title||s.source_ref])]);
  const description=el('div',undefined,'body');f.append(description);
  evidence.onchange=()=>{description.textContent=inputs.sources.find(s=>s.source_ref===evidence.value)?.body||'';};
  const reason=field(f,'人工判断与处理理由（理由本身不是外部证据）','reconcile-note','textarea');reason.required=true;
  choice.onchange=()=>{evidence.disabled=choice.value!=='CONFIRMED_NOT_SENT';evidence.required=!evidence.disabled;description.hidden=evidence.disabled;};choice.onchange();
  note(f,'没有已保存的证据时，先关闭此窗口，通过“补充材料”保存真实日志，再返回选择。证据会与这一个原请求和执行事件绑定。');
  submit(f,'记录处理决定',async()=>{if(choice.value==='CONFIRMED_NOT_SENT'&&!evidence.value)throw Error('确认未发送必须选择实际证据原件。');const data={instance,request_id:rid,disposition:choice.value,note:reason.value};if(choice.value==='CONFIRMED_NOT_SENT')data.not_sent_evidence_ref=evidence.value;await action('reconcile',data);closeDialog();await refresh();});box.append(f);
}
async function reformulate(){
  requireInstance();if(selectedInstanceRow()?.kind==='TFDW'){view='candidates';graphSelection=null;return refresh();}
  const inputs=await workflowInputs(),box=dialog('从当前目标交接到表述发现'),f=el('form',undefined,'stack');
  const name=field(f,'新发现流程名称','handoff-name','text','原目标的表述与边界发现');name.required=true;
  const fields=discoveryFields(f,'handoff-discovery',{sources:inputs.sources});
  note(f,'保留原 TRW 的精确目标，以明确现象、不变背景和探索范围创建共享材料的暂停 TFDW。');
  submit(f,'交接并创建暂停的 TFDW',async()=>{const r=await action('handoff',{direction:'TRW_TO_TFDW',name:name.value,discovery_scope:fields.value(),draft:fields.draft(),note:'用户从原目标明确选择表述发现交接。'});closeDialog();await openProject();$('instance').value=r.instance_id;graphSelection=null;await refresh();});box.append(f);
}
function renderProgress(s){
  latestCommit=s.commit||latestCommit;$('project-title').textContent=s.title||currentStatus?.title||'研究项目';$('demo-banner').hidden=!(s.synthetic??currentStatus?.synthetic);
  const remaining=s.budget.remaining_calls,instances=s.workflow.instances||[];
  $('status').replaceChildren();
  for(const [label,value,small] of [
    ['知识',s.mathematical.records+' 份记录','资格按精确范围'],
    ['所选流程',instances.map(i=>show(i.status)).join('、')||'全部共享知识','阶段活动不表示数学通过'],
    ['所选范围的实际请求',s.execution.running_processes+' 项在途','仅已预留或已发送的请求'],
    ['未知请求',s.execution.unknown+' 项不确定','保留消耗，禁止自动重发'],
    ['授权',remaining===null?'明确无限额':Math.max(0,remaining)+' 次尚未预留','项目剩余 '+(s.budget.project_remaining_calls??'明确无限额')+' · 费用未知']
  ]){const n=el('div',undefined,'stat');n.append(el('small',label),el('strong',value),el('small',small));$('status').append(n);}
  $('activity').replaceChildren();
  const jobs=s.project_jobs||s.jobs||[];
  for(const j of jobs){const n=el('div',undefined,'scope');const iid=j.initiated_by_instance_id||j.instance_id;const instance=instances.find(i=>i.instance_id===iid);n.append(el('strong','项目协调器 · '+show(j.state)),el('p','发起流程：'+(instance?instanceLabel(instance):iid||'项目级任务')));note(n,j.message||show(j.result?.state)||'按项目内已有授权处理任务；不表示每个流程都在运行。');$('activity').append(n);}
  if(!jobs.length)$('activity').append(el('p','项目当前没有运行中的协调任务。','muted'));
  renderWorkflowGraph(s.activity);
  const changed=contentProgressFingerprint&&progressFingerprint(s)!==contentProgressFingerprint;if(snapshot&&(latestCommit!==snapshot||changed)){$('content-update').hidden=false;$('content-update-label').textContent=(latestCommit!==snapshot?'后台状态':'任务进展')+'已更新，当前正文仍保留在快照 '+snapshot.slice(0,12)+'。';}
}
async function pollProgress(){
  if(!project||progressBusy)return;progressBusy=true;
  const selectedProject=project,selectedInstance=$('instance').value,generation=refreshGeneration;
  try{const s=await request('/api/progress',{params:{project:selectedProject,instance:selectedInstance}});
    if(project!==selectedProject||$('instance').value!==selectedInstance||generation!==refreshGeneration)return;
    // Readers keep their DOM, open details, scroll position and frozen commit.
    currentStatus={...currentStatus,...s,candidates:currentStatus?.candidates||[]};renderProgress(s);
    if(view==='tasks')patchTaskStates(s);
  }catch(e){$('notice').textContent='状态暂未更新：'+e.message+'。正在阅读的正文已保留。';}
  finally{progressBusy=false;}
}
function patchTaskStates(s){
  const content=$('content'),wanted=(s.tasks||[]).filter(t=>!graphSelection||t.stage_id===graphSelection);
  const cards=new Map([...content.querySelectorAll('[data-task-id]')].map(c=>[c.dataset.taskId,c]));
  const ids=new Set(wanted.map(t=>t.task_id));
  for(const [id,c] of cards)if(!ids.has(id))c.remove();
  for(const t of wanted){const c=cards.get(t.task_id);if(c)updateTaskCard(c,t,s);else content.append(task(t));}
  if(wanted.length){for(const empty of content.querySelectorAll('.empty'))empty.remove();}
  else if(!content.querySelector('.empty'))content.append(el('p','当前阶段尚无任务。','empty'));
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
function graphStateLabel(state){return !state.known?'状态未知':state.active?'正在处理':state.waiting?'等待处理':state.recent?'最近工作':state.status==='VISITED'?'已有记录':'未访问';}
function graphEdgeLabel(edge){return edge.from===edge.to?'可迭代':({forward:'分支',return:'回流',early_delivery:'提前交付'}[edge.kind]||edge.kind);}
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
  const toolbar=el('div',undefined,'graph-toolbar'),switches=el('div',undefined,'graph-switches');switches.setAttribute('role','group');switches.setAttribute('aria-label','选择流程图');
  for(const [kind,label] of [['TRW','定题研究 TRW'],['TFDW','表述发现 TFDW'],['overview','双图总览']]){const b=button(label,()=>{workflowGraphView.mode=kind;resetWorkflowGraphSelection();renderWorkflowGraph(currentStatus?.activity);},'graph-switch');b.dataset.graphMode=kind;switches.append(b);}toolbar.append(switches);
  const all=button('显示全部路径',()=>{workflowGraphView.allPaths=!workflowGraphView.allPaths;renderWorkflowGraph(currentStatus?.activity);},'graph-path-toggle');all.dataset.graphPaths='all';all.setAttribute('aria-pressed','false');toolbar.append(all);container.append(toolbar);
  const legend=el('p','主路径仅帮助阅读，不要求逐阶段执行。选中节点查看相关分支；↻ 表示可在原阶段迭代。','graph-legend');container.append(legend);
  const maps=el('div',undefined,'workflow-maps');
  for(const workflow of graphDefinition.workflows){
    const block=el('section',undefined,'workflow-map');block.dataset.kind=workflow.kind;
    const header=el('div',undefined,'workflow-map-heading');header.append(el('h3',workflow.kind==='TRW'?'定题研究 · P0–P14':'表述发现 · D0–D5'));const context=el('span',undefined,'graph-context');context.dataset.graphContext=workflow.kind;header.append(context);block.append(header);
    const viewport=el('div',undefined,'graph-viewport'),nodes=el('div',undefined,'stage-nodes');nodes.dataset.columns=workflow.kind==='TRW'?'5':'3';const columns=workflow.kind==='TRW'?5:3;
    for(const [index,stage] of workflow.nodes.entries()){
      const b=button('',()=>selectGraphStage(workflow.kind,stage.stage_id),'stage-node');b.dataset.stage=stage.stage_id;b.dataset.kind=workflow.kind;
      const row=Math.floor(index/columns),column=row%2?columns-index%columns:index%columns+1;b.style.gridRow=String(row+1);b.style.gridColumn=String(column);
      const heading=el('span',undefined,'stage-node-heading');heading.append(el('strong',stage.stage_id),el('span',workflowStageLabel(stage.stage_id)));b.append(heading);
      const state=el('small','状态未知');state.dataset.stageState=stage.stage_id;b.append(state);
      if((workflow.edges||[]).some(edge=>edge.from===stage.stage_id&&edge.to===stage.stage_id)){const loop=el('span','↻','stage-iteration');loop.title='此阶段登记有迭代路径';loop.setAttribute('aria-label','可在此阶段迭代');b.append(loop);}
      b.title=stage.label;nodes.append(b);
    }
    viewport.append(nodes);block.append(viewport);maps.append(block);
    if(typeof ResizeObserver==='function'){const observer=new ResizeObserver(()=>drawWorkflowEdges(block,workflow));observer.observe(nodes);workflowGraphView.observers.push(observer);}
  }
  container.append(maps);
  const links=el('details',undefined,'graph-registered-links');links.append(el('summary','逐条查看当前图的登记路径（仅导航）'));links.append(el('div',undefined,'edge-list'));container.append(links);
}
function renderWorkflowGraph(activity){
  if(!graphDefinition)return;const scope=workflowGraphScope(),bound=selectedGraphActivity(activity),container=$('workflow-graph');
  if(workflowGraphView.scope!==scope){workflowGraphView.scope=scope;workflowGraphView.mode=bound?.workflow_kind||selectedInstanceRow()?.kind||'overview';workflowGraphView.allPaths=false;resetWorkflowGraphSelection();}
  if(workflowGraphView.focus?.scope!==scope)workflowGraphView.focus=null;
  if(workflowGraphView.definition!==graphDefinition||!container.childNodes.length)buildWorkflowGraph(container);
  container.classList.toggle('graph-overview-mode',workflowGraphView.mode==='overview');
  for(const b of container.querySelectorAll('[data-graph-mode]')){const selected=b.dataset.graphMode===workflowGraphView.mode;b.setAttribute('aria-pressed',String(selected));b.classList.toggle('selected',selected);}
  const toggle=container.querySelector('[data-graph-paths]');toggle.setAttribute('aria-pressed',String(workflowGraphView.allPaths));toggle.textContent=workflowGraphView.allPaths?'收起到主路径与所选分支':'显示全部路径';
  for(const block of container.querySelectorAll('.workflow-map')){
    const known=bound?.workflow_kind===block.dataset.kind;block.hidden=workflowGraphView.mode!=='overview'&&workflowGraphView.mode!==block.dataset.kind;block.classList.toggle('selected-workflow',known);block.classList.toggle('structure-preview',!known);block.querySelector('.graph-context').textContent=known?(bound.name||'当前实例')+' · '+bound.instance_id.slice(-6)+' · '+show(bound.instance_status):'结构预览 · 未选择实例 · 状态未知';
  }
  for(const b of container.querySelectorAll('[data-stage]')){
    const state=workflowStagePresentation(bound,b.dataset.kind,b.dataset.stage),selected=workflowGraphView.focus?.kind===b.dataset.kind&&workflowGraphView.focus?.stage===b.dataset.stage;
    for(const [name,value] of [['running',state.active],['waiting',state.waiting],['visited',state.known&&state.status==='VISITED'],['recent',state.recent],['unknown-state',!state.known],['selected-stage',selected]])b.classList.toggle(name,value);
    b.setAttribute('aria-pressed',String(selected));b.querySelector('small').textContent=graphStateLabel(state);b.setAttribute('aria-label',b.dataset.stage+' '+b.title+'；'+graphStateLabel(state));
  }
  const list=container.querySelector('.edge-list');const edgeSignature=JSON.stringify([workflowGraphView.mode,workflowGraphView.focus?.kind,workflowGraphView.focus?.stage,workflowGraphView.allPaths]);
  if(list.dataset.signature!==edgeSignature){
    list.replaceChildren();list.dataset.signature=edgeSignature;
    for(const workflow of graphDefinition.workflows.filter(w=>workflowGraphView.mode==='overview'||w.kind===workflowGraphView.mode)){
      const selected=workflowGraphView.focus?.kind===workflow.kind?workflowGraphView.focus.stage:null,edges=workflowGraphEdges(workflow,selected,workflowGraphView.allPaths);
      for(const edge of edges.visible){const label=edges.main.includes(edge)?'主路径':graphEdgeLabel(edge);list.append(button(edge.from+' → '+edge.to+' · '+label,()=>selectGraphStage(workflow.kind,edge.to),'edge'));}
      for(const edge of edges.selfLoops.filter(edge=>workflowGraphView.allPaths||edge.from===selected))list.append(button(edge.from+' ↻ 可迭代',()=>selectGraphStage(workflow.kind,edge.from),'edge iteration'));
    }
  }
  if(bound){
    const active=bound.active_stages||[],waiting=bound.waiting_stages||[],recent=bound.recent_stages||[];
    const reasons=[...new Set((bound.stages||[]).flatMap(stage=>(stage.waiting_reasons||[]).map(reason=>stage.stage_id+'：'+(typeof reason==='string'?reason:JSON.stringify(reason)))))];
    $('workflow-summary').textContent=show(bound.instance_status)+' · '+(active.length?'实际活动：'+active.map(id=>id+' '+workflowStageLabel(id)).join('、'):'当前无在途工作')+' · '+(waiting.length?'等待阶段：'+waiting.map(id=>id+' '+workflowStageLabel(id)).join('、'):'无等待阶段')+' · 最近：'+(recent.join('、')||'尚无任务')+(reasons.length?'\n待处理事项：'+reasons.join('；'):'');
  }else $('workflow-summary').textContent='当前为结构预览，阶段状态未知。选择一个研究实例后，才显示它的实际活动与等待事项。';
  renderStageDetail(bound);redrawWorkflowGraphs();
}
async function navigateStage(kind,stage){
  const row=selectedInstanceRow();if(!row||row.kind!==kind){$('notice').textContent='请选择 '+kind+' 流程以查看 '+stage+' 的实际任务；图中的阶段按钮不会启动或推进研究。';return;}
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
  const header=el('div',undefined,'stage-detail-heading');header.append(el('h3',focus.stage+' · '+workflowStageLabel(focus.stage)),el('span',graphStateLabel(stage),'badge'));header.append(button('关闭详情',()=>{resetWorkflowGraphSelection();renderWorkflowGraph(currentStatus?.activity);},'stage-detail-close'));box.append(header);
  box.append(el('p',definition.label,'stage-description'));if(definition.purpose&&definition.purpose!==definition.label)note(box,definition.purpose);
  note(box,stage.known?'这里展示本实例的原生工作；已有记录、等待或最近活动都不表示数学通过。':'结构预览：未选择对应类型的实例，不判断此阶段是否已访问，也不显示其他实例的任务。');
  function section(id,title,open=false){const d=el('details',undefined,'stage-detail-section');d.dataset.detailSection=id;d.open=openSections.has(id)||open;d.append(el('summary',title));box.append(d);return d;}
  const workflow=graphDefinition.workflows.find(w=>w.kind===focus.kind),related=(workflow.edges||[]).filter(e=>e.from===focus.stage||e.to===focus.stage);
  const routes=section('paths','相关分支、回流与交接',true),links=el('div',undefined,'stage-related-paths');
  for(const edge of related){const target=edge.from===focus.stage?edge.to:edge.from;links.append(button(edge.from===edge.to?edge.from+' ↻ 可迭代':edge.from+' → '+edge.to+' · '+graphEdgeLabel(edge),()=>selectGraphStage(focus.kind,target),'edge '+edge.kind));}routes.append(links);
  if(focus.stage==='P7')for(const route of graphDefinition.analysis_routes||[]){const r=el('p',undefined,'graph-route');r.append(el('strong',route.label||route.id),el('span',' · '+(route.roles||[]).map(role=>typeof role==='string'?role:role.role).join(' → ')));routes.append(r);}
  for(const handoff of (graphDefinition.handoffs||[]).filter(row=>row.from===focus.kind)){
    const h=el('p',handoff.label||handoff.from+' → '+handoff.to,'graph-handoff');routes.append(h);
    if(stage.known)routes.append(button('打开人工交接入口',()=>{requireInstance();if(selectedInstanceRow()?.kind!==focus.kind)throw Error('流程范围已改变，请重新选择阶段。');return reformulate();},'edge'));
  }
  const model=section('policy','已登记职责与模型强度');
  if(definition.roles?.length)note(model,'已登记角色：'+definition.roles.join('、'));
  if(!policy)note(model,'策略尚未载入；此处不推测强度。');
  else {
    const rules=(policy.rules||[]).filter(r=>r.workflow_kind===focus.kind&&r.stage_id===focus.stage);
    for(const rule of rules){
      const override=overrides.find(o=>scopeKey(o.scope)===scopeKey({workflow_kind:focus.kind,stage_id:focus.stage,role:rule.role,purpose:rule.purpose||'DEFAULT'}));
      note(model,rule.role+' · '+(rule.call_model?'默认 '+rule.model+' / '+rule.reasoning_effort+' / '+rule.service_tier:'本地或人类职责，不调用模型'));
      if(override)note(model,'本实例未来覆盖：'+(override.model||rule.model)+' / '+(override.reasoning_effort||rule.reasoning_effort)+' / '+(override.service_tier||rule.service_tier));
    }
    for(const exception of (policy.purpose_exceptions||[]).filter(r=>r.stage_id===focus.stage))note(model,exception.role+' · 用途 '+exception.purpose+'：'+exception.reasoning_effort);
    if(rules.some(r=>r.role.startsWith('REPORT_')))note(model,'仅版式用途：'+policy.layout_only_reasoning_effort+'；实际任务以冻结用途与配置为准。');
    for(const override of overrides.filter(o=>o.scope.workflow_kind===focus.kind&&o.scope.stage_id===focus.stage&&o.scope.purpose!=='DEFAULT'))note(model,'未来用途覆盖 '+override.scope.role+' / '+override.scope.purpose+'：'+override.model+' / '+override.reasoning_effort+' / '+override.service_tier);
    note(model,'以上是已登记策略与未来覆盖；没有授权就不会调用，已有任务保留各自冻结配置。');
  }
  if(!stage.known)return;
  for(const route of stage.analysis_routes||[])note(box,'实际分析路线：'+route);
  if((stage.waiting_reasons||[]).length||(stage.next_actions||[]).length){const waiting=section('waiting','等待事项与可用处理',true);for(const reason of stage.waiting_reasons||[])note(waiting,'等待原因：'+(typeof reason==='string'?reason:JSON.stringify(reason)));for(const next of stage.next_actions||[])note(waiting,'可用处理：'+(typeof next==='string'?next:next.label||next.action||JSON.stringify(next)));}
  const actual=section('actual','实际任务、冻结配置与控制记录');
  if(!(stage.task_ids||[]).length&&!(stage.control_event_ids||[]).length)note(actual,'本实例尚无此阶段的任务或控制记录。');
  for(const t of tasks){const p=t.model_policy;note(actual,t.task_id+' · '+t.role+(p?' · 已冻结 '+(p.call_model===false?'不调用模型':p.model+' / '+p.reasoning_effort+' / '+p.service_tier):''));}
  for(const id of (stage.task_ids||[]).filter(id=>!tasks.some(t=>t.task_id===id)))note(actual,'实际任务：'+id);
  for(const id of stage.request_ids||[])note(actual,'关联请求：'+id);for(const id of stage.control_event_ids||[])note(actual,'已记录控制：'+id);
  if((stage.record_refs||[]).length){const products=section('products','本阶段产物 · '+stage.record_refs.length+' 份',true),readScope={project,instance:bound.instance_id,commit:latestCommit||snapshot};
    for(const ref of stage.record_refs)products.append(button('阅读产物 · '+ref.slice(-12),async()=>{const r=await readApi('body',{...readScope,ref});if(project!==readScope.project||$('instance').value!==readScope.instance)return;const d=dialog('阶段产物');d.append(el('p',ref,'ref'),el('div',r.body,'body'));await typeset(d);},'edge'));
  }
  const actions=el('div',undefined,'stage-detail-actions');actions.append(button('查看此阶段任务',()=>navigateStage(focus.kind,focus.stage)),button('查看相关开放问题',()=>selectView('frontier',{keepGraph:true})),button('查看全部任务',()=>selectView('tasks',{keepGraph:true})));box.append(actions);
}
async function environmentSettings(box,setup){
  if(!setup)return;
  const section=el('section',undefined,'dependency-settings');section.append(el('h3','运行与报告依赖'));
  note(section,(setup.research_ready?'研究执行环境可用。':'研究环境仍需配置。')+' '+(setup.pdf_dependencies_present?'PDF 依赖已发现；实际编译仍需通过环境检测。':'PDF 依赖尚不完整；这不阻止普通研究。'));
  for(const component of setup.components||[]){const row=el('div',undefined,'scope');row.append(el('strong',component.label||component.id));note(row,(component.installed?'已发现':'尚未配置')+(component.version?' · '+component.version:'')+(component.source?' · '+component.source:''));
    if(component.install_available)row.append(button('安装或准备 '+(component.label||component.id),async()=>{const confirmBox=dialog('安装所选依赖');confirmBox.append(el('p','准备 '+(component.label||component.id)+'。可能下载官方软件或 TeX 资源；如系统需要权限，将显示系统对话框。此操作不启动研究或模型调用。'));confirmBox.append(button('确认安装或准备此依赖',async()=>{await action('setup-install',{component:component.id,confirmed:true});await settings();},'primary'));}));section.append(row);}
  for(const job of setup.jobs||[]){const row=el('p',(job.component||job.job_id)+' · '+(show(job.state)||job.state)+' · '+(job.message||''),'scope');row.dataset.setupJob=job.job_id;section.append(row);}
  const form=el('form',undefined,'stack');const fields={};
  for(const [key,label] of [['codex','官方 Codex CLI'],['tectonic','Tectonic 可执行文件'],['tectonic_cache','离线 TeX 资源 / 缓存目录'],['ca_bundle','CA 证书包（可选）']]){
    fields[key]=field(form,label+'路径','setup-'+key,'text',setup.paths?.[key]||'');fields[key].placeholder=setup.resolved?.[key]||'自动检测；如需配置，可选择本机路径';
    form.append(button('选择 '+label,async()=>{const r=await action('setup-select',{kind:key});if(!r.cancelled)await settings();}));
  }
  note(form,'选择本机已安装的程序或资源目录，也可填写绝对路径。留空恢复该项自动检测；账号登录仍只通过官方客户端。');
  submit(form,'保存这些依赖路径',async()=>{await action('setup-configure',{paths:Object.fromEntries(Object.entries(fields).map(([k,input])=>[k,input.value.trim()||null]))});await settings();});section.append(form);box.append(section);
}
async function pollSetup(){
  if(!$('dialog').open||!$('dialog-content').querySelector('[data-setup-job]'))return;
  const d=await request('/api/settings');
  for(const job of d.setup?.jobs||[]){const row=[...$('dialog-content').querySelectorAll('[data-setup-job]')].find(n=>n.dataset.setupJob===job.job_id);if(row)row.textContent=(job.component||job.job_id)+' · '+job.state+' · '+(job.message||'');}
}

async function initial(){
  const token=new URLSearchParams(location.hash.slice(1)).get('session');if(token){await request('/api/session',{method:'POST',data:{token}});history.replaceState(null,'',location.pathname);}
  try{const s=await request('/api/session');csrf=s.csrf;workspaceId=s.workspace_id;operations.storage=indexedOperationStorage(window.indexedDB,workspaceId);$('app').hidden=false;graphDefinition=await request('/api/workflow-graph');await listProjects();const recovered=await operations.recover();await renderOperationRecovery(recovered);if(recovered?.result!==undefined)await applyRecovered(recovered.result,recovered.operation);}
  catch(e){if(!csrf)$('session-warning').hidden=false;throw e;}
}
$('close-dialog').onclick=closeDialog;$('new-project').onclick=()=>createForm();$('new-workflow').onclick=guarded(newWorkflowForm);$('handoff-workflow').onclick=guarded(reformulate);$('edit-discovery').onclick=guarded(discoveryConfigForm);$('import-project').onclick=importForm;$('settings-button').onclick=guarded(settings);$('help-button').onclick=help;$('start-round').onclick=guarded(startForm);$('add-source').onclick=sourceForm;
$('project').onchange=guarded(async()=>{project=$('project').value;clearStageSelection();projectGeneration++;refreshGeneration++;localStorage.setItem('pmrs_4_0_project',project);await listProjects();});$('instance').onchange=guarded(()=>{clearStageSelection();return refresh();});$('refresh').onclick=guarded(()=>refresh());$('refresh-content').onclick=guarded(()=>refresh());$('search-form').onsubmit=guarded(()=>refresh());$('more').onclick=guarded(()=>refresh(true));
for(const name of ['pause','continue','end'])$(name).onclick=guarded(async()=>{requireInstance();await action(name,{commit:latestCommit||snapshot});await openProject();});
$('request-report').onclick=guarded(async()=>{requireInstance();await action('report');view='reports';await refresh();});
$('export').onclick=guarded(async()=>{const r=await action('export');const a=el('a','下载项目备份');a.href=r.download;a.download='PMRS-4.0.0-backup.zip';$('notice').replaceChildren(a);a.click();});
$('quit').onclick=guarded(async()=>{await action('quit');$('notice').textContent='后台服务已退出；项目已保存。可从桌面重新打开。';$('app').hidden=true;});
for(const b of document.querySelectorAll('[data-new]'))b.onclick=()=>createForm(b.dataset.new);for(const b of document.querySelectorAll('[data-example]'))b.onclick=()=>createForm(b.dataset.example==='TRW'?'TRW':'TFDW',true);
for(const b of $('tabs').querySelectorAll('button'))b.onclick=guarded(()=>selectView(b.dataset.view));
setInterval(()=>{pollProgress();pollSetup().catch(e=>{$('notice').textContent='依赖状态暂未更新：'+e.message;});},5000);guarded(initial)();
})();
