const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function harness(job, dimensions=[1920,1080], decodeFails=false, randomSeed=39, storage=new Map(), localStorage=new Map(), setup=null) {
  const elements={}, timers=[], holds=new Map(), calls=[], intervals=[], windowEvents={},frameMessages=[];let now=0;
  function element() {return {style:{setProperty(){},removeProperty(){}},scrollHeight:58,value:'',disabled:false,hidden:true,children:[],events:{},dataset:{},classList:{add(){},remove(){},toggle(){}},setAttribute(){},removeAttribute(name){delete this[name];},focus(){},click(){},getBoundingClientRect(){return {left:0,top:0,width:100,height:50};},showModal(){this.open=true;},close(){this.open=false;this.events.close?.();},querySelector(selector){this._queries ||= {}; return this._queries[selector] ||= element();},querySelectorAll(){return [];},replaceWith(replacement){for(const key of Object.keys(elements))if(elements[key]===this)elements[key]=replacement;},replaceChildren(...items){this.children=items;},append(...items){this.children.push(...items);},addEventListener(event,handler){this.events[event]=handler;}};}
  const query = id => elements[id] ||= element();
  const popup=query('#thought-popup');
  const sections=['corrector','enhancer'].map(phase=>Object.assign(element(),{dataset:{phase}}));
  popup.querySelectorAll=()=>sections;
  query('#sketch-frame').contentWindow = {postMessage(message,origin){frameMessages.push({message,origin});}};
  Object.assign(query('#wallpaper'),{naturalWidth:dimensions[0],naturalHeight:dimensions[1],async decode(){if(decodeFails) throw Error('decode');}});
  if (setup) setup({query,element});
  const context=vm.createContext({AbortController,TextDecoder,matchMedia:()=>({matches:true}),crypto:{getRandomValues(values){values[0]=randomSeed;return values;}},
    Option:class {constructor(text,value){this.textContent=text;this.value=value;}},
    document:{addEventListener(){},querySelector:query,createElement:kind=>kind==='canvas'?{getContext:()=>({drawImage(){}}),toBlob:cb=>cb({size:12})}:element()},
    window:{location:{origin:'http://127.0.0.1:7860'},addEventListener(event,handler){windowEvents[event]=handler;},setTimeout:(fn,delay)=>{if(delay>=2500){const token=Symbol();holds.set(token,{fn,due:now+delay});return token;}return timers.push(fn);},clearTimeout:token=>holds.delete(token),setInterval:fn=>intervals.push(fn),sessionStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},localStorage:{getItem:key=>localStorage.get(key)??null,setItem:(key,value)=>localStorage.set(key,value),removeItem:key=>localStorage.delete(key)}},performance:{now:()=>now},Blob,Image:class {constructor(){Object.assign(this,element(),{naturalWidth:dimensions[0],naturalHeight:dimensions[1]});}async decode(){if(decodeFails)throw Error('decode');}},URL:{createObjectURL:()=> 'blob:ref',revokeObjectURL(){}},
    fetch:async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>{if(path==='/api/reference'){const letter=['a','b','c','d','e','f'][calls.filter(call=>call.path==='/api/reference').length-1];return {id:letter.repeat(32),image:`/references/${letter.repeat(32)}.png`};}return path.split('?')[0]==='/api/status'?(job.legacy?job:{...job,enhancer:{state:'stopped',...job.enhancer,options:job.enhancer?.options||{corrector:true,enhancer:true,lite:false}}}):{};}};}});
  vm.runInContext(fs.readFileSync('web/app.js','utf8'),context);
  return {elements,query,timers,calls,intervals,windowEvents,frameMessages,context,advance:ms=>{now+=ms;intervals.forEach(fn=>fn());for(const [token,item] of holds){if(item.due<=now){holds.delete(token);item.fn();}}}};
}
test('generation profile UI has three expandable model groups and seven approved preset IDs',()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 const groups=[...html.matchAll(/class="profile-card" data-family="([^"]+)"/g)].map(x=>x[1]);
 assert.deepEqual(groups,['z-image-turbo','klein','qwen-image21-experimental']);
 const variants=[...html.matchAll(/class="profile-preset" data-profile="([^"]+)"/g)].map(x=>x[1]);
 assert.deepEqual(variants,['default','z-image-5','z-image-4','klein','klein-3','qwen-image21-experimental','qwen-image21-4']);
 assert.match(html,/<select id="model-profile" hidden/);
 assert.match(html,/data-profile="qwen-image21-experimental"[^>]*>.*Original · 8 steps<\/span><small>Default<\/small>/);
 assert.match(html,/data-profile="qwen-image21-4"[^>]*>.*Fast · 4 steps/);
 assert.doesNotMatch(html,/Experimental · 4 steps/);
 assert.match(html,/id="profile-custom"/);
 assert.match(html,/id="sd-steps"/);
 assert.match(html,/id="sd-vae-tiling"/);
});

test('profile cards expand, choose existing presets, and mark edits as Custom',()=>{
 const familyPresets=[
  ['z-image-turbo',[['default',9],['z-image-5',5],['z-image-4',4]]],
  ['klein',[['klein',4],['klein-3',3]]],
  ['qwen-image21-experimental',[['qwen-image21-experimental',8],['qwen-image21-4',4]]]
 ];
 const cards=[], labels=[];
 const h=harness({state:'idle'},undefined,false,39,new Map(),new Map(),({query,element})=>{
  for(const [family,options] of familyPresets){
    const card=element(),toggle=element(),panel=element(),marker=element(),steps=element();
    card.dataset.family=family;steps.textContent=options[0][1]+' steps';
    const classes=new Set();card.classList={toggle(key,yes){if(yes)classes.add(key);else classes.delete(key);},contains:key=>classes.has(key)};
    const rows=options.map(([preset,n],i)=>{
      const label=element(),radio=element(),span=element(),small=i===0?element():null;
      label.dataset.profile=preset;radio.value=preset;span.textContent=`Original · ${n} steps`;
      label.querySelector=key=>({'input':radio,'small':small})[key]||null;
      return {label,radio,span};
    });
    card.querySelector=key=>({
      '.profile-card-toggle':toggle,'.profile-variants':panel,
      '.profile-current-marker':marker,'.profile-card-steps':steps,
      '.profile-preset span':rows[0].span
    })[key];
    cards.push({card,toggle,panel,marker,steps,rows});labels.push(...rows.map(r=>r.label));
  }
  query('#profile-list').querySelectorAll=key=>key==='.profile-card'?cards.map(row=>row.card):key==='.profile-preset'?labels:[];
 });
 const defaults={steps:8,cfg:1,sampler:'euler',scheduler:'simple',vae_tiling:true,vae_tile_size:0,mmap:true};
 const sdDefaults=Object.fromEntries(familyPresets.flatMap(([family,options])=>options.map(([profile,n])=>[profile,{...defaults,steps:n,scheduler:family==='klein'?'flux2':family==='qwen-image21-experimental'?'simple':'auto'}])));
 const families=Object.fromEntries(familyPresets.flatMap(([family,options])=>options.map(([profile])=>[profile,family])));
 const profiles=Object.fromEntries(familyPresets.map(([family])=>[family,{family}]));
 h.context.testingCatalog={selected:{sd_defaults:sdDefaults},sd_profile_families:families,profiles,profile_files:{},components:{}};
 h.query('#model-profile').value='qwen-image21-experimental';
 vm.runInContext('modelCatalog=testingCatalog; modelFiles=[]; activeFamily="qwen-image21-experimental"; customDraft={...modelCatalog.selected.sd_defaults["qwen-image21-experimental"]}; customModel={profile:"qwen-image21-experimental"}; choosePreset()',h.context);
 assert.equal(cards[2].panel.hidden,false);
 assert.equal(cards[2].marker.hidden,false);
 assert.equal(cards[2].rows[0].radio.checked,true);
 cards[1].toggle.events.click();
 assert.equal(cards[1].panel.hidden,false,'Clicking the family expands it');
 assert.equal(cards[2].panel.hidden,true,'Only one family is expanded');
 assert.equal(h.query('#model-profile').value,'qwen-image21-experimental','Expansion does not change the saved choice');
 cards[1].rows[1].radio.events.change();
 assert.equal(h.query('#model-profile').value,'klein-3');
 assert.equal(h.query('#sd-steps').value,3);
 assert.equal(h.query('#sd-scheduler').value,'flux2');
 assert.equal(cards[1].marker.hidden,false);
 assert.equal(cards[1].rows[1].radio.checked,true);
 h.query('#sd-steps').value='7';h.query('#sd-steps').events.input();
 assert.equal(h.query('#model-profile').value,'custom');
 assert.equal(h.query('#profile-mode').textContent,'Custom settings');
 assert.equal(cards[1].marker.hidden,false);
 assert.equal(cards[1].steps.textContent,'7 steps');
 cards[2].toggle.events.click();cards[2].rows[0].radio.events.change();
 assert.equal(h.query('#model-profile').value,'qwen-image21-experimental');
 assert.equal(h.query('#sd-steps').value,8);
 cards[2].rows[1].radio.events.change();
 assert.equal(h.query('#model-profile').value,'qwen-image21-4');
 assert.equal(h.query('#sd-steps').value,4);
 assert.equal(h.query('#sd-scheduler').value,'simple');
 assert.equal(cards[2].rows[1].radio.checked,true);
 h.query('#profile-custom').events.click();
 assert.equal(h.query('#model-profile').value,'custom');
});

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

test('official Qwen 2.1 profile enables uploaded and drawn references',async()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 assert.match(html,/<option value="qwen-image21-experimental">Qwen Image 2.1 · 8 steps \(default\)/);
 const h=harness({state:'idle',profile:'qwen-image21-experimental'});
 await tick();
 assert.equal(h.query('#add-reference').disabled,false);
 assert.equal(h.query('#draw-reference').hidden,false);
 h.query('#reference-file').files=[{type:'image/png',size:400,name:'qwen-ref.png'}];
 await h.query('#reference-file').events.change();
 assert.equal(h.query('#reference-preview').children.length,1);
 assert.equal(h.query('#prompt').placeholder,'Describe the edit you want…');
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
 assert.match(css,/\.composer-status\{max-width:calc\(100% - 244px\)/);
 const h=harness({state:'idle'});await tick();
 assert.equal(h.query('#new-generation').disabled,false);
 assert.equal(h.query('#generate-image').disabled,true);
 h.query('#prompt').value='Landscape';
 h.query('#prompt').events.input();
 assert.equal(h.query('#generate-image').disabled,false);
 assert.equal(h.query('#new-generation').disabled,false);
});
test('Hide sits beside Generate and New, gear has no hover menu, and status reopens prompt',async()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 const app=fs.readFileSync('web/app.js','utf8');
 assert.doesNotMatch(app,/scheduleComposerCollapse|composerIdleTimer/);
 assert.doesNotMatch(html,/id="model-options"/);
 assert.match(html,/<div class="new-generation-slot">[\s\S]*?id="generate-image"[\s\S]*?id="new-generation"[\s\S]*?id="hide-composer"/);
 assert.doesNotMatch(html,/id="expand-composer"/);
 const h=harness({state:'idle'});await tick();
 const fields=h.query('#composer-fields');
 assert.notEqual(fields.inert,true);
 assert.equal(h.query('#model-control').events.pointerenter,undefined);
 assert.equal(typeof h.query('#model-button').events.click,'function');
 h.query('#hide-composer').events.click();
 assert.equal(fields.inert,true);
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
test('all enhancement modes keep the original input until a complete final prompt and undo restores it',async()=>{
 const original='um homem com cabelo branco ao lado do carro';
 for (const mode of ['simple','detailed','creative','cinematic']) {
   const store=new Map();
   const h=harness({state:'idle',enhancer:{state:'ready'}},undefined,undefined,undefined,undefined,store);
   await tick();
   h.query('#prompt').value=original;
   h.query('#prompt').events.input();
   const encode=new TextEncoder();
   const lines=[
     {state:'started'},
     {stage:'corrector'},
     {phase:'corrector',thought:'Local reasoning'},
     {phase:'corrector',answer:'Corrected English'},
     {stage:'enhancer'},
     {phase:'enhancer',thought:'Local enhancer reasoning'},
     {phase:'enhancer',answer:'A finished English prompt.'},
     {text:'A finished '},
     {text:'English prompt.'},
     {state:'done',seconds:5.5},
   ];
   let i=0;
   const fetch=h.context.fetch;
   h.context.fetch=async(path,options)=>{
     if(path!=='/api/enhance')return fetch(path,options);
     assert.deepEqual(JSON.parse(options.body),{prompt:original,editing:false,mode});
     return {ok:true,body:{getReader:()=>({read:async()=>{
       assert.equal(h.query('#prompt').value,original,'No intermediate input change');
       const sections=h.query('#thought-popup').querySelectorAll();
       if(i<=2)assert.equal(h.query('#thought-popup').hidden,true);
       if(i===3){
         assert.equal(h.query('#thought-popup').hidden,false);
         assert.equal(sections[0].querySelector('.thought-text').textContent,'Local reasoning');
         assert.equal(h.query('#mascot').dataset.corrector,'active');
         assert.equal(h.query('#mascot').dataset.placement,'center');
         h.query('#thought-toggle').events.click();
         assert.equal(h.query('#thought-popup').hidden,true);
         assert.equal(h.query('#mascot').querySelector('.eye-corrector').disabled,false);
       }
       if(i===4)assert.equal(sections[0].querySelector('.thought-answer-text').textContent,'Corrected English');
       if(i===5){
         assert.equal(h.query('#mascot').dataset.enhancer,'active');
         assert.equal(h.query('#mascot').querySelector('.eye-corrector').disabled,true);
         assert.equal(h.query('#mascot').querySelector('.eye-enhancer').disabled,false);
         h.query('#mascot').querySelector('.eye-enhancer').events.click();
         assert.equal(h.query('#thought-popup').hidden,true);
       }
       if(i===6)assert.equal(h.query('#thought-popup').hidden,false);
       if(i===7){
         assert.equal(sections[1].querySelector('.thought-text').textContent,'Local enhancer reasoning');
         assert.equal(sections[1].querySelector('.thought-answer-text').textContent,'A finished English prompt.');
       }
       if(i===lines.length)return {done:true};
       return {done:false,value:encode.encode(JSON.stringify(lines[i++])+'\n')};
     }})}};
   };
   await vm.runInContext(`improvePrompt('${mode}')`,h.context);
   assert.equal(h.query('#prompt').value,'A finished English prompt.');
   assert.equal(h.query('#thought-popup').hidden,false);
   h.advance(2999);assert.equal(h.query('#thought-popup').hidden,false);
   h.advance(1);assert.equal(h.query('#thought-popup').hidden,true);
   assert.equal(h.query('#mascot').dataset.corrector,'idle');
   assert.equal(h.query('#mascot').dataset.enhancer,'idle');
   assert.equal(h.query('#undo-enhance').hidden,false);
   assert.equal(JSON.parse(store.get('popai.prompt-state')).undo.original,original);
   h.query('#undo-enhance').events.click();
   assert.equal(h.query('#prompt').value,original);
 }
});

test('failed or canceled enhancement preserves the original input and prior undo',async()=>{
 for(const failure of ['error','interrupted','cancel']){
   const original='Previously enhanced text';
   const store=new Map([['popai.prompt-state',JSON.stringify({version:1,text:original,undo:{original:'Initial raw idea',enhanced:original}})]]);
   const h=harness({state:'idle',enhancer:{state:'ready'}},undefined,undefined,undefined,undefined,store);
   await tick();
   const encode=new TextEncoder();
   const fetch=h.context.fetch;
   let i=0;
   h.context.fetch=async(path,options)=>{
     if(path!=='/api/enhance')return fetch(path,options);
     return {ok:true,body:{getReader:()=>({read:async()=>{
       assert.equal(h.query('#prompt').value,original);
       if(i++===0)return {done:false,value:encode.encode('{"state":"working"}\n{"text":"Incomplete text"}\n')};
       if(failure==='error')return {done:false,value:encode.encode('{"error":"Request failed."}\n')};
       if(failure==='cancel'){
         h.query('#cancel-enhance').events.click();
         assert.equal(options.signal.aborted,true);
         throw Object.assign(new Error('Canceled'),{name:'AbortError'});
       }
       return {done:true};
     }})}};
   };
   await vm.runInContext("improvePrompt('simple')",h.context);
   assert.equal(h.query('#prompt').value,original);
   assert.equal(JSON.parse(store.get('popai.prompt-state')).undo.original,'Initial raw idea');
   assert.equal(h.query('#undo-enhance').hidden,false);
   assert.equal(h.query('#cancel-enhance').hidden,true);
   if(failure==='cancel')assert.ok(h.calls.some(call=>call.path==='/api/enhance/cancel'));
 }
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
 assert.ok(reloaded.calls.some(call=>call.path==='/api/jobs/'+id+'/discard' && call.options.method==='POST'));
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
test('decoded PNG can be downloaded and manually upscaled without regeneration',async()=>{
 const id='c'.repeat(32), dimensions=[960,544], image=`/images/${id}.png`;
 const job={state:'done',id,image,width:1920,height:1080,image_width:960,image_height:544,can_upscale:true};
 const h=harness(job,dimensions);await tick();
 const button=h.query('#retry-finalize'), cancel=h.query('#cancel-generation');
 assert.equal(h.query('#wallpaper').hidden,false);
 assert.equal(h.query('#save').href,image);
 assert.equal(button.hidden,false);
 assert.equal(button.textContent,'Upscale');
 assert.equal(cancel.hidden,true);
 await button.events.click();
 assert.equal(button.hidden,true);
 assert.equal(cancel.hidden,false);
 assert.equal(h.calls.at(-1).path,`/api/jobs/${id}/retry-finalize`);
 assert.equal(h.calls.some(c=>c.path==='/api/generate'),false);
 Object.assign(job,{state:'running',phase:'upscaling'});
 await h.timers.shift()();
 assert.equal(h.query('#wallpaper').hidden,false);
 assert.equal(h.query('#save').href,image);
 assert.equal(h.query('#generation-preview').hidden,true);
 Object.assign(job,{state:'done',phase:'done',upscale_cancelled:true});
 await h.timers.shift()();
 assert.equal(button.hidden,false);
 assert.match(h.query('#status').textContent,/Upscale canceled/);
 await button.events.click();
 dimensions[0]=1920;dimensions[1]=1080;
 Object.assign(job,{state:'done',phase:'done',can_upscale:false,upscale_cancelled:false,image:image+'?v=upscaled',image_width:1920,image_height:1080});
 await h.timers.shift()();await tick();
 assert.equal(h.query('#save').href,job.image);
 assert.equal(h.query('#wallpaper').src,job.image);
 assert.equal(button.hidden,true);
 assert.equal(cancel.hidden,true);
});
test('small images cover the viewport without changing their aspect ratio or download',async()=>{
 const id='f'.repeat(32),image=`/images/${id}.png`;
 const h=harness({state:'done',id,image,image_width:256,image_height:144,can_upscale:true},[256,144],false,39,new Map(),new Map(),({query})=>{
   Object.assign(query('#image-viewport'),{clientWidth:1366,clientHeight:768});
 });
 await tick();
 let result=h.query('#wallpaper');
 assert.equal(result.hidden,false);
 assert.equal(parseFloat(result.style.width),1366);
 assert.ok(parseFloat(result.style.height)>=768);
 assert.ok(Math.abs(parseFloat(result.style.width)/parseFloat(result.style.height)-256/144)<1e-9);
 assert.equal(h.query('#save').href,image);
 Object.assign(h.query('#image-viewport'),{clientWidth:390,clientHeight:844});
 vm.runInContext('resizeImageView()',h.context);
 assert.equal(parseFloat(result.style.height),844);
 assert.ok(parseFloat(result.style.width)>=390);
 assert.ok(Math.abs(parseFloat(result.style.width)/parseFloat(result.style.height)-256/144)<1e-9);
});
test('wrong final resolution is rejected',async()=>{
 const h=await completedHarness({state:'done',id:'wrong',image:'/images/wrong.png'},[768,448]);await tick();assert.equal(h.query('#save').hidden,true);assert.equal(h.query('#prompt').disabled,false);
});
test('Qwen CLI progress distinguishes reference reading, sampling and decoding',async()=>{
 const h=harness({state:'running',phase:'generating',profile:'qwen-image21-experimental',
     reference_ids:['f'.repeat(32)],elapsed:21,progress:{stage:'conditioning'}});
 await tick();
 assert.match(h.query('#status').textContent,/Preparing generation/);
 assert.equal(h.query('#eta-arc').hidden,true);
 const job={id:'qwen-live',state:'running',phase:'generating',elapsed:48,
     progress:{stage:'sampling',unit:'steps',completed:3,total:8,remaining_seconds:65}};
 const streaming=harness(job);
 await tick();
 assert.match(streaming.query('#estimate-message').textContent,/3\/8 steps.*1min 5s/);
 assert.doesNotMatch(streaming.query('#estimate-message').textContent,/then decode|upscale/);
 assert.equal(streaming.query('#eta-arc').hidden,false);
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

test('visible corrector stays for three seconds while enhancer text buffers',async()=>{
 const h=harness({state:'idle'});await tick();
 const run=code=>vm.runInContext(code,h.context);
 run("resetThoughts();setMascotPhase('corrector')");
 assert.equal(h.query('#thought-popup').hidden,true);
 run("appendThought('corrector','   ')");assert.equal(h.query('#thought-popup').hidden,true);
 run("appendAnswer('corrector','Corrected.');setMascotPhase('enhancer');appendThought('enhancer','Reasoning')");
 assert.equal(run('thoughtDisplayPhase'),'corrector');
 h.advance(2999);assert.equal(run('thoughtDisplayPhase'),'corrector');
 h.advance(1);assert.equal(run('thoughtDisplayPhase'),'enhancer');
 assert.equal(h.query('#thought-popup').hidden,false);
 run("appendAnswer('enhancer','Final.');finishThoughts(true)");
 h.advance(2999);assert.equal(h.query('#thought-popup').hidden,false);
 h.advance(1);assert.equal(h.query('#thought-popup').hidden,true);
 run("resetThoughts();setMascotPhase('corrector');appendAnswer('corrector','Corrected.');setMascotPhase('enhancer');appendAnswer('enhancer','Final.');finishThoughts(true)");
 assert.equal(run('thoughtDisplayPhase'),'corrector');
 h.advance(3000);assert.equal(run('thoughtDisplayPhase'),'enhancer');
 h.advance(3000);assert.equal(h.query('#thought-popup').hidden,true);
});

test('generation instructions target only the indexed editor references',()=>{
 const h=harness({state:'idle',profile:'flux-2-klein'});
 const run=code=>vm.runInContext(code,h.context);
 const raw='Create a white-haired character';
 const imported={name:'Sketch 4:3'};
 const sketch={sketch:{version:1,items:[]}};
 const pose={sketch:{version:1,items:[{kind:'pose',x:1,y:2,w:3,h:4,png:'data:image/png;base64,AAAA'}]}};
 h.context.referenceFixtures=[imported,pose,sketch];
 const output=run("generationPrompt('Create a white-haired character',referenceFixtures)");
 assert.ok(output.startsWith(raw+'\n\n'));
 assert.match(output,/Use image 2 only as a guide for body poses/);
 assert.match(output,/Use image 3 as a guide for spatial layout/);
 assert.doesNotMatch(output,/image 1\b/);
 assert.equal(run("generationPrompt('Create a white-haired character',[referenceFixtures[0]])"),raw);
 assert.equal(run("generationPrompt('Create a white-haired character',[])"),raw);
});

test('prompt processing card expands independently and supports three persisted options', async()=>{
 const job={state:'idle',enhancer:{state:'stopped',options:{corrector:true,enhancer:false,lite:true}}};
 const h=harness(job);await tick();
 const run=code=>vm.runInContext(code,h.context);
 const panel=h.query('#prompt-processing-options');
 assert.equal(panel.hidden,true);
 h.query('#prompt-processing-toggle').events.click();
 assert.equal(panel.hidden,false);
 run('fillProcessingSettings(processingSettings)');
 assert.equal(h.query('#prompt-corrector-enabled').checked,true);
 assert.equal(h.query('#prompt-enhancer-enabled').checked,false);
 assert.equal(h.query('#prompt-lite-enabled').checked,true);
 assert.equal(h.query('#prompt-processing-summary').textContent,'Lite');
 h.query('#prompt').value='A cat';
 assert.equal(run('canImprovePrompt()'),true);
 vm.runInContext('setBusy()',h.context);
 assert.equal(h.query('#enhance-prompt').title,'Enhance prompt');
 assert.equal(run("allowedPromptMode('cinematic')"),true);
 assert.equal(run("allowedPromptMode('corrector')"),false);
 h.query('#prompt-corrector-enabled').checked=false;
 h.query('#prompt-corrector-enabled').events.change();
 assert.equal(h.query('#prompt-processing-summary').textContent,'Lite');
 assert.equal(run('processingDraft().corrector'),false);
 job.enhancer.options={corrector:false,enhancer:false,lite:true};
 await h.timers.shift()();
 assert.equal(run('canImprovePrompt()'),true);
 assert.equal(h.query('#enhance-control').hidden,false);
 h.query('#prompt-processing-toggle').events.click();
 assert.equal(panel.hidden,true);
});

test('stale server cannot expose or execute prompt processing modes',async()=>{
 const h=harness({state:'idle',legacy:true,enhancer:{state:'stopped'}});
 await tick();
 h.query('#prompt').value='A cat';
 const run=code=>vm.runInContext(code,h.context);
 assert.equal(run('canImprovePrompt()'),false);
 assert.equal(h.query('#enhance-control').hidden,true);
 assert.equal(h.query('#model-apply').disabled,true);
 await run("improvePrompt('cinematic')");
 assert.equal(h.calls.filter(c=>c.path==='/api/enhance').length,0);
});

test('wand offers every enhancer mode regardless of thinking settings',async()=>{
 for(const [corrector,enhancer] of [[true,false],[true,true],[false,true],[false,false]]){
  const modes=[];
  const h=harness({state:'idle',enhancer:{state:'stopped',options:{corrector,enhancer,lite:false}}},undefined,false,39,new Map(),new Map(),({query,element})=>{
    for(const mode of ['simple','detailed','creative','cinematic']){
      const button=element();button.dataset.mode=mode;modes.push(button);
    }
    query('#enhance-options').querySelectorAll=()=>modes;
    query('#enhance-options').querySelector=()=>modes.find(b=>!b.hidden&&!b.disabled);
  });
  await tick();
  h.query('#prompt').value='A cat';
  vm.runInContext('setBusy()',h.context);
  const wand=h.query('#enhance-prompt'),menu=h.query('#enhance-options');
  assert.ok(modes.every(b=>!b.hidden&&!b.disabled));
  h.query('#enhance-control').events.pointerenter({pointerType:'mouse'});
  assert.equal(menu.hidden,false);
  await wand.events.click();
  assert.equal(h.calls.filter(c=>c.path==='/api/enhance').length,0);
  assert.equal(menu.hidden,false);
  assert.equal(vm.runInContext("allowedPromptMode('corrector')",h.context),false);
  await vm.runInContext("improvePrompt('corrector')",h.context);
  assert.equal(h.calls.filter(c=>c.path==='/api/enhance').length,0);
 }
});

test('startup preload switch belongs to generation profile and follows busy state',()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 assert.match(html,/id="preload-model" type="checkbox" role="switch"/);
 assert.match(html,/Preload on startup/);
 const h=harness({state:'idle'});
 const run=code=>vm.runInContext(code,h.context);
 run('setBusy(true)');
 assert.equal(h.query('#preload-model').disabled,true);
 run('setBusy(false)');
 assert.equal(h.query('#preload-model').disabled,false);
});

test('generation preview blur follows the saved setting and leaves the preview available',async()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 assert.match(html,/id="blur-generation-preview" type="checkbox" checked/);
 assert.ok(html.indexOf('id="blur-generation-preview"')<html.indexOf('id="prompt-processing-card"'));
 const css=fs.readFileSync('web/style.css','utf8');
 assert.match(css,/#generation-preview\.unblurred img\{[^}]*filter:none;[^}]*animation:none/);
 assert.match(css,/#generation-preview\.unblurred::before,#generation-preview\.unblurred::after\{display:none/);
 const job={state:'idle',blur_generation_preview:false};
 const h=harness(job);let unblurred;
 h.query('#generation-preview').classList.toggle=(name,value)=>{if(name==='unblurred')unblurred=value;};
 await tick();
 assert.equal(unblurred,true);
 job.blur_generation_preview=true;
 await h.timers.shift()();
 assert.equal(unblurred,false);
 const run=code=>vm.runInContext(code,h.context);
 run('setBusy(true)');
 assert.equal(h.query('#blur-generation-preview').disabled,true);
 run('setBusy(false)');
 assert.equal(h.query('#blur-generation-preview').disabled,false);
});
