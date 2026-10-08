/* Display templates never enter research contracts. User/source text has no message tokens. */
(function(root){
'use strict';
const messages=typeof module!=='undefined'&&module.exports?require('./messages.js'):root.PMRS_MESSAGES;
let locale='en';const bindings=new Set();const finalizer=typeof FinalizationRegistry==='function'?new FinalizationRegistry(ref=>bindings.delete(ref)):null;const pattern=/\uE000([a-zA-Z0-9_.-]+)\uE001/g;
function normalize(value){return value==='zh-CN'?'zh-CN':'en';}
function systemMessage(value){if(typeof value!=='string')return value;const match=Object.entries(messages['zh-CN']).find(([key,text])=>text===value);if(match)return message(match[0]);const suffix=messages['zh-CN']['backend.wait.fenced'];if(suffix&&value.endsWith(suffix))return systemMessage(value.slice(0,-suffix.length))+message('backend.wait.fenced');return value;}
function message(key){return '\uE000'+key+'\uE001';}
function translate(key,params={},language=locale){let result=messages[normalize(language)]?.[key]??messages.en[key]??key;for(const [name,value] of Object.entries(params))result=result.replaceAll('{'+name+'}',String(value));return result;}
function render(template){return String(template??'').replace(pattern,(_,key)=>translate(key));}
function resolve(value){if(typeof value==='string')return render(value);if(Array.isArray(value))return value.map(resolve);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,resolve(v)]));return value;}
function bind(node,property,template){
  template=String(template??'');node.__pmrsTextBindings??={};
  if(template.includes('\uE000')){node.__pmrsTextBindings[property]=template;if(!node.__pmrsTextReference){node.__pmrsTextReference=typeof WeakRef==='function'?new WeakRef(node):{deref:()=>node};bindings.add(node.__pmrsTextReference);if(finalizer)finalizer.register(node,node.__pmrsTextReference);}}
  else delete node.__pmrsTextBindings[property];
  if(property.startsWith('@'))node.setAttribute(property.slice(1),render(template));else node[property]=render(template);return template;
}
function text(node,template){
  if(node.nodeType===3)return bind(node,'textContent',template);
  node.textContent=render(template);const child=node.firstChild;
  return bind(child?.nodeType===3?child:node,'textContent',template);
}
function attribute(node,name,template){return bind(node,'@'+name,template);}
function setLocale(value){
  locale=normalize(value);
  for(const ref of bindings){const node=ref.deref();if(!node){bindings.delete(ref);continue;}for(const [property,template] of Object.entries(node.__pmrsTextBindings||{})){if(property.startsWith('@'))node.setAttribute(property.slice(1),render(template));else node[property]=render(template);}}
  if(typeof document!=='undefined'&&document.documentElement)document.documentElement.lang=locale;return locale;
}
function initializeStatic(document){
  if(!document.createTreeWalker)return;const walker=document.createTreeWalker(document,128);let comment;
  while((comment=walker.nextNode())){if(comment.data.startsWith('pmrs-i18n:')&&comment.nextSibling?.nodeType===3)bind(comment.nextSibling,'textContent',message(comment.data.slice(10)));}
  for(const node of document.querySelectorAll('*'))for(const attr of [...node.attributes])if(attr.name.startsWith('data-i18n-')){if(attr.name==='data-i18n-content')text(node,message(attr.value));else attribute(node,attr.name.slice(10),message(attr.value));}
  document.documentElement.lang=locale;
}
const api={systemMessage,message,translate,render,resolve,text,attribute,setLocale,initializeStatic,normalize,getLocale:()=>locale,has:key=>Object.hasOwn(messages.en,key),messages};
root.PMRS_I18N=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
