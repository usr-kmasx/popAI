const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function harness(job, dimensions=[1920,1080], decodeFails=false, randomSeed=39, storage=new Map(), localStorage=new Map()) {
  const elements={}, timers=[], calls=[], intervals=[], windowEvents={},frameMessages=[];let now=0;
  function element() {return {style:{},scrollHeight:58,value:'',disabled:false,hidden:true,children:[],events:{},dataset:{},classList:{add(){},remove(){},toggle(){}},setAttribute(){},removeAttribute(name){delete this[name];},focus(){},click(){},showModal(){this.open=true;},close(){this.open=false;this.events.close?.();},querySelectorAll(){return [];},replaceWith(replacement){for(const key of Object.keys(elements))if(elements[key]===this)elements[key]=replacement;},replaceChildren(...items){this.children=items;},append(...items){this.children.push(...items);},addEventListener(event,handler){this.events[event]=handler;}};}
  const query = id => elements[id] ||= element();
  query('#sketch-frame').contentWindow = {postMessage(message,origin){frameMessages.push({message,origin});}};
  Object.assign(query('#wallpaper'),{naturalWidth:dimensions[0],naturalHeight:dimensions[1],async decode(){if(decodeFails) throw Error('decode');}});
  const context=vm.createContext({crypto:{getRandomValues(values){values[0]=randomSeed;return values;}},
    document:{addEventListener(){},querySelector:query,createElement:kind=>kind==='canvas'?{getContext:()=>({drawImage(){}}),toBlob:cb=>cb({size:12})}:element()},
    window:{location:{origin:'http://127.0.0.1:7860'},addEventListener(event,handler){windowEvents[event]=handler;},setTimeout:fn=>timers.push(fn),setInterval:fn=>intervals.push(fn),sessionStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},localStorage:{getItem:key=>localStorage.get(key)??null,setItem:(key,value)=>localStorage.set(key,value),removeItem:key=>localStorage.delete(key)}},performance:{now:()=>now},Blob,Image:class {constructor(){Object.assign(this,element(),{naturalWidth:dimensions[0],naturalHeight:dimensions[1]});}async decode(){if(decodeFails)throw Error('decode');}},URL:{createObjectURL:()=> 'blob:ref',revokeObjectURL(){}},
    fetch:async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>{if(path==='/api/reference'){const letter=['a','b','c','d','e','f'][calls.filter(call=>call.path==='/api/reference').length-1];return {id:letter.repeat(32),image:`/references/${letter.repeat(32)}.png`};}return path.split('?')[0]==='/api/status'?job:{};}};}});
  vm.runInContext(fs.readFileSync('web/app.js','utf8'),context);
  return {elements,query,timers,calls,intervals,windowEvents,frameMessages,advance:ms=>{now+=ms;intervals.forEach(fn=>fn());}};
}
test('drawing button follows the selected model and submits a sketch through reference upload',async()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 const css=fs.readFileSync('web/style.css','utf8');
 const sketch=fs.readFileSync('web/sketch.js','utf8');
 assert.match(html,/id="add-reference"[^>]*>[\s\S]*?id="draw-reference"/);
 assert.match(css,/#draw-reference\{[^}]*left:49px/);
 assert.match(sketch,/popai-sketch:submit/);
 assert.match(sketch,/popai-sketch:close/);
 const storage=new Map();
 const h=harness({state:'idle',profile:'flux-2-klein',enhancer:{state:'ready'}},undefined,undefined,undefined,storage);
 await tick();
 const button=h.query('#draw-reference'), dialog=h.query('#sketch-dialog'),frame=h.query('#sketch-frame');
 assert.equal(button.hidden,false);
 assert.equal(button.disabled,false);
 button.events.click();
 assert.equal(dialog.open,true);
 assert.equal(frame.src,'/sketch.html');
 const blob=new Blob(['sketch-png'],{type:'image/png'});
 const state={version:1,items:[{kind:'text',x:120,y:180,w:24,color:'#ffffff',value:'Original'}],color:'#ffffff',size:8,shape:'rect'};
 const source=frame.contentWindow;
 await h.windowEvents.message({origin:'https://wrong.example',source,data:{type:'popai-sketch:submit',blob}});
 await h.windowEvents.message({origin:'http://127.0.0.1:7860',source:{},data:{type:'popai-sketch:submit',blob}});
 assert.equal(h.calls.filter(c=>c.path==='/api/reference').length,0);
 await h.windowEvents.message({origin:'http://127.0.0.1:7860',source,data:{type:'popai-sketch:submit',blob,state}});
 assert.equal(h.calls.filter(c=>c.path==='/api/reference').length,1);
 const posted=h.calls.find(c=>c.path==='/api/reference');
 assert.equal(posted.options.body,blob);
 assert.equal(posted.options.headers['Content-Type'],'image/png');
 assert.equal(dialog.open,false);
 assert.equal(h.query('#reference-preview').children.length,1);
 assert.equal(h.query('#reference-preview').children[0].children[0].children[0].alt,'Image 1: Sketch 4:3');
 assert.equal(button.hidden,false);
 button.events.click();
 assert.equal(dialog.open,true);
 await h.windowEvents.message({origin:'http://127.0.0.1:7860',source,data:{type:'popai-sketch:close'}});
 assert.equal(dialog.open,false);
 assert.equal(h.calls.filter(c=>c.path==='/api/reference').length,1);
 const sketchThumb=h.query('#reference-preview').children[0].children[0];
 await sketchThumb.events.click();
 assert.equal(dialog.open,true,'Sketch thumbnail reopens the editor');
 frame.events.load();
 assert.deepEqual(JSON.stringify(h.frameMessages.at(-1).message.state),JSON.stringify(state),'The editor receives the original editable layers');
 const updated={...state,items:[...state.items,{kind:'pen',color:'#ff0000',w:5,points:[{x:5,y:5},{x:9,y:9}]}]};
 await h.windowEvents.message({origin:'http://127.0.0.1:7860',source,data:{type:'popai-sketch:submit',blob,state:updated}});
 assert.equal(h.query('#reference-preview').children.length,1,'Editing replaces reference in place');
 assert.equal(h.calls.filter(c=>c.path==='/api/reference').length,2);
 assert.ok(h.calls.some(call=>call.path==='/api/references/release' && call.options.body.includes('a'.repeat(32))),'Replaced PNG is released');
 assert.equal(JSON.stringify(JSON.parse(storage.get('popai.composer-session')).references[0].sketch),JSON.stringify(updated),'Layer data persists with the reference');
 const reloaded=harness({state:'idle',profile:'flux-2-klein'},undefined,undefined,undefined,storage);
 await tick();
 assert.equal(reloaded.query('#reference-preview').children.length,1,'Reference survives page reload');
 await reloaded.query('#reference-preview').children[0].children[0].events.click();
 reloaded.query('#sketch-frame').events.load();
 assert.equal(JSON.stringify(reloaded.frameMessages.at(-1).message.state),JSON.stringify(updated),'Editable layers survive page reload');

 const z=harness({state:'idle',profile:'z-image-turbo'});
 await tick();
 assert.equal(z.query('#draw-reference').hidden,true);
 z.query('#draw-reference').events.click();
 assert.notEqual(z.query('#sketch-dialog').open,true);
});

test('uploaded reference thumbnails open a full-size preview without modifying the reference',async()=>{
 const h=harness({state:'idle',profile:'flux-2-klein'});
 await tick();
 h.query('#reference-file').files=[{type:'image/png',size:400,name:'landscape.png'}];
 await h.query('#reference-file').events.change();
 const thumbnail=h.query('#reference-preview').children[0].children[0];
 assert.equal(thumbnail.children[0].alt,'Image 1: landscape.png');
 await thumbnail.events.click();
 assert.equal(h.query('#reference-dialog').open,true);
 assert.equal(h.query('#reference-large').alt,'landscape.png');
 assert.equal(h.query('#reference-large').src,'/references/'+'a'.repeat(32)+'.png');
 assert.equal(h.calls.filter(c=>c.path==='/api/reference').length,1);
 h.query('#reference-close').events.click();
 assert.equal(h.query('#reference-dialog').open,false);
 assert.equal(h.query('#reference-preview').children.length,1);
});

test('Generate and New controls stay visible without input hover',async()=>{
 const css=fs.readFileSync('web/style.css','utf8');
 assert.match(css,/\.new-generation-slot\{[^}]*pointer-events:auto/);
 assert.doesNotMatch(css,/\.composer:has\(form:hover\) \.new-generation-slot/);
 assert.doesNotMatch(css,/\.new-generation-slot:has\(#new-generation:disabled\)/);
 assert.match(css,/\.composer-status\{max-width:calc\(100% - 180px\)/);
 const h=harness({state:'idle'});await tick();
 assert.equal(h.query('#new-generation').disabled,false);
 assert.equal(h.query('#generate-image').disabled,true);
 h.query('#prompt').value='Landscape';
 h.query('#prompt').events.input();
 assert.equal(h.query('#generate-image').disabled,false);
 assert.equal(h.query('#new-generation').disabled,false);
});
test('prompt hides only by the gear hover action and reopens from the status area',async()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 const app=fs.readFileSync('web/app.js','utf8');
 assert.doesNotMatch(app,/scheduleComposerCollapse|composerIdleTimer/);
 assert.match(html,/id="model-options"/);
 assert.match(html,/id="hide-composer"/);
 assert.doesNotMatch(html,/id="expand-composer"/);
 const h=harness({state:'idle'});await tick();
 const fields=h.query('#composer-fields');
 const options=h.query('#model-options');
 assert.notEqual(fields.inert,true);
 h.query('#model-control').events.pointerenter({pointerType:'mouse'});
 assert.equal(options.hidden,false);
 h.query('#hide-composer').events.click();
 assert.equal(fields.inert,true);
 assert.equal(options.hidden,true);
 h.query('.composer-message').events.pointerenter({pointerType:'mouse'});
 assert.equal(fields.inert,false);
 h.query('.composer-message').events.pointerleave?.({pointerType:'mouse'});
 assert.equal(fields.inert,false);
});
test('Undo is the last enhancement option and appears only with a restorable prompt',async()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 const menu=html.split('id="enhance-options"')[1].split('</div>')[0];
 assert.ok(menu.indexOf('data-mode="cinematic"') < menu.indexOf('id="undo-enhance"'));
 assert.equal((html.match(/id="undo-enhance"/g)||[]).length,1);
 const fresh=harness({state:'idle',enhancer:{state:'ready'}});await tick();
 assert.equal(fresh.query('#undo-enhance').hidden,true);

 const store=new Map([['popai.prompt-state',JSON.stringify({version:1,text:'Enhanced sky',undo:{original:'Blue sky',enhanced:'Enhanced sky'}})]]);
 const restored=harness({state:'idle',enhancer:{state:'loading'}},undefined,undefined,undefined,undefined,store);
 await tick();
 assert.equal(restored.query('#prompt').value,'Enhanced sky');
 assert.equal(restored.query('#undo-enhance').hidden,false);
 assert.equal(restored.query('#enhance-prompt').disabled,false);
 restored.query('#enhance-control').events.pointerenter({pointerType:'mouse'});
 assert.equal(restored.query('#enhance-options').hidden,false);
 restored.query('#undo-enhance').events.click();
 assert.equal(restored.query('#prompt').value,'Blue sky');
 assert.equal(restored.query('#undo-enhance').hidden,true);
 assert.equal(restored.query('#enhance-options').hidden,true);
 assert.equal(restored.query('#enhance-prompt').disabled,true);
 assert.equal(JSON.parse(store.get('popai.prompt-state')).undo,null);

 const editStore=new Map([['popai.prompt-state',JSON.stringify({version:1,text:'Enhanced sky',undo:{original:'Blue sky',enhanced:'Enhanced sky'}})]]);
 const edited=harness({state:'idle',enhancer:{state:'ready'}},undefined,undefined,undefined,undefined,editStore);
 await tick();
 edited.query('#prompt').value='Manual revision';
 edited.query('#prompt').events.input();
 assert.equal(edited.query('#undo-enhance').hidden,true);
});
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function completedHarness(job,...args) {
 const state={state:'idle'};const h=harness(state,...args);await tick();Object.assign(state,job);await h.timers.shift()();return h;
}
test('reload retains the references and result until New clears only the result',async()=>{
 const id='b'.repeat(32), storage=new Map(), job={state:'done',id,image:`/images/${id}.png`,profile:'klein'};
 const first=harness(job,[1920,1080],false,41,storage);
 await tick();
 first.query('#reference-file').files=[{type:'image/jpeg',size:128,name:'ref.jpg'}];
 await first.query('#reference-file').events.change();
 first.windowEvents.pagehide({persisted:false});
 assert.equal(first.calls.some(call=>call.path==='/api/references/release'),false);

 const reloaded=harness(job,[1920,1080],false,42,storage);
 await tick();
 assert.equal(reloaded.query('#wallpaper').hidden,false);
 assert.equal(reloaded.query('#save').href,job.image);
 assert.equal(reloaded.query('#reference-preview').children.length,1);
 assert.ok(reloaded.calls.some(call=>call.path==='/api/status?references='+'a'.repeat(32)));
 reloaded.query('#prompt').value='Change the sky';
 reloaded.query('#new-generation').events.click();
 assert.equal(reloaded.query('#wallpaper').hidden,true);
 assert.equal(reloaded.query('#save').hidden,true);
 assert.equal(reloaded.query('#prompt').value,'Change the sky');
 assert.equal(reloaded.query('#reference-preview').children.length,1);
 assert.equal(reloaded.calls.some(call=>call.path==='/api/generate'),false);
 await reloaded.timers.shift()();
 assert.equal(reloaded.query('#wallpaper').hidden,true);
 await reloaded.query('#form').events.submit({preventDefault(){}});
 const request=JSON.parse(reloaded.calls.find(call=>call.path==='/api/generate').options.body);
 assert.notEqual(request.seed,42);
 assert.deepEqual(request.reference,['a'.repeat(32)]);

 const reset=harness(job,[1920,1080],false,44,storage);
 await tick();
 assert.equal(reset.query('#wallpaper').hidden,true);
 assert.equal(reset.query('#reference-preview').children.length,1);
});
test('failed image leaves input available and the saved PNG can be retried on poll',async()=>{
 const h=await completedHarness({state:'done',id:'bad',image:'/images/bad.png'},[1920,1080],true);await tick();
 assert.equal(h.query('#prompt').disabled,false);assert.equal(h.query('#save').hidden,true);assert.match(h.query('#status').textContent,/image|PNG/);
 await h.timers.shift()();assert.equal(h.query('#prompt').disabled,false);
});
test('display and download use the exact final backend PNG without canvas conversion',async()=>{
 const h=await completedHarness({state:'done',id:'good',image:'/images/final.png',width:1920,height:1080});await tick();
 assert.equal(h.query('#save').href,'/images/final.png');assert.equal(h.query('#wallpaper').src,h.query('#save').href);assert.equal(h.query('#save').hidden,false);
 assert.match(h.query('#save').download, /^popAI-[a-z]{6}\.png$/);
});
test('wrong final resolution is rejected',async()=>{
 const h=await completedHarness({state:'done',id:'wrong',image:'/images/wrong.png'},[768,448]);await tick();assert.equal(h.query('#save').hidden,true);assert.equal(h.query('#prompt').disabled,false);
});
test('live steps update the estimate; upscaling and recovery remain separate',async()=>{
 const sampling=harness({state:'running',phase:'generating',elapsed:20,progress:{stage:'sampling',unit:'steps',completed:2,total:9,remaining_seconds:70}});await tick();assert.match(sampling.query('#estimate-message').textContent,/2\/9.*1min 10s/);sampling.advance(1000);assert.match(sampling.query('#status').textContent,/0min 21s/);assert.match(sampling.query('#estimate-message').textContent,/2\/9.*1min 9s/);sampling.advance(1000);assert.match(sampling.query('#status').textContent,/0min 22s/);
 const running=harness({state:'running',phase:'upscaling',elapsed:130});await tick();assert.equal(running.query('#prompt').disabled,true);assert.match(running.query('#status').textContent,/Upscaling.*2min 10s/);assert.equal(running.query('#time-estimate').hidden,false);assert.match(running.query('#estimate-message').textContent,/Upscaling/);
 const upscale=harness({state:'running',phase:'upscaling',elapsed:150,progress:{unit:'percent',completed:50,total:100,remaining_seconds:20}});await tick();assert.match(upscale.query('#estimate-message').textContent,/50%.*0min 20s/);upscale.advance(1000);assert.match(upscale.query('#estimate-message').textContent,/50%.*0min 19s/);
 const recovery=harness({state:'error',id:'b'.repeat(32),error:'Failed',retryable:true});await tick();assert.equal(recovery.query('#retry-finalize').hidden,false);await recovery.query('#retry-finalize').events.click();assert.equal(recovery.calls.at(-1).path,`/api/jobs/${'b'.repeat(32)}/retry-finalize`);
});
test('the running clock names its stage and the final time includes the whole job',async()=>{
 const job={id:'timed',state:'running',phase:'generating',elapsed:8,progress:{stage:'conditioning'}};
 const h=harness(job);await tick();
 assert.match(h.query('#status').textContent,/Preparing generation.*Total 0min 8s/);
 Object.assign(job,{elapsed:12,progress:{stage:'sampling',unit:'steps',completed:0,total:4}});
 await h.timers.shift()();
 assert.match(h.query('#status').textContent,/Generating image.*Total 0min 12s/);
 assert.equal(h.query('#estimate-message').textContent,'0/4 steps');
 Object.assign(job,{elapsed:26,progress:{stage:'vae_decode'}});
 await h.timers.shift()();
 assert.match(h.query('#status').textContent,/Decoding image.*Total 0min 26s/);
 Object.assign(job,{phase:'upscaling',elapsed:31});
 await h.timers.shift()();
 assert.match(h.query('#status').textContent,/Upscaling.*Total 0min 31s/);
 Object.assign(job,{state:'done',phase:'done',elapsed:38,image:'/images/timed.png',width:1920,height:1080});
 await h.timers.shift()();await tick();
 assert.match(h.query('#status').textContent,/Ready.*Total 0min 38s/);
 h.advance(5000);
 assert.match(h.query('#status').textContent,/Total 0min 38s/);
 assert.equal(h.query('#time-estimate').hidden,true);
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
test('generations reuse the page seed and reopening the page draws a new one',async()=>{
 const job={state:'idle',profile:'z-image-turbo'};
 const h=harness(job,[1920,1080],false,41);await tick();
 h.query('#prompt').value='first prompt';
 await h.query('#form').events.submit({preventDefault(){}});
 await h.timers.shift()();
 job.profile='klein';
 h.query('#prompt').value='second prompt';
 await h.query('#form').events.submit({preventDefault(){}});
 const seeds=h.calls.filter(call=>call.path==='/api/generate').map(call=>JSON.parse(call.options.body).seed);
 assert.deepEqual(seeds,[41,41]);
 const reloaded=harness(job,[1920,1080],false,42);await tick();
 reloaded.query('#prompt').value='second prompt';
 await reloaded.query('#form').events.submit({preventDefault(){}});
 const request=reloaded.calls.find(call=>call.path==='/api/generate');
 assert.equal(JSON.parse(request.options.body).seed,42);
});
