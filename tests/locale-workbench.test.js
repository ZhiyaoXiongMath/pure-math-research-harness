'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../research_studio/static/i18n.js');
const {workflowStageLabel}=require('../research_studio/static/workbench.js');
class TextNode{constructor(value){this.nodeType=3;this.textContent=value;}}
class Element{
  constructor(){this.nodeType=1;this.children=[];this.attributes={};this.scrollTop=0;this.scrollLeft=0;}
  set textContent(value){this.children=[new TextNode(value)];}get textContent(){return this.children.map(n=>n.textContent||'').join('');}
  get firstChild(){return this.children[0];}append(...children){this.children.push(...children);}
  setAttribute(name,value){this.attributes[name]=String(value);}
}
test('new installation display defaults to English and all three stage families are translated',()=>{
  assert.equal(L.getLocale(),'en');assert.equal(workflowStageLabel('P7'),'Obligation analysis');assert.equal(workflowStageLabel('S4'),'Readiness review');
  assert.deepEqual(Object.keys(L.messages.en).sort(),Object.keys(L.messages['zh-CN']).sort());
  for(const [prefix,count] of [['P',15],['D',6],['S',8]])for(let n=0;n<count;n++){assert.ok(L.messages.en[`stage.${prefix}${n}.name`]);assert.ok(L.messages['zh-CN'][`stage.${prefix}${n}.description`]);}
});
test('locale replacement preserves input identity, drafts, selections, open details and scroll',()=>{
  L.setLocale('en');const label=new Element(),input={value:'中文原始输入\nEnglish mathematical statement',selectedIndex:2},detail={open:true};
  L.text(label,L.message('stage.S4.name'));label.append(input,detail);label.scrollTop=131;label.scrollLeft=7;
  const originalText=label.firstChild;L.setLocale('zh-CN');assert.equal(label.firstChild,originalText);assert.equal(originalText.textContent,'就绪审查');assert.equal(label.children[1],input);assert.equal(input.value,'中文原始输入\nEnglish mathematical statement');assert.equal(input.selectedIndex,2);assert.equal(label.children[2],detail);assert.equal(detail.open,true);assert.equal(label.scrollTop,131);assert.equal(label.scrollLeft,7);
  L.setLocale('en');assert.equal(originalText.textContent,'Readiness review');assert.equal(label.children[1],input);
});
test('unmarked source text stays verbatim and translated attributes use plain text without HTML',()=>{
  const source=new Element(),button=new Element();L.text(source,'目标授权 <script>not execution</script>');L.text(button,L.message('error.generic')+' <img src=x onerror=alert(1)>');L.attribute(button,'aria-label',L.message('stage.S0.name'));
  L.setLocale('zh-CN');assert.equal(source.textContent,'目标授权 <script>not execution</script>');assert.equal(button.attributes['aria-label'],'范围与授权');assert.equal(button.children.length,1);assert.match(button.textContent,/<img src=x onerror=alert\(1\)>/);L.setLocale('en');
});
test('missing translations fall back to English without altering message identity',()=>{
  const saved=L.messages['zh-CN']['stage.S4.name'];delete L.messages['zh-CN']['stage.S4.name'];L.setLocale('zh-CN');assert.equal(L.render(L.message('stage.S4.name')),'Readiness review');L.messages['zh-CN']['stage.S4.name']=saved;assert.equal(L.render(L.message('stage.S4.name')),'就绪审查');L.setLocale('unknown');assert.equal(L.getLocale(),'en');
});
