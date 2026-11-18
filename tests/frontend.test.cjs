const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function harness(job, dimensions=[1920,1080], decodeFails=false) {
  const elements={}, timers=[], calls=[], intervals=[];let now=0;
  function element() {return {style:{},scrollHeight:58,value:'',disabled:false,hidden:true,children:[],events:{},classList:{add(){},remove(){},toggle(){}},setAttribute(){},focus(){},click(){},querySelectorAll(){return [];},replaceWith(replacement){for(const key of Object.keys(elements))if(elements[key]===this)elements[key]=replacement;},replaceChildren(...items){this.children=items;},append(...items){this.children.push(...items);},addEventListener(event,handler){this.events[event]=handler;}};}
  const query = id => elements[id] ||= element();
  Object.assign(query('#wallpaper'),{naturalWidth:dimensions[0],naturalHeight:dimensions[1],async decode(){if(decodeFails) throw Error('decode');}});
  const context=vm.createContext({document:{addEventListener(){},querySelector:query,createElement:kind=>kind==='canvas'?{getContext:()=>({drawImage(){}}),toBlob:cb=>cb({size:12})}:element()},
    window:{addEventListener(){},setTimeout:fn=>timers.push(fn),setInterval:fn=>intervals.push(fn)},performance:{now:()=>now},Image:class {constructor(){Object.assign(this,element(),{naturalWidth:dimensions[0],naturalHeight:dimensions[1]});}async decode(){if(decodeFails)throw Error('decode');}},URL:{createObjectURL:()=> 'blob:ref',revokeObjectURL(){}},
    fetch:async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>path==='/api/reference'?{id:'a'.repeat(32),image:'/references/a.png'}:path==='/api/status'?job:{}};}});
  vm.runInContext(fs.readFileSync('web/app.js','utf8'),context);
  return {elements,query,timers,calls,intervals,advance:ms=>{now+=ms;intervals.forEach(fn=>fn());}};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function completedHarness(job,...args) {
 const state={state:'idle'};const h=harness(state,...args);await tick();Object.assign(state,job);await h.timers.shift()();return h;
}
test('reload hides the previous result and keeps it hidden on later polls',async()=>{
 const h=harness({state:'done',id:'old',image:'/images/old.png',last_result:{id:'old',image:'/images/old.png'}});await tick();assert.equal(h.query('#wallpaper').hidden,true);assert.equal(h.query('#save').hidden,true);await h.timers.shift()();assert.equal(h.query('#wallpaper').hidden,true);
});
test('failed image leaves input available and the saved PNG can be retried on poll',async()=>{
 const h=await completedHarness({state:'done',id:'bad',image:'/images/bad.png'},[1920,1080],true);await tick();
 assert.equal(h.query('#prompt').disabled,false);assert.equal(h.query('#save').hidden,true);assert.match(h.query('#status').textContent,/imagem|PNG/);
 await h.timers.shift()();assert.equal(h.query('#prompt').disabled,false);
});
test('display and download use the exact final backend PNG without canvas conversion',async()=>{
 const h=await completedHarness({state:'done',id:'good',image:'/images/final.png',width:1920,height:1080});await tick();
 assert.equal(h.query('#save').href,'/images/final.png');assert.equal(h.query('#wallpaper').src,h.query('#save').href);assert.equal(h.query('#save').hidden,false);
});
test('wrong final resolution is rejected',async()=>{
 const h=await completedHarness({state:'done',id:'wrong',image:'/images/wrong.png'},[768,448]);await tick();assert.equal(h.query('#save').hidden,true);assert.equal(h.query('#prompt').disabled,false);
});
test('live steps update the estimate; upscaling and recovery remain separate',async()=>{
 const sampling=harness({state:'running',phase:'generating',elapsed:20,progress:{stage:'sampling',unit:'steps',completed:2,total:9,remaining_seconds:70}});await tick();assert.match(sampling.query('#time-estimate').title,/2\/9.*1min 10s/);sampling.advance(1000);assert.match(sampling.query('#status').textContent,/0min 21s/);sampling.advance(1000);assert.match(sampling.query('#status').textContent,/0min 22s/);
 const running=harness({state:'running',phase:'upscaling',elapsed:130});await tick();assert.equal(running.query('#prompt').disabled,true);assert.match(running.query('#status').textContent,/Ampliando.*2min 10s/);assert.equal(running.query('#time-estimate').hidden,false);assert.match(running.query('#time-estimate').title,/Ampliando/);
 const upscale=harness({state:'running',phase:'upscaling',elapsed:150,progress:{unit:'percent',completed:50,total:100,remaining_seconds:20}});await tick();assert.match(upscale.query('#time-estimate').title,/50%.*0min 20s/);
 const recovery=harness({state:'error',id:'b'.repeat(32),error:'Falha',retryable:true});await tick();assert.equal(recovery.query('#retry-finalize').hidden,false);await recovery.query('#retry-finalize').events.click();assert.equal(recovery.calls.at(-1).path,`/api/jobs/${'b'.repeat(32)}/retry-finalize`);
});
test('upload attaches reference list and removing it clears the next request',async()=>{
 const h=harness({state:'idle',profile:'klein'});await tick();assert.equal(h.query('#add-reference').disabled,false);h.query('#reference-file').files=[{type:'image/jpeg',size:128,name:'ref.jpg'}];h.query('#prompt').value='change sky';
 await h.query('#reference-file').events.change();assert.equal(h.query('#reference-preview').hidden,false);
 assert.equal(h.query('#add-reference').hidden,false);
 assert.equal(h.query('#add-reference').disabled,false);
 await h.query('#form').events.submit({preventDefault(){}});let call=h.calls.find(c=>c.path==='/api/generate');assert.deepEqual(JSON.parse(call.options.body).reference,['a'.repeat(32)]);
 await h.timers.shift()();const remove=h.query('#reference-preview').children[0].children[2];remove.events.click();assert.equal(h.query('#reference-preview').hidden,true);
 await h.query('#form').events.submit({preventDefault(){}});call=h.calls.filter(c=>c.path==='/api/generate').at(-1);assert.deepEqual(JSON.parse(call.options.body).reference,[]);
});
