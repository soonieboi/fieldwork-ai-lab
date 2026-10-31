// Test-only controlled-delay harness for the actual dashboard handlers.
// Minimal DOM stubs exercise state transitions, not rendering or browser fetch.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');
class Element {
  constructor(){this.children=[];this.disabled=false;this.value='';this.handlers={};this.dataset={};this.classes=new Set();this.classList={toggle:(c,on)=>on?this.classes.add(c):this.classes.delete(c)};}
  append(...nodes){this.children.push(...nodes)}
  replaceChildren(...nodes){this.children=nodes}
  addEventListener(name,fn){this.handlers[name]=fn}
  querySelectorAll(){return []}
  setAttribute(){} focus(){} scrollIntoView(){}
}
function harness(){
  const nodes=new Map(),pending=[],timers=[];
  const $=key=>{if(!nodes.has(key))nodes.set(key,new Element());return nodes.get(key)};
  const context=vm.createContext({$,location:{hash:'#agents'},document:{querySelectorAll:()=>[]},
    el:(tag,text)=>{const n=new Element();n.text=String(text||'');return n},
    renderGenerated:(target,result)=>target.append({text:result.claims[0].text}),
    request:(path,body)=>new Promise((resolve,reject)=>pending.push({path,body,resolve,reject})),
    setTimeout:fn=>timers.push(fn)});
  const route=html.slice(html.indexOf("const views="),html.indexOf("document.querySelectorAll('[data-tab]').forEach((b,i)"));
  const agent=html.slice(html.indexOf('let activeAgent='),html.indexOf("$('#bounded-mode').onchange="));
  assert(agent.includes('async function pollAgent'));
  vm.runInContext(route+agent+';globalThis.state=()=>({activeAgent,agentPollingId});globalThis.route=renderRoute;',context);
  return {context,$,pending,timers,state:context.state};
}
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};
const job=(id,status='running',cancel=false)=>({id,status,cancel_requested:cancel,trace:[],
  result:status==='running'?null:{status,mode:'fake delayed fixture — no inference',claims:[{text:'LATE OLD ANSWER'}]}});
function take(h,path,id){const i=h.pending.findIndex(p=>p.path.endsWith(path)&&(!id||p.body.id===id));assert(i>=0,`Missing ${path} ${id||''}`);return h.pending.splice(i,1)[0]}
function text(n){return (n.text||'')+(n.children||[]).map(text).join(' ')}
async function start(h,id){
  const completion=h.$('#bounded-form').handlers.submit({preventDefault(){}});
  take(h,'start').resolve(job(id));await flush();return {completion};
}
async function main(){
  // Cancel while a status request is held, navigate away/back, then acknowledge.
  const h=harness();const a=await start(h,'old');const oldPoll=take(h,'status','old');
  const stop=h.$('#bounded-cancel').onclick();take(h,'cancel','old').resolve(job('old','running',true));await flush();await stop;
  assert.equal(h.state().activeAgent.cancelRequested,true);
  assert.match(text(h.$('#bounded-result')),/not yet acknowledged/);
  h.context.location.hash='#docs/model-agents';h.context.route();
  assert(h.$('#agents').classes.has('hidden'));
  h.context.location.hash='#agents';h.context.route();assert(!h.$('#agents').classes.has('hidden'));
  oldPoll.resolve(job('old','cancelled',true));await flush();await a.completion;
  assert.equal(h.state().activeAgent,null);assert(!text(h.$('#bounded-result')).includes('LATE OLD ANSWER'));
  const b=await start(h,'new');assert.equal(h.state().activeAgent.id,'new');
  take(h,'status','new').resolve(job('new','cancelled'));await flush();await b.completion;

  // A cancel terminal acknowledgment may arrive before an older held poll.
  // New polling must survive both a late successful response and a late error.
  for(const lateError of [false,true]){
    const h=harness();const a=await start(h,'old');const old=take(h,'status','old');
    const stop=h.$('#bounded-cancel').onclick();take(h,'cancel','old').resolve(job('old','cancelled',true));await stop;
    const b=await start(h,'new');const fresh=take(h,'status','new');
    if(lateError)old.reject(new Error('old status failed'));else old.resolve(job('old','completed'));
    await flush();await a.completion;
    assert.equal(h.state().activeAgent.id,'new');assert.equal(h.state().agentPollingId,'new');
    assert(!text(h.$('#bounded-result')).includes('LATE OLD ANSWER'));
    assert(!text(h.$('#bounded-result')).includes('old status failed'));
    fresh.resolve(job('new','cancelled'));await flush();await b.completion;
    assert.equal(h.state().activeAgent,null);assert.equal(h.state().agentPollingId,null);
  }
  // A late cancel response for a finished run cannot replace the next run.
  {
    const h=harness();const a=await start(h,'old');const old=take(h,'status','old');
    const stop=h.$('#bounded-cancel').onclick(),cancel=take(h,'cancel','old');
    old.resolve(job('old','cancelled'));await flush();await a.completion;
    const b=await start(h,'new');cancel.resolve(job('old','completed'));await stop;
    assert.equal(h.state().activeAgent.id,'new');assert(!text(h.$('#bounded-result')).includes('LATE OLD ANSWER'));
    take(h,'status','new').resolve(job('new','cancelled'));await flush();await b.completion;
  }
  console.log('Controlled-delay frontend handlers: cancel acknowledgment, navigation, run-cancel-run, stale poll success/error and stale cancel PASS. Not rendered-browser QA.');
}
main().catch(e=>{console.error(e);process.exitCode=1});
